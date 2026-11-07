"""Opt-in JSON pipe to the BrimDeck-derived read-only provider/media helper."""
import base64,json,sys,time
from pathlib import Path
from PyQt5.QtCore import QObject,QProcess,QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication


class DeckBridge(QObject):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.signature=None;self.closed=False;self.buffer=bytearray()
        self.providers=[];self.media={};self.cover=QPixmap();self.levels=[0.]*8;self.status='正在连接…'
        self.ai_status='正在读取…';self.alert='';self.alert_until=0.;self.previous_levels={}
        self.history_requested=False
        self.memory_blocked=False
        self.process=QProcess(self);self.process.readyReadStandardOutput.connect(self.read)
        self.process.errorOccurred.connect(self.failed);self.process.finished.connect(self.finished)
        self.restart=QTimer(self);self.restart.setSingleShot(True);self.restart.setInterval(15000);self.restart.timeout.connect(self.configure)

    def configure(self):
        if self.memory_blocked:return
        cfg=self.owner.cfg
        desktop=cfg['resource_enabled'] and not getattr(self.owner.runtime,'game_active',False)
        window=self.owner.window
        strip=getattr(self.owner,'strip',None);task_music=bool(strip and strip.music_requested())
        compact=getattr(self.owner,'compact',cfg['resource_collapsed'])
        presentation=bool(desktop and cfg['resource_music'] and window and ((compact and cfg['resource_fold']!='ball' and cfg['resource_music_text']=='wave') or (not compact and window.page_key=='music')))
        presentation=presentation or bool(task_music and strip.shows_wave())
        signature=(cfg['resource_ai_tray'] or cfg['resource_ai'] and desktop,tuple(cfg['resource_ai_providers']),cfg['resource_music'] and desktop or task_music,cfg['resource_lyrics'] and cfg['resource_music'] and desktop,cfg['resource_equalizer'],presentation)
        if signature==self.signature and (self.process.state()!=QProcess.NotRunning or self.owner.runtime.dock.preview):return
        self.signature=signature
        if not signature[0]:self.providers=[];self.ai_status='已关闭'
        if not signature[2]:self.media={};self.cover=QPixmap();self.levels=[0.]*8
        if self.owner.runtime.dock.preview:return
        starting=self.process.state()==QProcess.NotRunning
        if starting:
            from deck_runtime import installed_runtime
            if not installed_runtime():
                self.status=self.ai_status='AI / 音乐需要 .NET 10 桌面运行库，可在设置中打开下载页';return
            root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'artifacts'
            exe=root/'deck-bridge/BigFishDeckBridge.exe'
            if not exe.is_file():self.status=self.ai_status='未找到 AI / 音乐组件';return
            self.process.start(str(exe),[str(Path(self.owner.runtime.api.CONFIG_DIR)/'deck-data')])
        self.send(op='configure',ai=signature[0],providers=signature[1],music=signature[2],lyrics=signature[3],equalizer=signature[4],presentation=signature[5])
        if starting and self.history_requested:self.send(op='history',range='all')

    def request_history(self):
        if not self.history_requested:
            self.history_requested=True;self.send(op='history',range='all')

    def refresh(self):
        if self.closed:return
        self.memory_blocked=False
        if self.process.state()==QProcess.NotRunning:self.configure()
        self.send(op='refresh')

    def send(self,**data):
        if not self.closed and self.process.state()!=QProcess.NotRunning:
            self.process.write((json.dumps(data,ensure_ascii=False)+'\n').encode('utf-8'))

    def read(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer)>4*1024*1024:self.buffer.clear();return
        while b'\n' in self.buffer:
            line,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
            try:self.accept(json.loads(line.decode('utf-8-sig')))
            except (ValueError,TypeError,KeyError,AttributeError):continue

    def accept(self,data):
        kind=data.get('type');cfg=self.owner.cfg
        if kind=='ai' and (cfg['resource_ai'] or cfg['resource_ai_tray']):
            from resource_quota import remaining_percent, used_percent
            self.providers=data.get('providers',[])[:7];self.ai_status='更新于 '+str(data.get('at',''))[11:19]
            for row in self.providers:
                used = max((value for q in row.get('quotas', []) if (value := used_percent(q)) is not None), default=None)
                if used is None:continue
                level=2 if used>=80 else 1 if used>=60 else 0
                previous=self.previous_levels.get(row['id'],0);self.previous_levels[row['id']]=level
                if cfg['resource_quota_alert'] and level>previous:
                    self.alert=f"{row['name']}  额度剩余 {remaining_percent(used):.0f}%";self.alert_until=time.monotonic()+5
        elif kind=='memory_error':
            self.memory_blocked=True;self.restart.stop();self.status=self.ai_status=data.get('message','无法启用内存限制')
        elif kind=='ai_error':
            self.ai_status=data.get('message','读取失败')
            for row in self.providers:row['stale']=True
        elif kind=='media' and self.signature and self.signature[2]:
            self.media=data;self.status=data.get('status','')
            if data.get('pictureChanged'):
                self.cover=QPixmap()
                if data.get('cover'):self.cover.loadFromData(base64.b64decode(data['cover'],validate=True))
        elif kind=='levels' and self.signature and self.signature[2]:
            self.levels=[max(0.,min(1.,float(n))) for n in data.get('levels',[])[:20]]
            if self.owner.window:
                self.owner.window.update()
                view=getattr(self.owner.window,'_music_view',None)
                if view and view.isVisible():view.meter.update()
            strip=getattr(self.owner,'strip',None)
            if strip and strip.isVisible() and strip.shows_wave():strip.update()
            return
        elif kind in ('command','error') and data.get('message'):self.status=data['message']
        self.owner.display()

    def failed(self,error):
        if error==QProcess.FailedToStart:self.finished()
    def finished(self,*args):
        if self.closed:return
        if self.memory_blocked:self.owner.display();return
        self.status=self.ai_status='组件连接中断，正在重试';self.signature=None;self.buffer.clear()
        self.providers=[];self.media={};self.cover=QPixmap();self.levels=[0.]*8
        self.restart.start();self.owner.display()
    def close(self):
        self.closed=True;self.restart.stop();p=self.process
        if p.state()!=QProcess.NotRunning:
            p.write(b'{"op":"quit"}\n');p.setParent(QApplication.instance())
            timer=QTimer(p);timer.setSingleShot(True);timer.timeout.connect(p.kill);timer.start(1500)
            p.finished.connect(p.deleteLater)
        self.deleteLater()
