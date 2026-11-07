"""Dock additions, pre-render-only reflections and bounded settings updates."""
import copy,time,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from PyQt5.QtCore import Qt,QPointF,QEvent,QPoint
from PyQt5.QtGui import QPixmap,QPainter,QColor,QFont,QMouseEvent,QWheelEvent
from PyQt5.QtWidgets import QApplication
from dock_extras import REFLECTION_BUDGET,DockQuickSettings


def run(api,runtime,root,output,checks):
    cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG));cfg.update(icon_size=46,theme='light',glass=False,dock_material='solid',lite_enabled=False,running_dots=False,
        items=[{'path':str(Path(root)/('demo-app-'+str(i)+'.exe')),'name':'演示应用 '+str(i)} for i in range(1,7)])
    colors=['#3c8dd5','#38aa96','#986ed0','#e78d73','#d4a643','#637ed8']
    def icon(path,pixels,*args,**kwargs):
        pm=QPixmap(96,96);pm.fill(Qt.transparent);p=QPainter(pm);p.setRenderHint(QPainter.Antialiasing)
        i=int(Path(path).stem.rsplit('-',1)[-1])-1;p.setBrush(QColor(colors[i]));p.setPen(Qt.NoPen);p.drawRoundedRect(7,7,82,82,19,19)
        font=QFont('Segoe UI');font.setPixelSize(44);font.setWeight(QFont.Bold);p.setFont(font);p.setPen(Qt.white);p.drawText(pm.rect(),Qt.AlignCenter,chr(65+i));p.end();return pm
    dock=None;original=copy.deepcopy(runtime.dock.cfg)
    try:
        with patch.object(api.IconProvider,'get',side_effect=icon):dock=api.Dock(cfg,preview=True)
        fake_runtime=SimpleNamespace(lite=False,apply_settings=MagicMock(),show_settings=MagicMock())
        def set_lite(value):fake_runtime.lite=value;dock.lite_mode=value
        fake_runtime.set_lite=set_lite
        tray=SimpleNamespace(cfg=cfg,dock=dock,runtime=fake_runtime,add_icons=MagicMock(),show_settings=MagicMock(),importer=SimpleNamespace(show=MagicMock()))
        dock.tray=tray;dock.show();QApplication.processEvents();dock._recalc(uniform=True)
        gap=dock.bar_rect_f().bottom()-dock.rects[0][3]
        assert abs(gap-(dock.pad_y+dock.extras.reflection_room())/2)<=.5
        from appearance_presets import DOCK_PRESETS,PRESET_IDS
        liquid=DOCK_PRESETS[PRESET_IDS.index('liquid')][1]
        assert liquid['dock_highlight']==36 and liquid['transparency']==100
        baseline_icon=dock.items[0]['pixmap'].toImage();combined=dock.items[0]['_reflected'].toImage()
        memory=sum(it['_reflected'].width()*it['_reflected'].height()*4 for it in dock.items)
        assert memory<=REFLECTION_BUDGET
        edge=combined.width();assert combined.height()>edge
        assert combined.pixelColor(edge//2,edge//2).alpha()>200
        assert all(combined.pixelColor(x,combined.height()-1).alpha()<10 for x in range(edge))
        # Painting and hover frames must never generate a reflection or a scaled
        # original icon. One composite image replaces each original icon draw.
        painter_class=api.QPainter;calls=[]
        class Counter:
            Antialiasing=painter_class.Antialiasing;SmoothPixmapTransform=painter_class.SmoothPixmapTransform;TextAntialiasing=painter_class.TextAntialiasing
            def __init__(self,*args):self.inner=painter_class(*args)
            def __getattr__(self,key):return getattr(self.inner,key)
            def drawPixmap(self,*args):calls.append(1);return self.inner.drawPixmap(*args)
            def __del__(self):
                if self.inner.isActive():self.inner.end()
        with patch('dock_extras.compose_reflection',side_effect=AssertionError('Reflection generated during drawing')),patch.object(dock,'icon_scaled',side_effect=AssertionError('Reflection used frame-time scale cache')):
            with patch.object(api,'QPainter',Counter):dock.grab()
            assert len(calls)==len(dock.items),(len(calls),len(dock.items))
            for lite in (False,True):
                dock.lite_mode=lite;dock.mouse_x=-99999;dock.stretch=0;dock._recalc(uniform=True)
                before=list(dock.tgt);rect=dock.rects[1];point=QPointF(rect[0],rect[3]-rect[2]/2)
                QApplication.sendEvent(dock,QMouseEvent(QEvent.MouseMove,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier))
                assert max(abs(a-b) for a,b in zip(before,dock.tgt))>1,('magnify unavailable',lite)
                for _ in range(14):dock._tick()
                dock.grab().save(str(output/('dock-hover-'+('lite' if lite else 'normal')+'.png')))
        dock.lite_mode=False;dock.mouse_x=-99999;dock.stretch=0;dock.stretch_target=0;dock.hover_index=-1;dock._recalc(uniform=True)
        dock.grab().save(str(output/'dock-reflections-clock.png'))
        assert dock.extras.clock.isActive() and 0<dock.extras.clock.remainingTime()<=60000
        rectangles=dock.extras.rects();assert {'clock','quick','add'}==set(rectangles)
        for i,first in enumerate(rectangles.values()):
            for second in list(rectangles.values())[i+1:]:assert not first.intersects(second)
        apps_right=max(r[0]+r[1]/2 for r in dock.rects);assert apps_right<=min(rect.left() for rect in rectangles.values())
        # Actual press/release dispatch must not accidentally launch an app.
        def click(key):
            pt=dock.extras.rects()[key].center()
            QApplication.sendEvent(dock,QMouseEvent(QEvent.MouseButtonPress,pt,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
            QApplication.sendEvent(dock,QMouseEvent(QEvent.MouseButtonRelease,pt,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        click('add');assert tray.add_icons.call_count==1
        click('quick');QApplication.processEvents();popup=dock.extras.popup
        from quick_actions import ACTIONS,PRODUCTIVITY_ACTIONS
        assert popup.isVisible() and len(popup.tiles)==len(ACTIONS) and popup.pages.count()==(len(ACTIONS)+8)//9
        assert all(tile.height()>=82 for tile in popup.tiles.values()),[tile.size() for tile in popup.tiles.values()]
        popup.tiles['search'].click();assert '暂不可用' in popup.status.text()
        productivity=SimpleNamespace(closed=False,message='已撤销测试整理',history=SimpleNamespace(entries=[{}],message='可撤销：测试整理'),
                                     open_search=MagicMock(),open_layouts=MagicMock(),open_references=MagicMock(),undo=MagicMock(return_value=True))
        fake_runtime.productivity=productivity;popup.refresh()
        assert popup.tiles['undo'].value=='可撤销 · 1 步'
        for key,method in [('search','open_search'),('layouts','open_layouts'),('references','open_references')]:
            popup.tiles[key].click();assert getattr(productivity,method).call_count==1
            popup.show()
        popup.tiles['undo'].click();assert productivity.undo.call_count==1 and popup.status.text()==productivity.message
        productivity.message='保存失败，未撤销。';productivity.undo.return_value=False
        popup.tiles['undo'].click();assert '失败' in popup.status.text()
        popup.set_page(popup.pages.count()-1);popup.grab().save(str(output/'dock-quick-productivity.png'));popup.set_page(0)
        callbacks = []
        component = SimpleNamespace(backend=None, payload=True, install_process=None)
        def install_offline(callback):
            callbacks.append(callback)
            component.install_process = object()
            return True
        component.install_offline = install_offline
        fake_runtime.taskbar = component
        # Text color works without the optional background component, shares the
        # main setting, persists immediately, and preserves unrelated pending edits.
        from PyQt5.QtWidgets import QComboBox,QLineEdit
        from taskbar_text import MODES as TEXT_MODES
        text_field=QComboBox();pending=QLineEdit('尚未保存的主题色')
        for title,value in TEXT_MODES:text_field.addItem(title,value)
        from settings_dialog import SettingsDialog
        settings=SimpleNamespace(isVisible=lambda:True,fields={'taskbar_text_mode':text_field,'theme_color':pending},
            catalog={'taskbar_text_mode':None,'theme_color':None},_draft={},_runtime_switch_baseline={},findChildren=lambda *args:[])
        settings.set_draft_values=lambda changes:SettingsDialog.set_draft_values(settings,changes)
        tray.settings_dialog=settings
        for mode,label in [('light','浅色文字 · 白字'),('dark','深色文字 · 黑字'),('system','跟随系统')]:
            popup.tiles['taskbar_text'].click()
            assert cfg['taskbar_text_mode']==api.load_config()['taskbar_text_mode']==text_field.currentData()==mode
            assert settings._draft['taskbar_text_mode']==mode
            assert popup.tiles['taskbar_text'].value==label
            assert fake_runtime.apply_settings.call_args.args==({'taskbar_text_mode'},)
            assert not callbacks and pending.text()=='尚未保存的主题色'
        with patch.object(api,'save_config',return_value=False):popup.tiles['taskbar_text'].click()
        assert cfg['taskbar_text_mode']==text_field.currentData()=='system' and '失败' in popup.status.text()
        component.text=SimpleNamespace(error='模拟配色应用失败')
        popup.tiles['taskbar_text'].click()
        assert '失败' in popup.status.text() and popup.status.toolTip()==component.text.error
        component.text.error=''
        popup.tiles['taskbar_text'].click();popup.tiles['taskbar_text'].click()
        assert cfg['taskbar_text_mode']=='system' and not popup.status.toolTip()
        del tray.settings_dialog
        text_field.deleteLater();pending.deleteLater()
        popup.tiles['taskbar'].click()
        popup.tiles['taskbar'].click()
        assert len(callbacks) == 1 and popup.tiles['taskbar'].value == '正在安装…'
        assert cfg['taskbar_mode'] == 'system'
        component.install_process = None
        component.backend = object()
        callbacks.pop()(True, '组件已就绪。')
        assert cfg['taskbar_mode'] == api.load_config()['taskbar_mode'] == 'clear'
        assert popup.tiles['taskbar'].value == '全透明'
        popup.tiles['taskbar'].click()
        assert cfg['taskbar_mode'] == 'color'
        component.error='模拟任务栏应用失败';popup.tiles['taskbar'].click()
        assert popup.tiles['taskbar'].value=='应用失败' and '失败' in popup.status.text() and popup.status.toolTip()==component.error
        component.error='';component.status='任务栏效果已应用。';popup.taskbar_status_changed(component.status)
        assert popup.tiles['taskbar'].value!='应用失败' and popup.status.text()==component.status and not popup.status.toolTip()
        component._pending_effect=object();popup.refresh();assert popup.tiles['taskbar'].value=='正在应用…'
        component._pending_effect=None
        before_effect=cfg['taskbar_mode']
        with patch.object(api,'save_config',return_value=False):popup.tiles['taskbar'].click()
        assert cfg['taskbar_mode']==before_effect and '保存失败' in popup.status.text()
        cfg['taskbar_mode'] = 'system'
        del fake_runtime.taskbar
        popup.refresh()
        popup.grab().save(str(output/'dock-quick-settings.png'))
        def wheel_on(widget,delta):
            point=QPointF(widget.rect().center());global_point=QPointF(widget.mapToGlobal(widget.rect().center()))
            event=QWheelEvent(point,global_point,QPoint(),QPoint(0,delta),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
            QApplication.sendEvent(widget,event)
        wheel_on(popup.tiles['flash'],-120);assert popup.pages.currentIndex()==1
        popup.grab().save(str(output/'dock-quick-components.png'))
        for key,field in [('notes','notes_enabled'),('clock','clock_enabled'),('calendar','calendar_enabled'),('blur','glass'),('panel_auto_hide','panel_auto_hide'),('corners','screen_corners')]:
            original_value=cfg[field]
            with patch.object(dock,'start_backdrop'):popup.tiles[key].click()
            assert cfg[field]!=original_value and api.load_config()[field]==cfg[field]
            with patch.object(dock,'start_backdrop'):popup.tiles[key].click()
            assert cfg[field]==original_value
        wheel_on(popup.tiles['settings'],120);assert popup.pages.currentIndex()==0
        from quick_actions import normalize_order,DEFAULT_ORDER,PREVIOUS_ORDER,PRIORITY_ORDER,MIME
        assert DEFAULT_ORDER[:15] == PRIORITY_ORDER and normalize_order(PREVIOUS_ORDER) == DEFAULT_ORDER
        assert normalize_order(['clock','clock','not-an-action'])==['clock']+[key for key in PREVIOUS_ORDER if key!='clock']
        assert DEFAULT_ORDER.index('taskbar_text')==DEFAULT_ORDER.index('taskbar')+1
        previous_twenty=[key for key in PREVIOUS_ORDER if key not in PRODUCTIVITY_ACTIONS]
        assert len(previous_twenty)==20 and normalize_order(previous_twenty)==DEFAULT_ORDER
        custom_twenty=list(reversed(previous_twenty))
        assert normalize_order(custom_twenty)==custom_twenty+list(PRODUCTIVITY_ACTIONS)
        legacy=[key for key in previous_twenty if key!='taskbar_text']
        assert normalize_order(legacy)==DEFAULT_ORDER
        legacy[1],legacy[-1]=legacy[-1],legacy[1]
        assert normalize_order(legacy)==normalize_order(legacy[:-1])==DEFAULT_ORDER
        custom=list(reversed(legacy));upgraded=normalize_order(custom)
        assert upgraded[upgraded.index('taskbar')+1]=='taskbar_text'
        assert [key for key in upgraded if key!='taskbar_text' and key not in PRODUCTIVITY_ACTIONS]==custom
        rearranged=['taskbar_text']+custom
        assert normalize_order(rearranged)==rearranged+list(PRODUCTIVITY_ACTIONS)
        arranged_new=['references']+[key for key in DEFAULT_ORDER if key!='references']
        assert normalize_order(arranged_new)==arranged_new
        popup.toggle_edit();assert popup.editing
        popup.grab().save(str(output/'dock-quick-sort.png'))
        unchanged=cfg['clock_enabled'];popup.tiles['clock'].click();assert cfg['clock_enabled']==unchanged
        old_order=popup.order()
        # Real widget mouse handlers build a move-only drag; external data is rejected.
        from PyQt5.QtCore import QMimeData
        tile=popup.tiles['flash'];center=QPointF(tile.rect().center())
        with patch('dock_extras.QDrag') as make_drag:
            make_drag.return_value.exec_.return_value=Qt.MoveAction
            QApplication.sendEvent(tile,QMouseEvent(QEvent.MouseButtonPress,center,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
            QApplication.sendEvent(tile,QMouseEvent(QEvent.MouseMove,center+QPointF(30,0),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
            QApplication.sendEvent(tile,QMouseEvent(QEvent.MouseButtonRelease,center+QPointF(30,0),Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
            assert make_drag.called and bytes(make_drag.return_value.setMimeData.call_args.args[0].data(MIME))==b'flash'
        assert popup.order()==old_order
        mime=QMimeData();mime.setData(MIME,b'clock')
        external=SimpleNamespace(source=lambda:None,mimeData=lambda:mime)
        assert not popup.valid_drag(external)
        event=SimpleNamespace(source=lambda:popup.tiles['clock'],mimeData=lambda:mime,setDropAction=MagicMock(),accept=MagicMock(),ignore=MagicMock())
        tile.dropEvent(event);assert event.accept.called and not event.ignore.called
        assert popup.order()[0]=='clock' and api.load_config()['dock_quick_order'][0]=='clock'
        assert popup.tiles['clock'].parentWidget() is popup.pages.widget(0)
        duplicate=DockQuickSettings(dock.extras)
        try:assert duplicate.order()==popup.order() and duplicate.tiles['clock'].parentWidget() is duplicate.pages.widget(0)
        finally:duplicate.close();duplicate.deleteLater()
        before_order=popup.order()
        with patch.object(api,'save_config',return_value=False):assert not popup.move_action('clock','add')
        assert popup.order()==before_order
        assert popup.move_to_page('clock',1);assert popup.order()[9]=='clock' and popup.pages.currentIndex()==1
        assert popup.reset_order() and popup.order()==DEFAULT_ORDER
        popup.set_page(0);popup.toggle_edit();assert not popup.editing

        old=cfg['magnify'];popup.tiles['magnify'].click();assert cfg['magnify']!=old and api.load_config()['magnify']==cfg['magnify']
        size=cfg['icon_size']
        with patch.object(api.IconProvider,'get',side_effect=icon):popup.tiles['size'].click()
        assert cfg['icon_size']!=size
        values=copy.deepcopy(cfg)
        with patch.object(api,'save_config',return_value=False):popup.tiles['magnify'].click()
        assert cfg==values and '失败' in popup.status.text()
        with patch.object(dock,'start_backdrop'):
            for key,field in [('appearance','dock_material'),('position','position'),('panels','panel_enabled')]:
                old_value=cfg[field];popup.tiles[key].click();assert cfg[field]!=old_value and api.load_config()[field]==cfg[field]
        old_lite=fake_runtime.lite;popup.tiles['lite'].click();assert fake_runtime.lite!=old_lite
        popup.tiles['manage'].click();assert tray.importer.show.called
        popup.tiles['settings'].click();assert fake_runtime.show_settings.called
        # The actual quick tiles must return to the custom values, including after reopening.
        from quick_cycles import APPEARANCE_FIELDS
        from appearance_presets import DOCK_PRESETS
        cfg.update(icon_size=53,position='custom',custom_bottom=137,theme_color='#9acbd9',transparency=79,blur_px=9,dock_highlight=31)
        expected={key:cfg[key] for key in APPEARANCE_FIELDS}
        with patch.object(api.IconProvider,'get',side_effect=icon),patch.object(dock,'start_backdrop'):
            for key,rounds,fields in [('appearance',len(DOCK_PRESETS)+1,APPEARANCE_FIELDS),('size',5,('icon_size',)),('position',3,('position','custom_bottom'))]:
                original_values={field:cfg[field] for field in fields}
                for _ in range(rounds):popup.tiles[key].click()
                assert {field:cfg[field] for field in fields}==original_values,(key,cfg)
            saved=copy.deepcopy(cfg)
            with patch.object(api,'save_config',return_value=False):popup.tiles['appearance'].click()
            assert cfg==saved
        assert api.load_config()['dock_quick_custom']==cfg['dock_quick_custom']
        popup.close()
        cfg['magnify']=False;dock.stretch=1;dock.mouse_x=dock.rects[0][0];dock._recalc()
        assert max(dock.tgt)<=dock.icon_size+.5
        from settings_effects import apply_changes
        # An unrelated update preference must not reload native icons or panels.
        previous=dict(cfg);cfg['update_use_proxy']=not cfg['update_use_proxy']
        with patch.object(dock,'reload') as reload_icons,patch.object(dock,'start_backdrop') as backdrop:
            apply_changes(tray,api,previous);assert not reload_icons.called and not backdrop.called
        cfg.update(dock_clock=False,dock_quick_settings=False,dock_add_button=False,dock_reflections=False)
        dock.extras.prepare(dock.items);dock.refresh_geometry();dock.extras.sync_clock()
        assert dock.extras.width()==0 and not dock.extras.rects() and not dock.extras.clock.isActive() and all('_reflected' not in it for it in dock.items)
        # Main Save does not repaint the entire application or reload every icon.
        dialog=SettingsDialog(runtime.tray,api);dialog.reveal();dialog.commit()
        try:
            from ui_style import apply_theme
            app=QApplication.instance()
            with patch.object(app,'setStyleSheet') as global_style:apply_theme(app,runtime.dock.is_light());assert not global_style.called
            with patch.object(runtime.dock,'reload') as reload_icons,patch.object(runtime.panels,'apply_settings') as panels:
                dialog.fields['update_use_proxy'].setChecked(not runtime.dock.cfg['update_use_proxy'])
                started=time.perf_counter();dialog.commit();elapsed=time.perf_counter()-started
                assert not reload_icons.called and not panels.called and dialog.isVisible()
                dialog.commit();assert not reload_icons.called and not panels.called
            dialog.tabs.setCurrentIndex(0)
            from PyQt5.QtWidgets import QScrollArea
            page=dialog.tabs.pages.widget(0)
            if isinstance(page,QScrollArea):page.ensureWidgetVisible(dialog.fields['dock_clock'])
            dialog.grab().save(str(output/'dock-extension-settings.png'))
        finally:dialog.reject();dialog.deleteLater()
        (output/'dock-extension-metrics.json').write_text(json.dumps({'reflections':{'icons':len(dock.items),'bytes':memory,'budget_bytes':REFLECTION_BUDGET,'paint_draws_per_icon':1,'paint_generation':False},'unrelated_save_seconds':elapsed,'limits':'isolated UI fixture timing, not a system-wide latency measurement'},indent=2),encoding='utf-8')
        checks.append('Dock extensions: current-page bounded precomposed reflections replace original draw (one call/icon, no paint-time generation/scale cache); time timer minute-aligned/stops disabled; dynamic supported quick actions; local search/undo/layout/reference routes and unavailable/save-failure states, legacy 20-action order retained; taskbar text adjacent migration, three-mode cycle, persistence, main-setting sync without losing edits, backend-independent text control and failure reporting, child-tile wheel paging, component toggles, order sanitation/cross-page swap/save-failure/reopen/reset, exact half bottom reserve and 36-highlight/zero-opacity preset, actual add/grid press-release, setting persistence/failure, all additions disable; hover works before Save and in lite; unrelated and unchanged saves skip icon/panel/global-style refresh; rendered snapshots and memory/timing recorded')
    finally:
        if dock:dock.extras.close();dock.close();dock.deleteLater()
        runtime.dock.cfg.clear();runtime.dock.cfg.update(original);api.save_config(original);runtime.apply_settings()
