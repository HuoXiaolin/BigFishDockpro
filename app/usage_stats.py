"""Small local aggregate counters; no application names, paths or content."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import time
import weakref
from PyQt5.QtCore import QObject,QTimer
from PyQt5.QtWidgets import QMessageBox
from ui_style import label,button

EVENTS={'dock_launch':'Dock 启动入口','file_open':'卡片打开文件','settings_open':'打开软件设置','batch_open':'打开应用管理','panel_switch':'切换分类页面','panel_new':'新建收纳卡片','note_new':'新建便签','clock_settings':'打开时钟 / 日历设置'}


def fresh():
    return {'since':dt.datetime.now().isoformat(timespec='seconds'),'starts':0,'seconds':0,'counts':{key:0 for key in EVENTS},'days':{}}


def record(owner,key):
    store=getattr(getattr(owner,'dock',owner),'usage',None)
    if store:store.record(key)


class UsageStore(QObject):
    def __init__(self,directory,parent=None,log=lambda message:None):
        super().__init__(parent);self.path=Path(directory)/'usage_stats.json';self.log=log;self.data=fresh();self.last=time.monotonic();self.error=''
        try:
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(raw,dict):raise ValueError('invalid statistics')
            def number(value):return value if type(value) is int and 0<=value<10**15 else 0
            self.data['since']=str(raw.get('since',self.data['since']))[:30]
            for key in ('starts','seconds'):self.data[key]=number(raw.get(key))
            counts=raw.get('counts',{});self.data['counts']={key:number(counts.get(key)) for key in EVENTS} if isinstance(counts,dict) else self.data['counts']
            days=raw.get('days',{})
            if isinstance(days,dict):
                for day,value in days.items():
                    try:dt.date.fromisoformat(day)
                    except (TypeError,ValueError):continue
                    self.data['days'][day]=number(value)
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError):self.log('使用统计读取失败，已从本次运行重新累计。')
        self.data['starts']+=1;self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(2000);self.timer.timeout.connect(self.flush);self.timer.start()

    def accrue(self):
        now=time.monotonic();elapsed=int(now-self.last)
        if elapsed>0:self.data['seconds']+=elapsed;self.last+=elapsed

    def record(self,key):
        if key not in EVENTS:return
        self.accrue();self.data['counts'][key]+=1;today=dt.date.today().isoformat();self.data['days'][today]=self.data['days'].get(today,0)+1
        cutoff=(dt.date.today()-dt.timedelta(days=89)).isoformat();self.data['days']={day:count for day,count in self.data['days'].items() if cutoff<=day<=today}
        if not self.timer.isActive():self.timer.start()

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
        self.timer.stop();self.accrue();return self.write(self.data)

    def snapshot(self):
        self.accrue();return copy.deepcopy(self.data)

    def reset(self):
        candidate=fresh()
        if not self.write(candidate):return False
        self.timer.stop();self.data=candidate;self.last=time.monotonic();return True

    def close(self):self.flush()


class UsagePage(QObject):
    @property
    def dialog(self):return self._dialog()

    def __init__(self,dialog,form):
        super().__init__(dialog)
        self._dialog=weakref.ref(dialog);self.store=dialog.tray.runtime.usage;self.fields={}
        form.addRow(label('本机使用概览','section'))
        for key,title in [('since','开始统计'),('starts','软件启动次数'),('duration','累计运行时长'),('total','累计操作次数'),('today','今日操作次数'),('week','近七日操作次数')]:
            self.fields[key]=label('—');form.addRow(title,self.fields[key])
        dialog.action_row(form,'统计管理',button('刷新统计',self.refresh),button('重置统计…',self.reset))
        form.addRow(label('功能使用次数','section'))
        for key,title in EVENTS.items():self.fields[key]=label('0');form.addRow(title,self.fields[key])
        text=label('从此版本起累计，仅保存在本机。运行时长为程序运行时间，不代表前台活跃时间；不记录文件路径、应用名称或文字内容。统计独立保存，不随配置导入导出。','muted');text.setWordWrap(True);form.addRow(text)
        self.status=label('','muted');self.status.setWordWrap(True);form.addRow(self.status)
        self.refresh()

    def refresh(self):
        self.store.flush();data=self.store.snapshot();today=dt.date.today();days=data['days'];hours,remainder=divmod(data['seconds'],3600);minutes=remainder//60
        values={'since':data['since'].replace('T',' '),'starts':data['starts'],'duration':'%d 小时 %d 分钟'%(hours,minutes),'total':sum(data['counts'].values()),'today':days.get(today.isoformat(),0),'week':sum(days.get((today-dt.timedelta(days=i)).isoformat(),0) for i in range(7)),**data['counts']}
        for key,value in values.items():self.fields[key].setText(str(value))
        self.status.setText(self.store.error or '统计自动保存；进入本页或点击刷新查看最新数据。')

    def reset(self):
        box=QMessageBox(QMessageBox.Question,'重置使用统计','清空全部使用次数、运行时长和历史记录，并从现在重新统计？不会改变应用配置和卡片内容。',QMessageBox.Yes|QMessageBox.Cancel,self.dialog);box.setDefaultButton(QMessageBox.Cancel)
        if box.exec_()!=QMessageBox.Yes:return
        if self.store.reset():self.refresh();self.status.setText('使用统计已重置，后续操作将重新累计。')
        else:self.status.setText('重置失败，原统计数据已保留。')
