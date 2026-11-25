"""Crossfade the two painted almanac editions on a rotation boundary."""
from PyQt5.QtCore import QEasingCurve, Qt, QVariantAnimation
from PyQt5.QtGui import QPainter, QPixmap

from calendar_almanac import verse_index


class AlmanacTransition:
    def __init__(self, widget):
        self.widget = widget
        self.slot = None
        self.previous = None
        self.frames = None
        self.animation = QVariantAnimation(widget)
        self.animation.setDuration(480)
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.setEasingCurve(QEasingCurve.InOutSine)
        self.animation.valueChanged.connect(lambda _: widget.update())
        self.animation.finished.connect(self.finish)

    def finish(self):
        self.frames = None
        self.widget.update()

    def reset(self):
        self.animation.stop()
        self.frames = self.previous = self.slot = None

    def frame(self, rect, options):
        from desktop_clock import draw_clock
        size = self.widget.size()
        ratio = min(self.widget.devicePixelRatioF(), 2560 / max(1, size.width(), size.height()))
        image = QPixmap(max(1, round(size.width()*ratio)), max(1, round(size.height()*ratio)))
        if image.isNull():
            return None
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        ink = draw_clock(painter, rect, self.widget.dock, options, 'almanac')
        painter.end()
        return image, ink

    def paint(self, painter, rect, options, now):
        from desktop_clock import draw_clock
        # Keep the last displayed edition even if another repaint beats the timer.
        slot = (now.date(), verse_index(now))
        options = dict(options, _now=now)
        if self.slot is not None and slot != self.slot:
            before = self.frame(rect, self.previous)
            after = self.frame(rect, options)
            if before and after:
                self.frames = before[0], after[0], after[1]
                self.animation.start()
        elif self.frames and self.previous and any(
                self.previous.get(k) != v for k, v in options.items() if k != '_now'):
            self.reset()
        self.slot = slot
        self.previous = options
        if self.frames:
            before, after, ink = self.frames
            painter.save()
            painter.drawPixmap(0, 0, after)
            painter.setOpacity(1. - self.animation.currentValue())
            painter.drawPixmap(0, 0, before)
            painter.restore()
            return ink
        return draw_clock(painter, rect, self.widget.dock, options, 'almanac')
