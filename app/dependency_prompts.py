"""Remind once when enabled AI or music features need the desktop runtime."""
import json
from pathlib import Path

from PyQt5.QtCore import QObject, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QMessageBox

from deck_runtime import installed_runtime


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
        self.wanted = False
        self.dialog=None
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.present)

    def request(self, needed):
        if needed and not self.wanted and 'dotnet' not in self.seen and not installed_runtime():
            self.timer.start(0)
        elif not needed:
            self.timer.stop()
        self.wanted = needed

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
        if not self.wanted or self.dialog is not None or self.runtime.closed or installed_runtime():
            return
        self.remember('dotnet')
        parent=QApplication.activeModalWidget() or self.runtime.dock
        box=self.dialog=QMessageBox(QMessageBox.Information,'安装组件',
            'AI 和音乐功能需要 .NET 10 Desktop Runtime（x64）。安装后即可使用。', parent=parent)
        install=box.addButton('下载 .NET 10 安装程序',QMessageBox.AcceptRole)
        later=box.addButton('稍后',QMessageBox.RejectRole)
        box.setDefaultButton(later)
        box.setEscapeButton(later)
        box.finished.connect(lambda _:self.finished(box,install))
        box.open()

    def finished(self,box,install):
        self.dialog=None
        try:
            if box.clickedButton() is install:
                if not QDesktopServices.openUrl(QUrl(NET_INSTALLER)):
                    raise OSError('无法打开 .NET 10 下载。')
        except OSError as error:
            self.runtime.tray.showMessage('安装组件',str(error))
        finally:
            box.deleteLater()

    def close(self):
        self.timer.stop()
        if self.dialog:self.dialog.reject()
