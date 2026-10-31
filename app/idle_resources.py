"""One-shot release for hidden widgets; no periodic global window scan."""
import weakref
from PyQt5.QtCore import QObject,QTimer,QEvent

class IdleRelease(QObject):
    def __init__(self,widget):
        super().__init__(widget)
        self.owner=weakref.ref(widget)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(60000)
        self.timer.timeout.connect(self.release)
        widget.installEventFilter(self)
        if not widget.isVisible():self.timer.start()

    def eventFilter(self,widget,event):
        if event.type()==QEvent.Show:self.timer.stop()
        elif event.type()==QEvent.Hide:self.timer.start()
        return False

    def release(self):
        self.timer.stop()
        widget=self.owner()
        if widget is None:return
        from PyQt5 import sip
        if sip.isdeleted(widget) or widget.isVisible():return
        if widget.release_idle_resources() is False:self.timer.start()

def watch(widget):
    widget._idle_release=IdleRelease(widget)
