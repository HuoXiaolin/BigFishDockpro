using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using Microsoft.Win32;

// The on-demand helper opens only the installed PawnIO library and fixed, signed CPU modules.
internal static class CpuSensors {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryEx(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi,ExactSpelling=true)] static extern IntPtr GetProcAddress(IntPtr lib,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr lib);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentThread();
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool GetProcessAffinityMask(IntPtr process,out UIntPtr allowed,out UIntPtr system);
    [DllImport("kernel32.dll")] static extern UIntPtr SetThreadAffinityMask(IntPtr thread,UIntPtr mask);
    delegate int Open(out IntPtr handle);
    delegate int Load(IntPtr handle,byte[] bytes,UIntPtr length);
    delegate int Execute(IntPtr handle,[MarshalAs(UnmanagedType.LPStr)]string command,ulong[] input,UIntPtr inputs,[Out] ulong[] output,UIntPtr outputs,out UIntPtr used);
    delegate int Close(IntPtr handle);

    static T Export<T>(IntPtr lib,string name) where T:class {
        IntPtr address=GetProcAddress(lib,name);
        return address==IntPtr.Zero?null:Marshal.GetDelegateForFunctionPointer(address,typeof(T)) as T;
    }
    static bool Read(Execute call,IntPtr handle,string op,uint register,out ulong value) {
        ulong[] result=new ulong[1];UIntPtr count;
        bool ok=call(handle,op,new ulong[]{register},(UIntPtr)1,result,(UIntPtr)1,out count)>=0 && count.ToUInt64()==1;
        value=result[0];return ok;
    }
    static bool ReadTemperature(bool amd,Execute call,IntPtr handle,out double temperature) {
        temperature=0;ulong raw,target;
        if(!amd) {
            if(!Read(call,handle,"ioctl_read_msr",0x1a2,out target) || !Read(call,handle,"ioctl_read_msr",0x1b1,out raw) || (raw & 0x80000000)==0)return false;
            double tj=(target>>16)&255;
            if(tj<50 || tj>125)return false;
            temperature=tj-((raw>>16)&127);
            return temperature>0 && temperature<=150;
        }
        // The module and other hardware monitors share this mutex for the SMN address/data pair.
        try {
            using(var bus=new Mutex(false,@"Global\Access_PCI")) {
                bool acquired=false;
                try {
                    try {acquired=bus.WaitOne(60);} catch(AbandonedMutexException){acquired=true;}
                    if(!acquired || !Read(call,handle,"ioctl_read_smn",0x59800,out raw) || raw==0 || (uint)raw==uint.MaxValue)return false;
                    temperature=((raw>>21)&0x7ff)*0.125-(((raw&0x80000)!=0)?49:0);
                    return temperature>0 && temperature<=150;
                } finally {if(acquired)bus.ReleaseMutex();}
            }
        } catch(UnauthorizedAccessException){return false;}
    }
    static bool ReadPower(bool amd,bool atom,Execute call,IntPtr handle,out double watts) {
        watts=0;ulong unit,first,last;uint energy=amd?0xc001029bU:0x611U;
        if(!Read(call,handle,"ioctl_read_msr",amd?0xc0010299U:0x606U,out unit))return false;
        if(!Read(call,handle,"ioctl_read_msr",energy,out first))return false;
        var watch=Stopwatch.StartNew();Thread.Sleep(250);
        if(!Read(call,handle,"ioctl_read_msr",energy,out last))return false;
        var seconds=watch.Elapsed.TotalSeconds;
        if(seconds<=0 || seconds>3)return false;
        int exponent=(int)((unit>>8)&31);
        double joules=atom?1.0e-6*Math.Pow(2,exponent):Math.Pow(0.5,exponent);
        watts=unchecked((uint)last-(uint)first)*joules/seconds;
        return watts>0 && watts<3000;
    }
    public static void Collect(bool temp,bool power,Action<string,double,string,string> report) {
        if(!temp && !power)return;
        bool amd,atom;
        using(var chip=Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\CentralProcessor\0")){
            if(chip==null)return;
            string vendor=Convert.ToString(chip.GetValue("VendorIdentifier"));amd=vendor=="AuthenticAMD";
            if(!amd && vendor!="GenuineIntel")return;
            var match=Regex.Match(Convert.ToString(chip.GetValue("Identifier")),@"Family\s+(\d+)\s+Model\s+(\d+)",RegexOptions.IgnoreCase);
            if(!match.Success)return;
            int family=int.Parse(match.Groups[1].Value),model=int.Parse(match.Groups[2].Value);
            if(amd && family!=23 && family!=25 && family!=26)return;
            atom=!amd && family==6 && Array.IndexOf(new[]{0x37,0x4a,0x4d,0x5a,0x5d,0x4c},model)>=0;
        }
        string dll=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"PawnIO","PawnIOLib.dll");
        if(!File.Exists(dll))return;
        string name=amd?"AMDFamily17":"IntelMSR";byte[] bytes;
        using(var stream=typeof(CpuSensors).Assembly.GetManifestResourceStream(name+".bin")){
            if(stream==null || stream.Length>65536)return;
            using(var reader=new BinaryReader(stream)){bytes=reader.ReadBytes((int)stream.Length);}
        }
        IntPtr lib=LoadLibraryEx(dll,IntPtr.Zero,0x900);
        if(lib==IntPtr.Zero)return;
        try {
            var open=Export<Open>(lib,"pawnio_open");var load=Export<Load>(lib,"pawnio_load");
            var read=Export<Execute>(lib,"pawnio_execute");var close=Export<Close>(lib,"pawnio_close");
            if(open==null || load==null || read==null || close==null)return;
            IntPtr handle;if(open(out handle)<0 || handle==IntPtr.Zero)return;
            UIntPtr previous=UIntPtr.Zero;
            try {
                if(load(handle,bytes,(UIntPtr)bytes.Length)<0)return;
                UIntPtr allowed,system;
                if(GetProcessAffinityMask(GetCurrentProcess(),out allowed,out system) && allowed.ToUInt64()!=0){
                    ulong mask=allowed.ToUInt64();previous=SetThreadAffinityMask(GetCurrentThread(),(UIntPtr)(mask & unchecked(0UL-mask)));
                }
                double value;
                if(temp && ReadTemperature(amd,read,handle,out value))report("cpu_temp",value,amd?"PawnIO · AMD Tctl":"PawnIO · Intel DTS","CPU 温度");
                if(power && previous!=UIntPtr.Zero && ReadPower(amd,atom,read,handle,out value))report("cpu_power",value,"PawnIO · CPU 封装能量计数器","CPU 封装功率");
            } finally {
                if(previous!=UIntPtr.Zero)SetThreadAffinityMask(GetCurrentThread(),previous);
                close(handle);
            }
        } finally {FreeLibrary(lib);}
    }
}
