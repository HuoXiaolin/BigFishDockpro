"""Native app-styled traffic, AI usage and music views."""
from datetime import datetime
from PyQt5.QtCore import Qt,QDate,QRectF,QPointF,QSize
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen,QFont,QFontMetrics
from PyQt5.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton,QSlider,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QDateEdit,QDialog,QScrollArea,QFrame,QSizePolicy)
from ui_style import ModernComboBox,button
from resource_traffic import amount,totals
from resource_compact import text
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
    view.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            item=QTableWidgetItem(str(value));item.setTextAlignment(Qt.AlignVCenter|(Qt.AlignLeft if j==0 else Qt.AlignRight))
            view.setItem(i,j,item)


class InfoPage(QScrollArea):
    """Lazily created content pages share the capsule's fixed outer geometry."""
    def __init__(self,window,key):
        super().__init__();self.setWidgetResizable(True);self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body=QWidget();lay=QVBoxLayout(body);lay.setContentsMargins(3,2,3,1);lay.setSpacing(4)
        if key=='traffic':self.content=TrafficView(window)
        else:
            from resource_extras_view import WeatherView
            self.content=WeatherView(window)
        lay.addWidget(self.content);lay.addStretch();self.setWidget(body)
    def refresh(self):self.content.refresh()


class TrafficView(QWidget):
    def __init__(self,window):
        super().__init__();self.owner=window;lay=QVBoxLayout(self);lay.setContentsMargins(0,0,0,0);lay.setSpacing(4)
        head=QHBoxLayout();head.addWidget(QLabel('流量统计'),1);history=QToolButton();history.setText('历史记录');history.clicked.connect(self.history);head.addWidget(history);lay.addLayout(head)
        self.summary=TrafficReadout(window);lay.addWidget(self.summary)
        self.note=QLabel();self.note.setObjectName('Subtle');self.note.setWordWrap(True);lay.addWidget(self.note)
        self.remarks=QToolButton();self.remarks.setText('备注');self.remarks.setCheckable(True);lay.addWidget(self.remarks,0,Qt.AlignLeft)
        self.remarks.toggled.connect(self.note.setVisible);self.note.hide()
    def refresh(self):
        data=self.owner.service.latest.get('traffic') or {}
        self.summary.update();self.note.setText(data.get('error') or '统计开启期间的累计流量');self.note.setToolTip('按本机日历累计下载与上传；暂停监控期间不累计。')
    def history(self):
        from ui_style import exec_dialog
        dialog=QDialog(self.owner);dialog.setWindowTitle('流量历史');dialog.resize(610,440);lay=QVBoxLayout(dialog)
        mode=ModernComboBox();mode.addItems(['按日','按月','按年']);lay.addWidget(mode)
        view=table(['日期','下载','上传','合计']);lay.addWidget(view)
        def refresh():
            days=(self.owner.service.latest.get('traffic') or {}).get('days',{});group={};size=(10,7,4)[mode.currentIndex()]
            for date,value in days.items():
                row=group.setdefault(date[:size],[0,0]);row[0]+=value[0];row[1]+=value[1]
            set_rows(view,[(k,amount(v[0]),amount(v[1]),amount(sum(v))) for k,v in sorted(group.items(),reverse=True)])
        mode.currentIndexChanged.connect(refresh);refresh();exec_dialog(dialog)


class TrafficReadout(QWidget):
    def __init__(self,window):
        super().__init__();self.owner=window;self.setFixedHeight(66)
    def paintEvent(self,event):
        c=self.owner.colors
        if not c:return
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);data=self.owner.service.latest.get('traffic') or {};span=self.width()/3
        for i,(key,label) in enumerate((('day','今日'),('month','本月'),('year','本年'))):
            x=i*span;values=data.get(key)
            text(p,QRectF(x,0,span-10,18),label,c['muted'],10)
            text(p,QRectF(x,19,span-10,25),amount(sum(values)) if values is not None else '—',c['ink'],18,True)
            text(p,QRectF(x,45,span-10,19),'↓ '+amount(values[0])+'   ↑ '+amount(values[1]) if values is not None else '↓ —   ↑ —',c['muted'],10)


def reset_text(value):
    if not value:return ''
    try:
        seconds=max(0,int((datetime.fromisoformat(value.replace('Z','+00:00'))-datetime.now().astimezone()).total_seconds()))
        return f'{seconds//86400}天 {(seconds%86400)//3600}小时后重置' if seconds>=86400 else f'{seconds//3600}小时 {(seconds%3600)//60}分后重置'
    except (ValueError,TypeError):return ''


def token_text(value):
    return f'{value/1e6:.2f}M' if value>=1e6 else f'{value/1e3:.1f}K' if value>=1e3 else str(value)


def cost_text(summary):
    cost=summary.get('cost');unpriced=summary.get('unpriced',0)
    return '未定价' if cost is None or (not cost and unpriced) else ('≈' if summary.get('estimated') else '')+f'${cost:.2f}'+(' +' if unpriced else '')


class AiView(QWidget):
    def __init__(self,window):
        super().__init__();self.owner=window;self.signature=None
        lay=QVBoxLayout(self);lay.setContentsMargins(3,0,3,0);lay.setSpacing(3)
        from resource_statistics import StatisticsView
        self.statistics=StatisticsView(window);self.summary=self.statistics.quotas;lay.addWidget(self.statistics)
        self._detail_dialog=None
    @property
    def detail_dialog(self):self.ensure_details();return self._detail_dialog
    @property
    def provider(self):self.ensure_details();return self._provider
    @property
    def models(self):self.ensure_details();return self._models
    def ensure_details(self):
        if self._detail_dialog is not None:return
        self._detail_dialog=QDialog(self.owner);self._detail_dialog.setWindowTitle('AI 用量明细');self._detail_dialog.resize(700,430)
        detail_lay=QVBoxLayout(self._detail_dialog)
        filters=QHBoxLayout();self._provider=ModernComboBox();self._provider.addItem('全部工具','')
        self.start=QDateEdit(QDate.currentDate().addDays(-6));self.end=QDateEdit(QDate.currentDate())
        for date in (self.start,self.end):
            date.setCalendarPopup(True);date.setDisplayFormat('yyyy-MM-dd');date.setMinimumDate(QDate(2000,1,1));date.setMaximumDate(QDate.currentDate());date.dateChanged.connect(self.details)
        filters.addWidget(self._provider);filters.addWidget(self.start);filters.addWidget(QLabel('至'));filters.addWidget(self.end);detail_lay.addLayout(filters)
        self._models=table(['工具 / 模型','Token','费用（USD）']);detail_lay.addWidget(self._models,1)
        self._models.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        note=QLabel('费用为记录金额或模型单价估算；“+”包含未定价记录。订阅实付以账单为准。');note.setWordWrap(True);detail_lay.addWidget(note)
        self._provider.currentIndexChanged.connect(self.details)
        self.refresh()
    def show_details(self,provider='',period=None):
        self.ensure_details();self.refresh()
        self.provider.setCurrentIndex(max(0,self.provider.findData(provider if isinstance(provider,str) else '')))
        if period:
            from resource_usage import bounds
            start,end=bounds(period);self.start.setDate(QDate(start.year,start.month,start.day) if start else self.start.minimumDate());self.end.setDate(QDate(end.year,end.month,end.day))
        self.detail_dialog.setStyleSheet('QDialog{background:%s}'%self.owner.colors['surface'])
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
                row=group.setdefault(p['name']+' / '+day['model'],[0,0.,0]);s=day['summary'];row[0]+=s['tokens'];row[1]+=s.get('cost') or 0;row[2]+=s.get('unpriced',0)
        set_rows(self.models,[(k,f'{v[0]:,}',('未定价' if v[1]==0 and v[2] else f'${v[1]:.4f}'+(' + 未定价' if v[2] else ''))) for k,v in sorted(group.items(),key=lambda r:r[1][0],reverse=True)])


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
        super().__init__();self.view=view;self.setFixedSize(46,24)
    def paintEvent(self,event):
        c=self.view.owner.colors
        if not c:return
        bridge=self.view.owner.service.deck;active=bridge and (bridge.media.get('track') or {}).get('state')=='Playing'
        levels=bridge.levels if active else [0]*8;p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(c['muted']),3,Qt.SolidLine,Qt.RoundCap))
        for i,level in enumerate(levels[:8]):
            height=2+level*17;p.drawLine(QPointF(3+i*5.5,12-height/2),QPointF(3+i*5.5,12+height/2))


class MediaLabel(QLabel):
    """Bounded text lines: no QLabel word-wrap height squeezing or top clipping."""
    def __init__(self,lines=1,size=11,bold=False):
        super().__init__()
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
        p=QPainter(self);font=self.font();font.setPixelSize(self.pixel_size);font.setWeight(QFont.DemiBold if self.bold else QFont.Normal);p.setFont(font);p.setPen(self.palette().windowText().color())
        fm=p.fontMetrics();remaining=' '.join(self.text().split());width=max(1,self.width());line_h=self.height()/self.lines
        for line in range(self.lines):
            if line==self.lines-1:value=fm.elidedText(remaining,Qt.ElideRight,width)
            else:
                count=0
                while count<len(remaining) and fm.horizontalAdvance(remaining[:count+1])<=width:count+=1
                value=remaining[:max(1,count)];remaining=remaining[max(1,count):].lstrip()
            p.drawText(QRectF(0,line*line_h,width,line_h),Qt.AlignLeft|Qt.AlignVCenter,value)


class MusicView(QScrollArea):
    def __init__(self,window):
        super().__init__();self.owner=window;self.track_id='';self.seeking=False;self.route_ids=None
        self.setWidgetResizable(True);self.setFrameShape(QFrame.NoFrame);self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body=QWidget();self.setWidget(body);lay=QVBoxLayout(body);lay.setContentsMargins(4,0,4,3);lay.setSpacing(3)
        head=QHBoxLayout();head.addStretch();self.sources=ModernComboBox();self.sources.setMaximumWidth(260);self.sources.setMinimumWidth(60);self.sources.setFixedHeight(21);head.addWidget(self.sources)
        self.sources.setStyleSheet('QComboBox{min-height:0;padding:2px 30px 2px 7px;border:0;background:transparent;font-size:11px}')
        self.pin=QToolButton();self.pin.setText('固定');self.pin.setToolTip('固定当前播放器');self.pin.setCheckable(True);head.addWidget(self.pin);lay.addLayout(head)
        self.sources.activated.connect(lambda:self.send(op='select',id=self.sources.currentData() or ''))
        self.pin.clicked.connect(lambda on:self.send(op='pin',on=on))
        content=self.content_layout=QHBoxLayout();content.setSpacing(16);self.cover=CoverArt(self);content.addWidget(self.cover,0,Qt.AlignTop)
        texts=QVBoxLayout();self.title=MediaLabel(2,13,True);self.artist=MediaLabel(1,10);self.lyric=MediaLabel(1,11)
        texts.setSpacing(2);texts.setContentsMargins(0,2,0,3)
        for label in (self.title,self.artist,self.lyric):label.setTextFormat(Qt.PlainText);label.setWordWrap(True);label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        title_row=QHBoxLayout();title_row.addWidget(self.title,1);self.meter=AudioMeter(self);title_row.addWidget(self.meter,0,Qt.AlignTop);texts.addLayout(title_row)
        texts.addWidget(self.artist);texts.addWidget(self.lyric)
        self.artist.setObjectName('Subtle')
        content.addLayout(texts,1);lay.addLayout(content);lay.addSpacing(5)
        self.slider=QSlider(Qt.Horizontal);self.slider.setRange(0,1000);self.slider.setFixedHeight(17);self.slider.sliderPressed.connect(lambda:setattr(self,'seeking',True));self.slider.sliderReleased.connect(self.seek);lay.addWidget(self.slider)
        times=QHBoxLayout();self.time=QLabel();self.duration=QLabel();self.time.setObjectName('Subtle');self.duration.setObjectName('Subtle');times.addWidget(self.time);times.addStretch();times.addWidget(self.duration);lay.addLayout(times)
        controls=self.controls_layout=QHBoxLayout();controls.setSpacing(14);controls.addStretch();self.buttons={}
        for op,title in [('Shuffle','随机播放'),('Previous','上一首'),('PlayPause','播放 / 暂停'),('Next','下一首'),('Repeat','循环播放')]:
            btn=TransportButton(self,op,title);controls.addWidget(btn);self.buttons[op]=btn
        controls.addStretch();lay.addLayout(controls);self.status=QLabel();self.status.setObjectName('Subtle');self.status.setWordWrap(True);lay.addWidget(self.status);lay.addStretch(1)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not hasattr(self,'buttons'):return
        small=self.width()<340;self.cover.setFixedSize(38 if small else 70,38 if small else 70)
        self.content_layout.setSpacing(8 if small else 16);self.controls_layout.setSpacing(6 if small else 14)
        self.title.fit_text(11 if small else 13)
        self.meter.setVisible(not small)
    def send(self,**data):
        if data.get('op') == 'PlayPause' and self.track_id:
            data.setdefault('id', self.track_id)
        if self.owner.service.deck:self.owner.service.deck.send(**data)
    def seek(self):
        self.seeking=False;self.send(op='seek',fraction=self.slider.value()/1000)
    def refresh(self):
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
        self.lyric.setText(track.get('lyric') or ('暂无歌词' if track else '播放音乐后自动显示'))
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
