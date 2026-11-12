"""Calendar rollover, persistence, compact content, fonts, halo and opt-in lifecycle."""
import copy,json,time
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


def ledger_checks(checks):
    from PyQt5.QtGui import QColor
    from resource_traffic import TrafficLedger
    from resource_status import band_ink,threshold
    with TemporaryDirectory() as root:
        path=Path(root)/'traffic.json';ledger=TrafficLedger(path)
        first=datetime(2025,12,31,23,59,59)
        ledger.observe({1:(100,50)},first)
        ledger.observe({1:(300,150),2:(900000,800000)},first+timedelta(seconds=2))
        assert ledger.days=={'2025-12-31':[100,50],'2026-01-01':[100,50]}
        assert ledger.snapshot(first+timedelta(seconds=2))['year']==(100,50)
        ledger.observe({1:(20,10)},first+timedelta(seconds=3));assert ledger.snapshot()['days']['2026-01-01']==[100,50]
        ledger.observe({1:(40,15)},first+timedelta(seconds=4));ledger.flush()
        restored=TrafficLedger(path);assert restored.days==ledger.days
        restored.observe({1:(999999,999999)},first+timedelta(seconds=5));assert restored.days==ledger.days
        restored.pause();restored.observe({1:(1999999,1999999)},first+timedelta(seconds=6));assert restored.days==ledger.days
        restored.observe({1:(2999999,2999999)},first+timedelta(hours=2));assert restored.days==ledger.days
        path.write_text('damaged',encoding='utf-8');damaged=TrafficLedger(path);damaged.add('2026-01-01',[1,1]);damaged.flush()
        assert path.read_text()=='damaged' and damaged.error
    for light in (True,False):
        for readings in ((0,30,59),(60,70,79),(80,90,100)):
            soft,middle,strong=(QColor(threshold(n,100,light)).lightness() for n in readings)
            assert soft>middle>strong
        assert threshold(60,100,light)==band_ink(.6,.6,.8,'yellow',light)
        assert threshold(80,100,light)==band_ink(.8,.8,1,'red',light)
        assert threshold(160,200,light)==threshold(80,100,light)!=threshold(79.999,100,light)
        assert threshold(120,100,light)==threshold(100,100,light)
    assert threshold(None) is None and threshold(float('nan')) is None
    assert threshold(80,0) is None
    checks.append('Traffic: per-adapter deltas, new adapter/reset baselines, midnight/month/year split, restart persistence, disabled/suspend gaps and corrupt-file preservation. Resource thresholds retain 60/80 boundaries and deepen inside each band in both themes.')


def content_column_checks(window,app,output,checks):
    from PyQt5.QtWidgets import QBoxLayout

    for key in ('resources','ai','traffic','weather','pomodoro','agenda','music','news'):
        window.select_page(key)
        for width,columns in ((360,1),(361,2),(360,1)):
            window.resize(width,window.height())
            for _ in range(3):app.processEvents()
            assert window.width()==width,(key,width,window.width())
            if key=='resources':
                scroll=window.scroll
                assert window.graph.load_columns==window.system_readout.columns==columns
                first,second=window.graph.geometry(),window.rank_section.geometry()
                assert (first.top()==second.top())==(columns==2),(width,first,second)
            elif key=='ai':
                stats=window.stats_view;scroll=stats.scroll
                assert stats.summary.columns==stats.charts.columns==columns
                multi=[card[2] for card in stats.quotas.cards if len(card[0].get('quotas',[]))>1]
                assert multi and all(count==columns for count in multi),(width,multi)
            else:
                scroll=window.view(key)
                if key=='traffic':assert scroll.content.summary.columns==columns
                if key=='weather':
                    weather=scroll.content
                    assert weather.cards.columns==columns
                    assert weather.weather_head.y()==0 and weather.cards.y()==weather.weather_head.height()+4
                    assert weather.remarks_button.y()>=weather.cards.geometry().bottom()+1
                    assert weather.cards.geometry().bottom()<weather.height()
                if key in ('pomodoro','agenda'):
                    layout=scroll.content.cards if key=='pomodoro' else scroll.content.layout_
                    direction=QBoxLayout.LeftToRight if columns==2 else QBoxLayout.TopToBottom
                    assert layout.direction()==direction,(key,width,layout.direction())
                    first,second=(layout.itemAt(index).widget().geometry() for index in (0,1))
                    assert (first.top()==second.top())==(columns==2),(key,width,first,second)
                    assert second.right()<scroll.content.width(),(key,width,second,scroll.content.width())
            assert scroll.widget().width()==scroll.viewport().width(),(key,width,scroll.widget().width(),scroll.viewport().width())
            assert window.grab().save(str(output/f'capsule-columns-{key}-{width}.png'))
    checks.append('Expanded capsule: live 360 → 361 → 360 logical px resize across resource, AI, traffic, weather, focus, agenda, music and news pages. Cards and quota metrics switch at 361; each scroll viewport retains its full width.')


def run(api,runtime,root,app,output,checks):
    from PyQt5.QtCore import Qt,QRect,QRectF,QTimer
    from PyQt5.QtGui import QColor,QPixmap
    from resource_options import DEFAULTS,METRICS,SENSOR_UNITS,COMPACT_METRICS
    from resource_settings import ResourceOptions
    from resource_panel import display_values
    from resource_taskbar import Placement,free_slot
    from unittest.mock import patch
    ledger_checks(checks)
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources;dialog=None
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_auto_hide=False,resource_collapsed=False,
            resource_ai=True,resource_music=True,resource_weather=True,resource_news=True,resource_background='custom',
            resource_appearance=dict(material='solid',theme='dark',color='#436d86',opacity=95,blur=8,highlight=45))
        for key in SENSOR_UNITS:cfg['resource_'+key]=True
        service.sync();w=service.window;assert service.deck and service.deck.process.state()==0
        sensors={key:dict(value=84 if key.endswith('temp') else 72 if key=='gpu_memory' else 1300 if key.endswith(('fan','pump')) else 3100 if key.endswith('frequency') else 1.2 if key.endswith('voltage') else 32,
                         label=METRICS[key],source='隔离测试数据') for key in SENSOR_UNITS}
        service.sensors.values=sensors
        data=dict(time=time.monotonic(),cpu=62.,gpu=84.,memory=(42.,6.72*2**30,16*2**30),network=(2**20,220*1024),cpu_cores=[20,40,61,80]*4,
            traffic=dict(day=(3*2**30,800*2**20),month=(30*2**30,8*2**30),year=(300*2**30,80*2**30),days={'2026-11-07':[3*2**30,800*2**20]},error=''))
        service.accept_sample(data)
        assert set(SENSOR_UNITS)<=set(row[0] for row in display_values(service))
        bridge=service.deck
        providers=[dict(id=name,name=name,plan='测试套餐',status='已连接',source='fixture',note='隔离测试数据',usageNote='fixture',usageAvailable=True,
                        quotas=[dict(label='5小时 · 已用',percent=value,value=f'{value}%',reset='2026-11-08T12:00:00+08:00'),
                                dict(label='每周 · 已用',percent=max(0,value-18),value=f'{max(0,value-18)}%',reset='2026-11-12T12:00:00+08:00')],
                        today=dict(tokens=12345,cost=None,unpriced=1),week=dict(tokens=654321,cost=1.23,unpriced=0),
                        days=[dict(date='2026-11-07',model='fixture-model',summary=dict(tokens=12345,cost=None,unpriced=1))])
                   for name,value in [('Claude',34),('Codex',72),('Cursor',87),('Antigravity',51)]]
        bridge.accept(dict(type='ai',at='2026-11-07T12:30:00+08:00',providers=providers))
        assert bridge.alert == 'Cursor  额度剩余 13%'
        bridge.alert_until=0
        bridge.accept(dict(type='media',tracks=[dict(id='fixture',source='测试播放器',title='午后的海风')],pinned=False,
                          track=dict(id='fixture',title='午后的海风',artist='测试音乐家',state='Playing',duration=200,position=72,
                                     canToggle=True,canPrevious=True,canNext=True,canSeek=True,canShuffle=True,canRepeat=True,
                                     lyric='海风从窗边轻轻吹过',lyricSource='测试歌词',repeat='None',shuffle=False)))
        bridge.cover=QPixmap(60,60);bridge.cover.fill(QColor('#5287a1'));bridge.levels=[.1,.4,.9,.5,.2,.7,.6,.3]
        w.select_page('resources');service.display();app.processEvents();w.grab().save(str(output/'upgrade-resources.png'))
        assert w._traffic_view is None and w.animation.isActive()
        expanded = cfg['resource_expanded_width'], cfg['resource_expanded_height']
        for width in (260, 360, 361, 500, 720):
            cfg.update(resource_expanded_width=width, resource_expanded_height=321)
            w.sync_window();app.processEvents()
            readings = w.sensor_columns
            assert set(SENSOR_UNITS) <= {key for key, *_ in readings.cells}
            assert (readings.cells[0][3].top() == readings.cells[1][3].top()) == (width>360), (width, readings.width(), readings.cells[:2])
            for _, label, value, label_area, value_area in readings.cells:
                assert label and '…' not in value and not label_area.intersects(value_area), (width,label,value,label_area,value_area)
                assert QRectF(readings.rect()).contains(label_area.united(value_area))
            w.scroll.verticalScrollBar().setValue(w.scroll.verticalScrollBar().maximum())
            app.processEvents();w.grab().save(str(output/f'resource-sensor-grid-{width}.png'))
        cfg['resource_expanded_width'], cfg['resource_expanded_height'] = expanded
        w.sync_window();app.processEvents();w.scroll.verticalScrollBar().setValue(0)
        checks.append('Sensor layout: all values and units stay visible at 260, 360, 361, 500 and 720 logical px. Readings share rows above 360 px.')
        content_column_checks(w,app,output,checks)
        w.select_page('resources');w.sync_window();app.processEvents()
        geometry=w.geometry();w.select_page('traffic');app.processEvents()
        assert w.traffic.isVisible() and w.geometry()==geometry
        w.grab().save(str(output/'upgrade-traffic.png'))
        w.select_page('ai');app.processEvents();w.grab().save(str(output/'upgrade-ai.png'))
        assert len(w.ai_view.summary.rows)==4 and w.ai_view.models.rowCount()==4
        w.ai_view.provider.setCurrentIndex(1);assert w.ai_view.models.rowCount()==1
        w.ai_view.provider.setCurrentIndex(0)
        for attempt in range(2):
            QTimer.singleShot(50,w.ai_view.detail_dialog.reject);w.ai_view.show_details('Codex')
            assert w.ai_view.models.rowCount()==1
        w.select_page('music');app.processEvents();w.grab().save(str(output/'upgrade-music.png'))
        assert w.music_view.slider.isEnabled() and w.music_view.title.text()=='午后的海风'
        with patch.object(bridge,'send') as send:
            w.music_view.buttons['PlayPause'].click();send.assert_called_once_with(op='PlayPause',id='fixture')
            w.music_view.slider.setValue(500);w.music_view.seek();send.assert_called_with(op='seek',fraction=.5)
        recorded = bridge.media
        live = dict(recorded['track'], title='直播音频示例', artist='', lyric='', state='Paused', duration=0, position=0,
                    canSeek=False, canPrevious=False, canNext=False, canShuffle=False, canRepeat=False, liveAudio=True)
        bridge.accept(dict(recorded,track=live));app.processEvents()
        assert w.music_view.buttons['PlayPause'].toolTip() == '恢复直播声音'
        assert w.music_view.status.text() == '直播声音已暂停'
        assert w.grab().save(str(output/'live-audio-paused.png'))
        bridge.accept(recorded)
        service.fold(True);app.processEvents();assert 'gpu' in service.active_keys()
        assert not w.detail.isVisible() and w.clock_tick.isActive() and w.rotate.isActive()
        w.animation.stop();w.halo_phase=.1;first=w.grab().toImage();w.halo_phase=.5;second=w.grab().toImage();assert first!=second
        assert cfg['resource_halo_speed']=='medium'
        for speed, seconds in [('slow',12),('medium',8),('fast',4)]:
            cfg['resource_halo_speed']=speed;w.halo_phase=.1;w.halo_updated_at=100
            with patch('resource_panel.time.monotonic',return_value=101):w.animate()
            assert abs(w.halo_phase-(.1+1/seconds))<1e-9
        cfg['resource_halo_speed']='medium'
        second.save(str(output/'upgrade-compact.png'));assert {'cpu','gpu','memory','network'}<=set(w.compact_shown)
        cfg['resource_halo']=False;w.sync_window();app.processEvents();assert not w.animation.isActive()
        assert w.grab().toImage()!=second and w.clock_tick.isActive() and service.deck
        w.grab().save(str(output/'upgrade-compact-halo-off.png'))
        cfg['resource_halo']=True;w.sync_window();app.processEvents();assert w.animation.isActive()
        w.animation.stop();start=time.perf_counter()
        for frame in range(60):w.halo_phase=frame/60;w.grab()
        (output/'halo-render.json').write_text(json.dumps({'frames':60,'average_ms':round((time.perf_counter()-start)*1000/60,2),'dpr':w.devicePixelRatioF()}),encoding='utf-8')
        cfg['resource_music_text']='lyrics';w.grab().save(str(output/'upgrade-compact-lyrics.png'))
        seen=set()
        for page in range(w.compact_pages):w.offset=page;w.grab();seen.update(w.compact_shown)
        assert {'cpu','gpu','memory','network','traffic'}<=seen
        for width in (220,380,800):
            cfg['resource_compact_width']=width;w.sync_window();app.processEvents();w.grab().save(str(output/f'upgrade-compact-{width}.png'))
        cfg.update(resource_compact_width=560,resource_compact_height=38);w.offset=0;w.sync_window();app.processEvents();w.grab().save(str(output/'upgrade-compact-short.png'))
        cfg['resource_compact_height']=54;cfg['resource_appearance']['theme']='light';w.sync_window();app.processEvents();w.grab().save(str(output/'upgrade-compact-light.png'))
        service.fold(False);w.select_page('ai');app.processEvents();w.grab().save(str(output/'upgrade-ai-light.png'))
        w.select_page('music');app.processEvents();w.grab().save(str(output/'upgrade-music-light.png'))
        cfg['resource_appearance']['theme']='dark';w.sync_window()
        dialog=ResourceOptions(service);dialog.show();app.processEvents()
        dialog.fields['resource_task_font'].setValue(18);assert dialog.commit() and api.load_config()['resource_task_font']==18
        dialog.tabs.setCurrentIndex(2);app.processEvents();dialog.grab().save(str(output/'upgrade-settings-compact.png'))
        dialog.tabs.setCurrentIndex(3);app.processEvents();dialog.grab().save(str(output/'upgrade-settings-media.png'));dialog.reject()
        dialog.tabs.setCurrentIndex(4);dialog.show();app.processEvents()
        speed=dialog.fields['resource_halo_speed'];assert speed.currentData()=='medium'
        dialog.grab().save(str(output/'upgrade-settings-halo.png'))
        speed.setCurrentIndex(speed.findData('fast'));dialog.tabs.setCurrentIndex(2)
        assert dialog.commit() and api.load_config()['resource_halo_speed']=='fast';dialog.reject()
        cfg.update(resource_task_metrics=['cpu','gpu','memory','network','traffic'],resource_taskbar=True)
        bar=dict(rect=QRect(0,740,1366,40),screen='test',hwnd=1,map=(0,0,0,0,1,1))
        with patch.object(Placement,'bars',return_value=[bar]),patch.object(Placement,'query',lambda p,b,r:p.accept(b,r,free_slot(b['rect'],[],r))):service.sync()
        service.accept_sample(data);strip=service.strip
        for size in (8,11,18,24):
            cfg['resource_task_font']=size;strip.refresh();app.processEvents();strip.grab().save(str(output/f'upgrade-taskbar-{size}.png'))
            assert strip.effective_font<=size and strip.page_count>=1
        assert '年' in strip.toolTip()
        cfg.update(resource_enabled=False,resource_taskbar=False);service.sync();app.processEvents()
        assert not service.deck and not service.signature and not service.window and not service.strip
        assert not w.animation.isActive() and not w.clock_tick.isActive() and not w.rotate.isActive()
        checks.append('Native resource UI: all sensor fields, AI columns/model details reopened and date filtering, music controls and seeking, compact CPU/GPU/memory/network simultaneously, ring/media/clock composition, 220–800 widths, dark/light themes, moving rainbow halo and off switch (timer stops; data continues), paging, font 8/11/18/24 persistence and narrow taskbar fallback, and complete feature shutdown.')
        from deck_bridge_qt_tests import run as pipe_check
        from resource_redesign_tests import run as redesign
        redesign(api,runtime,app,output,checks)
        from taskbar_media_tests import run as taskbar_media
        taskbar_media(api,runtime,app,output,checks)
        from resource_resize_tests import run as resize_ui
        resize_ui(api,runtime,app,output,checks)
        from resource_liquid_tests import run as liquid_ui
        liquid_ui(api,runtime,app,output,checks)
        from resource_companion_tests import run as companion_ui
        companion_ui(api,runtime,app,output,checks)
        from resource_performance_tests import run as performance_ui
        performance_ui(api,runtime,app,output,checks)
        from resource_render_cache_tests import run as rendering_ui
        rendering_ui(api,runtime,app,output,checks)
        from panel_face_tests import run as panel_faces
        panel_faces(api,runtime,app,output,checks)
        pipe_check(app,output,checks)
    finally:
        if dialog:dialog.deleteLater()
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
