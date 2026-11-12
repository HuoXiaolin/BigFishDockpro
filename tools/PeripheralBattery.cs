// Windows USB HID discovery and read-only battery/status queries for known receivers.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using Microsoft.Win32.SafeHandles;

internal static class PeripheralBattery {
    const int MaxDevices = 12;
    const int MaxCollections = 192;
    const int MaxRequestChars = 32768;
    const int ReportLimit = 512;
    const int Pending = 997;
    const uint ReadWrite = 0xc0000000;
    const uint OverlappedFlag = 0x40000000;

    public sealed class Descriptor {
        public int vid { get; set; }
        public int pid { get; set; }
        public int revision { get; set; }
        public int usage_page { get; set; }
        public int usage { get; set; }
        public int input { get; set; }
        public int output { get; set; }
        public int feature { get; set; }
        public int @interface { get; set; } = -1;
        public int collection { get; set; } = -1;
        public string device_id { get; set; }
        public string receiver_id { get; set; }
        public string transport { get; set; }
        public string name { get; set; }
        public string protocol { get; set; }
        public string compatible_protocol { get; set; }
    }

    public sealed class Reading {
        public string id { get; set; }
        public string name { get; set; }
        public int? level { get; set; }
        public string state { get; set; }
        public bool approximate { get; set; }
    }

    sealed class Collection {
        internal string Path;
        internal Descriptor Info;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct InterfaceData {
        internal int Size;
        internal Guid ClassGuid;
        internal int Flags;
        internal IntPtr Reserved;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct DeviceData {
        internal int Size;
        internal Guid ClassGuid;
        internal uint Node;
        internal IntPtr Reserved;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct HidAttributes {
        internal int Size;
        internal ushort Vendor, Product, Revision;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct HidCaps {
        internal ushort Usage, UsagePage, Input, Output, Feature;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 26)]
        internal ushort[] Other;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct IoState {
        internal UIntPtr Status, Count;
        internal uint Offset, OffsetHigh;
        internal IntPtr Event;
    }

    [DllImport("hid.dll")]
    static extern void HidD_GetHidGuid(out Guid guid);
    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_GetAttributes(SafeFileHandle handle, ref HidAttributes attributes);
    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_GetPreparsedData(SafeFileHandle handle, out IntPtr data);
    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_FreePreparsedData(IntPtr data);
    [DllImport("hid.dll")]
    static extern int HidP_GetCaps(IntPtr data, out HidCaps caps);
    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_GetProductString(SafeFileHandle handle, [Out] byte[] value, uint size);
    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_SetFeature(SafeFileHandle handle, byte[] value, int length);
    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_GetFeature(SafeFileHandle handle, [In, Out] byte[] value, int length);
    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    static extern bool HidD_FlushQueue(SafeFileHandle handle);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr SetupDiGetClassDevsW(ref Guid guid, string enumerator, IntPtr parent, uint flags);
    [DllImport("setupapi.dll", SetLastError = true)]
    static extern bool SetupDiEnumDeviceInterfaces(IntPtr set, IntPtr device, ref Guid guid, uint index,
        ref InterfaceData data);
    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool SetupDiGetDeviceInterfaceDetailW(IntPtr set, ref InterfaceData data, IntPtr detail,
        int size, out int required, ref DeviceData device);
    [DllImport("setupapi.dll")]
    static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
    [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
    static extern uint CM_Get_Device_IDW(uint node, StringBuilder id, int capacity, uint flags);
    [DllImport("cfgmgr32.dll")]
    static extern uint CM_Get_Parent(out uint parent, uint node, uint flags);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security,
        uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool ReadFile(SafeFileHandle handle, IntPtr buffer, int count, IntPtr done, IntPtr overlapped);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool WriteFile(SafeFileHandle handle, IntPtr buffer, int count, IntPtr done, IntPtr overlapped);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetOverlappedResult(SafeFileHandle handle, IntPtr overlapped, out int count, bool wait);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CancelIoEx(SafeFileHandle handle, IntPtr overlapped);

    // All commands below are fixed queries. A configuration can select only an
    // adapter whose USB identity and HID collection match these constraints.
    sealed class Adapter {
        internal int Vid, Pid, Page, Usage, Interface, Collection, Input, Output, Feature;
        internal string Protocol, Name;
        internal bool Optional, Cable;

        internal Adapter(int vid, int pid, string name, string protocol, int page, int usage = -1,
            int @interface = -1, int input = 0, int output = 0, int feature = 0, bool optional = false,
            bool cable = false, int collection = -1) {
            Vid = vid; Pid = pid; Name = name; Protocol = protocol;
            Page = page; Usage = usage; Interface = @interface; Collection = collection; Input = input; Output = output;
            Feature = feature; Optional = optional; Cable = cable;
        }

        internal bool Match(Descriptor d) {
            return d.vid == Vid && d.pid == Pid && d.usage_page == Page
                && (Usage < 0 || d.usage == Usage) && (Interface < 0 || d.@interface == Interface)
                && (Collection < 0 || d.collection == Collection)
                && d.input >= Input && d.output >= Output && d.feature >= Feature
                && d.input <= ReportLimit && d.output <= ReportLimit && d.feature <= ReportLimit;
        }
    }

    // Protocol observations: HaloBattery docs/protocols.md and the linked captures.
    // Nova Pro also uses the status exchange documented by ChargeDock/HeadsetControl.
    static readonly Adapter[] Adapters = {
        new Adapter(0x3554, 0xf508, "Pulsar X2 V2 Mini", "compx-power", 0xff02, 2, input:17, output:17),
        new Adapter(0x3710, 0x5406, "Pulsar X2 CrazyLight Mini", "compx-power", 0xff02, 2, input:17, output:17),
        new Adapter(0x373b, 0x1085, "VXE R1 SE+", "compx-power", 0xff02, 2, input:17, output:17),
        new Adapter(0x3554, 0xf58a, "VXE R1 Pro Max", "compx-power", 0xff02, 2, input:17, output:17),
        new Adapter(0x3554, 0xf58e, "VXE R1 SE+", "compx-power", 0xff02, 2, input:17, output:17, optional:true),
        new Adapter(0x3770, 0x0200, "Hitscan Hyperlight", "compx-power", 0xff02, 2, input:17, output:17, optional:true),
        new Adapter(0x5253, 0x1020, "MCHOSE M7 Ultra", "mchose-status", 0xff01, 1, feature:21),
        new Adapter(0x3837, 0x100b, "MCHOSE A7 V2 Ultra", "mchose-status", 0xff01, 1, feature:21, optional:true),
        new Adapter(0x36a7, 0xa880, "WLmouse Beast X Max", "wlmouse-power", 0xffff, 0, feature:64),
        new Adapter(0x36a7, 0xa887, "WLmouse Beast X", "wlmouse-power", 0xffff, 0, feature:64, optional:true),
        new Adapter(0x36a7, 0xa868, "WLmouse Beast X Mini Pro", "wlmouse-power", 0xffff, 0, feature:64, optional:true),
        new Adapter(0x373e, 0x001e, "LAMZU Maya X", "wlmouse-power", 0xffff, 0, 2, feature:64),
        new Adapter(0x1e71, 0x2101, "NZXT Lift Elite Wireless", "nzxt-lift", 0xffca, 1, input:64, output:64),
        new Adapter(0x1038, 0x22a1, "SteelSeries Arctis Nova 7", "steelseries-nova7", 0xffc0, 1, 3, 5, 2),
        new Adapter(0x1038, 0x227e, "SteelSeries Arctis Nova 7 Gen 2", "steelseries-nova7", 0xffc0, 1, input:5, output:2, optional:true),
        new Adapter(0x1038, 0x12e0, "SteelSeries Arctis Nova Pro Wireless", "steelseries-nova-pro", 0xffc0, 1, input:16, output:64),
        new Adapter(0x1038, 0x12e5, "SteelSeries Arctis Nova Pro Wireless X", "steelseries-nova-pro", 0xffc0, 1, 4, 16, 64, optional:true),
        new Adapter(0x1038, 0x2244, "SteelSeries Arctis Nova Elite", "steelseries-nova-elite", 0xffc0, 1, 3, 16, 64),
        new Adapter(0x046d, 0xc547, "Logitech G502 X PLUS", "logitech-unified", 0xff00, input:20, output:20),
        new Adapter(0x0b05, 0x1a1a, "ROG 魔刃 X", "rog-chakram", 0xff01, 1, 0, 65, 65),
        new Adapter(0x0b05, 0x1a18, "ROG 魔刃 X", "rog-chakram", 0xff01, 1, 0, 65, 65, optional:true, cable:true),
        new Adapter(0x0b05, 0x1ace, "ROG 夜魔 OMNI", "rog-azoth-omni", 0xff00, 1, 2, 64, 64, collection:2),
        new Adapter(0x0b05, 0x1a83, "ROG 夜魔", "rog-azoth", 0xff00, 1, 1, 65, 65, optional:true, cable:true),
        new Adapter(0x0b05, 0x1a85, "ROG 夜魔", "rog-azoth", 0xff00, 1, 1, 65, 65, optional:true),
    };

    static SafeFileHandle Open(string path, uint access, uint flags = 0) {
        return CreateFileW(path, access, 3, IntPtr.Zero, 3, flags, IntPtr.Zero);
    }

    static string UsbRoot(uint node) {
        string root = null;
        for (int depth = 0; depth < 8; depth++) {
            var id = new StringBuilder(256);
            if (CM_Get_Device_IDW(node, id, id.Capacity, 0) != 0) break;
            string instance = id.ToString();
            if (instance.StartsWith(@"USB\VID_", StringComparison.OrdinalIgnoreCase)) {
                // Ignore the composite interface and stop at the first USB device.
                if (instance.IndexOf("&MI_", StringComparison.OrdinalIgnoreCase) < 0)
                    return instance;
                root = instance;
            } else if (root != null) break;
            if (CM_Get_Parent(out node, node, 0) != 0) break;
        }
        return root;
    }

    static string OpaqueId(SHA256 hash, string identity) {
        byte[] digest = hash.ComputeHash(Encoding.Unicode.GetBytes(identity.ToUpperInvariant()));
        return BitConverter.ToString(digest, 0, 16).Replace("-", "").ToLowerInvariant();
    }

    static int HexPart(string path, string marker) {
        int start = path.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        int value;
        start = start < 0 ? -1 : start + marker.Length;
        return start >= 0 && start + 2 <= path.Length &&
            Int32.TryParse(path.Substring(start, 2), NumberStyles.HexNumber,
                CultureInfo.InvariantCulture, out value) ? value : -1;
    }

    static string Name(SafeFileHandle handle, HidAttributes attributes) {
        var value = new byte[256];
        if (HidD_GetProductString(handle, value, (uint)value.Length)) {
            string name = Encoding.Unicode.GetString(value).Split('\0')[0];
            name = String.Concat(name.Where(ch => !Char.IsControl(ch))).Trim();
            if (name.Length > 0) return name.Length <= 96 ? name : name.Substring(0, 96);
        }
        return String.Format("USB HID {0:X4}:{1:X4}", attributes.Vendor, attributes.Product);
    }

    static Collection Describe(string path, string root, SHA256 hash, List<Descriptor> targets) {
        // Ignore unrelated collections before any descriptor I/O during polling.
        if (targets != null && !targets.Any(target => path.IndexOf(
                String.Format("vid_{0:x4}&pid_{1:x4}", target.vid, target.pid),
                StringComparison.OrdinalIgnoreCase) >= 0)) return null;
        using (var handle = Open(path, 0)) {
            if (handle.IsInvalid) return null;
            var attributes = new HidAttributes { Size = Marshal.SizeOf(typeof(HidAttributes)) };
            IntPtr preparsed;
            if (!HidD_GetAttributes(handle, ref attributes) || !HidD_GetPreparsedData(handle, out preparsed))
                return null;
            HidCaps caps;
            try {
                if (HidP_GetCaps(preparsed, out caps) != 0x00110000) return null;
            } finally { HidD_FreePreparsedData(preparsed); }

            var info = new Descriptor {
                vid = attributes.Vendor, pid = attributes.Product, revision = attributes.Revision,
                usage_page = caps.UsagePage, usage = caps.Usage,
                input = caps.Input, output = caps.Output, feature = caps.Feature,
                @interface = HexPart(path, "&mi_"), collection = HexPart(path, "&col"),
                device_id = OpaqueId(hash, path), receiver_id = OpaqueId(hash, root), transport = "usb"
            };
            var adapter = Adapters.FirstOrDefault(a => a.Match(info));
            if (adapter != null) {
                info.name = adapter.Name;
                info.transport = adapter.Cable ? "usb" : "2.4g";
                if (adapter.Optional) info.compatible_protocol = adapter.Protocol;
                else info.protocol = adapter.Protocol;
            } else {
                info.name = Name(handle, attributes);
            }
            return new Collection { Path = path, Info = info };
        }
    }

    static List<Collection> Enumerate(List<Descriptor> targets = null) {
        var rows = new List<Collection>();
        Guid guid;
        HidD_GetHidGuid(out guid);
        IntPtr set = SetupDiGetClassDevsW(ref guid, null, IntPtr.Zero, 0x12); // PRESENT | DEVICEINTERFACE
        if (set == new IntPtr(-1)) throw new InvalidOperationException("HID enumeration failed");
        try {
            using (var hash = SHA256.Create()) {
                for (uint i = 0; i < 512 && rows.Count < MaxCollections; i++) {
                    var data = new InterfaceData { Size = Marshal.SizeOf(typeof(InterfaceData)) };
                    if (!SetupDiEnumDeviceInterfaces(set, IntPtr.Zero, ref guid, i, ref data)) {
                        if (Marshal.GetLastWin32Error() == 259) break; // ERROR_NO_MORE_ITEMS
                        continue;
                    }
                    var device = new DeviceData { Size = Marshal.SizeOf(typeof(DeviceData)) };
                    int bytes;
                    SetupDiGetDeviceInterfaceDetailW(set, ref data, IntPtr.Zero, 0, out bytes, ref device);
                    if (bytes < 8 || bytes > 4096) continue;
                    IntPtr detail = Marshal.AllocHGlobal(bytes);
                    try {
                        Marshal.WriteInt32(detail, IntPtr.Size == 8 ? 8 : 6);
                        if (!SetupDiGetDeviceInterfaceDetailW(set, ref data, detail, bytes, out bytes, ref device))
                            continue;
                        string path = Marshal.PtrToStringUni(IntPtr.Add(detail, 4));
                        if (String.IsNullOrEmpty(path)) continue;
                        string root = UsbRoot(device.Node);
                        if (root == null) continue;
                        var row = Describe(path, root, hash, targets);
                        if (row != null) rows.Add(row);
                    } finally { Marshal.FreeHGlobal(detail); }
                }
            }
        } finally { SetupDiDestroyDeviceInfoList(set); }
        return rows;
    }

    internal static object Scan() {
        return Enumerate().Select(row => row.Info).ToArray();
    }

    static bool SameCollection(Descriptor a, Descriptor b) {
        return a.vid == b.vid && a.pid == b.pid && a.revision == b.revision &&
            a.usage_page == b.usage_page && a.usage == b.usage && a.@interface == b.@interface &&
            a.collection == b.collection && a.input == b.input && a.output == b.output && a.feature == b.feature;
    }

    static Reading Result(int? level, string state, bool approximate = false) {
        return new Reading { level = level, state = state, approximate = approximate };
    }

    static bool ValidId(string id) {
        return id != null && Regex.IsMatch(id, @"\A[0-9a-f]{32}\z");
    }

    internal static object Read() {
        var data = new char[MaxRequestChars + 1];
        int count;
        using (var input = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false), false))
            count = input.ReadBlock(data, 0, data.Length);
        if (count == 0 || count > MaxRequestChars) return new Reading[0];
        var requests = new JavaScriptSerializer { MaxJsonLength = MaxRequestChars, RecursionLimit = 8 }
            .Deserialize<List<Descriptor>>(new String(data, 0, count));
        if (requests == null || requests.Count > MaxDevices) return new Reading[0];
        requests = requests.Where(d => d != null && ValidId(d.device_id)).ToList();
        if (requests.Count == 0) return new Reading[0];
        var rows = Enumerate(requests);
        var results = new List<Reading>();
        var used = new HashSet<string>(StringComparer.Ordinal);
        foreach (var request in requests) {
            var adapter = Adapters.FirstOrDefault(a => a.Protocol == request.protocol && a.Match(request));
            Reading reading = Result(null, "unavailable");
            if (adapter != null) {
                var matches = rows.Where(row => SameCollection(row.Info, request)).ToArray();
                var match = matches.FirstOrDefault(row => row.Info.device_id == request.device_id);
                // Rebinding after a port change is safe only for an unambiguous live descriptor.
                if (match == null && matches.Length == 1 &&
                    !requests.Any(other => other.device_id == matches[0].Info.device_id))
                    match = matches[0];
                if (match == null) reading = Result(null, matches.Length == 0 ? "offline" : "unavailable");
                else if (used.Add(match.Info.device_id)) reading = QueryBounded(match, adapter);
            }
            reading.id = request.device_id;
            reading.name = adapter != null ? adapter.Name : "USB HID";
            results.Add(reading);
        }
        return results;
    }

    static Reading QueryBounded(Collection row, Adapter adapter) {
        // The driver owns the outstanding operation. A broken driver must not
        // hold up subsequent probes or our UI. The short-lived process provides
        // the outer deadline and releases any stuck handle on exit.
        var query = Task.Run(() => {
            try {
                using (var gate = new Mutex(false, @"Local\BigFishDock-Hid-" + row.Info.receiver_id)) {
                    bool acquired;
                    try { acquired = gate.WaitOne(0); }
                    catch (AbandonedMutexException) { acquired = true; }
                    if (!acquired) return Result(null, "busy");
                    try { return Query(row, adapter); }
                    finally { gate.ReleaseMutex(); }
                }
            }
            catch (Exception) { return Result(null, "unavailable"); }
        });
        return query.Wait(850) ? query.Result : Result(null, "unavailable");
    }

    static Reading Query(Collection row, Adapter adapter) {
        string protocol = adapter.Protocol;
        bool feature = protocol == "mchose-status" || protocol == "wlmouse-power";
        using (var handle = Open(row.Path, ReadWrite, feature ? 0 : OverlappedFlag)) {
            if (handle.IsInvalid) {
                int error = Marshal.GetLastWin32Error();
                return Result(null, error == 32 || error == 5 ? "busy" :
                    (error == 2 || error == 1167 ? "offline" : "unavailable"));
            }
            int length = row.Info.feature;
            if (protocol == "mchose-status") return ReadMchose(handle, length, row.Info.vid, row.Info.pid);
            if (protocol == "wlmouse-power") return ReadWlmouse(handle, length);

            HidD_FlushQueue(handle);
            if (protocol == "logitech-unified") return ReadLogitech(handle, row.Info);
            byte[] request;
            switch (protocol) {
                case "compx-power":
                    request = new byte[17]; request[0] = 0x08; request[1] = 0x04;
                    request[16] = 0x49; break;
                case "nzxt-lift": request = new byte[] { 0x4e, 0x02, 0x81, 0, 0xb0 }; break;
                case "steelseries-nova7": request = new byte[] { 0, 0xb0 }; break;
                case "steelseries-nova-pro": request = new byte[] { 0x06, 0xb0 }; break;
                case "steelseries-nova-elite": request = new byte[] { 0x01, 0xb0 }; break;
                case "rog-chakram": request = new byte[] { 0, 0x12, 0x07 }; break;
                case "rog-azoth-omni": request = new byte[] { 0x02, 0x12, 0x01 }; break;
                case "rog-azoth": request = new byte[] { 0, 0x12, 0x01 }; break;
                default: return Result(null, "unavailable");
            }
            var reply = Exchange(handle, row.Info, request, 420, (buffer, count) =>
                DecodeInterrupt(protocol, buffer, count) != null);
            return reply == null ? Result(null, "unavailable") : DecodeInterrupt(protocol, reply, reply.Length);
        }
    }

    static Reading DecodeInterrupt(string protocol, byte[] b, int n) {
        if (protocol == "compx-power" && n >= 17 && b[0] == 8 && b[1] == 4) {
            int sum = 0;
            for (int i = 0; i < 17; i++) sum += b[i];
            return (sum & 255) == 0x55 && b[6] <= 100 && b[7] <= 1
                ? Result(b[6], b[7] == 1 ? "charging" : "active") : null;
        }
        if (protocol == "nzxt-lift" && n >= 23 && b[0] == 0x4e && b[1] == 0x02 && b[2] == 0x97) {
            int value = b[17] | b[18] << 8;
            return value <= 100 ? Result(value, (b[22] & 1) != 0 ? "charging" : "active") : null;
        }
        if (protocol == "steelseries-nova7") {
            int i = n > 0 && b[0] == 0 ? 1 : 0; // Windows exposes the zero report ID.
            if (n < i + 4 || b[i] != 0xb0 || b[i + 1] != 0x03) return null;
            int level = b[i + 2], status = b[i + 3];
            if (status == 0) return Result(null, "offline");
            return level <= 100 ? Result(level, status == 1 || status == 2 ? "charging" : "active") : null;
        }
        if (protocol == "steelseries-nova-pro" && n >= 16 && b[0] == 0x06 && b[1] == 0xb0) {
            if (b[15] == 1) return Result(null, "offline", true);
            if (b[15] != 2 && b[15] != 8 || b[6] > 8) return null;
            return Result((b[6] * 100 + 4) / 8, b[15] == 2 ? "charging" : "active", true);
        }
        if (protocol == "steelseries-nova-elite" && n >= 16 && b[0] == 1 && b[1] == 0xb0) {
            if (b[14] == 1) return Result(null, "offline");
            if (b[14] == 4) return Result(null, "sleeping");
            if (b[6] > 100) return null;
            if (b[14] == 2 || b[15] == 2) return Result(b[6], "charging");
            if (b[14] == 8 && b[15] == 8) return Result(b[6], "active");
        }
        if (protocol == "rog-chakram" && n == 65 && b[0] == 0 && b[1] == 0x12 && b[2] == 7) {
            if (b[5] > 100) return null;
            if (b[5] == 0 && b[10] == 0) return Result(null, "unavailable");
            return Result(b[5], b[10] > 0 ? "charging" : "active");
        }
        if ((protocol == "rog-azoth-omni" || protocol == "rog-azoth") && n >= 10 &&
            b[0] == (protocol == "rog-azoth-omni" ? 2 : 0) && b[1] == 0x12 && b[2] == 1) {
            return b[6] <= 100 && b[9] <= 1 ? Result(b[6], b[9] == 1 ? "charging" : "active") : null;
        }
        return null;
    }

    static Reading ReadMchose(SafeFileHandle handle, int length, int vid, int pid) {
        bool sleeping = false;
        foreach (byte channel in new byte[] { 0x11, 0x12 }) {
            if (length < (channel == 0x11 ? 21 : 65)) continue;
            for (int attempt = 0; attempt < 3; attempt++) {
                byte[] request = Enumerable.Repeat((byte)0xff, length).ToArray();
                request[0] = channel;
                request[1] = 0xf9;
                var reply = ReadFeature(handle, request, channel, 24);
                if (reply == null || reply[0] != channel) continue;
                // A zero status from this receiver is observed during sleep.
                // An echo of the outgoing (inverted zero) request is not evidence.
                if (reply.Skip(1).All(value => value == 0)) { sleeping = true; continue; }
                if (reply[1] != 0xf9) continue;
                var payload = reply.Skip(2).Take(11).Select(value => value ^ 255).ToArray();
                int model = payload[2] | payload[3] << 8;
                if ((payload[0] | payload[1] << 8) != vid || (pid == 0x1020 && model != 0x0031)
                    || model == 0 || payload[9] > 100 || payload[10] > 1) continue;
                return Result(payload[9], payload[10] == 1 ? "charging" : "active");
            }
        }
        return Result(null, sleeping ? "sleeping" : "unavailable");
    }

    static Reading ReadWlmouse(SafeFileHandle handle, int length) {
        var request = new byte[length];
        request[3] = 2; request[4] = 2; request[6] = 0x83;
        if (!HidD_SetFeature(handle, request, request.Length)) return Result(null, "unavailable");
        for (int attempt = 0; attempt < 6; attempt++) {
            Thread.Sleep(50);
            var reply = new byte[length];
            if (!HidD_GetFeature(handle, reply, reply.Length)) continue;
            int i = reply[0] == 0 ? 1 : 0;
            if ((reply[i] == 0xa1 || reply[i] == 0xa2) && reply[i+1] == 0 &&
                reply[i+2] == 2 && reply[i+3] == 2 && reply[i+4] == 0 && reply[i+5] == 0x83 &&
                reply[i+6] <= 1 && reply[i+7] <= 100)
                return Result(reply[i+7], reply[i+6] == 1 ? "charging" : "active");
        }
        return Result(null, "unavailable");
    }

    static byte[] ReadFeature(SafeFileHandle handle, byte[] request, byte reportId, int gap) {
        if (!HidD_SetFeature(handle, request, request.Length)) return null;
        Thread.Sleep(gap);
        var response = new byte[request.Length];
        response[0] = reportId;
        return HidD_GetFeature(handle, response, response.Length) ? response : null;
    }

    static Reading ReadLogitech(SafeFileHandle handle, Descriptor d) {
        // Feature indices are assigned by each paired device. Resolve 0x1004
        // on slot one before using Unified Battery GET_CAPABILITIES / GET_STATUS.
        var root = Logitech(handle, d, 0, 0x09, 0x10, 0x04);
        if (root == null || root[4] == 0) return Result(null, "unavailable");
        byte index = root[4];
        var capabilities = Logitech(handle, d, index, 0x0a);
        if (capabilities == null || (capabilities[5] & 2) == 0) return Result(null, "unavailable");
        var reply = Logitech(handle, d, index, 0x1b);
        if (reply == null || reply[4] > 100) return Result(null, "unavailable");
        return Result(reply[4], reply[6] == 1 || reply[6] == 2 ? "charging" : "active");
    }

    static byte[] Logitech(SafeFileHandle handle, Descriptor d, byte feature, byte function,
        byte arg1 = 0, byte arg2 = 0) {
        return Exchange(handle, d, new byte[] { 0x11, 1, feature, function, arg1, arg2 }, 210,
            (b, n) => n >= 7 && b[0] == 0x11 && b[1] == 1 && b[2] == feature && b[3] == function);
    }

    static byte[] Exchange(SafeFileHandle handle, Descriptor d, byte[] command, int timeout,
        Func<byte[], int, bool> expected) {
        if (d.output < command.Length || d.input <= 0) return null;
        var timer = Stopwatch.StartNew();
        var request = new byte[d.output];
        Buffer.BlockCopy(command, 0, request, 0, command.Length);
        if (Transfer(handle, request, true, Math.Min(130, timeout)) != request.Length) return null;
        var buffer = new byte[d.input];
        for (int i = 0; i < 12; i++) {
            int remaining = timeout - (int)timer.ElapsedMilliseconds;
            if (remaining <= 0) break;
            int size = Transfer(handle, buffer, false, remaining);
            if (size <= 0) break;
            if (expected(buffer, size)) return buffer.Take(size).ToArray();
        }
        return null;
    }

    static int Transfer(SafeFileHandle handle, byte[] data, bool write, int timeout) {
        using (var ready = new EventWaitHandle(false, EventResetMode.ManualReset)) {
            var pinned = GCHandle.Alloc(data, GCHandleType.Pinned);
            IntPtr request = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(IoState)));
            try {
                Marshal.StructureToPtr(new IoState { Event = ready.SafeWaitHandle.DangerousGetHandle() },
                    request, false);
                IntPtr address = pinned.AddrOfPinnedObject();
                bool done = write ? WriteFile(handle, address, data.Length, IntPtr.Zero, request)
                    : ReadFile(handle, address, data.Length, IntPtr.Zero, request);
                if (!done) {
                    if (Marshal.GetLastWin32Error() != Pending) return 0;
                    if (!ready.WaitOne(timeout)) {
                        CancelIoEx(handle, request);
                        int ignored;
                        // Do not release the pinned buffer until the driver finishes cancellation.
                        GetOverlappedResult(handle, request, out ignored, true);
                        return 0;
                    }
                }
                int count;
                return GetOverlappedResult(handle, request, out count, false) ? count : 0;
            } finally {
                Marshal.FreeHGlobal(request);
                pinned.Free();
            }
        }
    }
}
