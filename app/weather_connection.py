"""Local-only QWeather credentials for the optional air quality source."""
import re
from pathlib import Path

from PyQt5.QtCore import QSettings


def settings(api):
    return QSettings(str(Path(api.CONFIG_DIR)/'weather-connection.ini'),QSettings.IniFormat)


def connection(api):
    saved=settings(api)
    host=saved.value('host','',type=str)
    key=saved.value('api_key','',type=str)
    return (host,key) if valid(host,key) else ('','')


def valid(host,key):
    return bool(re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.qweatherapi\.com',host) and
                re.fullmatch(r'[A-Za-z0-9_-]{1,128}',key))


def edit_connection(parent,service):
    from PyQt5.QtWidgets import QDialog,QFormLayout,QHBoxLayout,QLineEdit,QVBoxLayout
    from ui_style import button,compact_dialog,exec_dialog,label

    api=service.runtime.api
    dialog=QDialog(parent);dialog.setWindowTitle('和风天气连接');dialog.resize(470,215)
    box=QVBoxLayout(dialog);form=QFormLayout();box.addLayout(form)
    host,key=connection(api)
    endpoint=QLineEdit(host);endpoint.setPlaceholderText('项目的 API Host');endpoint.setMaxLength(120)
    secret=QLineEdit(key);secret.setEchoMode(QLineEdit.Password);secret.setMaxLength(128)
    form.addRow('API Host',endpoint);form.addRow('API Key',secret)
    status=label('填写和风天气控制台的项目地址和密钥。连接信息独立保存在本机。','muted');box.addWidget(status)

    def save():
        host=endpoint.text().strip().lower().removeprefix('https://').rstrip('/')
        key=secret.text().strip()
        if (host or key) and not valid(host,key):
            status.setText('请输入有效的 qweatherapi.com 项目地址和 API Key。');return
        saved=settings(api);saved.setValue('host',host);saved.setValue('api_key',key);saved.sync()
        if saved.status()!=QSettings.NoError:
            status.setText('连接信息保存失败。');return
        service.sync();dialog.accept()

    actions=QHBoxLayout();actions.addStretch();actions.addWidget(button('关闭',dialog.reject));actions.addWidget(button('保存连接',save,'primary'));box.addLayout(actions)
    compact_dialog(dialog);exec_dialog(dialog)
