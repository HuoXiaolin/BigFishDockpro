"""Portable TranslucentTB adapter with owned process lifecycle."""
import json
import os
from pathlib import Path
from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtGui import QColor


def configuration(cfg):
    modes = {'system': 'normal', 'clear': 'clear', 'color': 'opaque',
             'acrylic': 'acrylic', 'glass': 'blur'}
    mode = cfg.get('taskbar_mode', 'system')
    color = QColor(cfg.get('taskbar_color', '#85c6ed'))
    if not color.isValid():
        color = QColor('#85c6ed')
    alpha = round(max(0, min(100, int(cfg.get('taskbar_opacity', 32)))) * 2.55)
    tint = '#00000000' if mode in ('system', 'clear') else color.name() + f'{alpha:02x}'
    result = {'desktop_appearance': {'accent': modes.get(mode, 'normal'), 'color': tint,
              'blur_radius': max(0, min(50, int(cfg.get('taskbar_blur', 12)))),
              'show_line': mode == 'system'}, 'hide_tray': True, 'disable_saving': True}
    for state in ('visible_window', 'maximized_window', 'start_opened', 'search_opened',
                  'task_view_opened', 'battery_saver'):
        result[state + '_appearance'] = {'enabled': False}
    return result


EFFECT_KEYS = ('taskbar_mode', 'taskbar_color', 'taskbar_opacity', 'taskbar_blur')


def effect_key(cfg):
    return tuple(cfg.get(key) for key in EFFECT_KEYS)


class XamlTaskbar:
    def __init__(self, dock, directory, log, complete=None):
        self.dock, self.directory, self.log = dock, Path(directory), log
        self.process = QProcess(dock)
        self.process.setProgram(str(self.directory / 'TranslucentTB.exe'))
        self.process.setWorkingDirectory(str(self.directory))
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
        self.process.started.connect(self.started)
        self.complete = complete
        self.pending = None
        self.starting = None
        self.active = None
        self.closed = False
        self.stop_timer = QTimer(dock)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.process.kill)

    def write(self, cfg):
        path = self.directory / 'settings.json'
        temporary = path.with_suffix('.pending')
        temporary.write_text(json.dumps(configuration(cfg), ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)

    def sync(self):
        self.pending = dict(self.dock.cfg)
        if self.process.state() != QProcess.NotRunning:
            # Only the process started by this adapter is asked to exit.
            self.process.terminate()
            self.stop_timer.start(2000)
        else:
            self.finished()

    def report(self, cfg, success, message):
        if not success:
            self.log(message)
        if self.complete is not None:
            self.complete(effect_key(cfg), success, message)

    def started(self):
        if self.closed or self.starting is None:
            return
        self.active, self.starting = self.starting, None
        self.report(self.active, True, '任务栏组件已启动。')

    def failed(self, error):
        if self.closed or (self.pending is not None and error == QProcess.Crashed):
            return
        cfg = self.starting or self.active or self.pending or self.dock.cfg
        self.starting = self.active = None
        self.report(cfg, False, '任务栏效果未应用：'+self.process.errorString()+'；可点击重新应用。')

    def finished(self, *args):
        self.stop_timer.stop()
        if self.closed:
            return
        previous = self.active or self.starting
        self.active = self.starting = None
        if self.pending is None:
            if previous is not None:
                self.report(previous, False, '任务栏组件已退出，可点击重新应用。')
            return
        cfg, self.pending = self.pending, None
        try:
            self.write(cfg)
        except OSError as error:
            self.report(cfg, False, '任务栏效果未应用：无法保存组件配置，'+str(error)+'；可点击重新应用。')
            return
        if cfg.get('taskbar_mode', 'system') == 'system':
            self.report(cfg, True, '任务栏外观已恢复跟随系统。')
        else:
            self.starting = cfg
            self.process.start()

    def close(self):
        self.closed = True
        self.pending = None
        self.stop_timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)
