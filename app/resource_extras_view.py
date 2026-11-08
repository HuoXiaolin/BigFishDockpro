"""Compact weather cards with a local forecast and source notes."""
import time
from datetime import datetime,timedelta
from PyQt5.QtCore import Qt,QPointF,QRectF,QTimer
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton
from ui_style import ModernComboBox
from resource_compact import text
from resource_weather import moon_phase,weather_time
from resource_weather_style import (AIR_SURFACES,FORECAST_TONES,paint_card,paint_weather,
                                    solar_tone,weather_accent)


def degrees(value):return '—' if value is None else f'{value:.0f}°'


def weather_days(row,count,today):
    offsets=(-1,0,1) if count==3 else range(count)
    available={day.get('date'):day for day in row.get('days',[])}
    result=[]
    for offset in offsets:
        day=today+timedelta(days=offset);value=available.get(day.isoformat())
        if value is None:value=dict(date=day.isoformat(),condition='—',low=None,high=None)
        label={-1:'昨天',0:'今天',1:'明天'}.get(offset,'周'+'一二三四五六日'[day.weekday()])
        result.append((label,value))
    return result


class WeatherCards(QWidget):
    gap=6
    card_height=112

    def __init__(self,owner):
        super().__init__()
        self.owner=owner
        self.rows=[]
        self.city_index=0
        self.columns=2
        self.sun_clock=QTimer(self)
        self.sun_clock.setInterval(60_000)
        self.sun_clock.timeout.connect(self.update)

    def showEvent(self,event):
        super().showEvent(event)
        self.sun_clock.start()

    def hideEvent(self,event):
        self.sun_clock.stop()
        super().hideEvent(event)

    def refresh(self):
        service=self.owner.service;extra=service.extras;by_name={r['name']:r for r in extra.weather} if extra else {}
        self.rows=[by_name.get(name,dict(name=name)) for name in service.cfg['resource_weather_cities']]
        self.layout_cards();self.update()

    def layout_cards(self):
        self.columns=2 if self.width()>=420 else 1
        count=4//self.columns
        height=count*self.card_height+(count-1)*self.gap
        if self.height()!=height:self.setFixedHeight(height)

    def resizeEvent(self,event):self.layout_cards();super().resizeEvent(event)

    def set_city(self,index):
        self.city_index=max(0,index)
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        colors=self.owner.colors
        if not self.rows:
            text(p,QRectF(self.rect()),'请在天气设置中添加城市',colors['muted'],12,False,Qt.AlignHCenter)
            return
        row=self.rows[min(self.city_index,len(self.rows)-1)]
        now=weather_time(row)
        days=weather_days(row,self.owner.service.cfg['resource_weather_days'],now.date())
        today=next((day for day in row.get('days',[]) if day['date']==now.date().isoformat()),{})
        panels=((self.draw_current,row),(self.draw_days,days),(self.draw_air,row),
                (self.draw_sun,(now if row.get('sampled') else None,today)))
        span=(self.width()-(self.columns-1)*self.gap)/self.columns
        for i,(draw,data) in enumerate(panels):
            x=i%self.columns*(span+self.gap)
            y=i//self.columns*(self.card_height+self.gap)
            p.save()
            p.translate(x,y)
            draw(p,span,data,colors,colors['card_alpha'])
            p.restore()

    def draw_current(self,p,width,row,c,opacity):
        paint_weather(p,QRectF(0,0,width,self.card_height),row,c['light'],c['hover'],opacity)
        text(p,QRectF(10,4,width-20,15),row['name']+'  '+row.get('condition',''),c['ink'],11,True)
        temperature=row.get('temperature')
        text(p,QRectF(10,20,71,35),degrees(temperature),c['ink'],30,True)
        info=('体感 '+degrees(row.get('feels'))) if temperature is not None else row.get('error','等待天气')
        text(p,QRectF(82,20,width-92,16),info,c['muted'],10)
        humidity,wind=row.get('humidity'),row.get('wind')
        details='湿度 '+('—' if humidity is None else f'{humidity:.0f}%')+'   风 '+('—' if wind is None else f'{wind:.0f} km/h')
        text(p,QRectF(82,36,width-92,16),details,c['muted'],10)
        hours=[('现在',temperature),*row.get('hours',[])]
        values=[value for _,value in hours if value is not None]
        if not values:
            text(p,QRectF(10,65,width-20,24),'逐小时气温暂不可用',c['muted'],11)
            return
        low,high=min(values),max(values)
        step=(width-16)/len(hours)
        ink=weather_accent(row,c['light'])
        path=QPainterPath();previous=False;markers=[]
        for i,(name,value) in enumerate(hours):
            x=8+(i+.5)*step
            text(p,QRectF(x-step/2,91,step,16),name,c['muted'],9,False,Qt.AlignHCenter)
            if value is None:previous=False;continue
            y=86-(value-low)/max(2,high-low)*15
            if previous:path.lineTo(x,y)
            else:path.moveTo(x,y)
            previous=True;markers.append(QPointF(x,y))
            text(p,QRectF(x-step/2,y-17,step,14),degrees(value),c['ink'],9,False,Qt.AlignHCenter)
        p.setPen(QPen(ink,1.4));p.setBrush(Qt.NoBrush);p.drawPath(path)
        p.setPen(Qt.NoPen);p.setBrush(ink)
        for point in markers:p.drawEllipse(point,2,2)

    def draw_days(self,p,width,days,c,opacity):
        surface,accent=FORECAST_TONES[0 if c['light'] else 1]
        paint_card(p,QRectF(0,0,width,self.card_height),surface,opacity)
        text(p,QRectF(10,4,width-20,16),'未来一周' if len(days)==7 else '每日预报',c['ink'],11,True)
        step=(width-12)/len(days)
        temperatures=[v for _,day in days for v in (day['low'],day['high']) if v is not None]
        low,high=(min(temperatures),max(temperatures)) if temperatures else (0,1)
        for i,(name,day) in enumerate(days):
            x=6+i*step
            def center(top,value,size=10,muted=False):
                text(p,QRectF(x,top,step,14),value,c['muted' if muted else 'ink'],size,False,Qt.AlignHCenter)
            center(22,name,9);center(36,day['condition'],9,True)
            center(50,degrees(day['high']),10)
            if day['high'] is not None and day['low'] is not None:
                scale=16/max(1,high-low)
                y1=80-(day['high']-low)*scale
                y2=80-(day['low']-low)*scale
                p.setPen(QPen(QColor(accent),3,Qt.SolidLine,Qt.RoundCap))
                p.drawLine(QPointF(x+step/2,y1),QPointF(x+step/2,y2))
            center(81,degrees(day['low']),9,True)
            rain=day.get('rain')
            center(96,'—' if rain is None else f'{rain:.0f}%',9,True)

    def draw_air(self,p,width,row,c,opacity):
        paint_card(p,QRectF(0,0,width,self.card_height),AIR_SURFACES[0 if c['light'] else 1],opacity)
        data=row.get('air',{})
        aqi=data.get('aqi',data.get('us_aqi'))
        scale=data.get('scale','US AQI')
        bands=(50,100,150,200,300,500)
        names=('优','良','轻度污染','中度污染','重度污染','严重污染') if scale.startswith('中国') else ('良好','一般','敏感人群不健康','不健康','很不健康','严重')
        shades=('#1b8255','#947001','#b85b1a','#c73948','#8354ab','#9a354f') if c['light'] else (
            '#62d7a4','#f1ca61','#f4ab73','#fb8892','#c6a5ef','#e888a2')
        index=next((i for i,limit in enumerate(bands) if aqi is not None and round(aqi)<=limit),len(bands)-1)
        color=shades[index] if aqi is not None else c['muted']
        source=data.get('source','')
        source_label='上次读数' if data.get('stale') else '小时数据' if data.get('hourly') else source
        text(p,QRectF(10,4,width-86,16),'空气质量 · '+scale,c['ink'],11,True)
        text(p,QRectF(width-74,4,64,16),source_label,c['muted'],8,False,Qt.AlignRight)
        text(p,QRectF(10,21,65,34),'—' if aqi is None else f'{aqi:.0f}',color,27,True)
        status=names[index] if aqi is not None else row.get('air_error','等待空气质量')
        text(p,QRectF(78,27,width-88,20),status,color,10)
        step=(width-20)/6
        for i,shade in enumerate(shades):
            ink=QColor(shade);ink.setAlpha(230 if aqi is not None and i==index else 70)
            p.setPen(Qt.NoPen);p.setBrush(ink);p.drawRoundedRect(QRectF(10+i*step,60,step-2,3),1.5,1.5)
        step=(width-20)/3
        for i,(key,label) in enumerate((('pm2_5','PM2.5'),('pm10','PM10'),('ozone','O₃'))):
            x=10+i*step;value=data.get(key);unit='μg/m³'
            if 'pollutants' in data:value,unit=data['pollutants'].get(key) or (None,'')
            text(p,QRectF(x,70,step,14),label,c['muted'],10)
            text(p,QRectF(x,85,step,16),'—' if value is None else f'{value:g} {unit}',c['ink'],10,True)

    def draw_sun(self,p,width,data,c,opacity):
        now,today=data
        try:
            sunrise=datetime.fromisoformat(today.get('sunrise','')).replace(tzinfo=None)
            sunset=datetime.fromisoformat(today.get('sunset','')).replace(tzinfo=None)
        except (ValueError,TypeError):
            sunrise=sunset=None
        local=now.replace(tzinfo=None) if now else None
        stage,surface,accent=solar_tone(local,sunrise,sunset,c['light'])
        paint_card(p,QRectF(0,0,width,self.card_height),surface,opacity)
        moon,illumination=moon_phase(now.isoformat() if now else '')
        text(p,QRectF(10,4,85,16),'日出日落',c['ink'],11,True)
        clock=' '.join(part for part in (stage,now.strftime('%H:%M') if now else '') if part)
        text(p,QRectF(67,4,width-77,16),clock,accent,10,True,Qt.AlignRight)
        if moon:
            text(p,QRectF(10,22,width-20,14),f'{moon} {illumination}%',c['muted'],9,False,Qt.AlignRight)
        if local is not None and sunrise and sunset and sunrise<sunset:
            path=QPainterPath(QPointF(18,69))
            path.quadTo(width/2,-4,width-18,69)
            line=QColor(accent);line.setAlpha(122)
            p.setPen(QPen(line,1));p.drawLine(QPointF(16,69),QPointF(width-16,69))
            p.setPen(QPen(line,1.2,Qt.DotLine,Qt.RoundCap));p.setBrush(Qt.NoBrush);p.drawPath(path)
            p.setPen(Qt.NoPen);p.setBrush(line)
            for x in (18,width-18):p.drawEllipse(QPointF(x,69),2,2)
            if sunrise<=local<=sunset:
                position=(local-sunrise)/(sunset-sunrise)
                point=path.pointAtPercent(position)
                halo=QColor(accent);halo.setAlpha(42)
                p.setBrush(halo);p.drawEllipse(point,6,6)
                p.setBrush(QColor(accent));p.drawEllipse(point,3.2,3.2)
        else:
            text(p,QRectF(10,39,width-20,22),'暂无日照数据',c['muted'],10,False,Qt.AlignHCenter)
        length=today.get('daylight')
        length_text='—' if length is None else f'{int(length)//3600}小时 {int(length)%3600//60:02d}分'
        step=(width-20)/3
        for i,(label,value) in enumerate((('日出',sunrise.strftime('%H:%M') if sunrise else '—'),
                                           ('白昼',length_text),('日落',sunset.strftime('%H:%M') if sunset else '—'))):
            x=10+i*step
            align=(Qt.AlignLeft,Qt.AlignHCenter,Qt.AlignRight)[i]
            text(p,QRectF(x,77,step,14),label,c['muted'],9,False,align)
            text(p,QRectF(x,91,step,16),value,c['ink'],10,True,align)


class WeatherAction(QToolButton):
    def paintEvent(self,event):
        colors=self.window().colors
        if not colors:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        active=self.isChecked() or self.isDown()
        ink=QColor(colors['ink'] if self.isEnabled() else colors['muted'])
        fill=QColor(colors['hover']);fill.setAlpha(79 if active else 42 if self.underMouse() else 8)
        edge=QColor(ink);edge.setAlpha(145 if self.hasFocus() else 65)
        painter.setPen(QPen(edge,1) if active or self.hasFocus() else Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),6,6)
        painter.setPen(ink);painter.setFont(self.font())
        painter.drawText(self.rect(),Qt.AlignCenter,self.text())


class WeatherView(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(4)
        self.weather_head=QWidget();head=QHBoxLayout(self.weather_head);head.setContentsMargins(0,0,0,0);head.setSpacing(5)
        self.city=ModernComboBox();self.city.setAccessibleName('天气城市');self.city.setProperty('glassField',True)
        self.city.setMinimumWidth(94);self.city.setMaximumWidth(144);self.city.setFixedHeight(22)
        self.city.setStyleSheet('QComboBox{min-height:0;padding:1px 23px 1px 7px;border:0;background:transparent;font-size:11px}')
        head.addWidget(self.city);head.addStretch(1)
        self.week=WeatherAction();self.week.setText('七天');self.week.setCheckable(True)
        self.week.setToolTip('切换昨天、今天、明天与未来七天')
        self.week.clicked.connect(self.set_range);head.addWidget(self.week)
        self.refresh_button=WeatherAction();self.refresh_button.setText('刷新');self.refresh_button.clicked.connect(self.refresh_weather);head.addWidget(self.refresh_button)
        self.week.setFixedHeight(22);self.refresh_button.setFixedHeight(22)
        box.addWidget(self.weather_head);self.cards=WeatherCards(owner);box.addWidget(self.cards)
        self.city.currentIndexChanged.connect(self.cards.set_city)
        self.remarks_button=QToolButton();self.remarks_button.setText('备注');self.remarks_button.setCheckable(True);self.remarks_button.toggled.connect(self.toggle_notes)
        box.addWidget(self.remarks_button,0,Qt.AlignLeft);self.notes=QLabel();self.notes.setTextFormat(Qt.RichText);self.notes.setOpenExternalLinks(True)
        self.notes.setWordWrap(True);self.notes.setObjectName('Subtle');box.addWidget(self.notes);self.notes.hide()
    def toggle_notes(self,on):self.notes.setVisible(on)
    def set_range(self,on):
        if not self.owner.service.set_options(resource_weather_days=7 if on else 3):self.week.setChecked(not on)
    def refresh_weather(self):
        if self.owner.service.extras:self.owner.service.extras.refresh_weather();self.refresh()
    def refresh(self):
        service=self.owner.service;extra=service.extras
        self.setVisible(service.cfg['resource_weather'])
        self.refresh_button.setEnabled(not extra or extra.weather_job is None)
        names=tuple(service.cfg['resource_weather_cities'])
        if names!=getattr(self,'names',None):
            old=self.city.currentText()
            self.city.clear();self.city.addItems(list(names))
            if old in names:self.city.setCurrentIndex(names.index(old))
            self.names=names
        self.week.setChecked(service.cfg['resource_weather_days']==7)
        self.cards.refresh()
        stamp=max((r.get('updated',0) for r in extra.weather),default=0) if extra else 0
        self.notes.setText('天气由 <a href="https://open-meteo.com/">Open-Meteo</a> 提供，每 15 分钟刷新。'
                           '空气质量可用 <a href="https://ads.atmosphere.copernicus.eu/">CAMS</a> 模型或 <a href="https://www.qweather.com/">和风天气</a>。卡片标明 AQI 口径。日出日落使用城市当地时间，月相为近似值。'
                           +('更新于 '+time.strftime('%H:%M',time.localtime(stamp))+'。' if stamp else ''))
        self.notes.setVisible(self.remarks_button.isChecked())
