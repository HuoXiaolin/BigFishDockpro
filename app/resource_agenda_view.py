"""Date selection and local agenda in the capsule's card layout."""
from datetime import date
from math import ceil
from PyQt5.QtCore import QDate, QDateTime, QRectF, QSize, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PyQt5.QtWidgets import (QAbstractItemView, QBoxLayout, QCalendarWidget, QDateTimeEdit, QDialog, QFormLayout,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QSizePolicy, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget)
from card_design import paint_capsule_card
from calendar_markers import MARKER_TONES,countdowns,countdown_on,event_last_second,month_markers,paint_markers
from resource_agenda import SOURCES
from resource_charts import DashboardCard, sync_card_controls
from resource_compact import text
from resource_options import content_columns
from flash_view import icon


SOURCE_TONES = {
    'local': ('lavender', '#edf0f5', '#343b46'),
    'dingtalk': ('ice', '#d9eaff', '#273e5b'),
    'feishu': ('mint', '#d0efe4', '#234a41'),
    'tencent': ('peach', '#f8e7cd', '#523c2a'),
    'dida': ('ice', '#e1e5ff', '#333a65'),
    'nexttodo': ('rose', '#f8deed', '#4b3046'),
    'countdown': ('lavender', '#efe6f7', '#3b2e4b'),
}
DISPLAY_SOURCES={**SOURCES,'countdown':'倒数日'}
WEEKDAYS = '一二三四五六日'
ROW_HEIGHT = 44


def local_time(epoch):
    return QDateTime.fromSecsSinceEpoch(epoch)


def source_color(source, colors):
    return MARKER_TONES[source][0 if colors['light'] else 1]


class AgendaCalendar(QCalendarWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.events = None
        self.countdowns = ()
        self.markers = {}
        self.setNavigationBarVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.NoHorizontalHeader)
        self.setDateRange(QDate(1,1,1),QDate(9999,12,31))
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

    def set_events(self, events, items=()):
        if events is not self.events or items!=self.countdowns:
            self.events = events
            self.countdowns = items
            self.index_month()

    def index_month(self, *_):
        first = QDate(self.yearShown(), self.monthShown(), 1)
        # Include the leading and trailing dates shown from adjacent months.
        first=first.addDays(1-first.dayOfWeek())
        self.markers=month_markers(self.events or (),self.countdowns,date(first.year(),first.month(),first.day()),42)
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
            width = min(24, cell.width() - 2)
            highlight = QRectF(cell.center().x() - width / 2, cell.top() + 1, width, cell.height() - 2)
            painter.drawRoundedRect(highlight, 6, 6)
        ink = colors['ink'] if selected or day.month() == self.monthShown() else colors['muted']
        digits = cell.adjusted(0, 1, 0, -5)
        text(painter, digits, str(day.day()), ink, 12, selected or today, Qt.AlignHCenter)
        sources=self.markers.get(date(day.year(),day.month(),day.day()),()) if 1<=day.year()<=9999 else ()
        paint_markers(painter,cell.adjusted(0,0,0,-1),sources,colors['light'])
        painter.restore()


class AgendaRows(QStyledItemDelegate):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner

    def sizeHint(self,option,index):
        return QSize(0,ROW_HEIGHT)

    def paint(self,p,option,index):
        title,start,end,source,notice=index.data(Qt.UserRole+1)
        c=self.owner.colors
        tone,light,dark=SOURCE_TONES[source]
        rect=QRectF(option.rect).adjusted(.5,1,-1,-2)
        selected=bool(option.state&QStyle.State_Selected)
        p.save()
        try:
            p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
            paint_capsule_card(p,rect,c,tone,self.owner.background,radius=7,
                               base=light if c['light'] else dark,active=selected)
            top=rect.top()+3;left=rect.left()+10;width=rect.width()-20
            color=QColor(source_color(source,c))
            if selected:
                p.setPen(Qt.NoPen);p.setBrush(color)
                p.drawRoundedRect(QRectF(rect.left()+2,top+4,2,25),1,1)
            text(p,QRectF(left,top,width,18),title,c['ink'],13,True)
            source_text=DISPLAY_SOURCES[source]
            font=QFont(p.font());font.setPixelSize(9);font.setWeight(QFont.Bold)
            source_width=10+QFontMetrics(font).horizontalAdvance(source_text)
            tag=QRectF(rect.right()-source_width-8,top+19,source_width,15)
            fill=QColor(color);fill.setAlpha(25 if c['light'] else 47)
            p.setPen(Qt.NoPen);p.setBrush(fill);p.drawRoundedRect(tag,5,5)
            text(p,tag,source_text,color,9,True,Qt.AlignCenter)
            stamp=start+' – '+end if end else start
            text(p,QRectF(left,top+18,tag.left()-left-5,17),stamp+notice,c['muted'],10)
        finally:p.restore()


class AgendaView(QWidget):
    def __init__(self,window):
        super().__init__()
        self.owner=window;self.model=window.service.get_agenda();self.signature=None;self.calendar_style=None
        self.layout_=QBoxLayout(QBoxLayout.LeftToRight,self)
        self.layout_.setContentsMargins(0,0,0,0);self.layout_.setSpacing(7)
        month=DashboardCard(window,'mint')
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
            control.setFixedSize(20, 24)
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
        columns = 3
        for column in range(columns):
            legend.setColumnStretch(column, 1)
        self.legend = {}
        for index, source in enumerate(DISPLAY_SOURCES):
            label = QLabel()
            label.setTextFormat(Qt.RichText)
            label.setStyleSheet('font-size: 9px;')
            self.legend[source] = label
            legend.addWidget(label, index // columns, index % columns)
        month_body.addLayout(legend)
        month_body.addStretch(1)
        self.calendar.currentPageChanged.connect(self.update_month)
        self.update_month(self.calendar.yearShown(), self.calendar.monthShown())
        self.layout_.addWidget(month,2)

        listing=DashboardCard(window,'ice')
        body=QVBoxLayout(listing);body.setContentsMargins(10,6,10,7);body.setSpacing(4)
        header=QHBoxLayout();header.setSpacing(4)
        self.day=QLabel();self.day.setObjectName('AgendaDay');self.day.setWordWrap(True);header.addWidget(self.day,1)
        self.add_button=QToolButton();self.add_button.setText('+ 新增');self.add_button.clicked.connect(lambda:self.edit())
        header.addWidget(self.add_button);body.addLayout(header)
        self.count=QLabel();self.count.setObjectName('Subtle');body.addWidget(self.count)
        self.rows=QListWidget();self.rows.setAccessibleName('所选日期的日程')
        self.rows.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        self.reminder=QToolButton();self.reminder.clicked.connect(self.toggle_reminder)
        actions.addWidget(self.reminder);actions.addStretch()
        body.addLayout(actions);self.layout_.addWidget(listing,3)
        self.status=QLabel();self.status.setObjectName('Subtle');self.status.setWordWrap(True);body.addWidget(self.status)
        self.order_deadline = None
        self.order_timer = QTimer(self)
        self.order_timer.setSingleShot(True)
        self.order_timer.setTimerType(Qt.PreciseTimer)
        self.order_timer.timeout.connect(self.refresh)
        self.calendar.selectionChanged.connect(self.refresh)
        self.refresh()

    def update_month(self, year, month):
        self.month.setText(f'{year}年{month}月')

    def update_day_heading(self):
        day=self.calendar.selectedDate()
        date_text=day.toString('M月d日')
        weekday='周'+WEEKDAYS[day.dayOfWeek()-1]
        today=day==QDate.currentDate()
        compact=self.layout_.direction()==QBoxLayout.LeftToRight and self.width()<400
        if compact:
            title=date_text+'\n'+('今天 · ' if today else '')+weekday
        else:
            title=('今天  ' if today else '')+date_text+'  '+weekday
        self.day.setText(title)
        if self.day.property('compactHeading')!=compact:
            self.day.setProperty('compactHeading',compact)
            self.day.setStyleSheet(f'font-size: {12 if compact else 14}px; font-weight: 600;')

    def select_today(self):
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.showSelectedDate()

    def selected(self):
        item=self.rows.currentItem()
        return item.data(Qt.UserRole) if item else None

    def refresh_actions(self,*args):
        current=self.selected()
        event=next((row for row in self.model.events if row['id']==current),None)
        self.modify.setText('提醒设置' if event and event.get('synced') else '编辑')
        self.modify.setVisible(event is not None)
        self.reminder.setText('恢复提醒' if event and event['ack'] else '取消提醒')
        self.reminder.setVisible(bool(event and event['end']>self.model.clock()))

    def schedule_order_refresh(self, deadline, now):
        if deadline is None or not self.isVisible():
            self.order_timer.stop()
        elif self.order_deadline != deadline or not self.order_timer.isActive():
            delay = min(86400000, max(1, ceil((deadline - now) * 1000)))
            self.order_timer.start(delay)
        self.order_deadline = deadline

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def hideEvent(self, event):
        self.order_timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if not self.owner.colors:return
        colors=self.owner.colors
        sync_card_controls(self,colors)
        self.sync_calendar(colors)
        day = self.calendar.selectedDate()
        now = self.model.clock()
        due = {event['id'] for event in self.model.due(now)}
        today=QDate.currentDate()
        events=self.model.events
        items=countdowns(self.owner.service.cfg)
        self.calendar.set_events(events,items)
        day_start = day.startOfDay().toSecsSinceEpoch()
        day_end = day.endOfDay().toSecsSinceEpoch()
        ranked = []
        deadline = None
        for event in events:
            start = event['start']
            if start > day_end or event_last_second(event) < day_start:
                continue
            end = start if event.get('timing') == 'deadline' else event['end']
            if event['id'] in due:
                priority = 0
            elif now >= end:
                priority = 3
            elif now >= start:
                priority = 1
            else:
                priority = 2
            ranked.append((priority, event))
            for boundary in (start, end):
                if now < boundary and (deadline is None or boundary < deadline):
                    deadline = boundary
        self.schedule_order_refresh(deadline, now)
        signature = (day.toJulianDay(), today.toJulianDay(), events, items,
                     tuple(priority for priority, _ in ranked), self.model.error)
        if signature==self.signature:
            self.refresh_actions();return
        scrollbar = self.rows.verticalScrollBar()
        scroll_position = scrollbar.value() if self.signature and self.signature[0] == signature[0] else 0
        self.signature=signature
        self.update_day_heading()
        selected=self.selected()
        self.rows.clear()
        ranked.sort(key=lambda row: (row[0], row[1]['start'], row[1]['id']))
        for _, event in ranked:
            start=local_time(event['start'])
            last=local_time(event_last_second(event))
            flag=' · 提醒中' if event['id'] in due else ' · 提醒已取消' if event['ack'] else ''
            source=event['source']
            timing=event.get('timing')
            end_text=''
            if timing=='all_day':
                start_text='全天'
                detail=start.toString('M/d')
                if start.date()!=last.date():detail+=' – '+last.toString('M/d')
            elif timing=='deadline':
                start_text=start.toString('HH:mm')+' 截止'
                detail=start.toString('M/d HH:mm')+' 截止'
            else:
                end=local_time(event['end'])
                start_text=start.toString('HH:mm' if start.date()==day else 'M/d')
                end_text=end.toString('HH:mm' if end.date()==day else 'M/d')
                detail=start.toString('M/d HH:mm')+' – '+end.toString('M/d HH:mm')
            item=QListWidgetItem(f"{event['title']}，{SOURCES[source]}，{detail}{flag}")
            item.setToolTip(event['title']+'\n'+detail)
            item.setData(Qt.UserRole,event['id'])
            item.setData(Qt.UserRole+1,(event['title'],start_text,end_text,source,flag))
            self.rows.addItem(item)
            if event['id']==selected:self.rows.setCurrentItem(item)
        event_count=self.rows.count()
        selected_day=date(day.year(),day.month(),day.day())
        for row in items:
            if countdown_on(row,selected_day):
                item=QListWidgetItem(row['title'])
                item.setData(Qt.UserRole+1,(row['title'],row['time'] or '全天','','countdown',''))
                self.rows.addItem(item)
        if self.rows.count() and not self.rows.currentItem():self.rows.setCurrentRow(0)
        count = self.rows.count()
        self.count.setText(f'{event_count} 项日程'+(f'  ·  {count-event_count} 个倒数日' if count>event_count else ''))
        self.rows.setMinimumHeight(ROW_HEIGHT if count else 0)
        self.rows.setMaximumHeight(ROW_HEIGHT*min(4,count))
        self.rows.setToolTip('滚动查看全部日程' if count > 3 else '')
        self.rows.setVisible(bool(self.rows.count()));self.empty.setVisible(not self.rows.count())
        scrollbar.setValue(scroll_position)
        self.status.setText(self.model.error);self.status.setVisible(bool(self.model.error))
        self.refresh_actions()

    def sync_calendar(self,colors):
        style=tuple(colors[key] for key in ('ink','muted','light'))
        if style==self.calendar_style:return
        self.calendar_style=style
        self.rows.viewport().update()
        self.calendar.updateCells()
        for control, symbol in ((self.previous_month, 'back'), (self.next_month, 'fold')):
            control.setIcon(icon(symbol, colors['ink'], 13))
            control.setIconSize(QSize(13, 13))
        for source, label in self.legend.items():
            label.setText(f'<span style="color:{source_color(source, colors)}">●</span> {DISPLAY_SOURCES[source]}')

    def toggle_reminder(self):
        event=next((row for row in self.model.events if row['id']==self.selected()),None)
        if event:
            self.model.set_reminder(event['id'],enabled=event['ack']);self.refresh()

    def resizeEvent(self,event):
        self.layout_.setDirection(QBoxLayout.LeftToRight if content_columns(self.owner.width())==2 else QBoxLayout.TopToBottom)
        if event.size().width()!=event.oldSize().width():self.update_day_heading()
        super().resizeEvent(event)

    def edit(self,key=None):
        from ui_style import ModernSpinBox, SettingsHeader, button, compact_dialog, exec_dialog, label
        event=next((row for row in self.model.events if row['id']==key),None)
        if key and event is None:return
        synced=bool(event and event.get('synced'))
        initial=local_time(event['start']) if event else QDateTime(self.calendar.selectedDate(),QDateTime.currentDateTime().time())
        timing = event.get('timing') if event else None
        dialog=QDialog(self.owner, Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        dialog.setWindowTitle('日程提醒设置' if synced else '编辑日程' if event else '新增日程')
        dialog.setProperty('simpleForms',True)
        layout=QVBoxLayout(dialog);layout.addWidget(SettingsHeader(dialog,dialog.windowTitle()))
        form=QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        layout.addLayout(form)
        title=QLineEdit(event['title'] if event else '');title.setMaxLength(120);title.setReadOnly(synced)
        title.setAccessibleName('标题');form.addRow('标题',title)

        pattern = 'yyyy-MM-dd' if timing == 'all_day' else 'yyyy-MM-dd HH:mm'

        def add_date_field(caption, value):
            if synced:
                field = QLineEdit(value.toString(pattern))
                field.setReadOnly(True)
            else:
                field = QDateTimeEdit(value)
                field.setDisplayFormat(pattern)
                field.setCalendarPopup(True)
            field.setAccessibleName(caption)
            form.addRow(caption, field)
            return field

        end = None
        if timing == 'deadline':
            start = add_date_field('截止', initial)
        elif timing == 'all_day':
            last = local_time(event_last_second(event))
            single_day = initial.date() == last.date()
            start = add_date_field('日期' if single_day else '开始', initial)
            if not single_day:
                end = add_date_field('结束', last)
        else:
            start = add_date_field('开始', initial)
            end = add_date_field('结束', local_time(event['end']) if event else initial.addSecs(1800))
        dialog.resize(420, 246 if end is not None else 220)
        lead=ModernSpinBox();lead.setRange(0,180);lead.setValue(event['lead'] if event else 5)
        lead.setAccessibleName('提前提醒（分钟）')
        lead.setSpecialValueText('截止时' if timing=='deadline' else '开始时');form.addRow('提前提醒（分钟）',lead)
        if synced:
            layout.addWidget(label(f"标题和时间随 {SOURCES[event['source']]} 同步。", 'muted'))
        status=QLabel();status.setWordWrap(True);status.hide();layout.addWidget(status)
        actions=QHBoxLayout()
        def show_error():
            status.setText(self.model.error)
            status.show()
        def save():
            if synced:
                saved=self.model.synced_reminder(key,lead=lead.value())
            else:
                start_epoch = start.dateTime().toSecsSinceEpoch()
                if timing == 'all_day':
                    last_day = end.date() if end is not None else start.date()
                    start_epoch = start.date().startOfDay().toSecsSinceEpoch()
                    end_epoch = last_day.addDays(1).startOfDay().toSecsSinceEpoch()
                elif timing == 'deadline':
                    end_epoch = start_epoch + event['end'] - event['start']
                else:
                    end_epoch = end.dateTime().toSecsSinceEpoch()
                saved=self.model.update_event(key,title=title.text().strip(),start=start_epoch,
                                              end=end_epoch,lead=lead.value())
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
