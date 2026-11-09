"""Launch only the optional hardware queries requested by a visible consumer."""
import json
import os
import sys
from pathlib import Path
from PyQt5.QtCore import QObject,QProcess,QTimer
from PyQt5.QtWidgets import QApplication


def binary(name):
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'resource-probe'/name
    project=Path(__file__).resolve().parents[1]
    directories={'PresentMon.exe':'presentmon','PawnIO_setup.exe':'pawnio'}
    return project/'artifacts'/directories.get(name,'generated')/name


class SensorRead(QObject):
    def __init__(self,owner,keys):
        super().__init__(owner);self.owner=owner;self.keys=frozenset(keys);self.values={};self.closed=False
        self.requested=self.keys
        self.process=QProcess(self);self.process.finished.connect(self.finished);self.process.errorOccurred.connect(self.failed)
        self.next=QTimer(self);self.next.setSingleShot(True);self.next.setInterval(10000);self.next.timeout.connect(self.read)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.setInterval(9500);self.deadline.timeout.connect(self.process.kill)
        if not owner.runtime.dock.preview:self.read()
    def read(self):
        if self.closed or self.process.state()!=QProcess.NotRunning:return
        self.next.stop();self.requested=self.keys
        self.deadline.start()
        self.process.start(str(binary('DesktopResourceProbe.exe')),['--sensors',','.join(sorted(self.requested))])
    def reconfigure(self,keys):
        added=keys-self.keys;self.keys=frozenset(keys)
        self.values={k:v for k,v in self.values.items() if k in self.keys}
        if added and not self.owner.runtime.dock.preview:self.read()
    def finished(self,code,status):
        if self.closed:return
        self.deadline.stop()
        try:
            raw=bytes(self.process.readAllStandardOutput())
            data=json.loads(raw.decode('utf-8-sig')) if not code and len(raw)<=65536 else {}
            readings={k:v for k,v in data.items() if k in self.keys and k in self.requested and isinstance(v,dict)
                      and type(v.get('value')) in (int,float) and 0<=v['value']<=(100 if k=='brightness' else 100000)}
        except (ValueError,AttributeError):readings={}
        self.values={k:v for k,v in self.values.items() if k not in self.requested}
        self.values.update(readings)
        interval=(15000 if 'brightness' in self.values else 60000) if self.keys=={'brightness'} else 10000
        self.owner.display()
        if self.keys-self.requested:self.read()
        else:self.next.start(interval)
    def failed(self,error):
        if error==QProcess.FailedToStart:self.finished(1,QProcess.NormalExit)
    def close(self):
        self.closed=True;self.next.stop();self.deadline.stop();self.values.clear()
        if self.process.state()!=QProcess.NotRunning:
            p=self.process;p.setParent(QApplication.instance());p.finished.connect(p.deleteLater);p.kill()
        self.deleteLater()
