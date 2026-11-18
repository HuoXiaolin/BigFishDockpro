// Limited to this user's built-in shell processes. No service, startup entry or elevation.
#include <windows.h>
#include <tlhelp32.h>
#include <shellapi.h>
#include <filesystem>
#include <string>
#include "container.h"

static int attach(DWORD pid,const std::wstring& kind) {
    DWORD ours=0,theirs=0;
    if(!ProcessIdToSessionId(GetCurrentProcessId(),&ours)||!ProcessIdToSessionId(pid,&theirs)||ours!=theirs)return 20;
    HANDLE process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_CREATE_THREAD|PROCESS_VM_OPERATION|PROCESS_VM_WRITE|PROCESS_VM_READ|SYNCHRONIZE,FALSE,pid);
    if(!process)return 21;
    wchar_t target[32768]{},system[32768]{};DWORD length=32768;
    bool valid=QueryFullProcessImageNameW(process,0,target,&length)&&GetWindowsDirectoryW(system,32768);
    auto expected=std::wstring(system)+L"\\SystemApps\\";
    auto name=std::filesystem::path(target).filename().wstring();
    auto systemHost=std::wstring(system)+L"\\System32\\ShellHost.exe";
    valid=valid && (_wcsnicmp(target,expected.c_str(),expected.size())==0 ||
        (kind==L"notifications"&&_wcsicmp(target,systemHost.c_str())==0));
    valid=valid && ((kind==L"start"&&(_wcsicmp(name.c_str(),L"StartMenuExperienceHost.exe")==0||_wcsicmp(name.c_str(),L"SearchHost.exe")==0)) ||
        (kind==L"notifications"&&(_wcsicmp(name.c_str(),L"ShellExperienceHost.exe")==0||_wcsicmp(name.c_str(),L"ShellHost.exe")==0)));
    if(!valid){CloseHandle(process);return 22;}
    wchar_t executable[32768];GetModuleFileNameW(nullptr,executable,32768);
    auto library=std::filesystem::path(executable).parent_path()/(kind==L"start"?L"BigFishStartStyle.dll":L"BigFishNotificationStyle.dll");
    if(!std::filesystem::is_regular_file(library)){CloseHandle(process);return 23;}
    auto eventName=BF_EventName(process,pid,BIGFISH_BUILD_ID);
    if(eventName.empty()){CloseHandle(process);return 28;}
    HANDLE signal=OpenEventW(EVENT_MODIFY_STATE,FALSE,eventName.c_str());
    if(signal){SetEvent(signal);CloseHandle(signal);CloseHandle(process);return 0;}
    auto text=library.wstring();SIZE_T bytes=(text.size()+1)*sizeof(wchar_t);
    void* remote=VirtualAllocEx(process,nullptr,bytes,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!remote){CloseHandle(process);return 24;}
    if(!WriteProcessMemory(process,remote,text.c_str(),bytes,nullptr)){VirtualFreeEx(process,remote,0,MEM_RELEASE);CloseHandle(process);return 25;}
    auto load=(LPTHREAD_START_ROUTINE)GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"LoadLibraryW");
    HANDLE thread=CreateRemoteThread(process,nullptr,0,load,remote,0,nullptr);
    DWORD wait=thread?WaitForSingleObject(thread,6000):WAIT_FAILED;
    DWORD loaded=0;
    if(thread&&wait==WAIT_OBJECT_0)GetExitCodeThread(thread,&loaded);
    if(wait==WAIT_OBJECT_0)VirtualFreeEx(process,remote,0,MEM_RELEASE);
    if(thread)CloseHandle(thread);CloseHandle(process);
    if(wait!=WAIT_OBJECT_0)return 26;
    if(!loaded)return 28;
    for(unsigned i=0;i<20;++i) {
        signal=OpenEventW(EVENT_MODIFY_STATE,FALSE,eventName.c_str());
        if(signal){SetEvent(signal);CloseHandle(signal);return 0;}
        Sleep(50);
    }
    return 27;
}
int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    int count=0;auto args=CommandLineToArgvW(GetCommandLineW(),&count);int result=2;
    if(count==4&&wcscmp(args[1],L"--attach")==0) {
        wchar_t* tail=nullptr;unsigned long id=wcstoul(args[2],&tail,10);
        if(id&&tail&&!*tail&&(wcscmp(args[3],L"start")==0||wcscmp(args[3],L"notifications")==0))result=attach(id,args[3]);
    } else if(count==2&&wcscmp(args[1],L"--self-test")==0)result=0;
    LocalFree(args);return result;
}
