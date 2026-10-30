from ui_style import compact_dialog
"""Floating desktop collection windows using the original Dock liquid glass."""
import ctypes
import os
from ctypes import wintypes
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QTimer, QSize, QRectF, QMimeData, QUrl
from PyQt5.QtGui import QPainter, QPainterPath, QIcon, QDrag, QCursor, QColor, QPalette, QPixmap, QPen, QKeySequence
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QSizeGrip, QApplication,
    QMenu, QInputDialog, QFileDialog, QFormLayout, QSpinBox, QComboBox, QCheckBox, QLayout, QColorDialog, QSizePolicy, QTabBar)
from ui_style import AlignedMenu as QMenu
from app_catalog import path_key
from liquid_glass import paint_liquid_glass, tint_palette
from appearance_presets import PANEL_PRESETS
from ui_style import label, button, ModernComboBox, ModernSpinBox, ModernCheckBox
from dpi_support import metric, minimum, panel_css


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
                panel.dock.icons.clear();panel.manager.schedule_scan();panel.render();event.accept();return
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
        self.setMovable(True)
        self.setDrawBase(False)
        self.setToolTip('拖动分组栏目调整顺序，自动保存；点击切换分组')
        self.tabMoved.connect(self.save_order)

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.pressing = True
            self.update()
            self.pressed_identity = self.tabData(self.tabAt(event.pos()))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        identity = self.pressed_identity
        super().mouseReleaseEvent(event)
        if event.button()==Qt.LeftButton:
            self.pressing = False
            self.update()
            self.pressed_identity = None
            index = next((i for i in range(self.count()) if self.tabData(i)==identity),self.currentIndex())
            self.panel.select_tab(index)

    def hideEvent(self, event):
        self.pressing = False
        self.pressed_identity = None
        super().hideEvent(event)

    def save_order(self, source, destination):
        order = [self.tabData(index) for index in range(self.count())]
        if not self.panel.manager.reorder_panels(order):
            self.panel.update_tabs(self.panel.manager.merged_models(self.panel.identity))


class DesktopPanel(QDialog):
    def __init__(self, manager, identity, geometry):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.manager, self.runtime, self.dock = manager, manager.runtime, manager.dock
        self.identity, self.default_geometry = identity, list(geometry)
        self.default_ui_factor=geometry[2]/320 if not self.model.get('geometry') else 1.0
        self.ui_factor = 1.0
        self.disposed = False
        self.restoring = True
        self.collapsed = False
        self.manual_resize = False
        self.merged_view = self.manager.is_merged(self.identity)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_content)
        self.drag_origin = None
        self.dragged = False
        self.backdrop = None
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
        self.list.setMovement(QListWidget.Static)
        self.list.setIconSize(QSize(34, 34))
        self.list.setGridSize(QSize(78, 78))
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setWordWrap(True)
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
        footer = self.footer = QHBoxLayout()
        self.notice = label('拖入文件、文件夹或快捷方式', 'muted')
        self.notice.setObjectName('PanelLabel')
        self.notice.setStyleSheet('font-size:11px;')
        footer.addWidget(self.notice, 1)
        from ui_style import SubtleSizeGrip
        self.grip = SubtleSizeGrip(self,lambda:self.colors().get('light',True))
        footer.addWidget(self.grip)
        content.addLayout(footer)
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
        # Never rebuild the bar being dragged; its order already matches the saved model.
        if current != expected:
            while self.tabs.count(): self.tabs.removeTab(0)
            for identity,name in expected:
                index = self.tabs.addTab(name)
                self.tabs.setTabData(index, identity)
        for index,(identity,name) in enumerate(expected):
            if identity==self.identity and not self.tabs.pressing and self.tabs.currentIndex()!=index: self.tabs.setCurrentIndex(index)
        self.update_tab_icons()
        self.tabs.setVisible(self.manager.is_merged(self.identity))
        self.tabs.blockSignals(False)

    def update_tab_icons(self):
        size=metric(15,self.ui_factor,11);light=self.colors()['light'];dpr=self.devicePixelRatioF()
        signature=(size,light,dpr,tuple(self.tabs.tabData(i) for i in range(self.tabs.count())))
        if signature==getattr(self,'_tab_icon_signature',None):return
        self._tab_icon_signature=signature
        self.tabs.setIconSize(QSize(size,size))
        for index in range(self.tabs.count()):
            identity=self.tabs.tabData(index)
            self.tabs.setTabIcon(index,QIcon(category_icon(identity,category_color(identity,light),size,dpr)))
            self.tabs.setTabToolTip(index,self.tabs.tabText(index))

    def page_state(self):
        return (self.query.text(),self.selected_keys(),self.list.verticalScrollBar().value())

    def restore_page_state(self,state):
        query,selected,scroll=state
        self.query.blockSignals(True);self.query.setText(query);self.query.blockSignals(False)
        self.list.clearSelection();self._released_selection=set(selected)
        self.render();self.list.doItemsLayout();self.list.verticalScrollBar().setValue(scroll)

    def select_tab(self, index):
        if self.tabs.pressing: return
        identity = self.tabs.tabData(index)
        if identity and identity!=self.identity:
            self.manager.select_page(identity)
            if self.manager.active_for(identity)!=identity: self.update_tabs(self.manager.merged_models(identity))

    @property
    def model(self): return self.manager.model(self.identity)

    def option(self, key):
        if key in ('collapse_style','capsule_ratio'):
            from fold_options import settings
            return settings(self)['style' if key=='collapse_style' else 'ratio']
        return self.dock.cfg['panel_'+key]

    def colors(self):
        theme = self.option('theme')
        color = self.option('color')
        if theme == 'follow':
            theme = None
            color = color or self.dock.cfg.get('theme_color', '')
        if self.dock.cfg.get('card_design') in ('gradient','paper','minimal'):theme='light'
        from liquid_glass import material_palette
        return material_palette(tint_palette(self.dock.base_theme_colors(theme), color), self.option('material'))

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
        self.footer.setSpacing(metric(4,factor))
        self.grip.setFixedSize(metric(12,factor,6),metric(12,factor,6))
        self.notice.setStyleSheet('font-size:%dpx;'%metric(11,factor,6))
        view = self.model.get('view','small')
        self.list.setViewMode(QListWidget.ListMode if view=='list' else QListWidget.IconMode)
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
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWindowTitle(self.model['name']+' · 桌面收纳')
        self.grip.setVisible(not self.option('locked'))
        # Use min/max constraints as well as hiding the grip: native resize is locked too.
        if self.collapsed:
            self.set_collapsed_geometry(True)
        else:
            self.setMinimumSize(1,1)
            self.setMaximumSize(16777215,16777215)
            self.setMinimumSize(min(minimum(factor)[0],self.width()),min(minimum(factor)[1],self.height()))
            if self.option('locked'):self.setFixedSize(self.size())
        colors = self.colors()
        ink = colors['fg'].name()
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
            QTabBar#PanelTabs::tab {padding:4px 8px;margin:1px 3px 2px 0;border:1px solid transparent;border-radius:7px;background:transparent;font-weight:600;}
            QTabBar#PanelTabs::tab:hover {background:%s;}
            QTabBar#PanelTabs::tab:selected {background:%s;border:1px solid rgba(255,255,255,110);font-weight:600;}
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
        self.count.setStyleSheet(panel_css('padding:1px 5px;border-radius:5px;background:rgba(128,128,128,16);',factor))
        self.settings_button.setIcon(QIcon(category_icon('settings',ink,metric(16,factor,12),self.devicePixelRatioF())));self.settings_button.setIconSize(QSize(metric(16,factor,12),metric(16,factor,12)))
        for control in (self.settings_button,self.menu_button,self.collapse_button):control.setFixedSize(metric(24,factor,16),metric(24,factor,16))
        palette = self.query.palette()
        palette.setColor(QPalette.PlaceholderText, QColor('#5c626c' if colors['light'] else '#b4b8c0'))
        self.query.setPalette(palette)
        height=self.list.fontMetrics().height();icon=self.list.iconSize().height()
        if view!='list':
            grid=self.list.gridSize();self.list.setGridSize(QSize(grid.width(),max(grid.height(),icon+height*3+metric(12,factor))))
        self.render()
        self.refresh_timer.start(100)
        self.update()

    def update_identity_header(self):
        self.setWindowTitle(self.model['name']+' · 桌面收纳')
        size=metric(17,self.ui_factor,12);self.header_icon.setFixedSize(size,size)
        self.header_icon.setPixmap(category_icon(self.identity,category_color(self.identity,self.colors()['light']),size,self.devicePixelRatioF()))

    def text_pixels(self):
        from card_metrics import font_pixels
        return font_pixels(self.dock.cfg,self.ui_factor)

    def visible_items(self):
        query = self.query.text().strip().casefold()
        return [row for row in self.manager.rows(self.identity)
                if query in row['name'].casefold() or query in row['path'].casefold()]

    def render(self, *args):
        rows = self.visible_items()
        if self.collapsed and self.runtime.lite:
            self._released_selection = self.selected_keys() | getattr(self, '_released_selection', set())
            self.list.clear()
            self.title.setText(self.model['name'])
            self.count.setText(str(len(self.manager.rows(self.identity))))
            return
        scroll = self.list.verticalScrollBar().value()
        selected = {path_key(item.data(Qt.UserRole)['path']) for item in self.list.selectedItems()}
        selected |= getattr(self, '_released_selection', set())
        self._released_selection = set()
        self.list.clear()
        from card_file_ui import card_display_name
        icon_view=self.list.viewMode()==QListWidget.IconMode
        for row in rows:
            from card_file_ui import picture_thumbnail
            pixels=max(24,self.list.iconSize().width());thumbnail=picture_thumbnail(row['path'],pixels)
            item = QListWidgetItem(QIcon(thumbnail if thumbnail is not None else self.dock.icons.get(row['path'],pixels,shell_state=True,hide_shortcut=icon_view)),card_display_name(row,icon_view))
            item.setToolTip(('已置顶 · ' if row.get('pinned') else '')+row['path'])
            item.setData(Qt.UserRole, row)
            self.list.addItem(item)
            item.setSelected(path_key(row['path']) in selected)
        self.list.verticalScrollBar().setValue(scroll)
        self.title.setText(self.model['name'])
        self.count.setText(str(len(self.manager.rows(self.identity))))
        self.notice.setText(self.manager.message or ('拖入文件、文件夹或快捷方式' if rows else '拖入内容，或等待桌面自动分类'))
        self.fit_timer.start(0)

    def fit_content(self):
        # Preserve freely chosen dimensions, including when merged pages switch.
        self.list.doItemsLayout()

    def set_compact(self, enabled):
        self.manual_resize = False
        if self.manager.is_merged(self.identity): self.manager.update_group(self.identity,compact=enabled)
        if not enabled: self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
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
            if result=='shell':self.manager.schedule_scan()
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
        commands.append(('显示方式',views));commands.append(('粘贴到桌面',lambda:self.paste_files()))
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
        menu.addAction('收起样式…').triggered.connect(lambda:FoldOptions(self).exec_())
        menu.addAction('尺寸与文字…').triggered.connect(lambda: self.runtime.open_card_sizing('panel',self.identity))
        menu.addAction('粘贴到桌面').triggered.connect(lambda:self.paste_files())
        menu.addAction('添加文件…').triggered.connect(self.add_files)
        menu.addAction('添加文件夹…').triggered.connect(self.add_folder)
        menu.addAction('分组与合并管理…').triggered.connect(self.manager.manage_groups)
        merge = menu.addAction('独立显示此卡片' if self.manager.is_merged(self.identity) else '加入合并卡片')
        merge.triggered.connect(lambda: self.manager.set_merged(self.identity, not self.manager.is_merged(self.identity)))
        groups=menu.addMenu('加入合并组')
        for group in self.dock.cfg['merge_groups']:
            action=groups.addAction(group['name']);action.setCheckable(True)
            action.setChecked(self.manager.is_merged(self.identity) and self.manager.group_id(self.identity)==group['id'])
            action.triggered.connect(lambda checked=False,key=group['id']:self.manager.assign_group(self.identity,key))
        groups.addSeparator();groups.addAction('新建合并组…').triggered.connect(lambda:self.manager.new_merge_group(identity=self.identity))
        if self.identity not in dict(__import__('desktop_catalog').CATEGORIES):
            menu.addAction('自动归入格式…').triggered.connect(self.edit_definition)
        menu.addAction('设置…').triggered.connect(self.runtime.show_settings)
        menu.addAction('新建面板…').triggered.connect(lambda: self.manager.new_panel())
        menu.addAction('重命名…').triggered.connect(self.rename)
        menu.addAction('外观与收起…').triggered.connect(self.edit_options)
        self.add_view_menu(menu)
        sort = menu.addMenu('排序方式')
        for key, title in [('name_asc','文件名：升序'), ('name_desc','文件名：降序'),
                           ('modified_desc','修改时间：最新优先'), ('modified_asc','修改时间：最早优先')]:
            action = sort.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.model.get('sort', 'name_asc') == key)
            action.triggered.connect(lambda checked=False, value=key: self.manager.update_panel(self.identity, sort=value))
        lock = menu.addAction('锁定位置和大小')
        lock.setCheckable(True)
        lock.setChecked(self.option('locked'))
        lock.triggered.connect(lambda checked: self.manager.update_panel(self.identity, locked=checked))
        menu.addSeparator()
        menu.addAction('重新扫描桌面').triggered.connect(self.manager.scan)
        menu.addAction('移除此面板…').triggered.connect(lambda: self.manager.delete_panel(self.identity))
        return menu

    def edit_definition(self):
        from panel_management import PanelDefinition
        dialog = PanelDefinition(self.model, self)
        if dialog.exec_()==dialog.Accepted:
            self.manager.update_panel(self.identity, name=dialog.name.text().strip(), extensions=dialog.extensions())
            self.manager.schedule_scan()

    def rename(self):
        name, okay = QInputDialog.getText(self, '重命名面板', '面板名称：', text=self.model['name'])
        if okay and name.strip(): self.manager.update_panel(self.identity, name=name.strip()[:40])

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '收纳文件（保留原位）')
        self.manager.add_paths(self.identity, paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, '收纳文件夹（保留原位）')
        if path: self.manager.add_paths(self.identity, [path])

    def edit_options(self):
        dialog = PanelOptions(self)
        dialog.exec_()
        if self.option('auto_hide'): self.collapse_timer.start()

    def bounds(self):
        raw=(self.manager.group_value(self.identity,'geometry') if self.manager.is_merged(self.identity) and self.manager.group_value(self.identity,'geometry')
             else self.model.get('geometry',self.default_geometry))
        layout=getattr(self.runtime,'layout',None)
        if layout:return layout.panel_bounds(self.identity,raw)
        from card_metrics import metrics
        from screen_layout import screen_records
        return metrics(self.dock.cfg,list(raw),screen_records())[0]

    def set_collapsed_geometry(self, collapsed):
        self.restoring = True
        self.collapsed = collapsed
        self.content.setVisible(not collapsed)
        self.setMinimumSize(1, 1)
        self.setMaximumSize(16777215, 16777215)
        geometry = self.bounds()
        self.move(geometry[0], geometry[1])
        if collapsed:
            from fold_options import geometry as fold_geometry,settings
            target=fold_geometry(geometry,settings(self),metric(44,self.ui_factor,24))
            self.setFixedSize(target[2],target[3]);self.move(*target[:2]);self._fold_offset=(target[0]-geometry[0],target[1]-geometry[1])
        else:
            screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
            available = screen.availableGeometry()
            self.resize(min(geometry[2], available.width()), min(geometry[3], available.height()))
            self.move(max(available.left(), min(self.x(), available.right()+1-self.width())),
                      max(available.top(), min(self.y(), available.bottom()+1-self.height())))
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
        self.backdrop = None
        self.refresh_timer.start(100)
        self.update()

    def collapse(self):
        if self.disposed or self.collapsed: return
        self.store_geometry()
        if self.manager.update_panel(self.identity, collapsed=True): self.set_collapsed_geometry(True)

    def expand(self):
        if self.disposed or not self.collapsed: return
        if self.runtime.lite: self.runtime.set_lite(False)
        if self.manager.update_panel(self.identity, collapsed=False): self.set_collapsed_geometry(False)
        self.runtime.arm_lite()

    def toggle_collapse(self):
        if self.collapsed: self.expand()
        else: self.collapse()

    def collapse_if_outside(self):
        if self.option('auto_hide') and self.isVisible() and not self.rect().contains(self.mapFromGlobal(QCursor.pos())) and not QApplication.activePopupWidget():
            active = QApplication.activeWindow()
            if active and active is not self and self.isAncestorOf(active): return
            self.collapse()

    def expand_if_inside(self):
        if self.isVisible() and self.underMouse(): self.expand()

    def enterEvent(self, event):
        self.collapse_timer.stop()
        if self.collapsed: self.expand_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.expand_timer.stop()
        self.spec_alpha = 0
        self.update()
        if self.option('auto_hide'): self.collapse_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= 44 and not self.option('locked'):
            self.drag_origin = event.globalPos()-self.pos()
            self.dragged = False
            event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.spec_x, self.spec_alpha = event.pos().x(), .7
        self.update()
        if self.drag_origin is not None and event.buttons() & Qt.LeftButton:
            self.dragged = True
            self.move(event.globalPos()-self.drag_origin)
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_origin is not None:
            self.drag_origin = None
            self.store_geometry()
            if self.collapsed and not self.dragged: self.expand()
        super().mouseReleaseEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.restoring: self.resize_timer.start(250)

    def resizeEvent(self, event):
        if hasattr(self,'page_transition'):self.page_transition.cancel()
        super().resizeEvent(event)
        if not self.restoring:
            if not self.collapsed and event.oldSize().isValid(): self.manual_resize = True
            self.resize_timer.start(250)
            self.refresh_timer.start(200)

    def store_geometry(self):
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
            if any(self.dock.cfg.get(key)!=value for key,value in changes.items()) and not self.manager.commit(**changes):return
            self.manual_resize = False
            self._layout_geometry=self.geometry().getRect()
            return
        changes = {'geometry': geometry}
        if self.manual_resize:
            changes['compact'] = False
            self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        if anchor is not None or any(self.model.get(key) != value for key, value in changes.items()):
            if self.manager.update_panel(self.identity, _layout=anchor if anchor is not None else False, **changes):
                self.manual_resize = False
                self._layout_geometry=self.geometry().getRect()

    def showEvent(self, event):
        super().showEvent(event)
        self.attach_desktop()
        self.fit_timer.start(0)
        self.refresh_timer.start(100)
        if self.option('auto_hide'): self.collapse_timer.start()

    def attach_desktop(self, owner=None):
        # Desktop-owned tool window: no taskbar entry and no always-on-top flag.
        # Ownership changes only our HWND, never taskbar/desktop styles or files.
        if owner is not None or (not self.dock.preview and not os.environ.get('FISHDOCK_TEST_DESKTOP')):
            user = ctypes.windll.user32
            user.GetShellWindow.restype = wintypes.HWND
            owner = owner if owner is not None else user.GetShellWindow()
            if owner:
                user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
                user.SetWindowLongPtrW(int(self.winId()), -8, int(owner))
                user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
                user.SetWindowPos(int(self.winId()),1,0,0,0,0,0x13)

    def hideEvent(self, event):
        self.page_transition.cancel()
        if not self.disposed and not self.restoring: self.store_geometry()
        for timer in (self.refresh_timer, self.resize_timer, self.collapse_timer, self.expand_timer, self.fit_timer): timer.stop()
        self.backdrop = None
        super().hideEvent(event)

    def capture_backdrop(self):
        if self.dock.preview or not self.isVisible() or self.runtime.lite or self.runtime.game_active: return
        self.backdrop = None
        if self.option('material') in ('solid', 'clear'):
            self.update()
            return
        from glass_capture import capture_behind,surface_windows
        image=capture_behind(self,surface_windows(self.dock))
        if image is not None:
            from liquid_glass import material_blur
            from glass_capture import smooth_backdrop
            self.backdrop=smooth_backdrop(image,material_blur(self.option('blur'),self.option('material')))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        shape = QPainterPath()
        radius=self.surface_radius()
        shape.addRoundedRect(rect,radius,radius)
        colors = self.colors()
        highlight = self.option('highlight')/45
        colors['border'].setAlpha(min(255, round(colors['border'].alpha()*highlight)))
        colors['spec'] = min(255, round(colors['spec']*highlight))
        stops = [(position, min(255, round(alpha*highlight))) for position, alpha in self.dock.merged_grad_stops(colors)]
        material = self.option('material')
        alpha = self.option('opacity')*2.55
        if material == 'clear': alpha = min(alpha, 55)
        if material == 'mica': alpha = max(alpha, 210)
        if material == 'solid': alpha = 255
        surface = SimpleNamespace(cfg={'glass': material not in ('clear','solid'), 'clear_background': self.is_clear(), 'dock_material': material}, backdrop=self.backdrop,
                                  spec_x=self.spec_x, spec_alpha=self.spec_alpha)
        paint_liquid_glass(surface, painter, shape, rect, rect, colors, int(alpha), stops)
        from card_design import paint_design
        paint_design(painter,rect,self.dock.cfg,clear=self.is_clear(),
                     body_top=self.design_body_top(),body_inset=metric(4,self.ui_factor),corner_radius=radius)

    def surface_radius(self):
        return (22 if self.collapsed and self.option('collapse_style') in ('capsule','ball') else 18)*self.ui_factor

    def design_body_top(self):
        # Start the porcelain content surface below the entire live header/tab area.
        if self.collapsed:return self.height()
        return self.query.mapTo(self,self.query.rect().topLeft()).y()-metric(4,self.ui_factor)


    def is_clear(self):
        return self.option('material') == 'clear' and self.option('opacity') == 0 and self.option('highlight') == 0

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
        if self.disposed or QApplication.instance().isSavingSession(): event.accept()
        else:
            event.ignore()
            self.collapse()

    def dispose(self):
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
        from appearance_presets import MATERIALS,COLOR_MODES
        self.panel,self.fields=panel,{};self.applying_preset=True
        self.setWindowTitle('卡片外观设置 · 大肥鱼Dock');self.resize(540,620)
        body=QVBoxLayout(self);body.addWidget(SettingsHeader(self,'卡片外观设置'));form=QFormLayout();form.setVerticalSpacing(10);body.addLayout(form)
        self.preset=ModernComboBox();self.preset.addItem('自定义 / 保留当前设置');self.preset.addItems([name for name,_ in PANEL_PRESETS]);form.addRow('外观预设',self.preset)
        def choice(key,title,options):
            field=ModernComboBox()
            for name,value in options:field.addItem(name,value)
            self.fields[key]=field;form.addRow(title,field)
        def number(key,title,low,high):
            field=ModernSpinBox();field.setRange(low,high);self.fields[key]=field;form.addRow(title,field)
        choice('material','材质',MATERIALS);choice('theme','颜色模式',COLOR_MODES)
        self.color=QLineEdit();self.color.setPlaceholderText('默认色 / #RRGGBB');colors=QVBoxLayout();row=QHBoxLayout();row.addWidget(self.color,1);row.addWidget(button('选择',self.choose_color));colors.addLayout(row)
        from ui_style import ThemeSwatches
        colors.addWidget(ThemeSwatches(self.color));form.addRow('主题色',colors)
        number('highlight','高光（%）',0,100);number('opacity','不透明度（%）',0,100);number('blur','模糊强度',2,30)
        self.locked=ModernCheckBox('锁定卡片位置与大小');form.addRow(self.locked)
        self.auto=ModernCheckBox('鼠标离开后自动收起');form.addRow(self.auto)
        choice('collapse_style','收起形状',[('胶囊','capsule'),('方条','bar'),('圆球','ball')]);number('capsule_ratio','胶囊宽度比例（%）',1,100)
        self.status=label('所有桌面卡片共用此设置；保存后同步主设置。位置、大小和内容分别保留。','muted');body.addWidget(self.status)
        actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',self.reject));actions.addWidget(button('保存设置',self.commit,'primary'));body.addLayout(actions)
        self.refresh_shared()
        self.preset.currentIndexChanged.connect(self.apply_preset)
        for field in self.fields.values():
            signal=field.currentIndexChanged if isinstance(field,QComboBox) else field.valueChanged
            signal.connect(self.customized)
        self.color.textChanged.connect(self.customized);self.fields['material'].currentIndexChanged.connect(self.material_changed)
        panel.manager.shared_settings_changed.connect(self.refresh_shared)
        self.setAttribute(Qt.WA_DeleteOnClose)
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self,panel.dock.cfg)
    def refresh_shared(self):
        if self.panel.disposed:return
        self.applying_preset=True
        for key,field in self.fields.items():
            value=self.panel.option(key)
            if isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
            else:field.setValue(value)
        self.color.setText(self.panel.option('color'));self.auto.setChecked(self.panel.option('auto_hide'));self.locked.setChecked(self.panel.option('locked'))
        matching=next((i for i,(_,values) in enumerate(PANEL_PRESETS,1) if all(self.panel.option(key)==value for key,value in values.items())),0)
        self.preset.blockSignals(True);self.preset.setCurrentIndex(matching);self.preset.blockSignals(False)
        self.applying_preset=False
    def material_changed(self):
        if not self.applying_preset and self.fields['material'].currentData()!='clear' and self.fields['opacity'].value()==0 and self.fields['highlight'].value()==0:
            self.fields['opacity'].setValue(38);self.fields['highlight'].setValue(45)
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
        values.update(color=color.lower(),auto_hide=self.auto.isChecked(),locked=self.locked.isChecked())
        values['fold']={'style':values.pop('collapse_style'),'ratio':values.pop('capsule_ratio')}
        if self.panel.manager.update_panel(self.panel.identity,**values):self.status.setText('已保存：外观共用，收起样式仅用于当前卡片或合并组。');return True
        self.status.setText('保存失败，原设置保持不变，可重试。');return False
