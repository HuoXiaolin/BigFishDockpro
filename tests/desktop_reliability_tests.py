"""Private-desktop checks for icon view isolation and missed change notifications."""
import copy
import ctypes
import shutil
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication
from app_catalog import path_key
from desktop_icons import DesktopIcons
from desktop_item_visibility import CollectedDesktopItems
from desktop_panels import DesktopPanels
from desktop_panel_tests import wait_for


def run(api,runtime,root,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    previous=runtime.panels;previous_roots=list(previous.roots);previous.close()
    root=Path(root);desktop=root/'desktop-reliability';desktop.mkdir()
    source=root/'remote-source.txt';source.write_text('synthetic remote copy',encoding='utf-8')
    normal=desktop/'原始文档.txt';normal.write_text('original',encoding='utf-8')
    prehidden=desktop/'预先隐藏.txt';prehidden.write_text('private fixture',encoding='utf-8')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetFileAttributesW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint]
    assert kernel.SetFileAttributesW(str(prehidden),2)
    hidden=lambda path:bool(path.stat().st_file_attributes&2)
    journal=root/'old-desktop-items.json';manager=None
    try:
        # A previous version can have hidden only the entries it recorded.
        old=CollectedDesktopItems([str(desktop)],journal);assert old.apply([str(normal)]) and hidden(normal)
        for handle in old.handles.values():old.kernel.CloseHandle(handle)
        old.handles.clear();old.records.clear();old.journal=None
        recovered=CollectedDesktopItems([str(desktop)],journal)
        assert not hidden(normal) and hidden(prehidden) and not journal.exists()
        # If an old hidden file is moved outside the root before recovery, retain
        # its identity and retry when it returns; never guess or alter another file.
        moved_owner=CollectedDesktopItems([str(desktop)],journal);assert moved_owner.apply([str(normal)])
        for handle in moved_owner.handles.values():moved_owner.kernel.CloseHandle(handle)
        moved_owner.handles.clear();moved_owner.records.clear();moved_owner.journal=None
        moved=root/'moved-while-offline.txt';normal.rename(moved)
        pending=CollectedDesktopItems([str(desktop)],journal)
        assert journal.exists() and pending.records and pending.message and hidden(moved)
        moved.rename(normal);assert pending.restore() and not hidden(normal) and not journal.exists();pending.close()
        # Old saved or imported selective mode must migrate to co-display.
        old_cfg=copy.deepcopy(cfg);old_cfg['desktop_icon_mode']='collected';assert api.save_config(old_cfg)
        assert api.load_config()['desktop_icon_mode']=='both'
        from config_transfer import normalize as normalize_import
        assert normalize_import(old_cfg,api)['desktop_icon_mode']=='both'
        cfg.update(panel_enabled=True,panels_visible=True,desktop_icon_mode='both',desktop_auto_sort=True,
                   merged_panels=False,disabled_categories=[],desktop_excluded=[],desktop_entries=[],
                   desktop_panels=[{'id':'documents','name':'文档','enabled':True}])
        assert api.save_config(cfg)
        manager=runtime.panels=DesktopPanels(runtime,roots=[str(desktop)])
        manager.collected_icons.close();manager.collected_icons=recovered
        with patch.object(recovered,'apply',side_effect=AssertionError('must not hide user files')):
            manager.apply_settings();wait_for(app,lambda:manager.worker is None and bool(cfg['desktop_entries']))
            assert not hidden(normal) and hidden(prehidden) and not manager.icons.enabled
            # Exercise real card keyboard/menu routing with the OS clipboard mocked.
            from PyQt5.QtCore import QEvent,Qt
            from PyQt5.QtGui import QKeyEvent
            panel=manager.windows['documents'];item=next(panel.list.item(i) for i in range(panel.list.count()) if path_key(panel.list.item(i).data(Qt.UserRole)['path'])==path_key(str(normal)))
            item.setSelected(True)
            # Verify the card invokes the native menu with the exact selection and
            # routes its own actions separately, without opening a user desktop menu.
            from unittest.mock import MagicMock
            native=MagicMock();native.track.return_value='cancelled'
            with patch('native_file_menu.NativeFileMenu',return_value=native) as factory,patch.object(manager,'pin_entries') as pin:
                panel.item_menu(panel.list.visualItemRect(item).center())
                assert factory.call_args.args[1]==[str(normal)] and native.track.called and native.close.called
                commands=native.add_card_commands.call_args.args[0]
                assert {'置顶','显示方式','粘贴到桌面','移除收纳引用（保留原文件）'}<={entry[0] for entry in commands}
                next(callback for title,callback in commands if title=='置顶')()
                assert pin.call_args.args[0]=={path_key(str(normal))}
            fallback=MagicMock()
            with patch('native_file_menu.NativeFileMenu',side_effect=OSError('synthetic unavailable')),patch.object(panel,'build_item_menu',return_value=fallback):
                panel.item_menu(panel.list.visualItemRect(item).center())
                assert fallback.exec_.called and fallback.deleteLater.called and '系统菜单不可用' in panel.notice.text()
            failure=MagicMock();failure.track.side_effect=OSError('synthetic failed command')
            with patch('native_file_menu.NativeFileMenu',return_value=failure),patch.object(panel,'build_item_menu') as fallback_menu:
                panel.item_menu(panel.list.visualItemRect(item).center())
                assert not fallback_menu.called and failure.close.called and '操作未完成' in panel.notice.text()
            from ctypes import wintypes
            message=wintypes.MSG();message.message=0x0117;message.wParam=0;message.lParam=0
            handler=MagicMock();handler.handle_message.return_value=27;panel._active_file_menu=handler
            assert panel.nativeEvent(b'windows_generic_MSG',ctypes.addressof(message))==(True,27)
            panel._active_file_menu=None
            checks.append('card native menu: actual item entry point passes selected path; card action and extension message dispatch routed correctly')
            with patch('shell_file_clipboard.set_file_clipboard') as write,patch.object(panel,'paste_files') as paste:
                for key in (Qt.Key_C,Qt.Key_X,Qt.Key_V):QApplication.sendEvent(panel.list,QKeyEvent(QEvent.KeyPress,key,Qt.ControlModifier))
                assert write.call_count==2 and write.call_args_list[0].args[1] is False and write.call_args_list[1].args[1] is True
                assert paste.call_count==1
                menu=panel.build_item_menu();assert {'复制','剪切','粘贴到桌面'}<={action.text() for action in menu.actions()};menu.deleteLater()
                menu=panel.build_panel_menu();next(action for action in menu.actions() if action.text()=='粘贴到桌面').trigger();menu.deleteLater();assert paste.call_count==2
                folder=desktop/'测试文件夹';folder.mkdir();assert manager.add_paths('documents',[str(folder)])
                item=next(panel.list.item(i) for i in range(panel.list.count()) if path_key(panel.list.item(i).data(Qt.UserRole)['path'])==path_key(str(folder)))
                panel.list.clearSelection();item.setSelected(True);menu=panel.build_item_menu()
                next(action for action in menu.actions() if action.text()=='粘贴到此文件夹').trigger();menu.deleteLater()
                assert paste.call_args.args==(str(folder),)
            checks.append('card file actions: Ctrl+C/X/V and contextual paste-to-folder route selected fixture paths without touching the user clipboard')
            assert manager.reconcile_timer.isActive() and manager.reconcile_timer.interval()==15000
            # Simulate missed directory notifications: periodic reconciliation must find the copy.
            manager.watcher.blockSignals(True);manager.scan_timer.setInterval(30);manager.reconcile_timer.setInterval(200);manager.reconcile_timer.start()
            target=desktop/'远程新文件.txt';shutil.copy2(source,target)
            wait_for(app,lambda:any(path_key(row['path'])==path_key(str(target)) for row in cfg['desktop_entries']))
            renamed=desktop/'远程重命名.txt';target.rename(renamed)
            wait_for(app,lambda:any(path_key(row['path'])==path_key(str(renamed)) for row in cfg['desktop_entries']) and not any(path_key(row['path'])==path_key(str(target)) for row in cfg['desktop_entries']))
            assert not hidden(renamed) and normal.read_text(encoding='utf-8')=='original'
            # An unreadable root cannot erase prior references.
            saved=copy.deepcopy(cfg['desktop_entries']);manager.scanned([],['simulated unavailable desktop'])
            assert all(any(path_key(old['path'])==path_key(row['path']) for row in cfg['desktop_entries']) for old in saved)
            cfg['desktop_auto_sort']=False;manager.update_watchers();assert not manager.reconcile_timer.isActive()
        checks.append('desktop files: legacy hidden-attribute journal recovered test-owned files; old selective configurations migrate to co-display; pre-hidden files preserved; missed directory events recovered copied and renamed files by periodic reconciliation; unreadable scan retains prior references')

        # Fake native hosts exercise the exact production enumeration path without touching Explorer.
        class FakeUser:
            def __init__(self):
                self.names={1:'Progman',2:'WorkerW',3:'CabinetWClass',4:'Other',11:'SHELLDLL_DefView',21:'SHELLDLL_DefView',31:'SHELLDLL_DefView',41:'Other',12:'SysListView32',22:'SysListView32',32:'SysListView32',42:'SysListView32'}
                self.children={(1,'SHELLDLL_DefView'):11,(11,'SysListView32'):12,(2,'SHELLDLL_DefView'):21,(21,'SysListView32'):22,(3,'SHELLDLL_DefView'):31,(31,'SysListView32'):32}
                self.parents={12:11,22:21,32:31,42:41};self.visible={12:True,22:True,32:False,42:False};self.shown=[]
            def EnumWindows(self,callback,arg):
                for hwnd in (1,2,3,4):callback(hwnd,arg)
            def GetClassNameW(self,hwnd,buffer,size):buffer.value=self.names.get(hwnd,'');return len(buffer.value)
            def FindWindowExW(self,parent,after,name,title):return self.children.get((parent,name),0)
            def IsWindow(self,hwnd):return hwnd in self.names
            def GetParent(self,hwnd):return self.parents.get(hwnd,0)
            def GetWindowLongW(self,hwnd,index):return 0x10000000 if self.visible.get(hwnd,False) else 0
            def ShowWindow(self,hwnd,how):self.visible[hwnd]=bool(how);self.shown.append(hwnd);return True
        icons=DesktopIcons(preview=True);real_user=icons.user;fake=FakeUser()
        try:
            icons.preview=False;icons.user=fake;icons.pid=lambda hwnd:123
            assert set(icons.views())=={12,22}  # Folder host 3 is never hidden.
            icons.hidden={32:(123,True),42:(123,True)};icons.restore_native()
            assert fake.visible[32] and not fake.visible[42] and fake.shown==[32]
        finally:
            icons.hidden.clear();icons.user=real_user;icons.preview=True;icons.close()
        checks.append('desktop view scope: only Progman/WorkerW hosts selected; old recorded folder view can be restored by exact identity without showing unrelated windows')
    finally:
        if manager:manager.close()
        if prehidden.exists():kernel.SetFileAttributesW(str(prehidden),0x80)
        cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=previous_roots);runtime.apply_settings()
