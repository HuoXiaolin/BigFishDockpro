"""An independently enabled, two-line resource display in a verified taskbar gap."""
from ctypes import wintypes
from PyQt5.QtCore import Qt,QRect,QRectF,QPointF
from PyQt5.QtGui import QColor,QFont,QFontMetrics,QPainter
from PyQt5.QtWidgets import QWidget,QApplication
from resource_taskbar import Placement
from ui_style import AlignedMenu
from resource_options import SENSOR_UNITS,METRICS,TASK_COLUMN_NAMES,TASKBAR_LAYERS


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
        if key in SENSOR_UNITS:
            reading=sensors.get(key)
            if reading:
                tip=reading['source']
                if key=='cpu_temp' and reading['label']=='系统温区':
                    label='温区'
                number=reading['value'];value=f'{number:g}'+reading.get('unit',SENSOR_UNITS[key])
            elif service.cfg['resource_hide_unavailable']:return None
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
    groups = {
        'cpu_temp': [(cell('cpu_temp','CPU'),cell('cpu_power','CPWR'))],
        'gpu_temp': [(cell('gpu_temp','GPU'),cell('gpu_power','GPWR'))],
        'memory': [(cell('memory','内存'),cell('fps','FPS'))],
        'network': [tuple(pair)],
        'cpu': [(cell('cpu','CPU占用'),cell('gpu','GPU占用'))],
        'traffic': [],
        'sensors': [],
    }
    if 'traffic' in enabled:
        from resource_traffic import amount
        traffic=data.get('traffic',{})
        for period,label in [('day','日'),('month','月'),('year','年')]:
            v=traffic.get(period)
            groups['traffic'].append(tuple((label+arrow,amount(v[i]).replace(' ',''),'traffic',None,label+'流量'+('下载' if i==0 else '上传'))
                               if v is not None else (label+arrow,'—','traffic',None,'等待流量统计') for i,arrow in enumerate(('↓','↑'))))
    extras=[cell(k,METRICS[k]) for k in SENSOR_UNITS if k not in ('cpu_temp','gpu_temp','cpu_power','gpu_power')]
    for i in range(0,len(extras),2):groups['sensors'].append(tuple((extras[i:i+2]+[None])[:2]))
    order = service.cfg.get('resource_task_order', TASK_COLUMN_NAMES)
    return [pair for key in order for pair in groups[key] if any(pair)]


class TaskbarReadout(QWidget):
    def __init__(self,service):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint|Qt.WindowDoesNotAcceptFocus)
        self.service=service;self.placement=Placement(self);self.press=None;self.page=0;self.page_count=1;self.cells=[]
        self.media_actions={};self.media_bounds=[];self.text_bounds=[];self.wanted=288;self.press_media=None
        self.native_layer = None
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('任务栏监控 · 大肥鱼Dock');self.setAccessibleName('任务栏监控')

    def reposition(self):
        slot=self.placement.slot
        if slot is None or self.placement.slot_bar != self.placement.target or self.placement.suppressed():self.hide();return
        if self.geometry()!=slot:self.setGeometry(slot)
        was_visible = self.isVisible()
        self.show()
        from window_layers import click_through
        click_through(self,self.service.cfg['resource_taskbar_click_through'])
        if self.service.runtime.dock.preview:return
        hwnd=self.placement.target['hwnd']
        win = int(self.winId())
        layer = self.service.cfg['resource_taskbar_layer']
        state = (win, hwnd, layer)
        if not was_visible or self.native_layer != state:
            from taskbar_input import place_layer
            from platform_services import fullscreen_window
            if place_layer(win, hwnd, layer, cover=fullscreen_window() if layer=='top' else None):
                self.native_layer = state
        else:
            self.restore_input_layer()

    def restore_input_layer(self, cover=None):
        if (not self.isVisible() or self.placement.slot_bar != self.placement.target
                or not self.placement.target or self.service.runtime.dock.preview):
            return
        from taskbar_input import place_layer, restore_input_layer
        win, hwnd = int(self.winId()), self.placement.target['hwnd']
        if self.service.cfg['resource_taskbar_layer'] == 'bottom':
            place_layer(win, hwnd, 'bottom')
        else:
            from platform_services import fullscreen_window
            restore_input_layer(win, hwnd, cover=fullscreen_window() if cover is None else cover,
                                transparent=self.service.cfg['resource_taskbar_click_through'])

    def placement_changed(self):
        self.reposition();self.service.sync()

    def music_requested(self):
        cfg=self.service.cfg
        # Demand must survive a size transition; layout decides what fits.
        # Otherwise enlarging a tiny strip clears the track before it can grow.
        return cfg['resource_task_music'] and bool(cfg['resource_task_media_parts']) and self.isVisible() and not self.vertical()
    def vertical(self):
        rect=self.placement.target['rect'] if self.placement.target else self.rect()
        return rect.height()>rect.width()
    def preferred_width(self):
        import math
        from taskbar_media import natural_width,scale,spacing
        bridge=self.service.deck;cfg=self.service.cfg
        font,single=self.readout_font();fm=QFontMetrics(font)
        cells=columns(self.service)
        pairs=[(item,None) for pair in cells for item in pair if item] if single else cells
        widths=self.column_widths(pairs,fm)
        metrics=min(420,sum(widths)+spacing(cfg,5)*max(0,len(widths)-1))
        music=natural_width(cfg['resource_task_media_parts'],scale(cfg)) if cfg['resource_task_music'] and bridge and bridge.media.get('track') else 0
        minimum=round((136 if cfg['resource_task_music'] and cfg['resource_task_media_parts'] and cells else 32)*scale(cfg))
        return max(minimum,math.ceil((2*spacing(cfg,4)+metrics+music+(spacing(cfg,6) if metrics and music else 0))/2)*2)
    def readout_font(self):
        font=QFont(self.font());font.setWeight(QFont.DemiBold);font.setPixelSize(self.service.cfg.get('resource_task_font',11))
        while font.pixelSize()>2 and QFontMetrics(font).height()>(self.height()//4 if self.vertical() else self.height()):font.setPixelSize(font.pixelSize()-1)
        return font,not self.vertical() and 2*QFontMetrics(font).height()>self.height()-4
    def column_widths(self,pairs,fm):
        from taskbar_media import spacing
        # A small per-column high-water mark avoids movement on every numeric tick.
        signature=(tuple(self.service.cfg['resource_task_metrics']),fm.fontDpi(),self.service.cfg['resource_task_font'])
        if signature!=getattr(self,'width_signature',None):self.width_signature=signature;self.widths={}
        result=[]
        for pair in pairs:
            key=tuple(item[0] for item in pair if item)
            measured=max(fm.horizontalAdvance(item[0])+fm.horizontalAdvance(item[1])+spacing(self.service.cfg,5) for item in pair if item)
            self.widths[key]=max(measured,self.widths.get(key,0));result.append(self.widths[key])
        return result
    def shows_wave(self):
        from taskbar_media import layout
        return any(key=='wave' for key,_ in layout(self)['items'])

    def refresh(self):
        if not self.isVisible():return
        self.cells=columns(self.service)
        info='\n'.join(f'{label}  {value}'+(' · '+tip if tip else '') for pair in self.cells for item in pair if item for label,value,key,number,tip in (item,))
        self.setAccessibleDescription(info)
        if self.toolTip()!=info:self.setToolTip(info)
        wanted=self.preferred_width()
        if wanted!=self.wanted:self.wanted=wanted;self.placement.schedule_check()
        if self.service.deck:self.service.deck.configure()
        self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.TextAntialiasing|QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor(0,0,0,1))
        vertical=self.vertical()
        font,single=self.readout_font()
        p.setFont(font);fm=QFontMetrics(font)
        self.effective_font=font.pixelSize();self.single_line=single
        ink=QColor('#ffffff' if getattr(self,'system_mode',1)==0 else '#000000')
        self.foreground_ink=ink.name()
        from resource_status import default_limit,threshold
        cfg=self.service.cfg;colored=cfg.get('resource_task_threshold',False)
        from taskbar_media import layout,paint,spacing
        pad=spacing(cfg,4);gap=spacing(cfg,5);media_gap=spacing(cfg,6)
        media=layout(self);media_width=media['width'];self.media_actions={};self.media_bounds=[];self.text_bounds=[];self.media_parts_shown=[]
        if media['active']:paint(self,p,QRectF(pad,3,media_width,self.height()-4),ink,media);p.setFont(font)
        area=QRectF(pad+media_width+(media_gap if media_width else 0),0,max(1,self.width()-media_width-2*pad-(media_gap if media_width else 0)),self.height())
        if not self.cells:
            if not media['active']:p.setPen(ink);p.drawText(self.rect(),Qt.AlignCenter,'—')
            self.page_count=1;return
        pairs=[(item,None) for pair in self.cells for item in pair if item] if single else self.cells
        widths=self.column_widths(pairs,fm)
        pages=[];page=[];total=0;span=area.width()
        for pair,w in zip(pairs,widths):
            if page and (vertical or total+w>span):
                pages.append(page);page=[];total=0
            page.append((pair,min(w,span)));total+=w+gap
        if page:pages.append(page)
        self.page_count=len(pages);self.page%=self.page_count
        page=pages[self.page]
        used=sum(w for _,w in page)+gap*(len(page)-1)
        x=area.left();line=fm.height()
        # Center visible glyphs, rather than the font's leading/descent padding.
        glyphs=[fm.tightBoundingRect(item[0]+' '+item[1]) for pair,_ in page for item in pair if item]
        glyph_top=min(r.top() for r in glyphs);glyph_bottom=max(r.bottom() for r in glyphs)
        rows=[row for pair,_ in page for row,item in enumerate(pair) if item]
        block_height=glyph_bottom-glyph_top+1+(max(rows)-min(rows))*line
        baseline=(self.height()-block_height)/2-glyph_top-min(rows)*line
        if not vertical and block_height + 2 <= self.height():
            baseline += 1
        for pair,w in page:
            for row,item in enumerate(pair):
                if not item:continue
                label,value,key,number,_=item
                color=ink
                if colored:
                    shade=threshold(number,cfg['resource_limits'].get(key,default_limit(key)),getattr(self,'system_mode',1)!=0)
                    if shade:color=QColor(shade)
                if vertical:
                    h=max(1,self.height()//2);y=row*h
                    p.setPen(ink);p.drawText(QRect(0,y,self.width(),h//2),Qt.AlignCenter,label)
                    p.setPen(color);p.drawText(QRect(0,y+h//2,self.width(),h//2),Qt.AlignCenter,fm.elidedText(value,Qt.ElideRight,self.width()))
                else:
                    y=baseline+row*line;lw=min(w,fm.horizontalAdvance(label)+spacing(cfg,3))
                    p.save();p.setClipRect(QRectF(x,0,w,self.height()))
                    p.setPen(ink);p.drawText(QPointF(x,y),label)
                    p.setPen(color);p.drawText(QPointF(x+lw,y),fm.elidedText(value,Qt.ElideRight,max(0,int(w-lw))));p.restore()
                    self.text_bounds.append(QRectF(x,y+glyph_top,w,glyph_bottom-glyph_top+1))
            x+=w+gap

    def sync_style(self):
        from taskbar_text import read_mode
        try:self.system_mode=read_mode()
        except OSError:self.system_mode=1
        self.refresh()

    def nativeEvent(self,event_type,message):
        if event_type in (b'windows_generic_MSG',b'windows_dispatcher_MSG'):
            msg=wintypes.MSG.from_address(int(message))
            if msg.message==0x0021:return True,3  # MA_NOACTIVATE: preserve the first click.
            if msg.message==0x0084:return True,-1 if self.service.cfg['resource_taskbar_click_through'] else 1
            if msg.message in (0x001a,0x031a,0x0320):self.sync_style()
        return super().nativeEvent(event_type,message)

    def wheelEvent(self,event):
        if not event.angleDelta().y():event.ignore();return
        self.page=(self.page+(-1 if event.angleDelta().y()>0 else 1))%max(1,self.page_count);self.update();event.accept()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.press=event.globalPos();self.press_media=None
            bridge=self.service.deck;track=(bridge.media.get('track') or {}) if bridge else {}
            for op,rect in self.media_actions.items():
                if rect.contains(event.pos()):self.press_media=(op,QRectF(rect),track.get('id'));break
            event.accept()
    def mouseMoveEvent(self,event):
        self.setCursor(Qt.PointingHandCursor if any(rect.contains(event.pos()) for rect in self.media_actions.values()) else Qt.ArrowCursor)
        event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.press is None:return
        distance=(event.globalPos()-self.press).manhattanLength();self.press=None;pressed,self.press_media=self.press_media,None
        try:
            if pressed:
                op,rect,identity=pressed
                if rect.contains(event.pos()) and self.service.deck:
                    args=dict(op=op)
                    if identity:args['id']=identity
                    if op=='seek':args['fraction']=max(0,min(1,(event.x()-rect.left())/max(1,rect.width())))
                    self.service.deck.send(**args)
            elif distance<QApplication.startDragDistance():self.page=(self.page+1)%max(1,self.page_count);self.update()
        finally:self.placement.resume()
        event.accept()
    def contextMenuEvent(self,event):
        menu=AlignedMenu(self);menu.addAction('监控设置…',self.service.settings)
        alignment=menu.addMenu('任务栏位置')
        for key,title in [('left','靠左'),('center','居中'),('right','靠右')]:
            action=alignment.addAction(title);action.setCheckable(True);action.setChecked(self.service.cfg['resource_taskbar_position']==key)
            action.triggered.connect(lambda checked,key=key:self.service.set_options(resource_taskbar_position=key))
        layers=menu.addMenu('显示层级')
        for key,title in TASKBAR_LAYERS.items():
            action=layers.addAction(title);action.setCheckable(True);action.setChecked(self.service.cfg['resource_taskbar_layer']==key)
            action.triggered.connect(lambda checked,key=key:self.service.set_options(resource_taskbar_layer=key))
        passing=menu.addAction('鼠标穿透');passing.setCheckable(True);passing.setChecked(self.service.cfg['resource_taskbar_click_through'])
        passing.triggered.connect(lambda on:self.service.set_options(resource_taskbar_click_through=on))
        colors=menu.addAction('文字阈值变色');colors.setCheckable(True);colors.setChecked(self.service.cfg.get('resource_task_threshold',False))
        colors.triggered.connect(lambda on:self.service.set_options(resource_task_threshold=on))
        music=menu.addAction('显示任务栏音乐');music.setCheckable(True);music.setChecked(self.service.cfg['resource_task_music'])
        music.triggered.connect(lambda on:self.service.set_options(resource_task_music=on))
        colorful=menu.addAction('音乐多彩样式');colorful.setCheckable(True);colorful.setChecked(self.service.cfg.get('resource_task_music_colorful',False))
        colorful.triggered.connect(lambda on:self.service.set_options(resource_task_music_colorful=on))
        from resource_options import TASK_MEDIA_PARTS
        parts=menu.addMenu('音乐组件')
        for key,title in TASK_MEDIA_PARTS.items():
            action=parts.addAction(title);action.setCheckable(True);action.setChecked(key in self.service.cfg['resource_task_media_parts'])
            action.triggered.connect(lambda on,key=key:self.set_media_part(key,on))
        menu.addAction('移到桌面',lambda:self.service.return_from_taskbar(None))
        menu.addAction('关闭任务栏监控',lambda:self.service.set_options(resource_taskbar=False))
        try:menu.exec_(event.globalPos())
        finally:menu.deleteLater()
    def set_media_part(self,key,on):
        from resource_options import TASK_MEDIA_PARTS
        selected=set(self.service.cfg['resource_task_media_parts'])
        if on:selected.add(key)
        else:selected.discard(key)
        self.service.set_options(resource_task_media_parts=[part for part in TASK_MEDIA_PARTS if part in selected])
    def dispose(self):
        self.placement.close();self.hide();self.deleteLater()
