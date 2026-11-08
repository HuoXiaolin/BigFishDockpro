"""Shared face settings, native card input and lite-mode gaze regression."""
import copy,time
from unittest.mock import patch
from PyQt5.QtCore import Qt,QPoint,QPointF,QEvent
from PyQt5.QtGui import QCursor,QMouseEvent


def run(api,runtime,app,output,checks):
    from glass_panel import PanelOptions
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);was_lite=runtime.lite;dialog=None
    try:
        cfg.update(panel_enabled=True,panels_visible=True,panel_auto_hide=False,panel_face=True,
                   panel_face_interactive=True,panel_face_mood='default',panel_expand_mode='click',motion_enabled=True)
        runtime.panels.apply_settings();panel=next(w for w in runtime.panels.windows.values() if w.isVisible())
        runtime.lite=True;tracker=panel.face_tracker
        for shape,collapsed in [('bar',False),('capsule',True),('ball',True)]:
            assert runtime.panels.update_panel(panel.identity,fold={'style':shape,'ratio':70})
            panel.set_collapsed_geometry(collapsed);panel.expand_timer.stop();app.processEvents();panel.grab()
            assert tracker.watch.isActive() and tracker.face_bounds is not None
            positions=[]
            for direction in (-1,1):
                tracker.face_until=time.monotonic()-1;tracker.face_frame()
                cursor=panel.mapToGlobal(tracker.face_bounds.center()+QPoint(direction*1250,direction*620))
                with patch.object(QCursor,'pos',return_value=cursor):
                    tracker.watch_face()
                    assert tracker.frames.isActive() and not tracker.was_near
                    for _ in range(16):tracker.face._t-=.033;panel.grab()
                    positions.append((tracker.face.ex.x,tracker.face.ey.x))
                    panel.grab().save(str(output/f'desktop-face-{shape}-{direction}.png'))
            assert positions[0][0]<-.4<positions[1][0] and positions[1][0]>.4
            assert positions[0][1]<positions[1][1]
            tracker.face_until=time.monotonic()-1;tracker.face_frame();assert not tracker.frames.isActive()
            panel.enterEvent(QEvent(QEvent.Enter));assert not panel.expand_timer.isActive()
        badge=panel.fold_badge;point=QPointF(badge.rect().center());global_point=QPointF(badge.mapToGlobal(point.toPoint()))
        app.sendEvent(badge,QMouseEvent(QEvent.MouseButtonPress,point,global_point,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        panel.grab();assert tracker.down and tracker.face.spread==6
        app.sendEvent(badge,QMouseEvent(QEvent.MouseButtonRelease,point,global_point,Qt.LeftButton,Qt.NoButton,Qt.NoModifier))
        assert not panel.collapsed and not tracker.down
        panel.grab().save(str(output/'desktop-face-expanded.png'))
        dialog=PanelOptions(panel);dialog.show();app.processEvents()
        dialog.face.setChecked(True);dialog.face_interactive.setChecked(False)
        dialog.fields['face_mood'].setCurrentIndex(dialog.fields['face_mood'].findData('love'));dialog.fields['face_scale'].setValue(80)
        dialog.fields['expand_mode'].setCurrentIndex(dialog.fields['expand_mode'].findData('hover'))
        assert dialog.commit();saved=api.load_config()
        assert saved['panel_face'] and saved['panel_face_mood']=='love' and saved['panel_face_scale']==80
        assert all(w.option('face') and w.option('face_scale')==80 for w in runtime.panels.windows.values())
        panel.grab();assert tracker.face._m=='love' and not tracker.watch.isActive() and not tracker.frames.isActive()
        dialog.grab().save(str(output/'desktop-face-options.png'))
        dialog.face.setChecked(False);assert dialog.commit();panel.grab()
        assert not tracker.watch.isActive() and not panel.header_icon.pixmap().isNull()
        dialog.reject();dialog=None
        cfg.update(panel_face=True,panel_face_interactive=True);panel.apply_options();panel.set_collapsed_geometry(True)
        panel.enterEvent(QEvent(QEvent.Enter));assert panel.expand_timer.isActive();panel.expand_timer.stop()
        panel.hide();assert not tracker.watch.isActive() and not tracker.frames.isActive()
        panel.show();assert tracker.watch.isActive()
        cfg['motion_enabled']=False;runtime.apply_settings({'motion_enabled'});assert not tracker.watch.isActive()
        checks.append('Desktop faces follow distant cursor positions in expanded/capsule/ball lite mode, keep click/hover controls and moods, and stop tracking when hidden or motion is disabled.')
    finally:
        if dialog:dialog.reject()
        runtime.lite=was_lite;cfg.clear();cfg.update(before);runtime.apply_settings();api.save_config(cfg)
