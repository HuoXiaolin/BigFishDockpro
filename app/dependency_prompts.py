"""One machine-local reminder per missing, enabled resource dependency."""
import json
from pathlib import Path

from PyQt5.QtCore import QObject, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QMessageBox

from deck_runtime import installed_runtime
from pawnio_setup import installed as installed_pawnio


NET_INSTALLER='https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe'


class DependencyPrompts(QObject):
    def __init__(self,runtime):
        super().__init__(runtime.dock)
        self.runtime=runtime
        self.path=Path(runtime.api.CONFIG_DIR)/'dependency-reminders.json'
        self.seen=set()
        try:
            if self.path.stat().st_size<=256:
                value=json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(value,list):self.seen={key for key in ('dotnet','pawnio') if key in value}
        except (OSError,ValueError):pass
        self.wanted=set()
        self.pending=set()
        self.dialog=None
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.present)

    def request(self,dotnet,pawnio):
        wanted={key for key,on in (('dotnet',dotnet),('pawnio',pawnio)) if on}
        self.pending.intersection_update(wanted)
        for key in wanted-self.wanted-self.seen:
            installed=installed_runtime if key=='dotnet' else installed_pawnio
            if not installed():self.pending.add(key)
        self.wanted=wanted
        if self.pending and self.dialog is None:self.timer.start(0)

    def remember(self,key):
        self.seen.add(key)
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            draft=self.path.with_suffix('.tmp')
            draft.write_text(json.dumps(sorted(self.seen)),encoding='utf-8')
            draft.replace(self.path)
        except OSError as error:
            self.runtime.api.log('无法保存组件安装提醒记录：'+str(error))

    def present(self):
        if not self.pending or self.dialog is not None or self.runtime.closed:return
        key='dotnet' if 'dotnet' in self.pending else 'pawnio'
        self.pending.remove(key)
        dotnet=key=='dotnet'
        installed=installed_runtime if dotnet else installed_pawnio
        if installed():
            if self.pending:self.timer.start(0)
            return
        self.remember(key)
        parent=QApplication.activeModalWidget() or self.runtime.dock
        box=self.dialog=QMessageBox(QMessageBox.Information,'安装组件',
            ('AI 和音乐功能需要 .NET 10 Desktop Runtime（x64）。安装后即可使用。'
             if dotnet else 'CPU 温度与功耗读数可能需要 PawnIO。可以直接启动内置安装程序。'),parent=parent)
        install=box.addButton('下载 .NET 10 安装程序' if dotnet else '安装 PawnIO',QMessageBox.AcceptRole)
        later=box.addButton('稍后',QMessageBox.RejectRole)
        box.setDefaultButton(later)
        box.setEscapeButton(later)
        box.finished.connect(lambda _:self.finished(box,install,key))
        box.open()

    def finished(self,box,install,key):
        self.dialog=None
        try:
            if box.clickedButton() is install:
                if key=='dotnet':
                    if not QDesktopServices.openUrl(QUrl(NET_INSTALLER)):raise OSError('无法打开 .NET 10 下载。')
                else:
                    from pawnio_setup import launch
                    launch()
        except (OSError,ValueError) as error:
            self.runtime.tray.showMessage('安装组件',str(error))
        finally:
            box.deleteLater()
            if self.pending and not self.runtime.closed:self.timer.start(0)

    def close(self):
        self.timer.stop();self.pending.clear()
        if self.dialog:self.dialog.reject()
