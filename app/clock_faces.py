"""Pure day/week/month/year progress shared by clock renderers and checks."""
import calendar
import datetime

PROGRESS_ITEMS = (('work', '工作日 / 下班'), ('day', '今日'), ('week', '本周'),
                  ('month', '本月'), ('year', '本年'))
MAX_SECONDARY = 4
MAX_COUNTDOWNS = 8


def period_progress(now):
    day=(now.hour*60+now.minute)/1440
    return {'day':day,'week':(now.weekday()+day)/7,
            'month':(now.day-1+day)/calendar.monthrange(now.year,now.month)[1],
            'year':(now.timetuple().tm_yday-1+day)/(366 if calendar.isleap(now.year) else 365)}


def normalize_progress(value, legacy):
    if not isinstance(value,dict):
        return dict(primary='work' if legacy['show_work'] else '',
                    secondary=[key for key in ('week','month','year') if legacy['show_'+key]], countdowns=[])
    ids={key for key,_ in PROGRESS_ITEMS}
    rows=[]
    countdowns=value.get('countdowns',[])
    for row in countdowns[:MAX_COUNTDOWNS] if isinstance(countdowns,list) else []:
        if not isinstance(row,dict):continue
        identity,title,repeat=row.get('id'),row.get('title'),row.get('repeat')
        if not isinstance(identity,str) or not identity.isalnum() or len(identity)>40 or identity in ids:continue
        if not isinstance(title,str) or not title.strip() or repeat not in ('once','daily','weekly','monthly','yearly'):continue
        try:target=datetime.date.fromisoformat(row.get('date'))
        except (ValueError,TypeError):continue
        ids.add(identity)
        clock=row.get('time','')
        try:
            if len(clock)!=5 or datetime.time.fromisoformat(clock).strftime('%H:%M')!=clock:clock=''
        except (ValueError,TypeError):clock=''
        rows.append(dict(id=identity,title=title.strip()[:28],date=target.isoformat(),time=clock,repeat=repeat))
    primary=value.get('primary','')
    if not isinstance(primary,str) or primary not in ids:primary=''
    secondary=[]
    items=value.get('secondary',[])
    for key in items if isinstance(items,list) else []:
        if isinstance(key,str) and key in ids and key!=primary and key not in secondary:
            secondary.append(key)
            if len(secondary)==MAX_SECONDARY:break
    return dict(primary=primary,secondary=secondary,countdowns=rows)


def countdown_window(row,now):
    target=datetime.date.fromisoformat(row['date'])
    repeat=row['repeat']
    clock=datetime.time.fromisoformat(row.get('time') or '00:00')
    today=now.date()
    current=now.replace(second=0,microsecond=0) if row.get('time') else datetime.datetime.combine(today,clock)

    def combine(day):return datetime.datetime.combine(day,clock)

    if repeat=='once':return None,combine(target)
    if repeat in ('daily','weekly'):
        days=1 if repeat=='daily' else 7
        passed=0 if days==1 else (today.weekday()-target.weekday())%7
        previous=combine(today-datetime.timedelta(days=passed));delta=datetime.timedelta(days=days)
        return (previous-delta,previous) if current<=previous else (previous,previous+delta)

    def within(year,month):
        return combine(datetime.date(year,month,min(target.day,calendar.monthrange(year,month)[1])))

    if repeat=='monthly':
        def shifted(offset):
            year,month=divmod(today.year*12+today.month-1+offset,12)
            return within(year,month+1)
        this=shifted(0)
        return (shifted(-1),this) if current<=this else (this,shifted(1))
    this=within(today.year,target.month)
    return (within(today.year-1,target.month),this) if current<=this else (this,within(today.year+1,target.month))


def countdown_date(row,today):
    return countdown_window(row,datetime.datetime.combine(today,datetime.time.min))[1].date()


def countdown_display(row,now):
    previous,due=countdown_window(row,now)
    minute=now.replace(second=0,microsecond=0)
    ratio=None if previous is None else max(0,min(1,(minute-previous)/(due-previous)))
    if not row.get('time'):
        days=(due.date()-now.date()).days
        value='今天' if days==0 else f'{days} 天' if days>0 else f'已过 {-days} 天'
        return value,due.date().isoformat(),ratio
    minutes=int((due-minute).total_seconds()//60)
    if minutes<0:value='已到期'
    elif minutes==0:value='到点'
    elif minutes>=1440:
        days,hours=minutes//1440,minutes%1440//60
        value=f'{days}天 {hours}时' if hours else f'{days} 天'
    elif minutes>=60:value=f'{minutes//60}时 {minutes%60}分'
    else:value=f'{minutes} 分'
    return value,due.strftime('%m/%d %H:%M'),ratio


def next_countdown(progress,today):
    rows=[(countdown_date(row,today),row['title']) for row in progress['countdowns']]
    upcoming=[row for row in rows if row[0]>=today]
    if not upcoming:return ''
    date,title=min(upcoming,key=lambda row:row[0])
    days=(date-today).days
    return title+' · '+(f'{days} 天' if days else '今天')


def orbit_items(now,options):
    from work_schedule import progress as work_progress
    work=work_progress(now,options['work'])
    periods=period_progress(now)
    data={key:(label,f'{periods[key]:.0%}','',periods[key]) for key,label in PROGRESS_ITEMS if key in periods}
    data['work']=(work['title'],work['detail'].replace('还剩 ','').replace('分钟','分'),
                  options['work']['start']+' — '+options['work']['end'] if work['working'] else
                  '下次 '+work['next_start'].strftime('%m/%d %H:%M') if work.get('next_start') else '', work['ratio'])
    for row in options['progress']['countdowns']:
        value,due,ratio=countdown_display(row,now)
        data[row['id']]=(row['title'],value,due,ratio)
    return data,periods['day'],work['ratio']
