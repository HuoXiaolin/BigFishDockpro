"""Shared native Qt styling. Dock painting and glass rendering stay unchanged."""
from PyQt5.QtGui import QColor, QPalette, QFont, QPen, QPainterPath, QPainter, QIcon, QPixmapCache
from PyQt5.QtCore import Qt, QRectF, QSize, QRect, QObject, QEvent, QCoreApplication
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel, QPushButton,
    QProxyStyle, QStyle, QStyleFactory, QSpinBox, QComboBox, QToolButton,
    QAbstractSpinBox, QCheckBox, QStyleOptionButton, QSizePolicy, QWidget, QHBoxLayout, QSizeGrip)

THEME_COLORS = [('冰川蓝','#8fbfe0'), ('薄荷绿','#8fc9b0'), ('青碧','#70b9bc'),
                ('雾紫','#b3a0d6'), ('樱花粉','#dea6bb'), ('暖杏','#e5ba8d'), ('石墨灰','#8a95a5')]


class ColorSwatch(QToolButton):
    def __init__(self, field, name, color, parent):
        super().__init__(parent)
        self.field, self.color = field, color
        self.setFixedSize(32, 30)
        self.setAccessibleName(name+' '+color)
        self.setToolTip(name+' · '+color)
        self.clicked.connect(lambda: field.setText(color))
        field.textChanged.connect(self.update)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        chosen = self.field.text().strip().casefold() == self.color
        p.setPen(QPen(self.palette().color(QPalette.Text), 1.5) if chosen or self.hasFocus() else Qt.NoPen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1), 6, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(5,5,-5,-5), 4, 4)
        if self.underMouse():
            p.setPen(QPen(self.palette().color(QPalette.Text), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4,4,-4,-4), 5, 5)


class ThemeSwatches(QWidget):
    def __init__(self, field):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(6)
        self.buttons = []
        for name, color in THEME_COLORS:
            swatch = ColorSwatch(field, name, color, self)
            row.addWidget(swatch)
            self.buttons.append(swatch)
        row.addStretch()


class CaptionButton(QToolButton):
    """DPI-independent thin strokes, with native button keyboard semantics."""
    def __init__(self, window, close=False):
        super().__init__(window)
        self.close_button = close
        self.setObjectName('CaptionClose' if close else 'CaptionMinimize')
        self.setFixedSize(36, 32)
        self.setAccessibleName('关闭' if close else '最小化')
        self.setToolTip(self.accessibleName())
        self.clicked.connect(window.reject if close else window.showMinimized)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.isDown() or self.hasFocus():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#c5343f') if self.close_button else self.palette().color(QPalette.AlternateBase))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1), 6, 6)
        color = QColor('white') if self.close_button and self.underMouse() else self.palette().color(QPalette.Text)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap))
        cx, cy = self.width()/2, self.height()/2
        if self.close_button:
            painter.drawLine(int(cx-4), int(cy-4), int(cx+4), int(cy+4))
            painter.drawLine(int(cx+4), int(cy-4), int(cx-4), int(cy+4))
        else: painter.drawLine(int(cx-5), int(cy), int(cx+5), int(cy))


class SettingsHeader(QWidget):
    def __init__(self, window, caption='大肥鱼Dock 设置'):
        super().__init__(window)
        self.drag_offset = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        title = label(caption, 'title')
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(title)
        row.addStretch()
        self.minimize = CaptionButton(window)
        self.close = CaptionButton(window, True)
        row.addWidget(self.minimize)
        row.addWidget(self.close)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPos()-self.window().pos()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPos()-self.drag_offset)

    def mouseReleaseEvent(self, event): self.drag_offset = None


class SettingsGrip(QSizeGrip):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.Mid), 1.2, Qt.SolidLine, Qt.RoundCap))
        for distance in (4, 8):
            painter.drawLine(self.width()-distance, self.height()-2, self.width()-2, self.height()-distance)


class ModernComboBox(QComboBox):
    def __init__(self, *args):
        super().__init__(*args)
        self.setProperty('modern', True)
        self.setMaxVisibleItems(9)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.Text if self.isEnabled() else QPalette.Mid), 1.5))
        cx, cy = self.width()-18, self.height()/2
        path = QPainterPath()
        path.moveTo(cx-4, cy-2)
        path.lineTo(cx, cy+2)
        path.lineTo(cx+4, cy-2)
        painter.drawPath(path)


class ModernSpinBox(QSpinBox):
    def __init__(self, *args):
        super().__init__(*args)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setProperty('modern', True)
        self.minus = QToolButton(self)
        self.plus = QToolButton(self)
        for widget, text, name, callback in [(self.minus, '−', '减少数值', self.stepDown),
                                              (self.plus, '+', '增加数值', self.stepUp)]:
            widget.setText(text)
            widget.setAccessibleName(name)
            widget.setObjectName('SpinStep')
            widget.setAutoRepeat(True)
            widget.setFocusPolicy(Qt.NoFocus)
            widget.clicked.connect(callback)
        self.valueChanged.connect(self.sync_steps)
        self.sync_steps()

    def sync_steps(self):
        self.minus.setEnabled(self.value() > self.minimum())
        self.plus.setEnabled(self.value() < self.maximum())

    def showEvent(self, event):
        self.sync_steps()
        super().showEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        y = (self.height()-26)//2
        self.minus.setGeometry(self.width()-62, y, 26, 26)
        self.plus.setGeometry(self.width()-32, y, 26, 26)


class ModernCheckBox(QCheckBox):
    """A wrapping native checkbox, retaining keyboard and accessibility behavior."""
    def __init__(self, *args):
        super().__init__(*args)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def heightForWidth(self, width):
        return max(30, self.fontMetrics().boundingRect(QRect(0,0,max(50,width-30),1000),
                    Qt.TextWordWrap, self.text()).height()+10)

    def sizeHint(self):
        width = min(340, self.fontMetrics().horizontalAdvance(self.text())+32)
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self): return QSize(110, 30)

    def hitButton(self, point): return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''
        self.style().drawControl(QStyle.CE_CheckBox, option, painter, self)
        painter.setPen(self.palette().color(QPalette.Text if self.isEnabled() else QPalette.Mid))
        painter.drawText(self.rect().adjusted(30,4,0,-4), Qt.TextWordWrap | Qt.AlignVCenter, self.text())


class ReadableChecks(QProxyStyle):
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(option.palette.color(QPalette.Mid), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(option.rect).adjusted(1,1,-1,-1), 5, 5)
            painter.restore()
            return
        if element not in (QStyle.PE_IndicatorCheckBox, QStyle.PE_IndicatorItemViewItemCheck):
            return super().drawPrimitive(element, option, painter, widget)
        rect = QRectF(option.rect).adjusted(1,1,-1,-1)
        painter.save()
        painter.setRenderHint(painter.Antialiasing)
        checked = bool(option.state & (QStyle.State_On | QStyle.State_NoChange))
        ink = option.palette.color(QPalette.Text)
        paper = option.palette.color(QPalette.Base)
        painter.setPen(QPen(ink if checked else option.palette.color(QPalette.Mid), 1.1))
        painter.setBrush(ink if checked else paper)
        painter.drawRoundedRect(rect, 3, 3)
        if checked:
            tick = QPainterPath()
            tick.moveTo(rect.left()+rect.width()*.20, rect.top()+rect.height()*.52)
            tick.lineTo(rect.left()+rect.width()*.43, rect.top()+rect.height()*.75)
            tick.lineTo(rect.left()+rect.width()*.82, rect.top()+rect.height()*.26)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(paper, 1.8))
            painter.drawPath(tick)
        painter.restore()


class DialogChrome(QObject):
    def eventFilter(self, widget, event):
        if event.type() == QEvent.Show and isinstance(widget, QDialog) and not widget.windowFlags() & Qt.FramelessWindowHint:
            import ctypes
            from ctypes import wintypes
            api = ctypes.windll.dwmapi
            api.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            palette = widget.palette()
            ground = palette.color(QPalette.Window)
            dark = ctypes.c_int(ground.lightness() < 128)
            handle = int(widget.winId())
            api.DwmSetWindowAttribute(handle, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            for attribute, color in [(35, ground), (36, palette.color(QPalette.WindowText))]:
                value = wintypes.DWORD(color.red() | color.green()<<8 | color.blue()<<16)
                api.DwmSetWindowAttribute(handle, attribute, ctypes.byref(value), ctypes.sizeof(value))
        return False


def apply_theme(app, light):
    if not hasattr(app, '_fish_icon'):
        import sys
        from pathlib import Path
        app._fish_icon = QIcon(str(Path(getattr(sys, '_MEIPASS', Path(__file__).parent))/'dock.ico'))
        app.setWindowIcon(app._fish_icon)
    # Keep the base style alive for the entire QApplication. Replacing proxy
    # styles under live stylesheet widgets leaves native cached style pointers
    # vulnerable during teardown after repeated preset/theme changes.
    if not hasattr(app, '_fish_style'):
        QPixmapCache.setCacheLimit(4096)
        app._fish_style = ReadableChecks(QStyleFactory.create('Fusion'))
        app.setStyle(app._fish_style)
    app.setFont(QFont('Microsoft YaHei UI', 10))
    colors = ({'ground':'#f7f8fa','surface':'#ffffff','text':'#17191c','muted':'#5c626c',
               'line':'#d5d9df','hover':'#eceff3','primary':'#22262c','on':'#ffffff',
               'danger':'#b4232c','selection':'#e9eaec'} if light else
              {'ground':'#161719','surface':'#202124','text':'#f1f2f4','muted':'#b4b8c0',
               'line':'#44474e','hover':'#303238','primary':'#f1f2f4','on':'#18191c',
               'danger':'#ff8e99','selection':'#303236'})
    p = QPalette()
    for role, key in [(QPalette.Window,'ground'), (QPalette.Base,'surface'),
                      (QPalette.AlternateBase,'ground'), (QPalette.WindowText,'text'),
                      (QPalette.Text,'text'), (QPalette.Button,'surface'),
                      (QPalette.ButtonText,'text'), (QPalette.Highlight,'selection'),
                      (QPalette.HighlightedText,'text'), (QPalette.ToolTipBase,'surface'),
                      (QPalette.ToolTipText,'text'), (QPalette.PlaceholderText,'muted')]:
        p.setColor(role, QColor(colors[key]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(colors['muted']))
    p.setColor(QPalette.Mid, QColor('#7a808a' if light else '#858b95'))
    p.setColor(QPalette.Link, QColor('#225eaa' if light else '#8fc2ff'))
    p.setColor(QPalette.LinkVisited, QColor('#225eaa' if light else '#8fc2ff'))
    app.setPalette(p)
    app.setStyleSheet('''
        * {font-family:"Microsoft YaHei UI"; font-size:13px;}
        QDialog[compactDialog="true"] QLabel, QDialog[compactDialog="true"] QLineEdit,
        QDialog[compactDialog="true"] QComboBox, QDialog[compactDialog="true"] QSpinBox,
        QDialog[compactDialog="true"] QCheckBox, QDialog[compactDialog="true"] QPushButton,
        QDialog[compactDialog="true"] QListWidget {font-size:14px;}
        QDialog[compactDialog="true"] QLabel[role="title"] {font-size:20px; font-weight:600;}
        QDialog[compactDialog="true"] QLabel[role="page-title"] {font-size:17px; font-weight:600;}
        QDialog[compactDialog="true"] QLineEdit, QDialog[compactDialog="true"] QSpinBox,
        QDialog[compactDialog="true"] QComboBox {padding-top:5px; padding-bottom:5px; min-height:22px;}
        QDialog[compactDialog="true"] QPushButton {padding-top:5px; padding-bottom:5px; min-height:22px;}
        QDialog, QMessageBox {background:%(ground)s; color:%(text)s;}
        QDialog[compactDialog="true"] {border:1px solid %(line)s;}
        QLabel {color:%(text)s; background:transparent;}
        QLabel[role="title"] {font-size:22px; font-weight:600;}
        QLabel[role="muted"] {color:%(muted)s;}
        QLabel[role="section"] {font-size:15px; font-weight:600;}
        QPushButton {background:%(surface)s; color:%(text)s; border:1px solid %(line)s;
            border-radius:8px; padding:8px 16px; min-height:22px;}
        QPushButton:hover {background:%(hover)s;}
        QPushButton:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus {border:1px solid %(text)s;}
        QPushButton:pressed {background:%(selection)s;}
        QPushButton[role="primary"] {background:%(primary)s; color:%(on)s; border-color:%(primary)s;}
        QPushButton[role="primary"]:hover {border:1px solid %(muted)s;}
        QPushButton[role="danger"] {color:%(danger)s;}
        QPushButton:disabled {color:%(muted)s; background:%(ground)s; border-color:%(line)s;}
        QLineEdit, QSpinBox, QComboBox {background:%(surface)s; color:%(text)s;
            border:1px solid %(line)s; border-radius:8px; padding:8px 12px; min-height:22px;}
        QComboBox {padding-right:34px;}
        QComboBox[modern="true"]::drop-down {border:0; width:32px; background:transparent;}
        QComboBox[modern="true"]::down-arrow {image:none; width:0; height:0;}
        QSpinBox[modern="true"] {padding-right:68px;}
        QSpinBox QLineEdit {border:0; background:transparent; padding:0; min-height:0;}
        QDialog[compactDialog="true"] QSpinBox QLineEdit {border:0; background:transparent; padding:0; min-height:0;}
        QToolButton#SpinStep {border:0; border-radius:5px; background:transparent; color:%(muted)s; font-size:16px;}
        QToolButton#SpinStep:hover {background:%(hover)s; color:%(text)s;}
        QToolButton#SpinStep:pressed {background:%(selection)s;}
        QToolButton#SpinStep:disabled {color:%(line)s;}
        QComboBox QAbstractItemView {background:%(surface)s; color:%(text)s;
            border:1px solid %(line)s; outline:0; selection-background-color:%(selection)s;
            selection-color:%(text)s; padding:5px;}
        QListWidget {background:%(surface)s; color:%(text)s; border:1px solid %(line)s; border-radius:8px; padding:6px;}
        QListWidget::item {min-height:30px; padding:7px 10px; border-radius:4px;}
        QListWidget::item:selected {background:%(selection)s; color:%(text)s;}
        QListWidget::item:hover {background:%(hover)s;}
        QListWidget#SettingsNav {background:transparent; border:0; padding:0; outline:0;}
        QListWidget#SettingsNav::item {height:28px; min-height:28px; padding:8px 12px; margin:2px 0; border-radius:8px; color:%(muted)s;}
        QListWidget#SettingsNav::item:selected {background:%(selection)s; color:%(text)s; font-weight:600;}
        QListWidget#SettingsNav::item:hover {background:%(hover)s;}
        QLabel[role="page-title"] {font-size:18px; font-weight:600;}
        QCheckBox {color:%(text)s; spacing:9px; padding:4px 0;}
        QCheckBox::indicator {width:18px; height:18px;}
        QTabBar::tab {background:transparent; color:%(muted)s; padding:10px 16px; border-bottom:2px solid transparent;}
        QTabBar::tab:selected {color:%(text)s; border-bottom:2px solid %(text)s;}
        QTabWidget::pane {border:0;}
        QScrollArea {border:0; background:transparent;}
        QScrollArea > QWidget > QWidget {background:%(ground)s;}
        QScrollBar:vertical {background:transparent; width:10px; margin:0;}
        QScrollBar::handle:vertical {background:%(line)s; min-height:30px; border-radius:5px;}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background:transparent;}
        QScrollBar:horizontal {background:transparent; height:8px; margin:0;}
        QScrollBar::handle:horizontal {background:%(line)s; min-width:30px; border-radius:4px;}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {width:0;}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {background:transparent;}
        QMenu {background:%(surface)s; color:%(text)s; border:1px solid %(line)s; padding:5px;}
        QMenu::item {padding:7px 26px 7px 22px; border-radius:4px;}
        QMenu::item:selected {background:%(selection)s;}
        QMenu::separator {height:1px; background:%(line)s; margin:5px 10px;}
        QToolTip {background:%(surface)s; color:%(text)s; border:1px solid %(line)s; padding:6px;}
    ''' % colors)
    if not hasattr(app, '_chrome_filter'):
        app._chrome_filter = DialogChrome(app)
        app.installEventFilter(app._chrome_filter)


def label(text, role=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if role:
        widget.setProperty('role', role)
    return widget


def button(text, callback, role=None):
    widget = QPushButton(text)
    if role:
        widget.setProperty('role', role)
    widget.clicked.connect(callback)
    return widget


def shutdown_ui(app):
    """Delete GUI resources while QApplication and its paint/style services live."""
    from PyQt5 import sip
    if hasattr(app, '_chrome_filter'):
        app.removeEventFilter(app._chrome_filter)
    for widget in list(app.topLevelWidgets()):
        if not sip.isdeleted(widget):
            widget.hide()
            widget.deleteLater()
    # Tests use nested loops; simply returning would leave deferred native widget
    # destruction to Python interpreter teardown, after Qt services start dying.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
