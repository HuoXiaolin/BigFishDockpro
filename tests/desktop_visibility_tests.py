"""Desktop co-display and reversible file visibility checks on test-owned files only."""
import copy
import ctypes
from pathlib import Path
from app_catalog import path_key
from desktop_catalog import scan_desktop,DesktopScan
from desktop_item_visibility import CollectedDesktopItems
from desktop_panels import DesktopPanels
from PyQt5.QtCore import Qt,QMimeData,QPoint,QPointF,QUrl
from PyQt5.QtGui import QDragEnterEvent,QDropEvent
from PyQt5.QtWidgets import QApplication
from desktop_panel_tests import wait_for


def run(api,runtime,root,output,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    prior=runtime.panels;prior_roots=list(prior.roots);prior.close()
    desktop=Path(root)/'visibility-desktop';desktop.mkdir()
    files=[desktop/name for name in ('收纳.txt','保留.txt','原本隐藏.txt')]
    for path in files:path.write_text('owned fixture',encoding='utf-8')
    outside=Path(root)/'非桌面.txt';outside.write_text('outside',encoding='utf-8')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetFileAttributesW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint]
    assert kernel.SetFileAttributesW(str(files[2]),2)
    hidden=lambda path:bool(path.stat().st_file_attributes&2)
    journal=Path(root)/'selective-visibility.json'
    manager=None
    try:
        cfg.update(panel_enabled=True,panels_visible=True,desktop_icon_mode='both',desktop_auto_sort=False,
                   merged_panels=False,disabled_categories=[],desktop_excluded=[],desktop_entries=[],
                   desktop_panels=[{'id':'selected','name':'演示收纳','enabled':True,'auto_hide':False}])
        api.save_config(cfg)
        manager=runtime.panels=DesktopPanels(runtime,roots=[str(desktop)])
        manager.collected_icons.close();manager.collected_icons=CollectedDesktopItems([str(desktop)],journal)
        manager.apply_settings();app.processEvents()
        panel=manager.windows['selected'];assert panel.isVisible() and not manager.icons.enabled
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(files[0])),QUrl.fromLocalFile(str(outside))])
        enter=QDragEnterEvent(QPoint(20,65),Qt.CopyAction|Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier)
        panel.dragEnterEvent(enter);assert enter.isAccepted() and enter.dropAction()==Qt.CopyAction
        drop=QDropEvent(QPointF(20,65),Qt.CopyAction|Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier)
        panel.dropEvent(drop);assert drop.isAccepted() and drop.dropAction()==Qt.CopyAction
        assert len(manager.rows('selected'))==2 and not hidden(files[0]) and outside.exists()
        cfg['desktop_icon_mode']=api.normalize_features(dict(cfg,desktop_icon_mode='collected'))['desktop_icon_mode'];manager.apply_settings();app.processEvents()
        assert not hidden(files[0]) and not hidden(files[1]) and hidden(files[2]) and not hidden(outside)
        assert not journal.exists() and not manager.collected_icons.records
        scanned,errors=scan_desktop([str(desktop)],included_hidden=manager.collected_icons.records)
        assert not errors and {row['path'] for row in scanned}=={str(files[0]),str(files[1])}
        worker=DesktopScan([str(desktop)],manager.collected_icons.records);received=[]
        worker.ready.connect(lambda rows,errors:received.extend(rows));worker.start()
        wait_for(app,lambda:bool(received));worker.close()
        assert str(files[0]) in {row['path'] for row in received}
        # Excluding the item restores it, while the independent desktop item stays visible.
        manager.remove_entries([path_key(str(files[0]))],'selected')
        assert not hidden(files[0]) and not journal.exists()
        manager.add_paths('selected',[str(files[0])]);assert not hidden(files[0])
        manager.shown=False;manager.sync_windows();assert not hidden(files[0])
        manager.shown=True;manager.sync_windows();assert not hidden(files[0])
        cfg['desktop_icon_mode']='both';manager.apply_settings();assert not hidden(files[0]) and not manager.icons.enabled
        assert api.save_config(cfg) and api.load_config()['desktop_icon_mode']=='both'
        # Simulated interrupted session: another controller recovers the durable record.
        owner=CollectedDesktopItems([str(desktop)],journal);owner.apply([str(files[0])]);assert hidden(files[0])
        for handle in owner.handles.values():owner.kernel.CloseHandle(handle)
        owner.handles.clear();owner.records.clear();owner.journal=None
        recovered=CollectedDesktopItems([str(desktop)],journal);assert not hidden(files[0]) and not journal.exists();recovered.close()
        # A current-session move is restored through its identity-preserving open handle.
        owner=CollectedDesktopItems([str(desktop)],journal);owner.apply([str(files[0])])
        moved=Path(root)/'moved-visibility.txt';files[0].rename(moved)
        owner.close();assert not hidden(moved);moved.rename(files[0])
        # Never unhide another file that replaced the same path.
        owner=CollectedDesktopItems([str(desktop)],journal);owner.apply([str(files[0])])
        renamed=desktop/'renamed-visibility.txt';files[0].rename(renamed);files[0].write_text('replacement',encoding='utf-8')
        owner.close();assert not hidden(renamed) and not hidden(files[0]);renamed.unlink()
        blocker=Path(root)/'visibility-block';blocker.write_text('block',encoding='utf-8')
        blocked=CollectedDesktopItems([str(desktop)],blocker/'record.json')
        assert not blocked.apply([str(files[1])]) and not hidden(files[1]);blocked.close()
        invalid=Path(root)/'bad-visibility.json';invalid.write_text('{bad',encoding='utf-8')
        blocked=CollectedDesktopItems([str(desktop)],invalid);assert not blocked.apply([str(files[1])]) and invalid.read_text()=='{bad';blocked.close()
        runtime.show_settings();settings=runtime.tray.settings_dialog
        field=settings.fields['desktop_icon_mode'];assert field.count()==2
        settings.tabs.setCurrentIndex(1);scroll=settings.tabs.pages.currentWidget();scroll.ensureWidgetVisible(field,10,10);app.processEvents()
        settings.grab().save(str(Path(output)/'desktop-icon-modes.png'));settings.reject()
        checks.append('desktop visibility modes: co-display and desktop-to-card Copy drop preserve originals; old selective mode migrates to co-display and files remain unchanged; scanner and worker retain owned hidden items; exclude/panel-hide/mode switch/exit restore, restart journal recovery, rename/move/file identity and backup-failure safety; two staged settings options persist')
    finally:
        if manager:manager.close()
        for path in files:
            if path.exists():kernel.SetFileAttributesW(str(path),0x80)
        cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=prior_roots);runtime.apply_settings()
