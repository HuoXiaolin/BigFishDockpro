"""The dates and colors shared by the agenda and desktop calendars."""
import calendar
from datetime import date
from functools import lru_cache

from PyQt5.QtCore import QPointF,Qt
from PyQt5.QtGui import QColor


MARKER_TONES={
    'local':('#56677a','#b4c1d2'), 'dingtalk':('#1763ba','#85baff'),
    'feishu':('#12745d','#67dcb3'), 'tencent':('#a6570c','#ffc17a'),
    'dida':('#4246ad','#adb5ff'), 'nexttodo':('#a3366d','#ffa7d4'),
    'countdown':('#8548a3','#e4afff'),
}


def countdowns(cfg):
    entries={}
    for key in ('clock_appearance','calendar_appearance'):
        for row in cfg.get(key,{}).get('progress',{}).get('countdowns',()):
            identity=row.get('id') or (row['title'],row['date'],row.get('time'),row['repeat'])
            entries.setdefault(identity,row)
    unique={}
    for row in entries.values():
        key=(row['title'],row['date'],row.get('time') or '',row['repeat'])
        unique.setdefault(key,row)
    return tuple(row for row in unique.values() if row.get('calendar',True))


def upcoming_countdowns(cfg,day,now=None):
    """Next occurrence of each shared countdown on the date being viewed."""
    from datetime import datetime,time
    moment=now if now and now.date()==day else datetime.combine(day,time.min)
    entries=tuple((row['title'],row['date'],row.get('time',''),row['repeat']) for row in countdowns(cfg))
    return _next_occurrences(entries,moment.replace(second=0,microsecond=0))


@lru_cache(maxsize=64)
def _next_occurrences(rows,minute):
    from clock_faces import countdown_window
    entries=[]
    for title,day,clock,repeat in rows:
        _,due=countdown_window(dict(date=day,time=clock,repeat=repeat),minute)
        if due.date()<minute.date() or (clock and due<minute):continue
        entries.append((due,title))
    return tuple((title,(due.date()-minute.date()).days) for due,title in sorted(entries,key=lambda item:item[0]))


def countdown_on(row,day):
    target=date.fromisoformat(row['date'])
    repeat=row['repeat']
    if repeat=='once':return day==target
    if repeat=='daily':return True
    if repeat=='weekly':return day.weekday()==target.weekday()
    if repeat=='yearly' and day.month!=target.month:return False
    return day.day==min(target.day,calendar.monthrange(day.year,day.month)[1])


def event_last_second(event):
    return event['start'] if event.get('timing') == 'deadline' else event['end'] - 1


def month_markers(events,items,first,days):
    start=first.toordinal()
    finish=min(date.max.toordinal(),start+days-1)
    result={}
    for event in events:
        first_day=max(start,date.fromtimestamp(event['start']).toordinal())
        last_day=min(finish,date.fromtimestamp(event_last_second(event)).toordinal())
        for number in range(first_day,last_day+1):
            result.setdefault(date.fromordinal(number),set()).add(event['source'])
    if items:
        for number in range(start,finish+1):
            day=date.fromordinal(number)
            if any(countdown_on(row,day) for row in items):
                result.setdefault(day,set()).add('countdown')
    return result


def paint_markers(p,cell,sources,light,holiday=None):
    colors=[tones[0 if light else 1] for source,tones in MARKER_TONES.items() if source in sources]
    if holiday is not None:colors.append(holiday)
    if not colors:return
    gap=1.6
    diameter=min(3.4,max(1.5,(cell.width()-4-gap*(len(colors)-1))/len(colors)))
    x=cell.center().x()-(diameter*len(colors)+gap*(len(colors)-1))/2
    p.setPen(Qt.NoPen)
    for color in colors:
        radius=diameter/2
        p.setBrush(QColor(color));p.drawEllipse(QPointF(x+radius,cell.bottom()-radius-1),radius,radius)
        x+=diameter+gap
