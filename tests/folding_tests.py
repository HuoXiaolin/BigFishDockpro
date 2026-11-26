"""Independent fold styles and centered expanded-geometry restoration."""
import copy
from pathlib import Path
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget


def check_first_frame():
    import ctypes
    from ctypes import wintypes
    from unittest.mock import patch
    import fold_transition
    from window_layers import native

    class Pattern(fold_transition.Foldable,QWidget):
        ink=QColor(44,120,180,93)

        def paintEvent(self,event):
            painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen);painter.setBrush(self.ink)
            painter.drawRoundedRect(0,0,self.width()//2,self.height(),13,13)

    class Inspectable(fold_transition.FoldSurface):
        def __init__(self,owner,first):
            super().__init__(owner,first)
            # Let Win32 query the uploaded per-pixel alpha of this test window.
            self.setWindowFlag(Qt.WindowTransparentForInput,False)
            self.setAttribute(Qt.WA_TransparentForMouseEvents,False)

    window=Pattern(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint)
    window.setAttribute(Qt.WA_TranslucentBackground)
    window.setAttribute(Qt.WA_ShowWithoutActivating)
    window.setWindowOpacity(.72)
    user=native()
    user.WindowFromPoint.argtypes=[wintypes.POINT];user.WindowFromPoint.restype=wintypes.HWND
    try:
        window.setGeometry(90,90,184,52);window.show();QApplication.processEvents()
        original=window.windowOpacity()
        with patch.object(fold_transition,'FoldSurface',Inspectable):
            for width,height in ((310,190),(184,52),(184,52)):
                first=window.grab().toImage()
                same_size=window.width()==width and window.height()==height
                with fold_transition.transition(window,True,lambda:18,content_change=same_size):
                    surface=window._fold_surface;hwnd=int(surface.winId())
                    rect=wintypes.RECT();assert user.GetWindowRect(hwnd,ctypes.byref(rect))
                    style=user.GetWindowLongW(hwnd,-20)
                    user.SetWindowLongPtrW(hwnd,-20,style & ~0x20)  # WS_EX_TRANSPARENT
                    try:
                        y=(rect.top+rect.bottom)//2
                        # Cross a compositor refresh before Qt gets to send an expose.
                        ctypes.windll.dwmapi.DwmFlush()
                        for part,painted in ((.25,True),(.75,False)):
                            pt=wintypes.POINT(round(rect.left+(rect.right-rect.left)*part),y)
                            assert (user.WindowFromPoint(pt)==hwnd)==painted, (part,painted)
                    finally:
                        user.SetWindowLongPtrW(hwnd,-20,style)
                    assert surface.grab().toImage()==first and surface.windowOpacity()==original
                    if same_size:
                        window.ink=QColor(174,104,61,152);window.update()
                    window.resize(width,height)
                if same_size:assert surface.last.image.toImage()!=first
                surface.animation.setCurrentTime(200)
                assert window.windowOpacity()==original and window._fold_surface is None
    finally:
        window.close();window.deleteLater()


def check_native_glass_input():
    import ctypes
    from ctypes import wintypes
    from fold_transition import Foldable,transition
    from window_layers import native

    class Glass(Foldable,QWidget):
        def paintEvent(self,event):
            p=QPainter(self)
            p.fillRect(self.rect(),QColor(50,130,190,35))

    window=Glass(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint)
    window.setAttribute(Qt.WA_TranslucentBackground)
    window.setAttribute(Qt.WA_ShowWithoutActivating)
    user=native()
    user.WindowFromPoint.argtypes=[wintypes.POINT];user.WindowFromPoint.restype=wintypes.HWND
    def hit():
        rect=wintypes.RECT()
        hwnd=int(window.winId())
        assert user.GetWindowRect(hwnd,ctypes.byref(rect))
        return user.WindowFromPoint(wintypes.POINT(rect.left+20,rect.top+20))==hwnd
    try:
        window.setGeometry(80,90,150,46);window.show();QApplication.processEvents()
        assert hit()
        with transition(window,True,lambda:17):
            window.setGeometry(70,90,270,210)
        surface=window._fold_surface
        surface.animation.setCurrentTime(100);QApplication.processEvents()
        assert hit() and window.grab().toImage().pixelColor(20,20).alpha()==35
        surface.animation.setCurrentTime(200)
        assert hit()
    finally:
        window.close();window.deleteLater()


def check_anchored_pixels():
    from fold_transition import Foldable, native_origin, transition

    class MarkedGlass(Foldable,QWidget):
        marker = None
        def paintEvent(self,event):
            painter=QPainter(self)
            painter.fillRect(self.rect(),QColor(36,52,69,110))
            if self.marker is not None:
                scale=self.devicePixelRatioF()
                painter.scale(1/scale,1/scale)
                point=self.marker-native_origin(self)
                painter.fillRect(point.x(),point.y(),5,5,QColor('#f02987'))

    window=MarkedGlass(None,Qt.Tool|Qt.FramelessWindowHint)
    window.setAttribute(Qt.WA_TranslucentBackground)
    small,big=QRect(211,163,45,39),QRect(59,92,349,211)
    try:
        window.setGeometry(small);window.show();QApplication.processEvents()
        window.marker=native_origin(window)+QPoint(20,20)
        for target in (big,small):
            with transition(window,True,lambda:12,target_rect=lambda:target):
                surface=window._fold_surface
                canvas=surface.geometry()
                window.setGeometry(target)
            pos=window.marker-native_origin(surface)
            for t in (0,23,64,99,137,175,199):
                surface.animation.setCurrentTime(t)
                assert surface.geometry()==canvas
                image=surface.grab().toImage()
                for dx in range(-1,6):
                    for dy in range(-1,6):
                        color=image.pixelColor(pos.x()+dx,pos.y()+dy)
                        assert (color.red()>210 and color.green()<70)==(0<=dx<5 and 0<=dy<5), (target,t,dx,dy,color.getRgb())
                if t==0:
                    source=surface.first.image.toImage()
                    assert image.copy(QRect(surface.first.origin-surface.origin,source.size()))==source
            surface.advance(1.)
            target_image=surface.last.image.toImage()
            assert surface.grab().toImage().copy(QRect(surface.last.origin-surface.origin,target_image.size()))==target_image
            surface.animation.setCurrentTime(200)
            assert window.geometry()==target and window._fold_surface is None
    finally:
        window.close();window.deleteLater()


def sample_transition(window, preview=None):
    """Step the real presentation clock; the real app window already owns its final layout."""
    surface=window._fold_surface
    assert surface is not None and surface.isVisible() and surface.animation.duration()==200
    first,last=surface.first.rect,surface.last.rect
    assert window.geometry()==last and window.windowOpacity()<.01
    assert surface.windowFlags() & Qt.WindowTransparentForInput
    assert surface.windowFlags() & Qt.WindowDoesNotAcceptFocus
    import ctypes
    from ctypes import wintypes
    from window_layers import native
    assert native().GetWindowLongW(int(surface.winId()),-20) & 0x20
    def native_bounds():
        rect=wintypes.RECT()
        assert native().GetWindowRect(int(surface.winId()),ctypes.byref(rect))
        return rect.left,rect.top,rect.right,rect.bottom
    canvas=native_bounds()
    assert QApplication.activeWindow() is not surface
    opacity=surface.opacity
    area=first.united(last).adjusted(-6,-6,6,6)
    frames=9
    if preview:
        sheet=QPixmap(area.width()*frames,area.height())
        p=QPainter(sheet)
        matte=QLinearGradient(0,0,0,area.height())
        matte.setColorAt(0,QColor('#c6dce4'));matte.setColorAt(1,QColor('#9eb7ce'))
        p.fillRect(sheet.rect(),matte);p.end()
    for index in range(frames):
        surface.animation.setCurrentTime(round(surface.animation.duration()*index/(frames-1)))
        visual=window if index==frames-1 else surface
        if visual is surface:
            assert native_bounds()==canvas, 'The native animation window moved or resized during playback'
        if index==frames//2:
            mid=surface.viewport
            assert abs(mid.height()-(first.height()+last.height())/2)<=1
            assert abs(mid.width()-(first.width()+last.width())/2)<=1
            for current,a,b in zip(surface.corners,surface.first.corners,surface.last.corners):
                assert abs(current-(a+b)/2)<.01
            assert not surface.grab().isNull()
        if preview:
            p=QPainter(sheet)
            p.drawPixmap(visual.x()-area.x()+area.width()*index,visual.y()-area.y(),visual.grab())
            p.end()
    assert window._fold_surface is None and window.windowOpacity()==opacity and window.geometry()==last
    if preview:assert sheet.save(str(preview))


def run(api,runtime,root,output,checks):
    from desktop_panels import DesktopPanels
    from fold_options import FoldOptions, geometry, normalize as normalize_fold, settings
    cfg=runtime.dock.cfg;saved=copy.deepcopy(cfg);app=QApplication.instance();previous=runtime.panels;roots=list(previous.roots);previous.close();manager=None
    try:
        check_first_frame()
        check_native_glass_input()
        check_anchored_pixels()
        checks.append('Both directions display the original translucent pixels on the native fold surface before layout and the first queued expose, including its transparent area and antialiased edges.')
        cfg.update(panel_enabled=True,panels_visible=True,desktop_auto_sort=False,panel_auto_hide=False,panel_locked=False,merged_panels=False,merge_initialized=False,merge_groups=[],desktop_entries=[],desktop_excluded=[],disabled_categories=[],display_layout={},desktop_panels=[{'id':'a','name':'独立一','geometry':[100,100,360,280]},{'id':'b','name':'独立二','geometry':[500,100,320,240]}])
        cfg.update(api.normalize_features(cfg));api.save_config(cfg);manager=runtime.panels=DesktopPanels(runtime,roots=[]);manager.apply_settings();app.processEvents()
        a,b=manager.windows['a'],manager.windows['b'];before=list(a.bounds())
        cfg['motion_enabled']=True
        for shape in ('bar','capsule','ball'):
            assert manager.update_panel('a',fold={'style':shape,'ratio':55})
            a.collapse()
            sample_transition(a,Path(output)/('fold-card-'+shape+'.png'))
            a.expand();sample_transition(a)
            assert list(a.bounds())==before
        a.collapse();a._fold_surface.animation.setCurrentTime(86)
        surface=a._fold_surface
        intermediate=surface.grab().toImage()
        a.expand()
        assert a._fold_surface is surface and surface.grab().toImage()==intermediate
        sample_transition(a)
        cfg['motion_enabled']=False
        a.collapse();a.expand()
        assert a._fold_surface is None and list(a.bounds())==before
        cfg['motion_enabled']=True
        checks.append('Desktop cards and capsules animate inside a stationary native canvas. Bar, pill and ball transitions retain smooth intermediate bounds, input, and pixel-identical frames on rapid reversal.')
        assert manager.update_panel('a',fold={'style':'capsule','ratio':40})
        a.collapse();app.processEvents();assert abs(a.geometry().center().x()-(before[0]+before[2]/2))<=2 and a.y()==before[1],(before,a.geometry().getRect(),a.bounds(),settings(a),a.minimumSize(),a.maximumSize(),a.layout().sizeConstraint(),a.ui_factor)
        assert a.fold_badge.isVisible() and not a.fold_badge.text()
        a.grab().save(str(Path(output)/'panel-fold-capsule.png'))
        a.expand();app.processEvents();assert list(a.bounds())==before
        assert manager.update_panel('a',fold={'style':'ball','ratio':1});a.collapse();app.processEvents();assert a.width()==a.height() and a.fold_badge.isVisible() and not a.fold_badge.text()
        assert settings(a)['diameter'] == cfg['panel_ball_diameter'] == 44
        dialog = FoldOptions(a)
        dialog.size_field.setValue(74)
        dialog.style.setCurrentIndex(dialog.style.findData('capsule'))
        dialog.size_field.setValue(32)
        dialog.ratio.setValue(55)
        dialog.commit()
        app.processEvents()
        assert a.height() == round(32 * a.ui_factor) and abs(a.width() - before[2]*.55) <= 1
        dialog.style.setCurrentIndex(dialog.style.findData('bar'))
        assert dialog.size_field.value() == 32
        dialog.commit()
        assert a.width() == before[2] and a.height() == round(32*a.ui_factor)
        dialog.style.setCurrentIndex(dialog.style.findData('ball'))
        assert dialog.size_field.value() == 74
        dialog.commit()
        assert a.width() == a.height() == round(74*a.ui_factor) and a.surface_radius() == a.height()/2
        dialog.size_field.setValue(100)
        dialog.reject()
        assert settings(a) == dict(style='ball', ratio=55, diameter=74, height=32)
        loaded = api.load_config()
        assert next(row for row in loaded['desktop_panels'] if row['id']=='a')['fold'] == settings(a)
        from layout_profiles import snapshot
        assert snapshot(cfg)['panels']['a']['fold'] == settings(a)
        assert normalize_fold({'diameter': 999, 'height': 3}) == dict(style='capsule',ratio=70,diameter=120,height=24)
        assert geometry([10,20,360,230],settings(a),44,1.5)==[134,20,111,111]
        a.grab().save(str(Path(output)/'panel-fold-ball.png'));a.move(a.x()+30,a.y()+20);a.store_geometry();a.expand();app.processEvents();assert a.x()==before[0]+30 and a.y()==before[1]+20 and a.width()==before[2]
        assert settings(b)!=settings(a)
        manager.set_merged('a',True);app.processEvents();group_fold=dict(style='capsule',ratio=20,diameter=64,height=46)
        assert manager.update_panel('a',fold=group_fold)
        active=manager.windows[manager.active_for('a')]
        assert settings(active)==group_fold
        active.collapse();app.processEvents();manager.select_page('b');app.processEvents()
        assert settings(manager.windows['b'])==group_fold
        cfg.update(notes_enabled=True,notes_visible=True,note_style='glass');runtime.notes.reload();identity=runtime.notes.new();other=runtime.notes.new()
        assert runtime.notes.select(identity)
        note=runtime.notes.windows[identity];original=note.geometry().getRect()
        assert runtime.notes.update_and_save(identity,fold={'style':'ball','ratio':1});note.set_collapsed(True);app.processEvents()
        assert settings(note)['diameter']==42 and note.width()==note.height() and note.fold_badge.isVisible() and not note.fold_badge.text();assert abs(note.geometry().center().x()-(original[0]+original[2]/2))<=2 and note.y()==original[1]
        note.grab().save(str(Path(output)/'note-fold-ball.png'));note.move(note.x()+25,note.y()+15);note.save_geometry();note.set_collapsed(False);app.processEvents()
        assert note.width()==original[2] and note.height()==original[3] and note.x()==original[0]+25 and note.y()==original[1]+15, (original,note.geometry().getRect(),note._fold_expanded)
        assert runtime.notes.select(other) and settings(runtime.notes.windows[other])['style']=='bar'
        loaded=api.load_config();assert next(row for row in loaded['sticky_notes'] if row['id']==identity)['fold']['style']=='ball'
        from config_transfer import normalize
        assert normalize(copy.deepcopy(cfg),api)['merge_groups']==cfg['merge_groups']
        checks.append('Fold settings resize the ball, capsule and bar in place. Dimensions survive shape changes, reload and layout snapshots. Merged tabs share their sizes and dragging a folded card or note preserves its expanded dimensions.')
    finally:
        if manager:manager.close()
        cfg.clear();cfg.update(saved);api.save_config(cfg);runtime.notes.reload();runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings();app.processEvents()
