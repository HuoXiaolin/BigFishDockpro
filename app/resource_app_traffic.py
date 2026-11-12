"""Collect Windows application traffic only while recording is enabled."""
from datetime import date, datetime, time as day_time, timedelta
import json
import math
import os
from pathlib import Path
import sqlite3
import time

from PyQt5.QtCore import QObject, QProcess, QTimer

from resource_probes import binary


FRAME_LIMIT = 256 * 1024
APP_LIMIT = 1024


class AppTrafficHistory:
    def __init__(self, path):
        self.path = Path(path)
        self.connection = None
        self.pending = {}
        self.cache = {}
        self.error = ''
        self.saved = time.monotonic()

    def database(self):
        if self.connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=.1)
            try:
                connection.execute('CREATE TABLE IF NOT EXISTS traffic (day TEXT, id TEXT, name TEXT, '
                                   'down INTEGER, up INTEGER, PRIMARY KEY(day,id)) WITHOUT ROWID')
            except sqlite3.Error:
                connection.close()
                raise
            self.connection = connection
        return self.connection

    def add(self, rows, day):
        for key, name, down, up in rows:
            if not (down or up):
                continue
            old = self.pending.get((day, key))
            if old is None and len(self.pending) >= APP_LIMIT * 4:
                key, name = 'unattributed', '其他应用'
                old = self.pending.get((day, key))
            self.pending[day, key] = (name, down + (old[1] if old else 0), up + (old[2] if old else 0))
        if time.monotonic() - self.saved >= 15:
            self.flush()

    def flush(self):
        self.saved = time.monotonic()
        if not self.pending:
            return True
        try:
            connection = self.database()
            with connection:
                connection.executemany(
                    'INSERT INTO traffic VALUES(?,?,?,?,?) ON CONFLICT(day,id) DO UPDATE SET '
                    'name=excluded.name,down=down+excluded.down,up=up+excluded.up',
                    ((day, key, *row) for (day, key), row in self.pending.items()))
        except (OSError, sqlite3.Error):
            self.error = '应用流量历史暂时无法保存。'
            return False
        self.error = ''
        self.pending.clear()
        self.cache.clear()
        return True

    def history(self, period):
        today = date.today().isoformat()
        first = {'day': today, 'month': today[:7]+'-01', 'year': today[:4]+'-01-01',
                 'all': '0001-01-01'}.get(period, today)
        key = period, today
        if key in self.cache:
            return self.cache[key]
        if self.connection is None and not self.path.is_file():
            return []
        try:
            rows = self.database().execute(
                'SELECT MIN(name),SUM(down),SUM(up) FROM traffic WHERE day >= ? AND day <= ? '
                'GROUP BY id ORDER BY SUM(down)+SUM(up) DESC, MIN(name) LIMIT 30', (first,today)).fetchall()
        except (OSError, sqlite3.Error):
            self.error = '应用流量历史暂时无法读取。'
            return []
        if len(self.cache) >= 8:
            self.cache.clear()
        self.cache[key] = rows
        return rows

    def reset(self):
        try:
            if self.connection is not None or self.path.exists():
                connection = self.database()
                with connection:
                    connection.execute('DELETE FROM traffic')
        except (OSError, sqlite3.Error):
            self.error = '重置应用流量历史失败。'
            return False
        self.pending.clear()
        self.cache.clear()
        self.error = ''
        return True

    def close(self):
        self.flush()
        self.cache.clear()
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def frame_rows(frame):
    elapsed = frame.get('elapsed')
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not .1 <= elapsed <= 120:
        raise ValueError('invalid duration')
    entries = frame.get('rows')
    if not isinstance(entries,list) or len(entries)>APP_LIMIT:
        raise ValueError('invalid counters')
    found = {}
    for row in entries:
        if not isinstance(row,dict):
            continue
        key, name, down, up = (row.get(k) for k in ('id','name','down','up'))
        if (not isinstance(key,str) or not 1<=len(key)<=96 or not isinstance(name,str) or
                not all(type(n) is int and 0<=n<2**53 for n in (down,up)) or not (down or up)):
            continue
        display = ' '.join(''.join(c if c.isprintable() else ' ' for c in name[:192]).split())
        old = found.get(key)
        found[key] = (key,display[:96] or '未知应用',down+(old[2] if old else 0),up+(old[3] if old else 0))
    return sorted(found.values(),key=lambda row:(-row[2]-row[3],row[1].casefold())),elapsed


def add_interval(ledger, rows, elapsed, now):
    midnight = datetime.combine(now.date(), day_time.min)
    before = max(0., elapsed - (now-midnight).total_seconds())
    if before:
        earlier, later = [], []
        for key,name,down,up in rows:
            down_before,up_before = round(down*before/elapsed),round(up*before/elapsed)
            earlier.append((key,name,down_before,up_before))
            later.append((key,name,down-down_before,up-up_before))
        ledger.add(earlier,(now.date()-timedelta(days=1)).isoformat())
        ledger.add(later,now.date().isoformat())
    else:
        ledger.add(rows,now.date().isoformat())


class AppTrafficMonitor(QObject):
    def __init__(self, owner, path):
        super().__init__(owner)
        self.owner = owner
        self.ledger = AppTrafficHistory(path)
        self.process = QProcess(self)
        self.process.setStandardErrorFile(QProcess.nullDevice())
        self.process.readyReadStandardOutput.connect(self.receive)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.started.connect(self.started)
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self.timeout)
        self.live = []
        self.output = bytearray()
        self.error = ''
        self.status = '应用流量采集已关闭'
        self.enabled = False
        self.stopping = False
        self.closed = False
        self.drop_next = False
        self.preview = owner.runtime.dock.preview or bool(os.environ.get('FISHDOCK_TEST_DESKTOP'))

    def configure(self, enabled):
        if self.closed or self.enabled == enabled:
            return
        self.enabled = enabled
        if enabled:
            if not self.stopping:
                self.start()
        else:
            self.live = []
            self.error = ''
            self.status = '应用流量采集已关闭'
            self.output.clear()
            self.ledger.close()
            self.stop()
            self.owner.app_traffic_updated.emit()
            self.release_disabled()

    def release_disabled(self):
        if (not self.enabled and not self.ledger.pending and
                self.process.state()==QProcess.NotRunning and self.owner.app_traffic is self):
            self.owner.app_traffic=None
            self.close()
            self.deleteLater()

    def start(self):
        if self.preview or self.process.state() != QProcess.NotRunning:
            return
        program = binary('DesktopResourceProbe.exe')
        self.error = ''
        self.live = []
        self.output.clear()
        self.drop_next = False
        if not program.is_file():
            self.error = '应用流量读取器尚未生成。'
            self.status = '采集未启动'
            self.owner.app_traffic_updated.emit()
            return
        self.status = '正在启动应用流量采集…'
        self.watchdog.start(12000)
        self.process.start(str(program), ['--app-traffic'])
        self.owner.app_traffic_updated.emit()

    def started(self):
        if not self.enabled or self.stopping:
            self.process.closeWriteChannel()

    def receive(self):
        data = bytes(self.process.readAllStandardOutput())
        if self.stopping or self.closed:
            return
        self.output.extend(data)
        if len(self.output) > FRAME_LIMIT:
            self.error = '应用流量读取器返回了过多数据。'
            self.stop()
            self.owner.app_traffic_updated.emit()
            return
        while (end := self.output.find(b'\n')) >= 0:
            line = bytes(self.output[:end])
            del self.output[:end+1]
            try:
                payload = json.loads(line.decode('utf-8-sig'))
                if not isinstance(payload,dict):
                    raise ValueError('invalid frame')
                if payload.get('error'):
                    self.error = ('Windows 拒绝启动采集，请用管理员身份运行 Dock，或使用已有采集权限的账户。'
                                  if payload['error']=='access' else 'Windows 应用流量采集暂不可用。')
                    self.status = '采集未启动'
                    self.watchdog.stop()
                    self.owner.app_traffic_updated.emit()
                    return
                rows,elapsed = frame_rows(payload)
            except (ValueError,RecursionError):
                continue
            self.watchdog.start(12000)
            self.status = '正在采集 · 约每 2 秒更新'
            self.error = '部分 Windows 流量事件丢失，统计可能偏低。' if payload.get('lost') else ''
            if self.drop_next:
                self.drop_next = False
                self.live = []
            else:
                self.live = [(name,down/elapsed,up/elapsed) for _,name,down,up in rows[:30]]
                add_interval(self.ledger,rows,elapsed,datetime.now())
            self.owner.app_traffic_updated.emit()

    def process_error(self,error):
        if error==QProcess.FailedToStart:
            self.finished()

    def finished(self, *_):
        requested = self.stopping
        self.watchdog.stop()
        self.stopping = False
        if self.closed:
            return
        if self.enabled and requested and not self.error:
            self.start()
            return
        if self.enabled:
            self.live = []
            self.status = '采集已停止'
            if not self.error:
                self.error = '应用流量读取器已退出，可关闭并重新开启采集。'
            self.ledger.close()
            self.owner.app_traffic_updated.emit()
        else:
            self.release_disabled()

    def stop(self):
        self.watchdog.stop()
        if self.process.state()!=QProcess.NotRunning:
            self.stopping = True
            self.process.closeWriteChannel()
            self.watchdog.start(3500)

    def timeout(self):
        if self.stopping:
            self.process.kill()
        else:
            self.error = '应用流量读取器超时，可关闭并重新开启采集。'
            self.status = '采集已停止'
            self.live = []
            self.stop()
            self.owner.app_traffic_updated.emit()

    def snapshot(self, period):
        history = self.ledger.history(period) if period else []
        return dict(live=self.live,history=history,status=self.status,error=self.error or self.ledger.error)

    def reset(self):
        ok = self.ledger.reset()
        if ok:
            self.drop_next = self.process.state()==QProcess.Running
            self.live = []
        self.owner.app_traffic_updated.emit()
        return ok

    def close(self):
        self.closed = True
        self.stop()
        self.watchdog.stop()
        if self.process.state()!=QProcess.NotRunning and not self.process.waitForFinished(1500):
            self.process.kill()
            self.process.waitForFinished(400)
        self.ledger.close()
