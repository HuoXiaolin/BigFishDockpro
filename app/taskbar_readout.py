"""An independently enabled, two-line resource display in a verified taskbar gap."""
import ctypes
from ctypes import wintypes
from PyQt5.QtCore import Qt,QRect
from PyQt5.QtGui import QColor,QFont,QFontMetrics,QPainter
from PyQt5.QtWidgets import QWidget,QApplication
from resource_taskbar import Placement
from ui_style import AlignedMenu


def transfer(value):
    if value>=2**20:return f'{value/2**20:.1f}M/s'
    if value>=1024:return f'{value/1024:.0f}K/s'
    return f'{value:.0f}B/s'


def columns(service):
    enabled=set(service.cfg['resource_task_metrics'])
    data=service.latest
    sensors=service.sensors.values if service.sensors else {}
    def cell(key,label):
        if key not in enabled:return None
        value='—';tip='';number=None
        if key in ('cpu_temp','gpu_temp','cpu_power','gpu_power'):
            reading=sensors.get(key)
            if reading:
                tip=reading['source']
                if key=='cpu_temp' and reading['label']=='系统温区':
                    label='温区'
                number=reading['value'];value=f'{number:g}'+('°C' if key.endswith('temp') else 'W')
        elif key=='fps':
            if service.fps:
                number=service.fps.value;tip=service.fps.name
                if number is not None:value=f'{number:.0f}'
        else:
            entry=data.get(key)
            if entry is not None:
                number=entry[0] if key=='memory' else entry
                value=f'{number:.1f}%' if key=='memory' else f'{number:.0f}%'
        return (label,value,key,number,tip)
    network=data.get('network')
    pair=[(arrow,transfer(network[i]) if network is not None else '—','network',None,'下载' if i==0 else '上传') for i,arrow in enumerate(('↓','↑'))] if 'network' in enabled else [None,None]
    pairs=[(cell('cpu_temp','CPU'),cell('cpu_power','CPWR')),(cell('gpu_temp','GPU'),cell('gpu_power','GPWR')),
           (cell('memory','内存'),cell('fps','FPS')),tuple(pair),(cell('cpu','CPU占用'),cell('gpu','GPU占用'))]
    return [p for p in pairs if any(p)]


class TaskbarReadout(QWidget):
    def __init__(self,service):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.NoDropShadowWindowHint|Qt.WindowDoesNotAcceptFocus)
        self.service=service;self.placement=Placement(self);self.press=None;self.page=0;self.page_count=1;self.host=0;self.cells=[]
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('任务栏监控 · 大肥鱼Dock');self.setAccessibleName('任务栏监控')

    def reposition(self):
        slot=self.placement.slot
        if slot is None or not self.placement.target:self.hide();return
        if self.geometry()!=slot:self.setGeometry(slot)
        self.show()
        hwnd=self.placement.target['hwnd']
        if self.host!=hwnd and not self.service.runtime.dock.preview:
            user=ctypes.windll.user32;win=int(self.winId())
            user.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t];user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowLongPtrW(win,-8,hwnd);user.SetWindowPos(win,-1,0,0,0,0,0x13);self.host=hwnd

    def placement_changed(self):
        self.reposition();self.service.sync()

    def refresh(self):
        if not self.isVisible():return
        self.cells=columns(self.service)
        info='\\n'.join(f'{label}  {value}'+(' · '+tip if tip else '') for pair in self.cells for item in pair if item for label,value,key,number,tip in (item,))
        self.setAccessibleDescription(info)
        if self.toolTip()!=info:self.setToolTip(info)
        self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.TextAntialiasing|QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor(0,0,0,1))
        vertical=self.height()>self.width()
        font=QFont(self.font());font.setWeight(QFont.DemiBold)
        font.setPixelSize(max(8,min(11,(self.height()-2)//2-1)) if not vertical else 9)
        p.setFont(font);fm=QFontMetrics(font)
        mode=self.service.cfg.get('taskbar_text_mode','system')
        if mode=='system':
            light_ink=(getattr(self,'system_mode',1)==0)
        else:light_ink=mode=='light'
        ink=QColor('#ffffff' if light_ink else '#182432')
        normal=QColor('#86efa4' if light_ink else '#08703f')
        warm=QColor('#ffcf74' if light_ink else '#985200');hot=QColor('#ff9992' if light_ink else '#ae292f')
        if not self.cells:
            p.setPen(ink);p.drawText(self.rect(),Qt.AlignCenter,'—');self.page_count=1;return
        pairs=self.cells
        widths=[max(fm.horizontalAdvance(item[0])+fm.horizontalAdvance(item[1])+5 for item in pair if item) for pair in pairs]
        pages=[];page=[];total=0;span=max(1,self.width()-8)
        for pair,w in zip(pairs,widths):
            if page and (vertical or total+w+5>span):
                pages.append(page);page=[];total=0
            page.append((pair,min(w,span)));total+=w+5
        if page:pages.append(page)
        self.page_count=len(pages);self.page%=self.page_count
        page=pages[self.page]
        used=sum(w for _,w in page)+5*(len(page)-1)
        x=max(3,(self.width()-used)//2);line=fm.height()
        top=max(0,(self.height()-2*line)//2)
        for pair,w in page:
            for row,item in enumerate(pair):
                if not item:continue
                label,value,key,number,_=item
                color=normal
                if key.endswith('_temp') and number is not None:color=hot if number>=85 else warm if number>=60 else normal
                elif key in ('cpu','gpu','memory') and number is not None:color=hot if number>=90 else warm if number>=70 else normal
                if number is None and value=='—':color=ink
                if vertical:
                    h=max(1,self.height()//2);y=row*h
                    p.setPen(ink);p.drawText(QRect(0,y,self.width(),h//2),Qt.AlignCenter,label)
                    p.setPen(color);p.drawText(QRect(0,y+h//2,self.width(),h//2),Qt.AlignCenter,fm.elidedText(value,Qt.ElideRight,self.width()))
                else:
                    y=top+row*line;lw=min(w,fm.horizontalAdvance(label)+3)
                    p.setPen(ink);p.drawText(QRect(x,y,lw,line),Qt.AlignLeft|Qt.AlignVCenter,label)
                    p.setPen(color);p.drawText(QRect(x+lw,y,w-lw,line),Qt.AlignLeft|Qt.AlignVCenter,fm.elidedText(value,Qt.ElideRight,max(0,w-lw)))
            x+=w+5

    def sync_style(self):
        from taskbar_text import read_mode
        try:self.system_mode=read_mode()
        except OSError:self.system_mode=1
        self.refresh()

    def wheelEvent(self,event):
        if not event.angleDelta().y():event.ignore();return
        self.page=(self.page+(-1 if event.angleDelta().y()>0 else 1))%max(1,self.page_count);self.update();event.accept()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.press=event.globalPos();event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.press is None:return
        pos=event.globalPos();distance=(pos-self.press).manhattanLength();self.press=None
        if distance<QApplication.startDragDistance():
            self.page=(self.page+1)%max(1,self.page_count);self.update();return
        bar=next((bar for bar in self.placement.bars() if bar['rect'].contains(pos)),None)
        if bar:self.placement.offer(bar,pos)
        else:self.service.return_from_taskbar(pos)
    def contextMenuEvent(self,event):
        menu=AlignedMenu(self);menu.addAction('监控设置…',self.service.settings)
        menu.addAction('移到桌面',lambda:self.service.return_from_taskbar(None))
        menu.addAction('关闭任务栏监控',lambda:self.service.set_options(resource_taskbar=False))
        try:menu.exec_(event.globalPos())
        finally:menu.deleteLater()
    def dispose(self):
        self.placement.close();self.hide();self.deleteLater()
