"""Focused interaction regressions, called only by the isolated runtime harness."""
import copy
import ctypes
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def run(api, runtime, main, app, output, checks):
    from PyQt5.QtCore import Qt, QEvent, QPointF
    from PyQt5.QtGui import QKeyEvent, QMouseEvent
    from ui_test_events import Events as QTest
    from app_catalog import launch_identity, merge_items, path_key
    from batch_import import BatchDialog
    from dock_folders import application_entries, remove_applications, entry, normalize_folder, show_folder
    from card_file_actions import rename_file, reconcile_shell_delete
    import native_file_menu

    with tempfile.TemporaryDirectory(prefix='interaction-review-', dir=str(output)) as temporary:
        root=Path(temporary)
        program=root/'example.exe'; program.write_bytes(b'fixture only; never execute')
        first=dict(path=str(program),name='Profile A',arguments='--profile A')
        second=dict(path=str(program),name='Profile B',arguments='--profile B')
        baseline=[first]
        draft=SimpleNamespace(importer=SimpleNamespace(dock=SimpleNamespace(cfg={'items':baseline})),pending_add=[],pending_remove=set())
        draft.draft_items=lambda:merge_items(remove_applications(baseline,draft.pending_remove),draft.pending_add)[0]
        BatchDialog.stage_add(draft,[second])
        assert len(draft.pending_add)==1 and launch_identity(draft.pending_add[0])==launch_identity(second)
        combined=merge_items(baseline,draft.pending_add)[0]
        assert len(combined)==2
        remaining=remove_applications(combined,{launch_identity(first)})
        assert len(remaining)==1 and launch_identity(remaining[0])==launch_identity(second)
        folder=entry('a'*32,combined,'常用工具')
        remaining=remove_applications([folder],{launch_identity(first)})
        assert len(remaining)==1 and launch_identity(remaining[0])==launch_identity(second)
        assert normalize_folder(folder)[0]['name']=='常用工具'
        draft.pending_add=[];draft.pending_remove={launch_identity(first)}
        BatchDialog.stage_add(draft,[first]);assert not draft.pending_remove and not draft.pending_add
        # HTTP path casing is meaningful even though Windows file paths are not.
        upper={'path':'https://example.com/Case','name':'Case'}
        lower={'path':'https://example.com/case','name':'case'}
        assert remove_applications([upper,lower],{launch_identity(upper)})==[lower]
        checks.append('batch identity: parameterized app add/remove/cancel-removal, folder child removal and case-sensitive URL selection preserve distinct launch targets')

        source=root/'Original';source.mkdir();child=source/'child.txt';child.write_text('retain',encoding='utf-8')
        sibling=root/'Original-other';sibling.mkdir();other=sibling/'keep.txt';other.write_text('keep',encoding='utf-8')
        old=str(source);old_child=str(child)
        cfg={'desktop_entries':[{'path':old,'name':'Original','panel':'folders','source':'manual'},
              {'path':old_child,'name':'child.txt','panel':'documents','source':'manual'},
              {'path':str(other),'name':'keep.txt','panel':'documents','source':'manual'}],
             'desktop_excluded':[], 'desktop_panels':[{'id':'documents','pinned_paths':[path_key(old_child)]}]}
        manager=SimpleNamespace(cfg=cfg,scanned_rows=[],status=MagicMock(),sync_windows=MagicMock(),schedule_scan=MagicMock(),closed=False)
        def commit(**values):cfg.update(values);return True
        manager.commit=commit
        panel=SimpleNamespace(selected_paths=lambda:[old],collapse_timer=MagicMock(),manager=manager,notice=MagicMock(),disposed=False,option=lambda key:False)
        with patch('card_file_actions.QInputDialog.getText',return_value=('Renamed',True)):
            assert rename_file(panel)
        renamed=root/'Renamed';new_child=str(renamed/'child.txt')
        assert Path(new_child).read_text(encoding='utf-8')=='retain'
        assert cfg['desktop_entries'][1]['path']==new_child
        assert cfg['desktop_entries'][2]['path']==str(other)
        assert cfg['desktop_panels'][0]['pinned_paths']==[path_key(new_child)]
        before=copy.deepcopy(cfg)
        panel.selected_paths=lambda:[str(renamed)]
        with patch('card_file_actions.QInputDialog.getText',return_value=('Rejected',True)), patch.object(manager,'commit',return_value=False):
            assert not rename_file(panel)
        assert Path(new_child).exists() and not (root/'Rejected').exists() and cfg==before
        with patch('card_file_actions.QTimer.singleShot'):
            reconcile_shell_delete(manager,[new_child]);assert cfg==before
            Path(new_child).unlink();reconcile_shell_delete(manager,[new_child])
        assert all(row['path']!=new_child for row in cfg['desktop_entries']) and other.exists()
        checks.append('card operations: real temporary directory rename rebases descendant card/pin references without touching prefix siblings; canceled delete keeps references and confirmed missing target is pruned')

        menu=native_file_menu.NativeFileMenu.__new__(native_file_menu.NativeFileMenu)
        menu.callbacks={};menu.command_count=1;menu.selected_verb='';menu.command_verb=lambda index:'delete';menu.verb_handlers={'delete':lambda:None}
        assert menu.invoke(native_file_menu.SHELL_FIRST)=='card' and menu.selected_verb=='delete'

        cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG));cfg['items']=combined;cfg['running_dots']=True
        dock=api.Dock(cfg,preview=True)
        try:
            # A refused save must leave both persisted-model order and visible order intact.
            dock.drag_idx=0
            with patch.object(api,'save_config',return_value=False):
                assert not dock._drag_reorder(dock.rects[1][0]+100)
            assert cfg['items']==combined and dock.items[0]['arguments']=='--profile A'
            with patch.object(api,'save_config',return_value=True):
                dock._drag_reorder(dock.rects[1][0]+100)
            assert cfg['items'][0]['arguments']=='--profile B'
            # Moving into the center is only a candidate until dwell completes.
            dock.drag_idx=0;dock.drag_moved=True
            x,w,h,edge=dock.rects[1][:4]
            from PyQt5.QtCore import QPoint
            point=QPoint(round(x),round(edge+h/2 if dock.bump_down() else edge-h/2))
            dock._update_folder_hover(point)
            assert dock.folder_hover==-1 and dock.folder_candidate==1
            QTest.qWait(400);assert dock.folder_hover==1
            dock._cancel_folder_hover();assert dock.folder_hover==-1 and not dock.folder_timer.isActive()
            # Hidden components pause polling; a visible non-preview Dock resumes exactly once.
            with patch.object(dock,'refresh_running') as refresh:
                dock.preview=False;dock.show();app.processEvents()
                assert dock.proc_timer.isActive() and dock.geo_timer.isActive() and refresh.called
                dock.hide();app.processEvents()
                assert not dock.proc_timer.isActive() and not dock.geo_timer.isActive()
            dock.preview=True
            cfg['items']=[folder];dock.reload();dock.show();app.processEvents()
            popup=show_folder(dock,cfg['items'][0],lambda candidate:True)
            app.processEvents();popup.folder_search.setText('Profile B');app.processEvents()
            assert len(popup.filtered_tiles)==1 and popup.filtered_tiles[0].child['name']=='Profile B'
            popup.folder_title.setText('开发工具');popup.folder_title.editingFinished.emit()
            assert cfg['items'][0]['name']=='开发工具'
            popup.grab().save(str(Path(output)/'review-dock-folder.png'))
            app.sendEvent(popup,QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier));app.processEvents()
            from PyQt5 import sip
            assert sip.isdeleted(popup) or not popup.isVisible()
            checks.append('Dock interaction: failed sort rolls back, successful sort commits, folder merge waits for dwell, hidden process/geometry timers stop; searchable folder name persists and Escape closes popup')
        finally:
            dock.hide();dock.extras.close();dock.deleteLater();app.processEvents()
