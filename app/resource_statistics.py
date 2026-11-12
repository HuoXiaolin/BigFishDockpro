"""Compact, theme-aware cost distribution and usage history from real aggregates."""
from PyQt5.QtCore import Qt,QRect,QRectF,QPointF
from PyQt5.QtGui import QColor,QFont,QFontMetrics,QPainter,QPen
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QBoxLayout,QToolButton,QLabel,QSizePolicy
from ui_style import ModernComboBox
from resource_compact import text
from resource_options import content_columns
from resource_pages import CapsuleScrollArea,token_text,cost_text,cost_note,reset_text
from resource_usage import aggregate
from resource_quota import amount_label, amount_text, provider_plan_name, quota_color, remaining_percent, used_percent
import reset_credits
from card_design import paint_capsule_card

COLORS=('#13a58b','#428fe2','#b28a49','#897fb6','#d57480','#59a9b5','#8a9d71')


class ResetCreditButton(QToolButton):
    def __init__(self, overview):
        super().__init__(overview)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(lambda: reset_credits.show_details(overview, self.provider))

    def refresh(self, provider, colors):
        self.provider = provider
        self.setText('重置卡 ' + reset_credits.badge_text(provider))
        summary = reset_credits.summary(provider)
        self.setAccessibleName(f"{provider['name']} {summary}，查看重置卡详情")
        self.setToolTip(summary + '\n' + (reset_credits.expiry_note(provider) or '查看重置卡详情'))
        if colors:
            self.setIcon(reset_credits.card_icon(colors['muted']))
        self.show()

    def row_height(self, width):
        font = self.font()
        font.setPixelSize(11)
        fits = QFontMetrics(font).horizontalAdvance(self.text()) <= width - 45
        return 25 if fits else 39

    def paintEvent(self, event):
        colors = self.parentWidget().view.owner.colors
        if not colors:
            return
        p = QPainter(self)
        p.setFont(self.font())
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        if self.underMouse() or self.isDown() or self.hasFocus():
            p.setBrush(QColor(colors['hover']))
            p.setPen(QPen(QColor(colors['muted']), 1) if self.hasFocus() else Qt.NoPen)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 5, 5)
        center = 11 if self.height() > 25 else self.height() // 2
        width = max(0, self.width() - 45)
        if self.height() > 25:
            label, separator, expiry = self.text().partition(' · ')
            if not separator:
                label, _, expiry = self.text().partition(' ')
            self.icon().paint(p, QRect(4, 3, 16, 16))
            text(p, QRectF(25, 1, width, 18), label, colors['ink'], 11)
            text(p, QRectF(25, 19, self.width() - 30, 17), expiry, colors['muted'], 11)
        else:
            self.icon().paint(p, QRect(4, center - 8, 16, 16))
            text(p, QRectF(25, 0, width, self.height()), self.text(), colors['ink'], 11)
        x = self.width() - 12
        p.setPen(QPen(QColor(colors['muted']), 1.35, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x - 2, center - 3), QPointF(x + 1, center))
        p.drawLine(QPointF(x + 1, center), QPointF(x - 2, center + 3))


class QuotaOverview(QWidget):
    """The same quota cards fit the capsule, desktop card and tray popup."""

    inset = 12
    header_height = 32
    metric_gap = 16
    card_gap = 6

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.rows = []
        self.cards = []
        self.reset_buttons = []

    def refresh(self, rows):
        self.rows = rows
        credits = [row for row in rows if reset_credits.applicable(row)]
        while len(self.reset_buttons) > len(credits):
            button = self.reset_buttons.pop()
            button.hide()
            button.deleteLater()
        while len(self.reset_buttons) < len(credits):
            self.reset_buttons.append(ResetCreditButton(self))
        for button, row in zip(self.reset_buttons, credits):
            button.refresh(row, self.view.owner.colors)
        self.fit_rows()
        self.update()

    def fit_rows(self):
        self.cards = []
        y = 0
        buttons = iter(self.reset_buttons)
        columns = content_columns(self.view.owner.width())
        for row in self.rows:
            quotas = row.get('quotas', [])
            card_columns = min(columns, max(1, len(quotas)))
            cell_width = (self.width() - 2 * self.inset - self.metric_gap * (card_columns - 1)) / card_columns
            metric_height = 64 if cell_width < 168 else 48
            metric_rows = (len(quotas) + card_columns - 1) // card_columns
            body_height = metric_rows * metric_height if quotas else 28
            footer_y = y + self.header_height + body_height
            button = next(buttons) if reset_credits.applicable(row) else None
            height = self.header_height + body_height + 2
            if button:
                button_width = max(0, self.width() - 2 * self.inset + 8)
                button_height = button.row_height(button_width)
                button.setGeometry(self.inset - 4, footer_y + 2, button_width, button_height)
                height += button_height + 3
            self.cards.append((row, QRectF(0, y, self.width(), height), card_columns, metric_height, footer_y if button else None))
            y += height + self.card_gap
        self.setFixedHeight(y - self.card_gap if self.cards else 38)

    def resizeEvent(self, event):
        self.fit_rows()
        super().resizeEvent(event)

    def paintEvent(self, event):
        colors = self.view.owner.colors
        if not colors:
            return
        p = QPainter(self)
        p.setFont(self.font())
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        if not self.cards:
            bridge = self.view.owner.service.deck
            text(p, QRectF(10, 4, self.width() - 20, 30), bridge.ai_status if bridge else '等待 AI 额度', colors['muted'])
            return
        for row, rect, columns, metric_height, footer_y in self.cards:
            self.paint_card(p, colors, row, rect, columns, metric_height, footer_y)

    def paint_card(self, p, colors, row, rect, columns, metric_height, footer_y):
        surface(p, rect, self.view.owner, 'sky', base=colors['field'])
        left = self.inset
        right = rect.width() - left
        width = max(0, right - left)
        quotas = row.get('quotas', [])
        plan = provider_plan_name(row)
        if row.get('stale'):
            plan = f'{plan} · 上次读数' if plan else '上次读数'
        elif not plan and quotas:
            plan = row.get('status') or ''
        title_width = width * .55 if plan else width
        text(p, QRectF(left, rect.top() + 6, title_width, 21), row['name'], colors['ink'], 14, True)
        if plan:
            text(p, QRectF(left + title_width, rect.top() + 6, width - title_width, 21),
                 plan, colors['muted'], 11, True, Qt.AlignRight)

        top = rect.top() + self.header_height
        if not quotas:
            status = row.get('status') or '等待读取额度'
            text(p, QRectF(left, top, width, 22), '暂无额度数据' if status == '已连接' else status, colors['muted'])
        gap = self.metric_gap
        cell_width = (width - gap * (columns - 1)) / columns
        for index, metric in enumerate(quotas):
            x = left + (index % columns) * (cell_width + gap)
            y = top + (index // columns) * metric_height
            self.paint_metric(p, colors, metric, x, y, cell_width, metric_height == 64)

        if footer_y is not None:
            line = QColor(colors['ink'])
            line.setAlpha(28)
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(left, footer_y), QPointF(right, footer_y))

    @staticmethod
    def paint_metric(p, colors, metric, x, y, width, narrow):
        money = amount_text(metric)
        value_y = y + 16 if narrow else y
        if money is not None:
            label_width = width if narrow else width * .47
            label_height = 16 if narrow else 28
            text(p, QRectF(x, y, label_width, label_height), amount_label(metric), colors['muted'], 12)
            value_left = x if narrow else x + label_width
            text(p, QRectF(value_left, value_y, x + width - value_left, 28),
                 money, colors['ink'], 18, True, Qt.AlignRight)
            if reset := reset_text(metric.get('reset')):
                text(p, QRectF(x, value_y + 31, width, 16), reset, colors['muted'])
            return

        remaining = remaining_percent(used_percent(metric))
        ink = quota_color(remaining, colors['light'])
        label = metric['label'].replace(' · 已用', '')
        value = '—' if remaining is None else f'{remaining:.0f}%'
        value_font = QFont(p.font())
        value_font.setPixelSize(20)
        value_font.setWeight(QFont.DemiBold)
        value_width = QFontMetrics(value_font).horizontalAdvance(value) + 2
        value_x = x + width - value_width
        label_width = width if narrow else max(0, width - value_width - 40)
        text(p, QRectF(x, y, label_width, 16 if narrow else 23), label, colors['ink'], 12, True)
        text(p, QRectF(value_x - 32, value_y, 26, 23), '剩余', colors['muted'])
        text(p, QRectF(value_x, value_y - 2, value_width, 25), value, ink, 20, True, Qt.AlignRight)

        track = QRectF(x, value_y + 25, width, 4)
        track_color = QColor(colors['ink'])
        track_color.setAlpha(30 if colors['light'] else 45)
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(track, 2, 2)
        if remaining:
            track.setWidth(width * remaining / 100)
            p.setBrush(QColor(ink))
            p.drawRoundedRect(track, 2, 2)
        text(p, QRectF(x, value_y + 31, width, 16),
             reset_text(metric.get('reset')) or '未提供恢复时间', colors['muted'])


def number(value):return '—' if value is None else token_text(value)


def surface(p,rect,owner,tone,*,base=None):
    colors=owner.colors
    if hasattr(owner,'background'):
        paint_capsule_card(p,rect,colors,tone,owner.background,base=base)
        return
    color=QColor(colors['field']);color.setAlpha(170 if colors['light'] else 155)
    p.setBrush(color);p.setPen(Qt.NoPen);p.drawRoundedRect(rect,9,9)


class UsageSummary(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view
        self.fit_rows()

    def fit_rows(self):
        self.columns=content_columns(self.view.owner.width())
        self.row_height=42 if self.columns==1 else 64
        self.setFixedHeight(4*self.row_height//self.columns)

    def resizeEvent(self,event):
        self.fit_rows()
        super().resizeEvent(event)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.view.owner.colors
        if not c:return
        surface(p,QRectF(self.rect()),self.view.owner,'sky');data=self.view.data;total=data['total'];w=self.width()/self.columns
        fields=[('Token',number(total['tokens']),f"输入 {number(total['input'])} · 输出 {number(total['output'])}"),
                ('调用记录',number(total['records']),'按来源计量记录'),
                ('费用',cost_text(total),cost_note(total)),
                ('缓存命中',f"{total['cacheRate']:.0f}%" if total['cacheRate'] is not None else '—','占输入 Token')]
        cost_ink=('#0a6f61' if c['light'] else '#70e2cc') if hasattr(self.view.owner,'background') else COLORS[0]
        for i,(label,value,note) in enumerate(fields):
            x=(i%self.columns)*w+10;y=(i//self.columns)*self.row_height
            ink=cost_ink if i==2 else c['ink']
            value=value if data['available'] else '—'
            if self.columns==1:
                text(p,QRectF(x,y+4,w/2-12,18),label,c['muted'],10)
                text(p,QRectF(w/2,y+3,w/2-10,22),value,ink,16,True,Qt.AlignRight)
                text(p,QRectF(x,y+23,w-20,15),note,c['muted'],9)
                continue
            text(p,QRectF(x,y+6,w-15,16),label,c['muted'],9)
            text(p,QRectF(x,y+23,w-15,24),value,ink,16,True)
            text(p,QRectF(x,y+46,w-15,15),note,c['muted'],9)


class UsageCharts(QWidget):
    def __init__(self,view):
        super().__init__();self.view=view;self.bars=[];self.hover=-1;self.setMouseTracking(True)
        self.fit_charts()

    def fit_charts(self):
        self.columns=content_columns(self.view.owner.width())
        self.setFixedHeight(262 if self.columns==1 else 128)

    def resizeEvent(self,event):
        self.fit_charts()
        super().resizeEvent(event)
    def mouseMoveEvent(self,event):
        found=next((i for i,(rect,_,_) in enumerate(self.bars) if rect.adjusted(-2,-100,2,25).contains(event.pos())),-1)
        if found!=self.hover:self.hover=found;self.update()
    def leaveEvent(self,event):self.hover=-1;self.update();super().leaveEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.view.owner.colors
        if not c:return
        surface(p,QRectF(self.rect()),self.view.owner,'mint');data=self.view.data;total=data['total'];metric=self.view.metric
        text(p,QRectF(12,7,140,18),'费用分布',c['ink'],10,True)
        narrow=self.columns==1;shift=(self.width()-126)/2 if narrow else 0;offset=134 if narrow else 0
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
        filter_bar = QWidget()
        filter_bar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.filter_box = QBoxLayout(QBoxLayout.LeftToRight, filter_bar)
        self.filter_box.setContentsMargins(0, 0, 0, 0)
        self.filter_box.setSpacing(4)
        lay.addWidget(filter_bar)
        self.range_tabs = QWidget()
        filters = QHBoxLayout(self.range_tabs)
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(1)
        self.ranges = {}
        field_style = 'QComboBox{min-height:0;padding:1px 28px 1px 5px;font-size:10px;border:0}'
        self.period_selector = ModernComboBox()
        self.period_selector.setAccessibleName('用量时间范围')
        self.period_selector.setFixedSize(76, 24)
        self.period_selector.setStyleSheet(field_style)
        self.period_selector.setProperty('glassField', True)
        for key,label in [('today','今天'),('yesterday','昨天'),('week','7 天'),('month','30 天'),('all','全部')]:
            b=QToolButton();b.setText(label);b.setCheckable(True);b.clicked.connect(lambda checked=False,key=key:self.set_period(key));self.ranges[key]=b;filters.addWidget(b)
            self.period_selector.addItem(label, key)
        self.period_selector.currentIndexChanged.connect(lambda: self.set_period(self.period_selector.currentData()))
        filters.addStretch()
        self.filter_box.addWidget(self.range_tabs, 1)
        self.filter_box.addWidget(self.period_selector)
        self.filter_box.addStretch(1)
        tool_row = QWidget()
        tools = QHBoxLayout(tool_row)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(4)
        tools.addStretch()
        self.filter_box.addWidget(tool_row)
        self.provider=ModernComboBox();self.provider.setMinimumWidth(70);self.provider.setMaximumWidth(124);self.provider.setFixedHeight(24);self.provider.setStyleSheet(field_style)
        self.provider.setProperty('glassField',True)
        self.provider.setAccessibleName('额度服务商')
        self.provider.addItem('全部工具','');self.provider.currentIndexChanged.connect(self.recalculate);tools.addWidget(self.provider)
        refresh=QToolButton();refresh.setText('刷新');refresh.clicked.connect(self.refresh_request);tools.addWidget(refresh)
        scroll=self.scroll=CapsuleScrollArea()
        body=QWidget();scroll.setWidget(body);stack=QVBoxLayout(body);stack.setContentsMargins(0,0,3,0);stack.setSpacing(6);lay.addWidget(scroll,1)
        self.quotas=QuotaOverview(self);stack.addWidget(self.quotas)
        self.summary=UsageSummary(self);stack.addWidget(self.summary)
        self.mode_box = QBoxLayout(QBoxLayout.LeftToRight)
        self.mode_box.setSpacing(3)
        self.trend_title = QLabel('用量趋势')
        self.mode_box.addWidget(self.trend_title, 1)
        mode_row = QWidget()
        modes = QHBoxLayout(mode_row)
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(3)
        self.modes = {}
        for key,label in [('tokens','Token'),('cost','费用'),('records','记录')]:
            b=QToolButton();b.setText(label);b.setCheckable(True);b.clicked.connect(lambda checked=False,key=key:self.set_metric(key));modes.addWidget(b);self.modes[key]=b
            b.setStyleSheet('padding:3px 5px;')
        self.mode_box.addWidget(mode_row)
        detail=self.detail_button=QToolButton();detail.setText('模型明细');detail.clicked.connect(self.show_details)
        self.mode_box.addWidget(detail, 0, Qt.AlignRight)
        stack.addLayout(self.mode_box)
        self.charts=UsageCharts(self);stack.addWidget(self.charts);self.providers=UsageProviders(self);stack.addWidget(self.providers)
        stack.addStretch(1)
        self.note=QLabel();self.note.setWordWrap(True);self.note.setObjectName('Subtle');self.note.hide();lay.addWidget(self.note)
        footer=QHBoxLayout();self.notes_button=QToolButton();self.notes_button.setText('备注');self.notes_button.setCheckable(True);self.notes_button.toggled.connect(self.note.setVisible)
        footer.addWidget(self.notes_button);footer.addStretch();lay.addLayout(footer);self.recalculate()
    def layout_controls(self):
        small = self.width() < 420
        narrow = self.width() < 220
        self.range_tabs.setVisible(not small)
        self.period_selector.setVisible(small)
        stacked_filters = narrow and not self.provider.isHidden()
        self.filter_box.setDirection(QBoxLayout.TopToBottom if stacked_filters else QBoxLayout.LeftToRight)
        self.mode_box.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        self.trend_title.setVisible(not small)
        self.detail_button.setText('明细' if small else '模型明细')

    def resizeEvent(self,event):
        self.layout_controls()
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
        self.layout_controls()
        self.recalculate()
    def recalculate(self):
        from datetime import date
        bridge=self.owner.service.deck;rows=bridge.providers if bridge else [];key=(id(rows),self.period,self.provider.currentData() or '',date.today())
        if key!=getattr(self,'data_key',None):self.data=aggregate(rows,self.period,key[2]);self.data_key=key
        selected=self.provider.currentData() or '';self.quotas.refresh([r for r in rows if not selected or r['id']==selected])
        for key,b in self.ranges.items():b.setChecked(key==self.period)
        self.period_selector.blockSignals(True)
        self.period_selector.setCurrentIndex(self.period_selector.findData(self.period))
        self.period_selector.blockSignals(False)
        for key,b in self.modes.items():b.setChecked(key==self.metric)
        self.summary.update();self.charts.update();self.providers.refresh()
        note=(bridge.ai_status+'。 ' if bridge else '')+'费用为记录金额或估算，未定价部分单列；调用记录不等同于 HTTP 请求数。'
        if self.period=='all':note+=' 全部为来源可读历史，线上明细可能仅有最近 30 天。'
        if not self.data['complete']:note+=' 部分来源仍在补全。'
        self.note.setText(note)
