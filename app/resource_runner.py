"""Small, transparent running animals for the capsule and notification area."""
from functools import lru_cache
from math import ceil, floor, isfinite
from pathlib import Path
import sys
from time import perf_counter

from PyQt5.QtCore import QObject, QRect, QTimer, Qt
from PyQt5.QtGui import QCursor, QIcon, QImage, QImageReader, QPixmap
from PyQt5.QtWidgets import QSystemTrayIcon, QToolTip

from resource_options import RUNNER_ANIMALS, RUNNER_FIXED_RATES, RUNNER_METRICS, RUNNER_SLOT


ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'runner'
FRAMES = 8  # Timing ticks per complete walk or wingbeat, independent of the artwork.
TILE_SIZE = 128


def uptime_minutes():
    import ctypes
    try:
        ticks=ctypes.windll.kernel32.GetTickCount64
        ticks.argtypes=()
        ticks.restype=ctypes.c_uint64
        return ticks()//60_000
    except (AttributeError, OSError):
        return None


def uptime_text(minutes):
    if minutes is None:
        return '暂不可用'
    if minutes==0:
        return '不足 1 分钟'
    hours, minutes=divmod(minutes,60)
    days, hours=divmod(hours,24)
    if days:
        return f'{days} 天 {hours} 小时 {minutes} 分钟'
    if hours:
        return f'{hours} 小时 {minutes} 分钟'
    return f'{minutes} 分钟'


def frame_rate(speed, percent):
    if speed in RUNNER_FIXED_RATES:
        return RUNNER_FIXED_RATES[speed][1]
    load = max(0, min(100, percent)) if isinstance(percent, (int, float)) and isfinite(percent) else 0
    return RUNNER_FIXED_RATES['fixed_high'][1] * (load / 100)


def capsule_rect(window):
    side = min(RUNNER_SLOT - 2, window.height() - 6, max(1, window.width() // 2 - 3))
    inset = 4 if window.width() < 70 else 7
    if window.service.compact and window.fold_shape()=='ball':
        from capsule_order import has_component_order
        if has_component_order(window.service.cfg):
            from capsule_order_layout import ball_slots
            placed=ball_slots(window,window.width()).get('runner')
            if placed is None:return QRect()
            return QRect(placed.x+(placed.width-side)//2,(window.height()-side)//2,side,side)
    if window.width() >= 70 and window.service.compact and window.fold_shape() != 'ball':
        from resource_compact import plan
        layout = plan(window, window.width())
        if not layout['runner_width']:
            return QRect()
        if 'positions' in layout:
            placed=layout['positions']['runner']
            side=min(side,placed.width)
            return QRect(placed.x+(placed.width-side)//2,(window.height()-side)//2,side,side)
        inset += layout['clock_width']
    return QRect(window.width() - inset - side, (window.height() - side) // 2, side, side)


@lru_cache(maxsize=len(RUNNER_ANIMALS))
def frame_count(animal):
    size = QImageReader(str(ASSETS / (animal + '.png'))).size()
    return max(1, size.width() // TILE_SIZE * (size.height() // TILE_SIZE))


def _tiles(animal, *, tray=False):
    sheet = QImage(str(ASSETS / (animal + '.png'))).convertToFormat(QImage.Format_ARGB32_Premultiplied)
    columns = max(1, sheet.width() // TILE_SIZE)
    inset = int(sheet.text('TrayInset') or 0) if tray else 0
    for frame in range(frame_count(animal)):
        rect = QRect(frame % columns * TILE_SIZE, frame // columns * TILE_SIZE, TILE_SIZE, TILE_SIZE)
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
        self.device = ''
        self.readout = ''
        self.metric_text = ''
        self.frame = 0
        self.cycle_tick = 0
        self.samples_per_tick = 1
        self.fps = 0
        self.next_frame = 0.0
        self.frame_remaining = 1.0
        self.tray = QSystemTrayIcon(self) if target == 'tray' else None
        if self.tray is not None:
            self.tray.setContextMenu(service.runtime.tray.contextMenu())
            self.tray.activated.connect(self.tray_activated)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.advance)

    def configure(self, animal, speed, metric, device=''):
        if (animal, speed, metric, device) == (self.animal, self.speed, self.metric, self.device):
            return
        if self.animal != animal:
            self.frame = self.cycle_tick = 0
            self.frame_remaining = 1.0
            self.fps = 0
            self.timer.stop()
        self.animal, self.speed, self.metric, self.device = animal, speed, metric, device
        self.update_reading()
        if self.tray is not None:
            self.tray.setIcon(tray_frame(self.animal, self.frame))
            self.tray.show()
        else:
            self.service.window.update(capsule_rect(self.service.window))

    def update_reading(self):
        value = self.service.runner_reading(self.metric, self.device)
        if self.metric == 'memory' and isinstance(value, (list, tuple)) and value:
            value = value[0]
        percent = max(0, min(100, value)) if isinstance(value, (int, float)) and isfinite(value) else None
        fps = frame_rate(self.speed, percent)
        if self.animal=='bird' and self.speed=='adaptive':
            fps=max(8.,fps)
        # Between slow sensor-driven ticks, display intermediate drawings from
        # denser sheets within the low-speed refresh budget. All pets still
        # reach the same eight timing ticks per cycle.
        samples = 1
        if fps:
            available = frame_count(self.animal) / FRAMES
            samples = max(1, int(min(available, RUNNER_FIXED_RATES['fixed_low'][1] / fps)))
        if (self.fps, self.samples_per_tick) != (fps, samples):
            now = perf_counter()
            # Carry the same point in the walk through load changes and pauses.
            if self.fps:
                self.advance_ticks(now)
                self.frame_remaining = (min(1., max(0., (self.next_frame - now) * self.fps))
                                        if isfinite(self.next_frame) else 1.)
            self.fps, self.samples_per_tick = fps, samples
            if fps:
                self.next_frame = now + self.frame_remaining / fps
                self.present_frame(self.schedule_frame(now))
            else:
                self.timer.stop()
        label = '—' if percent is None else f'{percent:.0f}%'
        text = f'{RUNNER_ANIMALS[self.animal]} {RUNNER_METRICS[self.metric]} {label}'
        if self.device:
            name = self.service.hardware_name(self.metric, self.device)
            text += f' · {name}'
        self.metric_text = text
        if self.refresh_readout() and self.tray is None:
            window = self.service.window
            if window.runner_hovered and QToolTip.isVisible() and capsule_rect(window).contains(window.mapFromGlobal(QCursor.pos())):
                self.show_reading(QCursor.pos())

    def refresh_readout(self):
        text=f'{self.metric_text}\n本次开机时长　{uptime_text(uptime_minutes())}'
        if text==self.readout:
            return False
        self.readout=text
        if self.tray is not None:
            self.tray.setToolTip(text)
        return True

    def show_reading(self, point):
        self.refresh_readout()
        if self.tray is not None:
            QToolTip.showText(point, self.readout)
        else:
            window = self.service.window
            QToolTip.showText(point, self.readout, window, capsule_rect(window))

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_reading(QCursor.pos())

    def schedule_frame(self, now):
        remaining = self.next_frame - now
        sample = 0
        if self.samples_per_tick > 1 and isfinite(remaining):
            progress = max(0., 1 - remaining * self.fps)
            sample = min(self.samples_per_tick - 1, int(progress * self.samples_per_tick))
            remaining -= (self.samples_per_tick - 1 - sample) / (self.samples_per_tick * self.fps)
        self.timer.start(max(1, ceil(min(2_147_483_647, remaining * 1000))))
        return sample

    def advance_ticks(self, now):
        if now >= self.next_frame:
            ticks = 1 + floor((now - self.next_frame) * self.fps)
            self.cycle_tick = (self.cycle_tick + ticks) % FRAMES
            self.next_frame += ticks / self.fps

    def advance(self):
        if not self.fps:
            return
        now = perf_counter()
        self.advance_ticks(now)
        self.present_frame(self.schedule_frame(now))

    def present_frame(self, sample):
        position = self.cycle_tick * self.samples_per_tick + sample
        frame = position * frame_count(self.animal) // (FRAMES * self.samples_per_tick)
        if self.frame == frame:
            return
        self.frame = frame
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
