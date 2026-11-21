"""One settings control for the device scopes used by monitoring and the pets."""
from PyQt5.QtCore import QSignalBlocker

from resource_options import DEVICE_SOURCES, valid_device
from ui_style import ModernComboBox


def device_choices(service, metric, selected=''):
    if metric == 'network':
        kind, automatic = 'network_utilization', '自动 · 已连接网卡汇总'
    elif metric in DEVICE_SOURCES:
        kind, automatic = metric, DEVICE_SOURCES[metric][2]
    else:
        return {'': '整机'}
    choices = {'': automatic}
    if service:
        choices.update((key, item.name) for key, item in service.hardware.get(kind, {}).items())
    if valid_device(selected, kind) and selected not in choices:
        choices[selected] = f'已选{DEVICE_SOURCES[kind][1]}（未检测到）'
    return choices


class DevicePicker(ModernComboBox):
    def __init__(self, service, metric, selected='', parent=None):
        super().__init__(parent)
        self.service = service
        self.metric = None
        self.set_metric(metric, selected)
        if service:
            service.hardware_changed.connect(self.refresh_choices)

    def set_metric(self, metric, selected=None):
        if selected is None:
            selected = self.currentData() if metric == self.metric else ''
        self.metric = metric
        self.select_device(selected)
        self.discover()

    def select_device(self, selected):
        choices = device_choices(self.service, self.metric, selected)
        if choices == {self.itemData(i): self.itemText(i) for i in range(self.count())}:
            self.setCurrentIndex(max(0, self.findData(selected)))
            return
        blocker = QSignalBlocker(self)
        self.clear()
        for key, name in choices.items():
            self.addItem(name, key)
        self.setCurrentIndex(max(0, self.findData(selected)))
        del blocker
        if self._popup is not None and self._popup.isVisible():
            super().showPopup()

    def refresh_choices(self):
        self.select_device(self.currentData())

    def discover(self):
        if self.service:
            self.service.discover_hardware('network_utilization' if self.metric == 'network' else self.metric)

    def showPopup(self):
        self.discover()
        super().showPopup()
