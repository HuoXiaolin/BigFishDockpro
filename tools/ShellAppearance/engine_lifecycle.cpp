// Included after the pinned XAML styling implementation.
#include "container.h"
static DWORD BF_WorkerCore() {
    if(!BF_AllowedProcess())return 0;
    bool container=BF_IsContainer(GetCurrentProcess());
    if(container) {
        // The owner stages only these components/configs inside this package's
        // LocalState. No permission changes to the user's application data.
        wchar_t module[32768]{};if(!GetModuleFileNameW(bf_module,module,32768))return 0;
        bf_root=std::filesystem::path(module).parent_path().parent_path().parent_path();
    }else {
        PWSTR roaming=nullptr;
        if(FAILED(SHGetKnownFolderPath(FOLDERID_RoamingAppData,KF_FLAG_NO_PACKAGE_REDIRECTION,nullptr,&roaming)))return 0;
        bf_root=std::filesystem::path(roaming)/L"BigFishDock"/L"shell-appearance";
        CoTaskMemFree(roaming);
    }
    auto eventName=L"Local\\BigFishDock.ShellAppearance."+std::to_wstring(GetCurrentProcessId());
    bf_config_event=CreateEventW(nullptr,FALSE,FALSE,eventName.c_str());
    bf_status_event=CreateEventW(nullptr,FALSE,FALSE,nullptr);
    if(!bf_config_event||!bf_status_event)return 0;
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    MH_Initialize();
    bool active=false;HANDLE owner=nullptr;
    std::wstring ownerKey;
    for(;;) {
        bool loaded=BF_LoadSettings();
        DWORD ownerId=loaded?wcstoul(BF_Setting(L"owner_pid").c_str(),nullptr,10):0;
        auto nextKey=BF_Setting(L"owner_pid")+L":"+BF_Setting(L"owner_start");
        if(!container || nextKey!=ownerKey) {
            if(owner)CloseHandle(owner);
            owner=nullptr;ownerKey=nextKey;
            if(container) {
                auto key=L"owner_handle_"+std::to_wstring(GetCurrentProcessId());
                auto candidate=reinterpret_cast<HANDLE>(_wcstoui64(BF_Setting(key.c_str()).c_str(),nullptr,10));
                // A narrowly duplicated handle works even though the sandbox
                // cannot OpenProcess on its out-of-container owner.
                if(candidate&&GetProcessId(candidate)==ownerId)owner=candidate;
            }else if(ownerId)owner=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,ownerId);
        }
        FILETIME created{},exited{},kernel{},user{};
        auto stamp=_wcstoui64(BF_Setting(L"owner_start").c_str(),nullptr,10);
        bool sameOwner=owner && GetProcessTimes(owner,&created,&exited,&kernel,&user) &&
            stamp==((static_cast<unsigned long long>(created.dwHighDateTime)<<32)|created.dwLowDateTime);
        bool enabled=loaded && BF_Setting(L"enabled")==L"1" && sameOwner && WaitForSingleObject(owner,0)==WAIT_TIMEOUT;
        try {
            if(active&&!enabled) {
                Wh_ModUninit();MH_DisableHook(MH_ALL_HOOKS);MH_RemoveHook(MH_ALL_HOOKS);active=false;
            } else if(enabled) {
                bf_matches=0;bf_errors=0;bf_layout_pending=false;
                if(active)Wh_ModSettingsChanged();
                else if(Wh_ModInit()) {MH_EnableHook(MH_ALL_HOOKS);active=true;Wh_ModAfterInit();}
            }
            BF_Status(active?(bf_matches.load()?"applied":"waiting"):"restored");
        }catch(...) {++bf_errors;BF_Status("failed");}
        // Named event and owner process handles keep the idle backend asleep.
        for(;;) {
            HANDLE handles[]={bf_config_event,bf_status_event,owner};
            DWORD wait=WaitForMultipleObjects(owner?3:2,handles,FALSE,INFINITE);
            if(wait==WAIT_OBJECT_0)break;
            if(wait==WAIT_OBJECT_0+1) {
                // Coalesce the initial visual-tree batch; no polling while idle.
                if(WaitForSingleObject(bf_config_event,100)==WAIT_OBJECT_0)break;
                BF_Status(active?(bf_matches.load()?"applied":"waiting"):"restored");
                continue;
            }
            if(wait==WAIT_OBJECT_0+2) {
                try {if(active){Wh_ModUninit();MH_DisableHook(MH_ALL_HOOKS);MH_RemoveHook(MH_ALL_HOOKS);active=false;}}catch(...){}
                CloseHandle(owner);owner=nullptr;BF_Status("restored");
                if(bf_status_file){CloseHandle(bf_status_file);bf_status_file=nullptr;}
                continue;
            }
            return 0;
        }
    }
}
static DWORD WINAPI BF_Worker(void*) {
    try {return BF_WorkerCore();}catch(...) {++bf_errors;BF_Status("failed");return 1;}
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) {
        bf_module=instance;DisableThreadLibraryCalls(instance);
        HANDLE worker=CreateThread(nullptr,0,BF_Worker,nullptr,0,nullptr);
        if(worker)CloseHandle(worker);
    }
    return TRUE;
}
