// Declarative HID battery readers can obtain reports but cannot send commands.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

internal static partial class PeripheralBattery {
    const string CustomProtocol = "custom-read";
    const string GetFeatureMode = "get-feature";
    const string InputReportMode = "input-report";
    const uint ReadOnly = 0x80000000;

    sealed class ByteCheck {
        internal int Offset, Mask, Value;
    }

    sealed class ReportReader {
        internal string Mode;
        internal int ReportId, Length;
        internal List<ByteCheck> Match = new List<ByteCheck>();
        internal int LevelOffset, LevelMask, Shift, Maximum;
        internal int StatusOffset = -1, StatusMask;
        internal Dictionary<int, string> States = new Dictionary<int, string>();
    }

    public sealed class SampleResult {
        public string state { get; set; }
        public List<string> reports { get; set; }
    }

    static JavaScriptSerializer RequestSerializer() {
        return new JavaScriptSerializer { MaxJsonLength = MaxRequestChars, RecursionLimit = 12 };
    }

    static string ReadRequest() {
        var data = new char[MaxRequestChars + 1];
        int count;
        using (var input = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false), false))
            count = input.ReadBlock(data, 0, data.Length);
        return count > 0 && count <= MaxRequestChars ? new String(data, 0, count) : null;
    }

    static object Field(Dictionary<string, object> fields, string key) {
        object value;
        return fields.TryGetValue(key, out value) ? value : null;
    }

    static bool Number(Dictionary<string, object> fields, string key, int min, int max, out int result) {
        object value = Field(fields, key);
        result = value is int ? (int)value : min - 1;
        return result >= min && result <= max;
    }

    static bool VendorCollection(Descriptor device) {
        return device != null && ValidId(device.device_id) &&
            device.vid > 0 && device.vid <= UInt16.MaxValue &&
            device.pid >= 0 && device.pid <= UInt16.MaxValue &&
            device.revision >= 0 && device.revision <= UInt16.MaxValue &&
            device.usage_page >= 0xff00 && device.usage_page <= UInt16.MaxValue &&
            device.usage >= 0 && device.usage <= UInt16.MaxValue &&
            device.input >= 0 && device.input <= UInt16.MaxValue &&
            device.output >= 0 && device.output <= UInt16.MaxValue &&
            device.feature >= 0 && device.feature <= UInt16.MaxValue &&
            device.@interface >= -1 && device.@interface <= Byte.MaxValue &&
            device.collection >= -1 && device.collection <= Byte.MaxValue;
    }

    static int ReportLength(Descriptor device, string mode) {
        if (mode == GetFeatureMode) return device.feature;
        if (mode == InputReportMode) return device.input;
        return 0;
    }

    static ReportReader ParseReader(Descriptor device) {
        if (!VendorCollection(device) || device.reader == null) return null;
        var fields = device.reader;
        var reader = new ReportReader { Mode = Field(fields, "mode") as string };
        reader.Length = ReportLength(device, reader.Mode);
        if (reader.Length < 2 || reader.Length > ReportLimit ||
            fields.Keys.Any(key => key != "mode" && key != "report_id" &&
                key != "match" && key != "level" && key != "status") ||
            !Number(fields, "report_id", 0, 255, out reader.ReportId)) return null;

        var checks = Field(fields, "match") as IList;
        if (checks == null || checks.Count < 1 || checks.Count > 8) return null;
        foreach (object entry in checks) {
            var rule = entry as Dictionary<string, object>;
            var check = new ByteCheck();
            if (rule == null || rule.Count != 3 ||
                !Number(rule, "offset", 1, reader.Length - 1, out check.Offset) ||
                !Number(rule, "mask", 1, 255, out check.Mask) ||
                !Number(rule, "value", 0, 255, out check.Value) ||
                (check.Value & ~check.Mask) != 0) return null;
            reader.Match.Add(check);
        }

        var level = Field(fields, "level") as Dictionary<string, object>;
        if (level == null || level.Count != 4 ||
            !Number(level, "offset", 1, reader.Length - 1, out reader.LevelOffset) ||
            !Number(level, "mask", 1, 255, out reader.LevelMask) ||
            !Number(level, "shift", 0, 7, out reader.Shift) ||
            !Number(level, "maximum", 1, 255, out reader.Maximum) ||
            (reader.LevelMask & ((1 << reader.Shift) - 1)) != 0 ||
            reader.Maximum > (reader.LevelMask >> reader.Shift)) return null;

        if (fields.ContainsKey("status")) {
            var status = Field(fields, "status") as Dictionary<string, object>;
            if (status == null || status.Keys.Any(key => key != "offset" && key != "mask" &&
                    key != "charging" && key != "sleeping" && key != "offline") ||
                !Number(status, "offset", 1, reader.Length - 1, out reader.StatusOffset) ||
                !Number(status, "mask", 1, 255, out reader.StatusMask)) return null;
            foreach (string state in new[] { "charging", "sleeping", "offline" }) {
                if (!status.ContainsKey(state)) continue;
                var codes = Field(status, state) as IList;
                if (codes == null || codes.Count > 16) return null;
                foreach (object code in codes) {
                    if (!(code is int)) return null;
                    int value = (int)code;
                    if (value < 0 || value > 255 || (value & ~reader.StatusMask) != 0 ||
                        reader.States.ContainsKey(value)) return null;
                    reader.States.Add(value, state);
                }
            }
        }
        return reader;
    }

    static Reading DecodeCustom(ReportReader reader, byte[] report, int count) {
        if (count != reader.Length || report[0] != reader.ReportId ||
            reader.Match.Any(check => (report[check.Offset] & check.Mask) != check.Value)) return null;
        string state = "active";
        string reported;
        if (reader.StatusOffset >= 0 &&
            reader.States.TryGetValue(report[reader.StatusOffset] & reader.StatusMask, out reported))
            state = reported;
        if (state == "sleeping" || state == "offline") return Result(null, state);
        int raw = (report[reader.LevelOffset] & reader.LevelMask) >> reader.Shift;
        if (raw > reader.Maximum) return null;
        return Result((raw * 200 + reader.Maximum) / (2 * reader.Maximum), state, reader.Maximum != 100);
    }

    static string ReadFailure(int error) {
        return error == 32 || error == 5 ? "busy" :
            (error == 2 || error == 1167 ? "offline" : "unavailable");
    }

    static Reading QueryCustom(Collection row, ReportReader reader) {
        if (!VendorCollection(row.Info) || ReportLength(row.Info, reader.Mode) != reader.Length)
            return Result(null, "unavailable");
        Reading reading = null;
        string state = ReadReports(row, reader.Mode, reader.ReportId, reader.Length, 460, (report, count) => {
            reading = DecodeCustom(reader, report, count);
            return reading != null;
        });
        return reading ?? Result(null, state);
    }

    static string ReadReports(Collection row, string mode, int reportId, int length, int timeout,
        Func<byte[], int, bool> accept) {
        // No SetFeature/WriteFile path for imported profiles or sample capture.
        bool feature = mode == GetFeatureMode;
        using (var handle = Open(row.Path, ReadOnly, feature ? 0 : OverlappedFlag)) {
            if (handle.IsInvalid) return ReadFailure(Marshal.GetLastWin32Error());
            var report = new byte[length];
            if (feature) {
                report[0] = (byte)reportId;
                if (HidD_GetFeature(handle, report, report.Length) && report[0] == reportId &&
                    accept(report, report.Length)) return "active";
                return "unavailable";
            }
            var elapsed = Stopwatch.StartNew();
            for (int attempt = 0; attempt < 64; attempt++) {
                int remaining = timeout - (int)elapsed.ElapsedMilliseconds;
                if (remaining <= 0) break;
                int count = Transfer(handle, report, false, remaining);
                if (count <= 0) break;
                if (count == length && (reportId < 0 || report[0] == reportId) &&
                    accept(report, count)) return "active";
            }
            return "unavailable";
        }
    }

    static SampleResult Samples(string state) {
        return new SampleResult { state = state, reports = new List<string>() };
    }

    internal static object Sample() {
        string data = ReadRequest();
        if (data == null) return Samples("unavailable");
        var serializer = RequestSerializer();
        Dictionary<string, object> fields;
        try { fields = serializer.DeserializeObject(data) as Dictionary<string, object>; }
        catch (ArgumentException) { return Samples("unavailable"); }
        catch (InvalidOperationException) { return Samples("unavailable"); }
        int reportId;
        if (fields == null || fields.Count != 3) return Samples("unavailable");
        string mode = Field(fields, "mode") as string;
        if (!Number(fields, "report_id", mode == InputReportMode ? -1 : 0, 255, out reportId))
            return Samples("unavailable");
        var rawDevice = Field(fields, "device") as Dictionary<string, object>;
        if (rawDevice == null) return Samples("unavailable");
        // Reject missing/non-integer fingerprint fields before conversion (0 is
        // a valid value for several fields, so defaults would weaken matching).
        int unused;
        foreach (string key in new[] { "vid", "pid", "revision", "usage_page", "usage", "input", "output", "feature" })
            if (!Number(rawDevice, key, 0, UInt16.MaxValue, out unused)) return Samples("unavailable");
        if (!Number(rawDevice, "interface", -1, 255, out unused) ||
            !Number(rawDevice, "collection", -1, 255, out unused) ||
            !(Field(rawDevice, "device_id") is string)) return Samples("unavailable");
        var request = serializer.ConvertToType<Descriptor>(rawDevice);
        if (!VendorCollection(request)) return Samples("unavailable");
        int length = ReportLength(request, mode);
        if (length < 2 || length > ReportLimit) return Samples("unavailable");
        var row = Enumerate(new List<Descriptor> { request })
            .FirstOrDefault(candidate => candidate.Info.device_id == request.device_id && SameCollection(candidate.Info, request));
        if (row == null) return Samples("offline");
        return ProbeBounded(row, () => {
            var result = Samples("unavailable");
            string state = ReadReports(row, mode, reportId, length, 660, (report, count) => {
                result.reports.Add(BitConverter.ToString(report, 0, count).Replace("-", "").ToLowerInvariant());
                return mode == GetFeatureMode || result.reports.Count >= 4;
            });
            result.state = result.reports.Count > 0 ? "active" : state;
            return result;
        }, Samples);
    }
}
