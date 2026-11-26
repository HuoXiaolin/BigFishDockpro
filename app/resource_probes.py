"""Launch only the optional hardware queries requested by a visible consumer."""
import json
import os
import sys
from pathlib import Path
from PyQt5.QtCore import QObject,QProcess,QTimer
from PyQt5.QtWidgets import QApplication
from probe_lifecycle import allowed, start as start_probe
from resource_options import MONITOR_DEVICES, SENSOR_UNITS


SENSOR_SCOPES = {
    'gpu': frozenset(key for key in SENSOR_UNITS if key.startswith('gpu_')),
    'disk_activity': frozenset({'disk_temp'}),
    'display': frozenset({'brightness'}),
}


def binary(name):
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'resource-probe'/name
    project=Path(__file__).resolve().parents[1]
    directories={'PresentMon.exe':'presentmon','DesktopFrameProbe.exe':'presentmon'}
    return project/'artifacts'/directories.get(name,'generated')/name


class SensorRead(QObject):
    def __init__(self,owner,keys):
        super().__init__(owner);self.owner=owner;self.keys=frozenset();self.values={};self.closed=False
        self.scopes={};self.requested={}
        self.process=QProcess(self);self.process.finished.connect(self.finished);self.process.errorOccurred.connect(self.failed)
        self.next=QTimer(self);self.next.setSingleShot(True);self.next.setInterval(10000);self.next.timeout.connect(self.read)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.setInterval(9500);self.deadline.timeout.connect(self.process.kill)
        owner.hardware_changed.connect(self.refresh_scope)
        self.reconfigure(keys)

    def refresh_scope(self):
        self.reconfigure(self.keys)

    def targets(self):
        keys = set(self.keys)
        gpu = disk = display = instance = '-'
        for metric, (identifier, device) in self.scopes.items():
            if device is None:
                keys.difference_update(SENSOR_SCOPES[metric])
            elif metric == 'gpu':
                gpu = str(device.number)
            elif metric == 'disk_activity':
                disk = str(device.number)
            else:
                display, instance = device.number, device.instance or '-'
        return keys, [gpu, disk, display, instance]

    @staticmethod
    def scope_for(key, scopes):
        return next((scopes.get(metric) for metric, keys in SENSOR_SCOPES.items() if key in keys), None)

    def read(self):
        if self.closed or not allowed() or self.process.state()!=QProcess.NotRunning:return
        self.owner.discover_hardware(*self.scopes)
        self.next.stop()
        keys, targets = self.targets()
        self.requested = {key: self.scope_for(key, self.scopes) for key in keys}
        if not keys:
            self.next.start(10000)
            return
        self.deadline.start()
        args = ['--sensors', ','.join(sorted(keys))]
        if self.scopes:args.extend(targets)
        if not start_probe(self.process,binary('DesktopResourceProbe.exe'),args):self.deadline.stop()

    def reconfigure(self,keys):
        if self.closed:return
        scopes = {}
        for metric, readings in SENSOR_SCOPES.items():
            selected = self.owner.cfg[MONITOR_DEVICES[metric]]
            if readings & keys and selected:
                scopes[metric] = (selected, self.owner.hardware.get(metric, {}).get(selected))
        changed = keys - self.keys or scopes != self.scopes
        self.keys=frozenset(keys)
        self.values={k:v for k,v in self.values.items() if k in keys and self.scope_for(k,self.scopes)==self.scope_for(k,scopes)}
        self.scopes = scopes
        if changed and not self.owner.runtime.dock.preview:self.read()

    def finished(self,code,status):
        if self.closed or not allowed():return
        self.deadline.stop()
        matched = {key: scope for key, scope in self.requested.items()
                   if key in self.keys and scope == self.scope_for(key, self.scopes)}
        try:
            raw=bytes(self.process.readAllStandardOutput())
            data=json.loads(raw.decode('utf-8-sig')) if not code and len(raw)<=65536 else {}
            readings={k:v for k,v in data.items() if k in matched and isinstance(v,dict)
                      and type(v.get('value')) in (int,float) and 0<=v['value']<=(100 if k=='brightness' else 100000)}
        except (ValueError,AttributeError):readings={}
        for key, row in readings.items():
            scope = matched[key]
            if scope:
                row['source'] += ' · ' + scope[1].name
        self.values={k:v for k,v in self.values.items() if k not in matched}
        self.values.update(readings)
        indicators=getattr(self.owner,'indicators',None)
        if 'brightness' in matched and indicators:
            indicators.sensor_brightness(readings.get('brightness'))
        interval=(15000 if 'brightness' in self.values else 60000) if self.keys=={'brightness'} else 10000
        if self.keys=={'brightness'} and 'brightness' in self.values and indicators and 'brightness' in indicators.selected and not indicators.power_reading:
            interval=2000
        self.owner.display()
        keys, _ = self.targets()
        if keys - matched.keys():self.read()
        else:self.next.start(interval)
    def failed(self,error):
        if error==QProcess.FailedToStart:self.finished(1,QProcess.NormalExit)
    def close(self):
        self.closed=True;self.next.stop();self.deadline.stop();self.values.clear()
        if self.process.state()!=QProcess.NotRunning:
            p=self.process;p.setParent(QApplication.instance());p.finished.connect(p.deleteLater);p.kill()
        self.deleteLater()
