using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Automation;

// Read only Explorer's control bounds; the capsule remains a window owned by BigFishDockpro.
internal static class TaskbarSpace {
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window,StringBuilder name,int count);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent,Child callback,IntPtr param);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint pid);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr window,out Rect rect);
    delegate bool Child(IntPtr window,IntPtr param);
    [StructLayout(LayoutKind.Sequential)] struct Rect { public int x,y,r,b; }
    public static object Read(long handle) {
        try{ SetProcessDpiAwarenessContext(new IntPtr(-4)); }catch(EntryPointNotFoundException){}
        var hwnd=new IntPtr(handle);var type=new StringBuilder(128);
        GetClassName(hwnd,type,128);
        if (type.ToString()!="Shell_TrayWnd" && type.ToString()!="Shell_SecondaryTrayWnd") throw new ArgumentException();
        var blocks=new List<int[]>(); uint shell; GetWindowThreadProcessId(hwnd,out shell);
        EnumChildWindows(hwnd,(child,arg)=>{
            var cls=new StringBuilder(100);GetClassName(child,cls,100);Rect r;
            if((cls.ToString()=="TrayNotifyWnd" || cls.ToString()=="Start" || cls.ToString()=="TrayClockWClass")
                && IsWindowVisible(child) && GetWindowRect(child,out r)) blocks.Add(new[]{r.x,r.y,r.r,r.b});
            return true;
        },IntPtr.Zero);
        var controls=new[]{ControlType.Button,ControlType.SplitButton,ControlType.ListItem,ControlType.TabItem,
            ControlType.CheckBox,ControlType.ComboBox,ControlType.Edit,ControlType.MenuItem,ControlType.Hyperlink,ControlType.RadioButton};
        var conditions=new List<Condition>();
        foreach(var control in controls) conditions.Add(new PropertyCondition(AutomationElement.ControlTypeProperty,control));
        var root=AutomationElement.FromHandle(hwnd);
        var cache=new CacheRequest();cache.Add(AutomationElement.BoundingRectangleProperty);
        cache.Add(AutomationElement.IsOffscreenProperty);cache.Add(AutomationElement.ProcessIdProperty);
        int interactive=0;
        using(cache.Activate()) {
            var items=root.FindAll(TreeScope.Descendants,new OrCondition(conditions.ToArray()));
            foreach(AutomationElement el in items){
                if(el.Cached.IsOffscreen || el.Cached.ProcessId!=(int)shell)continue;
                var rect=el.Cached.BoundingRectangle;
                if(rect.IsEmpty || rect.Width<2 || rect.Height<2)continue;
                blocks.Add(new[]{(int)Math.Floor(rect.Left),(int)Math.Floor(rect.Top),(int)Math.Ceiling(rect.Right),(int)Math.Ceiling(rect.Bottom)});
                if(++interactive>=512)break;
            }
        }
        return new { ok=interactive>0, blocks=blocks };
    }
}
