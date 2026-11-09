using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Microsoft.Win32;

internal static class HardwareFans {
    internal static readonly Dictionary<string,string> Labels = new Dictionary<string,string> {
        {"cpu_fan", "CPU 风扇"}, {"gpu_fan", "GPU 风扇"},
        {"board_fan", "主板风扇"}, {"cpu_pump", "CPU 水泵"}
    };

    internal static string MonitorMetric(string identifier, string name) {
        string id = identifier.ToLowerInvariant();
        string label = name.ToLowerInvariant().Replace('_', ' ').Replace('-', ' ');
        if (label.Contains("pump") || label.Contains("aio") || label.Contains("水泵"))
            return "cpu_pump";
        if (id.StartsWith("/gpu", StringComparison.Ordinal) || id.StartsWith("/nvidiagpu/", StringComparison.Ordinal)
            || id.StartsWith("/atigpu/", StringComparison.Ordinal) || id.StartsWith("/intelgpu/", StringComparison.Ordinal)
            || label.Contains("gpu") || label.Contains("显卡"))
            return "gpu_fan";
        if (id.Contains("cpu/") || label.Contains("cpu") || label.Contains("processor") || label.Contains("处理器"))
            return "cpu_fan";
        if (id.StartsWith("/lpc/", StringComparison.Ordinal) || id.StartsWith("/motherboard/", StringComparison.Ordinal)
            || label.Contains("mainboard") || label.Contains("motherboard") || label.Contains("chipset")
            || label.Contains("chassis") || label.Contains("case fan") || label.Contains("system fan")
            || label.Contains("sys fan") || label.Contains("cha fan") || label.Contains("sysfan") || label.Contains("chafan")
            || label.Contains("主板") || label.Contains("机箱") || label.Contains("系统风扇"))
            return "board_fan";
        return null;
    }

    // NVIDIA's public NVAPI entry points, resolved through nvapi_interface.h.
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    [DllImport("nvapi64.dll", CallingConvention=CallingConvention.Cdecl, ExactSpelling=true)]
    static extern IntPtr nvapi_QueryInterface(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate int SessionCall();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate int EnumerateCall([Out, MarshalAs(UnmanagedType.LPArray, SizeConst=64)] IntPtr[] handles, out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate int TachometerCall(IntPtr handle, ref uint rpm);

    static T NvApi<T>(uint id) where T : class {
        IntPtr address = nvapi_QueryInterface(id);
        return address == IntPtr.Zero ? null : Marshal.GetDelegateForFunctionPointer(address, typeof(T)) as T;
    }

    static void Nvidia(Action<string,double,string,string> put) {
        var initialize = NvApi<SessionCall>(0x0150e828);
        var unload = NvApi<SessionCall>(0xd22bdd7e);
        if (initialize == null || unload == null || initialize() != 0)
            return;
        try {
            var enumerate = NvApi<EnumerateCall>(0xe5ac921f);
            var tachometer = NvApi<TachometerCall>(0x5f608315);
            var handles = new IntPtr[64];
            uint count;
            if (enumerate == null || tachometer == null || enumerate(handles, out count) != 0 || count > handles.Length)
                return;
            for (int i = 0; i < count; i++) {
                uint rpm = UInt32.MaxValue;
                if (handles[i] != IntPtr.Zero && tachometer(handles[i], ref rpm) == 0 && rpm != UInt32.MaxValue)
                    put("gpu_fan", rpm, "NVIDIA NVAPI · GPU " + (i + 1), Labels["gpu_fan"]);
            }
        } finally {
            unload();
        }
    }

    static void WindowsTachometers(HashSet<string> wanted, Action<string,double,string,string> put) {
        // CIM_Tachometer.CurrentReading is expressed in RPM.
        HardwareSensors.Query(@"root\cimv2", "SELECT Name,Description,DeviceID,CurrentReading FROM CIM_Tachometer", row => {
            var rpm = row["CurrentReading"];
            if (rpm == null)
                return;
            string name = Convert.ToString(row["Name"]);
            string metric = MonitorMetric("", name + " " + Convert.ToString(row["Description"]) + " " + Convert.ToString(row["DeviceID"]));
            if (metric != null && metric != "cpu_pump" && wanted.Contains(metric))
                put(metric, Convert.ToDouble(rpm, CultureInfo.InvariantCulture), "Windows 转速计 · " + name, Labels[metric]);
        });
    }

    internal static string AidaMetric(string id) {
        // F* IDs in AIDA64's Cooling Fans table are distinct from D* duty cycles.
        if (Regex.IsMatch(id, @"^FCPU(?:OPT|[0-9]+)?$"))
            return "cpu_fan";
        if (Regex.IsMatch(id, @"^FGPU[0-9]+(?:GPU[0-9]+|MEM|PWM)?$"))
            return "gpu_fan";
        if (Regex.IsMatch(id, @"^F(?:SYS|CHIP|NB|SB|PCH|NFORCE|CHA|FRONT|REAR|VRM|MOS|HAMP|AUX|OPT)[0-9]*$"))
            return "board_fan";
        return null;
    }

    static void Aida64(HashSet<string> wanted, Action<string,double,string,string> put) {
        using (var values = Registry.CurrentUser.OpenSubKey(@"Software\FinalWire\AIDA64\SensorValues")) {
            if (values == null)
                return;
            // The registry can outlive an interrupted monitor process.
            Process[] publishers = Process.GetProcessesByName("aida64");
            foreach (Process publisher in publishers)
                publisher.Dispose();
            if (publishers.Length == 0)
                return;
            foreach (string id in values.GetValueNames()) {
                string metric = AidaMetric(id.ToUpperInvariant());
                if (metric == null || !wanted.Contains(metric))
                    continue;
                string raw = Convert.ToString(values.GetValue(id), CultureInfo.InvariantCulture).Trim();
                if (raw.EndsWith(" RPM", StringComparison.OrdinalIgnoreCase))
                    raw = raw.Substring(0, raw.Length - 4);
                double rpm;
                if (Double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out rpm))
                    put(metric, rpm, "AIDA64 · " + id, Labels[metric]);
            }
        }
    }

    internal static void Collect(HashSet<string> wanted, Action<string,double,string,string> put) {
        if (!wanted.Contains("board_fan") && !wanted.Contains("cpu_fan") && !wanted.Contains("gpu_fan"))
            return;
        if (wanted.Contains("gpu_fan")) {
            try { Nvidia(put); }
            catch (DllNotFoundException) { }
            catch (EntryPointNotFoundException) { }
            catch (BadImageFormatException) { }
        }
        try { WindowsTachometers(wanted, put); }
        catch (System.Management.ManagementException) { }
        catch (UnauthorizedAccessException) { }
        catch (COMException) { }
        try { Aida64(wanted, put); }
        catch (System.IO.IOException) { }
        catch (System.Security.SecurityException) { }
        catch (UnauthorizedAccessException) { }
    }
}
