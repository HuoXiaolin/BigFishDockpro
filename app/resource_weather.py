"""Small Open-Meteo forecasts; no location permission, key, or large cache."""
import json
import math
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from PyQt5.QtCore import pyqtSignal
from background_worker import BackgroundWorker

DEFAULT_CITIES=['天津','乌鲁木齐','沈阳']
KNOWN={'天津':(39.14222,117.17667),'乌鲁木齐':(43.80096,87.60046),'沈阳':(41.79222,123.43278)}
AIR_FIELDS=('us_aqi','pm2_5','pm10','ozone')
WEATHER_ERRORS=(OSError,ValueError,TypeError,KeyError,AttributeError,IndexError)
SHANGHAI_OFFSET=8*3600


def clean_cities(value,strict=False):
    valid=isinstance(value,list) and len(value)<=6 and all(isinstance(n,str) and 0<len(n.strip())<=40 and not any(ord(c)<32 for c in n) for n in value)
    if not valid:
        if strict:raise ValueError('天气城市最多 6 个，每个城市名称不超过 40 字。')
        return list(DEFAULT_CITIES)
    return list(dict.fromkeys(n.strip() for n in value))


def fetch_json(url,headers=None):
    from urllib.request import Request,urlopen
    limit=256*1024
    request=Request(url,headers={'User-Agent':'BigFishDockpro/1.1 (weather)','Accept':'application/json'})
    for name,value in (headers or {}).items():request.add_unredirected_header(name,value)
    with urlopen(request,timeout=6) as response:
        data=response.read(limit+1)
        encoding=response.headers.get('Content-Encoding','').lower()
    if len(data)<=limit and encoding=='gzip':
        from gzip import GzipFile
        from io import BytesIO
        with GzipFile(fileobj=BytesIO(data)) as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('Weather response too large')
    value=json.loads(data)
    if not isinstance(value,(dict,list)):raise ValueError('Invalid weather response')
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


def locate(name,lookup):
    coordinates=KNOWN.get(name)
    if coordinates is None:
        found=lookup('https://geocoding-api.open-meteo.com/v1/search?'+urlencode(dict(name=name,count=1,language='zh'))).get('results') or []
        if not found:raise ValueError('未找到城市')
        row=found[0];coordinates=(number(row.get('latitude')),number(row.get('longitude')))
        if any(n is None for n in coordinates):raise ValueError('城市坐标无效')
    return coordinates


def forecast(name,lookup=fetch_json,coordinates=None):
    coordinates=coordinates or locate(name,lookup)
    lat,lon=coordinates
    raw=lookup('https://api.open-meteo.com/v1/forecast?'+urlencode(dict(latitude=lat,longitude=lon,
        current='temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m,apparent_temperature',
        hourly='temperature_2m',
        daily='temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,sunrise,sunset,daylight_duration',
        timezone='auto',forecast_days=7,past_days=1)))
    if not isinstance(raw,dict):raise ValueError('天气暂无读数')
    current=raw.get('current') or {};daily=raw.get('daily') or {};days=[]
    sampled=str(current.get('time',''))[:19]
    for i,day in enumerate((daily.get('time') or [])[:8]):
        def at(key, convert=number):
            values=daily.get(key) or []
            return convert(values[i]) if len(values)>i and values[i] is not None else None
        code=at('weather_code')
        days.append(dict(date=str(day)[:10],low=at('temperature_2m_min'),high=at('temperature_2m_max'),
                         code=code,condition=condition(code),rain=at('precipitation_probability_max'),
                         sunrise=at('sunrise',str),sunset=at('sunset',str),daylight=at('daylight_duration')))
    temp=number(current.get('temperature_2m'))
    if temp is None:raise ValueError('天气暂无读数')
    hourly=raw.get('hourly') or {};hours=[]
    if sampled:
        for stamp,value in zip(hourly.get('time') or [],hourly.get('temperature_2m') or []):
            if isinstance(stamp,str) and stamp>sampled[:16]:
                hours.append((stamp[11:16],number(value)))
                if len(hours)>=6:break
    offset=raw.get('utc_offset_seconds')
    if type(offset) is not int or abs(offset)>=86400:offset=SHANGHAI_OFFSET
    return dict(name=name,temperature=temp,code=current.get('weather_code'),condition=condition(current.get('weather_code')),days=days,
                humidity=number(current.get('relative_humidity_2m')),wind=number(current.get('wind_speed_10m')),
                feels=number(current.get('apparent_temperature')),hours=hours,sampled=sampled,
                utc_offset_seconds=offset,updated=time.time())


def weather_time(row):
    # Sunrise and sunset from this response use the same fixed offset.
    return datetime.now(timezone(timedelta(seconds=row.get('utc_offset_seconds',SHANGHAI_OFFSET))))


def measurement(value):
    result=number(value)
    return result if result is not None and result>=0 else None


def air_quality(coordinates,lookup=fetch_json,hourly=False):
    if not coordinates:return {}
    lat,lon=zip(*coordinates.values())
    query=dict(latitude=','.join(map(str,lat)),longitude=','.join(map(str,lon)),timezone='Asia/Shanghai')
    if hourly:query.update(hourly=','.join(AIR_FIELDS),domains='cams_global',past_hours=6,forecast_hours=1)
    else:query['current']=','.join(AIR_FIELDS)
    raw=lookup('https://air-quality-api.open-meteo.com/v1/air-quality?'+urlencode(query))
    rows=[raw] if isinstance(raw,dict) else raw
    if len(rows)!=len(coordinates):return {}
    result={}
    for name,row in zip(coordinates,rows):
        if not isinstance(row,dict):continue
        current=latest_air_hour(row.get('hourly',{})) if hourly else row.get('current')
        if not isinstance(current,dict):continue
        values={key:measurement(current.get(key)) for key in AIR_FIELDS}
        if any(value is not None for value in values.values()):
            result[name]=dict(values,source='Open-Meteo',scale='US AQI',hourly=hourly,received=time.time())
    return result


def latest_air_hour(hourly):
    if not isinstance(hourly,dict):return None
    now=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='minutes')[:16]
    times=hourly.get('time') or []
    for index in reversed(range(len(times))):
        if not isinstance(times[index],str) or times[index]>now:continue
        values={key:series[index] if isinstance(series,list) and index<len(series) else None
                for key in AIR_FIELDS for series in (hourly.get(key),)}
        if any(measurement(value) is not None for value in values.values()):return values
    return None


def qweather_air(coordinates,host,key,lookup=fetch_json):
    lat,lon=coordinates
    raw=lookup(f'https://{host}/airquality/v1/current/{lat:.2f}/{lon:.2f}?lang=zh',
               {'X-QW-Api-Key':key,'Accept-Encoding':'gzip'})
    if not isinstance(raw,dict):return None
    indexes={entry.get('code'):entry for entry in raw.get('indexes',[]) if isinstance(entry,dict)}
    for code,scale in (('cn-mee','中国 AQI'),('cn-mee-1h','中国 AQI · 1 小时'),('us-epa','US AQI')):
        entry=indexes.get(code,{})
        aqi=measurement(entry.get('aqi'))
        if aqi is not None:break
    else:return None
    concentrations={}
    for pollutant in raw.get('pollutants',[]):
        if not isinstance(pollutant,dict):continue
        reading=pollutant.get('concentration') or {}
        value=measurement(reading.get('value'))
        unit=reading.get('unit')
        if value is not None and unit in ('μg/m3','µg/m3','μg/m³','ppb','ppm'):
            concentrations[pollutant.get('code')]=(value,unit.replace('m3','m³').replace('µ','μ'))
    return dict(aqi=aqi,scale=scale,source='和风天气',received=time.time(),
                pollutants={key:concentrations.get(code) for key,code in (('pm2_5','pm2p5'),('pm10','pm10'),('ozone','o3'))})


def moon_phase(stamp):
    try:local=datetime.fromisoformat(stamp)
    except (TypeError,ValueError):return '',None
    if local.tzinfo is None:local=local.replace(tzinfo=timezone(timedelta(hours=8)))
    epoch=datetime(2000,1,6,18,14,tzinfo=timezone.utc)
    phase=((local-epoch).total_seconds()/86400/29.530588853)%1
    names=('新月','蛾眉月','上弦月','盈凸月','满月','亏凸月','下弦月','残月')
    return names[int(phase*8+.5)%8],round((1-math.cos(phase*2*math.pi))*50)


class WeatherJob(BackgroundWorker):
    ready=pyqtSignal(object)
    def __init__(self,cities,source='auto',connection=('', '')):
        super().__init__();self.cities=list(cities);self.source=source;self.connection=connection

    def read_air(self,locations):
        if self.source=='qweather':
            if not all(self.connection):return {},'请配置和风天气连接'
            result={}
            for name,coordinates in locations.items():
                if self.cancelled.is_set():break
                try:
                    if row:=qweather_air(coordinates,*self.connection):result[name]=row
                except WEATHER_ERRORS:pass
            return result,'和风天气暂不可用'
        result={}
        if self.source=='auto':
            try:result=air_quality(locations)
            except WEATHER_ERRORS:pass
        missing={name:coords for name,coords in locations.items() if result.get(name,{}).get('us_aqi') is None}
        for name,coordinates in missing.items():
            if self.cancelled.is_set():break
            try:result.update(air_quality({name:coordinates},hourly=True))
            except WEATHER_ERRORS:pass
        return result,'Open-Meteo 暂不可用'

    def run(self):
        rows=[];locations={}
        for city in self.cities:
            if self.cancelled.is_set():return
            try:
                coordinates=locate(city,fetch_json)
                locations[city]=coordinates
                row=forecast(city,coordinates=coordinates)
            except WEATHER_ERRORS:row=dict(name=city,error='暂时无法更新')
            rows.append(row)
        if self.cancelled.is_set():return
        air,error=self.read_air(locations)
        for row in rows:
            if row['name'] in air:row['air']=air[row['name']]
            else:row['air_error']=error
        if not self.cancelled.is_set():self.ready.emit(rows)
