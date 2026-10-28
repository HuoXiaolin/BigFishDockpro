"""Offline work shifts and bounded holiday calendars; no timer or network access."""
import datetime as dt
import json,re,sys
from functools import lru_cache
from pathlib import Path

DEFAULTS={'start':'09:00','end':'18:00','calendar':'cn','weekdays':[0,1,2,3,4],
          'rest_dates':[],'work_dates':[],'calendars':{},'break_enabled':False,'break_start':'12:00','break_end':'13:00'}


def minute(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):raise ValueError('时间请使用 HH:mm 格式。')
    h,m=map(int,value.split(':'));return h*60+m


def dates(values,year=None):
    if not isinstance(values,list) or len(values)>800:raise ValueError('日期列表格式或数量无效。')
    result=[]
    for value in values:
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('日期请使用 YYYY-MM-DD 格式。')
        date=dt.date.fromisoformat(value)
        if year is not None and date.year!=year:raise ValueError('日期与年度日历的年份不一致。')
        result.append(date.isoformat())
    return sorted(set(result))


def validate_calendar(value):
    if not isinstance(value,dict) or type(value.get('year')) is not int or not 1900<=value['year']<=2199:raise ValueError('年度日历缺少有效年份。')
    year=value['year'];holidays=value.get('holidays',{});workdays=dates(value.get('workdays',[]),year)
    if not isinstance(holidays,dict):raise ValueError('放假日期应为日期和名称的对应表。')
    keys=dates(list(holidays),year)
    if set(keys)&set(workdays):raise ValueError('同一日期不能同时设置为放假和上班。')
    if any(not isinstance(holidays[key],str) or len(holidays[key])>40 for key in keys):raise ValueError('节假日名称无效。')
    return {'year':year,'holidays':{key:holidays[key] for key in keys},'workdays':workdays,'source':str(value.get('source','自定义日历'))[:160]}


@lru_cache(maxsize=8)
def builtin(year):
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    path=root/'assets/holidays'/('cn-%d.json'%year)
    if not path.is_file():return None
    try:return validate_calendar(json.loads(path.read_text(encoding='utf-8')))
    except (ValueError,OSError):return None


def normalize(value,strict=False):
    result=dict(DEFAULTS,weekdays=list(DEFAULTS['weekdays']),calendars={})
    try:
        if not isinstance(value,dict):value={}
        result.update({key:value[key] for key in DEFAULTS if key in value})
        start,end=minute(result['start']),minute(result['end'])
        if start==end:raise ValueError('上班和下班时间不能相同。')
        if result['calendar'] not in ('cn','weekdays','daily'):raise ValueError('工作日历模式无效。')
        days=result['weekdays']
        if not isinstance(days,list) or any(type(day) is not int or not 0<=day<=6 for day in days):raise ValueError('工作周设置无效。')
        result['weekdays']=sorted(set(days));result['rest_dates']=dates(result['rest_dates']);result['work_dates']=dates(result['work_dates'])
        if set(result['rest_dates'])&set(result['work_dates']):raise ValueError('额外休息日与上班日不能重复。')
        if type(result['break_enabled']) is not bool:raise ValueError('午休设置无效。')
        pause_start,pause_end=minute(result['break_start']),minute(result['break_end'])
        if result['break_enabled']:
            finish=end+(1440 if end<start else 0)
            if pause_start<start:pause_start+=1440
            if pause_end<=minute(result['break_start']):pause_end+=1440
            if pause_end<=pause_start:pause_end+=1440
            if not start<=pause_start<pause_end<=finish or pause_end-pause_start>=finish-start:raise ValueError('休息时段需在班次内，且不能占满整个班次。')
        calendars=result['calendars']
        if not isinstance(calendars,dict) or len(calendars)>20:raise ValueError('最多保留 20 份年度日历。')
        result['calendars']={}
        for year,row in calendars.items():
            normalized=validate_calendar(row)
            if str(normalized['year'])!=str(year):raise ValueError('年度日历索引与年份不一致。')
            result['calendars'][str(year)]=normalized
        return result
    except (ValueError,TypeError,OverflowError):
        if strict:raise
        return dict(DEFAULTS,weekdays=list(DEFAULTS['weekdays']),rest_dates=[],work_dates=[],calendars={})


def day_info(day,work):
    key=day.isoformat()
    if key in work['work_dates']:return True,'自定义上班',True
    if key in work['rest_dates']:return False,'自定义休息',True
    if work['calendar']=='daily':return True,'每日班次',True
    if work['calendar']=='cn':
        data=work['calendars'].get(str(day.year)) or builtin(day.year)
        if data:
            if key in data['workdays']:return True,'调休上班',True
            if key in data['holidays']:return False,data['holidays'][key],True
        known=data is not None
    else:known=True
    active=day.weekday() in work['weekdays']
    return active,('工作日' if active else '休息日'),known


def shift(day,work):
    start=dt.datetime.combine(day,dt.time())+dt.timedelta(minutes=minute(work['start']))
    end=dt.datetime.combine(day,dt.time())+dt.timedelta(minutes=minute(work['end']))
    if end<=start:end+=dt.timedelta(days=1)
    pauses=[]
    if work['break_enabled']:
        begin=dt.datetime.combine(day,dt.time())+dt.timedelta(minutes=minute(work['break_start']))
        if begin<start:begin+=dt.timedelta(days=1)
        finish=dt.datetime.combine(begin.date(),dt.time())+dt.timedelta(minutes=minute(work['break_end']))
        if finish<=begin:finish+=dt.timedelta(days=1)
        pauses=[(begin,finish)]
    return start,end,pauses


def duration(seconds):
    minutes=max(0,int((seconds+59)//60));hours,minutes=divmod(minutes,60)
    return ('%d小时'%hours if hours else '')+('%d分钟'%minutes if minutes or not hours else '')


def progress(now,value):
    work=normalize(value);day=now.date()
    overnight=minute(work['end'])<minute(work['start'])
    if overnight:
        previous=day-dt.timedelta(days=1);start,end,_=shift(previous,work)
        if start<=now<=end and day_info(previous,work)[0]:day=previous
    working,name,known=day_info(day,work);start,end,pauses=shift(day,work)
    result={'working':working,'name':name,'known':known,'shift_date':day.isoformat(),'start':start,'end':end,'ratio':None}
    if not working:
        result.update(state='rest',title='今天休息',detail=name,next_start=None)
        for offset in range(1,371):
            candidate=day+dt.timedelta(days=offset)
            if day_info(candidate,work)[0]:result['next_start']=shift(candidate,work)[0];break
        return result
    total=(end-start).total_seconds()-sum((b-a).total_seconds() for a,b in pauses)
    elapsed=max(0,min((now-start).total_seconds(),(end-start).total_seconds()))
    for a,b in pauses:elapsed-=max(0,(min(now,b)-max(start,a)).total_seconds()) if now>a else 0
    result['ratio']=max(0,min(1,elapsed/max(1,total)))
    if now<start:result.update(state='before',title='尚未上班',detail='距上班 '+duration((start-now).total_seconds()))
    elif now>=end:result.update(state='done',title='已下班',detail='今天辛苦了')
    elif any(a<=now<b for a,b in pauses):result.update(state='break',title='休息中',detail='距下班 '+duration((end-now).total_seconds()))
    else:result.update(state='working',title='下班进度',detail='还剩 '+duration((end-now).total_seconds()))
    return result
