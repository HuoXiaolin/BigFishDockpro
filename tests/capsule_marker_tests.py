"""Regressions for the actual capsule window, its two menus, and its folded markers."""
import json
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QPoint, Qt, QStandardPaths
from PyQt5.QtGui import QContextMenuEvent
from PyQt5.QtWidgets import QApplication, QMessageBox

from desktop_panel_tests import wait_for
from ui_test_events import Events


def action(menu, *titles):
    for title in titles:
        item=next(item for item in menu.actions() if item.text()==title)
        menu=item.menu()
    return item


def check_strip(w,edge,checks):
    bar=edge.light.geometry()
    assert bar.top()==0 and abs(bar.center().x()-w.rect().center().x())<=1
    assert w.mask().boundingRect().top()==0 and w.y()==w.floating_rect(True).top()
    assert all(handle.isHidden() for handle in w.resize_edges.handles.values())
    for point in (bar.topLeft(),bar.bottomRight(),QPoint(bar.center().x(),bar.top()),bar.center()):
        hit=w.childAt(point) or w
        assert hit not in w.resize_edges.handles.values() and hit.cursor().shape()==Qt.ArrowCursor
    # With both switches on, a real application always uses the capsule's own top edge.
    with patch.object(edge,'edge_enabled',True),patch.object(edge,'find_edge',return_value='right'):
        assert edge.hiding_position()=='app-top'
    checks.append('App light strip aligns to the original capsule top at its horizontal center. Its edges have arrow cursors and no resize handles.')


def check_ball(w,edge,checks):
    cfg=w.service.cfg
    with patch.object(w.liquid,'paint_face'),patch.dict(cfg,resource_face=True,resource_halo=True,
            resource_halo_color_mode='mono',resource_halo_mono_color='#ef3fcc',passthrough_mode='all'):
        marker=edge.light
        w.service.runtime.click_policy.apply(w,alt_down=False)
        w.halo_phase=.2
        first=marker.grab().toImage()
        with patch('wallpaper_source.wallpaper_key',return_value=('updated wallpaper',)),patch.object(marker.glass,'clear') as clear:
            w.refresh_wallpaper()
            clear.assert_called_once()
        center=first.rect().center()
        assert first.pixelColor(center).alpha()==0 and first.pixelColor(0,0).alpha()==0
        inks=[first.pixelColor(x,y) for y in range(first.height()) for x in range(first.width())]
        assert sum(c.alpha()>100 and c.red()>c.green()+50 for c in inks)>5
        w.halo_phase=.7
        assert marker.grab().toImage()!=first
        cfg['resource_halo_color_mode']='rainbow'
        assert marker.grab().toImage()!=first
        cfg['resource_halo']=False
        empty=w.grab(marker.geometry()).toImage()
        assert max(empty.pixelColor(x,y).alpha() for y in range(empty.height()) for x in range(empty.width()))==0
        from ctypes.wintypes import POINT
        from window_layers import client_frame,native,restack,TOPMOST
        with patch.dict(cfg,passthrough_mode='none'):
            w.service.runtime.click_policy.apply(w)
            restack(int(w.winId()),TOPMOST)
            w.repaint();marker.repaint()
            px,py,width,height=client_frame(int(w.winId()))
            mid=marker.geometry().center()
            point=POINT(px+round((mid.x()+.5)*width/w.width()),py+round((mid.y()+.5)*height/w.height()))
            user=native()
            hit=user.GetAncestor(user.WindowFromPoint(point),2)
            assert hit==int(w.winId()),('clear interactive ball center',hit,int(w.winId()))
    w.service.runtime.click_policy.apply(w)
    checks.append('Covered ball keeps clear material with no underlying badge pixels, and uses the live capsule halo phase, monochrome or colorful palette and off switch.')


def check_fade(runtime,w,edge,checks):
    from desktop_idle_fade import IDLE_MS
    cfg=runtime.dock.cfg
    with patch.dict(cfg,resource_idle_fade=True,desktop_idle_fade_mode='custom',desktop_idle_fade_amount=65,
                    passthrough_mode='all',passthrough_alt_unlock=True), \
         patch('window_layers.alt_pressed',return_value=False) as alt:
        policy=runtime.click_policy
        policy.apply(w)
        runtime.idle_fade.sync_window(w)
        state=runtime.idle_fade.states[w]
        assert state.delay.interval()==IDLE_MS==6000
        state.delay.stop();state.dim()
        assert abs(w.windowOpacity()-.35)<.01 and edge.light.window() is w
        QApplication.sendEvent(w,QEvent(QEvent.Enter))
        assert state.idle and edge.fraction==0.
        alt.return_value=True
        with patch.object(edge,'visible_at_cursor',return_value=False):
            QApplication.sendEvent(w,QEvent(QEvent.Enter))
            assert state.idle
        with patch.object(edge,'visible_at_cursor',return_value=True):
            QApplication.sendEvent(w,QEvent(QEvent.Enter))
            assert not state.idle and state.factor==1. and edge.fraction==1.
        cfg['desktop_idle_fade_mode']='off'
        runtime.idle_fade.sync_window(w)
        assert w not in runtime.idle_fade.states
        edge.manual_hover=False;edge.settle()
    runtime.click_policy.apply(w)
    runtime.idle_fade.sync_window(w)
    checks.append('Covered '+edge.hidden_shape+' uses the capsule six-second fade, configured opacity and global off. Passthrough and clipped areas do not wake it; Alt interaction restores it.')


def check_export(runtime,w,folder,expected_app,checks):
    from ctypes.wintypes import POINT
    from tray_menu import rebuild
    app=QApplication.instance()
    rebuild(runtime.tray)
    monitor=action(runtime.tray.menu,'胶囊与监控','灵动胶囊').menu()
    export=action(monitor,'导出诊断日志')
    from background_contrast import majority_surface
    actual=w._content_contrast.last_measurement[1]
    expected='#{:02X}{:02X}{:02X}'.format(*majority_surface(actual))
    monitor.aboutToShow.emit()
    # The trip to the tray is outside the capsule. The exported cursor sample must survive it.
    runtime.click_policy.apply(w,POINT(-30000,-30000),False)
    with patch.object(QStandardPaths,'writableLocation',return_value=str(folder)),patch.object(QMessageBox,'information') as notice:
        export.trigger()
        wait_for(app,lambda:notice.called)
        files=list(Path(folder).glob('灵动胶囊诊断-*.json'))
        assert len(files)==1 and str(files[0]) in notice.call_args.args[-1]
        data=json.loads(files[0].read_text(encoding='utf-8'))
        assert data['最近一次鼠标在胶囊内的条件穿透判定']['穿透']
        probe=data['菜单打开时可见形态中心的窗口探测']
        windows=probe['窗口（由近到远）']
        assert windows[-1]['HWND']==hex(expected_app) and windows[-1]['PID']>0
        assert any(row['窗口类']=='CEF-OSC-WIDGET' and '跳过' in row['判定'] for row in windows)
        colors=data['最近背景取色']
        assert colors['应用窗口采样点数']==128 and colors['背景实测代表色']==expected,colors
        assert any(row['HWND']==hex(expected_app) and row['成功读取点数']>0 for row in colors['实际参与取色的窗口'])
        assert data['最近背景取色']['文字判定']=='深色字'
        assert data['当前基础文字颜色']==w.colors['ink']
        from capsule_diagnostics import write_report
        assert write_report(data,folder)!=files[0]
    checks.append('Tray action exports a unique readable diagnostics file with pre-menu cursor decision, skipped HUD, application HWND/PID, actual background RGB and selected ink.')


def check_lock(runtime,w,checks):
    from resource_settings import ResourceOptions
    from resource_options import DEFAULTS
    from tray_menu import rebuild
    from ui_style import AlignedMenu
    service=w.service
    assert DEFAULTS['resource_geometry_locked'] is False
    with patch.dict(service.cfg,resource_app_fold='off',resource_edge_hide=False,passthrough_mode='none',
                    resource_geometry_locked=False,resource_auto_hide=False):
        service.sync()
        opts=ResourceOptions(service)
        try:
            field=opts.fields['resource_geometry_locked']
            assert not field.isChecked()
            field.setChecked(True)
            assert opts.commit() and runtime.api.load_config()['resource_geometry_locked']
        finally:opts.close();opts.deleteLater()
        for compact in (False,True):
            service.fold(compact,automatic=True)
            before=w.geometry()
            assert all(grip.isHidden() for grip in w.resize_edges.handles.values())
            with patch.object(w,'expand_from',wraps=w.expand_from) as expand,patch.object(w.liquid,'drop') as drop:
                Events.drag(w,QPoint(20,16),QPoint(44,25))
                assert w.geometry()==before and not expand.called and not drop.called
                if compact:
                    Events.drag(w,QPoint(w.width()-10,w.height()//2),QPoint())
                    assert expand.called
        def toggle(menu,*args):
            assert action(menu,'导出诊断日志').isEnabled()
            lock=action(menu,'窗口与交互','锁定位置和大小')
            assert lock.isChecked()
            lock.trigger()
        with patch.object(AlignedMenu,'exec_',toggle):
            event=QContextMenuEvent(QContextMenuEvent.Mouse,QPoint(12,8),w.mapToGlobal(QPoint(12,8)))
            w.contextMenuEvent(event)
        assert not service.cfg['resource_geometry_locked'] and not runtime.api.load_config()['resource_geometry_locked']
        service.fold(False,automatic=True)
        assert all(not grip.isHidden() for grip in w.resize_edges.handles.values())
        rebuild(runtime.tray)
        assert not action(runtime.tray.menu,'胶囊与监控','灵动胶囊','锁定位置和大小').isChecked()
        runtime.tray.menu.release_if_hidden()
        QApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    checks.append('Capsule settings and both context menus share the persisted geometry lock. Both sizes ignore user drags; compact clicks and resize handles after unlocking still work.')
