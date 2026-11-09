"""Regression cases from reported screenshots; only run on a private desktop."""
import copy,json,time
from datetime import date,timedelta
from unittest.mock import patch


def fixtures():
    today=date.today();providers=[]
    for name,factor in [('Codex',1),('Claude',2)]:
        days=[]
        for i in range(45):
            summary=dict(tokens=5000*(i+1)*factor,input=1000*(i+1)*factor,output=900*(i+1)*factor,
                         cacheRead=3000*(i+1)*factor,cacheWrite=100*(i+1)*factor,records=2,cost=.25*(i+1)*factor,estimated=True,unpriced=0)
            days.append(dict(date=(today-timedelta(days=i)).isoformat(),model='测试模型',summary=summary))
        used = 39 if factor == 1 else 0
        providers.append(dict(id=name,name=name,plan='测试套餐',status='已连接',usageAvailable=True,usageComplete=True,allHistory=True,
            quotas=[dict(label='每周 · 已用',percent=used,value=f'{used}%')],
            today=days[0]['summary'],week=days[0]['summary'],days=days,
            hours=[dict(date=days[i]['date']+'T12',summary=days[i]['summary']) for i in (0,1)]))
    return providers


def aggregation(checks):
    from resource_pages import cost_note,cost_text
    from resource_usage import aggregate,combine
    rows=fixtures()
    result=aggregate(rows)
    assert result['total']['tokens']==15000 and result['total']['records']==4 and result['total']['cost']==.75
    assert abs(result['total']['cacheRate']-3000/4100*100)<1e-8
    assert len(result['series'])==24 and sum(s['tokens'] for _,s in result['series'])==15000
    assert aggregate(rows,'yesterday')['total']['tokens']==30000
    assert aggregate(rows,'week')['total']['tokens']==5000*28*3
    assert aggregate(rows,'month')['total']['cost']==.75*465
    result=aggregate(rows,'all','Codex');assert result['total']['tokens']==5000*1035 and len(result['series'])<=45
    unknown=combine([dict(tokens=10,cost=None,unpriced=1),dict(tokens=20,cost=.5,unpriced=0)])
    assert unknown['tokens']==30 and unknown['cost']==.5 and unknown['unpriced']==1 and unknown['records'] is None and unknown['cacheRate'] is None
    estimate=dict(cost=10.37,estimated=True,unpriced=2)
    assert cost_text(estimate)=='$10.37' and cost_text(estimate,currency=False)=='10.37'
    assert cost_note(estimate)=='含估算 · 2 条未定价' and cost_note(unknown)=='1 条未定价'
    assert cost_text(dict(cost=None,unpriced=2))=='未定价' and cost_text(dict(cost=0))=='$0.00'
    assert cost_text(dict(cost=.000037))=='$0.000037'
    assert cost_text(dict(cost=.000000037))=='<$0.000001'
    old=dict(rows[0]);old.pop('hours');assert len(aggregate([old])['series'])==1
    many=copy.deepcopy(rows[0]);many['days']=[dict(date=(date.today()-timedelta(days=i)).isoformat(),model='历史测试',summary=rows[0]['days'][0]['summary']) for i in range(500)]
    result=aggregate([many],'all');assert len(result['series'])<=45 and sum(s['tokens'] for _,s in result['series'])==2500000
    checks.append('AI statistics: day/yesterday/7-day/30-day/all/provider filters, hourly totals, weighted cache hit rate, unknown pricing and record counts, historical binning without losing totals. No HTTP request count invented.')


def run(api,runtime,app,output,checks):
    from PyQt5.QtCore import QRectF,QTimer
    from PyQt5.QtGui import QFontMetrics
    from resource_options import DEFAULTS,SENSOR_UNITS
    from resource_compact import plan
    from resource_ai_tray import quota_icon
    from resource_quota import amount_label, amount_text, quota_color, quota_text, used_percent
    from resource_settings import ResourceOptions
    import resource_compact
    import resource_statistics
    aggregation(checks)
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_collapsed=False,resource_auto_hide=False,resource_ai=True,resource_music=True,
            resource_cpu_power=True,resource_gpu_power=True,resource_rank=False,resource_background='custom',resource_appearance=dict(material='solid',theme='light',color='#c3d7df',opacity=96,blur=8,highlight=45))
        service.sync();w=service.window;bridge=service.deck
        service.accept_sample(dict(time=time.monotonic(),cpu=100.,gpu=8.,memory=(72.,11*2**30,15.4*2**30),network=(915,1024),traffic=dict(day=(17*2**20,30*2**20),month=(17*2**20,30*2**20),year=(17*2**20,30*2**20))))
        sensors={key:dict(value=value,label=label,source='隔离测试数据') for key,label,value in [('cpu_power','CPU 功耗',29.99),('gpu_power','GPU 功耗',1.56)]}
        service.sensors.values=sensors
        bridge.accept(dict(type='ai',at='2026-11-07T12:00:00+08:00',providers=fixtures()));bridge.alert_until=0
        assert 'Codex · 每周 剩余 61%' in w.accessibleName()
        painted = []
        draw_text = resource_compact.text

        def record_text(painter, rect, value, color, *args, **kwargs):
            painted.append((value, color))
            draw_text(painter, rect, value, color, *args, **kwargs)

        title='BrimDeck | 新版本增加系统资源监控、多个内置主题，支持自定义_哔哩哔哩_bilibili_Long Title Regression'
        media=dict(type='media',tracks=[dict(id='test',source='Google Chrome',title=title)],track=dict(id='test',title=title,artist='',state='Playing',duration=67,position=50,lyric='',canToggle=True,canSeek=True))
        bridge.accept(media);bridge.levels=[.1,.4,.8,.4,.2,.7,.6,.3]
        assert w._ai_view is None and w._music_view is None,'Hidden pages were constructed eagerly'
        geometry=w.geometry();sizes={}
        for page in ('resources','ai','music','resources','music'):
            w.select_page(page);app.processEvents();assert w.geometry()==geometry,(page,w.geometry(),geometry)
            assert not w.toolTip();sizes[page]=[w.width(),w.height()]
            assert bridge.signature[5]==(page=='music'),'Audio capture continued without visible bars'
            w.grab().save(str(output/f'redesign-{page}.png'))
        w.select_page('ai')
        with patch.object(resource_statistics, 'text', record_text):
            w.ai_view.summary.grab()
        assert ('61%', quota_color(61, True)) in painted
        assert ('100%', quota_color(100, True)) in painted
        assert w.music_view.title.text()==title and w.music_view.title.height()<42
        font=w.music_view.title.font();font.setPixelSize(w.music_view.title.pixel_size)
        assert w.music_view.title.height()/2>=QFontMetrics(font).height()
        w.select_page('stats');stats=w.stats_view
        for period in ('today','yesterday','week','month','all'):
            stats.set_period(period);app.processEvents();assert stats.data['available']
        assert bridge.history_requested
        stats.provider.setCurrentIndex(stats.provider.findData('Codex'));assert stats.data['total']['tokens']==5175000
        for metric in ('tokens','records','cost'):stats.set_metric(metric);app.processEvents()
        painted.clear()
        with patch.object(resource_statistics,'text',record_text):
            stats.summary.grab();stats.charts.grab();stats.providers.grab()
        amounts={value for value,_ in painted}
        assert {'258.75','$258.75','USD','费用趋势 · USD','含估算'}<=amounts and not any('≈$' in value for value in amounts)
        stats.grab().save(str(output/'redesign-statistics-all.png'))
        QTimer.singleShot(25,w.ai_view.detail_dialog.reject);stats.show_details('Codex')
        assert w.ai_view.models.rowCount()==1 and w.ai_view.models.item(0,1).text()=='5,175,000'
        assert w.ai_view.models.item(0,2).text()=='258.75' and w.ai_view.models.item(0,3).text()=='含估算'
        with patch('resource_statistics.aggregate',wraps=__import__('resource_statistics').aggregate) as calculation:
            stats.refresh();stats.refresh();assert calculation.call_count==0,'Media ticks recalculated unchanged usage history'
        stats.provider.setCurrentIndex(0);stats.set_period('month');w.grab().save(str(output/'redesign-statistics-month.png'))
        cfg['resource_appearance']['theme']='dark';w.sync_window();app.processEvents();w.grab().save(str(output/'redesign-statistics-dark.png'))
        service.fold(True);app.processEvents();w.animation.stop();assert bridge.signature[5] is True
        cfg['resource_music_text']='title';bridge.configure();assert bridge.signature[5] is False
        cfg['resource_music_text']='wave';bridge.configure();assert bridge.signature[5] is True
        defaults=list(cfg['resource_compact_pinned'])
        painted.clear()
        quota_captured = False
        for width in (220,380,440,560,800):
            cfg['resource_compact_width']=width;cfg['resource_compact_pinned']=defaults;w.sync_window();app.processEvents();seen=set();sources=set();music=False
            for page in range(len(plan(w,w.width())['pages'])):
                w.offset=page
                with patch.object(resource_compact, 'text', record_text):w.grab()
                seen.update(w.compact_shown);sources.update(w.compact_providers);music=music or w.compact_media
                if width==560 and 'Codex' in w.compact_providers and not quota_captured:
                    assert w.grab().save(str(output/'resource-compact-quota.png'))
                    quota_captured = True
                bounds=w.compact_bounds
                for rect in bounds:assert QRectF(w.rect()).contains(rect)
                for i,rect in enumerate(bounds):assert all(not rect.intersects(other) for other in bounds[i+1:])
                assert len(bounds)==len(w.compact_shown),'A reading was reported as visible but was not painted'
                if not plan(w,w.width())['overflow']:assert set(defaults)<=set(w.compact_shown)
            assert {'cpu','memory','gpu','network','cpu_power','gpu_power','traffic'}<=seen and sources=={'Codex','Claude'} and music
            w.offset=0;w.grab().save(str(output/f'redesign-compact-{width}.png'))
        assert ('61%', quota_color(61, False)) in painted
        assert ('100%', quota_color(100, False)) in painted
        cfg.update(resource_compact_width=560,resource_compact_pinned=['cpu_power','gpu_power']);w.sync_window();app.processEvents()
        for page in range(len(plan(w,w.width())['pages'])):
            w.offset=page;w.grab();assert {'cpu_power','gpu_power'}<=set(w.compact_shown)
        cfg['resource_compact_pinned']=defaults
        dialog=ResourceOptions(service)
        dialog.tabs.setCurrentIndex(2)
        for key,field in dialog.compact_fields.items():
            field.setChecked(key in ('cpu_power','gpu_power'))
        dialog.fields['resource_compact_ai'].setChecked(False)
        dialog.tabs.setCurrentIndex(0)
        dialog.tabs.setCurrentIndex(2)
        assert not dialog.fields['resource_compact_ai'].isChecked()
        assert dialog.commit()
        saved=api.load_config()
        assert saved['resource_compact_metrics']==['cpu_power','gpu_power']
        assert saved['resource_compact_pinned']==defaults and saved['resource_ai'] and not saved['resource_compact_ai']
        dialog.reject();dialog.deleteLater()
        cfg.update(resource_cpu=False,resource_gpu=False,resource_memory=False,resource_network=False,resource_traffic=False)
        w.refresh();w.reposition();app.processEvents();assert w.width()<400
        w.offset=0;w.grab().save(str(output/'redesign-power-only.png'))
        cfg.update(resource_enabled=False,resource_ai=False,resource_ai_tray=True,resource_taskbar=False,resource_music=True);service.sync();app.processEvents()
        assert service.ai_tray and service.deck and not service.window and not service.strip
        assert not service.signature and not service.job and not service.sensors and not service.fps
        assert service.deck.signature[0] is True and service.deck.signature[2] is False
        tray=service.ai_tray;tray.open('stats');app.processEvents();popup=tray.popup;popup.stats_view.set_period('month');popup.grab().save(str(output/'redesign-ai-tray-statistics.png'));geometry=popup.geometry()
        tray.open('ai');app.processEvents();assert popup.geometry()==geometry
        popup.grab().save(str(output/'redesign-ai-tray-quota.png'))
        icons=[quota_icon(used).pixmap(32,32).toImage() for used in (None,0,60,80,100)]
        assert all(a!=b for i,a in enumerate(icons) for b in icons[i+1:])
        for i,pix in enumerate(icons):pix.save(str(output/f'redesign-tray-icon-{i}.png'))
        balance = dict(kind='balance', label='账户余额', value='¥12.48', percent=87.52)
        assert amount_text(balance) == quota_text(balance) == '¥12.48' and used_percent(balance) is None
        assert amount_text(dict(value='¥12.48', percent=87.52)) == '¥12.48'
        spend=dict(kind='spend',label='累计消费',value='≥¥3.18')
        assert amount_text(spend)=='¥3.18' and amount_label(spend)=='累计消费（已知金额）'
        assert quota_color(100) == quota_color(70) != quota_color(69)
        assert quota_color(69) == quota_color(40) != quota_color(39)
        assert quota_color(39) == quota_color(11) != quota_color(10)
        assert quota_color(10) == quota_color(0)
        assert {s.width() for s in quota_icon(30).availableSizes()} >= {16, 20, 24, 32}
        cfg['resource_ai_tray']=False;service.sync();app.processEvents();assert not service.deck and not service.ai_tray and not service.signature
        (output/'resource-page-sizes.json').write_text(json.dumps(sizes),encoding='utf-8')
        checks.append('Reported UI regressions: identical page geometry, long mixed-language title in bounded lines, no aggregate hover popup, all compact values/AI/media reachable at 220–800 widths without overlapping or dropped cells, persisted custom pinned metrics, automatic width shrink, independent AI tray with hardware/music stopped, quota icons and complete shutdown.')
    finally:
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
