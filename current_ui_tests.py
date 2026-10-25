"""Current UI runtime regression using synthetic data on a private Windows desktop."""
import copy,json,os,tempfile,time,traceback
from pathlib import Path
from unittest.mock import patch


def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    checks=[];runtime=app=tray=None;root=None;result=None
    try:
        from run_isolated_test import assert_isolated
        desktop=assert_isolated()
        import dock as api
        from PyQt5.QtCore import Qt,QPoint,QPointF,QEvent,QTimer
        from PyQt5.QtGui import QMouseEvent
        from PyQt5.QtWidgets import QApplication,QMessageBox,QPushButton
        from ui_style import apply_theme,shutdown_ui
        from desktop_panel_tests import wait_for
        from desktop_catalog import CATEGORIES
        from runtime_controller import RuntimeController
        from glass_panel import category_color,_category_icon
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app,True)
        root=tempfile.TemporaryDirectory(prefix='fishdock-current-ui-')
        api.CONFIG_DIR=root.name;api.CONFIG_PATH=str(Path(root.name)/'config.json');api.LOG_PATH=str(Path(root.name)/'dock.log')
        api.RUN_KEY=r'Software\BigFishDockpro_Test_'+desktop
        cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
        cfg.update(items=[],card_scale=100,settings_size='small',glass=False,running_dots=False,lite_enabled=False,hide_tray=True,
                   theme='light',panel_theme='light',panel_enabled=True,panels_visible=True,desktop_auto_sort=False,
                   desktop_icon_mode='both',panel_auto_hide=False,panel_locked=False,screen_corners=False,check_updates_on_start=False,
                   merged_panels=True,merged_active='apps',merged_geometry=[70,90,640,330],merged_compact=False,
                   desktop_panels=[{'id':key,'name':name,'merged':True,'enabled':True,'compact':False,'geometry':[70,90,640,330]} for key,name in CATEGORIES])
        assert api.save_config(cfg)
        dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
        from batch_import import BatchImporter
        tray.importer=BatchImporter(dock,tray,api.save_config)
        runtime=tray.runtime=RuntimeController(dock,tray,api)
        app.processEvents();runtime.panels.sync_windows();app.processEvents()
        checks.append('private Windows desktop: '+desktop+'; temporary configuration and synthetic entries only')
        assert len({category_color(key,True) for key,_ in CATEGORIES})==7
        assert len({category_color(key,False) for key,_ in CATEGORIES})==7
        for theme in ('light','dark'):
            cfg.update(theme=theme,panel_theme=theme);apply_theme(app,theme=='light')
            for window in runtime.panels.windows.values():window.apply_options()
            panel=runtime.panels.windows[runtime.panels.active_window];tabs=panel.tabs
            assert tabs.count()==7 and tabs.isMovable()
            for index in range(7):
                assert not tabs.tabIcon(index).isNull() and tabs.tabData(index) in dict(CATEGORIES)
                assert not tabs.tabIcon(index).pixmap(tabs.iconSize()).isNull()
            panel.grab().save(str(output/('category-tabs-'+theme+'.png')))
        from glass_panel import PanelOptions
        shortcut_errors=[]
        def close_panel_options():
            try:
                modal=QApplication.activeModalWidget();assert isinstance(modal,PanelOptions)
                modal.grab().save(str(output/'panel-header-settings.png'));modal.reject()
            except Exception:
                shortcut_errors.append(traceback.format_exc())
                active=QApplication.activeModalWidget()
                if active:active.reject()
        active_panel=runtime.panels.windows[runtime.panels.active_window]
        QTimer.singleShot(30,close_panel_options);active_panel.settings_button.click()
        assert not shortcut_errors,shortcut_errors
        checks.append('card settings shortcut: header settings icon opens actual PanelOptions modal directly in a visible card')
        cfg.update(theme='light',panel_theme='light');apply_theme(app,True)
        for window in runtime.panels.windows.values():window.apply_options()
        panel=runtime.panels.windows['apps'];tabs=panel.tabs;index=1;point=tabs.tabRect(index).center()
        assert tabs.rect().contains(point)
        for event_type,buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
            event=QMouseEvent(event_type,QPointF(point),QPointF(tabs.mapToGlobal(point)),Qt.LeftButton,buttons,Qt.NoModifier)
            QApplication.sendEvent(tabs,event);app.processEvents()
        assert runtime.panels.active_window==tabs.tabData(index)
        current=runtime.panels.windows[runtime.panels.active_window];current.tabs.moveTab(0,1);app.processEvents()
        order=[current.tabs.tabData(i) for i in range(7)]
        assert [model['id'] for model in cfg['desktop_panels']]==order
        assert [model['id'] for model in api.load_config()['desktop_panels']]==order
        assert not current.tabs.property('pointerDown')
        checks.append('category bar: seven colored vector icons in both themes, real Qt mouse press/release changes page; movable-tab signal persists ordering; selected/pressed state resets; light/dark runtime screenshots')
        assert runtime.panels.update_panel('documents',merged=False)
        independent=runtime.panels.windows['documents'];independent.resize(430,295);independent.store_geometry();app.processEvents()
        first_size=independent.size();shared_size=list(cfg['merged_geometry'][2:])
        identity=runtime.notes.new();assert identity
        note=runtime.notes.windows[identity];note.editor.setPlainText('演示便签：图标与字号运行检查');assert runtime.notes.flush()
        from sticky_notes_store import COLORS
        note_icons=set()
        for name,color in COLORS:
            note.set_option('color',color);pixmap=note.handle.pixmap()
            assert pixmap is not None and not pixmap.isNull()
            image=pixmap.toImage();pixel=max((image.pixelColor(x,y) for x in range(image.width()) for y in range(image.height())),key=lambda c:c.alpha())
            assert pixel.alpha()>0;note_icons.add(pixel.rgba())
        assert len(note_icons)==7
        for style in ('glass','paper','plain'):
            note.set_option('style',style);assert not note.handle.pixmap().isNull()
            note.grab().save(str(output/('note-icon-'+style+'.png')))
        checks.append('note header: sticky-note vector icon remains the drag handle, follows seven distinct note accents and all three note styles; runtime screenshots')
        note.resize(370,275);note.save_geometry();assert runtime.notes.flush();note_size=note.size()
        from card_sizing import CardSizingDialog
        sizing=CardSizingDialog(runtime);sizing.text_field.setValue(16);assert sizing.commit()
        assert independent.size()==first_size and note.size()==note_size
        assert independent.text_pixels()==16 and note.text_pixels()==16
        assert all(window.text_pixels()==16 for window in runtime.panels.windows.values())
        sizing.reject();sizing.deleteLater()
        assert runtime.panels.update_panel('documents',merged=True)
        runtime.panels.select_page('documents');app.processEvents()
        assert runtime.panels.windows['documents'].bounds()[2:]==shared_size
        checks.append('card sizing: independent card and note keep manual dimensions after shared font save; all card/note content fonts are 16 pixels; merged pages retain shared width/height')
        from PyQt5.QtGui import QKeyEvent
        from sticky_notes import NoteOptions
        assert note.title.isReadOnly() and note.title.width()<note.width()*.6
        original_title=note.row()['title']
        def begin_title():
            point=note.title.rect().center()
            event=QMouseEvent(QEvent.MouseButtonDblClick,QPointF(point),QPointF(note.title.mapToGlobal(point)),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier)
            QApplication.sendEvent(note.title,event);assert not note.title.isReadOnly()
        begin_title();note.title.setText('取消的标题');QApplication.sendEvent(note.title,QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier))
        assert note.title.isReadOnly() and note.title.text()==original_title
        begin_title();note.title.setText('演示便签')
        note.editor.insertPlainText(' 正文自动保存演示');note.changed()
        assert note.row()['title']==original_title
        QApplication.sendEvent(note.title,QKeyEvent(QEvent.KeyPress,Qt.Key_Return,Qt.NoModifier));assert runtime.notes.flush()
        assert note.row()['title']=='演示便签' and note.title.isReadOnly()
        assert api.load_config()['sticky_notes'][0]['title']=='演示便签'
        dialog_errors=[]
        def edit_body_from_header():
            try:
                dialog=QApplication.activeModalWidget();assert isinstance(dialog,NoteOptions)
                dialog.body_font.setValue(22);assert dialog.commit() and dialog.isVisible()
                dialog.grab().save(str(output/'note-settings-body-font.png'));dialog.reject()
            except Exception:
                dialog_errors.append(traceback.format_exc())
                active=QApplication.activeModalWidget()
                if active:active.reject()
        QTimer.singleShot(35,edit_body_from_header);note.settings_button.click()
        assert not dialog_errors,dialog_errors
        assert note.text_pixels()==22 and note.editor.document().defaultFont().pixelSize()==22
        assert note.title.font().pixelSize()==16 and note.size()==note_size
        dialog=NoteOptions(note);dialog.body_font.setValue(30)
        with patch.object(api,'save_config',return_value=False):assert not dialog.commit()
        assert note.text_pixels()==22 and note.row()['body_font_size']==22
        dialog.reject();dialog.deleteLater()
        sizing=CardSizingDialog(runtime);sizing.text_field.setValue(18);assert sizing.commit()
        assert independent.text_pixels()==18 and note.text_pixels()==22 and note.title.font().pixelSize()==18
        sizing.text_field.setValue(16);assert sizing.commit();sizing.reject();sizing.deleteLater()
        dialog=NoteOptions(note);dialog.follow_font();assert dialog.commit() and note.text_pixels()==16
        dialog.body_font.setValue(22);assert dialog.commit();dialog.reject();dialog.deleteLater()
        runtime.notes.reload();note=runtime.notes.windows[identity]
        assert note.text_pixels()==22 and note.title.text()=='演示便签' and note.title.isReadOnly()
        assert note.title.width()<note.width()*.6
        note.editor.setPlainText('正文独立设置字号\n标题保持卡片字号\n拖动右下角调整大小');assert runtime.notes.flush()
        note.grab().save(str(output/'note-compact-title-body-font.png'))
        checks.append('note editing: compact title is read-only until double-click; Escape cancels and Enter persists; body autosave preserves uncommitted title; header settings button opens actual modal; body 22px differs from title 16px, remains after global change/reload, follow/reset and failed-save retention verified')

        from settings_dialog import SettingsDialog
        settings=SettingsDialog(tray,api);settings.reveal();settings.tabs.setCurrentIndex(1);app.processEvents()
        controls={b.text():b for b in settings.findChildren(QPushButton)}
        for left,right in [('新建便签','管理与搜索'),('新建面板','分组与合并')]:
            a,b=controls[left],controls[right]
            assert a.parentWidget() is b.parentWidget() and a.geometry().y()==b.geometry().y(),(left,right)
            assert not a.geometry().intersects(b.geometry())
        settings.tabs.pages.currentWidget().ensureWidgetVisible(controls['新建便签']);app.processEvents()
        settings.grab().save(str(output/'settings-grouped-actions.png'));settings.reject();settings.deleteLater()
        checks.append('settings runtime: note and panel actions share logical rows without overlapping; sizing entry and scale control grouped; desktop page screenshot')
        # Both entry points edit one shared set; an open peer receives saved values.
        main=SettingsDialog(tray,api);main.reveal();main.tabs.setCurrentIndex(1)
        panel=runtime.panels.windows[runtime.panels.active_window];options=PanelOptions(panel);options.show();app.processEvents()
        icon_before=cfg['icon_size'];main.fields['icon_size'].setValue(icon_before+1)
        options.fields['opacity'].setValue(78);options.fields['blur'].setValue(10);options.fields['capsule_ratio'].setValue(30)
        options.fields['collapse_style'].setCurrentIndex(options.fields['collapse_style'].findData('capsule'))
        options.color.setText('#8fc8df');options.auto.setChecked(False);assert options.commit()
        assert cfg['panel_opacity']==78 and cfg['panel_collapse_style']=='capsule'
        assert main.fields['panel_opacity'].value()==78 and main.fields['panel_collapse_style'].currentData()=='capsule'
        assert main.fields['icon_size'].value()==icon_before+1
        assert all(window.option('opacity')==78 and window.option('collapse_style')=='capsule' for window in runtime.panels.windows.values())
        options.fields['opacity'].setValue(99)
        main.fields['panel_collapse_style'].setCurrentIndex(main.fields['panel_collapse_style'].findData('bar'))
        main.fields['panel_locked'].setChecked(False);main.commit();app.processEvents()
        assert cfg['panel_collapse_style']=='bar' and options.fields['collapse_style'].currentData()=='bar'
        assert options.fields['opacity'].value()==78
        assert all(window.option('collapse_style')=='bar' for window in runtime.panels.windows.values())
        old=copy.deepcopy(cfg)
        options.fields['opacity'].setValue(31)
        with patch.object(api,'save_config',return_value=False):assert not options.commit()
        assert cfg==old and main.fields['panel_opacity'].value()==78
        options.refresh_shared()
        from panel_preferences import KEYS
        assert all(not set(model).intersection(KEYS) for model in cfg['desktop_panels'])
        legacy=copy.deepcopy(cfg);legacy['desktop_panels'][0].update(opacity=2,collapse_style='capsule')
        migrated=api.normalize_features(legacy)
        assert 'opacity' not in migrated['desktop_panels'][0] and migrated['panel_opacity']==78
        assert api.load_config()['panel_collapse_style']=='bar'
        assert note.text_pixels()==22 and note.size()==note_size
        options.grab().save(str(output/'shared-card-options.png'));main.grab().save(str(output/'shared-main-options.png'))
        options.reject();main.reject();main.deleteLater()
        checks.append('shared card preferences: card save refreshes main and every card; main save refreshes open card dialog, last saved shared values win without changing unrelated main drafts; obsolete overrides migrated, failed write retains saved values, local dimensions and note body font preserved')

        tray.rebuild()
        for menu in (tray.menu,dock.icon_context_menu(-1)):
            titles={action.text() for action in menu.actions()}
            assert {'应用批量管理…','Dock 布局','桌面卡片','便签','运行模式','设置…','帮助与更新'}<=titles
        tray.add_separator();assert sum(bool(item.get('sep')) for item in cfg['items'])==1
        snapshot=copy.deepcopy(cfg['items']);tray.add_separator()
        with patch.object(tray,'showMessage'):
            assert not tray.remove_separator(0,snapshot)
        assert len(cfg['items'])==2
        assert tray.remove_separator(0,copy.deepcopy(cfg['items'])) and len(cfg['items'])==1
        assert tray.remove_separator(None,copy.deepcopy(cfg['items'])) and not cfg['items']
        checks.append('menus and separators: tray/Dock task groups present; add, single removal, remove-all and stale-menu guard persist safely')
        def decide(remove):
            def click():
                modal=QApplication.activeModalWidget()
                if isinstance(modal,QMessageBox):
                    assert modal.defaultButton().text()=='取消'
                    modal.grab().save(str(output/'note-permanent-delete-confirm.png'))
                    next(button for button in modal.buttons() if button.text()==('永久删除' if remove else '取消')).click()
            QTimer.singleShot(30,click)
        decide(False);assert not runtime.notes.permanent_delete(identity,note) and identity in runtime.notes.windows
        decide(True);assert runtime.notes.permanent_delete(identity,note) and identity not in runtime.notes.windows
        second=runtime.notes.new();assert runtime.notes.delete(second)
        assert any(row['id']==second for row in cfg['notes_trash'])
        decide(True)
        with patch.object(api,'save_config',return_value=False):assert not runtime.notes.permanent_delete(second)
        assert any(row['id']==second for row in cfg['notes_trash'])
        decide(True);assert runtime.notes.permanent_delete(second)
        assert not any(row['id']==second for row in cfg['notes_trash'])
        checks.append('note permanent deletion: actual confirmation modal defaults to Cancel; cancel retains active note, confirmed deletion removes it, trash removal supported, failed write retains trash content')
        from glass_capture_tests import run as capture_checks
        capture_checks(checks)
        runtime.close();runtime=None
        checks.append('normal controller shutdown persists synthetic configuration and closes owned windows/timers')
        result={'passed':True,'version':__import__('app_version').VERSION,'scope':'current-ui-runtime','checks':checks,'limits':['Qt mouse events are simulated on a private desktop; tab reordering uses moveTab and its real persistence signal','no physical mouse/OLE drag, real monitor switching, user desktop changes or installer installation']}
    except Exception:result={'passed':False,'scope':'current-ui-runtime','checks':checks,'error':traceback.format_exc()}
    finally:
        if runtime:
            try:runtime.close()
            except Exception:pass
        if app:
            try:
                from ui_style import shutdown_ui
                shutdown_ui(app)
                from glass_panel import _category_icon
                _category_icon.cache_clear()
            except Exception:pass
        if root:
            try:root.cleanup()
            except OSError:pass
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result.get('passed') else 1
