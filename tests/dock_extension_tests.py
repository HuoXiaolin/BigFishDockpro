"""Dock additions, pre-render-only reflections and bounded settings updates."""
import copy,time,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from PyQt5.QtCore import Qt,QPointF,QEvent,QPoint
from PyQt5.QtGui import QPixmap,QPainter,QColor,QFont,QMouseEvent,QWheelEvent,QImage,QRegion
from PyQt5.QtWidgets import QApplication,QWidget,QStyle,QStyleOptionButton
from dock_extras import REFLECTION_BUDGET,DockQuickSettings


def check_quick_controls(popup,dock,output,checks):
    from background_contrast import blend,contrast
    from ui_style import apply_theme
    app=QApplication.instance()
    app_light=app.palette().window().color().lightness()>128
    def check_footer():
        pager = popup.next_button.geometry()
        assert popup.status.text()=='滚轮翻页' and pager.center().y()==popup.status.geometry().center().y()
        assert popup.height()-pager.bottom()-1==popup.layout().contentsMargins().bottom()
        assert popup.layout().count()==3  # Header, tiles, pagination.
    def control_image(button):
        image=QImage(button.size(),QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        button.render(image,QPoint(),QRegion(),QWidget.DrawChildren)
        return image
    def check_buttons():
        for button in (popup.edit_button,popup.reset_button,popup.close_button,popup.prev_button,popup.next_button):
            if not button.isVisible():continue
            opt=QStyleOptionButton();button.initStyleOption(opt)
            area=button.style().subElementRect(QStyle.SE_PushButtonContents,opt,button)
            if button.text():
                assert area.width()>=button.fontMetrics().horizontalAdvance(button.text()), (button.text(),area)
                assert area.height()>=button.fontMetrics().boundingRect(button.text()).height(), (button.text(),area)
            else:
                assert not button.icon().isNull() and button.iconSize().boundedTo(area.size())==button.iconSize()
            fill=control_image(button).pixelColor(4,button.height()//2)
            assert 90<fill.alpha()<255, (button.text(),fill.getRgb())
    try:
        for dark in (True,False):
            apply_theme(app,dark)
            with patch.dict(dock.cfg,theme='dark' if dark else 'light',theme_color='#7450ca',clear_background=True):
                popup.set_page(2);popup.refresh_surface()
                app.processEvents()
                check_footer()
                popup.close();app.processEvents()
                dock.extras.activate('quick');app.processEvents()
                assert dock.extras.popup is popup and popup.isVisible() and popup.pages.currentIndex()==2, (dark,'reopen',popup.isVisible())
                check_buttons()
                apply_theme(app,not dark);app.processEvents()
                assert popup.isVisible(), (dark,'palette change')
                check_buttons()
                frames={}
                for button in (popup.edit_button,popup.close_button,popup.prev_button,popup.next_button):
                    frame=control_image(button);fill=frame.pixelColor(4,frame.height()//2)
                    assert 90<fill.alpha()<255,(dark,button.text(),fill.getRgb())
                    # Real glyphs must have contrast on even the least favourable desktop.
                    paper=(255,255,255) if dark else (0,0,0)
                    surface=blend(fill.getRgb()[:3],paper,fill.alphaF())
                    glyphs=[frame.pixelColor(x,y) for x in range(6,frame.width()-6) for y in range(4,frame.height()-4)]
                    assert any(c.alpha()>245 and contrast(surface,c.name())>=4.5 for c in glyphs),(dark,button.text())
                    frames[button]=frame
                popup.edit_button.click();app.processEvents()
                assert popup.edit_button.isChecked() and popup.reset_button.isVisible(), (dark,popup.editing,popup.isVisible(),popup.reset_button.isHidden())
                check_footer()
                check_buttons()
                reset=control_image(popup.reset_button);assert reset.pixelColor(4,reset.height()//2).alpha()<255
                assert control_image(popup.edit_button).pixelColor(4,popup.edit_button.height()//2)!=frames[popup.edit_button].pixelColor(4,popup.edit_button.height()//2)
                popup.edit_button.click();popup.set_page(0)
                assert not popup.prev_button.isEnabled() and control_image(popup.prev_button)!=frames[popup.prev_button]
                popup.set_page(popup.pages.count()-1)
                assert not popup.next_button.isEnabled()
                popup.set_page(2)
                # Composite the real transparent window on light and dark areas of a test backdrop.
                snap=popup.grab()
                preview=QImage(snap.size(),QImage.Format_RGB32)
                preview.fill(QColor('#d9ddea'))
                p=QPainter(preview);p.fillRect(preview.width()//2,0,preview.width(),preview.height(),QColor('#493b77'))
                p.drawPixmap(preview.rect(),snap);p.end()
                assert preview.save(str(output/('quick-controls-'+('dark' if dark else 'light')+'.png')))
    finally:
        apply_theme(app,app_light);popup.set_page(0);popup.refresh_surface()
    popup.show_feedback('保存失败。'*10,'测试写入错误')
    app.processEvents()
    assert popup.status.geometry().right()<popup.prev_button.x() and popup.rect().contains(popup.next_button.geometry())
    assert popup.status.toolTip()=='测试写入错误'
    popup.status_timer.timeout.emit()
    app.processEvents()
    check_footer()
    checks.append('Quick Settings ends with a single pagination row in normal and sort modes; temporary feedback shares the row without moving the buttons.')
    checks.append('Reopening the third Quick Settings page and changing the application theme keep Dock-tinted translucent buttons with space for the full sort/reset labels and all three navigation glyphs.')
    checks.append('Quick Settings header and page controls render translucent fills and legible glyphs against opposite application themes. Edit, reset and page-boundary states remain distinct.')


def run(api,runtime,root,output,checks):
    cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG));cfg.update(icon_size=46,theme='light',glass=False,dock_material='solid',running_dots=False,
        items=[{'path':str(Path(root)/('demo-app-'+str(i)+'.exe')),'name':'演示应用 '+str(i)} for i in range(1,7)])
    colors=['#3c8dd5','#38aa96','#986ed0','#e78d73','#d4a643','#637ed8']
    def icon(path,pixels,*args,**kwargs):
        pm=QPixmap(96,96);pm.fill(Qt.transparent);p=QPainter(pm);p.setRenderHint(QPainter.Antialiasing)
        i=int(Path(path).stem.rsplit('-',1)[-1])-1;p.setBrush(QColor(colors[i]));p.setPen(Qt.NoPen);p.drawRoundedRect(7,7,82,82,19,19)
        font=QFont('Segoe UI');font.setPixelSize(44);font.setWeight(QFont.Bold);p.setFont(font);p.setPen(Qt.white);p.drawText(pm.rect(),Qt.AlignCenter,chr(65+i));p.end();return pm
    dock=None;original=copy.deepcopy(runtime.dock.cfg)
    try:
        with patch.object(api.IconProvider,'get',side_effect=icon):dock=api.Dock(cfg,preview=True)
        fake_runtime=SimpleNamespace(apply_settings=MagicMock(),show_settings=MagicMock())
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
            dock.mouse_x=-99999;dock.stretch=0;dock._recalc(uniform=True)
            before=list(dock.tgt);rect=dock.rects[1];point=QPointF(rect[0],rect[3]-rect[2]/2)
            QApplication.sendEvent(dock,QMouseEvent(QEvent.MouseMove,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier))
            assert max(abs(a-b) for a,b in zip(before,dock.tgt))>1,'magnify unavailable'
            for _ in range(14):dock._tick()
            dock.grab().save(str(output/'dock-hover-normal.png'))
        dock.mouse_x=-99999;dock.stretch=0;dock.stretch_target=0;dock.hover_index=-1;dock._recalc(uniform=True)
        dock.grab().save(str(output/'dock-reflections-clock.png'))
        from settings_effects import apply_changes
        cfg['dock_icon_shape']='circle'
        with patch.object(dock,'reload') as reload_icons:
            apply_changes(tray,api,dict(cfg,dock_icon_shape='default'))
            reload_icons.assert_not_called()
        images=[it['_circle_icon'].toImage() for it in dock.items]
        assert all(image.pixelColor(0,0).alpha()==0 and image.pixelColor(image.width()//2,4).alpha()==255 for image in images)
        assert len({image.pixelColor(image.width()//2,4).name() for image in images})==len(images)
        assert dock.items[0]['pixmap'].toImage()==baseline_icon
        circular=dock.items[0]['_circle_icon'].cacheKey()
        dock.extras.prepare(dock.items)
        assert dock.items[0]['_circle_icon'].cacheKey()==circular
        with patch('dock_extras.circular_icon',side_effect=AssertionError('Circle composed during drawing')):
            assert dock.grab().save(str(output/'dock-icons-circular.png'))
        cfg['dock_icon_shape']='default'
        apply_changes(tray,api,dict(cfg,dock_icon_shape='circle'))
        assert all('_circle_icon' not in it for it in dock.items)
        assert dock.items[0]['_reflected'].toImage()==combined
        assert dock.extras.clock.isActive() and 0<dock.extras.clock.remainingTime()<=60000
        rectangles=dock.extras.rects();assert {'clock','quick','add'}==set(rectangles)
        # Inspect both text draws and the shared wallpaper sample.
        probe = MagicMock()
        inks = []
        probe.drawText.side_effect = lambda *args: inks.append(probe.setPen.call_args.args[0].name())
        with patch.object(dock, 'preview', False), patch.object(dock, 'update') as repaint, \
                patch('dock_extras.wallpaper_color', side_effect=[(49,18,80),(49,18,80),None,(250,250,250)]) as sample:
            for _ in range(4):
                dock.extras.refresh_clock_ink()
                dock.extras.paint(probe, dock.theme_colors())
            assert inks == ['#ffffff']*6 + ['#000000']*2
            assert repaint.call_count == 2 and sample.call_count == 4
            assert sample.call_args.args[1] == rectangles['clock']
        monitor=dock.screen().geometry().getRect()
        dark=('',None,0,QColor('#311250').rgba(),monitor,monitor)
        bright=('',None,0,QColor('#fafafa').rgba(),monitor,monitor)
        with patch.object(dock,'preview',False), patch('wallpaper_source.wallpaper_key',return_value=dark) as wallpaper, \
             patch('taskbar_surface.composed_color',side_effect=AssertionError('Dock sampled the foreground window')):
            for event in (QEvent.WindowActivate,QEvent.WindowDeactivate,QEvent.WindowActivate):
                QApplication.sendEvent(dock,QEvent(event))
                dock.extras.refresh_clock_ink()
                dock.extras.paint(probe,dock.theme_colors())
                assert inks[-2:]==['#ffffff','#ffffff']
            wallpaper.return_value=bright
            dock.extras.refresh_clock_ink();dock.extras.paint(probe,dock.theme_colors())
            assert inks[-2:]==['#000000','#000000']
        checks.append('Dock time and date keep the same wallpaper-based foreground on window activation and deactivation; changing the wallpaper updates both.')
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
        check_quick_controls(popup,dock,output,checks)
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
        popup.set_page(popup.order().index('search')//9);popup.grab().save(str(output/'dock-quick-productivity.png'));popup.set_page(0)
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
        from PyQt5.QtWidgets import QCheckBox,QComboBox,QLineEdit
        from taskbar_text import MODES as TEXT_MODES
        auto=QCheckBox();text_field=QComboBox();pending=QLineEdit('尚未保存的主题色')
        for title,value in TEXT_MODES:text_field.addItem(title,value)
        from settings_dialog import SettingsDialog
        settings=SimpleNamespace(isVisible=lambda:True,fields={'taskbar_text_mode':text_field,'taskbar_text_auto':auto,'theme_color':pending},
            catalog={'taskbar_text_mode':None,'taskbar_text_auto':None,'theme_color':None},_draft={},_runtime_switch_baseline={},findChildren=lambda *args:[])
        settings.set_draft_values=lambda changes:SettingsDialog.set_draft_values(settings,changes)
        tray.settings_dialog=settings
        for mode,auto_enabled,label in [('light',False,'浅色文字 · 白字'),('dark',False,'深色文字 · 黑字'),
                                        ('dark',True,'随壁纸自动配色'),('system',False,'跟随系统')]:
            before={key:cfg[key] for key in ('taskbar_text_mode','taskbar_text_auto')}
            popup.tiles['taskbar_text'].click()
            saved=api.load_config()
            assert cfg['taskbar_text_mode']==saved['taskbar_text_mode']==text_field.currentData()==mode
            assert cfg['taskbar_text_auto']==saved['taskbar_text_auto']==auto.isChecked()==auto_enabled
            assert text_field.isEnabled() is not auto_enabled
            assert settings._draft['taskbar_text_mode']==mode
            assert popup.tiles['taskbar_text'].value==label
            assert fake_runtime.apply_settings.call_args.args==({key for key in before if cfg[key]!=before[key]},)
            assert not callbacks and pending.text()=='尚未保存的主题色'
        with patch.object(api,'save_config',return_value=False):popup.tiles['taskbar_text'].click()
        assert cfg['taskbar_text_mode']==text_field.currentData()=='system' and '失败' in popup.status.text()
        component.text=SimpleNamespace(error='模拟配色应用失败')
        popup.tiles['taskbar_text'].click()
        assert '失败' in popup.status.text() and popup.status.toolTip()==component.text.error
        component.text.error=''
        for _ in range(3):popup.tiles['taskbar_text'].click()
        assert cfg['taskbar_text_mode']=='system' and not popup.status.toolTip()
        del tray.settings_dialog
        auto.deleteLater();text_field.deleteLater();pending.deleteLater()
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
        for key,field in [('notes','notes_enabled'),('clock','clock_enabled'),('calendar','calendar_enabled'),('watermark','watermark_enabled'),('blur','glass'),('panel_auto_hide','panel_auto_hide'),('corners','screen_corners')]:
            original_value=cfg[field]
            with patch.object(dock,'start_backdrop'):popup.tiles[key].click()
            assert cfg[field]!=original_value and api.load_config()[field]==cfg[field]
            with patch.object(dock,'start_backdrop'):popup.tiles[key].click()
            assert cfg[field]==original_value
        wheel_on(popup.tiles['settings'],120);assert popup.pages.currentIndex()==0
        from quick_actions import normalize_order,DEFAULT_ORDER,PREVIOUS_DEFAULT,PREVIOUS_ORDER,PRIORITY_ORDER,MIME,SHELL_ACTIONS,SYSTEM_ACTIONS,WIDGET_SWITCHES
        def without_system(order):
            return [key for key in order if key not in SYSTEM_ACTIONS and key not in WIDGET_SWITCHES]
        assert [key for key in DEFAULT_ORDER if key not in WIDGET_SWITCHES][:len(PRIORITY_ORDER)]==PRIORITY_ORDER
        assert normalize_order(PREVIOUS_ORDER)==normalize_order(PREVIOUS_DEFAULT)==DEFAULT_ORDER
        reversed_order=list(reversed(PREVIOUS_DEFAULT))
        with_cursor=list(reversed_order)
        with_cursor.insert(with_cursor.index('shell_notifications')+1,'cursor_styles')
        assert normalize_order(reversed_order)==with_cursor+list(WIDGET_SWITCHES)
        assert without_system(normalize_order(['clock','clock','not-an-action']))==['clock']+[key for key in PREVIOUS_ORDER if key!='clock']
        assert DEFAULT_ORDER.index('taskbar_text')==DEFAULT_ORDER.index('taskbar')+1
        assert normalize_order([key for key in DEFAULT_ORDER if key not in SHELL_ACTIONS])==DEFAULT_ORDER
        previous=[key for key in PREVIOUS_ORDER if key not in PRODUCTIVITY_ACTIONS]
        assert normalize_order(previous+['lite'])==DEFAULT_ORDER
        custom_order=list(reversed(previous))
        migrated_order=normalize_order(['lite']+custom_order)
        assert without_system(migrated_order)==custom_order+list(PRODUCTIVITY_ACTIONS)
        index=migrated_order.index('taskbar_text')+1
        assert tuple(migrated_order[index:index+2])==SHELL_ACTIONS
        legacy=[key for key in previous if key!='taskbar_text']
        assert normalize_order(legacy)==DEFAULT_ORDER
        legacy[1],legacy[-1]=legacy[-1],legacy[1]
        assert normalize_order(legacy)==normalize_order(legacy[:-1])==DEFAULT_ORDER
        custom=list(reversed(legacy));upgraded=normalize_order(custom)
        assert upgraded[upgraded.index('taskbar')+1]=='taskbar_text'
        assert [key for key in without_system(upgraded) if key!='taskbar_text' and key not in PRODUCTIVITY_ACTIONS]==custom
        rearranged=['taskbar_text']+custom
        assert without_system(normalize_order(rearranged))==rearranged+list(PRODUCTIVITY_ACTIONS)
        arranged_new=['shell_notifications','references']+[key for key in DEFAULT_ORDER if key not in ('shell_notifications','references')]
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
        popup.tiles[old_order[0]].dropEvent(event);assert event.accept.called and not event.ignore.called
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
        for key,(_,_,field,_,tip) in WIDGET_SWITCHES.items():
            previous_value=cfg[field]
            tile=popup.tiles[key]
            tile.click()
            assert cfg[field]!=previous_value and api.load_config()[field]==cfg[field]
            assert tile.accessibleDescription()==('已开启' if cfg[field] else '已关闭') and tile.toolTip()==tip
            tile.click();assert cfg[field]==previous_value
        size=cfg['icon_size']
        with patch.object(api.IconProvider,'get',side_effect=icon):popup.tiles['size'].click()
        assert cfg['icon_size']!=size
        values=copy.deepcopy(cfg)
        with patch.object(api,'save_config',return_value=False):popup.tiles['magnify'].click()
        assert cfg==values and '失败' in popup.status.text()
        with patch.object(dock,'start_backdrop'):
            for key,field in [('appearance','dock_material'),('position','position'),('panels','panel_enabled')]:
                old_value=cfg[field];popup.tiles[key].click();assert cfg[field]!=old_value and api.load_config()[field]==cfg[field]
        assert 'lite' not in popup.tiles
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
            shape=dialog.fields['dock_icon_shape']
            assert shape.findText('默认')==shape.findData('default') and shape.findText('圆形')==shape.findData('circle')
            shape.setCurrentIndex(shape.findData('circle'))
            dialog.commit()
            assert api.load_config()['dock_icon_shape']=='circle'
            shape.setCurrentIndex(shape.findData('default'))
            dialog.commit()
            assert api.load_config()['dock_icon_shape']=='default'
            assert api.normalize_features(dict(cfg,dock_icon_shape='unknown'))['dock_icon_shape']=='default'
            dialog.tabs.setCurrentIndex(0)
            from PyQt5.QtWidgets import QScrollArea
            page=dialog.tabs.pages.widget(0)
            if isinstance(page,QScrollArea):page.ensureWidgetVisible(dialog.fields['dock_clock'])
            dialog.grab().save(str(output/'dock-extension-settings.png'))
        finally:dialog.reject();dialog.deleteLater()
        (output/'dock-extension-metrics.json').write_text(json.dumps({'reflections':{'icons':len(dock.items),'bytes':memory,'budget_bytes':REFLECTION_BUDGET,'paint_draws_per_icon':1,'paint_generation':False},'unrelated_save_seconds':elapsed,'limits':'isolated UI fixture timing, not a system-wide latency measurement'},indent=2),encoding='utf-8')
        checks.append('Dock extensions: current-page bounded precomposed reflections replace original draw (one call/icon, no paint-time generation/scale cache); time timer minute-aligned/stops disabled; dynamic supported quick actions; local search/undo/layout/reference routes and unavailable/save-failure states, retired tile removed from legacy custom order; taskbar text adjacent migration, three-mode cycle, persistence, main-setting sync without losing edits, backend-independent text control and failure reporting, child-tile wheel paging, component toggles, order sanitation/cross-page swap/save-failure/reopen/reset, exact half bottom reserve and 36-highlight/zero-opacity preset, actual add/grid press-release, setting persistence/failure, all additions disable; hover works before Save; unrelated and unchanged saves skip icon/panel/global-style refresh; rendered snapshots and memory/timing recorded')
        checks.append('Dock icon shape restores the default and persists round mode through the main settings. Rounded icons preserve their source, choose individual backdrop colors and cache the result with reflections outside paint.')
    finally:
        if dock:dock.extras.close();dock.close();dock.deleteLater()
        runtime.dock.cfg.clear();runtime.dock.cfg.update(original);api.save_config(original);runtime.apply_settings()
