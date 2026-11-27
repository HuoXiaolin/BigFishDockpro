"""Exercise native desktop layers and independent inactivity on a private desktop."""
from PyQt5.QtCore import QEvent, QRect, Qt
from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from desktop_panel_tests import wait_for
from ui_test_events import Events


def run(api, runtime, output, checks):
    from desktop_idle_fade import IDLE_MS, add_action
    from idle_fade_options import SINGLE_FIELDS, enabled
    from default_settings import apply, load
    from PyQt5.QtWidgets import QMenu
    from dock_extras import DockQuickSettings
    from settings_effects import save_changes
    from window_layers import is_topmost

    cfg = runtime.dock.cfg
    fields = ('desktop_layer_mode','passthrough_mode','desktop_idle_fade_mode','component_idle_fade','desktop_idle_fade_amount',*SINGLE_FIELDS.values(),
              'motion_enabled','component_passthrough','layer')
    previous = {key: cfg[key] for key in fields}
    policy = runtime.idle_fade
    app = QApplication.instance()
    widgets = []
    popup = None
    clock_was_visible = runtime.clock.isVisible()

    def change(**values):
        assert save_changes(runtime.tray, api, values)

    def floating(key, x):
        w = QWidget(None, Qt.Tool | Qt.FramelessWindowHint)
        widgets.append(w)
        w.runtime = runtime
        w.setProperty('clickThroughKey', key)
        w.setAttribute(Qt.WA_ShowWithoutActivating)
        w.setGeometry(x, 22, 90, 40)
        return w

    try:
        for defaults in (api.normalize_features({}), api.normalize_features({'desktop_idle_fade':True}),
                         apply(dict(cfg,clock_idle_fade=True,desktop_idle_fade_mode='on',component_idle_fade={'note:one':True}),load())):
            assert defaults['desktop_idle_fade_mode']=='custom' and not defaults['component_idle_fade']
            assert not any(defaults[key] for key in SINGLE_FIELDS.values()) and defaults['desktop_idle_fade_amount']==50
        change(desktop_layer_mode='custom', passthrough_mode='custom', desktop_idle_fade_mode='custom',
               daily_picture_idle_fade=True,resource_idle_fade=True,component_idle_fade={},
               desktop_idle_fade_amount=50, motion_enabled=True, component_passthrough={'clock':True}, layer='top')
        runtime.clock.show()
        popup = DockQuickSettings(runtime.dock.extras)
        popup.show()
        app.processEvents()
        for mode in ('top','bottom','custom'):
            popup.tiles['global_layer'].click()
            assert cfg['desktop_layer_mode']==mode
            assert is_topmost(int(runtime.clock.winId())) == (mode=='top')
            assert is_topmost(int(runtime.dock.winId())) == (mode!='bottom')
            assert cfg['desktop_idle_fade_mode']=='custom' and cfg['desktop_idle_fade_amount']==50
        for mode in ('all','none','custom'):
            popup.tiles['global_passthrough'].click()
            assert cfg['passthrough_mode']==mode
            assert runtime.clock.testAttribute(Qt.WA_TransparentForMouseEvents) == (mode!='none')
            assert cfg['component_passthrough']=={'clock':True}
        popup.hide()
        first,second = floating('picture',25),floating('custom:test',145)
        second_label = QLabel('组件内容',second)
        strip,capsule = floating('taskbar',255),floating('resource',365)
        slot = [QRect(0,0,80,30)]
        capsule.taskbar_slot = lambda:slot[0]
        for w in widgets:w.show()
        app.processEvents()
        assert first in policy.states and second not in policy.states
        menu=QMenu()
        toggle=add_action(menu,runtime,'custom:test')
        assert not toggle.isChecked()
        toggle.trigger()
        assert api.load_config()['component_idle_fade']=={'custom:test':True}
        assert first in policy.states and second in policy.states
        assert strip not in policy.states and capsule not in policy.states and popup not in policy.states
        for w in (first,second):
            assert policy.states[w].delay.interval()==IDLE_MS==6000
            app.sendEvent(w,QEvent(QEvent.Enter))
        Events.qWait(5200)
        assert first.windowOpacity()>.99
        app.sendEvent(second_label,QEvent(QEvent.Enter))
        wait_for(app,lambda:abs(first.windowOpacity()-.5)<.02,seconds=2.5)
        assert second.windowOpacity()>.99
        assert strip.windowOpacity()==capsule.windowOpacity()==1.
        change(desktop_layer_mode='top')
        assert abs(first.windowOpacity()-.5)<.02
        change(desktop_idle_fade_amount=75)
        Events.qWait(320)
        assert abs(first.windowOpacity()-.25)<.02
        app.sendEvent(first,QEvent(QEvent.Enter))
        Events.qWait(170)
        assert first.windowOpacity()>.99
        slot[0]=None
        policy.sync_window(capsule)
        policy.states[capsule].dim()
        Events.qWait(320)
        assert abs(capsule.windowOpacity()-.25)<.02
        slot[0]=QRect(0,0,80,30)
        policy.sync_window(capsule)
        assert capsule not in policy.states and capsule.windowOpacity()>.99
        policy.states[first].dim()
        Events.qWait(320)
        popup.tiles['idle_fade'].click()
        assert api.load_config()['desktop_idle_fade_mode']=='on' and first in policy.states
        assert enabled(cfg,'custom:another') and not enabled(cfg,'taskbar')
        popup.tiles['idle_fade'].click()
        assert first not in policy.states and first.windowOpacity()>.99 and cfg['desktop_layer_mode']=='top'
        assert api.load_config()['desktop_idle_fade_mode']=='off' and api.load_config()['desktop_idle_fade_amount']==75
        popup.tiles['idle_fade'].click()
        assert first in policy.states and api.load_config()['desktop_idle_fade_mode']=='custom'
        assert second in policy.states and not enabled(cfg,'custom:another')
        second.setProperty('clickThroughKey','custom:another')
        assert second not in policy.states and second.windowOpacity()>.99
        second.setProperty('clickThroughKey','custom:test')
        assert second in policy.states and not policy.states[second].idle
        second.hide()
        assert second not in policy.states and second.windowOpacity()>.99
        checks.append('Native Dock and desktop clock cycle through top, bottom and their individual layers; passthrough restores mixed per-component choices.')
        checks.append('Opt-in fresh/legacy/reset defaults, per-instance menu and persistence, six-second fade/recovery, global on/off/custom restoration, layer independence and taskbar exclusion verified.')
    finally:
        if popup is not None:
            popup.close()
            popup.deleteLater()
        for w in widgets:
            w.hide()
            w.deleteLater()
        if not clock_was_visible:runtime.clock.hide()
        change(**previous)
