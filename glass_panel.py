from ui_style import compact_dialog
"""Floating desktop collection windows using the original Dock liquid glass."""
import ctypes
import os
from ctypes import wintypes
from types import SimpleNamespace
from PyQt5.QtCore import Qt, QTimer, QSize, QRectF, QMimeData, QUrl
from PyQt5.QtGui import QPainter, QPainterPath, QIcon, QDrag, QCursor, QColor, QPalette
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QSizeGrip, QApplication,
    QMenu, QInputDialog, QFileDialog, QFormLayout, QSpinBox, QComboBox, QCheckBox, QLayout, QColorDialog, QSizePolicy, QTabBar)
from ui_style import AlignedMenu as QMenu
from app_catalog import path_key
from liquid_glass import paint_liquid_glass, tint_palette
from appearance_presets import PANEL_PRESETS
from ui_style import label, button, ModernComboBox, ModernSpinBox, ModernCheckBox
from dpi_support import metric, minimum, panel_css


class CollectionList(QListWidget):
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
        self.setToolTip('拖动分组栏目调整顺序，自动保存；点击切换分组')
        self.tabMoved.connect(self.save_order)

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.pressing = True
            self.pressed_identity = self.tabData(self.tabAt(event.pos()))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        identity = self.pressed_identity
        super().mouseReleaseEvent(event)
        if event.button()==Qt.LeftButton:
            self.pressing = False
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
            self.panel.update_tabs(self.panel.manager.merged_models())


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
        self.title = label('')
        self.title.setObjectName('PanelLabel')
        self.title.setStyleSheet('font-weight:600;')
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.count = label('')
        self.count.setObjectName('PanelLabel')
        self.count.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(self.title, 1)
        header.addWidget(self.count)
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
        self.list.setWordWrap(False)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(False)
        self.list.viewport().setAcceptDrops(False)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.item_menu)
        self.list.itemDoubleClicked.connect(self.launch_item)
        content.addWidget(self.list, 1)
        footer = self.footer = QHBoxLayout()
        self.notice = label('拖入文件、文件夹或快捷方式', 'muted')
        self.notice.setObjectName('PanelLabel')
        self.notice.setStyleSheet('font-size:11px;')
        footer.addWidget(self.notice, 1)
        self.grip = QSizeGrip(self)
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
            if identity==self.identity and not self.tabs.pressing: self.tabs.setCurrentIndex(index)
        self.tabs.setVisible(self.manager.is_merged(self.identity))
        self.tabs.blockSignals(False)

    def select_tab(self, index):
        if self.tabs.pressing: return
        identity = self.tabs.tabData(index)
        if identity and identity!=self.identity:
            self.manager.select_page(identity)
            if self.manager.active_window!=identity: self.update_tabs(self.manager.merged_models())

    @property
    def model(self): return self.manager.model(self.identity)

    def option(self, key):
        return self.model.get(key, self.dock.cfg['panel_'+key])

    def colors(self):
        theme = self.option('theme')
        color = self.option('color')
        if theme == 'follow':
            theme = None
            color = color or self.dock.cfg.get('theme_color', '')
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
        self.header_layout.setSpacing(metric(4,factor))
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
        self.list.setGridSize(QSize() if view=='list' else QSize(metric(108,factor),metric(102,factor)) if view=='large' else QSize(metric(78,factor),metric(78,factor)))
        self.list.setSpacing(0)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWindowTitle(self.model['name']+' · 桌面收纳')
        self.grip.setVisible(False)
        # Use min/max constraints as well as hiding the grip: native resize is locked too.
        if self.collapsed:
            self.set_collapsed_geometry(True)
        else:
            self.setMinimumSize(1,1)
            self.setMaximumSize(16777215,16777215)
            bounds=self.bounds();self.resize(bounds[2],bounds[3]);self.setFixedSize(self.size())
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
        palette = self.query.palette()
        palette.setColor(QPalette.PlaceholderText, QColor('#5c626c' if colors['light'] else '#b4b8c0'))
        self.query.setPalette(palette)
        height=self.list.fontMetrics().height();icon=self.list.iconSize().height()
        if view!='list':
            grid=self.list.gridSize();self.list.setGridSize(QSize(grid.width(),max(grid.height(),icon+height*2+metric(6,factor))))
        self.render()
        self.refresh_timer.start(100)
        self.update()

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
        for row in rows:
            item = QListWidgetItem(QIcon(self.dock.icons.get(row['path'], 64)), row['name'])
            if self.model.get('view')=='list': item.setSizeHint(QSize(metric(80,self.ui_factor),max(metric(34,self.ui_factor,18),self.list.fontMetrics().height()+metric(8,self.ui_factor),self.list.iconSize().height()+metric(6,self.ui_factor))))
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
        return  # Width and height are shared by every card.
        # Fit the full collection, so filtering never moves the window under the cursor.
        if (self.disposed or self.collapsed or self.restoring or self.manual_resize
                or self.option('locked') or not (self.dock.cfg['merged_compact'] if self.manager.is_merged(self.identity) else self.model.get('compact', True))):
            return
        self.layout().activate()
        grid = self.list.gridSize()
        list_view = self.model.get('view')=='list'
        if list_view: grid = QSize(max(1,self.list.width()),max(metric(34,self.ui_factor,18),self.list.fontMetrics().height()+metric(8,self.ui_factor),self.list.iconSize().height()+metric(6,self.ui_factor)))
        available = (QApplication.screenAt(self.pos()) or QApplication.primaryScreen()).availableGeometry()
        limit = min(available.height(), max(240, self.bounds()[3]))
        margins = self.layout().contentsMargins()
        chrome = (margins.top()+margins.bottom()+self.layout().itemAt(0).sizeHint().height()
                  + self.layout().spacing()+self.query.sizeHint().height()
                  + self.footer.sizeHint().height()+2*self.content.layout().spacing())
        if self.manager.is_merged(self.identity): chrome += self.tabs.sizeHint().height()+self.content.layout().spacing()
        width = self.list.contentsRect().width()
        count = max(1, len(self.manager.rows(self.identity)))
        columns = 1 if list_view else max(1, width//grid.width())
        height = chrome + ((count+columns-1)//columns)*grid.height()+2
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if height > limit else Qt.ScrollBarAlwaysOff)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if height > limit:
            width -= self.style().pixelMetric(self.style().PM_ScrollBarExtent)
            columns = 1 if list_view else max(1, width//grid.width())
            height = chrome + ((count+columns-1)//columns)*grid.height()+2
        height = max(min(minimum(self.ui_factor)[1],available.height()), min(limit, height))
        if height != self.height():
            self.restoring = True
            self.resize(self.width(), height)
            self.move(self.x(), max(available.top(), min(self.y(), available.bottom()+1-height)))
            self.restoring = False
            self.backdrop = None
            self.refresh_timer.start(100)
        self._layout_geometry=self.geometry().getRect()
        self.list.doItemsLayout()

    def set_compact(self, enabled):
        self.manual_resize = False
        if self.manager.is_merged(self.identity): self.manager.commit(merged_compact=enabled)
        if not enabled: self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        if self.manager.update_panel(self.identity, compact=enabled): self.fit_timer.start(0)

    def selected_keys(self):
        return {path_key(item.data(Qt.UserRole)['path']) for item in self.list.selectedItems()}

    def launch_item(self, item):
        path = item.data(Qt.UserRole)['path']
        if not os.path.exists(path):
            self.notice.setText('原文件已移动或不存在，请重新拖入。')
            return
        self.dock.launch(path)

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
        menu = self.build_item_menu()
        menu.exec_(self.list.viewport().mapToGlobal(point))
        menu.deleteLater()
        if self.option('auto_hide'): self.collapse_timer.start()

    def build_item_menu(self):
        menu = QMenu(self)
        keys = self.selected_keys()
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
        menu.addAction('统一尺寸与文字…').triggered.connect(lambda: self.runtime.open_card_sizing('panel',self.identity))
        menu.addAction('添加文件…').triggered.connect(self.add_files)
        menu.addAction('添加文件夹…').triggered.connect(self.add_folder)
        menu.addAction('分组与合并管理…').triggered.connect(self.manager.manage_groups)
        merge = menu.addAction('独立显示此卡片' if self.manager.is_merged(self.identity) else '加入合并卡片')
        merge.triggered.connect(lambda: self.manager.set_merged(self.identity, not self.manager.is_merged(self.identity)))
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
        raw=(self.dock.cfg['merged_geometry'] if self.manager.is_merged(self.identity) and self.dock.cfg.get('merged_geometry')
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
            width = geometry[2] if self.option('collapse_style') == 'bar' else max(metric(180,self.ui_factor,100), round(geometry[2]*self.option('capsule_ratio')/100))
            screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
            self.setFixedSize(min(width, screen.availableGeometry().width()), metric(44,self.ui_factor,24))
        else:
            screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
            available = screen.availableGeometry()
            self.resize(min(geometry[2], available.width()), min(geometry[3], available.height()))
            self.move(max(available.left(), min(self.x(), available.right()+1-self.width())),
                      max(available.top(), min(self.y(), available.bottom()+1-self.height())))
            self.setMinimumSize(min(minimum(self.ui_factor)[0],geometry[2],available.width()), min(minimum(self.ui_factor)[1],geometry[3],available.height()))
            self.setFixedSize(self.size())
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        self.move(max(available.left(), min(self.x(), available.right()+1-self.width())),
                  max(available.top(), min(self.y(), available.bottom()+1-self.height())))
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
        if self.merged_view and self.manager.active_window != self.identity: return
        geometry = self.bounds()
        geometry[0:2] = [self.x(), self.y()]
        if not self.collapsed: geometry[2:4] = [self.width(), self.height()]
        changed=self.geometry().getRect()!=getattr(self,'_layout_geometry',None)
        anchor=layout.panel_update(self.identity,geometry) if layout and (changed or not layout.record(self.identity)) else None
        if self.manager.is_merged(self.identity):
            changes = {'merged_geometry': geometry}
            if anchor is not None:changes['display_layout']=anchor
            if self.manual_resize: changes['merged_compact'] = False
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

    def hideEvent(self, event):
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
            ratio,divisor=image.devicePixelRatio(),material_blur(self.option('blur'),self.option('material'))
            self.backdrop=image.scaled(max(1,image.width()//divisor),max(1,image.height()//divisor),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            self.backdrop.setDevicePixelRatio(ratio)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        shape = QPainterPath()
        radius = 22 if self.collapsed and self.option('collapse_style') == 'capsule' else (8 if self.collapsed else 18)
        shape.addRoundedRect(rect, radius*self.ui_factor, radius*self.ui_factor)
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
        if self.disposed: event.accept()
        else:
            event.ignore()
            self.collapse()

    def dispose(self):
        self.disposed = True
        for timer in (self.refresh_timer, self.resize_timer, self.collapse_timer, self.expand_timer, self.fit_timer): timer.stop()
        self.backdrop = None
        self.close()
        self.deleteLater()


class PanelOptions(QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel, self.fields = panel, {}
        self.applying_preset = False
        self.setWindowTitle('面板外观 · '+panel.model['name'])
        self.resize(440, 530)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setVerticalSpacing(12)
        self.preset = ModernComboBox()
        self.preset.addItem('自定义 / 保留当前设置')
        self.preset.addItems([name for name, _ in PANEL_PRESETS])
        form.addRow('外观预设', self.preset)
        for key, title, lower, upper in [('opacity','不透明度（%）',0,100), ('blur','模糊强度',2,30), ('highlight','高光（%）',0,100), ('capsule_ratio','胶囊宽度比例（%）',30,100)]:
            field = ModernSpinBox()
            field.setRange(lower, upper)
            field.setValue(panel.option(key))
            self.fields[key] = field
            form.addRow(title, field)
        from appearance_presets import MATERIALS, COLOR_MODES
        for key, title, options in [('material','材质', MATERIALS), ('theme','颜色模式',COLOR_MODES),
                 ('collapse_style','收起形状',[('胶囊','capsule'),('方条','bar')])]:
            field = ModernComboBox()
            for name, value in options: field.addItem(name, value)
            field.setCurrentIndex(max(0, field.findData(panel.option(key))))
            self.fields[key] = field
            form.addRow(title, field)
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self.color = QLineEdit(panel.option('color'))
        self.color.setPlaceholderText('留空使用默认色，或 #RRGGBB')
        color_row.addWidget(self.color, 1)
        color_row.addWidget(button('选择', self.choose_color))
        from ui_style import ThemeSwatches
        colors = QVBoxLayout()
        colors.setSpacing(4)
        colors.addLayout(color_row)
        colors.addWidget(ThemeSwatches(self.color))
        form.addRow('主题色', colors)
        self.auto = ModernCheckBox('鼠标离开后自动收起')
        self.auto.setChecked(panel.option('auto_hide'))
        form.addRow(self.auto)
        self.status = label('只调整当前面板。胶囊宽度为展开宽度的 30–100%，最窄 180 像素。', 'muted')
        form.addRow(self.status)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(button('取消', self.reject))
        actions.addWidget(button('保存', self.commit, 'primary'))
        form.addRow(actions)
        matching = next((index for index, (_, values) in enumerate(PANEL_PRESETS, 1)
                         if all(panel.option(key) == value for key, value in values.items())), 0)
        self.preset.setCurrentIndex(matching)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        for field in self.fields.values():
            signal = field.currentIndexChanged if isinstance(field, QComboBox) else field.valueChanged
            signal.connect(self.customized)
        self.color.textChanged.connect(self.customized)
        self.fields['material'].currentIndexChanged.connect(self.material_changed)
        compact_dialog(self)

    def material_changed(self):
        if not self.applying_preset and self.fields['material'].currentData()!='clear' and self.fields['opacity'].value()==0 and self.fields['highlight'].value()==0:
            self.fields['opacity'].setValue(38)
            self.fields['highlight'].setValue(45)

    def customized(self, *args):
        if not self.applying_preset: self.preset.setCurrentIndex(0)

    def apply_preset(self, index):
        if index <= 0: return
        self.applying_preset = True
        for key, value in PANEL_PRESETS[index-1][1].items():
            if key == 'color': self.color.setText(value)
            else:
                field = self.fields[key]
                if isinstance(field, QComboBox): field.setCurrentIndex(field.findData(value))
                else: field.setValue(value)
        self.applying_preset = False

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color.text() or '#b8d9ef'), self, '选择面板主题色')
        if color.isValid(): self.color.setText(color.name())

    def commit(self):
        import re
        color = self.color.text().strip()
        if color and not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            self.status.setText('主题色请使用 #RRGGBB，或留空使用默认色。')
            return
        values = {key: field.currentData() if isinstance(field, QComboBox) else field.value() for key, field in self.fields.items()}
        if self.panel.manager.update_panel(self.panel.identity, color=color.lower(), auto_hide=self.auto.isChecked(), **values):
            self.status.setText('当前面板设置已保存并生效，可继续调整。')
        else: self.status.setText('保存失败，当前调整已保留，可重试。')
