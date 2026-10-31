"""Hidden resources release safely and rebuild from retained configuration."""
from pathlib import Path
from unittest.mock import patch

def run(api,runtime,root,output,checks):
    from PyQt5 import sip
    from PyQt5.QtCore import QCoreApplication,QEvent,Qt
    from PyQt5.QtGui import QPixmap,QColor
    from PyQt5.QtWidgets import QApplication
    from desktop_panel_tests import wait_for
    app=QApplication.instance();dock=runtime.dock;cfg=dock.cfg
    cfg.update(panel_enabled=True,panels_visible=True,notes_enabled=True,notes_visible=True,lite_enabled=False)
    runtime.apply_settings()
    panel=next(w for w in runtime.panels.windows.values() if w.isVisible())
    paths=[]
    for i in range(36):
        sample=Path(root)/('hidden-resource-sample-%02d.txt'%i);sample.write_text('synthetic',encoding='utf-8');paths.append(str(sample))
    assert runtime.panels.add_paths(panel.identity,paths)
    panel.set_collapsed_geometry(False)
    panel.query.setText('hidden-resource-sample');panel.render();panel.list.doItemsLayout()
    panel.list.setCurrentRow(panel.list.count()-1)
    panel.list.verticalScrollBar().setValue(panel.list.verticalScrollBar().maximum())
    state=panel.page_state();assert state[1]
    panel.hide();assert panel.list.count()==0 and panel.backdrop is None
    panel.render();assert panel.list.count()==0
    panel.show();assert panel.list.count()==36 and panel.page_state()==state,(state,panel.page_state())
    runtime.panels.sync_windows()
    assert all(w.list.count()==0 for w in runtime.panels.windows.values() if not w.isVisible())
    checks.append('hidden cards release icon/thumbnail lists; query/selection/scroll restored on reopen; inactive merged pages do not rebuild lists')
    # Assert the production 60s policy; shorten only the test timer deadline.
    def expire(widget):
        for _ in range(5):app.processEvents()
        assert widget._idle_release.timer.interval()==60000
        fired=[];widget._idle_release.timer.timeout.connect(lambda:fired.append(True))
        widget._idle_release.timer.start(20)
        wait_for(app,lambda:sip.isdeleted(widget) or bool(fired))
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    identity=runtime.notes.new();note=runtime.notes.windows[identity]
    note.editor.setHtml('<p><b>Saved resource fixture</b></p>');assert runtime.notes.flush()
    assert runtime.notes.update_and_save(identity,visible=False)
    assert note.backdrop is None
    note.todo_input.setText('Unsubmitted draft')
    note._idle_release.release();assert runtime.notes.windows[identity] is note
    note.todo_input.clear()
    with patch.object(runtime.notes,'flush',return_value=False):
        note._idle_release.release();assert runtime.notes.windows[identity] is note
    note._idle_release.timer.setInterval(60000);expire(note)
    assert identity not in runtime.notes.windows and sip.isdeleted(note),(note.isVisible(),note.disposed,runtime.notes.message)
    runtime.notes.sync();assert identity not in runtime.notes.windows
    runtime.notes.open(identity);restored=runtime.notes.windows[identity]
    assert restored.editor.toPlainText()=='Saved resource fixture' and '<b' not in restored.editor.toPlainText()
    assert 'font-weight' in restored.editor.toHtml()
    restored.flip();assert restored.pages.frames is not None
    restored.hide();assert restored.pages.frames is None and restored.pages.currentIndex()==1
    restored.show();assert restored.pages.currentWidget().isVisible()
    checks.append('hidden note editor releases only after a successful save; failed-save protection, lazy recreation and saved rich text retained')
    runtime.notes.manage();dialog=runtime.notes.dialog;dialog.reject();expire(dialog)
    assert runtime.notes.dialog is None and sip.isdeleted(dialog)
    runtime.notes.manage();assert runtime.notes.dialog is not dialog
    runtime.notes.dialog.reject()
    runtime.show_settings();dialog=runtime.tray.settings_dialog
    assert not dialog._idle_release.timer.isActive()
    dialog.reject();expire(dialog)
    assert not hasattr(runtime.tray,'settings_dialog') and sip.isdeleted(dialog)
    runtime.show_settings();assert runtime.tray.settings_dialog is not dialog
    runtime.tray.settings_dialog.reject()
    from dock_extras import DockQuickSettings
    popup=dock.extras.popup=DockQuickSettings(dock.extras);popup.refresh();popup.show();popup.hide();expire(popup)
    assert dock.extras.popup is None and sip.isdeleted(popup)
    importer=runtime.tray.importer
    with patch('batch_import.discover_apps',return_value=[]):
        importer.show();dialog=importer.dialog
        wait_for(app,lambda:not dialog.worker.isRunning())
        dialog.reject()
        with patch.object(dialog.worker,'isRunning',return_value=True):
            dialog._idle_release.release();assert importer.dialog is dialog
        dialog._idle_release.timer.setInterval(60000);expire(dialog)
        assert importer.dialog is None and sip.isdeleted(dialog)
        importer.show();assert importer.dialog is not dialog
        wait_for(app,lambda:not importer.dialog.worker.isRunning());importer.dialog.reject()
    checks.append('main settings, note manager, quick popup and application manager release after hidden idle; visible windows and active discovery protected; reopen creates valid fresh controls')
    cfg['clock_enabled']=True;cfg['calendar_enabled']=True;runtime.clock.sync();runtime.calendar.sync()
    for window in (runtime.clock,runtime.calendar):
        window.backdrop=QPixmap(window.size());window.backdrop.fill(QColor('#9bcce8'))
        window.hide();assert window.backdrop is None and not window.tick.isActive()
        window.sync();assert window.isVisible()
    checks.append('clock/calendar hidden backdrop and tick release; reopen remains usable')
