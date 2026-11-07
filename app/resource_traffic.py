"""Persist byte deltas, never rates; one ledger is owned by the sampling worker."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import time


def amount(value):
    for unit in ('B','KB','MB','GB','TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.2f} {unit}'
        value /= 1024


def totals(days, now=None):
    day=(now or datetime.now()).strftime('%Y-%m-%d')
    return {period:tuple(sum(v[i] for k,v in days.items() if k.startswith(prefix)) for i in (0,1))
            for period,prefix in (('day',day),('month',day[:7]),('year',day[:4]))}


class TrafficLedger:
    def __init__(self,path):
        self.path=Path(path) if path else None
        self.days={};self.previous=None;self.previous_at=None;self.dirty=False
        self.saved_at=0.;self.error='';self.blocked=False
        if self.path and self.path.exists():
            try:
                if self.path.stat().st_size>2*1024*1024:raise ValueError('too large')
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('version')!=1 or not isinstance(data.get('days'),dict):raise ValueError('format')
                for day,row in data['days'].items():
                    if datetime.strptime(day,'%Y-%m-%d').strftime('%Y-%m-%d')!=day:raise ValueError('date')
                    if not isinstance(row,list) or len(row)!=2 or any(type(n) is not int or n<0 for n in row):raise ValueError('bytes')
                    self.days[day]=row
            except (OSError,ValueError,TypeError,KeyError,AttributeError):
                self.days={};self.blocked=True;self.error='流量记录无法读取，原文件已保留'

    def pause(self):
        self.flush();self.previous=None;self.previous_at=None

    def observe(self,readings,now=None):
        now=now or datetime.now()
        if readings is None:
            self.previous=None;self.previous_at=None
            return self.snapshot(now)
        if self.previous is not None and self.previous_at and now>=self.previous_at:
            pairs=[(self.previous[k],v) for k,v in readings.items() if k in self.previous
                   and all(v[i]>=self.previous[k][i] for i in (0,1))]
            delta=[sum(end[i]-start[i] for start,end in pairs) for i in (0,1)]
            # A short interval crossing midnight is apportioned by elapsed time.
            # A suspended clock/adapter must establish a fresh baseline, not invent a day's traffic.
            duration=(now-self.previous_at).total_seconds()
            if duration<=120 and any(delta):
                cursor=self.previous_at;remaining=delta.copy()
                while cursor.date()<now.date():
                    midnight=datetime.combine(cursor.date()+timedelta(days=1),datetime.min.time())
                    part=[round(n*(midnight-cursor).total_seconds()/max(.001,duration)) for n in delta]
                    self.add(cursor.strftime('%Y-%m-%d'),part)
                    remaining=[a-b for a,b in zip(remaining,part)];cursor=midnight
                self.add(now.strftime('%Y-%m-%d'),remaining)
        self.previous=dict(readings);self.previous_at=now
        if time.monotonic()-self.saved_at>=15:self.flush()
        return self.snapshot(now)

    def add(self,day,delta):
        row=self.days.setdefault(day,[0,0])
        for i in (0,1):row[i]+=delta[i]
        self.dirty=True

    def snapshot(self,now=None):
        return dict(totals(self.days,now),days={k:list(v) for k,v in self.days.items()},error=self.error)

    def flush(self):
        if not self.path or not self.dirty or self.blocked:return
        try:
            from config_store import _atomic
            _atomic(self.path,json.dumps({'version':1,'days':self.days},separators=(',',':')).encode('utf-8'))
            self.dirty=False;self.error='';self.saved_at=time.monotonic()
        except OSError:self.error='流量记录保存失败，将自动重试'
