"""Regressions for narrow resident content, face controls and weather."""
import copy,time
from unittest.mock import patch
from PyQt5.QtCore import Qt,QEvent,QPointF,QRectF,QPoint
from PyQt5.QtGui import QPainter,QImage,QColor,QCursor,QMouseEvent,QFontMetrics


def run(api,runtime,app,output,checks):
    from resource_options import DEFAULTS
    from resource_redesign_tests import fixtures
    from resource_compact import plan
    from resource_settings import ResourceOptions
    from resource_weather_style import weather_kind,compact_temperature_ink
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
        import resource_compact
        import resource_provider_icons as marks
        assert all(marks.provider_art(name, '#223744') for name in set(marks.PROVIDER_MARKS.values()))
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
        tones=[compact_temperature_ink(n,True,thresholds) for n in (-1,0,16,27,31)]
        assert len(set(tones))==5
        assert compact_temperature_ink(26,True,thresholds)==tones[2]
        assert compact_temperature_ink(30,True,thresholds)==tones[3]
        from resource_settings import ResourceOptions
        options=ResourceOptions(service);options.tabs.setCurrentIndex(5)
        options.weather_threshold_fields[1].setValue(29)
        assert not options.commit() and cfg['resource_weather_thresholds']==thresholds
        options.weather_threshold_fields[1].setValue(18)
        assert options.commit() and cfg['resource_weather_thresholds']==[0,18,26,30]
        assert compact_temperature_ink(16,True,cfg['resource_weather_thresholds'])==tones[1]
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
        options.fields['resource_weather_days'].setCurrentIndex(options.fields['resource_weather_days'].findData(3))
        options.fields['resource_task_threshold'].setChecked(True);options.fields['resource_task_music_colorful'].setChecked(True)
        assert options.commit();saved=api.load_config()
        assert saved['resource_face_scale']==110 and saved['resource_task_threshold'] and saved['resource_task_music_colorful'] and saved['resource_weather_days']==3
        assert all(options.fields[key].isChecked() for key in
                   ('resource_compact_ai','resource_compact_music','resource_weather_compact'))
        assert 'notifications' not in options.compact_fields
        options.reject();options.deleteLater()
        cfg['resource_face']=False;w.sync_window()
        assert not w.liquid.watch.isActive() and not w.liquid.frames.isActive()
        face_calls.clear()
        with patch.object(w.liquid, 'paint_face', new=count_face):
            w.grab()
        assert not face_calls
        checks.append('Resident compact regressions: 96×28–560×44 bounds, stable CPU/core pins at 292px, all supplementary values/AI/media reachable, AI/music/cities independently pinned; face static/interactive/size, hover with auto-collapse off and click-only; all five pages stay 260×180 with scrollable tabs. Seven vector weather backgrounds in both themes; options persist.')
    finally:cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
