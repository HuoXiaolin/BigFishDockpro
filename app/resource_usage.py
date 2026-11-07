"""Pure aggregation of metering records. Missing fields stay unknown, not zero."""
from datetime import date,timedelta

FIELDS=('tokens','input','output','cacheRead','cacheWrite','records')


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


def aggregate(providers,period='today',provider='',today=None):
    start,end=bounds(period,today);selected=[p for p in providers if not provider or p['id']==provider]
    groups=[];daily={};models={};hourly=period in ('today','yesterday')
    for p in selected:
        summaries=[]
        for row in p.get('days',[]):
            try:day=date.fromisoformat(row['date'])
            except (KeyError,ValueError):continue
            if day>end or start and day<start:continue
            summary=row['summary'];summaries.append(summary)
            if not hourly:daily.setdefault(row['date'],[]).append(summary)
            models.setdefault((p['name'],row['model']),[]).append(summary)
        if hourly:
            for row in p.get('hours',[]):
                if row['date'][:10]==end.isoformat():daily.setdefault(row['date'],[]).append(row['summary'])
            # Older helper snapshots have daily totals, not invented hourly points.
            if not p.get('hours') and summaries:daily.setdefault(end.isoformat(),[]).extend(summaries)
        groups.append(dict(id=p['id'],name=p['name'],available=p.get('usageAvailable',False),summary=combine(summaries)))
    total=combine(row['summary'] for row in groups if row['available'])
    series=sorted((key,combine(value)) for key,value in daily.items())
    if hourly and series and all(len(key)>10 for key,_ in series):
        lookup=dict(series);series=[(f'{end.isoformat()}T{hour:02}',lookup.get(f'{end.isoformat()}T{hour:02}',combine([]))) for hour in range(24)]
    elif not hourly and start:
        lookup=dict(series);series=[((start+timedelta(days=i)).isoformat(),lookup.get((start+timedelta(days=i)).isoformat(),combine([]))) for i in range((end-start).days+1)]
    # Keep the full sum; large histories are binned into at most 45 contiguous groups.
    if len(series)>45:
        step=(len(series)+44)//45;series=[(series[i][0],combine(v for _,v in series[i:i+step])) for i in range(0,len(series),step)]
    return dict(total=total,groups=groups,series=series,models=[(key,combine(value)) for key,value in models.items()],available=any(p.get('usageAvailable') for p in selected),
                complete=all(p.get('usageComplete',True) for p in selected),start=start,end=end)
