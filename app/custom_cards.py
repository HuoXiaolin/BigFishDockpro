"""Desktop instances for the native card editor."""
import datetime
import json
from pathlib import Path

from PyQt5.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QImage, QImageReader, QPainter, QPainterPath
from PyQt5.QtWidgets import QApplication, QWidget

from custom_card_data import SAMPLERS
from resource_compact import text
from screen_layout import capture, project, screen_records


class CustomCards:
    def __init__(self,runtime):
        self.runtime=runtime
        self.windows={}
        self.feeds=None
        self.clock=QTimer(runtime.dock);self.clock.setSingleShot(True)
        self.clock.timeout.connect(self.update_time)

    @property
    def cards(self):
        return self.runtime.dock.cfg['custom_cards']

    def sync(self):
        from resource_options import component_location
        routed=component_location(self.runtime.dock.cfg,'custom')=='capsule'
        visible={}
        if not self.runtime.game_active:
            for i,row in enumerate(self.cards):
                if not row['visible']:continue
                host=self.runtime.resources.hosted_component('custom',row['id']) if routed else None
                if not routed or host is not None:visible[row['id']]=(i,row,host)
        for identity,window in list(self.windows.items()):
            if identity not in visible or window.parentWidget() is not visible[identity][2]:
                self.windows.pop(identity);window.hide();window.deleteLater()
        for identity,(i,row,host) in visible.items():
            window=self.windows.get(identity)
            if window is None:
                window=self.windows[identity]=CustomCard(self,row,i,host)
                if host:host.layout().addWidget(window)
            window.sync(row)
        self.update_time()

    def needs(self):
        return {SAMPLERS[row['kind']] for window in self.windows.values() for row in window.card['rows'] if row['kind'] in SAMPLERS}

    def update_time(self):
        self.clock.stop()
        keys=set()
        active=False
        for window in self.windows.values():
            if window.card['data_file']:window.read_data()
            if window.feed_key:keys.add(window.feed_key)
            if window.feed_key or window.card['header_date'] or window.card['data_file'] or any(row['kind'] in ('time','date','countdown') for row in window.card['rows']):
                window.update();active=True
        if self.feeds:self.feeds.sync(keys)
        if active:
            now=datetime.datetime.now()
            self.clock.start(max(50,60000-now.second*1000-now.microsecond//1000))

    def ensure_feeds(self):
        if self.feeds is None:
            from custom_card_tools import CardFeeds
            self.feeds=CardFeeds(self.runtime)

    def redraw(self,metrics_only=False):
        for window in self.windows.values():
            if not metrics_only or any(row['kind'] in SAMPLERS for row in window.card['rows']):
                window.update()

    def reposition(self):
        for window in self.windows.values():window.reposition()

    def save(self,cards):
        from settings_effects import save_changes
        return save_changes(self.runtime.tray,self.runtime.api,{'custom_cards':cards})

    def change(self,identity,**changes):
        return self.save([dict(card,**changes) if card['id']==identity else card for card in self.cards])

    def edit(self,identity=None):
        from custom_card_editor import CardEditor
        from ui_style import exec_dialog
        exec_dialog(CardEditor(self,identity))

    def close(self):
        self.clock.stop()
        if self.feeds:self.feeds.sync(set())
        for window in self.windows.values():window.hide();window.deleteLater()
        self.windows.clear()


class CustomCard(QWidget):
    def __init__(self,manager,card,index,parent=None):
        super().__init__(parent,Qt.Widget if parent else Qt.Tool|Qt.FramelessWindowHint)
        self.embedded=parent is not None
        self.manager=manager;self.runtime=manager.runtime;self.card=card;self.index=index
        self.drag=None;self.placement=None
        self.image=QImage();self.image_path='';self.data={};self.data_key=None
        self.remote=None
        self.tool_widget=None;self.tool_config=None;self.feed_key=None;self.tool_size=0
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def sync(self,card):
        self.card=card
        self.setProperty('clickThroughKey','custom:'+card['id'])
        self.setWindowTitle(card['title']+' · 大肥鱼Dock')
        self.sync_tool()
        self.read_data(reposition=False)
        picture=card['image'].get('path','')
        if self.image_path!=picture:
            self.image_path=picture;self.image=self.read_image(picture)
        placement=(card['width'],card['rows'],card['arrangement'],card['image'],card['fonts'],card['tool'],
                   card['layout'],self.data_key,self.runtime.dock.cfg['card_scale'])
        if placement!=self.placement:
            self.placement=placement
            self.reposition()
        if not self.isVisible():self.show()
        self.update()

    def local_file(self,name):
        return Path(self.runtime.api.CONFIG_DIR)/Path(name)

    def read_image(self,name):
        if not name:return QImage()
        path=self.local_file(name)
        if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.bmp'):return QImage()
        reader=QImageReader(str(path));reader.setAutoTransform(True);size=reader.size()
        if not size.isValid() or size.width()*size.height()>20_000_000:return QImage()
        reader.setScaledSize(size.scaled(QSize(min(640,size.width()),min(420,size.height())),Qt.KeepAspectRatio))
        return reader.read()

    def read_data(self,reposition=True):
        source=self.card['data_file']
        path=self.local_file(source) if source else None
        try:stamp=path.stat().st_mtime_ns if path else None
        except OSError:stamp=None
        key=(source,stamp)
        if key==self.data_key:return
        values={}
        if stamp is not None:
            try:
                with path.open('rb') as stream:raw=stream.read(32*1024+1)
                if len(raw)>32*1024:raise ValueError('data too large')
                loaded=json.loads(raw)
                if isinstance(loaded,dict):values=loaded
            except (OSError,ValueError,RecursionError):pass
        self.data_key=key;self.data=values
        if reposition:self.reposition();self.update()

    def sync_tool(self):
        tool=self.card['tool']
        if tool==self.tool_config:return
        if self.tool_widget:self.tool_widget.hide();self.tool_widget.deleteLater();self.tool_widget=None
        self.tool_config=tool;self.feed_key=None;self.tool_size=0
        if not tool:return
        from custom_card_tools import TOOLS,feed_key,tool_height
        self.feed_key=feed_key(tool)
        if self.feed_key:self.manager.ensure_feeds()
        if tool['kind']=='feed':
            if not getattr(self,'feed_bound',False):
                self.manager.feeds.changed.connect(self.feed_updated);self.feed_bound=True
            self.remote=(self.manager.feeds.read(self.feed_key) or {}).get('data');return
        self.tool_widget=TOOLS[tool['kind']](tool,self);self.tool_size=tool_height(tool);self.tool_widget.show()

    def feed_updated(self):
        if not self.feed_key or self.feed_key[0]!='feed':return
        self.remote=(self.manager.feeds.read(self.feed_key) or {}).get('data')
        self.reposition();self.update()

    def reposition(self):
        factor=self.runtime.dock.cfg['card_scale']/70
        if self.embedded:
            height=self.arrange(max(1,self.width()),factor)
            if height!=self.maximumHeight():self.setFixedHeight(height)
            return
        screens=screen_records()
        if not screens:return
        width=round(self.card['width']*factor)
        x,y,_,_=screens[0]['area']
        point=QPoint(x+24+22*self.index,y+46+26*self.index)
        if self.card['layout']:
            bounds=project(self.card['layout'],screens,minimum=(1,1))
            if bounds:point=QPoint(*bounds[:2])
        screen=QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen:width=min(width,screen.availableGeometry().width())
        height=self.arrange(width,factor)
        self.setGeometry(self.clamped(QRect(point.x(),point.y(),width,height)))

    def arrange(self,width,factor):
        card=self.card;picture=card['image'];mode=card['arrangement'];fonts=card['fonts']
        margin=10*factor;gap=7*factor;span=max(1,width-2*margin)
        self.title_height=round((fonts['title']+12)*factor)
        top=self.title_height+gap
        left=margin;row_width=span
        self.photo_rect=QRectF();side=bool(picture and card['rows'] and mode in ('image_left','image_right'))
        if picture:
            photo_width=span*.39 if side else span
            photo_left=width-margin-photo_width if side and mode=='image_right' else margin
            self.photo_rect=QRectF(photo_left,top,photo_width,picture['height']*factor)
            if side:
                row_width-=photo_width+gap
                if mode=='image_left':left+=photo_width+gap
            else:top=self.photo_rect.bottom()+gap
        grid=mode=='grid';columns=2 if grid else 1
        cell=(row_width-gap*(columns-1))/columns
        label_height=(fonts['label']+3)*factor;value_height=(fonts['body']+5)*factor
        font=QFont(self.font());font.setPixelSize(max(1,round(fonts['body']*factor)))
        metrics=QFontMetrics(font)
        self.row_boxes=[]
        for index in range(0,len(card['rows']),columns):
            rows=card['rows'][index:index+columns]
            heights=[]
            for row in rows:
                if row['kind'] in ('text','data','remote'):
                    value=card_value(row,{},datetime.datetime.now(),self.data,self.remote)
                    measured=metrics.boundingRect(QRect(0,0,max(1,int(cell)),1000),Qt.TextWrapAnywhere,value).height()
                    height=min(6*value_height,max(value_height,measured+2))
                else:height=value_height
                if row['label'] and (grid or row['kind'] in ('text','data','remote')):height+=label_height
                heights.append(height)
            for column,row in enumerate(rows):
                rect=QRectF(left+column*(cell+gap),top,cell,heights[column])
                self.row_boxes.append((row,rect,grid or row['kind'] in ('text','data','remote')))
            top+=max(heights)+gap
        if side:top=max(top,self.photo_rect.bottom()+gap)
        if self.tool_widget:
            self.tool_widget.setGeometry(round(margin),round(top),round(span),round(self.tool_size*factor))
            top+=self.tool_size*factor+gap
        return round(top+margin)

    @staticmethod
    def clamped(rect):
        screen=QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
        if screen:
            area=screen.availableGeometry()
            rect.setWidth(min(rect.width(),area.width()))
            rect.setHeight(min(rect.height(),area.height()))
            rect.moveLeft(max(area.left(),min(rect.left(),area.right()+1-rect.width())))
            rect.moveTop(max(area.top(),min(rect.top(),area.bottom()+1-rect.height())))
        return rect

    def showEvent(self,event):
        from window_layers import BOTTOM,restack
        super().showEvent(event)
        if not self.embedded:restack(int(self.winId()),BOTTOM)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.embedded and self.placement is not None and event.size().width()!=event.oldSize().width():
            self.reposition()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and not self.embedded and not self.card['locked']:
            self.drag=(self.pos(),event.globalPos())
            event.accept()

    def mouseMoveEvent(self,event):
        if self.drag:
            start,pointer=self.drag
            self.move(start+event.globalPos()-pointer)

    def mouseReleaseEvent(self,event):
        if not self.drag or event.button()!=Qt.LeftButton:return
        start,_=self.drag
        self.drag=None
        if self.pos()==start:return
        from card_snap import finish_drag
        self.setGeometry(self.clamped(self.geometry()))
        finish_drag(self,event.globalPos())
        layout=getattr(self.runtime,'layout',None)
        if layout and (layout.pending or layout.applying):return
        record=capture(list(self.geometry().getRect()),screen_records())
        if record and not self.manager.change(self.card['id'],layout=record):self.move(start)

    def contextMenuEvent(self,event):
        from ui_style import AlignedMenu
        identity=self.card['id'];menu=AlignedMenu(self.runtime.dock)
        menu.addAction('编辑卡片…').triggered.connect(lambda:self.manager.edit(identity))
        if self.card['data_file']:menu.addAction('刷新本地数据',self.read_data)
        lock=menu.addAction('锁定位置');lock.setCheckable(True);lock.setChecked(self.card['locked'])
        lock.triggered.connect(lambda on:self.manager.change(identity,locked=on))
        menu.addAction('隐藏卡片').triggered.connect(lambda:self.manager.change(identity,visible=False))
        menu.exec_(event.globalPos());menu.deleteLater()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing)
        dock=self.runtime.dock;cfg=dock.cfg;rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        card=self.card;style=card['style'];colors=dock.base_theme_colors(cfg['panel_theme'])
        custom=card['colors'];factor=cfg['card_scale']/70
        clear=style=='clear' or style=='follow' and cfg['panel_material']=='clear'
        if not clear:
            path=QPainterPath();path.addRoundedRect(rect,12,12)
            surface=QColor(custom.get('surface') or ('#f5fafc' if colors['light'] else '#1e2b34'))
            if style=='follow':surface.setAlpha(min(250,155+cfg['panel_opacity']))
            p.fillPath(path,surface)
            if style=='follow':
                from card_design import paint_design
                design=dict(theme_color=custom.get('accent') or cfg['theme_color'],panel_color=cfg['panel_color'],card_design=cfg['card_design'])
                paint_design(p,rect,design,corner_radius=12,header_separator=False)
        ink=QColor(custom.get('text') or colors['fg'])
        if 'text' not in custom and 'surface' in custom:
            ink=QColor('#f2f7fa' if QColor(custom['surface']).lightness()<128 else '#172b36')
        muted=QColor(ink);muted.setAlpha(180)
        fonts={key:max(1,round(size*factor)) for key,size in card['fonts'].items()}
        latest=self.runtime.resources.latest;now=datetime.datetime.now()
        date_width=85*factor if card['header_date'] else 0
        title=QRectF(10*factor,3*factor,rect.width()-20*factor,self.title_height)
        text(p,title.adjusted(0,0,-date_width,0),card['title'],ink,fonts['title'],True)
        if date_width:text(p,title.adjusted(title.width()-date_width,0,0,0),now.date().isoformat(),muted,fonts['label'],False,Qt.AlignRight)
        if not self.photo_rect.isEmpty():self.paint_image(p,muted)
        for row,box,stacked in self.row_boxes:
            value=card_value(row,latest,now,self.data,self.remote)
            if stacked:
                height=(fonts['label']+3) if row['label'] else 0
                if height:text(p,QRectF(box.x(),box.y(),box.width(),height),row['label'],muted,fonts['label'])
                self.paint_value(p,box.adjusted(0,height,0,0),value,ink,fonts['body'])
            else:
                span=box.width()*.44
                text(p,QRectF(box.x(),box.y(),span,box.height()),row['label'],muted,fonts['label'])
                text(p,box.adjusted(span,0,0,0),value,ink,fonts['body'],True,Qt.AlignRight)

    def paint_value(self,p,box,value,ink,size):
        font=QFont(self.font());font.setPixelSize(size);p.setFont(font);p.setPen(ink)
        p.save();p.setClipRect(box);p.drawText(box,Qt.AlignTop|Qt.TextWrapAnywhere,value);p.restore()

    def paint_image(self,p,ink):
        rect=self.photo_rect
        if self.image.isNull():
            text(p,rect,'配图不可用',ink,10,False,Qt.AlignCenter);return
        image=self.image;cover=self.card['image']['fit']=='cover'
        scale=(max if cover else min)(rect.width()/image.width(),rect.height()/image.height())
        width,height=image.width()*scale,image.height()*scale
        path=QPainterPath();path.addRoundedRect(rect,8,8)
        p.save();p.setRenderHint(QPainter.SmoothPixmapTransform);p.setClipPath(path)
        p.drawImage(QRectF(rect.center().x()-width/2,rect.center().y()-height/2,width,height),image)
        p.restore()


def card_value(row,latest,now,data=None,remote=None):
    kind=row['kind']
    if kind=='text':return row['value']
    if kind in ('data','remote'):
        value=(data or {}).get(row['value']) if kind=='data' else remote_value(remote,row['value'])
        return str(value)[:260] if type(value) in (str,int,float,bool) else '—'
    if kind=='time':return now.strftime('%H:%M')
    if kind=='date':return now.strftime('%Y-%m-%d')
    if kind=='countdown':
        remaining=(datetime.date.fromisoformat(row['value'])-now.date()).days
        return '今天' if remaining==0 else f'{remaining} 天' if remaining>0 else f'已过 {-remaining} 天'
    value=latest.get(SAMPLERS[kind])
    if value is None:return '—'
    if kind in ('download','upload'):
        from resource_traffic import amount
        return amount(value[0 if kind=='download' else 1])+'/s'
    return f'{(value[0] if kind=="memory" else value):.0f}%'


def remote_value(value,path):
    for part in path.split('.'):
        if isinstance(value,dict):value=value.get(part)
        elif isinstance(value,list) and part.isdecimal() and int(part)<len(value):value=value[int(part)]
        else:return None
    return value
