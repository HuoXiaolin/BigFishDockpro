"""Short, non-activating Dock startup animation drawn with Qt."""
from math import cos, tau

from PyQt5.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QGradient, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QWidget


WORDMARK = 'PureDock'
OUTLINE_WIDTH = 279


def dock_strokes():
    prefix_capital = QPainterPath()
    prefix_capital.moveTo(0, 38)
    prefix_capital.lineTo(0, 0)
    prefix_capital.lineTo(13, 0)
    prefix_capital.cubicTo(30, 0, 30, 21, 13, 21)
    prefix_capital.lineTo(0, 21)

    bowl = QPainterPath()
    bowl.moveTo(37, 12)
    bowl.lineTo(37, 26)
    bowl.cubicTo(37, 42, 61, 42, 61, 26)
    bowl.moveTo(61, 12)
    bowl.lineTo(61, 38)

    shoulder = QPainterPath()
    shoulder.moveTo(74, 38)
    shoulder.lineTo(74, 12)
    shoulder.moveTo(74, 24)
    shoulder.cubicTo(74, 17, 80, 12, 88, 12)
    shoulder.lineTo(91, 12)

    loop = QPainterPath()
    loop.moveTo(101, 24)
    loop.lineTo(127, 24)
    loop.cubicTo(127, 17, 122, 12, 115, 12)
    loop.cubicTo(107, 12, 101, 17, 101, 25)
    loop.cubicTo(101, 33, 106, 38, 115, 38)
    loop.cubicTo(120, 38, 124, 36, 126, 33)

    capital = QPainterPath()
    capital.moveTo(0, 38)
    capital.lineTo(0, 0)
    capital.lineTo(12, 0)
    capital.cubicTo(36, 0, 36, 38, 12, 38)
    capital.closeSubpath()

    ring = QPainterPath()
    ring.addEllipse(QRectF(42, 12, 26, 26))

    curve = QPainterPath()
    arc = QRectF(79, 12, 26, 26)
    curve.arcMoveTo(arc, 45)
    curve.arcTo(arc, 45, 270)

    stem = QPainterPath()
    stem.moveTo(116, 0)
    stem.lineTo(116, 38)
    arms = QPainterPath()
    arms.moveTo(137, 12)
    arms.lineTo(116, 27)
    arms.lineTo(138, 38)
    suffix = tuple(path.translated(141, 0) for path in (capital, ring, curve, stem, arms))
    return (prefix_capital, bowl, shoulder, loop) + suffix


def text_shape(text, font):
    path = QPainterPath()
    path.addText(QPointF(), font, text)
    bounds = path.boundingRect()
    return path.translated(-bounds.left(), -bounds.center().y())


class StartupAnimation(QWidget):
    DESIGN_WIDTH = 336
    DESIGN_HEIGHT = 86
    ARTWORK_SCALE = 1.5
    INTRO_MS = 700
    SETTLE_MS = 530
    HOLD_MS = 2020
    FADE_MS = 180
    READY_MS = INTRO_MS + SETTLE_MS
    FADE_START_MS = READY_MS + HOLD_MS
    DURATION_MS = FADE_START_MS + FADE_MS
    FRAME_INTERVAL_MS = 16

    def __init__(self, style, language, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.NoFocus)
        self.artwork_scale = self.ARTWORK_SCALE
        self.setObjectName('DockStartupAnimation')
        self.setWindowTitle(WORDMARK)
        self.setAccessibleName(WORDMARK)
        self.style_name = style
        self.clock = QElapsedTimer()
        self.settle = QEasingCurve(QEasingCurve.OutCubic)
        self.roll = QEasingCurve(QEasingCurve.OutBack)
        self.roll.setOvershoot(0.72)
        self.frames = QTimer(self)
        self.frames.setTimerType(Qt.PreciseTimer)
        self.frames.setSingleShot(True)
        self.frames.timeout.connect(self.next_frame)

        if self.style_name == 'rolling':
            words = ('Starting', 'Ready') if language == 'en' else ('启动中', '已就绪')
            font = QFont('Segoe UI')
            font.setPixelSize(34)
            font.setWeight(QFont.DemiBold)
            title = text_shape(WORDMARK, font)
            if language != 'en':
                font.setFamily('Microsoft YaHei UI')
            font.setPixelSize(23)
            self.word_shapes = tuple(text_shape(word, font) for word in words)
            center = self.DESIGN_HEIGHT / 2
            title_width = title.boundingRect().width()
            word_width = max(path.boundingRect().width() for path in self.word_shapes) + 4
            left = (self.DESIGN_WIDTH - title_width - 14 - word_width) / 2
            self.title_shape = title.translated(left, center)
            self.word_viewport = QRectF(left + title_width + 14, center - 22, word_width, 44)
            self.word_mask = QLinearGradient(0, self.word_viewport.top(), 0, self.word_viewport.bottom())
            self.word_mask.setColorAt(0, Qt.transparent)
            self.word_mask.setColorAt(.20, Qt.white)
            self.word_mask.setColorAt(.80, Qt.white)
            self.word_mask.setColorAt(1, Qt.transparent)
            self.title_color = QLinearGradient(0, 0, 0, 1)
            self.title_color.setCoordinateMode(QGradient.ObjectBoundingMode)
            self.title_color.setColorAt(0, QColor('#88E8FF'))
            self.title_color.setColorAt(1, QColor('#389EFA'))
            self.word_color = QLinearGradient(0, 0, 0, 1)
            self.word_color.setCoordinateMode(QGradient.ObjectBoundingMode)
            self.word_color.setColorAt(0, QColor('#E3C7FF'))
            self.word_color.setColorAt(1, QColor('#9B7CFF'))
        else:
            self.strokes = tuple((path, path.length()) for path in dock_strokes())
            self.stroke_color = QLinearGradient(0, 38, OUTLINE_WIDTH, 0)
            self.stroke_color.setColorAt(0, QColor('#49D8FF'))
            self.stroke_color.setColorAt(.52, QColor('#CAA5FF'))
            self.stroke_color.setColorAt(1, QColor('#55F5C8'))

    def play(self, screen=None):
        screen = screen or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None
        if area is not None and area.isValid():
            self.artwork_scale = min(self.ARTWORK_SCALE, area.width() / self.DESIGN_WIDTH,
                                     area.height() / self.DESIGN_HEIGHT)
        self.setFixedSize(round(self.DESIGN_WIDTH * self.artwork_scale),
                          round(self.DESIGN_HEIGHT * self.artwork_scale))
        if area is not None and area.isValid():
            self.move(area.center() - self.rect().center())
        self.show()
        from window_layers import click_through, native
        click_through(self, True)
        hwnd = int(self.winId())
        user = native()
        extended = user.GetWindowLongW(hwnd, -20)
        user.SetWindowLongPtrW(hwnd, -20, extended | 0x08000000)  # WS_EX_NOACTIVATE
        self.clock.start()
        first_interval = self.INTRO_MS if self.style_name == 'rolling' else self.FRAME_INTERVAL_MS
        self.frames.start(first_interval)

    def next_frame(self):
        elapsed = self.clock.elapsed()
        if elapsed >= self.DURATION_MS:
            self.close()
        elif elapsed >= self.FADE_START_MS:
            remaining = self.DURATION_MS - elapsed
            self.setWindowOpacity(remaining / self.FADE_MS)
            self.update()  # Flush the translucent window with the new opacity.
            self.frames.start(min(self.FRAME_INTERVAL_MS, remaining))
        elif elapsed >= self.READY_MS:
            # Draw the settled frame once, then let it hold until the fade.
            self.update()
            self.frames.start(self.FADE_START_MS - elapsed)
        else:
            self.update()
            self.frames.start(min(self.FRAME_INTERVAL_MS, self.READY_MS - elapsed))

    def closeEvent(self, event):
        self.frames.stop()
        super().closeEvent(event)

    def paintEvent(self, event):
        elapsed = self.clock.elapsed() if self.clock.isValid() else 0
        progress = max(0.0, min(1.0, (elapsed - self.INTRO_MS) / self.SETTLE_MS))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        # Scale the vector shapes and their stroke widths together.
        painter.scale(self.artwork_scale, self.artwork_scale)
        if self.style_name == 'rolling':
            self.paint_words(painter, progress)
        else:
            self.paint_outline(painter, elapsed, progress)

    def paint_outline(self, painter, elapsed, progress):
        # Flowing dash motion inspired by SelfMadeSystem's Uiverse loader.
        painter.translate((self.DESIGN_WIDTH - OUTLINE_WIDTH) / 2, (self.DESIGN_HEIGHT - 38) / 2)
        painter.setBrush(Qt.NoBrush)
        width = 3.5
        pen = QPen(self.stroke_color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setOpacity(.22)
        for path, _ in self.strokes:
            painter.drawPath(path)
        painter.setOpacity(1.0)

        phase = elapsed / 1200
        settle = self.settle.valueForProgress(progress)
        for index, (path, length) in enumerate(self.strokes):
            offset = phase + index * .15
            coverage = .4 + .3 * (.5 - .5 * cos(tau * offset))
            coverage += (1 - coverage) * settle
            if coverage < .995:
                unit = length / width
                pen.setDashPattern([unit * coverage, unit * (1 - coverage)])
                pen.setDashOffset(-unit * offset)
            else:
                pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.drawPath(path)

    def paint_words(self, painter, progress):
        viewport = self.word_viewport
        painter.fillPath(self.title_shape, self.title_color)

        painter.setClipRect(viewport)
        travel = viewport.height() * self.roll.valueForProgress(progress)
        for index, shape in enumerate(self.word_shapes):
            word = shape.translated(viewport.left() + 2, viewport.center().y() + index * viewport.height() - travel)
            painter.fillPath(word, self.word_color)

        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.fillRect(viewport, self.word_mask)
