// A real per-process commit budget. This does not trim the working set or force GC.
using System.ComponentModel;
using System.Runtime.InteropServices;

internal static class MemoryBudget
{
    internal const long Bytes = 50L * 1024 * 1024;
    static nint job;
    [StructLayout(LayoutKind.Sequential)]
    struct Basic
    {
        public long ProcessTime, JobTime;
        public uint Flags;
        public nuint MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcesses;
        public nuint Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct Limits
    {
        public Basic Basic;
        public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
        public nuint ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern nint CreateJobObjectW(nint security, string? name);
    [DllImport("kernel32", SetLastError = true)]
    static extern bool SetInformationJobObject(nint handle, int kind, ref Limits limits, uint length);
    [DllImport("kernel32", SetLastError = true)]
    static extern bool AssignProcessToJobObject(nint handle, nint process);
    [DllImport("kernel32", SetLastError = true)]
    static extern bool QueryInformationJobObject(nint handle, int kind, out Limits limits, uint length, nint returned);
    [DllImport("kernel32")] static extern nint GetCurrentProcess();
    [DllImport("kernel32")] static extern bool CloseHandle(nint handle);
    internal static void Install()
    {
        job = CreateJobObjectW(0, null);
        // Silent breakaway: the restriction is for this adapter, never a player it opens.
        var limits = new Limits { Basic = new Basic { Flags = 0x100 | 0x1000 }, ProcessMemory = (nuint)Bytes };
        if (job == 0 || !SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<Limits>()) || !AssignProcessToJobObject(job, GetCurrentProcess()))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }
    internal static void Close() { if (job != 0) { CloseHandle(job); job = 0; } }
    internal static long InstalledLimit()
    {
        if (!QueryInformationJobObject(job, 9, out var limits, (uint)Marshal.SizeOf<Limits>(), 0)) throw new Win32Exception();
        return (long)limits.ProcessMemory;
    }
}
