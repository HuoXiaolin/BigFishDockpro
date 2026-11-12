"""Bluetooth readings and the shared peripheral battery tray icon."""
import json
import os
import re
import sys
from pathlib import Path
from PyQt5.QtCore import QObject,QProcess,QTimer,Qt,QRectF,QPointF
from PyQt5.QtGui import QPainter,QPen,QColor,QPixmap,QIcon,QPainterPath
from PyQt5.QtWidgets import QApplication,QSystemTrayIcon
from ui_style import AlignedMenu
from resource_status import BATTERY_WARNING_LEVEL, TRAY_RING_SIZES, low_battery_ink, ring_dimensions
from probe_lifecycle import allowed, start as start_probe

HUES=('#5b8def','#41b66a','#8297c9','#ac81e2','#e99d36','#35adb3')
GROUP=3


def ring_ink(row,light=True):
    state=row.get('state')
    if state=='charging':return '#087b60' if light else '#6de3ba'
    if row.get('stale') or state in ('sleeping','offline','unavailable','busy'):
        return '#566b7b' if light else '#a8bac8'
    level=row['level']
    return low_battery_ink(level,light) if level is not None and level<BATTERY_WARNING_LEVEL else row['ink']


def devices(raw):
    if not isinstance(raw,list):raise ValueError('蓝牙结果无效')
    found={}
    for row in raw[:96]:
        if not isinstance(row,dict):continue
        key=row.get('id')
        if not isinstance(key,str) or not re.fullmatch('[0-9A-Fa-f]{12}',key):continue
        key=key.upper();level=row.get('level')
        level=level if type(level) is int and 0<=level<=100 else None
        name=' '.join(str(row.get('name') or '蓝牙设备').split())[:96]
        if key not in found or (found[key]['level'] is None and level is not None):
            found[key]=dict(id=key,name=name,level=level)
    return [found[k] for k in sorted(found)]


def draw_rings(painter,rect,rows,dark=False):
    painter.save();painter.setRenderHint(QPainter.Antialiasing)
    center=rect.center()
    radius,width,pitch=ring_dimensions(min(rect.width(),rect.height()),len(rows))
    for index,row in enumerate(rows or [{'level':None,'ink':'#8795a1'}]):
        r=max(.55,radius-index*pitch);circle=QRectF(center.x()-r,center.y()-r,2*r,2*r)
        value=row['level']
        track=QColor('#aab3bc' if dark else '#657581');track.setAlpha(105)
        if value==0:
            track=QColor(ring_ink(row,not dark));track.setAlpha(210)  # Warn without showing a filled battery.
        pen=QPen(track,width,Qt.DotLine if value is None or row.get('stale') else Qt.SolidLine,Qt.RoundCap)
        painter.setPen(pen);painter.setBrush(Qt.NoBrush);painter.drawEllipse(circle)
        if value is not None and value>0:
            pen=QPen(QColor(ring_ink(row,not dark)),width,Qt.SolidLine,Qt.RoundCap);painter.setPen(pen)
            painter.drawArc(circle,90*16,-round(value*360*16/100))
    painter.restore()


def draw_peripheral_rings(painter,rect,rows,dark=False):
    draw_rings(painter,rect,rows,dark)
    mark=next((row for state in ('charging','sleeping') for row in rows if row.get('state')==state),None)
    if not mark:return
    center=rect.center();scale=min(rect.width(),rect.height())/20
    painter.save();painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(ring_ink(mark,not dark)),max(1.,1.25*scale),Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    path=QPainterPath()
    points=(((.6,-3.8),(-2.5,.3),(.5,.3),(-.6,3.8)) if mark['state']=='charging' else
            ((-2.4,-2.1),(2.3,-2.1),(-2.3,2.1),(2.4,2.1)))
    for index,(x,y) in enumerate(points):
        point=QPointF(center.x()+x*scale,center.y()+y*scale)
        if index==0:path.moveTo(point)
        else:path.lineTo(point)
    painter.drawPath(path);painter.restore()


def tray_icon(rows,dark):
    result=QIcon()
    for side in TRAY_RING_SIZES:
        pm=QPixmap(side,side);pm.fill(Qt.transparent);p=QPainter(pm)
        draw_peripheral_rings(p,QRectF(0,0,side,side),rows,dark);p.end();result.addPixmap(pm)
    return result


def tray_line(row):
    name=row['name']
    if row['source']=='2.4g':
        name+='（2.4G）'
    return f'{name}  {row["display_value"]}'


class BluetoothGauge(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.rows=[];self.assignments={};self.status='正在读取蓝牙电量…'
        self.tray=self.menu=None;self.tray_page=0;self.closed=False;self.busy=False
        self.preview=owner.runtime.dock.preview or bool(os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.process=QProcess(self);self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.next=QTimer(self);self.next.setSingleShot(True);self.next.setInterval(120000);self.next.timeout.connect(self.refresh)
        self.deadline=QTimer(self);self.deadline.setSingleShot(True);self.deadline.setInterval(16000);self.deadline.timeout.connect(self.timed_out)

    def refresh(self):
        if self.closed or self.busy or self.preview or not allowed():return
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
        program=(root/'resource-probe'/'DesktopResourceProbe.exe' if getattr(sys,'frozen',False)
                 else root/'artifacts'/'generated'/'DesktopResourceProbe.exe')
        if not program.is_file():
            self.publish([], '蓝牙读取器尚未生成，请从完整发行包启动或运行开发构建。');return
        self.busy=True;self.next.stop();self.deadline.start()
        if not start_probe(self.process,program,[]):self.busy=False;self.deadline.stop()

    def process_error(self,error):
        if error==QProcess.FailedToStart and self.busy:self.publish([],'蓝牙读取器未能启动。')
    def timed_out(self):
        if self.busy:
            self.process.kill();self.publish([],'蓝牙读取超时，可手动刷新。')
    def finished(self,code,status):
        if self.closed or not self.busy:return
        try:
            payload=bytes(self.process.readAllStandardOutput())
            if code or status!=QProcess.NormalExit or len(payload)>65536:raise ValueError()
            rows=devices(json.loads(payload.decode('utf-8-sig')))
        except (ValueError,UnicodeError):
            self.publish([],'暂时无法读取蓝牙设备。');return
        self.publish(rows,'' if rows else '未发现已连接的蓝牙设备。')

    def publish(self,rows,status):
        if self.closed or not allowed():return
        self.busy=False;self.deadline.stop();self.status=status
        # Keep colours for still-connected devices as others connect or leave.
        keys={r['id'] for r in rows}
        self.assignments={k:v for k,v in self.assignments.items() if k in keys}
        for i,row in enumerate(rows):
            if row['id'] not in self.assignments:
                self.assignments[row['id']]=next((c for c in HUES if c not in self.assignments.values()),HUES[i%len(HUES)])
            row['ink']=self.assignments[row['id']]
        self.rows=rows;self.owner.batteries_changed()
        if not self.preview:self.next.start()

    def set_tray(self,visible):
        if visible and self.tray is None:
            self.tray=QSystemTrayIcon(self);self.menu=AlignedMenu()
            self.menu.aboutToShow.connect(self.build_menu);self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self.activated);self.paint_tray()
            if not self.preview:self.tray.show()
        elif not visible and self.tray is not None:
            self.tray.hide();self.tray.setContextMenu(None);self.tray.deleteLater();self.tray=None
            self.menu.close();self.menu.deleteLater();self.menu=None

    def activated(self,reason):
        if reason==QSystemTrayIcon.Trigger:
            from PyQt5.QtGui import QCursor
            self.menu.popup(QCursor.pos())

    def tray_group(self,step=0):
        rows=self.owner.battery_rows(tray=True)
        pages=max(1,(len(rows)+GROUP-1)//GROUP)
        self.tray_page=(min(self.tray_page,pages-1)+step)%pages
        start=self.tray_page*GROUP
        return rows[start:start+GROUP],pages

    def turn_tray(self):
        self.tray_group(1)
        self.paint_tray()

    def build_menu(self):
        rows,pages=self.tray_group()
        self.menu.clear();self.menu.addAction('外设电量').setEnabled(False)
        for row in rows:
            self.menu.addAction(tray_line(row).replace('&','&&')).setEnabled(False)
        if not rows:self.menu.addAction(self.owner.battery_status(tray=True)).setEnabled(False)
        if pages>1:
            self.menu.addAction(f'下一组（{self.tray_page+1}/{pages}）',self.turn_tray)
        self.menu.addSeparator()
        self.menu.addAction('刷新电量',self.owner.refresh_batteries)
        self.menu.addAction('关闭外设电量托盘图标',lambda:self.owner.set_options(resource_bt_tray=False))

    def paint_tray(self):
        if self.tray is None:return
        rows,pages=self.tray_group()
        self.tray.setIcon(tray_icon(rows,not self.owner.runtime.dock.is_light()))
        lines=['外设电量']+[tray_line(row) for row in rows]
        if not rows:lines.append(self.owner.battery_status(tray=True))
        if pages>1:lines.append(f'第 {self.tray_page+1}/{pages} 组')
        self.tray.setToolTip('\n'.join(lines))

    def close(self):
        self.closed=True;self.next.stop();self.deadline.stop();self.set_tray(False)
        if self.process.state()!=QProcess.NotRunning:
            process=self.process
            process.setParent(QApplication.instance());process.finished.connect(process.deleteLater);process.kill()
        self.rows.clear();self.assignments.clear();self.deleteLater()
