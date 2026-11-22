// Physical readings only. No driver installation and no conversion from TDP or relative GPU power.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Management;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class HardwareSensors {
    sealed class Value {
        public double value {get;set;}
        public string source {get;set;}
        public string label {get;set;}
    }

    [StructLayout(LayoutKind.Sequential)]
    struct Adapter { public uint handle; public uint low; public int high; public uint sources; public int precise; }
    [StructLayout(LayoutKind.Sequential)]
    struct AdapterLuid { public uint low; public int high; public uint handle; }
    [StructLayout(LayoutKind.Sequential)]
    struct AdapterAddress { public uint bus, device, function; }
    [StructLayout(LayoutKind.Sequential)]
    struct EnumAdapters { public uint count; public IntPtr adapters; }
    [StructLayout(LayoutKind.Sequential)]
    struct Info { public uint handle; public int type; public IntPtr buffer; public uint size; }
    [StructLayout(LayoutKind.Sequential)]
    struct Perf {
        public uint physical;
        public ulong frequency,maxFrequency,overclock,bandwidth,pci;
        public uint rpm,powerPercent10,tempC10;
        public byte overrideState;
    }
    [DllImport("gdi32.dll")] static extern int D3DKMTEnumAdapters2(ref EnumAdapters args);
    [DllImport("gdi32.dll")] static extern int D3DKMTOpenAdapterFromLuid(ref AdapterLuid args);
    [DllImport("gdi32.dll")] static extern int D3DKMTQueryAdapterInfo(ref Info query);
    [DllImport("gdi32.dll")] static extern int D3DKMTCloseAdapter(ref uint handle);
    const DllImportSearchPath SystemOnly=DllImportSearchPath.System32;
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlInit_v2();
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlShutdown();
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetCount_v2(out uint n);
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetHandleByIndex_v2(uint i,out IntPtr dev);
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Ansi)] struct NvPciInfo {
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=16)] public string legacyId;
        public uint domain,bus,device,pciDevice,subsystem;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string busId;
    }
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetPciInfo_v3(IntPtr dev,out NvPciInfo pci);
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetPowerUsage(IntPtr dev,out uint mw);
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetTemperature(IntPtr dev,uint sensor,out uint deg);
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetClockInfo(IntPtr dev,uint clock,out uint mhz);
    [StructLayout(LayoutKind.Sequential)] struct NvMemory { public ulong total,free,used; }
    [DefaultDllImportSearchPaths(SystemOnly),DllImport("nvml.dll")] static extern int nvmlDeviceGetMemoryInfo(IntPtr dev,out NvMemory memory);

    static void Put(Dictionary<string,Value> data,string key,double value,string source,string label) {
        if (Double.IsNaN(value) || Double.IsInfinity(value) || value<0 || (key.EndsWith("temp") && (value<=0 || value>150)) || value>100000) return;
        Value old;
        if (!data.TryGetValue(key,out old) || value>old.value)
            data[key]=new Value{value=Math.Round(value,key.EndsWith("_power")?2:1),source=source,label=label};
    }

    static AdapterAddress? PciAddress(ulong luid) {
        var adapter = new AdapterLuid { low = (uint)luid, high = unchecked((int)(luid >> 32)) };
        if (D3DKMTOpenAdapterFromLuid(ref adapter) != 0) return null;
        int size = Marshal.SizeOf(typeof(AdapterAddress));
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try {
            var query = new Info { handle = adapter.handle, type = 6, buffer = buffer, size = (uint)size }; // KMTQAITYPE_ADAPTERADDRESS
            if (D3DKMTQueryAdapterInfo(ref query) == 0)
                return (AdapterAddress)Marshal.PtrToStructure(buffer, typeof(AdapterAddress));
            return null;
        } finally { Marshal.FreeHGlobal(buffer); D3DKMTCloseAdapter(ref adapter.handle); }
    }

    static void DriverTemperature(Dictionary<string,Value> data,HashSet<string> wanted,ulong? target) {
        var args=new EnumAdapters();
        if(D3DKMTEnumAdapters2(ref args)!=0 || args.count<1 || args.count>64) return;
        int stride=Marshal.SizeOf(typeof(Adapter));
        uint capacity=args.count;args.adapters=Marshal.AllocHGlobal((int)capacity*stride);
        var perf=new Perf();int size=Marshal.SizeOf(typeof(Perf));var buffer=Marshal.AllocHGlobal(size);
        try {
            if(D3DKMTEnumAdapters2(ref args)!=0 || args.count>capacity)return;
            for(int i=0;i<args.count;i++){
                var dev=(Adapter)Marshal.PtrToStructure(IntPtr.Add(args.adapters,i*stride),typeof(Adapter));
                try {
                    if (target.HasValue && (((ulong)(uint)dev.high << 32) | dev.low) != target.Value) continue;
                    Marshal.StructureToPtr(perf,buffer,false);
                    var query=new Info{handle=dev.handle,type=62,buffer=buffer,size=(uint)size};
                    if(D3DKMTQueryAdapterInfo(ref query)==0){
                        var reading=(Perf)Marshal.PtrToStructure(buffer,typeof(Perf));
                        if(wanted.Contains("gpu_temp"))Put(data,"gpu_temp",reading.tempC10/10.0,"Windows 显卡驱动 · GPU "+i,"GPU 温度");
                        if(wanted.Contains("gpu_frequency") && reading.frequency>0)Put(data,"gpu_frequency",reading.frequency/1000000.0,"Windows 显卡驱动 · GPU "+i,"GPU 频率");
                        if(wanted.Contains("gpu_fan") && reading.rpm>0)Put(data,"gpu_fan",reading.rpm,"Windows 显卡驱动 · GPU "+i,"GPU 风扇");
                    }
                } finally {if(dev.handle!=0)D3DKMTCloseAdapter(ref dev.handle);}
            }
        } finally {Marshal.FreeHGlobal(buffer);Marshal.FreeHGlobal(args.adapters);}
    }

    static void Nvidia(Dictionary<string,Value> data,bool temp,bool watts,HashSet<string> wanted,ulong? target) {
        AdapterAddress? address = target.HasValue ? PciAddress(target.Value) : null;
        if (target.HasValue && !address.HasValue) return;
        if(nvmlInit_v2()!=0)return;
        try {
            uint count;
            if(nvmlDeviceGetCount_v2(out count)!=0)return;
            var devices = new List<KeyValuePair<uint,IntPtr>>();
            for(uint i=0;i<Math.Min(32U,count);i++){
                IntPtr dev;
                if(nvmlDeviceGetHandleByIndex_v2(i,out dev)!=0)continue;
                if (address.HasValue) {
                    AdapterAddress pci = address.Value;
                    NvPciInfo info;
                    if (nvmlDeviceGetPciInfo_v3(dev,out info) != 0 || info.bus != pci.bus || info.device != pci.device ||
                        !info.busId.EndsWith("." + pci.function.ToString("x"),StringComparison.OrdinalIgnoreCase)) continue;
                }
                devices.Add(new KeyValuePair<uint,IntPtr>(i,dev));
            }
            if (target.HasValue && devices.Count != 1) return;
            foreach (var device in devices) {
                uint value;
                IntPtr dev = device.Value;
                string source="NVIDIA NVML · GPU "+device.Key;
                if(temp && nvmlDeviceGetTemperature(dev,0,out value)==0)Put(data,"gpu_temp",value,source,"GPU 温度");
                if(watts && nvmlDeviceGetPowerUsage(dev,out value)==0)Put(data,"gpu_power",value/1000.0,source,"GPU 板卡功率");
                if(wanted.Contains("gpu_frequency") && nvmlDeviceGetClockInfo(dev,0,out value)==0)Put(data,"gpu_frequency",value,source,"GPU 频率");
                NvMemory memory;
                if(wanted.Contains("gpu_memory") && nvmlDeviceGetMemoryInfo(dev,out memory)==0 && memory.total>0)
                    Put(data,"gpu_memory",100.0*memory.used/memory.total,source+" · "+(memory.used/1073741824.0).ToString("F1")+" / "+(memory.total/1073741824.0).ToString("F1")+" GB","显存占用");
            }
        } finally {nvmlShutdown();}
    }

    internal static void Query(string scope,string query,Action<ManagementObject> read) {
        var options=new EnumerationOptions { ReturnImmediately=true,Rewindable=false,Timeout=TimeSpan.FromSeconds(2) };
        using(var search=new ManagementObjectSearcher(new ManagementScope(scope),new ObjectQuery(query),options))
        using(var list=search.Get()) foreach(ManagementObject row in list) using(row) read(row);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct ScreenPoint { public int x,y; }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]
    struct MonitorInfo {
        public uint size;
        public int left,top,right,bottom,workLeft,workTop,workRight,workBottom;
        public uint flags;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string device;
    }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]
    struct PhysicalMonitor {
        public IntPtr handle;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=128)]
        public string description;
    }
    [DllImport("user32.dll")] static extern IntPtr MonitorFromPoint(ScreenPoint point,uint flags);
    delegate bool MonitorCallback(IntPtr monitor,IntPtr dc,IntPtr bounds,IntPtr data);
    [DllImport("user32.dll")] static extern bool EnumDisplayMonitors(IntPtr dc,IntPtr bounds,MonitorCallback callback,IntPtr data);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern bool GetMonitorInfo(IntPtr monitor,ref MonitorInfo info);
    [DllImport("dxva2.dll")] static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(IntPtr monitor,out uint count);
    [DllImport("dxva2.dll")] static extern bool GetPhysicalMonitorsFromHMONITOR(IntPtr monitor,uint count,[Out] PhysicalMonitor[] devices);
    [DllImport("dxva2.dll")] static extern bool DestroyPhysicalMonitors(uint count,[In] PhysicalMonitor[] devices);
    [DllImport("dxva2.dll")] static extern bool GetMonitorCapabilities(IntPtr monitor,out uint caps,out uint temperatures);
    [DllImport("dxva2.dll")] static extern bool GetMonitorBrightness(IntPtr monitor,out uint min,out uint value,out uint max);

    static IntPtr DisplayMonitor(string device) {
        if (device == null) return MonitorFromPoint(new ScreenPoint(),1);
        IntPtr result = IntPtr.Zero;
        EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,(monitor,dc,bounds,context)=>{
            var info = new MonitorInfo { size = (uint)Marshal.SizeOf(typeof(MonitorInfo)) };
            if (!GetMonitorInfo(monitor,ref info) || !String.Equals(info.device,device,StringComparison.OrdinalIgnoreCase)) return true;
            result = monitor;
            return false;
        },IntPtr.Zero);
        return result;
    }

    static void Brightness(Dictionary<string,Value> data,string display,string instance) {
        try {
            Query(@"root\wmi","SELECT InstanceName, CurrentBrightness FROM WmiMonitorBrightness WHERE Active=TRUE",row=>{
                if (display != null && (String.IsNullOrEmpty(instance) ||
                    !String.Equals(Convert.ToString(row["InstanceName"]),instance,StringComparison.OrdinalIgnoreCase) &&
                    !Convert.ToString(row["InstanceName"]).StartsWith(instance+"_",StringComparison.OrdinalIgnoreCase))) return;
                if (row["CurrentBrightness"] is byte && (byte)row["CurrentBrightness"]<=100)
                    Put(data,"brightness",(byte)row["CurrentBrightness"],"Windows WMI · 内置屏幕","亮度");
            });
        } catch(ManagementException) {} catch(UnauthorizedAccessException) {} catch(COMException) {}
        if (data.ContainsKey("brightness")) return;
        var monitor=DisplayMonitor(display);
        uint count;
        if (monitor==IntPtr.Zero || !GetNumberOfPhysicalMonitorsFromHMONITOR(monitor,out count) || count<1 || count>16) return;
        var devices=new PhysicalMonitor[count];
        if (!GetPhysicalMonitorsFromHMONITOR(monitor,count,devices)) return;
        try {
            foreach(var device in devices) {
                uint caps,temperatures,min,value,max;
                if (GetMonitorCapabilities(device.handle,out caps,out temperatures) && (caps&2)!=0 &&
                    GetMonitorBrightness(device.handle,out min,out value,out max) && max>min && value>=min && value<=max) {
                    Put(data,"brightness",Math.Round(100.0*(value-min)/(max-min)),"显示器 · DDC/CI","亮度");
                    break;
                }
            }
        } finally { DestroyPhysicalMonitors(count,devices); }
    }

    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    static extern SafeFileHandle CreateFile(string name,uint access,uint share,IntPtr security,uint mode,uint flags,IntPtr template);
    [DllImport("kernel32.dll",SetLastError=true)]
    static extern bool DeviceIoControl(SafeFileHandle disk,uint control,byte[] query,uint querySize,[Out] byte[] result,
                                       uint resultSize,out uint received,IntPtr overlapped);

    static void DiskTemperature(Dictionary<string,Value> data,uint disk) {
        using (var file = CreateFile(@"\\.\PhysicalDrive"+disk,0,3,IntPtr.Zero,3,0,IntPtr.Zero)) {
            if (file.IsInvalid) return;
            foreach (byte property in new byte[] {52,51}) { // Device, then adapter temperature for this disk.
                var query = new byte[12]; query[0] = property;
                var result = new byte[1024];
                uint received;
                if (!DeviceIoControl(file,0x2d1400,query,(uint)query.Length,result,(uint)result.Length,out received,IntPtr.Zero) || received < 24) continue;
                // STORAGE_TEMPERATURE_DATA_DESCRIPTOR: 24-byte header, 16-byte sensor entries.
                int count = Math.Min((int)BitConverter.ToUInt16(result,12),(int)(received-24)/16);
                for (int i=0;i<count;i++)
                    Put(data,"disk_temp",BitConverter.ToInt16(result,26+i*16),"Windows 存储驱动 · 磁盘 "+disk,"磁盘温度");
                if (data.ContainsKey("disk_temp")) return;
            }
        }
    }

    public static object Read(string options,ulong? gpu=null,uint? disk=null,string display=null,string instance=null) {
        var wanted=new HashSet<string>(options.Split(','));
        var data=new Dictionary<string,Value>();
        if(wanted.Contains("gpu_temp") || wanted.Contains("gpu_frequency") || wanted.Contains("gpu_fan"))try{DriverTemperature(data,wanted,gpu);}catch(Exception){}
        bool wantGpuTemp=wanted.Contains("gpu_temp") && !data.ContainsKey("gpu_temp");
        if(wantGpuTemp || wanted.Contains("gpu_power") || wanted.Contains("gpu_frequency") || wanted.Contains("gpu_memory"))try{Nvidia(data,wantGpuTemp,wanted.Contains("gpu_power"),wanted,gpu);}catch(Exception){}
        // Sources without a device identity can still provide the automatic readings.
        if (gpu.HasValue) wanted.RemoveWhere(k => k.StartsWith("gpu_",StringComparison.Ordinal));
        if (disk.HasValue && wanted.Remove("disk_temp")) try { DiskTemperature(data,disk.Value); } catch(Exception) {}
        if(wanted.Contains("cpu_temp") || wanted.Contains("cpu_power")){
            try {CpuSensors.Collect(wanted.Contains("cpu_temp"),wanted.Contains("cpu_power"),(key,value,source,label)=>Put(data,key,value,source,label));}
            catch(System.IO.IOException){}catch(UnauthorizedAccessException){}catch(System.Security.SecurityException){}catch(ExternalException){}
        }
        foreach(var provider in new[]{"LibreHardwareMonitor","OpenHardwareMonitor"}){
            var missing=new HashSet<string>(wanted.Where(k=>!data.ContainsKey(k)));
            if(missing.Count==0)break;
            var types=new List<string>();
            if(missing.Any(k=>k.EndsWith("_temp")))types.Add("SensorType='Temperature'");
            if(missing.Any(k=>k.EndsWith("_power")))types.Add("SensorType='Power'");
            if(types.Count==0)break;
            try {Query(@"root\"+provider,"SELECT Identifier,Name,SensorType,Value FROM Sensor WHERE "+String.Join(" OR ",types),row=>{
                var id=Convert.ToString(row["Identifier"]).ToLowerInvariant();var name=Convert.ToString(row["Name"]);
                var label=name.ToLowerInvariant();var type=Convert.ToString(row["SensorType"]);if(row["Value"]==null)return;
                double value=Convert.ToDouble(row["Value"],CultureInfo.InvariantCulture);
                if(id.Contains("cpu/") && type=="Temperature" && missing.Contains("cpu_temp") &&
                    (label.Contains("package") || label.Contains("tctl") || label.Contains("tdie") || label.Contains("core")))
                    Put(data,"cpu_temp",value,provider+" · "+name,"CPU 温度");
                if(id.Contains("cpu/") && type=="Power" && missing.Contains("cpu_power") &&
                    (label.Contains("package") || label.Contains("ppt")))
                    Put(data,"cpu_power",value,provider+" · "+name,"CPU 封装功率");
                if(id.Contains("gpu/") && type=="Temperature" && missing.Contains("gpu_temp") &&
                    (label.Contains("core") || label=="gpu temperature"))Put(data,"gpu_temp",value,provider+" · "+name,"GPU 温度");
                if(id.Contains("gpu/") && type=="Power" && missing.Contains("gpu_power") &&
                    (label.Contains("board") || label.Contains("package") || label.Contains("total")))
                    Put(data,"gpu_power",value,provider+" · "+name,label.Contains("board")?"GPU 板卡功率":"GPU 功率");
            });}catch(ManagementException){}catch(UnauthorizedAccessException){}catch(COMException){}
        }
        if(wanted.Contains("cpu_temp") && !data.ContainsKey("cpu_temp"))
            try {Query(@"root\wmi","SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature",row=>{
                if(row["CurrentTemperature"]!=null)Put(data,"cpu_temp",Convert.ToDouble(row["CurrentTemperature"])/10.0-273.15,"ACPI 热区 · CPU 封装温度未提供","系统温区");
            });}catch(Exception){}
        try{HardwareExtended.Collect(wanted,(key,value,source,label)=>Put(data,key,value,source,label));}catch(Exception){}
        HardwareFans.Collect(wanted,(key,value,source,label)=>Put(data,key,value,source,label));
        var missingFans=new HashSet<string>(wanted.Where(key=>HardwareFans.Labels.ContainsKey(key) && !data.ContainsKey(key)));
        try {HardwareFans.ReadMissing(missingFans,(key,value,source,label)=>Put(data,key,value,source,label));}
        catch (Exception) { }
        if(wanted.Contains("brightness"))try{Brightness(data,display,instance);}catch(Exception){}
        return data;
    }
}
