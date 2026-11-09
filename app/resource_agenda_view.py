"""Date selection and local agenda in the capsule's card layout."""
from PyQt5.QtCore import QDate, QDateTime, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPalette, QPen
from PyQt5.QtWidgets import (QAbstractItemView, QBoxLayout, QCalendarWidget, QDateTimeEdit, QDialog, QFormLayout,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QSizePolicy, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget)
from card_design import paint_capsule_card
from resource_agenda import SOURCES
from resource_charts import DashboardCard, sync_card_controls
from resource_compact import text
from flash_view import icon


SOURCE_TONES = {
    'local': ('lavender', '#edf0f5', '#343b46', '#56677a', '#b4c1d2'),
    'dingtalk': ('ice', '#d9eaff', '#273e5b', '#1763ba', '#85baff'),
    'feishu': ('mint', '#d0efe4', '#234a41', '#12745d', '#67dcb3'),
    'tencent': ('peach', '#f8e7cd', '#523c2a', '#a6570c', '#ffc17a'),
}
WEEKDAYS = '一二三四五六日'
ROW_HEIGHT = 44


def local_time(epoch):
    return QDateTime.fromSecsSinceEpoch(epoch)


def source_color(source, colors):
    return SOURCE_TONES[source][3 if colors['light'] else 4]


def dot(painter, x, y, color, diameter=4):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(x, y, diameter, diameter))


class AgendaCalendar(QCalendarWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.events = None
        self.markers = {}
        self.setNavigationBarVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.NoHorizontalHeader)
        self.setFirstDayOfWeek(Qt.Monday)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setFixedHeight(128)
        self.setAccessibleName('日程月历')
        self.setStyleSheet('QCalendarWidget QAbstractItemView {background: transparent; border: 0; padding: 0;'
                           'selection-background-color: transparent; outline: 0;}')
        palette = self.palette()
        palette.setColor(QPalette.Highlight, Qt.transparent)
        self.setPalette(palette)
        self.currentPageChanged.connect(self.index_month)

    def set_events(self, events):
        if events is not self.events:
            self.events = events
            self.index_month()

    def index_month(self, *_):
        first = QDate(self.yearShown(), self.monthShown(), 1)
        # Include the leading and trailing dates shown from adjacent months.
        first = first.addDays(-first.dayOfWeek()).toJulianDay()
        markers = {}
        for event in self.events or ():
            start = max(first, local_time(event['start']).date().toJulianDay())
            end = min(first + 42, local_time(event['end'] - 1).date().toJulianDay())
            for day in range(start, end + 1):
                markers.setdefault(day, set()).add(event['source'])
        self.markers = markers
        self.updateCells()

    def paintCell(self, painter, rect, day):
        colors = self.owner.colors
        if not colors:
            return super().paintCell(painter, rect, day)
        selected = day == self.selectedDate()
        today = day == QDate.currentDate()
        cell = QRectF(rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if selected or today:
            tint = QColor(colors['ink'])
            tint.setAlpha(32 if selected else 12)
            painter.setBrush(tint)
            painter.setPen(Qt.NoPen if selected else QPen(QColor(colors['muted']), .75))
            highlight = QRectF(cell.center().x() - 12, cell.top() + 1, 24, cell.height() - 2)
            painter.drawRoundedRect(highlight, 6, 6)
        ink = colors['ink'] if selected or day.month() == self.monthShown() else colors['muted']
        digits = cell.adjusted(0, 1, 0, -5)
        text(painter, digits, str(day.day()), ink, 12, selected or today, Qt.AlignHCenter)
        sources = self.markers.get(day.toJulianDay())
        if sources:
            x = cell.center().x() - (6 * len(sources) - 2) / 2
            for source in SOURCES:
                if source in sources:
                    dot(painter, x, cell.bottom() - 6, source_color(source, colors))
                    x += 6
        painter.restore()


class AgendaRows(QStyledItemDelegate):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner

    def sizeHint(self,option,index):
        return QSize(0,ROW_HEIGHT)

    def paint(self,p,option,index):
        title,start,end,source,notice=index.data(Qt.UserRole+1)
        c=self.owner.colors
        tone,light,dark,*_=SOURCE_TONES[source]
        rect=QRectF(option.rect).adjusted(.5,1,-1,-2)
        selected=bool(option.state&QStyle.State_Selected)
        p.save()
        try:
            p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
            paint_capsule_card(p,rect,c,tone,self.owner.background,radius=7,
                               base=light if c['light'] else dark,active=selected)
            top = rect.top() + 3
            left = rect.left() + 8
            content = left + 47
            width = rect.right() - content - 8
            text(p, QRectF(left, top, 37, 18), start, c['ink'], 13, True, Qt.AlignRight)
            text(p, QRectF(left, top+18, 37, 16), end, c['muted'], 11, False, Qt.AlignRight)
            text(p, QRectF(content, top, width, 18), title, c['ink'], 13, True)
            color = source_color(source, c)
            dot(p, content+1, top+24, color)
            text(p, QRectF(content+9, top+18, width-9, 16), SOURCES[source]+notice, color, 11)
        finally:p.restore()


class AgendaView(QWidget):
    def __init__(self,window):
        super().__init__()
        self.owner=window;self.model=window.service.get_agenda();self.signature=None;self.calendar_style=None
        self.layout_=QBoxLayout(QBoxLayout.LeftToRight,self)
        self.layout_.setContentsMargins(0,0,0,0);self.layout_.setSpacing(7)
        month=DashboardCard(window,'mint')
        month.setMinimumWidth(174)
        month_body=QVBoxLayout(month);month_body.setContentsMargins(8,6,8,7);month_body.setSpacing(3)
        self.calendar=AgendaCalendar(window)
        navigation = QHBoxLayout()
        navigation.setSpacing(3)
        self.month = QLabel()
        self.month.setObjectName('RankTitle')
        navigation.addWidget(self.month, 1)
        self.today = QToolButton()
        self.today.setText('今天')
        self.today.clicked.connect(self.select_today)
        navigation.addWidget(self.today)
        self.previous_month = QToolButton()
        self.next_month = QToolButton()
        for control, label, slot in ((self.previous_month, '上个月', self.calendar.showPreviousMonth),
                                     (self.next_month, '下个月', self.calendar.showNextMonth)):
            control.setAccessibleName(label)
            control.setToolTip(label)
            control.setFixedSize(23, 24)
            control.clicked.connect(slot)
            navigation.addWidget(control)
        month_body.addLayout(navigation)
        weekdays = QHBoxLayout()
        weekdays.setSpacing(0)
        for character in WEEKDAYS:
            label = QLabel(character)
            label.setAlignment(Qt.AlignCenter)
            label.setObjectName('Subtle')
            weekdays.addWidget(label, 1)
        month_body.addLayout(weekdays)
        month_body.addWidget(self.calendar)
        legend = QGridLayout()
        legend.setHorizontalSpacing(5)
        legend.setVerticalSpacing(1)
        self.legend = {}
        for index, source in enumerate(SOURCES):
            label = QLabel()
            label.setTextFormat(Qt.RichText)
            self.legend[source] = label
            legend.addWidget(label, index // 2, index % 2)
        month_body.addLayout(legend)
        month_body.addStretch(1)
        self.calendar.currentPageChanged.connect(self.update_month)
        self.update_month(self.calendar.yearShown(), self.calendar.monthShown())
        self.layout_.addWidget(month,2)

        listing=DashboardCard(window,'ice')
        body=QVBoxLayout(listing);body.setContentsMargins(10,6,10,7);body.setSpacing(4)
        header=QHBoxLayout();header.setSpacing(4)
        self.day=QLabel();self.day.setObjectName('AgendaDay');header.addWidget(self.day,1)
        self.add_button=QToolButton();self.add_button.setText('+ 新增');self.add_button.clicked.connect(lambda:self.edit())
        header.addWidget(self.add_button);body.addLayout(header)
        self.count=QLabel();self.count.setObjectName('Subtle');body.addWidget(self.count)
        self.rows=QListWidget();self.rows.setAccessibleName('所选日期的日程')
        self.rows.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rows.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.rows.setUniformItemSizes(True)
        self.rows.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        self.rows.setStyleSheet('QListWidget{border:0;padding:0;margin:0;background:transparent;}'
                                'QListWidget::item{min-height:0;padding:0;margin:0;}')
        self.rows.setItemDelegate(AgendaRows(window,self.rows))
        self.rows.itemDoubleClicked.connect(lambda item:self.edit(item.data(Qt.UserRole)))
        self.rows.currentItemChanged.connect(self.refresh_actions);body.addWidget(self.rows)
        self.empty=QLabel('当天没有安排');self.empty.setObjectName('Subtle');body.addWidget(self.empty)
        body.addStretch(1)
        actions=QHBoxLayout();actions.setSpacing(4)
        self.modify=QToolButton();self.modify.setText('编辑');self.modify.clicked.connect(lambda:self.edit(self.selected()))
        actions.addWidget(self.modify)
        self.dismiss=QToolButton();self.dismiss.setText('结束提醒');self.dismiss.clicked.connect(self.dismiss_current)
        actions.addWidget(self.dismiss);actions.addStretch()
        body.addLayout(actions);self.layout_.addWidget(listing,3)
        self.status=QLabel();self.status.setObjectName('Subtle');self.status.setWordWrap(True);body.addWidget(self.status)
        self.calendar.selectionChanged.connect(self.refresh)
        self.refresh()

    def update_month(self, year, month):
        self.month.setText(f'{year}年{month}月')

    def select_today(self):
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.showSelectedDate()

    def selected(self):
        item=self.rows.currentItem()
        return item.data(Qt.UserRole) if item else None

    def refresh_actions(self,*args):
        current=self.selected()
        synced=any(row['id']==current and row.get('synced') for row in self.model.events)
        self.modify.setText('提醒设置' if synced else '编辑')
        self.modify.setVisible(bool(current))
        self.dismiss.setVisible(bool(current and any(event['id']==current for event in self.model.due())))

    def refresh(self):
        if not self.owner.colors:return
        colors=self.owner.colors
        sync_card_controls(self,colors)
        self.sync_calendar(colors)
        day=self.calendar.selectedDate();due={event['id'] for event in self.model.due()}
        today=QDate.currentDate()
        events=self.model.events
        self.calendar.set_events(events)
        signature=(day.toJulianDay(),today.toJulianDay(),events,due,self.model.error)
        if signature==self.signature:return
        self.signature=signature
        self.day.setText(day.toString('M月d日')+'  周'+WEEKDAYS[day.dayOfWeek()-1])
        selected=self.selected()
        self.rows.clear()
        for event in events:
            start,end=local_time(event['start']),local_time(event['end'])
            if not start.date()<=day<=end.addSecs(-1).date():continue
            flag=' · 提醒中' if event['id'] in due else ''
            source=event['source']
            start_text=start.toString('HH:mm' if start.date()==day else 'M/d')
            end_text=end.toString('HH:mm' if end.date()==day else 'M/d')
            item=QListWidgetItem(f"{start_text} {event['title']}，{SOURCES[source]}，{end_text} 结束{flag}")
            item.setToolTip(event['title']+'\n'+start.toString('M/d HH:mm')+' – '+end.toString('M/d HH:mm'))
            item.setData(Qt.UserRole,event['id'])
            item.setData(Qt.UserRole+1,(event['title'],start_text,end_text,source,flag))
            self.rows.addItem(item)
            if event['id']==selected:self.rows.setCurrentItem(item)
        if self.rows.count() and not self.rows.currentItem():self.rows.setCurrentRow(0)
        count = self.rows.count()
        self.count.setText(('今天 · ' if day==today else '')+f'{count} 项日程')
        self.rows.setMinimumHeight(ROW_HEIGHT+3 if count else 0)
        self.rows.setMaximumHeight(ROW_HEIGHT*min(4,count)+3)
        self.rows.setToolTip('滚动查看全部日程' if count > 3 else '')
        self.rows.setVisible(bool(self.rows.count()));self.empty.setVisible(not self.rows.count())
        self.status.setText(self.model.error);self.status.setVisible(bool(self.model.error))
        self.refresh_actions()

    def sync_calendar(self,colors):
        style=tuple(colors[key] for key in ('ink','muted','light'))
        if style==self.calendar_style:return
        self.calendar_style=style
        self.rows.viewport().update()
        self.calendar.updateCells()
        self.day.setStyleSheet('font-size: 14px; font-weight: 600;')
        for control, symbol in ((self.previous_month, 'back'), (self.next_month, 'fold')):
            control.setIcon(icon(symbol, colors['ink'], 13))
            control.setIconSize(QSize(13, 13))
        for source, label in self.legend.items():
            label.setText(f'<span style="color:{source_color(source, colors)}">●</span> {SOURCES[source]}')

    def dismiss_current(self):
        if self.selected():
            self.model.dismiss(self.selected());self.refresh()

    def resizeEvent(self,event):
        self.layout_.setDirection(QBoxLayout.LeftToRight if event.size().width()>=425 else QBoxLayout.TopToBottom)
        super().resizeEvent(event)

    def edit(self,key=None):
        from ui_style import ModernSpinBox, SettingsHeader, button, compact_dialog, exec_dialog
        event=next((row for row in self.model.events if row['id']==key),None)
        if key and event is None:return
        synced=bool(event and event.get('synced'))
        initial=local_time(event['start']) if event else QDateTime(self.calendar.selectedDate(),QDateTime.currentDateTime().time())
        dialog=QDialog(self.owner)
        dialog.setWindowTitle('日程提醒设置' if synced else '编辑日程' if event else '新增日程')
        dialog.resize(420,246)
        dialog.setProperty('simpleForms',True)
        layout=QVBoxLayout(dialog);layout.addWidget(SettingsHeader(dialog,dialog.windowTitle()))
        form=QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        layout.addLayout(form)
        title=QLineEdit(event['title'] if event else '');title.setMaxLength(120)
        title.setAccessibleName('标题');form.addRow('标题',title)
        start=QDateTimeEdit(initial)
        end=QDateTimeEdit(local_time(event['end']) if event else initial.addSecs(1800))
        for label,field in (('开始',start),('结束',end)):
            field.setCalendarPopup(True);field.setDisplayFormat('yyyy-MM-dd HH:mm')
            field.setAccessibleName(label);form.addRow(label,field)
        if synced:
            for field in (title,start,end):field.setReadOnly(True)
            hint=QLabel(f"标题和时间随{SOURCES[event['source']]}同步。")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        lead=ModernSpinBox();lead.setRange(0,180);lead.setValue(event['lead'] if event else 5)
        lead.setSpecialValueText('开始时');form.addRow('提前提醒（分钟）',lead)
        status=QLabel();status.setWordWrap(True);status.hide();layout.addWidget(status)
        actions=QHBoxLayout()
        def show_error():
            status.setText(self.model.error)
            status.show()
        def save():
            if synced:
                saved=self.model.synced_reminder(key,lead=lead.value())
            else:
                saved=self.model.update_event(key,title=title.text().strip(),start=start.dateTime().toSecsSinceEpoch(),
                                              end=end.dateTime().toSecsSinceEpoch(),lead=lead.value())
            if saved:
                if not synced:self.calendar.setSelectedDate(start.date())
                dialog.accept()
            else:show_error()
        def remove():
            if self.model.remove(key):dialog.accept()
            else:show_error()
        if event and not synced:actions.addWidget(button('删除',remove))
        actions.addStretch();actions.addWidget(button('取消',dialog.reject))
        actions.addWidget(button('保存',save,'primary'));layout.addLayout(actions)
        compact_dialog(dialog);(lead if synced else title).setFocus()
        try:exec_dialog(dialog)
        finally:self.refresh()
