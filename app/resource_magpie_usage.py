"""Read Magpie's local session accounting without changing its configuration."""
import csv
import ctypes
import io
import os
import subprocess
import time
from collections import defaultdict
from ctypes import wintypes
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryFile

from PyQt5.QtCore import QObject, Qt, pyqtSlot

from background_worker import BackgroundWorker
from external_launch import clean_environment
from resource_processes import ProcessRanking, executable_path
from resource_usage import bounds


PROVIDERS = {'codex': 'Codex', 'dsh': 'Dsh'}
PROCESS_NAMES = {'magpie', 'magpie-windows-amd64', 'magpie-windows-arm64'}
TOKEN_COLUMNS = {'input': 'input_tokens', 'output': 'output_tokens',
                 'cacheRead': 'cache_read_tokens', 'cacheWrite': 'cache_write_tokens'}
REQUIRED_COLUMNS = {'source', 'agent', 'rejected', 'time', 'model', 'cost_usd', *TOKEN_COLUMNS.values()}
REFRESH_SECONDS = 300


def magpie_executable():
    kernel = ctypes.windll.kernel32
    session_id = kernel.ProcessIdToSessionId
    session_id.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    ours = wintypes.DWORD()
    if not session_id(os.getpid(), ctypes.byref(ours)):
        return None
    for process in ProcessRanking().snapshot().values():
        if process.name.casefold() not in PROCESS_NAMES:
            continue
        session = wintypes.DWORD()
        if not session_id(process.pid, ctypes.byref(session)) or session.value != ours.value:
            continue
        executable = Path(executable_path(process.pid))
        if (executable.is_absolute() and executable.suffix.casefold() == '.exe'
                and executable.stem.casefold() in PROCESS_NAMES and executable.is_file()):
            return executable
    return None


class UsageTotals:
    def __init__(self):
        self.tokens = dict.fromkeys(TOKEN_COLUMNS, 0)
        self.records = self.unpriced = 0
        self.cost = Decimal(0)

    def add(self, tokens, cost):
        for key, amount in tokens.items():
            self.tokens[key] += amount
        self.records += 1
        if cost is None:
            self.unpriced += 1
        else:
            self.cost += cost

    def summary(self):
        priced = self.records > self.unpriced
        return dict(self.tokens, tokens=sum(self.tokens.values()), records=self.records,
                    cost=float(self.cost) if priced else None, unpriced=self.unpriced, estimated=priced)


def parse_usage(stream, start, end, cancelled=lambda: False):
    reader = csv.DictReader(stream, strict=True)
    if not REQUIRED_COLUMNS.issubset(reader.fieldnames or ()):
        raise ValueError('Unsupported Magpie usage export')
    daily = defaultdict(UsageTotals)
    hourly = defaultdict(UsageTotals)
    yesterday = end - timedelta(days=1)
    for row in reader:
        if cancelled():
            raise InterruptedError
        provider = PROVIDERS.get(row['agent'])
        if provider is None or row['source'] != 'log' or row['rejected'] != 'false':
            continue
        stamp = datetime.fromisoformat(row['time']).astimezone()
        day = stamp.date()
        if day > end or (start and day < start):
            continue
        model = row['model']
        if row.get('swapped') == 'true':
            model = row.get('served_model') or model
        tokens = {key: int(row[column]) for key, column in TOKEN_COLUMNS.items()}
        if min(tokens.values()) < 0 or not model:
            raise ValueError('Invalid Magpie usage row')
        value = row['cost_usd']
        cost = Decimal(value) if value else None
        if cost is not None and (not cost.is_finite() or cost < 0):
            raise ValueError('Invalid Magpie price')
        daily[provider, day.isoformat(), model].add(tokens, cost)
        if day >= yesterday:
            hourly[provider, stamp.strftime('%Y-%m-%dT%H')].add(tokens, cost)

    snapshot = defaultdict(lambda: {'days': [], 'hours': []})
    for (provider, day, model), total in sorted(daily.items()):
        snapshot[provider]['days'].append(dict(date=day, model=model, summary=total.summary(), magpie=True))
    for (provider, hour), total in sorted(hourly.items()):
        snapshot[provider]['hours'].append(dict(date=hour, summary=total.summary()))
    return dict(snapshot)


def apply_session_history(provider, imported):
    if not imported:
        return provider
    local = defaultdict(list)
    external = defaultdict(list)
    for row in provider.get('days', []):
        local[row['date']].append(row)
    for row in imported['days']:
        external[row['date']].append(row)

    # Choose a source for each complete day. The same request can be present in both sources.
    use_magpie = {
        day for day, rows in external.items()
        if all(sum(row['summary'].get(key) or 0 for row in rows) >=
               sum(row['summary'].get(key) or 0 for row in local.get(day, []))
               for key in ('records', 'tokens'))
    }
    if not use_magpie:
        return provider
    days = [row for row in provider.get('days', []) if row['date'] not in use_magpie]
    days.extend(row for row in imported['days'] if row['date'] in use_magpie)
    hours = [row for row in provider.get('hours', []) if row['date'][:10] not in use_magpie]
    hours.extend(row for row in imported['hours'] if row['date'][:10] in use_magpie)
    return dict(provider, days=days, hours=hours, usageAvailable=True)


class MagpieJob(BackgroundWorker):
    def __init__(self, period):
        super().__init__()
        self.period = period
        self.start_date, self.end_date = bounds('all' if period == 'all' else 'month')
        self.snapshot = None

    def run(self):
        try:
            executable = magpie_executable()
            if executable is None or self.cancelled.is_set():
                return
            with TemporaryFile() as output:
                with clean_environment() as env:
                    process = subprocess.Popen([str(executable), 'usage', '--csv', self.period],
                                               cwd=executable.parent, env=env, stdin=subprocess.DEVNULL,
                                               stdout=output, stderr=subprocess.DEVNULL,
                                               creationflags=subprocess.CREATE_NO_WINDOW)
                self.own_process(process)
                try:
                    if process.wait(timeout=20) != 0 or self.cancelled.is_set():
                        return
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    return
                finally:
                    self.release_process(process)
                output.seek(0)
                with io.TextIOWrapper(output, encoding='utf-8-sig', newline='') as stream:
                    self.snapshot = parse_usage(stream, self.start_date, self.end_date, self.cancelled.is_set)
        except (OSError, ValueError, TypeError, csv.Error, InvalidOperation, OverflowError):
            return


class MagpieUsage(QObject):
    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.job = None
        self.rows = {}
        self.next_read = {}

    def refresh(self, include_history=False, *, force=False):
        period = 'all' if include_history else '30d'
        if self.job is not None or (not force and time.monotonic() < self.next_read.get(period, 0)):
            return
        self.job = MagpieJob(period)
        self.job.finished.connect(self.finished, Qt.QueuedConnection)
        self.job.start()

    @pyqtSlot()
    def finished(self):
        job = self.sender()
        if job is not self.job:
            return
        self.job = None
        now = time.monotonic()
        self.next_read[job.period] = now + (60 if job.snapshot is None else REFRESH_SECONDS)
        if job.snapshot is not None:
            if job.start_date is None:
                self.next_read['30d'] = now + REFRESH_SECONDS
                self.rows = job.snapshot
            else:
                start = job.start_date.isoformat()
                self.rows = {
                    provider: {
                        'days': [row for row in self.rows.get(provider, {}).get('days', []) if row['date'] < start]
                                + job.snapshot.get(provider, {}).get('days', []),
                        'hours': job.snapshot.get(provider, {}).get('hours', []),
                    }
                    for provider in PROVIDERS.values()
                }
            self.bridge.publish_ai()
        job.deleteLater()

    def close(self):
        job, self.job = self.job, None
        if job:
            job.requestInterruption()
            job.deleteLater()
