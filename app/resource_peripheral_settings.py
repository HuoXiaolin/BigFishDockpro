"""Discover, test and manage 2.4 GHz peripheral battery readers."""
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHeaderView, QHBoxLayout, QInputDialog, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout,
)

from background_worker import BackgroundWorker
from resource_peripherals import (
    DIAGNOSTICS_FILENAME, FIELDS, MAX_PROFILE_BYTES, MAX_PROFILES, PROFILE_FILENAME,
    STATE_LABELS, PeripheralProbe, bind_profiles, diagnostics_prompt, load_profile_file,
    normalize_alias, normalize_profiles, parse_profile_bytes, save_diagnostics,
    save_diagnostics_prompt, save_profile_file,
)
from ui_style import AlignedMenu, SettingsHeader, button, compact_dialog
from update_sources import REPOSITORY


CATALOG_FILE = PROFILE_FILENAME
CATALOG_URL = REPOSITORY + '/releases/latest/download/' + CATALOG_FILE
CATALOG_LIMIT = 128
ASSET_HOSTS = {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
ID_ROLE = Qt.UserRole
STATE_HINTS = {
    'sleeping': '设备已休眠。唤醒设备后再次试读。',
    'offline': '设备未连接。请检查接收器并唤醒设备。',
    'busy': '接收器可能被其他软件占用。关闭厂商软件后重试。',
    'unavailable': '暂时未取得电量。请唤醒设备，确认已切换到 2.4G 模式后重试。',
    'stale': '当前显示的是上次读数。唤醒设备后再次试读。',
}


def _catalog_redirect(target):
    try:
        target = urlsplit(target)
        if target.scheme != 'https' or target.port not in (None, 443) or target.username is not None:
            return False
    except ValueError:
        return False
    if target.hostname in ASSET_HOSTS:
        return True
    repo = urlsplit(REPOSITORY)
    return (target.hostname == repo.hostname
            and target.path.startswith(repo.path + '/releases/download/')
            and target.path.endswith('/' + CATALOG_FILE))


class CatalogWorker(BackgroundWorker):
    ready = pyqtSignal(object, str)

    def run(self):
        import http.client
        import ssl
        from time import monotonic
        from urllib.error import HTTPError
        from urllib.parse import urljoin
        from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *_):
                return None

        url = CATALOG_URL
        deadline = monotonic() + 9
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_default_certs()
            opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
            for _ in range(5):
                if self.isInterruptionRequested():
                    return
                timeout = min(4, deadline - monotonic())
                if timeout <= 0:
                    raise TimeoutError()
                request = Request(url, headers={'User-Agent': 'BigFishDockpro', 'Accept': 'application/json'})
                try:
                    response = opener.open(request, timeout=timeout)
                except HTTPError as error:
                    with error:
                        if error.code == 404:
                            self._result([], '发布频道暂无独立适配文件。当前可使用本机适配或导入配置。')
                            return
                        redirect = error.headers.get('Location')
                        if error.code not in (301, 302, 303, 307, 308) or not redirect:
                            raise
                    url = urljoin(url, redirect)
                    if not _catalog_redirect(url):
                        break
                    continue
                with response:
                    data = bytearray()
                    while len(data) <= MAX_PROFILE_BYTES:
                        if self.isInterruptionRequested():
                            return
                        if monotonic() >= deadline:
                            raise TimeoutError()
                        chunk = response.read1(min(8192, MAX_PROFILE_BYTES + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                try:
                    catalog = parse_profile_bytes(bytes(data), limit=CATALOG_LIMIT)
                except ValueError:
                    self._result([], '发布频道的适配文件无效，可继续使用本机适配。')
                else:
                    self._result(catalog, '')
                return
            self._result([], '无法验证适配文件的来源，可继续使用本机适配。')
        except TimeoutError:
            self._result([], '检查超时，可继续使用本机适配。')
        except (OSError, ValueError, http.client.HTTPException):
            self._result([], '无法连接适配发布频道，可继续使用本机适配。')

    def _result(self, rows, error):
        if not self.isInterruptionRequested():
            self.ready.emit(rows, error)


def _name(row):
    return row.get('alias') or row.get('name') or '{:04X}:{:04X}'.format(row['vid'], row['pid'])


def _trial(row):
    protocol = row.get('protocol') or row.get('compatible_protocol')
    return dict(row, protocol=protocol) if protocol else None


def _has_live_level(reading):
    return (reading is not None and reading['state'] in ('active', 'charging')
            and reading['level'] is not None)


def _read_level(reading):
    if not reading or reading['level'] is None:
        return '—'
    return ('约 ' if reading.get('approximate') else '') + str(reading['level']) + '%'


def _signature(row):
    return tuple(row[key] for key in FIELDS)


class PeripheralSettings(QDialog):
    """Edits stay local to the dialog until the user saves the device list."""

    def __init__(self, parent, profiles):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setWindowTitle('2.4G 外设电量')
        self.resize(600, 380)
        self.setProperty('simpleForms', True)
        self.profiles = normalize_profiles(profiles)
        self.original_profiles = self.profiles
        self.closing = False
        self.probe = PeripheralProbe(self)
        self.probe.completed.connect(self._completed)
        self.scanned = []
        self.has_scanned = False
        self.catalog = []
        self.readings = {}
        self.rows = {}
        self.pending = None
        self.import_batch = []
        self.catalog_job = None
        self.catalog_timeout = QTimer(self)
        self.catalog_timeout.setSingleShot(True)
        self.catalog_timeout.timeout.connect(lambda: self._end_catalog('检查超时，可继续使用本机适配。'))

        layout = QVBoxLayout(self)
        layout.addWidget(SettingsHeader(self, self.windowTitle()))
        hint = QLabel('接上 USB 接收器，切换到 2.4G 模式并唤醒设备。试读成功后即可添加。')
        hint.setWordWrap(True)
        hint.setObjectName('Subtle')
        layout.addWidget(hint)
        tools = QHBoxLayout()
        self.scan_button = button('扫描设备', self.scan)
        self.more_button = QPushButton('更多操作')
        self.more_button.setAutoDefault(False)
        self.menu = AlignedMenu(self.more_button)
        self.catalog_action = self.menu.addAction('检查适配更新', self.check_catalog)
        self.import_action = self.menu.addAction('导入适配配置…', self.import_profiles)
        self.export_action = self.menu.addAction('导出已添加设备的适配…', self.export_profiles)
        self.diagnostics_action = self.menu.addAction('导出扫描诊断与提示词…', self.export_diagnostics)
        self.copy_prompt_action = self.menu.addAction('复制适配提示词', self.copy_prompt)
        self.more_button.setMenu(self.menu)
        tools.addWidget(self.scan_button)
        tools.addWidget(self.more_button)
        tools.addStretch()
        self.count = QLabel()
        self.count.setObjectName('Subtle')
        tools.addWidget(self.count)
        layout.addLayout(tools)

        self.table = QTreeWidget()
        self.table.setAccessibleName('扫描到的外设及已添加设备')
        self.table.setHeaderLabels(['设备', '电量', '状态'])
        self.table.setRootIsDecorated(False)
        self.table.setItemsExpandable(False)
        self.table.setUniformRowHeights(True)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.header().setStretchLastSection(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.currentItemChanged.connect(self._update_controls)
        self.table.itemDoubleClicked.connect(lambda *_: self.preview())
        layout.addWidget(self.table, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setObjectName('Subtle')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('操作结果')
        layout.addWidget(self.status)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.PlainText)
        self.detail.setAccessibleName('当前设备详情')
        layout.addWidget(self.detail)

        actions = QHBoxLayout()
        self.preview_button = button('试读电量', self.preview)
        self.add_button = button('添加', self.add_profile)
        self.alias_button = button('设备别名…', self.edit_alias)
        self.remove_button = button('移除', self.remove_profile)
        self.save_button = button('保存', self.accept, 'primary')
        for widget in (self.preview_button, self.add_button, self.alias_button, self.remove_button):
            actions.addWidget(widget)
        actions.addStretch()
        actions.addWidget(button('取消', self.reject))
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        compact_dialog(self)
        self._populate()
        QTimer.singleShot(0, self.scan)

    def _selected(self):
        item = self.table.currentItem()
        return self.rows.get(item.data(0, ID_ROLE)) if item is not None else None

    def _known_rows(self):
        rows = {row['device_id']: row for row in self.scanned}
        if not self.catalog:
            return rows
        candidates = {}
        for row in self.scanned:
            candidates.setdefault(_signature(row), []).append(row)
        for profile in self.catalog:
            matches = candidates.get(_signature(profile))
            if not matches:
                continue
            try:
                row, = bind_profiles([profile], matches)
            except ValueError:
                continue
            key = row['device_id']
            if key in rows and not rows[key].get('protocol'):
                rows[key] = row
        return rows

    def _populate(self, select=None):
        previous = self._selected()
        select = select or (previous and previous['device_id'])
        scroll = self.table.verticalScrollBar().value()
        saved = {row['device_id']: row for row in self.profiles}
        found = self._known_rows()
        ordered = list(saved.values())
        signatures = {}
        for row in found.values():
            if _trial(row):
                signature = (_signature(row), _trial(row)['protocol'])
                signatures.setdefault(signature, []).append(row['device_id'])
        reattached = set()
        for row in self.profiles:
            if row['device_id'] not in found:
                ids = signatures.get((_signature(row), row['protocol']), ())
                if len(ids) == 1:
                    reattached.add(ids[0])
        unknown_receivers = set()
        for key, row in found.items():
            if key in saved or key in reattached:
                continue
            if not _trial(row):
                physical = row.get('receiver_id') or (row['vid'], row['pid'], row.get('name'))
                if physical in unknown_receivers:
                    continue
                unknown_receivers.add(physical)
            ordered.append(row)
        self.rows = {row['device_id']: row for row in ordered}
        self.table.blockSignals(True)
        self.table.clear()
        selected_item = None
        for row in ordered:
            key = row['device_id']
            reading = self.readings.get(key)
            status = STATE_LABELS.get(reading['state'], '暂不可读') if reading else (
                '已添加' if key in saved else ('待试读' if _trial(row) else '尚无适配'))
            if reading and key in saved:
                status = '已添加 · ' + status
            item = QTreeWidgetItem([_name(row), _read_level(reading), status])
            item.setData(0, ID_ROLE, key)
            tooltip = f'<span>{escape(_name(row))}</span>'
            if row.get('alias'):
                tooltip += f'<br>设备名称：{escape(row["name"])}'
            item.setToolTip(0, tooltip)
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            if reading and reading['state'] == 'charging':
                light = self.palette().color(QPalette.Base).lightness() > 120
                item.setForeground(2, QColor('#0b7258' if light else '#78d9b1'))
            self.table.addTopLevelItem(item)
            if key == select:
                selected_item = item
        if not ordered:
            message = '未找到可显示的设备' if self.has_scanned else '正在准备设备扫描'
            item = QTreeWidgetItem([message, '—', ''])
            item.setFlags(Qt.NoItemFlags)
            self.table.addTopLevelItem(item)
        else:
            if selected_item is None:
                selected_item = next((self.table.topLevelItem(index)
                                      for index, row in enumerate(ordered) if _trial(row)),
                                     self.table.topLevelItem(0))
            self.table.setCurrentItem(selected_item)
            self.table.verticalScrollBar().setValue(scroll)
        self.table.blockSignals(False)
        self.count.setText(f'已添加 {len(self.profiles)}/{MAX_PROFILES}')
        self._update_controls()

    def _update_controls(self, *_):
        row = self._selected()
        key = row['device_id'] if row else ''
        saved = any(profile['device_id'] == key for profile in self.profiles)
        available = self.pending is None
        reading = self.readings.get(key)
        self.scan_button.setEnabled(available)
        self.more_button.setEnabled(available)
        self.scan_button.setText('正在扫描…' if self.pending == 'scan' else
                                 ('重新扫描' if self.has_scanned else '扫描设备'))
        self.preview_button.setEnabled(available and bool(row and _trial(row)))
        self.add_button.setEnabled(available and not saved and len(self.profiles) < MAX_PROFILES
                                   and _has_live_level(reading))
        self.remove_button.setEnabled(available and saved)
        self.alias_button.setEnabled(available and saved)
        self.save_button.setEnabled(available and self.profiles != self.original_profiles)
        self.export_action.setEnabled(bool(self.profiles))
        self.diagnostics_action.setEnabled(self.has_scanned)
        self.copy_prompt_action.setEnabled(self.has_scanned and bool(self.scanned))
        if row is None:
            details = '若设备未出现，请重插接收器后扫描。'
        elif reading and reading['state'] in STATE_HINTS:
            details = STATE_HINTS[reading['state']]
        elif _has_live_level(reading):
            details = '请核对电量，确认后添加。' if not saved else '可在资源卡片查看电量和状态。'
        elif not _trial(row):
            details = ('此接口没有已知的电量查询方式。可以检查适配更新、导入配置，或导出诊断。'
                       f"  USB {row['vid']:04X}:{row['pid']:04X}")
        else:
            details = '试读会查询选中设备的电量和状态。'
        self.detail.setText(details)

    def _start(self, operation, label, start):
        if self.closing or self.pending is not None:
            return False
        self.pending = operation
        self.status.setText(label)
        self._update_controls()
        if start():
            return True
        if self.pending == operation:
            self.pending = None
            self.status.setText('读取器正在结束上一项操作，请稍后重试。')
            self._update_controls()
        return False

    def scan(self):
        self._start('scan', '正在查找已接入的 USB 接收器…', self.probe.scan)

    def preview(self):
        row = self._selected()
        trial = _trial(row) if row else None
        if trial and self.pending is None:
            self.readings.pop(trial['device_id'], None)
            self._populate(trial['device_id'])
            self._start('preview', '正在读取 ' + _name(trial) + '…', lambda: self.probe.read([trial]))

    def _completed(self, operation, rows, error):
        pending = self.pending
        if pending not in ('scan', 'preview', 'import'):
            return
        if (operation == 'scan') != (pending == 'scan'):
            return
        self.pending = None
        if error:
            self.import_batch = []
            self.status.setText(error)
        elif operation == 'scan':
            self.scanned = rows
            self.has_scanned = True
            self.readings.clear()
            self.status.setText('扫描完成。选择设备后试读电量。' if rows else
                                '未检测到可查询的接收器。请确认设备已连接后重新扫描。')
        else:
            self.readings.update({row['id']: row for row in rows})
            if pending == 'import':
                self._finish_import(rows)
            else:
                reading = rows[0] if rows else None
                self.status.setText('试读成功。' if _has_live_level(reading) else
                                    '试读未取得可用电量。')
        self._populate()

    def add_profile(self):
        row = self._selected()
        if row is None or not self.add_button.isEnabled():
            return
        profile = _trial(row)
        if profile is None:
            return
        self.profiles = normalize_profiles([*self.profiles, profile])
        self.status.setText('已加入设备列表。点击「保存」应用。')
        self._populate(row['device_id'])

    def remove_profile(self):
        row = self._selected()
        if row is None or not self.remove_button.isEnabled():
            return
        self.profiles = [item for item in self.profiles if item['device_id'] != row['device_id']]
        self.status.setText('已从设备列表移除。点击「保存」应用。')
        self._populate(row['device_id'])

    def edit_alias(self):
        row = self._selected()
        if row is None or not self.alias_button.isEnabled():
            return
        alias, accepted = QInputDialog.getText(self, '设备别名', '显示名称（留空恢复设备名称）',
                                               text=row.get('alias', ''))
        if not accepted:
            return
        try:
            alias = normalize_alias(alias, strict=True)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        key = row['device_id']
        updated = normalize_profiles([dict(profile, alias=alias) if profile['device_id']==key else profile
                                      for profile in self.profiles], strict=True)
        if updated != self.profiles:
            self.profiles = updated
            self.status.setText('已更新别名。点击「保存」应用。')
            self._populate(key)

    def import_profiles(self):
        if not self.has_scanned:
            self.status.setText('请先扫描，导入后会在本机试读匹配的设备。')
            return
        file, _ = QFileDialog.getOpenFileName(self, '导入外设适配', '', '适配配置 (*.json)')
        if not file:
            return
        try:
            rows = bind_profiles(load_profile_file(Path(file)), self.scanned)
            current = {row['device_id']: row for row in self.profiles}
            rows = [row for row in rows if row['device_id'] not in current or
                    ('alias' in row and row['alias'] != current[row['device_id']].get('alias'))]
            if len(current.keys() | {row['device_id'] for row in rows}) > MAX_PROFILES:
                raise ValueError(f'最多添加 {MAX_PROFILES} 台设备。')
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        if not rows:
            self.status.setText('配置中的设备均已添加。')
            return
        self.import_batch = rows
        if not self._start('import', '正在试读导入配置中的设备…', lambda: self.probe.read(rows)):
            self.import_batch = []

    def _finish_import(self, readings):
        rows, self.import_batch = self.import_batch, []
        current = {row['id']: row for row in readings}
        passed = [row for row in rows if _has_live_level(current.get(row['device_id']))]
        current_profiles = {row['device_id']: row for row in self.profiles}
        for row in passed:
            key = row['device_id']
            if key not in current_profiles:
                current_profiles[key] = row
            elif 'alias' in row:
                current_profiles[key] = dict(current_profiles[key], alias=row['alias'])
        self.profiles = normalize_profiles(list(current_profiles.values()))
        failures = len(rows) - len(passed)
        summary = f'{len(passed)} 台试读成功。'
        if failures:
            summary += f' {failures} 台未取得电量，可唤醒设备后重试。'
        if passed:
            summary += ' 点击「保存」应用。'
        self.status.setText(summary)

    def export_profiles(self):
        file, _ = QFileDialog.getSaveFileName(self, '导出外设适配', CATALOG_FILE, '适配配置 (*.json)')
        if file:
            try:
                save_profile_file(Path(file), self.profiles)
                self.status.setText('已导出适配配置。')
            except (ValueError, OSError) as exc:
                self.status.setText(str(exc))

    def export_diagnostics(self):
        file, _ = QFileDialog.getSaveFileName(self, '导出外设诊断与提示词', DIAGNOSTICS_FILENAME,
                                             '诊断文件 (*.json)')
        if not file:
            return
        path = Path(file)
        try:
            save_diagnostics(path, self.scanned)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        try:
            prompt_file = save_diagnostics_prompt(path, self.adaptation_prompt(path.name))
        except (ValueError, OSError) as exc:
            self.status.setText(f'诊断已导出，提示词保存失败：{exc}。可使用「复制适配提示词」。')
            return
        self.status.setText(f'已导出诊断和 {prompt_file.name}。将两份文件交给 Agent，按提示生成配置后导入。')

    def adaptation_prompt(self, filename=DIAGNOSTICS_FILENAME):
        row = self._selected()
        return diagnostics_prompt(self.scanned, row['device_id'] if row else None, filename)

    def copy_prompt(self):
        QApplication.clipboard().setText(self.adaptation_prompt())
        self.status.setText('已复制适配提示词，可交给 Agent。')

    def check_catalog(self):
        if self.closing or self.pending is not None:
            return
        self.pending = 'catalog'
        self.status.setText('正在检查发布频道的外设适配…')
        self._update_controls()
        self.catalog_timeout.start(10000)
        self.catalog_job = CatalogWorker()
        self.catalog_job.ready.connect(self._catalog_finished)
        self.catalog_job.start()

    def _catalog_finished(self, rows, error):
        if self.sender() is not self.catalog_job:
            return
        if not error:
            self.catalog = rows
        self._end_catalog(error or '适配已载入。请扫描或选择已连接的设备试读。')

    def _end_catalog(self, label):
        self.catalog_timeout.stop()
        worker, self.catalog_job = self.catalog_job, None
        if worker is not None:
            worker.requestInterruption()
            worker.deleteLater()
        self.pending = None
        if label:
            self.status.setText(label)
            self._populate()

    def done(self, result):
        self.closing = True
        self._end_catalog('')
        self.probe.close()
        super().done(result)
