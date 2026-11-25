"""Exercise new indicator, edge, stopwatch and alarm paths on the private desktop."""
import copy
from datetime import datetime
import time
from unittest.mock import patch

from PyQt5.QtCore import Qt
from ui_test_events import Events as QTest


def wait_for(condition,seconds=2):
    end=time.monotonic()+seconds
    while not condition() and time.monotonic()<end:QTest.qWait(25)
    return condition()


def run(api,runtime,app,output,checks):
    from capsule_indicators import GROW,HOLD,SHRINK
    from desktop_edge_reveal import EdgeReveal
    from resource_compact import plan
    from resource_options import DEFAULTS,DEVICE_ALERTS
    from resource_pomodoro import DEFAULT_STATE,read_state
    from resource_settings import ResourceOptions
    cfg=runtime.dock.cfg;service=runtime.resources;before=copy.deepcopy(cfg)
    previous_auto=service.auto_compact
    model=old_clock=old_state=None
    try:
        assert DEFAULTS['resource_edge_hide'] is False and api.normalize_features({})['card_edge_hide'] is False
        service.auto_compact=None
        cfg.update(resource_enabled=True,resource_collapsed=True,resource_fold='pill',resource_edge='right',
                   resource_edge_snap=True,card_snap=True,resource_capsule_taskbar=False,resource_edge_hide=False,
                   resource_compact_width=500,resource_compact_auto_width=True,resource_halo=False,
                   motion_enabled=True,resource_expand_mode='click',resource_face=True,resource_auto_hide=False,
                   resource_pomodoro=True,resource_alert_alarm=True,resource_alert_stopwatch=True,
                   resource_compact_metrics=[],resource_alert_almanac=False,resource_alert_focus=False,
                   resource_alert_agenda=False,resource_clock=False,resource_water_enabled=False,
                   resource_runner_enabled=False,resource_mail_icon=False,resource_component_locations={})
        cfg.update({'resource_alert_'+k:False for k in DEVICE_ALERTS})
        service.sync();window=service.window;app.processEvents()
        settings=ResourceOptions(service)
        try:
            for key in DEVICE_ALERTS:settings.fields['resource_alert_'+key].setChecked(True)
            assert settings.commit()
        finally:settings.deleteLater()
        indicators=service.indicators;now=[40.]
        data={'caps_lock':False,'input_mode':'en','num_lock':True,'microphone':True,'touchpad':True,
              'bluetooth_link':(),'network_link':()}
        with patch.object(indicators,'clock',lambda:now[0]):
            for key,value in data.items():indicators.observe(key,value)
            assert not indicators.transitions and len(plan(window,window.width())['devices'])==7
            assert window.grab().save(str(output/'capsule-status-icons.png'))
            indicators.observe('caps_lock',True)
            assert indicators.fraction('caps_lock',now[0])==0
            now[0]+=GROW/2
            assert 0<indicators.fraction('caps_lock',now[0])<1
            indicators.observe('microphone',False);indicators.observe('bluetooth_link',(('test','蓝牙耳机'),))
            now[0]+=GROW+.01;indicators.advance()
            rows=plan(window,window.width())['devices']
            assert any(key=='bluetooth_link' and '耳机' in label and width>side for key,side,width,label in rows)
            assert window.grab().save(str(output/'capsule-status-expanded.png'))
            now[0]+=HOLD-.3
            indicators.observe('microphone',True)
            now[0]+=.6;indicators.advance()
            assert set(indicators.transitions)=={'microphone'}
            now[0]+=HOLD+SHRINK;indicators.advance()
            assert not indicators.transitions and not indicators.frame.isActive()
            indicators.observe('touchpad',None);indicators.observe('touchpad',False)
            assert not indicators.transitions and indicators.values['touchpad'] is False
            for kind,value in (('input_mode','zh'),('num_lock',False),('network_link',(('WLAN','测试网络'),))):
                indicators.observe(kind,value)
                assert kind in indicators.transitions
        checks.append('Seven device states: real settings roundtrip, quiet first reading, independently animated five-second labels, repeat-change deadline, missing hardware and bounded idle icons.')

        assert service.set_options(resource_edge_hide=True,resource_fold='ball')
        edge=window.edge_reveal
        with patch.object(edge,'visible_at_cursor',return_value=False):
            edge.settle();wait_for(lambda:edge.fraction==0.)
            mask=window.mask().boundingRect()
            assert edge.fraction==0. and not mask.isEmpty() and min(mask.width(),mask.height())<=7, (
                edge.edge,edge.find_edge(),edge.target,edge.fraction,window.geometry().getRect(),mask.getRect(),
                cfg['resource_edge'],window.isWindow(),service.editing,edge.peek_until)
            assert edge.light.grab().save(str(output/'capsule-edge-light.png'))
            indicators.observe('touchpad',True);wait_for(lambda:edge.fraction==1.)
            assert edge.fraction==1. and service.compact and window.fold_shape()=='pill', (
                edge.target,edge.fraction,edge.as_pill,edge.peek_until,service.compact,window.fold_shape())
            assert not window.detail.isVisible() and window.mask().isEmpty()
            QTest.qWait(max(1,int(1000*(edge.peek_until-time.monotonic()-.5))))
            assert edge.fraction==1. and service.compact
            assert wait_for(lambda:edge.fraction==0.,3) and window.fold_shape()=='ball'
            edge.move_to(1.);assert wait_for(lambda:edge.fraction==1.)
        assert service.set_options(resource_edge_hide=False,resource_fold='pill',**{'resource_alert_'+k:False for k in DEVICE_ALERTS})
        assert not indicators.selected and not indicators.poll.isActive() and not indicators.link_timer.isActive()
        assert window.mask().isEmpty()
        from PyQt5.QtWidgets import QWidget
        card=QWidget();card.setWindowFlags(Qt.Tool);card.resize(100,76)
        area=app.primaryScreen().availableGeometry();card.move(area.topLeft());card.show()
        try:
            controller=EdgeReveal(card,runtime,False);controller.configure(True);controller.edge='top'
            controller.move_to(0.);assert wait_for(lambda:controller.fraction==0.);controller.notify()
            assert controller.fraction==0. and not controller.peek_until
            controller.configure(False);assert card.mask().isEmpty()
        finally:card.close();card.deleteLater()
        checks.append('Edge hiding defaults off. An edge-docked ball shows only the light strip, opens as a compact pill on a device event, and returns after five real seconds. A desktop card stays hidden during reminders.')

        model=service.get_pomodoro();old_state=copy.deepcopy(model.state);old_clock=model.clock
        clock=[datetime(2026,11,25,18,20,10).timestamp()];model.clock=lambda:clock[0]
        model.state=dict(DEFAULT_STATE);model.sync()
        assert service.fold(False);window.select_page('pomodoro');app.processEvents()
        page=window.view('pomodoro').content;page.tab_buttons[1].click()
        page.watch_toggle.click();clock[0]+=75;model.sync()
        assert page.watch_value.text()=='01:15'
        from PyQt5.QtCore import QTime
        page.alarm_time.setTime(QTime(18,22));page.repeat.setChecked(True);page.arm.click()
        assert window.grab().save(str(output/'capsule-stopwatch-alarm.png'))
        assert service.fold(True);window.grab()
        assert ('stopwatch','01:15') in service.reminders() and ('alarm','18:22') in service.reminders()
        assert {'stopwatch','alarm'}<=set(window.reminder_kinds)
        assert window.grab().save(str(output/'capsule-timers-compact.png'))
        model.toggle_stopwatch();clock[0]+=36
        with patch.object(runtime.dock,'preview',False),patch.object(runtime.tray,'showMessage') as notify,patch.object(service,'play_reminder_sound') as sound:
            model.sync();model.sync()
            assert notify.call_count==1 and sound.call_count==1
        assert model.elapsed()==75 and ('alarm_due','18:22') in model.badges()
        assert datetime.fromtimestamp(model.state['alarm_at']).day==26
        assert read_state(model.path)['alarm_at']==model.state['alarm_at']
        model.dismiss_alarm();model.cancel_alarm();model.toggle_stopwatch();clock[0]+=3
        assert model.elapsed()==78;model.reset_stopwatch()
        model.arm_alarm('18:23',False);clock[0]+=60;model.sync()
        assert model.state['alarm_due'] and not model.state['alarm_at']
        checks.append('Stopwatch and one-time/daily alarms use real controls and compact chips. Time survives fold, pause and resume, daily alarms reschedule once, dismissed alarms and resets persist.')
    finally:
        if model and old_state is not None:
            model.clock=old_clock;model.save(old_state);model.timer.stop()
        service.auto_compact=previous_auto
        cfg.clear();cfg.update(before);service.sync();api.save_config(cfg);app.processEvents()
