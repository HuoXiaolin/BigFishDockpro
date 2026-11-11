"""Independent persistent desktop collections, directory events and panel lifecycle."""
import copy
import os
import uuid
from pathlib import Path
from PyQt5.QtCore import QObject, QFileSystemWatcher, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox
from app_catalog import path_key
from desktop_catalog import CATEGORIES, DesktopScan, desktop_roots, reconcile


class DesktopPanels(QObject):
    shared_settings_changed=pyqtSignal()
    def __init__(self, runtime, roots=None):
        super().__init__(runtime.dock)
        self.runtime, self.dock = runtime, runtime.dock
        self.windows = {}
        self.dormant_pages = {}
        self.default_geometries = {}
        self.release_hidden_cards = False
        self.shown, self.blocked, self.closed = bool(self.cfg.get('panels_visible', True)), False, False
        self.active_window = None
        self.scanned_rows = []
        self.file_metadata = {}
        testing = self.dock.preview or bool(os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.roots = list(roots) if roots is not None else ([] if testing else desktop_roots())
        self.worker = None
        self.scan_again = False
        self.message = ''
        from desktop_icons import DesktopIcons
        self.icons = DesktopIcons(preview=testing, journal_path=None if testing else
                                  os.path.join(runtime.api.CONFIG_DIR, 'desktop_visibility.json'))
        self.icons.setParent(self)
        from desktop_item_visibility import CollectedDesktopItems
        self.collected_icons=CollectedDesktopItems(self.roots, None if testing else os.path.join(runtime.api.CONFIG_DIR,'desktop_items_visibility.json'))
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.schedule_scan)
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.setInterval(350)
        self.scan_timer.timeout.connect(self.scan)
        # Some remote transfers and redirected desktops miss native notifications.
        self.reconcile_timer=QTimer(self);self.reconcile_timer.setInterval(15000)
        self.reconcile_timer.timeout.connect(self.schedule_scan)

    @property
    def cfg(self): return self.dock.cfg

    def commit(self, *, history_title=None, **changes):
        candidate = dict(self.cfg, **copy.deepcopy(changes))
        if self.runtime.api.save_config(candidate) is False:
            self.status('收纳设置保存失败，改动未应用，请检查数据目录。')
            return False
        if history_title:
            from arrangement_history import record
            record(self.cfg,{key:self.cfg.get(key) for key in changes},
                   {key:candidate[key] for key in changes},history_title)
        self.cfg.update({key: candidate[key] for key in changes})
        return True

    def status(self, message):
        self.message = message
        for window in self.windows.values(): window.notice.setText(message or '拖入文件、文件夹或快捷方式')
        if message: self.runtime.api.log(message)

    def apply_settings(self):
        if self.closed: return
        self.shown=bool(self.cfg['panels_visible'])
        if self.cfg['panel_enabled'] and not self.cfg['desktop_panels'] and not self.cfg.get('disabled_categories'):
            self.commit(desktop_panels=[{'id': 'other', 'name': '其他'}])
        self.sync_windows()
        for window in self.windows.values():
            window.apply_options();window.collapse_timer.stop()
            if window.isVisible() and window.option('auto_hide'):window.collapse_timer.start()
        self.shared_settings_changed.emit()
        self.update_watchers()
        if self.cfg['panel_enabled'] and self.cfg['desktop_auto_sort']:
            self.schedule_scan()

    def update_watchers(self):
        enabled=not self.closed and self.cfg['panel_enabled'] and self.cfg['desktop_auto_sort']
        paths=set()
        if enabled:
            for root in self.roots:
                path = root if os.path.isdir(root) else str(Path(root).parent)
                if os.path.isdir(path):paths.add(os.path.normpath(path))
        current={os.path.normpath(path) for path in self.watcher.directories()}
        if current-paths:self.watcher.removePaths(sorted(current-paths))
        if paths-current:self.watcher.addPaths(sorted(paths-current))
        if enabled and not self.reconcile_timer.isActive():self.reconcile_timer.start()
        elif not enabled:self.reconcile_timer.stop()

    def schedule_scan(self, *args):
        if not self.closed and self.cfg['panel_enabled'] and self.cfg['desktop_auto_sort']:
            self.scan_timer.start()

    def scan(self):
        if self.closed or not self.cfg['panel_enabled'] or not self.cfg['desktop_auto_sort']: return
        self.update_watchers()
        if self.worker:
            self.scan_again = True
            return
        self.worker = DesktopScan(self.roots, included_hidden=list(self.collected_icons.records),
                                  reference_paths=[row['path'] for row in self.cfg['desktop_entries']])
        self.worker.ready.connect(self.scanned)
        self.worker.start()

    def scanned(self, rows, errors):
        metadata=getattr(self.worker,'metadata',self.file_metadata)
        metadata_changed=metadata!=self.file_metadata
        self.file_metadata=metadata
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
            entries_changed=entries != self.cfg['desktop_entries'] or panels != self.cfg['desktop_panels']
            if entries_changed:
                if self.commit(desktop_entries=entries, desktop_panels=panels):self.sync_windows()
            elif metadata_changed:self.sync_windows()
            self.status('部分桌面目录不可读取，已保留原收纳记录；可稍后重新整理。' if errors else '')
        if self.scan_again:
            self.scan_again = False
            self.schedule_scan()

    def enabled_models(self):
        return [model for model in self.cfg['desktop_panels'] if model.get('enabled', True)
                and model['id'] not in self.cfg['disabled_categories']]

    def is_merged(self, identity):
        return bool(self.cfg['merged_panels'] and self.model(identity).get('merged', True))

    def group_id(self,identity):
        from panel_merge import group_id
        return group_id(self.cfg,identity)

    def group_value(self,identity,field):
        from panel_merge import value
        return value(self.cfg,self.group_id(identity),field)

    def group_changes(self,identity,**values):
        from panel_merge import changes
        return changes(self.cfg,self.group_id(identity),**values)

    def update_group(self,identity,**values):
        return self.commit(**self.group_changes(identity,**values))

    def merged_models(self,identity=None):
        return [model for model in self.enabled_models() if self.is_merged(model['id']) and
                (identity is None or self.group_id(model['id'])==self.group_id(identity))]

    def active_for(self,identity):
        models=self.merged_models(identity);active=self.group_value(identity,'active')
        return active if active in {model['id'] for model in models} else (models[0]['id'] if models else None)

    def assign_group(self,identity,group):
        self.save_visible_geometry()
        if group is not None and group not in {row['id'] for row in self.cfg['merge_groups']}:return False
        panels=copy.deepcopy(self.cfg['desktop_panels']);row=next(row for row in panels if row['id']==identity)
        row['merged']=group is not None
        if group is not None:row['merge_group']=group
        changes={'desktop_panels':panels}
        if group is not None:changes.update(merged_panels=True,merge_initialized=True)
        if not self.commit(history_title="移动卡片分组",**changes):return False
        self.sync_windows();return True

    def card_at(self, source, point):
        return next((window for window in self.windows.values()
                     if window is not source and window.isVisible() and window.geometry().contains(point)),None)

    def preview_card_drop(self, source=None, point=None):
        target=self.card_at(source,point) if point is not None else None
        previous=getattr(self,'drop_preview',None)
        if target is previous:return
        self.drop_preview=target
        if previous is not None and not previous.disposed:previous.update()
        if target is not None:target.update()

    def join_panel_at(self, identity, target, point):
        panels=copy.deepcopy(self.cfg['desktop_panels'])
        if not self.cfg['merged_panels']:
            for row in panels:row['merged']=False
        source=next(row for row in panels if row['id']==identity)
        changes=dict(desktop_panels=panels,merged_panels=True,merge_initialized=True)
        if self.is_merged(target.identity):
            group=self.group_id(target.identity)
            changes.update(self.group_changes(target.identity,collapsed=False))
        else:
            if len(self.cfg['merge_groups'])>=64:
                self.status('最多支持 64 个合并组。')
                return False
            group=uuid.uuid4().hex
            row=next(row for row in panels if row['id']==target.identity)
            row.update(merged=True,merge_group=group)
            geometry=list(target.bounds() if target.collapsed else target.geometry().getRect())
            groups=copy.deepcopy(self.cfg['merge_groups'])
            groups.append(dict(id=group,name=row['name'],active=target.identity,geometry=geometry,
                               collapsed=False,compact=row.get('compact',True)))
            changes.update(merge_groups=groups,display_layout=self.runtime.layout.panel_update(target.identity,geometry,group=group))
        source.update(merged=True,merge_group=group)
        panels.remove(source)
        local=target.tabs.mapFromGlobal(point)
        index=target.tabs.tabAt(local) if target.tabs.isVisible() else -1
        if index>=0:
            anchor=target.tabs.tabData(index)
            position=next(i for i,row in enumerate(panels) if row['id']==anchor)
            if local.x()>target.tabs.tabRect(index).center().x():position+=1
        else:
            position=max(i for i,row in enumerate(panels) if row.get('merged',True) and row.get('merge_group','default')==group)+1
        panels.insert(position,source)
        if not self.commit(history_title='拖入合并卡片',**changes):return False
        self.sync_windows()
        if target.isVisible() and target.collapsed:target.set_collapsed_geometry(False)
        return True

    def drop_independent_at(self, source, point):
        self.preview_card_drop()
        if self.is_merged(source.identity):return False
        target=self.card_at(source,point)
        if target is None:return False
        if not self.join_panel_at(source.identity,target,point):
            source.set_collapsed_geometry(source.collapsed)
        return True

    def drop_tab_at(self, identity, source, point):
        target=self.card_at(source,point)
        if target is not None:
            return self.join_panel_at(identity,target,point)
        from card_snap import drop_rect
        bounds=drop_rect(point,*source.bounds()[2:4])
        if bounds is None:return False
        panels=copy.deepcopy(self.cfg['desktop_panels'])
        row=next(row for row in panels if row['id']==identity)
        row.update(merged=False,collapsed=False,geometry=bounds)
        anchor=self.runtime.layout.panel_update(identity,bounds,group=None)
        if not self.commit(history_title='拖出独立卡片',desktop_panels=panels,display_layout=anchor):return False
        self.sync_windows()
        return True

    def new_merge_group(self,name=None,identity=None):
        if name is None:
            name,accepted=QInputDialog.getText(None,'新建合并组','合并组名称：')
            if not accepted:return False
        name=name.strip()[:40]
        if not name or len(self.cfg['merge_groups'])>=64:return False
        self.save_visible_geometry()
        key=uuid.uuid4().hex;groups=copy.deepcopy(self.cfg['merge_groups'])
        row={'id':key,'name':name,'active':identity or '','geometry':[],'collapsed':False,'compact':True}
        if identity and identity in self.windows:row['geometry']=list(self.windows[identity].bounds())
        groups.append(row);panels=copy.deepcopy(self.cfg['desktop_panels'])
        if identity:next(model for model in panels if model['id']==identity).update(merged=True,merge_group=key)
        if not self.commit(history_title="新建合并组",merge_groups=groups,desktop_panels=panels,merged_panels=True,merge_initialized=True):return False
        self.sync_windows();return key

    def save_visible_geometry(self,persist=True):
        for window in self.windows.values():
            if window.isVisible(): window.store_geometry(persist=persist)

    def set_merged(self, identity, merged):
        self.save_visible_geometry()
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        # The first merge collects all cards into the default group.
        if merged and not self.cfg.get('merge_initialized') and not self.cfg['merged_panels']:
            for model in panels:model.update(merged=True,merge_group='default')
        next(model for model in panels if model['id']==identity)['merged'] = merged
        changes = dict(desktop_panels=panels)
        if merged: changes.update(merged_panels=True,merge_initialized=True)
        if not self.commit(history_title="合并或拆分卡片",**changes): return False
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
        if panels!=models and not self.commit(history_title="调整卡片顺序",desktop_panels=panels): return False
        for window in self.windows.values(): window.update_tabs(self.merged_models(window.identity))
        self.status('分组顺序已保存。')
        return True

    def select_page(self, identity):
        if not self.is_merged(identity) or identity not in {model['id'] for model in self.enabled_models()}:return
        current=self.windows.get(self.active_for(identity));target=self.windows.get(identity)
        if self.active_for(identity) == identity:return
        if current:current.store_geometry()
        if not self.update_group(identity,active=identity):return
        from usage_stats import record
        record(self.runtime,'panel_switch')
        if current and current.isVisible() and (target is None or not target.isVisible()):
            # The displayed group keeps its native window and wallpaper.
            current.page_transition.cancel();front=current.page_transition.capture() if not current.collapsed else None
            order=[model['id'] for model in self.merged_models(identity)]
            direction=1 if order.index(identity)>order.index(current.identity) else -1
            previous_view=current.model.get('view','small')
            previous = current.identity
            old_state = current.page_state()
            current.identity = identity
            if target is not None:
                new_state = target.page_state()
                target.identity = previous
                current.default_geometry, target.default_geometry = target.default_geometry, current.default_geometry
                self.windows[previous] = target
                target.resize_timer.stop()
                target.restore_page_state(old_state)
            else:
                self.dormant_pages[previous] = old_state
                new_state = self.dormant_pages.pop(identity, ('', set(), 0))
                current.default_geometry = self.default_geometries[identity]
                self.windows.pop(previous)
            self.windows[identity] = current
            current.resize_timer.stop()
            if previous_view!=current.model.get('view','small'):current.apply_options()
            else:current.update_identity_header()
            current.refresh_timer.stop()
            current.restore_page_state(new_state)
            self.sync_windows();current.list.doItemsLayout();current.list.verticalScrollBar().setValue(new_state[2])
            current.page_transition.begin(front,direction)
            current._interaction_motion.trigger('tab')
        else:self.sync_windows()

    def manage_groups(self):
        from panel_management import GroupDialog
        from ui_style import exec_dialog
        exec_dialog(GroupDialog(self))

    def release_hidden_windows(self):
        self.release_hidden_cards = True
        for identity, window in tuple(self.windows.items()):
            if not window.isVisible():
                self.dormant_pages[identity] = window.page_state()
                self.windows.pop(identity)
                window.dispose()

    def sync_windows(self):
        if self.closed: return
        from glass_panel import DesktopPanel
        models = {model['id']: model for model in self.cfg['desktop_panels']}
        self.dormant_pages = {key: state for key, state in self.dormant_pages.items() if key in models}
        self.default_geometries.clear()
        for identity in set(self.windows)-set(models):
            self.windows.pop(identity).dispose()
        enabled = self.enabled_models()
        active_by_group={}
        for group in self.cfg.get('merge_groups',[]):
            members=[model for model in self.merged_models() if self.group_id(model['id'])==group['id']]
            if not members:continue
            active=self.active_for(members[0]['id']);active_by_group[group['id']]=active
            if self.group_value(active,'active')!=active:self.update_group(active,active=active)
        geo = QApplication.primaryScreen().availableGeometry()
        from card_metrics import new_geometry
        from screen_layout import initial_card_factor, screen_records
        base_factor=initial_card_factor(list(geo.getRect()));cell_width=round(336*base_factor)
        columns = max(1, min(4, (geo.width()-32)//cell_width))
        rows = max(1, (len(models)+columns-1)//columns)
        height = max(round(180*base_factor), min(round(240*base_factor), (geo.height()-48)//rows-round(16*base_factor)))
        enabled_ids = {model['id'] for model in enabled}
        screens = screen_records() if any(not model.get('geometry') for model in models.values()) else []
        for index, model in enumerate(models.values()):
            identity = model['id']
            merged = self.is_merged(identity)
            presentation = self.group_id(identity) if merged else None
            visible = (self.shown and not self.blocked and self.cfg['panel_enabled'] and identity in enabled_ids
                       and (not merged or identity == active_by_group.get(presentation)))
            default = [geo.left()+20+(index % columns)*cell_width,
                       geo.top()+20+(index//columns)*(height+round(16*base_factor)), round(320*base_factor), height]
            if not model.get('geometry'):
                default = new_geometry(self.cfg, default, screens)
            self.default_geometries[identity] = default
            if identity not in self.windows:
                if not visible:
                    continue
                window = self.windows[identity] = DesktopPanel(self, identity, default)
                state = self.dormant_pages.pop(identity, None)
                if state is not None:
                    window.restore_page_state(state)
            window = self.windows[identity]
            window.update_tabs(self.merged_models(identity))
            if window.merged_view != merged or getattr(window,'merge_presentation',None)!=presentation:
                window.resize_timer.stop()
                window.manual_resize = False
            if visible and (not window.isVisible() or window.merged_view != merged or getattr(window,'merge_presentation',None)!=presentation):
                window.merged_view = merged
                window.merge_presentation=presentation
                window.apply_options()
                window.set_collapsed_geometry(self.group_value(identity,'collapsed') if merged else bool(model.get('collapsed')))
            if visible:window.render(prepare=True)
            window.setVisible(visible)
            if not visible:window.release_hidden_resources()
        if self.release_hidden_cards:
            self.release_hidden_windows()
        self.active_windows=active_by_group
        self.active_window = active_by_group.get('default') or next(iter(active_by_group.values()),None)
        layout=getattr(self.runtime,'layout',None)
        if layout:layout.ensure_profiles()
        active=(self.shown and self.cfg['panel_enabled'] and not self.blocked
                and any(window.isVisible() for window in self.windows.values()))
        mode=self.cfg.get('desktop_icon_mode','hide_all')
        if self.cfg.get('desktop_icons_override'):self.icons.set_visible(mode=='both')
        else:self.icons.set_enabled(active and mode=='hide_all')
        # Per-file hidden attributes also hide files in Explorer and remote copy.
        # Recover old records, but never set new file attributes for icon display.
        self.collected_icons.restore()
        if self.collected_icons.message:self.status(self.collected_icons.message)


    def toggle_desktop_icons(self):
        if self.closed:return False
        views=self.icons.views()
        if not views:return False
        visible=not any(self.icons.user.GetWindowLongW(hwnd,-16)&0x10000000 for hwnd in views)
        mode='both' if visible else 'hide_all'
        if not self.commit(desktop_icon_mode=mode,desktop_icons_override=True):return False
        self.icons.set_visible(visible)
        dialog=getattr(self.runtime.tray,'settings_dialog',None)
        if dialog:
            field=dialog.fields.get('desktop_icon_mode')
            if field:field.setCurrentIndex(field.findData(mode))
        return True

    def rows(self, identity):
        model = self.model(identity)
        excluded = set(model.get('excluded', []))
        rows = [dict(row) for row in self.cfg['desktop_entries'] if row['panel'] == identity]
        if self.cfg['desktop_auto_sort'] and model.get('extensions'):
            from desktop_catalog import effective_suffix
            candidates = {path_key(row['path']):row for row in self.cfg['desktop_entries']+self.scanned_rows if row.get('source')=='desktop'}
            def matches(row):
                key=path_key(row['path'])
                if key in self.file_metadata:
                    state=self.file_metadata[key]
                    return state is not None and state[4] in model['extensions']
                return effective_suffix(row['path']) in model['extensions'] and os.path.exists(row['path'])
            rows += [dict(row, panel=identity, pinned=False) for row in candidates.values() if matches(row)]
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
                state=self.file_metadata.get(path_key(row['path']))
                if state is not None:modified=state[0]/1_000_000_000
                elif path_key(row['path']) in self.file_metadata:modified=0
                else:
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
        if self.commit(history_title="置顶收纳项目",desktop_entries=entries): self.sync_windows()

    def model(self, identity):
        return next(model for model in self.cfg['desktop_panels'] if model['id'] == identity)

    def update_panel(self, identity, _layout=None, **values):
        panels = copy.deepcopy(self.cfg['desktop_panels'])
        from panel_preferences import KEYS,without_overrides
        shared={key:value for key,value in values.items() if key in KEYS}
        local={key:value for key,value in values.items() if key not in KEYS}
        if self.is_merged(identity):local.pop('fold',None)
        panels=without_overrides(panels)
        next(model for model in panels if model['id']==identity).update(local)
        changes={'desktop_panels':panels,**{'panel_'+key:value for key,value in shared.items()}}
        if 'material' in shared and shared['material']!=self.cfg['panel_material']:
            from appearance_presets import material_design
            changes['card_design']=material_design(shared['material'],self.cfg.get('card_design','aurora'))
        if 'fold' in values and self.is_merged(identity):
            groups=copy.deepcopy(self.cfg['merge_groups']);group=next(row for row in groups if row['id']==self.group_id(identity));group['fold']=values['fold']
            changes['merge_groups']=groups
        layout=getattr(self.runtime,'layout',None)
        if _layout is None and 'geometry' in values and layout:
            _layout=layout.panel_update(identity,values['geometry'])
        if isinstance(_layout,dict):changes['display_layout']=_layout
        if self.is_merged(identity) and 'collapsed' in values:changes.update(self.group_changes(identity,collapsed=values['collapsed']))
        history_title='编辑卡片' if set(values)&{'name','extensions','enabled','merged','merge_group','excluded','pinned_paths'} else None
        if self.commit(history_title=history_title,**changes):
            if shared:
                for window in self.windows.values():
                    window.apply_options();window.collapse_timer.stop()
                    if window.isVisible() and window.option('auto_hide'):window.collapse_timer.start()
                self.shared_settings_changed.emit()
            elif identity in self.windows:self.windows[identity].apply_options()
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
        if self.commit(history_title="添加收纳引用",desktop_entries=entries, desktop_excluded=excluded, desktop_panels=panels):
            self.sync_windows()
            self.status('已收纳 %d 项，原文件保持原位。' % len(paths))
            return True
        return False

    def move_entries(self, keys, identity):
        entries = [dict(row, panel=identity, source='manual') if path_key(row['path']) in keys else dict(row)
                   for row in self.cfg['desktop_entries']]
        if self.commit(history_title="移动收纳引用",desktop_entries=entries): self.sync_windows()

    def remove_entries(self, keys, identity=None):
        if identity is not None:
            panels = copy.deepcopy(self.cfg['desktop_panels'])
            model = next(model for model in panels if model['id']==identity)
            model['excluded'] = list(dict.fromkeys(model.get('excluded',[])+list(keys)))
            entries = [dict(row) for row in self.cfg['desktop_entries'] if row['panel']!=identity or path_key(row['path']) not in keys]
            if self.commit(history_title="移除收纳引用",desktop_panels=panels, desktop_entries=entries): self.sync_windows()
            return
        entries = [dict(row) for row in self.cfg['desktop_entries'] if path_key(row['path']) not in keys]
        excluded = list(dict.fromkeys(self.cfg['desktop_excluded']+list(keys)))
        if self.commit(history_title="移除收纳引用",desktop_entries=entries, desktop_excluded=excluded):
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
        if self.commit(history_title='新建卡片',desktop_panels=self.cfg['desktop_panels']+[{'id': identity, 'name': name, 'extensions': list(extensions or [])}], panels_visible=True):
            self.shown = True
            self.sync_windows()
            self.schedule_scan()
            from usage_stats import record
            record(self.runtime,'panel_new')
            return identity

    def delete_panel(self, identity):
        if QMessageBox.question(self.windows.get(identity), '移除面板',
                '移除此面板及其中的引用？原文件和其他面板不受影响。默认分组可在分组管理中重新开启。') != QMessageBox.Yes:
            return
        disabled = list(self.cfg['disabled_categories'])
        if identity in dict(CATEGORIES) and identity not in disabled: disabled.append(identity)
        if self.commit(history_title='移除卡片',desktop_panels=[model for model in self.cfg['desktop_panels'] if model['id'] != identity],
                       desktop_entries=[row for row in self.cfg['desktop_entries'] if row['panel'] != identity],
                       disabled_categories=disabled):
            self.sync_windows()

    def reveal(self):
        if not self.commit(panels_visible=True):return False
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

    def restore_layout_state(self):
        """Apply a saved layout's fold state without reopening native windows."""
        if self.closed:return
        for identity,window in self.windows.items():
            merged=self.is_merged(identity)
            window.expand_timer.stop();window.collapse_timer.stop()
            window.merged_view=merged
            window.merge_presentation=self.group_id(identity) if merged else None
            collapsed=self.group_value(identity,'collapsed') if merged else bool(self.model(identity).get('collapsed'))
            window.set_collapsed_geometry(bool(collapsed))
            window.manual_resize=False;window.resize_timer.stop()
            if window.isVisible():
                window.render(prepare=True)
                if window.option('auto_hide'):window.collapse_timer.start()

    def reposition(self):
        for window in self.windows.values():
            window.restoring=True
            try:
                window.apply_options()
                window.set_collapsed_geometry(window.collapsed)
                window.manual_resize=False
                window.resize_timer.stop()
            finally:window.restoring=False

    def close(self,save_geometry=True,wait_ms=300):
        if self.closed: return
        if save_geometry:
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
        self.collected_icons.close()
        self.scan_timer.stop();self.reconcile_timer.stop()
        if self.watcher.directories(): self.watcher.removePaths(self.watcher.directories())
        if self.worker: self.worker.close(wait_ms=wait_ms)
        for window in self.windows.values(): window.dispose()
        self.windows.clear()
