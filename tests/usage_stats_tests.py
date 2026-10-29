"""Local counter persistence and actual settings reset/cancel/failure behavior."""
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication,QMessageBox


def run(api,runtime,root,output,checks):
    def stage(message):
        with (Path(output)/'usage-stage.log').open('a',encoding='utf-8') as stream:stream.write(message+'\n')
    stage('begin')
    from usage_stats import UsageStore
    from settings_dialog import SettingsDialog
    app=QApplication.instance();previous=runtime.usage;store=UsageStore(Path(root)/'usage-fixture');runtime.usage=runtime.dock.usage=store;dialog=None
    try:
        with patch.object(runtime.dock,'raise_') as raised,patch.object(runtime.dock,'apply_layer') as layer,patch.object(runtime.dock,'show'):
            runtime.tray._show_dock();assert not raised.called and layer.called
        stage('launch tests')
        with patch('external_launch.launch',return_value=None):
            runtime.dock.launch('synthetic-app');runtime.dock.launch('synthetic-document',source='file_open')
        assert store.data['counts']['dock_launch']==store.data['counts']['file_open']==1
        with patch('external_launch.launch',side_effect=OSError('test failure')),patch('external_launch.startfile',side_effect=OSError('test failure')):runtime.dock.launch('failed-app')
        assert store.data['counts']['dock_launch']==1
        stage('persistence')
        store.last-=65;assert store.flush();assert store.data['seconds']>=65
        loaded=UsageStore(Path(root)/'usage-fixture');assert loaded.data['starts']==2 and loaded.data['counts']==store.data['counts'];loaded.timer.stop();loaded.deleteLater()
        stage('create settings')
        dialog=SettingsDialog(runtime.tray,api);dialog.reveal();index=next(i for i in range(dialog.tabs.count()) if dialog.tabs.nav.item(i).text()=='使用统计');dialog.tabs.setCurrentIndex(index);app.processEvents();page=dialog.usage_page
        assert page.fields['total'].text()=='2' and page.fields['week'].text()=='2'
        dialog.grab().save(str(Path(output)/'usage-statistics.png'))
        def answer(value):
            for widget in app.topLevelWidgets():
                if isinstance(widget,QMessageBox) and widget.isVisible():widget.done(value);return
        stage('reset checks')
        QTimer.singleShot(0,lambda:answer(QMessageBox.Cancel));page.reset();assert sum(store.data['counts'].values())==2
        original=store.snapshot()
        with patch.object(store,'write',return_value=False):
            QTimer.singleShot(0,lambda:answer(QMessageBox.Yes));page.reset();assert store.data==original and '原统计数据已保留' in page.status.text()
        QTimer.singleShot(0,lambda:answer(QMessageBox.Yes));page.reset();assert not sum(store.data['counts'].values()) and store.data['seconds']==store.data['starts']==0
        assert store.path.is_file();store.record('note_new');assert store.flush()
        loaded=UsageStore(Path(root)/'usage-fixture');assert loaded.data['counts']['note_new']==1 and loaded.data['counts']['dock_launch']==0;loaded.timer.stop();loaded.deleteLater()
        assert 'synthetic-app' not in store.path.read_text(encoding='utf-8')
        checks.append('usage statistics: successful launch routes count once, failed launches excluded; local persistence and process duration, seven-day totals; actual settings page rendered; reset cancel and failed save retain counters; confirmed reset persists and new actions restart counting without paths/content')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        store.timer.stop();store.deleteLater();runtime.usage=runtime.dock.usage=previous;app.processEvents()
