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
        self.shown, self.blocked, self.closed = bool(self.cfg.get('panels_visible', True)), False, False
        self.active_window = None
        self.scanned_rows = []
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
        if self.cfg['panel_enabled'] and not self.cfg['desktop_panels'] and not self.cfg.get('disabled_categories'):
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
            self.scanned_rows = list(rows)
            if errors:
                # An unavailable redirected desktop must not erase its references.
                keys = {path_key(row['path']) for row in rows}
                rows = list(rows) + [dict(row) for row in self.cfg['desktop_entries']
                                     if row.get('source') == 'desktop' and path_key(row['path']) not in keys]
            entries = reconcile(self.cfg['desktop_entries'], rows, self.cfg['desktop_excluded'])
            panels = copy.deepcopy(self.cfg['desktop_panels'])
            known = {panel['id'] for panel in panels}
            for identity, name in CATEGORIES:
                if identity not in known and identity not in self.cfg['disabled_categories'] and any(row['panel'] == identity for row in entries):
                    panels.append({'id': identity, 'name': name})
            if entries != self.cfg['desktop_entries'] or panels != self.cfg['desktop_panels']:
                if self.commit(desktop_entries=entries, desktop_panels=panels): self.sync_windows()
            self.sync_windows()
            self.status('部分桌面目录不可读取，已保留原收纳记录；可稍后重新整理。' if errors else '')
        if self.scan_again:
            self.scan_again = False
            self.schedule_scan()

    def enabled_models(self):
        return [model for model in self.cfg['desktop_panels'] if model.get('enabled', True)
                and model['id'] not in self.cfg['disabled_categories']]

    def is_merged(self, identity):
        return bool(self.cfg['merged_panels'] and self.model(identity).get('merged', True))

    def merged_models(self):
        return [model for model in self.enabled_models() if self.is_merged(model['id'])]

    def save_visible_geometry(self):
        for window in self.windows.values():
            if window.isVisible(): window.store_geometry()

    def set_merged(self, identity, merged):
        self.save_visible_geometry()
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        # Starting a merge from independent mode affects only the chosen card.
        if merged and not self.cfg['merged_panels']:
            for model in panels: model['merged'] = False
        next(model for model in panels if model['id']==identity)['merged'] = merged
        changes = dict(desktop_panels=panels)
        if merged: changes['merged_panels'] = True
        if not self.commit(**changes): return False
        self.sync_windows()
        return True

    def reorder_panels(self, identities):
        identities = list(identities)
        models = self.cfg['desktop_panels']
        known = {model['id']:model for model in models}
        if len(identities)!=len(set(identities)) or not set(identities)<=set(known): return False
        # Reorder only participating slots; disabled and independent groups retain their places.
        selected = set(identities)
        ordered = iter(identities)
        panels = [known[next(ordered)] if model['id'] in selected else model for model in models]
        if panels!=models and not self.commit(desktop_panels=panels): return False
        for window in self.windows.values(): window.update_tabs(self.merged_models())
        self.status('分组顺序已保存。')
        return True

    def select_page(self, identity):
        if identity not in {model['id'] for model in self.merged_models()}: return
        current = self.windows.get(self.active_window)
        if current: current.store_geometry()
        if self.commit(merged_active=identity): self.sync_windows()

    def manage_groups(self):
        from panel_management import GroupDialog
        GroupDialog(self).exec_()

    def sync_windows(self):
        if self.closed: return
        from glass_panel import DesktopPanel
        models = {model['id']: model for model in self.cfg['desktop_panels']}
        for identity in set(self.windows)-set(models):
            self.windows.pop(identity).dispose()
        enabled = self.enabled_models()
        members = self.merged_models()
        member_ids = {model['id'] for model in members}
        active = self.cfg.get('merged_active')
        if active not in member_ids:
            active = members[0]['id'] if members else ''
            if self.cfg.get('merged_active') != active: self.commit(merged_active=active)
        geo = QApplication.primaryScreen().availableGeometry()
        columns = max(1, min(4, (geo.width()-32)//336))
        rows = max(1, (len(models)+columns-1)//columns)
        height = max(180, min(240, (geo.height()-48)//rows-16))
        enabled_ids = {model['id'] for model in enabled}
        for index, model in enumerate(models.values()):
            identity = model['id']
            if identity not in self.windows:
                default = [geo.left()+20+(index % columns)*336,
                           geo.top()+20+(index//columns)*(height+16), 320, height]
                self.windows[identity] = DesktopPanel(self, identity, default)
            window = self.windows[identity]
            merged = self.is_merged(identity)
            window.update_tabs(members)
            if window.merged_view != merged:
                window.resize_timer.stop()
                window.manual_resize = False
            visible = (self.shown and not self.blocked and self.cfg['panel_enabled'] and identity in enabled_ids
                       and (not merged or identity==active))
            if visible and (not window.isVisible() or window.merged_view != merged):
                window.merged_view = merged
                window.set_collapsed_geometry(self.cfg['merged_collapsed'] if merged else bool(model.get('collapsed')))
            window.render()
            window.setVisible(visible)
        self.active_window = active or None
        layout=getattr(self.runtime,'layout',None)
        if layout:layout.ensure_profiles()
        self.icons.set_enabled(self.shown and self.cfg['panel_enabled'] and not self.blocked
                               and any(window.isVisible() for window in self.windows.values()))

    def rows(self, identity):
        model = self.model(identity)
        excluded = set(model.get('excluded', []))
        rows = [dict(row) for row in self.cfg['desktop_entries'] if row['panel'] == identity]
        if self.cfg['desktop_auto_sort'] and model.get('extensions'):
            from desktop_catalog import effective_suffix
            candidates = {path_key(row['path']):row for row in self.cfg['desktop_entries']+self.scanned_rows if row.get('source')=='desktop'}
            rows += [dict(row, panel=identity, pinned=False) for row in candidates.values()
                     if effective_suffix(row['path']) in model['extensions'] and os.path.exists(row['path'])]
        unique = {}
        for row in rows:
            key = path_key(row['path'])
            if key not in excluded and key not in unique: unique[key] = row
        rows = list(unique.values())
        if 'pinned_paths' in model:
            for row in rows: row['pinned'] = path_key(row['path']) in model['pinned_paths']
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

    def pin_entries(self, keys, pinned, identity=None):
        if identity is not None:
            paths = set(self.model(identity).get('pinned_paths', [path_key(row['path']) for row in self.rows(identity) if row.get('pinned')]))
            if pinned: paths.update(keys)
            else: paths.difference_update(keys)
            self.update_panel(identity, pinned_paths=sorted(paths))
            return
        entries = [dict(row, pinned=pinned) if path_key(row['path']) in keys else dict(row)
                   for row in self.cfg['desktop_entries']]
        if self.commit(desktop_entries=entries): self.sync_windows()

    def model(self, identity):
        return next(model for model in self.cfg['desktop_panels'] if model['id'] == identity)

    def update_panel(self, identity, _layout=None, **values):
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        next(model for model in panels if model['id'] == identity).update(values)
        changes = {'desktop_panels': panels}
        layout=getattr(self.runtime,'layout',None)
        if _layout is None and 'geometry' in values and layout:
            _layout=layout.panel_update(identity,values['geometry'])
        if isinstance(_layout,dict):changes['display_layout']=_layout
        if self.is_merged(identity) and 'collapsed' in values: changes['merged_collapsed'] = values['collapsed']
        if self.commit(**changes):
            if identity in self.windows: self.windows[identity].apply_options()
            return True
        return False

    def add_paths(self, identity, paths):
        paths = list(dict.fromkeys(os.path.abspath(path) for path in paths if os.path.exists(path)))
        if not paths: return False
        entries = copy.deepcopy(self.cfg['desktop_entries'])
        existing = {(path_key(row['path']), row['panel']): row for row in entries}
        keys = set()
        for path in paths:
            key = path_key(path)
            keys.add(key)
            pair = (key,identity)
            if pair in existing:
                existing[pair]['source'] = 'manual'
            else:
                entries.append({'path': path, 'name': Path(path).name, 'panel': identity, 'source': 'manual'})
        excluded = [key for key in self.cfg['desktop_excluded'] if key not in keys]
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        for panel in panels:
            if panel['id']==identity: panel['excluded'] = [key for key in panel.get('excluded',[]) if key not in keys]
        if self.commit(desktop_entries=entries, desktop_excluded=excluded, desktop_panels=panels):
            self.sync_windows()
            self.status('已收纳 %d 项，原文件保持原位。' % len(paths))
            return True
        return False

    def move_entries(self, keys, identity):
        entries = [dict(row, panel=identity, source='manual') if path_key(row['path']) in keys else dict(row)
                   for row in self.cfg['desktop_entries']]
        if self.commit(desktop_entries=entries): self.sync_windows()

    def remove_entries(self, keys, identity=None):
        if identity is not None:
            panels = copy.deepcopy(self.cfg['desktop_panels'])
            model = next(model for model in panels if model['id']==identity)
            model['excluded'] = list(dict.fromkeys(model.get('excluded',[])+list(keys)))
            entries = [dict(row) for row in self.cfg['desktop_entries'] if row['panel']!=identity or path_key(row['path']) not in keys]
            if self.commit(desktop_panels=panels, desktop_entries=entries): self.sync_windows()
            return
        entries = [dict(row) for row in self.cfg['desktop_entries'] if path_key(row['path']) not in keys]
        excluded = list(dict.fromkeys(self.cfg['desktop_excluded']+list(keys)))
        if self.commit(desktop_entries=entries, desktop_excluded=excluded):
            self.sync_windows()
            self.status('已移除收纳引用，原文件保留；可重新拖入。')

    def new_panel(self, name=None, extensions=None):
        if name is None:
            from panel_management import PanelDefinition
            dialog = PanelDefinition()
            if dialog.exec_() != dialog.Accepted: return
            name, extensions = dialog.name.text(), dialog.extensions()
        name = name.strip()[:40]
        if not name: return
        identity = uuid.uuid4().hex
        if self.commit(desktop_panels=self.cfg['desktop_panels']+[{'id': identity, 'name': name, 'extensions': list(extensions or [])}], panels_visible=True):
            self.shown = True
            self.sync_windows()
            self.schedule_scan()
            return identity

    def delete_panel(self, identity):
        if QMessageBox.question(self.windows[identity], '移除面板',
                '移除此面板及其中的引用？原文件和其他面板不受影响。默认分组可在分组管理中重新开启。') != QMessageBox.Yes:
            return
        disabled = list(self.cfg['disabled_categories'])
        if identity in dict(CATEGORIES) and identity not in disabled: disabled.append(identity)
        if self.commit(desktop_panels=[model for model in self.cfg['desktop_panels'] if model['id'] != identity],
                       desktop_entries=[row for row in self.cfg['desktop_entries'] if row['panel'] != identity],
                       disabled_categories=disabled):
            self.sync_windows()

    def reveal(self):
        self.commit(panels_visible=True)
        self.shown = True
        if not self.cfg['desktop_panels']: self.new_panel('收纳面板')
        self.sync_windows()
        self.schedule_scan()

    def toggle(self):
        if self.shown and self.windows:
            if not self.commit(panels_visible=False): return
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
            else:
                desired = self.cfg.get('lite_restore',{}).get(window.identity, window.collapsed)
                window.set_collapsed_geometry(desired)
                if not self.is_merged(window.identity): self.update_panel(window.identity, collapsed=desired)
                window.render()
                window.refresh_timer.start(100)
            window.update()

    def reposition(self):
        for window in self.windows.values():
            window.set_collapsed_geometry(window.collapsed)
            window.resize_timer.stop()

    def close(self):
        if self.closed: return
        self.save_visible_geometry()
        if self.cfg['merged_panels']:
            window = self.windows.get(self.active_window)
            if window: window.store_geometry()
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        for model in panels:
            window = self.windows.get(model['id']) if not self.is_merged(model['id']) else None
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
