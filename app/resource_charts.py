"""Native-pixel resource graphs. All values come from the capsule's enabled samplers."""
import math
import time

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget, QSizePolicy

from flash_view import blend
from card_design import paint_capsule_card
from resource_options import TINTS
from resource_status import metric_ink,threshold


def rate(value):
    if value < 1024:
        return f'{value:.0f} B/s'
    if value < 2**20:
        return f'{value/1024:.1f} KB/s'
    return f'{value/2**20:.1f} MB/s'


def metric_colors(service):
    cfg = service.cfg
    if cfg['resource_palette'] == 'custom':
        return dict(TINTS, **cfg['resource_tints'])
    if cfg['resource_palette'] == 'vivid':
        return dict(cpu='#5b8def', memory='#41bf76', network='#20b9c4', gpu='#ff6e89')
    accent = cfg['panel_color'] or cfg.get('theme_color') or TINTS['cpu']
    return {key:blend(rgb,accent,.12).name() for key,rgb in TINTS.items()}


def reading_ink(service,key,colors,fallback):
    ink=metric_ink(service,key,colors['light'],fallback)
    return QColor(ink).darker(121) if colors['light'] and ink!=fallback else ink


def text(p, area, label, ink, size=11, weight=QFont.Normal, align=Qt.AlignLeft):
    font = QFont(p.font())
    font.setPixelSize(size)
    font.setWeight(weight)
    p.setFont(font)
    p.setPen(QColor(ink))
    p.drawText(area, Qt.AlignVCenter | align, label)


def fill(p, area, ink, radius):
    if area.width() <= 0 or area.height() <= 0:
        return
    p.setPen(Qt.NoPen)
    p.setBrush(ink)
    p.drawRoundedRect(area,radius,radius)


def series(history, key, index=None):
    result = []
    for row in history:
        value = row.get(key)
        if value is not None:
            result.append((row['time'],value if index is None else value[index]))
    return result


def trend(p, box, values, now, ink, ceiling):
    if box.width() < 7 or box.height() < 3:
        return
    points = []
    for stamp,value in values:
        age = now-stamp
        if age > 60:
            continue
        x = box.right()-max(0,age)*box.width()/60
        y = box.bottom()-min(1,max(0,value)/max(1,ceiling))*box.height()
        points.append(QPointF(x,y))
    if not points:
        return
    ink = QColor(ink)
    if box.height() >= 24:
        guide = QColor(ink)
        guide.setAlpha(45)
        p.setPen(QPen(guide,1))
        for y in (box.center().y(),box.bottom()):
            p.drawLine(QPointF(box.left(),y),QPointF(box.right(),y))
    path = QPainterPath(points[0])
    for first,last in zip(points,points[1:]):
        middle = (first.x()+last.x())/2
        path.cubicTo(middle,first.y(),middle,last.y(),last.x(),last.y())
    if len(points)>1:
        area = QPainterPath(path)
        area.lineTo(points[-1].x(),box.bottom())
        area.lineTo(points[0].x(),box.bottom())
        area.closeSubpath()
        wash = QColor(ink)
        wash.setAlpha(32)
        p.fillPath(area,wash)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(ink,1.6,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(ink)
    p.drawEllipse(points[-1],2,2)


def sync_card_controls(widget,colors):
    ink,muted=colors['ink'],colors['muted']
    if widget.property('cardInk')==ink:return
    widget.setProperty('cardInk',ink)
    # The application stylesheet gives QLabel its own color. Scope the override
    # to these cards so an independent capsule theme stays readable.
    widget.setStyleSheet(f'''
        QLabel{{color:{ink};}}
        QLabel#Subtle,QLabel#RankMemory{{color:{muted};}}
        QToolButton{{color:{muted};}}
        QToolButton:hover,QToolButton:checked{{color:{ink};}}
    ''')


class DashboardCard(QWidget):
    def __init__(self,window,tone,parent=None):
        super().__init__(parent)
        self.owner=window
        self.tone=tone

    def paint_surface(self,p):
        paint_capsule_card(p,QRectF(self.rect()),self.owner.colors,self.tone,self.owner.background)

    def paintEvent(self,event):
        if not self.owner.colors:return
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.paint_surface(p)


class MetricDisplay(DashboardCard):
    inset = 9
    load_height = 71

    def __init__(self, window):
        super().__init__(window,'sky')
        self.rows = {}
        self.basic = ()
        self.extras = ()
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

    def refresh(self, rows):
        self.rows = {key:(label,value,tip) for key,label,value,tip in rows}
        self.basic = tuple(k for k in ('cpu','gpu','memory','network') if k in self.rows)
        self.extras = tuple(k for k in self.rows if k not in self.basic)
        upper = self.load_height if 'cpu' in self.rows or 'gpu' in self.rows else 0
        height = 2*self.inset + upper + 25*('memory' in self.rows) + 25*('network' in self.rows) + 25*math.ceil(len(self.extras)/2)
        self.setFixedHeight(max(1,height))
        self.setVisible(bool(rows))
        tips = [label+' · '+tip for _,label,_,tip in rows if tip]
        if 'cpu' in self.rows:
            tips.insert(0,'柱形按逻辑处理器顺序排列。核心较多时，相邻核心合并取平均值。')
        self.setToolTip('')
        self.setAccessibleName('，'.join(label+' '+value for _,label,value,_ in rows))
        self.update()

    def processors(self,p,area,values,history,now,inks,colors,track):
        box = QRectF(area)
        text(p,QRectF(box.x(),box.y(),30,21),'CPU',colors['ink'],11,QFont.DemiBold)
        text(p,QRectF(box.x()+29,box.y(),52,21),self.rows['cpu'][1],inks['cpu'],15,QFont.Bold)
        readings = series(history,'cpu')
        plot = box.adjusted(0,25,0,-5)
        if not values:
            trend(p,plot.adjusted(2,0,-2,0),readings,now,inks['cpu'],100)
            return
        trend(p,QRectF(box.x()+77,box.y()+4,box.width()-80,13),readings,now,inks['cpu'],100)
        count = min(len(values),max(1,min(32,int(plot.width()//6))))
        step = plot.width()/count
        gap = min(3,step*.33)
        width = step-gap
        p.setPen(QPen(track,1))
        p.drawLine(QPointF(plot.left(),plot.center().y()),QPointF(plot.right(),plot.center().y()))
        p.drawLine(QPointF(plot.left(),plot.bottom()),QPointF(plot.right(),plot.bottom()))
        use_threshold = self.owner.service.cfg['resource_threshold']
        for i in range(count):
            first,last = i*len(values)//count,(i+1)*len(values)//count
            level = sum(values[first:last])/(last-first)
            if level <= 0:
                continue
            x = plot.x()+i*step+gap/2
            height = min(plot.height(),max(1,plot.height()*level/100))
            color = threshold(level,100,colors['light']) if use_threshold else inks['cpu']
            fill(p,QRectF(x,plot.bottom()-height,width,height),QColor(color),min(2.5,width/2,height/2))

    def gpu(self,p,box,history,now,colors,inks):
        text(p,QRectF(box.x(),box.y(),30,21),'GPU',colors['ink'],11,QFont.DemiBold)
        text(p,QRectF(box.x()+29,box.y(),box.width()-29,21),self.rows['gpu'][1],inks['gpu'],15,QFont.Bold)
        trend(p,box.adjusted(2,25,-2,-5),series(history,'gpu'),now,inks['gpu'],100)

    def paintEvent(self,event):
        if not self.owner.colors:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.paint_surface(p)
        p.translate(self.inset,self.inset)
        cfg = self.owner.colors
        service = self.owner.service
        inks = metric_colors(service)
        inks={key:reading_ink(service,key,cfg,ink) for key,ink in inks.items()}
        track = QColor(cfg['ink'])
        track.setAlpha(26 if cfg['light'] else 39)
        w = self.width()-2*self.inset
        history = service.history or ()
        now = time.monotonic()
        y = 0
        if 'cpu' in self.rows or 'gpu' in self.rows:
            both = 'cpu' in self.rows and 'gpu' in self.rows
            cpu_width = w-max(58,w*.30)-12 if both else w
            if 'cpu' in self.rows:
                self.processors(p,QRectF(0,0,cpu_width,self.load_height),service.latest.get('cpu_cores') or (),history,now,inks,cfg,track)
            if 'gpu' in self.rows:
                x = cpu_width+12 if both else 0
                if both:
                    p.setPen(QPen(track,1))
                    p.drawLine(QPointF(x-6,3),QPointF(x-6,self.load_height-5))
                self.gpu(p,QRectF(x,0,w-x,self.load_height),history,now,cfg,inks)
            y = self.load_height
        if 'memory' in self.rows:
            record = service.latest.get('memory')
            value = '—'
            if record:
                total = f'{record[2]/2**30:.1f}'.removesuffix('.0')
                value = f'{record[1]/2**30:.1f} / {total} GB'
            text(p,QRectF(0,y,w/2,20),'内存',cfg['ink'],11,QFont.DemiBold)
            text(p,QRectF(32,y,w-32,20),value,inks['memory'],11,QFont.DemiBold)
            track_x=32+p.fontMetrics().horizontalAdvance(value)+10
            gauge = QRectF(track_x,y+8,max(0,w-track_x),4)
            fill(p,gauge,track,2)
            if record and record[0]>0:
                fill(p,QRectF(gauge.x(),gauge.y(),gauge.width()*min(100,record[0])/100,4),QColor(inks['memory']),2)
            y += 25
        if 'network' in self.rows:
            net = service.latest.get('network')
            half = (w-12)/2
            for i,(arrow,color) in enumerate((('↓',inks['cpu']),('↑',inks['network']))):
                pos = i*(half+12)
                text(p,QRectF(pos,y,14,22),arrow,color,14,QFont.Bold)
                value = rate(net[i]) if net else '—'
                text(p,QRectF(pos+15,y,half-15,22),value,cfg['ink'],11,QFont.DemiBold)
                occupied = p.fontMetrics().horizontalAdvance(value)+22
                values = series(history,'network',i)
                trend(p,QRectF(pos+occupied,y+4,half-occupied-2,14),values,now,color,max((v for _,v in values),default=1))
            y += 25
        for i,key in enumerate(self.extras):
            x = (i%2)*(w/2)
            top = y+(i//2)*25
            label,value,_ = self.rows[key]
            if key=='fps':
                label='FPS'
            area = QRectF(x+1,top,w/2-5,22)
            text(p,area,label,cfg['muted'],10)
            label_width=p.fontMetrics().horizontalAdvance(label)+6
            text(p,area.adjusted(label_width,0,0,0),value,reading_ink(service,key,cfg,cfg['ink']),11,QFont.DemiBold)


class SensorColumns(DashboardCard):
    """Keep the hardware group title and several readings on the same row."""
    group_width = 36
    row_height = 20
    column_gap = 7
    minimum_cell_width = 81
    inset = 9

    def __init__(self,window):
        super().__init__(window,'peach');self.groups=[];self.headings=[];self.cells=[]
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    def refresh(self,rows):
        self.groups=[]
        for prefix,title in (('cpu_','CPU'),('gpu_','GPU'),('','主机')):
            readings=[row for row in rows if row[0].startswith(prefix)] if prefix else [row for row in rows if not row[0].startswith(('cpu_','gpu_'))]
            if readings:self.groups.append((title,readings))
        self.setVisible(bool(self.groups));self.fit_height();self.update()
        self.setAccessibleName('\n'.join(label+' · '+value+(' · '+tip if tip else '') for _,label,value,tip in rows));self.setToolTip('')
    def fit_height(self):
        self.headings = []
        self.cells = []
        font = QFont(self.font())
        font.setPixelSize(11)
        labels = QFontMetrics(font)
        font.setWeight(QFont.DemiBold)
        values = QFontMetrics(font)
        gap = self.column_gap
        available = max(1, self.width() - self.group_width - 2*self.inset)
        columns = max(1, min(6, (available + gap) // (self.minimum_cell_width + gap)))
        span = (available - (columns - 1) * gap) / columns
        y = self.inset+20
        for title, readings in self.groups:
            self.headings.append((QRectF(self.inset, y, self.group_width - 4, self.row_height), title))
            column = 0
            for key, label, value, _ in readings:
                label = label.removeprefix('CPU ').removeprefix('GPU ').replace('帧率 FPS', '实时帧率')
                value_width = values.horizontalAdvance(value) + 1
                required = labels.horizontalAdvance(label) + 6 + value_width
                slots = min(columns, max(1, math.ceil((required + gap) / (span + gap))))
                if column + slots > columns:
                    column = 0
                    y += self.row_height
                x = self.inset + self.group_width + column * (span + gap)
                width = slots * (span + gap) - gap
                value_width = min(width, value_width)
                label_width = max(0, width - value_width - 5)
                self.cells.append((key, labels.elidedText(label, Qt.ElideRight, int(label_width)),
                                   values.elidedText(value, Qt.ElideRight, int(value_width)),
                                   QRectF(x, y, label_width, self.row_height),
                                   QRectF(x + width - value_width, y, value_width, self.row_height)))
                column += slots
            y += self.row_height + 3
        self.setFixedHeight(y+self.inset-3 if self.groups else 1)
    def resizeEvent(self,event):
        self.fit_height();super().resizeEvent(event)
    def paintEvent(self,event):
        if not self.groups or not self.owner.colors:return
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.owner.colors
        self.paint_surface(p)
        text(p,QRectF(self.inset,self.inset-1,self.width()-2*self.inset,18),'硬件读数',c['ink'],11,QFont.DemiBold)
        for area, title in self.headings:
            text(p,area,title,c['ink'],12,QFont.DemiBold)
        for key, label, value, label_area, value_area in self.cells:
            text(p,label_area,label,c['muted'],11)
            ink = c['muted'] if value == '—' else reading_ink(self.owner.service,key,c,c['ink'])
            text(p,value_area,value,ink,11,QFont.DemiBold,Qt.AlignRight)
