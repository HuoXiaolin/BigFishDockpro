#include <windows.h>
#include <stdio.h>
#include <wchar.h>
/* Test-only child. Records its loaded CRT path, then waits for an owned stop file. */
int wmain(void) {
    wchar_t exe[32768], report[32768], stop[32768], dllpath[32768];
    GetModuleFileNameW(NULL, exe, 32768);
    swprintf(report, 32768, L"%ls.library.txt", exe);
    swprintf(stop, 32768, L"%ls.stop", exe);
    HMODULE crt = LoadLibraryW(L"VCRUNTIME140_1.dll");
    if (!crt) return 2;
    GetModuleFileNameW(crt, dllpath, 32768);
    char utf8[65536];
    int bytes = WideCharToMultiByte(CP_UTF8, 0, dllpath, -1, utf8, sizeof(utf8), NULL, NULL);
    FILE *file = _wfopen(report, L"wb");
    if (!file || bytes <= 0) return 3;
    fwrite(utf8, 1, bytes-1, file); fclose(file);
    for (int n=0; n<3000; ++n) {
        if (GetFileAttributesW(stop) != INVALID_FILE_ATTRIBUTES) break;
        Sleep(20);
    }
    FreeLibrary(crt);
    return 0;
}
