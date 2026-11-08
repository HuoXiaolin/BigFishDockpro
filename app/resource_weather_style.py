"""Small vector weather scenes; no image cache, animation timer or downloads."""
import math
from datetime import timedelta
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QLinearGradient,QRadialGradient,QPainterPath,QPen
from card_design import SOFT_SURFACES,blend


FORECAST_TONES=tuple(zip(SOFT_SURFACES['lavender'],('#4d5695','#b7c2ff')))
AIR_SURFACES=SOFT_SURFACES['mint']
SUN_TONES={
    'dawn':(('#ffd7b8','#8c411b'),('#553628','#ffc69c')),
    'day':tuple(zip(SOFT_SURFACES['peach'],('#844f35','#f1bf9f'))),
    'dusk':tuple(zip(SOFT_SURFACES['rose'],('#803b67','#fac0e2'))),
    'night':(('#c3d3f1','#324878'),('#243454','#c0d2ff')),
}


def solar_tone(now,sunrise,sunset,light):
    """Interpolate from the horizon's colors over the minutes around each event."""
    theme=0 if light else 1
    night=SUN_TONES['night'][theme]
    if now is None or sunrise is None or sunset is None or sunset<=sunrise:
        return '',*night
    edge=min(timedelta(minutes=50),(sunset-sunrise)/3)
    stages=((sunrise-edge,sunrise,'night','dawn','清晨'),
            (sunrise,sunrise+edge,'dawn','day','清晨'),
            (sunrise+edge,sunset-edge,'day','day','白天'),
            (sunset-edge,sunset,'day','dusk','黄昏'),
            (sunset,sunset+edge,'dusk','night','黄昏'))
    for start,end,first,last,label in stages:
        if start<=now<end:
            amount=(now-start)/(end-start)
            surface,ink=(blend(QColor(a),QColor(b),amount) for a,b in zip(SUN_TONES[first][theme],SUN_TONES[last][theme]))
            return label,surface,ink
    return '夜间',*night


def paint_card(p,rect,surface,opacity):
    color=QColor(surface)
    gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
    for stop,tint in ((0,color.lighter(105)),(1,color)):
        tint.setAlpha(opacity)
        gradient.setColorAt(stop,tint)
    p.setPen(Qt.NoPen);p.setBrush(gradient);p.drawRoundedRect(rect,9,9)


def weather_kind(row):
    code=row.get('code')
    if code in (95,96,99):return 'storm'
    if code in (71,73,75,77,85,86):return 'snow'
    if code in (51,53,55,56,57,61,63,65,66,67,80,81,82):return 'rain'
    if code in (45,48):return 'fog'
    if code==0:return 'sun'
    if code in (1,2):return 'cloud'
    if code==3:return 'overcast'
    return {'晴':'sun','多云':'cloud','阴':'overcast','雨':'rain','毛毛雨':'rain','雪':'snow','雾':'fog','雷雨':'storm'}.get(row.get('condition'),'unknown')


def weather_accent(row,light):
    kind=weather_kind(row)
    if kind=='sun':return QColor('#996315' if light else '#ffcf83')
    if kind=='storm':return QColor('#6554a4' if light else '#c7b4ff')
    if kind=='fog':return QColor('#39796d' if light else '#a0d9c5')
    return QColor('#216d98' if light else '#a1d8f4')


def paint_weather(p,rect,row,light,fallback,opacity=255):
    kind=weather_kind(row)
    palettes={
        'sun':(('#fff5df','#f5dda5'),('#3b3429','#625337')),
        'cloud':(('#ecf4fb','#c7ddeb'),('#273948','#3c5368')),
        'overcast':(('#e9eef2','#c1ced8'),('#29333f','#455461')),
        'rain':(('#e4f2fb','#b4d6eb'),('#233745','#35566c')),
        'snow':(('#f4faff','#d1e6f5'),('#2b3c4b','#496379')),
        'fog':(('#edf1f0','#d1dbd9'),('#303c3e','#4a5859')),
        'storm':(('#eeebfb','#c8c6e9'),('#302e44','#504c6c'))}
    p.save();shape=QPainterPath();shape.addRoundedRect(rect,9,9);p.setClipPath(shape)
    colors=palettes.get(kind)
    if colors:
        a,b=map(QColor,colors[0 if light else 1])
        a.setAlpha(opacity);b.setAlpha(opacity)
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight());gradient.setColorAt(0,a);gradient.setColorAt(1,b);p.fillPath(shape,gradient)
    else:
        fill=QColor(fallback);fill.setAlpha(opacity);p.fillPath(shape,fill)
    # Decoration occupies the trailing portion, leaving a quiet area for text.
    x=rect.right()-29;y=rect.top()+22;accent=QColor('#fffaf0' if light else '#b8d5e8')
    def cloud(cx,cy):
        path=QPainterPath();path.setFillRule(Qt.WindingFill);path.addRoundedRect(QRectF(cx-25,cy,48,15),7,7)
        for dx,dy,r in [(-13,0,10),(0,-5,14),(14,1,9)]:path.addEllipse(QPointF(cx+dx,cy+dy),r,r)
        p.setPen(Qt.NoPen);p.setBrush(accent);p.drawPath(path.simplified())
    p.setOpacity(.64 if light else .33)
    if kind in ('sun','cloud'):
        sun=QColor('#f2bb48' if light else '#e7c781');p.setPen(Qt.NoPen)
        glow=QRadialGradient(QPointF(x,y),37);glow.setColorAt(0,QColor(sun));edge=QColor(sun);edge.setAlpha(0);glow.setColorAt(1,edge)
        p.setBrush(glow);p.drawEllipse(QPointF(x,y),37,37);p.setBrush(sun);p.drawEllipse(QPointF(x,y),11,11)
        p.setPen(QPen(sun,1.4,Qt.SolidLine,Qt.RoundCap))
        for i in range(8):
            a=i*math.pi/4;p.drawLine(QPointF(x+15*math.cos(a),y+15*math.sin(a)),QPointF(x+19*math.cos(a),y+19*math.sin(a)))
    if kind in ('cloud','overcast','rain','snow','storm'):
        cloud(x-4,y+9)
        if kind in ('cloud','overcast'):p.setOpacity(.24);cloud(x+13,y+31)
    if kind=='rain':
        p.setPen(QPen(QColor('#6aadc9' if light else '#80bdd9'),1.2,Qt.SolidLine,Qt.RoundCap))
        for dx,dy in [(-20,31),(-7,35),(6,30),(-13,47),(0,50)]:p.drawLine(QPointF(x+dx,y+dy),QPointF(x+dx-4,y+dy+7))
    if kind=='snow':
        p.setPen(QPen(QColor('#91b9d3' if light else '#d7eafa'),1,Qt.SolidLine,Qt.RoundCap))
        for dx,dy in [(-21,34),(2,36),(-10,53)]:
            for a in (0,math.pi/3,2*math.pi/3):p.drawLine(QPointF(x+dx-4*math.cos(a),y+dy-4*math.sin(a)),QPointF(x+dx+4*math.cos(a),y+dy+4*math.sin(a)))
    if kind=='fog':
        p.setPen(QPen(QColor('#a5b4b7' if light else '#b0c1c4'),3,Qt.SolidLine,Qt.RoundCap))
        for i in range(5):p.drawLine(QPointF(x-28+(i%2)*9,y+i*10),QPointF(x+22-(i%2)*7,y+i*10))
    if kind=='storm':
        bolt=QPainterPath();bolt.moveTo(x-2,y+21);bolt.lineTo(x-12,y+40);bolt.lineTo(x-3,y+38);bolt.lineTo(x-10,y+55);bolt.lineTo(x+9,y+29);bolt.lineTo(x,y+32);bolt.closeSubpath()
        p.setPen(Qt.NoPen);p.setBrush(QColor('#e7bd64'));p.drawPath(bolt)
    p.restore()
