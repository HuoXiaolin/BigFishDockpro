"""Small local aggregate counters; no application names, paths or content."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import time
from PyQt5.QtCore import QObject, QTimer

SCHEMA_VERSION = 2
HISTORY_DAYS = 90
EVENTS = {
    'dock_launch': 'Dock 启动入口',
    'file_open': '卡片打开文件',
    'settings_open': '打开软件设置',
    'batch_open': '打开应用管理',
    'panel_switch': '切换分类页面',
    'panel_new': '新建收纳卡片',
    'note_new': '新建便签',
    'clock_settings': '时钟与日历设置',
    'resource_open': '展开资源胶囊',
    'flash_new': '新建闪念',
    'agenda_new': '新建本地日程',
}


def fresh():
    return dict(version=SCHEMA_VERSION, since=dt.datetime.now().isoformat(timespec='seconds'),
                starts=0, seconds=0, counts=dict.fromkeys(EVENTS, 0), days={})


def number(value):
    return value if type(value) is int and 0 <= value < 10**15 else 0


def counters(values):
    return {key: number(values.get(key)) for key in EVENTS} if isinstance(values, dict) else dict.fromkeys(EVENTS, 0)


def recent_days(days, today):
    lower = (today - dt.timedelta(days=HISTORY_DAYS-1)).isoformat()
    upper = today.isoformat()
    return {day: counts for day, counts in days.items() if lower <= day <= upper}


def daily_counts(data, today, days):
    since = dt.datetime.fromisoformat(data['since']).date()
    dates = (today - dt.timedelta(days=offset) for offset in range(days-1, -1, -1))
    return [(day, data['days'].get(day.isoformat(), {}) if day >= since else None) for day in dates]


def record(owner,key):
    store=getattr(getattr(owner,'dock',owner),'usage',None)
    if store:store.record(key)


class UsageStore(QObject):
    def __init__(self,directory,parent=None,log=lambda message:None):
        super().__init__(parent)
        self.path = Path(directory)/'usage_stats.json'
        self.log = log
        self.data = self.load()
        self.last = time.monotonic()
        self.error = ''
        self.data['starts'] += 1
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.flush)
        self.timer.start()

    def load(self):
        data = fresh()
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(raw, dict):
                raise ValueError('invalid statistics')
            if raw.get('version') != SCHEMA_VERSION:
                return data
            since = dt.datetime.fromisoformat(raw.get('since')).isoformat(timespec='seconds')
        except FileNotFoundError:
            return data
        except (OSError, ValueError, TypeError, RecursionError):
            self.log('使用统计读取失败，已从本次运行重新累计。')
            return data
        data.update(since=since, starts=number(raw.get('starts')), seconds=number(raw.get('seconds')),
                    counts=counters(raw.get('counts')))
        days = raw.get('days')
        if isinstance(days, dict):
            for day, values in recent_days(days, dt.date.today()).items():
                try:
                    if dt.date.fromisoformat(day).isoformat() != day:
                        continue
                except ValueError:
                    continue
                if isinstance(values, dict):
                    data['days'][day] = counters(values)
        return data

    def accrue(self):
        now=time.monotonic();elapsed=int(now-self.last)
        if elapsed>0:self.data['seconds']+=elapsed;self.last+=elapsed

    def record(self,key):
        if key not in EVENTS:
            return
        self.accrue()
        self.data['counts'][key] += 1
        today = dt.date.today()
        day = self.data['days'].setdefault(today.isoformat(), {})
        day[key] = day.get(key, 0) + 1
        if not self.timer.isActive():
            self.timer.start()

    def write(self,data):
        temporary=self.path.with_suffix('.json.tmp')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with temporary.open('w',encoding='utf-8') as stream:
                json.dump(data,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path);self.error='';return True
        except OSError as error:
            self.error='统计保存失败，当前计数仍保留，可点击刷新重试。';self.log('使用统计保存失败: '+str(error));return False

    def flush(self):
        self.timer.stop()
        self.accrue()
        self.data['days'] = recent_days(self.data['days'], dt.date.today())
        return self.write(self.data)

    def snapshot(self):
        self.accrue();return copy.deepcopy(self.data)

    def reset(self):
        candidate=fresh()
        if not self.write(candidate):return False
        self.timer.stop();self.data=candidate;self.last=time.monotonic();return True

    def close(self):self.flush()
