"""Animate desktop fold shapes without feeding intermediate sizes into saved layouts."""
from contextlib import contextmanager
from typing import NamedTuple
import sys

from PyQt5 import sip
from PyQt5.QtCore import QEvent, QEasingCurve, QPoint, QPointF, QRect, QRectF, QSizeF, Qt, QVariantAnimation
from PyQt5.QtGui import QBackingStore, QPainter, QPixmap, QRegion
from PyQt5.QtWidgets import QWidget
from resource_liquid_shape import body_path


def native_origin(window):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        from window_layers import native
        rect = wintypes.RECT()
        if native().GetWindowRect(int(window.winId()), ctypes.byref(rect)):
            return QPoint(rect.left, rect.top)
    return None


class Frame(NamedTuple):
    rect: QRect
    corners: tuple
    image: QPixmap
    origin: QPoint | None

    @classmethod
    def capture(cls, window, corners):
        if isinstance(corners, (int, float)):
            corners = (corners,) * 4
        image = window.grab()
        return cls(window.geometry(), corners, image, native_origin(window))


class Foldable:
    def grab(self, *args):
        surface = getattr(self, '_fold_surface', None)
        if surface is None:
            return super().grab(*args)
        surface.grabbing += 1
        try:
            return super().grab(*args)
        finally:
            surface.grabbing -= 1


class FoldSurface(QWidget):
    def __init__(self, owner, first):
        flags = (Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint |
                 Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        super().__init__(owner, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.owner = owner
        self.opacity = owner.windowOpacity()
        self.first = self.last = first
        self.corners = first.corners
        self.progress = 0.
        self.origin = None
        self.start_area = self.end_area = self.viewport = QRectF(QPointF(), QSizeF(first.rect.size()))
        self.content_shift = QPointF()
        self.preparing = True
        self.grabbing = 0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(200)
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.finish)

    def frame_area(self, frame):
        ratio = frame.image.devicePixelRatioF()
        if self.origin is not None and frame.origin is not None and ratio == self.devicePixelRatioF():
            # HWND origins round independently at fractional DPI. Preserve the exact
            # desktop pixel that the snapshot occupied before switching surfaces.
            point = QPointF(frame.origin - self.origin) / ratio
        else:
            point = QPointF(frame.rect.topLeft() - self.geometry().topLeft())
        return QRectF(point, QSizeF(frame.image.size()) / ratio)

    def present(self, bounds):
        self.owner._fold_surface = self
        self.owner.installEventFilter(self)
        self.setGeometry(bounds)
        # The first Qt expose is asynchronous. Map transparently and upload the
        # actual pixels before handing over, even if layout blocks the GUI loop.
        self.setWindowOpacity(0.)
        hwnd = int(self.winId())
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            disable = wintypes.BOOL(True)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 3,
                                                       ctypes.byref(disable), ctypes.sizeof(disable))
        self.show()
        if sys.platform == 'win32':
            from window_layers import native, restack, is_topmost, TOPMOST
            owner = int(self.owner.winId())
            previous = native().GetWindow(owner, 3)  # GW_HWNDPREV
            if previous != hwnd:
                if previous and not is_topmost(owner) and is_topmost(previous):
                    previous = 0
                restack(hwnd, previous or (TOPMOST if is_topmost(owner) else 0))
        self.origin = native_origin(self)
        self.start_area = self.viewport = self.frame_area(self.first)
        if not self.prime_first_frame():
            self.finish()
            return
        if sys.platform == 'win32':
            ctypes.windll.dwmapi.DwmFlush()
        # Both layers are ready. Exchange their opacity together, before any
        # layout, native resize, repaint or event processing can intervene.
        self.setWindowOpacity(self.opacity)
        self.owner.setWindowOpacity(min(self.opacity, 1 / 255))

    def prime_first_frame(self):
        handle = self.windowHandle()
        store = QBackingStore(handle)
        store.resize(self.size())
        region = QRegion(self.rect())
        store.beginPaint(region)
        painter = QPainter(store.paintDevice())
        try:
            if not painter.isActive():
                return False
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.transparent)
            painter.drawPixmap(self.start_area.topLeft(), self.first.image)
        finally:
            if painter.isActive():
                painter.end()
            store.endPaint()
        store.flush(region, handle)
        return True

    def freeze(self):
        self.animation.stop()
        current = self.first
        if self.progress:
            image = self.grab()
            ratio = image.devicePixelRatioF()
            pixels = QRectF(self.viewport.topLeft()*ratio, self.viewport.size()*ratio).toAlignedRect().intersected(image.rect())
            area = QRectF(QPointF(pixels.topLeft())/ratio, QSizeF(pixels.size())/ratio)
            bounds = area.translated(QPointF(self.geometry().topLeft())).toAlignedRect()
            origin = self.origin + pixels.topLeft() if self.origin is not None else None
            current = Frame(bounds, self.corners, image.copy(pixels), origin)
        self.first = self.last = current
        self.start_area = self.viewport = self.frame_area(current)
        self.progress = 0.
        self.preparing = True

    def play(self, last):
        self.last = last
        if not self.geometry().contains(last.rect):
            # Content-only changes (such as a new reminder) can grow beyond the
            # predicted bounds. Establish their canvas before starting the clock.
            self.setGeometry(self.geometry().united(last.rect))
            self.origin = native_origin(self)
            self.start_area = self.viewport = self.frame_area(self.first)
            if not self.prime_first_frame():
                self.finish()
                return
        start = self.start_area
        end = self.end_area = self.frame_area(last)
        def shift(leading, trailing):
            # If the two edges grow around an anchor, its content stays still.
            return 0. if leading*trailing <= 0 else min((leading, trailing), key=abs)
        self.content_shift = QPointF(shift(end.left()-start.left(), end.right()-start.right()),
                                     shift(end.top()-start.top(), end.bottom()-start.bottom()))
        self.preparing = False
        self.owner.repaint()
        self.advance(0.)
        self.animation.start()

    def advance(self, value):
        self.progress = float(value)
        start, end = self.start_area, self.end_area
        self.viewport = QRectF(start.topLeft() + (end.topLeft()-start.topLeft())*value,
                               start.size() + (end.size()-start.size())*value)
        self.corners = tuple(a+(b-a)*value for a,b in zip(self.first.corners, self.last.corners))
        self.update()

    def paintEvent(self, event):
        if self.first is None:
            return
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(event.rect(), Qt.transparent)
        if self.progress == 0. or self.progress == 1.:
            # Endpoint snapshots already contain their antialiased glass edges.
            frame = self.first if self.progress == 0. else self.last
            painter.drawPixmap(self.viewport.topLeft(), frame.image)
            return
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipPath(body_path(self.viewport,self.corners))
        p = self.progress
        opening = self.first.rect.height() < self.last.rect.height()
        blend = 1-(1-p)**2 if opening else p*p
        for frame, point, opacity in ((self.first, self.start_area.topLeft() + self.content_shift*p, 1-blend),
                                      (self.last, self.end_area.topLeft() - self.content_shift*(1-p), blend)):
            if opacity <= 0:
                continue
            painter.setOpacity(opacity)
            painter.drawPixmap(point, frame.image)
            painter.setCompositionMode(QPainter.CompositionMode_Plus)

    def eventFilter(self, owner, event):
        if event.type() == QEvent.Paint and not self.preparing and not self.grabbing:
            # At 1/255 window opacity, normal glass pixels can round to zero.
            # Windows skips such pixels during hit testing. Keep the target
            # silhouette at exactly one alpha level while the proxy is visible.
            painter = QPainter(owner)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillPath(body_path(QRectF(owner.rect()).adjusted(1,1,-1,-1), self.last.corners), Qt.black)
            painter.end()
            return True
        if (event.type() in (QEvent.Hide, QEvent.ParentAboutToChange) or
                not self.preparing and event.type() in (QEvent.Move, QEvent.Resize)
                and owner.geometry() != self.last.rect):
            self.finish()
        return False

    def finish(self):
        if self.owner._fold_surface is not self:
            return
        self.animation.stop()
        self.owner._fold_surface = None
        self.owner.removeEventFilter(self)
        if self.owner.isVisible():
            self.owner.repaint()
        self.owner.setWindowOpacity(self.opacity)
        self.setWindowOpacity(0.)
        self.hide()
        self.first = self.last = None
        self.deleteLater()


@contextmanager
def transition(window, enabled, corners, *, content_change=False, target_rect=None):
    """Capture the two real states around one synchronous layout update."""
    surface = getattr(window, '_fold_surface', None)
    edge = getattr(window, 'edge_reveal', None)
    if (not enabled or window is None or not window.isVisible() or not window.isWindow()
            or window.isMinimized() or edge and edge.fraction < 1.):
        if surface and not surface.preparing:
            surface.finish()
        yield
        return
    if surface and surface.preparing:
        yield
        return
    if surface:
        surface.freeze()
    else:
        first = Frame.capture(window, corners())
        if first.image.isNull() or window.windowOpacity() <= 0:
            yield
            return
        surface = FoldSurface(window, first)
        bounds = first.rect.united(target_rect()) if target_rect is not None else first.rect
        surface.present(bounds)
    try:
        yield
        if sip.isdeleted(surface) or window._fold_surface is not surface:
            return
        if window.isVisible() and (content_change or window.geometry() != surface.first.rect):
            last = Frame.capture(window, corners())
            if not last.image.isNull():
                surface.play(last)
    finally:
        if not sip.isdeleted(surface) and surface.preparing:
            surface.finish()
