"""White, multiline readouts for the data icons in the Windows notification area."""
import ctypes
from ctypes import wintypes as wt
from math import ceil
from weakref import WeakValueDictionary

from PyQt5.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QAbstractTextDocumentLayout, QCursor, QPainter, QPalette, QTextDocument, QTextOption
from PyQt5.QtWidgets import QApplication, QStyle, QSystemTrayIcon, QToolTip, QWidget


# The bundled Qt Windows plugin registers a hidden window for each tray icon.
# Listen only on our data icons. Qt continues to handle their clicks and menus.
TRAY_MESSAGE = 0x8000 + 101
WM_MOUSEMOVE = 0x0200
NIN_POPUPOPEN, NIN_POPUPCLOSE = 0x0406, 0x0407
_owners = WeakValueDictionary()
_enumerate = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_subclass = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                               ctypes.c_size_t, ctypes.c_size_t)
user = ctypes.WinDLL('user32')
controls = ctypes.WinDLL('comctl32')
kernel = ctypes.WinDLL('kernel32')
user.EnumThreadWindows.argtypes = (wt.DWORD, _enumerate, wt.LPARAM)
user.GetWindowTextW.argtypes = (wt.HWND, wt.LPWSTR, ctypes.c_int)
user.GetCursorPos.argtypes = (ctypes.POINTER(wt.POINT),)
controls.SetWindowSubclass.argtypes = (wt.HWND, _subclass, ctypes.c_size_t, ctypes.c_size_t)
controls.DefSubclassProc.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
controls.DefSubclassProc.restype = wt.LPARAM
_set_dwm_attribute = ctypes.WinDLL('dwmapi').DwmSetWindowAttribute
_set_dwm_attribute.argtypes = (wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD)


class IconId(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('hwnd', wt.HWND), ('id', wt.UINT), ('guid', ctypes.c_ubyte * 16)]


_get_rect = ctypes.WinDLL('shell32').Shell_NotifyIconGetRect
_get_rect.argtypes = (ctypes.POINTER(IconId), ctypes.POINTER(wt.RECT))
_get_rect.restype = ctypes.c_long


def _pointer():
    point = wt.POINT()
    return QPoint(point.x, point.y) if user.GetCursorPos(ctypes.byref(point)) else None


def _icon_rect(hwnd):
    icon, rect = IconId(ctypes.sizeof(IconId), hwnd), wt.RECT()
    if _get_rect(ctypes.byref(icon), ctypes.byref(rect)) == 0:
        return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    return QRect()


def _tray_windows():
    handles = set()
    title = ctypes.create_unicode_buffer(64)

    @_enumerate
    def visit(hwnd, unused):
        if user.GetWindowTextW(hwnd, title, len(title)) and title.value == 'QTrayIconMessageWindow':
            handles.add(hwnd)
        return True

    user.EnumThreadWindows(kernel.GetCurrentThreadId(), visit, 0)
    return handles


@_subclass
def _tray_event(hwnd, message, wparam, lparam, subclass_id, data):
    tray = _owners.get(hwnd)
    if tray is not None:
        if message == TRAY_MESSAGE:
            kind = lparam & 0xffff
            if kind in (WM_MOUSEMOVE, NIN_POPUPOPEN):
                tray.hover(kind == NIN_POPUPOPEN)
            elif 0x0201 <= kind <= 0x0209 or kind in (0x007b, 0x02a3, 0x0400, 0x0401):  # buttons, menu, leave, select
                tray.dismiss()
            elif kind == NIN_POPUPCLOSE and tray.leave.isActive():
                tray.check_pointer()
        elif message == 0x0082:  # WM_NCDESTROY, including QSystemTrayIcon.hide()
            _owners.pop(hwnd, None)
            tray.hwnd = None
            tray.dismiss()
            if tray.popup is not None:
                tray.popup.deleteLater()
                tray.popup = None
    return controls.DefSubclassProc(hwnd, message, wparam, lparam)


class ReadoutPopup(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        # Windows 11 can also paint a compositor border outside the Qt client.
        no_border = wt.DWORD(0xfffffffe)  # DWMWA_COLOR_NONE
        _set_dwm_attribute(int(self.winId()), 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
        self.document = QTextDocument(self)
        self.document.setDefaultFont(QToolTip.font())
        self.document.setDocumentMargin(0)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.document.setDefaultTextOption(option)
        self.paint_context = QAbstractTextDocumentLayout.PaintContext()
        palette = self.paint_context.palette
        palette.setColor(QPalette.Text, Qt.black)
        self.paint_context.palette = palette
        self.anchor = QPoint()

    def present(self, text, point):
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is None:
            return
        self.anchor = QPoint(point)
        area = screen.availableGeometry()
        self.setAccessibleName(text)
        self.document.setPlainText(text)
        self.document.setTextWidth(-1)
        width = min(350, max(1, area.width() - 24), ceil(self.document.idealWidth()))
        self.document.setTextWidth(width)
        width += 18
        height = ceil(self.document.size().height()) + 10
        x = max(area.left(), min(point.x() - width // 2, area.right() + 1 - width))
        y = point.y() - height - 12
        if y < area.top():
            y = point.y() + 16
        y = max(area.top(), min(y, area.bottom() + 1 - height))
        self.setGeometry(x, y, width, height)
        self.update()
        if not self.isVisible():
            self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        painter.translate(9, 5)
        self.document.documentLayout().draw(painter, self.paint_context)


class ReadoutTrayIcon(QSystemTrayIcon):
    readoutRequested = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.readout = ''
        self.hwnd = self.popup = self.anchor = None
        self.tried_icon = False
        self.delay = QTimer(self, singleShot=True)
        self.delay.timeout.connect(self.show_readout)
        self.leave = QTimer(self, interval=120)
        self.leave.timeout.connect(self.check_pointer)

    def attach(self, previous):
        new = _tray_windows() - previous
        if len(new) == 1:
            hwnd = new.pop()
            if controls.SetWindowSubclass(hwnd, _tray_event, 1, 0):
                self.hwnd = hwnd
                _owners[hwnd] = self

    def setIcon(self, icon):
        if self.tried_icon:
            return super().setIcon(icon)
        previous = _tray_windows()
        super().setIcon(icon)
        self.tried_icon = True
        self.attach(previous)

    def show(self):
        previous = _tray_windows() if self.hwnd is None else None
        super().show()
        if previous is not None:
            self.attach(previous)
        if self.anchor is None:
            super().setToolTip(self.readout)

    def hide(self):
        self.dismiss()
        super().hide()

    def set_readout(self, text):
        if text == self.readout:
            return
        self.readout = text
        if self.anchor is None:
            super().setToolTip(text)
        if self.popup is not None and self.popup.isVisible():
            self.popup.present(text, self.popup.anchor)

    def hover(self, ready):
        if not self.isVisible() or not self.readout or QApplication.activePopupWidget():
            return
        point = _pointer()
        if point is None:
            return
        if self.anchor is None:
            if ready and not _icon_rect(self.hwnd).contains(point):
                return  # Keyboard focus uses the usual Shell tooltip.
            for other in list(_owners.values()):
                if other is not self and other.anchor is not None:
                    other.dismiss()
            self.anchor = point
            # Keep the normal Shell label for keyboard access. During actual mouse
            # hover the tracking tooltip owns the display, even as Qt changes frames.
            super().setToolTip('')
        self.anchor = point
        if self.leave.isActive():
            return
        if ready:
            self.delay.start(0)
        elif not self.delay.isActive():
            self.delay.start(max(1, QApplication.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay)))

    def check_pointer(self):
        point = _pointer()
        rect = _icon_rect(self.hwnd)
        # In the overflow flyout some Explorer versions give the chevron's
        # rectangle. The latest move delivered to this icon identifies its slot.
        if self.anchor is not None and not rect.contains(self.anchor):
            rect = QRect(self.anchor.x() - 8, self.anchor.y() - 8, 17, 17)
        if point is None or not rect.contains(point) or QApplication.activePopupWidget():
            self.dismiss()
            return False
        return True

    def show_on_click(self):
        if self.hwnd is None:
            return False
        self.hover(False)
        if self.anchor is None:
            return False
        self.delay.stop()
        self.show_readout()
        return self.leave.isActive()

    def show_readout(self):
        if not self.hwnd or not self.check_pointer():
            return
        self.readoutRequested.emit()
        if self.popup is None:
            self.popup = ReadoutPopup()
        self.popup.present(self.readout, QCursor.pos())
        self.leave.start()

    def dismiss(self):
        self.delay.stop()
        self.leave.stop()
        had_hover = self.anchor is not None
        self.anchor = None
        if self.popup is not None:
            self.popup.hide()
        if had_hover and self.hwnd:
            super().setToolTip(self.readout)
