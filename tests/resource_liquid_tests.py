"""Native liquid, face and weather checks, exclusively on the private desktop."""
import copy
import time
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QPointF,QRect,QRectF,QEvent
from PyQt5.QtGui import QContextMenuEvent,QMouseEvent,QImage,QPainter,QColor,QScreen
from PyQt5.QtWidgets import QApplication,QWidget


def daily_picture_wallpaper_checks(runtime,app,output,wallpapers,checks):
    from ctypes import addressof,wintypes
    from io import BytesIO
    from PyQt5.QtCore import QStandardPaths
    from PyQt5.QtWidgets import QFileDialog
    from daily_picture_card import DailyPictureCard
    from desktop_panel_tests import wait_for
    from resource_desktop_card import ResourceDesktopCard
    import wallpaper_source as wallpaper

    dock=runtime.dock
    card=DailyPictureCard(runtime)
    detached=ResourceDesktopCard(runtime.resources,'traffic')
    content=card.content
    current=wallpapers[0]
    moment=0.0
    picture_dir=output/'重定向的图片'
    chosen=output/'自选原图.jpg'
    sample=output/'wallpaper-download-fixture.jpg'
    assert QImage(current).save(str(sample),'JPG')
    data=sample.read_bytes()
    url='https://www.bing.com/th?id=OHR.WallpaperTest_UHD.jpg'

    class BingResponse(BytesIO):
        headers={'Content-Length':str(len(data))}

        def geturl(self):return url

    def cache_colors():
        colors=[]
        for window in (card,detached):
            window.grab()
            image=window.glass.image.toImage()
            colors.append(image.pixelColor(image.width()//2,image.height()//2))
        return colors

    try:
        with patch.object(runtime,'daily_picture',card), patch.dict(runtime.resources.desktop_cards,{'traffic':detached}), \
             patch.object(content,'refresh'), patch.object(dock,'start_backdrop'), \
             patch.dict(dock.cfg,{'daily_picture_material':'liquid','panel_opacity':48,'resource_background':'global','panel_material':'liquid'}):
            card.sync();detached.sync_window();app.processEvents()
            screen=QApplication.screenAt(card.geometry().center()) or QApplication.primaryScreen()
            monitor=screen.geometry()
            with patch.object(dock,'preview',False), patch.object(runtime,'_wallpaper_keys',{}), \
                 patch.object(wallpaper,'desktop_wallpaper',side_effect=lambda _: (current,2,QColor('white'),monitor,monitor)), \
                 patch.object(wallpaper,'time',SimpleNamespace(monotonic=lambda:moment)):
                runtime.wallpaper_changed()
                red=cache_colors()
                current=wallpapers[1]
                msg=wintypes.MSG();msg.hWnd=int(dock.winId());msg.message=0x001a;msg.wParam=20
                clock=runtime.clock
                with patch.object(clock,'isVisible',return_value=True), patch.object(clock.refresh_timer,'start') as refresh_clock:
                    runtime.layout.native_filter.nativeEventFilter(b'windows_generic_MSG',addressof(msg))
                    refresh_clock.assert_called_once()
                assert card.glass.image is None and detached.glass.image is None
                blue=cache_colors()
                assert all(first.red()>second.red() and first.blue()<second.blue() for first,second in zip(red,blue))
                runtime.wallpaper_timer.timeout.emit();cache_colors()
                cached=card.glass.image.cacheKey(),detached.glass.image.cacheKey()
                moment+=6;runtime.wallpaper_timer.timeout.emit()
                assert cached==(card.glass.image.cacheKey(),detached.glass.image.cacheKey())
                current=wallpapers[0];moment+=6;runtime.wallpaper_timer.timeout.emit()
                assert cache_colors()==red

                content.items=[dict(date='20261112',original=url,story='')];content.update_controls()
                with patch.object(QStandardPaths,'writableLocation',return_value=str(picture_dir)), \
                     patch.object(QFileDialog,'getSaveFileName',return_value=(str(chosen),'')) as save, \
                     patch('urllib.request.urlopen',side_effect=lambda *args,**kwargs:BingResponse(data)), \
                     patch.object(wallpaper,'set_wallpaper') as setter:
                    content.wallpaper.click();wait_for(app,lambda:content.job is None)
                    saved_wallpaper=picture_dir/'BigFishDock'/'bing-wallpapers'/'Bing-20261112.jpg'
                    setter.assert_called_once_with(saved_wallpaper)
                    save.assert_not_called()
                    assert saved_wallpaper.read_bytes()==data and content.status.text()=='已设为桌面壁纸'
                    content.download.click();wait_for(app,lambda:content.job is None)
                    save.assert_called_once()
                    assert setter.call_count==1 and chosen.read_bytes()==data and content.status.text()=='原图已保存'
    finally:
        card.hide();card.deleteLater();detached.dispose();wallpaper.invalidate_source()
    checks.append('Daily picture and detached resource glass refresh on WM_SETTINGCHANGE and silent wallpaper rotation, with unchanged sources reusing caches. Bing wallpaper saves under the redirected Pictures folder, and Download Original saves to the chosen file. OS wallpaper and HTTP are simulated.')


def run(api,runtime,app,output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from resource_options import DEFAULTS,migrate_docked
    from feature_config import normalize
    from resource_liquid import attached
    from resource_settings import ResourceOptions
    from resource_weather import forecast,clean_cities,DEFAULT_CITIES
    from card_snap import snap_target,touching_edge
    from resource_face import PetFace
    from screen_layout import capture,screen_records
    from ui_style import AlignedMenu
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.processEvents();time.sleep(.005)
    def event(w,kind,pos,global_pos):
        buttons=Qt.NoButton if kind==QEvent.MouseButtonRelease else Qt.LeftButton
        app.sendEvent(w,QMouseEvent(kind,QPointF(pos),QPointF(global_pos),Qt.LeftButton,buttons,Qt.NoModifier))
    def edge_menu(menu,point):
        action=next(action for action in menu.actions() if action.text()=='屏幕边缘吸附')
        assert action.isCheckable() and action.isEnabled() and not action.isChecked()
        action.trigger()
    try:
        assert 'resource_live_glass' not in normalize({'resource_live_glass':True})
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_auto_hide=False,resource_collapsed=True,card_snap=True,card_snap_distance=12,
            resource_face=True,resource_expand_mode='click',resource_weather=True,motion_enabled=True,
            resource_background='custom',resource_appearance=dict(material='liquid',theme='light',color='',opacity=48,blur=8,highlight=45))
        service.sync();w=service.window;extra=service.extras;app.processEvents()
        assert extra and extra.weather_job is None
        assert not w.wallpaper_timer.isActive() and w.liquid.watch.isActive()
        area=(QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen()).availableGeometry()
        demo_area = QRect(-500, 0, 1000, 650)
        middle = QRect(-100, 200, 100, 65)
        assert snap_target(middle, demo_area, [], 12) is None
        assert snap_target(middle, demo_area, [QRect(13, 230, 90, 100)], 12) is None
        assert snap_target(middle, demo_area, [QRect(12, 230, 90, 100)], 12) == (middle.translated(12, 0), 'free')
        assert snap_target(middle, demo_area, [QRect(8, 500, 90, 100)], 12) is None
        near_top=middle.translated(0, -193)
        assert snap_target(near_top, demo_area, [], 12)[1] == 'top'
        assert snap_target(near_top, demo_area, [], 12, snap_edges=False) is None
        assert snap_target(near_top.translated(0,-7), demo_area, [QRect(5,0,90,100)], 12)[1]=='top'
        assert migrate_docked({'resource_edge_snap':False})['resource_peer_snap'] is False
        assert migrate_docked({'resource_edge_snap':False,'resource_peer_snap':True})['resource_peer_snap'] is True
        for edge in ('top','bottom','left','right'):
            rect=attached(QRect(area.center().x()-w.width()//2,area.center().y()-22,w.width(),44),area,edge)
            assert touching_edge(rect,area)==edge
            w.press=QPoint();w.setGeometry(rect);w.press=None;w.liquid.drop(rect.center());pump(.3)
            assert not w.liquid.landing and cfg['resource_edge']==edge and w.geometry()==attached(w.geometry(),area,edge)
            service.fold(False);assert w.geometry()==attached(w.geometry(),area,edge)
            expanded=w.geometry();w.select_page('resources');assert w.geometry()==expanded
            service.fold(True);assert w.geometry()==attached(w.geometry(),area,edge)
            if edge=='top':w.grab().save(str(output/'liquid-attached-top.png'))
        dialog=ResourceOptions(service)
        dialog.fields['resource_edge_snap'].setChecked(False)
        assert dialog.fields['resource_peer_snap'].isChecked() and dialog.commit()
        dialog.deleteLater()
        saved=api.load_config()
        assert not saved['resource_edge_snap'] and saved['resource_peer_snap']
        near=attached(w.geometry(),area,'top').translated(0,7)
        near.moveLeft(area.center().x()-near.width()//2)
        peer=QWidget(None,Qt.Tool|Qt.FramelessWindowHint)
        peer.setGeometry(near.right()+5,near.top(),80,100)
        peer.show()
        try:
            with patch.object(runtime,'daily_picture',peer):
                w.setGeometry(near);assert w.liquid.drop(near.center());pump(.28)
                assert w.pos()==near.topLeft()+QPoint(4,0) and cfg['resource_edge']=='free'
                local=w.rect().center()
                with patch.object(AlignedMenu,'exec_',edge_menu):
                    w.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse,local,w.mapToGlobal(local)))
                assert cfg['resource_edge_snap']
                assert service.set_options(resource_peer_snap=False)
                w.setGeometry(near);assert w.liquid.drop(near.center());pump(.28)
                assert w.pos()==near.topLeft()-QPoint(0,7) and cfg['resource_edge']=='top'
                assert service.set_options(card_snap=False)
                w.setGeometry(near);assert not w.liquid.drop(near.center())
        finally:peer.close();peer.deleteLater()

        assert service.set_options(card_snap=True)
        top=attached(w.geometry(),area,'top')
        # Legacy placement can be flush with the screen even with no saved edge.
        assert service.set_options(resource_edge='free',resource_layout=capture(list(top.getRect()),screen_records()))
        assert w.y()==area.top()
        assert w.animation.isActive()
        start=w.mapToGlobal(QPoint(65,20));event(w,QEvent.MouseButtonPress,QPoint(65,20),start)
        event(w,QEvent.MouseMove,QPoint(65,20),start+QPoint(35,0));app.processEvents()
        assert not w.liquid.bridge or not w.liquid.bridge.isVisible()
        event(w,QEvent.MouseMove,QPoint(65,20),start+QPoint(35,40));app.processEvents()
        assert w.liquid.bridge and w.liquid.bridge.isVisible() and not w.liquid.bridge.path.isEmpty()
        w.liquid.bridge.grab().save(str(output/'liquid-tether.png'));assert w.liquid.down
        w.grab().save(str(output/'liquid-pressed.png'))
        scene=QImage(w.width()+32,w.height()+56,QImage.Format_RGB32);scene.fill(QColor('#173246'))
        origin=QPoint(w.x()-16,area.top());painter=QPainter(scene)
        painter.drawPixmap(w.pos()-origin,w.grab())
        painter.drawPixmap(w.liquid.bridge.pos()-origin,w.liquid.bridge.grab());painter.end()
        assert scene.save(str(output/'readme-resource-edge-tether.png'))
        # Windows can coalesce the last movement into the release event.
        event(w,QEvent.MouseButtonRelease,QPoint(65,20),start+QPoint(35,120))
        assert w.y()==area.top()+120 and not w.liquid.down
        assert w.liquid.broken and w.liquid.bridge.timer.isActive()
        w.liquid.bridge.grab().save(str(output/'liquid-drip.png'))
        pump(.38)
        assert not w.liquid.bridge.isVisible() and not w.liquid.bridge.timer.isActive()
        checks.append('Capsule screen/peer snaps switch and persist independently, respect the global switch, and a flush legacy anchor stretches and finishes its drop after mouse release.')
        # A disabled snap retains normal placement; a failed save restores it.
        old=copy.deepcopy(cfg['resource_layout']);old_edge=cfg['resource_edge'];old_rect=w.geometry()
        with patch.object(service,'set_options',return_value=False):
            w.move(area.center().x()-w.width()//2,area.top()+5);assert w.liquid.drop(w.geometry().center())
        assert cfg['resource_layout']==old and cfg['resource_edge']==old_edge and w.geometry()==old_rect
        service.set_options(motion_enabled=False);assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive()
        w.move(w.x(),w.y()+30);w.liquid.drop(w.geometry().center());assert not w.liquid.landing
        # Seven vector expressions, both app themes, no widget/layout changes.
        montage=QImage(7*90,144,QImage.Format_ARGB32_Premultiplied);montage.fill(Qt.transparent);p=QPainter(montage);p.setRenderHint(QPainter.Antialiasing)
        for row,light in enumerate((True,False)):
            p.fillRect(0,row*72,630,72,QColor('#f3f7fa' if light else '#202532'))
            for i,mood in enumerate(PetFace.MOODS):
                face=PetFace();face.mood=mood;face._near=True;face.blink_at=time.monotonic()+100
                for _ in range(70):face._t=time.monotonic()-.05;face._step(QPointF(),True,.9)
                colors=dict(ink='#172836' if light else '#e1edf3',light=light)
                face.paint(p,i*90+45,row*72+31,.9,1,QPointF(),True,colors)
                p.setPen(QColor(colors['ink']));p.drawText(QRect(i*90,row*72+51,90,17),Qt.AlignCenter,mood)
        p.end();montage.save(str(output/'liquid-seven-faces.png'))
        service.set_options(motion_enabled=True,resource_face=False,resource_halo=False)
        assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive() and not w.animation.isActive()
        # Known cities do not need geocoding. Only a bounded forecast is retained.
        queries=[]
        def lookup(url):
            queries.append(url)
            return dict(current=dict(temperature_2m=16,weather_code=2,relative_humidity_2m=40,wind_speed_10m=8,time='2026-11-07T14:00'),
                daily=dict(time=['2026-11-07','2026-11-08','2026-11-09'],temperature_2m_min=[6,7,8],temperature_2m_max=[17,18,19],weather_code=[2,0,61]))
        extra.weather=[forecast(name,lookup) for name in DEFAULT_CITIES]
        assert len(queries)==3 and all('timezone=auto' in q for q in queries) and extra.weather[1]['name']=='乌鲁木齐'
        assert all('forecast_days=7' in q and 'past_days=1' in q for q in queries)
        def weekly(url):
            result=lookup(url);result['daily']={key:(values*3)[:7] for key,values in result['daily'].items()};return result
        assert len(forecast('天津',weekly)['days'])==7
        assert clean_cities(['天津','天津',' 沈阳 '])==['天津','沈阳']
        try:clean_cities(['天津']*7,True);raise AssertionError('Oversized city list accepted')
        except ValueError:pass
        service.fold(False);w.select_page('weather');pump(.03)
        assert not w.weather_view.notes.isVisible();w.grab().save(str(output/'liquid-weather.png'))
        service.fold(True);w.offset=0;seen=set()
        for page in range(12):w.offset=page;w.grab();seen.update(w.compact_shown)
        assert 'weather' in seen
        # A real PNG exercises the wallpaper crop and material cache even with motion off.
        import wallpaper_source as wallpaper
        screen=QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen()
        monitor=screen.geometry()
        wallpapers=[]
        for color in ('#d14455','#2660ba'):
            source=QImage(64,32,QImage.Format_RGB32);source.fill(QColor(color))
            path=output/f'wallpaper-{color[1:]}.png';assert source.save(str(path))
            wallpapers.append(str(path))
        foreground=QWidget(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint)
        foreground.setGeometry(monitor.adjusted(32,32,-32,-32));foreground.show()
        current=wallpapers[0];now=0.0
        wallpaper.invalidate_source()
        service.set_options(motion_enabled=False, resource_expanded_width=501, resource_expanded_height=321,
                            resource_edge='free', resource_halo=True)
        # Large panels cache the background at half resolution. The four
        # margins must stay transparent and the far side must still be filled.
        try:
            with patch.object(wallpaper,'desktop_wallpaper',side_effect=lambda _: (current,2,QColor('white'),monitor,monitor)), \
                 patch.object(wallpaper,'time',SimpleNamespace(monotonic=lambda:now)), \
                 patch.object(QScreen,'grabWindow',side_effect=AssertionError('Foreground capture forbidden')):
                for compact in (True,False):
                    service.fold(compact)
                    if not compact:w.select_page('resources')
                    current=wallpapers[0];now+=3
                    with patch.object(runtime.dock,'preview',False):
                        w.sync_wallpaper()
                        assert w.wallpaper_timer.isActive()
                        w.grab()
                        first=w.glass.image.toImage()
                        foreground.setStyleSheet('background:#36ed52');foreground.raise_()
                        w.wallpaper_timer.timeout.emit();w.grab()
                        unchanged=w.glass.image.cacheKey()
                        foreground.setStyleSheet('background:#ff00ff');foreground.raise_()
                        now+=6
                        w.wallpaper_timer.timeout.emit();w.grab()
                        assert w.glass.image.cacheKey()==unchanged
                        current=wallpapers[1];now+=6
                        w.wallpaper_timer.timeout.emit()
                        frame=w.grab().toImage()
                        cache=w.glass.image.toImage()
                        x,y=cache.width()*3//4,cache.height()//2
                        assert first.pixelColor(x,y).red()>cache.pixelColor(x,y).red()
                        assert first.pixelColor(x,y).blue()<cache.pixelColor(x,y).blue()
                    w.sync_wallpaper()
                    if compact:assert frame.save(str(output/'liquid-wallpaper-compact.png'))
                assert frame.save(str(output/'liquid-expanded-clip.png'))
                assert cache.width()==round(w.width()*w.devicePixelRatioF()/2)
                for image in (cache,frame):
                    width,height=image.width(),image.height()
                    rim=[(0,height//2),(width-1,height//2),(width//2,0),(width//2,height-1)]
                    alpha=[image.pixelColor(x,y).alpha() for x,y in rim]
                    assert alpha==[0,0,0,0],(image.size(),alpha)
                    assert image.pixelColor(width*3//4,height*3//4).alpha()>240
        finally:
            foreground.close();foreground.deleteLater();wallpaper.invalidate_source()
        daily_picture_wallpaper_checks(runtime,app,output,wallpapers,checks)
        service.fold(True)
        folded_geometry=w.geometry();start=QPoint(w.width()//2,w.height()//2);point=w.mapToGlobal(start)
        event(w,QEvent.MouseButtonPress,start,point)
        event(w,QEvent.MouseButtonRelease,start,point)
        assert not service.compact and w.geometry()!=folded_geometry
        service.fold(True)
        service.set_options(resource_face=True,resource_halo=True,motion_enabled=True);pump(.04)
        assert w.animation.isActive() and w.clock_tick.isActive()
        with patch.object(runtime.dock,'preview',False):w.sync_wallpaper()
        assert w.wallpaper_timer.isActive()
        w.hide();app.processEvents()
        assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive() and not w.wallpaper_timer.isActive()
        assert not extra.weather_timer.isActive()
        assert not w.animation.isActive() and not w.clock_tick.isActive() and not w.rotate.isActive()
        w.show();pump(.04);assert extra.weather_timer.isActive() and w.animation.isActive() and w.clock_tick.isActive()
        w.move(w.x()+30,w.y()+30);w.liquid.drop(w.geometry().center())
        service.set_options(motion_enabled=False)
        assert not w.liquid.landing and w.geometry()==attached(w.geometry(),area,cfg['resource_edge'])
        service.set_options(resource_weather=False);assert service.extras is None and not extra.weather_timer.isActive()
        service.set_options(resource_enabled=False);assert service.extras is None and not w.liquid.watch.isActive()
        checks.append('Liquid capsule: four-edge snap and fold anchoring, finite tether/drip, failed-save restore, seven vector moods in both themes, click expansion, transparent margins at half-resolution, and timers stop on hide/disable.')
        checks.append('Capsule wallpaper: legacy capture preference discarded; compact and expanded cache ignores a changing foreground window and refreshes from a second wallpaper file with motion disabled. Private desktop with fixture wallpapers.')
        checks.append('Weather: Tianjin/Urumqi/Shenyang, Beijing time and three-day parsing, city validation, compact paging, pause when hidden and stop when disabled.')
    finally:
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
