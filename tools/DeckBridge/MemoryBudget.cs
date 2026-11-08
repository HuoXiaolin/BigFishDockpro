using System.ComponentModel;
using System.Runtime.InteropServices;

internal static class MemoryBudget
{
    // Task Manager's private working set is part of this total. Leave the CLR,
    // WPF codecs and audio drivers room to commit native memory as needed.
    internal const long Bytes = 47L * 1024 * 1024;
    const uint HardMaximum = 0x00000004;

    [DllImport("kernel32", SetLastError = true)]
    static extern bool GetProcessWorkingSetSizeEx(nint process, out nuint minimum, out nuint maximum, out uint flags);
    [DllImport("kernel32", SetLastError = true)]
    static extern bool SetProcessWorkingSetSizeEx(nint process, nuint minimum, nuint maximum, uint flags);
    [DllImport("kernel32")]
    static extern nint GetCurrentProcess();

    internal static void Install()
    {
        nint process = GetCurrentProcess();
        if (!GetProcessWorkingSetSizeEx(process, out nuint minimum, out _, out _) ||
            !SetProcessWorkingSetSizeEx(process, minimum, (nuint)Bytes, HardMaximum))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }

    internal static long InstalledLimit()
    {
        if (!GetProcessWorkingSetSizeEx(GetCurrentProcess(), out _, out nuint maximum, out uint flags))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return (flags & HardMaximum) != 0 ? (long)maximum : 0;
    }
}
