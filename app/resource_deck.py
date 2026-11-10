"""Opt-in JSON pipe to the BrimDeck-derived read-only provider/media helper."""
import base64,ctypes,json,sys,time
from pathlib import Path
from PyQt5.QtCore import QObject,QProcess,QProcessEnvironment,QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication


def start_headless(process, executable, data_dir, runtime):
    env = QProcessEnvironment.systemEnvironment()
    env.insert('DOTNET_ROOT_X64', str(runtime))
    env.insert('DOTNET_DISABLE_GUI_ERRORS', '1')
    process.setProcessEnvironment(env)
    # The Windows error mode is inherited at CreateProcess, including failures
    # before managed Main. Restore the parent's mode as soon as QProcess starts.
    kernel = ctypes.windll.kernel32
    previous = kernel.GetErrorMode()
    kernel.SetErrorMode(previous | 0x0001 | 0x0002)  # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX
    try:
        process.start(str(executable), [str(data_dir)])
    finally:
        kernel.SetErrorMode(previous)


class DeckBridge(QObject):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.signature=None;self.closed=False;self.buffer=bytearray()
        self.providers=[];self.media={};self.cover=QPixmap();self.levels=[0.]*8;self.status='正在连接…'
        self.local_providers=[];self.gateway=None;self.idling=False
        self.ai_status='正在读取…';self.alert='';self.alert_until=0.;self.previous_levels={}
        self.history_requested=False
        self.memory_blocked=False
        self.failures=0
        self.launched_at=0.
        self.launch_timed_out=False
        self.process=QProcess(self);self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.errorOccurred.connect(self.failed);self.process.finished.connect(self.finished)
        self.restart=QTimer(self);self.restart.setSingleShot(True);self.restart.timeout.connect(self.configure)
        self.launch_watch=QTimer(self);self.launch_watch.setSingleShot(True)
        self.launch_watch.timeout.connect(self.startup_timeout)
        if (Path(owner.runtime.api.CONFIG_DIR)/'resource-gateway-accounts.dat').is_file():
            from resource_gateway import load_accounts
            try:self.load_gateways(load_accounts(owner.runtime.api.CONFIG_DIR))
            except (ValueError,OSError):self.ai_status='用量连接读取失败，请检查设置'

    def load_gateways(self,accounts):
        if self.gateway:
            if accounts==self.gateway.accounts:return
            self.gateway.cancel();self.gateway.deleteLater();self.gateway=None
        if accounts:
            from resource_gateway import GatewayUsage
            self.gateway=GatewayUsage(self,accounts)
        self.providers=self.local_providers

    def provider_rows_changed(self):
        from resource_quota import remaining_percent,used_percent
        self.providers=[*self.local_providers,*(self.gateway.rows if self.gateway else ())]
        cfg=self.owner.cfg
        for row in self.providers:
            used=max((value for q in row.get('quotas',[]) if (value:=used_percent(q)) is not None),default=None)
            if used is None:continue
            level=2 if used>=80 else 1 if used>=60 else 0
            previous=self.previous_levels.get(row['id'],0);self.previous_levels[row['id']]=level
            if cfg['resource_quota_alert'] and level>previous:
                self.alert=f"{row['name']}  额度剩余 {remaining_percent(used):.0f}%";self.alert_until=time.monotonic()+5
        self.owner.display()

    def configure(self):
        if self.closed:return
        cfg=self.owner.cfg
        window=self.owner.window
        visible=getattr(self.owner,'feature_visible',None)
        desktop=cfg['resource_enabled'] and not getattr(self.owner.runtime,'game_active',False)
        ai_visible=visible('ai') if visible else desktop
        music_visible=visible('music') if visible else desktop
        detached=getattr(self.owner,'detached',None)
        music_card=detached('music') if detached else None
        strip=getattr(self.owner,'strip',None);task_music=bool(strip and strip.music_requested())
        compact=getattr(self.owner,'compact',cfg['resource_collapsed'])
        presentation=bool(music_card or music_visible and cfg['resource_music'] and window and
                          ((compact and cfg['resource_fold']!='ball' and cfg['resource_music_text']=='wave') or
                           (not compact and window.page_key=='music')))
        presentation=presentation or bool(task_music and strip.shows_wave())
        spectrum=bool(getattr(self.owner.runtime,'spectrum',None))
        ai=bool(cfg['resource_ai_tray'] or cfg['resource_ai'] and ai_visible)
        if self.gateway:self.gateway.set_active(ai)
        signature=(ai and bool(cfg['resource_ai_providers']),tuple(cfg['resource_ai_providers']),cfg['resource_music'] and music_visible or task_music,cfg['resource_lyrics'] and cfg['resource_music'] and music_visible,cfg['resource_equalizer'],presentation,spectrum)
        if not (signature[0] or signature[2] or signature[6]):
            self.signature=signature
            self.restart.stop()
            if self.local_providers:
                self.local_providers=[];self.provider_rows_changed()
            if self.process.state()!=QProcess.NotRunning and not self.idling:
                self.idling=True;self.send(op='quit');self.launch_watch.start(1500)
            return
        if self.idling or self.memory_blocked or self.restart.isActive():return
        if signature==self.signature and (self.process.state()!=QProcess.NotRunning or self.owner.runtime.dock.preview):return
        self.signature=signature
        if not signature[0] and self.local_providers:
            self.local_providers=[];self.provider_rows_changed()
        if not signature[2]:self.media={};self.cover=QPixmap();self.levels=[0.]*8
        if self.owner.runtime.dock.preview:return
        starting=self.process.state()==QProcess.NotRunning
        if starting:
            wait=getattr(self.owner.runtime,'bridge_start_after',0)-time.monotonic()
            if wait>0:
                self.restart.start(max(1, round(wait*1000)))
                return
            from deck_runtime import installed_runtime
            runtime=installed_runtime()
            if not runtime:
                self.status=self.ai_status='AI / 音乐需要 .NET 10 桌面运行库，可在设置中打开下载页';return
            root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'artifacts'
            exe=root/'deck-bridge/BigFishDeckBridge.exe'
            if not exe.is_file():self.status=self.ai_status='未找到 AI / 音乐组件';return
            self.launched_at=time.monotonic()
            self.launch_timed_out=False
            self.launch_watch.start(35000)
            start_headless(self.process, exe, Path(self.owner.runtime.api.CONFIG_DIR)/'deck-data', runtime)
        self.send(op='configure',ai=signature[0],providers=signature[1],music=signature[2],lyrics=signature[3],equalizer=signature[4],presentation=signature[5],desktopSpectrum=signature[6])
        if starting and self.history_requested:self.send(op='history',range='all')

    def request_history(self):
        if not self.history_requested:
            self.history_requested=True;self.send(op='history',range='all')

    def refresh(self):
        if self.closed:return
        if self.gateway:self.gateway.refresh()
        self.memory_blocked=False
        if self.process.state()==QProcess.NotRunning:
            self.restart.stop()
            self.configure()
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
        if kind=='ready':
            self.launch_watch.stop()
            return
        if kind=='spectrum':
            window=getattr(self.owner.runtime,'spectrum',None)
            if window:
                from desktop_spectrum import BANDS
                window.set_levels([max(0.,min(1.,float(n))) for n in data.get('levels',[])[:BANDS]])
            return
        if kind=='ai' and (cfg['resource_ai'] or cfg['resource_ai_tray']):
            if self.idling:return
            self.local_providers=data.get('providers',[])[:7];self.ai_status='更新于 '+str(data.get('at',''))[11:19]
            self.provider_rows_changed();return
        elif kind=='memory_error':
            self.memory_blocked=True;self.restart.stop();self.launch_watch.stop();self.status=self.ai_status=data.get('message','无法启用内存限制')
        elif kind=='ai_error':
            self.ai_status=data.get('message','读取失败')
            for row in self.local_providers:row['stale']=True
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
            if hasattr(self.owner,'detached') and (card:=self.owner.detached('music')):
                card.content.meter.update()
            strip=getattr(self.owner,'strip',None)
            if strip and strip.isVisible() and strip.shows_wave():strip.update()
            return
        elif kind in ('command','error') and data.get('message'):self.status=data['message']
        self.owner.display()

    def failed(self,error):
        if error==QProcess.FailedToStart:self.finished()

    def startup_timeout(self):
        if not self.closed and self.process.state()!=QProcess.NotRunning:
            self.launch_timed_out=True
            self.process.kill()

    def finished(self,*args):
        if self.closed:return
        self.launch_watch.stop()
        if self.idling:
            self.idling=False;self.signature=None;self.buffer.clear()
            self.configure();return
        if self.memory_blocked:self.owner.display();return
        if time.monotonic()-self.launched_at>=120:self.failures=0
        self.failures=min(self.failures+1,5)
        reason = ('启动超时' if self.launch_timed_out else
                  f'退出码 0x{args[0]&0xffffffff:08X}' if args else '无法启动进程')
        log=getattr(self.owner.runtime.api,'log',None)
        if log:log(f'AI / 音乐组件{reason}，稍后重试。')
        self.status=self.ai_status='组件连接中断，正在重试';self.signature=None;self.buffer.clear()
        self.local_providers=[];self.media={};self.cover=QPixmap();self.levels=[0.]*8
        spectrum=getattr(self.owner.runtime,'spectrum',None)
        if spectrum:spectrum.set_levels([])
        self.restart.start(min(60000,5000*2**(self.failures-1)));self.provider_rows_changed()
    def close(self):
        self.closed=True;self.restart.stop();self.launch_watch.stop();p=self.process
        if self.gateway:self.gateway.cancel()
        if p.state()!=QProcess.NotRunning:
            p.write(b'{"op":"quit"}\n');p.setParent(QApplication.instance())
            timer=QTimer(p);timer.setSingleShot(True);timer.timeout.connect(p.kill);timer.start(1500)
            p.finished.connect(p.deleteLater)
        self.deleteLater()
