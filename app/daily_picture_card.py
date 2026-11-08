"""A separate desktop card for the current Bing picture and its archive."""
from PyQt5.QtCore import QEvent, QPoint, QRect, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPalette
from PyQt5.QtWidgets import QColorDialog, QFileDialog, QInputDialog, QVBoxLayout, QWidget

from capsule_glass import CapsuleGlass
from resource_content import ContentView
from screen_layout import capture, project, screen_records


def add_menu_actions(menu,runtime):
    from appearance_presets import MATERIALS
    cfg=runtime.dock.cfg
    show=menu.addAction('显示桌面每日图片')
    show.setCheckable(True);show.setChecked(cfg['daily_picture_enabled'])
    show.triggered.connect(lambda on:runtime.set_daily_picture_options(daily_picture_enabled=on))
    lock=menu.addAction('锁定位置')
    lock.setCheckable(True);lock.setChecked(cfg['daily_picture_locked'])
    lock.triggered.connect(lambda on:runtime.set_daily_picture_options(daily_picture_locked=on))
    materials=menu.addMenu('外框材质')
    for name,value in [('跟随应用','follow'),*MATERIALS]:
        action=materials.addAction(name);action.setCheckable(True)
        action.setChecked(cfg['daily_picture_material']==value)
        action.triggered.connect(lambda _,style=value:runtime.set_daily_picture_options(daily_picture_material=style))
    menu.addAction('选择外框颜色…',lambda:choose_color(runtime))
    menu.addAction('外框跟随应用色',lambda:runtime.set_daily_picture_options(daily_picture_color=''))
    source=menu.addMenu('图片来源与轮播')
    for label,value in (('必应每日图片','bing'),('本地图片轮播','local')):
        action=source.addAction(label);action.setCheckable(True);action.setChecked(cfg['daily_picture_source']==value)
        action.triggered.connect(lambda _,key=value:runtime.set_daily_picture_options(daily_picture_source=key))
    source.addAction('选择图片…',lambda:choose_local(runtime))
    source.addAction('选择文件夹…',lambda:choose_local(runtime,folder=True))
    source.addAction('轮播间隔…',lambda:choose_interval(runtime))


def choose_local(runtime,folder=False):
    if folder:
        path=QFileDialog.getExistingDirectory(runtime.dock,'选择图片文件夹');paths=[path] if path else []
    else:
        paths,_=QFileDialog.getOpenFileNames(runtime.dock,'选择轮播图片','','图片 (*.jpg *.jpeg *.png *.webp *.bmp)')
    if paths:runtime.set_daily_picture_options(daily_picture_source='local',daily_picture_local_paths=paths[:64])


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
        self.glass=CapsuleGlass();self.colors={};self.appearance={};self.border={}
        self.setWindowTitle('每日图片 · 大肥鱼Dock')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        body=QVBoxLayout(self);body.setContentsMargins(10,7,10,7)
        self.content=ContentView(self,'picture')
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

    def sync(self):
        placement=(self.cfg['daily_picture_layout'],self.cfg['card_scale'])
        if placement!=self.placement:
            self.placement=placement;self.reposition()
        if self.cfg['daily_picture_locked']:self.drag=None
        from flash_view import palette_for
        from appearance_presets import material_design
        style={key:self.cfg['panel_'+key] for key in ('material','theme','color','opacity','blur','highlight')}
        if self.cfg['daily_picture_material']!='follow':style['material']=self.cfg['daily_picture_material']
        if self.cfg['daily_picture_color']:style['color']=self.cfg['daily_picture_color']
        self.appearance=style
        design=self.cfg['card_design'] if self.cfg['daily_picture_material']=='follow' else material_design(style['material'],self.cfg['card_design'])
        self.border=dict(theme_color=self.cfg['daily_picture_color'] or self.cfg['theme_color'],panel_color=style['color'],card_design=design)
        colors=palette_for(self.service,style)
        if self.colors!=colors:
            self.colors=colors;palette=self.palette()
            for role,key in ((QPalette.WindowText,'ink'),(QPalette.ButtonText,'ink'),(QPalette.Text,'ink'),
                             (QPalette.Button,'hover'),(QPalette.Mid,'muted')):
                palette.setColor(role,QColor(colors[key]))
            self.setPalette(palette);self.content.update_icons()
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
        target=project(record,screens,minimum=(1,1)) if record else None
        x,y,w,h=screens[0]['area']
        self.content.photo.setFixedHeight(photo_height)
        self.setFixedWidth(width)
        self.fit_height()
        point=QPoint(*target[:2]) if target else QPoint(x+28,y+h-self.height()-78)
        self.move(self.clamped(point))

    def fit_height(self):
        height=self.layout().sizeHint().height()
        if height==self.maximumHeight():return False
        self.setFixedHeight(height);return True

    def event(self,event):
        handled=super().event(event)
        if event.type()==QEvent.LayoutRequest and getattr(self,'placement',None) is not None and self.fit_height():
            if not self.embedded:self.move(self.clamped(self.pos()))
        return handled

    def resize_photo(self):
        height=min(235,round(max(1,self.width()-20)*9/16))
        if self.content.photo.height()!=height:self.content.photo.setFixedHeight(height)
        self.fit_height()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.embedded and hasattr(self,'content') and event.size().width()!=event.oldSize().width():self.resize_photo()

    def clamped(self,point):
        from PyQt5.QtWidgets import QApplication
        screen=QApplication.screenAt(point+self.rect().center()) or QApplication.primaryScreen()
        if screen:
            area=screen.availableGeometry()
            return QPoint(max(area.left(),min(point.x(),area.right()+1-self.width())),
                          max(area.top(),min(point.y(),area.bottom()+1-self.height())))
        return point

    def showEvent(self,event):
        from window_layers import BOTTOM,restack
        super().showEvent(event)
        if not self.embedded:restack(int(self.winId()),BOTTOM)

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and not self.embedded and not self.cfg['daily_picture_locked']:
            self.drag=(self.pos(),event.globalPos())
            event.accept()

    def mouseMoveEvent(self,event):
        if self.drag:
            start,pointer=self.drag
            self.move(start+event.globalPos()-pointer)

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or not self.drag:return
        start,_=self.drag;self.drag=None
        if self.pos()==start:return
        from card_snap import finish_drag
        self.move(self.clamped(self.pos()));finish_drag(self,event.globalPos())
        if self.runtime.layout.pending or self.runtime.layout.applying:return
        record=capture(list(self.geometry().getRect()),screen_records())
        if record and not self.runtime.set_daily_picture_options(daily_picture_layout=record):self.move(start)

    def contextMenuEvent(self,event):
        from ui_style import AlignedMenu
        menu=AlignedMenu(self.runtime.dock);add_menu_actions(menu,self.runtime)
        menu.exec_(event.globalPos());menu.deleteLater()

    def paintEvent(self,event):
        if not self.appearance:return
        from card_design import paint_design
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        self.glass.paint(p,self,self,12,self.drag is not None,self.appearance)
        paint_design(p,rect,self.border,clear=self.appearance['material']=='clear',corner_radius=12,header_separator=False)
