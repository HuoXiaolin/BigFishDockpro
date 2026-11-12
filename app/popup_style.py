"""Readable native popup surfaces, independent of desktop-card materials."""
from PyQt5.QtCore import Qt, QSize, QObject, QEvent, QPointF
from PyQt5.QtGui import QPalette, QTextCharFormat, QPainter, QPen, QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QCalendarWidget, QDateTimeEdit, QWidget, QToolButton, QTableView


CALENDAR_STYLE = '''
QCalendarWidget {background:palette(base);color:palette(text);border:0;}
QCalendarWidget QWidget {background:palette(base);color:palette(text);font-size:12px;}
QCalendarWidget QWidget#qt_calendar_navigationbar {background:palette(window);border:0;}
QCalendarWidget QToolButton {background:transparent;color:palette(window-text);border:0;
    border-radius:5px;padding:5px;min-height:24px;font-size:12px;}
QCalendarWidget QToolButton:hover {background:palette(button);}
QCalendarWidget QToolButton::menu-indicator {width:0;}
QCalendarWidget QSpinBox {background:palette(base);color:palette(text);border:1px solid palette(mid);padding:3px;}
QCalendarWidget QAbstractItemView {background:palette(base);color:palette(text);
    alternate-background-color:palette(window);selection-background-color:palette(highlight);
    selection-color:palette(highlighted-text);border:0;outline:0;font-size:12px;}
QCalendarWidget QAbstractItemView:disabled {color:palette(mid);}
QCalendarWidget QMenu {background:palette(base);color:palette(text);border:1px solid palette(mid);padding:4px;}
QCalendarWidget QMenu::item {padding:6px 16px;}
QCalendarWidget QMenu::item:selected {background:palette(highlight);color:palette(highlighted-text);}
'''

POPUP_STYLE = '''
QDialog[themedPopup="true"] {background:palette(window);color:palette(window-text);}
QDialog[themedPopup="true"] QWidget {color:palette(window-text);font-size:12px;}
QDialog[themedPopup="true"] QLabel {background:transparent;color:palette(window-text);font-size:12px;}
QDialog[themedPopup="true"] QLabel[role="title"] {font-size:16px;font-weight:600;}
QDialog[themedPopup="true"] QLabel[role="muted"] {color:palette(mid);font-size:11px;}
QDialog[themedPopup="true"] QPushButton {background:palette(base);color:palette(text);border:1px solid palette(midlight);
    border-radius:6px;padding:6px 12px;min-height:20px;}
QDialog[themedPopup="true"] QPushButton:hover {background:palette(highlight);}
QDialog[themedPopup="true"] QToolButton {background:transparent;color:palette(text);border:0;border-radius:5px;padding:5px 8px;}
QDialog[themedPopup="true"] QToolButton:hover,QDialog[themedPopup="true"] QToolButton:checked {background:palette(highlight);}
QDialog[themedPopup="true"] QLineEdit,QDialog[themedPopup="true"] QPlainTextEdit,
QDialog[themedPopup="true"] QSpinBox {background:palette(base);color:palette(text);border:1px solid palette(midlight);border-radius:6px;padding:5px 7px;}
QDialog[themedPopup="true"] QDateTimeEdit QLineEdit {background:transparent;border:0;padding:0;}
QDialog[themedPopup="true"] QTableView {background:palette(base);color:palette(text);border:0;
    alternate-background-color:palette(window);selection-background-color:palette(highlight);
    selection-color:palette(highlighted-text);gridline-color:palette(midlight);font-size:12px;}
QDialog[themedPopup="true"] QTableView::item {padding:4px 8px;border:0;}
QDialog[themedPopup="true"] QHeaderView {background:palette(window);}
QDialog[themedPopup="true"] QHeaderView::section {background:palette(window);color:palette(mid);
    border:0;border-bottom:1px solid palette(midlight);padding:8px;font-size:11px;font-weight:400;}
QDialog[themedPopup="true"] QTableCornerButton::section {background:palette(window);border:0;}
QDialog[themedPopup="true"] QDateTimeEdit {background:palette(base);color:palette(text);
    border:1px solid palette(midlight);border-radius:6px;padding:5px 7px;min-height:20px;font-size:12px;}
QDialog[themedPopup="true"] QDateTimeEdit:focus {border-color:palette(highlight);}
QDialog[themedPopup="true"] QDateTimeEdit::drop-down {width:25px;border:0;border-left:1px solid palette(midlight);}
'''

DATE_STYLE = '''
QDateTimeEdit {background:palette(base);color:palette(text);border:1px solid palette(midlight);
    border-radius:6px;padding:5px 7px;min-height:20px;font-size:12px;}
QDateTimeEdit:focus {border-color:palette(highlight);}
QDateTimeEdit::drop-down {width:25px;border:0;border-left:1px solid palette(midlight);}
QDateTimeEdit QLineEdit {background:transparent;border:0;padding:0;}
'''

TABLE_STYLE = '''
QTableView {background:palette(base);color:palette(text);border:0;font-size:12px;
    alternate-background-color:palette(window);selection-background-color:palette(highlight);
    selection-color:palette(highlighted-text);gridline-color:palette(midlight);}
QTableView::item {padding:4px 8px;border:0;}
QHeaderView {background:palette(window);}
QHeaderView::section {background:palette(window);color:palette(mid);border:0;
    border-bottom:1px solid palette(midlight);padding:8px;font-size:11px;font-weight:400;}
QTableCornerButton::section {background:palette(window);border:0;}
'''

HEADER_STYLE = '''
QHeaderView {background:palette(window);color:palette(mid);}
QHeaderView::section {background:palette(window);color:palette(mid);border:0;
    border-bottom:1px solid palette(midlight);padding:6px 8px;font-size:11px;font-weight:400;}
'''


def resolved_style(style):
    palette=QApplication.palette()
    roles={'base':QPalette.Base,'text':QPalette.Text,'window':QPalette.Window,'window-text':QPalette.WindowText,
           'button':QPalette.Button,'mid':QPalette.Mid,'midlight':QPalette.Midlight,'highlight':QPalette.Highlight,
           'highlighted-text':QPalette.HighlightedText}
    for name,role in roles.items():style=style.replace('palette('+name+')',palette.color(role).name())
    return style


def arrow_icon(right=False):
    pix=QPixmap(32,32);pix.setDevicePixelRatio(2);pix.fill(Qt.transparent)
    painter=QPainter(pix);painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QApplication.palette().color(QPalette.Text),1.6,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    direction=-1 if right else 1
    painter.drawLine(QPointF(8+direction*2,4),QPointF(8-direction*2,8));painter.drawLine(QPointF(8-direction*2,8),QPointF(8+direction*2,12));painter.end()
    return QIcon(pix)


class ThemedCalendar(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalHeaderFormat(self.NoVerticalHeader)
        self.setHorizontalHeaderFormat(self.ShortDayNames)
        self.setFirstDayOfWeek(Qt.Monday)
        self.setGridVisible(False)
        self.setMinimumSize(280, 240)
        self.refresh_palette()

    def sizeHint(self):
        return super().sizeHint().expandedTo(QSize(280, 240))

    def refresh_palette(self):
        palette = QApplication.palette()
        self.setPalette(palette)
        self.setStyleSheet(resolved_style(CALENDAR_STYLE))
        for name,right in (('qt_calendar_prevmonth',False),('qt_calendar_nextmonth',True)):
            button=self.findChild(QToolButton,name)
            if button:button.setIcon(arrow_icon(right))
        # Qt defaults to bright red weekends, including in dark mode. Use the
        # app's foreground; selection and disabled dates still use native roles.
        fmt = QTextCharFormat();fmt.setForeground(palette.brush(QPalette.Text))
        for day in (Qt.Saturday, Qt.Sunday):self.setWeekdayTextFormat(day, fmt)
        self.update()


class DateArrow(QWidget):
    def __init__(self,field):
        super().__init__(field);self.field=field
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet('background:transparent;border:0;')
        self.watcher=DateArrowLayout(self);field.installEventFilter(self.watcher)
        self.reposition();self.show()
    def reposition(self):self.setGeometry(self.field.width()-26,1,24,max(1,self.field.height()-2));self.raise_()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QApplication.palette().color(QPalette.Text),1.4,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        cx,cy=self.width()/2,self.height()/2
        p.drawLine(QPointF(cx-3,cy-1),QPointF(cx,cy+2));p.drawLine(QPointF(cx,cy+2),QPointF(cx+3,cy-1))


class DateArrowLayout(QObject):
    def eventFilter(self,field,event):
        if event.type() in (QEvent.Resize,QEvent.Show):self.parent().reposition()
        return False


def prepare_date(field):
    style=resolved_style(DATE_STYLE)
    if field.styleSheet()!=style:field.setStyleSheet(style)
    if not field.calendarPopup() or isinstance(field.calendarWidget(), ThemedCalendar):return
    calendar = ThemedCalendar(field)
    calendar.setLocale(field.locale())
    field.setCalendarWidget(calendar)
    # QDateTimeEdit owns the replacement and releases its original calendar.
    field._date_arrow=DateArrow(field)
    field.setMinimumWidth(max(field.minimumWidth(),field.fontMetrics().horizontalAdvance(field.displayFormat())+46))


def prepare_popup(dialog):
    """An opaque dialog gets its own palette; glass parents must not leak in."""
    if not dialog.property('compactDialog'):
        if not dialog.property('themedPopup'):
            dialog.setProperty('popupOriginalStyle',dialog.styleSheet())
            dialog.setProperty('themedPopup',True)
        style=(dialog.property('popupOriginalStyle') or '')+'\n'+resolved_style(POPUP_STYLE)
        if dialog.styleSheet()!=style:dialog.setStyleSheet(style)
        dialog.setPalette(QApplication.palette())
    for field in dialog.findChildren(QDateTimeEdit):prepare_date(field)
    for calendar in dialog.findChildren(ThemedCalendar):calendar.refresh_palette()
    for table in dialog.findChildren(QTableView):
        parent=table.parentWidget()
        while parent is not None and not isinstance(parent,QCalendarWidget):parent=parent.parentWidget()
        if parent is not None:continue
        if table.property('popupTableStyle') is None:table.setProperty('popupTableStyle',table.styleSheet())
        style=(table.property('popupTableStyle') or '')+'\n'+resolved_style(TABLE_STYLE)
        if table.styleSheet()!=style:table.setStyleSheet(style)
        table.setPalette(QApplication.palette())
        header=table.horizontalHeader();header_style=resolved_style(HEADER_STYLE)
        if header.styleSheet()!=header_style:header.setStyleSheet(header_style)
        header.setMinimumHeight(30)
