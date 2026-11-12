"""Regressions for narrow resident content, face controls and weather."""
import copy,time
from unittest.mock import patch
from PyQt5.QtCore import Qt,QEvent,QPointF,QRectF,QPoint
from PyQt5.QtGui import QPainter,QImage,QColor,QCursor,QMouseEvent,QFontMetrics,QWheelEvent


def check_news_presets(options):
    from types import SimpleNamespace
    from PyQt5.QtWidgets import QPushButton
    from content_sources import MAX_NEWS_FEEDS, NEWS_FEED_PRESETS
    from feature_config import normalize
    from resource_content import ContentView

    defaults=[url for _,url in NEWS_FEED_PRESETS]
    custom='https://example.org/feed.xml'
    assert normalize({})['resource_news_feeds']==defaults
    assert normalize({'resource_news_feeds':[custom]})['resource_news_feeds']==[custom]
    assert normalize({'resource_news_feeds':[]})['resource_news_feeds']==[]
    assert normalize({'resource_news_feeds':[custom], 'resource_news_disabled_feeds':[custom,defaults[0]]})['resource_news_disabled_feeds']==[custom]

    options.tabs.setCurrentIndex(7)
    menu=options.tabs.widget(7).findChild(QPushButton,'NewsFeedPresets').menu()
    actions={action.text():action for action in menu.actions() if not action.isSeparator()}
    options.news_feeds.setPlainText(custom)
    actions['IT之家'].trigger()
    assert options.news_feeds.toPlainText().split()==[custom,defaults[1]]
    actions['IT之家'].trigger()
    assert '已在列表中' in options.status.text()
    actions['添加全部内置源'].trigger()
    merged=[custom,defaults[1],defaults[0],defaults[2]]
    assert options.news_feeds.toPlainText().split()==merged

    full='\n'.join(f'https://example.org/feed-{i}.xml' for i in range(MAX_NEWS_FEEDS))
    options.news_feeds.setPlainText(full)
    actions['添加全部内置源'].trigger()
    assert options.news_feeds.toPlainText()==full and f'最多 {MAX_NEWS_FEEDS} 个' in options.status.text()
    options.news_feeds.setPlainText('\n'.join(merged))
    sources=options.news_source_list
    sources.item(0).setCheckState(Qt.Unchecked)
    sources.item(1).setCheckState(Qt.Unchecked)
    sources.item(1).setCheckState(Qt.Checked)
    sources.item(2).setCheckState(Qt.Unchecked)
    disabled=[custom,defaults[0]]
    options.tabs.setCurrentIndex(6)
    options.tabs.setCurrentIndex(7)
    assert options.news_feeds.toPlainText().split()==merged
    sources=options.news_source_list
    assert [sources.item(i).data(Qt.UserRole) for i in range(sources.count()) if sources.item(i).checkState()==Qt.Unchecked]==disabled

    cfg={'resource_news_feeds':merged, 'resource_news_disabled_feeds':disabled}
    view=ContentView(SimpleNamespace(service=SimpleNamespace(cfg=cfg)), 'news')
    try:
        with patch.object(view,'isVisible',return_value=True), patch.object(view,'start') as start:
            view.refresh()
            assert view.source==(defaults[1],defaults[2])
            start.assert_called_once_with(renew=True)
            start.reset_mock()
            cfg['resource_news_disabled_feeds']=merged
            view.refresh()
            assert view.source==() and not view.reload.isEnabled()
            start.assert_not_called()
    finally:
        view.deleteLater()
    return merged,disabled


def check_compact_scroll(window,app,output,checks):
    from resource_compact import plan
    from resource_panel import COMPACT_SCROLL_SECONDS

    cfg=window.service.cfg
    options=dict(resource_compact_width=392,resource_compact_height=35,
                 resource_compact_pinned=['cpu','ai','weather'],resource_face_interactive=False,
                 resource_halo=False,resource_compact_rotate=True,motion_enabled=True)
    original={key:cfg[key] for key in options}
    point=QPointF(45,17)

    def wheel(delta):
        event=QWheelEvent(point,QPointF(window.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,delta),
                          Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        app.sendEvent(window,event)
        assert event.isAccepted()

    def finish():
        with patch('resource_panel.time.monotonic',return_value=window.compact_scroll[1]+COMPACT_SCROLL_SECONDS+.01):
            window.animate()

    def bounds(key):
        return [rect for name,rect in zip(window.compact_shown,window.compact_bounds) if name==key]

    def middle(direction):
        assert window.compact_scroll[2]==direction and window.animation.interval()==16
        since=window.compact_scroll[1]
        with patch('resource_panel.time.monotonic',return_value=since+COMPACT_SCROLL_SECONDS/2):
            image=window.grab()
        outgoing,incoming=bounds('weather')
        assert (outgoing.center().y()-incoming.center().y())*direction<0
        assert not outgoing.intersects(incoming)
        assert bounds('cpu')==cpu and window.reminder_bounds==reminders and window.geometry()==geometry
        assert len(window.compact_providers)==2
        assert image.save(str(output/f'compact-scroll-{direction}.png'))

    try:
        cfg.update(options)
        with patch.object(window.service,'reminders',return_value=(('focus','04:45'),)):
            window.offset=0;window.sync_window();window.grab()
            assert len(plan(window,window.width())['pages'])>2
            cpu=bounds('cpu');reminders=window.reminder_bounds;geometry=window.geometry()
            assert cpu and reminders and not window.animation.isActive()
            wheel(-120);middle(1);finish()
            assert window.offset==1 and not window.compact_scroll and not window.animation.isActive()
            wheel(120);middle(-1)
            wheel(-120);wheel(-120);finish()
            assert window.offset==2 and window.compact_scroll[0]==0
            finish()
            with patch.object(window,'underMouse',return_value=False):
                window.rotate.timeout.emit()
            assert window.offset==3 and window.compact_scroll[2]==1
            cfg['motion_enabled']=False;window.sync_animation()
            assert not window.compact_scroll and not window.animation.isActive()
            wheel(120)
            assert window.offset==2 and not window.compact_scroll and not window.animation.isActive()
    finally:
        cfg.update(original);window.offset=0;window.sync_window()
    checks.append('Compact pages and rotating pinned cells scroll vertically in both directions; fixed readings and reminder hit regions stay aligned, rapid wheel events settle, and animation obeys the motion setting.')


def run(api,runtime,app,output,checks):
    from resource_options import DEFAULTS
    from resource_redesign_tests import fixtures
    from resource_compact import plan
    from resource_settings import ResourceOptions
    from resource_status import band_ink
    from resource_weather_style import weather_kind,compact_temperature_ink,air_quality_style
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_auto_hide=False,resource_collapsed=True,
            resource_ai=True,resource_music=True,resource_weather=True,resource_face=True,
            resource_expand_mode='click',resource_compact_width=292,resource_compact_height=50,resource_compact_auto_width=False,
            resource_background='custom',resource_appearance=dict(material='solid',theme='light',color='',opacity=98,blur=8,highlight=40))
        service.sync();w=service.window;extra=service.extras;deck=service.deck
        deck.accept(dict(type='ai',providers=fixtures()));deck.alert_until=0
        deck.accept(dict(type='media',tracks=[],track=dict(title='海风',state='Playing',duration=120,position=30)))
        deck.levels=[.2,.8,.5,.9,.2,.5,.3,.6]
        from datetime import date,timedelta
        extra.weather=[dict(name=name,temperature=9,code=code,condition=condition,days=[dict(date=(date.today()+timedelta(days=i)).isoformat(),low=1-i,high=12-i,condition=condition) for i in range(-1,7)])
                       for name,code,condition in [('天津',51,'毛毛雨'),('乌鲁木齐',0,'晴'),('沈阳',2,'多云')]]
        service.accept_sample(dict(time=time.monotonic(),cpu=37,gpu=21,memory=(62,8,16),network=(1024,2048)))
        for width,height in [(292,50),(220,38),(96,28),(560,44)]:
            cfg.update(resource_compact_width=width,resource_compact_height=height);w.sync_window();app.processEvents()
            seen=set();providers=set();music=False;core=None
            for page in range(len(plan(w,w.width())['pages'])):
                w.offset=page;w.grab();seen.update(w.compact_shown);providers.update(w.compact_providers);music|=w.compact_media
                bounds=w.compact_bounds
                assert len(bounds)==len(w.compact_shown) and all(QRectF(w.rect()).contains(r) for r in bounds)
                for i,r in enumerate(bounds):assert all(not r.intersects(other) for other in bounds[i+1:])
                actual=[r[0] for r in plan(w,w.width())['pinned']]
                if core is None:core=actual
                assert actual==core and ('cpu' in actual or width<128)
                assert plan(w,w.width())['face']>0
                assert all(r.left()>=8+plan(w,w.width())['face'] for r in bounds)
                if width>=292:assert {'cpu','memory','gpu','network'}<=set(w.compact_shown)
            assert {'cpu','memory','gpu','network','weather'}<=seen and providers=={'Codex','Claude'} and music,(width,seen,providers,music)
            w.offset=0;w.grab().save(str(output/f'companion-resident-{width}x{height}.png'))
        cfg.update(resource_compact_pinned=['ai','music','weather'],resource_compact_width=560)
        w.sync_window();seen_cities=set()
        for page in range(len(plan(w,w.width())['pages'])):
            w.offset=page;w.grab();assert {'ai','music','weather'}<=set(w.compact_shown)
            seen_cities.update(r[1] for r in plan(w,w.width())['pinned'] if r[0]=='weather')
        assert seen_cities=={'天津','乌鲁木齐','沈阳'}
        w.offset=0;assert w.grab().save(str(output/'readme-compact-content.png'))
        check_compact_scroll(w,app,output,checks)
        import resource_compact
        import resource_provider_icons as marks
        original_height=cfg['resource_compact_height']
        options=ResourceOptions(service)
        badge_size=options.fields['resource_compact_badge_height']
        assert (badge_size.minimum(),badge_size.value(),badge_size.maximum())==(16,20,40)
        badge_size.setValue(24)
        assert options.commit() and api.load_config()['resource_compact_badge_height']==24
        options.reject();options.deleteLater()
        badges=[]
        paint_chip=resource_compact.chip

        def record_badge(painter,rect,ink,light):
            badges.append((rect.height(),rect.center().y()))
            paint_chip(painter,rect,ink,light)

        with patch.object(service,'reminders',return_value=(('focus','04:45'),)):
            for height,requested,expected in ((35,20,20),(35,24,24),(28,24,24),(28,40,24),(35,16,16)):
                cfg.update(resource_compact_height=height,resource_compact_badge_height=requested)
                w.sync_window();w.refresh();w.offset=0
                badges.clear()
                with patch.object(resource_compact,'chip',record_badge):
                    preview=w.grab()
                assert {'ai','weather','music'}<=set(w.compact_shown) and w.reminder_kinds==['focus']
                assert badges==[(expected,w.height()/2)]*4
                if height==35 and requested in (20,24):
                    assert preview.save(str(output/f'compact-badges-{requested}px.png'))
        cfg.update(resource_compact_height=original_height,resource_compact_badge_height=20)
        assert all(marks.provider_art(name, '#223744') for name in set(marks.PROVIDER_MARKS.values()))
        deepseek_mark = marks.provider_art('deepseek-color.svg', '#223744')
        assert deepseek_mark.aspectRatioMode() == Qt.KeepAspectRatio
        codex_mark = marks.provider_art('codex.png', '#223744')
        assert isinstance(codex_mark, QImage) and codex_mark.width() == codex_mark.height() == 104
        balance = dict(id='Dsh', name='DeepSeek Harness',
                       quotas=[dict(kind='balance', label='账户余额', value='¥12.48')])
        deck.accept(dict(type='ai', providers=[balance, *fixtures()]))
        cfg.update(resource_compact_width=220,resource_compact_pinned=['ai'])
        painted_amounts=[]
        draw_text=resource_compact.text

        def record_amount(painter, rect, value, color, size=11, bold=False, *args, **kwargs):
            if value in ('¥12.48','61%'):
                font=resource_compact.ai_value_font()
                font.setPixelSize(size)
                assert QFontMetrics(font).horizontalAdvance(value) <= rect.width()
                painted_amounts.append(value)
            draw_text(painter, rect, value, color, size, bold, *args, **kwargs)

        for theme in ('light','dark'):
            cfg['resource_appearance']['theme']=theme
            w.sync_window()
            for page, provider, mark, value, shot in (
                (0,'Dsh','deepseek-color.svg','¥12.48','balance'),
                (1,'Codex','codex.png','61%','codex'),
            ):
                w.offset=page
                painted_amounts.clear()
                with patch.object(resource_compact,'text',record_amount), patch.object(marks,'provider_art',wraps=marks.provider_art) as art:
                    image=w.grab()
                assert provider in w.compact_providers and value in painted_amounts
                assert any(call.args[0]==mark for call in art.call_args_list)
                assert image.save(str(output/f'compact-provider-{shot}-{theme}.png'))
        cfg['resource_appearance']['theme']='light'
        deck.accept(dict(type='ai', providers=fixtures()))
        checks.append('Compact AI quota shows official Codex with 61% and DeepSeek with the complete CNY 12.48 balance at 220 px in both themes.')
        checks.append('Compact badge height defaults to 20 px and saves through settings. AI, weather, music and reminders share the selected height and center, limited to available space.')
        # A long pinned list cannot evict an enabled face, including after save.
        cfg.update(resource_compact_width=300,resource_compact_pinned=['cpu','memory','network','ai','music','weather']);w.sync_window();w.grab()
        assert plan(w,w.width())['face']>0
        assert plan(w,w.width())['face_gap']==4 and plan(w,w.width())['gap']==1.5
        w.grab().save(str(output/'face-reserved-many-pins.png'))
        cfg['resource_compact_order']=['memory','cpu','network']
        w.refresh()
        assert [row[0] for row in plan(w,w.width())['pinned'][:2]]==['memory','cpu']
        cfg['resource_compact_order']=[]
        from resource_face import PetFace
        face = PetFace()
        face._step(QPointF(12, 0), True, .7)
        mood = face.mood
        face._step(QPointF(120, 0), False, .7)
        assert mood in PetFace.MOODS and face._m == mood
        cfg.update(resource_face_interactive=True,resource_face_mood='default',motion_enabled=True)
        for shape,collapsed in [('pill',True),('ball',True),('pill',False)]:
            cfg.update(resource_fold=shape,resource_collapsed=collapsed);service.auto_compact=None;service.sync();w.grab()
            assert w.liquid.watch.isActive()
            center=w.liquid.face_bounds.center();positions=[]
            for direction in (-1,1):
                w.liquid.face_until=time.monotonic()-1;w.liquid.face_frame()
                position=w.mapToGlobal(center+QPoint(direction*1250,direction*620))
                with patch.object(QCursor,'pos',return_value=position):
                    w.liquid.watch_face()
                    assert w.liquid.frames.isActive() and not w.liquid.was_near
                    for _ in range(16):w.liquid.face._t-=.033;w.grab()
                    positions.append((w.liquid.face.ex.x,w.liquid.face.ey.x))
                    w.grab().save(str(output/f'face-follow-{shape}-{collapsed}-{direction}.png'))
            assert positions[0][0]<-.4 and positions[1][0]>.4 and positions[0][1]<positions[1][1]
            w.liquid.face_until=time.monotonic()-1;w.liquid.face_frame();assert not w.liquid.frames.isActive()
        cfg.update(resource_fold='pill',resource_collapsed=True,resource_compact_width=560);service.sync()
        # Face switches are independent of motion and the automatic collapse setting.
        cfg.update(resource_face_mood='love',resource_face_interactive=False,resource_face_scale=75);w.sync_window();w.grab()
        assert w.liquid.face._m=='love' and not w.liquid.watch.isActive() and not w.liquid.frames.isActive()
        w.enterEvent(QEvent(QEvent.Enter));assert not w.enter_timer.isActive()
        cfg.update(resource_expand_mode='hover');w.sync_window();w.enterEvent(QEvent(QEvent.Enter));assert w.enter_timer.isActive()
        w.enter_timer.stop()
        with patch.object(QCursor,'pos',return_value=w.geometry().center()):w.expand_hover()
        assert not service.compact,'Hover mode must work with automatic collapse disabled'
        service.fold(True);cfg['resource_expand_mode']='click';w.sync_window()
        with patch.object(QCursor,'pos',return_value=w.geometry().center()):w.expand_hover()
        assert service.compact
        point=QPointF(w.rect().center());global_point=QPointF(w.mapToGlobal(point.toPoint()))
        for kind,buttons in [(QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)]:
            app.sendEvent(w,QMouseEvent(kind,point,global_point,Qt.LeftButton,buttons,Qt.NoModifier))
        assert not service.compact
        assert w.header_face_width>0
        paint_face = w.liquid.paint_face
        face_calls = []
        def count_face(painter, center, size):
            face_calls.append(True)
            paint_face(painter, center, size)
        # A Mock would retain the active painter beyond the lifetime of grab().
        with patch.object(w.liquid, 'paint_face', new=count_face):
            w.grab()
        assert len(face_calls) == 1
        cfg.update(resource_expanded_width=260,resource_expanded_height=180);w.sync_window();app.processEvents();geometry=w.geometry()
        for page in w.page_buttons:
            w.select_page(page)
            for _ in range(6):app.processEvents();time.sleep(.01)
            assert w.geometry()==geometry
            assert w.nav_end<=w.settings_button.x() and all(b.isVisible() for b in w.nav_arrows)
            w.grab().save(str(output/f'companion-small-{page}.png'))
        w.nav.horizontalScrollBar().setValue(0);w.nav_arrows[1].click();assert w.nav.horizontalScrollBar().value()>0
        # All condition scenes render in both themes with a bounded vector surface.
        codes=[0,2,3,51,71,45,95];kinds=['sun','cloud','overcast','rain','snow','fog','storm']
        assert [weather_kind(dict(code=n)) for n in codes]==kinds
        thresholds=cfg['resource_weather_thresholds']
        for light in (True,False):
            for degrees in ((-18,-8,-1),(0,8,15),(16,21,26),(27,28,30),(31,37,45)):
                assert len({compact_temperature_ink(n,light,thresholds) for n in degrees})==3
            assert compact_temperature_ink(26,light,thresholds)==band_ink(26,16,26,'green',light)
            assert compact_temperature_ink(30,light,thresholds)==band_ink(30,26,30,'yellow',light)
            samples=[air_quality_style(n,light) for n in (101,125,150)]
            assert {index for index,_ in samples}=={2} and len({ink for _,ink in samples})==3
            assert air_quality_style(151,light)[0]==3
        from resource_settings import ResourceOptions
        options=ResourceOptions(service);options.tabs.setCurrentIndex(5)
        options.weather_threshold_fields[1].setValue(29)
        assert not options.commit() and cfg['resource_weather_thresholds']==thresholds
        options.weather_threshold_fields[1].setValue(18)
        assert options.commit() and cfg['resource_weather_thresholds']==[0,18,26,30]
        assert compact_temperature_ink(16,True,cfg['resource_weather_thresholds'])==band_ink(16,18,0,'cyan',True)
        options.deleteLater()
        from resource_weather_style import paint_weather
        montage=QImage(7*165,2*95,QImage.Format_ARGB32_Premultiplied);montage.fill(Qt.transparent);p=QPainter(montage);p.setRenderHint(QPainter.Antialiasing)
        for row,light in enumerate((True,False)):
            for col,code in enumerate(codes):
                r=QRectF(col*165,row*95,159,89);paint_weather(p,r,dict(code=code),light,'#ddeeff')
                p.setPen(QColor('#162f40' if light else '#edf5fa'));p.drawText(r.adjusted(10,5,-8,-6),Qt.AlignLeft|Qt.AlignTop,kinds[col]+'\n9°\n1° / 12°')
        p.end();montage.save(str(output/'companion-weather-scenes.png'))
        cfg.update(resource_expanded_width=560,resource_expanded_height=300);w.sync_window();w.select_page('weather');app.processEvents()
        for _ in range(6):app.processEvents();time.sleep(.01)
        import json
        objects={'detail':w.detail,'page':w.view('weather'),'body':w.view('weather').widget(),'content':w.weather_view,'head':w.weather_view.weather_head,'cards':w.weather_view.cards}
        (output/'weather-layout.json').write_text(json.dumps({k:dict(rect=v.geometry().getRect(),visible=v.isVisible(),minimum=[v.minimumWidth(),v.minimumHeight()]) for k,v in objects.items()},indent=2),encoding='utf-8')
        assert all(len(row['days'])==8 for row in w.weather_view.cards.rows) and w.weather_view.cards.isVisible()
        assert w.weather_view.cards.card_height==112
        w.grab().save(str(output/'companion-weather-cards.png'))
        from resource_extras_view import weather_days
        today=date.fromisoformat(extra.weather[0]['days'][1]['date'])
        assert [label for label,day in weather_days(extra.weather[0],3,today)]==['昨天','今天','明天']
        assert weather_days(extra.weather[0],3,today)[0][1]['low']==2
        assert len(weather_days(extra.weather[0],7,today))==7 and weather_days(extra.weather[0],7,today)[0][0]=='今天'
        assert weather_days(dict(days=[]),3,today)[0][1]['low'] is None
        cfg['resource_weather_days']=7;w.refresh()
        for _ in range(6):app.processEvents();time.sleep(.01)
        assert w.weather_view.cards.card_height==112
        w.grab().save(str(output/'companion-weather-week.png'))
        options=ResourceOptions(service)
        assert options.loaded=={0}
        untouched={key:copy.deepcopy(cfg[key]) for key in ('resource_ai_providers','resource_compact_pinned','resource_weather_cities','resource_appearance')}
        options.fields['resource_task_font'].setValue(2)
        assert options.loaded=={0,1} and options.commit()
        assert cfg['resource_task_font']==2 and all(cfg[k]==v for k,v in untouched.items())
        options.fields['resource_face_scale'].setValue(110);options.fields['resource_face_interactive'].setChecked(True)
        interval = options.fields['resource_face_switch_minutes']
        assert interval.value() == 10 and not interval.isEnabled()
        options.fields['resource_face_auto_switch'].setChecked(True)
        assert interval.isEnabled()
        interval.setValue(4)
        options.show_page(6)
        news_feeds,disabled_feeds=check_news_presets(options)
        options.tabs.setCurrentIndex(6)
        interval = options.fields['resource_face_switch_minutes']
        assert interval.isEnabled() and interval.value() == 4
        options.grab().save(str(output/'resource-face-options.png'))
        options.fields['resource_weather_days'].setCurrentIndex(options.fields['resource_weather_days'].findData(3))
        options.fields['resource_task_threshold'].setChecked(True);options.fields['resource_task_music_colorful'].setChecked(True)
        assert options.commit();saved=api.load_config()
        assert saved['resource_news_feeds']==news_feeds and saved['resource_news_disabled_feeds']==disabled_feeds
        checks.append('RSS presets and switches: defaults, existing and cleared profiles, individual and bulk additions, deduplication, limit feedback, saved enabled states, and refresh only for enabled feeds.')
        assert saved['resource_face_scale']==110 and saved['resource_task_threshold'] and saved['resource_task_music_colorful'] and saved['resource_weather_days']==3
        assert saved['resource_face_auto_switch'] and saved['resource_face_switch_minutes'] == 4
        assert w.liquid.rotation.isActive() and w.liquid.rotation.interval() == 240_000
        assert w.liquid.watch.isActive()
        assert all(options.fields[key].isChecked() for key in
                   ('resource_compact_ai','resource_compact_music','resource_weather_compact'))
        assert 'notifications' not in options.compact_fields
        options.reject();options.deleteLater()
        cfg['resource_face']=False;w.sync_window()
        assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive()
        assert not w.liquid.rotation.isActive()
        face_calls.clear()
        with patch.object(w.liquid, 'paint_face', new=count_face):
            w.grab()
        assert not face_calls
        checks.append('Capsule face rotation settings survive page changes and persistence, run alongside cursor tracking, and stop when faces are disabled.')
        checks.append('Resident compact regressions: 96×28–560×44 bounds, stable CPU/core pins at 292px, all supplementary values/AI/media reachable, AI/music/cities independently pinned; face static/interactive/size, hover with auto-collapse off and click-only; all five pages stay 260×180 with scrollable tabs. Seven vector weather backgrounds in both themes; options persist.')
    finally:cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
