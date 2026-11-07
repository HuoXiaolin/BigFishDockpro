// Optional metrics. Unknown or unlabelled fans/temperatures are never guessed.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Management;
using System.Runtime.InteropServices;

internal static class HardwareExtended {
    [StructLayout(LayoutKind.Sequential)]
    struct ProcessorPower { public uint number,maxMhz,currentMhz,mhzLimit,maxIdle,currentIdle; }
    [DllImport("powrprof.dll")]
    static extern uint CallNtPowerInformation(int level,IntPtr input,uint inputSize,IntPtr output,uint outputSize);
    static void Query(string scope,string query,Action<ManagementObject> action) {
        var options=new EnumerationOptions { ReturnImmediately=true,Rewindable=false,Timeout=TimeSpan.FromSeconds(2) };
        using(var search=new ManagementObjectSearcher(new ManagementScope(scope),new ObjectQuery(query),options))
        using(var rows=search.Get())foreach(ManagementObject row in rows)using(row)action(row);
    }
    public static void Collect(HashSet<string> wanted,Action<string,double,string,string> put) {
        var supported=new HashSet<string>(new[]{"cpu_frequency","cpu_voltage","cpu_fan","cpu_pump","gpu_frequency","gpu_fan","gpu_memory","disk_temp","board_temp","case_temp"});
        wanted=new HashSet<string>(wanted.Where(supported.Contains));
        if(wanted.Count==0)return;
        if(wanted.Contains("cpu_frequency"))try {
            int count=Environment.ProcessorCount,stride=Marshal.SizeOf(typeof(ProcessorPower));
            var memory=Marshal.AllocHGlobal(stride*count);
            try {
                if(CallNtPowerInformation(11,IntPtr.Zero,0,memory,(uint)(stride*count))==0) {
                    double total=0;int valid=0;
                    for(int i=0;i<count;i++) {
                        var row=(ProcessorPower)Marshal.PtrToStructure(IntPtr.Add(memory,i*stride),typeof(ProcessorPower));
                        if(row.currentMhz>0 && row.currentMhz<20000){total+=row.currentMhz;valid++;}
                    }
                    if(valid>0)put("cpu_frequency",total/valid,"Windows 处理器电源信息 · 当前频率均值","CPU 频率");
                }
            } finally {Marshal.FreeHGlobal(memory);}
        }catch(Exception){}
        if(wanted.Contains("cpu_voltage"))try {
            Query(@"root\cimv2","SELECT CurrentVoltage FROM Win32_Processor",row=>{
                if(row["CurrentVoltage"]==null)return;int v=Convert.ToInt32(row["CurrentVoltage"]);
                if((v&128)!=0 && (v&127)>0)put("cpu_voltage",(v&127)/10.0,"固件 WMI CurrentVoltage","CPU 电压");
            });
        }catch(Exception){}
        if(wanted.Contains("disk_temp"))try {
            Query(@"root\Microsoft\Windows\Storage","SELECT DeviceId,Temperature FROM MSFT_StorageReliabilityCounter",row=>{
                if(row["Temperature"]!=null){double v=Convert.ToDouble(row["Temperature"]);if(v>0 && v<150)put("disk_temp",v,"Windows 存储可靠性 · 磁盘 "+row["DeviceId"],"磁盘温度");}
            });
        }catch(Exception){}
        if(!wanted.Any(k=>k.EndsWith("_fan") || k.EndsWith("_pump") || k.EndsWith("_frequency") || k.EndsWith("_voltage") || k.EndsWith("_temp") || k=="gpu_memory"))return;
        foreach(string provider in new[]{"LibreHardwareMonitor","OpenHardwareMonitor"})try {
            Query(@"root\"+provider,"SELECT Identifier,Name,SensorType,Value FROM Sensor",row=>{
                if(row["Value"]==null)return;
                var id=Convert.ToString(row["Identifier"]).ToLowerInvariant();var name=Convert.ToString(row["Name"]);var label=name.ToLowerInvariant();var type=Convert.ToString(row["SensorType"]);
                double value=Convert.ToDouble(row["Value"],CultureInfo.InvariantCulture);string key=null,title=null;
                bool cpu=id.Contains("cpu/"),gpu=id.Contains("gpu/");
                if(type=="Clock" && (label.Contains("core") || label=="gpu")) {if(cpu){key="cpu_frequency";title="CPU 频率";}else if(gpu){key="gpu_frequency";title="GPU 频率";}}
                if(type=="Voltage" && (cpu || label.Contains("cpu") || label.Contains("vcore"))){key="cpu_voltage";title="CPU 电压";}
                if(type=="Fan") {
                    if(label.Contains("pump") || label.Contains("aio")){key="cpu_pump";title="CPU 水泵";}
                    else if(cpu || label.Contains("cpu")){key="cpu_fan";title="CPU 风扇";}
                    else if(gpu){key="gpu_fan";title="GPU 风扇";}
                }
                if(type=="Load" && gpu && (label.Contains("memory") || label.Contains("vram"))){key="gpu_memory";title="显存占用";}
                if(type=="Temperature") {
                    if(id.Contains("hdd/") || id.Contains("nvme/") || id.Contains("ssd/")){key="disk_temp";title="磁盘温度";}
                    else if(label.Contains("motherboard") || label.Contains("mainboard") || label=="system"){key="board_temp";title="主板温度";}
                    else if(label.Contains("chassis") || label.Contains("case") || label.Contains("ambient")){key="case_temp";title="机箱温度";}
                }
                if(key!=null && wanted.Contains(key))put(key,value,provider+" · "+name,title);
            });
        }catch(Exception){}
    }
}
