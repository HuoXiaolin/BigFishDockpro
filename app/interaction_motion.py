"""Finite surface feedback; no idle timer, frame cache, or moving wallpaper."""
from PyQt5.QtCore import QObject, QEvent, QVariantAnimation, QEasingCurve


class InteractionMotion(QObject):
    def __init__(self, window, settings):
        super().__init__(window)
        self.window=window
        self.settings=settings
        self.progress=None
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(320)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)
        window.installEventFilter(self)

    def enabled(self):
        cfg=self.settings() if callable(self.settings) else self.settings
        return cfg.get('motion_enabled',True) and self.window.isVisible()

    def trigger(self, reason='interaction'):
        if not self.enabled():
            self.stop()
            return False
        # A press during an active entrance does not restart the light indefinitely.
        if self.animation.state()==self.animation.Running:
            return False
        self.progress=0.0
        self.animation.start()
        return True

    def advance(self, value):
        if not self.enabled():
            self.stop()
            return
        self.progress=float(value)
        self.window.update()

    def finish(self):
        self.progress=None
        self.window.update()

    def stop(self):
        was_active=self.progress is not None
        self.animation.stop()
        self.progress=None
        if was_active:self.window.update()

    def eventFilter(self, watched, event):
        kind=event.type()
        if kind in (QEvent.Hide,QEvent.Close,QEvent.WindowDeactivate):
            self.stop()
        elif kind in (QEvent.Enter,QEvent.Show,QEvent.MouseButtonPress):
            self.trigger()
        return False


def attach(window, settings):
    controller=getattr(window,'_interaction_motion',None)
    if controller is None:
        controller=InteractionMotion(window,settings)
        window._interaction_motion=controller
    return controller
