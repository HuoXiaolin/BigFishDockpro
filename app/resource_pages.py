"""Native app-styled traffic, AI usage and music views."""
from datetime import datetime
from PyQt5.QtCore import Qt,QDate,QRectF,QPointF,QSize
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen,QFont,QFontMetrics,QPalette
from PyQt5.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton,QSlider,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDateEdit,QDialog,QScrollArea,QFrame,QSizePolicy,QMessageBox,QLayout)
from ui_style import ModernComboBox,SettingsHeader,button,exec_dialog
from resource_traffic import amount,totals
from resource_compact import text
from card_design import paint_capsule_card
from resource_charts import DashboardCard,rate,sync_card_controls
from resource_options import content_columns
from resource_status import threshold

SCROLL_STYLE='''
QScrollBar:vertical{width:5px;margin:0;background:transparent}
QScrollBar:horizontal{height:5px;margin:0;background:transparent}
QScrollBar::handle{background:rgba(120,140,155,100);border-radius:2px;min-height:24px;min-width:24px}
QScrollBar::add-line,QScrollBar::sub-line{width:0;height:0}
QScrollBar::add-page,QScrollBar::sub-page{background:transparent}
'''


def table(headings):
    view=QTableWidget(0,len(headings));view.setHorizontalHeaderLabels(headings)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers);view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.verticalHeader().hide();view.setShowGrid(False);view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return view


def set_rows(view,rows):
    if view.rowCount()!=len(rows):view.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            value=str(value);item=view.item(i,j)
            if item is None:
                item=QTableWidgetItem(value);item.setTextAlignment(Qt.AlignVCenter|(Qt.AlignLeft if j==0 else Qt.AlignRight))
                if j==0:item.setToolTip(value)
                view.setItem(i,j,item)
            elif item.text()!=value:
                item.setText(value)
                if j==0:item.setToolTip(value)


class CapsuleScrollArea(QScrollArea):
    """Keep the viewport full-width while preserving native scrolling."""
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setProperty('scrollThroughContent',True)

    def wheelEvent(self,event):
        bar=self.verticalScrollBar()
        pixels=event.pixelDelta().y()
        angle=event.angleDelta().y()
        if bar.maximum()==0 or not (pixels or angle):
            super().wheelEvent(event)
            return
        delta=pixels or round(angle*bar.singleStep()*QApplication.wheelScrollLines()/120)
        bar.setValue(bar.value()-delta)
        event.accept()


class InfoPage(CapsuleScrollArea):
    """Lazily created content pages share the capsule's fixed outer geometry."""
    def __init__(self,window,key):
        super().__init__()
        body=QWidget();lay=QVBoxLayout(body);lay.setContentsMargins(3,2,3,1);lay.setSpacing(4)
        lay.setSizeConstraint(QLayout.SetMinAndMaxSize)
        if key=='traffic':self.content=TrafficView(window)
        elif key=='weather':
            from resource_extras_view import WeatherView
            self.content=WeatherView(window)
        elif key=='pomodoro':
            from resource_pomodoro_view import PomodoroView
            self.content=PomodoroView(window)
        elif key=='agenda':
            from resource_agenda_view import AgendaView
            self.content=AgendaView(window)
        else:
            from resource_content import ContentView
            self.content=ContentView(window,key)
        lay.addWidget(self.content);lay.addStretch();self.setWidget(body)
    def refresh(self):self.content.refresh()


class TrafficView(QWidget):
    def __init__(self,window):
        super().__init__();self.owner=window;lay=QVBoxLayout(self);lay.setContentsMargins(0,0,0,0);lay.setSpacing(4)
        head=QHBoxLayout();title=QLabel('流量统计');title.setObjectName('RankTitle');head.addWidget(title,1)
        history=QToolButton();history.setText('历史记录');history.clicked.connect(self.history);head.addWidget(history);lay.addLayout(head)
        self.summary=TrafficReadout(window);lay.addWidget(self.summary)
        self.apps=DashboardCard(window,'ice',self);lay.addWidget(self.apps)
        app_lay=QVBoxLayout(self.apps);app_lay.setContentsMargins(8,5,8,6);app_lay.setSpacing(3)
        app_head=QHBoxLayout();app_title=QLabel('应用实时流量');app_title.setObjectName('RankTitle')
        app_head.addWidget(app_title,1)
        self.record=QToolButton();self.record.clicked.connect(self.toggle_recording);app_head.addWidget(self.record)
        ranking=QToolButton();ranking.setText('应用历史');ranking.clicked.connect(lambda:self.history(True));app_head.addWidget(ranking)
        app_lay.addLayout(app_head)
        self.live=None
        self.app_status=QLabel();self.app_status.setObjectName('Subtle')
        self.app_status.setWordWrap(True);app_lay.addWidget(self.app_status)
        self.note=QLabel();self.note.setObjectName('Subtle');self.note.setWordWrap(True);lay.addWidget(self.note)
        self.remarks=QToolButton();self.remarks.setText('备注');self.remarks.setCheckable(True);lay.addWidget(self.remarks,0,Qt.AlignLeft)
        self.remarks.toggled.connect(self.note.setVisible);self.note.hide()
        self._live_signature=None
        signal=getattr(window.service,'app_traffic_updated',None)
        if signal is not None:signal.connect(self.refresh)
        totals_signal=getattr(window.service,'traffic_updated',None)
        if totals_signal is not None:totals_signal.connect(self.refresh_totals)

    def live_table(self):
        view=table(['应用','下载','上传'])
        view.setAccessibleName('应用实时流量排行')
        view.setSelectionMode(QAbstractItemView.NoSelection)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.verticalHeader().setDefaultSectionSize(22)
        view.horizontalHeader().setMinimumHeight(21)
        view.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for col in (1,2):view.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeToContents)
        layout=self.apps.layout()
        layout.insertWidget(layout.indexOf(self.app_status),view)
        self._table_style=None
        return view

    def toggle_recording(self):
        service=self.owner.service
        service.set_options(resource_app_traffic=not service.cfg.get('resource_app_traffic',False))
        self.refresh()

    def refresh(self):
        service=self.owner.service
        colors=self.owner.colors
        active=service.cfg.get('resource_app_traffic',False)
        snapshot=service.app_traffic_snapshot(None) if active and hasattr(service,'app_traffic_snapshot') else {}
        rows=tuple(snapshot.get('live',())[:5])
        if rows and self.live is None:self.live=self.live_table()
        elif not active and self.live is not None:
            view,self.live=self.live,None
            self.apps.layout().removeWidget(view)
            view.hide();view.deleteLater()
        if colors:
            sync_card_controls(self,colors)
            table_style=(colors['ink'],colors['muted'],colors['hover'])
            if self.live is not None and table_style!=self._table_style:
                self._table_style=table_style
                self.live.setStyleSheet('QTableWidget{background:transparent;border:0;color:%s}'
                    'QHeaderView::section{background:%s;color:%s;border:0;padding:2px 4px}'
                    %(table_style[0],table_style[2],table_style[1]))
        self.refresh_totals()
        self.record.setText('停止记录' if active else '开始记录')
        if rows!=self._live_signature:
            self._live_signature=rows
            if self.live is not None:
                set_rows(self.live,[(name,rate(down),rate(up)) for name,down,up in rows])
                self.live.setFixedHeight(24+22*len(rows))
                self.live.setVisible(bool(rows))
        status=snapshot.get('error') or snapshot.get('status')
        if not status:
            status=('等待应用产生网络流量…' if active else '开启后记录本机应用的上传和下载量。') if not rows else ''
        if self.app_status.text()!=status:self.app_status.setText(status)
        self.app_status.setVisible(bool(status))

    def refresh_totals(self):
        data=self.owner.service.latest.get('traffic') or {}
        self.summary.update()
        self.note.setText(data.get('error') or '按本机日历累计下载与上传。应用记录从开启时开始。')

    def history(self,apps=False):
        exec_dialog(TrafficHistory(self.owner,apps))


class TrafficHistory(QDialog):
    def __init__(self,owner,apps):
        super().__init__(owner,Qt.Dialog|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.owner=owner;self.apps=apps;self.service=owner.service
        self.setWindowTitle('应用流量历史' if apps else '流量历史')
        self.setObjectName('TrafficHistory')
        self.setProperty('compactDialog',True)
        self.resize(590,402);self.setMinimumSize(360,250);self.setSizeGripEnabled(True)
        layout=QVBoxLayout(self);layout.setContentsMargins(14,12,14,12);layout.setSpacing(9)
        layout.addWidget(SettingsHeader(self,self.windowTitle()))
        filters=QHBoxLayout();filters.setSpacing(8)
        filters.addWidget(QLabel('统计范围' if apps else '分组方式'))
        self.mode=ModernComboBox();filters.addWidget(self.mode);filters.addStretch(1)
        periods=(('今日','day'),('本月','month'),('本年','year'),('全部','all')) if apps else (
            ('按日',10),('按月',7),('按年',4))
        for title,value in periods:self.mode.addItem(title,value)
        layout.addLayout(filters)
        self.rows=table(['应用' if apps else '日期','下载','上传','合计'])
        self.rows.setAccessibleName(self.windowTitle())
        self.rows.setAlternatingRowColors(True)
        self.rows.verticalHeader().setDefaultSectionSize(31)
        self.rows.horizontalHeader().setMinimumHeight(31)
        self.rows.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for col in (1,2,3):self.rows.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeToContents)
        layout.addWidget(self.rows,1)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setProperty('role','muted');layout.addWidget(self.status)
        footer=QHBoxLayout()
        self.clear=button('清空应用历史' if apps else '清空流量历史',self.clear_history,'danger')
        footer.addWidget(self.clear);footer.addStretch(1);footer.addWidget(button('关闭',self.reject))
        layout.addLayout(footer)
        self._group_key=None;self._grouped_rows=();self._rendered_rows=None
        self.mode.currentIndexChanged.connect(self.refresh)
        signal=getattr(self.service,'app_traffic_updated' if apps else 'traffic_updated',None)
        if signal is not None:signal.connect(self.refresh)
        self.apply_colors()
        self.refresh()

    def refresh_interface_style(self):self.apply_colors()

    def apply_colors(self):
        palette=QApplication.palette()
        self.setPalette(palette)
        style={key:palette.color(role).name() for key,role in (
            ('window',QPalette.Window),('base',QPalette.Base),('text',QPalette.Text),
            ('alternate',QPalette.AlternateBase),('selection',QPalette.Highlight),
            ('selected',QPalette.HighlightedText),('muted',QPalette.PlaceholderText))}
        self.setStyleSheet('''
            QDialog#TrafficHistory {background:%(window)s;color:%(text)s;}
            QDialog#TrafficHistory QLabel {background:transparent;color:%(text)s;}
            QDialog#TrafficHistory QLabel[role="muted"] {color:%(muted)s;}
            QDialog#TrafficHistory QTableWidget {background:%(base)s;alternate-background-color:%(alternate)s;
                color:%(text)s;selection-background-color:%(selection)s;selection-color:%(selected)s;border:0;}
            QDialog#TrafficHistory QTableWidget::item {padding:0 6px;}
            QDialog#TrafficHistory QHeaderView {background:%(alternate)s;}
            QDialog#TrafficHistory QHeaderView::section {background:%(alternate)s;color:%(text)s;
                border:0;padding:4px 8px;}
            QDialog#TrafficHistory QComboBox {background:%(base)s;color:%(text)s;}
        '''%style)

    def refresh(self):
        if self.apps:
            data=self.service.app_traffic_snapshot(self.mode.currentData())
            rows=data.get('history',())
            status=data.get('error') or ('按应用合计流量排序。' if rows else '这个范围内还没有应用流量记录。')
        else:
            data=self.service.latest.get('traffic') or {}
            days=data.get('days',{});width=self.mode.currentData()
            key=(width,days)
            if self._group_key!=key:
                self._group_key=key
                group={}
                for date,value in days.items():
                    row=group.setdefault(date[:width],[0,0]);row[0]+=value[0];row[1]+=value[1]
                self._grouped_rows=tuple((date,down,up) for date,(down,up) in sorted(group.items(),reverse=True))
            rows=self._grouped_rows
            pending=getattr(self.service,'traffic_reset_pending',False)
            self.clear.setEnabled(not pending)
            status=('正在清空总流量记录…' if pending else
                    getattr(self.service,'traffic_reset_error','') or data.get('error') or
                    ('' if rows else '暂无流量记录。'))
        rows=tuple(rows)
        if rows!=self._rendered_rows:
            self._rendered_rows=rows
            set_rows(self.rows,[(name,amount(down),amount(up),amount(down+up)) for name,down,up in rows])
        if self.status.text()!=status:self.status.setText(status)
        self.status.setVisible(bool(status))

    def clear_history(self):
        title='清空应用流量历史' if self.apps else '清空总流量历史'
        content=('清空所有日期的应用流量记录？总流量统计会保留。' if self.apps else
                 '清空所有日期的总流量记录？应用流量历史会保留。')
        if QMessageBox.question(self,title,content,QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return
        if not self.service.reset_traffic(self.apps):
            self.status.setText('暂时无法清空流量记录，请稍后重试。');self.status.show()
        else:self.refresh()


class TrafficReadout(QWidget):
    gap=6
    periods=(('day','今日','ice'),('month','本月','lavender'),('year','本年','mint'))

    def __init__(self,window):
        super().__init__();self.owner=window
        self.fit_cards()

    def fit_cards(self):
        self.columns=content_columns(self.owner.width())
        pairs,unpaired=divmod(len(self.periods),2) if self.columns==2 else (0,len(self.periods))
        rows=pairs+unpaired
        self.setFixedHeight(pairs*83+unpaired*57+(rows-1)*self.gap)

    def resizeEvent(self,event):
        self.fit_cards()
        super().resizeEvent(event)

    def paintEvent(self,event):
        c=self.owner.colors
        if not c:return
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        data=self.owner.service.latest.get('traffic') or {}
        for i,(key,label,tint) in enumerate(self.periods):
            row,column=divmod(i,self.columns)
            paired=self.columns==2 and (row+1)*self.columns<=len(self.periods)
            width=(self.width()-self.gap)/2 if paired else self.width()
            height=83 if paired else 57
            x=column*(width+self.gap)
            y=row*((83 if self.columns==2 else 57)+self.gap)
            values=data.get(key)
            paint_capsule_card(p,QRectF(x,y,width,height),c,tint,self.owner.background)
            text(p,QRectF(x+10,y+5,width-20,16),label,c['muted'],10)
            total=amount(sum(values)) if values is not None else '—'
            text(p,QRectF(x+10,y+21,width-20 if paired else width/2-12,25),total,c['ink'],18,True)
            detail_x=x+10 if paired else x+width/2
            detail_width=x+width-10-detail_x
            detail_y=y+48 if paired else y+10
            for j,title in enumerate(('下载','上传')):
                top=detail_y+15*j
                text(p,QRectF(detail_x,top,detail_width,14),title,c['muted'],10)
                text(p,QRectF(detail_x,top,detail_width,14),amount(values[j]) if values is not None else '—',
                     c['ink'],10,True,Qt.AlignRight)


def reset_text(value):
    if not isinstance(value, str) or not value:
        return ''
    try:
        reset_at = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone()
        seconds = (reset_at - datetime.now().astimezone()).total_seconds()
    except (ValueError, OverflowError, OSError):
        return ''
    if seconds <= 0:
        return '已到恢复时间'
    minutes = int(seconds) // 60
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f'{days} 天 {hours} 小时后恢复'
    if hours:
        return f'{hours} 小时 {minutes} 分钟后恢复'
    return f'{minutes} 分钟后恢复' if minutes else '不到 1 分钟后恢复'


def token_text(value):
    return f'{value/1e6:.2f}M' if value>=1e6 else f'{value/1e3:.1f}K' if value>=1e3 else str(value)


def cost_text(summary,currency=True):
    cost=summary.get('cost')
    if cost is None or (cost==0 and summary.get('unpriced')):
        return '未定价'
    prefix='$' if currency else ''
    if 0<cost<.000001:return '<'+prefix+'0.000001'
    decimals=2 if not cost or abs(cost)>=.01 else 4 if abs(cost)>=.0001 else 6
    value=f'{cost:,.{decimals}f}'
    return prefix+(value.rstrip('0') if decimals>2 else value)


def cost_note(summary):
    notes=['含估算'] if summary.get('estimated') else []
    if count:=summary.get('unpriced',0):
        notes.append(f'{count} 条未定价')
    return ' · '.join(notes)


class AiView(QWidget):
    def __init__(self,window):
        super().__init__();self.owner=window;self.signature=None
        lay=QVBoxLayout(self);lay.setContentsMargins(3,0,3,0);lay.setSpacing(3)
        from resource_statistics import StatisticsView
        self.statistics=StatisticsView(window);self.summary=self.statistics.quotas;lay.addWidget(self.statistics)
        self._detail_dialog=None;self.detail_dates=None
    @property
    def detail_dialog(self):self.ensure_details();return self._detail_dialog
    @property
    def provider(self):self.ensure_details();return self._provider
    @property
    def models(self):self.ensure_details();return self._models
    def ensure_details(self):
        if self._detail_dialog is not None:return
        self._detail_dialog=QDialog(self);self._detail_dialog.setWindowTitle('AI 用量明细');self._detail_dialog.resize(720,390)
        self._detail_dialog.setMinimumSize(620,300)
        self._detail_dialog.setWindowFlags(self._detail_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        detail_lay=QVBoxLayout(self._detail_dialog);detail_lay.setContentsMargins(16,12,16,12);detail_lay.setSpacing(10)
        filters=QHBoxLayout();self._provider=ModernComboBox();self._provider.addItem('全部工具','')
        self._provider.setMinimumWidth(156);self._provider.setMaximumWidth(220)
        start,end=self.detail_dates or (QDate.currentDate().addDays(-6),QDate.currentDate())
        self.start=QDateEdit(start);self.end=QDateEdit(end)
        for date in (self.start,self.end):
            date.setCalendarPopup(True);date.setDisplayFormat('yyyy-MM-dd');date.setMinimumDate(QDate(2000,1,1));date.setMaximumDate(QDate.currentDate());date.dateChanged.connect(self.details)
        for date in (self.start,self.end):date.setFixedWidth(142)
        filters.addWidget(self._provider,1);filters.addStretch();filters.addWidget(self.start);filters.addWidget(QLabel('至'));filters.addWidget(self.end);detail_lay.addLayout(filters)
        self._models=table(['工具 / 模型','Token','费用（USD）','计价情况']);detail_lay.addWidget(self._models,1)
        self._models.setAlternatingRowColors(True);self._models.verticalHeader().setDefaultSectionSize(34)
        self._models.horizontalHeader().setMinimumSectionSize(90)
        for index in range(4):self._models.horizontalHeaderItem(index).setTextAlignment(Qt.AlignVCenter|(Qt.AlignRight if index in (1,2) else Qt.AlignLeft))
        for index in (1,2,3):self._models.horizontalHeader().setSectionResizeMode(index,QHeaderView.ResizeToContents)
        self.detail_note=QLabel();self.detail_note.setProperty('role','muted');self.detail_note.setWordWrap(True);detail_lay.addWidget(self.detail_note)
        from popup_style import prepare_popup
        prepare_popup(self._detail_dialog)
        self._provider.currentIndexChanged.connect(self.details)
        self.refresh()
    def show_details(self,provider='',period=None):
        self.ensure_details();self.refresh()
        self.provider.setCurrentIndex(max(0,self.provider.findData(provider if isinstance(provider,str) else '')))
        if period:
            from resource_usage import bounds
            start,end=bounds(period);self.start.setDate(QDate(start.year,start.month,start.day) if start else self.start.minimumDate());self.end.setDate(QDate(end.year,end.month,end.day))
        self.details();self.detail_dialog.exec_()
    def refresh_request(self):
        if self.owner.service.deck:self.owner.service.deck.refresh()
    def refresh(self):
        bridge=self.owner.service.deck;self.statistics.refresh()
        if self._detail_dialog is None:return
        providers=bridge.providers if bridge else []
        ids=tuple(p['id'] for p in providers)
        if ids!=self.signature:
            selected=self.provider.currentData();self.provider.blockSignals(True);self.provider.clear();self.provider.addItem('全部工具','')
            for p in providers:self.provider.addItem(p['name'],p['id'])
            self.provider.setCurrentIndex(max(0,self.provider.findData(selected)));self.provider.blockSignals(False);self.signature=ids
        self.details()
    def details(self):
        bridge=self.owner.service.deck;group={};start=self.start.date().toString('yyyy-MM-dd');end=self.end.date().toString('yyyy-MM-dd')
        key=(id(bridge.providers) if bridge else 0,self.provider.currentData(),start,end)
        if key==getattr(self,'details_key',None):return
        self.details_key=key
        for p in bridge.providers if bridge else []:
            if self.provider.currentData() and p['id']!=self.provider.currentData():continue
            for day in p.get('days',[]):
                if not start<=day['date']<=end:continue
                row=group.setdefault(p['name']+' / '+day['model'],[])
                row.append(day['summary'])
        from resource_usage import combine
        summaries={name:combine(rows) for name,rows in group.items()}
        set_rows(self.models,[(name,f"{row['tokens']:,}" if row['tokens'] is not None else '—',
                              cost_text(row,currency=False),cost_note(row) or '—')
                             for name,row in sorted(summaries.items(),key=lambda item:item[1]['tokens'] or 0,reverse=True)])
        self.detail_note.setText('开始日期不能晚于结束日期。' if start>end else
            '估算和未定价记录在「计价情况」中标注。' if summaries else '当前日期范围内没有用量记录。')
        for row in range(self.models.rowCount()):self.models.item(row,3).setTextAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        if summaries and not getattr(self,'_details_sized',False):
            self._details_sized=True
            self.detail_dialog.resize(self.detail_dialog.width(),min(450,max(270,136+34*len(summaries))))


class TransportButton(QToolButton):
    def __init__(self,view,op,title):
        super().__init__();self.view=view;self.op=op;self.playing=False;self.active=False
        size = 29 if op == 'PlayPause' else 23
        self.setFixedSize(size, size)
        self.setAccessibleName(title);self.setToolTip(title);self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(lambda:self.view.send(op=op))
    def paintEvent(self,event):
        c=self.view.owner.colors
        if not c:return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.op=='PlayPause':
            p.setPen(Qt.NoPen);p.setBrush(QColor(c['hover']));p.drawEllipse(QRectF(self.rect()).adjusted(1,1,-1,-1))
        p.translate(self.width()/2,self.height()/2);p.scale(.8,.8);ink=QColor(c['ink'] if self.op in ('PlayPause','Previous','Next') or self.active else c['muted'])
        if not self.isEnabled():ink.setAlpha(70)
        p.setPen(QPen(ink,1.8,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(ink)
        def shape(points):
            path=QPainterPath(QPointF(*points[0]))
            for point in points[1:]:path.lineTo(*point)
            path.closeSubpath();p.drawPath(path)
        if self.op=='PlayPause':
            if self.playing:p.drawRoundedRect(QRectF(-6,-7,4,14),1,1);p.drawRoundedRect(QRectF(2,-7,4,14),1,1)
            else:shape([(-4,-7),(7,0),(-4,7)])
        elif self.op in ('Previous','Next'):
            if self.op=='Previous':p.scale(-1,1)
            shape([(-6,-6),(3,0),(-6,6)]);p.drawLine(QPointF(6,-6),QPointF(6,6))
        elif self.op=='Repeat':
            p.setBrush(Qt.NoBrush);path=QPainterPath(QPointF(-7,1));path.lineTo(-7,-3);path.quadTo(-7,-6,-4,-6);path.lineTo(7,-6);p.drawPath(path)
            path=QPainterPath(QPointF(7,-1));path.lineTo(7,3);path.quadTo(7,6,4,6);path.lineTo(-7,6);p.drawPath(path)
            p.drawLine(QPointF(4,-9),QPointF(7,-6));p.drawLine(QPointF(7,-6),QPointF(4,-3));p.drawLine(QPointF(-4,3),QPointF(-7,6));p.drawLine(QPointF(-7,6),QPointF(-4,9))
        else:
            p.setBrush(Qt.NoBrush)
            for sign in (-1,1):
                path=QPainterPath(QPointF(-8,sign*5));path.cubicTo(-1,sign*5,1,-sign*5,8,-sign*5);p.drawPath(path)
                p.drawLine(QPointF(5,-sign*8),QPointF(8,-sign*5));p.drawLine(QPointF(8,-sign*5),QPointF(5,-sign*2))
        if self.active:p.setPen(Qt.NoPen);p.setBrush(ink);p.drawEllipse(QPointF(0,14),1.5,1.5)


class CoverArt(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view;self.setFixedSize(70,70)
    def paintEvent(self,event):
        c=self.view.owner.colors
        if not c:return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.SmoothPixmapTransform)
        r=QRectF(self.rect()).adjusted(1,1,-1,-1);path=QPainterPath();path.addRoundedRect(r,10,10);p.setClipPath(path)
        bridge=self.view.owner.service.deck
        if bridge and not bridge.cover.isNull():
            pix=bridge.cover;side=min(pix.width(),pix.height());p.drawPixmap(r,pix,QRectF((pix.width()-side)/2,(pix.height()-side)/2,side,side))
        else:
            p.fillRect(r,QColor(c['hover']));p.setPen(QPen(QColor(c['muted']),1.5));p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.center(), r.width() * .30, r.height() * .30)
            p.drawEllipse(r.center(), 1.5, 1.5)


class AudioMeter(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view;self.setMinimumWidth(24);self.setFixedHeight(16)
    def paintEvent(self,event):
        c=self.view.owner.colors
        if not c:return
        bridge=self.view.owner.service.deck;active=bridge and (bridge.media.get('track') or {}).get('state')=='Playing'
        levels=bridge.levels if active else [0]*8;p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if not levels:return
        count=max(8,min(28,self.width()//5));step=self.width()/count
        for i in range(count):
            level=levels[min(len(levels)-1,i*len(levels)//count)]
            color=QColor('#1b8b7e' if c['light'] else '#79d9ca') if level>.02 else QColor(c['muted'])
            if level<=.02:color.setAlpha(65)
            p.setPen(QPen(color,2,Qt.SolidLine,Qt.RoundCap))
            height=2+level*11;x=(i+.5)*step
            p.drawLine(QPointF(x,8-height/2),QPointF(x,8+height/2))


class MediaLabel(QLabel):
    """Bounded text lines: no QLabel word-wrap height squeezing or top clipping."""
    def __init__(self,lines=1,size=11,bold=False,*,owner=None):
        super().__init__()
        self.owner=owner
        self.lines = lines
        self.bold = bold
        self.fit_text(size)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)

    def fit_text(self, size):
        self.pixel_size = size
        font = self.font()
        font.setPixelSize(size)
        font.setWeight(QFont.DemiBold if self.bold else QFont.Normal)
        self.setFixedHeight(self.lines * QFontMetrics(font).height())
    def paintEvent(self,event):
        p=QPainter(self);font=self.font();font.setPixelSize(self.pixel_size);font.setWeight(QFont.DemiBold if self.bold else QFont.Normal)
        color=QColor(self.owner.colors['ink' if self.bold else 'muted']) if self.owner else self.palette().windowText().color()
        p.setFont(font);p.setPen(color)
        fm=p.fontMetrics();remaining=' '.join(self.text().split());width=max(1,self.width());line_h=self.height()/self.lines
        for line in range(self.lines):
            if line==self.lines-1:value=fm.elidedText(remaining,Qt.ElideRight,width)
            else:
                count=0
                while count<len(remaining) and fm.horizontalAdvance(remaining[:count+1])<=width:count+=1
                value=remaining[:max(1,count)];remaining=remaining[max(1,count):].lstrip()
            p.drawText(QRectF(0,line*line_h,width,line_h),Qt.AlignLeft|Qt.AlignVCenter,value)


class MusicView(CapsuleScrollArea):
    def __init__(self,window):
        super().__init__();self.owner=window;self.track_id='';self.seeking=False;self.route_ids=None
        body=QWidget();self.setWidget(body);outer=QVBoxLayout(body);outer.setContentsMargins(3,2,3,2);outer.setSpacing(0)
        self.card=DashboardCard(window,'ice',body);outer.addWidget(self.card);outer.addStretch(1)
        lay=QVBoxLayout(self.card);lay.setContentsMargins(9,7,9,8);lay.setSpacing(5)
        head=QHBoxLayout();title=QLabel('媒体控制');title.setObjectName('RankTitle');head.addWidget(title,1)
        self.sources=ModernComboBox();self.sources.setMaximumWidth(224);self.sources.setMinimumWidth(60);self.sources.setFixedHeight(21);head.addWidget(self.sources)
        self.sources.setProperty('glassField',True)
        self.sources.setStyleSheet('QComboBox{min-height:0;padding:2px 30px 2px 7px;border:0;background:transparent;font-size:11px}')
        self.pin=QToolButton();self.pin.setText('固定');self.pin.setToolTip('固定当前播放器');self.pin.setCheckable(True);head.addWidget(self.pin);lay.addLayout(head)
        self.sources.activated.connect(lambda:self.send(op='select',id=self.sources.currentData() or ''))
        self.pin.clicked.connect(lambda on:self.send(op='pin',on=on))
        content=self.content_layout=QHBoxLayout();content.setSpacing(12);self.cover=CoverArt(self);content.addWidget(self.cover,0,Qt.AlignTop)
        texts=QVBoxLayout();self.title=MediaLabel(2,13,True,owner=window);self.artist=MediaLabel(1,10,owner=window);self.lyric=MediaLabel(1,11,owner=window)
        texts.setSpacing(1);texts.setContentsMargins(0,1,0,0)
        for label in (self.title,self.artist,self.lyric):label.setTextFormat(Qt.PlainText);label.setWordWrap(True);label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        texts.addWidget(self.title);texts.addWidget(self.artist)
        self.meter=AudioMeter(self);texts.addWidget(self.meter)
        self.artist.setObjectName('Subtle')
        progress=QHBoxLayout();progress.setSpacing(3)
        self.slider=QSlider(Qt.Horizontal);self.slider.setRange(0,1000);self.slider.setFixedHeight(14);self.slider.sliderPressed.connect(lambda:setattr(self,'seeking',True));self.slider.sliderReleased.connect(self.seek);progress.addWidget(self.slider,1)
        self.time=QLabel();self.duration=QLabel()
        for label in (self.time,QLabel('/'),self.duration):
            label.setObjectName('Subtle');progress.addWidget(label)
        texts.addLayout(progress)
        controls=self.controls_layout=QHBoxLayout();controls.setSpacing(3);self.buttons={}
        for op,title in [('Previous','上一首'),('PlayPause','播放 / 暂停'),('Next','下一首'),('Shuffle','随机播放'),('Repeat','循环播放')]:
            btn=TransportButton(self,op,title);controls.addWidget(btn);self.buttons[op]=btn
        controls.addStretch(1)
        texts.addLayout(controls)
        texts.addWidget(self.lyric)
        content.addLayout(texts,1);lay.addLayout(content)
        self.status=QLabel();self.status.setObjectName('Subtle');self.status.setWordWrap(True);lay.addWidget(self.status)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not hasattr(self,'buttons'):return
        small=self.width()<350;self.cover.setFixedSize(42 if small else 84,42 if small else 84)
        self.content_layout.setSpacing(7 if small else 12);self.controls_layout.setSpacing(1 if small else 5)
        self.fit_title()
    def fit_title(self):
        size=11 if self.width()<350 else 13
        font=QFont(self.title.font());font.setPixelSize(size);font.setWeight(QFont.DemiBold)
        available=max(1,self.viewport().width()-self.cover.width()-self.content_layout.spacing()-24)
        self.title.lines=1 if QFontMetrics(font).horizontalAdvance(self.title.text())<=available else 2
        self.title.fit_text(size)
    def send(self,**data):
        if data.get('op') == 'PlayPause' and self.track_id:
            data.setdefault('id', self.track_id)
        if self.owner.service.deck:self.owner.service.deck.send(**data)
    def seek(self):
        self.seeking=False;self.send(op='seek',fraction=self.slider.value()/1000)
    def refresh(self):
        sync_card_controls(self.card,self.owner.colors)
        bridge=self.owner.service.deck;data=bridge.media if bridge else {};track=data.get('track') or {};tracks=data.get('tracks') or []
        self.track_id = track.get('id', '')
        ids=tuple((r['id'],r['title']) for r in tracks)
        if ids!=self.route_ids:
            self.sources.clear()
            for r in tracks:
                self.sources.addItem(r['source'],r['id']);self.sources.setItemData(self.sources.count()-1,r['title'],Qt.ToolTipRole)
            if not tracks:self.sources.addItem('没有可用播放器','')
            self.route_ids=ids
        self.sources.setCurrentIndex(max(0,self.sources.findData(track.get('id'))));self.pin.setChecked(data.get('pinned',False))
        self.title.setText(track.get('title') or '没有正在播放的媒体');self.artist.setText(track.get('artist',''))
        self.artist.setVisible(bool(track.get('artist')))
        self.fit_title()
        self.lyric.setText(track.get('lyric') or ('暂无歌词' if track else '播放音乐后自动显示'))
        self.lyric.setVisible(bool(track.get('lyric')))
        status = bridge.status if bridge else '在设置中开启音乐'
        if not status and track.get('liveAudio') and track.get('state') == 'Paused':
            status = '直播声音已暂停'
        self.status.setText(status);self.status.setVisible(bool(status))
        self.cover.update();self.title.setAccessibleName(track.get('title',''));self.artist.setAccessibleName(track.get('artist',''))
        duration=track.get('duration',0);position=track.get('position',0)
        if not self.seeking:self.slider.setValue(round(min(1,position/max(1,duration))*1000))
        self.slider.setEnabled(bool(track.get('canSeek')))
        self.time.setText(f'{int(position)//60}:{int(position)%60:02}');self.duration.setText(f'{int(duration)//60}:{int(duration)%60:02}')
        for op,flag in [('Previous','canPrevious'),('PlayPause','canToggle'),('Next','canNext'),('Shuffle','canShuffle'),('Repeat','canRepeat')]:self.buttons[op].setEnabled(bool(track.get(flag)))
        playback = self.buttons['PlayPause']
        playback.playing = track.get('state') == 'Playing'
        title = ('暂停直播声音' if playback.playing else '恢复直播声音') if track.get('liveAudio') else ('暂停' if playback.playing else '播放')
        playback.setToolTip(title);playback.setAccessibleName(title)
        self.buttons['Shuffle'].active=bool(track.get('shuffle'));self.buttons['Shuffle'].setToolTip('随机：开' if track.get('shuffle') else '随机：关')
        self.buttons['Repeat'].active=track.get('repeat') in ('Track','List');self.buttons['Repeat'].setToolTip({'Track':'单曲循环','List':'列表循环'}.get(track.get('repeat'),'循环：关'))
        for btn in self.buttons.values():btn.update()
