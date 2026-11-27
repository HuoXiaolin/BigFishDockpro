"""Independent inactivity fading for floating desktop components."""
from weakref import WeakKeyDictionary

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QObject, Qt, QTimer, QVariantAnimation, QEasingCurve
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QWidget
from idle_fade_options import HINT, LABEL, enabled, individual, selection_changes
from ui_style import ModernCheckBox


IDLE_MS = 6000
INPUT_EVENTS = frozenset((QEvent.Enter, QEvent.MouseMove, QEvent.HoverMove,
                          QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick,
                          QEvent.Wheel, QEvent.KeyPress, QEvent.TouchBegin, QEvent.TouchUpdate,
                          QEvent.TabletMove, QEvent.DragEnter, QEvent.DragMove))


class FadeCheckBox(ModernCheckBox):
    def __init__(self, cfg, key=None):
        super().__init__(LABEL)
        self.setToolTip(HINT)
        self.load(cfg, key)

    def load(self, cfg, key):
        self.key = key
        self.saved = individual(cfg, key) if key else False
        self.setChecked(self.saved)

    def changes(self, cfg, key=None):
        if self.isChecked() == self.saved:
            return {}
        return selection_changes(cfg, {key or self.key: self.isChecked()})


def add_action(menu, runtime, key):
    from settings_effects import save_changes
    action = menu.addAction(LABEL)
    action.setCheckable(True)
    action.setChecked(individual(runtime.dock.cfg, key))
    action.setToolTip(HINT)

    def toggle(checked):
        if not save_changes(runtime.tray, runtime.api, selection_changes(runtime.dock.cfg, {key: checked})):
            action.setChecked(individual(runtime.dock.cfg, key))

    action.triggered.connect(toggle)
    return action


class WindowFade(QObject):
    def __init__(self, window, cfg):
        super().__init__(window)
        self.cfg = cfg
        surface = getattr(window, '_fold_surface', None)
        self.base = surface.opacity if surface else window.windowOpacity()
        self.factor = self.target = 1.
        self.idle = False
        self.had_hover = window.testAttribute(Qt.WA_Hover)
        window.setAttribute(Qt.WA_Hover, True)
        self.delay = QTimer(self)
        self.delay.setSingleShot(True)
        self.delay.setTimerType(Qt.PreciseTimer)
        self.delay.setInterval(IDLE_MS)
        self.delay.timeout.connect(self.dim)
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutSine)
        self.animation.valueChanged.connect(self.paint_opacity)
        self.delay.start()

    def paint_opacity(self, factor):
        self.factor = float(factor)
        opacity = self.base * self.factor
        window = self.parent()
        surface = getattr(window, '_fold_surface', None)
        if surface is not None:
            # The folding animation temporarily owns the visible pixels and
            # restores its recorded opacity when it hands the window back.
            surface.opacity = opacity
            if not surface.preparing:
                surface.setWindowOpacity(opacity)
        else:
            window.setWindowOpacity(opacity)

    def fade_to(self, target, duration):
        if target == self.target:
            return
        self.target = target
        self.animation.stop()
        if not self.cfg.get('motion_enabled', True):
            self.paint_opacity(target)
            return
        self.animation.setStartValue(self.factor)
        self.animation.setEndValue(target)
        self.animation.setDuration(duration)
        self.animation.start()

    def dim(self):
        grabber = QWidget.mouseGrabber()
        window = self.parent()
        if grabber is not None and grabber.window() is window and not window.testAttribute(Qt.WA_TransparentForMouseEvents):
            self.delay.start()
            return
        self.idle = True
        self.fade_to(1. - self.cfg['desktop_idle_fade_amount'] / 100., 240)

    def interact(self):
        self.idle = False
        self.fade_to(1., 110)
        self.delay.start()

    def release(self):
        self.delay.stop()
        self.animation.stop()
        if self.factor != 1.:
            self.paint_opacity(1.)
        self.parent().setAttribute(Qt.WA_Hover, self.had_hover)
        self.deleteLater()


class DesktopIdleFade(QObject):
    def __init__(self, runtime):
        super().__init__(runtime.dock)
        self.runtime = runtime
        self.states = WeakKeyDictionary()
        self.app = QApplication.instance()
        self.app.installEventFilter(self)
        # Hit-test after all windows in a global policy change have updated.
        runtime.click_policy.input_restored.connect(self.restore_under_pointer, Qt.QueuedConnection)

    def restore_under_pointer(self, window):
        if sip.isdeleted(window):
            return
        state = self.states.get(window)
        if state is None or window.testAttribute(Qt.WA_TransparentForMouseEvents):
            return
        hit = self.app.widgetAt(QCursor.pos())
        if hit is not None and hit.window() is window:
            state.interact()

    def owns_floating_window(self, window, key):
        if not window.isWindow():
            return False
        owner = getattr(window, 'runtime', None) or getattr(getattr(window, 'service', None), 'runtime', None)
        if window is not self.runtime.dock and owner is not self.runtime:
            return False
        return key != 'resource' or window.taskbar_slot() is None

    def forget(self, window):
        state = self.states.pop(window, None)
        if state is not None and not sip.isdeleted(state):
            state.release()

    def sync_window(self, window):
        cfg = self.runtime.dock.cfg
        key = window.property('clickThroughKey') or window.property('desktopLayerKey')
        if not (key and cfg['desktop_idle_fade_amount'] and enabled(cfg, key) and
                window.isVisible() and self.owns_floating_window(window, key)):
            self.forget(window)
        elif window not in self.states:
            self.states[window] = WindowFade(window, cfg)
        elif self.states[window].idle:
            self.states[window].dim()

    def refresh(self):
        for window in self.app.topLevelWidgets():
            self.sync_window(window)

    def eventFilter(self, widget, event):
        kind = event.type()
        if kind == QEvent.DynamicPropertyChange and event.propertyName() == b'clickThroughKey' and isinstance(widget, QWidget):
            # Tabbed notes and merged cards reuse the same native window for a different item.
            self.forget(widget)
            if widget.isVisible():
                self.sync_window(widget)
        elif kind in (QEvent.Show, QEvent.Hide, QEvent.ParentChange) and isinstance(widget, QWidget):
            if widget.isWindow() or widget in self.states:
                if kind == QEvent.Hide:
                    self.forget(widget)
                else:
                    self.sync_window(widget)
        elif kind in INPUT_EVENTS and self.states and isinstance(widget, QWidget):
            window = widget.window()
            state = self.states.get(window)
            if state is not None and self.runtime.click_policy.accepts_input(window):
                state.interact()
        return False

    def close(self):
        self.app.removeEventFilter(self)
        for window in list(self.states):
            if not sip.isdeleted(window):
                self.forget(window)
        self.states.clear()
