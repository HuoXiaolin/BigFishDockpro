"""Exercise shell, overlay and application stacking on the isolated Windows desktop."""
import os
import time
from ctypes.wintypes import POINT
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QImage, QRegion
from PyQt5.QtWidgets import QApplication

from desktop_panel_tests import wait_for
from window_layers import TOPMOST, client_frame, native, restack, window_class


def check_wallpaper_sources(folder,window,monitor,checks):
    from wallpaper_source import _source_for_monitor
    missing=str(folder/'old-slide.jpg')
    info=(missing,2,QColor('#142047'),monitor,monitor)
    alternate=folder/'readable.png'
    image=QImage(24,12,QImage.Format_RGB32);image.fill(QColor('#f2f2f2'))
    assert image.save(str(alternate))
    cache=folder/'Microsoft'/'Windows'/'Themes'/'TranscodedWallpaper'
    cache.parent.mkdir(parents=True);assert image.save(str(cache),'PNG')
    with patch.dict(os.environ,APPDATA=str(folder)), patch('wallpaper_source.desktop_wallpaper',return_value=info), \
         patch('wallpaper_source.system_wallpaper',return_value=(str(alternate),*info[1:])) as system, \
         patch('wallpaper_source._window_monitor',return_value=SimpleNamespace(flags=1)) as screen:
        assert _source_for_monitor(window,True)[0]==str(alternate)
        system.return_value=info
        assert _source_for_monitor(window,True)[0]==str(cache)
        screen.return_value=SimpleNamespace(flags=0)
        assert _source_for_monitor(window,True)[0]==missing
        with patch('wallpaper_source.desktop_wallpaper',return_value=('',*info[1:])):
            assert _source_for_monitor(window,True)[0]==''
    checks.append('Missing per-monitor wallpaper selects the readable system image or transcoded primary cache; a secondary monitor and a solid desktop keep their own source.')


def run(runtime,output,checks):
    from capsule_marker_tests import check_ball,check_desktop_return,check_export,check_fade,check_lock,check_strip
    from component_contrast import card_text_ink
    from desktop_underlay import exposed_wallpaper_samples, window_samples
    from desktop_underlay_tests import TestBackground
    from resource_options import DEFAULTS
    from resource_settings import ResourceOptions
    from wallpaper_source import _window_monitor,invalidate_source
    app=QApplication.instance()
    cfg=runtime.dock.cfg;service=runtime.resources;policy=runtime.click_policy
    before=service.auto_compact
    user=native()
    paper,application,hud,pet=[TestBackground(color) for color in ('#131922','#f4f6f8','#070707','#ffffff')]
    for overlay in (hud,pet):
        overlay.setWindowFlags(Qt.Tool|Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus)
        overlay.setAttribute(Qt.WA_TranslucentBackground)
    windows=(paper,application,hud,pet)
    geometry=app.primaryScreen().availableGeometry()
    for surface in windows:
        surface.setAttribute(Qt.WA_ShowWithoutActivating)
        surface.setGeometry(geometry)
    options=dict(resource_enabled=True,resource_collapsed=False,resource_auto_hide=False,resource_layer='top',
                 desktop_layer_mode='custom',resource_edge='free',resource_edge_snap=False,resource_edge_hide=False,
                 resource_capsule_taskbar=False,resource_expand_mode='click',resource_fold='pill',resource_app_fold='light',
                 resource_backdrop_mode='dynamic',resource_background='app',clear_background=True,dock_material='clear',
                 resource_content_mode='auto',resource_click_through=False,component_passthrough={'resource':'apps'},
                 passthrough_mode='custom',passthrough_alt_unlock=True,motion_enabled=False)
    try:
        with patch.dict(cfg,options),TemporaryDirectory() as temp:
            assert DEFAULTS['resource_app_fold']=='light'
            service.auto_compact=None;service.sync()
            w=service.window;edge=w.edge_reveal
            ui=ResourceOptions(service)
            try:
                field=ui.fields['resource_app_fold']
                assert [field.itemData(i) for i in range(field.count())]==['light','ball','off'] and field.currentData()=='light'
            finally:ui.close();ui.deleteLater()
            paper.show();hud.show();pet.show()
            shell,app_id,hud_id,pet_id=(int(s.winId()) for s in windows)
            hwnd=int(w.winId())
            def fixture_class(handle):
                if handle==shell:return 'WorkerW'
                if handle==hud_id:return 'CEF-OSC-WIDGET'
                return window_class(handle)
            get_pid=user.GetWindowThreadProcessId
            def fixture_pid(handle,pid):
                thread=get_pid(handle,pid)
                if handle in (app_id,hud_id,pet_id):pid._obj.value+=1
                return thread
            def stack():
                # Shell and ordinary app occupy the normal band. Windows may
                # reactivate the app after a popup; this must not put it above the capsule.
                for surface in (paper,application):
                    if surface.isVisible():assert restack(int(surface.winId()),0)  # HWND_TOP
                for surface in (hud,pet,w):
                    if surface.isVisible():assert restack(int(surface.winId()),TOPMOST)
            def pointer(fraction=.5,alt=False,marker=False):
                x,y,width,height=client_frame(hwnd)
                point=POINT(x+int(width*fraction),y+height//2)
                if marker:
                    center=w.mask().boundingRect().center()
                    point=POINT(x+round((center.x()+.5)*width/w.width()),y+round((center.y()+.5)*height/w.height()))
                policy.apply(w,point,alt)
                result=w.testAttribute(Qt.WA_TransparentForMouseEvents)
                assert bool(user.GetWindowLongW(hwnd,-20)&0x20)==result
                return result
            palette=QImage(24,12,QImage.Format_RGB32)
            native_bounds=_window_monitor(w).monitor
            monitor=QRect(native_bounds.left,native_bounds.top,native_bounds.right-native_bounds.left,native_bounds.bottom-native_bounds.top)
            with patch('window_layers.window_class',side_effect=fixture_class),patch('desktop_underlay.window_class',side_effect=fixture_class), \
                 patch.object(user,'GetWindowThreadProcessId',side_effect=fixture_pid),patch.object(edge,'visible_at_cursor',return_value=False), \
                 patch('wallpaper_source.desktop_wallpaper') as wallpaper:
                stack()
                for name,light in (('#131922',False),('#f4f6f8',True)):
                    path=str(Path(temp)/(name[1:]+'.png'))
                    palette.fill(QColor(name));assert palette.save(path)
                    wallpaper.return_value=(path,2,QColor('black'),monitor,monitor)
                    invalidate_source();edge.check_application()
                    assert not edge.over_app and not pointer() and window_samples(w,w.rect()) is None
                    w._content_contrast.refresh()
                    assert w.colors['light'] is light
                    colors=w.capsule_diagnostics.colors
                    assert colors['背景实测代表色']==name.upper() and colors['桌面采样点数']==128
                    assert (card_text_ink('',light,None).lightness()<128)==light
                checks.append('HUD and layered pet over the desktop keep the topmost capsule interactive; light and dark wallpaper files select opposite text colors.')

                hud.hide();pet.hide();stack()
                with patch('desktop_underlay._colors',side_effect=lambda handle,points:[(28,31,42)]*len(points)) as read:
                    assert set(exposed_wallpaper_samples(w,w.rect()))=={(28,31,42)}
                    read.reset_mock()
                    application.show();app.processEvents();application.repaint();stack()
                    assert exposed_wallpaper_samples(w,w.rect()) is None
                    read.assert_not_called()
                hud.show();pet.show()
                wallpaper.return_value=(str(Path(temp)/'131922.png'),2,QColor('black'),monitor,monitor)
                invalidate_source()
                application.show();stack();edge.check_application()
                assert edge.over_app and edge.fraction==0 and service.compact and not cfg['resource_collapsed']
                assert pointer() and not pointer(alt=True) and pointer()
                shape=w.mask().boundingRect()
                assert shape.width()>shape.height() and shape.height()<=7
                check_strip(w,edge,checks)
                check_fade(runtime,w,edge,checks)
                stack();assert pointer(marker=True)
                w._content_contrast.refresh()
                # Native readback can finish after the first Qt frame on a private desktop.
                try:
                    wait_for(app,lambda: w.colors['light'] and w._content_contrast.live and
                             w.capsule_diagnostics.colors['应用窗口采样点数']==128)
                except AssertionError as exc:
                    raise AssertionError(w.capsule_diagnostics.colors) from exc
                check_export(runtime,w,Path(temp),app_id,checks)
                stack();edge.check_application();edge.settle()
                assert edge.light.grab().save(str(Path(output)/'application-fold-light.png'))
                cfg['resource_app_fold']='ball';policy.apply(w);edge.settle()
                shape=w.mask().boundingRect()
                assert shape.width()==shape.height() and not w.mask().contains(shape.topLeft())
                assert edge.light.grab().save(str(Path(output)/'application-fold-ball.png'))
                check_ball(w,edge,checks)
                check_fade(runtime,w,edge,checks)
                notice=('quota_notice','额度提醒')
                with patch.dict(cfg,resource_idle_fade=True,desktop_idle_fade_mode='custom',desktop_idle_fade_amount=50,
                                passthrough_mode='all'):
                    policy.apply(w);runtime.idle_fade.sync_window(w)
                    fade=runtime.idle_fade.states[w];fade.dim()
                    service.peek_reminder(notice)
                    assert edge.as_pill and edge.fraction==1 and edge.notice==notice and pointer()
                    remaining=edge.peek_until-time.monotonic()
                    assert 4.5<remaining<=5 and abs(w.windowOpacity()-.5)<.01
                    try:wait_for(app,lambda:edge.fraction==0 and not edge.as_pill,7)
                    except AssertionError as exc:
                        raise AssertionError((edge.over_app,edge.target,edge.fraction,edge.notice,edge.idle.remainingTime(),
                                              service.compact,w.geometry().getRect())) from exc
                    assert runtime.idle_fade.states[w] is fade and abs(w.windowOpacity()-.5)<.01
                runtime.idle_fade.sync_window(w)
                assert w.mask().boundingRect().width()==shape.width()
                application.hide();stack();edge.check_application()
                assert not edge.over_app and not pointer() and service.compact and w.mask().isEmpty()
                assert w.detail.isHidden() and w.geometry()==w.floating_rect(True) and not cfg['resource_collapsed']
                check_desktop_return(w,application,stack,checks)
                cfg['resource_app_fold']='off';policy.apply(w)
                application.show();stack()
                assert pointer() and not edge.app_timer.isActive() and w.mask().isEmpty()
                checks.append('A real underlying app triggers the light strip and ball, keeps app passthrough and Alt override, shows a new notice for five seconds and returns to the compact desktop capsule. Off preserves the pointer policy.')

                # The same app has a cut-out over the middle of the capsule.
                left=w.mapToGlobal(w.rect().topLeft()).x()-application.x()
                hole=QRect(left+w.width()//4,0,w.width()//2,application.height())
                application.setMask(QRegion(application.rect()).subtracted(QRegion(hole)))
                assert not pointer() and pointer(.1)
                cells=window_samples(w,w.rect())
                assert cells and cells[0] is not None and cells[8] is None
                checks.append('Points in the hole of a shaped application fall through to wallpaper for both pointer routing and regional color sampling.')
            check_wallpaper_sources(Path(temp),w,monitor,checks)
            check_lock(runtime,w,checks)
    finally:
        invalidate_source()
        for surface in windows:surface.hide();surface.deleteLater()
        service.auto_compact=before
        service.sync()
