using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

// Windows kernel TCP/IP and UDP/IP send/receive events contain a PID and byte count.
// Schema: https://learn.microsoft.com/windows/win32/etw/tcpip and /udpip.
// The trace is real-time only. No packet payload, addresses, ports, or executable paths are exported.
internal static class AppTraffic {
    const uint RealTime = 0x00000100;
    const uint SystemLogger = 0x02000000;
    const uint NoPerProcessorBuffers = 0x10000000;
    const uint ProcessEventRecords = 0x10000000;
    const uint NetworkTcpIp = 0x00010000;
    const uint NoSystemConfiguration = 0x10000000;
    const uint WnodeTracedGuid = 0x00020000;
    const uint Query = 0, Stop = 1;
    const int MaxPids = 1024, MaxRows = 256, FrameMilliseconds = 2000;
    static readonly Guid TcpIp = new Guid("9a280ac0-c8e0-11d1-84e2-00c04fb998a2");
    static readonly Guid UdpIp = new Guid("bf3a50c5-a9c9-4988-a005-2df0b7c80f80");

    [StructLayout(LayoutKind.Sequential)]
    struct WnodeHeader {
        public uint BufferSize, ProviderId;
        public ulong HistoricalContext;
        public long TimeStamp;
        public Guid Guid;
        public uint ClientContext, Flags;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct TraceProperties {
        public WnodeHeader Wnode;
        public uint BufferSize, MinimumBuffers, MaximumBuffers, MaximumFileSize, Mode, FlushTimer;
        public uint EnableFlags;
        public int AgeLimit;
        public uint NumberOfBuffers, FreeBuffers, EventsLost, BuffersWritten, LogBuffersLost, RealTimeBuffersLost;
        public IntPtr LoggerThreadId;
        public uint LogFileNameOffset, LoggerNameOffset;
    }

    // These two opaque embedded structures only reserve the Win32 x64 ABI layout.
    [StructLayout(LayoutKind.Sequential, Size = 88)] struct ClassicEvent { }
    [StructLayout(LayoutKind.Sequential, Size = 280)] struct LogfileHeader { }

    [StructLayout(LayoutKind.Sequential)]
    struct TraceLogfile {
        public IntPtr LogFileName, LoggerName;
        public long CurrentTime;
        public uint BuffersRead, ProcessTraceMode;
        public ClassicEvent CurrentEvent;
        public LogfileHeader Header;
        public IntPtr BufferCallback;
        public uint BufferSize, Filled, EventsLost;
        public IntPtr EventRecordCallback;
        public uint IsKernelTrace;
        public IntPtr Context;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct EventHeader {
        public ushort Size, HeaderType, Flags, Property;
        public uint ThreadId, ProcessId;
        public long TimeStamp;
        public Guid Provider;
        public ushort EventId;
        public byte Version, Channel, Level, Opcode;
        public ushort Task;
        public ulong Keyword, ProcessorTime;
        public Guid ActivityId;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct EventRecord {
        public EventHeader Header;
        public uint BufferContext;
        public ushort ExtendedDataCount, UserDataLength;
        public IntPtr ExtendedData, UserData, UserContext;
    }

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    delegate void EventRecordCallback(ref EventRecord record);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    static extern uint StartTraceW(out ulong session, string name, IntPtr properties);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    static extern uint ControlTraceW(ulong session, string name, IntPtr properties, uint control);
    [DllImport("advapi32.dll", SetLastError = true, ExactSpelling = true)]
    static extern ulong OpenTraceW(ref TraceLogfile logfile);
    [DllImport("advapi32.dll", ExactSpelling = true)]
    static extern uint ProcessTrace([In] ulong[] handles, uint count, IntPtr start, IntPtr end);
    [DllImport("advapi32.dll", ExactSpelling = true)]
    static extern uint CloseTrace(ulong handle);
    [DllImport("kernel32.dll", ExactSpelling = true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    static extern bool QueryFullProcessImageNameW(IntPtr process, uint flags, StringBuilder path, ref uint size);
    [DllImport("kernel32.dll", ExactSpelling = true)]
    static extern bool CloseHandle(IntPtr handle);

    sealed class Counters {
        public long Down, Up;
    }

    sealed class AppRow {
        public string id, name;
        public long down, up;
    }

    sealed class Collector {
        readonly object gate = new object();
        Dictionary<int, Counters> pending = new Dictionary<int, Counters>();
        readonly Dictionary<int, Identity> identities = new Dictionary<int, Identity>();

        sealed class Identity {
            public string Id, Name;
            public int Expires;
        }

        public void Receive(ref EventRecord record) {
            // Use the PID in the event data. The header belongs to the thread logging it.
            EventHeader header = record.Header;
            if ((header.Flags & 0x0100) == 0 || header.Version < 1 || header.Version > 2 ||
                (header.Provider != TcpIp && header.Provider != UdpIp) ||
                record.UserDataLength < 8 || record.UserData == IntPtr.Zero) return;
            bool send = header.Opcode == 10 || header.Opcode == 26;
            if (!send && header.Opcode != 11 && header.Opcode != 27) return;
            int pid = Math.Max(0, Marshal.ReadInt32(record.UserData));
            uint size = unchecked((uint)Marshal.ReadInt32(record.UserData, 4));
            if (size == 0) return;
            lock (gate) {
                Counters count;
                if (!pending.TryGetValue(pid, out count)) {
                    if (pending.Count >= MaxPids) pid = 0;
                    if (!pending.TryGetValue(pid, out count)) pending[pid] = count = new Counters();
                }
                if (send) count.Up += size;
                else count.Down += size;
            }
        }

        public List<AppRow> Take() {
            Dictionary<int, Counters> frame;
            lock (gate) {
                frame = pending;
                if (frame.Count == 0) return new List<AppRow>();
                pending = new Dictionary<int, Counters>();
            }
            int now = Environment.TickCount;
            foreach (int expired in identities.Where(x => unchecked(now - x.Value.Expires) >= 0)
                                              .Select(x => x.Key).ToArray()) identities.Remove(expired);
            var totals = new Dictionary<string, AppRow>();
            foreach (var pair in frame) {
                Identity identity = Identify(pair.Key, now);
                AppRow row;
                if (!totals.TryGetValue(identity.Id, out row)) {
                    row = new AppRow { id = identity.Id, name = identity.Name };
                    totals.Add(identity.Id, row);
                }
                row.down += pair.Value.Down;
                row.up += pair.Value.Up;
            }
            var sorted = totals.Values.OrderByDescending(row => row.down + row.up).ToList();
            if (sorted.Count > MaxRows) {
                var other = new AppRow { id = "other", name = "其他进程" };
                foreach (AppRow row in sorted.Skip(MaxRows - 1)) { other.down += row.down; other.up += row.up; }
                sorted.RemoveRange(MaxRows - 1, sorted.Count - MaxRows + 1);
                sorted.Add(other);
            }
            return sorted;
        }

        Identity Identify(int pid, int now) {
            Identity identity;
            if (identities.TryGetValue(pid, out identity)) return identity;
            identity = new Identity { Id = "unknown", Name = "未识别进程", Expires = unchecked(now + 4000) };
            if (pid == 4) {
                identity.Id = "system";
                identity.Name = "System";
            } else if (pid > 0) {
                IntPtr process = OpenProcess(0x1000, false, pid); // PROCESS_QUERY_LIMITED_INFORMATION
                if (process != IntPtr.Zero) {
                    try {
                        var path = new StringBuilder(1024);
                        uint length = (uint)path.Capacity;
                        if (QueryFullProcessImageNameW(process, 0, path, ref length)) {
                            string fullPath = path.ToString();
                            identity.Name = Path.GetFileName(fullPath);
                            using (SHA256 sha = SHA256.Create()) {
                                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(fullPath.ToUpperInvariant()));
                                identity.Id = BitConverter.ToString(hash, 0, 16).Replace("-", "").ToLowerInvariant();
                            }
                            identity.Expires = unchecked(now + 15000);
                        }
                    } finally { CloseHandle(process); }
                }
            }
            if (identities.Count < MaxPids) identities[pid] = identity;
            return identity;
        }
    }

    static TraceProperties Properties(int size, int offset, bool start) {
        return new TraceProperties {
            Wnode = new WnodeHeader { BufferSize = (uint)size, Flags = WnodeTracedGuid, ClientContext = 1 },
            BufferSize = 32, MinimumBuffers = 4, MaximumBuffers = 32, FlushTimer = 1,
            Mode = RealTime | SystemLogger | NoPerProcessorBuffers,
            EnableFlags = NetworkTcpIp | NoSystemConfiguration,
            LoggerNameOffset = (uint)offset,
            LogFileNameOffset = start ? 0 : (uint)(offset + 1024)
        };
    }

    static void Write(JavaScriptSerializer json, object frame) {
        Console.WriteLine(json.Serialize(frame));
        Console.Out.Flush();
    }

    static int Fail(JavaScriptSerializer json, uint code) {
        Write(json, new { error = (code == 5 || code == 1314) ? "access" : "unavailable", code });
        return 1;
    }

    public static int Run() {
        var json = new JavaScriptSerializer();
        Console.OutputEncoding = new UTF8Encoding(false);
        if (IntPtr.Size != 8) return Fail(json, 50);
        try { return Capture(json); }
        catch (IOException) { return 0; } // Parent closed its pipe.
    }

    static int Capture(JavaScriptSerializer json) {
        string name = "BigFishDockAppTraffic-" + Guid.NewGuid().ToString("N");
        int offset = Marshal.SizeOf(typeof(TraceProperties));
        int size = offset + 2048; // Buffers for the returned logger and file names.
        IntPtr properties = Marshal.AllocHGlobal(size);
        IntPtr nativeName = IntPtr.Zero;
        ulong session = 0, trace = ulong.MaxValue;
        var collector = new Collector();
        EventRecordCallback callback = collector.Receive;
        Thread worker = null;
        using (var consumerStopped = new ManualResetEvent(false)) {
            try {
                Marshal.Copy(new byte[size], 0, properties, size);
                TraceProperties initial = Properties(size, offset, true);
                initial.Wnode.Guid = Guid.NewGuid();
                Marshal.StructureToPtr(initial, properties, false);
                uint error = StartTraceW(out session, name, properties);
                if (error != 0) { session = 0; return Fail(json, error); }
                nativeName = Marshal.StringToHGlobalUni(name);
                var logfile = new TraceLogfile {
                    LoggerName = nativeName, ProcessTraceMode = RealTime | ProcessEventRecords,
                    EventRecordCallback = Marshal.GetFunctionPointerForDelegate(callback)
                };
                trace = OpenTraceW(ref logfile);
                if (trace == ulong.MaxValue) return Fail(json, unchecked((uint)Marshal.GetLastWin32Error()));
                var handles = new[] { trace };
                uint consumeResult = 0;
                worker = new Thread(() => {
                    consumeResult = ProcessTrace(handles, 1, IntPtr.Zero, IntPtr.Zero);
                    try { consumerStopped.Set(); } catch (ObjectDisposedException) { }
                }) { IsBackground = true, Name = "App traffic ETW" };
                worker.Start();

                // A single byte or EOF on stdin stops only this trace session.
                var inputStopped = new ManualResetEvent(false);
                new Thread(() => {
                    try { Console.Read(); }
                    catch (IOException) { }
                    finally { inputStopped.Set(); }
                }) { IsBackground = true, Name = "App traffic stop signal" }.Start();

                var signals = new WaitHandle[] { inputStopped, consumerStopped };
                var time = Stopwatch.StartNew();
                double previous = 0;
                uint lost = 0, buffersLost = 0;
                while (true) {
                    int signal = WaitHandle.WaitAny(signals, FrameMilliseconds);
                    if (signal == 0) return 0;
                    if (signal == 1) return Fail(json, consumeResult == 0 ? 1062 : consumeResult);
                    double current = time.Elapsed.TotalSeconds;
                    List<AppRow> rows = collector.Take();
                    Marshal.StructureToPtr(Properties(size, offset, false), properties, false);
                    uint newLost = 0, newBuffersLost = 0;
                    if (ControlTraceW(session, null, properties, Query) == 0) {
                        var queried = (TraceProperties)Marshal.PtrToStructure(properties, typeof(TraceProperties));
                        newLost = unchecked(queried.EventsLost - lost);
                        newBuffersLost = unchecked(queried.RealTimeBuffersLost - buffersLost);
                        lost = queried.EventsLost;
                        buffersLost = queried.RealTimeBuffersLost;
                    }
                    Write(json, new { rows, elapsed = current - previous, lost = Math.Max(newLost, newBuffersLost) });
                    previous = current;
                }
            } finally {
                if (session != 0) {
                    Marshal.StructureToPtr(Properties(size, offset, false), properties, false);
                    ControlTraceW(session, null, properties, Stop);
                }
                if (trace != ulong.MaxValue) CloseTrace(trace);
                bool stopped = worker == null || worker.Join(2000);
                if (stopped && nativeName != IntPtr.Zero) Marshal.FreeHGlobal(nativeName);
                Marshal.FreeHGlobal(properties);
                GC.KeepAlive(callback);
            }
        }
    }
}
