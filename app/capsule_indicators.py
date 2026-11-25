"""Read explicitly selected device states and animate their compact badges."""
import ctypes as C
from ctypes import wintypes as W
import json
import math
import os
import time

from PyQt5.QtCore import QObject, QPointF, QProcess, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen

from resource_options import DEVICE_ALERTS

GROW, HOLD, SHRINK = .19, 5., .23
KEYBOARD = {'caps_lock', 'input_mode', 'num_lock'}
ACTIVE_INK = {
    'caps_lock': ('#2458a0','#a8d2ff'), 'input_mode': ('#53409b','#d5c3ff'),
    'num_lock': ('#006874','#9ee6eb'), 'microphone': ('#14644e','#92e7bb'),
    'touchpad': ('#245999','#9fd5ff'), 'bluetooth_link': ('#2857a6','#b1d2ff'),
    'network_link': ('#176a64','#9eece1'),
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
        if self.user.SystemParametersInfoW(0x00AE,C.sizeof(params),C.byref(params),0):
            return bool(params[3]&16) if params[3]&1 else None
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad\Status') as key:
                enabled,kind=winreg.QueryValueEx(key,'Enabled')
                return bool(enabled) if kind==winreg.REG_DWORD and enabled in (0,1) else None
        except OSError:return None


def description(kind,value,previous=None):
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
        self.native=None;self.touch_due=0.
        self.bluetooth=QProcess(self);self.bluetooth.finished.connect(self.links_finished)
        self.link_timer=QTimer(self);self.link_timer.setInterval(5000);self.link_timer.timeout.connect(self.read_links)
        self.link_timeout=QTimer(self);self.link_timeout.setSingleShot(True);self.link_timeout.timeout.connect(self.bluetooth.kill)

    def configure(self,selected):
        selected=tuple(k for k in DEVICE_ALERTS if k in selected)
        if selected==self.selected:return
        self.selected=selected
        self.values={k:v for k,v in self.values.items() if k in selected}
        self.transitions={k:v for k,v in self.transitions.items() if k in selected}
        self.poll.stop();self.link_timer.stop()
        if not (self.owner.runtime.dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP')):
            if KEYBOARD.intersection(selected) or 'touchpad' in selected:
                if self.native is None:self.native=ForegroundInput()
                self.poll.start(240 if KEYBOARD.intersection(selected) else 900)
                self.read_local()
            if 'bluetooth_link' in selected:
                self.link_timer.start();self.read_links()
        if 'bluetooth_link' not in selected:
            self.link_timeout.stop()
            if self.bluetooth.state()!=QProcess.NotRunning:self.bluetooth.kill()
        self.advance()

    def read_local(self):
        for key,vk in (('caps_lock',0x14),('num_lock',0x90)):
            if key in self.selected:self.observe(key,bool(self.native.user.GetKeyState(vk)&1))
        if 'input_mode' in self.selected:self.observe('input_mode',self.native.language())
        if 'touchpad' in self.selected and self.clock()>=self.touch_due:
            self.touch_due=self.clock()+.85;self.observe('touchpad',self.native.touchpad())

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

    def observe(self,kind,value):
        if kind not in self.selected:return
        old=self.values.get(kind)
        if old==value:return
        if value is None:
            self.values.pop(kind,None);self.transitions.pop(kind,None)
        else:
            self.values[kind]=value
            if old is not None:
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
            window.update()

    def cells(self,capacity,height):
        side=min(23,max(14,height-8));space=max(0,int(capacity));now=self.clock()
        ordered=[k for k in self.selected if k in self.values]
        priority=sorted(ordered,key=lambda k:self.transitions.get(k,(-1,))[0],reverse=True)
        visible=priority[:space//(side+3)]
        spare=space-len(visible)*(side+3)
        font=QFont();font.setPixelSize(11);metrics=QFontMetrics(font);items={}
        for key in visible:
            label=self.transitions[key][2] if key in self.transitions else ''
            extra=min(spare,round(self.fraction(key,now)*min(156,metrics.horizontalAdvance(label)+6)))
            items[key]=(key,side,side+extra,label);spare-=extra
        return [items[key] for key in ordered if key in items]

    def paint(self,p,items,left,middle,colors):
        for kind,side,width,label in items:
            value=self.values[kind]
            active=bool(value) or kind=='input_mode'
            ink=QColor(ACTIVE_INK[kind][0 if colors['light'] else 1] if active else colors['muted'])
            tint=QColor(ink);tint.setAlpha(42 if active else 25)
            box=QRectF(left,middle-side/2,width,side);left+=width+3
            p.save();p.setPen(Qt.NoPen);p.setBrush(tint);p.drawRoundedRect(box,5,5)
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
    elif kind=='bluetooth_link':
        path=QPainterPath(QPointF(-4,-4));path.lineTo(4,4);path.lineTo(0,7);path.lineTo(0,-7);path.lineTo(4,-4);path.lineTo(-4,4);p.drawPath(path)
    else:
        for radius in (4,8):
            p.drawArc(QRectF(-radius,4-radius,2*radius,2*radius),43*16,94*16)
        p.setBrush(ink);p.drawEllipse(QPointF(0,4),1.1,1.1)
    if not value and kind not in ('caps_lock','input_mode'):
        p.drawLine(QPointF(-6,-6),QPointF(6,6))
    p.restore()
