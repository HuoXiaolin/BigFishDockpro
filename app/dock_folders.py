"""Dock folder entries and their transient app grid."""
import uuid

CAPACITY = 81


def entry(folder_id, children, name='应用文件夹'):
    return {'path': 'dock-folder:' + folder_id, 'name': str(name).strip()[:40] or '应用文件夹', 'folder': children}


def application_entries(items):
    for item in items:
        if 'folder' in item:
            yield from item['folder']
        elif not item.get('sep'):
            yield item


def rename_folder(dock, folder, save, name=None):
    if name is None:
        from PyQt5.QtWidgets import QInputDialog
        name, accepted = QInputDialog.getText(dock, '重命名文件夹', '文件夹名称：', text=folder.get('name', '应用文件夹'))
        if not accepted: return False
    name = str(name).strip()[:40]
    if not name: return False
    items = list(dock.cfg['items'])
    index = next((i for i, item in enumerate(items) if item.get('path') == folder['path'] and 'folder' in item), None)
    if index is None: return False
    if items[index].get('name') == name: return True
    items[index] = dict(items[index], name=name)
    return bool(dock.commit_folder_items(items, save))


def show_folder(dock, folder, save):
    from PyQt5.QtCore import QPoint, QRectF, QSize, Qt
    from PyQt5.QtGui import QIcon, QCursor, QPainter, QPainterPath
    from PyQt5.QtWidgets import QApplication, QGridLayout, QScrollArea, QToolButton, QVBoxLayout, QWidget, QLineEdit

    colors = dock.theme_colors()
    icon_size = max(28, min(72, dock.icon_size))
    tile_width = max(72, icon_size + 16)
    tile_height = icon_size + 30

    class FolderPopup(QWidget):
        def __init__(self):
            super().__init__(dock, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_DeleteOnClose)
            self.cfg = dock.cfg
            self.backdrop = None
            self.spec_alpha = 0.0

        def prepare_backdrop(self):
            if (not self.cfg['glass'] or self.cfg.get('clear_background')
                    or self.cfg.get('dock_material') in ('clear', 'solid')):
                return
            from glass_capture import capture_behind, smooth_backdrop
            wallpaper = capture_behind(self)
            if wallpaper is not None and not wallpaper.isNull():
                self.backdrop = smooth_backdrop(wallpaper, dock.blur_divisor())

        def hideEvent(self, event):
            set_marker(None)
            super().hideEvent(event)

        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Escape:
                self.close(); event.accept(); return
            super().keyPressEvent(event)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
            bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            radius = min(dock.corner_radius(), bounds.height() / 2)
            path = QPainterPath()
            path.addRoundedRect(bounds, radius, radius)
            dock.paint_dock_surface(self, painter, [path], bounds, colors)

    popup = FolderPopup()
    popup.setObjectName('dockFolder')
    hover = 'rgba(0,0,0,26)' if colors['light'] else 'rgba(255,255,255,38)'
    popup.setStyleSheet(
        'QWidget#folderGrid, QScrollArea, QWidget#folderViewport {background:transparent;border:0;}'
        f'QToolButton {{background:transparent;color:{colors["fg"].name()};border:0;border-radius:8px;}}'
        f'QToolButton:hover {{background:{hover};}}'
        f'QLineEdit {{background:transparent;color:{colors["fg"].name()};border:0;padding:4px 6px;}}'
        f'QLineEdit:focus {{background:{hover};border-radius:6px;}}'
    )
    area = QScrollArea(popup)
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.viewport().setObjectName('folderViewport')
    area.viewport().setAutoFillBackground(False)
    content = QWidget()
    content.setObjectName('folderGrid')
    content.setAutoFillBackground(False)
    grid = QGridLayout(content)
    area.setWidget(content)
    layout = QVBoxLayout(popup)
    title = QLineEdit(folder.get('name', '应用文件夹'), popup)
    title.setMaxLength(40); title.setAccessibleName('文件夹名称')
    title.setToolTip('编辑名称后按 Enter 保存'); title.setStyleSheet('font-weight:600;')
    search = QLineEdit(popup)
    search.setPlaceholderText('搜索文件夹中的应用'); search.setAccessibleName('搜索文件夹中的应用')
    layout.addWidget(title); layout.addWidget(search); layout.addWidget(area)
    popup.folder_title = title; popup.folder_search = search

    def save_title():
        nonlocal folder
        if rename_folder(dock, folder, save, title.text()):
            folder = next(item for item in dock.cfg['items'] if item.get('path') == folder['path'])
        title.setText(folder.get('name', '应用文件夹'))
    title.editingFinished.connect(save_title)
    anchor = QCursor.pos()
    screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
    bounds = screen.availableGeometry()
    columns = min(9, len(folder['folder']), max(1, (bounds.width()-40)//(tile_width+6)))

    def insertion_slot(point, folder_index):
        local = dock.mapFromGlobal(point)
        if dock.bar_rect_f().contains(local.x(), local.y()):
            for index, rect in enumerate(dock.rects):
                if local.x() < rect[0]:
                    return dock.page_offset + index
            return dock.page_offset + len(dock.rects)
        return folder_index + 1

    def set_marker(slot):
        if getattr(dock, '_folder_drop_slot', None) != slot:
            dock._folder_drop_slot = slot
            dock.update()

    def extract(child, point, origin, pixmap):
        items = list(dock.cfg['items'])
        index = next((i for i, item in enumerate(items) if item is folder), None)
        if index is None:
            return
        remaining = [item for item in folder['folder'] if item is not child]
        replacement = [dict(folder, folder=remaining)] if len(remaining) > 1 else remaining
        items[index:index+1] = replacement
        destination = insertion_slot(point, index)
        if destination > index:
            destination += len(replacement) - 1
        items.insert(destination, child)
        if dock.commit_folder_items(items, save):
            popup.close()
            animate_transfer(dock, pixmap, origin, destination, into_folder=False)

    class Tile(QToolButton):
        def __init__(self, child):
            super().__init__(content)
            self.child = child
            self.origin = None
            self.setFixedSize(tile_width, tile_height)
            self.setIconSize(QSize(icon_size, icon_size))
            self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            name = str(child.get('name') or child['path'])
            self.setText(self.fontMetrics().elidedText(name, Qt.ElideRight, tile_width - 8))
            self.setToolTip(name + '\n拖出文件夹可放回 Dock')
            icon = child.get('icon')
            self.setIcon(QIcon(dock.icons.get(icon or child['path'], icon_size * 2, bool(icon),
                                              icon_index=child.get('icon_index', 0))))
            self.clicked.connect(self.open_app)

        def open_app(self):
            popup.close()
            dock.launch(self.child)

        def mousePressEvent(self, event):
            self.origin = event.globalPos() if event.button() == Qt.LeftButton else None
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            point = event.globalPos()
            dragging = (self.origin is not None and event.buttons() & Qt.LeftButton
                        and (point-self.origin).manhattanLength() >= QApplication.startDragDistance())
            outside = dragging and not popup.geometry().contains(point)
            folder_index = next((i for i, item in enumerate(dock.cfg['items']) if item is folder), None)
            set_marker(insertion_slot(point, folder_index) if outside and folder_index is not None else None)
            if outside:
                self.setCursor(Qt.DragMoveCursor)
            else:
                self.unsetCursor()
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            point = event.globalPos()
            set_marker(None)
            self.unsetCursor()
            if (event.button() == Qt.LeftButton and self.origin is not None
                    and (point-self.origin).manhattanLength() >= QApplication.startDragDistance()
                    and not popup.geometry().contains(point)):
                self.setDown(False)
                center = self.rect().center()
                center.setY(self.iconSize().height() // 2 + 4)
                extract(self.child, point, self.mapToGlobal(center),
                        self.icon().pixmap(self.iconSize()))
                event.accept()
                return
            super().mouseReleaseEvent(event)

    tiles = [Tile(child) for child in folder['folder']]
    popup.folder_tiles = tiles

    def filter_tiles(text):
        query = text.strip().casefold()
        while grid.count(): grid.takeAt(0)
        visible = []
        for tile in tiles:
            match = query in (str(tile.child.get('name', '')) + ' ' + tile.child['path']).casefold()
            tile.setVisible(match)
            if match:
                index = len(visible); grid.addWidget(tile, index // columns, index % columns); visible.append(tile)
        popup.filtered_tiles = visible
    search.textChanged.connect(filter_tiles)
    search.returnPressed.connect(lambda: popup.filtered_tiles[0].open_app() if popup.filtered_tiles else None)
    filter_tiles('')
    rows = (len(folder['folder']) + columns - 1) // columns
    popup.resize(min(bounds.width(), (tile_width+6)*columns + 40), min(bounds.height(), (tile_height+6)*rows + 104))
    dock_top = dock.mapToGlobal(QPoint()).y()
    y = dock_top - popup.height()
    if y < bounds.top():
        y = dock_top + dock.height()
    popup.move(max(bounds.left(), min(anchor.x()-popup.width()//2, bounds.right()-popup.width()+1)),
               max(bounds.top(), min(y, bounds.bottom()-popup.height()+1)))
    popup.prepare_backdrop()
    popup.show()
    search.setFocus()
    return popup


def combine(items, source, target):
    dragged, destination = items[source], items[target]
    if 'folder' in dragged or dragged.get('sep') or destination.get('sep'):
        return None
    children = destination.get('folder', [destination])
    if len(children) >= CAPACITY:
        return None
    result = list(items)
    result[target] = dict(destination, folder=children+[dragged]) if 'folder' in destination else entry(uuid.uuid4().hex, children+[dragged])
    del result[source]
    return result


def normalize_folder(item, strict=False):
    from shortcut_mapping import map_entry

    children = item.get('folder')
    folder_path = item.get('path')
    valid_id = (isinstance(folder_path, str) and folder_path.startswith('dock-folder:')
                and len(folder_path) == 44 and all(c in '0123456789abcdef' for c in folder_path[12:]))
    if not isinstance(children, list) or (strict and (not valid_id or not 2 <= len(children) <= CAPACITY)):
        if strict:
            raise ValueError('Dock 文件夹格式不正确。')
        return []
    apps = []
    for child in children:
        valid = (isinstance(child, dict) and not child.get('sep') and 'folder' not in child
                 and isinstance(child.get('path'), str) and bool(child['path'].strip())
                 and '\x00' not in child['path'] and len(child['path']) <= 32768)
        if not valid:
            if strict:
                raise ValueError('Dock 文件夹中存在无效应用。')
            continue
        apps.append(map_entry(child, validate=False) or dict(child))
    if len(apps) <= 1:
        return apps
    folder_id = folder_path[12:] if valid_id else uuid.uuid4().hex
    return [entry(folder_id, apps[:CAPACITY], item.get('name') or '应用文件夹'), *apps[CAPACITY:]]


def folder_icon(dock, folder):
    from PyQt5.QtCore import QRectF, Qt
    from PyQt5.QtGui import QColor, QPainter, QPixmap

    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor('#c8e0f2'))
    painter.drawRoundedRect(QRectF(3, 3, 122, 122), 26, 26)
    for index, child in enumerate(folder['folder'][:9]):
        icon = child.get('icon')
        preview = dock.icons.get(icon or child['path'], 32, bool(icon),
                                 icon_index=child.get('icon_index', 0))
        if preview and not preview.isNull():
            painter.drawPixmap(15 + index % 3 * 34, 15 + index // 3 * 34, 30, 30, preview)
    painter.end()
    return pixmap


def remove_applications(items, keys):
    from app_catalog import launch_identity

    result = []
    for item in items:
        if 'folder' in item:
            children = [child for child in item['folder'] if launch_identity(child) not in keys]
            result.extend([dict(item, folder=children)] if len(children) > 1 else children)
        elif not item.get('path') or launch_identity(item) not in keys:
            result.append(item)
    return result



def animate_transfer(dock, pixmap, origin, destination, *, into_folder):
    """Animate a cached icon toward the committed Dock slot."""
    from PyQt5.QtCore import QEasingCurve, QPoint, QRectF, Qt, QVariantAnimation
    from PyQt5.QtGui import QPainter
    from PyQt5.QtWidgets import QWidget

    index = destination - dock.page_offset
    if not 0 <= index < len(dock.rects) or pixmap is None or pixmap.isNull():
        return
    previous = getattr(dock, '_folder_motion', None)
    if previous is not None:
        previous.close()

    x, width, height, edge = dock.rects[index][:4]
    target = dock.mapToGlobal(QPoint(round(x), round(edge + height/2 if dock.bump_down() else edge-height/2)))
    side = max(24, round(width))
    start_size, end_size = (side, side * .33) if into_folder else (side * .75, side)
    rise = max(16, min(54, (target-origin).manhattanLength() * .15))
    lift = rise if dock.bump_down() else -rise

    class Transfer(QWidget):
        def __init__(self):
            super().__init__(dock, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WA_DeleteOnClose)
            self.resize(side + 8, side + 8)
            self.progress = 0.0
            self.animation = QVariantAnimation(self)
            self.animation.setDuration(280 if into_folder else 340)
            self.animation.setStartValue(0.0)
            self.animation.setEndValue(1.0)
            self.animation.setEasingCurve(QEasingCurve.InOutCubic if into_folder else QEasingCurve.OutCubic)
            self.animation.valueChanged.connect(self.advance)
            self.animation.finished.connect(self.close)

        def advance(self, progress):
            self.progress = progress
            x = origin.x() + (target.x()-origin.x()) * progress
            y = origin.y() + (target.y()-origin.y()) * progress + 4 * lift * progress * (1-progress)
            self.move(round(x-self.width()/2), round(y-self.height()/2))
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            size = start_size + (end_size-start_size) * self.progress
            if into_folder:
                painter.setOpacity(min(1.0, (1-self.progress) * 3))
            rect = QRectF((self.width()-size)/2, (self.height()-size)/2, size, size)
            painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))

        def closeEvent(self, event):
            self.animation.stop()
            if getattr(dock, '_folder_motion', None) is self:
                dock._folder_motion = None
                dock._folder_landing_path = None
                dock.update()
            super().closeEvent(event)

    motion = Transfer()
    dock._folder_motion = motion
    if not into_folder:
        dock._folder_landing_path = dock.items[index]['path']
        dock.update()
    motion.advance(0.0)
    motion.show()
    motion.animation.start()
