"""Native shell appearance pages in the existing Qt settings hierarchy."""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPalette, QPen
from PyQt5.QtWidgets import QWidget
from ui_style import label, button
from settings_design import section_marker
from background_contrast import blend
from shell_appearance import system_appearance
from shell_appearance_model import NOTIFICATION_PARTS, appearance, panel_ink


class ShellPreview(QWidget):
    def __init__(self, dialog, kind):
        super().__init__(dialog)
        from weakref import proxy
        self.dialog = proxy(dialog)
        self.kind = kind
        self.setMinimumHeight(138)
        self.setMaximumHeight(138)
        self.setAccessibleName('开始菜单外观示意' if kind == 'start' else '通知与快捷面板外观示意')

    def refresh(self, *args):
        from PyQt5 import sip
        if sip.isdeleted(self):
            return
        prefix = 'shell_' + self.kind + '_'
        field = self.dialog.fields.get(prefix + 'source')
        if field is None:
            return
        custom = field.currentData() == 'custom'
        material = self.dialog.fields[prefix + 'material'].currentData()
        _, transparent = system_appearance(self.dialog.api)
        for key in ('material', 'theme', 'color', 'highlight'):
            self.dialog.fields[prefix + key].setEnabled(custom)
        self.dialog.fields[prefix + 'opacity'].setEnabled(custom and transparent and material != 'clear')
        self.dialog.fields[prefix + 'blur'].setEnabled(custom and transparent and material not in ('clear', 'solid', 'mica'))
        self.update()

    def paintEvent(self, event):
        cfg = dict(self.dialog.tray.cfg, **self.dialog.draft_values())
        style = appearance(cfg, self.kind, *system_appearance(self.dialog.api))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1, 1, self.width()-2, self.height()-2)
        tint = QColor(style['color'])
        tint.setAlpha(round(style['opacity'] * 255 / 100))
        painter.setBrush(tint)
        painter.setPen(QPen(QColor('#75a8c9'), 1))
        painter.drawRoundedRect(rect, 12, 12)
        backdrop = self.palette().color(QPalette.Window).getRgb()[:3]
        system_text_light = None
        if style['text_mode'] == 'system':
            from taskbar_text import system_mode
            mode = system_mode()
            system_text_light = None if mode is None else bool(mode)
        painter.setPen(QColor(panel_ink(style, blend(style['color'], backdrop, tint.alphaF()), system_text_light)))
        w = self.width()
        if self.kind == 'start':
            painter.drawText(18, 26, '所有应用')
            painter.drawText(int(w*.58), 26, '已固定')
            for index, title in enumerate(('文件资源管理器', '设置', '计算器')):
                painter.drawText(24, 55+26*index, title)
            for row in range(2):
                for col in range(3):
                    painter.fillRect(int(w*.59)+col*int(w*.105), 43+row*39, 22, 22, QColor('#5cb8df'))
        else:
            painter.drawText(18, 26, '快速设置 · 媒体控制')
            painter.drawText(int(w*.56), 26, '通知 · 日历')
            for col, title in enumerate(('Wi-Fi', '蓝牙', '音量')):
                painter.drawText(20+col*int(w*.15), 64, title)
            painter.drawText(20, 102, '保留系统按钮与交互')
            painter.drawText(int(w*.56), 64, '在系统原位置弹出')
            painter.drawText(int(w*.56), 102, '统一材质与配色')


def build_page(dialog, form, kind):
    prefix = 'shell_' + kind + '_'
    section_marker(form, '系统入口与样式' if kind == 'start' else '系统面板')
    dialog.add_field(form, prefix + 'enabled')
    if kind == 'notifications':
        for part, _ in NOTIFICATION_PARTS:
            dialog.add_field(form, prefix + part)
        dialog.fields[prefix + 'tray_overflow'].setToolTip('任务栏上箭头打开的隐藏图标面板使用此页外观。需要任务栏效果组件。')
        dialog.fields[prefix + 'taskbar_menu'].setToolTip('右键任务栏空白处打开的系统菜单使用此页外观。需要任务栏效果组件。')
    text = ('点击系统开始按钮或按 Win 键打开。玻璃网格左侧显示应用列表，右侧显示固定应用。'
            if kind == 'start' else 'Win+A 打开快速设置与媒体控制，Win+N 打开通知与日历；通知弹窗保留系统位置。')
    form.addRow(label(text, 'muted'))
    section_marker(form, '材质与背景')
    dialog.add_field(form, prefix + 'source')
    form.addRow(label('跟随本应用时，材质、配色和明暗模式取自 Dock 外观。', 'muted'))
    for key in ('material', 'theme', 'text_mode', 'color', 'opacity', 'blur', 'highlight'):
        dialog.add_field(form, prefix + key)
    form.addRow(label('底色 0% 时只保留所选模糊效果，100% 时背景为纯色。Windows 关闭透明效果时使用纯色。', 'muted'))
    preview = ShellPreview(dialog, kind)
    form.addRow(preview)
    form.addRow(label('玻璃网格外观示意。' if kind == 'start' else '通知与快捷面板外观示意。', 'muted'))
    for key in ('source', 'material', 'theme', 'text_mode', 'color', 'opacity', 'blur', 'highlight'):
        dialog.change_signal(dialog.fields[prefix + key]).connect(preview.refresh)
    # Fields receive their saved values after the page builder returns.
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(0, preview.refresh)
    runtime = getattr(dialog.tray, 'runtime', None)
    backend = getattr(runtime, 'shell_appearance', None)
    section_marker(form, '应用状态')
    if backend:
        status = label(backend.status, 'muted')
        form.addRow(status)
        backend.changed.connect(status.setText)
        if kind == 'notifications' and runtime.taskbar is not None:
            from taskbar_xaml import taskbar_surfaces_requested
            taskbar_status = label('', 'muted')
            form.addRow(taskbar_status)
            def update_taskbar_status(message):
                taskbar_status.setText(message)
                taskbar_status.setVisible(taskbar_surfaces_requested(runtime.dock.cfg))
            update_taskbar_status(runtime.taskbar.status)
            runtime.taskbar.changed.connect(update_taskbar_status)
        def retry():
            backend.retry()
            if kind == 'notifications':
                from taskbar_xaml import taskbar_surfaces_requested
                if taskbar_surfaces_requested(runtime.dock.cfg):
                    runtime.taskbar.retry()
        dialog.action_row(form, '当前配置', button('重试接入', retry))
    def restore():
        dialog.set_draft_values({prefix + 'enabled': False})
        dialog.status.setText('已关闭此页美化选项，保存设置后恢复系统外观。')
    dialog.action_row(form, '系统外观', button('恢复此页默认外观', restore))
    form.addRow(label('保存后应用。退出本应用时恢复系统外观，无需安装第三方美化软件。Windows 更新后若控件不兼容，可关闭此页美化。', 'muted'))
