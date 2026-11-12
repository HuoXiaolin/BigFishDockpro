"""Compact status readout for the existing mint hardware card."""
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from resource_compact import ring, text
from resource_options import content_columns
from resource_status import BATTERY_WARNING_LEVEL, band_ink, low_battery_ink


BATTERY_STATES = {
    'charging':'充电中', 'full':'已充满', 'plugged':'已接电源', 'battery':'电池供电',
    'ac':'交流供电', 'no_battery':'无内置电池', 'unknown':'待读取',
}


def battery_ink(level, state, light, muted):
    if state == 'charging':
        return '#087d59' if light else '#65d8a4'
    if level is None:
        return muted
    if level <= BATTERY_WARNING_LEVEL:
        return low_battery_ink(level, light)
    if level <= 35:
        return band_ink(level, 35, BATTERY_WARNING_LEVEL, 'yellow', light)
    return band_ink(level, 100, 35, 'blue', light)


def battery_icon(painter, center, state, ink):
    x,y=center.x(),center.y()
    path=QPainterPath()
    if state in ('charging','ac'):
        path.moveTo(x+1,y-6);path.lineTo(x-4,y+1);path.lineTo(x-.5,y+1)
        path.lineTo(x-1,y+6);path.lineTo(x+4,y-1);path.lineTo(x+.5,y-1);path.closeSubpath()
        painter.setPen(Qt.NoPen);painter.setBrush(QColor(ink));painter.drawPath(path)
    else:
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(QColor(ink),1.3,Qt.SolidLine,Qt.RoundCap))
        painter.drawRoundedRect(QRectF(x-5.5,y-3,10,6),1.3,1.3)
        painter.drawLine(QPointF(x+6,y-1),QPointF(x+6,y+1))


class SystemReadout(QWidget):
    def __init__(self,owner):
        super().__init__()
        self.owner=owner
        self.fit_rows()

    def fit_rows(self):
        self.columns=content_columns(self.owner.width())
        self.setFixedHeight(57 if self.columns==2 else 89)

    def resizeEvent(self,event):
        if event.oldSize().width()!=event.size().width():self.fit_rows()
        super().resizeEvent(event)

    def values(self):
        service=self.owner.service
        status=service.latest.get('system_status') or {}
        level,state=status.get('battery',(None,'unknown'))
        reading=service.sensors.values.get('brightness',{}) if service.sensors else {}
        return level,state,status.get('volume'),reading.get('value'),status.get('connection')

    def refresh(self):
        level,state,volume,brightness,connection=self.values()
        volume_text='—' if volume is None else '静音' if volume[1] else f'{volume[0]}%'
        brightness_text='—' if brightness is None else f'{brightness:.0f}%'
        battery_text=f'电池 {level}% {BATTERY_STATES[state]}' if level is not None else BATTERY_STATES[state]
        connection_text='—' if connection is None else connection or '未连接'
        self.setAccessibleName(f'{battery_text}，音量 {volume_text}，亮度 {brightness_text}，网卡 {connection_text}')
        self.update()

    def paintEvent(self,event):
        c=self.owner.colors
        level,state,volume,brightness,connection=self.values()
        width=self.width()
        paired=self.columns==2
        split=width//2 if paired else 0
        battery_width=split if paired else width
        tight=paired and battery_width<86
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        ink=battery_ink(level,state,c['light'],c['muted'])
        circle=QRectF(1,2,22,22) if tight else QRectF(2,5,26,26)
        ring(p,circle,level,ink,c['hover'])
        if level==0:ring(p,circle,None,ink,ink)
        battery_icon(p,circle.center(),state,ink)
        label=f'{level}%' if level is not None else ('AC' if state=='ac' else '—')
        left=26 if tight else 34
        text(p,QRectF(left,2,battery_width-left-2,21 if tight else 17),label,ink,11 if tight else 14,True)
        state_rect=QRectF(0,24,battery_width-2,13) if tight else QRectF(left,19,battery_width-left-2,15)
        text(p,state_rect,BATTERY_STATES[state],c['muted'],9 if tight else 10)
        volume_text='—' if volume is None else '静音' if volume[1] else f'{volume[0]}%'
        for i,(label,value) in enumerate((('音量',volume_text),('亮度','—' if brightness is None else f'{brightness:.0f}%'))):
            top=(3 if paired else 35)+16*i
            level=brightness if i else volume[0] if volume and not volume[1] else None
            ring(p,QRectF(split,top+2,10,10),level,c['muted'],c['hover'])
            label_x=split+(13 if tight else 16)
            label_width=20 if tight else 24
            value_x=label_x+label_width+2
            text(p,QRectF(label_x,top,label_width,15),label,c['muted'],9 if tight else 10)
            text(p,QRectF(value_x,top,width-value_x,15),value,c['muted'] if value=='—' else c['ink'],
                 9 if tight else 11,True,Qt.AlignRight)
        bottom=self.height()-19
        p.setPen(QPen(QColor(c['hover']),1))
        p.drawLine(QPointF(0,bottom),QPointF(width,bottom))
        text(p,QRectF(0,bottom+2,28,16),'网卡',c['muted'],10)
        connection_text='—' if connection is None else connection or '未连接'
        text(p,QRectF(30,bottom+2,width-30,16),connection_text,c['ink'] if connection else c['muted'],11)
