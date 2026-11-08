"""The taskbar's shell setting and the Dock's related controls."""
import ctypes
import os
from ctypes import wintypes


class AppBarData(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('window',wintypes.HWND),('message',wintypes.UINT),
              ('edge',wintypes.UINT),('rect',wintypes.RECT),('state',wintypes.LPARAM)]


def auto_hide(value=None):
    user=ctypes.WinDLL('user32');shell=ctypes.WinDLL('shell32')
    user.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];user.FindWindowW.restype=wintypes.HWND
    handle=user.FindWindowW('Shell_TrayWnd',None)
    if not handle:return None
    call=shell.SHAppBarMessage;call.argtypes=[wintypes.DWORD,ctypes.POINTER(AppBarData)];call.restype=ctypes.c_size_t
    data=AppBarData();data.size=ctypes.sizeof(data);data.window=handle
    state=call(4,ctypes.byref(data))  # ABM_GETSTATE
    if value is None:return bool(state&1)
    if os.environ.get('FISHDOCK_TEST_DESKTOP'):raise OSError('隔离测试不修改任务栏。')
    data.state=(state&~1)|int(value)
    return bool(call(10,ctypes.byref(data)))  # ABM_SETSTATE


def add_menu(menu,runtime):
    from PyQt5.QtWidgets import QActionGroup
    from settings_effects import save_changes
    from taskbar_appearance import MODES as EFFECTS
    from taskbar_text import MODES as TEXT
    cfg=runtime.dock.cfg
    for title,key,values in (('任务栏效果','taskbar_mode',EFFECTS),('任务栏文字','taskbar_text_mode',TEXT)):
        submenu=menu.addMenu(title);group=QActionGroup(submenu);group.setExclusive(True)
        for label,value in values:
            action=submenu.addAction(label);action.setCheckable(True);action.setChecked(cfg[key]==value);group.addAction(action)
            action.triggered.connect(lambda _,key=key,value=value:save_changes(runtime.tray,runtime.api,{key:value}))
    state=auto_hide()
    action=menu.addAction('自动隐藏 Windows 任务栏');action.setCheckable(True);action.setChecked(bool(state));action.setEnabled(state is not None)

    def change_hidden(on):
        try:success=not runtime.dock.preview and auto_hide(on)
        except OSError:success=False
        if not success:runtime.tray.showMessage('任务栏','Windows 未能修改自动隐藏状态。',runtime.tray.icon(),3000)

    action.triggered.connect(change_hidden)
    menu.addSeparator()
    monitor=menu.addAction('显示任务栏监控');monitor.setCheckable(True);monitor.setChecked(cfg['resource_taskbar'])
    monitor.triggered.connect(lambda on:runtime.resources.set_options(resource_taskbar=on))
    menu.addAction('任务栏监控设置…',lambda:runtime.resources.settings(page=1))
