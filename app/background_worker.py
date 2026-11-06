"""Cancellable, non-owning daemon jobs: a closing dialog never waits on shell I/O."""
import threading
from PyQt5.QtCore import QObject,pyqtSignal,pyqtSlot

_active=set()


class BackgroundWorker(QObject):
    finished=pyqtSignal()
    def __init__(self,parent=None):
        # A Qt parent can destroy a still-busy job along with its editor window.
        super().__init__()
        self.thread=None;self.cancelled=threading.Event();self._processes=set();self._lock=threading.Lock();self._delete_requested=False
        self.finished.connect(self._release)
    def start(self):
        if self.isRunning():return
        self.cancelled.clear();_active.add(self)
        self.thread=threading.Thread(target=self._run,daemon=True,name=type(self).__name__);self.thread.start()
    def _run(self):
        try:self.run()
        finally:
            try:self.finished.emit()
            except RuntimeError:pass
    def run(self):raise NotImplementedError
    def isRunning(self):return bool(self.thread and self.thread.is_alive())
    def isInterruptionRequested(self):return self.cancelled.is_set()
    def requestInterruption(self):
        self.cancelled.set()
        with self._lock:processes=tuple(self._processes)
        for process in processes:
            try:process.kill()
            except OSError:pass
    def own_process(self,process):
        with self._lock:self._processes.add(process);cancelled=self.cancelled.is_set()
        if cancelled:
            try:process.kill()
            except OSError:pass
    def release_process(self,process):
        with self._lock:self._processes.discard(process)
    def wait(self,milliseconds=0):
        if self.thread:self.thread.join(max(0,milliseconds)/1000)
        return not self.isRunning()
    def deleteLater(self):
        if self.isRunning():self._delete_requested=True
        else:_active.discard(self);super().deleteLater()
    @pyqtSlot()
    def _release(self):
        _active.discard(self)
        if self._delete_requested:super().deleteLater()
