"""Session cleanup is bounded; pending note content and geometry are committed once."""
import copy,ctypes,json,threading,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch


def run(api,runtime,root,app,output,checks):
    from ctypes import wintypes
    from PyQt5.QtCore import Qt,QEvent,QPointF,QProcess
    from PyQt5.QtGui import QMouseEvent
    from session_state import save_state
    from desktop_panel_tests import wait_for
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);was_ending=runtime.session_ending;importer=None;gate=threading.Event();workers=[];metrics={}
    try:
        runtime.session_ending=False
        cfg.update(notes_enabled=True,notes_visible=True,game_mode=False)
        runtime.apply_settings();note_id=runtime.notes.new();note=runtime.notes.windows[note_id]
        note.editor.setPlainText('会话结束前尚未自动保存的正文')
        event=QMouseEvent(QEvent.MouseButtonDblClick,QPointF(2,2),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier)
        note.title.mouseDoubleClickEvent(event);note.title.setText('尚未按回车的新标题')
        note.move(note.x()+7,note.y()+3)
        runtime.clock.move(runtime.clock.x()+6,runtime.clock.y()+4)
        expected_clock=list(runtime.clock.geometry().getRect())
        writer=api.save_config;start=time.perf_counter()
        with patch.object(api,'save_config',wraps=writer) as calls:assert save_state(runtime);assert calls.call_count==1
        metrics['snapshot_ms']=round((time.perf_counter()-start)*1000,2)
        loaded=api.load_config();row=next(row for row in loaded['sticky_notes'] if row['id']==note_id)
        assert row['text']=='会话结束前尚未自动保存的正文' and row['title']=='尚未按回车的新标题'
        assert loaded['clock_layout']['rect']==expected_clock and not runtime.notes.pending
        note.editor.setPlainText('写入失败时仍需恢复的正文');state=copy.deepcopy(cfg)
        with patch.object(api,'save_config',return_value=False),patch('PyQt5.QtWidgets.QMessageBox.warning',side_effect=AssertionError('shutdown must not show blocking dialogs')):assert not save_state(runtime)
        assert cfg==state and runtime.notes.pending
        recovered=json.loads(runtime.notes.recovery.read_text(encoding='utf-8'))
        assert next(row for row in recovered['notes'] if row['id']==note_id)['text']=='写入失败时仍需恢复的正文'
        assert save_state(runtime) and not runtime.notes.recovery.exists()
        assert next(row for row in api.load_config()['sticky_notes'] if row['id']==note_id)['text']=='写入失败时仍需恢复的正文'
        from probe_lifecycle import allowed,start as start_probe
        registered=MagicMock();registered.state.return_value=QProcess.Running
        unregistered=MagicMock();unregistered.state.return_value=QProcess.Running
        assert start_probe(registered,'mock-owned-probe.exe',[])
        msg=wintypes.MSG();msg.message=0x11;msg.hWnd=int(runtime.dock.winId());msg.wParam=0
        fake=MagicMock()
        assert runtime.layout.native_filter.nativeEventFilter(b'windows_generic_MSG',ctypes.addressof(msg))==(False,0) and runtime.session_ending
        assert not allowed() and not start_probe(fake,'must-not-launch.exe',[])
        fake.start.assert_not_called()
        registered.kill.assert_called_once();unregistered.kill.assert_not_called()
        assert all(getattr(runtime.resources,key) is None for key in ('sensors','bluetooth','peripherals','app_traffic','fps','deck'))
        runtime.set_session_ending(True)  # Repeated top-level query notifications.
        msg.message=0x16;msg.wParam=1
        assert runtime.layout.native_filter.nativeEventFilter(b'windows_generic_MSG',ctypes.addressof(msg))==(False,0) and runtime.session_ending
        panel=runtime.panels.windows[runtime.panels.active_window];collapsed=panel.collapsed
        note.close();panel.close();runtime.dock.close()
        assert runtime.notes.row(note_id)['visible'] and panel.collapsed==collapsed and cfg['dock_visible']
        msg.wParam=0;runtime.layout.native_filter.nativeEventFilter(b'windows_generic_MSG',ctypes.addressof(msg));assert not runtime.session_ending
        runtime.apply_settings();app.processEvents()
        assert allowed()
        with patch('probe_lifecycle.system_ending',return_value=True):
            assert not start_probe(fake,'must-not-launch.exe',[])
        fake.start.assert_not_called()
        checks.append('probe shutdown guard: WM_QUERYENDSESSION stops collectors before DLL teardown, rejects new children and retries idempotently; cancelled session restores demand-driven collection; OS shutdown metric also blocks launches without a native message')
        checks.append('session save: one config commit captures pending body, unfinished title, clock geometry and visibility; failed save rolls back in-memory state and writes a note recovery file without dialogs; successful retry clears recovery; cancelled WM_ENDSESSION restores ordinary exit mode')
        # Both catalog jobs can be stuck in native I/O; closing the editor must
        # neither wait for them nor destroy a running QThread.
        import batch_import
        started=threading.Event();running=threading.Event()
        def slow_apps(cancelled):started.set();gate.wait(8);return []
        def slow_running(cancelled):running.set();gate.wait(8);return []
        with patch('batch_import.discover_apps',side_effect=slow_apps),patch('batch_import.discover_running_apps',side_effect=slow_running):
            importer=batch_import.BatchImporter(runtime.dock,runtime.tray,api.save_config,api.log)
            importer.show();dialog=importer.dialog;dialog.tabs.setCurrentIndex(3)
            wait_for(app,lambda:started.is_set() and running.is_set())
            workers=[dialog.worker,dialog.running_worker];assert all(worker.thread.daemon and worker.isRunning() for worker in workers)
            process=MagicMock();workers[0].own_process(process)
            start=time.perf_counter();importer.close();metrics['blocked_batch_close_ms']=round((time.perf_counter()-start)*1000,2)
            assert metrics['blocked_batch_close_ms']<150 and all(worker.isInterruptionRequested() for worker in workers)
            process.kill.assert_called_once();workers[0].release_process(process)
            dialog.deleteLater();app.processEvents();importer.close()
            gate.set();wait_for(app,lambda:all(not worker.isRunning() for worker in workers));app.processEvents()
        checks.append('shutdown catalog cancellation: two real daemon workers held in simulated slow I/O; editor closes without waits or QThread ownership, only owned scan child is killed, queued completion after window disposal is safe, repeated close is idempotent')
        from taskbar_xaml import XamlTaskbar
        class Process:
            def __init__(self):self.waits=[];self.terminated=self.killed=False
            def state(self):return QProcess.Running
            def terminate(self):self.terminated=True
            def kill(self):self.killed=True
            def waitForFinished(self,ms):self.waits.append(ms);return False
        backend=XamlTaskbar.__new__(XamlTaskbar);backend.process=Process();backend.stop_timer=MagicMock()
        backend.close(shutdown=True)
        assert backend.process.terminated and backend.process.killed and sum(backend.process.waits)==200
        from update_service import UpdateService
        worker=SimpleNamespace(cancelled=threading.Event(),wait=MagicMock())
        service=SimpleNamespace(closed=False,generation=1,restart_requested=True,worker=worker)
        UpdateService.close(service,wait_ms=0);assert worker.cancelled.is_set();worker.wait.assert_not_called()
        from desktop_catalog import DesktopScan
        scan=SimpleNamespace(cancelled=threading.Event(),thread=MagicMock())
        DesktopScan.close(scan,wait_ms=0);assert scan.cancelled.is_set();scan.thread.join.assert_not_called()
        from taskbar_text import TaskbarText
        mode={'value':1};text=TaskbarText(Path(root)/'shutdown-text.json',lambda *_:None,True,lambda:mode['value'],lambda v:mode.update(value=v),lambda:None)
        assert text.sync('light') and mode['value']==0
        with patch('taskbar_text._thread') as notification:text.close(wait_ms=0);notification.join.assert_not_called()
        assert mode['value']==1 and text.record is None
        metrics['taskbar_wait_budget_ms']=sum(backend.process.waits)
        checks.append('session cleanup budgets: taskbar adapter requests exit then kills only its owned component with a 200 ms total wait cap; update/desktop/colour-notification daemon jobs cancel without joins; original taskbar text mode is still restored')
        from running_apps_tests import run as running_app_checks
        running_app_checks(api,runtime,root,output,checks)
        (Path(output)/'shutdown-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        gate.set()
        if importer:importer.close()
        for worker in workers:worker.wait(1000)
        runtime.session_ending=was_ending;cfg.clear();cfg.update(before);api.save_config(cfg);runtime.notes.reload();runtime.apply_settings();app.processEvents()
