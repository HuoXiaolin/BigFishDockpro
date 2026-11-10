"""Compact, theme-aware cost distribution and usage history from real aggregates."""
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QPainter,QPen
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QBoxLayout,QToolButton,QLabel
from ui_style import ModernComboBox
from resource_compact import text
from resource_pages import CapsuleScrollArea,token_text,cost_text,cost_note,reset_text
from resource_usage import aggregate
from resource_quota import amount_label, amount_text, quota_color, remaining_percent, used_percent
from card_design import paint_capsule_card

COLORS=('#13a58b','#428fe2','#b28a49','#897fb6','#d57480','#59a9b5','#8a9d71')


class QuotaOverview(QWidget):
    """Compact quota rows above the usage summary, sharing its provider filter."""
    def __init__(self,view):super().__init__();self.view=view;self.rows=[]
    def refresh(self,rows):
        self.rows=rows;self.fit_rows();self.update()
    def fit_rows(self):
        columns=1 if self.width()<340 else 2
        self.setFixedHeight(sum(24+45*max(1,(len(r.get('quotas',[]))+columns-1)//columns) for r in self.rows) if self.rows else 38)
    def resizeEvent(self,event):self.fit_rows();super().resizeEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.view.owner.colors
        if not c:return
        if not self.rows:
            bridge=self.view.owner.service.deck
            text(p,QRectF(10,4,self.width()-20,30),bridge.ai_status if bridge else '等待 AI 额度',c['muted'],10);return
        y=0
        for row in self.rows:
            quotas=row.get('quotas',[]);columns=min(1 if self.width()<340 else 2,max(1,len(quotas)));height=24+45*max(1,(len(quotas)+columns-1)//columns)
            surface(p,QRectF(0,y,self.width(),height-4),self.view.owner,'lavender')
            name_width = min(175, self.width() * .62)
            text(p,QRectF(10,y+3,name_width,18),row['name'],c['ink'],11,True)
            status=row.get('status','') if row.get('stale') else row.get('plan') or row.get('status','')
            text(p,QRectF(14+name_width,y+3,self.width()-24-name_width,18),status,c['muted'],9,False,Qt.AlignRight)
            if not quotas:text(p,QRectF(10,y+25,self.width()-20,26),row.get('status') or '等待额度读数',c['muted'],10)
            width=(self.width()-20-10*(columns-1))/columns
            for i,q in enumerate(quotas):
                x=10+(i%columns)*(width+10);top=y+23+(i//columns)*45
                money = amount_text(q)
                if money is not None:
                    text(p,QRectF(x,top,width,16),amount_label(q),c['muted'],9)
                    text(p,QRectF(x,top+15,width,23),money,c['ink'],15,True)
                    continue
                remaining = remaining_percent(used_percent(q))
                ink = quota_color(remaining, c['light'])
                text(p,QRectF(x,top,width-53,16),q['label'].replace(' · 已用',''),c['muted'],9)
                text(p,QRectF(x,top+18,width-53,15),reset_text(q.get('reset')) or '重置时间未提供',c['muted'],8)
                circle=QRectF(x+width-36,top-1,31,31);p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(c['hover']),3));p.drawEllipse(circle)
                if remaining is not None:
                    p.setPen(QPen(QColor(ink),3,Qt.SolidLine,Qt.RoundCap));p.drawArc(circle,90*16,-round(remaining*3.6*16))
                    text(p,circle,f'{remaining:.0f}%',ink,9,True,Qt.AlignCenter)
                else:text(p,circle,'—',ink,10,False,Qt.AlignCenter)
                text(p,QRectF(circle.x()-3,top+30,37,12),'剩余',c['muted'],8,False,Qt.AlignCenter)
            y+=height


def number(value):return '—' if value is None else token_text(value)


def surface(p,rect,owner,tone):
    colors=owner.colors
    if hasattr(owner,'background'):
        paint_capsule_card(p,rect,colors,tone,owner.background)
        return
    color=QColor(colors['field']);color.setAlpha(170 if colors['light'] else 155)
    p.setBrush(color);p.setPen(Qt.NoPen);p.drawRoundedRect(rect,9,9)


class UsageSummary(QWidget):
    def __init__(self,view):super().__init__();self.view=view;self.setFixedHeight(64)
    def resizeEvent(self,event):self.setFixedHeight(128 if self.width()<360 else 64);super().resizeEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.view.owner.colors
        if not c:return
        surface(p,QRectF(self.rect()),self.view.owner,'sky');data=self.view.data;total=data['total'];columns=2 if self.width()<360 else 4;w=self.width()/columns
        fields=[('Token',number(total['tokens']),f"输入 {number(total['input'])} · 输出 {number(total['output'])}"),
                ('调用记录',number(total['records']),'按来源计量记录'),
                ('费用',cost_text(total),cost_note(total)),
                ('缓存命中',f"{total['cacheRate']:.0f}%" if total['cacheRate'] is not None else '—','占输入 Token')]
        cost_ink=('#0a6f61' if c['light'] else '#70e2cc') if hasattr(self.view.owner,'background') else COLORS[0]
        for i,(label,value,note) in enumerate(fields):
            x=(i%columns)*w+10;y=(i//columns)*64
            text(p,QRectF(x,y+6,w-15,16),label,c['muted'],9)
            text(p,QRectF(x,y+23,w-15,24),value if data['available'] else '—',cost_ink if i==2 else c['ink'],16,True)
            text(p,QRectF(x,y+46,w-15,15),note,c['muted'],9)


class UsageCharts(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view;self.setFixedHeight(128);self.bars=[];self.hover=-1;self.setMouseTracking(True)
    def resizeEvent(self,event):self.setFixedHeight(262 if self.width()<360 else 128);super().resizeEvent(event)
    def mouseMoveEvent(self,event):
        found=next((i for i,(rect,_,_) in enumerate(self.bars) if rect.adjusted(-2,-100,2,25).contains(event.pos())),-1)
        if found!=self.hover:self.hover=found;self.update()
    def leaveEvent(self,event):self.hover=-1;self.update();super().leaveEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.view.owner.colors
        if not c:return
        surface(p,QRectF(self.rect()),self.view.owner,'mint');data=self.view.data;total=data['total'];metric=self.view.metric
        text(p,QRectF(12,7,140,18),'费用分布',c['ink'],10,True)
        narrow=self.width()<360;shift=(self.width()-126)/2 if narrow else 0;offset=134 if narrow else 0
        ring=QRectF(28+shift,31,70,70);p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(c['hover']),9));p.drawEllipse(ring)
        groups=[(i,g) for i,g in enumerate(data['groups']) if (g['summary']['cost'] or 0)>0]
        cost=sum(g['summary']['cost'] for _,g in groups);angle=90*16
        for i,group in groups:
            span=round(group['summary']['cost']/cost*360*16);p.setPen(QPen(QColor(COLORS[i%len(COLORS)]),9,Qt.SolidLine,Qt.FlatCap));p.drawArc(ring,angle,-max(0,span-24));angle-=span
        value=cost_text(total,currency=False) if data['available'] else '—'
        text(p,QRectF(30+shift,49,66,23),value,c['ink'],12 if len(value)<8 else 10,True,Qt.AlignCenter)
        if value not in ('未定价','—'):
            text(p,QRectF(30+shift,71,66,16),'USD',c['muted'],8,False,Qt.AlignCenter)
        label=groups[0][1]['name'] if len(groups)==1 else f'{len(groups)} 个来源' if groups else '暂无费用记录'
        text(p,QRectF(10+shift,108,110,17),label,c['muted'],9,False,Qt.AlignCenter)
        x=44. if narrow else 164.;w=max(40,self.width()-x-16);plot=QRectF(x,34+offset,w,62);series=data['series'];max_value=max((s.get(metric) or 0 for _,s in series),default=0)
        ceiling=(max_value or 1) if metric=='cost' else max(1,max_value)
        grid=QColor(c['muted']);grid.setAlpha(45)
        title_x=12 if narrow else 132
        text(p,QRectF(title_x,7+offset,self.width()-title_x-12,18),{'cost':'费用趋势 · USD','tokens':'Token 趋势','records':'调用记录趋势'}[metric],c['ink'],10,True)
        for ratio in (0,.5,1):
            y=plot.bottom()-plot.height()*ratio;p.setPen(QPen(grid,.7,Qt.DotLine));p.drawLine(QPointF(plot.x(),y),QPointF(plot.right(),y))
            value=ceiling*ratio
            label=cost_text({'cost':value},currency=False).rstrip('0').rstrip('.') if metric=='cost' and value else token_text(round(value))
            text(p,QRectF(x-45,y-7,39,15),label,c['muted'],8,False,Qt.AlignRight)
        self.bars=[]
        if series and data['available']:
            step=w/len(series);bar_width=min(12,max(2,step-3));p.setPen(Qt.NoPen)
            for i,(day,summary) in enumerate(series):
                v=summary.get(metric);height=0 if v is None else plot.height()*v/ceiling
                box=QRectF(x+i*step+(step-bar_width)/2,plot.bottom()-max(1,height),bar_width,max(1,height));self.bars.append((box,day,v))
                p.setBrush(QColor(COLORS[1] if i==self.hover else COLORS[0]));p.drawRoundedRect(box,1,1)
            for index,align in ((0,Qt.AlignLeft),(len(series)-1,Qt.AlignRight)):
                date=series[index][0];label=date[11:]+':00' if len(date)>10 else date[5:]
                text(p,QRectF(x,99+offset,w,14),label,c['muted'],8,False,align)
        else:text(p,plot,'暂无用量记录',c['muted'],11,False,Qt.AlignCenter)
        if 0<=self.hover<len(self.bars):
            _,day,value=self.bars[self.hover]
            amount=cost_text(series[self.hover][1],currency=False) if metric=='cost' else number(value)
            label=day.replace('T',' ')+(':00' if 'T' in day else '')+'  '+amount
            text(p,QRectF(x,113+offset,w,14),label,c['ink'],9,False,Qt.AlignRight)


class UsageProviders(QWidget):
    def __init__(self,view):super().__init__();self.view=view;self.setCursor(Qt.PointingHandCursor)
    def refresh(self):self.setFixedHeight(max(34,len(self.view.data['groups'])*42));self.update()
    def mouseReleaseEvent(self,event):
        groups=self.view.data['groups'];index=event.y()//42
        if event.button()==Qt.LeftButton and 0<=index<len(groups):self.view.show_details(groups[index]['id'])
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.view.owner.colors
        if not c:return
        groups=self.view.data['groups'];total=sum(g['summary']['cost'] or 0 for g in groups)
        for i,g in enumerate(groups):
            y=i*42;s=g['summary'];p.setPen(Qt.NoPen);p.setBrush(QColor(COLORS[i%len(COLORS)]));p.drawRoundedRect(QRectF(8,y+8,6,6),2,2)
            cost_x=max(90,self.width()*.52)
            text(p,QRectF(22,y,cost_x-27,22),g['name'],c['ink'],11,True)
            text(p,QRectF(cost_x,y,self.width()-cost_x-10,22),cost_text(s) if g['available'] else '—',c['ink'],11,True,Qt.AlignRight)
            meta=f"{number(s['records'])} 条记录 · {number(s['tokens'])} Token" if g['available'] else '来源未提供用量记录'
            if g['available'] and (note:=cost_note(s)):meta+=' · '+note
            text(p,QRectF(22,y+21,self.width()-32,16),meta,c['muted'],9)
            if total and s['cost']:
                p.setPen(Qt.NoPen);p.setBrush(QColor(COLORS[i%len(COLORS)]));p.drawRoundedRect(QRectF(22,y+39,(self.width()-32)*s['cost']/total,2),1,1)


class StatisticsView(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.period='today';self.metric='cost';self.signature=None;self.data=aggregate([])
        lay=QVBoxLayout(self);lay.setContentsMargins(4,0,4,0);lay.setSpacing(5)
        self.filter_box=QBoxLayout(QBoxLayout.LeftToRight);lay.addLayout(self.filter_box)
        filters=QHBoxLayout();filters.setContentsMargins(0,0,0,0);filters.setSpacing(1);self.ranges={}
        ranges=QWidget();ranges.setLayout(filters);self.filter_box.addWidget(ranges)
        for key,label in [('today','今天'),('yesterday','昨天'),('week','7 天'),('month','30 天'),('all','全部')]:
            b=QToolButton();b.setText(label);b.setCheckable(True);b.clicked.connect(lambda checked=False,key=key:self.set_period(key));self.ranges[key]=b;filters.addWidget(b)
        filters.addStretch();tools=QHBoxLayout();tools.setContentsMargins(0,0,0,0);tool_row=QWidget();tool_row.setLayout(tools);self.filter_box.addWidget(tool_row)
        self.provider=ModernComboBox();self.provider.setMinimumWidth(70);self.provider.setMaximumWidth(124);self.provider.setFixedHeight(24);self.provider.setStyleSheet('QComboBox{min-height:0;padding:1px 28px 1px 5px;font-size:10px;border:0}')
        self.provider.setProperty('glassField',True)
        self.provider.addItem('全部工具','');self.provider.currentIndexChanged.connect(self.recalculate);tools.addWidget(self.provider);tools.addStretch()
        refresh=QToolButton();refresh.setText('刷新');refresh.clicked.connect(self.refresh_request);tools.addWidget(refresh)
        scroll=self.scroll=CapsuleScrollArea()
        body=QWidget();scroll.setWidget(body);stack=QVBoxLayout(body);stack.setContentsMargins(0,0,3,0);stack.setSpacing(6);lay.addWidget(scroll,1)
        self.quotas=QuotaOverview(self);stack.addWidget(self.quotas)
        self.summary=UsageSummary(self);stack.addWidget(self.summary)
        modes=QHBoxLayout();self.trend_title=QLabel('用量趋势');modes.addWidget(self.trend_title,1);self.modes={}
        for key,label in [('tokens','Token'),('cost','费用'),('records','记录')]:
            b=QToolButton();b.setText(label);b.setCheckable(True);b.clicked.connect(lambda checked=False,key=key:self.set_metric(key));modes.addWidget(b);self.modes[key]=b
        detail=self.detail_button=QToolButton();detail.setText('模型明细');detail.clicked.connect(self.show_details);modes.addWidget(detail);stack.addLayout(modes)
        self.charts=UsageCharts(self);stack.addWidget(self.charts);self.providers=UsageProviders(self);stack.addWidget(self.providers)
        stack.addStretch(1)
        self.note=QLabel();self.note.setWordWrap(True);self.note.setObjectName('Subtle');self.note.hide();lay.addWidget(self.note)
        footer=QHBoxLayout();self.notes_button=QToolButton();self.notes_button.setText('备注');self.notes_button.setCheckable(True);self.notes_button.toggled.connect(self.note.setVisible)
        footer.addWidget(self.notes_button);footer.addStretch();lay.addLayout(footer);self.recalculate()
    def resizeEvent(self,event):
        small=self.width()<420
        self.filter_box.setDirection(QBoxLayout.TopToBottom if small else QBoxLayout.LeftToRight)
        self.trend_title.setVisible(not small);self.detail_button.setText('明细' if small else '模型明细')
        super().resizeEvent(event)
    def set_period(self,key):
        self.period=key
        if key=='all' and self.owner.service.deck:self.owner.service.deck.request_history()
        self.recalculate()
    def set_metric(self,key):self.metric=key;self.recalculate()
    def refresh_request(self):
        if self.owner.service.deck:self.owner.service.deck.refresh()
    def show_details(self,provider=None):
        self.owner.ai_view.show_details(provider if isinstance(provider,str) else self.provider.currentData() or '',self.period)
    def refresh(self):
        bridge=self.owner.service.deck;rows=bridge.providers if bridge else [];signature=tuple((r['id'],r['name']) for r in rows)
        if signature!=self.signature:
            old=self.provider.currentData();self.provider.blockSignals(True);self.provider.clear();self.provider.addItem('全部工具','')
            for row in rows:self.provider.addItem(row['name'],row['id'])
            self.provider.setCurrentIndex(max(0,self.provider.findData(old)));self.provider.blockSignals(False);self.signature=signature
        self.provider.setVisible(len(rows)>1)
        self.recalculate()
    def recalculate(self):
        from datetime import date
        bridge=self.owner.service.deck;rows=bridge.providers if bridge else [];key=(id(rows),self.period,self.provider.currentData() or '',date.today())
        if key!=getattr(self,'data_key',None):self.data=aggregate(rows,self.period,key[2]);self.data_key=key
        selected=self.provider.currentData() or '';self.quotas.refresh([r for r in rows if not selected or r['id']==selected])
        for key,b in self.ranges.items():b.setChecked(key==self.period)
        for key,b in self.modes.items():b.setChecked(key==self.metric)
        self.summary.update();self.charts.update();self.providers.refresh()
        note=(bridge.ai_status+'。 ' if bridge else '')+'费用为记录金额或估算，未定价部分单列；调用记录不等同于 HTTP 请求数。'
        if self.period=='all':note+=' 全部为来源可读历史，线上明细可能仅有最近 30 天。'
        if not self.data['complete']:note+=' 部分来源仍在补全。'
        self.note.setText(note)
