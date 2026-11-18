"""Small, transparent running animals for the capsule and notification area."""
from functools import lru_cache
from pathlib import Path
import sys

from PyQt5.QtCore import QObject, QRect, QTimer, Qt
from PyQt5.QtGui import QIcon, QImage, QPixmap
from PyQt5.QtWidgets import QSystemTrayIcon

from resource_options import RUNNER_ANIMALS, RUNNER_SLOT, RUNNER_SPEEDS


ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'runner'
FRAMES = 8
FIXED_INTERVALS = {'fixed_140ms': 140, 'fixed_80ms': 80, 'fixed_50ms': 50}


def frame_interval(speed, cpu):
    if speed in FIXED_INTERVALS:
        return FIXED_INTERVALS[speed]
    load = max(0, min(100, cpu or 0)) / 100
    return round(300 / (1 + 3 * load))


def capsule_rect(window):
    side = min(RUNNER_SLOT - 2, window.height() - 6, max(1, window.width() // 2 - 3))
    inset = 4 if window.width() < 70 else 7
    return QRect(window.width() - inset - side, (window.height() - side) // 2, side, side)


@lru_cache(maxsize=2)
def _sheet(animal):
    return QImage(str(ASSETS / (animal + '.png'))).convertToFormat(QImage.Format_ARGB32_Premultiplied)


@lru_cache(maxsize=64)
def sprite(animal, frame, pixels):
    sheet = _sheet(animal)
    side = sheet.height() // 2
    tile = sheet.copy(frame % 4 * side, frame // 4 * side, side, side)
    return QPixmap.fromImage(tile.scaled(pixels, pixels, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))


@lru_cache(maxsize=16)
def tray_frame(animal, frame):
    # Let Qt scale the original tile directly to the monitor's physical icon size.
    return QIcon(sprite(animal, frame, _sheet(animal).height() // 2))


class RunningAnimal(QObject):
    def __init__(self, service, target):
        super().__init__(service)
        self.service = service
        self.animal = None
        self.speed = None
        self.frame = 0
        self.tray = QSystemTrayIcon(self) if target == 'tray' else None
        if self.tray is not None:
            self.tray.setContextMenu(service.runtime.tray.contextMenu())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)

    def configure(self, animal, speed):
        if (animal, speed) == (self.animal, self.speed):
            return
        if self.animal != animal:
            self.frame = 0
        self.animal, self.speed = animal, speed
        if self.tray is not None:
            self.tray.setIcon(tray_frame(self.animal, self.frame))
            self.tray.setToolTip(f"{RUNNER_ANIMALS[animal]} · {RUNNER_SPEEDS[speed]}")
            self.tray.show()
        else:
            self.service.window.update(capsule_rect(self.service.window))
        self.update_speed()
        if not self.timer.isActive():
            self.timer.start()

    def update_speed(self):
        interval = frame_interval(self.speed, self.service.latest.get('cpu'))
        if self.timer.interval() != interval:
            self.timer.setInterval(interval)

    def advance(self):
        self.frame = (self.frame + 1) % FRAMES
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
        self.deleteLater()
