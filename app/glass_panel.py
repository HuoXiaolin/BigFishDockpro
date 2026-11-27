from ui_style import compact_dialog
"""Floating desktop collection windows using the original Dock liquid glass."""
import os
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QEvent, QPoint, QTimer, QSize, QRect, QRectF, QMimeData, QUrl, QItemSelectionModel
from PyQt5.QtGui import QPainter, QPainterPath, QIcon, QDrag, QCursor, QColor, QPalette, QPixmap, QPen, QKeySequence, QFont
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QApplication,
    QMenu, QInputDialog, QFileDialog, QFormLayout, QSpinBox, QComboBox, QCheckBox, QLayout, QColorDialog, QSizePolicy, QTabBar, QStyle, QStyleOptionTab)
from ui_style import AlignedMenu as QMenu
from app_catalog import path_key
from liquid_glass import paint_liquid_glass, tint_palette
from appearance_presets import BACKDROP_MODES, PANEL_PRESETS
from ui_style import label, button, ModernComboBox, ModernSpinBox, ModernCheckBox
from dpi_support import metric, minimum, panel_css
from window_edges import edges_at, paint_edge_targets, resize_cursor, resized_rect
from window_backdrop import BACKDROP_HINT, component_backdrop, uses_wallpaper
from panel_preferences import ICON_ALIGNMENTS
from fold_transition import Foldable


CATEGORY_COLORS={
    'apps':('#2f75d9','#80b5ff'),'folders':('#b97713','#f3c56c'),
    'documents':('#148577','#72d8c5'),'images':('#8958ca','#c7a3ff'),
    'media':('#c45479','#ffa0be'),'archives':('#ae6a27','#edb77c'),
    'other':('#55738d','#adc5da')}


def category_color(category,light=True):
    return CATEGORY_COLORS.get(category,CATEGORY_COLORS['other'])[0 if light else 1]


def category_icon(category,ink,size,dpr):
    return _category_icon(category,ink,size,round(dpr,2))


from functools import lru_cache
@lru_cache(maxsize=96)
def _category_icon(category,ink,size,dpr):
    pixmap=QPixmap(max(1,round(size*dpr)),max(1,round(size*dpr)));pixmap.fill(Qt.transparent);pixmap.setDevicePixelRatio(dpr)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing);painter.scale(size/24,size/24)
    pen=QPen(QColor(ink));pen.setWidthF(1.7);pen.setCapStyle(Qt.RoundCap);pen.setJoinStyle(Qt.RoundJoin);painter.setPen(pen);painter.setBrush(Qt.NoBrush)
    if category=='apps':
        for x in (4,14):
            for y in (4,14):painter.drawRoundedRect(QRectF(x,y,6,6),1.5,1.5)
    elif category=='documents':
        path=QPainterPath();path.moveTo(6,3);path.lineTo(14,3);path.lineTo(19,8);path.lineTo(19,21);path.lineTo(6,21);path.closeSubpath();painter.drawPath(path)
        painter.drawLine(14,3,14,8);painter.drawLine(14,8,19,8);painter.drawLine(9,12,16,12);painter.drawLine(9,16,14,16)
    elif category=='images':
        painter.drawRoundedRect(QRectF(3,4,18,16),2,2);painter.drawEllipse(QRectF(6,7,3,3))
        path=QPainterPath();path.moveTo(4,18);path.lineTo(10,12);path.lineTo(13,15);path.lineTo(17,10);path.lineTo(21,15);painter.drawPath(path)
    elif category=='media':
        painter.drawRoundedRect(QRectF(3,4,18,16),3,3)
        path=QPainterPath();path.moveTo(10,8);path.lineTo(16,12);path.lineTo(10,16);path.closeSubpath();painter.drawPath(path)
    elif category=='settings':
        painter.drawLine(4,6,8,6);painter.drawLine(14,6,20,6);painter.drawEllipse(QRectF(8,3,6,6))
        painter.drawLine(4,17,12,17);painter.drawLine(18,17,20,17);painter.drawEllipse(QRectF(12,14,6,6))
    elif category=='note':
        path=QPainterPath();path.moveTo(4,3);path.lineTo(20,3);path.lineTo(20,15);path.lineTo(14,21);path.lineTo(4,21);path.closeSubpath();painter.drawPath(path)
        painter.drawLine(14,21,14,15);painter.drawLine(14,15,20,15);painter.drawLine(8,8,16,8);painter.drawLine(8,12,13,12)
    elif category=='archives':
        painter.drawRoundedRect(QRectF(5,3,14,18),2,2)
        for y in (6,10,14):painter.drawLine(10,y,14,y)
        painter.drawRoundedRect(QRectF(10,16,4,3),.5,.5)
    else:
        path=QPainterPath();path.moveTo(3,7);path.lineTo(3,5);path.lineTo(10,5);path.lineTo(12,8);path.lineTo(21,8);path.lineTo(21,20);path.lineTo(3,20);path.closeSubpath();painter.drawPath(path)
    painter.end();return pixmap


class CollectionList(QListWidget):
    def wheelEvent(self,event):
        bar=self.verticalScrollBar()
        pixels=event.pixelDelta().y()
        angle=event.angleDelta().y()
        if self.viewMode()!=QListWidget.IconMode or not bar.maximum() or event.modifiers() or not (pixels or angle):
            super().wheelEvent(event)
            return
        if pixels:
            delta=pixels
            self._wheel_remainder=0.
        else:
            # Three system lines advance one icon row; a precision wheel can
            # move a fraction of a row without waiting for an entire detent.
            step=min(self.viewport().height(),self.gridSize().height()*QApplication.wheelScrollLines()/3)
            remainder=getattr(self,'_wheel_remainder',0.)
            distance=angle*step/120+(remainder if remainder*angle>0 else 0.)
            delta=int(distance)
            self._wheel_remainder=distance-delta
        bar.setValue(bar.value()-delta)
        event.accept()

    def align_icons(self,alignment):
        if self.viewMode()!=QListWidget.IconMode or not self.count():
            return
        grid=self.gridSize()
        width=self.viewport().width()
        if not grid.isValid() or grid.isEmpty() or width<=0:
            return
        columns=max(1,(width-1)//grid.width())
        for first in range(0,self.count(),columns):
            count=min(columns,self.count()-first)
            remaining=max(0,width-count*grid.width())
            left=remaining if alignment=='right' else remaining//2 if alignment=='center' else 0
            top=(first//columns)*grid.height()
            for column in range(count):
                index=self.model().index(first+column,0)
                rect=self.rectForIndex(index)
                x=left+column*grid.width()+(grid.width()-rect.width())//2
                position=QPoint(x,top)
                if rect.topLeft()!=position:
                    self.setPositionForIndex(position,index)

    def keyPressEvent(self,event):
        panel=self.window()
        if event.matches(QKeySequence.Copy):panel.copy_files(False);event.accept();return
        if event.matches(QKeySequence.Cut):panel.copy_files(True);event.accept();return
        if event.matches(QKeySequence.Paste):panel.paste_files();event.accept();return
        key=event.key();modifiers=event.modifiers()
        if modifiers==Qt.ControlModifier and key==Qt.Key_A:self.selectAll();event.accept();return
        if modifiers==Qt.AltModifier and key in (Qt.Key_Return,Qt.Key_Enter):panel.shell_file_action('properties');event.accept();return
        if modifiers==Qt.NoModifier:
            if key==Qt.Key_F2:panel.rename_file();event.accept();return
            if key==Qt.Key_Delete:panel.shell_file_action('delete');event.accept();return
            if key in (Qt.Key_Return,Qt.Key_Enter):
                for item in list(self.selectedItems()):panel.launch_item(item)
                event.accept();return
            if key==Qt.Key_F5:
                panel.dock.icons.clear();panel.manager.schedule_scan();panel.render(force=True);event.accept();return
        super().keyPressEvent(event)

    def startDrag(self, actions):
        urls = [QUrl.fromLocalFile(item.data(Qt.UserRole)['path']) for item in self.selectedItems()]
        if not urls: return
        mime = QMimeData()
        mime.setUrls(urls)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


class PanelTabs(QTabBar):
    """Keep this page alive while dragging a different tab to a new position."""
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.pressing = False
        self.pressed_identity = None
        self.press_point = None
        self.order_dirty = False
        self.setMovable(True)
        self.setDrawBase(False)
        self.setToolTip('拖动栏目排序，拖出卡片后独立显示，拖到另一张卡片可合入')
        self.tabMoved.connect(self.save_order)

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.property('movingTab'):return
        painter=QPainter(self)
        for index in range(self.count()):
            opt=QStyleOptionTab()
            self.initStyleOption(opt,index)
            if not event.rect().intersects(opt.rect):continue
            rect=self.style().subElementRect(QStyle.SE_TabBarTabText,opt,self)
            font=QFont(self.font());font.setWeight(QFont.DemiBold);painter.setFont(font)
            ink=self.panel.text_ink_at(self,rect,index!=self.currentIndex(),on_selection=index==self.currentIndex())
            painter.setPen(QColor(ink));painter.drawText(rect,Qt.AlignCenter,opt.text)

    def native_drag_labels(self,enabled):
        if bool(self.property('movingTab'))==enabled:return
        self.setProperty('movingTab',enabled)
        self.style().unpolish(self);self.style().polish(self);self.update()

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.pressing = True
            self.update()
            self.pressed_identity = self.tabData(self.tabAt(event.pos()))
            self.press_point = event.globalPos()
            self.order_dirty = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.press_point is not None and (event.globalPos()-self.press_point).manhattanLength()>=QApplication.startDragDistance():
            self.native_drag_labels(True)
        if self.pressed_identity and not self.panel.option('locked'):
            point=event.globalPos()
            if not self.panel.geometry().contains(point):
                self.panel.manager.preview_card_drop(self.panel,point)
            else:self.panel.manager.preview_card_drop()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        identity = self.pressed_identity
        moved = self.press_point is not None and (event.globalPos()-self.press_point).manhattanLength()>=QApplication.startDragDistance()
        super().mouseReleaseEvent(event)
        self.native_drag_labels(False)
        if event.button()==Qt.LeftButton:
            self.pressing = False
            self.update()
            self.pressed_identity = None
            self.press_point = None
            manager=self.panel.manager
            manager.preview_card_drop()
            if identity and moved:
                if not self.panel.geometry().contains(event.globalPos()):
                    if not self.panel.option('locked') and manager.drop_tab_at(identity,self.panel,event.globalPos()):
                        return
                    self.panel.update_tabs(manager.merged_models(self.panel.identity))
                    return
                # A quick drag can reach its destination on the first move,
                # before Qt has updated its transient tab order.
                destination=self.tabAt(event.pos())
                if not self.order_dirty and destination>=0:
                    origin=next(i for i in range(self.count()) if self.tabData(i)==identity)
                    if origin!=destination:self.moveTab(origin,destination)
            if self.order_dirty:self.save_order()
            index = next((i for i in range(self.count()) if self.tabData(i)==identity),self.currentIndex())
            self.panel.select_tab(index)

    def hideEvent(self, event):
        self.native_drag_labels(False)
        if self.pressing:self.panel.manager.preview_card_drop()
        self.pressing = False
        self.pressed_identity = None
        self.press_point = None
        self.order_dirty = False
        super().hideEvent(event)

    def save_order(self, *_):
        if self.pressing:
            self.order_dirty = True
            return
        order = [self.tabData(index) for index in range(self.count())]
        if not self.panel.manager.reorder_panels(order):
            self.panel.update_tabs(self.panel.manager.merged_models(self.panel.identity))


class DesktopPanel(Foldable,QDialog):
    def __init__(self, manager, identity, geometry):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.manager, self.runtime, self.dock = manager, manager.runtime, manager.dock
        from interaction_motion import attach
        attach(self,lambda:self.dock.cfg)
        self.identity, self.default_geometry = identity, list(geometry)
        self.setProperty('clickThroughKey','panel:'+str(identity))
        self.default_ui_factor=geometry[2]/320 if not self.model.get('geometry') else 1.0
        self.ui_factor = 1.0
        from widget_face import FaceTracker
        self.face_tracker=FaceTracker(self,lambda:self.dock.cfg,'panel',lambda:self.runtime.face_roles)
        self.disposed = False
        self.restoring = True
        self.collapsed = False
        self.manual_resize = False
        self.merged_view = self.manager.is_merged(self.identity)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_content)
        self.drag_origin = None
        self.edge_drag = None
        self.dragged = False
        self.backdrop = None
        self.desktop_stack = None
        self.spec_x, self.spec_alpha = 0, 0
        self.setObjectName('DesktopPanel')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.store_geometry)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.capture_backdrop)
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.setInterval(650)
        self.collapse_timer.timeout.connect(self.collapse_if_outside)
        self.expand_timer = QTimer(self)
        self.expand_timer.setSingleShot(True)
        self.expand_timer.setInterval(250)
        self.expand_timer.timeout.connect(self.expand_if_inside)
        body = QVBoxLayout(self)
        body.setContentsMargins(10, 6, 10, 6)
        body.setSpacing(4)
        body.setSizeConstraint(QLayout.SetNoConstraint)
        header = self.header_layout = QHBoxLayout()
        header.setSpacing(4)
        self.header_icon=label('');self.header_icon.setAttribute(Qt.WA_TransparentForMouseEvents);header.addWidget(self.header_icon)
        self.title = label('')
        self.title.setObjectName('PanelLabel')
        self.title.setStyleSheet('font-weight:600;');self.title.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.count = label('')
        self.count.setObjectName('PanelLabel')
        self.count.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(self.title, 1)
        header.addWidget(self.count)
        self.settings_button=button('',self.edit_options);self.settings_button.setObjectName('PanelButton');self.settings_button.setToolTip('卡片设置');self.settings_button.setAccessibleName('卡片设置');header.addWidget(self.settings_button)
        self.menu_button = button('⋯', self.open_menu)
        self.menu_button.setObjectName('PanelButton')
        self.menu_button.setToolTip('面板选项')
        self.collapse_button = button('−', self.toggle_collapse)
        self.collapse_button.setObjectName('PanelButton')
        self.collapse_button.setToolTip('收起 / 展开')
        header.addWidget(self.menu_button)
        header.addWidget(self.collapse_button)
        body.addLayout(header)
        self.content = QWidget()
        self.content.setObjectName('PanelContent')
        self.content.installEventFilter(self)
        content = QVBoxLayout(self.content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(4)
        content.setSizeConstraint(QLayout.SetNoConstraint)
        self.tabs = PanelTabs(self)
        self.tabs.setObjectName('PanelTabs')
        self.tabs.setExpanding(False)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.currentChanged.connect(self.select_tab)
        content.addWidget(self.tabs)
        self.tabs.setVisible(self.manager.is_merged(self.identity))
        self.query = QLineEdit()
        self.query.setObjectName('PanelSearch')
        self.query.setPlaceholderText('搜索此面板')
        content.addWidget(self.query)
        self.list = CollectionList()
        self.list.setObjectName('PanelFiles')
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.list.setMinimumHeight(0)
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Free)
        self.list.setIconSize(QSize(34, 34))
        self.list.setGridSize(QSize(78, 78))
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setWordWrap(True)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        from card_file_ui import FileNameDelegate
        self.list.setItemDelegate(FileNameDelegate(self.list))
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(False)
        self.list.viewport().setAcceptDrops(False)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.item_menu)
        self.list.itemDoubleClicked.connect(self.launch_item)
        content.addWidget(self.list, 1)
        from flip_stack import ContentTransition
        self.page_transition=ContentTransition(self.list)
        from page_footer import CollectionHint, PagePager
        self.notice = CollectionHint(CollectionHint.drop_text, self.list)
        self.notice.setObjectName('PanelLabel')
        self.notice.setStyleSheet('font-size:11px;')
        self.notice.setContentsMargins(0, 0, 4, 0)
        self.notice.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.list.verticalScrollBar().valueChanged.connect(self.notice.update)
        self.list.verticalScrollBar().rangeChanged.connect(self.notice.update)
        self.page_pager = PagePager(self.list, self.shift_merged_page, bottom=0, leading=self.notice)
        self.page_pager.hide()
        body.addWidget(self.content, 1)
        self.query.textChanged.connect(self.render)
        self.setGeometry(*self.model.get('geometry', self.default_geometry))
        self.apply_options()
        self.set_collapsed_geometry(bool(self.model.get('collapsed')))
        self.restoring = False

    def update_tabs(self, models):
        self.tabs.blockSignals(True)
        expected = [(model['id'],model['name']) for model in models]
        current = [(self.tabs.tabData(i),self.tabs.tabText(i)) for i in range(self.tabs.count())]
        # Keep Qt's transient tab order intact until the drag is committed.
        if current != expected and not self.tabs.pressing:
            while self.tabs.count(): self.tabs.removeTab(0)
            for identity,name in expected:
                index = self.tabs.addTab(name)
                self.tabs.setTabData(index, identity)
        for index,(identity,name) in enumerate(expected):
            if identity==self.identity and not self.tabs.pressing and self.tabs.currentIndex()!=index: self.tabs.setCurrentIndex(index)
        self.update_tab_icons()
        merged = self.manager.is_merged(self.identity)
        self.tabs.setVisible(merged)
        self.tabs.blockSignals(False)
        can_switch = merged and len(expected) > 1
        self.page_pager.setVisible(can_switch)
        self.page_pager.set_page(self.model['name'], can_switch)

    def update_tab_icons(self):
        size=metric(15,self.ui_factor,11);light=self.colors()['light'];dpr=self.devicePixelRatioF()
        signature=(size,light,dpr,tuple(self.tabs.tabData(i) for i in range(self.tabs.count())))
        if signature==getattr(self,'_tab_icon_signature',None):return
        self._tab_icon_signature=signature
        self.tabs.setIconSize(QSize(size,size))
        for index in range(self.tabs.count()):
            identity=self.tabs.tabData(index)
            self.tabs.setTabIcon(index,QIcon(category_icon(identity,category_color(identity,light),size,dpr)))
            self.tabs.setTabToolTip(index,self.tabs.tabText(index)+' · 拖动排序或拖出卡片')

    def page_state(self):
        if getattr(self,'_idle_state',None) is not None:return self._idle_state
        return (self.query.text(),self.selected_keys(),self.list.verticalScrollBar().value())

    def restore_page_state(self,state):
        query,selected,scroll=state
        self._idle_state=None
        self.query.blockSignals(True);self.query.setText(query);self.query.blockSignals(False)
        self.list.clearSelection();self._released_selection=set(selected)
        if self.isVisible():
            self.render();self.fit_content();self.list.verticalScrollBar().setValue(scroll)
        else:self._idle_state=(query,set(selected),scroll)

    def select_tab(self, index):
        if self.tabs.pressing: return
        identity = self.tabs.tabData(index)
        if identity and identity!=self.identity:
            self.manager.select_page(identity)
            if self.manager.active_for(identity)!=identity: self.update_tabs(self.manager.merged_models(identity))

    def shift_merged_page(self, step):
        if self.tabs.pressing or not self.manager.is_merged(self.identity):
            return
        index = self.tabs.currentIndex()
        count = self.tabs.count()
        if index >= 0 and count > 1:
            self.select_tab((index + step) % count)

    @property
    def model(self): return self.manager.model(self.identity)

    def option(self, key):
        if key in ('collapse_style','capsule_ratio','ball_diameter','fold_height'):
            from fold_options import settings
            return settings(self)[{'collapse_style':'style','capsule_ratio':'ratio','ball_diameter':'diameter','fold_height':'height'}[key]]
        return self.dock.cfg['panel_'+key]

    def surface_colors(self, style=None):
        from appearance_presets import panel_appearance
        style = panel_appearance(self.dock.cfg) if style is None else style
        theme, color = style['theme'], style['color']
        if theme == 'follow':
            theme = None
            color = color or self.dock.cfg.get('theme_color', '')
        if self.option('appearance_source') == 'custom' and self.dock.cfg.get('card_design') in ('gradient','paper','minimal'):theme='light'
        from liquid_glass import material_palette
        return material_palette(tint_palette(self.dock.base_theme_colors(theme), color), style['material'])

    def colors(self, style=None):
        from appearance_presets import material_design, panel_appearance
        from component_contrast import content_contrast
        style=panel_appearance(self.dock.cfg) if style is None else style
        design=material_design(style['material'],'aurora') if self.option('appearance_source')=='app' else self.dock.cfg['card_design']
        light=content_contrast(self,self.dock,style,self.option('content_mode'),self.refresh_content_style,
                               design=design,regional=True)
        return dict(self.surface_colors(style),light=light,fg=QColor('#101b25' if light else '#ffffff'))

    def text_ink_at(self,child,rect,muted=False,on_selection=False):
        from compact_colors import area_colors
        state=getattr(self,'_content_contrast',None)
        light=state.result if state is not None else self.surface_colors()['light']
        colors=dict(light=light,ink='#101b25' if light else '#ffffff',muted='#34485a' if light else '#e1ebf3')
        area=QRectF(rect).translated(child.mapTo(self,QPoint()))
        colors=area_colors(self,area,colors)
        if on_selection and 'background_rgb' in colors:
            from background_contrast import blend,foreground
            return foreground(blend('#ffffff',colors['background_rgb'],(145 if light else 45)/255))
        return colors['muted' if muted else 'ink']

    def apply_options(self):
        layout=getattr(self.runtime,'layout',None)
        from card_metrics import metrics
        from screen_layout import screen_records
        self.ui_factor=layout.panel_scale(self.identity) if layout else metrics(self.dock.cfg,self.model.get('geometry',self.default_geometry),screen_records())[1]
        factor=self.ui_factor
        self.layout().setContentsMargins(metric(10,factor),metric(6,factor),metric(10,factor),metric(6,factor))
        self.layout().setSpacing(metric(4,factor))
        self.header_layout.setSpacing(metric(5,factor))
        self.content.layout().setSpacing(metric(4,factor))
        self.notice.setStyleSheet('font-size:%dpx;'%metric(11,factor,6))
        view = self.model.get('view','small')
        self.list.setViewMode(QListWidget.ListMode if view=='list' else QListWidget.IconMode)
        if view=='list':self.list.resetVerticalScrollMode()
        else:self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # Programmatic icon placement uses Free mode. File dragging is handled
        # by CollectionList, and internal drops into this view stay disabled.
        self.list.setMovement(QListWidget.Static if view=='list' else QListWidget.Free)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(False)
        self.list.viewport().setAcceptDrops(False)
        icon=metric(22 if view=='list' else 54 if view=='large' else 34,factor,12)
        self.list.setIconSize(QSize(icon,icon))
        # Reset explicit IconMode properties: a zero grid makes list rows overlap.
        self.list.setFlow(QListWidget.TopToBottom if view=='list' else QListWidget.LeftToRight)
        self.list.setWrapping(view!='list')
        from PyQt5.QtGui import QFont,QFontMetrics
        text_font=QFont(self.list.font());text_font.setPixelSize(self.text_pixels())
        font_height=QFontMetrics(text_font).height();margin=max(2,round(font_height*.2))
        # Keep icon and column widths; reserve three complete filename lines.
        grid_height=max(metric(102 if view=='large' else 78,factor),icon+margin*3+font_height*3)
        self.list.setGridSize(QSize() if view=='list' else QSize(metric(108 if view=='large' else 78,factor),grid_height))
        self.list.setSpacing(0)
        self.setWindowTitle(self.model['name']+' · 桌面收纳')
        if self.collapsed:
            self.set_collapsed_geometry(True)
        else:
            self.setMinimumSize(1,1)
            self.setMaximumSize(16777215,16777215)
            self.setMinimumSize(min(minimum(factor)[0],self.width()),min(minimum(factor)[1],self.height()))
            if self.option('locked'):self.setFixedSize(self.size())
        self.unsetCursor()
        self.refresh_content_style()
        height=self.list.fontMetrics().height();icon=self.list.iconSize().height()
        if view!='list':
            grid=self.list.gridSize();self.list.setGridSize(QSize(grid.width(),max(grid.height(),icon+height*3+metric(12,factor))))
        self.render()
        if self.isVisible():self.fit_timer.start(0)
        self.face_tracker.sync_face()
        from fold_options import header
        header(self,self.collapsed)
        if self.isVisible():self.attach_desktop()
        self.refresh_wallpaper_later(100)
        self.update()

    def refresh_content_style(self):
        factor=self.ui_factor
        colors = self.colors()
        ink = colors['fg'].name()
        self.page_pager.sync_appearance(self.text_ink_at(self.page_pager,self.page_pager.rect()))
        content_ink='#000000' if colors['light'] else '#ffffff'
        self.list.setStyleSheet('QListWidget#PanelFiles {color:'+content_ink+';}')
        content_palette=self.list.palette()
        content_palette.setColor(QPalette.Text,QColor(content_ink));content_palette.setColor(QPalette.HighlightedText,QColor(content_ink))
        self.list.setPalette(content_palette)
        search_background = 'transparent' if self.is_clear() else 'rgba(128,128,128,20)'
        self.setStyleSheet(panel_css('''QDialog#DesktopPanel, QWidget#PanelContent {background:transparent;}
            QLabel#PanelLabel, QListWidget#PanelFiles, QLineEdit#PanelSearch, QPushButton#PanelButton, QTabBar#PanelTabs {color:%s;}
            QTabBar#PanelTabs::tab {padding:5px 8px; margin:0; border-bottom:2px solid transparent;}
            QTabBar#PanelTabs::tab:selected {border-bottom-color:rgba(128,128,128,140);}
            QTabBar#PanelTabs QToolButton {border:0; background:rgba(128,128,128,28); border-radius:4px; width:18px;}
            QListWidget#PanelFiles {background:transparent; border:0; padding:0;}
            QListWidget#PanelFiles::item {padding:2px; border-radius:6px;}
            QListWidget#PanelFiles::item:selected {background:rgba(128,128,128,65);}
            QListWidget#PanelFiles::item:hover {background:rgba(128,128,128,35);}
            QPushButton#PanelButton {background:transparent; border:0; padding:0; min-height:24px; max-width:26px; min-width:26px;}
            QPushButton#PanelButton:hover {background:rgba(128,128,128,40);}
            QLineEdit#PanelSearch {background:%s; border:0; padding:3px 8px; min-height:20px;}
        ''' % (ink, search_background),factor)+'''QLabel#PanelLabel, QLineEdit#PanelSearch, QListWidget#PanelFiles, QPushButton#PanelButton, QTabBar#PanelTabs {font-size:%dpx;}'''%self.text_pixels())
        hover='rgba(255,255,255,85)' if colors['light'] else 'rgba(255,255,255,25)'
        selected='rgba(255,255,255,145)' if colors['light'] else 'rgba(255,255,255,45)'
        pressed='rgba(255,255,255,205)' if colors['light'] else 'rgba(255,255,255,72)'
        self.setStyleSheet(self.styleSheet()+panel_css("""
            QTabBar#PanelTabs::tab {color:transparent;padding:4px 8px;margin:1px 3px 2px 0;border:1px solid transparent;border-radius:7px;background:transparent;font-weight:600;}
            QTabBar#PanelTabs::tab:hover {background:%s;}
            QTabBar#PanelTabs::tab:selected {color:transparent;background:%s;border:1px solid rgba(255,255,255,110);font-weight:600;}
            QTabBar#PanelTabs[movingTab="true"]::tab {color:palette(window-text);}
            QTabBar#PanelTabs::tab:selected:hover {background:%s;}
            QTabBar#PanelTabs[pointerDown="true"]::tab:selected {background:%s;}
            QPushButton#PanelButton {padding:0;min-width:24px;max-width:24px;min-height:24px;max-height:24px;border:0;border-radius:6px;outline:0;background:transparent;}
            QPushButton#PanelButton:hover {background:%s;}
            QPushButton#PanelButton:pressed {background:%s;}
            QPushButton#PanelButton:focus {border:0;outline:0;}
        """%(hover,selected,pressed,pressed,hover,pressed),factor))
        self.update_identity_header()
        self.update_tab_icons()
        self.title.setToolTip(self.model['name']);self.count.setToolTip('此分组项目数量')
        for label,text in ((self.title,self.model['name']),(self.notice,self.notice.text())):
            extent=label.rect()
            extent.setWidth(min(extent.width(),label.fontMetrics().horizontalAdvance(text)+4))
            label_ink=self.text_ink_at(label,extent,muted=label is self.notice)
            font='font-weight:600;' if label is self.title else 'font-size:%dpx;'%metric(11,factor,6)
            label.setStyleSheet(f'color:{label_ink};'+font)
        count_ink=self.text_ink_at(self.count,self.count.rect())
        self.count.setStyleSheet(panel_css(f'color:{count_ink};padding:1px 5px;border-radius:5px;background:rgba(128,128,128,16);',factor))
        self.settings_button.setIcon(QIcon(category_icon('settings',self.text_ink_at(self.settings_button,self.settings_button.rect()),metric(16,factor,12),self.devicePixelRatioF())));self.settings_button.setIconSize(QSize(metric(16,factor,12),metric(16,factor,12)))
        for control in (self.menu_button,self.collapse_button):
            control.setStyleSheet('color:'+self.text_ink_at(control,control.rect())+';')
        for control in (self.settings_button,self.menu_button,self.collapse_button):control.setFixedSize(metric(24,factor,16),metric(24,factor,16))
        extent=self.query.contentsRect()
        extent.setWidth(min(extent.width(),8+self.query.fontMetrics().horizontalAdvance(self.query.text() or self.query.placeholderText())))
        self.query.setStyleSheet('color:'+self.text_ink_at(self.query,extent)+';')
        palette = self.query.palette()
        palette.setColor(QPalette.PlaceholderText,QColor(self.text_ink_at(self.query,extent,muted=True)))
        self.query.setPalette(palette)
        if getattr(self,'fold_badge',None) is not None:
            self.fold_badge.update()
        self.list.viewport().update();self.update()

    def update_identity_header(self):
        self.setWindowTitle(self.model['name']+' · 桌面收纳')
        if self.option('face'):
            self.header_icon.clear()
            self.header_icon.setFixedSize(metric(38*self.option('face_scale')/100,self.ui_factor,24),metric(24,self.ui_factor,18))
            return
        size=metric(17,self.ui_factor,12);self.header_icon.setFixedSize(size,size)
        self.header_icon.setPixmap(category_icon(self.identity,category_color(self.identity,self.colors()['light']),size,self.devicePixelRatioF()))

    def text_pixels(self):
        from card_metrics import font_pixels
        return font_pixels(self.dock.cfg,self.ui_factor)

    def visible_items(self):
        query = self.query.text().strip().casefold()
        return [row for row in self.manager.rows(self.identity)
                if query in row['name'].casefold() or query in row['path'].casefold()]

    def release_hidden_resources(self):
        if self.isVisible():return False
        if getattr(self,'_idle_state',None) is None:
            self._idle_state=(self.query.text(),self.selected_keys()|getattr(self,'_released_selection',set()),self.list.verticalScrollBar().value())
        self._released_selection=set(self._idle_state[1])
        self.list.clear();self.backdrop=None;self._render_signature=None
        self.refresh_timer.stop();self.fit_timer.stop()
        return True

    def render(self, *args, prepare=False, force=False):
        if not prepare and not self.isVisible():
            self.release_hidden_resources()
            self.title.setText(self.model['name']);self.count.setText(str(len(self.manager.rows(self.identity))))
            return
        if force:
            # F5 is an explicit reload, including manual cards when automatic
            # collection is disabled. Do not reuse the previous scan's metadata.
            for row in self.manager.rows(self.identity):self.manager.file_metadata.pop(path_key(row['path']),None)
            self._render_signature=None
        rows = self.visible_items()
        restoring_idle=getattr(self,'_idle_state',None) is not None
        scroll = self._idle_state[2] if restoring_idle else self.list.verticalScrollBar().value()
        self._idle_state=None
        selected = self.selected_keys() | getattr(self, '_released_selection', set())
        self._released_selection = set()
        from card_file_ui import card_display_name, file_item_pixmap
        icon_view=self.list.viewMode()==QListWidget.IconMode
        pixels=max(24,self.list.iconSize().width())
        metadata=self.manager.file_metadata
        signature=(self.identity,icon_view,pixels,self.devicePixelRatioF(),rows,
                   tuple(metadata.get(path_key(row['path'])) for row in rows))
        self.title.setText(self.model['name'])
        self.count.setText(str(len(self.manager.rows(self.identity))))
        self.notice.setText(self.manager.message or (self.notice.drop_text if rows else self.notice.empty_text))
        if not restoring_idle and signature==getattr(self,'_render_signature',None):return
        current=self.list.currentItem();current_key=path_key(current.data(Qt.UserRole)['path']) if current else None
        current_row=self.list.currentRow()
        existing={path_key(self.list.item(i).data(Qt.UserRole)['path']):self.list.item(i) for i in range(self.list.count())}
        desired={path_key(row['path']) for row in rows}
        # Keep existing QListWidgetItems: unchanged files retain their pixmaps,
        # current keyboard item and selection instead of being recreated on scan.
        self.list.setUpdatesEnabled(False)
        try:
            for index in range(self.list.count()-1,-1,-1):
                if path_key(self.list.item(index).data(Qt.UserRole)['path']) not in desired:self.list.takeItem(index)
            for index,row in enumerate(rows):
                key=path_key(row['path']);state=metadata.get(key);item=existing.get(key)
                if item is None:
                    item=QListWidgetItem();self.list.insertItem(index,item)
                elif self.list.row(item)!=index:
                    self.list.takeItem(self.list.row(item));self.list.insertItem(index,item)
                icon_signature=(row['path'],pixels,icon_view,state)
                if force or item.data(Qt.UserRole+1)!=icon_signature:
                    item.setIcon(QIcon(file_item_pixmap(self.dock.icons, row['path'], pixels,
                                                       state=state, hide_shortcut=icon_view)))
                    item.setData(Qt.UserRole+1,icon_signature)
                item.setText(card_display_name(row,icon_view,state))
                item.setToolTip(('已置顶 · ' if row.get('pinned') else '')+row['path'])
                item.setData(Qt.UserRole,row);item.setSelected(key in selected)
                if key==current_key:self.list.setCurrentItem(item,QItemSelectionModel.NoUpdate)
            if current_key not in desired and current_row>=0 and self.list.count():
                self.list.setCurrentRow(min(current_row,self.list.count()-1),QItemSelectionModel.NoUpdate)
            self._render_signature=signature
            if restoring_idle:self.list.doItemsLayout()
            self.list.verticalScrollBar().setValue(scroll)
        finally:self.list.setUpdatesEnabled(True)
        self.fit_timer.start(0)

    def fit_content(self):
        # Preserve freely chosen dimensions, including when merged pages switch.
        self.fit_timer.stop()
        self.list.doItemsLayout()
        self.list.align_icons(self.model.get('icon_alignment','center'))
        self.notice.update()

    def set_compact(self, enabled):
        self.manual_resize = False
        if self.manager.is_merged(self.identity): self.manager.update_group(self.identity,compact=enabled)
        if self.manager.update_panel(self.identity, compact=enabled): self.fit_timer.start(0)

    def selected_keys(self):
        return {path_key(item.data(Qt.UserRole)['path']) for item in self.list.selectedItems()}

    def launch_item(self, item):
        path = item.data(Qt.UserRole)['path']
        if not os.path.exists(path):
            self.notice.setText('原文件已移动或不存在，请重新拖入。')
            return
        self.dock.launch(path,source='file_open')

    def item_menu(self, point):
        item = self.list.itemAt(point)
        if item is None:
            self.exec_panel_menu(self.list.viewport().mapToGlobal(point))
            return
        if item and not item.isSelected():
            self.list.clearSelection()
            item.setSelected(True)
        if not self.selected_keys(): return
        self.collapse_timer.stop()
        from native_file_menu import NativeFileMenu
        menu=None;shown=False
        try:
            menu=NativeFileMenu(int(self.winId()),self.selected_paths());menu.add_card_commands(self.card_item_commands())
            paths=tuple(self.selected_paths());menu.verb_handlers['rename']=lambda:self.rename_file(paths)
            self._active_file_menu=menu;shown=True
            result=menu.track()
            if result=='shell':
                self.manager.schedule_scan()
                if menu.selected_verb=='delete':
                    from card_file_actions import reconcile_shell_delete
                    reconcile_shell_delete(self.manager,paths)
        except Exception as error:
            self.runtime.api.log('系统文件菜单或操作失败：'+str(error))
            if shown:self.notice.setText('系统文件操作未完成，请检查后重试。')
            else:
                self.notice.setText('系统菜单不可用，已显示卡片操作。')
                fallback=self.build_item_menu();fallback.exec_(self.list.viewport().mapToGlobal(point));fallback.deleteLater()
        finally:
            self._active_file_menu=None
            if menu:menu.close()
            if not self.disposed and self.option('auto_hide'):self.collapse_timer.start()

    def nativeEvent(self,event_type,message):
        from fold_options import native_minimum
        if native_minimum(self,message):return True,0
        menu=getattr(self,'_active_file_menu',None)
        if menu:
            import ctypes
            from ctypes import wintypes
            msg=ctypes.cast(int(message),ctypes.POINTER(wintypes.MSG)).contents
            result=menu.handle_message(msg.message,msg.wParam,msg.lParam)
            if result is not None:return True,result
        return super().nativeEvent(event_type,message)

    def card_item_commands(self):
        keys=self.selected_keys();paths=self.selected_paths();identity=self.identity
        rows=self.manager.rows(identity)
        pinned=all(row.get('pinned',False) for row in rows if path_key(row['path']) in keys)
        references=[(model['name'],lambda target=model['id']:self.manager.add_paths(target,paths))
                    for model in self.dock.cfg['desktop_panels'] if model['id']!=identity]
        commands=[('取消置顶' if pinned else '置顶',lambda:self.manager.pin_entries(keys,not pinned,identity))]
        if references:commands.append(('引用到其他面板',references))
        views=[(title+('（当前）' if self.model.get('view','small')==key else ''),
                lambda mode=key:self.manager.update_panel(identity,view=mode))
               for key,title in [('small','小图标'),('large','大图标'),('list','列表')]]
        commands.append(('显示方式',views))
        if self.model.get('view','small')!='list':
            alignment=self.model.get('icon_alignment','center')
            commands.append(('图标对齐',[(title+('（当前）' if value==alignment else ''),
                             lambda mode=value:self.manager.update_panel(identity,icon_alignment=mode))
                            for title,value in ICON_ALIGNMENTS]))
        commands.append(('粘贴到桌面',lambda:self.paste_files()))
        if len(paths)==1 and os.path.isdir(paths[0]):commands.append(('粘贴到此文件夹',lambda:self.paste_files(paths[0])))
        commands.append(('移除收纳引用（保留原文件）',lambda:self.manager.remove_entries(keys,identity)))
        return commands

    def rename_file(self,paths=None):
        from card_file_actions import rename_file
        return rename_file(self,paths)

    def shell_file_action(self,verb):
        from card_file_actions import shell_action
        return shell_action(self,verb)

    def selected_paths(self):
        return [item.data(Qt.UserRole)['path'] for item in self.list.selectedItems()]

    def copy_files(self,cut=False):
        from shell_file_clipboard import set_file_clipboard
        try:
            set_file_clipboard(self.selected_paths(),cut,int(self.winId()))
            self.notice.setText('已剪切，可在文件夹中粘贴。' if cut else '已复制，可在文件夹中粘贴。')
            return True
        except (OSError,ValueError) as error:
            self.notice.setText(str(error));return False

    def paste_files(self,folder=None):
        from shell_file_clipboard import paste_into_folder,paste_shell_clipboard,preferred_effect,clipboard_paths,MOVE
        try:
            destination=folder or (self.manager.roots[0] if self.manager.roots else '')
            if not destination:raise ValueError('未找到桌面文件夹，无法粘贴。')
            import ctypes
            clipboard=QApplication.clipboard();sequence=ctypes.windll.user32.GetClipboardSequenceNumber()
            mime=clipboard.mimeData();effect=preferred_effect(mime)
            try:paths=clipboard_paths(mime)
            except ValueError:
                result=paste_shell_clipboard(destination,int(self.winId()),effect,sequence)
                self.manager.schedule_scan()
                if result=='cancelled':self.notice.setText('Windows 文件传输已取消。');return False
                self.notice.setText('已交给 Windows 粘贴，远程文件将在传输完成后显示。')
                return True
            if sequence!=ctypes.windll.user32.GetClipboardSequenceNumber():raise ValueError('剪贴板内容已变化，请重新粘贴。')
            result=paste_into_folder(destination,int(self.winId()),effect,paths)
            if result=='same-folder':self.notice.setText('文件已经在目标文件夹中，无需移动。');return False
            if result=='cancelled':self.notice.setText('文件操作已取消，可能有部分项目已处理。');self.manager.schedule_scan();return False
            # A cut is cleared only if no one replaced the clipboard and every source moved.
            if effect==MOVE and sequence==ctypes.windll.user32.GetClipboardSequenceNumber() and all(not os.path.exists(path) for path in paths):clipboard.clear()
            self.notice.setText('已粘贴到'+('选定文件夹。' if folder else '桌面。'))
            self.manager.schedule_scan();return True
        except (OSError,ValueError) as error:
            self.notice.setText(str(error));return False

    def build_item_menu(self):
        menu = QMenu(self)
        keys = self.selected_keys()
        paths=self.selected_paths()
        menu.addAction('复制').triggered.connect(lambda:self.copy_files(False))
        menu.addAction('剪切').triggered.connect(lambda:self.copy_files(True))
        menu.addAction('粘贴到桌面').triggered.connect(lambda:self.paste_files())
        menu.addAction('重命名（F2）').triggered.connect(lambda:self.rename_file())
        menu.addAction('删除文件（Delete）').triggered.connect(lambda:self.shell_file_action('delete'))
        menu.addAction('属性（Alt+Enter）').triggered.connect(lambda:self.shell_file_action('properties'))
        if len(paths)==1 and os.path.isdir(paths[0]):
            menu.addAction('粘贴到此文件夹').triggered.connect(lambda:self.paste_files(paths[0]))
        menu.addSeparator()
        pinned = all(row.get('pinned', False) for row in self.manager.rows(self.identity) if path_key(row['path']) in keys)
        menu.addAction('取消置顶' if pinned else '置顶').triggered.connect(
            lambda: self.manager.pin_entries(keys, not pinned, self.identity))
        menu.addSeparator()
        move = menu.addMenu('引用到其他面板')
        for model in self.dock.cfg['desktop_panels']:
            if model['id'] != self.identity:
                move.addAction(model['name']).triggered.connect(
                    lambda checked=False, identity=model['id']: self.manager.add_paths(identity, [row['path'] for row in self.manager.rows(self.identity) if path_key(row['path']) in self.selected_keys()]))
        self.add_view_menu(menu)
        menu.addAction('移除收纳引用（保留原文件）').triggered.connect(
            lambda: self.manager.remove_entries(self.selected_keys(), self.identity))
        return menu

    def add_view_menu(self, menu):
        views = menu.addMenu('显示方式')
        for key,title in [('small','小图标'),('large','大图标'),('list','列表')]:
            action = views.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.model.get('view','small')==key)
            action.triggered.connect(lambda checked=False,value=key:self.manager.update_panel(self.identity,view=value))
        if self.model.get('view','small')!='list':
            align=menu.addMenu('图标对齐')
            for title,value in ICON_ALIGNMENTS:
                action=align.addAction(title);action.setCheckable(True)
                action.setChecked(self.model.get('icon_alignment','center')==value)
                action.triggered.connect(lambda checked=False,mode=value:self.manager.update_panel(self.identity,icon_alignment=mode))
        return views

    def contextMenuEvent(self, event):
        self.exec_panel_menu(event.globalPos())

    def open_menu(self):
        self.exec_panel_menu(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def exec_panel_menu(self, point):
        self.collapse_timer.stop()
        menu = self.build_panel_menu()
        menu.exec_(point)
        from PyQt5 import sip
        if not sip.isdeleted(menu): menu.deleteLater()
        if not self.disposed and self.option('auto_hide'): self.collapse_timer.start()

    def build_panel_menu(self):
        menu = QMenu(self)
        from fold_options import FoldOptions
        from ui_style import exec_dialog,menu_group,menu_heading
        menu_heading(menu,self.model['name']+' · 桌面收纳')
        menu.addAction('外观与收起…').triggered.connect(self.edit_options)
        menu.addAction('粘贴到桌面').triggered.connect(lambda:self.paste_files())
        menu.addSeparator()
        layout=menu_group(menu,'图标与排列','grid')
        self.add_view_menu(layout)
        files=menu_group(menu,'文件与收纳','apps')
        files.addAction('添加文件…').triggered.connect(self.add_files)
        files.addAction('添加文件夹…').triggered.connect(self.add_folder)
        files.addAction('重新扫描桌面').triggered.connect(self.manager.scan)
        manage=menu_group(menu,'卡片与分组','panels')
        manage.addAction('分组与合并管理…').triggered.connect(self.manager.manage_groups)
        merge = manage.addAction('独立显示此卡片' if self.manager.is_merged(self.identity) else '加入合并卡片')
        merge.triggered.connect(lambda: self.manager.set_merged(self.identity, not self.manager.is_merged(self.identity)))
        groups=manage.addMenu('加入合并组')
        for group in self.dock.cfg['merge_groups']:
            action=groups.addAction(group['name']);action.setCheckable(True)
            action.setChecked(self.manager.is_merged(self.identity) and self.manager.group_id(self.identity)==group['id'])
            action.triggered.connect(lambda checked=False,key=group['id']:self.manager.assign_group(self.identity,key))
        groups.addSeparator();groups.addAction('新建合并组…').triggered.connect(lambda:self.manager.new_merge_group(identity=self.identity))
        if self.identity not in dict(__import__('desktop_catalog').CATEGORIES):
            files.addAction('自动归入格式…').triggered.connect(self.edit_definition)
        manage.addAction('新建面板…').triggered.connect(lambda: self.manager.new_panel())
        manage.addAction('重命名…').triggered.connect(self.rename)
        manage.addSeparator()
        manage.addAction('移除此面板…').triggered.connect(lambda: self.manager.delete_panel(self.identity))
        window=menu_group(menu,'窗口与交互','position')
        window.addAction('收起样式…').triggered.connect(lambda:exec_dialog(FoldOptions(self)))
        window.addAction('尺寸与文字…').triggered.connect(lambda: self.runtime.open_card_sizing('panel',self.identity))
        top = window.addAction('桌面卡片置顶')
        top.setCheckable(True)
        top.setChecked(self.option('layer')=='top')
        top.triggered.connect(lambda on:self.manager.update_panel(self.identity,layer='top' if on else 'bottom'))
        from component_passthrough import component_actions
        component_actions(window.addMenu('鼠标穿透'),self.runtime,self.property('clickThroughKey'))
        from desktop_idle_fade import add_action
        add_action(window,self.runtime,self.property('clickThroughKey'))
        sort = layout.addMenu('排序方式')
        for key, title in [('name_asc','文件名：升序'), ('name_desc','文件名：降序'),
                           ('modified_desc','修改时间：最新优先'), ('modified_asc','修改时间：最早优先')]:
            action = sort.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.model.get('sort', 'name_asc') == key)
            action.triggered.connect(lambda checked=False, value=key: self.manager.update_panel(self.identity, sort=value))
        lock = window.addAction('锁定位置和大小')
        lock.setCheckable(True)
        lock.setChecked(self.option('locked'))
        lock.triggered.connect(lambda checked: self.manager.update_panel(self.identity, locked=checked))
        menu.addSeparator()
        menu.addAction('设置…').triggered.connect(self.runtime.show_settings)
        return menu

    def edit_definition(self):
        from panel_management import PanelDefinition
        dialog = PanelDefinition(self.model, self)
        if dialog.exec_()==dialog.Accepted:
            self.manager.update_panel(self.identity, name=dialog.name.text().strip(), extensions=dialog.extensions())
            self.manager.schedule_scan()
        dialog.deleteLater()

    def rename(self):
        name, okay = QInputDialog.getText(self, '重命名面板', '面板名称：', text=self.model['name'])
        if okay and name.strip(): self.manager.update_panel(self.identity, name=name.strip()[:40])

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '收纳文件（保留原位）')
        self.manager.add_paths(self.identity, paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, '收纳文件夹（保留原位）')
        if path: self.manager.add_paths(self.identity, [path])

    def edit_options(self,page=0):
        dialog = PanelOptions(self)
        if type(page) is int:dialog.tabs.setCurrentIndex(page)
        dialog.exec_()
        dialog.deleteLater()
        if self.option('auto_hide'): self.collapse_timer.start()

    def bounds(self):
        raw=(self.manager.group_value(self.identity,'geometry') if self.manager.is_merged(self.identity) and self.manager.group_value(self.identity,'geometry')
             else self.model.get('geometry',self.default_geometry))
        layout=getattr(self.runtime,'layout',None)
        if layout:return layout.panel_bounds(self.identity,raw)
        from card_metrics import metrics
        from screen_layout import screen_records
        return metrics(self.dock.cfg,list(raw),screen_records())[0]

    from fold_options import instant_geometry

    @instant_geometry
    def set_collapsed_geometry(self, collapsed):
        self.restoring = True
        self.collapsed = collapsed
        self.edge_drag = None
        self.unsetCursor()
        self.content.setVisible(not collapsed)
        self.setMinimumSize(1, 1)
        self.setMaximumSize(16777215, 16777215)
        geometry = self.bounds()
        if collapsed:
            from fold_options import geometry as fold_geometry,settings
            from panel_preferences import CARD_FOLD_SIZE
            target=fold_geometry(geometry,settings(self),metric(CARD_FOLD_SIZE,self.ui_factor,24),self.ui_factor,CARD_FOLD_SIZE)
            self._fold_target=tuple(target)
            self.setFixedSize(target[2],target[3]);self.move(*target[:2]);self._fold_offset=(target[0]-geometry[0],target[1]-geometry[1])
        else:
            from PyQt5.QtCore import QPoint
            screen = QApplication.screenAt(QPoint(geometry[0], geometry[1])) or QApplication.primaryScreen()
            available = screen.availableGeometry()
            width = min(geometry[2], available.width())
            height = min(geometry[3], available.height())
            x = max(available.left(), min(geometry[0], available.right()+1-width))
            y = max(available.top(), min(geometry[1], available.bottom()+1-height))
            self.setGeometry(x, y, width, height)
            self.setMinimumSize(min(minimum(self.ui_factor)[0],geometry[2],available.width()), min(minimum(self.ui_factor)[1],geometry[3],available.height()))
            if self.option('locked'):self.setFixedSize(self.size())
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        self.move(max(available.left(), min(self.x(), available.right()+1-self.width())),
                  max(available.top(), min(self.y(), available.bottom()+1-self.height())))
        from fold_options import header
        header(self,collapsed)
        if collapsed:
            self.layout().activate()
            from fold_options import apply_compact_size
            apply_compact_size(self,target)
            header(self,collapsed)
        self._fold_offset=(self.x()-geometry[0],self.y()-geometry[1]) if collapsed else (0,0)
        self._layout_geometry=self.geometry().getRect()
        self.collapse_button.setText('+' if collapsed else '−')
        if not collapsed: self.fit_timer.start(0)
        self.restoring = False
        if self.isVisible():
            self.refresh_timer.stop()
            self.capture_backdrop()
        self.update()

    def collapse(self):
        self.change_fold(True)

    def expand(self):
        self.change_fold(False)

    def change_fold(self, collapsed):
        from fold_transition import transition
        layout=getattr(self.runtime,'layout',None)
        if layout and layout.pending:return
        if self.disposed or self.collapsed == collapsed:return
        if collapsed:self.store_geometry()
        with transition(self, self.dock.cfg.get('motion_enabled', True), self.surface_radius,
                        target_rect=lambda: QRect(*self.bounds())):
            if self.manager.update_panel(self.identity, collapsed=collapsed):
                self.set_collapsed_geometry(collapsed)

    def toggle_collapse(self):
        if self.collapsed: self.expand()
        else: self.collapse()

    def collapse_if_outside(self):
        if self.option('auto_hide') and self.isVisible() and not self.tabs.pressing and self.drag_origin is None and self.edge_drag is None and not self.rect().contains(self.mapFromGlobal(QCursor.pos())) and not QApplication.activePopupWidget():
            active = QApplication.activeWindow()
            if active and active is not self and self.isAncestorOf(active): return
            self.collapse()

    def expand_if_inside(self):
        if self.option('expand_mode')=='hover' and self.isVisible() and self.underMouse(): self.expand()

    def enterEvent(self, event):
        self.collapse_timer.stop()
        self.face_tracker.pulse()
        if self.collapsed and self.option('expand_mode')=='hover': self.expand_timer.start()
        super().enterEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.content and event.type() == QEvent.Enter and self.edge_drag is None:
            self.unsetCursor()
        return super().eventFilter(watched, event)

    def leaveEvent(self, event):
        self.expand_timer.stop()
        self.spec_alpha = 0
        self.update()
        if self.option('auto_hide'): self.collapse_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:self.face_tracker.press(True)
        edges = self.resize_edges(event.pos())
        if event.button() == Qt.LeftButton and edges:
            self.edge_drag = (self.geometry(), event.globalPos(), edges)
            self.resize_timer.stop()
            self.refresh_timer.stop()
            self.setCursor(resize_cursor(edges))
            event.accept()
            return
        if event.button() == Qt.LeftButton and event.pos().y() <= 44 and not self.option('locked'):
            self.drag_origin = event.globalPos()-self.pos()
            self.drag_start = event.globalPos()
            self.dragged = False
            event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.spec_x, self.spec_alpha = event.pos().x(), .7
        self.update()
        if self.edge_drag is not None and event.buttons() & Qt.LeftButton:
            self.resize_from_edge(event.globalPos())
            event.accept()
        elif self.drag_origin is not None and event.buttons() & Qt.LeftButton:
            if self.dragged or (event.globalPos()-self.drag_start).manhattanLength()>=QApplication.startDragDistance():
                self.dragged = True
                self.move(event.globalPos()-self.drag_origin)
                if not self.merged_view:self.manager.preview_card_drop(self,event.globalPos())
        else:
            edges = self.resize_edges(event.pos())
            self.setCursor(resize_cursor(edges) if edges else Qt.ArrowCursor)
            super().mouseMoveEvent(event)

    def resize_edges(self, point):
        return edges_at(self.rect(), point) if not self.collapsed and not self.option('locked') else 0

    def resize_from_edge(self, point):
        original, pointer, edges = self.edge_drag
        self.setGeometry(resized_rect(original, edges, point - pointer, (self.minimumWidth(), self.minimumHeight())))

    def mouseReleaseEvent(self, event):
        if event.button()==Qt.LeftButton:self.face_tracker.press(False)
        if event.button() == Qt.LeftButton and self.edge_drag is not None:
            self.resize_from_edge(event.globalPos())
            original, _, _ = self.edge_drag
            self.edge_drag = None
            if self.size() != original.size():
                self.manual_resize = True
            self.store_geometry()
            self.refresh_wallpaper_later(150)
            edges = self.resize_edges(self.mapFromGlobal(event.globalPos()))
            self.setCursor(resize_cursor(edges) if edges else Qt.ArrowCursor)
            event.accept()
            return
        if event.button()==Qt.LeftButton and self.drag_origin is not None:
            if self.dragged or (event.globalPos()-self.drag_start).manhattanLength()>=QApplication.startDragDistance():
                self.dragged = True
                self.move(event.globalPos()-self.drag_origin)
            self.drag_origin = None
            if self.dragged:
                if self.manager.drop_independent_at(self,event.globalPos()):return
                from card_snap import finish_drag
                finish_drag(self, event.globalPos())
            self.store_geometry()
            if self.collapsed and not self.dragged: self.expand()
        elif event.button()==Qt.LeftButton and self.collapsed:self.expand()
        super().mouseReleaseEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.refresh_wallpaper_later(120)
        badge=getattr(self,'fold_badge',None)
        if not self.restoring and self.drag_origin is None and self.edge_drag is None and (not badge or badge.origin is None):
            self.resize_timer.start(250)

    def resizeEvent(self, event):
        if hasattr(self,'page_transition'):self.page_transition.cancel()
        super().resizeEvent(event)
        if not self.collapsed and event.oldSize().width()!=event.size().width():
            self.fit_timer.start(0)
        if not self.restoring and self.edge_drag is None:
            if self.collapsed:
                target=getattr(self,'_fold_target',None);layout=getattr(self.runtime,'layout',None)
                if target and (self.width(),self.height())!=target[2:] and layout:layout.changed()
                return
            if not self.collapsed and event.oldSize().isValid(): self.manual_resize = True
            self.resize_timer.start(250)
            self.refresh_wallpaper_later(200)

    def store_geometry(self,persist=True):
        if self.restoring or self.disposed: return
        layout=getattr(self.runtime,'layout',None)
        if layout and (layout.pending or layout.applying):return
        if self.merged_view != self.manager.is_merged(self.identity): return
        if self.merged_view and self.manager.active_for(self.identity) != self.identity: return
        geometry = self.bounds()
        offset=getattr(self,'_fold_offset',(0,0)) if self.collapsed else (0,0)
        geometry[0:2] = [self.x()-offset[0], self.y()-offset[1]]
        if not self.collapsed: geometry[2:4] = [self.width(), self.height()]
        changed=self.geometry().getRect()!=getattr(self,'_layout_geometry',None)
        anchor=layout.panel_update(self.identity,geometry) if layout and (changed or not layout.record(self.identity)) else None
        if self.manager.is_merged(self.identity):
            changes = self.manager.group_changes(self.identity,geometry=geometry,**({'compact':False} if self.manual_resize else {}))
            if anchor is not None:changes['display_layout']=anchor
            if not persist:self.dock.cfg.update(changes);return
            if any(self.dock.cfg.get(key)!=value for key,value in changes.items()) and not self.manager.commit(**changes):return
            self.manual_resize = False
            self._layout_geometry=self.geometry().getRect()
            return
        changes = {'geometry': geometry}
        if self.manual_resize:
            changes['compact'] = False
        if not persist:
            import copy
            panels=copy.deepcopy(self.dock.cfg['desktop_panels'])
            next(row for row in panels if row['id']==self.identity).update(changes)
            self.dock.cfg['desktop_panels']=panels
            if anchor is not None:self.dock.cfg['display_layout']=anchor
            return
        if anchor is not None or any(self.model.get(key) != value for key, value in changes.items()):
            if self.manager.update_panel(self.identity, _layout=anchor if anchor is not None else False, **changes):
                self.manual_resize = False
                self._layout_geometry=self.geometry().getRect()

    def showEvent(self, event):
        super().showEvent(event)
        self.face_tracker.sync_face()
        self.desktop_stack = None
        self.attach_desktop()
        if getattr(self,'_idle_state',None) is not None:self.render(prepare=True)
        self.fit_timer.stop()
        self.fit_content()
        self.refresh_timer.stop()
        self.capture_backdrop()
        if self.option('auto_hide'): self.collapse_timer.start()

    def attach_desktop(self, owner=None):
        if owner is None and self.dock.preview:return
        from window_layers import desktop_layer, effective_top, is_topmost, owner_of, shell_owner
        hwnd = int(self.winId())
        top = effective_top(self.dock.cfg,self.option('layer')=='top')
        owner = 0 if top else shell_owner() if owner is None else owner
        state = (hwnd, top, owner)
        if self.desktop_stack!=state or is_topmost(hwnd)!=top or owner_of(hwnd)!=owner:
            if desktop_layer(hwnd,top,owner):self.desktop_stack=state
            self.runtime.click_policy.apply(self)

    def hideEvent(self, event):
        if self.edge_drag is not None:
            self.manual_resize |= self.edge_drag[0].size() != self.size()
            self.edge_drag = None
        self.face_tracker.hide_face()
        self.page_transition.cancel()
        if not self.disposed and not self.restoring: self.store_geometry()
        for timer in (self.refresh_timer, self.resize_timer, self.collapse_timer, self.expand_timer, self.fit_timer): timer.stop()
        self.backdrop = None
        super().hideEvent(event)
        self.release_hidden_resources()

    def refresh_wallpaper_later(self, delay):
        if component_backdrop(self.dock.cfg,'panel')=='wallpaper' and self.isVisible():
            self.refresh_timer.start(delay)
        else:
            self.refresh_timer.stop()
            self.backdrop = None

    def capture_backdrop(self):
        if self.dock.preview or not self.isVisible() or self.runtime.game_active: return
        from appearance_presets import panel_appearance
        style = panel_appearance(self.dock.cfg)
        if not uses_wallpaper(component_backdrop(self.dock.cfg,'panel'),style):
            self.backdrop = None
            self.update()
            return
        from glass_capture import capture_behind,surface_windows,backdrop_key
        from liquid_glass import material_blur
        from glass_capture import smooth_backdrop
        blur=material_blur(style['blur'],style['material']) if style.get('blur_enabled',True) else 0
        key=backdrop_key(self,blur,style['material'])
        if key is not None and key==getattr(self,'_backdrop_key',None) and self.backdrop is not None:return
        image=capture_behind(self,surface_windows(self.dock))
        if image is not None:
            self.backdrop=smooth_backdrop(image,blur)
            self._backdrop_key=key
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        shape = QPainterPath()
        radius=self.surface_radius()
        shape.addRoundedRect(rect,radius,radius)
        if not self.collapsed and not self.option('locked'):
            paint_edge_targets(painter, self.rect())
        from appearance_presets import material_design, panel_appearance
        style = panel_appearance(self.dock.cfg)
        mode = component_backdrop(self.dock.cfg,'panel')
        wallpaper = uses_wallpaper(mode,style)
        colors = self.surface_colors(style)
        highlight = style['highlight']/45
        colors['border'].setAlpha(min(255, round(colors['border'].alpha()*highlight)))
        colors['spec'] = min(255, round(colors['spec']*highlight))
        stops = [(position, min(255, round(alpha*highlight))) for position, alpha in self.dock.merged_grad_stops(colors)]
        material = style['material']
        alpha = style['opacity']*2.55
        if material == 'clear': alpha = min(alpha, 55)
        if material == 'mica': alpha = max(alpha, 210)
        if material == 'solid': alpha = 255
        clear = self.is_clear(style)
        surface = SimpleNamespace(cfg={'glass': wallpaper, 'clear_background': clear,
                                       'dock_material': material, 'live_backdrop': mode=='dynamic'}, backdrop=self.backdrop if wallpaper else None,
                                  spec_x=self.spec_x, spec_alpha=self.spec_alpha)
        paint_liquid_glass(surface, painter, shape, rect, rect, colors, int(alpha), stops)
        from card_design import paint_design
        following = self.option('appearance_source') == 'app'
        design = material_design(material, 'aurora') if following else None
        design_cfg = {'theme_color': style['color']} if following else self.dock.cfg
        paint_design(painter,rect,design_cfg,design,clear=clear,
                     body_top=self.design_body_top(),body_inset=metric(4,self.ui_factor),corner_radius=radius)
        if self.option('face'):
            badge=getattr(self,'fold_badge',None)
            compact=badge is not None and badge.isVisible()
            center=QRectF(self.rect() if compact else self.header_icon.geometry()).center()
            slot=min(self.width()-12,self.height()-2,metric(42*self.option('face_scale')/100,self.ui_factor,24)) if compact else self.header_icon.width()
            from compact_colors import area_colors
            content=self.colors()
            area=QRectF(center.x()-slot/2,center.y()-slot/2,slot,slot)
            face=area_colors(self,area,dict(light=content['light'],ink=content['fg'].name()))
            self.face_tracker.paint_face(painter,center,slot,face)
        if getattr(self.manager,'drop_preview',None) is self:
            painter.setPen(QPen(self.palette().color(QPalette.Link),2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(shape)

    def surface_radius(self):
        if self.collapsed and self.option('collapse_style') in ('capsule','ball'):
            return min(self.width(), self.height())/2
        return 18*self.ui_factor

    def design_body_top(self):
        # Start the porcelain content surface below the entire live header/tab area.
        if self.collapsed:return self.height()
        return self.query.mapTo(self,self.query.rect().topLeft()).y()-metric(4,self.ui_factor)


    def is_clear(self, style=None):
        from appearance_presets import panel_appearance
        style = panel_appearance(self.dock.cfg) if style is None else style
        return style['material'] == 'clear' and style['opacity'] == 0 and style['highlight'] == 0

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            self.collapse_timer.stop()
            if self.collapsed: self.expand()
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event): self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if self.manager.add_paths(self.identity, paths):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else: event.ignore()

    def closeEvent(self, event):
        if self.disposed or QApplication.instance().isSavingSession() or getattr(self.runtime,'session_ending',False): event.accept()
        else:
            event.ignore()
            self.collapse()

    def dispose(self):
        self.face_tracker.hide_face()
        self.page_transition.cancel()
        self.disposed = True
        for timer in (self.refresh_timer, self.resize_timer, self.collapse_timer, self.expand_timer, self.fit_timer): timer.stop()
        self.backdrop = None
        self.close()
        self.deleteLater()


class PanelOptions(QDialog):
    def __init__(self,panel):
        super().__init__(panel,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        from ui_style import SettingsHeader
        from appearance_presets import APPEARANCE_SOURCES, material_choices, COLOR_MODES
        from resource_options import FACE_SWITCH_RANGE
        self.panel,self.fields=panel,{};self.applying_preset=True
        from component_settings import ComponentPages, settings_footer
        self.setWindowTitle('卡片外观设置 · 大肥鱼Dock');self.resize(650,500)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'卡片外观设置'))
        self.tabs=ComponentPages(self,body,'桌面卡片')
        form=self.tabs.form('材质与配色','palette','卡片外观')
        management=QHBoxLayout()
        self.groups_button=button('分组管理…',panel.manager.manage_groups)
        self.sizing_button=button('尺寸控制…',self.open_sizing)
        management.addWidget(self.groups_button)
        management.addWidget(self.sizing_button)
        management.addStretch()
        behavior=self.tabs.form('显示与交互','panels','卡片管理与层级')
        behavior.addRow(management)
        self.icon_alignment=ModernComboBox()
        for title,value in ICON_ALIGNMENTS:self.icon_alignment.addItem(title,value)
        self.icon_alignment.setAccessibleName('当前分类的图标对齐')
        self.icon_alignment.setCurrentIndex(self.icon_alignment.findData(panel.model.get('icon_alignment','center')))
        behavior.addRow('当前分类的图标对齐',self.icon_alignment)
        self.text_size=ModernSpinBox()
        self.text_size.setRange(8,48)
        form.addRow('卡片文字大小（像素）',self.text_size)
        def choice(key,title,options):
            field=ModernComboBox()
            for name,value in options:field.addItem(name,value)
            self.fields[key]=field;form.addRow(title,field)
        def number(key,title,low,high):
            field=ModernSpinBox();field.setRange(low,high);self.fields[key]=field;form.addRow(title,field)
        choice('appearance_source','外观来源',APPEARANCE_SOURCES)
        from appearance_presets import CONTENT_MODES
        choice('content_mode','文字与方块',CONTENT_MODES)
        choice('backdrop_mode','玻璃背景',BACKDROP_MODES)
        self.fields['backdrop_mode'].setToolTip(BACKDROP_HINT)
        self.preset=ModernComboBox();self.preset.addItem('自定义');self.preset.addItems([name for name,_ in PANEL_PRESETS]);form.addRow('主题预设',self.preset)
        choice('material','材质',material_choices(panel.option('material')));choice('theme','明暗模式',COLOR_MODES)
        self.color=QLineEdit();self.color.setPlaceholderText('默认色 / #RRGGBB');self.color_box=QWidget();colors=QVBoxLayout(self.color_box);colors.setContentsMargins(0,0,0,0);row=QHBoxLayout();row.addWidget(self.color,1);row.addWidget(button('选择',self.choose_color));colors.addLayout(row)
        from ui_style import ThemeSwatches
        colors.addWidget(ThemeSwatches(self.color));form.addRow('主题色',self.color_box)
        number('highlight','高光（%）',0,100);number('opacity','不透明度（%）',0,100);number('blur','模糊强度',0,30)
        form=behavior
        choice('layer','桌面卡片层级',[('置底','bottom'),('置顶','top')])
        from component_passthrough import CHOICES
        self.passthrough=ModernComboBox()
        for title,value in CHOICES:self.passthrough.addItem(title,value)
        self.passthrough.setAccessibleName('当前卡片的鼠标穿透')
        form.addRow('当前卡片的鼠标穿透',self.passthrough)
        from desktop_idle_fade import FadeCheckBox
        self.idle_fade=FadeCheckBox(panel.dock.cfg,panel.property('clickThroughKey'))
        form.addRow('当前卡片',self.idle_fade)
        self.locked=ModernCheckBox('锁定卡片位置与大小');form.addRow(self.locked)
        form=self.tabs.form('展开与收起','size','触发方式与尺寸')
        self.auto=ModernCheckBox('鼠标离开后自动收起');form.addRow(self.auto)
        choice('expand_mode','展开方式',[('鼠标移入','hover'),('点击展开','click')])
        choice('collapse_style','收起形状',[('胶囊','capsule'),('方条','bar'),('圆球','ball')]);number('capsule_ratio','胶囊宽度比例（%）',1,100)
        from panel_preferences import FOLD_SIZE_RANGE
        number('ball_diameter','圆球直径（像素）',*FOLD_SIZE_RANGE)
        number('fold_height','收起栏高度（像素）',*FOLD_SIZE_RANGE)
        self.fields['collapse_style'].currentIndexChanged.connect(self.sync_fold_fields)
        form=self.tabs.form('表情与角色','paw','表情与互动')
        self.face=ModernCheckBox('显示小表情（展开与收起均保留）');form.addRow(self.face)
        self.face_interactive=ModernCheckBox('表情跟随鼠标与按压互动');form.addRow(self.face_interactive)
        choice('face_mood','表情样式',[('随机变化','random'),('默认','default'),('开心','happy'),('眨眼','wink'),('爱心','love'),('星星眼','star'),('害羞','shy'),('嘟嘴','pout'),('眯眼','squint')])
        self.face_auto_switch = ModernCheckBox('定时切换表情')
        form.addRow(self.face_auto_switch)
        number('face_switch_minutes', '切换间隔（分钟）', *FACE_SWITCH_RANGE)
        self.face_auto_switch.toggled.connect(self.fields['face_switch_minutes'].setEnabled)
        number('face_scale','表情大小（%）',60,130)
        self.status=label('外观与收起设置由桌面卡片共用。','muted')
        self.status.setWordWrap(True)
        from face_role_controls import add_role_controls
        self.fields['face_role']=add_role_controls(self,form,panel.runtime,self.status,panel.option('face_role'))
        settings_footer(self,body,self.status,self.commit)
        self.refresh_shared()
        self.preset.currentIndexChanged.connect(self.apply_preset)
        for key,field in self.fields.items():
            if key in ('layer','backdrop_mode','content_mode'):continue
            signal=field.currentIndexChanged if isinstance(field,QComboBox) else field.valueChanged
            signal.connect(self.customized)
        self.color.textChanged.connect(self.customized);self.fields['material'].currentIndexChanged.connect(self.material_changed)
        self.fields['appearance_source'].currentIndexChanged.connect(self.sync_source)
        panel.manager.shared_settings_changed.connect(self.refresh_shared)
        self.setAttribute(Qt.WA_DeleteOnClose)
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,panel.dock.cfg)
    def refresh_shared(self):
        if self.panel.disposed:return
        self.applying_preset=True
        from card_metrics import normalize_profile
        self.text_size.setValue(normalize_profile(self.panel.dock.cfg.get('card_sizing'))['font_size'])
        from component_passthrough import individual
        pointer=individual(self.panel.dock.cfg,self.panel.property('clickThroughKey'))
        self.passthrough.setCurrentIndex(self.passthrough.findData(pointer))
        for key,field in self.fields.items():
            value=self.panel.option(key)
            if key=='material':
                from appearance_presets import select_material
                select_material(field,value)
            elif key=='face_role':field.select(value)
            elif isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
            else:field.setValue(value)
        self.color.setText(self.panel.option('color'));self.auto.setChecked(self.panel.option('auto_hide'));self.locked.setChecked(self.panel.option('locked'))
        self.face.setChecked(self.panel.option('face'));self.face_interactive.setChecked(self.panel.option('face_interactive'))
        self.face_auto_switch.setChecked(self.panel.option('face_auto_switch'))
        self.fields['face_switch_minutes'].setEnabled(self.face_auto_switch.isChecked())
        matching=next((i for i,(_,values) in enumerate(PANEL_PRESETS,1) if all(self.panel.option(key)==value for key,value in values.items())),0)
        self.preset.blockSignals(True);self.preset.setCurrentIndex(matching);self.preset.blockSignals(False)
        self.applying_preset=False
        self.sync_source()
        self.sync_fold_fields()

    def sync_fold_fields(self):
        shape = self.fields['collapse_style'].currentData()
        self.fields['ball_diameter'].setEnabled(shape == 'ball')
        self.fields['fold_height'].setEnabled(shape != 'ball')
        self.fields['capsule_ratio'].setEnabled(shape == 'capsule')

    def open_sizing(self):
        from card_metrics import normalize_profile
        panel=self.panel
        before=normalize_profile(panel.dock.cfg.get('card_sizing'))['font_size']
        panel.runtime.open_card_sizing('panel',panel.identity)
        current=normalize_profile(panel.dock.cfg.get('card_sizing'))['font_size']
        if current!=before:self.text_size.setValue(current)
    def sync_source(self):
        custom = self.fields['appearance_source'].currentData() == 'custom'
        self.preset.setEnabled(custom)
        self.color_box.setEnabled(custom)
        for key in ('material', 'theme', 'opacity', 'blur', 'highlight'):
            self.fields[key].setEnabled(custom)
    def material_changed(self):
        if not self.applying_preset and self.fields['material'].currentData()=='clear':
            self.fields['opacity'].setValue(0);self.fields['highlight'].setValue(0)
        if not self.applying_preset and self.fields['material'].currentData()!='clear' and self.fields['opacity'].value()==0 and self.fields['highlight'].value()==0:
            values=next(v for _,v in PANEL_PRESETS if v['material']=='crystal') if self.fields['material'].currentData()=='crystal' else dict(opacity=38,highlight=45,blur=6)
            self.fields['opacity'].setValue(values['opacity']);self.fields['highlight'].setValue(values['highlight'])
            if self.fields['material'].currentData()=='crystal':self.fields['blur'].setValue(values['blur'])
    def customized(self,*args):
        if not self.applying_preset:self.preset.setCurrentIndex(0)
    def apply_preset(self,index):
        if index<=0:return
        self.applying_preset=True
        for key,value in PANEL_PRESETS[index-1][1].items():
            if key=='color':self.color.setText(value)
            elif isinstance(self.fields[key],QComboBox):self.fields[key].setCurrentIndex(self.fields[key].findData(value))
            else:self.fields[key].setValue(value)
        self.applying_preset=False
    def choose_color(self):
        color=QColorDialog.getColor(QColor(self.color.text() or '#b8d9ef'),self,'选择卡片主题色')
        if color.isValid():self.color.setText(color.name())
    def commit(self):
        import re
        color=self.color.text().strip()
        if color and not re.fullmatch(r'#[0-9a-fA-F]{6}',color):self.status.setText('主题色请使用 #RRGGBB，或留空使用默认色。');return False
        values={key:field.currentData() if isinstance(field,QComboBox) else field.value() for key,field in self.fields.items()}
        values.update(color=color.lower(),auto_hide=self.auto.isChecked(),locked=self.locked.isChecked(),face=self.face.isChecked(),face_interactive=self.face_interactive.isChecked())
        values['face_auto_switch'] = self.face_auto_switch.isChecked()
        values['fold']={'style':values.pop('collapse_style'),'ratio':values.pop('capsule_ratio'),
                        'diameter':values.pop('ball_diameter'),'height':values.pop('fold_height')}
        if self.panel.manager.update_panel(self.panel.identity,_font_size=self.text_size.value(),icon_alignment=self.icon_alignment.currentData(),
                                           _pointer_mode=self.passthrough.currentData(),_fade_changes=self.idle_fade.changes(self.panel.dock.cfg),**values):
            self.idle_fade.saved=self.idle_fade.isChecked()
            self.status.setText('已保存。外观和层级应用到所有桌面卡片。');return True
        self.status.setText('保存失败，原设置保持不变，可重试。');return False
