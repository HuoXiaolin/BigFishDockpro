"""One silent PawnIO installation attempt, with an offline option on failure."""
import ctypes
from ctypes import wintypes
import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QVBoxLayout

from background_worker import BackgroundWorker
from external_launch import clean_environment
from pawnio_setup import DIGEST, INSTALLER_NAME, SOURCE_PAGE, export_installer, installed, save_installer
from probe_lifecycle import allowed


def launch_silently(setup, may_start):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    # Keep the verified file open for read sharing only until CreateProcess succeeds.
    handle = kernel.CreateFileW(str(setup), 0x80000000, 1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if hashlib.sha256(setup.read_bytes()).hexdigest() != DIGEST:
            raise ValueError('PawnIO 安装包校验失败。请重新获取 Dock。')
        with clean_environment() as env:
            if not may_start():
                return None
            # Use the existing token. CreateProcess returns a failure if the
            # installer requires elevation, so it never opens a UAC prompt.
            return subprocess.Popen([str(setup), '-install', '-silent'], cwd=str(setup.parent), env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        kernel.CloseHandle(handle)


def failure_text(code):
    if code in (5, 740, 1260):
        return 'Windows 权限或电脑策略阻止了 PawnIO 安装。'
    return f'PawnIO 自动安装失败（错误码 {code}）。' if code else '安装结束后仍未检测到 PawnIO 驱动。'


class AutoInstall(BackgroundWorker):
    def __init__(self, runtime):
        super().__init__()
        self.runtime = runtime
        self.marker = Path(runtime.api.CONFIG_DIR) / f'pawnio-auto-{DIGEST[:12]}.attempt'
        self.log = runtime.api.log
        self.error = ''
        self.dialog = None
        self.finished.connect(self.complete)

    def may_start(self):
        return not self.cancelled.is_set() and allowed()

    def run(self):
        if not self.may_start() or installed():
            return
        try:
            self.marker.parent.mkdir(parents=True, exist_ok=True)
            with self.marker.open('xb'):
                pass
        except FileExistsError:
            return
        except OSError:
            self.error = '无法记录 PawnIO 自动安装状态。'
        else:
            self.install()
        if self.error:
            self.log(self.error)

    def install(self):
        try:
            with TemporaryDirectory(prefix='bfp-pawnio-install-', ignore_cleanup_errors=True) as folder:
                setup = Path(folder) / INSTALLER_NAME
                save_installer(setup)
                process = launch_silently(setup, self.may_start)
                if process is None:
                    return
                code = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.error = 'PawnIO 安装超过两分钟。请稍后检查驱动状态。'
        except OSError as error:
            self.error = failure_text(error.winerror) if getattr(error, 'winerror', None) else str(error)
        except ValueError as error:
            self.error = str(error)
        else:
            if code == 3010:  # ERROR_SUCCESS_REBOOT_REQUIRED
                self.log('PawnIO 安装完成，重启 Windows 后生效。')
            elif installed():
                self.log('已检测到 PawnIO，硬件采集将使用已安装的驱动。')
            else:
                self.error = failure_text(code)

    @pyqtSlot()
    def complete(self):
        if not self.error or not self.may_start() or self.runtime.closed:
            return
        from ui_style import SettingsHeader, button, compact_dialog

        parent = QApplication.activeModalWidget() or self.runtime.dock
        title = 'PawnIO 自动安装未完成'
        box = QDialog(parent, Qt.Dialog | Qt.FramelessWindowHint)
        box.setWindowTitle(title)
        box.resize(450, 145)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 12, 16, 12)
        header = SettingsHeader(box, title)
        header.minimize.hide()
        layout.addWidget(header)

        status = QLabel(self.error)
        status.setObjectName('PawnIOInstallStatus')
        status.setTextFormat(Qt.PlainText)
        status.setWordWrap(True)
        layout.addWidget(status)
        details = QLabel(
            f'安装包来自 <a href="{SOURCE_PAGE}">PawnIO 官方发布页</a>，用于读取支持的 CPU 封装温度和功耗。'
            '<br>可保存离线安装包，交给管理员手动安装。')
        details.setObjectName('PawnIOInstallerDetails')
        details.setTextFormat(Qt.RichText)
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextBrowserInteraction)
        details.setOpenExternalLinks(True)
        layout.addWidget(details)

        def save_setup():
            try:
                if export_installer(box):
                    box.accept()
            except (OSError, ValueError) as error:
                status.setText(str(error))

        actions = QHBoxLayout()
        actions.addStretch()
        save = button('保存离线安装包…', save_setup, 'primary')
        save.setObjectName('ExportPawnIOInstaller')
        actions.addWidget(save)
        close = button('关闭', box.reject)
        close.setDefault(True)
        actions.addWidget(close)
        layout.addLayout(actions)

        compact_dialog(box)
        self.dialog = box
        box.finished.connect(self.clear_dialog)
        box.finished.connect(box.deleteLater)
        box.open()
        close.setFocus()

    def clear_dialog(self):
        self.dialog = None

    def close(self):
        self.requestInterruption()
        if self.dialog is not None:
            self.dialog.reject()
