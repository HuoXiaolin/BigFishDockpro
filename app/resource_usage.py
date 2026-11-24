"""Pure aggregation of metering records. Missing fields stay unknown, not zero."""
from datetime import date,timedelta

FIELDS=('tokens','input','output','cacheRead','cacheWrite','records')
HEATMAP_WEEKS=26


def combine(rows):
    rows=list(rows);result={key:sum(row.get(key,0) or 0 for row in rows) if all(row.get(key) is not None for row in rows) else None for key in FIELDS}
    result.update(cost=sum(row.get('cost') or 0 for row in rows) if not rows or any(row.get('cost') is not None for row in rows) else None,
                  unpriced=sum(row.get('unpriced',0) for row in rows),estimated=any(row.get('estimated',False) for row in rows))
    prompt=sum(result.get(k) or 0 for k in ('input','cacheRead','cacheWrite'))
    result['cacheRate']=100*result['cacheRead']/prompt if prompt and all(result.get(k) is not None for k in ('input','cacheRead','cacheWrite')) else None
    return result


def bounds(period,today=None):
    today=today or date.today()
    end=today-timedelta(days=1) if period=='yesterday' else today
    return (None if period=='all' else end-timedelta(days={'week':6,'month':29}.get(period,0))),end


def heatmap_days(providers, provider='', today=None):
    today = today or date.today()
    first = today - timedelta(days=today.weekday() + 7*(HEATMAP_WEEKS-1))
    lower, upper = first.isoformat(), today.isoformat()
    daily = {}
    covered_since = today + timedelta(days=1)
    for source in providers:
        if (provider and source['id'] != provider) or not source.get('usageAvailable'):
            continue
        for row in source.get('days', ()):
            day = row.get('date')
            if isinstance(day, str) and lower <= day <= upper:
                daily.setdefault(day, []).append(row['summary'])
        if source.get('usageComplete') and source.get('historyStart'):
            try:
                covered_since = min(covered_since, date.fromisoformat(source['historyStart']))
            except (TypeError, ValueError):
                pass
    empty = combine(())
    days = []
    for offset in range((today-first).days+1):
        day = first + timedelta(days=offset)
        readings = daily.get(day.isoformat())
        days.append((day, combine(readings) if readings else empty if day >= covered_since else None))
    return days


def aggregate(providers,period='today',provider='',today=None):
    start,end=bounds(period,today);selected=[p for p in providers if not provider or p['id']==provider]
    groups=[];daily={};models={};hourly=period in ('today','yesterday');magpie=False
    for p in selected:
        summaries=[]
        for row in p.get('days',[]):
            try:day=date.fromisoformat(row['date'])
            except (KeyError,ValueError):continue
            if day>end or start and day<start:continue
            summary=row['summary'];summaries.append(summary)
            magpie=magpie or row.get('magpie',False)
            if not hourly:daily.setdefault(row['date'],[]).append(summary)
            models.setdefault((p['name'],row['model']),[]).append(summary)
        if not summaries and (reported:=p.get('periods',{}).get(period)) is not None:
            summaries.append(reported)
        if hourly:
            for row in p.get('hours',[]):
                if row['date'][:10]==end.isoformat():daily.setdefault(row['date'],[]).append(row['summary'])
            # Older helper snapshots have daily totals, not invented hourly points.
            if not p.get('hours') and summaries:daily.setdefault(end.isoformat(),[]).extend(summaries)
        available=p.get('usageAvailable',False) and ('periods' not in p or bool(summaries))
        groups.append(dict(id=p['id'],name=p['name'],available=available,summary=combine(summaries)))
    total=combine(row['summary'] for row in groups if row['available'])
    series=sorted((key,combine(value)) for key,value in daily.items())
    if hourly and series and all(len(key)>10 for key,_ in series):
        lookup=dict(series);series=[(f'{end.isoformat()}T{hour:02}',lookup.get(f'{end.isoformat()}T{hour:02}',combine([]))) for hour in range(24)]
    elif not hourly and start:
        lookup=dict(series);series=[((start+timedelta(days=i)).isoformat(),lookup.get((start+timedelta(days=i)).isoformat(),combine([]))) for i in range((end-start).days+1)]
    # Keep the full sum; large histories are binned into at most 45 contiguous groups.
    if len(series)>45:
        step=(len(series)+44)//45;series=[(series[i][0],combine(v for _,v in series[i:i+step])) for i in range(0,len(series),step)]
    return dict(total=total,groups=groups,series=series,models=[(key,combine(value)) for key,value in models.items()],available=any(g['available'] for g in groups),
                complete=all(p.get('usageComplete',True) for p in selected),start=start,end=end,magpie=magpie)
