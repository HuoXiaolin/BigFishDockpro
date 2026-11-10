"""The dates and colors shared by the agenda and desktop calendars."""
import calendar
from datetime import date

from PyQt5.QtCore import QPointF,Qt
from PyQt5.QtGui import QColor


MARKER_TONES={
    'local':('#56677a','#b4c1d2'), 'dingtalk':('#1763ba','#85baff'),
    'feishu':('#12745d','#67dcb3'), 'tencent':('#a6570c','#ffc17a'),
    'countdown':('#8548a3','#e4afff'),
}


def countdowns(cfg):
    entries={}
    for key in ('clock_appearance','calendar_appearance'):
        for row in cfg.get(key,{}).get('progress',{}).get('countdowns',()):
            entries.setdefault((row['title'],row['date'],row['time'],row['repeat']),row)
    return tuple(entries.values())


def countdown_on(row,day):
    target=date.fromisoformat(row['date'])
    repeat=row['repeat']
    if repeat=='once':return day==target
    if repeat=='daily':return True
    if repeat=='weekly':return day.weekday()==target.weekday()
    if repeat=='yearly' and day.month!=target.month:return False
    return day.day==min(target.day,calendar.monthrange(day.year,day.month)[1])


def month_markers(events,items,first,days):
    start=first.toordinal()
    finish=min(date.max.toordinal(),start+days-1)
    result={}
    for event in events:
        first_day=max(start,date.fromtimestamp(event['start']).toordinal())
        last_day=min(finish,date.fromtimestamp(event['end']-1).toordinal())
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
