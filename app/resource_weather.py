"""Small Open-Meteo forecasts; no location permission, key, or large cache."""
import json
import math
import time
from PyQt5.QtCore import pyqtSignal
from background_worker import BackgroundWorker

DEFAULT_CITIES=['天津','乌鲁木齐','沈阳']
KNOWN={'天津':(39.14222,117.17667),'乌鲁木齐':(43.80096,87.60046),'沈阳':(41.79222,123.43278)}


def clean_cities(value,strict=False):
    valid=isinstance(value,list) and len(value)<=6 and all(isinstance(n,str) and 0<len(n.strip())<=40 and not any(ord(c)<32 for c in n) for n in value)
    if not valid:
        if strict:raise ValueError('天气城市最多 6 个，每个城市名称不超过 40 字。')
        return list(DEFAULT_CITIES)
    return list(dict.fromkeys(n.strip() for n in value))


def fetch_json(url):
    from urllib.request import Request,urlopen
    request=Request(url,headers={'User-Agent':'BigFishDockpro/1.1 (weather)','Accept':'application/json'})
    with urlopen(request,timeout=6) as response:data=response.read(256*1024+1)
    if len(data)>256*1024:raise ValueError('Weather response too large')
    value=json.loads(data)
    if not isinstance(value,dict):raise ValueError('Invalid weather response')
    return value


def condition(code):
    if code==0:return '晴'
    if code in (1,2,3):return '多云' if code!=3 else '阴'
    if code in (45,48):return '雾'
    if code in (51,53,55,56,57):return '毛毛雨'
    if code in (61,63,65,66,67,80,81,82):return '雨'
    if code in (71,73,75,77,85,86):return '雪'
    if code in (95,96,99):return '雷雨'
    return '—'


def number(value):
    return float(value) if type(value) in (float,int) and math.isfinite(value) else None


def forecast(name,lookup=fetch_json):
    from urllib.parse import urlencode
    coordinates=KNOWN.get(name)
    if coordinates is None:
        found=lookup('https://geocoding-api.open-meteo.com/v1/search?'+urlencode(dict(name=name,count=1,language='zh'))).get('results') or []
        if not found:raise ValueError('未找到城市')
        row=found[0];coordinates=(number(row.get('latitude')),number(row.get('longitude')))
        if any(n is None for n in coordinates):raise ValueError('城市坐标无效')
    lat,lon=coordinates
    raw=lookup('https://api.open-meteo.com/v1/forecast?'+urlencode(dict(latitude=lat,longitude=lon,
        current='temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m',
        daily='temperature_2m_max,temperature_2m_min,weather_code',timezone='Asia/Shanghai',forecast_days=7,past_days=1)))
    current=raw.get('current') or {};daily=raw.get('daily') or {};days=[]
    for i,day in enumerate((daily.get('time') or [])[:8]):
        def at(key):
            values=daily.get(key) or [];return number(values[i]) if len(values)>i else None
        days.append(dict(date=str(day)[:10],low=at('temperature_2m_min'),high=at('temperature_2m_max'),condition=condition(at('weather_code'))))
    temp=number(current.get('temperature_2m'))
    if temp is None:raise ValueError('天气暂无读数')
    return dict(name=name,temperature=temp,code=current.get('weather_code'),condition=condition(current.get('weather_code')),days=days,
                humidity=number(current.get('relative_humidity_2m')),wind=number(current.get('wind_speed_10m')),
                sampled=str(current.get('time',''))[:19],updated=time.time())


class WeatherJob(BackgroundWorker):
    ready=pyqtSignal(object)
    def __init__(self,cities):super().__init__();self.cities=list(cities)
    def run(self):
        rows=[]
        for city in self.cities:
            if self.cancelled.is_set():return
            try:row=forecast(city)
            except (OSError,ValueError,TypeError,KeyError):row=dict(name=city,error='暂时无法更新')
            rows.append(row)
        if not self.cancelled.is_set():self.ready.emit(rows)
