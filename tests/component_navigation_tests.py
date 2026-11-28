"""Exercise component shortcuts, staged edits and the frames actually painted."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QWidget


def run(runtime, app, output, checks):
    from component_preferences import COMPONENTS, ComponentPreferences
    from menu_paths import action_at
    from settings_dialog import SettingsDialog
    from settings_catalog import INTERACTION, PAGE_GROUPS, PAGES, VISUALS
    from settings_sections import CAPSULE_SECTIONS, MAIL, MUSIC, NEWS, SIZE, STATUS
    from resource_settings import ResourceOptions
    from command_search import matches
    from quick_actions import ACTIONS, TILE_TINTS

    assert {key for key, _, _ in ACTIONS} == set(TILE_TINTS)
    main = SettingsDialog(runtime.tray, runtime.api)
    main.show()
    app.processEvents()
    try:
        indices=[index for _,members in PAGE_GROUPS for index in members]
        assert sorted(indices)==list(range(len(PAGES)))
        for key,page in (('passthrough_alt_unlock',INTERACTION),('watermark_size',VISUALS)):
            main.focus_setting(key)
            assert main.tabs.currentIndex()==page and main.fields[key].isVisible()
        main.tabs.setCurrentIndex(0)
        menu = main.shortcuts.menu()
        for component, (name, pages) in COMPONENTS.items():
            for index, (title, _, _) in enumerate(pages):
                form = ComponentPreferences(runtime, component, index)
                assert form.tabs.currentIndex() == index and form.tabs.nav.currentItem().text() == title
                form.deleteLater()
            if component != 'note':
                with patch('settings_shortcuts.open_preferences') as opened:
                    menu.aboutToShow.emit()
                    action_at(menu, name, pages[-1][0]).trigger()
                    opened.assert_called_once_with(runtime, component, len(pages)-1)
        with patch.object(runtime.clock,'open_settings') as clock_page:
            menu.aboutToShow.emit()
            action_at(menu,'桌面时钟','工作时间').trigger()
            clock_page.assert_called_once_with(3)
        with patch.object(runtime.resources,'settings') as capsule_page:
            menu.aboutToShow.emit()
            action_at(menu,'灵动胶囊','监控与媒体','任务栏监控').trigger()
            capsule_page.assert_called_once_with(1)
            rows=main.search_targets()
            for query,index in (('应用窗口前收起',6),('麦克风',STATUS),('色块高度',SIZE),
                                ('音乐预览',MUSIC),('验证码',MAIL),('RSS',NEWS)):
                results,_=matches({},[],rows,query,'settings')
                target=next(row for row in results if row['payload']==f'@editor/resource/{index}')
                assert target['detail'].startswith('灵动胶囊 › ')
                main.focus_setting(target['payload'])
                capsule_page.assert_called_with(index)
        editor=ResourceOptions(runtime.resources)
        try:
            ids=[i for _,rows in CAPSULE_SECTIONS for i,*_ in rows]
            assert sorted(ids)==list(range(editor.tabs.count()))
            for index in ids:
                editor.tabs.setCurrentIndex(index)
                assert set(editor.fields)==editor.field_pages[index],(index,set(editor.fields)^editor.field_pages[index])
            editor.category_query.setText('应用窗口前收起')
            assert [index for index in ids if not editor.nav_items[index].isHidden()]==[6]
            editor.category_query.returnPressed.emit()
            assert editor.tabs.currentIndex()==6 and 'resource_app_fold' in editor.fields
            editor.category_query.setText('无匹配条件')
            assert not editor.empty_categories.isHidden()
            editor.category_query.clear()
            assert all(not editor.nav_items[index].isHidden() for index in ids)
        finally:editor.reject();editor.deleteLater()
        checks.append('All main and capsule categories occur once. Search and shortcuts open the same component pages; sidebar filtering finds app folding and restores all categories after clearing.')
        main.grab().save(str(output/'main-component-shortcuts.png'))
        preview=main.dock_preview
        saved_material=runtime.dock.cfg['dock_material']
        main.set_draft_values({'dock_material':'acrylic','theme_color':'#cd785c','glass':True,
                               'transparency':15,'blur_px':22,'clear_background':False})
        frosted=preview.grab().toImage()
        frosted.save(str(output/'dock-preview-acrylic.png'))
        main.set_draft_values({'clear_background':True})
        clear=preview.grab().toImage()
        clear.save(str(output/'dock-preview-clear.png'))
        changes=sum(abs(frosted.pixelColor(x,y).red()-clear.pixelColor(x,y).red())>12
                    for x in range(4,clear.width()-4,3) for y in range(clear.height()//2,clear.height()-4,3))
        assert changes>25 and runtime.dock.cfg['dock_material']==saved_material
        cfg=runtime.dock.cfg
        original=cfg['watermark_size']
        pending=22 if original!=22 else 23
        saved=26 if original!=26 else 27
        editor=ComponentPreferences(runtime,'watermark')
        try:
            main.set_draft_values({'watermark_size':pending})
            editor.fields['watermark_size'].setValue(saved)
            editor.reject()
            assert cfg['watermark_size']==original
            with patch.object(runtime.tray,'settings_dialog',main,create=True):
                main.open_secondary(editor.commit)
            assert cfg['watermark_size']==saved and main.draft_values()['watermark_size']==pending
            assert runtime.api.load_config()['watermark_size']==saved
        finally:
            editor.deleteLater()
            from settings_effects import save_changes
            save_changes(runtime.tray,runtime.api,{'watermark_size':original})
    finally:
        main.reject();main.deleteLater()
    checks.append('Component navigation opens the requested clock, capsule and widget pages. All feature forms mount. Close discards changes and nested Save preserves an existing main draft.')
    picture_frames(runtime,app)
    almanac_frames(runtime)
    checks.append('Daily picture and almanac paint the old, blended and final frames. Rapid picture turns continue from the displayed blend. Hidden transitions release their buffers.')


def picture_frames(runtime,app):
    from resource_content import Picture
    photo=Picture(SimpleNamespace(colors={'hover':'#758797'}))
    photo.resize(220,135);photo.show();app.processEvents()
    try:
        def solid(color):
            image=QImage(80,60,QImage.Format_RGB32);image.fill(QColor(color));return image
        red,blue,green=(solid(c) for c in ('#ff0000','#0000ff','#00ff00'))
        photo.set_image(red);photo.set_image(blue)
        assert photo.fade.currentTime()==0
        photo.fade.setCurrentTime(photo.fade.duration()//2)
        frame=photo.blended_image()
        mid=frame.pixelColor(frame.rect().center())
        assert 120<=mid.red()<=136 and 120<=mid.blue()<=136 and mid.alpha()==255
        photo.set_image(green)
        assert photo.outgoing.pixelColor(photo.outgoing.rect().center())==mid
        photo.fade.setCurrentTime(photo.fade.duration())
        assert photo.outgoing.isNull() and photo.image==green
        photo.set_image(red);photo.hide()
        assert photo.outgoing.isNull() and photo.fade.state()==photo.fade.Stopped
    finally:photo.hide();photo.deleteLater()


def almanac_frames(runtime):
    from almanac_transition import AlmanacTransition
    widget=QWidget()
    widget.dock=runtime.dock
    widget.resize(280,160)
    effect=AlmanacTransition(widget)
    options=runtime.clock.draw_options()
    rect=QRectF(widget.rect())
    def render(minute):
        ratio=widget.devicePixelRatioF()
        image=QImage(widget.size()*ratio,QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio);image.fill(Qt.transparent)
        p=QPainter(image)
        try:effect.paint(p,rect,options,datetime(2026,11,25,9,minute))
        finally:p.end()
        return image
    try:
        old=render(9)
        assert effect.frames is None
        first=render(10)
        assert effect.frames is not None
        effect.animation.setCurrentTime(effect.animation.duration()//2)
        mid=render(10)
        effect.animation.setCurrentTime(effect.animation.duration())
        last=render(10)
        assert (first!=mid and mid!=last and old!=last and effect.frames is None)
        points=[(x,y) for x in range(10,270,9) for y in range(10,150,9)]
        for x,y in points:
            a=first.pixelColor(x,y).red();b=last.pixelColor(x,y).red()
            if abs(a-b)>45:
                assert abs(mid.pixelColor(x,y).red()-(a+b)/2)<8,(x,y,a,mid.pixelColor(x,y).red(),b)
                break
        else:raise AssertionError('Expected a changed illustration')
    finally:
        effect.reset();widget.deleteLater()
