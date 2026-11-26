"""Regression cases from reported screenshots; only run on a private desktop."""
import copy,json,time
from datetime import date,datetime,timedelta
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
    from resource_pages import cost_note,cost_text,cost_label
    from resource_usage import HEATMAP_WEEKS,aggregate,combine,heatmap_days
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
    assert cost_label(estimate)=='已计价费用' and cost_label(dict(cost=10,estimated=True))=='参考费用'
    assert cost_label(dict(cost=10,estimated=False))=='费用'
    assert cost_text(dict(cost=None,unpriced=2))=='未定价' and cost_text(dict(cost=0))=='$0.00'
    assert cost_text(dict(cost=0,unpriced=2))=='$0.00'
    assert cost_text(dict(cost=.000037))=='$0.000037'
    assert cost_text(dict(cost=.000000037))=='<$0.000001'
    old=dict(rows[0]);old.pop('hours');assert len(aggregate([old])['series'])==1
    many=copy.deepcopy(rows[0]);many['days']=[dict(date=(date.today()-timedelta(days=i)).isoformat(),model='历史测试',summary=rows[0]['days'][0]['summary']) for i in range(500)]
    result=aggregate([many],'all');assert len(result['series'])<=45 and sum(s['tokens'] for _,s in result['series'])==2500000
    checks.append('AI statistics: day/yesterday/7-day/30-day/all/provider filters, hourly totals, weighted cache hit rate, unknown pricing and record counts, historical binning without losing totals. No HTTP request count invented.')
    today=date.today()
    yesterday=today-timedelta(days=1)
    since=today-timedelta(days=2)
    row=lambda day, model, summary: dict(date=day.isoformat(),model=model,summary=summary)
    summary=rows[0]['days'][0]['summary']
    first=dict(rows[0],days=[row(today,'one',summary),row(today,'two',summary),
                            row(today+timedelta(days=1),'future',summary)],historyStart=since.isoformat())
    second=dict(rows[1],days=[row(today,'one',dict(summary,cost=None,unpriced=2))])
    days=heatmap_days([first,second],today=today)
    assert len(days)+6-today.weekday()==HEATMAP_WEEKS*7 and days[0][0].weekday()==0 and days[-1][0]==today
    assert days[-1][1]['records']==6 and days[-1][1]['unpriced']==2 and days[-1][1]['cost']==.5
    assert dict(days)[yesterday]['records']==0 and dict(days)[since-timedelta(days=1)] is None
    assert heatmap_days([first,second],'Claude',today)[-1][1]['cost'] is None
    assert dict(heatmap_days([dict(first,usageComplete=False)],today=today))[yesterday] is None
    checks.append('AI heatmap: 26 Monday-aligned week columns, full daily aggregates, provider filtering, distinct zero, unknown and unpriced dates, and no future cells.')


def magpie_history(checks):
    import csv
    from datetime import timezone
    from io import StringIO
    from resource_magpie_usage import MagpieJob, apply_session_history, parse_usage
    from resource_usage import aggregate, heatmap_days, heatmap_start

    today = date.today()
    yesterday = today - timedelta(days=1)
    older = today - timedelta(days=4)
    first = heatmap_start(today)
    def stamp(day, hour=0):
        return datetime(day.year, day.month, day.day, hour, 15).astimezone(timezone.utc).isoformat()

    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(['time', 'agent', 'model', 'served_model', 'swapped', 'input_tokens',
                     'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens',
                     'cost_usd', 'source', 'rejected'])
    writer.writerows([
        (stamp(today), 'codex', 'asked', 'served', 'true', 20, 10, 60, 10, 4, '.015', 'log', 'false'),
        (stamp(today), 'codex', 'new-model', '', 'false', 1, 1, 0, 0, 0, '', 'log', 'false'),
        (stamp(yesterday), 'codex', 'free-model', '', 'false', 10, 2, 8, 0, 1, '0', 'log', 'false'),
        (stamp(older), 'codex', 'older', '', 'false', 12, 6, 4, 0, 2, '.02', 'log', 'false'),
        (stamp(first), 'codex', '', '', 'false', 5, 1, 4, 0, 0, '', 'log', 'false'),
        (stamp(today), 'codex', 'rejected', '', 'false', 50, 20, 0, 0, 0, '1', 'log', 'true'),
        (stamp(today), 'codex', 'gateway', '', 'false', 50, 20, 0, 0, 0, '1', 'gateway', 'false'),
        (stamp(today), 'dsh', 'deepseek', '', 'false', 6, 4, 0, 0, 0, '.0005', 'log', 'false'),
    ])
    stream.seek(0)
    job = MagpieJob('heatmap')
    assert job.start_date == first and job.arguments == ('--days', str((today-first).days+1))
    job.deleteLater()
    imported = parse_usage(stream, first, today)
    recent = dict(tokens=100, input=20, output=10, cacheRead=60, cacheWrite=10,
                  records=1, cost=.05, estimated=True, unpriced=0)
    fuller = dict(recent, records=2)
    local = dict(id='Codex', name='Codex', usageAvailable=True, quotas=[{'percent': 25}],
                 days=[dict(date=today.isoformat(), model='asked', summary=recent),
                       dict(date=yesterday.isoformat(), model='local', summary=fuller)],
                 hours=[dict(date=today.isoformat()+'T01', summary=recent),
                        dict(date=yesterday.isoformat()+'T05', summary=fuller)])
    merged = apply_session_history(local, imported['Codex'])
    assert merged['quotas'] == local['quotas'] and len(local['days']) == 2
    assert {row['model'] for row in merged['days']} == {'served', 'new-model', 'older', 'local', '未记录模型'}
    first_day = dict(heatmap_days([merged], today=today))[first]
    assert first_day['records'] == 1 and first_day['tokens'] == 10 and first_day['cost'] is None
    result = aggregate([merged], 'today', today=today)
    assert result['magpie'] and result['total']['tokens'] == 102 and result['total']['records'] == 2
    assert result['total']['cost'] == .015 and result['total']['unpriced'] == 1
    assert sum(row['tokens'] for _, row in result['series']) == 102
    assert result['series'][0][1]['tokens'] == 102 and result['series'][1][1]['tokens'] == 0
    assert aggregate([merged], 'yesterday', today=today)['total']['records'] == 2
    assert aggregate([merged], 'month', today=today)['total']['records'] == 5
    assert imported['Codex']['hours'][0]['summary']['cost'] == 0
    assert imported['Dsh']['days'][0]['summary']['cost'] == .0005
    checks.append('Magpie usage: CSV effective prices, local dates, exact token buckets, zero and missing prices, and historical coverage with no duplicate day totals.')
    checks.append('The default heatmap export covers the first visible week and keeps historical requests without a model name.')


def ai_tray_modes(service, app, output, checks):
    import ctypes
    from ctypes import wintypes
    from PyQt5.QtWidgets import QSystemTrayIcon
    from resource_ai_tray import amount_icon
    from resource_quota import tray_balance_text, tray_readings
    from resource_settings import ResourceOptions

    bridge, tray = service.deck, service.ai_tray
    cfg = service.cfg
    reset = (datetime.now().astimezone() + timedelta(days=5, minutes=10)).isoformat()
    week = dict(label='每周额度', percent=78, reset=reset)
    hour = dict(id='session', label='每小时额度', percent=15, window=60)
    codex = dict(id='Codex', name='Codex', plan='prolite', quotas=[week, hour])
    claude = dict(id='Claude', name='Claude', quotas=[dict(week, percent=45)])
    cursor = dict(id='Cursor', name='Cursor', stale=True, quotas=[dict(week, percent=92)])
    dsh = dict(id='Dsh', name='DeepSeek Harness', quotas=[
        dict(id='spend:CNY', label='累计消费', kind='spend', value='¥40.00'),
        dict(id='total:CNY', label='账户余额', kind='balance', value='¥20.12', percent=80)])
    rows = [cursor, dsh, claude, codex]
    cfg.update(resource_ai_providers=['Claude','Codex','Cursor','Dsh'],
               resource_quota_alert=False)
    bridge.accept(dict(type='ai', providers=rows))
    assert [(r.provider, r.remaining) for r in tray.readings] == [('Codex',85),('Claude',55),('Cursor',8)]
    assert tray.balance is None
    tip_lines = tray.tray.toolTip().splitlines()
    assert tip_lines[:2] == ['Codex Pro 100', '小时额度剩余 85%']
    cursor_line = tip_lines.index('Cursor')
    assert tip_lines[cursor_line-1:cursor_line+3] == ['', 'Cursor', '周额度剩余 8%', '上次读数']
    tray.tray.icon().pixmap(32,32).save(str(output/'ai-tray-auto.png'))
    tray.tray.activated.emit(QSystemTrayIcon.Trigger)
    app.processEvents()
    popup = tray.popup
    assert [r['id'] for r in popup.stats_view.quotas.rows] == ['Codex','Cursor','Dsh','Claude']
    assert popup.stats_view.quotas.rows[0]['quotas'][0] == hour
    assert codex['quotas'][0] == week
    assert popup.stats_view.provider.findData('Claude') >= 0
    popup.grab().save(str(output/'ai-tray-priority.png'))
    popup.hide()

    with patch.object(tray, 'refresh', wraps=tray.refresh) as refresh:
        for _ in range(4):
            service.display()
        refresh.assert_not_called()
    with patch.object(tray.tray, 'setIcon', wraps=tray.tray.setIcon) as icon, \
            patch.object(tray.tray, 'setToolTip', wraps=tray.tray.setToolTip) as tip:
        bridge.accept(dict(type='ai', providers=rows))
        icon.assert_not_called()
        tip.assert_not_called()
        with patch.object(service.runtime.dock, 'is_light', return_value=not service.runtime.dock.is_light()), \
                patch('resource_ai_tray.tray_readings', wraps=tray_readings) as select:
            tray.refresh()
            icon.assert_called_once()
            select.assert_not_called()
            tip.assert_not_called()
    tray.refresh()
    dock = service.runtime.dock
    theme, system_light = cfg['theme'], dock._sys_light
    cfg['theme'] = 'auto'
    try:
        send = ctypes.WinDLL('user32').SendMessageW
        send.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        with patch.object(service.runtime.api, 'system_is_light', return_value=not system_light):
            send(int(dock.winId()), 0x031a, 0, 0)
            app.processEvents()
            assert dock._sys_light != system_light and tray.key[0] == dock._sys_light
    finally:
        cfg['theme'], dock._sys_light = theme, system_light
        tray.refresh()

    pro = dict(codex, quotas=[week])
    bridge.accept(dict(type='ai', providers=[cursor,dsh,claude,pro]))
    assert [r.remaining for r in tray.readings] == [22,55,8]
    assert tray.tray.toolTip().splitlines()[:3] == ['Codex Pro 100', '周额度剩余 22%', '5 天后恢复']
    fourth = dict(id='Pi', name='Pi', quotas=[dict(week, percent=5)])
    assert [r.provider for r in tray_readings([*rows, fourth], 'auto','','')] == ['Codex','Claude','Pi']
    assert tray_readings([claude], 'fixed','Codex','week') == ()
    bridge.accept(dict(type='ai_error', message='离线测试'))
    assert all(r.stale for r in tray.readings) and all(row['stale'] for row in bridge.providers)
    bridge.accept(dict(type='ai', providers=rows))

    options = ResourceOptions(service)
    try:
        options.tabs.setCurrentIndex(3)
        mode, provider, metric = (options.fields['resource_ai_tray_' + key] for key in ('mode','provider','metric'))
        mode.setCurrentIndex(mode.findData('fixed'))
        provider.setCurrentIndex(provider.findData('Dsh'))
        assert metric.findData('id:spend:CNY') == -1
        metric.setCurrentIndex(metric.findData('id:total:CNY'))
        options.tabs.setCurrentIndex(0)
        options.tabs.setCurrentIndex(3)
        assert options.fields['resource_ai_tray_provider'].currentData() == 'Dsh'
        assert options.fields['resource_ai_tray_metric'].currentData() == 'id:total:CNY'
        assert options.commit()
    finally:
        options.deleteLater()
    assert '账户余额 ¥20.12' in tray.tray.toolTip()
    assert len(tray.readings) == 1 and tray.readings[0].remaining is None
    assert tray.balance == '¥20'
    for value, expected in [('¥20.99','¥20'),('$1,234.75','$1234'),('JPY 2500','JPY 2500'),
                            ('−¥5.12','−¥5'),('¥0.20','¥0'),('—',None)]:
        assert tray_balance_text(value) == expected
    from resource_status import TRAY_RING_SIZES
    from taskbar_text import foreground_ink
    for shell_mode in (0, 1):
        with patch('taskbar_text.read_mode', return_value=shell_mode), \
                patch('resource_ai_tray.tray_readings', wraps=tray_readings) as select:
            # The application theme can stay the same while the shell changes.
            send(int(dock.winId()), 0x001a, 0, 0)
            app.processEvents()
            select.assert_not_called()
        ink = foreground_ink(shell_mode)
        assert tray.taskbar_ink == ink
        icon = tray.tray.icon()
        for size in TRAY_RING_SIZES:
            current = icon.pixmap(size,size).toImage()
            assert current == amount_icon('¥20',ink).pixmap(size,size).toImage()
            assert current != amount_icon('¥0',ink).pixmap(size,size).toImage()
            pixels = [[current.pixelColor(x,y) for x in range(current.width())] for y in range(current.height())]
            assert all(p.name() == ink for row in pixels for p in row if p.alpha() > 0)
            assert not any(p.alpha() for row in (pixels[0],pixels[-1]) for p in row)
            rows_with_text = sum(any(p.alpha() for p in row) for row in pixels)
            assert 0 < rows_with_text <= round(current.height() * .62) + 2, (size, current.size(), rows_with_text)
            current.save(str(output/f'ai-tray-balance-{shell_mode}-{size}.png'))
    old_mode = cfg['taskbar_text_mode']
    try:
        cfg['taskbar_text_mode'] = 'light'
        with patch('taskbar_text.read_mode', return_value=0):
            service.runtime.apply_settings({'taskbar_text_mode'})
            assert tray.taskbar_ink == '#ffffff'
    finally:
        cfg['taskbar_text_mode'] = old_mode
        service.runtime.apply_settings({'taskbar_text_mode'})
    tray.tray.activated.emit(QSystemTrayIcon.Trigger)
    app.processEvents()
    assert popup.stats_view.quotas.rows[0]['id'] == 'Dsh'
    assert popup.stats_view.quotas.rows[0]['quotas'][0]['value'] == '¥20.12'
    popup.hide()

    cfg.update(resource_ai_tray_mode='auto', resource_ai_providers=['Dsh'])
    service.sync()
    assert tray.balance == '¥20' and '账户余额 ¥20.12' in tray.tray.toolTip()
    cfg['resource_ai_providers'] = ['Claude','Dsh']
    service.sync()
    waiting = dict(claude, quotas=[dict(week, percent=None)])
    bridge.accept(dict(type='ai', providers=[waiting,dsh]))
    assert tray.balance == '¥20' and tray.readings[0].provider == 'Dsh'
    exhausted = dict(claude, quotas=[dict(week, percent=100)])
    bridge.accept(dict(type='ai', providers=[dsh,exhausted]))
    assert tray.balance is None and tray.readings[0].remaining == 0
    bridge.accept(dict(type='ai', providers=[waiting,dsh]))
    assert tray.balance == '¥20'
    with patch.object(tray.tray, 'setIcon', wraps=tray.tray.setIcon) as icon:
        revised = dict(dsh, quotas=[dict(dsh['quotas'][1], value='¥20.99')])
        bridge.accept(dict(type='ai', providers=[waiting,revised]))
        assert tray.balance == '¥20' and '账户余额 ¥20.99' in tray.tray.toolTip()
        icon.assert_not_called()
    bridge.accept(dict(type='ai', providers=[dict(dsh, quotas=[dict(dsh['quotas'][1], value='¥0.00')])]))
    assert tray.balance == '¥0' and '账户余额 ¥0.00' in tray.tray.toolTip()
    tray.tray.activated.emit(QSystemTrayIcon.Trigger)
    app.processEvents()
    assert popup.stats_view.quotas.rows[0]['id'] == 'Dsh'
    popup.hide()
    cfg.update(resource_ai_providers=['Claude','Codex','Cursor','Dsh'])
    service.sync()
    bridge.accept(dict(type='ai', providers=rows))
    assert tray.balance is None and tray.readings[0].provider == 'Codex'
    cfg.update(resource_ai_tray_mode='fixed',resource_ai_tray_provider='Codex',
               resource_ai_tray_metric='label:每周额度')
    service.sync()
    assert tray.readings[0].remaining == 22
    cfg['resource_ai_tray_metric']='id:session'
    service.sync()
    assert tray.readings[0].remaining == 85
    checks.append('AI tray: hourly quota precedence, weekly fallback, live values before stale, up to three rings, saved fixed metric, integer balance in auto and fixed modes, exact amounts in the tooltip and details, single-line digits in both taskbar colors, click-to-prioritize and no refresh for cent-only changes or resource samples.')


def run(api,runtime,app,output,checks):
    from PyQt5.QtCore import QEvent,QRectF,QTimer
    from PyQt5.QtGui import QColor,QFontMetrics,QHelpEvent
    from PyQt5.QtWidgets import QSystemTrayIcon
    from desktop_panel_tests import wait_for
    from resource_options import DEFAULTS,SENSOR_UNITS
    from resource_compact import plan
    from resource_ai_tray import quota_icon
    from resource_quota import amount_label, amount_text, provider_plan_name, quota_color, quota_text, used_percent
    from resource_status import TRAY_RING_SIZES, band_ink
    from bluetooth_gauge import tray_icon as battery_icon
    from resource_settings import ResourceOptions
    import resource_compact
    import resource_statistics
    aggregation(checks)
    magpie_history(checks)
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);service=runtime.resources
    try:
        cfg.update(copy.deepcopy(DEFAULTS));cfg.update(resource_enabled=True,resource_collapsed=False,resource_auto_hide=False,resource_ai=True,resource_music=True,
            resource_cpu_power=True,resource_gpu_power=True,resource_rank=False,resource_background='custom',resource_appearance=dict(material='solid',theme='light',color='#c3d7df',opacity=96,blur=8,highlight=45))
        service.sync();w=service.window;bridge=service.deck
        service.accept_sample(dict(time=time.monotonic(),cpu=100.,gpu=8.,memory=(72.,11*2**30,15.4*2**30),network=(915,1024),traffic=dict(day=(17*2**20,30*2**20),month=(17*2**20,30*2**20),year=(17*2**20,30*2**20))))
        sensors={key:dict(value=value,label=label,source='隔离测试数据') for key,label,value in [('cpu_power','CPU 功耗',29.99),('gpu_power','GPU 功耗',1.56)]}
        service.sensors.values=sensors
        with patch.object(service,'play_reminder_sound') as sound:
            for used in (59,60,60,79,80,80):
                row=dict(id='quota-fixture',name='测试额度',quotas=[dict(percent=used,label='每周额度')])
                bridge.accept(dict(type='ai',providers=[row]))
            assert [call.args for call in sound.call_args_list]==[('quota',),('quota',)]
        providers = fixtures()
        now = datetime.now().astimezone()
        providers[0].update(plan='prolite', resetCredits=dict(available=2, status='ok',
            expiries=[(now+timedelta(days=18)).isoformat(),(now+timedelta(days=19)).isoformat()]))
        providers[0]['quotas'][0]['reset'] = (now+timedelta(days=6,hours=23)).isoformat()
        bridge.accept(dict(type='ai',at='2026-11-07T12:00:00+08:00',providers=providers));bridge.alert_until=0
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
        assert 'Pro 100' in {value for value, _ in painted}
        assert len(w.ai_view.summary.reset_buttons) == 1
        assert all(provider_plan_name(dict(id='Codex',plan=code)) == label for code,label in (
            ('free','Free'),('go','Go'),('plus','Plus'),('prolite','Pro 100'),('pro','Pro 200'),('promax','Pro 500'),
            ('Pro-500','Pro 500'),('unrecognized_internal_plan','套餐未识别'),('', '')))
        assert provider_plan_name(dict(id='Claude',plan='pro')) == 'Pro'
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
        service.deck.accept(dict(type='ai', providers=providers))
        tray=service.ai_tray;tray.tray.activated.emit(QSystemTrayIcon.Trigger);app.processEvents()
        popup=tray.popup;popup.stats_view.set_period('month');popup.grab().save(str(output/'redesign-ai-tray-statistics.png'));geometry=popup.geometry()
        assert (popup.width(),popup.height()) == (360,540), geometry
        assert popup.screen().availableGeometry().contains(geometry), geometry
        stats=popup.stats_view
        heatmap=stats.heatmap
        assert heatmap.y() > stats.providers.geometry().bottom()
        stats.scroll.ensureWidgetVisible(heatmap,0,0);app.processEvents()
        assert stats.scroll.verticalScrollBar().value()>0
        cell=heatmap.hit_rect(len(heatmap.days)-1).center().toPoint()
        assert heatmap.cell_at(cell)==len(heatmap.days)-1
        with patch('resource_statistics.QToolTip.showText') as tooltip:
            app.sendEvent(heatmap,QHelpEvent(QEvent.ToolTip,cell,heatmap.mapToGlobal(cell)))
            assert 'Token' in tooltip.call_args.args[1] and '调用记录' in tooltip.call_args.args[1]
        original_days=heatmap.days
        stats.set_period('week');stats.set_metric('tokens')
        assert heatmap.days is original_days
        stats.provider.setCurrentIndex(stats.provider.findData('Codex'))
        assert heatmap.days[-1][1]['tokens']==5000
        stats.provider.setCurrentIndex(0);stats.set_period('month');stats.set_metric('cost')
        popup.grab().save(str(output/'redesign-ai-tray-heatmap.png'))
        checks.append('AI usage popup: heatmap scrolls into view under providers, uses the selected tool and metric, and opens exact-date details without resetting the calendar on period changes.')
        tray.open('ai');app.processEvents();assert popup.geometry()==geometry
        popup.grab().save(str(output/'redesign-ai-tray-quota.png'))
        # The same popup must preserve every returned period and distinguish a real zero from missing data.
        multi = dict(id='Kimi',name='Kimi',plan='会员版',status='已连接',
                     quotas=[dict(label='5 小时额度',percent=20),dict(label='每周额度',percent=100),
                             dict(label='每月额度',percent=None),dict(label='账户余额',kind='balance',value='¥12.48',
                                 reset=(now+timedelta(days=7)).isoformat())])
        bridge = service.deck
        bridge.accept(dict(type='ai',providers=[providers[0],multi]))
        overview = popup.stats_view.quotas
        for width,columns in ((180,1),(360,1),(361,2),(360,1)):
            popup.resize(width,420);app.processEvents()
            assert popup.width() == width, (width, popup.width())
            scroll = popup.stats_view.scroll
            # A width change also changes the calendar's height. Observe the
            # scroll area after Qt has processed the resulting layout request.
            wait_for(app, lambda: scroll.widget().width() == scroll.viewport().width(), seconds=1)
            assert heatmap.rect().contains(heatmap.hit_rect(len(heatmap.days)-1).center().toPoint())
            painted.clear()
            with patch.object(resource_statistics,'text',record_text):
                overview.grab().save(str(output/f'quota-periods-{width}.png'))
            labels = {value for value,_ in painted}
            assert {'Pro 100','5 小时额度','每周额度','每月额度','80%','0%','—','¥12.48'} <= labels
            assert overview.rect().contains(overview.reset_buttons[0].geometry())
            assert overview.cards[-1][2] == popup.stats_view.charts.columns == columns
            assert popup.stats_view.summary.columns == (1 if width==180 else 2)
            assert (overview.reset_buttons[0].height() > 25) == (width == 180)
        selector = popup.stats_view.period_selector
        selector.setCurrentIndex(selector.findData('week'))
        assert popup.stats_view.period == 'week'
        popup.setGeometry(geometry)
        popup.hide()
        app.processEvents()
        checks.append('Quota cards: automatic Codex plans in capsule and tray, 360 × 540 logical px on tray click, single column at 180 and 360 px, two at 361 px, hour/week/month metrics, zero, unavailable, and currency balance.')
        icons=[quota_icon([(level,False)] if level is not None else [],False).pixmap(32,32).toImage()
               for level in (None,100,40,20,0)]
        assert all(a!=b for i,a in enumerate(icons) for b in icons[i+1:])
        for i,pix in enumerate(icons):pix.save(str(output/f'redesign-tray-icon-{i}.png'))
        balance = dict(kind='balance', label='账户余额', value='¥12.48', percent=87.52)
        assert amount_text(balance) == quota_text(balance) == '¥12.48' and used_percent(balance) is None
        assert amount_text(dict(value='¥12.48', percent=87.52)) == '¥12.48'
        spend=dict(kind='spend',label='累计消费',value='≥¥3.18')
        assert amount_text(spend)=='¥3.18' and amount_label(spend)=='累计消费（已知金额）'
        for light in (True,False):
            for remaining in ((100,85,70),(69,55,40),(39,25,11),(10,5,0)):
                soft,middle,strong=(QColor(quota_color(n,light)).lightness() for n in remaining)
                assert soft>middle>strong
            assert quota_color(70,light)==band_ink(70,100,70,'green',light)
            assert quota_color(40,light)==band_ink(40,70,40,'yellow',light)
            assert quota_color(10.1,light)==band_ink(10.1,40,10,'orange',light)
            assert quota_color(10,light)==band_ink(10,10,0,'red',light)
        for light in (True,False):
            for levels in ((),((25,False),),((100,False),),((40,False),(85,False),(8,True))):
                quota=quota_icon(levels,light)
                battery=battery_icon([dict(level=level,ink=quota_color(level,light),stale=stale)
                                     for level,stale in levels],not light)
                assert [s.width() for s in quota.availableSizes()]==list(TRAY_RING_SIZES)
                for side in TRAY_RING_SIZES:
                    ai = quota.pixmap(side,side).toImage()
                    bt = battery.pixmap(side,side).toImage()
                    changed = [(x,y) for y in range(side) for x in range(side)
                               if ai.pixel(x,y) != bt.pixel(x,y)]
                    assert changed and all(x >= side // 2 and y >= side // 2 for x,y in changed), (light,side,levels)
                    assert any(ai.pixelColor(x,y).alpha() > bt.pixelColor(x,y).alpha() for x,y in changed)
        ai_tray_modes(service,app,output,checks)
        cfg['resource_ai_tray']=False;service.sync();app.processEvents();assert not service.deck and not service.ai_tray and not service.signature
        (output/'resource-page-sizes.json').write_text(json.dumps(sizes),encoding='utf-8')
        checks.append('Reported UI regressions: identical page geometry, long mixed-language title in bounded lines, no aggregate hover popup, all compact values/AI/media reachable at 220–800 widths without overlapping or dropped cells, persisted custom pinned metrics, automatic width shrink, independent AI tray with hardware/music stopped, quota icons and complete shutdown.')
        checks.append('AI tray rings retain the peripheral arc geometry at all six sizes in both themes, with a Q tail only in the lower-right quadrant, including multi-ring, full, partial and stale readings.')
    finally:
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg)
