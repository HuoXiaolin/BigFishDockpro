"""Group/rule/popup and saved runtime regressions on the test-owned desktop."""
import copy
from pathlib import Path
from PyQt5.QtCore import Qt,QPoint
from PyQt5.QtWidgets import QApplication,QComboBox,QListView
from desktop_panel_tests import wait_for
from app_catalog import path_key
from panel_management import GroupDialog,PanelDefinition
from desktop_panels import DesktopPanels
from ui_style import apply_theme,ModernComboBox


def run(api,runtime,root,output,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;manager=runtime.panels
    original=copy.deepcopy(cfg);roots=list(manager.roots)
    demo=Path(root)/'RuleDemo';demo.mkdir(exist_ok=True)
    picture=demo/'测试图片.png';picture.write_text('demo',encoding='utf-8')
    document=demo/'测试文档.txt';document.write_text('demo',encoding='utf-8')
    try:
        import json,subprocess,base64
        from app_catalog import discover_apps,is_uninstall_entry
        fixture=Path(root)/'UninstallDemo';fixture.mkdir(exist_ok=True)
        program=fixture/'正常程序.exe';program.write_text('fixture',encoding='utf-8')
        uninstaller=fixture/'unins000.exe';uninstaller.write_text('fixture',encoding='utf-8')
        (fixture/'卸载演示应用.url').write_text('[InternetShortcut]\nURL=https://example.invalid/uninstall\n',encoding='utf-8')
        pairs=[[str(fixture/'软件维护.lnk'),str(uninstaller)], [str(fixture/'应用别名.lnk'),str(program)], [str(fixture/'产品管理.lnk'),str(program),'--uninstall']]
        data=fixture/'links.json';data.write_text(json.dumps(pairs),encoding='utf-8')
        script="$pairs=Get-Content -LiteralPath '"+str(data).replace("'","''")+"' -Raw -Encoding UTF8 | ConvertFrom-Json; $shell=New-Object -ComObject WScript.Shell; foreach($pair in $pairs){$link=$shell.CreateShortcut($pair[0]);$link.TargetPath=$pair[1];if($pair.Count -gt 2){$link.Arguments=$pair[2]};$link.Save()}"
        process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],capture_output=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
        assert process.returncode==0,process.stderr
        found=discover_apps([str(fixture)],include_store=False)
        assert len(found)==1 and not any(is_uninstall_entry(row) for row in found),found
        assert uninstaller.exists() and (fixture/'软件维护.lnk').exists()
        checks.append('discovery filter: Chinese removal names, disguised real uninstaller shortcut targets and --uninstall arguments hidden; normal aliases deduplicated, originals preserved')
        runtime.set_lite(False)
        cfg.update(panel_enabled=True,desktop_auto_sort=True,panel_auto_hide=False,merged_panels=False,hide_tray=False,lite_enabled=True)
        manager.roots=[str(demo)];manager.shown=True
        first=manager.new_panel('设计资料',['.png','.txt'])
        second=manager.new_panel('共享图片',['.png'])
        manager.scan_timer.stop();manager.scan()
        wait_for(app,lambda:manager.worker is None)
        assert len(manager.rows(second))==1, (manager.closed,manager.roots,manager.model(second),manager.scanned_rows,manager.rows(second),cfg['desktop_auto_sort'])
        assert any(row['path']==str(picture) for row in manager.rows('images'))
        assert len(manager.rows(first))==2 and manager.rows(second)[0]['path']==str(picture)
        manager.add_paths(first,[str(picture)])
        assert sum(row['path']==str(picture) for row in manager.rows(first))==1
        assert len(manager.rows(second))==1
        assert sum(row['path']==str(picture) for row in api.load_config()['desktop_entries'])==2
        manager.remove_entries({path_key(str(picture))},first)
        assert all(row['path']!=str(picture) for row in manager.rows(first)) and len(manager.rows(second))==1
        assert any(row['path']==str(picture) for row in manager.rows('images')) and picture.exists()
        manager.add_paths(first,[str(picture)])
        manager.pin_entries({path_key(str(picture))},True,first)
        assert manager.rows(first)[0]['pinned'] and not manager.rows(second)[0].get('pinned')
        definition=PanelDefinition();definition.name.setText('无效格式');definition.formats.setText('*.png /bad/path');definition.validate()
        assert definition.result()!=definition.Accepted and definition.status.text()
        definition.formats.setText('*.PNG， txt; .png');definition.validate()
        assert definition.extensions()==['.png','.txt'] and definition.result()==definition.Accepted
        definition.deleteLater()
        dialog=GroupDialog(manager);dialog.show();app.processEvents()
        dialog.find_card('images').setCheckState(0,Qt.Unchecked)
        dialog.merged.setChecked(True);dialog.commit();app.processEvents()
        assert 'images' in cfg['disabled_categories'] and not manager.windows['images'].isVisible()
        visible=[window for window in manager.windows.values() if window.isVisible()]
        assert len(visible)==1 and visible[0].tabs.count()==len(manager.enabled_models())
        manager.select_page(first);app.processEvents();current=manager.windows[first]
        current.move(90,110);current.resize(430,330);current.store_geometry()
        index=next(i for i in range(current.tabs.count()) if current.tabs.tabData(i)==second)
        current.tabs.setCurrentIndex(index);app.processEvents()
        assert cfg['merged_active']==second and manager.windows[second].geometry().getRect()==(90,110,430,330)
        assert not current.isVisible() and manager.windows[second].isVisible()
        assert api.load_config()['merged_active']==second
        for theme in ('light','dark'):
            apply_theme(app,theme=='light')
            manager.update_panel(second,theme=theme)
            app.processEvents();manager.windows[second].grab().save(str(Path(output)/('merged-panel-'+theme+'.png')))
            dialog.grab().save(str(Path(output)/('panel-groups-'+theme+'.png')))
        dialog.reject();dialog.deleteLater()
        from PyQt5.QtWidgets import QListWidget
        for mode,icon_width in [('large',54),('list',22),('small',34)]:
            window=manager.windows[second]
            menu=window.build_panel_menu()
            submenu=next(action.menu() for action in menu.actions() if action.text()=='显示方式')
            index={'small':0,'large':1,'list':2}[mode]
            submenu.actions()[index].trigger();app.processEvents()
            assert window.model['view']==mode and window.list.iconSize().width()==icon_width
            assert window.list.count()==len(manager.rows(second))
            assert window.list.viewMode()==(QListWidget.ListMode if mode=='list' else QListWidget.IconMode)
            assert api.load_config()['desktop_panels'][-1]['view']==mode
            window.grab().save(str(Path(output)/('panel-view-'+mode+'.png')))
        manager.update_panel(second,view='list')
        save=api.save_config;previous=copy.deepcopy(cfg)
        api.save_config=lambda value:False
        try:
            assert not manager.update_panel(second,view='large')
            assert runtime.set_lite(True) is False and not runtime.lite and cfg==previous
        finally:api.save_config=save
        from PyQt5.QtWidgets import QMessageBox
        question=QMessageBox.question;QMessageBox.question=lambda *args:QMessageBox.Yes
        try:manager.delete_panel(first)
        finally:QMessageBox.question=question
        assert len(manager.rows(second))==1 and any(row['path']==str(picture) for row in manager.rows('images'))
        assert path_key(str(picture)) not in cfg['desktop_excluded']
        manager.scan();wait_for(app,lambda:manager.worker is None)
        assert not manager.windows['images'].isVisible() and len([w for w in manager.windows.values() if w.isVisible()])==1
        saved=api.load_config();manager.close();cfg.update(saved)
        runtime.panels=manager=DesktopPanels(runtime,roots=[str(demo)]);manager.apply_settings();manager.scan_timer.stop();app.processEvents()
        assert manager.active_window==second and not manager.windows['images'].isVisible()
        assert manager.windows[second].geometry().getRect()==(90,110,430,330)
        assert len(manager.rows(second))==1 and manager.model(second)['view']=='list'
        # Eleven rows must occupy distinct rectangles, not merely exist in the model.
        collection=manager.new_panel('列表与独立卡片')
        samples=[]
        for number in range(11):
            sample=demo/('演示文件%02d.pdf'%number);sample.write_text('demo',encoding='utf-8');samples.append(str(sample))
        manager.add_paths(collection,samples)
        changed=manager.set_merged(collection,False)
        assert changed
        window=manager.windows[collection]
        manager.update_panel(collection,compact=False,geometry=[550,120,400,270])
        window.set_collapsed_geometry(False)
        for mode in ('small','list','large','list'):
            manager.update_panel(collection,view=mode);app.processEvents();window.list.doItemsLayout()
            assert window.list.count()==11
            rects=[window.list.visualItemRect(window.list.item(i)) for i in range(11)]
            assert all(rect.width()>0 and rect.height()>0 for rect in rects),rects
            assert len({(rect.x(),rect.y()) for rect in rects})==11,rects
            if mode=='list':
                assert all(rects[i].bottom()<rects[i+1].top() for i in range(10)),rects
                assert window.list.verticalScrollBar().maximum()>0
                window.list.scrollToItem(window.list.item(10));app.processEvents()
                assert window.list.viewport().rect().intersects(window.list.visualItemRect(window.list.item(10)))
        window.list.item(3).setSelected(True);window.query.setText('演示文件03');app.processEvents()
        assert window.list.count()==1 and window.list.item(0).isSelected()
        window.query.clear();app.processEvents();assert window.list.count()==11
        window.list.scrollToTop();app.processEvents()
        window.grab().save(str(Path(output)/'list-eleven-rows.png'))
        assert manager.windows[second].isVisible() and window.isVisible() and not window.tabs.isVisible()
        assert collection not in {manager.windows[second].tabs.tabData(i) for i in range(manager.windows[second].tabs.count())}
        # Actual context actions must join/split the active page and preserve independent geometry.
        independent=window.geometry().getRect();window.store_geometry()
        menu=window.build_panel_menu();next(a for a in menu.actions() if a.text()=='加入合并卡片').trigger();menu.deleteLater()
        manager.select_page(collection);app.processEvents();assert window.tabs.isVisible() and not manager.windows[second].isVisible()
        menu=window.build_panel_menu();next(a for a in menu.actions() if a.text()=='独立显示此卡片').trigger();menu.deleteLater()
        app.processEvents();assert window.isVisible() and window.geometry().getRect()==independent
        assert manager.active_window!=collection and manager.windows[manager.active_window].isVisible()
        dialog=GroupDialog(manager)
        dialog.move_cards([second],'independent');dialog.commit();dialog.reject();dialog.deleteLater();app.processEvents()
        assert manager.windows[second].isVisible() and not manager.windows[second].tabs.isVisible()
        assert not next(m for m in api.load_config()['desktop_panels'] if m['id']==second)['merged']
        window.grab().save(str(Path(output)/'independent-list-card.png'))
        manager.windows[manager.active_window].grab().save(str(Path(output)/'partial-merged-card.png'))
        saved=api.load_config();manager.close();cfg.update(saved)
        runtime.panels=manager=DesktopPanels(runtime,roots=[str(demo)]);manager.apply_settings();manager.scan_timer.stop();app.processEvents()
        window=manager.windows[collection]
        assert window.isVisible() and window.geometry().getRect()==independent and not window.tabs.isVisible()
        assert window.list.count()==11 and manager.model(collection)['view']=='list'
        before={key:value.collapsed for key,value in manager.windows.items()}
        runtime.set_lite(True);runtime.set_lite(False);app.processEvents()
        assert {key:value.collapsed for key,value in manager.windows.items()}==before
        assert manager.windows[second].isVisible() and window.isVisible()
        saved_merge=copy.deepcopy(cfg)
        save=api.save_config;api.save_config=lambda value:False
        try:
            assert manager.set_merged(collection,True) is False and cfg==saved_merge
        finally:api.save_config=save
        # Empty membership is valid: all enabled cards remain independently visible.
        members=[model['id'] for model in manager.merged_models()]
        for identity in members:
            changed=manager.set_merged(identity,False)
            assert changed
        app.processEvents();assert manager.active_window is None
        assert all(manager.windows[model['id']].isVisible() for model in manager.enabled_models())
        manager.select_page(collection);assert manager.active_window is None
        panels=copy.deepcopy(cfg['desktop_panels'])
        for model in panels:model['merged']=True
        manager.commit(merged_panels=False,desktop_panels=panels);manager.sync_windows()
        joined=manager.set_merged(collection,True)
        assert joined and {model['id'] for model in manager.merged_models()}=={collection}
        manager.set_merged(collection,False)
        for identity in members:
            joined=manager.set_merged(identity,True)
            assert joined
        checks.append('11-file list regression: distinct full rows, scrolling to final row, repeated small/large/list changes, search and selection, restart; partial merge context/group controls, active split, independent geometry, empty membership and lite coexistence')
        # Tab order: moveTab emits the same signal as native dragging; keep active identity stable.
        members=[model['id'] for model in manager.merged_models()]
        assert len(members)>=3
        manager.select_page(members[0]);app.processEvents()
        host=manager.windows[members[0]];host.resize(900,330);app.processEvents();bar=host.tabs
        entries=copy.deepcopy(cfg['desktop_entries'])
        fixed={i:model['id'] for i,model in enumerate(cfg['desktop_panels']) if model['id'] not in members}
        bar.moveTab(len(members)-1,0);app.processEvents()
        expected=[members[-1]]+members[:-1]
        assert [model['id'] for model in manager.merged_models()]==expected
        assert manager.active_window==members[0] and cfg['desktop_entries']==entries
        assert all(cfg['desktop_panels'][index]['id']==identity for index,identity in fixed.items())
        for w in manager.windows.values():
            assert [w.tabs.tabData(i) for i in range(w.tabs.count())]==expected
        before=copy.deepcopy(cfg);save=api.save_config;api.save_config=lambda value:False
        try:
            bar.moveTab(0,len(members)-1);app.processEvents()
            assert cfg==before and [bar.tabData(i) for i in range(bar.count())]==expected
            assert manager.active_window==members[0]
        finally:api.save_config=save
        # An inactive tab must not hide its source window until the drag is released.
        from PyQt5.QtGui import QMouseEvent,QKeyEvent
        from PyQt5.QtCore import QEvent,QPointF
        identity=bar.tabData(0);point=QPointF(bar.tabRect(0).center())
        app.sendEvent(bar,QMouseEvent(QEvent.MouseButtonPress,point,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        assert manager.active_window==members[0] and bar.pressing
        destination=QPointF(bar.tabRect(2).center())
        assert bar.rect().contains(point.toPoint()) and bar.rect().contains(destination.toPoint())
        for step in range(1,13):
            position=point+(destination-point)*(step/12)
            app.sendEvent(bar,QMouseEvent(QEvent.MouseMove,position,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
            app.processEvents()
        wait_for(app,lambda:bar.tabData(2)==identity)
        assert manager.active_window==members[0]
        app.sendEvent(bar,QMouseEvent(QEvent.MouseButtonRelease,destination,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        app.processEvents();assert manager.active_window==identity and manager.windows[identity].isVisible(),(identity,manager.active_window,bar.currentIndex(),bar.pressed_identity)
        expected=[model['id'] for model in manager.merged_models()]
        tab=manager.windows[identity].tabs
        index=tab.currentIndex();next_index=index+1 if index+1<tab.count() else index-1
        next_identity=tab.tabData(next_index)
        app.sendEvent(tab,QKeyEvent(QEvent.KeyPress,Qt.Key_Right if next_index>index else Qt.Key_Left,Qt.NoModifier))
        app.processEvents();assert manager.active_window==next_identity
        dialog=GroupDialog(manager);dialog.show();app.processEvents()
        initial=[item.data(0,Qt.UserRole) for item in dialog.card_items()]
        dialog.move_cards([initial[0]],'default',before=initial[2])
        staged=[initial[1],initial[0]]+initial[2:]
        assert [item.data(0,Qt.UserRole) for item in dialog.card_items()]==staged
        dialog.populate();assert [item.data(0,Qt.UserRole) for item in dialog.card_items()]==staged
        previous=[m['id'] for m in cfg['desktop_panels']];dialog.reject();dialog.deleteLater()
        assert [m['id'] for m in cfg['desktop_panels']]==previous
        dialog=GroupDialog(manager);dialog.move_cards([initial[0]],'default',before=initial[2]);dialog.commit()
        app.processEvents();dialog.show();dialog.grab().save(str(Path(output)/'group-order-controls.png'));dialog.reject();dialog.deleteLater()
        assert [m['id'] for m in cfg['desktop_panels']]==[key for key in staged if key in set(previous)]
        order=[m['id'] for m in cfg['desktop_panels']];active=manager.active_window
        manager.windows[active].grab().save(str(Path(output)/'ordered-tabs.png'))
        saved=api.load_config();manager.close();cfg.update(saved)
        runtime.panels=manager=DesktopPanels(runtime,roots=[str(demo)]);manager.apply_settings();manager.scan_timer.stop();app.processEvents()
        assert [m['id'] for m in cfg['desktop_panels']]==order and manager.active_window==active
        assert cfg['desktop_entries']==entries
        checks.append('group order: tabMoved forward/back, Qt mouse press/move/release defers page switching, keyboard navigation, synchronized bars, independent/disabled slots, save-failure rollback, staged drag-order cancel/save and restart persist order without changing file references')
        runtime.set_dock_visible(False);assert not api.load_config()['dock_visible'] and not runtime.dock.isVisible()
        runtime.set_dock_visible(True);assert api.load_config()['dock_visible'] and runtime.dock.isVisible()
        cfg['hide_tray']=True;runtime.apply_settings();assert not runtime.tray.isVisible()
        cfg['hide_tray']=False;runtime.apply_settings();assert runtime.tray.isVisible()
        context=runtime.dock.icon_context_menu(-1)
        assert {'设置…','应用批量管理…'} <= {action.text() for action in context.actions()}
        runtime.tray.rebuild();menu=runtime.tray.menu
        menu.popup(QPoint(40,40));app.processEvents();menu.grab().save(str(Path(output)/'tray-menu-aligned.png'));menu.hide()
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32
        user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        runtime.tray.hide();runtime.set_dock_visible(False)
        assert user.PostMessageW(int(runtime.dock.winId()),api.WM_OPEN_SETTINGS,0,0)
        wait_for(app,lambda:runtime.settings_open and runtime.tray.settings_dialog.isVisible())
        settings=runtime.tray.settings_dialog
        from PyQt5.QtWidgets import QPushButton
        from PyQt5.QtGui import QFocusEvent,QMouseEvent
        from PyQt5.QtCore import QEvent,QPointF
        assert not any(b.text()=='显示桌面面板' for b in settings.findChildren(QPushButton))
        target=settings.save
        app.sendEvent(target,QFocusEvent(QEvent.FocusIn,Qt.TabFocusReason))
        assert target.property('keyboardFocus') is True
        app.sendEvent(target,QMouseEvent(QEvent.MouseButtonPress,QPointF(5,5),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        assert target.property('keyboardFocus') is False
        app.sendEvent(target,QMouseEvent(QEvent.MouseButtonRelease,QPointF(-5,-5),Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        app.sendEvent(target,QFocusEvent(QEvent.FocusIn,Qt.MouseFocusReason))
        assert target.property('keyboardFocus') is False
        settings.grab().save(str(Path(output)/'settings-mouse-focus.png'))
        checks.append('settings actions: redundant reveal button removed; mouse press clears rounded focus decoration, Tab reason retains keyboard focus')
        for theme in ('light','dark'):
            apply_theme(app,theme=='light')
            for number,combo in enumerate(settings.findChildren(QComboBox)):
                assert isinstance(combo,ModernComboBox) and isinstance(combo.view(),QListView)
                settings.tabs.setCurrentIndex(next((i for i in range(settings.tabs.count()) if settings.tabs.pages.widget(i).isAncestorOf(combo)),0))
                settings.tabs.pages.currentWidget().ensureWidgetVisible(combo,10,10)
                app.processEvents()
                app.setActiveWindow(settings);combo.setFocus()
                combo.showPopup();app.processEvents()
                assert combo.view().isVisible() and combo.view().sizeHintForRow(0)>=combo.view().fontMetrics().height()+4, (number,combo.currentText(),combo.view().isVisible(),combo.view().sizeHintForRow(0),type(combo.view().itemDelegate()),settings.isVisible(),settings.isMinimized(),combo.isVisible(),combo.isEnabled())
                if number<3:combo.view().window().grab().save(str(Path(output)/('popup-%s-%d.png'%(theme,number))))
                from PyQt5.QtGui import QKeyEvent
                from PyQt5.QtCore import QEvent
                original_index=combo.currentIndex()
                combo.view().setCurrentIndex(combo.model().index(combo.count()-1,combo.modelColumn()))
                app.sendEvent(combo.view(),QKeyEvent(QEvent.KeyPress,Qt.Key_Return,Qt.NoModifier))
                assert combo.currentIndex()==combo.count()-1 and not combo.view().isVisible()
                combo.setCurrentIndex(original_index)
                combo.showPopup();app.sendEvent(combo.view(),QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier))
                assert combo.currentIndex()==original_index and not combo.view().isVisible()
        settings.reject()
        assert runtime.lite_timer.isActive() and runtime.lite_timer.interval()==60000
        runtime.set_lite(True)
        assert api.load_config()['runtime_lite'] and not runtime.dock.blur_timer.isActive()
        runtime.show_settings();assert not runtime.lite and not runtime.lite_timer.isActive()
        settings.reject();assert runtime.lite_timer.isActive()
        checks.append('panel groups: default switches survive scan/reload, merged tabs share position/size and restore active page; matching formats allow duplicate references, per-panel pin/exclusion, originals preserved')
        checks.append('card views: real menu small/large/list switches preserve entries and reload; menus/popups: uniform tray layout, all settings combo popups opened in both themes, Dock settings/batch shortcuts, tray hide and preferred Dock visibility persist; real settings finished signal arms 60000ms lite timer')
    finally:
        runtime.panels.close();cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings()
