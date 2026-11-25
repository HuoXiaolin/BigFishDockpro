"""Native liquid, face and weather checks, exclusively on the private desktop."""
import copy
import time
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QPointF,QRect,QRectF,QEvent
from PyQt5.QtGui import QContextMenuEvent,QMouseEvent,QImage,QPainter,QColor,QScreen
from PyQt5.QtWidgets import QApplication,QWidget


def daily_picture_recovery_checks(runtime,app,output,checks):
    import json
    from daily_picture_card import DailyPictureCard
    from desktop_panel_tests import wait_for
    from ui_test_events import check_edge_resize
    from tempfile import TemporaryDirectory
    from pathlib import Path

    photo=QImage(48,27,QImage.Format_RGB32)
    photo.fill(QColor('#166a92'))
    fixture=output/'daily-recovery-preview.jpg'
    assert photo.save(str(fixture),'JPG')
    preview=fixture.read_bytes()
    day=['19']
    failure=[None]
    requested=[]
    def fetch(url,_maximum):
        requested.append(url)
        if failure[0]=='offline':
            raise OSError('fixture offline')
        if 'HPImageArchive' in url:
            return json.dumps({'images':[dict(urlbase='/th?id=OHR.Fixture'+d,startdate='202611'+d,
                           title='图片'+d,copyright='说明'+d,copyrightlink='/search?q='+d)
                           for d in (day[0],'18')]}).encode()
        if failure[0]=='primary' and url.startswith('https://www.bing.com/'):
            return b'incomplete'
        return b'incomplete' if failure[0]=='image' else preview

    def shown(view):
        return (view.title.text(),view.credit.text(),view.position.text(),view.items[view.index]['story'],
                view.photo.image.pixelColor(4,4).rgb())

    with TemporaryDirectory() as temp, patch.object(runtime.api,'CONFIG_DIR',temp), \
         patch.dict(runtime.dock.cfg,{'daily_picture_enabled':True,'daily_picture_source':'bing',
                                     'daily_picture_layout':{},'daily_picture_manual_size':False,'daily_picture_locked':False}), \
         patch.object(runtime.dock,'preview',False),patch('resource_content.fetch',side_effect=fetch):
        cards=[]
        def open_card():
            card=DailyPictureCard(runtime);cards.append(card)
            card.sync();card.show();app.processEvents()
            wait_for(app,lambda:card.content.job is None)
            return card.content
        try:
            failure[0]='primary'
            view=open_card()
            first=shown(view)
            assert first[:3]==('图片19','说明19','11/19  1/2')
            assert [url.split('/')[2] for url in requested if '/th?' in url]==['www.bing.com','th.bing.com']
            card=view.owner
            app.processEvents()
            wait_for(app,lambda:card.height()==card.layout().sizeHint().height())
            automatic_size=card.size()
            with patch.object(runtime,'daily_picture',card):
                check_edge_resize(card)
                saved_geometry=card.geometry()
                assert runtime.dock.cfg['daily_picture_manual_size']
                assert runtime.api.load_config()['daily_picture_layout']['rect']==list(saved_geometry.getRect())
                assert runtime.set_daily_picture_options(daily_picture_locked=True)
                check_edge_resize(card,locked=True)
                app.processEvents()
                assert card.geometry()==saved_geometry and view.photo.height()>100
                assert card.grab().save(str(output/'daily-picture-edge-resize.png'))
                assert runtime.set_daily_picture_options(daily_picture_locked=False)
                restarted=DailyPictureCard(runtime);cards.append(restarted);restarted.sync()
                assert restarted.geometry()==saved_geometry
                restarted.hide();cards.remove(restarted);restarted.deleteLater()
                assert runtime.set_daily_picture_options(daily_picture_manual_size=False)
                wait_for(app,lambda:card.size()==automatic_size)
            checks.append('Daily picture: all edges and corners resize, lock preserves size, manual frame and photograph layout restore after reopening, default size can be restored.')
            cache=view.picture_cache_path();original=cache.read_bytes()
            failure[0]='offline'
            view.previous.click();wait_for(app,lambda:view.job is None)
            assert shown(view)==first and view.status.isHidden() and view.previous.isEnabled() and not view.newer.isEnabled()
            failure[0]=None;view.next_fetch=0;view.tick();wait_for(app,lambda:view.job is None)
            second=shown(view)
            assert second[:3]==('图片18','说明18','11/18  2/2') and cache.read_bytes()!=original
            saved=cache.read_bytes();day[0]='20';failure[0]='image'
            view.reload.click();assert shown(view)==second and view.status.isHidden()
            wait_for(app,lambda:view.job is None)
            assert shown(view)==second and cache.read_bytes()==saved
            cards[-1].hide();failure[0]='offline'
            restored=open_card()
            assert shown(restored)==second and restored.status.isHidden() and cache.read_bytes()==saved
            failure[0]=None;restored.next_fetch=0;restored.tick();wait_for(app,lambda:restored.job is None)
            assert shown(restored)[:3]==('图片20','说明20','11/20  1/2') and cache.read_bytes()!=saved
            cards[-1].hide();cache.write_bytes(b'incomplete');failure[0]='offline'
            empty=open_card()
            assert not empty.items and empty.photo.image.isNull() and empty.status.text()=='等待每日图片'
            assert cache==Path(temp)/'cache'/'bing-last-preview.bin'
        finally:
            for card in cards:
                card.hide();card.deleteLater()
            app.processEvents()
    checks.append('Daily picture loads from a second Bing image source on a cold start, retains its image and page through outages, corrupt downloads and offline restarts, and updates after recovery.')


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
             patch.dict(dock.cfg,{'daily_picture_material':'liquid','panel_opacity':48,'resource_background':'global',
                                  'resource_backdrop_mode':'wallpaper','panel_material':'liquid'}):
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
    from resource_weather import forecast,clean_cities
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
        from menu_paths import action_at
        action=action_at(menu,'展开与吸附','屏幕边缘吸附')
        assert action.isCheckable() and action.isEnabled() and not action.isChecked()
        action.trigger()
    try:
        assert 'resource_live_glass' not in normalize({'resource_live_glass':True})
        cities=['天津','乌鲁木齐','沈阳']
        assert not DEFAULTS['resource_weather_cities'] and not api.initial_defaults()['resource_weather_cities']
        assert migrate_docked({'resource_weather_cities':cities})['resource_weather_cities']==[]
        assert migrate_docked({'resource_weather_cities':['天津','上海']})['resource_weather_cities']==['天津','上海']
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_auto_hide=False,resource_collapsed=True,card_snap=True,card_snap_distance=12,
            resource_face=True,resource_expand_mode='click',resource_weather=True,motion_enabled=True,resource_backdrop_mode='wallpaper',
            resource_weather_cities=cities,
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
        bridge=w.liquid.bridge
        bridge.grab().save(str(output/'liquid-tether.png'));assert w.liquid.down
        with patch.object(w,'background',dict(w.background,material='clear')):
            clear=bridge.grab().toImage()
            y=clear.height()//2
            edge=[clear.pixelColor(x,y) for x in range(clear.width()) if clear.pixelColor(x,y).alpha()>45]
            assert 2<=len(edge)<clear.width()//3 and clear.pixelColor(clear.width()//2,y).alpha()==0
            assert max(c.lightness() for c in edge)-min(c.lightness() for c in edge)>90
        def material_sample(tint):
            with patch.object(w,'background',dict(w.background,material='solid',color=tint,opacity=90,highlight=0)):
                image=bridge.grab().toImage()
                center=image.rect().center()
                return image.pixelColor(center)
        warm=material_sample('#ff6655');cool=material_sample('#3355ff')
        assert warm.alpha()>0 and cool.alpha()>0 and warm.red()>cool.red() and cool.blue()>warm.blue()
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
        extra.weather=[forecast(name,lookup) for name in cities]
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
        from datetime import datetime,timedelta,timezone
        from resource_weather import active_weather_notice,forecast_rain_end,hourly_rainfall
        from resource_weather_style import weather_accent
        from resource_compact import compact_badges
        zone=timezone(timedelta(hours=8))
        now=datetime.now(zone).replace(second=0,microsecond=0)
        first_hour=now.replace(minute=0)+timedelta(hours=1)
        end=first_hour+timedelta(hours=3)
        times=[(first_hour+timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M') for i in range(6)]
        def notice_forecast(url):
            query=url.split('hourly=',1)[1].split('&',1)[0]
            assert all(key in query for key in ('weather_code','rain','showers','precipitation','snowfall','visibility'))
            return dict(utc_offset_seconds=8*3600,current=dict(temperature_2m=7,weather_code=61,
                         time=now.strftime('%Y-%m-%dT%H:%M')),
                         hourly=dict(time=times,weather_code=[53,95,66,3,2,None],temperature_2m=[6,6,7,8,8,8],
                                     rain=[.2,.6,.5,0,0,None],showers=[0,.8,0,0,0,None],
                                     precipitation=[.2,1.7,.5,0,0,None],snowfall=[0,2.1,0,0,0,None],
                                     visibility=[None,420,2600,3500,4500,None]))
        alert_row=forecast('乌鲁木齐',notice_forecast)
        notice=active_weather_notice(alert_row)
        assert notice and notice['label']=='雨' and notice['until']==end.timestamp()
        slots=alert_row['forecast_hours']
        assert [hour['time'] for hour in slots]==[stamp[11:16] for stamp in times]
        assert [hour['rainfall'] for hour in slots]==[.2,1.4,.5,0,0,None]
        assert slots[1]['snowfall']==2.1 and slots[1]['visibility']==420
        assert hourly_rainfall(dict(code=61,precipitation=2,snowfall=0))==2
        assert hourly_rainfall(dict(code=71,precipitation=2,snowfall=1.4)) is None
        assert forecast_rain_end(slots)==end.timestamp() and forecast_rain_end([slots[1],slots[3]]) is None
        assert not active_weather_notice(alert_row,now.timestamp()+31*60)
        assert not active_weather_notice(dict(alert_row,error='暂时无法更新'))
        extra.weather[1]=alert_row
        with patch.dict(cfg,resource_alert_weather=True):
            service.display();w.grab()
            assert ('weather_notice','雨 · 乌鲁木齐') in compact_badges(service)[0]
            index=w.reminder_kinds.index('weather_notice')
            point=w.reminder_bounds[index].center().toPoint()
            event(w,QEvent.MouseButtonPress,point,w.mapToGlobal(point))
            event(w,QEvent.MouseButtonRelease,point,w.mapToGlobal(point))
            assert not service.compact and w.page_key=='weather'
            assert w.weather_view.city.currentText()=='乌鲁木齐' and w.weather_view.cards.notice==notice
            cards=w.weather_view.cards
            assert cards.trend==slots and cards.trend_kind=='雨' and cards.rain_end==end.timestamp()
            plotted=cards.grab();image=plotted.toImage();ratio=plotted.devicePixelRatio()
            step=(cards.width()-40)/len(slots)
            y=round((cards.notice_height+79-23)*ratio)
            peak_pixel=image.pixelColor(round((31+1.5*step)*ratio),y)
            low_pixel=image.pixelColor(round((31+.5*step)*ratio),y)
            assert peak_pixel==weather_accent({'code':61},cards.owner.colors['light']) and low_pixel!=peak_pixel
            w.grab().save(str(output/'liquid-weather-notice.png'))
            extra.weather[1]=dict(alert_row,code=2,condition='多云',notice=None)
            w.weather_view.refresh()
            assert not cards.notice and cards.trend==slots and cards.rain_end==end.timestamp()
            w.weather_view.select_city('天津')
            assert w.weather_view.cards.notice is None and not w.weather_view.cards.trend
            service.fold(True)
            with patch.dict(cfg,resource_alert_weather=False):
                assert not any(kind=='weather_notice' for kind,value in compact_badges(service)[0])
        extra.weather[1]=forecast('乌鲁木齐',lookup)
        manual_rows=list(extra.weather)
        with patch.object(service,'play_reminder_sound') as cue:
            extra.receive_weather([alert_row])
            cue.assert_not_called()
            extra.weather=manual_rows
            with patch.dict(cfg,resource_weather_alert_sound=True):
                extra.receive_weather([alert_row])
                extra.receive_weather([alert_row])
                extra.receive_weather([dict(name='乌鲁木齐',error='暂时无法更新')])
                extra.receive_weather([alert_row])
                cue.assert_called_once_with('weather')
                extra.receive_weather(manual_rows)
                extra.receive_weather([alert_row])
                assert cue.call_count==2
        extra.weather=manual_rows
        from tempfile import TemporaryDirectory
        from resource_options import DEFAULTS
        from weather_location import WeatherLocation,address_name
        from resource_weather import WeatherJob
        from unittest.mock import Mock
        assert DEFAULTS['resource_weather_location'] is True
        district_coords=(31.226,121.476)
        district_name='上海市 · 徐汇区'
        district_address=dict(countryCode='CN',city='上海市',locality='斜土路街道',localityInfo={'administrative':[
            dict(name='上海市',chinaAdminCode='310000',adminLevel=4),
            dict(name='市辖区',chinaAdminCode='310100'),
            dict(name='徐汇区',chinaAdminCode='310104'),
            dict(name='斜土路街道',chinaAdminCode='310104009',adminLevel=8),
        ]})
        county_address=dict(countryCode='CN',city='昆山市',locality='花桥镇',localityInfo={'administrative':[
            dict(name='苏州市',adminLevel=5),dict(name='昆山市',adminLevel=6),dict(name='花桥镇',adminLevel=8),
        ]})
        assert address_name(district_address)==district_name
        assert address_name(county_address)=='苏州市 · 昆山市'
        assert address_name(dict(district_address,localityInfo={'administrative':[None,{'adminLevel':8,'name':'斜土路街道'}]}))=='上海市'
        assert address_name(dict(district_address,lookupSource='ip-geolocation'))=='当前位置'
        with TemporaryDirectory(dir=output) as directory:
            import json
            from pathlib import Path
            cache=Path(directory)/'weather-location.json'
            cache.write_text(json.dumps(dict(day=now.date().isoformat(),name='上海市',latitude=31.226,longitude=121.476)),encoding='utf-8')
            with patch('weather_location.date') as local_date:
                local_date.today.return_value=now.date()
                fixes=dict(latitude=31.2264,longitude=121.4764)
                moved=dict(latitude=31.301,longitude=121.094)
                queries=[]
                def city_from_position(url):
                    queries.append(url)
                    if 'latitude=31.301&longitude=121.094' in url:
                        return county_address
                    assert 'latitude=31.226&longitude=121.476' in url
                    return district_address
                position=Mock(side_effect=[fixes,fixes,dict(status='timeout'),fixes,moved,
                                            dict(status='timeout'),dict(status='permission')])
                def requested(location,refresh=False):
                    return location.resolve(directory,city_from_position,lambda:False,read=position,refresh=refresh)
                expected=((district_name,district_coords),'ready')
                first=WeatherLocation()
                assert requested(first)==requested(first)==expected
                position.assert_called_once_with(refresh=False)
                restarted=WeatherLocation()
                assert requested(restarted)==requested(restarted)==expected
                assert position.call_count==2 and len(queries)==1
                saved=cache.read_bytes()
                local_date.today.return_value=now.date()+timedelta(days=1)
                assert requested(restarted)==requested(restarted)==(expected[0],'timeout')
                assert position.call_count==3 and cache.read_bytes()==saved
                assert requested(restarted,refresh=True)==requested(restarted)==expected
                assert position.call_count==4 and len(queries)==2
                after_move=('苏州市 · 昆山市',(31.301,121.094))
                assert requested(restarted,refresh=True)==requested(restarted)==(after_move,'ready')
                assert position.call_count==5 and len(queries)==3
                saved=cache.read_bytes()
                assert requested(restarted,refresh=True)==(after_move,'timeout')
                assert requested(restarted,refresh=True)==(after_move,'permission')
                assert position.call_count==7 and len(queries)==3 and cache.read_bytes()==saved
                offline=Mock(return_value=None)
                assert WeatherLocation().resolve(directory,city_from_position,lambda:False,read=offline)==(after_move,'unavailable')
                offline.assert_called_once_with(refresh=False)
                assert cache.read_bytes()==saved and len(queries)==3

                def crossing_midnight(*,refresh):
                    assert not refresh
                    local_date.today.return_value=now.date()+timedelta(days=2)
                    return fixes
                midnight=WeatherLocation()
                location=midnight.resolve(directory,city_from_position,lambda:False,read=crossing_midnight)
                assert location==requested(midnight)==expected and position.call_count==7
        with TemporaryDirectory(dir=output) as directory, \
                patch('weather_location.windows_position',return_value=fixes) as refreshed_position, \
                patch('resource_weather.fetch_json',return_value=district_address), \
                patch('resource_weather.forecast') as weather_forecast, \
                patch.object(WeatherJob,'read_air',return_value=({},'')):
            job=WeatherJob([],location_dir=directory,refresh_location=True)
            located_rows=[];positions=[]
            job.location_ready.connect(lambda name,status:positions.append((name,status)))
            job.ready.connect(located_rows.extend)
            def read_forecast(name,coordinates):
                assert positions==[(district_name,'ready')]
                return forecast(name,lookup,coordinates=coordinates)
            weather_forecast.side_effect=read_forecast
            job.run()
            refreshed_position.assert_called_once_with(refresh=True)
            weather_forecast.assert_called_once_with(district_name,coordinates=district_coords)
            assert len(located_rows)==1 and located_rows[0]['located'] and located_rows[0]['temperature']==16
            feature_visible=service.feature_visible
            with patch.object(runtime.dock,'preview',False),patch('resource_weather.WeatherJob') as jobs, \
                    patch.object(runtime.api,'CONFIG_DIR',directory),patch.object(extra,'location_name',None), \
                    patch.object(service,'feature_visible',side_effect=lambda key:key!='weather' and feature_visible(key)):
                extra.cancel();extra.weather_timer.stop()
                service.sync()
                assert service.extras is extra and extra.located_city()==district_name
                w.weather_view.refresh()
                assert w.weather_view.city.currentText()==district_name and '上次定位' in w.weather_view.city.toolTip()
                assert not w.weather_view.refresh_button.isEnabled()
                jobs.assert_called_once()
                assert jobs.call_args.kwargs['location_session'] is service.weather_location
                jobs.return_value.start.assert_called_once()
                assert service.compact and extra.weather_timer.isActive()
                extra.cancel();extra.weather_timer.timeout.emit()
                assert jobs.call_count==2 and jobs.call_args.kwargs['location_session'] is service.weather_location
                extra.cancel()
        w.weather_view.refresh()
        with patch.object(extra,'refresh_weather') as refresh:
            w.weather_view.refresh_button.click()
            refresh.assert_called_once_with(refresh_location=True)
        local_row=located_rows[0]
        with patch.dict(cfg,resource_weather_cities=[]):
            extra.weather=[local_row]
            w.weather_view.refresh()
            assert w.weather_view.city.count()==1 and w.weather_view.city.currentText()==district_name
            assert w.weather_view.city.toolTip()==district_name
        extra.weather=[local_row,*manual_rows]
        w.weather_view.refresh()
        assert w.weather_view.city.itemText(0)==w.weather_view.city.currentText()==district_name
        w.weather_view.select_city('天津');w.weather_view.refresh()
        assert w.weather_view.city.currentText()=='天津'
        extra.weather.pop(0)
        w.weather_view.refresh()
        checks.append('Weather notice and location: the rain block opens its city, the hourly chart paints the liquid-rain peak, and the first dry hour is marked.')
        checks.append('Weather locates at startup even while hidden, once per launch and local date change, and refreshes the position and forecast on demand. A midnight-spanning request covers the new day.')
        checks.append('Weather district location: the reported county boundary outranks street names, legacy cached labels are upgraded, and the district forecast uses the rounded device coordinates.')
        checks.append('Weather shows the last saved district while locating and retains it across timeouts, denied access, and restarts. The location result is emitted before the forecast request.')
        checks.append('Weather defaults and audio: the located city appears first, manual cities stay selectable, and the opt-in cue plays once for a new condition.')
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
        daily_picture_recovery_checks(runtime,app,output,checks)
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
        checks.append('Weather: city forecasts and compact paging, fresh weather reminder opens the matching city, hourly end estimate and stale suppression, hide and disable lifecycle.')
    finally:
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
