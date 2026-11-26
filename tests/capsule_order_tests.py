"""The compact-order editor, saved preferences and native painted hit regions agree."""
import copy
import time
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QModelIndex, QTimer, Qt
from PyQt5.QtWidgets import QApplication, QListWidget, QPushButton


def sort_dialog(options, expected, target=None, *, accept=True, shot=None):
    errors=[]
    def inspect():
        dialog=QApplication.activeModalWidget()
        try:
            view=dialog.findChild(QListWidget)
            actions={b.text():b for b in dialog.findChildren(QPushButton)}
            def keys():return [view.item(i).data(Qt.UserRole) for i in range(view.count())]
            assert keys()==expected,(keys(),expected)
            assert view.dragDropMode()==view.InternalMove and not actions['上移'].isEnabled()
            if target:
                # The internal drop and the arrow buttons must move the same model.
                before=keys()
                assert view.model().moveRow(QModelIndex(),len(before)-1,QModelIndex(),0)
                assert keys()==[before[-1],*before[:-1]]
                for index,key in enumerate(target):
                    view.setCurrentRow(keys().index(key))
                    while view.currentRow()>index:actions['上移'].click()
                assert keys()==target
                view.setCurrentRow(0)
            if shot:assert dialog.grab().save(str(shot))
            actions['确定' if accept else '取消'].click()
        except BaseException as problem:
            errors.append(problem)
            if dialog:dialog.reject()
    QApplication.processEvents()
    page=options.tabs.currentWidget()
    sort_button=next(b for b in page.findChildren(QPushButton) if b.text()=='显示顺序…' and b.isVisibleTo(page))
    QTimer.singleShot(0,inspect)
    sort_button.click()
    if errors:raise errors[0]


def run(api,runtime,app,output,checks):
    from capsule_order import NAMES,configured_items,display_order
    from capsule_order_layout import ball_slots
    from config_transfer import normalize
    from resource_compact import plan
    from resource_options import COMPACT_ITEMS,DEFAULTS,DEVICE_ALERTS,METRICS
    from resource_runner import capsule_rect
    from resource_settings import ResourceOptions
    cfg=runtime.dock.cfg
    service=runtime.resources
    before=copy.deepcopy(cfg)
    auto=service.auto_compact
    options=None
    try:
        all_on=dict(cfg,resource_component_locations={},resource_compact_metrics=list(COMPACT_ITEMS))
        all_on.update({key:True for key in all_on if key.startswith(('resource_alert_','resource_compact_')) and type(all_on[key]) is bool})
        all_on.update({'resource_'+key:True for key in METRICS})
        all_on.update(resource_alert_stopwatch=True,resource_alert_alarm=True,resource_ai=True,resource_pomodoro=True,
                      resource_water_enabled=True,resource_agenda=True,resource_weather=True,resource_weather_compact=True,
                      resource_music=True,resource_mail=True,resource_mail_icon=True,resource_mail_notifications=True,
                      resource_runner_enabled=True,resource_face=True,resource_clock=True,resource_quota_alert=True)
        assert set(configured_items(all_on))==set(NAMES),set(NAMES)-set(configured_items(all_on))
        all_on['resource_component_locations']={'resources':'desktop','weather':'desktop','ai':'desktop','traffic':'desktop'}
        assert not {'cpu','board_temp','ai','weather','traffic','bluetooth'}.intersection(configured_items(all_on))
        cfg.update(copy.deepcopy(DEFAULTS))
        cfg.update(resource_enabled=True,resource_collapsed=True,resource_fold='pill',resource_auto_hide=False,
                   resource_compact_width=560,resource_compact_auto_width=False,resource_edge='free',
                   resource_compact_metrics=['memory','board_temp','volume'],resource_compact_pinned=['memory','cpu'],
                   resource_compact_order=['memory','cpu'],resource_system_status=True,resource_board_temp=False,
                   resource_ai=False,resource_ai_tray=False,resource_music=False,resource_weather=False,
                   resource_face=True,resource_runner_enabled=True,resource_mail=True,resource_mail_icon=True,
                   resource_mail_notifications=False,resource_alert_mail_code=False,resource_alert_almanac=False,
                   resource_pomodoro=False,resource_agenda=False,resource_mail_accounts=[],
                   resource_component_locations={},resource_hide_unavailable=True,motion_enabled=False)
        cfg.update({'resource_alert_'+key:key in ('caps_lock','volume') for key in DEVICE_ALERTS})
        service.auto_compact=None;service.sync()
        window=service.window
        options=ResourceOptions(service);options.tabs.setCurrentIndex(2);options.show();app.processEvents()
        initial=list(configured_items(cfg))
        assert set(initial)=={'face','memory','volume','mail','runner','device_caps_lock','clock'} and initial[-1]=='clock'
        sort_dialog(options,initial)
        # Unsaved changes on a released lazy page and directly on this page both count.
        options.tabs.setCurrentIndex(5);options.fields['resource_board_temp'].setChecked(True)
        options.tabs.setCurrentIndex(2);options.compact_fields['cpu'].setChecked(True)
        options.compact_fields['memory'].setChecked(False)
        draft=[k for k in display_order(cfg) if k in (set(initial)-{'memory'})|{'cpu','board_temp'}]
        target=['device_caps_lock','clock','volume','cpu','runner','mail','board_temp','face']
        sort_dialog(options,draft,target,accept=False)
        assert 'resource_compact_order' not in options.orders and cfg['resource_compact_order']==['memory','cpu']
        sort_dialog(options,draft,target,shot=output/'compact-order-settings.png')
        assert list(configured_items(cfg))==initial
        sort_dialog(options,target)
        assert options.commit()
        options.close();options.deleteLater();options=None
        stored=api.load_config()
        assert list(configured_items(stored))==target and len(stored['resource_compact_order'])==len(NAMES)
        assert configured_items(normalize(stored,api))==configured_items(stored)
        assert 'board_temp' in configured_items(cfg) and 'memory' not in configured_items(cfg)
        # Disabled items keep their own positions through edits and re-enabling.
        options=ResourceOptions(service);options.tabs.setCurrentIndex(2);options.show();app.processEvents()
        options.fields['resource_runner_enabled'].setChecked(False)
        reduced=[k for k in target if k!='runner'];swapped=[reduced[1],reduced[0],*reduced[2:]]
        sort_dialog(options,reduced,swapped)
        options.fields['resource_runner_enabled'].setChecked(True)
        restored=['clock','device_caps_lock',*target[2:]]
        sort_dialog(options,restored)
        options.reject();options.deleteLater();options=None
        assert list(configured_items(cfg))==target
        indicators=service.indicators
        indicators.observe('caps_lock',True);indicators.observe('volume',(42,False))
        service.accept_sample(dict(cpu=31,volume=(42,False),time=time.monotonic()))
        expected=[key for key in target if key!='board_temp']
        for shape in ('pill','bar'):
            assert service.set_options(resource_fold=shape)
            window.offset=0;image=window.grab();layout=plan(window,window.width())
            slots=layout['positions']
            assert list(slots)==expected,(list(slots),expected)
            assert all(a.x+a.width<=b.x for a,b in zip(slots.values(),list(slots.values())[1:]))
            assert slots['clock'].x < slots['cpu'].x and slots['volume'].slot.kind=='device'
            assert window.status_bounds['mail'].center().x()>capsule_rect(window).right()
            assert window.compact_bounds[window.compact_shown.index('cpu')].left()==slots['cpu'].x
            assert image.save(str(output/('compact-order-'+shape+'.png')))
        with patch.object(service,'open_component') as opened:
            window.expand_from(window.status_bounds['mail'].center().toPoint())
            opened.assert_called_once_with('mail')
        assert service.compact
        # Rain, per-city weather readings, the music card, running timers, a
        # pending agenda and a low-battery reminder all use the same spatial order.
        weather=[dict(name='示例城市',temperature=10,code=61),dict(name='另一城市',temperature=13,code=0)]
        fake_deck=SimpleNamespace(providers=[],media={'track':{'title':'示例曲目','state':'Paused'}},alert_until=0.)
        named=['music','alert_weather','weather','alert_alarm','device_caps_lock','alert_stopwatch','cpu',
               'alert_quota','alert_mail_new','alert_mail_code','alert_agenda','alert_battery','alert_focus','alert_water','alert_almanac','clock']
        alerts=(('weather_notice','雨'),('alarm','17:30'),('stopwatch','01:23'),('quota_notice','低额度'),
                ('mail_new','新邮件'),('mail_code','123456'),('agenda','会议'),('battery','10%'),
                ('focus','12:34'),('water','喝水'),('almanac','节气'))
        with patch.dict(cfg,resource_music=True,resource_weather=True,resource_compact_order=[*named,*(k for k in NAMES if k not in named)],
                        resource_alert_almanac=True,resource_compact_auto_width=False), \
                patch.object(service,'extras',SimpleNamespace(weather=weather)),patch.object(service,'deck',fake_deck), \
                patch.object(service,'reminders',return_value=alerts):
            window.resize(1360,35);window._compact_cache=None;window.offset=0
            first=plan(window,window.width())['positions']
            assert [key for key in first if key in named]==named
            window.grab()
            assert window.compact_media and set(window.reminder_kinds)=={kind for kind,_ in alerts}
            assert first['weather'].data[2]=='10℃'
            window.offset=1;assert plan(window,window.width())['positions']['weather'].data[2]=='13℃'
        window.offset=0
        assert service.set_options(resource_compact_width=96)
        count=len(plan(window,window.width())['pages']);seen=set()
        assert 1<count<100
        for page in range(count):
            window.offset=page;window.grab()
            slots=plan(window,window.width())['positions']
            assert list(slots)==[key for key in expected if key in slots]
            assert all(0<=s.x<s.x+s.width<=window.width() for s in slots.values())
            seen.update(slots)
        assert seen==set(expected),(seen,expected)
        assert service.set_options(resource_fold='ball',resource_compact_width=560)
        window.grab()
        ball=ball_slots(window,window.width())
        assert list(ball)==['device_caps_lock','volume','runner','mail','face'],list(ball)
        assert capsule_rect(window).right()<window.status_bounds['mail'].left()
        assert window.grab().save(str(output/'compact-order-ball.png'))
        with patch.dict(cfg,resource_face=False,resource_clock=False,resource_runner_enabled=False,
                        resource_mail_icon=False,resource_compact_metrics=[],
                        resource_alert_caps_lock=False,resource_alert_volume=False):
            assert not configured_items(cfg)
            options=ResourceOptions(service);options.tabs.setCurrentIndex(2);options.show();app.processEvents()
            sort_dialog(options,[])
        checks.append('Compact order filters live checkbox drafts and feature placement, preserves disabled positions, cancellation and config imports, and places the clock, readings, device icons, mail, face and pet in the chosen order across pills, bars, balls and narrow pages.')
    finally:
        if options:options.close();options.deleteLater()
        cfg.clear();cfg.update(before);service.auto_compact=auto
        api.save_config(cfg);service.sync();app.processEvents()
