"""Desktop-only middle clicks and icon visibility on test-owned windows."""
import copy,ctypes
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from desktop_shortcut import DesktopMiddleShortcut,MouseEvent
from desktop_icons import DesktopIcons


def run(app,api,runtime,root,checks):
    shortcut=DesktopMiddleShortcut(runtime.dock,disabled=True)
    state={'leaf':'SysListView32','root':'Progman','pid':22,'shell':4,'next':0,'unhook':0}
    def name(hwnd,text,size):text.value=state['leaf'] if hwnd==1 else state['root'];return len(text.value)
    def pid(hwnd,out):ctypes.cast(out,ctypes.POINTER(wintypes.DWORD)).contents.value=22 if hwnd==4 else state['pid'];return 1
    def next_hook(*args):state['next']+=1;return 17
    def unhook(handle):state['unhook']+=1;return 1
    shortcut.user=SimpleNamespace(WindowFromPoint=lambda point:1,GetAncestor=lambda hwnd,kind:2,
        GetClassNameW=name,GetShellWindow=lambda:state['shell'],GetWindowThreadProcessId=pid,
        CallNextHookEx=next_hook,SetWindowsHookExW=lambda *args:555,UnhookWindowsHookEx=unhook)
    hits=[];shortcut.triggered.connect(lambda:hits.append(1));event=MouseEvent();event.pt=wintypes.POINT(450,250)
    pointer=ctypes.addressof(event);shortcut.enabled=True
    try:
        assert shortcut.mouse_event(0,0x207,pointer)==17
        assert not hits  # Hook never writes settings or changes the desktop inline.
        app.processEvents();assert len(hits)==1
        for message in (0x20a,0x20e,0x208,0x201,0x204):shortcut.mouse_event(0,message,pointer)
        for leaf,root_name in [('Qt5152QWindowIcon','Progman'),('Shell_TrayWnd','Shell_TrayWnd'),('SysListView32','CabinetWClass')]:
            state.update(leaf=leaf,root=root_name);shortcut.mouse_event(0,0x207,pointer)
        state.update(leaf='WorkerW',root='WorkerW',pid=999);shortcut.mouse_event(0,0x207,pointer)
        state['pid']=22;event.flags=1;shortcut.mouse_event(0,0x207,pointer);event.flags=0
        shortcut.mouse_event(-1,0x207,pointer);app.processEvents();assert len(hits)==1
        state.update(leaf='WorkerW',root='WorkerW');shortcut.mouse_event(0,0x207,pointer);app.processEvents();assert len(hits)==2
        shortcut.enabled=False;shortcut.mouse_event(0,0x207,pointer);app.processEvents();assert len(hits)==2
        shortcut.disabled=False;shortcut.set_enabled(True);shortcut.set_enabled(True);assert shortcut.hook==555
        shortcut.close();shortcut.close();assert state['unhook']==1
    finally:shortcut.close();shortcut.deleteLater()
    # Real window visibility, with no Explorer/user-desktop access.
    windows=[QWidget(),QWidget()];windows[0].show();app.processEvents()
    handles=[int(w.winId()) for w in windows]
    icons=DesktopIcons(finder=lambda:handles,journal_path=str(Path(root)/'middle-icon-state.json'))
    manager=runtime.panels;saved_icons=manager.icons;cfg=copy.deepcopy(runtime.dock.cfg)
    visible=lambda handle:bool(icons.user.GetWindowLongW(handle,-16)&0x10000000)
    try:
        manager.icons=icons;runtime.dock.cfg['panel_enabled']=False
        assert visible(handles[0]) and not visible(handles[1])
        assert manager.toggle_desktop_icons() and not any(visible(h) for h in handles)
        assert api.load_config()['desktop_icons_override'] and api.load_config()['desktop_icon_mode']=='hide_all'
        assert manager.toggle_desktop_icons() and all(visible(h) for h in handles)
        before=copy.deepcopy(runtime.dock.cfg)
        with patch.object(api,'save_config',return_value=False):assert not manager.toggle_desktop_icons()
        assert runtime.dock.cfg==before and all(visible(h) for h in handles)
        icons.close();assert visible(handles[0]) and not visible(handles[1])
        checks.append('desktop middle button: down-only, queued dispatch, desktop Explorer host/PID filter, no wheel/up/app/taskbar/card/injected triggers, original message forwarded, single hook cleanup; real test-window visibility toggles without cards, saved state and failed-save protection; exit restores initially visible and hidden windows')
    finally:
        icons.close();manager.icons=saved_icons
        runtime.dock.cfg.clear();runtime.dock.cfg.update(cfg);api.save_config(cfg)
        for window in windows:window.close();window.deleteLater()
