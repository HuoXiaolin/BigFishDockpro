"""Small vector weather scenes; no image cache, animation timer or downloads."""
import math
from datetime import timedelta
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QColor,QLinearGradient,QRadialGradient,QPainterPath,QPen
from card_design import SOFT_SURFACES,blend
from resource_status import band_ink


FORECAST_TONES=tuple(zip(SOFT_SURFACES['lavender'],('#4d5695','#b7c2ff')))
AIR_SURFACES=SOFT_SURFACES['mint']
AIR_BANDS=(50,100,150,200,300,500)
AIR_HUES=('green','yellow','orange','red','purple','maroon')
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


def compact_temperature_ink(temperature,light,thresholds):
    blue,green,yellow,red=thresholds
    if temperature>red:
        return band_ink(temperature,red,red+15,'red',light)
    if temperature>yellow:
        return band_ink(temperature,yellow,red,'yellow',light)
    if temperature>=green:
        return band_ink(temperature,green,yellow,'green',light)
    if temperature>=blue:
        return band_ink(temperature,green,blue,'cyan',light)
    return band_ink(temperature,blue,blue-20,'blue',light)


def air_quality_style(aqi,light):
    value=round(aqi)
    index=next((i for i,limit in enumerate(AIR_BANDS) if value<=limit),len(AIR_BANDS)-1)
    start=AIR_BANDS[index-1] if index else 0
    return index,band_ink(aqi,start,AIR_BANDS[index],AIR_HUES[index],light)


def paint_weather_icon(p,rect,row,light):
    kind=weather_kind(row)
    color={
        'sun':('#be8007','#ffc868'), 'cloud':('#5682a1','#aacde5'),
        'overcast':('#657991','#bac8d7'), 'rain':('#227eaf','#83d1ff'),
        'snow':('#4a64ab','#bad0ff'), 'fog':('#378376','#a0dac9'),
        'storm':('#6e4db4','#cab3ff'), 'unknown':('#647683','#afbfcc'),
    }[kind][0 if light else 1]
    p.save()
    p.translate(rect.topLeft());p.scale(rect.width()/16,rect.height()/16)
    ink=QColor(color)
    if kind in ('sun','cloud'):
        center=QPointF(8,8) if kind=='sun' else QPointF(10,5)
        sun=QColor('#c58912' if light else '#ffd275')
        p.setBrush(sun);p.setPen(Qt.NoPen);p.drawEllipse(center,3.5,3.5)
        p.setPen(QPen(sun,1.1,Qt.SolidLine,Qt.RoundCap))
        for i in range(8):
            angle=i*math.pi/4
            direction=QPointF(math.cos(angle),math.sin(angle))
            p.drawLine(center+direction*5.0,center+direction*6.4)
    if kind in ('cloud','overcast','rain','snow','storm'):
        top=7 if kind=='cloud' else 5
        cloud=QPainterPath();cloud.setFillRule(Qt.WindingFill)
        cloud.addRoundedRect(QRectF(1.5,top+2,13,5),2.5,2.5)
        cloud.addEllipse(QPointF(6.2,top+2.1),3.2,3.2)
        cloud.addEllipse(QPointF(10.8,top+3.1),2.4,2.4)
        p.setPen(Qt.NoPen);p.setBrush(ink);p.drawPath(cloud)
    p.setPen(QPen(ink,1.2,Qt.SolidLine,Qt.RoundCap))
    if kind=='rain':
        for x in (4,8,12):p.drawLine(QPointF(x,13),QPointF(x-1,15))
    elif kind=='snow':
        for x in (5,10):
            p.drawLine(QPointF(x,13),QPointF(x,15));p.drawLine(QPointF(x-1,14),QPointF(x+1,14))
    elif kind=='storm':
        p.setPen(QPen(QColor('#b0780c' if light else '#ffcf77'),1.5,Qt.SolidLine,Qt.RoundCap))
        p.drawLine(QPointF(9,10),QPointF(6.5,13));p.drawLine(QPointF(6.5,13),QPointF(8.8,13))
        p.drawLine(QPointF(8.8,13),QPointF(7.5,15))
    elif kind=='fog':
        for x,y,w in ((3,4,10),(1.5,8,11),(5,12,9)):
            p.drawLine(QPointF(x,y),QPointF(x+w,y))
    elif kind=='unknown':
        p.drawLine(QPointF(5,8),QPointF(11,8))
    p.restore()


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
