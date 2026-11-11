"""Compact status readout for the existing mint hardware card."""
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from resource_compact import ring, text
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
        self.setFixedHeight(57)

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
        width=self.width();split=round(width*.53)
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        ink=battery_ink(level,state,c['light'],c['muted'])
        circle=QRectF(2,5,26,26)
        ring(p,circle,level,ink,c['hover'])
        if level==0:ring(p,circle,None,ink,ink)
        battery_icon(p,circle.center(),state,ink)
        label=f'{level}%' if level is not None else ('AC' if state=='ac' else '—')
        text(p,QRectF(34,2,split-36,17),label,ink,14,True)
        text(p,QRectF(34,19,split-36,15),BATTERY_STATES[state],c['muted'],10)
        volume_text='—' if volume is None else '静音' if volume[1] else f'{volume[0]}%'
        for i,(label,value) in enumerate((('音量',volume_text),('亮度','—' if brightness is None else f'{brightness:.0f}%'))):
            top=3+16*i
            level=brightness if i else volume[0] if volume and not volume[1] else None
            ring(p,QRectF(split,top+2,10,10),level,c['muted'],c['hover'])
            text(p,QRectF(split+16,top,24,15),label,c['muted'],10)
            text(p,QRectF(split+41,top,width-split-41,15),value,c['muted'] if value=='—' else c['ink'],11,True,Qt.AlignRight)
        p.setPen(QPen(QColor(c['hover']),1))
        p.drawLine(QPointF(0,38),QPointF(width,38))
        text(p,QRectF(0,40,28,16),'网卡',c['muted'],10)
        connection_text='—' if connection is None else connection or '未连接'
        text(p,QRectF(30,40,width-30,16),connection_text,c['ink'] if connection else c['muted'],11)
