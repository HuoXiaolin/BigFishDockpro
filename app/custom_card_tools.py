"""Small native card tools, with shared daily feeds for the visible cards."""
import datetime
import json
import math
import time
from urllib.parse import quote_plus,urlencode

from PyQt5.QtCore import QObject, QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QDoubleSpinBox,QHBoxLayout,QLabel,QLineEdit,QVBoxLayout,QWidget

from background_worker import BackgroundWorker
from content_sources import fetch
from custom_card_data import CURRENCIES,ENGINES
from ui_style import ModernComboBox,button


SEARCH_URLS={
    'bing':('https://www.bing.com/search','q'),
    'baidu':('https://www.baidu.com/s','wd'),
    'google':('https://www.google.com/search','q'),
    'duckduckgo':('https://duckduckgo.com/','q'),
}


def search_url(engine,query):
    base,parameter=SEARCH_URLS[engine]
    return base+'?'+urlencode({parameter:query})


def history_url(day,lang):
    if lang=='zh':return f'https://zh.wikipedia.org/wiki/{day.month}月{day.day}日'
    return f'https://en.wikipedia.org/wiki/{day.strftime("%B")}_{day.day}'


def history_events(day,language,lookup=fetch):
    for lang in dict.fromkeys((language,'en')):
        try:
            url=f'https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/selected/{day:%m/%d}'
            raw=json.loads(lookup(url,1536*1024))
            events=[]
            for entry in raw.get('selected',raw.get('events',[])):
                year,description=entry.get('year'),entry.get('text')
                if type(year) is int and isinstance(description,str) and description.strip():
                    events.append((year,' '.join(description.split())[:270]))
                if len(events)>=5:break
            if events:return dict(events=events,lang=lang,day=day)
        except (OSError,ValueError,TypeError,AttributeError):continue
    return None


def currency_rates(lookup=fetch):
    url='https://api.frankfurter.dev/v2/rates?'+urlencode(dict(base='EUR',quotes=','.join(CURRENCIES),providers='ecb'))
    data=json.loads(lookup(url,64*1024))
    by_date={}
    for row in data:
        date=row.get('date','');quote=row.get('quote');rate=row.get('rate')
        if quote in CURRENCIES and type(rate) in (int,float) and math.isfinite(rate) and rate>0:
            by_date.setdefault(datetime.date.fromisoformat(date).isoformat(),{'EUR':1.0})[quote]=rate
    if not by_date:return None
    date=max(by_date)
    return dict(date=date,rates=by_date[date])


class FeedJob(BackgroundWorker):
    ready=pyqtSignal(object)

    def __init__(self,key,day):
        super().__init__();self.key=key;self.day=day

    def run(self):
        try:
            if self.key[0]=='rates':result=currency_rates()
            elif self.key[0]=='history':result=history_events(self.day,self.key[1])
            else:
                url=self.key[1].replace('{date}',self.day.isoformat()).replace('{month}',f'{self.day:%m}').replace('{day}',f'{self.day:%d}')
                data=json.loads(fetch(url,64*1024));result=dict(data=data) if isinstance(data,(dict,list)) else None
        except (OSError,ValueError,TypeError,AttributeError,OverflowError):result=None
        if not self.cancelled.is_set():self.ready.emit(result)


class CardFeeds(QObject):
    changed=pyqtSignal()

    def __init__(self,runtime):
        super().__init__(runtime.dock);self.runtime=runtime;self.jobs={};self.cache={};self.retry={}

    def sync(self,keys):
        for key in self.jobs.keys()-keys:
            job=self.jobs.pop(key);job.requestInterruption();job.deleteLater()
        for key in self.cache.keys()-keys:self.cache.pop(key)
        for key in self.retry.keys()-keys:self.retry.pop(key)
        if self.runtime.dock.preview:return
        today=datetime.date.today();now=time.monotonic()
        for key in keys:
            cached=self.cache.get(key)
            if key in self.jobs or (key[0]!='feed' and cached and cached[0]==today) or self.retry.get(key,0)>now:continue
            job=self.jobs[key]=FeedJob(key,today)
            job.ready.connect(self.receive,Qt.QueuedConnection);job.finished.connect(self.finished,Qt.QueuedConnection);job.start()

    def receive(self,result):
        job=self.sender()
        if self.jobs.get(job.key) is not job:return
        if result is not None:self.cache[job.key]=job.day,result
        interval=job.key[2]*60 if job.key[0]=='feed' and result is not None else 1800
        self.retry[job.key]=time.monotonic()+interval
        self.changed.emit()

    def finished(self):
        job=self.sender()
        if self.jobs.get(job.key) is job:self.jobs.pop(job.key)
        job.deleteLater()

    def read(self,key):
        return self.cache.get(key,(None,None))[1]


def feed_key(tool):
    kind=tool.get('kind')
    if kind=='rates':return kind,''
    if kind=='history':return kind,tool['lang']
    if kind=='feed':return kind,tool['url'],tool['interval']
    return None


def tool_height(tool):
    kind=tool.get('kind')
    if kind=='history':return 25+tool['limit']*31
    return {'search':34,'pomodoro':63,'rates':82,'convert':60}.get(kind,0)


def combo(choices,selected,accessible):
    field=ModernComboBox();field.setAccessibleName(accessible)
    for key,label in choices:field.addItem(label,key)
    field.setCurrentIndex(max(0,field.findData(selected)))
    return field


class SearchTool(QWidget):
    def __init__(self,tool,parent):
        super().__init__(parent);row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(5)
        self.query=QLineEdit();self.query.setPlaceholderText('输入搜索词');self.query.setMaxLength(512);row.addWidget(self.query,1)
        self.custom=tool.get('url','')
        choices=list(ENGINES.items())
        if self.custom:choices.append(('custom','自定义'))
        self.engine=combo(choices,'custom' if self.custom else tool['engine'],'搜索引擎');self.engine.setFixedWidth(72);row.addWidget(self.engine)
        row.addWidget(button('搜索',self.submit));self.query.returnPressed.connect(self.submit)

    def submit(self):
        query=self.query.text().strip()
        if not query:return
        engine=self.engine.currentData()
        url=self.custom.replace('{query}',quote_plus(query)) if engine=='custom' else search_url(engine,query)
        QDesktopServices.openUrl(QUrl(url))


class PomodoroTool(QWidget):
    def __init__(self,tool,parent):
        super().__init__(parent);self.tool=tool;self.deadline=None;self.resting=False;self.remaining=tool['minutes']*60
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        self.clock=QLabel();self.clock.setAlignment(Qt.AlignCenter);layout.addWidget(self.clock)
        actions=QHBoxLayout();actions.addStretch();self.toggle=button('开始',self.start_or_pause)
        actions.addWidget(self.toggle);actions.addWidget(button('重置',self.reset));actions.addStretch();layout.addLayout(actions)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.refresh);self.refresh()

    def start_or_pause(self):
        if self.deadline is None:
            self.deadline=time.monotonic()+self.remaining;self.timer.start()
        else:
            self.remaining=max(1,math.ceil(self.deadline-time.monotonic()));self.deadline=None;self.timer.stop()
        self.refresh()

    def reset(self):
        self.deadline=None;self.resting=False;self.remaining=self.tool['minutes']*60;self.timer.stop();self.refresh()

    def refresh(self):
        if self.deadline is not None:
            self.remaining=max(0,math.ceil(self.deadline-time.monotonic()))
            if not self.remaining:
                self.deadline=None;self.timer.stop();self.resting=not self.resting
                self.remaining=self.tool['break_minutes' if self.resting else 'minutes']*60
        phase='休息' if self.resting else '专注'
        self.clock.setText(f'{phase}  {self.remaining//60:02d}:{self.remaining%60:02d}')
        self.toggle.setText('暂停' if self.deadline is not None else '开始')


class HistoryTool(QWidget):
    def __init__(self,tool,parent):
        super().__init__(parent);self.tool=tool;self.feeds=parent.manager.feeds
        self.key=feed_key(tool);self.entries=[];self.result=None
        from resource_pages import MediaLabel
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        for _ in range(tool['limit']):
            entry=MediaLabel(2,10);entry.setFixedHeight(28);layout.addWidget(entry);self.entries.append(entry)
        self.source=button('维基百科',self.open_source);layout.addWidget(self.source,0,Qt.AlignLeft)
        self.feeds.changed.connect(self.refresh);self.refresh()

    def refresh(self):
        result=self.feeds.read(self.key)
        self.result=result if result and result['day']==datetime.date.today() else None
        events=self.result['events'] if self.result else []
        for index,label in enumerate(self.entries):
            value=f'{events[index][0]}  {events[index][1]}' if index<len(events) else '暂未取得事件' if index==0 else ''
            label.setText(value);label.setToolTip(value)
        lang=self.result['lang'] if self.result else self.tool['lang']
        self.source.setText('维基百科 · 英文' if lang=='en' else '维基百科')

    def open_source(self):
        result=self.result or dict(day=datetime.date.today(),lang=self.tool['lang'])
        QDesktopServices.openUrl(QUrl(history_url(result['day'],result['lang'])))


class RatesTool(QWidget):
    def __init__(self,tool,parent):
        super().__init__(parent);self.feeds=parent.manager.feeds
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        row=QHBoxLayout();row.setSpacing(4);layout.addLayout(row)
        choices=[(code,code) for code in CURRENCIES]
        self.amount=QDoubleSpinBox();self.amount.setAccessibleName('换算金额');self.amount.setRange(0,10_000_000);self.amount.setValue(tool['amount'])
        self.origin=combo(choices,tool['from'],'原货币');self.target=combo(choices,tool['to'],'目标货币')
        for control in (self.origin,self.target):control.setFixedWidth(58)
        row.addWidget(self.amount,1);row.addWidget(self.origin);row.addWidget(self.target)
        self.result=QLabel();layout.addWidget(self.result);self.source=QLabel();layout.addWidget(self.source)
        self.amount.valueChanged.connect(self.refresh);self.origin.currentIndexChanged.connect(self.refresh);self.target.currentIndexChanged.connect(self.refresh)
        self.feeds.changed.connect(self.refresh);self.refresh()

    def refresh(self):
        snapshot=self.feeds.read(('rates',''))
        origin,target=self.origin.currentData(),self.target.currentData()
        rates=snapshot['rates'] if snapshot else {}
        if origin not in rates or target not in rates:
            self.result.setText('等待汇率数据');self.source.setText('Frankfurter · 欧洲央行');return
        rate=rates[target]/rates[origin]
        self.result.setText(f'{self.amount.value()*rate:,.2f} {target}')
        self.source.setText(f'1 {origin} = {rate:.5g} {target} · {snapshot["date"]}')


class ConversionTool(QWidget):
    def __init__(self,tool,parent):
        super().__init__(parent);self.units=tool['units']
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        row=QHBoxLayout();row.setSpacing(4);layout.addLayout(row)
        choices=[(index,unit['name']) for index,unit in enumerate(self.units)]
        self.amount=QDoubleSpinBox();self.amount.setAccessibleName('换算数值');self.amount.setRange(-1e7,1e7);self.amount.setValue(1)
        self.origin=combo(choices,0,'原单位');self.target=combo(choices,1,'目标单位')
        for control in (self.origin,self.target):control.setMaximumWidth(90)
        row.addWidget(self.amount,1);row.addWidget(self.origin,1);row.addWidget(self.target,1)
        self.result=QLabel();layout.addWidget(self.result)
        self.amount.valueChanged.connect(self.refresh);self.origin.currentIndexChanged.connect(self.refresh);self.target.currentIndexChanged.connect(self.refresh);self.refresh()

    def refresh(self):
        origin=self.units[self.origin.currentData()];target=self.units[self.target.currentData()]
        base=self.amount.value()*origin['factor']+origin['offset']
        result=(base-target['offset'])/target['factor']
        self.result.setText(f'{result:,.6g} {target["name"]}')


TOOLS={'search':SearchTool,'pomodoro':PomodoroTool,'history':HistoryTool,'rates':RatesTool,'convert':ConversionTool}
