"""Settings for existing upstream features; edits apply only on Save."""
import os
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QSpinBox, QCheckBox, QComboBox, QScrollArea, QApplication, QLineEdit, QColorDialog,
    QListWidget, QStackedWidget, QSizePolicy)
from ui_style import (label, button, apply_theme, ModernComboBox, ModernSpinBox,
                      ModernCheckBox, SettingsHeader, SettingsGrip, ThemeSwatches)
from app_version import VERSION, AUTHOR, PROJECT_URL
from appearance_presets import DOCK_PRESETS, MATERIALS, COLOR_MODES


class SettingsPages(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.nav = QListWidget()
        self.nav.setObjectName('SettingsNav')
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setFixedWidth(132)
        self.pages = QStackedWidget()
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)

    def addTab(self, page, name):
        self.pages.addWidget(page)
        self.nav.addItem(name)
        if self.nav.currentRow() < 0: self.nav.setCurrentRow(0)

    def count(self): return self.pages.count()
    def currentIndex(self): return self.nav.currentRow()
    def setCurrentIndex(self, index): self.nav.setCurrentRow(index)

    def resizeEvent(self, event):
        self.nav.setFixedWidth(118 if self.width() < 620 else 132)
        super().resizeEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, tray, api):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.setObjectName('SettingsDialog')
        self.setProperty('compactDialog', True)
        self.tray, self.api = tray, api
        self.fields = {}
        self.applying_dock_preset = False
        self.setWindowTitle('设置 · 大肥鱼Dock')
        self.resize(800, 640)
        self.setMinimumSize(640, 480)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 12, 18, 12)
        body.setSpacing(12)
        self.header = SettingsHeader(self)
        body.addWidget(self.header)
        body.addWidget(label('管理 Dock、桌面收纳与运行偏好，保存后生效。', 'muted'))
        self.tabs = SettingsPages()
        body.addWidget(self.tabs)
        appearance = self.section('外观设置')
        self.dock_preset = ModernComboBox()
        self.dock_preset.addItem('自定义 / 保留当前设置')
        self.dock_preset.addItems([name for name, _ in DOCK_PRESETS])
        appearance.addRow(self.field_label('外观预设'), self.dock_preset)
        self.combo(appearance, 'dock_material', '材质', MATERIALS)
        self.combo(appearance, 'theme', '颜色模式', COLOR_MODES)
        self.color(appearance, 'theme_color', '主题色')
        self.number(appearance, 'dock_highlight', '高光（%）', 0, 100)
        self.number(appearance, 'transparency', '不透明度（%）', 0, 100)
        self.number(appearance, 'blur_px', '模糊强度', 3, 30)
        self.check(appearance, 'glass', '启用背景模糊')
        self.check(appearance, 'clear_background', '背景全透明（仅保留图标与文字）')
        self.combo(appearance, 'blur_mode', '背景抓取', api.BLUR_MODES)
        self.number(appearance, 'icon_size', '图标大小（像素）', 20, 256)
        self.check(appearance, 'magnify', '鼠标悬停时放大图标')
        self.combo(appearance, 'bump_level', '拉伸鼓包', [(title, key) for key, title, _ in api.BUMP_LEVELS])
        layout = appearance
        self.combo(layout, 'position', '窗口位置', api.POSITIONS)
        self.number(layout, 'custom_bottom', '自定义距底部（像素）', 0, 2000)
        self.number(layout, 'bottom_margin', '边缘距离（像素）', 0, 200)
        self.combo(layout, 'layer', '窗口层级', api.LAYERS)
        self.check(layout, 'show_name', '悬停时显示应用名称')
        self.check(layout, 'sep_split', '分隔符切开玻璃背景')
        self.combo(layout, 'lang', '原 Dock 菜单语言', [(name, key) for name, key in api.LANGS])
        self.check(layout, 'screen_corners', '屏幕圆角美化（仅游戏模式隐藏，鼠标穿透）')
        self.number(layout, 'corner_radius', '屏幕圆角半径（像素）', 0, 120)

        panel = self.section('桌面收纳')
        panel.addRow(label('这里设置面板的默认外观；各面板可单独覆盖。', 'muted'))
        self.check(panel, 'panel_enabled', '启用桌面悬浮收纳面板')
        self.check(panel, 'desktop_auto_sort', '自动将桌面内容按类型归入多个面板')
        self.combo(panel, 'panel_material', '材质', MATERIALS)
        self.combo(panel, 'panel_theme', '颜色模式', COLOR_MODES)
        self.color(panel, 'panel_color', '主题色')
        self.number(panel, 'panel_highlight', '高光（%）', 0, 100)
        self.number(panel, 'panel_opacity', '不透明度（%）', 0, 100)
        self.number(panel, 'panel_blur', '模糊强度', 2, 30)
        self.check(panel, 'panel_locked', '默认锁定面板位置与大小')
        self.check(panel, 'panel_auto_hide', '默认鼠标离开后自动收起')
        self.combo(panel, 'panel_collapse_style', '默认收起形状', [('胶囊', 'capsule'), ('方条', 'bar')])
        self.number(panel, 'panel_capsule_ratio', '胶囊宽度比例（%）', 30, 100)
        panel.addRow(label('这里设置面板默认外观；材质决定表面质感，颜色模式决定明暗，主题色只控制配色。各面板可独立覆盖。', 'muted'))
        panel.addRow(label('比例相对于面板展开宽度，最窄 180 像素；每个面板的外观设置中可单独调整。方条保持展开宽度。', 'muted'))
        panel.addRow(label('标题处拖动，右下角调整大小；每个面板可独立锁定、设置外观并保存位置。收起仍常驻桌面，点击或悬停展开。沿用 Dock 液态玻璃绘制；模糊不支持时保留半透明。', 'muted'))
        panel.addRow(button('新建桌面面板', lambda: self.tray.runtime.panels.new_panel()))
        panel.addRow(button('分组与合并管理', lambda: self.tray.runtime.panels.manage_groups()))
        panel.addRow(label('可开启或关闭默认分组、管理自定义格式规则，选择部分卡片合并并在顶部切换，其余卡片独立显示。','muted'))

        apps = self.section('应用管理')
        apps.addRow(label('Dock 的应用批量管理独立保留；桌面收纳面板不再与 Dock 共用列表。', 'muted'))
        apps.addRow(button('打开应用批量管理', self.open_batch))
        self.check(apps, 'reorder', '允许拖动 Dock 图标排序')
        self.check(apps, 'running_dots', '显示 Dock 应用的运行标记')
        apps.addRow(label('桌面内容按应用、文件夹、文档、图片、影音、压缩包等分类，也能手动拖入指定面板。启用面板后自动隐藏系统桌面图标，关闭面板或退出时恢复原显示状态。收纳仅保存引用，原文件不移动、不删除。', 'muted'))

        running = self.section('启动与运行')
        self.check(running, 'lite_enabled', '启用自动精简：关闭设置 1 分钟后进入')
        running.addRow(label('精简时保留基础 Dock、拖入、托盘与静态圆角；桌面面板收为方条或胶囊，目录变动仍自动分类。暂停屏幕抓取、运行扫描、位置与全屏轮询。打开设置恢复完整模式。', 'muted'))
        self.check(running, 'hide_tray', '隐藏托盘图标（可从 Dock 右键打开设置）')
        self.check(running, 'autostart', '开机自动启动（恢复上次显示与运行状态）')
        self.startup_status = label('', 'muted')
        running.addRow(self.startup_status)
        self.startup_path = QLineEdit()
        self.startup_path.setReadOnly(True)
        self.startup_path.setAccessibleName('已登记的自启动路径')
        running.addRow(self.field_label('已登记路径'), self.startup_path)
        self.current_startup_path = QLineEdit(api.SCRIPT_PATH)
        self.current_startup_path.setReadOnly(True)
        self.current_startup_path.setAccessibleName('当前运行文件路径')
        running.addRow(self.field_label('当前运行路径'), self.current_startup_path)
        startup_actions = QHBoxLayout()
        self.startup_check = button('检测自启动路径', self.check_startup)
        self.startup_repair = button('修复并启用自启动', self.repair_startup)
        startup_actions.addWidget(self.startup_check)
        startup_actions.addWidget(self.startup_repair)
        startup_actions.addStretch()
        running.addRow('', startup_actions)
        running.addRow(label('修复会立即将当前运行版本登记为开机自启动，其他未保存的设置保持不变。', 'muted'))
        self.combo(running, 'startup_priority', '进程优先级', [('低（节省后台竞争）', 'low'), ('普通', 'normal'), ('较高（非实时）', 'high')])
        self.number(running, 'startup_delay', '登录后延迟（秒）', 0, 300)
        running.addRow(label('延迟仅作用于开机自启动，手动启动不等待。进程优先级不保证 Windows 登录启动顺序。', 'muted'))
        self.check(running, 'game_mode', '游戏模式：隐藏 Dock、面板和圆角')
        self.check(running, 'fullscreen_detection', '前台全屏应用自动隐藏 Dock 和面板')
        running.addRow(label('全屏检测每 1.5 秒一次，普通最大化窗口不算全屏；不区分游戏与视频，因此不隐藏圆角。游戏时可从托盘开启游戏模式。精简模式暂停检测。', 'muted'))

        updates = self.section('更新设置')
        self.check(updates, 'check_updates_on_start', '启动时检查更新')
        self.check(updates, 'update_use_proxy', '使用系统 / 环境代理')
        self.text(updates, 'update_source', '本项目版本清单（HTTPS）')
        updates.addRow(label('当前没有预设更新源，请填写本项目的版本清单地址。检查到新版本后可打开下载页面，由你决定是否更新。', 'muted'))
        self.update_status = label('尚未配置更新源', 'muted')
        updates.addRow(self.update_status)
        updates.addRow(button('检查更新', self.check_update))
        self.update_link = button('打开新版本下载页面', self.open_update_link)
        self.update_link.setEnabled(False)
        updates.addRow(self.update_link)
        info = self.section('关于与数据')
        info.addRow(label('大肥鱼Dock  ' + VERSION, 'section'))
        info.addRow(label('用液态玻璃 Dock 启动常用应用，用桌面悬浮面板分类收纳文件与快捷方式。', 'muted'))
        info.addRow('维护作者', label(AUTHOR))
        info.addRow('原项目版权', label('WWQ / WKaleXD · MIT，保留上游许可'))
        info.addRow('平台', label('Windows 10 / 11 · x64'))
        info.addRow('第三方许可', label('PyQt5 GPLv3；Qt、Python 等许可见发行文件 licenses。'))
        self.project = label('')
        self.project.setOpenExternalLinks(True)
        info.addRow('项目地址', self.project)
        upstream = label('<a href="https://github.com/WKaleXD/iOS-style-Dock">查看原始基础项目</a>')
        upstream.setOpenExternalLinks(True)
        info.addRow('基础项目', upstream)
        path = label(api.CONFIG_DIR)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.addRow('数据目录', path)
        info.addRow(label('config.json 保存 Dock、桌面收纳记录与面板布局；dock.log 为日志。desktop_visibility.json 是临时图标恢复记录，正常退出会清除。卸载默认保留个人配置。', 'muted'))
        info.addRow(button('打开数据目录', self.open_data))
        self.status = label('未保存的修改会在关闭时放弃。', 'muted')
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.status, 1)
        actions.addWidget(button('关闭', self.reject))
        self.save = button('保存设置', self.commit, 'primary')
        self.save.setDefault(True)
        actions.addWidget(self.save)
        self.grip = SettingsGrip(self)
        self.grip.setFixedSize(12, 18)
        self.grip.setAccessibleName('调整设置窗口大小')
        actions.addWidget(self.grip, 0, Qt.AlignBottom)
        body.addLayout(actions)
        self.fields['position'].currentIndexChanged.connect(self.position_changed)
        self.dock_preset.currentIndexChanged.connect(self.apply_dock_preset)
        self.fields['dock_material'].currentIndexChanged.connect(self.material_changed)
        for key in DOCK_PRESETS[0][1]:
            field = self.fields[key]
            signal = (field.currentIndexChanged if isinstance(field, QComboBox) else
                      field.valueChanged if isinstance(field, QSpinBox) else
                      field.textChanged if isinstance(field, QLineEdit) else field.toggled)
            signal.connect(self.customize_dock)
        runtime = getattr(tray, 'runtime', None)
        if runtime:
            runtime.updater.changed.connect(self.update_changed)

    def section(self, name):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(2, 8, 12, 12)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.addRow(label(name, 'page-title'))
        scroll.setWidget(page)
        self.tabs.addTab(scroll, name)
        return form

    def field_label(self, title):
        widget = label(title)
        widget.setFixedWidth(130)
        widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return widget

    def combo(self, form, key, title, options):
        field = ModernComboBox()
        for name, value in options:
            field.addItem(name, value)
        field.setAccessibleName(title)
        self.fields[key] = field
        form.addRow(self.field_label(title), field)

    def number(self, form, key, title, lower, upper):
        field = ModernSpinBox()
        field.setRange(lower, upper)
        field.setAccessibleName(title)
        self.fields[key] = field
        form.addRow(self.field_label(title), field)

    def text(self, form, key, title):
        field = QLineEdit()
        field.setAccessibleName(title)
        self.fields[key] = field
        form.addRow(self.field_label(title), field)

    def color(self, form, key, title):
        container = QVBoxLayout()
        container.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        field = QLineEdit()
        field.setPlaceholderText('默认色 / #RRGGBB')
        field.setAccessibleName(title)
        self.fields[key] = field
        row.addWidget(field, 1)
        def choose():
            value = QColorDialog.getColor(QColor(field.text() or '#b8d9ef'), self, title)
            if value.isValid(): field.setText(value.name())
        row.addWidget(button('选择', choose))
        row.addWidget(button('默认', field.clear))
        container.addLayout(row)
        container.addWidget(ThemeSwatches(field))
        form.addRow(self.field_label(title), container)

    def material_changed(self):
        if not self.applying_dock_preset and self.fields['dock_material'].currentData()!='clear' and self.fields['clear_background'].isChecked():
            self.fields['clear_background'].setChecked(False)
            if self.fields['transparency'].value()==0: self.fields['transparency'].setValue(38)
            if self.fields['dock_highlight'].value()==0: self.fields['dock_highlight'].setValue(45)

    def apply_dock_preset(self, index):
        if index <= 0: return
        self.applying_dock_preset = True
        for key, value in DOCK_PRESETS[index-1][1].items():
            field = self.fields[key]
            if isinstance(field, QComboBox): field.setCurrentIndex(field.findData(value))
            elif isinstance(field, QSpinBox): field.setValue(100-value if key == 'transparency' else value)
            elif isinstance(field, QLineEdit): field.setText(value)
            else: field.setChecked(value)
        self.applying_dock_preset = False

    def customize_dock(self, *args):
        if not self.applying_dock_preset: self.dock_preset.setCurrentIndex(0)

    def check(self, form, key, title):
        field = ModernCheckBox(title)
        self.fields[key] = field
        form.addRow('', field)

    def position_changed(self):
        self.fields['custom_bottom'].setEnabled(self.fields['position'].currentData() == 'custom')

    def reveal(self):
        link_color = QApplication.palette().color(QPalette.Link).name()
        self.project.setText('<a style="color:%s" href="%s">BigFishDockpro</a>' % (link_color, PROJECT_URL))
        cfg = self.tray.cfg
        self.applying_dock_preset = True
        for key, field in self.fields.items():
            if isinstance(field, QComboBox):
                field.setCurrentIndex(max(0, field.findData(cfg[key])))
            elif isinstance(field, QSpinBox):
                field.setValue(100-cfg[key] if key == 'transparency' else cfg[key])
            elif isinstance(field, QLineEdit):
                field.setText(cfg[key])
            else:
                field.setChecked(bool(cfg[key]))
        self.applying_dock_preset = False
        matching = next((index for index, (_, values) in enumerate(DOCK_PRESETS, 1)
                         if all(cfg[key] == value for key, value in values.items())), 0)
        self.dock_preset.blockSignals(True)
        self.dock_preset.setCurrentIndex(matching)
        self.dock_preset.blockSignals(False)
        self.position_changed()
        runtime = getattr(self.tray, 'runtime', None)
        if runtime:
            self.update_changed(runtime.updater.message)
        self.check_startup()
        self.status.setText('未保存的修改会在关闭时放弃。')
        self.move(QApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()

    def open_data(self):
        try:
            os.makedirs(self.api.CONFIG_DIR, exist_ok=True)
            os.startfile(self.api.CONFIG_DIR)
        except OSError as error:
            self.api.log('打开数据目录失败: ' + str(error))
            self.status.setText('无法打开数据目录，请检查目录是否可用。')

    def commit(self):
        import re
        cfg = dict(self.tray.cfg)
        for key, field in self.fields.items():
            cfg[key] = (field.currentData() if isinstance(field, QComboBox) else
                        field.value() if isinstance(field, QSpinBox) else
                        field.text().strip() if isinstance(field, QLineEdit) else field.isChecked())
            if key == 'transparency': cfg[key] = 100-cfg[key]
        for key in ('theme_color', 'panel_color'):
            if cfg[key] and not re.fullmatch(r'#[0-9a-fA-F]{6}', cfg[key]):
                self.status.setText('主题色请使用 #RRGGBB，或留空使用默认色。')
                return
            cfg[key] = cfg[key].lower()
        if cfg['update_source'] and not cfg['update_source'].startswith('https://'):
            self.status.setText('更新源必须是 HTTPS 版本清单地址。')
            return
        startup_changed = cfg['autostart'] != self.tray.cfg['autostart']
        if startup_changed and not self.api.set_autostart(cfg['autostart']):
            self.status.setText('启动项保存失败，设置尚未应用。请查看日志。')
            return
        if self.api.save_config(cfg) is False:
            if startup_changed:
                self.api.set_autostart(self.tray.cfg['autostart'])
            self.status.setText('配置保存失败，设置尚未应用。请检查数据目录权限。')
            return
        self.tray.cfg.update(cfg)
        self.api.set_lang(cfg['lang'])
        self.tray.dock._sys_light = self.api.system_is_light()
        apply_theme(QApplication.instance(), self.tray.dock.is_light())
        self.tray.dock.reload()
        self.tray.dock.apply_layer()
        if hasattr(self.tray, 'runtime'):
            self.tray.runtime.apply_settings()
        self.check_startup()
        self.status.setText('设置已保存并生效，可继续调整。')

    def check_startup(self):
        from startup_service import inspect_startup
        result = inspect_startup(self.api)
        self.startup_status.setText(result['message'])
        self.startup_path.setText(result['path'] or '未登记')
        self.startup_path.setCursorPosition(0)
        self.startup_path.setToolTip(str(result['command']))
        self.current_startup_path.setText(self.api.SCRIPT_PATH)
        self.current_startup_path.setCursorPosition(0)
        self.current_startup_path.setToolTip(result['expected'])
        return result

    def repair_startup(self):
        from startup_service import repair_startup
        success, message = repair_startup(self.api, self.tray.cfg)
        if success:
            self.tray.cfg['autostart'] = True
            self.fields['autostart'].setChecked(True)
        self.check_startup()
        self.startup_status.setText(message)
        self.status.setText(message)

    def open_batch(self):
        runtime = getattr(self.tray, 'runtime', None)
        if runtime:
            runtime.show_batch()
        else:
            self.tray.importer.show()

    def check_update(self):
        if self.fields['update_source'].text().strip() != self.tray.cfg['update_source'] or self.fields['update_use_proxy'].isChecked() != self.tray.cfg['update_use_proxy']:
            self.update_status.setText('请先保存更新设置，再执行检查。')
            return
        if hasattr(self.tray, 'runtime'):
            self.tray.runtime.updater.check()

    def update_changed(self, message):
        self.update_status.setText(message)
        self.update_link.setEnabled(bool(self.tray.runtime.updater.release_url))

    def open_update_link(self):
        if hasattr(self.tray, 'runtime') and self.tray.runtime.updater.release_url:
            self.tray.dock.launch(self.tray.runtime.updater.release_url)
