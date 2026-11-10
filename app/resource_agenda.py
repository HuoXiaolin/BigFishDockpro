"""Local agenda data and an on-demand reminder deadline."""
import re
import time
import uuid

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from resource_options import component_location, resource_page_active

MAX_EVENTS=128
SOURCES={'local':'本地','dingtalk':'钉钉','feishu':'飞书','tencent':'腾讯会议'}
SYNC_SOURCES=tuple(source for source in SOURCES if source!='local')


def normalize_events(raw,strict=False,limit=MAX_EVENTS):
    if not isinstance(raw,list) or len(raw)>limit:
        if strict:raise ValueError(f'日程列表无效，最多支持 {limit} 条。')
        return []
    events=[];ids=set()
    for row in raw:
        if isinstance(row,dict):
            key=row.get('id');title=row.get('title');start=row.get('start');end=row.get('end')
            lead=row.get('lead',5);ack=row.get('ack',False)
            source=row.get('source','local')
            if (isinstance(key,str) and re.fullmatch(r'[a-f0-9]{32}',key) and key not in ids and
                    isinstance(title,str) and 1<=len(title.strip())<=120 and title.isprintable() and
                    type(start) is int and type(end) is int and 0<=start<end<10**10 and
                    type(lead) is int and 0<=lead<=180 and type(ack) is bool and
                    isinstance(source,str) and source in SOURCES):
                events.append(dict(id=key,title=title.strip(),start=start,end=end,lead=lead,ack=ack,source=source))
                ids.add(key)
                continue
        if strict:raise ValueError('日程名称、时间或提醒设置无效。')
    return sorted(events,key=lambda row:(row['start'],row['id']))


class Agenda(QObject):
    changed=pyqtSignal()

    def __init__(self,owner,clock=time.time):
        super().__init__(owner)
        self.owner=owner;self.clock=clock
        self.announced=set();self.error=''
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.sync)

    @property
    def local_events(self):return self.owner.cfg['resource_agenda_events']

    @property
    def events(self):
        sync=self.owner.calendar_sync
        return sync.events_for(self.local_events) if sync else self.local_events

    def enabled(self):
        cfg=self.owner.cfg
        return resource_page_active(cfg,'agenda') and cfg['resource_alert_agenda']

    def next_event(self,now=None):
        now=self.clock() if now is None else now
        return next((row for row in self.events if row['end']>now),None)

    def due(self,now=None):
        if not self.enabled():return ()
        now=self.clock() if now is None else now
        return tuple(event for event in self.events if not event['ack'] and event['start']-event['lead']*60<=now<event['end'])

    def sync(self):
        self.timer.stop()
        cfg=self.owner.cfg;now=self.clock();deadlines=[]
        if self.enabled():
            due=self.due(now)
            stamps={(row['id'],row['start'],row['lead']) for row in due}
            new=[row for row in due if (row['id'],row['start'],row['lead']) not in self.announced]
            runtime=self.owner.runtime
            if new and not (runtime.dock.preview or runtime.game_active):
                title=new[0]['title']
                if len(new)>1:title+=f' 等 {len(new)} 项日程'
                runtime.tray.showMessage('日程提醒',title,runtime.tray.icon(),5000)
            self.announced.update(stamps)
            deadlines=[value for row in self.events if not row['ack'] for value in
                       (row['start']-row['lead']*60,row['start'],row['end']) if value>now]
        if ('agenda' in cfg.get('resource_compact_metrics',()) and cfg['resource_enabled'] and cfg['resource_agenda']
                and component_location(cfg,'agenda')=='capsule' and cfg['resource_fold']!='ball' and self.owner.compact
                and self.owner.window and self.owner.window.isVisible()):
            upcoming=self.next_event(now)
            if upcoming:
                deadlines.extend(value for value in (upcoming['start'],upcoming['end']) if value>now)
        if deadlines:self.timer.start(max(1,min(86400000,round(1000*(min(deadlines)-now)))))
        self.announced.intersection_update((row['id'],row['start'],row['lead']) for row in self.events if not row['ack'])
        self.changed.emit()

    def save(self,events):
        try:
            valid=normalize_events(events,strict=True)
        except ValueError as error:
            self.error=str(error)
            return False
        if not self.owner.set_options(resource_agenda_events=valid):
            self.error='保存日程失败，请重试。'
            return False
        self.error=''
        return True

    def update_event(self,key,**details):
        old=next((row for row in self.local_events if row['id']==key),{})
        record=dict(old,**details);record.update(id=key or uuid.uuid4().hex,ack=False)
        return self.save([row for row in self.local_events if row['id']!=key]+[record])

    def synced_reminder(self,key,*,lead=None,ack=False):
        self.error=''
        if not self.owner.calendar_sync.set_reminder(key,lead=lead,ack=ack):
            self.error='无法保存此提醒。日程可能已变更，请重新打开查看。'
            return False
        return True

    def set_reminder(self,key,*,enabled):
        event=next((row for row in self.events if row['id']==key),None)
        if not event or event['end']<=self.clock():
            self.error='此日程已结束或已移除。'
            return False
        if event.get('synced'):
            return self.synced_reminder(key,ack=not enabled)
        return self.save([dict(row,ack=not enabled) if row['id']==key else row for row in self.local_events])

    def dismiss(self,key):
        return self.set_reminder(key,enabled=False)

    def remove(self,key):
        return self.save([row for row in self.local_events if row['id']!=key])
