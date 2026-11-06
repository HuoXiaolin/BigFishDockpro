"""Native-pixel resource graphs. All values come from the capsule's enabled samplers."""
import math
import time

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget, QSizePolicy

from flash_view import blend
from resource_options import TINTS


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
    if box.width() < 7 or box.height() < 3 or len(values) < 2:
        return
    path = QPainterPath()
    for stamp,value in values:
        age = now-stamp
        if age > 60:
            continue
        x = box.right()-max(0,age)*box.width()/60
        y = box.bottom()-min(1,max(0,value)/max(1,ceiling))*box.height()
        if path.elementCount():
            path.lineTo(x,y)
        else:
            path.moveTo(x,y)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(ink),1.6,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    p.drawPath(path)


class MetricDisplay(QWidget):
    def __init__(self, window):
        super().__init__()
        self.owner = window
        self.rows = {}
        self.basic = ()
        self.extras = ()
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

    def refresh(self, rows):
        self.rows = {key:(label,value,tip) for key,label,value,tip in rows}
        self.basic = tuple(k for k in ('cpu','gpu','memory','network') if k in self.rows)
        self.extras = tuple(k for k in self.rows if k not in self.basic)
        upper = 82 if 'cpu' in self.rows or 'gpu' in self.rows else 0
        height = upper + 31*('memory' in self.rows) + 27*('network' in self.rows) + 25*math.ceil(len(self.extras)/2)
        self.setFixedHeight(max(1,height))
        self.setVisible(bool(rows))
        tips = [label+' · '+tip for _,label,_,tip in rows if tip]
        if 'cpu' in self.rows:
            tips.insert(0,'蓝青柱按逻辑处理器顺序排列。核心较多时，相邻核心合并取平均值。')
        self.setToolTip('\n'.join(tips))
        self.setAccessibleName('，'.join(label+' '+value for _,label,value,_ in rows))
        self.update()

    def processors(self,p,area,values,history,now,inks,colors,track):
        box = QRectF(area)
        text(p,QRectF(box.x(),box.y(),34,21),'CPU',colors['ink'],12,QFont.DemiBold)
        text(p,QRectF(box.x()+32,box.y(),53,21),self.rows['cpu'][1],colors['ink'],15,QFont.Bold)
        trend(p,QRectF(box.x()+86,box.y()+3,box.width()-87,13),series(history,'cpu'),now,inks['cpu'],100)
        plot = box.adjusted(0,25,0,-5)
        if not values:
            trend(p,plot,series(history,'cpu'),now,inks['cpu'],100)
            return
        count = min(len(values),max(1,min(32,int(plot.width()//7))))
        gap = 2.5
        width = (plot.width()-gap*(count-1))/count
        for i in range(count):
            first,last = i*len(values)//count,(i+1)*len(values)//count
            level = sum(values[first:last])/(last-first)
            x = plot.x()+i*(width+gap)
            radius = min(3,width/2)
            fill(p,QRectF(x,plot.y(),width,plot.height()),track,radius)
            if level <= 0:
                continue
            height = min(plot.height(),max(1,plot.height()*level/100))
            color = blend(inks['cpu'],inks['network'],min(1,max(0,(i/max(1,count-1)-.45)*2.2)))
            fill(p,QRectF(x,plot.bottom()-height,width,height),color,min(radius,height/2))

    def gpu(self,p,box,colors,inks,track):
        text(p,QRectF(box.x(),box.y(),box.width(),19),'GPU',colors['muted'],10,QFont.DemiBold)
        text(p,QRectF(box.x(),box.y()+16,box.width(),19),self.rows['gpu'][1],colors['ink'],13,QFont.Bold)
        gauge = box.adjusted(0,38,0,-5)
        fill(p,gauge,track,4)
        level = self.owner.service.latest.get('gpu')
        if level is not None and level > 0:
            height = max(1,min(gauge.height(),gauge.height()*level/100))
            fill(p,QRectF(gauge.x(),gauge.bottom()-height,gauge.width(),height),QColor(inks['gpu']),min(4,height/2))

    def paintEvent(self,event):
        if not self.owner.colors:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cfg = self.owner.colors
        service = self.owner.service
        inks = metric_colors(service)
        track = QColor(cfg['ink'])
        track.setAlpha(27 if cfg['light'] else 38)
        w = self.width()
        history = service.history or ()
        now = time.monotonic()
        y = 0
        if 'cpu' in self.rows or 'gpu' in self.rows:
            if 'cpu' in self.rows:
                reserve = 55 if 'gpu' in self.rows else 0
                self.processors(p,QRectF(0,0,w-reserve,80),service.latest.get('cpu_cores') or (),history,now,inks,cfg,track)
            if 'gpu' in self.rows:
                x = w-43 if 'cpu' in self.rows else 0
                self.gpu(p,QRectF(x,0,43,80),cfg,inks,track)
                if 'cpu' not in self.rows:
                    trend(p,QRectF(56,13,w-60,60),series(history,'gpu'),now,inks['gpu'],100)
            y = 82
        if 'memory' in self.rows:
            record = service.latest.get('memory')
            value = '—'
            if record:
                total = f'{record[2]/2**30:.1f}'.removesuffix('.0')
                value = f'{record[1]/2**30:.1f} / {total} GB'
            text(p,QRectF(0,y,w/2,17),'内存',cfg['ink'],11,QFont.DemiBold)
            text(p,QRectF(32,y,w-32,17),value,cfg['ink'],11,QFont.DemiBold)
            track_x=32+p.fontMetrics().horizontalAdvance(value)+9
            gauge = QRectF(track_x,y+7,max(0,w-track_x),4)
            fill(p,gauge,track,2)
            if record and record[0]>0:
                fill(p,QRectF(gauge.x(),gauge.y(),gauge.width()*min(100,record[0])/100,4),QColor(inks['memory']),2)
            y += 31
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
            y += 27
        for i,key in enumerate(self.extras):
            x = (i%2)*(w/2)
            top = y+(i//2)*25
            label,value,_ = self.rows[key]
            if key=='fps':
                label='FPS'
            area = QRectF(x+1,top,w/2-5,22)
            text(p,area,label,cfg['muted'],10)
            label_width=p.fontMetrics().horizontalAdvance(label)+6
            text(p,area.adjusted(label_width,0,0,0),value,cfg['ink'],11,QFont.DemiBold)
