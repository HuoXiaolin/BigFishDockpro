"""Offline illustrations, verses and Chinese civil dates for the desktop almanac."""
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from types import MappingProxyType
import json
from pathlib import Path
import sys

from almanac_verses import VERSES
from calendar_details import civil_festivals, lunar_details, next_civil_festivals

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'almanac'
FIRST_DAY, LAST_DAY = date(1901, 1, 1), date(2099, 12, 31)

# Names stay in atlas order: the same index selects both illustration editions.
SEASONS = {
    'spring': '立春 雨水 惊蛰 春分 清明 谷雨'.split(),
    'summer': '立夏 小满 芒种 夏至 小暑 大暑'.split(),
    'autumn': '立秋 处暑 白露 秋分 寒露 霜降'.split(),
    'winter': '立冬 小雪 大雪 冬至 小寒 大寒'.split(),
}
FESTIVALS = {
    'festivals-a': '春节 元宵节 龙抬头 端午节 七夕 中元节'.split(),
    'festivals-b': '中秋节 重阳节 腊八节 北方小年 南方小年 除夕'.split(),
}


@dataclass(frozen=True)
class Illustration:
    name: str
    key: str
    verses: tuple


ART = {name: Illustration(name, f'{group}-{index}', VERSES[name])
       for group, names in (SEASONS | FESTIVALS).items() for index, name in enumerate(names, 1)}

_CIVIL_ART = {
    (1, 1): ('元旦','new-year'), (3, 8): ('妇女节','womens-day'), (3, 12): ('植树节','arbor-day'),
    (5, 1): ('劳动节','labour-day'), (5, 4): ('青年节','youth-day'), (6, 1): ('儿童节','childrens-day'),
    (9, 10): ('教师节','teachers-day'), (10, 1): ('国庆节','national-day'),
}
CIVIL_HOLIDAYS = {day: Illustration(name, 'civil-'+key, VERSES[name]) for day,(name,key) in _CIVIL_ART.items()}
ART.update((art.name, art) for art in CIVIL_HOLIDAYS.values())
_names = tuple(name for names in SEASONS.values() for name in names)
JANUARY_ORDER = _names[-2:] + _names[:-2]


@lru_cache(maxsize=1)
def _table():
    payload = json.loads((ASSETS / 'solar-terms.json').read_text(encoding='utf-8'))
    return payload['first_year'], payload['years']


@lru_cache(maxsize=4)
def term_dates(year):
    first, years = _table()
    if not 0 <= year-first < len(years):
        return ()
    digits = years[year-first]
    return tuple((date(year, i//2+1, int(digits[2*i:2*i+2])), name)
                 for i, name in enumerate(JANUARY_ORDER))


@lru_cache(maxsize=16)
def next_festival(day):
    for i in range(1, min(366, (LAST_DAY-day).days)+1):
        on = day + timedelta(days=i)
        name = lunar_details(on)[2]
        if name:
            return name, i
    return '', 0


def next_civil_holiday(day):
    names, distance = next_civil_festivals(day)
    return '、'.join(names), distance


ROTATION_MINUTES = 10


def verse_index(now):
    return (now.hour*60 + now.minute) // ROTATION_MINUTES % 4


def edition(now):
    return verse_index(now) % 2


def until_rotation(now):
    boundary = now.replace(second=0, microsecond=0) + timedelta(minutes=ROTATION_MINUTES-now.minute%ROTATION_MINUTES)
    return max(1, int((boundary-now).total_seconds()*1000)+1)


@dataclass(frozen=True)
class AlmanacDay:
    day: date
    lunar: str
    term: str
    term_today: bool
    next_term: str
    days_left: int
    festival: str
    civil_names: tuple

    @property
    def civil_festival(self):
        return '、'.join(self.civil_names)

    @property
    def events(self):
        return tuple(filter(None, (*self.civil_names, self.festival, self.term if self.term_today else '')))

    def card(self, choice=0):
        events = self.events
        name = events[choice % len(events)] if events else self.term
        if name in ART:
            return ART[name]
        seasonal = ART[self.term]
        return Illustration(name, seasonal.key, VERSES[name])

    def civil_countdown(self):
        if self.civil_festival:
            return f'今日{self.civil_festival}'
        holiday, distance = next_civil_holiday(self.day)
        return f'距{holiday} {distance} 天'

    def badge_due(self, categories):
        return (('term' in categories and self.term_today) or ('lunar' in categories and bool(self.festival))
                or ('civil' in categories and bool(self.civil_names)))

    @lru_cache(maxsize=64)
    def badge_lines(self, categories=('term','lunar','civil')):
        entries = []
        if 'term' in categories:
            entries.append((self.term, 0) if self.term_today else (self.next_term, self.days_left))
        if 'lunar' in categories:
            entries.append((self.festival, 0) if self.festival else next_festival(self.day))
        if 'civil' in categories:
            civil, days = (self.civil_names, 0) if self.civil_names else next_civil_festivals(self.day)
            entries.extend((name, days) for name in civil)
        # Start with today's event, then keep cycling through the three calendars.
        start = next((i for i, (name, left) in enumerate(entries) if name and left == 0), 0)
        rows = {}
        for name, left in entries[start:] + entries[:start]:
            if name:
                short = '新春' if name == '春节' else name.removesuffix('节')
                countdown = f'{left}天' if left else '今天'
                rows[short+countdown if left else short] = (short,countdown)
        return MappingProxyType(rows)

    def badge_labels(self, categories=('term','lunar','civil')):
        return tuple(self.badge_lines(categories))

    def badge(self, page=0):
        labels = self.badge_labels()
        return labels[page % len(labels)]


@lru_cache(maxsize=32)
def almanac(day):
    if not FIRST_DAY <= day <= LAST_DAY:
        return None
    entries = term_dates(day.year-1) + term_dates(day.year) + term_dates(day.year+1)
    at = bisect_right(entries, day, key=lambda entry: entry[0])
    previous, term = entries[at-1] if at else (None, '冬至')
    upcoming, name = entries[at]
    _, lunar, festival = lunar_details(day)
    return AlmanacDay(day, lunar, term, previous == day, name, (upcoming-day).days, festival, civil_festivals(day))
