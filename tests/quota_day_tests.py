"""Local-day quota accounting and the native folded/tray indicators."""
import copy
from datetime import datetime, time, timedelta
from math import cos, radians, sin
from tempfile import TemporaryDirectory


def accounting(checks):
    from resource_quota import DailyQuota, quota_reading
    from resource_quota_day import QuotaDayHistory
    today=datetime(2026,5,6)
    start=int(today.timestamp())
    reset=start+3*86400

    def row(used, deadline=reset, period=10080, name='Codex', plan='plus', **extra):
        return dict(id=name,name=name,plan=plan,quotas=[dict(label='额度',window=period,percent=used,reset=deadline)],**extra)

    def reading(history, provider, at, observe=True):
        if observe:history.observe([provider],at)
        return quota_reading(history.decorate(provider,at),provider['quotas'][0]).daily

    with TemporaryDirectory() as directory:
        ledger=QuotaDayHistory(directory)
        first=start+600
        assert reading(ledger,row(40),first)==DailyQuota(0,0,True)
        assert reading(ledger,row(55),first+60)==DailyQuota(15,15,True)
        assert reading(ledger,row(52),first+65)==DailyQuota(12,12,True)
        assert reading(ledger,row(55),first+70)==DailyQuota(15,15,True)
        restarted=QuotaDayHistory(directory)
        assert reading(restarted,row(55,stale=True),first+80)==DailyQuota(15,15,True)
        assert reading(restarted,row(90,quotaAt=first-2),first+100) is None
        assert reading(restarted,row(90,stale=True),first+100) is None
        assert reading(restarted,row(60),first+100)==DailyQuota(20,20,True)
        assert reading(restarted,row(60,plan='pro'),first+100)==DailyQuota(0,0,True)
        assert reading(restarted,row(60,name='Claude'),first+100)==DailyQuota(0,0,True)
        assert reading(restarted,row(60),start+86401,False) is None
        assert reading(restarted,row(60),start+86401)==DailyQuota(0,0,False)
        assert reading(restarted,row(60,stale=True,quotaAt=first),start+86402) is None
        assert reading(restarted,row(64),start+86404)==DailyQuota(4,4,False)
        short=row(60,start+3600,60)
        assert reading(ledger,short,start+1200)==DailyQuota(60,60,False)
        assert reading(ledger,row(20,start+7200,60),start+4000)==DailyQuota(20,80,True)
        assert reading(ledger,row(0,start+86400,1440),start+1)==DailyQuota(0,0,False)
        assert reading(ledger,row(100,start+86400,1440),start+800)==DailyQuota(100,100,False)
        anchor=dict(at=first,plan='pro_100',quotas=row(10)['quotas'])
        latest=row(67,plan='prolite',quotaDayStart=anchor)
        assert reading(ledger,latest,first+200)==DailyQuota(57,57,True)
        assert reading(ledger,row(67,plan='free',quotaDayStart=anchor),first+200)==DailyQuota(0,0,True)
        assert reading(ledger,row(67,reset+86400,plan='business',quotaDayStart=dict(anchor,plan='business')),first+200)==DailyQuota(0,0,True)
        assert reading(ledger,row(54,start+100),first+200) is None
        cash=row(54);cash['quotas'][0].update(kind='balance',value='¥54.00')
        assert reading(ledger,cash,first+200) is None
        ledger.path.write_text('[bad',encoding='utf-8')
        assert reading(QuotaDayHistory(directory),row(60),first+100)==DailyQuota(0,0,True)
    checks.append('Daily allowance accounting across local midnight, restart, reset, corrections, plan changes, incomplete history, stale snapshots, and balances.')


def run(api,runtime,app,output,checks):
    from PyQt5.QtCore import QEvent
    from PyQt5.QtGui import QColor,QHelpEvent
    from PyQt5.QtWidgets import QToolTip
    from resource_ai_tray import quota_icon
    from resource_quota import DailyQuota,quota_color
    from resource_status import TRAY_RING_SIZES,ring_dimensions,today_ring_ink
    accounting(checks)
    service=runtime.resources
    cfg=service.cfg
    before,auto=copy.deepcopy(cfg),service.auto_compact
    try:
        cfg.update(resource_enabled=True,resource_ai=True,resource_ai_tray=True,resource_collapsed=True,
                   resource_fold='pill',resource_auto_hide=False,resource_capsule_taskbar=False,
                   resource_component_locations={},resource_compact_ai=True,resource_compact_width=350,
                   resource_compact_auto_width=False,resource_compact_pinned=['ai'],resource_quota_alert=False,
                   resource_ai_tray_mode='fixed',resource_ai_tray_provider='Codex',resource_ai_tray_metric='week')
        service.auto_compact=None;service.sync();service.fold(True)
        now=datetime.now().astimezone()
        midnight=datetime.combine(now.date(),time.min).astimezone()
        anchor=midnight+(now-midnight)/2
        reset=(now+timedelta(days=3)).isoformat()
        metric=dict(label='每周额度',kind='percent',window=10080,reset=reset)
        provider=dict(id='Codex',name='Codex',plan='pro500',quotaAt=now.isoformat(),
                      quotaDayStart=dict(at=anchor.isoformat(),plan='promax',quotas=[dict(metric,percent=25)]),
                      quotas=[dict(metric,percent=65)])
        service.deck.accept(dict(type='ai',providers=[provider]))
        tray=service.ai_tray
        assert tray.readings[0].daily==DailyQuota(40,40,True) and '今日已记录 40%' in tray.tray.toolTip()
        for light in (True,False):
            icon=quota_icon([(35,False)],light,(40,))
            for side in TRAY_RING_SIZES:
                image=icon.pixmap(side,side).toImage()
                radius=ring_dimensions(side)[0]
                def pixel(degrees):
                    angle=radians(degrees)
                    return image.pixelColor(int(side/2+sin(angle)*radius),int(side/2-cos(angle)*radius))
                def close(actual,expected):
                    return max(abs(a-b) for a,b in zip(actual.getRgb()[:3],QColor(expected).getRgb()[:3]))<=16
                assert close(pixel(60),quota_color(35,light)),(side,light,pixel(60).name())
                assert close(pixel(215),today_ring_ink(not light)),(side,light,pixel(215).name())
                assert pixel(320).alpha()<pixel(215).alpha()
            assert image.save(str(output/f'quota-tray-{"light" if light else "dark"}.png'))
        window=service.window;window.animation.stop()
        for shape in ('pill','bar','ball'):
            cfg['resource_fold']=shape;window.sync_window();app.processEvents()
            shot=window.grab()
            assert window.compact_ai_hits,shape
            rect,reading=window.compact_ai_hits[0]
            assert reading==tray.readings[0],(shape,reading,tray.readings)
            position=rect.center().toPoint()
            app.sendEvent(window,QHelpEvent(QEvent.ToolTip,position,window.mapToGlobal(position)))
            assert '今日已记录 40%' in QToolTip.text(),(shape,QToolTip.text())
            QToolTip.hideText()
            assert shot.save(str(output/f'quota-capsule-{shape}.png'))
        checks.append('Native AI rings at all six tray sizes in light and dark, plus matching colored/gray readings and hover details for pill, bar and ball.')
    finally:
        cfg.clear();cfg.update(before);service.auto_compact=auto;service.sync();api.save_config(cfg)
