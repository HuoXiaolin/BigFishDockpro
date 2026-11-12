// Short-lived reader for paired, connected Windows peripherals. Never initiates pairing.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Devices.Enumeration;
using Windows.Storage.Streams;

internal static class BluetoothBattery {
    // The inbox .NET compiler references split OS WinMD files. Await their native
    // completion callback directly, without depending on a separately installed SDK.
    static System.Runtime.CompilerServices.TaskAwaiter<T> GetAwaiter<T>(this Windows.Foundation.IAsyncOperation<T> op) {
        var completion=new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        op.Completed=(sender,status) => {
            try { completion.TrySetResult(sender.GetResults()); }
            catch(Exception error) { completion.TrySetException(error); }
            finally { ((Windows.Foundation.IAsyncInfo)sender).Close(); }
        };
        return completion.Task.GetAwaiter();
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PropertyKey {
        public Guid format;
        public uint pid;
        public PropertyKey(string id, uint property) { format = new Guid(id); pid = property; }
    }
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    static extern uint CM_Get_Device_ID_List_SizeW(out uint length, string filter, uint flags);
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    static extern uint CM_Get_Device_ID_ListW(string filter, [Out] char[] buffer, uint length, uint flags);
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    static extern uint CM_Locate_DevNodeW(out uint node, string instance, uint flags);
    [DllImport("cfgmgr32.dll", CharSet=CharSet.Unicode)]
    static extern uint CM_Get_DevNode_PropertyW(uint node, ref PropertyKey key, out uint type,
        [Out] byte[] buffer, ref uint length, uint flags);

    public sealed class Reading {
        public string id { get; set; }
        public string name { get; set; }
        public int? level { get; set; }
    }

    static Dictionary<ulong,int> ClassicLevels() {
        var result = new Dictionary<ulong,int>();
        const uint filters = 0x101; // Present BTHENUM device nodes.
        uint n;
        if (CM_Get_Device_ID_List_SizeW(out n,"BTHENUM",filters)!=0 || n<2 || n>1048576) return result;
        var ids=new char[n];
        if (CM_Get_Device_ID_ListW("BTHENUM",ids,n,filters)!=0) return result;
        var battery=new PropertyKey("104ea319-6ee2-4701-bd47-8ddbf425bbe5",2);
        var address=new PropertyKey("2bd67d8b-8beb-48d5-87e0-6cda3428040a",1);
        foreach (var id in new string(ids).Split(new[]{'\0'},StringSplitOptions.RemoveEmptyEntries)) {
            uint node, type, size=1; var percent=new byte[1];
            if (CM_Locate_DevNodeW(out node,id,0)!=0 ||
                CM_Get_DevNode_PropertyW(node,ref battery,out type,percent,ref size,0)!=0 ||
                type!=3 || size!=1 || percent[0]>100) continue; // DEVPROP_TYPE_BYTE
            byte[] text=new byte[160];size=(uint)text.Length;
            if (CM_Get_DevNode_PropertyW(node,ref address,out type,text,ref size,0)!=0 || type!=18) continue;
            ulong mac;
            if (UInt64.TryParse(Encoding.Unicode.GetString(text,0,(int)size).TrimEnd('\0').Replace(":",""),
                System.Globalization.NumberStyles.HexNumber,null,out mac)) result[mac]=percent[0];
        }
        return result;
    }

    static async Task<List<Reading>> Classic() {
        var result=new List<Reading>();
        var devices=await DeviceInformation.FindAllAsync(BluetoothDevice.GetDeviceSelectorFromConnectionStatus(BluetoothConnectionStatus.Connected));
        var levels=devices.Count==0 ? new Dictionary<ulong,int>() : ClassicLevels();
        foreach(var info in devices.Take(48)) {
            try {
                using(var dev=await BluetoothDevice.FromIdAsync(info.Id)) {
                    if(dev==null || dev.ConnectionStatus!=BluetoothConnectionStatus.Connected) continue;
                    int value;
                    result.Add(new Reading { id=dev.BluetoothAddress.ToString("X12"), name=dev.Name,
                        level=levels.TryGetValue(dev.BluetoothAddress,out value) ? (int?)value : null });
                }
            } catch(Exception) { /* A peripheral can disconnect between enumeration and lookup. */ }
        }
        return result;
    }

    static async Task<Reading> LowEnergy(DeviceInformation info) {
        using(var dev=await BluetoothLEDevice.FromIdAsync(info.Id)) {
            if(dev==null || dev.ConnectionStatus!=BluetoothConnectionStatus.Connected) return null;
            var row=new Reading { id=dev.BluetoothAddress.ToString("X12"), name=dev.Name };
            try {
                var services=await dev.GetGattServicesForUuidAsync(GattServiceUuids.Battery);
                if(services.Status!=GattCommunicationStatus.Success) return row;
                try {
                    foreach(var service in services.Services) {
                        var chars=await service.GetCharacteristicsForUuidAsync(GattCharacteristicUuids.BatteryLevel);
                        if(chars.Status!=GattCommunicationStatus.Success) continue;
                        foreach(var characteristic in chars.Characteristics) {
                            var read=await characteristic.ReadValueAsync(BluetoothCacheMode.Uncached);
                            if(read.Status!=GattCommunicationStatus.Success || read.Value.Length<1) continue;
                            using(var reader=DataReader.FromBuffer(read.Value)) {
                                int percent=reader.ReadByte();
                                if(percent<=100){row.level=percent;return row;}
                            }
                        }
                    }
                } finally { foreach(var service in services.Services) service.Dispose(); }
            } catch(Exception) { /* Some connected devices expose no readable Battery Service. */ }
            return row;
        }
    }

    static async Task<List<Reading>> Ble() {
        var devices=await DeviceInformation.FindAllAsync(BluetoothLEDevice.GetDeviceSelectorFromConnectionStatus(BluetoothConnectionStatus.Connected));
        var rows=await Task.WhenAll(devices.Take(48).Select(async device => {
            try { return await LowEnergy(device); } catch(Exception) { return null; }
        }));
        return rows.Where(x=>x!=null).ToList();
    }

    static async Task<List<Reading>> Scan() {
        var classic=Classic();var ble=Ble();var found=new Dictionary<string,Reading>();
        bool ok=false;
        foreach(var task in new[]{classic,ble}) {
            List<Reading> rows;
            try { rows=await task;ok=true; } catch(Exception) { continue; }
            foreach(var row in rows) {
                Reading old;
                if(!found.TryGetValue(row.id,out old) || (!old.level.HasValue && row.level.HasValue)) found[row.id]=row;
            }
        }
        if(!ok) throw new InvalidOperationException("Bluetooth unavailable");
        return found.Values.ToList();
    }

    [MTAThread]
    static int Main(string[] args) {
        try {
            if(args.Length==1 && args[0]=="--app-traffic") return AppTraffic.Run();
            object result;
            if(args.Length==2 && args[0]=="--taskbar") result=TaskbarSpace.Read(Int64.Parse(args[1]));
            else if(args.Length==2 && args[0]=="--sensors") result=HardwareSensors.Read(args[1]);
            else if(args.Length==1 && args[0]=="--peripherals-scan") result=PeripheralBattery.Scan();
            else if(args.Length==1 && args[0]=="--peripherals-read") result=PeripheralBattery.Read();
            else if(args.Length==0) result=Scan().GetAwaiter().GetResult();
            else return 1;
            Console.OutputEncoding=new UTF8Encoding(false);
            Console.WriteLine(new JavaScriptSerializer().Serialize(result));return 0;
        } catch(Exception) { return 1; }
    }
}
