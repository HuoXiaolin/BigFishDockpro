"""Pure monitor maps plus real widgets on a verified private test desktop."""
import copy
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from desktop_panels import DesktopPanels
from desktop_panel_tests import wait_for
from screen_layout import capture,project,normalize_layout


def run(api,runtime,root,output,checks):
    left={'screen':'left','area':[-1920,0,1920,1040]};right={'screen':'right','area':[0,0,2560,1400]}
    record=capture([-1720,120,600,400],[right,left])
    assert record['screen']=='left'
    assert project(record,[left])==[-1720,120,600,400]
    assert project(record,[right])==[267,163,800,533]
    assert project(record,[right,left])==[-1720,120,600,400]
    original_record=copy.deepcopy(record)
    for _ in range(20):
        project(record,[{'screen':'replacement','area':[10,20,1280,720]}]);project(record,[left])
    assert record==original_record
    narrow=project({'screen':'base','area':[0,0,1920,1080],'rect':[100,100,800,400]},[{'screen':'small','area':[0,0,480,270]}])
    assert narrow[2:]==[200,100] and narrow[2]==narrow[3]*2
    assert normalize_layout({'dock':{'area':[0,0,0,1],'rect':[0,0,1,1]}})['dock']=={}
    assert not normalize_layout({'panels':{'bad':{'area':[0,0,100,100],'rect':[0,0,float('nan'),20]}}})['panels']
    app=QApplication.instance();cfg=runtime.dock.cfg;layout=runtime.layout;manager=runtime.panels
    original=copy.deepcopy(cfg);roots=list(manager.roots);provider=layout.screens
    screens=provider();current=screens[0];x,y,w,h=current['area']
    basis=dict(screen=current['screen'],area=[x,y,w*2,h*2])
    a=dict(basis,rect=[x+200,y+120,800,400]);b=dict(basis,rect=[x+400,y+180,600,400])
    from dpi_support import awareness,metric
    assert awareness()==2, 'GUI thread must be per-monitor DPI aware'
    try:
        runtime.set_lite(False);manager.close()
        cfg.update(panel_enabled=True,desktop_auto_sort=False,panel_auto_hide=False,merged_panels=False,
                   merged_active='',desktop_entries=[],disabled_categories=[],icon_size=48,position='custom',custom_bottom=200,
                   desktop_panels=[{'id':'layout-a','name':'布局演示 A','geometry':a['rect'],'compact':False,'locked':True},
                                   {'id':'layout-b','name':'布局演示 B','geometry':b['rect'],'compact':False}],
                   display_layout={'dock':dict(basis,rect=list(basis['area'])),'panels':{'layout-a':a,'layout-b':b},'merged':{}})
        api.save_config(cfg)
        runtime.panels=manager=DesktopPanels(runtime,roots=[]);manager.shown=True;manager.apply_settings();layout.apply();app.processEvents()
        first=manager.windows['layout-a'];second=manager.windows['layout-b']
        assert first.geometry().getRect()==(x+100,y+60,400,200),first.geometry().getRect()
        assert runtime.dock.ui_mult==1.0
        assert runtime.dock.icon_size==max(12,round(48*.5))
        assert first.list.iconSize().width()==metric(34,.5,12)
        assert first.query.font().pixelSize()==metric(13,.5,7)
        bar_top,area=runtime.dock.layout_position()
        assert bar_top==area.bottom()+1-100-runtime.dock.bar_h()
        stable=copy.deepcopy(cfg['display_layout'])
        geometry=first.geometry().getRect()
        layout.screens=lambda:[];layout.apply()
        assert layout.pending and not layout.timer.isActive()
        assert cfg['display_layout']==stable and first.geometry().getRect()==geometry
        layout.screens=provider;layout.apply();assert not layout.pending
        # A real connected QScreen signal invokes the coalescing timer without changing Windows settings.
        app.primaryScreen().availableGeometryChanged.emit(app.primaryScreen().availableGeometry())
        assert layout.pending and layout.timer.isActive()
        wait_for(app,lambda:not layout.pending)
        first.store_geometry();assert cfg['display_layout']==stable
        previous_metrics=(second.ui_factor,second.list.iconSize(),second.query.font().pixelSize())
        second.move(x+220,y+140);second.resize(330,210);second.store_geometry()
        assert (second.ui_factor,second.list.iconSize(),second.query.font().pixelSize())==previous_metrics
        assert cfg['display_layout']['panels']['layout-b']['area']==current['area']
        assert cfg['display_layout']['panels']['layout-b']['rect']==[x+220,y+140,330,210]
        before=copy.deepcopy(cfg);save=api.save_config;api.save_config=lambda value:False
        try:
            second.move(x+230,y+150);second.store_geometry()
            assert cfg==before
        finally:api.save_config=save
        second.store_geometry()
        assert cfg['display_layout']['panels']['layout-b']['rect']==[x+230,y+150,330,210]
        saved=copy.deepcopy(cfg['display_layout'])
        small=dict(screen='temporary-monitor',area=[x,y,max(300,w//2),max(200,h//2)])
        layout.screens=lambda:[small];layout.apply();app.processEvents()
        assert first.geometry().getRect()==tuple(project(a,[small]))
        first.collapse();first.store_geometry();first.expand();first.store_geometry()
        assert cfg['display_layout']==saved
        runtime.set_lite(True);layout.apply()
        assert runtime.lite and first.collapsed and not runtime.dock.blur_timer.isActive()
        runtime.set_lite(False);assert not first.collapsed
        assert cfg['display_layout']==saved
        # Restart on the smaller replacement, then reconnect the original display.
        manager.close();cfg.update(api.load_config())
        runtime.panels=manager=DesktopPanels(runtime,roots=[]);manager.apply_settings();app.processEvents()
        assert manager.windows['layout-a'].geometry().getRect()==tuple(project(a,[small]))
        layout.screens=provider;layout.apply();app.processEvents()
        assert manager.windows['layout-a'].geometry().getRect()==(x+100,y+60,400,200)
        assert manager.windows['layout-b'].geometry().getRect()==(x+230,y+150,330,210)
        merged=copy.deepcopy(cfg['display_layout']);merged['merged']=a
        manager.commit(merged_panels=True,merged_compact=False,merged_active='layout-a',merged_geometry=a['rect'],display_layout=merged)
        manager.sync_windows();layout.apply();app.processEvents()
        assert manager.windows['layout-a'].geometry().getRect()==(x+100,y+60,400,200)
        manager.select_page('layout-b');app.processEvents()
        assert manager.windows['layout-b'].geometry().getRect()==(x+100,y+60,400,200)
        anchor=copy.deepcopy(cfg['display_layout'])
        layout.screens=lambda:[small];layout.apply();manager.windows['layout-b'].store_geometry()
        assert cfg['display_layout']==anchor
        layout.screens=provider;layout.apply();app.processEvents()
        # Same physical 2K screens: 100% external -> 150% notebook means 2/3 logical work area.
        screen=dict(current,area=[x,y,round(w*1.5),round(h*1.5)])
        example=dict(screen,rect=[x+150,y+90,600,330])
        state=copy.deepcopy(cfg['display_layout']);state['merged']=example
        manager.commit(display_layout=state,merged_geometry=example['rect']);layout.apply();app.processEvents()
        card=manager.windows['layout-b'];ratio=card.ui_factor
        assert abs(ratio-2/3)<.003,(ratio,current,example)
        assert card.list.iconSize().width()==23
        assert card.list.gridSize().width()==52
        assert card.query.font().pixelSize()==9
        card.query.setText('2K 100% → 2K 150%');app.processEvents()
        card.grab().save(str(Path(output)/'mixed-dpi-card.png'))
        layout.apply();app.processEvents()
        assert card.ui_factor==ratio and card.query.font().pixelSize()==9
        card.move(card.x()+6,card.y()+4);card.store_geometry()
        assert abs(card.ui_factor-ratio)<.003 and card.list.iconSize().width()==23
        assert api.load_config()['display_layout']['merged']['ui_scale']==card.ui_factor
        checks.append('mixed DPI regression: per-monitor native awareness, single Qt DPI owner; same-2K 100%-150% frame/font/icon/grid/padding scale together; repeated notifications and manual move/reload retain visual scale')
        manager.windows['layout-b'].grab().save(str(Path(output)/'screen-relative-panel.png'))
        checks.append('display layout: negative-origin monitors, proportional position and uniform dimensions including minimum-size bounds, replacement/disconnect/reconnect and temporarily unavailable monitor data without anchor drift, invalid config rejection; real locked/independent/merged cards, manual move/resize rebases, save-failure retry, lite/collapsed/restart restores, actual connected QScreen signal coalesces; Dock icon/offset scale in logical pixels')
    finally:
        layout.timer.stop();layout.pending=False;layout.applying=False;layout.screens=provider
        manager.close();cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);layout.update_dock();runtime.apply_settings()
