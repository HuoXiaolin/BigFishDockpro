from ui_style import compact_dialog, compact_px
"""Staged batch additions/removals: cancel never changes the saved Dock."""
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent, QPoint
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QFileDialog, QApplication, QTabBar)
from app_catalog import discover_apps, merge_items, path_key, launch_identity, unique_apps
from running_apps import discover_running_apps
from ui_style import label, button, SettingsHeader, SettingsGrip


class Discovery(QThread):
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.ready.emit(discover_apps(cancelled=self.isInterruptionRequested))
        except Exception as error:
            self.failed.emit(str(error))


class RunningDiscovery(QThread):
    ready=pyqtSignal(int,object)
    failed=pyqtSignal(int,str)
    def __init__(self,generation,parent=None):
        super().__init__(parent);self.generation=generation
    def run(self):
        try:
            apps=discover_running_apps(cancelled=self.isInterruptionRequested)
            if not self.isInterruptionRequested():self.ready.emit(self.generation,apps)
        except Exception as error:
            if not self.isInterruptionRequested():self.failed.emit(self.generation,str(error))


class BatchDialog(QDialog):
    def __init__(self, importer):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setProperty('compactDialog', True)
        self.importer = importer
        self.apps = []
        self.running_apps=[];self.running_worker=None;self.running_generation=0;self.running_rescan=False;self.running_error=''
        self.catalog_released = False
        self.selected = [set(), set(), set(), set()]
        self.queries = ['', '', '', '']
        self.mode = 0
        self.pending_add = []
        self.pending_remove = set()
        self.setWindowTitle('应用批量管理 · 大肥鱼Dock')
        self.resize(740, 580)
        self.setMinimumSize(620, 480)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 12, 18, 12)
        body.setSpacing(10)
        self.header = SettingsHeader(self, '应用批量管理')
        body.addWidget(self.header)
        body.addWidget(label('添加常用应用，或从 Dock 移除固定入口。原文件始终保留。', 'muted'))
        self.tabs = QTabBar()
        self.tabs.addTab('添加应用')
        self.tabs.addTab('已固定应用')
        self.tabs.addTab('Windows 应用')
        self.tabs.addTab('正在运行')
        self.tabs.setExpanding(False)
        body.addWidget(self.tabs)
        self.query = QLineEdit()
        self.query.setPlaceholderText('搜索应用名称或路径')
        self.query.setAccessibleName('搜索应用名称或路径')
        body.addWidget(self.query)
        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(button('全选当前结果', self.select_visible))
        tools.addWidget(button('取消选择', self.clear_selection))
        tools.addStretch()
        self.refresh_running_button=button('刷新运行列表',self.refresh_running)
        self.refresh_running_button.setVisible(False)
        tools.addWidget(self.refresh_running_button)
        self.pick = button('从文件添加…', self.pick_files)
        tools.addWidget(self.pick)
        body.addLayout(tools)
        self.list = QListWidget()
        self.list.setIconSize(QSize(28, 28))
        self.icon_rows = set()
        self.icon_timer = QTimer(self)
        self.icon_timer.setSingleShot(True)
        self.icon_timer.setInterval(16)
        self.icon_timer.timeout.connect(self.load_visible_icons)
        self.list.verticalScrollBar().valueChanged.connect(lambda: self.icon_timer.start())
        self.list.viewport().installEventFilter(self)
        body.addWidget(self.list, 1)
        self.empty = label('正在扫描开始菜单、桌面及 Windows 应用…', 'muted')
        body.addWidget(self.empty)
        self.status = label('', 'muted')
        body.addWidget(self.status)
        actions = QHBoxLayout()
        self.action = button('添加所选', self.perform)
        actions.addWidget(self.action)
        actions.addStretch()
        self.cancel = button('关闭', self.reject)
        actions.addWidget(self.cancel)
        self.save_button = button('保存更改', self.commit, 'primary')
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        self.grip = SettingsGrip(self)
        self.grip.setFixedSize(12, 18)
        actions.addWidget(self.grip, 0, Qt.AlignBottom)
        body.addLayout(actions)
        self.pending = label('尚无待保存的更改', 'muted')
        body.addWidget(self.pending)
        self.query.textChanged.connect(self.render)
        self.tabs.currentChanged.connect(self.switch_mode)
        self.list.itemChanged.connect(self.checked)
        self.worker = Discovery()
        self.worker.ready.connect(self.discovered)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.release_if_idle)
        self.worker.start()
        compact_dialog(self)
        from idle_resources import watch
        watch(self)

    def release_idle_resources(self):
        if not self.release_memory():return False
        self.worker.deleteLater()
        if self.importer.dialog is self:self.importer.dialog=None
        self.deleteLater()
        return True

    def refresh_running(self):
        self.running_error=''
        self.running_generation+=1
        if self.running_worker and self.running_worker.isRunning():
            self.running_rescan=True;self.running_worker.requestInterruption();return
        self.running_rescan=False
        self.running_worker=RunningDiscovery(self.running_generation,self)
        worker=self.running_worker
        worker.ready.connect(self.running_discovered)
        worker.failed.connect(self.running_failed)
        worker.finished.connect(lambda:self.running_finished(worker))
        self.refresh_running_button.setEnabled(False)
        self.empty.setText('正在读取有窗口的运行应用…')
        worker.start()

    def running_discovered(self,generation,apps):
        if generation!=self.running_generation:return
        self.running_apps=apps
        keys={path_key(app['path']) for app in apps}
        self.selected[3].intersection_update(keys)
        if self.mode==3:self.render()

    def running_failed(self,generation,message):
        if generation!=self.running_generation:return
        self.running_error='运行列表读取失败，请点击刷新重试。'
        self.importer.log('运行应用读取失败: '+message)
        if self.mode==3:self.status.setText('运行列表读取失败，请点击刷新重试。')

    def running_finished(self,worker):
        if worker is self.running_worker:self.running_worker=None
        worker.deleteLater()
        self.refresh_running_button.setEnabled(True)
        if self.running_rescan and self.isVisible() and self.mode==3:self.refresh_running()
        elif self.mode==3 and self.isVisible():self.render()
        self.release_if_idle()

    def scan_failed(self, message):
        self.empty.setText('应用扫描失败，可从文件添加。详细信息已记录到日志。')
        self.importer.log('应用扫描失败: ' + message)

    def discovered(self, apps):
        self.apps = apps
        if not (self.importer.dock.lite_mode and not self.isVisible()): self.render()
        self.release_if_idle()

    def release_if_idle(self):
        if self.importer.dock.lite_mode: self.release_memory()

    def release_memory(self):
        if self.isVisible() or self.worker.isRunning() or (self.running_worker and self.running_worker.isRunning()): return False
        self.icon_timer.stop()
        self.list.clear()
        self.icon_rows.clear()
        self.apps = []
        self.running_apps=[]
        self.catalog_released = True
        self.selected = [set(), set(), set(), set()]
        return True

    def rescan(self):
        self.worker.deleteLater()
        self.worker = Discovery()
        self.worker.ready.connect(self.discovered)
        self.worker.failed.connect(self.scan_failed)
        self.worker.finished.connect(self.release_if_idle)
        self.worker.start()

    def reveal(self):
        if self.catalog_released:
            self.catalog_released = False
            self.rescan()
        self.pending_add.clear()
        self.pending_remove.clear()
        self.selected = [set(), set(), set(), set()]
        self.render()
        self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        self.query.setFocus()
        if self.mode==3:self.refresh_running()

    def switch_mode(self, mode):
        self.queries[self.mode] = self.query.text()
        self.mode = mode
        self.query.blockSignals(True)
        self.query.setText(self.queries[mode])
        self.query.blockSignals(False)
        self.pick.setVisible(mode == 0)
        self.refresh_running_button.setVisible(mode==3)
        self.action.setText('移除所选' if mode == 1 else '添加所选')
        self.action.setProperty('role', 'danger' if mode == 1 else '')
        self.action.style().unpolish(self.action)
        self.action.style().polish(self.action)
        self.render()
        if mode==3:self.refresh_running()

    def draft_items(self):
        existing = [i for i in self.importer.dock.cfg['items']
                    if not i.get('path') or path_key(i['path']) not in self.pending_remove]
        return merge_items(existing, self.pending_add)[0]

    def render(self):
        current = self.list.currentItem()
        current_key = path_key(current.data(Qt.UserRole)['path']) if current else None
        scroll = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        query = self.query.text().casefold()
        draft = self.draft_items()
        pinned = {launch_identity(i['path']) for i in draft if i.get('path')}
        rows = unique_apps([i for i in draft if i.get('path')]) if self.mode == 1 else unique_apps(self.running_apps) if self.mode==3 else unique_apps(
            [i for i in self.apps if (i.get('column') == 'windows') == (self.mode == 2)])
        for app in rows:
            if query not in app['name'].casefold() and query not in app['path'].casefold():
                continue
            key = path_key(app['path'])
            title = app['name']
            already_pinned = launch_identity(app['path']) in pinned
            if self.mode != 1 and already_pinned:
                title += '  · 已固定'
            item = QListWidgetItem(title)
            item.setToolTip(app['path']+ ('\n合并显示 %d 个重复入口，移除时一并取消固定。' % len(app['_paths']) if self.mode == 1 and len(app['_paths'])>1 else ''))
            item.setData(Qt.UserRole, app)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if self.mode != 1 and already_pinned:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                self.selected[self.mode].discard(key)
            item.setCheckState(Qt.Checked if key in self.selected[self.mode] else Qt.Unchecked)
            self.list.addItem(item)
            if key == current_key:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self.icon_rows.clear()
        self.list.verticalScrollBar().setValue(scroll)
        self.load_visible_icons()
        self.icon_timer.start()
        self.empty.setVisible(self.list.count() == 0)
        self.empty.setText(('正在读取运行应用…' if self.running_worker and self.running_worker.isRunning() else (self.running_error or '未找到匹配的运行应用，可点击刷新。')) if self.mode==3 else '正在扫描应用…' if self.mode != 1 and self.worker.isRunning() else
                           ('没有匹配的已固定应用。' if self.mode == 1 else '没有匹配的应用，可更换关键词。'))
        self.update_status()

    def eventFilter(self, watched, event):
        if watched is self.list.viewport() and event.type() == QEvent.Resize:
            self.icon_timer.start()
        return super().eventFilter(watched, event)

    def load_visible_icons(self):
        count = self.list.count()
        if not count: return
        viewport = self.list.viewport()
        first = max(0, self.list.indexAt(QPoint(max(1,viewport.width()//2),10)).row())
        visible = max(1, viewport.height()//max(1,self.list.sizeHintForRow(first)))+2
        wanted = set(range(max(0,first-2), min(count,first+visible+2)))
        self.list.blockSignals(True)
        for index in self.icon_rows-wanted:
            item = self.list.item(index)
            if item: item.setIcon(QIcon())
        for index in wanted:
            item = self.list.item(index)
            if item.icon().isNull():
                app = item.data(Qt.UserRole)
                item.setIcon(QIcon(self.importer.dock.icons.get(app.get('icon') or app['path'],56,bool(app.get('icon')))))
        self.icon_rows = wanted
        self.list.blockSignals(False)

    def visible_selected(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).flags() & Qt.ItemIsEnabled and
                path_key(self.list.item(i).data(Qt.UserRole)['path']) in self.selected[self.mode]]

    def update_status(self):
        visible = len(self.visible_selected())
        hidden = len(self.selected[self.mode]) - visible
        self.status.setText(('有窗口的软件（含最小化） · ' if self.mode==3 else '')+'当前结果 %d 个 · 当前已选 %d 个%s' %
            (self.list.count(), visible, (' · 筛选外已选 %d 个（本次不操作）' % hidden) if hidden else ''))
        self.pending.setText('待保存：添加 %d 个，移除 %d 个。取消或关闭将放弃这些改动。' %
                             (len(self.pending_add), len(self.pending_remove)) if self.pending_add or self.pending_remove else '尚无待保存的更改')
        if self.mode==3 and self.running_error:self.status.setText(self.running_error)
        self.action.setEnabled(visible > 0)
        self.save_button.setEnabled(bool(self.pending_add or self.pending_remove))

    def checked(self, item):
        key = path_key(item.data(Qt.UserRole)['path'])
        if item.checkState() == Qt.Checked:
            self.selected[self.mode].add(key)
        else:
            self.selected[self.mode].discard(key)
        self.update_status()

    def select_visible(self):
        self.selected[self.mode].update(path_key(self.list.item(i).data(Qt.UserRole)['path'])
            for i in range(self.list.count()) if self.list.item(i).flags() & Qt.ItemIsEnabled)
        self.render()

    def clear_selection(self):
        self.selected[self.mode].clear()
        self.render()

    def stage_add(self, candidates):
        draft, added, duplicates, invalid = merge_items(self.draft_items(), candidates)
        baseline = {path_key(i['path']) for i in self.importer.dock.cfg['items'] if i.get('path')}
        # Re-adding an existing removed entry cancels that pending removal.
        valid_keys = {path_key(i['path']) for i in draft if i.get('path')}
        self.pending_remove -= valid_keys
        self.pending_add = [i for i in draft if i.get('path') and path_key(i['path']) not in baseline]
        return '已暂存 %d 个 · 重复 %d 个 · 无效 %d 个' % (added, duplicates, invalid)

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, '批量添加应用', self.importer.last_directory,
            '程序和快捷方式 (*.exe *.lnk *.url *.appref-ms *.bat *.cmd *.msc *.ps1);;所有文件 (*)')
        if files:
            import os
            self.importer.last_directory = os.path.dirname(files[0])
            report = self.stage_add([{'path': f} for f in files])
            self.render()
            self.status.setText(report)

    def perform(self):
        candidates = self.visible_selected()
        keys = {path_key(a['path']) for a in candidates}
        if self.mode != 1:
            report = self.stage_add(candidates)
        else:
            keys = {path_key(path) for app in candidates for path in app.get('_paths', [app['path']])}
            self.pending_add = [i for i in self.pending_add if path_key(i['path']) not in keys]
            baseline = {path_key(i['path']) for i in self.importer.dock.cfg['items'] if i.get('path')}
            self.pending_remove.update(keys & baseline)
            report = '已暂存移除 %d 个入口，原文件不会删除。' % len(keys)
        self.selected[self.mode] -= keys
        self.render()
        self.status.setText(report)

    def commit(self):
        existing = [i for i in self.importer.dock.cfg['items']
                    if not i.get('path') or path_key(i['path']) not in self.pending_remove]
        items, _, _, _ = merge_items(existing, self.pending_add)
        if self.importer.apply_items(items):
            self.pending_add.clear()
            self.pending_remove.clear()
            self.render()
            self.pending.setText('更改已保存，可继续添加或移除应用。')

    def reject(self):
        self.running_generation+=1;self.running_rescan=False;self.running_apps=[]
        if self.running_worker:self.running_worker.requestInterruption()
        if self.mode==3:self.icon_timer.stop();self.list.clear();self.icon_rows.clear()
        self.pending_add.clear()
        self.pending_remove.clear()
        self.selected = [set(), set(), set(), set()]
        super().reject()
        self.release_if_idle()


class BatchImporter:
    def __init__(self, dock, tray, save, log=lambda message: None):
        self.dock, self.tray, self.save, self.log = dock, tray, save, log
        self.dialog = None
        self.last_directory = ''
        QApplication.instance().aboutToQuit.connect(self.close)

    def show(self):
        from usage_stats import record
        record(self.dock,'batch_open')
        if self.dialog is None:
            self.dialog = BatchDialog(self)
        if self.dialog.isVisible():
            if self.dialog.isMinimized(): self.dialog.showNormal()
            self.dialog.raise_()
            self.dialog.activateWindow()
        else:
            self.dialog.reveal()

    def apply_items(self, items):
        candidate = dict(self.dock.cfg, items=items)
        if self.save(candidate) is False:
            self.tray.showMessage('保存失败', '无法保存 Dock 配置，改动尚未应用。请检查数据目录权限。', self.tray.icon(), 4000)
            return False
        self.dock.cfg['items'] = items
        self.dock.reload()
        if self.dialog and self.dialog.isVisible():
            self.dialog.render()
        return True

    def pin(self, candidates):
        items, added, duplicates, invalid = merge_items(self.dock.cfg['items'], candidates)
        if added and not self.apply_items(items):
            return '保存失败，未添加应用。'
        report = '添加 %d 个 · 重复 %d 个 · 无效 %d 个' % (added, duplicates, invalid)
        self.tray.showMessage('添加应用', report, self.tray.icon(), 2500)
        return report

    def release_memory(self):
        return self.dialog.release_memory() if self.dialog else False

    def close(self):
        if self.dialog:
            self.dialog.worker.requestInterruption()
            self.dialog.worker.wait(27000)
            if self.dialog.running_worker:
                self.dialog.running_worker.requestInterruption();self.dialog.running_worker.wait(5000)
            self.dialog.reject()
