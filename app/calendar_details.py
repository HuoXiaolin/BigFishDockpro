"""Offline lunar labels and holiday markers, independent from weekly rest days."""
import datetime as dt
from functools import lru_cache
from lunardate import LunarDate
from work_schedule import builtin,normalize

SOLAR = {
    (1, 1): '元旦', (2, 14): '情人节', (3, 8): '妇女节', (3, 12): '植树节',
    (4, 1): '愚人节', (5, 1): '劳动节', (5, 4): '青年节', (5, 12): '护士节',
    (6, 1): '儿童节', (7, 1): '建党节', (8, 1): '建军节', (9, 10): '教师节',
    (10, 1): '国庆节', (10, 31): '万圣夜', (11, 1): '万圣节',
    (12, 24): '平安夜', (12, 25): '圣诞节',
}
# Month, occurrence in the month, weekday (Monday = 0).
WEEKDAY_FESTIVALS = (
    (5, 2, 6, '母亲节'), (6, 3, 6, '父亲节'), (11, 4, 3, '感恩节'),
)
LUNAR = {
    (1, 1): '春节', (1, 15): '元宵节', (2, 2): '龙抬头', (3, 3): '上巳节',
    (5, 5): '端午节', (7, 7): '七夕', (7, 15): '中元节', (8, 15): '中秋节',
    (9, 9): '重阳节', (10, 1): '寒衣节', (10, 15): '下元节', (12, 8): '腊八节',
    (12, 23): '北方小年', (12, 24): '南方小年',
}


@lru_cache(maxsize=8)
def _civil_year(year):
    by_date = {dt.date(year, month, day): (name,) for (month, day), name in SOLAR.items()}
    for month, occurrence, weekday, name in WEEKDAY_FESTIVALS:
        first = dt.date(year, month, 1)
        on = first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (occurrence - 1))
        by_date[on] = (*by_date.get(on, ()), name)
    return dict(sorted(by_date.items()))


def civil_festivals(day):
    return _civil_year(day.year).get(day, ())


@lru_cache(maxsize=32)
def next_civil_festivals(day):
    for year in range(day.year, min(day.year + 1, dt.MAXYEAR) + 1):
        for on, names in _civil_year(year).items():
            if on > day:
                return names, (on - day).days
    return (), 0


def day_name(day):
    if day==10:return '初十'
    if day==20:return '二十'
    if day==30:return '三十'
    return ('初','十','廿')[day//10]+'一二三四五六七八九'[day%10-1]


@lru_cache(maxsize=768)
def lunar_details(day):
    if not dt.date(1900,1,31)<=day<=dt.date(2099,12,31):return '', '', ''
    try:
        value=LunarDate.from_solar_date(day.year,day.month,day.day)
        month=('闰' if value.is_leap_month else '')+'正二三四五六七八九十冬腊'[value.month-1]+'月'
        label=month if value.day==1 else day_name(value.day)
        festival=LUNAR.get((value.month,value.day),'') if not value.is_leap_month else ''
        if value.month==12 and value.day>=29:
            tomorrow=day+dt.timedelta(days=1);next_day=LunarDate.from_solar_date(tomorrow.year,tomorrow.month,tomorrow.day)
            if next_day.month==1 and next_day.day==1 and not next_day.is_leap_month:festival='除夕'
        return label,month+day_name(value.day),festival
    except (ValueError,OverflowError):return '', '', ''


def lunar(day):
    label,_,festival=lunar_details(day)
    return label,festival


def info(day,work):
    options=normalize(work);data=options['calendars'].get(str(day.year)) or builtin(day.year)
    key=day.isoformat();lunar_label,lunar_festival=lunar(day)
    festival='、'.join(filter(None, (*civil_festivals(day), lunar_festival)))
    public=data['holidays'].get(key,'') if data else '';makeup=bool(data and key in data['workdays'])
    return {'lunar':lunar_label,'name':festival or public,'marker':bool(festival or public) and not makeup,'makeup':makeup,'known':data is not None}
