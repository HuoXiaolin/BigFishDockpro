"""Poll only configured receivers, independently of the fast resource sampler."""
from PyQt5.QtCore import QObject, QTimer

from bluetooth_gauge import HUES
from resource_peripherals import PeripheralProbe, merge_readings


class PeripheralMonitor(QObject):
    page_size = 3

    def __init__(self, owner, profiles):
        super().__init__(owner)
        self.owner = owner
        self.profiles = profiles
        self.rows = []
        self.page = 0
        self.status = '正在读取 2.4G 外设…'
        self.failures = 0
        self.queued = False
        self.closed = False
        self.probe = PeripheralProbe(self)
        self.probe.completed.connect(self.finished)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(0)

    def pages(self):
        return max(1, (len(self.rows) + self.page_size - 1) // self.page_size)

    def group(self):
        start = self.page * self.page_size
        return self.rows[start:start + self.page_size]

    def turn(self):
        self.page = (self.page + 1) % self.pages()
        self.owner.peripherals_changed()

    def device_changed(self):
        if self.probe.busy:
            self.queued = True
        else:
            self.timer.start(800)

    def refresh(self):
        if self.closed:
            return
        if self.probe.busy:
            self.queued = True
            return
        self.timer.stop()
        if not self.probe.read(self.profiles) and not self.timer.isActive():
            self.finished('read', [], '暂时无法启动外设读取。')

    def finished(self, operation, readings, error):
        if self.closed or operation != 'read':
            return
        rows = merge_readings(self.profiles, readings, self.rows)
        for index, row in enumerate(rows):
            row['ink'] = HUES[index % len(HUES)]
        status = error or '暂无外设电量'
        changed = rows != self.rows or status != self.status
        self.rows, self.status = rows, status
        self.page = min(self.page, self.pages() - 1)
        if any(row['state'] in ('active', 'charging') and row['level'] is not None for row in rows):
            self.failures = 0
        else:
            self.failures = min(3, self.failures + 1)
        delay = min(300, 60 * 2 ** max(0, self.failures - 1))
        self.timer.start(800 if self.queued else delay * 1000)
        self.queued = False
        if changed:
            self.owner.peripherals_changed()

    def close(self):
        self.closed = True
        self.timer.stop()
        self.probe.close()
        self.deleteLater()
