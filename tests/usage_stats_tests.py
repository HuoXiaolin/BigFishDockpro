"""Local counter persistence and actual settings reset/cancel/failure behavior."""
import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication,QMessageBox


def run(api,runtime,root,output,checks):
    def stage(message):
        with (Path(output)/'usage-stage.log').open('a',encoding='utf-8') as stream:stream.write(message+'\n')
    stage('begin')
    from settings_catalog import APPEARANCE, TASKBAR, USAGE, WIDGETS
    from usage_stats import SCHEMA_VERSION, UsageStore
    from settings_dialog import SettingsDialog
    from ui_style import apply_theme
    from ui_test_events import Events
    app = QApplication.instance()
    previous = runtime.usage
    folder = Path(root)/'usage-fixture'
    folder.mkdir()
    path = folder/'usage_stats.json'
    today = dt.date.today()
    path.write_text(json.dumps(dict(since='2020-01-01', starts=126, seconds=553500,
                                    counts=dict(dock_launch=100), days={today.isoformat():100})), encoding='utf-8')
    store = UsageStore(folder)
    runtime.usage = runtime.dock.usage = store
    dialog = None
    try:
        assert store.data['version']==SCHEMA_VERSION and store.data['starts']==1 and store.data['seconds']==0
        assert not any(store.data['counts'].values()) and not store.data['days']
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
        loaded=UsageStore(folder)
        assert loaded.data['starts']==2 and loaded.data['counts']==store.data['counts']
        assert loaded.data['days'][today.isoformat()]['dock_launch']==1
        loaded.timer.stop();loaded.deleteLater()
        stage('create settings')
        def iso(days):return (today-dt.timedelta(days=days)).isoformat()
        store.data['since'] = iso(100)+'T09:00:00'
        history = {iso(days): {'file_open': days//2+3} for days in range(1, 7)}
        history.update({iso(20): {'dock_launch': 50}, iso(60): {'flash_new': 16}, iso(95): {'agenda_new': 9}})
        store.data['days'].update(history)
        for counts in history.values():
            for key, count in counts.items():store.data['counts'][key] += count

        dialog = SettingsDialog(runtime.tray, api)
        dialog.reveal()
        assert not dialog.tabs.nav.item(0).flags() & Qt.ItemIsSelectable
        dialog.tabs.setCurrentIndex(USAGE)
        app.processEvents()
        page = dialog.usage_page
        week = 2+sum(days//2+3 for days in range(1,7))
        assert page.fields['today'].text()=='2 次' and page.fields['total'].text()==f'{week+75} 次'
        assert len(page.chart.series)==7 and sum(count for _,count in page.chart.series)==week
        assert page.rank_layout.itemAt(0).widget() is page.rank_rows['file_open'][0]
        assert page.rank_rows['file_open'][1].text()==f'{week-1} 次  ·  {(week-1)/week:.1%}'
        Events.keyClick(page.range_tabs, Qt.Key_Right)
        assert page.view_state()==(30, 'period') and len(page.chart.series)==30
        assert page.period_counts['dock_launch']==51 and page.rank_layout.itemAt(0).widget() is page.rank_rows['dock_launch'][0]
        page.range_tabs.setCurrentIndex(2)
        assert len(page.chart.series)==90 and page.period_counts['flash_new']==16 and page.period_counts['agenda_new']==0
        assert iso(95) not in store.data['days']
        page.ranking_scope.setCurrentIndex(page.ranking_scope.findData('total'))
        assert page.rank_rows['agenda_new'][0].isVisible() and page.rank_rows['agenda_new'][1].text().startswith('9 次')

        old_value = dialog.fields['icon_size'].value()
        dialog.fields['icon_size'].setValue(old_value+1)
        dialog.focus_setting('taskbar_mode')
        assert dialog.tabs.currentIndex()==TASKBAR and dialog.tabs.nav.currentItem() is dialog.tabs.nav_items[TASKBAR]
        assert tuple(dialog._mounted)==(TASKBAR,)
        dialog.focus_setting('daily_picture_source')
        assert dialog.tabs.currentIndex()==WIDGETS and tuple(dialog._mounted)==(WIDGETS,)
        dialog.tabs.setCurrentIndex(APPEARANCE)
        assert dialog.fields['icon_size'].value()==old_value+1
        dialog.focus_setting('@usage')
        page = dialog.usage_page
        assert page.view_state()==(90, 'total') and tuple(dialog._mounted)==(USAGE,)

        for _ in range(4):app.processEvents()
        scroll = dialog.tabs.pages.currentWidget()
        assert scroll.verticalScrollBar().maximum() > 0, (
            scroll.viewport().size(), scroll.widget().size(), page.size(), page.minimumSize(), page.minimumSizeHint())
        assert page.chart.height() >= 65 and scroll.widget().height() > scroll.viewport().height()
        assert dialog.grab().save(str(Path(output)/'usage-statistics-small.png'))
        original_theme = app._fish_theme_light
        for light in (True, False):
            apply_theme(app, light)
            dialog.size_mode.setCurrentIndex(dialog.size_mode.findData('medium'))
            app.processEvents()
            scroll=dialog.tabs.pages.currentWidget()
            assert scroll.horizontalScrollBar().maximum()==0 and scroll.widget().width()<=scroll.viewport().width()+2
            assert page.overview.height() <= page.overview.minimumSizeHint().height()+4 < 108
            assert page.management.parentWidget() is page and page.management.width()==page.overview.width()
            assert page.management.y() > page.analysis_layout.parentWidget().geometry().bottom()
            scroll.verticalScrollBar().setValue(0)
            assert dialog.grab().save(str(Path(output)/('usage-statistics.png' if light else 'usage-statistics-dark.png')))
            scroll.ensureWidgetVisible(page.ranking, 8, 8)
            app.processEvents()
            assert dialog.grab().save(str(Path(output)/('usage-ranking.png' if light else 'usage-ranking-dark.png')))
        apply_theme(app, original_theme)
        def answer(value):
            for widget in app.topLevelWidgets():
                if isinstance(widget,QMessageBox) and widget.isVisible():widget.done(value);return
        stage('reset checks')
        QTimer.singleShot(0,lambda:answer(QMessageBox.Cancel));page.reset();assert sum(store.data['counts'].values())==week+75
        original=store.snapshot()
        with patch.object(store,'write',return_value=False):
            QTimer.singleShot(0,lambda:answer(QMessageBox.Yes));page.reset();assert store.data==original and '原统计数据已保留' in page.status.text()
        QTimer.singleShot(0,lambda:answer(QMessageBox.Yes));page.reset();assert not sum(store.data['counts'].values()) and store.data['seconds']==store.data['starts']==0
        assert page.empty_ranking.isVisible() and not page.ranking.isVisible()
        assert page.chart.series[-1][1]==0 and page.chart.series[0][1] is None
        assert store.path.is_file();store.record('note_new');assert store.flush()
        loaded=UsageStore(folder);assert loaded.data['counts']['note_new']==1 and loaded.data['counts']['dock_launch']==0;loaded.timer.stop();loaded.deleteLater()
        assert 'synthetic-app' not in store.path.read_text(encoding='utf-8')
        checks.append('Usage statistics clears the legacy schema once, persists daily and cumulative counts, and excludes failed launches. Real 7/30/90-day trend, ranked period/lifetime counts, empty state, light/dark and compact rendering, reset cancel/failure/success, and new actions after reset checked.')
        checks.append('Grouped main settings navigate by page identity, search selects moved taskbar and widget fields, the previous editor is released, and pending field edits plus statistics selections survive page switches.')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        store.timer.stop();store.deleteLater();runtime.usage=runtime.dock.usage=previous;app.processEvents()
