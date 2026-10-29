"""Offline lunar labels and holiday markers, independent from weekly rest days."""
import datetime as dt
from functools import lru_cache
from lunardate import LunarDate
from work_schedule import builtin,normalize

SOLAR={(1,1):'元旦',(5,1):'劳动节',(5,4):'青年节',(6,1):'儿童节',(7,1):'建党节',(8,1):'建军节',(9,10):'教师节',(10,1):'国庆节'}
LUNAR={(1,1):'春节',(1,15):'元宵节',(2,2):'龙抬头',(5,5):'端午节',(7,7):'七夕',(7,15):'中元节',(8,15):'中秋节',(9,9):'重阳节',(12,8):'腊八节'}


def day_name(day):
    if day==10:return '初十'
    if day==20:return '二十'
    if day==30:return '三十'
    return ('初','十','廿')[day//10]+'一二三四五六七八九'[day%10-1]


@lru_cache(maxsize=768)
def lunar(day):
    if not 1900<=day.year<=2099:return '', ''
    try:
        value=LunarDate.from_solar_date(day.year,day.month,day.day)
        month=('闰' if value.is_leap_month else '')+'正二三四五六七八九十冬腊'[value.month-1]+'月'
        label=month if value.day==1 else day_name(value.day)
        festival=LUNAR.get((value.month,value.day),'') if not value.is_leap_month else ''
        tomorrow=day+dt.timedelta(days=1);next_day=LunarDate.from_solar_date(tomorrow.year,tomorrow.month,tomorrow.day)
        if next_day.month==1 and next_day.day==1 and not next_day.is_leap_month:festival='除夕'
        return label,festival
    except (ValueError,OverflowError):return '', ''


def info(day,work):
    options=normalize(work);data=options['calendars'].get(str(day.year)) or builtin(day.year)
    key=day.isoformat();lunar_label,lunar_festival=lunar(day);festival=SOLAR.get((day.month,day.day),'') or lunar_festival
    public=data['holidays'].get(key,'') if data else '';makeup=bool(data and key in data['workdays'])
    return {'lunar':lunar_label,'name':festival or public,'marker':bool(festival or public) and not makeup,'makeup':makeup,'known':data is not None}
