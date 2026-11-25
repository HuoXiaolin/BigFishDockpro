"""Local-day usage measured from quota percentages, independently for each allowance."""
import json
import time
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import NamedTuple

from config_store import _atomic
from resource_quota import DailyQuota, provider_plan_name, quota_window, tray_metric_key, used_percent


class Sample(NamedTuple):
    at: int
    used: float
    reset: int | None
    daily: DailyQuota


def timestamp(value):
    try:
        if isinstance(value,str):
            return int(datetime.fromisoformat(value).timestamp())
        if type(value) in (float,int) and isfinite(value):
            return int(value)
    except (ValueError,OverflowError,OSError):
        pass
    return None


def key_for(row, metric):
    plan = provider_plan_name(row)
    if plan == '套餐未识别':
        plan = row['plan'].strip().casefold()
    return (row['id'], plan, tray_metric_key(metric), quota_window(metric))


def same_reset(first, second):
    # Countdown-based APIs can round the deadline differently on adjacent polls.
    return first==second or (first is not None and second is not None and abs(first-second)<=60)


def measure(previous, at, used, reset, minutes):
    day=date.fromtimestamp(at)
    midnight=int(datetime.combine(day,datetime.min.time()).timestamp())
    start=reset-minutes*60 if reset and minutes else None
    starts_today=start is not None and midnight<=start<=at<reset
    if previous is None or date.fromtimestamp(previous.at)!=day:
        if starts_today or used==0:
            # Earlier short windows may also have been consumed before this observation.
            partial=start>midnight if starts_today else not (reset and minutes and start<=midnight)
            return DailyQuota(used,used,partial)
        complete=at==midnight or bool(previous and reset is not None and same_reset(previous.reset,reset) and previous.used==used)
        return DailyQuota(0.,0.,not complete)

    last=previous.daily
    new_window=(reset is not None and previous.reset is not None and previous.reset<=at and not same_reset(previous.reset,reset))
    new_window=new_window or (start is not None and previous.at<start<=at and not same_reset(previous.reset,reset))
    if new_window:
        return DailyQuota(used,last.total+used,last.partial or previous.used<100)
    portion=max(0.,min(used,last.in_window+used-previous.used))
    return DailyQuota(portion,last.total-last.in_window+portion,last.partial or used<previous.used)


class QuotaDayHistory:
    limit=512

    def __init__(self, directory):
        self.path=Path(directory)/'quota-day.json'
        self.samples={}
        self.loaded=False
        self.dirty=False

    def load(self, now):
        self.loaded=True
        try:
            if self.path.stat().st_size>256*1024:return
            records=json.loads(self.path.read_bytes())
            if not isinstance(records,list) or len(records)>self.limit:return
        except (OSError,ValueError,RecursionError):
            return
        for record in records:
            try:
                key,at,used,reset,portion,total,partial=record
                if (not isinstance(key,list) or len(key)!=4 or not all(isinstance(s,str) for s in key[:3])
                        or key[3] is not None and type(key[3]) is not int
                        or type(at) is not int or not now-2*86400<=at<=now
                        or reset is not None and type(reset) is not int or type(partial) is not bool
                        or not all(type(n) in (int,float) and isfinite(n) for n in (used,portion,total))
                        or not 0<=portion<=used<=100 or total<portion):continue
                self.samples[tuple(key)]=Sample(at,used,reset,DailyQuota(portion,total,partial))
            except (TypeError,ValueError):
                continue

    def observe(self, rows, when=None):
        now=int(time.time()) if when is None else int(when)
        for row in rows:
            at=timestamp(row.get('quotaAt'))
            if row.get('stale') and at is None:continue
            at=now if at is None else min(at,now)
            if at<now-2*86400:continue
            anchor=row.get('quotaDayStart') or {}
            anchor_at=timestamp(anchor.get('at'))
            midnight=int(datetime.combine(date.fromtimestamp(at),datetime.min.time()).timestamp())
            anchor_row=dict(row,plan=anchor.get('plan') or row.get('plan'))
            baselines={key_for(anchor_row,q):q for q in anchor.get('quotas',())} if anchor_at is not None and midnight<=anchor_at<=at else {}
            for metric in row.get('quotas',()):
                level=used_percent(metric)
                if level is None:continue
                used=max(0.,min(100.,level));reset=timestamp(metric.get('reset'))
                if reset is not None and reset<=at:continue
                if not self.loaded:self.load(now)
                key=key_for(row,metric)
                previous=self.samples.get(key)
                if previous and at<previous.at:continue
                first=baselines.get(key)
                if (first and reset is not None and same_reset(timestamp(first.get('reset')),reset)
                        and (not previous or previous.at<anchor_at)):
                    initial=used_percent(first)
                    if initial is not None and 0<=initial<=used:
                        baseline=measure(previous,anchor_at,initial,reset,key[3])
                        previous=Sample(anchor_at,initial,reset,baseline)
                daily=measure(previous,at,used,reset,key[3])
                item=Sample(at,used,reset,daily)
                old=self.samples.get(key)
                if not old or item[1:]!=old[1:] or date.fromtimestamp(at)!=date.fromtimestamp(old.at):
                    self.dirty=True
                self.samples[key]=item
        if self.dirty:
            recent=sorted(self.samples.items(),key=lambda item:item[1].at,reverse=True)
            self.samples={key:s for key,s in recent[:self.limit] if now-2*86400<=s.at<=now}
            data=[[key,s.at,s.used,s.reset,*s.daily] for key,s in self.samples.items()]
            try:
                _atomic(self.path,json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
                self.dirty=False
            except OSError:
                pass  # Keep the current session and retry on the next reading.

    def decorate(self, row, now):
        day=date.fromtimestamp(now)
        observed=timestamp(row.get('quotaAt'))
        if observed is not None and observed<int(datetime.combine(day,datetime.min.time()).timestamp()):
            return row
        readings={}
        for metric in row.get('quotas',()):
            used=used_percent(metric)
            if used is None:continue
            if not self.loaded:self.load(int(now))
            key=key_for(row,metric);sample=self.samples.get(key)
            if (sample and date.fromtimestamp(sample.at)==day and sample.used==max(0.,min(100.,used))
                    and same_reset(sample.reset,timestamp(metric.get('reset')))
                    and (sample.reset is None or now<sample.reset)):
                readings[key[2:]]=sample.daily
        return dict(row,_quota_today=readings) if readings else row
