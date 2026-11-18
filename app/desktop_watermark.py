"""Non-interactive desktop text overlays, rendered only when their surface changes."""
import math
import os

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QPainter, QTextLayout, QTextOption, QTransform
from PyQt5.QtWidgets import QApplication, QWidget

from window_layers import click_through, desktop_layer, native, shell_owner


class WatermarkStamp:
    def __init__(self, cfg, area):
        self.angle = cfg['watermark_angle']
        self.color = QColor(cfg['watermark_color'] or '#ffffff')
        self.color.setAlpha(round(cfg['watermark_opacity'] * 255 / 100))
        font = QFont('Microsoft YaHei UI')
        font.setPixelSize(cfg['watermark_size'])
        text = cfg['watermark_text']
        limit = area.width() * (.52 if cfg['watermark_mode'] == 'tile' else .92)
        width = max(1, min(math.ceil(QFontMetricsF(font).horizontalAdvance(text))+2, limit))
        self.layout = QTextLayout(text, font)
        option = QTextOption(Qt.AlignHCenter)
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.layout.setTextOption(option)
        self.layout.setCacheEnabled(True)
        self.layout.beginLayout()
        height = 0
        while True:
            line = self.layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            line.setPosition(QPointF(0, height))
            height += line.height()
        self.layout.endLayout()
        self.offset = QPointF(-width / 2, -height / 2)
        rotated = QTransform().rotate(self.angle).mapRect(QRectF(0, 0, width, height))
        # Fit the entire rotated string even on a small work area.
        self.scale = min(1., max(1, area.width()-8) / max(1, rotated.width()),
                         max(1, area.height()-8) / max(1, rotated.height()))
        self.size = QSize(math.ceil(rotated.width()*self.scale)+4, math.ceil(rotated.height()*self.scale)+4)

    def draw(self, painter, center):
        painter.save()
        painter.translate(center)
        painter.scale(self.scale, self.scale)
        painter.rotate(self.angle)
        painter.setPen(self.color)
        self.layout.draw(painter, self.offset)
        painter.restore()


def single_geometry(area, size, position):
    bounds = QRect(QPoint(), size.boundedTo(area.size()))
    bounds.moveCenter(area.center())
    gap = min(24, (area.width()-bounds.width())//2, (area.height()-bounds.height())//2)
    if position == 'top':
        bounds.moveTop(area.top()+gap)
    elif position == 'bottom':
        bounds.moveBottom(area.bottom()-gap)
    elif position == 'left':
        bounds.moveLeft(area.left()+gap)
    elif position == 'right':
        bounds.moveRight(area.right()-gap)
    return bounds


def tile_centers(area, stamp, density):
    gap = (11-density)*18
    step_x, step_y = stamp.width()+2*gap, stamp.height()+gap
    # Center the grid so small displays always have a complete middle stamp.
    middle = area.center()
    columns = math.ceil(area.width() / (2*step_x))
    rows = math.ceil(area.height() / (2*step_y))
    visible = area.adjusted(-stamp.width()/2, -stamp.height()/2, stamp.width()/2, stamp.height()/2)
    for y in range(-rows, rows+1):
        for x in range(-columns, columns+1):
            center = QPointF(middle.x()+x*step_x, middle.y()+y*step_y)
            if visible.contains(center):
                yield center


class WatermarkWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle('桌面文字水印 · 大肥鱼Dock')
        self.signature = None
        self.stamp = None

    def configure(self, cfg, screen):
        tiled = cfg['watermark_mode'] == 'tile'
        area = screen.geometry() if tiled else screen.availableGeometry()
        signature = (area.getRect(), screen.devicePixelRatio(), *(cfg['watermark_'+key] for key in
                     ('text','color','size','angle','opacity','mode','position','density','layer')))
        if signature == self.signature and self.isVisible():
            return
        self.tiled, self.density = tiled, cfg['watermark_density']
        self.stamp = WatermarkStamp(cfg, area)
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(area if tiled else single_geometry(area, self.stamp.size, cfg['watermark_position']))
        self.show()
        # Qt and Win32 both pass input through, including over painted letters.
        user = native()
        hwnd = int(self.winId())
        extended = user.GetWindowLongW(hwnd, -20)
        user.SetWindowLongW(hwnd, -20, extended | 0x08000000)  # WS_EX_NOACTIVATE
        click_through(self, True)
        top = cfg['watermark_layer'] == 'top'
        owner = 0 if top or os.environ.get('FISHDOCK_TEST_DESKTOP') else shell_owner()
        desktop_layer(hwnd, top, owner)
        self.signature = signature
        self.update()

    def paintEvent(self, event):
        if self.stamp is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        area = QRectF(self.rect())
        if self.tiled:
            for center in tile_centers(area, self.stamp.size, self.density):
                self.stamp.draw(painter, center)
        else:
            self.stamp.draw(painter, area.center())
        painter.end()


class DesktopWatermarks:
    def __init__(self, runtime):
        self.runtime = runtime
        self.windows = {}

    def sync(self):
        cfg = self.runtime.dock.cfg
        screens = []
        if (cfg['watermark_enabled'] and cfg['watermark_text'].strip() and cfg['watermark_opacity'] > 0
                and not self.runtime.game_active and not self.runtime.closed):
            screens = QApplication.screens() if cfg['watermark_mode'] == 'tile' else [QApplication.primaryScreen()]
        for screen in tuple(self.windows):
            if screen not in screens:
                window = self.windows.pop(screen)
                window.hide()
                window.deleteLater()
        for screen in filter(None, screens):
            if screen not in self.windows:
                self.windows[screen] = WatermarkWindow()
            self.windows[screen].configure(cfg, screen)
