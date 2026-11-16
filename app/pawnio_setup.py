"""Read installed PawnIO status and save the verified offline installer on request."""
import hashlib
import os
import sys
from pathlib import Path

INSTALLER_NAME = 'PawnIO_setup.exe'
DIGEST = '1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032'
SOURCE_PAGE = 'https://github.com/namazso/PawnIO.Setup/releases/tag/2.2.0'


def installed():
    import winreg

    program_files = os.environ.get('ProgramW6432') or os.environ.get('ProgramFiles')
    if not program_files or not (Path(program_files) / 'PawnIO' / 'PawnIOLib.dll').is_file():
        return ''
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Services\PawnIO', 0,
                            winreg.KEY_QUERY_VALUE):
            pass
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO',
                            0, winreg.KEY_QUERY_VALUE | winreg.KEY_WOW64_64KEY) as key:
            return str(winreg.QueryValueEx(key, 'DisplayVersion')[0])
    except OSError:
        return ''


def installer_bytes():
    try:
        if getattr(sys, 'frozen', False):
            from _pawnio_payload import INSTALLER
            return INSTALLER
        return (Path(__file__).resolve().parents[1] / 'artifacts/pawnio' / INSTALLER_NAME).read_bytes()
    except (ImportError, OSError, EOFError) as error:
        raise ValueError('无法读取内置 PawnIO 安装包。请重新获取 Dock。') from error


def save_installer(path):
    from PyQt5.QtCore import QIODevice, QSaveFile

    data = installer_bytes()
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise ValueError('PawnIO 安装包校验失败。请重新获取 Dock。')

    target = QSaveFile(str(path))
    if not target.open(QIODevice.WriteOnly):
        raise OSError('无法保存安装包。请选择可写入的位置。')
    if target.write(data) != len(data):
        target.cancelWriting()
        raise OSError('安装包写入不完整。请检查磁盘空间或更换保存位置。')
    if not target.commit():
        raise OSError('无法保存安装包。请检查目标文件是否被占用。')


def export_installer(parent):
    from PyQt5.QtCore import QStandardPaths
    from PyQt5.QtWidgets import QFileDialog

    folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    path, _ = QFileDialog.getSaveFileName(parent, '保存 PawnIO 离线安装包',
                                          str(Path(folder) / INSTALLER_NAME), '安装程序 (*.exe)')
    if path:
        save_installer(path)
    return bool(path)
