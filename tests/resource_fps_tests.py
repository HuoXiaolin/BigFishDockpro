"""Check recovery from a running collector that never returns a frame."""
import io
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5.QtCore import QObject, pyqtSignal


class Probe(QObject):
    updated = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, pid=None):
        super().__init__()
        self.last_frame_at = 0.
        self.started = self.cancelled = False

    def start(self):
        self.started = True

    def requestInterruption(self):
        self.cancelled = True

    def isInterruptionRequested(self):
        return self.cancelled


def run(app, checks):
    from resource_fps import DesktopCapture, FrameMonitor

    clock = SimpleNamespace(now=100.)
    stream = io.BytesIO(b'bad sample\n0 0\n30 500000\n0 500000\n')
    process = Mock(stdout=stream, poll=Mock(return_value=0))
    desktop = DesktopCapture()
    observed = []
    desktop.updated.connect(observed.append)
    with patch('probe_lifecycle.subprocess.Popen', return_value=process) as launch, \
         patch('probe_lifecycle.system_ending', return_value=False), \
         patch('resource_fps.time', SimpleNamespace(monotonic=lambda:clock.now)):
        desktop.run()
    assert [r[0] for r in observed] == [60., 0.] and stream.closed
    assert all(r[1] == '桌面更新帧率 · DXGI' for r in observed)
    assert str(launch.call_args.args[0][0]).endswith('DesktopFrameProbe.exe')
    desktop.deleteLater()

    owner = QObject()
    owner.runtime = SimpleNamespace(dock=SimpleNamespace(preview=True))
    owner.display = Mock()
    with patch.multiple('resource_fps', Capture=Probe, DesktopCapture=Probe, stop_trace=Mock(),
                        allowed=lambda:True, time=SimpleNamespace(monotonic=lambda:clock.now)):
        monitor = FrameMonitor(owner)
        try:
            monitor.tick()
            first = monitor.job
            assert first.started and monitor.desktop_job is None and monitor.value is None
            clock.now = 103.1
            monitor.tick()
            backup = monitor.desktop_job
            assert backup.started
            backup.updated.emit((56., '桌面更新帧率 · DXGI', clock.now))
            app.processEvents()
            assert monitor.value == 56. and monitor.name.endswith('DXGI')
            clock.now = 110.1
            monitor.tick()
            assert first.cancelled, 'a running but silent collector must be restarted'
            first.finished.emit()
            app.processEvents()
            assert monitor.job is None
            clock.now = 111.
            monitor.tick()
            assert monitor.job is None, 'respect the retry delay'
            clock.now = 113.2
            monitor.tick()
            recovered = monitor.job
            recovered.session = 'fixture'
            assert recovered.started and recovered is not first
            recovered.updated.emit((90., '前台 · game.exe', clock.now))
            app.processEvents()
            assert monitor.value == 90. and monitor.name.startswith('前台') and backup.cancelled
            assert monitor.desktop_job is None
        finally:
            if monitor.job and not hasattr(monitor.job,'session'):monitor.job.session='fixture'
            monitor.close()
        assert recovered.cancelled
    checks.append('FPS recovery: desktop update stream accepts measured counts including zero; a silent PresentMon process is retried, and recovered app FPS wins and stops the fallback.')
