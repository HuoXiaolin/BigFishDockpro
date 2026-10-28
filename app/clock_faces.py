"""Pure day/week/month/year progress shared by clock renderers and checks."""
import calendar
import datetime


def period_progress(now):
    day=(now.hour*60+now.minute)/1440
    return {'day':day,'week':(now.weekday()+day)/7,
            'month':(now.day-1+day)/calendar.monthrange(now.year,now.month)[1],
            'year':(now.timetuple().tm_yday-1+day)/(366 if calendar.isleap(now.year) else 365)}
