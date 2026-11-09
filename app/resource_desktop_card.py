"""Desktop hosts for resource pages, with their own placement and no fold state."""
from PyQt5.QtCore import QRectF, QSize, Qt, QTimer
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QApplication, QLabel, QToolButton

from flash_view import icon
from resource_options import RESOURCE_PAGES
from resource_panel import ResourceContentHost, display_values
from screen_layout import capture, project, screen_records
from ui_style import SubtleSizeGrip


INITIAL_SIZES={'resources':(560,305),'ai':(450,360),'music':(430,164),
               'traffic':(430,150),'weather':(520,303),
               'pomodoro':(470,173),'agenda':(550,315),'news':(360,248)}


class ResourceDesktopCard(ResourceContentHost):
    def __init__(self,service,key):
        super().__init__(service,hardware=key=='resources')
        self.runtime=service.runtime
        self.page_key=key
        self.drag=None
        self.restoring=True
        self.setProperty('clickThroughKey','resource:'+key)
        self.setMinimumSize(260,136)
        title=RESOURCE_PAGES[key]
        self.setWindowTitle(title+' · 大肥鱼Dock')
        self.header=QLabel(title,self)
        self.header.setObjectName('RankTitle')
        self.header.setToolTip('拖动标题栏移动，拖回资源胶囊可合入')
        self.settings_button=QToolButton(self)
        self.settings_button.setToolTip('组件设置')
        self.settings_button.setAccessibleName('组件设置')
        self.settings_button.clicked.connect(lambda:self.service.settings(8))
        self.grip=SubtleSizeGrip(self,lambda:self.colors.get('light',True))
        self.grip.setFixedSize(14,14)
        self.save_timer=QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(350)
        self.save_timer.timeout.connect(self.save_geometry)
        self.content=None
        if key!='resources':
            from resource_pages import AiView,InfoPage,MusicView
            self.content=AiView(self) if key=='ai' else MusicView(self) if key=='music' else InfoPage(self,key)
            if key=='ai':self.ai_view=self.content
            self.detail.layout().addWidget(self.content)
        self.reposition()
        self.restoring=False

    def sync_window(self):
        if self.sync_palette():
            self.header.setStyleSheet('color:%s;font-size:11px;font-weight:600;'%self.colors['ink'])
            self.settings_button.setIcon(icon('settings',self.colors['ink'],14))
            self.settings_button.setIconSize(QSize(14,14))
        if not self.isVisible():self.show()
        self.refresh()

    def refresh(self):
        if self.page_key=='resources':
            self.values=display_values(self.service,compact=False)
            self.refresh_dashboard()
        else:self.content.refresh()

    def reposition(self):
        screens=screen_records()
        if not screens:return
        stored=self.service.cfg['resource_card_layouts'].get(self.page_key)
        if not stored:
            x,y,w,h=screens[0]['area']
            width,height=INITIAL_SIZES[self.page_key]
            index=list(RESOURCE_PAGES).index(self.page_key)
            stored=capture([x+38+index*28,y+68+index*28,min(w,width),min(h,height)],screens)
        bounds=project(stored,screens,minimum=(260,136))
        if bounds:
            self.restoring=True
            self.setGeometry(*bounds)
            self.restoring=False

    def save_geometry(self):
        if self.restoring or not self.isVisible():return
        record=capture(list(self.geometry().getRect()),screen_records())
        if record:
            layouts=dict(self.service.cfg['resource_card_layouts'])
            if layouts.get(self.page_key)!=record:
                layouts[self.page_key]=record
                self.service.set_options(resource_card_layouts=layouts)

    def paintEvent(self,event):
        if not self.colors:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        self.glass.paint(painter,self,self,14,self.drag is not None,self.background)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not hasattr(self,'header'):return
        self.header.setGeometry(13,4,max(1,self.width()-52),22)
        self.settings_button.setGeometry(self.width()-36,4,25,22)
        self.detail.setGeometry(0,30,self.width(),max(1,self.height()-30))
        self.grip.move(self.width()-16,self.height()-16)
        self.grip.raise_()
        if self.dashboard is not None:self.layout_dashboard()
        if not self.restoring and self.isVisible():self.save_timer.start()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and event.y()<30:
            self.drag=self.pos(),event.globalPos()
            event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag is not None:
            origin,start=self.drag
            delta=event.globalPos()-start
            if delta.manhattanLength()>=QApplication.startDragDistance() or self.pos()!=origin:
                self.move(origin+delta)
                self.service.preview_component_at(self.page_key,event.globalPos())
            event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.drag is None:return
        origin,_=self.drag
        self.mouseMoveEvent(event)
        self.drag=None
        if self.pos()==origin:
            if self.service.window:self.service.window.clear_tab_drop()
            return
        from card_snap import finish_drag
        if finish_drag(self,event.globalPos(),component=self.page_key):return
        area=(QApplication.screenAt(event.globalPos()) or QApplication.primaryScreen()).availableGeometry()
        self.move(max(area.left(),min(self.x(),area.right()+1-self.width())),
                  max(area.top(),min(self.y(),area.bottom()+1-self.height())))
        self.update();self.save_geometry()

    def showEvent(self,event):
        super().showEvent(event)
        from window_layers import desktop_layer,shell_owner
        desktop_layer(int(self.winId()),False,shell_owner())

    def closeEvent(self,event):
        event.ignore()

    def dispose(self):
        self.save_timer.stop();self.glass.clear();self.hide();self.deleteLater()
