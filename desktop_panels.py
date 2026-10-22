"""Independent persistent desktop collections, directory events and panel lifecycle."""
import copy
import os
import uuid
from pathlib import Path
from PyQt5.QtCore import QObject, QFileSystemWatcher, QTimer
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox
from app_catalog import path_key
from desktop_catalog import CATEGORIES, DesktopScan, desktop_roots, reconcile


class DesktopPanels(QObject):
    def __init__(self, runtime, roots=None):
        super().__init__(runtime.dock)
        self.runtime, self.dock = runtime, runtime.dock
        self.windows = {}
        self.shown, self.blocked, self.closed = True, False, False
        testing = self.dock.preview or bool(os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.roots = list(roots) if roots is not None else ([] if testing else desktop_roots())
        self.worker = None
        self.scan_again = False
        self.message = ''
        from desktop_icons import DesktopIcons
        self.icons = DesktopIcons(preview=testing, journal_path=None if testing else
                                  os.path.join(runtime.api.CONFIG_DIR, 'desktop_visibility.json'))
        self.icons.setParent(self)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.schedule_scan)
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.setInterval(350)
        self.scan_timer.timeout.connect(self.scan)

    @property
    def cfg(self): return self.dock.cfg

    def commit(self, **changes):
        candidate = dict(self.cfg, **copy.deepcopy(changes))
        if self.runtime.api.save_config(candidate) is False:
            self.status('收纳设置保存失败，改动未应用，请检查数据目录。')
            return False
        self.cfg.update({key: candidate[key] for key in changes})
        return True

    def status(self, message):
        self.message = message
        for window in self.windows.values(): window.notice.setText(message or '拖入文件、文件夹或快捷方式')
        if message: self.runtime.api.log(message)

    def apply_settings(self):
        if self.closed: return
        if self.cfg['panel_enabled'] and not self.cfg['desktop_panels']:
            self.commit(desktop_panels=[{'id': 'other', 'name': '其他'}])
        self.sync_windows()
        for window in self.windows.values(): window.apply_options()
        self.update_watchers()
        if self.cfg['panel_enabled'] and self.cfg['desktop_auto_sort']:
            self.schedule_scan()

    def update_watchers(self):
        if self.watcher.directories(): self.watcher.removePaths(self.watcher.directories())
        if self.closed or not self.cfg['panel_enabled'] or not self.cfg['desktop_auto_sort']: return
        paths = set()
        for root in self.roots:
            path = root if os.path.isdir(root) else str(Path(root).parent)
            if os.path.isdir(path): paths.add(path)
        if paths: self.watcher.addPaths(sorted(paths))

    def schedule_scan(self, *args):
        if not self.closed and self.cfg['panel_enabled'] and self.cfg['desktop_auto_sort']:
            self.scan_timer.start()

    def scan(self):
        if self.closed or not self.cfg['panel_enabled'] or not self.cfg['desktop_auto_sort']: return
        self.update_watchers()
        if self.worker:
            self.scan_again = True
            return
        self.worker = DesktopScan(self.roots)
        self.worker.ready.connect(self.scanned)
        self.worker.start()

    def scanned(self, rows, errors):
        self.worker = None
        if self.closed: return
        if self.cfg['panel_enabled'] and self.cfg['desktop_auto_sort']:
            if errors:
                # An unavailable redirected desktop must not erase its references.
                keys = {path_key(row['path']) for row in rows}
                rows = list(rows) + [dict(row) for row in self.cfg['desktop_entries']
                                     if row.get('source') == 'desktop' and path_key(row['path']) not in keys]
            entries = reconcile(self.cfg['desktop_entries'], rows, self.cfg['desktop_excluded'])
            panels = copy.deepcopy(self.cfg['desktop_panels'])
            known = {panel['id'] for panel in panels}
            for identity, name in CATEGORIES:
                if identity not in known and any(row['panel'] == identity for row in entries):
                    panels.append({'id': identity, 'name': name})
            if entries != self.cfg['desktop_entries'] or panels != self.cfg['desktop_panels']:
                if self.commit(desktop_entries=entries, desktop_panels=panels): self.sync_windows()
            self.status('部分桌面目录不可读取，已保留原收纳记录；可稍后重新整理。' if errors else '')
        if self.scan_again:
            self.scan_again = False
            self.schedule_scan()

    def sync_windows(self):
        if self.closed: return
        from glass_panel import DesktopPanel
        models = {model['id']: model for model in self.cfg['desktop_panels']}
        for identity in set(self.windows)-set(models):
            window = self.windows.pop(identity)
            window.dispose()
        geo = QApplication.primaryScreen().availableGeometry()
        columns = max(1, min(4, (geo.width()-32)//336))
        rows = max(1, (len(models)+columns-1)//columns)
        height = max(180, min(240, (geo.height()-48)//rows-16))
        for index, model in enumerate(models.values()):
            if model['id'] not in self.windows:
                default = [geo.left()+20+(index % columns)*336,
                           geo.top()+20+(index//columns)*(height+16), 320, height]
                self.windows[model['id']] = DesktopPanel(self, model['id'], default)
            window = self.windows[model['id']]
            window.render()
            window.setVisible(self.shown and not self.blocked and self.cfg['panel_enabled'])
        # Never hide the user's icons until at least one collection window exists.
        self.icons.set_enabled(self.shown and self.cfg['panel_enabled'] and bool(self.windows))

    def rows(self, identity):
        rows = [row for row in self.cfg['desktop_entries'] if row['panel'] == identity]
        order = self.model(identity).get('sort', 'name_asc')
        def key(row):
            name = (row['name'].casefold(), row['path'].casefold())
            if order.startswith('modified'):
                try: modified = os.path.getmtime(row['path'])
                except OSError: modified = 0
                return (modified, name)
            return name
        rows.sort(key=key, reverse=order in ('name_desc', 'modified_desc'))
        rows.sort(key=lambda row: not row.get('pinned', False))
        return rows

    def pin_entries(self, keys, pinned):
        entries = [dict(row, pinned=pinned) if path_key(row['path']) in keys else dict(row)
                   for row in self.cfg['desktop_entries']]
        if self.commit(desktop_entries=entries): self.sync_windows()

    def model(self, identity):
        return next(model for model in self.cfg['desktop_panels'] if model['id'] == identity)

    def update_panel(self, identity, **values):
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        next(model for model in panels if model['id'] == identity).update(values)
        if self.commit(desktop_panels=panels):
            self.windows[identity].apply_options()
            return True
        return False

    def add_paths(self, identity, paths):
        paths = list(dict.fromkeys(os.path.abspath(path) for path in paths if os.path.exists(path)))
        if not paths: return False
        entries = copy.deepcopy(self.cfg['desktop_entries'])
        existing = {path_key(row['path']): row for row in entries}
        keys = set()
        for path in paths:
            key = path_key(path)
            keys.add(key)
            if key in existing:
                existing[key]['panel'] = identity
                existing[key]['source'] = 'manual'
            else:
                entries.append({'path': path, 'name': Path(path).name, 'panel': identity, 'source': 'manual'})
        excluded = [key for key in self.cfg['desktop_excluded'] if key not in keys]
        if self.commit(desktop_entries=entries, desktop_excluded=excluded):
            self.sync_windows()
            self.status('已收纳 %d 项，原文件保持原位。' % len(paths))
            return True
        return False

    def move_entries(self, keys, identity):
        entries = [dict(row, panel=identity, source='manual') if path_key(row['path']) in keys else dict(row)
                   for row in self.cfg['desktop_entries']]
        if self.commit(desktop_entries=entries): self.sync_windows()

    def remove_entries(self, keys):
        entries = [dict(row) for row in self.cfg['desktop_entries'] if path_key(row['path']) not in keys]
        excluded = list(dict.fromkeys(self.cfg['desktop_excluded']+list(keys)))
        if self.commit(desktop_entries=entries, desktop_excluded=excluded):
            self.sync_windows()
            self.status('已移除收纳引用，原文件保留；可重新拖入。')

    def new_panel(self, name=None):
        if name is None:
            name, okay = QInputDialog.getText(None, '新建桌面面板', '面板名称：')
            if not okay: return
        name = name.strip()[:40]
        if not name: return
        identity = uuid.uuid4().hex
        if self.commit(desktop_panels=self.cfg['desktop_panels']+[{'id': identity, 'name': name}]):
            self.shown = True
            self.sync_windows()
            return identity

    def delete_panel(self, identity):
        if QMessageBox.question(self.windows[identity], '移除面板',
                '移除此面板及收纳引用？原文件保留。自动分类面板在后续发现新内容时可能重新建立。') != QMessageBox.Yes:
            return
        keys = {path_key(row['path']) for row in self.rows(identity)}
        if self.commit(desktop_panels=[model for model in self.cfg['desktop_panels'] if model['id'] != identity],
                       desktop_entries=[row for row in self.cfg['desktop_entries'] if row['panel'] != identity],
                       desktop_excluded=list(dict.fromkeys(self.cfg['desktop_excluded']+list(keys)))):
            self.sync_windows()

    def reveal(self):
        self.shown = True
        if not self.cfg['desktop_panels']: self.new_panel('收纳面板')
        self.sync_windows()
        self.schedule_scan()

    def toggle(self):
        if self.shown and self.windows:
            self.shown = False
            self.sync_windows()
        else: self.reveal()

    def set_blocked(self, blocked):
        self.blocked = blocked
        self.sync_windows()

    def set_lite(self, enabled):
        for window in self.windows.values():
            window.backdrop = None
            window.refresh_timer.stop()
            if enabled:
                window.collapse()
                window._released_selection = window.selected_keys() | getattr(window, '_released_selection', set())
                window.list.clear()
            else: window.refresh_timer.start(100)
            window.update()

    def reposition(self):
        for window in self.windows.values():
            window.set_collapsed_geometry(window.collapsed)
            window.store_geometry()

    def close(self):
        if self.closed: return
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        for model in panels:
            window = self.windows.get(model['id'])
            if window and not window.disposed:
                geometry = window.bounds()
                geometry[:2] = [window.x(), window.y()]
                if not window.collapsed: geometry[2:] = [window.width(), window.height()]
                model['geometry'] = geometry
        if panels != self.cfg['desktop_panels']: self.commit(desktop_panels=panels)
        self.closed = True
        self.icons.close()
        self.scan_timer.stop()
        if self.watcher.directories(): self.watcher.removePaths(self.watcher.directories())
        if self.worker: self.worker.close()
        for window in self.windows.values(): window.dispose()
        self.windows.clear()
