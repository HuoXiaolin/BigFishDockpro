#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <wchar.h>
static wchar_t stop_file[32768];
static LRESULT CALLBACK proc(HWND w,UINT message,WPARAM a,LPARAM b){
    if(message==WM_TIMER && GetFileAttributesW(stop_file)!=INVALID_FILE_ATTRIBUTES)DestroyWindow(w);
    if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
    return DefWindowProcW(w,message,a,b);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE old,LPWSTR command,int show){
    wchar_t desktop[256];
    if(!GetEnvironmentVariableW(L"FISHDOCK_TEST_DESKTOP",desktop,256))return 2;
    HDESK handle=OpenDesktopW(desktop,0,FALSE,0x1ff);
    if(!handle || !SetThreadDesktop(handle))return 3;
    BOOL input=TRUE;DWORD needed=0;
    if(!GetUserObjectInformationW(handle,6,&input,sizeof(input),&needed) || input)return 4;
    int argc=0;LPWSTR* argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    if(argc!=3)return 5;
    wcsncpy(stop_file,argv[2],32767);
    WNDCLASSW cls={0};cls.hInstance=instance;cls.lpfnWndProc=proc;cls.lpszClassName=L"BigFishDockActivationFixture";
    if(!RegisterClassW(&cls))return 6;
    HWND window=CreateWindowW(cls.lpszClassName,L"Synthetic existing application",WS_OVERLAPPEDWINDOW,80,80,320,180,NULL,NULL,instance,NULL);
    if(!window)return 7;
    ShowWindow(window,SW_SHOWMINNOACTIVE);
    FILE* report=_wfopen(argv[1],L"w");
    if(!report)return 8;
    fprintf(report,"%llu %lu\n",(unsigned long long)(UINT_PTR)window,GetCurrentProcessId());fclose(report);
    SetTimer(window,1,100,NULL);
    MSG message;while(GetMessageW(&message,NULL,0,0)>0){TranslateMessage(&message);DispatchMessageW(&message);}
    LocalFree(argv);return 0;
}
