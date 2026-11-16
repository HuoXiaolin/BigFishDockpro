#include <windows.h>
#include <shellapi.h>
int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int) {
    wchar_t name[256]{};
    if(!GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",name,256))return 96;
    auto desktop=OpenDesktopW(name,0,FALSE,0x01ff);
    if(!desktop||!SetThreadDesktop(desktop))return 97;
    int count=0;auto args=CommandLineToArgvW(GetCommandLineW(),&count);int result=2;
    if(count==3) {
        auto library=LoadLibraryW(args[1]);
        if(library) {
            auto probe=(int(WINAPI*)(PCWSTR))GetProcAddress(library,"BigFishShellProbe");
            if(probe)result=probe(args[2]);
            // XAML owns callbacks until process exit. Do not unload their DLL.
        }else result=95;
    }
    LocalFree(args);return result;
}
