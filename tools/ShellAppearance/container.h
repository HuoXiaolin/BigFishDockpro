#pragma once
#include <windows.h>
#include <string>

static bool BF_IsContainer(HANDLE process) {
    HANDLE token=nullptr;DWORD value=0,size=0;
    if(!OpenProcessToken(process,TOKEN_QUERY,&token))return false;
    bool ok=GetTokenInformation(token,TokenIsAppContainer,&value,sizeof(value),&size);
    CloseHandle(token);return ok&&value;
}

static std::wstring BF_EventName(HANDLE process,DWORD pid) {
    std::wstring prefix=L"Local\\";
    if(BF_IsContainer(process)) {
        HANDLE token=nullptr;wchar_t path[1024]{};ULONG size=0;
        if(!OpenProcessToken(process,TOKEN_QUERY,&token))return {};
        BOOL ok=GetAppContainerNamedObjectPath(token,nullptr,1024,path,&size);
        CloseHandle(token);if(!ok)return {};
        prefix+=path;prefix+=L"\\";
    }
    return prefix+L"BigFishDock.ShellAppearance."+std::to_wstring(pid);
}
