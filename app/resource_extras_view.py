"""Compact weather cards with a local forecast and source notes."""
import time
from datetime import datetime,timedelta
from math import floor,log10
from PyQt5.QtCore import Qt,QPointF,QRectF,QTimer
from PyQt5.QtGui import QColor,QPainter,QPainterPath,QPen
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton
from ui_style import ModernComboBox
from resource_compact import text
from resource_charts import sync_note_controls
from resource_options import content_columns
from resource_status import band_ink
from resource_weather import (RAIN_NOTICES,active_weather_notice,condition,forecast_rain_end,
                              measurement,moon_phase,notice_label,weather_time)
from resource_weather_style import (AIR_HUES,AIR_SURFACES,FORECAST_TONES,air_quality_style,
                                    paint_card,paint_weather,paint_weather_icon,solar_tone,weather_accent)


def degrees(value):return '—' if value is None else f'{value:.0f}°'


TREND_METRICS={
    '雨':('rainfall','逐时雨量（mm）',61,1),
    '雪':('snowfall','逐时雪量（cm）',71,1),
    '雾':('visibility','逐时能见度（km）',45,1000),
}
LOCATION_MESSAGES={
    'permission':'Windows 定位未授权，授权后刷新',
    'timeout':'定位超时，点击刷新可重试',
    'unavailable':'系统暂未返回位置，点击刷新可重试',
}


def trend_tick(peak):
    rough=max(.01,(peak or 1)/3)
    scale=10**floor(log10(rough))
    return next(step*scale for step in (1,2,2.5,5,10) if step*scale>=rough)


def forecast_value(value):
    if value is None:return '—'
    if 0<value<.01:return '<0.01'
    return f'{value:.2f}'.rstrip('0').rstrip('.')


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
    notice_height=55
    trend_height=112

    def __init__(self,owner):
        super().__init__()
        self.owner=owner
        self.rows=[]
        self.city_index=0
        self.layout_cards()
        self.sun_clock=QTimer(self)
        self.sun_clock.setInterval(60_000)
        self.sun_clock.timeout.connect(self.refresh_clock)

    def showEvent(self,event):
        super().showEvent(event)
        self.refresh_clock()
        self.sun_clock.start()

    def hideEvent(self,event):
        self.sun_clock.stop()
        super().hideEvent(event)

    def refresh(self):
        service=self.owner.service;extra=service.extras;by_name={r['name']:r for r in extra.weather} if extra else {}
        names=extra.city_names() if extra else service.cfg['resource_weather_cities']
        self.rows=[by_name.get(name,dict(name=name)) for name in names]
        self.refresh_clock()

    def selected_row(self):
        return self.rows[min(self.city_index,len(self.rows)-1)] if self.rows else {}

    def refresh_clock(self):
        self.layout_cards()
        self.update()

    def layout_cards(self):
        self.columns=content_columns(self.owner.width())
        count=4//self.columns
        height=count*self.card_height+(count-1)*self.gap
        row=self.selected_row()
        now=time.time()
        self.notice=active_weather_notice(row,now)
        self.trend=[slot for slot in row.get('forecast_hours',[]) if slot['at']>now]
        kinds=[kind for slot in self.trend if (kind:=notice_label(slot['code']))]
        if self.notice:kinds.insert(0,self.notice['label'])
        self.trend_kind='雨' if any(kind in RAIN_NOTICES for kind in kinds) else (kinds[0] if kinds else None)
        self.rain_end=forecast_rain_end(self.trend,self.notice) if self.trend_kind=='雨' else None
        if self.trend_kind is None:self.trend=[]
        self.weather_height=(self.notice_height if self.notice else 0)+(self.trend_height if self.trend else 0)
        if self.weather_height:height+=self.weather_height+self.gap
        if self.height()!=height:self.setFixedHeight(height)

    def resizeEvent(self,event):self.layout_cards();super().resizeEvent(event)

    def set_city(self,index):
        self.city_index=max(0,index)
        self.refresh_clock()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        colors=self.owner.colors
        if not self.rows:
            service=self.owner.service
            message='在天气设置中添加城市'
            if service.cfg['resource_weather_location']:
                extra=service.extras
                if extra and extra.weather_job:message='正在获取当前位置…'
                else:message=LOCATION_MESSAGES.get(getattr(extra,'location_status',''),LOCATION_MESSAGES['unavailable'])
            text(p,QRectF(self.rect()),message,colors['muted'],12,False,Qt.AlignHCenter)
            return
        row=self.selected_row()
        now=weather_time(row)
        origin=0
        if self.weather_height:
            surface,_=FORECAST_TONES[0 if colors['light'] else 1]
            paint_card(p,QRectF(0,0,self.width(),self.weather_height),surface,colors['card_alpha'])
            if self.notice:self.draw_notice(p,row,now,colors)
            if self.trend:self.draw_trend(p,self.notice_height if self.notice else 0,now,colors)
            origin=self.weather_height+self.gap
        days=weather_days(row,self.owner.service.cfg['resource_weather_days'],now.date())
        today=next((day for day in row.get('days',[]) if day['date']==now.date().isoformat()),{})
        panels=((self.draw_current,row),(self.draw_days,days),(self.draw_air,row),
                (self.draw_sun,(now if row.get('sampled') else None,today)))
        span=(self.width()-(self.columns-1)*self.gap)/self.columns
        for i,(draw,data) in enumerate(panels):
            x=i%self.columns*(span+self.gap)
            y=origin+i//self.columns*(self.card_height+self.gap)
            p.save()
            p.translate(x,y)
            draw(p,span,data,colors,colors['card_alpha'])
            p.restore()

    def draw_notice(self,p,row,now,c):
        width=self.width()
        paint_weather_icon(p,QRectF(10,15,24,24),row,c['light'])
        label=self.notice['label']+' · 预计持续时间'
        text(p,QRectF(43,3,width-52,17),label,c['ink'],11,True)
        until=self.notice['until']
        if until is None or until<=now.timestamp():
            text(p,QRectF(43,22,width-52,25),'结束时间待更新',c['muted'],11)
            return
        seconds=until-now.timestamp()
        duration='1 小时内' if seconds<3600 else f'约 {round(seconds/1800)/2:g} 小时'
        end=datetime.fromtimestamp(until,now.tzinfo)
        stamp=end.strftime('%H:%M' if end.date()==now.date() else '%m/%d %H:%M')
        text(p,QRectF(43,19,width-52,19),duration,weather_accent(row,c['light']),14,True)
        caption=f'预计 {stamp} 停雨' if self.notice['label'] in RAIN_NOTICES else '预计至 '+stamp
        text(p,QRectF(43,38,width-52,14),caption,c['muted'],10)

    def draw_trend(self,p,top,now,c):
        width=self.width()
        metric,title,code,divisor=TREND_METRICS[self.trend_kind]
        values=[measurement(slot.get(metric)) for slot in self.trend]
        values=[value/divisor if value is not None else None for value in values]
        peak=max((value for value in values if value is not None),default=0)
        tick=trend_tick(peak)
        accent=weather_accent({'code':code},c['light'])
        subtle=QColor(accent);subtle.setAlpha(134)
        if top:
            rule=QColor(c['muted']);rule.setAlpha(42);p.setPen(QPen(rule,1))
            p.drawLine(QPointF(10,top),QPointF(width-10,top))
        text(p,QRectF(10,top+2,width-20,16),title,c['ink'],11,True)
        if self.trend_kind=='雨':
            caption=''
            if self.rain_end and not (self.notice and self.notice['label'] in RAIN_NOTICES):
                end=datetime.fromtimestamp(self.rain_end,now.tzinfo)
                caption=f'预计 {end:%H:%M} 停雨'
            elif peak>0:
                caption='最大 '+self.trend[values.index(peak)]['time']
            text(p,QRectF(width/2,top+2,width/2-10,16),caption,accent,10,True,Qt.AlignRight)

        left,right=31,width-9
        plot_height=48
        baseline=top+79
        for index in range(4):
            y=baseline-index*plot_height/3
            grid=QColor(c['muted']);grid.setAlpha(70 if index==0 else 34)
            p.setPen(QPen(grid,1));p.drawLine(QPointF(left,y),QPointF(right,y))
            text(p,QRectF(2,y-6,left-7,12),f'{index*tick:g}',c['muted'],9,False,Qt.AlignRight)
        step=(right-left)/len(self.trend)
        is_visibility=self.trend_kind=='雾'
        path=QPainterPath();previous=False;markers=[]
        bar_width=min(31,step*.52)
        for index,(slot,value) in enumerate(zip(self.trend,values)):
            x=left+index*step
            center=x+step/2
            kind=notice_label(slot['code'])
            caption=kind or condition(slot['code'])
            stops=slot['at']==self.rain_end
            if stops:
                p.setPen(QPen(subtle,1,Qt.DashLine))
                p.drawLine(QPointF(center,baseline-plot_height),QPointF(center,baseline))
            height=(value or 0)/(3*tick)*plot_height
            y=baseline-height
            highest=peak>0 and value==peak and not is_visibility
            if is_visibility and value is not None:
                if previous:path.lineTo(center,y)
                else:path.moveTo(center,y)
                markers.append(QPointF(center,y))
            elif height>0:
                p.fillRect(QRectF(center-bar_width/2,y,bar_width,height),accent if highest else subtle)
            previous=value is not None
            ink=accent if highest else c['muted'] if value is None else c['ink']
            text(p,QRectF(x,y-15,step,13),forecast_value(value),ink,10,highest,Qt.AlignHCenter)
            text(p,QRectF(x,baseline+3,step,13),slot['time'],accent if stops else c['muted'],10,stops,Qt.AlignHCenter)
            text(p,QRectF(x,baseline+17,step,13),caption,c['ink'],10,False,Qt.AlignHCenter)
        if is_visibility:
            p.setPen(QPen(accent,1.4));p.setBrush(Qt.NoBrush);p.drawPath(path)
            p.setPen(Qt.NoPen);p.setBrush(accent)
            for point in markers:p.drawEllipse(point,2,2)

    def draw_current(self,p,width,row,c,opacity):
        paint_weather(p,QRectF(0,0,width,self.card_height),row,c['light'],c['hover'],opacity)
        text(p,QRectF(10,4,width-20,15),row['name']+'  '+row.get('condition',''),c['ink'],11,True)
        temperature=row.get('temperature')
        text(p,QRectF(10,20,71,35),degrees(temperature),c['ink'],30,True)
        tight=width<220
        left=66 if tight else 82
        info=('体感 '+degrees(row.get('feels'))) if temperature is not None else row.get('error','等待天气')
        text(p,QRectF(left,17 if tight else 20,width-left-10,15),info,c['muted'],10)
        humidity,wind=row.get('humidity'),row.get('wind')
        humidity_text='湿度 '+('—' if humidity is None else f'{humidity:.0f}%')
        wind_text='风 '+('—' if wind is None else f'{wind:.0f} km/h')
        if tight:
            text(p,QRectF(left,31,width-left-10,13),humidity_text,c['muted'],9)
            text(p,QRectF(left,44,width-left-10,13),wind_text,c['muted'],9)
        else:
            text(p,QRectF(left,36,width-left-10,16),humidity_text+'   '+wind_text,c['muted'],10)
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
            if step<26 and ':' in name:name=name.split(':',1)[0]+'时'
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
            center(22,name,9)
            if step<25 and day['condition']!='—':
                paint_weather_icon(p,QRectF(x+step/2-6,36,12,12),day,c['light'])
            else:
                center(36,day['condition'],9,True)
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
        names=('优','良','轻度污染','中度污染','重度污染','严重污染') if scale.startswith('中国') else ('良好','一般','敏感人群不健康','不健康','很不健康','严重')
        index,color=air_quality_style(aqi,c['light']) if aqi is not None else (-1,c['muted'])
        source=data.get('source','')
        source_label='上次读数' if data.get('stale') else '小时数据' if data.get('hourly') else source
        tight=width<220
        if tight:
            text(p,QRectF(10,4,width-72,16),'空气质量',c['ink'],11,True)
            text(p,QRectF(width-62,4,52,16),scale,c['muted'],9,False,Qt.AlignRight)
        else:
            text(p,QRectF(10,4,width-86,16),'空气质量 · '+scale,c['ink'],11,True)
            text(p,QRectF(width-74,4,64,16),source_label,c['muted'],8,False,Qt.AlignRight)
        text(p,QRectF(10,21,65,34),'—' if aqi is None else f'{aqi:.0f}',color,27,True)
        status=names[index] if aqi is not None else row.get('air_error','等待空气质量')
        left=65 if tight else 78
        text(p,QRectF(left,23 if tight else 27,width-left-10,20),status,color,10)
        if tight:
            text(p,QRectF(left,42,width-left-10,14),source_label,c['muted'],8)
        step=(width-20)/len(AIR_HUES)
        for i,hue in enumerate(AIR_HUES):
            ink=QColor(color if i==index else band_ink(.5,0,1,hue,c['light']));ink.setAlpha(230 if i==index else 70)
            p.setPen(Qt.NoPen);p.setBrush(ink);p.drawRoundedRect(QRectF(10+i*step,60,step-2,3),1.5,1.5)
        step=(width-20)/3
        for i,(key,label) in enumerate((('pm2_5','PM2.5'),('pm10','PM10'),('ozone','O₃'))):
            x=10+i*step;value=data.get(key);unit='μg/m³'
            if 'pollutants' in data:value,unit=data['pollutants'].get(key) or (None,'')
            text(p,QRectF(x,70,step,14),label,c['muted'],10)
            if tight and value is not None:
                text(p,QRectF(x,82,step,14),f'{value:g}',c['ink'],10,True)
                text(p,QRectF(x,96,step,12),unit,c['muted'],8)
            else:
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
        hour_label='时' if width<220 else '小时 '
        length_text='—' if length is None else f'{int(length)//3600}{hour_label}{int(length)%3600//60:02d}分'
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
        box.setAlignment(Qt.AlignTop)
        self.weather_head=QWidget();head=QHBoxLayout(self.weather_head);head.setContentsMargins(0,0,0,0);head.setSpacing(5)
        self.city=ModernComboBox();self.city.setAccessibleName('天气城市');self.city.setProperty('glassField',True)
        self.city.setMinimumWidth(94);self.city.setMaximumWidth(178);self.city.setFixedHeight(22)
        self.city.currentTextChanged.connect(self.city.setToolTip)
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
        if self.owner.service.extras:
            self.owner.service.extras.refresh_weather(refresh_location=True)
            self.refresh()
    def select_city(self,name):
        index=self.city.findText(name)
        if index>=0:self.city.setCurrentIndex(index)
    def refresh(self):
        service=self.owner.service;extra=service.extras
        self.setVisible(service.cfg['resource_weather'])
        self.refresh_button.setEnabled(not extra or extra.weather_job is None)
        names=extra.city_names() if extra else tuple(service.cfg['resource_weather_cities'])
        self.city.setEnabled(bool(names))
        if names!=getattr(self,'names',None):
            old=self.city.currentText()
            self.city.clear();self.city.addItems(list(names))
            if old in names:self.city.setCurrentIndex(names.index(old))
            self.names=names
        located=extra.located_city() if extra else None
        if located and located!=getattr(self,'located_city',None):self.select_city(located)
        self.located_city=located
        self.week.setChecked(service.cfg['resource_weather_days']==7)
        self.cards.refresh()
        stamp=max((r.get('updated',0) for r in extra.weather),default=0) if extra else 0
        sync_note_controls(self.remarks_button, self.notes, self.owner.colors)
        self.notes.setText('查看所选城市的天气、空气质量、日出日落和月相。天气来自 <a href="https://open-meteo.com/">Open-Meteo</a>，每 15 分钟刷新。天气持续时间由逐时预报估算。'
                           '逐时天气使用城市当地时间，雨雪量为截至该时的前一小时累计值。空气质量卡标注来源和 AQI 口径。'
                           +('更新于 '+time.strftime('%H:%M',time.localtime(stamp))+'。' if stamp else ''))
        self.notes.setVisible(self.remarks_button.isChecked())
