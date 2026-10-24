"""Shared native Qt styling. Dock painting and glass rendering stay unchanged."""
from PyQt5.QtGui import QColor, QPalette, QFont, QPen, QPainterPath, QPainter, QIcon, QPixmapCache
from PyQt5.QtCore import Qt, QRectF, QSize, QRect, QObject, QEvent, QCoreApplication, QPoint
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel, QPushButton,
    QProxyStyle, QStyle, QStyleFactory, QSpinBox, QComboBox, QToolButton,
    QAbstractSpinBox, QCheckBox, QStyleOptionButton, QSizePolicy, QWidget, QHBoxLayout, QSizeGrip,
    QListView, QStyledItemDelegate, QMenu, QFrame, QAbstractItemView)

# Half the former screen area, while retaining readable text at normal DPI.
UI_DENSITY = 0.70

def widget_px(widget,value):
    node=widget
    while node is not None:
        factor=node.property('interfaceScale')
        if factor:return max(1,round(value*float(factor)))
        node=node.parent()
    return compact_px(value)


def compact_px(value):
    return max(1, round(value * UI_DENSITY)) if value > 0 else value


def compact_dialog(dialog):
    """Apply geometry density once; theme changes and reopens must never rescale."""
    if dialog.property('densityApplied'):
        return
    dialog.setProperty('densityApplied', True)
    dialog.setProperty('compactDialog', True)
    size = dialog.size()
    minimum = dialog.minimumSize()
    for widget in [dialog] + dialog.findChildren(QWidget):
        if widget is not dialog and widget.window() is not dialog:
            continue
        for axis in ('Width', 'Height'):
            lower = getattr(widget, 'minimum'+axis)()
            upper = getattr(widget, 'maximum'+axis)()
            if lower == upper and upper < 16777215:
                getattr(widget, 'setFixed'+axis)(compact_px(lower))
        if isinstance(widget, QAbstractItemView):
            icons = widget.iconSize()
            if icons.isValid():widget.setIconSize(QSize(compact_px(icons.width()), compact_px(icons.height())))
        layout = widget.layout()
        def compress(current):
            margins=current.contentsMargins()
            current.setContentsMargins(*(compact_px(v) for v in (margins.left(),margins.top(),margins.right(),margins.bottom())))
            if current.spacing() >= 0:current.setSpacing(compact_px(current.spacing()))
            if hasattr(current,'horizontalSpacing'):
                for name in ('HorizontalSpacing','VerticalSpacing'):
                    value=getattr(current,name[0].lower()+name[1:])()
                    if value>=0:getattr(current,'set'+name)(compact_px(value))
            for i in range(current.count()):
                child=current.itemAt(i).layout()
                if child is not None:compress(child)
        if layout is not None:compress(layout)
    dialog.setMinimumSize(compact_px(minimum.width()),compact_px(minimum.height()))
    dialog.resize(compact_px(size.width()),compact_px(size.height()))


def density_stylesheet(stylesheet,factor=UI_DENSITY):
    """Scope compact metrics to dialogs/menus; desktop card metrics remain local."""
    import re
    rules=[]
    for selectors,body in re.findall(r'([^{}]+)\{([^{}]*)\}',stylesheet):
        scoped=[]
        for selector in selectors.split(','):
            selector=selector.strip()
            if selector=='*':scoped.extend(('QDialog','QDialog *','QMenu','QToolTip'))
            elif selector.startswith(('QDialog','QMessageBox','QMenu','QToolTip')):scoped.append(selector)
            else:scoped.append('QDialog '+selector)
        def scale(match):
            number=int(match.group(1));prefix=body[:match.start()].rsplit(';',1)[-1]
            value=max(10,round(number*factor)) if 'font-size' in prefix else max(1,round(number*factor)) if number>0 else 0
            return str(value)+'px'
        rules.append(', '.join(scoped)+' {'+re.sub(r'(\d+)px',scale,body)+'}')
    return '\n'.join(rules)


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
        p.setPen(QPen(self.palette().color(QPalette.Text), 1.5) if chosen or self.property('keyboardFocus') else Qt.NoPen)
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
        if self.underMouse() or self.isDown() or self.property('keyboardFocus'):
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


class PopupDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width()+compact_px(16), max(compact_px(32), option.fontMetrics.height()+compact_px(14)))


class AlignedMenu(QMenu):
    """One text column for checked, ordinary and submenu actions."""
    def addMenu(self, title):
        if isinstance(title, str):
            menu = AlignedMenu(title, self)
            super().addMenu(menu)
            return menu
        return super().addMenu(title)

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(max(compact_px(220), size.width()), size.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        font = self.font(); font.setUnderline(False); p.setFont(font)
        p.setPen(QPen(palette.color(QPalette.Mid), .7))
        p.setBrush(palette.color(QPalette.Base))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5), 7, 7)
        for action in self.actions():
            if not action.isVisible(): continue
            rect = self.actionGeometry(action)
            rect.setRight(self.width()-compact_px(6))
            if action.isSeparator():
                p.setPen(QPen(palette.color(QPalette.Mid), .5))
                p.drawLine(rect.left()+12, rect.center().y(), rect.right()-12, rect.center().y())
                continue
            if action == self.activeAction() and action.isEnabled():
                p.setPen(Qt.NoPen); p.setBrush(palette.color(QPalette.Highlight))
                p.drawRoundedRect(QRectF(rect).adjusted(3,1,-3,-1), 4, 4)
            ink = palette.color(QPalette.Text if action.isEnabled() else QPalette.Mid)
            p.setPen(ink)
            p.drawText(rect.adjusted(compact_px(32),0,-compact_px(25),0), Qt.AlignVCenter, action.text().replace('&',''))
            if action.isChecked():
                path = QPainterPath(); y = rect.center().y()
                path.moveTo(rect.left()+compact_px(11),y); path.lineTo(rect.left()+compact_px(14),y+compact_px(3)); path.lineTo(rect.left()+compact_px(20),y-compact_px(4))
                p.setPen(QPen(ink,1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin)); p.drawPath(path)
            if action.menu():
                path = QPainterPath(); x,y = rect.right()-compact_px(13),rect.center().y()
                path.moveTo(x-2,y-3); path.lineTo(x+1,y); path.lineTo(x-2,y+3)
                p.setPen(QPen(ink,1.4)); p.drawPath(path)


class PopupList(QListView):
    def __init__(self, combo, parent):
        super().__init__(parent)
        self.combo = combo

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.combo.choose_popup(self.currentIndex())
            event.accept()
        elif event.key()==Qt.Key_Escape:
            self.combo.hidePopup(); event.accept()
        else: super().keyPressEvent(event)


class ModernComboBox(QComboBox):
    def __init__(self, *args):
        super().__init__(*args)
        self.setProperty('modern', True)
        self.setMaxVisibleItems(9)
        self._popup = QFrame(self, Qt.Popup | Qt.FramelessWindowHint)
        self._popup.setObjectName('ComboPopupFrame')
        layout = QVBoxLayout(self._popup)
        layout.setContentsMargins(4,4,4,4)
        view = self._popup_view = PopupList(self, self._popup)
        view.setObjectName('ComboPopup')
        view.setUniformItemSizes(True)
        view.setItemDelegate(PopupDelegate(view))
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(view)
        view.clicked.connect(self.choose_popup)

    def view(self): return self._popup_view

    def choose_popup(self, index):
        if index.isValid():
            self.setCurrentIndex(index.row())
            self.activated[int].emit(index.row())
            self.activated[str].emit(self.currentText())
        self.hidePopup()

    def showPopup(self):
        if not self.isEnabled() or not self.count(): return
        view = self._popup_view
        view.setModel(self.model())
        view.setModelColumn(self.modelColumn())
        view.setFont(self.font())
        view.setCurrentIndex(self.model().index(self.currentIndex(),self.modelColumn()))
        row_height = max(compact_px(32),view.sizeHintForRow(0))
        height = min(self.count(),self.maxVisibleItems())*row_height+compact_px(20)
        width = max(self.width(),min(compact_px(520),view.sizeHintForColumn(0)+compact_px(32)))
        point = self.mapToGlobal(QPoint(0,self.height()+3))
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        height = min(height,bounds.height()-8)
        width = min(width,bounds.width()-8)
        if point.y()+height>bounds.bottom(): point.setY(self.mapToGlobal(QPoint(0,0)).y()-height-3)
        point.setX(max(bounds.left()+4,min(point.x(),bounds.right()-width-3)))
        point.setY(max(bounds.top()+4,min(point.y(),bounds.bottom()-height-3)))
        self._popup.setGeometry(point.x(),point.y(),width,height)
        self._popup.show()
        self._popup.raise_()
        view.scrollTo(view.currentIndex(),QAbstractItemView.PositionAtCenter)
        view.setFocus(Qt.PopupFocusReason)

    def hidePopup(self):
        if hasattr(self,'_popup'): self._popup.hide()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.Text if self.isEnabled() else QPalette.Mid), 1.5))
        cx, cy = self.width()-widget_px(self,18), self.height()/2
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
        step=widget_px(self,26)
        y = (self.height()-step)//2
        self.minus.setGeometry(self.width()-widget_px(self,62), y, step, step)
        self.plus.setGeometry(self.width()-widget_px(self,32), y, step, step)


class ModernCheckBox(QCheckBox):
    """A wrapping native checkbox, retaining keyboard and accessibility behavior."""
    def __init__(self, *args):
        super().__init__(*args)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def heightForWidth(self, width):
        return max(widget_px(self,30), self.fontMetrics().boundingRect(QRect(0,0,max(widget_px(self,50),width-widget_px(self,30)),1000),
                    Qt.TextWordWrap, self.text()).height()+widget_px(self,10))

    def sizeHint(self):
        width = min(widget_px(self,340), self.fontMetrics().horizontalAdvance(self.text())+widget_px(self,32))
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self): return QSize(widget_px(self,110), widget_px(self,30))

    def hitButton(self, point): return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''
        self.style().drawControl(QStyle.CE_CheckBox, option, painter, self)
        painter.setPen(self.palette().color(QPalette.Text if self.isEnabled() else QPalette.Mid))
        painter.drawText(self.rect().adjusted(widget_px(self,30),widget_px(self,4),0,-widget_px(self,4)), Qt.TextWordWrap | Qt.AlignVCenter, self.text())


class ReadableChecks(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_ComboBox_Popup: return 0
        return super().styleHint(hint, option, widget, returnData)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            # Mouse focus must not leave an inner rounded frame after activation.
            if not option.state & QStyle.State_KeyboardFocusChange: return
            if widget is not None and widget.property('keyboardFocus') is False: return
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
        if isinstance(widget, (QPushButton, QToolButton, QCheckBox)):
            keyboard = None
            if event.type() == QEvent.FocusIn:
                keyboard = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
            elif event.type() in (QEvent.MouseButtonPress, QEvent.FocusOut): keyboard = False
            elif event.type() == QEvent.KeyPress: keyboard = True
            if keyboard is not None and widget.property('keyboardFocus') != keyboard:
                widget.setProperty('keyboardFocus', keyboard)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
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
    stylesheet = '''
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
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {border:1px solid %(text)s;}
        QPushButton:pressed {background:%(selection)s;}
        QPushButton[role="primary"] {background:%(primary)s; color:%(on)s; border-color:%(primary)s;}
        QPushButton[role="primary"]:hover {border:1px solid %(muted)s;}
        QPushButton[role="danger"] {color:%(danger)s;}
        QPushButton[keyboardFocus="true"] {border:1px solid %(text)s;}
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
        QComboBox QAbstractItemView::item {min-height:28px; padding:4px 8px; border:0;}
        QFrame#ComboPopupFrame {background:%(surface)s; border:1px solid %(line)s; border-radius:6px;}
        QListView#ComboPopup {background:%(surface)s; color:%(text)s; border:0; padding:4px; outline:0;}
        QListView#ComboPopup::item:selected {background:%(selection)s; color:%(text)s;}
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
    ''' % colors
    app._base_stylesheet=stylesheet
    app.setStyleSheet(stylesheet + density_stylesheet(stylesheet))
    for window in app.topLevelWidgets():
        if window.isVisible() and hasattr(window,'refresh_interface_style'):window.refresh_interface_style()
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
    widget.setAutoDefault(False)
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
