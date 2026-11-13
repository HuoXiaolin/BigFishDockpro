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
    from PyQt5.QtWidgets import QApplication,QLabel,QScrollArea,QSlider
    from PyQt5.QtCore import QCoreApplication,QEvent,Qt
    from PyQt5.QtTest import QTest
    from ui_style import apply_theme,shutdown_ui
    from runtime_controller import RuntimeController
    from batch_import import BatchImporter,BatchDialog
    from settings_dialog import SettingsDialog
    from settings_design import ResponsiveFields,NumericControl
    from resource_settings import ResourceOptions
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
            cfg.update(items=[],settings_size='medium',hide_tray=True,panel_enabled=False,notes_enabled=False,clock_enabled=False,calendar_enabled=False,desktop_icon_mode='both',desktop_middle_toggle=False,screen_corners=False,check_updates_on_start=False)
            api.save_config(cfg);apply_theme(app,True)
            dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
            tray.importer=BatchImporter(dock,tray,api.save_config)
            runtime=tray.runtime=RuntimeController(dock,tray,api)
            main=SettingsDialog(tray,api);main.reveal();settle(app)
            assert main.property('designPopup') and main.fields['icon_size'].window() is main
            for name,body_size in (('small',10),('medium',11)):
                main.size_mode.setCurrentIndex(main.size_mode.findData(name));settle(app)
                for index in range(main.tabs.count()):
                    main.tabs.setCurrentIndex(index);settle(app)
                    scroll=main.tabs.pages.currentWidget()
                    page=scroll.widget()
                    assert page.width()<=scroll.viewport().width()+2,(name,index)
                    fields=[w for w in page.findChildren(QLabel) if w.property('role')=='field-label']
                    assert all(w.font().pixelSize()==body_size for w in fields),(name,index)
                main.tabs.setCurrentIndex(0);settle(app)
                main.grab().save(str(output/f'settings-{name}.png'))
                for grid in main.findChildren(ResponsiveFields):
                    if grid.isVisible():
                        for widget,_ in grid.cells:
                            assert widget.geometry().right()<=grid.width()+2,(name,widget.geometry().getRect(),grid.width())
                cfg['settings_size']=name
                capsule_options=ResourceOptions(runtime.resources);capsule_options.show();settle(app)
                assert capsule_options.property('interfaceScale')==main.property('interfaceScale')
                assert capsule_options.fields['resource_layer'].font().pixelSize()==body_size
                pin=capsule_options.fields['resource_capsule_taskbar']
                position=capsule_options.fields['resource_capsule_taskbar_position']
                assert not pin.isChecked() and not position.isEnabled()
                pin.setChecked(True);assert position.isEnabled() and position.findData('custom')>=0
                pin.setChecked(False);assert not position.isEnabled()
                capsule_options.grab().save(str(output/f'resource-settings-{name}.png'))
                for index in range(capsule_options.tabs.count()):
                    capsule_options.tabs.setCurrentIndex(index);settle(app)
                    scroll=capsule_options.tabs.currentWidget().findChild(QScrollArea)
                    assert scroll.widget().width()<=scroll.viewport().width()+2,(name,index,'resource options')
                nav=capsule_options.nav
                heading=nav.item(0)
                assert not heading.flags() & Qt.ItemIsSelectable
                assert heading.font().weight()>nav.font().weight()
                assert nav.width()==main.tabs.nav.width() and nav.iconSize()==main.tabs.nav.iconSize()
                assert nav.font().pixelSize()==main.tabs.nav.font().pixelSize()
                assert all(not item.icon().isNull() for item in capsule_options.nav_items.values())
                for index in (0, 5, 3, 2):
                    item=capsule_options.nav_items[index]
                    nav.scrollToItem(item);settle(app)
                    rect=nav.visualItemRect(item)
                    assert rect.height()==main.tabs.nav.visualItemRect(main.tabs.nav_items[0]).height()
                    point=rect.bottomRight()
                    point.setX(point.x()-8);point.setY(point.y()-4)
                    assert nav.itemAt(point) is item
                    QTest.mouseClick(nav.viewport(),Qt.LeftButton,pos=point);settle(app)
                    assert capsule_options.tabs.currentIndex()==index and len(capsule_options.loaded)==1
                nav.scrollToItem(heading);settle(app)
                QTest.mouseClick(nav.viewport(),Qt.LeftButton,pos=nav.visualItemRect(heading).center());settle(app)
                assert capsule_options.tabs.currentIndex()==2
                assert capsule_options.grab().save(str(output/f'resource-compact-{name}.png'))
                capsule_options.tabs.setCurrentIndex(9);settle(app)
                assert nav.currentItem() is capsule_options.nav_items[9]
                assert capsule_options.grab().save(str(output/f'resource-agenda-{name}.png'))
                capsule_options.reject();capsule_options.deleteLater();settle(app)
            main.size_mode.setCurrentIndex(main.size_mode.findData('medium'));settle(app)
            spin=main.fields['dock_highlight'];control=next(w for w in main.findChildren(NumericControl) if w.findChild(type(spin)) is spin)
            original=spin.value();control.slider.setValue(44);assert spin.value()==44;spin.setValue(original);assert control.slider.value()==original
            main.dock_preset.setCurrentIndex(1);settle(app);main.commit();assert main.isVisible()
            checks.append('real fields retained, slider/spin sync, preset selection, Save keeps main window open; three sizes render without field-cell overflow')
            for index in range(main.tabs.count()):
                main.tabs.setCurrentIndex(index);settle(app)
                main.grab().save(str(output/f'main-page-{index}.png'))
                scroll=main.tabs.pages.currentWidget()
                assert scroll.widget().width() <= scroll.viewport().width()+2
                if index in (0,1,3):
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum());settle(app)
                    main.grab().save(str(output/f'main-page-{index}-bottom.png'))
                    scroll.verticalScrollBar().setValue(0)
            main.tabs.setCurrentIndex(0);settle(app)
            from PyQt5.QtTest import QTest
            from PyQt5.QtCore import Qt
            choice=main.fields['dock_material'];saved=choice.currentIndex()
            QTest.mouseClick(choice,Qt.LeftButton);settle(app)
            assert choice._popup.isVisible()
            main.grab().save(str(output/'settings-dropdown-owner.png'))
            choice._popup.grab().save(str(output/'settings-dropdown.png'))
            QTest.keyClick(choice.view(),Qt.Key_Down);QTest.keyClick(choice.view(),Qt.Key_Return);settle(app)
            assert choice.currentIndex()!=saved and not choice._popup.isVisible()
            choice.setCurrentIndex(saved)
            main.size_mode.setCurrentIndex(main.size_mode.findData('small'));settle(app)
            main.resize(main.minimumSize());settle(app)
            for index in range(main.tabs.count()):
                main.tabs.setCurrentIndex(index);settle(app)
                scroll=main.tabs.pages.currentWidget()
                assert scroll.widget().width() <= scroll.viewport().width()+2, ('minimum',index,scroll.widget().width(),scroll.viewport().width())
            main.tabs.setCurrentIndex(0);settle(app);main.grab().save(str(output/'settings-minimum.png'))
            main.size_mode.setCurrentIndex(main.size_mode.findData('medium'));settle(app)
            checks.append('all pages scroll at minimum width without horizontal clipping; real combo popup mouse open and keyboard selection work')
            from appearance_profile_tests import run as check_profiles
            check_profiles(api,runtime,main,app,output,checks)
            dialogs=[('clock',ClockOptions(runtime.clock)),('calendar',ClockOptions(runtime.calendar)),('sizing',CardSizingDialog(runtime)),('new-panel',PanelDefinition()),('groups',GroupDialog(runtime.panels))]
            with patch('batch_import.discover_apps',return_value=[]):
                batch=BatchDialog(tray.importer);batch.worker.wait(5000);settle(app);dialogs.append(('applications',batch))
            from sticky_notes import NoteOptions
            cfg['settings_size']='small'
            identity=runtime.notes.new();note_options=NoteOptions(runtime.notes.windows[identity]);dialogs.append(('note-small',note_options))
            cfg['settings_size']='medium'
            for name,dialog in dialogs:
                dialog.show();settle(app);assert dialog.property('designPopup')
                for scroll in dialog.findChildren(QScrollArea):
                    if scroll.isVisible():assert scroll.widget().width()<=scroll.viewport().width()+2,(name,scroll.widget().width(),scroll.viewport().width())
                if name=='note-small':
                    dialog.body_font.setValue(22);assert dialog.commit();settle(app)
                    assert dialog.auto_hide.geometry().bottom()<dialog.pinned.parentWidget().geometry().bottom() or dialog.auto_hide.height()>=20
                    assert dialog.style.height()>=20 and dialog.body_font.height()>=20
                    assert dialog.style.mapTo(dialog,dialog.style.rect().topLeft()).y()>40
                dialog.grab().save(str(output/f'{name}-light.png'))
                if name=='calendar':
                    diagnostic=[dict(scroll=w.width(),viewport=w.viewport().width(),page=w.widget().width(),minimum=w.widget().minimumWidth(),hint=w.widget().minimumSizeHint().width(),horizontal=w.horizontalScrollBar().maximum(),forms=[dict(width=f.width(),hint=f.minimumSizeHint().width(),cells=[(c.width(),c.minimumSizeHint().width()) for c,_ in f.cells]) for f in w.widget().findChildren(ResponsiveFields)]) for w in dialog.findChildren(QScrollArea)]
                    (output/'layout-diagnostic.json').write_text(json.dumps(diagnostic,indent=2),encoding='utf-8')
                dialog.reject()
            apply_theme(app,False);main.show();settle(app);main.tabs.setCurrentIndex(0);main.grab().save(str(output/'settings-dark.png'))
            capsule_options=ResourceOptions(runtime.resources);capsule_options.show();settle(app)
            assert capsule_options.grab().save(str(output/'resource-settings-dark.png'))
            capsule_options.reject();capsule_options.deleteLater()
            for name,dialog in dialogs[:2]:
                dialog.show();settle(app);dialog.grab().save(str(output/f'{name}-dark.png'));dialog.reject()
            checks.append('main grouped pages, clock/calendar, sizing, new-card, grouping and application manager rendered; light/dark theme remains readable')
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
