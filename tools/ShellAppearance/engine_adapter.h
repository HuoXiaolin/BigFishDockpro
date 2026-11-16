// BigFishDock native shell adapter. No Windhawk installation or network service.
#pragma once
#include <windows.h>
#include <shlobj.h>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <string>
#include <sstream>
#include <vector>
#include "MinHook.h"

#ifdef BIGFISH_START_ENGINE
#define WH_MOD_ID L"BigFishDock.Start"
static constexpr auto BF_KIND = L"start";
#else
#define WH_MOD_ID L"BigFishDock.Notifications"
static constexpr auto BF_KIND = L"notifications";
#endif
static HMODULE bf_module;
static HANDLE bf_config_event, bf_status_event;
static std::atomic<unsigned long> bf_matches{0}, bf_errors{0};
static std::mutex bf_settings_mutex;
static std::map<std::wstring, std::wstring> bf_settings;
static std::filesystem::path bf_root;
static bool bf_layout_pending = false;
static HANDLE bf_status_file;
static std::wstring bf_status_owner;

static std::wstring BF_Setting(const wchar_t* key) {
    std::lock_guard lock(bf_settings_mutex);
    auto it = bf_settings.find(key);
    return it == bf_settings.end() ? std::wstring{} : it->second;
}
static bool BF_LoadSettings() {
    auto file = bf_root / (std::wstring(BF_KIND) + L".ini");
    std::vector<wchar_t> values(131072);
    DWORD size = GetPrivateProfileSectionW(L"settings", values.data(), (DWORD)values.size(), file.c_str());
    if (!size || size >= values.size()-2) return false;
    std::map<std::wstring,std::wstring> next;
    for (auto p=values.data(); *p; p+=wcslen(p)+1) {
        std::wstring entry(p); auto split=entry.find(L'=');
        if (split!=std::wstring::npos) next.emplace(entry.substr(0,split),entry.substr(split+1));
    }
    std::lock_guard lock(bf_settings_mutex); bf_settings.swap(next); return true;
}
static PCWSTR Wh_GetStringSetting(PCWSTR format, ...) {
    wchar_t key[512]; va_list args; va_start(args,format);
    _vsnwprintf_s(key,512,_TRUNCATE,format,args); va_end(args);
    auto value=BF_Setting(key); auto result=new wchar_t[value.size()+1];
    memcpy(result,value.c_str(),(value.size()+1)*sizeof(wchar_t)); return result;
}
static void Wh_FreeStringSetting(PCWSTR value) { delete[] value; }
static void Wh_Log(PCWSTR format, ...) {
    // Deliberately avoid per-element logs, account data and upstream telemetry.
    if (wcsstr(format,L"Applying styles to") == format) {
        ++bf_matches; if (bf_status_event) SetEvent(bf_status_event);
    } else if (wcsncmp(format,L"Error",5) == 0) {
        ++bf_errors;
    }
}
static BOOL Wh_SetFunctionHook(void* target,void* hook,void** original) {
    auto result=MH_CreateHook(target,hook,original);
    return result==MH_OK || result==MH_ERROR_ALREADY_CREATED;
}
static long long Wh_GetIntValue(PCWSTR,long long fallback) { return fallback; }
static BOOL Wh_SetIntValue(PCWSTR,long long) { return TRUE; }
static size_t Wh_GetBinaryValue(PCWSTR,void*,size_t) { return 0; }
static BOOL Wh_SetBinaryValue(PCWSTR,const void*,size_t) { return TRUE; }
static DWORD Wh_GetModStoragePath(PWSTR buffer,DWORD capacity) {
    auto value=bf_root.wstring();
    if(value.size()+1>capacity)return 0;
    memcpy(buffer,value.c_str(),(value.size()+1)*sizeof(wchar_t));return (DWORD)value.size();
}
struct WH_GET_URL_CONTENT_OPTIONS {size_t optionsSize;PCWSTR targetFilePath;};
struct WH_URL_CONTENT {int statusCode;const char* data;size_t length;};
static const WH_URL_CONTENT* Wh_GetUrlContent(PCWSTR,const WH_GET_URL_CONTENT_OPTIONS*) {return nullptr;}
static void Wh_FreeUrlContent(const WH_URL_CONTENT*) {}
static void BF_LayoutPending() {bf_layout_pending=true;}

static void BF_Status(const char* state) noexcept {
    try {
        if(bf_root.empty())return;
        auto path=bf_root/(std::to_wstring(GetCurrentProcessId())+L".json");
        auto temporary=path;temporary+=L".tmp";
        std::ostringstream output;
        output << "{\"protocol\":1,\"pid\":" << GetCurrentProcessId()
               << ",\"owner_pid\":" << wcstoul(BF_Setting(L"owner_pid").c_str(),nullptr,10)
               << ",\"state\":\"" << state << "\",\"matches\":" << bf_matches.load()
               << ",\"errors\":" << bf_errors.load()
               << ",\"layout_pending\":" << (bf_layout_pending?"true":"false") << "}";
        auto key=L"status_handle_"+std::to_wstring(GetCurrentProcessId());
        auto incoming=BF_Setting(key.c_str());
        if(!incoming.empty()) {
            auto owner=BF_Setting(L"owner_pid")+L":"+BF_Setting(L"owner_start");
            if(owner!=bf_status_owner) {
                if(bf_status_file)CloseHandle(bf_status_file);
                bf_status_file=reinterpret_cast<HANDLE>(_wcstoui64(incoming.c_str(),nullptr,10));
                if(GetFileType(bf_status_file)!=FILE_TYPE_DISK)bf_status_file=nullptr;
                bf_status_owner=owner;
            }
            if(bf_status_file) {
                auto bytes=output.str();DWORD written=0;LARGE_INTEGER zero{};
                SetFilePointerEx(bf_status_file,zero,nullptr,FILE_BEGIN);
                if(WriteFile(bf_status_file,bytes.data(),(DWORD)bytes.size(),&written,nullptr)&&written==bytes.size())SetEndOfFile(bf_status_file);
            }
        } else {
            std::ofstream file(temporary,std::ios::binary|std::ios::trunc);file<<output.str();file.close();
            MoveFileExW(temporary.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
        }
    }catch(...){}
}
static bool BF_AllowedProcess() {
    wchar_t path[32768];if(!GetModuleFileNameW(nullptr,path,32768))return false;
    auto name=std::filesystem::path(path).filename().wstring();
#ifdef BIGFISH_START_ENGINE
    return _wcsicmp(name.c_str(),L"StartMenuExperienceHost.exe")==0;
#else
    return _wcsicmp(name.c_str(),L"ShellExperienceHost.exe")==0 || _wcsicmp(name.c_str(),L"ShellHost.exe")==0;
#endif
}
