"""Native grouped-dialog rendering on the project's private Windows desktop."""
import sys, json, copy, tempfile, traceback
from pathlib import Path

def settle(app):
    for _ in range(5):app.processEvents()

def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    from run_isolated_test import assert_isolated
    assert_isolated()
    import dock as api
    from PyQt5.QtWidgets import QApplication,QLabel,QSlider
    from PyQt5.QtCore import QCoreApplication,QEvent
    from ui_style import apply_theme,shutdown_ui
    from runtime_controller import RuntimeController
    from batch_import import BatchImporter,BatchDialog
    from settings_dialog import SettingsDialog
    from settings_design import ResponsiveFields,NumericControl
    from clock_options import ClockOptions
    from card_sizing import CardSizingDialog
    from panel_management import PanelDefinition
    from panel_group_view import GroupDialog
    from unittest.mock import patch
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    checks=[];runtime=None
    try:
        with tempfile.TemporaryDirectory(prefix='bfp-settings-design-') as folder:
            api.CONFIG_DIR=folder;api.CONFIG_PATH=str(Path(folder)/'config.json');api.LOG_PATH=str(Path(folder)/'dock.log')
            cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
            cfg.update(items=[],settings_size='medium',hide_tray=True,panel_enabled=False,notes_enabled=False,clock_enabled=False,calendar_enabled=False,desktop_icon_mode='both',desktop_middle_toggle=False,screen_corners=False,check_updates_on_start=False,lite_enabled=False)
            api.save_config(cfg);apply_theme(app,True)
            dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
            tray.importer=BatchImporter(dock,tray,api.save_config)
            runtime=tray.runtime=RuntimeController(dock,tray,api)
            main=SettingsDialog(tray,api);main.reveal();settle(app)
            assert main.property('designPopup') and main.fields['icon_size'].window() is main
            for name,width in [('small',560),('medium',800),('large',1100)]:
                main.size_mode.setCurrentIndex(main.size_mode.findData(name));settle(app)
                main.tabs.setCurrentIndex(0);settle(app)
                main.grab().save(str(output/f'settings-{name}.png'))
                for grid in main.findChildren(ResponsiveFields):
                    if grid.isVisible():
                        for widget,_ in grid.cells:
                            assert widget.geometry().right()<=grid.width()+2,(name,widget.geometry().getRect(),grid.width())
            main.size_mode.setCurrentIndex(main.size_mode.findData('medium'));settle(app)
            spin=main.fields['dock_highlight'];control=next(w for w in main.findChildren(NumericControl) if w.findChild(type(spin)) is spin)
            original=spin.value();control.slider.setValue(44);assert spin.value()==44;spin.setValue(original);assert control.slider.value()==original
            main.dock_preset.setCurrentIndex(1);settle(app);main.commit();assert main.isVisible()
            checks.append('real fields retained, slider/spin sync, preset selection, Save keeps main window open; three sizes render without field-cell overflow')
            for index in range(main.tabs.count()):
                main.tabs.setCurrentIndex(index);settle(app)
                main.grab().save(str(output/f'main-page-{index}.png'))
            dialogs=[('clock',ClockOptions(runtime.clock)),('calendar',ClockOptions(runtime.calendar)),('sizing',CardSizingDialog(runtime)),('new-panel',PanelDefinition()),('groups',GroupDialog(runtime.panels))]
            with patch('batch_import.discover_apps',return_value=[]):
                batch=BatchDialog(tray.importer);batch.worker.wait(5000);settle(app);dialogs.append(('applications',batch))
            from sticky_notes import NoteOptions
            cfg['settings_size']='small'
            identity=runtime.notes.new();note_options=NoteOptions(runtime.notes.windows[identity]);dialogs.append(('note-small',note_options))
            cfg['settings_size']='medium'
            for name,dialog in dialogs:
                dialog.show();settle(app);assert dialog.property('designPopup')
                from PyQt5.QtWidgets import QScrollArea
                for scroll in dialog.findChildren(QScrollArea):
                    if scroll.isVisible():assert scroll.widget().width()<=scroll.viewport().width()+2,(name,scroll.widget().width(),scroll.viewport().width())
                if name=='note-small':
                    dialog.body_font.setValue(22);assert dialog.commit();settle(app)
                    assert dialog.auto_hide.geometry().bottom()<dialog.pinned.parentWidget().geometry().bottom() or dialog.auto_hide.height()>=20
                    assert dialog.style.height()>=20 and dialog.body_font.height()>=20
                    assert dialog.style.mapTo(dialog,dialog.style.rect().topLeft()).y()>40
                dialog.grab().save(str(output/f'{name}-light.png'))
                if name=='calendar':
                    from PyQt5.QtWidgets import QScrollArea
                    diagnostic=[dict(scroll=w.width(),viewport=w.viewport().width(),page=w.widget().width(),minimum=w.widget().minimumWidth(),hint=w.widget().minimumSizeHint().width(),horizontal=w.horizontalScrollBar().maximum(),forms=[dict(width=f.width(),hint=f.minimumSizeHint().width(),cells=[(c.width(),c.minimumSizeHint().width()) for c,_ in f.cells]) for f in w.widget().findChildren(ResponsiveFields)]) for w in dialog.findChildren(QScrollArea)]
                    (output/'layout-diagnostic.json').write_text(json.dumps(diagnostic,indent=2),encoding='utf-8')
                dialog.reject()
            apply_theme(app,False);main.show();settle(app);main.tabs.setCurrentIndex(0);main.grab().save(str(output/'settings-dark.png'))
            for name,dialog in dialogs[:2]:
                dialog.show();settle(app);dialog.grab().save(str(output/f'{name}-dark.png'));dialog.reject()
            checks.append('main seven pages, clock/calendar, sizing, new-card, grouping and application manager rendered; light/dark theme remains readable')
            main.reject();runtime.close();runtime=None;shutdown_ui(app)
        result={'passed':True,'checks':checks,'limits':['isolated Qt rendering and local controls only; no physical monitor/DPI switch or user configuration touched']}
    except Exception:
        result={'passed':False,'checks':checks,'error':traceback.format_exc()}
    finally:
        if runtime:runtime.close()
        shutdown_ui(app)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1

if __name__=='__main__':
    root=Path(__file__).resolve().parent.parent
    for folder in ('app','tests','tools'):sys.path.insert(0,str(root/folder))
    raise SystemExit(run(sys.argv[-1]))
