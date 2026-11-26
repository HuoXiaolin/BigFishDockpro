using System;
using System.Management;

internal static class TouchpadEvents {
    // Huawei/Honor HWMI reports distinct absolute on/off events for the Fn key.
    // Only subscribe to those two values, even when the pad stops sending input.
    const int On = 0x283;
    const int Off = 0x2a3;
    static readonly Guid Provider = new Guid("ABBC0F5C-8EA1-11D1-A000-C90629100000");

    public static int Watch() {
        var scope = new ManagementScope(@"\\.\root\wmi");
        using (var type = new ManagementClass(scope, new ManagementPath("OemWMIEvent"), null)) {
            type.Get();
            if (new Guid(Convert.ToString(type.Qualifiers["Guid"].Value)) != Provider) return 1;
        }
        var query = new WqlEventQuery("SELECT * FROM OemWMIEvent WHERE Force = " + On + " OR Force = " + Off);
        using (var watcher = new ManagementEventWatcher(scope, query)) {
            watcher.EventArrived += (sender, args) => {
                using (var item = args.NewEvent) {
                    uint code = Convert.ToUInt32(item["Force"]);
                    if (code == On || code == Off) Console.WriteLine(code == On ? "on" : "off");
                }
            };
            watcher.Start();
            Console.WriteLine("ready");
            // EOF also releases the subscription if the parent exits unexpectedly.
            Console.ReadLine();
            return 0;
        }
    }
}
