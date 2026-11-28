"""A separate desktop card for the current Bing picture and its archive."""
from PyQt5.QtCore import QEvent, QPoint, QRect, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPalette
from PyQt5.QtWidgets import QApplication, QColorDialog, QFileDialog, QInputDialog, QLayout, QSizePolicy, QVBoxLayout, QWidget

from capsule_glass import CapsuleGlass
from resource_content import ContentView
from screen_layout import capture, project, screen_records
from window_edges import edges_at, paint_edge_targets, resize_cursor, resized_rect


MINIMUM_SIZE = (270, 156)


def add_menu_actions(menu,runtime):
    from appearance_presets import APPEARANCE_SOURCES, MATERIALS
    from ui_style import menu_group
    cfg=runtime.dock.cfg
    from component_preferences import open_preferences
    menu.addAction('每日图片设置…',lambda:open_preferences(runtime,'daily_picture'))
    show=menu.addAction('显示桌面每日图片')
    show.setCheckable(True);show.setChecked(cfg['daily_picture_enabled'])
    show.triggered.connect(lambda on:runtime.set_daily_picture_options(daily_picture_enabled=on))
    menu.addSeparator()
    source=menu_group(menu,'图片来源与轮播','picture')
    frame=menu_group(menu,'外框与材质','palette')
    window=menu_group(menu,'尺寸与位置','position')
    from desktop_idle_fade import add_action
    add_action(window,runtime,'picture')
    lock=window.addAction('锁定位置')
    lock.setCheckable(True);lock.setChecked(cfg['daily_picture_locked'])
    lock.triggered.connect(lambda on:runtime.set_daily_picture_options(daily_picture_locked=on))
    size=window.addAction('恢复默认大小',lambda:runtime.set_daily_picture_options(daily_picture_manual_size=False))
    size.setEnabled(cfg['daily_picture_manual_size'] and not cfg['daily_picture_locked'])
    appearance=frame.addMenu('外观来源')
    for name,value in APPEARANCE_SOURCES:
        action=appearance.addAction(name);action.setCheckable(True)
        action.setChecked(cfg['daily_picture_appearance_source']==value)
        action.triggered.connect(lambda _,source=value:runtime.set_daily_picture_options(daily_picture_appearance_source=source))
    materials=frame.addMenu('自定义外框材质')
    for name,value in [('沿用桌面收纳材质','follow'),*MATERIALS]:
        action=materials.addAction(name);action.setCheckable(True)
        action.setChecked(cfg['daily_picture_material']==value)
        action.triggered.connect(lambda _,style=value:runtime.set_daily_picture_options(daily_picture_material=style))
    frame.addAction('选择外框颜色…',lambda:choose_color(runtime))
    frame.addAction('恢复外框默认色',lambda:runtime.set_daily_picture_options(daily_picture_color=''))
    for label,value in (('必应每日图片','bing'),('本地图片轮播','local')):
        action=source.addAction(label);action.setCheckable(True);action.setChecked(cfg['daily_picture_source']==value)
        action.triggered.connect(lambda _,key=value:runtime.set_daily_picture_options(daily_picture_source=key))
    source.addAction('选择图片…',lambda:choose_local(runtime))
    source.addAction('选择文件夹…',lambda:choose_local(runtime,folder=True))
    source.addAction('轮播间隔…',lambda:choose_interval(runtime))


def pick_local_paths(parent,folder=False):
    if folder:
        path=QFileDialog.getExistingDirectory(parent,'选择图片文件夹');paths=[path] if path else []
    else:
        paths,_=QFileDialog.getOpenFileNames(parent,'选择轮播图片','','图片 (*.jpg *.jpeg *.png *.webp *.bmp)')
    return paths[:64]


def choose_local(runtime,folder=False):
    paths=pick_local_paths(runtime.dock,folder)
    if paths:runtime.set_daily_picture_options(daily_picture_source='local',daily_picture_local_paths=paths)


def choose_interval(runtime):
    seconds,ok=QInputDialog.getInt(runtime.dock,'图片轮播','每张图片显示的秒数',runtime.dock.cfg['daily_picture_interval'],5,3600)
    if ok:runtime.set_daily_picture_options(daily_picture_interval=seconds)


def choose_color(runtime):
    cfg=runtime.dock.cfg
    color=QColorDialog.getColor(QColor(cfg['daily_picture_color'] or cfg['panel_color'] or '#b8d9ef'),runtime.dock,'每日图片外框颜色')
    if color.isValid():runtime.set_daily_picture_options(daily_picture_color=color.name())


class DailyPictureCard(QWidget):
    def __init__(self,runtime,parent=None):
        super().__init__(parent,Qt.Widget if parent else Qt.Tool|Qt.FramelessWindowHint)
        self.embedded=parent is not None
        self.setProperty('clickThroughKey','picture')
        self.runtime=runtime;self.service=runtime.resources
        self.drag=None;self.placement=None
        self.flexible_size=False
        self.glass=CapsuleGlass();self.colors={};self.appearance={};self.border={}
        self.setWindowTitle('每日图片 · 大肥鱼Dock')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        body=QVBoxLayout(self);body.setContentsMargins(10,7,10,7)
        if not self.embedded:
            self.setMouseTracking(True)
            body.setSizeConstraint(QLayout.SetNoConstraint)
        self.content=ContentView(self,'picture')
        self.content.installEventFilter(self)
        body.addWidget(self.content)
        self.setStyleSheet("""
            QWidget#DailyPictureContent {background:transparent;}
            QLabel {color:palette(window-text);}
            QToolButton {border:1px solid transparent; padding:0; border-radius:5px; background:transparent;}
            QToolButton:hover,QToolButton:focus {border-color:rgba(118,144,162,100);background:rgba(118,144,162,47);}
            QToolButton:pressed {background:rgba(118,144,162,78);}
        """)

    @property
    def cfg(self):return self.runtime.dock.cfg

    def text_color_at(self,label,rect,role):
        from compact_colors import widget_colors
        return widget_colors(self,label,rect)[role]

    def sync(self):
        placement=(self.cfg['daily_picture_layout'],self.cfg['card_scale'],self.cfg['daily_picture_manual_size'])
        if placement!=self.placement:
            self.placement=placement;self.reposition()
        if self.cfg['daily_picture_locked']:
            self.unsetCursor()
            if self.drag is not None:
                self.drag=None
                self.reposition()
        from flash_view import palette_for
        from appearance_presets import dock_appearance, material_design, panel_appearance
        following = self.cfg['daily_picture_appearance_source'] == 'app'
        if self.embedded:
            from capsule_scale import native_host
            host=native_host(self)
            style=dict(host.background)
        elif following:
            style=dock_appearance(self.cfg)
        else:
            style=panel_appearance(self.cfg)
            if self.cfg['daily_picture_material']!='follow':style['material']=self.cfg['daily_picture_material']
        custom_color = '' if following else self.cfg['daily_picture_color']
        if custom_color:style['color']=custom_color
        self.appearance=style
        design=self.cfg['card_design']
        if following or self.cfg['daily_picture_material']!='follow':
            design=material_design(style['material'],'aurora' if following else design)
        self.border=dict(theme_color=custom_color or self.cfg['theme_color'],panel_color=style['color'],card_design=design)
        colors=palette_for(self.service,style,widget=self,component='daily_picture',refresh=self.sync,design=design)
        if self.embedded:colors['card_alpha']=host.colors['card_alpha']
        if self.colors!=colors:
            self.colors=colors;palette=self.palette()
            for role,key in ((QPalette.WindowText,'ink'),(QPalette.ButtonText,'ink'),(QPalette.Text,'ink'),
                             (QPalette.Button,'hover'),(QPalette.Mid,'muted')):
                palette.setColor(role,QColor(colors[key]))
            self.setPalette(palette)
        self.content.update_icons()
        for label in (self.content.position,self.content.status):
            color=self.text_color_at(label,label.contentsRect(),'muted')
            if label.property('contentInk')!=color:
                label.setProperty('contentInk',color)
                label.setStyleSheet(f'color:{color};')
        for label in (self.content.heading,self.content.title,self.content.credit):label.update()
        if not self.isVisible():self.show()
        self.content.refresh()
        self.update()

    def reposition(self):
        if self.embedded:
            self.resize_photo();return
        screens=screen_records()
        if not screens:return
        density=self.cfg['card_scale']/70
        # The source caption and navigation keep a readable minimum at small scales.
        width=round(max(270,min(440,338*density)))
        photo_height=round((width-20)*9/16)
        record=self.cfg['daily_picture_layout']
        manual=self.cfg['daily_picture_manual_size']
        target=project(record,screens,minimum=MINIMUM_SIZE if manual else (1,1))
        if target and manual:
            self.allow_resize()
            self.setGeometry(*target)
            return
        self.flexible_size=False
        x,y,w,h=screens[0]['area']
        self.content.photo.setFixedHeight(photo_height)
        self.setFixedWidth(width)
        self.fit_height()
        point=QPoint(*target[:2]) if target else QPoint(x+28,y+h-self.height()-78)
        self.move(self.clamped(point))

    def fit_height(self):
        if self.flexible_size:return False
        height=self.layout().sizeHint().height()
        if height==self.maximumHeight():return False
        self.setFixedHeight(height);return True

    def event(self,event):
        handled=super().event(event)
        if event.type()==QEvent.LayoutRequest and getattr(self,'placement',None) is not None and self.fit_height():
            if not self.embedded:self.move(self.clamped(self.pos()))
        return handled

    def eventFilter(self,watched,event):
        if watched is self.content and event.type()==QEvent.Enter and self.drag is None:
            self.unsetCursor()
        return super().eventFilter(watched,event)

    def resize_photo(self):
        height=min(235,round(max(1,self.width()-20)*9/16))
        if self.content.photo.height()!=height:self.content.photo.setFixedHeight(height)
        self.fit_height()

    def allow_resize(self):
        if self.flexible_size:return
        self.flexible_size=True
        self.setMinimumSize(*MINIMUM_SIZE)
        self.setMaximumSize(16777215,16777215)
        photo=self.content.photo
        photo.setMinimumHeight(48)
        photo.setMaximumHeight(16777215)
        photo.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Expanding)
        self.content.layout().setStretchFactor(photo,1)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.embedded and hasattr(self,'content') and event.size().width()!=event.oldSize().width():self.resize_photo()

    def clamped(self,point):
        screen=QApplication.screenAt(point+self.rect().center()) or QApplication.primaryScreen()
        if screen:
            area=screen.availableGeometry()
            return QPoint(max(area.left(),min(point.x(),area.right()+1-self.width())),
                          max(area.top(),min(point.y(),area.bottom()+1-self.height())))
        return point

    def showEvent(self,event):
        from window_layers import place_desktop
        super().showEvent(event)
        if not self.embedded:place_desktop(self,self.runtime.dock.cfg)

    def hideEvent(self,event):
        self.glass.clear()
        if self.drag is not None:
            self.drag=None
            self.reposition()
        super().hideEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and not self.embedded and not self.cfg['daily_picture_locked']:
            edges=edges_at(self.rect(),event.pos())
            self.drag=(self.geometry(),event.globalPos(),edges)
            if edges:self.allow_resize()
            self.setCursor(resize_cursor(edges))
            event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag:
            original,pointer,edges=self.drag
            delta=event.globalPos()-pointer
            if edges:
                self.setGeometry(resized_rect(original,edges,delta,MINIMUM_SIZE))
            else:
                self.move(original.topLeft()+delta)
                self.runtime.resources.preview_component_at('picture',event.globalPos())
            event.accept()
        elif not self.embedded and not self.cfg['daily_picture_locked']:
            edges=edges_at(self.rect(),event.pos())
            self.setCursor(resize_cursor(edges) if edges else Qt.ArrowCursor)

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or not self.drag:
            super().mouseReleaseEvent(event)
            return
        self.mouseMoveEvent(event)
        original,_,edges=self.drag;self.drag=None
        self.unsetCursor()
        self.update()
        event.accept()
        if self.geometry()==original:
            if edges and not self.cfg['daily_picture_manual_size']:self.reposition()
            elif not edges:self.runtime.resources.preview_component_at('picture')
            return
        if not edges:
            from card_snap import finish_drag
            self.move(self.clamped(self.pos()))
            if finish_drag(self,event.globalPos(),component='picture'):return
        if self.runtime.layout.pending or self.runtime.layout.applying:return
        record=capture(list(self.geometry().getRect()),screen_records())
        changes={'daily_picture_layout':record}
        if edges:changes['daily_picture_manual_size']=True
        if not record or not self.runtime.set_daily_picture_options(**changes):
            if edges and not self.cfg['daily_picture_manual_size']:self.reposition()
            self.setGeometry(original)

    def contextMenuEvent(self,event):
        from ui_style import AlignedMenu
        from ui_style import menu_heading
        menu=AlignedMenu(self.runtime.dock);menu_heading(menu,'每日图片');add_menu_actions(menu,self.runtime)
        menu.exec_(event.globalPos());menu.deleteLater()

    def paintEvent(self,event):
        if not self.appearance:return
        from card_design import paint_capsule_card,paint_design
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if self.embedded:
            paint_capsule_card(p,QRectF(self.rect()),self.colors,'ice',self.appearance,radius=12)
            return
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        if not self.cfg['daily_picture_locked']:
            paint_edge_targets(p,self.rect())
        self.glass.paint(p,self,self.service.runtime.dock,12,self.drag is not None,self.appearance)
        paint_design(p,rect,self.border,clear=self.appearance['material']=='clear',corner_radius=12,header_separator=False)
