"""Capture compatibility checks with synthetic pixels and fake Windows APIs."""
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import QRect,Qt,QRectF
from PyQt5.QtGui import QPixmap,QColor,QImage,QPainter,QPainterPath,QLinearGradient
import glass_capture as capture


class Function:
    def __init__(self,call):self.call=call
    def __call__(self,*args):return self.call(*args)


def run(checks):
    bright=QPixmap(240,120);bright.fill(QColor('#d9eaff'));bright.setDevicePixelRatio(1.5)
    black=QPixmap(240,120);black.fill(QColor('#000000'))
    transparent=QPixmap(10,10);transparent.fill(QColor(255,255,255,0))
    dark=QPixmap(10,10);dark.fill(QColor('#101820'))
    assert capture.valid_backdrop(bright) and capture.valid_backdrop(dark)
    assert not capture.valid_backdrop(black) and not capture.valid_backdrop(transparent)
    assert not capture.valid_backdrop(QPixmap())
    calls=[];states={1:0,2:1}
    def get(hwnd,value):value._obj.value=states[hwnd];return True
    def set_(hwnd,value):calls.append((hwnd,value));states[hwnd]=value;return True
    user=SimpleNamespace(GetWindowDisplayAffinity=Function(get),SetWindowDisplayAffinity=Function(set_))
    dll=SimpleNamespace(user32=user,dwmapi=SimpleNamespace(DwmFlush=lambda:None))
    grab=[];pixels=[bright]
    def grab_window(*args):grab.append(args);return pixels[0]
    screen=SimpleNamespace(geometry=lambda:QRect(-1920,0,1920,1080),grabWindow=grab_window)
    def window(hwnd):return SimpleNamespace(isVisible=lambda:True,winId=lambda:hwnd,frameGeometry=lambda:QRect(-1850,20,160,80))
    first,second=window(1),window(2)
    with patch.object(capture.sys,'getwindowsversion',return_value=SimpleNamespace(build=19045)),patch.object(capture.ctypes,'windll',dll),patch.object(capture.QApplication,'screenAt',return_value=screen):
        assert capture.capture_behind(first,[first,second]) is bright
        assert grab==[(0,70,20,160,80)] and states=={1:0,2:1}
        assert calls==[(1,17),(2,17),(2,1),(1,0)]
        pixels[0]=black;assert capture.capture_behind(first,[second]) is None and states=={1:0,2:1}
        with patch.object(capture.sys,'getwindowsversion',return_value=SimpleNamespace(build=18363)):
            count=len(calls);assert capture.capture_behind(first,[second]) is None and len(calls)==count
        calls.clear()
        def fail_second(hwnd,value):
            if hwnd==2 and value==17:return False
            return set_(hwnd,value)
        user.SetWindowDisplayAffinity=Function(fail_second)
        assert capture.capture_behind(first,[second]) is None and states=={1:0,2:1}
        assert calls==[(1,17),(1,0)]
    # Explicit source rectangles are in physical pixels, not logical Qt units.
    # A half-width sample of a 200%-DPR gradient gives 64 instead of 128.
    from liquid_glass import paint_liquid_glass
    for ratio in (1,1.5,2):
        pm=QPixmap(round(100*ratio),round(50*ratio));p=QPainter(pm)
        gradient=QLinearGradient(0,0,pm.width(),0);gradient.setColorAt(0,QColor(0,0,0));gradient.setColorAt(1,QColor(255,255,255));p.fillRect(pm.rect(),gradient);p.end();pm.setDevicePixelRatio(ratio)
        target=QImage(100,50,QImage.Format_ARGB32);target.fill(Qt.transparent)
        painter=QPainter(target);rect=QRectF(0,0,100,50);path=QPainterPath();path.addRect(rect)
        surface=SimpleNamespace(cfg={'glass':True,'dock_material':'liquid'},backdrop=pm,spec_alpha=0,spec_x=0)
        colors={'tint':QColor('white'),'border':QColor(0,0,0,0)}
        paint_liquid_glass(surface,painter,path,rect,rect,colors,0,[(0,0),(1,0)]);painter.end()
        assert 124<=target.pixelColor(50,25).red()<=132,(ratio,target.pixelColor(50,25).red())
        assert target.pixelColor(90,25).red()>225,(ratio,target.pixelColor(90,25).red())
    checks.append('glass DPR drawing: full gradient extent and midpoint preserved at 100/150/200 percent instead of sampling only the top-left fraction')
    checks.append('glass capture: logical screen-local coordinates at 150 percent and negative monitor origin, DPR retained, all overlapping surfaces excluded, original affinities restored on success and partial failure, pre-2004 Windows bypass, black/transparent rejection with genuine dark tint retained')
