// BigFishDock native shell adapter. No Windhawk installation or network service.
#pragma once
#include <windows.h>
#include <shlobj.h>
#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <ranges>
#include <string>
#include <sstream>
#include <vector>
#include <utility>
#include "MinHook.h"

#ifdef BIGFISH_START_ENGINE
#define WH_MOD_ID L"BigFishDock.Start." BIGFISH_BUILD_ID
static constexpr auto BF_KIND = L"start";
#else
#define WH_MOD_ID L"BigFishDock.Notifications." BIGFISH_BUILD_ID
static constexpr auto BF_KIND = L"notifications";
static std::atomic<bool> bf_calendar_matched{false};
#endif
static constexpr std::wstring_view BF_BUILD = BIGFISH_BUILD_ID;
static HMODULE bf_module;
static HANDLE bf_config_event, bf_status_event;
static std::atomic<unsigned long> bf_matches{0}, bf_errors{0};
static std::atomic<unsigned long> bf_last_error{0};
static std::atomic<bool> bf_init_enabled{false};
static std::atomic<unsigned> bf_init_generation{0},bf_init_state{0},bf_init_attempts{0};
static thread_local UINT_PTR bf_init_timer=0;
static thread_local unsigned bf_thread_init_generation=0,bf_thread_init_attempts=0;
static void BF_CancelThreadInitialization() {
    if (bf_init_timer) KillTimer(nullptr,std::exchange(bf_init_timer,0));
}
#ifdef BIGFISH_START_ENGINE
static bool bf_is_start_menu = false;
static std::atomic<bool> bf_search_button_ready{false};
static std::atomic<unsigned> bf_start_width{0}, bf_start_height{0};
static std::atomic<int> bf_start_apps_inset{-1},bf_start_pinned_inset{-1};
static std::atomic<int> bf_start_apps_item_x{-1},bf_start_pinned_item_x{-1};
static std::atomic<int> bf_start_heading_x{-1},bf_start_letter_x{-1},bf_start_logo_x{-1},bf_start_row_width{-1};
static std::atomic<int> bf_start_scroll_right{-1},bf_start_apps_right{-1};
static constexpr int bf_unmeasured_center=-999999;
static std::atomic<int> bf_start_pin_title_delta{bf_unmeasured_center};
static std::atomic<int> bf_start_pin_icon_delta{bf_unmeasured_center},bf_start_pin_label_delta{bf_unmeasured_center};
static std::atomic<bool> bf_search_position_ready{false};
static std::atomic<uintptr_t> bf_startScreenBounds{0},bf_searchScreenBounds{0},bf_searchViewportBounds{0};
static std::atomic<uintptr_t> bf_searchInputBounds{0};
static std::atomic<int> bf_searchVisibleWidth{0},bf_searchVisibleHeight{0};
static std::atomic<bool> bf_search_view_seen{false}, bf_search_styles_ready{false};
static std::atomic<unsigned> bf_search_style_generation{0};
static std::mutex bf_panelGeometryMutex;
static HANDLE bf_panelGeometryHandle;
static uint64_t* bf_panelGeometry;

static RECT BF_DecodePanelRect(uintptr_t value) {
    const auto x=static_cast<int16_t>(value),y=static_cast<int16_t>(value>>16);
    return {x,y,x+static_cast<uint16_t>(value>>32),y+static_cast<uint16_t>(value>>48)};
}

static void BF_AppendPanelBounds(std::ostringstream& output,const char* key,uintptr_t value) {
    if (!value) return;
    const auto bounds=BF_DecodePanelRect(value);
    output<<",\""<<key<<"\":["<<bounds.left<<","<<bounds.top<<","<<bounds.right<<","<<bounds.bottom<<"]";
}

static void BF_UnbindPanelGeometry() {
    std::lock_guard lock(bf_panelGeometryMutex);
    if (bf_panelGeometry) UnmapViewOfFile(bf_panelGeometry);
    bf_panelGeometry = nullptr;
    bf_panelGeometryHandle = nullptr;
}

static void BF_BindPanelGeometry(HANDLE handle, bool writable) {
    std::lock_guard lock(bf_panelGeometryMutex);
    if (!handle || handle == bf_panelGeometryHandle) return;
    if (bf_panelGeometry) UnmapViewOfFile(bf_panelGeometry);
    bf_panelGeometryHandle = handle;
    bf_panelGeometry = static_cast<uint64_t*>(MapViewOfFile(handle, writable ? FILE_MAP_WRITE : FILE_MAP_READ, 0, 0, sizeof(uint64_t)));
    CloseHandle(handle); // The mapped view now owns the section reference.
}

static uintptr_t BF_ReadPanelGeometry() {
    std::lock_guard lock(bf_panelGeometryMutex);
    return bf_panelGeometry ? std::atomic_ref(*bf_panelGeometry).load() : 0;
}

static void BF_WritePanelGeometry(uintptr_t value) {
    std::lock_guard lock(bf_panelGeometryMutex);
    if (bf_panelGeometry && bf_is_start_menu) std::atomic_ref(*bf_panelGeometry).store(value);
}
#endif
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
static bool BF_StyleSettingsEqual(const std::map<std::wstring,std::wstring>& previous,
                                  const std::map<std::wstring,std::wstring>& next) {
    const auto transport=[](const std::wstring& key) {
        return key.starts_with(L"owner_") || key.starts_with(L"status_handle_") || key.starts_with(L"panel_geometry_");
    };
    for (const auto& [key,value]:previous) if (!transport(key)) {
        const auto found=next.find(key);
        if (found==next.end() || found->second!=value) return false;
    }
    for (const auto& [key,value]:next) if (!transport(key) && !previous.contains(key)) return false;
    return true;
}
static bool BF_LoadSettings(bool* changed=nullptr) {
    auto name = std::wstring(BF_KIND);
    if (!BF_BUILD.empty()) {name+=L".";name+=BF_BUILD;}
    auto file = bf_root / (name + L".ini");
    std::vector<wchar_t> values(131072);
    DWORD size = GetPrivateProfileSectionW(L"settings", values.data(), (DWORD)values.size(), file.c_str());
    if (!size || size >= values.size()-2) return false;
    std::map<std::wstring,std::wstring> next;
    for (auto p=values.data(); *p; p+=wcslen(p)+1) {
        std::wstring entry(p); auto split=entry.find(L'=');
        if (split!=std::wstring::npos) next.emplace(entry.substr(0,split),entry.substr(split+1));
    }
    std::lock_guard lock(bf_settings_mutex);
    // A new Search process only changes duplicated handles. Rebuilding all
    // Start styles for that bookkeeping briefly exposes the default menu.
    if (changed) *changed = !BF_StyleSettingsEqual(bf_settings,next);
    bf_settings.swap(next);
    return true;
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
        wchar_t message[512]{};va_list args;va_start(args,format);
        _vsnwprintf_s(message,512,_TRUNCATE,format,args);va_end(args);
        bf_last_error=wcstoul(message+5,nullptr,16);
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
        auto name=std::to_wstring(GetCurrentProcessId());
        if(!BF_BUILD.empty()) {name+=L".";name+=BF_BUILD;}
        auto path=bf_root/(name+L".json");
        auto temporary=path;temporary+=L".tmp";
        std::ostringstream output;
        output << "{\"protocol\":1,\"pid\":" << GetCurrentProcessId()
               << ",\"owner_pid\":" << wcstoul(BF_Setting(L"owner_pid").c_str(),nullptr,10)
               << ",\"state\":\"" << state << "\",\"matches\":" << bf_matches.load()
               << ",\"errors\":" << bf_errors.load()
               << ",\"last_error\":" << bf_last_error.load()
               << ",\"initialization\":" << bf_init_state.load()
               << ",\"initialization_attempts\":" << bf_init_attempts.load()
               << ",\"layout_pending\":" << (bf_layout_pending?"true":"false");
#ifdef BIGFISH_START_ENGINE
        if(bf_is_start_menu)output<<",\"search_button\":"<<(bf_search_button_ready.load()?"true":"false")
            <<",\"start_width\":"<<bf_start_width.load()<<",\"start_height\":"<<bf_start_height.load()
            <<",\"apps_inset_dip\":"<<bf_start_apps_inset.load()/100.0
            <<",\"pinned_inset_dip\":"<<bf_start_pinned_inset.load()/100.0
            <<",\"apps_item_x_dip\":"<<bf_start_apps_item_x.load()/100.0
            <<",\"pinned_item_x_dip\":"<<bf_start_pinned_item_x.load()/100.0;
        if (bf_is_start_menu && bf_start_heading_x.load()>=0)
            output<<",\"apps_heading_x_dip\":"<<bf_start_heading_x.load()/100.0
                  <<",\"apps_logo_x_dip\":"<<bf_start_logo_x.load()/100.0
                  <<",\"apps_row_width_dip\":"<<bf_start_row_width.load()/100.0;
        if (bf_is_start_menu && bf_start_letter_x.load()>=0)
            output<<",\"apps_letter_x_dip\":"<<bf_start_letter_x.load()/100.0;
        if (bf_is_start_menu && bf_start_scroll_right.load()>=0)
            output<<",\"apps_scrollbar_right_dip\":"<<bf_start_scroll_right.load()/100.0
                  <<",\"apps_column_right_dip\":"<<bf_start_apps_right.load()/100.0;
        if (bf_is_start_menu && bf_start_pin_icon_delta.load()!=bf_unmeasured_center)
            output<<",\"pinned_icon_center_delta_dip\":"<<bf_start_pin_icon_delta.load()/100.0;
        if (bf_is_start_menu && bf_start_pin_title_delta.load()!=bf_unmeasured_center)
            output<<",\"pinned_title_center_delta_dip\":"<<bf_start_pin_title_delta.load()/100.0;
        if (bf_is_start_menu && bf_start_pin_label_delta.load()!=bf_unmeasured_center)
            output<<",\"pinned_label_center_delta_dip\":"<<bf_start_pin_label_delta.load()/100.0;
        if(bf_search_view_seen.load())output<<",\"search_styles\":"<<(bf_search_styles_ready.load()?"true":"false");
        if(!bf_is_start_menu && bf_search_view_seen.load())
            output<<",\"search_position\":"<<(bf_search_position_ready.load()?"true":"false");
        BF_AppendPanelBounds(output,"start_bounds_px",bf_startScreenBounds.load());
        BF_AppendPanelBounds(output,"search_bounds_px",bf_searchScreenBounds.load());
        BF_AppendPanelBounds(output,"search_viewport_px",bf_searchViewportBounds.load());
        BF_AppendPanelBounds(output,"search_input_px",bf_searchInputBounds.load());
        if (!bf_is_start_menu && bf_searchVisibleWidth.load()>0)
            output<<",\"search_visible_size_px\":["<<bf_searchVisibleWidth.load()<<","<<bf_searchVisibleHeight.load()<<"]";
#else
        output<<",\"calendar_matched\":"<<(bf_calendar_matched.load()?"true":"false");
#endif
        output<<"}";
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
    bf_is_start_menu = _wcsicmp(name.c_str(),L"StartMenuExperienceHost.exe")==0;
    return bf_is_start_menu || _wcsicmp(name.c_str(),L"SearchHost.exe")==0;
#else
    return _wcsicmp(name.c_str(),L"ShellExperienceHost.exe")==0 || _wcsicmp(name.c_str(),L"ShellHost.exe")==0;
#endif
}
