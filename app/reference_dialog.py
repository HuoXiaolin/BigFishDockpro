"""Manual reference inspection with a cancellable, bounded background scan."""
import threading
import time
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog)
from ui_style import SettingsHeader, compact_dialog, label, button
from settings_layout import fit_auxiliary_dialog
from reference_repair import candidates, inspect, change


class ReferenceScan(QObject):
    ready=pyqtSignal(object,bool,str)
    progress=pyqtSignal(int,int)
    def __init__(self,rows,parent=None):
        super().__init__(parent)
        self.rows=rows;self.cancelled=threading.Event();self.thread=None
    def start(self):
        def work():
            last=[0.0]
            def progress(done,total):
                now=time.monotonic()
                if done==total or now-last[0]>=.08:
                    last[0]=now
                    try:self.progress.emit(done,total)
                    except RuntimeError:self.cancelled.set()
            error=''
            try:rows=inspect(self.rows,self.cancelled,progress)
            except Exception as failure:rows=[];error=str(failure)
            try:self.ready.emit(rows,self.cancelled.is_set(),error)
            except RuntimeError:pass  # Owner closed while the filesystem call completed.
        self.thread=threading.Thread(target=work,name='reference-check',daemon=True);self.thread.start()


class ReferencesDialog(QDialog):
    def __init__(self,runtime,parent=None):
        super().__init__(parent,Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.runtime=runtime;self.worker=None;self.closed=False;self.total=0;self.rows=[]
        self.setWindowTitle('入口检查 · 大肥鱼Dock');self.resize(800,580);self.setMinimumSize(640,430)
        body=QVBoxLayout(self);body.setContentsMargins(18,14,18,16);body.setSpacing(10)
        body.addWidget(SettingsHeader(self,'入口检查'))
        help_text=label('只检查 Dock 和卡片中保存的路径。网络、可移动磁盘和无权限位置不判为失效。','muted');help_text.setWordWrap(True);body.addWidget(help_text)
        toolbar=QHBoxLayout()
        self.scan_button=button('重新检查',self.refresh,'primary');toolbar.addWidget(self.scan_button)
        self.cancel_scan_button=button('取消检查',self.cancel_scan);self.cancel_scan_button.setEnabled(False);toolbar.addWidget(self.cancel_scan_button)
        toolbar.addStretch();body.addLayout(toolbar)
        self.list=QTreeWidget();self.list.setColumnCount(3);self.list.setHeaderLabels(['入口 / 路径','使用位置','检查结果'])
        self.list.setRootIsDecorated(False);self.list.setUniformRowHeights(True);self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.header().setSectionResizeMode(0,QHeaderView.Stretch);self.list.header().setSectionResizeMode(1,QHeaderView.ResizeToContents);self.list.header().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.list.itemSelectionChanged.connect(self.selection_changed);body.addWidget(self.list,1)
        self.scope=label('选择一项可重新定位；同一路径的所有 Dock 和卡片引用会一起修复。','muted');self.scope.setWordWrap(True);body.addWidget(self.scope)
        actions=QHBoxLayout()
        self.locate_file=button('定位文件…',lambda:self.relocate(False));actions.addWidget(self.locate_file)
        self.locate_folder=button('定位文件夹…',lambda:self.relocate(True));actions.addWidget(self.locate_folder)
        self.remove_button=button('移除所选失效引用',self.remove_selected);actions.addWidget(self.remove_button)
        actions.addStretch();actions.addWidget(button('关闭',self.close));body.addLayout(actions)
        self.status=label('点击“重新检查”开始。原文件始终保持原位。','muted');self.status.setWordWrap(True);body.addWidget(self.status)
        self.selection_changed();compact_dialog(self);fit_auxiliary_dialog(self,runtime.dock.cfg)

    def selected(self):return [item.data(0,Qt.UserRole) for item in self.list.selectedItems()]

    def selection_changed(self):
        rows=self.selected();busy=self.worker is not None
        self.locate_file.setEnabled(not busy and len(rows)==1);self.locate_folder.setEnabled(not busy and len(rows)==1)
        self.remove_button.setEnabled(not busy and bool(rows) and all(row['missing'] for row in rows))
        if len(rows)==1:
            row=rows[0];self.scope.setText('此目标共有 %d 处引用（%s）。重新定位会更新这些引用；选择新的快捷方式时使用其启动参数。'%(row.get('count',1),row['kind']))
        elif rows:self.scope.setText('已选 %d 个目标。只允许移除已确认不存在的引用；原文件不会删除。'%len(rows))
        else:self.scope.setText('选择一项可重新定位；同一路径的所有 Dock 和卡片引用会一起修复。')

    def refresh(self):
        if self.closed or self.worker is not None:return
        rows=candidates(self.runtime.dock.cfg);self.total=len(rows);self.rows=[];self.list.clear()
        self.scan_button.setEnabled(False);self.cancel_scan_button.setEnabled(True)
        self.worker=ReferenceScan(rows,self);worker=self.worker
        worker.progress.connect(self.progress);worker.ready.connect(lambda rows,cancelled,error:self.finished(worker,rows,cancelled,error))
        self.status.setText('正在检查 0 / %d 个目标…'%self.total);self.selection_changed();worker.start()

    def progress(self,done,total):
        if not self.closed and self.worker and not self.worker.cancelled.is_set():self.status.setText('正在检查 %d / %d 个目标…'%(done,total))

    def cancel_scan(self):
        if self.worker:
            self.worker.cancelled.set();self.cancel_scan_button.setEnabled(False);self.status.setText('正在取消检查…')

    def finished(self,worker,rows,cancelled,error):
        if self.closed or worker is not self.worker:return
        self.worker=None;worker.deleteLater();self.rows=rows
        self.scan_button.setEnabled(True);self.cancel_scan_button.setEnabled(False)
        self.render()
        missing=sum(bool(row['missing']) for row in rows);unknown=len(rows)-missing
        if error:self.status.setText('检查失败，未修改任何引用。请重试。');self.runtime.api.log('入口检查失败：'+error)
        elif cancelled:self.status.setText('检查已取消，显示已完成部分；未修改任何引用。')
        else:self.status.setText('检查完成：%d 个目标，失效 %d 个，暂不判断 %d 个。'%(self.total,missing,unknown))
        self.selection_changed()

    def render(self):
        self.list.clear()
        for row in self.rows:
            item=QTreeWidgetItem([row['name'],row['kind'],row['status']]);item.setData(0,Qt.UserRole,row)
            item.setToolTip(0,row['path']);self.list.addTopLevelItem(item)
        self.selection_changed()

    def apply(self,candidate,title,removed):
        if not self.runtime.productivity.commit(candidate,title,history=True,refresh=True):
            self.status.setText(self.runtime.productivity.message);return False
        self.rows=[row for row in self.rows if row['path'] not in removed];self.render()
        self.status.setText(self.runtime.productivity.message+'。可通过“撤销上一步整理”恢复引用。');return True

    def relocate(self,folder=False):
        rows=self.selected()
        if self.worker or len(rows)!=1:return False
        row=rows[0]
        if folder:new=QFileDialog.getExistingDirectory(self,'重新定位文件夹')
        else:new,_=QFileDialog.getOpenFileName(self,'重新定位文件或快捷方式','','所有文件 (*)')
        if not new:return False
        try:candidate=change(self.runtime.dock.cfg,row['path'],new)
        except (OSError,ValueError) as error:self.status.setText(str(error));return False
        return self.apply(candidate,'修复入口',{row['path']})

    def remove_selected(self):
        rows=self.selected()
        if self.worker or not rows or not all(row['missing'] for row in rows):return False
        # Revalidate immediately: a previously missing file may have been restored.
        from reference_repair import inspect
        current=inspect(rows,threading.Event())
        missing={row['path'] for row in current if row['missing']}
        if any(row['path'] not in missing for row in rows):
            self.status.setText('部分目标状态已变化，请重新检查后操作。');return False
        candidate=self.runtime.dock.cfg
        for row in rows:candidate=change(candidate,row['path'])
        return self.apply(candidate,'移除失效引用',missing)

    def closeEvent(self,event):
        self.closed=True
        if self.worker:self.worker.cancelled.set()
        super().closeEvent(event)
