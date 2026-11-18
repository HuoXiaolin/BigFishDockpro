// No windows, hooks or injection. An owned AppContainer child checks transport.
#include <windows.h>
#include <sddl.h>
#include <aclapi.h>
#include <cstdint>
#include <filesystem>
#include <string>
#include <fstream>
#include "container.h"

static bool allowTestDesktop(PSID sid) {
    wchar_t name[256]{};GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",name,256);
    if(wcsncmp(name,L"Fishdock_Test_",14))return false;
    auto desktop=OpenDesktopW(name,0,FALSE,READ_CONTROL|WRITE_DAC|WRITE_OWNER|0x01ff);
    if(!desktop)return false;
    BOOL input=TRUE;DWORD size=0;
    if(!GetUserObjectInformationW(desktop,6,&input,sizeof(input),&size)||input){CloseDesktop(desktop);return false;}
    PACL old=nullptr,acl=nullptr;PSECURITY_DESCRIPTOR sd=nullptr;
    bool ok=GetSecurityInfo(desktop,SE_WINDOW_OBJECT,DACL_SECURITY_INFORMATION,nullptr,nullptr,&old,nullptr,&sd)==ERROR_SUCCESS;
    EXPLICIT_ACCESSW access{};access.grfAccessPermissions=0x01ff;access.grfAccessMode=GRANT_ACCESS;
    access.Trustee.TrusteeForm=TRUSTEE_IS_SID;access.Trustee.TrusteeType=TRUSTEE_IS_USER;access.Trustee.ptstrName=(LPWSTR)sid;
    if(ok)ok=SetEntriesInAclW(1,&access,old,&acl)==ERROR_SUCCESS&&SetSecurityInfo(desktop,SE_WINDOW_OBJECT,DACL_SECURITY_INFORMATION,nullptr,nullptr,acl,nullptr)==ERROR_SUCCESS;
    if(acl)LocalFree(acl);if(sd)LocalFree(sd);
    PSECURITY_DESCRIPTOR low=nullptr;
    if(ok&&ConvertStringSecurityDescriptorToSecurityDescriptorW(L"S:(ML;;NW;;;LW)",1,&low,nullptr)) {
        SECURITY_INFORMATION info=LABEL_SECURITY_INFORMATION;ok=SetUserObjectSecurity(desktop,&info,low);LocalFree(low);
    }else ok=false;
    CloseDesktop(desktop);return ok;
}

static std::filesystem::path iniFile(const std::filesystem::path& folder, bool start) {
    return folder/(start?L"start." BIGFISH_BUILD_ID L".ini":L"notifications." BIGFISH_BUILD_ID L".ini");
}

static bool report(const std::filesystem::path& ini,const std::string& data) {
    wchar_t value[64]{};GetPrivateProfileStringW(L"settings",L"status_handle",L"0",value,64,ini.c_str());
    HANDLE file=reinterpret_cast<HANDLE>(_wcstoui64(value,nullptr,10));
    DWORD written=0;bool ok=WriteFile(file,data.data(),(DWORD)data.size(),&written,nullptr)&&written==data.size();
    CloseHandle(file);return ok;
}

static int child(const std::filesystem::path& folder, bool start) {
    if(!BF_IsContainer(GetCurrentProcess()))return 31;
    auto ini=iniFile(folder,start);wchar_t text[64]{};
    GetPrivateProfileStringW(L"settings",L"owner_handle",L"0",text,64,ini.c_str());
    HANDLE owner=reinterpret_cast<HANDLE>(_wcstoui64(text,nullptr,10));
    DWORD pid=GetPrivateProfileIntW(L"settings",L"owner_pid",0,ini.c_str());
    DWORD actual=GetProcessId(owner),queryError=GetLastError();DWORD waitOwner=WaitForSingleObject(owner,0);
    if(!owner||actual!=pid||waitOwner!=WAIT_TIMEOUT) {
        report(ini,"{\"passed\":false,\"stage\":\"owner_handle\"}");
        return 32;
    }
    bool read_start_panel = false;
    if (start) {
        GetPrivateProfileStringW(L"settings", L"panel_geometry_handle", L"0", text, 64, ini.c_str());
        const auto handle = reinterpret_cast<HANDLE>(_wcstoui64(text, nullptr, 10));
        const auto view = static_cast<const uint64_t*>(MapViewOfFile(handle, FILE_MAP_READ, 0, 0, sizeof(uint64_t)));
        const auto writeView = MapViewOfFile(handle, FILE_MAP_WRITE, 0, 0, sizeof(uint64_t));
        read_start_panel = view && *view == 0x02c602800010ffe8ULL && !writeView;
        if (view) UnmapViewOfFile(view);
        if (writeView) UnmapViewOfFile(writeView);
        CloseHandle(handle);
        if (!read_start_panel) {
            report(ini, "{\"passed\":false,\"stage\":\"panel_geometry_handle\"}");
            return 38;
        }
    }
    auto module=LoadLibraryW((folder/(start?L"BigFishStartStyle.dll":L"BigFishNotificationStyle.dll")).c_str());
    if(!module)return 1000+(int)GetLastError();
    auto probe=(int(WINAPI*)(PCWSTR))GetProcAddress(module,"BigFishShellTransportProbe");
    if(!probe||probe(folder.c_str()))return 37;
    auto name=L"Local\\"+BF_EventSuffix(GetCurrentProcessId(),BIGFISH_BUILD_ID);
    HANDLE event=CreateEventW(nullptr,FALSE,FALSE,name.c_str());if(!event)return 34;
    DWORD wait=WaitForSingleObject(event,5000);CloseHandle(event);CloseHandle(owner);
    if(wait!=WAIT_OBJECT_0)return 35;
    return report(ini, read_start_panel ?
        "{\"passed\":true,\"dll_loaded\":true,\"owner_wait_handle\":true,\"qualified_event\":true,\"start_panel_read_only\":true}" :
        "{\"passed\":true,\"dll_loaded\":true,\"owner_wait_handle\":true,\"qualified_event\":true}")?0:36;
}

int wmain(int count,wchar_t** args) {
    bool startMode=count==4&&wcscmp(args[3],L"start")==0;
    if(count==4&&wcscmp(args[1],L"--child")==0)return child(args[2],startMode);
    if((count!=3&&!startMode)||!GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",nullptr,0))return 2;
    PSID sid=nullptr;if(!ConvertStringSidToSidW(args[1],&sid))return 3;
    if(!allowTestDesktop(sid)){LocalFree(sid);return 9;}
    std::filesystem::path folder(args[2]);
    SECURITY_CAPABILITIES caps{};caps.AppContainerSid=sid;
    // Packaged hosts also carry their per-package capability (S-1-15-3-...),
    // which is the inherited ACL on their LocalState directory.
    std::wstring capability(args[1]);capability.replace(7,1,L"3");
    PSID packageCapability=nullptr;
    if(!ConvertStringSidToSidW(capability.c_str(),&packageCapability))return 3;
    SID_AND_ATTRIBUTES access{packageCapability,SE_GROUP_ENABLED};
    caps.Capabilities=&access;caps.CapabilityCount=1;
    SIZE_T bytes=0;InitializeProcThreadAttributeList(nullptr,1,0,&bytes);
    auto attrs=reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(HeapAlloc(GetProcessHeap(),0,bytes));
    if(!attrs||!InitializeProcThreadAttributeList(attrs,1,0,&bytes))return 4;
    if(!UpdateProcThreadAttribute(attrs,0,PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,&caps,sizeof(caps),nullptr,nullptr))return 5;
    STARTUPINFOEXW start{};start.StartupInfo.cb=sizeof(start);start.lpAttributeList=attrs;
    wchar_t desktop[256]{};GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",desktop,256);start.StartupInfo.lpDesktop=desktop;
    PROCESS_INFORMATION process{};
    auto exe=folder/L"BigFishContainerProbe.exe";
    auto command=L"\""+exe.wstring()+L"\" --child \""+folder.wstring()+L"\""+(startMode?L" start":L" notifications");
    BOOL created=CreateProcessW(exe.c_str(),command.data(),nullptr,nullptr,FALSE,
        EXTENDED_STARTUPINFO_PRESENT|CREATE_SUSPENDED|CREATE_NO_WINDOW,nullptr,folder.c_str(),&start.StartupInfo,&process);
    DWORD error=GetLastError();DeleteProcThreadAttributeList(attrs);HeapFree(GetProcessHeap(),0,attrs);LocalFree(sid);LocalFree(packageCapability);
    if(!created){printf("CreateProcess error=%lu\n",error);return 6;}
    if (startMode) {
        auto mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(uint64_t), nullptr);
        auto view = static_cast<uint64_t*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, sizeof(uint64_t)));
        HANDLE remoteMapping = nullptr;
        if (view) *view = 0x02c602800010ffe8ULL;
        const bool shared = view && DuplicateHandle(GetCurrentProcess(), mapping, process.hProcess, &remoteMapping,
                                                     FILE_MAP_READ, FALSE, 0);
        if (view) UnmapViewOfFile(view);
        if (mapping) CloseHandle(mapping);
        if (!shared) {
            TerminateProcess(process.hProcess, 99);
            CloseHandle(process.hThread);
            CloseHandle(process.hProcess);
            return 11;
        }
        WritePrivateProfileStringW(L"settings", L"panel_geometry_handle",
            std::to_wstring(reinterpret_cast<uintptr_t>(remoteMapping)).c_str(), iniFile(folder, true).c_str());
    }
    HANDLE remote=nullptr;
    int result=7;
    if(DuplicateHandle(GetCurrentProcess(),GetCurrentProcess(),process.hProcess,&remote,SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,0)) {
        auto ini=iniFile(folder,startMode);
        HANDLE file=CreateFileW((folder/L"container-report.json").c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        HANDLE remoteFile=nullptr;
        bool shared=file!=INVALID_HANDLE_VALUE&&DuplicateHandle(GetCurrentProcess(),file,process.hProcess,&remoteFile,GENERIC_WRITE,FALSE,0);
        if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
        if(!shared){TerminateProcess(process.hProcess,99);CloseHandle(process.hThread);CloseHandle(process.hProcess);return 10;}
        WritePrivateProfileStringW(L"settings",L"status_handle",std::to_wstring(reinterpret_cast<uintptr_t>(remoteFile)).c_str(),ini.c_str());
        file=CreateFileW((folder/L"native-status.json").c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
        remoteFile=nullptr;
        shared=file!=INVALID_HANDLE_VALUE&&DuplicateHandle(GetCurrentProcess(),file,process.hProcess,&remoteFile,GENERIC_WRITE,FALSE,0);
        if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
        if(!shared){TerminateProcess(process.hProcess,99);CloseHandle(process.hThread);CloseHandle(process.hProcess);return 10;}
        auto statusKey=L"status_handle_"+std::to_wstring(process.dwProcessId);
        WritePrivateProfileStringW(L"settings",statusKey.c_str(),std::to_wstring(reinterpret_cast<uintptr_t>(remoteFile)).c_str(),ini.c_str());
        WritePrivateProfileStringW(L"settings",L"owner_start",L"transport-test",ini.c_str());
        WritePrivateProfileStringW(L"settings",L"owner_handle",std::to_wstring(reinterpret_cast<uintptr_t>(remote)).c_str(),ini.c_str());
        WritePrivateProfileStringW(L"settings",L"owner_pid",std::to_wstring(GetCurrentProcessId()).c_str(),ini.c_str());
        ResumeThread(process.hThread);
        auto name=BF_EventName(process.hProcess,process.dwProcessId,BIGFISH_BUILD_ID);
        for(int i=0;i<100;++i) {
            HANDLE event=OpenEventW(EVENT_MODIFY_STATE,FALSE,name.c_str());
            if(event){SetEvent(event);CloseHandle(event);break;}
            if(WaitForSingleObject(process.hProcess,50)==WAIT_OBJECT_0)break;
        }
        if(WaitForSingleObject(process.hProcess,6000)==WAIT_OBJECT_0) {
            DWORD code=99;GetExitCodeProcess(process.hProcess,&code);result=(int)code;
        }else result=8;
    }
    if(WaitForSingleObject(process.hProcess,0)!=WAIT_OBJECT_0){TerminateProcess(process.hProcess,99);WaitForSingleObject(process.hProcess,1000);}
    CloseHandle(process.hThread);CloseHandle(process.hProcess);return result;
}
