"""Compact weather cards with a local forecast and source notes."""
import math
import time
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QColor,QPainter
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton
from resource_compact import text


def degrees(value):return '—' if value is None else f'{value:.0f}°'


def weather_days(row,count):
    from datetime import date,timedelta
    try:today=date.fromisoformat(row.get('sampled','')[:10])
    except ValueError:today=date.today()
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
    def __init__(self,owner):super().__init__();self.owner=owner;self.rows=[];self.columns=3
    def refresh(self):
        service=self.owner.service;extra=service.extras;by_name={r['name']:r for r in extra.weather} if extra else {}
        self.rows=[by_name.get(name,dict(name=name)) for name in service.cfg['resource_weather_cities']]
        self.layout_cards();self.update()
    def layout_cards(self):
        self.columns=max(1,min(3,self.width()//145,len(self.rows) or 1))
        self.card_height=58+18*self.owner.service.cfg['resource_weather_days']
        self.setFixedHeight((self.card_height+6)*math.ceil(len(self.rows)/self.columns) if self.rows else 0)
    def resizeEvent(self,event):self.layout_cards();super().resizeEvent(event)
    def paintEvent(self,event):
        if not self.rows:return
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing);c=self.owner.colors
        columns=self.columns;span=self.width()/columns
        for i,row in enumerate(self.rows):
            x=i%columns*span;y=i//columns*(self.card_height+6);r=QRectF(x,y,span-6,self.card_height)
            from resource_weather_style import paint_weather
            paint_weather(p,r,row,c['light'],c['hover'])
            def label(value,top,height=16,size=10,color='ink',bold=False):
                text(p,QRectF(x+9,y+top,span-24,height),value,c[color],size,bold)
            label(row['name']+(' · 待更新' if row.get('error') and row.get('temperature') is not None else ''),5,color='muted')
            label((degrees(row['temperature'])+'  '+row['condition']) if 'temperature' in row else row.get('error','等待天气'),22,23,16,bold=True)
            days=weather_days(row,self.owner.service.cfg['resource_weather_days'])
            for index,(name,day) in enumerate(days):
                top=y+51+index*18
                text(p,QRectF(x+9,top,28,16),name,c['muted'],9)
                text(p,QRectF(x+39,top,max(26,span-111),16),day['condition'],c['muted'],9)
                text(p,QRectF(x+span-70,top,54,16),degrees(day['low'])+' / '+degrees(day['high']),c['ink'],9,False,Qt.AlignRight)


class WeatherView(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0);box.setSpacing(4)
        self.weather_head=QWidget();head=QHBoxLayout(self.weather_head);head.setContentsMargins(0,0,0,0);head.addWidget(QLabel('天气'),1)
        self.refresh_button=QToolButton();self.refresh_button.setText('刷新');self.refresh_button.clicked.connect(self.refresh_weather);head.addWidget(self.refresh_button)
        box.addWidget(self.weather_head);self.cards=WeatherCards(owner);box.addWidget(self.cards)
        self.remarks_button=QToolButton();self.remarks_button.setText('备注');self.remarks_button.setCheckable(True);self.remarks_button.toggled.connect(self.toggle_notes)
        box.addWidget(self.remarks_button,0,Qt.AlignLeft);self.notes=QLabel();self.notes.setTextFormat(Qt.RichText);self.notes.setOpenExternalLinks(True)
        self.notes.setWordWrap(True);self.notes.setObjectName('Subtle');box.addWidget(self.notes);self.notes.hide()
    def toggle_notes(self,on):self.notes.setVisible(on)
    def refresh_weather(self):
        if self.owner.service.extras:self.owner.service.extras.refresh_weather();self.refresh()
    def refresh(self):
        service=self.owner.service;extra=service.extras
        self.setVisible(service.cfg['resource_weather'])
        self.refresh_button.setEnabled(not extra or extra.weather_job is None)
        self.cards.refresh()
        stamp=max((r.get('updated',0) for r in extra.weather),default=0) if extra else 0
        self.notes.setText('天气：<a href="https://open-meteo.com/">Open-Meteo</a>，北京时间；每 15 分钟更新。'
                           +('更新于 '+time.strftime('%H:%M',time.localtime(stamp))+'。' if stamp else ''))
        self.notes.setVisible(self.remarks_button.isChecked())
