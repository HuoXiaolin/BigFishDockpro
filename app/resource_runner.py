"""Small, transparent running animals for the capsule and notification area."""
from functools import lru_cache
from math import ceil, floor, isfinite
from pathlib import Path
import sys
from time import monotonic

from PyQt5.QtCore import QObject, QRect, QTimer, Qt
from PyQt5.QtGui import QCursor, QIcon, QImage, QPixmap
from PyQt5.QtWidgets import QSystemTrayIcon, QToolTip

from resource_options import RUNNER_ANIMALS, RUNNER_FIXED_RATES, RUNNER_METRICS, RUNNER_SLOT


ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'runner'
FRAMES = 8
IDLE_FPS = 12


def frame_rate(speed, percent):
    if speed in RUNNER_FIXED_RATES:
        return RUNNER_FIXED_RATES[speed][1]
    load = max(0, min(100, percent or 0)) / 100
    return IDLE_FPS + (RUNNER_FIXED_RATES['fixed_high'][1] - IDLE_FPS) * load


def capsule_rect(window):
    side = min(RUNNER_SLOT - 2, window.height() - 6, max(1, window.width() // 2 - 3))
    inset = 4 if window.width() < 70 else 7
    return QRect(window.width() - inset - side, (window.height() - side) // 2, side, side)


def _tiles(animal, *, tray=False):
    sheet = QImage(str(ASSETS / (animal + '.png'))).convertToFormat(QImage.Format_ARGB32_Premultiplied)
    side = sheet.height() // 2
    inset = int(sheet.text('TrayInset') or 0) if tray else 0
    for frame in range(FRAMES):
        rect = QRect(frame % 4 * side, frame // 4 * side, side, side)
        yield sheet.copy(rect.adjusted(inset, inset, -inset, -inset))


@lru_cache(maxsize=4)
def _capsule_frames(animal, pixels):
    return tuple(QPixmap.fromImage(tile.scaled(pixels, pixels, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                 for tile in _tiles(animal))


@lru_cache(maxsize=1)
def _tray_frames(animal):
    # Keep full-resolution tray frames so Qt can serve every monitor DPI.
    return tuple(QIcon(QPixmap.fromImage(tile)) for tile in _tiles(animal, tray=True))


def sprite(animal, frame, pixels):
    return _capsule_frames(animal, pixels)[frame]


def tray_frame(animal, frame):
    return _tray_frames(animal)[frame]


class RunningAnimal(QObject):
    def __init__(self, service, target):
        super().__init__(service)
        self.service = service
        self.animal = None
        self.speed = None
        self.metric = None
        self.readout = ''
        self.frame = 0
        self.fps = 0
        self.next_frame = 0.0
        self.tray = QSystemTrayIcon(self) if target == 'tray' else None
        if self.tray is not None:
            self.tray.setContextMenu(service.runtime.tray.contextMenu())
            self.tray.activated.connect(self.tray_activated)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.advance)

    def configure(self, animal, speed, metric):
        if (animal, speed, metric) == (self.animal, self.speed, self.metric):
            return
        if self.animal != animal:
            self.frame = 0
        self.animal, self.speed, self.metric = animal, speed, metric
        self.update_reading()
        if self.tray is not None:
            self.tray.setIcon(tray_frame(self.animal, self.frame))
            self.tray.show()
        else:
            self.service.window.update(capsule_rect(self.service.window))

    def update_reading(self):
        value = self.service.latest.get(self.metric)
        if self.metric == 'memory' and isinstance(value, (list, tuple)) and value:
            value = value[0]
        percent = max(0, min(100, value)) if isinstance(value, (int, float)) and isfinite(value) else None
        fps = frame_rate(self.speed, percent)
        if self.fps != fps:
            now = monotonic()
            # Preserve the current frame's progress when the sensor reading changes.
            remaining = min(1., max(0., (self.next_frame - now) * self.fps)) if self.fps else 1.
            self.fps = fps
            self.next_frame = now + remaining / fps
            self.schedule_frame(now)
        label = '—' if percent is None else f'{percent:.0f}%'
        text = f'{RUNNER_ANIMALS[self.animal]} {RUNNER_METRICS[self.metric]} {label}'
        if text != self.readout:
            self.readout = text
            if self.tray is not None:
                self.tray.setToolTip(text)
            else:
                window = self.service.window
                if window.runner_hovered and QToolTip.isVisible() and capsule_rect(window).contains(window.mapFromGlobal(QCursor.pos())):
                    self.show_reading(QCursor.pos())

    def show_reading(self, point):
        if self.tray is not None:
            QToolTip.showText(point, self.readout)
        else:
            window = self.service.window
            QToolTip.showText(point, self.readout, window, capsule_rect(window))

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_reading(QCursor.pos())

    def schedule_frame(self, now):
        self.timer.start(max(1, ceil((self.next_frame - now) * 1000)))

    def advance(self):
        now = monotonic()
        # Keep fractional deadlines. After a delayed event, paint only the current frame.
        steps = max(1, 1 + floor((now - self.next_frame) * self.fps))
        self.next_frame += steps / self.fps
        self.frame = (self.frame + steps) % FRAMES
        self.schedule_frame(now)
        if self.tray is not None:
            self.tray.setIcon(tray_frame(self.animal, self.frame))
        else:
            window = self.service.window
            window.update(capsule_rect(window))

    def paint(self, painter, window):
        rect = capsule_rect(window)
        pixels = max(1, round(rect.width() * window.devicePixelRatioF()))
        pixmap = sprite(self.animal, self.frame, pixels)
        painter.drawPixmap(rect, pixmap)

    def close(self):
        self.timer.stop()
        if self.tray is not None:
            self.tray.hide()
            _tray_frames.cache_clear()
        else:
            _capsule_frames.cache_clear()
        self.deleteLater()
