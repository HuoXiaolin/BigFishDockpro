"""Focused Shell discovery checks, confined to the isolated test desktop."""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'tools')]


def main(output):
    from run_isolated_test import assert_isolated
    from PyQt5.QtCore import QCoreApplication, QObject
    from shell_appearance import ShellAppearance, ShellWindowEvents, payload_root
    output = Path(output)
    checks = []
    try:
        desktop = assert_isolated()
        app = QCoreApplication([])
        dock = QObject()
        dock.preview = True
        dock.cfg = {'shell_start_enabled': True, 'shell_notifications_enabled': True}
        api = type('Api', (), {'CONFIG_DIR': str(output), 'system_is_light': staticmethod(lambda: True),
                              'log': staticmethod(lambda message: None)})
        controller = ShellAppearance(dock, api)
        controller.disabled = False
        controller.supported = True
        controller.hosts = {1234: 'notifications'}
        with patch.object(controller, 'signal') as signal:
            controller.window_created(1234)
            assert controller.next_attach.isActive() and controller.next_attach.interval() == 0
            controller.window_created(1234)
            assert not signal.called
            controller.next_attach.stop()
            controller.attached.add(1234)
            controller.window_created(1234)
            signal.assert_called_once_with(1234)
            dock.cfg['shell_notifications_enabled'] = False
            controller.window_created(1234)
            assert signal.call_count == 1 and not controller.next_attach.isActive()
            dock.cfg['shell_notifications_enabled'] = True
        checks.append('New Shell windows wake discovery immediately; attached hosts retry readiness without rewriting preferences.')

        controller.attached.clear()
        with patch('shell_appearance.stage_payload', return_value=payload_root()), \
             patch('shell_appearance.shell_hosts', return_value={1234: 'notifications'}), \
             patch('shell_appearance.system_appearance', return_value=(True, True)), \
             patch('shell_container.context', return_value=None), \
             patch('shell_container.panel_geometry_mapping', return_value=200), \
             patch('shell_container.close_panel_geometry'), \
             patch('shell_appearance.signal_host', return_value=False), \
             patch.object(controller, 'attach') as attach, \
             patch.object(controller.window_events, 'start') as watch, \
             patch.object(controller.window_events, 'stop') as stop:
            controller.sync()
            attach.assert_called_once_with(1234, 'notifications')
            watch.assert_called_once()
            assert controller.timer.interval() == 5000
            controller.attached.add(1234)
            controller.containers[1234] = None
            preferences = controller.root / f'notifications.{controller.build}.ini'
            before = preferences.stat().st_mtime_ns
            controller.sync()
            assert preferences.stat().st_mtime_ns == before
            controller.suspend()
            assert stop.called and not controller.timer.isActive()
            controller.window_created(1234)
            assert not controller.next_attach.isActive()
            controller.resume()
            assert controller.timer.isActive()
            controller.close()
            assert not controller.timer.isActive() and not controller.next_attach.isActive()
        checks.append('Unchanged settings remain untouched; five-second fallback stays slow; suspend/resume/close release the window hook.')

        # Recreate the live sequence with new PIDs every two seconds. Exercise
        # the normal settings writer, attach queue, launcher completion and retry.
        from shell_appearance import HOSTS
        guarded = ShellAppearance(dock, api)
        guarded.disabled = False
        guarded.supported = True
        calendar_pid = 501
        live = {601: 'startmenuexperiencehost.exe', calendar_pid: 'shellexperiencehost.exe'}
        def discover(names):
            names.update(live)
            return {pid: HOSTS[name] for pid, name in live.items()}
        with patch('shell_appearance.shell_hosts', side_effect=discover), \
             patch('shell_appearance.stage_payload', return_value=payload_root()), \
             patch('shell_appearance.signal_host', return_value=False), \
             patch('shell_appearance.system_appearance', return_value=(True, True)), \
             patch('shell_appearance.time.monotonic', return_value=100) as clock, \
             patch('shell_container.context', return_value=None), \
             patch('shell_container.panel_geometry_mapping', return_value=200), \
             patch('shell_container.share_panel_geometry', return_value=201), \
             patch('shell_container.close_panel_geometry'), patch('shell_appearance.QProcess'):
            guarded.sync()
            assert guarded.active_pid == calendar_pid
            guarded.finished(0, 0)
            for pid in (601, 602, 603):
                guarded.sync()
                assert guarded.active_pid == pid
                guarded.finished(0, 0)
                clock.return_value += 2
                live.pop(pid)
                live[pid + 1] = 'startmenuexperiencehost.exe'
            guarded.sync()
            assert guarded.start_paused and guarded.active_pid is None
            assert guarded.attached == {calendar_pid} and dock.cfg['shell_start_enabled']
            def enabled(kind):
                key = (str(guarded.root), kind, guarded.build)
                return 'enabled=1' in guarded.last[key].decode('utf-16').splitlines()
            assert not enabled('start') and enabled('notifications')
            assert '系统进程连续退出' in guarded.status
            guarded.retry()
            guarded.finished(0, 0)
            guarded.sync()
            assert not guarded.start_paused and guarded.active_pid == 604 and enabled('start')
            guarded.finished(0, 0)
            clock.return_value += 60
            live.pop(604)
            guarded.sync()
            assert not guarded.start_recent_exits
            guarded.close()
        checks.append('Repeated early Start exits restore the system menu; the calendar stays connected and manual retry restores styling.')

        # Exercise the same sampled-color path used when native Start opens.
        dock.cfg.update(shell_start_source='custom', shell_start_material='crystal',
                        shell_start_text_mode='auto', shell_start_opacity=0)
        ink_controller = ShellAppearance(dock, api)
        ink_controller.disabled = False
        ink_controller.hosts = {2314: 'start'}
        ink_controller.attached.add(2314)
        base = ('start', (240, 242, 244), 1)
        dark = ('start', (12, 15, 19), 1)
        with patch.object(ink_controller, 'signal'), patch.object(ink_controller, 'sync') as reapplied, \
             patch.object(ink_controller, 'sampled_surface') as surface, \
             patch.object(ink_controller, 'start_window_visible', return_value=True), \
             patch('shell_appearance.system_appearance', return_value=(True, True)), \
             patch('shell_appearance.time.monotonic', return_value=100.) as clock:
            ink_controller.ink_profiles(True, True)
            assert ink_controller.start_profile['text_mode'] == 'auto'
            ink_controller.window_created(2314, 1)
            for when, frame in [(100., dark), (100.10, dark), (100.18, dark), (100.31, base),
                                (100.55, dark), (100.72, base)]:
                clock.return_value = when
                surface.return_value = frame
                ink_controller.refresh_foreground()
            reapplied.assert_not_called()
            for when in (101., 101.16):
                clock.return_value = when
                surface.return_value = dark
                ink_controller.refresh_foreground()
            reapplied.assert_called_once_with(dark)
            assert ink_controller.pending_start_surface == dark[1]
            for when in (101.40, 101.56, 101.75):
                clock.return_value=when
                surface.return_value=base
                ink_controller.window_created(2314,1)  # Duplicate show/focus notices.
                ink_controller.refresh_foreground()
            reapplied.assert_called_once_with(dark)
            ink_controller.window_created(2314,1,hidden=True)
            ink_controller.window_created(2314,1)
            for when in (102.,102.3,102.46):
                clock.return_value=when
                ink_controller.refresh_foreground()
            assert [call.args[0] for call in reapplied.call_args_list]==[dark,base]
            ink_controller.ink_timer.stop()
        from background_contrast import foreground, majority_surface
        assert foreground(majority_surface([(0,255,0),(255,0,255),(20,20,20)]))=='#000000'
        assert foreground(majority_surface([(0,0,255),(30,20,30),(240,240,245)]))=='#ffffff'
        checks.append('Start settles after the opening animation, honors the majority of real pixels, and keeps its text color until the same HWND closes and reopens.')

        # Native panel bounds are physical pixels; a DPI-virtualized host
        # rectangle and glass that hits through must not suppress the sample.
        import ctypes
        from ctypes import wintypes as W
        from shell_appearance import foreground_surface
        native=MagicMock()
        native.SetThreadDpiAwarenessContext.return_value=11
        native.GetAncestor.side_effect=lambda window,mode:window
        native.WindowFromPoint.return_value=99  # Background owns input across the glass.
        def window_pid(window,result):
            ctypes.cast(result,ctypes.POINTER(W.DWORD))[0]=2314
        def window_rect(window,result):
            scope=native.SetThreadDpiAwarenessContext.call_args.args[0]
            assert isinstance(scope,ctypes.c_void_p) and scope.value==ctypes.c_void_p(-4).value
            ctypes.cast(result,ctypes.POINTER(W.RECT))[0]=W.RECT(0,200,730,1010)
            return True
        native.GetWindowThreadProcessId.side_effect=window_pid
        native.GetWindowRect.side_effect=window_rect
        bounds=(15,224,719,1005)
        with patch('shell_appearance.foreground_target',return_value=(native,1,'start')), \
             patch('shell_appearance.panel_visible',return_value=True), \
             patch('window_layers.native',return_value=native), \
             patch('taskbar_surface.composed_samples',return_value=((20,20,20),)*25) as pixels:
            assert foreground_surface({2314:'start'},lambda window,user:bounds)==('start',(20,20,20),1)
        dots=pixels.call_args.args[0]
        assert len(dots)==25 and all(bounds[0]<x<bounds[2] and bounds[1]<y<bounds[3] for x,y in dots)
        native.SetThreadDpiAwarenessContext.assert_called_with(11)
        checks.append('Foreground Start samples the measured visible glass in physical coordinates even when Win32 hit testing sees the background.')

        listener = ShellWindowEvents(lambda pid: None)
        listener.start()
        assert os.environ.get('FISHDOCK_TEST_DESKTOP') and listener.handle is None
        listener.stop()
        checks.append('Isolated tests cannot register a hook on the user input desktop.')
        result = {'passed': True, 'scope': 'shell-controller-isolated', 'desktop': desktop, 'checks': checks}
    except Exception:
        result = {'passed': False, 'checks': checks, 'error': traceback.format_exc()}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[-1]))
