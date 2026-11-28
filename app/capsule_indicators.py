"""Read explicitly selected device states and animate their compact badges."""
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
import time

from PyQt5.QtCore import QObject, QPointF, QProcess, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen

from resource_options import DEVICE_ALERTS, compact_tile_height
from compact_colors import content_colors, badge_fill, on_badge, text_ink

GROW, HOLD, SHRINK = .19, 5., .23
KEYBOARD = {'caps_lock', 'input_mode', 'num_lock'}
ACTIVE_INK = {
    'caps_lock': ('#2458a0','#a8d2ff'), 'input_mode': ('#53409b','#d5c3ff'),
    'num_lock': ('#006874','#9ee6eb'), 'microphone': ('#14644e','#92e7bb'),
    'touchpad': ('#245999','#9fd5ff'), 'bluetooth_link': ('#2857a6','#b1d2ff'),
    'network_link': ('#176a64','#9eece1'),
    'volume': ('#285e92','#a7d4ff'), 'brightness': ('#815719','#f4cc89'),
}


class ForegroundInput:
    def __init__(self):
        self.user=C.WinDLL('user32')
        self.ime=C.WinDLL('imm32')
        self.user.GetForegroundWindow.restype=W.HWND
        self.user.GetWindowThreadProcessId.argtypes=(W.HWND,C.POINTER(W.DWORD))
        self.user.GetKeyboardLayout.argtypes=(W.DWORD,)
        self.user.GetKeyboardLayout.restype=W.HANDLE
        self.ime.ImmGetDefaultIMEWnd.argtypes=(W.HWND,)
        self.ime.ImmGetDefaultIMEWnd.restype=W.HWND
        self.user.SendMessageTimeoutW.argtypes=(W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,C.POINTER(C.c_size_t))

    def language(self):
        hwnd=self.user.GetForegroundWindow()
        thread=self.user.GetWindowThreadProcessId(hwnd,None) if hwnd else 0
        if not thread:return None
        language=(self.user.GetKeyboardLayout(thread) or 0)&0x3ff
        if language==9:return 'en'
        if language!=4:return None
        ime=self.ime.ImmGetDefaultIMEWnd(hwnd)
        if not ime:return None
        def read(command):
            value=C.c_size_t()
            if self.user.SendMessageTimeoutW(ime,0x0283,command,0,2,30,C.byref(value)):
                return value.value
        opened=read(5)
        if opened==0:return 'en'
        mode=read(1) if opened is not None else None
        return None if mode is None else ('zh' if mode&1 else 'en')

    def touchpad(self):
        # TOUCHPAD_PARAMETERS_V1, including the two packed DWORD flag words.
        params=(W.UINT*11)(1)
        available=self.user.SystemParametersInfoW(0x00AE,C.sizeof(params),C.byref(params),0)
        flags=params[3]
        if available and (flags&1 or (flags&2 and params[2]&1)):
            # touchpadEnabled is the switch. touchpadActive can be false just
            # because an external mouse is connected while the switch is on.
            return bool(flags&0x08)
        import winreg
        path=r'Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad\Status'
        for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive,path) as key:
                    enabled,kind=winreg.QueryValueEx(key,'Enabled')
                if kind==winreg.REG_DWORD:
                    if available and not flags&3 and enabled:return None
                    return bool(enabled)
            except OSError:
                continue
        return None


def description(kind,value,previous=None):
    if kind=='volume':return '系统音量已静音' if value[1] else f'系统音量 {value[0]}%'
    if kind=='brightness':return f'屏幕亮度 {value}'
    if kind=='touchpad' and value=='pending':return '触控板状态待确认，按专用键后同步'
    if kind in ('bluetooth_link','network_link'):
        devices=dict(value)
        if previous is not None:
            old=dict(previous)
            def names(keys,rows):
                keys=sorted(keys)
                return rows[keys[0]]+(f' 等 {len(keys)} 台' if len(keys)>1 else '')
            added=devices.keys()-old.keys();removed=old.keys()-devices.keys()
            if kind=='network_link':
                added|={k for k in devices.keys()&old.keys() if devices[k]!=old[k]}
            changes=[]
            if added:changes.append('已连接 '+names(added,devices))
            if removed:changes.append('已断开 '+names(removed,old))
            if changes:return ' · '.join(changes)
        if kind=='network_link':return '已连接 '+ '、'.join(devices.values()) if devices else '网络已断开'
        return f'蓝牙已连接 {len(devices)} 台' if devices else '蓝牙未连接'
    if kind=='input_mode':return '中文输入' if value=='zh' else '英文输入'
    labels={'caps_lock':('小写','大写锁定'),'num_lock':('小键盘已关闭','小键盘已开启'),
            'microphone':('麦克风已静音','麦克风已开启'),'touchpad':('触控板已关闭','触控板已开启')}
    return labels[kind][bool(value)]


class Indicators(QObject):
    def __init__(self,owner,clock=time.monotonic):
        super().__init__(owner)
        self.owner=owner;self.clock=clock
        self.selected=();self.values={};self.transitions={}
        self.frame=QTimer(self);self.frame.setSingleShot(True);self.frame.timeout.connect(self.advance)
        self.poll=QTimer(self);self.poll.timeout.connect(self.read_local)
        self.native=None
        self.touchpad_watch=None;self.touchpad_source='windows'
        self.audio=None;self.brightness=None;self.power_reading=False;self.display_device=''
        self.bluetooth=QProcess(self);self.bluetooth.finished.connect(self.links_finished)
        self.link_timer=QTimer(self);self.link_timer.setInterval(5000);self.link_timer.timeout.connect(self.read_links)
        self.link_timeout=QTimer(self);self.link_timeout.setSingleShot(True);self.link_timeout.timeout.connect(self.bluetooth.kill)

    def configure(self,selected,watch_touchpad=False):
        selected=tuple(k for k in DEVICE_ALERTS if k in selected)
        live=not (self.owner.runtime.dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.configure_touchpad(watch_touchpad and live)
        display_device=self.owner.cfg['resource_display_device'] if 'brightness' in selected else ''
        if selected==self.selected and display_device==self.display_device:return
        if display_device!=self.display_device and not self.power_reading:
            self.values.pop('brightness',None);self.transitions.pop('brightness',None)
        self.display_device=display_device
        self.selected=selected
        self.values={k:v for k,v in self.values.items() if k in selected}
        self.transitions={k:v for k,v in self.transitions.items() if k in selected}
        self.poll.stop();self.link_timer.stop()
        self.configure_readers(set(selected) if live else set())
        if live:
            if KEYBOARD.intersection(selected) or 'touchpad' in selected:
                if self.native is None:self.native=ForegroundInput()
                self.poll.start(240)
                self.read_local()
            if 'bluetooth_link' in selected:
                self.link_timer.start();self.read_links()
        if 'bluetooth_link' not in selected:
            self.link_timeout.stop()
            if self.bluetooth.state()!=QProcess.NotRunning:self.bluetooth.kill()
        self.advance()

    def configure_touchpad(self,enabled):
        if enabled and self.touchpad_watch is None:
            from device_alert_readings import TouchpadSwitchRead,has_oem_touchpad
            if has_oem_touchpad():
                self.touchpad_source='pending'
                self.touchpad_watch=TouchpadSwitchRead()
                self.touchpad_watch.reported.connect(self.touchpad_reported,Qt.QueuedConnection)
                self.touchpad_watch.start()
        elif not enabled and self.touchpad_watch is not None:
            worker,self.touchpad_watch=self.touchpad_watch,None
            worker.requestInterruption();worker.deleteLater()
            self.touchpad_source='windows'

    def touchpad_reported(self,source):
        if self.sender() is not self.touchpad_watch or self.touchpad_watch is None:return
        self.touchpad_source=source
        if 'touchpad' in self.selected:
            self.read_touchpad(changed=source in ('on','off'))

    def read_touchpad(self,changed=False):
        system=self.native.touchpad()
        source=self.touchpad_source
        if source=='windows' or system is False:value=system
        elif source=='pending':value='pending'
        else:value=source=='on'
        self.observe('touchpad',value,changed=changed)

    def configure_readers(self,selected):
        from device_alert_readings import AudioSwitchRead,BrightnessNotifications
        audio_keys=selected & {'microphone','volume'}
        if self.audio and self.audio.keys!=audio_keys:
            old,self.audio=self.audio,None
            old.requestInterruption();old.deleteLater()
        if audio_keys and self.audio is None:
            self.audio=AudioSwitchRead(audio_keys)
            self.audio.changed.connect(self.audio_changed,Qt.QueuedConnection)
            self.audio.start()
        # A system brightness hotkey controls the built-in screen, even if a
        # different display is selected for the hardware monitoring page.
        subscribed='brightness' in selected
        if self.brightness and not subscribed:
            self.brightness.close();self.brightness=None;self.power_reading=False
        elif subscribed and self.brightness is None:
            self.brightness=BrightnessNotifications()
            self.brightness.changed.connect(self.brightness_changed,Qt.QueuedConnection)
            if not self.brightness.start():
                self.brightness.close();self.brightness=None

    def audio_changed(self,key,value):
        if self.sender() is self.audio and self.audio is not None:self.observe(key,value)

    def brightness_changed(self,value):
        if self.sender() is self.brightness and self.brightness is not None:
            self.power_reading=True
            self.observe('brightness',value)

    def sensor_brightness(self,reading):
        if not self.power_reading:
            value=(reading or {}).get('value')
            self.observe('brightness',round(value) if value is not None else None)

    def read_local(self):
        for key,vk in (('caps_lock',0x14),('num_lock',0x90)):
            if key in self.selected:self.observe(key,bool(self.native.user.GetKeyState(vk)&1))
        if 'input_mode' in self.selected:self.observe('input_mode',self.native.language())
        if 'touchpad' in self.selected:self.read_touchpad()

    def read_links(self):
        from bluetooth_gauge import probe_program
        from probe_lifecycle import allowed,start
        if self.bluetooth.state()!=QProcess.NotRunning or not allowed():return
        program=probe_program()
        if program.is_file() and start(self.bluetooth,program,['--bluetooth-links']):
            self.link_timeout.start(4000)

    def links_finished(self,code,status):
        self.link_timeout.stop()
        raw=bytes(self.bluetooth.readAllStandardOutput())
        if code or status!=QProcess.NormalExit or len(raw)>65536:return
        try:
            rows=json.loads(raw.decode('utf-8-sig'))
            if not isinstance(rows,list):return
            devices=tuple(sorted((r['id'],str(r['name'] or '蓝牙设备')[:96]) for r in rows if r.get('id')))
        except (AttributeError,KeyError,TypeError,ValueError):return
        self.observe('bluetooth_link',devices)

    def observe(self,kind,value,*,changed=False):
        if kind not in self.selected:return
        old=self.values.get(kind)
        if old==value:return
        if value is None:
            self.values.pop(kind,None);self.transitions.pop(kind,None)
        else:
            self.values[kind]=value
            if kind=='touchpad' and value=='pending':
                self.transitions.pop(kind,None)
            elif (old is not None and old!='pending') or changed:
                if kind=='bluetooth_link' and dict(old).keys()==dict(value).keys():return
                now=self.clock()
                fraction=self.fraction(kind,now)
                self.transitions[kind]=(now,fraction,description(kind,value,old))
                self.owner.peek_reminder()
        self.advance()

    def fraction(self,key,now):
        transition=self.transitions.get(key)
        if not transition:return 0.
        start,initial,_=transition
        age=max(0.,now-start)
        if not self.owner.cfg.get('motion_enabled',True):return float(age<HOLD)
        if age<GROW:
            return 1-(1-initial)*(1-age/GROW)**3
        return 1-min(1.,max(0.,(age-HOLD+SHRINK)/SHRINK))**2

    def advance(self):
        now=self.clock();self.frame.stop();waits=[]
        for key,(start,_,_) in list(self.transitions.items()):
            age=now-start
            if age>=HOLD:self.transitions.pop(key);continue
            if not self.owner.cfg.get('motion_enabled',True):waits.append(math.ceil(1000*(HOLD-age)))
            else:waits.append(24 if age<GROW or age>=HOLD-SHRINK else math.ceil(1000*(HOLD-SHRINK-age)))
        if waits:self.frame.start(max(1,min(waits)))
        window=self.owner.window
        if window and self.owner.compact:
            window._compact_cache=None
            if window.isVisible() and (self.owner.cfg['resource_compact_auto_width'] or self.owner.cfg['resource_fold']=='ball'):
                window.reposition()
            window.sync_rotation()
            window.update()

    def cells(self,capacity,height):
        side=compact_tile_height(self.owner.cfg,height);space=max(0,int(capacity));now=self.clock()
        ordered=[k for k in self.selected if k in self.values]
        active=sorted((k for k in ordered if k in self.transitions),key=lambda k:self.transitions[k][0],reverse=True)
        visible=active[:space//(side+3)]
        space-=len(visible)*(side+3)
        font=QFont();font.setPixelSize(11);metrics=QFontMetrics(font);items={}
        for key in visible:
            value=self.values[key]
            if key=='volume':label='0' if value[1] else str(value[0])
            elif key=='brightness':label=str(value)
            else:label=self.transitions[key][2]
            sample='100' if key in ('volume','brightness') else label
            extra=min(space,round(self.fraction(key,now)*min(156,metrics.horizontalAdvance(sample)+6)))
            items[key]=(key,side,side+extra,label);space-=extra
        for key in ordered:
            if space<side+3:break
            if key not in self.transitions:
                items[key]=(key,side,side,'');space-=side+3
        return [items[key] for key in ordered if key in items]

    def paint(self,p,items,left,middle,colors):
        for kind,side,width,label in items:
            value=self.values[kind]
            active=(not value[1] if kind=='volume' else value!='pending' and (bool(value) or kind in ('input_mode','brightness')))
            box=QRectF(left,middle-side/2,width,side);left+=width+3
            local=content_colors(self.owner.window,box,colors)
            accent=ACTIVE_INK[kind][0 if local['light'] else 1]
            fill=badge_fill(accent,local,active)
            ink=QColor(text_ink(accent if active else local['muted'],on_badge(local,fill)))
            p.save();p.setPen(Qt.NoPen);p.setBrush(fill);p.drawRoundedRect(box,5,5)
            p.setPen(ink);p.setBrush(Qt.NoBrush)
            symbol=QRectF(box.left(),box.top(),side,side)
            draw_symbol(p,symbol,kind,value,ink)
            if width>side+3:
                font=QFont(p.font());font.setPixelSize(11);p.setFont(font)
                area=box.adjusted(side,0,-3,0);p.setClipRect(area)
                p.drawText(area,Qt.AlignVCenter|Qt.AlignLeft,QFontMetrics(font).elidedText(label,Qt.ElideRight,int(area.width())))
            p.restore()


def draw_symbol(p,rect,kind,value,ink):
    p.save();p.translate(rect.center());scale=rect.width()/24;p.scale(scale,scale)
    p.setPen(QPen(ink,1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    if kind in KEYBOARD:
        char=('中' if value=='zh' else '英') if kind=='input_mode' else ('A' if value else 'a') if kind=='caps_lock' else '1'
        font=QFont(p.font());font.setPixelSize(14);font.setBold(True);p.setFont(font)
        p.drawText(QRectF(-10,-11,20,22),Qt.AlignCenter,char)
    elif kind=='microphone':
        p.drawRoundedRect(QRectF(-2.5,-6,5,8),2.5,2.5);p.drawArc(QRectF(-5,-4,10,9),180*16,180*16)
        p.drawLine(QPointF(0,5),QPointF(0,7));p.drawLine(QPointF(-3,7),QPointF(3,7))
    elif kind=='touchpad':
        p.drawRoundedRect(QRectF(-7,-5,14,10),1.8,1.8);p.drawLine(QPointF(-6,2),QPointF(6,2))
        if value=='pending':
            for x in (-3,0,3):p.drawPoint(QPointF(x,-1.5))
    elif kind=='volume':
        draw_volume_speaker(p,value,3)
    elif kind=='brightness':
        draw_brightness_sun(p,value,3)
    elif kind=='bluetooth_link':
        path=QPainterPath(QPointF(-4,-4));path.lineTo(4,4);path.lineTo(0,7);path.lineTo(0,-7);path.lineTo(4,-4);path.lineTo(-4,4);p.drawPath(path)
    else:
        for radius in (4,8):
            p.drawArc(QRectF(-radius,4-radius,2*radius,2*radius),43*16,94*16)
        p.setBrush(ink);p.drawEllipse(QPointF(0,4),1.1,1.1)
    if not value and kind not in ('caps_lock','input_mode','brightness'):
        p.drawLine(QPointF(-6,-6),QPointF(6,6))
    p.restore()


def dim_pen(pen):
    muted=QPen(pen)
    ink=muted.color()
    ink.setHsl(ink.hslHue(),round(ink.hslSaturation()*.22),ink.lightness(),round(ink.alpha()*.42))
    muted.setColor(ink)
    return muted


def draw_volume_speaker(p,value,radius):
    level,muted=value or (0,False)
    p.save();p.scale(radius/3,radius/3)
    pen=p.pen()
    speaker=QPainterPath(QPointF(-7,-2.15));speaker.lineTo(-4.7,-2.15);speaker.lineTo(-1.7,-5.25)
    speaker.lineTo(-1.7,5.25);speaker.lineTo(-4.7,2.15);speaker.lineTo(-7,2.15);speaker.closeSubpath()
    p.drawPath(speaker)
    if muted:
        p.drawLine(QPointF(2.2,-2.3),QPointF(6.8,2.3));p.drawLine(QPointF(2.2,2.3),QPointF(6.8,-2.3))
    else:
        wave=QPen(pen);wave.setWidthF(1.15)
        quiet=dim_pen(wave)
        lit=min(4,max(0,math.ceil(level/25)))
        for i,r in enumerate((2.,4.,6.,8.)):
            p.setPen(wave if i<lit else quiet)
            p.drawArc(QRectF(-1.1-r,-r,2*r,2*r),-52*16,104*16)
    p.restore()


def draw_brightness_sun(p,value,radius):
    pen=p.pen();quiet=dim_pen(pen)
    light=QPen(pen);light.setColor(QColor('#c86d08' if pen.color().lightness()<128 else '#ffda80'))
    p.drawEllipse(QPointF(),radius,radius)
    lit=min(8,max(0,math.ceil((value or 0)*8/100)))
    p.save();p.rotate(-90)
    for i in range(8):
        p.setPen(light if i<lit else quiet)
        p.drawLine(QPointF(radius*1.65,0),QPointF(radius*2.3,0))
        p.rotate(45)
    p.restore()
