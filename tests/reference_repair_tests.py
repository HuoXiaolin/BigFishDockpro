"""Reference repair tests use temporary paths and a private GUI desktop only."""
import copy
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock


def run(api,runtime,main,app,output,checks):
    from PyQt5.QtCore import Qt
    from ui_test_events import Events as QTest
    import reference_repair as repair
    from reference_dialog import ReferencesDialog
    with tempfile.TemporaryDirectory(prefix='reference-review-',dir=str(output)) as temporary:
        root=Path(temporary);missing=str(root/'missing.exe');target=root/'replacement.exe';target.write_bytes(b'fixture only')
        first={'path':missing,'name':'Profile A','arguments':'--profile A','working_directory':str(root)}
        second=dict(first,name='Profile B',arguments='--profile B')
        cfg=copy.deepcopy(api.DEFAULT_CONFIG)
        cfg.update(items=[first,second],desktop_entries=[{'path':missing,'name':'missing.exe','panel':'apps','source':'manual'}])
        rows=repair.candidates(cfg);assert len(rows)==1 and rows[0]['count']==3 and 'Dock' in rows[0]['kind'] and '桌面卡片' in rows[0]['kind']
        with patch.object(repair,'drive_kind',return_value=3):
            result=repair.inspect(rows,threading.Event());assert len(result)==1 and result[0]['missing']
        for kind in (0,1,2,4,5):
            with patch.object(repair,'drive_kind',return_value=kind),patch.object(repair.os,'stat') as stat:
                result=repair.inspect(rows,threading.Event());assert not result[0]['missing'] and not stat.called
        with patch.object(repair,'drive_kind',return_value=3),patch.object(repair.os,'stat',side_effect=PermissionError('denied')):
            assert not repair.inspect(rows,threading.Event())[0]['missing']
        stopped=threading.Event();stopped.set();assert repair.inspect(rows,stopped)==[]
        fixed=repair.change(cfg,missing,str(target))
        assert [row['arguments'] for row in fixed['items']]==['--profile A','--profile B']
        assert all(row['path']==str(target) for row in fixed['items']+fixed['desktop_entries'])
        assert cfg['items'][0]['path']==missing
        link=root/'Fresh.lnk';link.write_bytes(b'synthetic shortcut metadata supplied below')
        with patch('shortcut_targets.lnk_metadata',return_value={'path':str(target),'arguments':'--new-profile','working_directory':str(root),'icon':str(target),'icon_index':2}):
            linked=repair.change(cfg,missing,str(link))
        assert all(row['arguments']=='--new-profile' and row['path']==str(target) and row['icon_index']==2 for row in linked['items'])
        assert linked['desktop_entries'][0]['path']==str(link)
        removed=repair.change(cfg,missing);assert not removed['items'] and not removed['desktop_entries'] and target.exists() and link.exists()
        checks.append('reference repair: saved-target dedup/count, skipped network/removable/unavailable drives, denied access stays unknown, cancellation, profile preservation for EXE and new-shortcut metadata replacement; originals unchanged')

        cfg=copy.deepcopy(cfg)
        service=SimpleNamespace(message='Saved',allow=True)
        def commit(candidate,title,**options):
            if not service.allow:service.message='Save refused';return False
            cfg.clear();cfg.update(candidate);service.message=title+'已保存';return True
        service.commit=commit
        test_runtime=SimpleNamespace(dock=SimpleNamespace(cfg=cfg),api=SimpleNamespace(log=MagicMock()),productivity=service)
        dialog=ReferencesDialog(test_runtime)
        try:
            dialog.show();app.processEvents()
            with patch.object(repair,'drive_kind',return_value=3):
                dialog.refresh();worker=dialog.worker;assert worker.thread.daemon
                for _ in range(100):
                    if dialog.worker is None:break
                    QTest.qWait(10)
            assert dialog.worker is None and dialog.list.topLevelItemCount()==1
            dialog.list.topLevelItem(0).setSelected(True);assert dialog.remove_button.isEnabled()
            dialog.grab().save(str(Path(output)/'review-reference-check.png'))
            service.allow=False
            with patch('reference_dialog.QFileDialog.getOpenFileName',return_value=(str(target),'')):
                assert not dialog.relocate() and cfg['items'][0]['path']==missing
            service.allow=True
            with patch('reference_dialog.QFileDialog.getOpenFileName',return_value=(str(target),'')):
                assert dialog.relocate() and cfg['items'][0]['path']==str(target)
            assert dialog.list.topLevelItemCount()==0
            unknown=dict(rows[0],missing=False,status='暂不可访问')
            dialog.rows=[unknown];dialog.render();dialog.list.topLevelItem(0).setSelected(True)
            assert not dialog.remove_button.isEnabled() and not dialog.remove_selected()
        finally:dialog.close();app.processEvents()
        # Close while a cancelled worker finishes; no UI access or second worker.
        dialog=ReferencesDialog(test_runtime)
        def delayed(rows,event,progress):
            event.wait(.15);return []
        with patch('reference_dialog.inspect',side_effect=delayed):
            dialog.refresh();worker=dialog.worker;dialog.refresh();assert dialog.worker is worker
            dialog.cancel_scan();assert worker.cancelled.is_set()
            dialog.close();worker.thread.join(.5);assert not worker.thread.is_alive();app.processEvents()
        checks.append('reference dialog: one cancellable daemon scan, completed state, failed save retains references, relink commits all selected-target references, unknown cannot be removed, close during scan releases window safely')
