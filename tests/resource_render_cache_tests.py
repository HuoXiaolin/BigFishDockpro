"""Cached layers must retain fresh readings, live overlays and hit targets."""
import copy
import time
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QEventLoop, QObject, QPoint, QPointF, QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QImage, QMouseEvent, QPainter, QRegion
from PyQt5.QtWidgets import QApplication


def check_mirror_damage(runtime):
    from desktop_spectrum import DesktopSpectrum, draw_spectrum
    with patch.dict(runtime.dock.cfg, spectrum_style='mirror'):
        spectrum = DesktopSpectrum(runtime)
        spectrum.resize(253,119)
        try:
            for dpr in (1.,1.25,2.):
                def draw(image,clip=None):
                    p=QPainter(image)
                    if clip is not None:p.setClipRect(clip)
                    p.setCompositionMode(QPainter.CompositionMode_Source)
                    p.fillRect(spectrum.rect(),Qt.transparent)
                    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
                    p.setRenderHint(QPainter.Antialiasing)
                    draw_spectrum(p,QRectF(spectrum.rect()),spectrum.levels,'mirror',QColor('cyan'),True,spectrum.peaks)
                    p.end()
                image=QImage(round(253*dpr),round(119*dpr),QImage.Format_ARGB32_Premultiplied)
                image.setDevicePixelRatio(dpr)
                image.fill(Qt.transparent)
                draw(image)
                for level in (.12,1.,.1,.1,0.):
                    previous=spectrum.levels
                    with patch.object(spectrum,'update') as update:
                        spectrum.set_levels([level]*120)
                    if spectrum.levels==previous:
                        update.assert_not_called()
                    else:
                        update.assert_called_once()
                        draw(image,update.call_args.args[0])
                    expected=image.copy()
                    draw(expected)
                    assert image==expected,(dpr,level)
        finally:
            spectrum.close()
            spectrum.deleteLater()


def check_colorful_spectrum(runtime):
    from math import sin, tau
    from PyQt5.QtWidgets import QMenu
    from desktop_spectrum import (BANDS, SPECTRUM_DEFAULT_SIZES, DesktopSpectrum,
                                  add_menu_actions, draw_spectrum, spectrum_area)
    from feature_config import SPECTRUM_FIXED_PALETTES, normalize

    def frame(style, size, levels, peaks=None, dpr=1, **options):
        width, height = size
        image = QImage(width*dpr, height*dpr, QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            draw_spectrum(painter, QRectF(0, 0, width, height), levels, style, QColor('white'), False, peaks, **options)
        finally:
            painter.end()
        return image

    active = [.21 + .73 * abs(sin(i * .14) * cos_level) for i, cos_level in
              enumerate(sin(i * .41 + .53) for i in range(BANDS))]
    with patch.dict(runtime.dock.cfg, spectrum_style='peak_bars', spectrum_color_mode='mono'):
        for style in SPECTRUM_FIXED_PALETTES:
            runtime.dock.cfg['spectrum_style'] = style
            assert normalize(runtime.dock.cfg)['spectrum_style'] == style
            menu = QMenu()
            add_menu_actions(menu, runtime)
            styles = next(action.menu() for action in menu.actions() if action.text() == '频谱样式')
            assert len(styles.actions()) == 8 and sum(action.isChecked() for action in styles.actions()) == 1
            assert not next(action for action in menu.actions() if action.text() == '频谱配色').isEnabled()
            for size in ((96,40), SPECTRUM_DEFAULT_SIZES[style]):
                quiet, loud = (frame(style, size, levels) for levels in ([0.] * BANDS, active))
                assert quiet != loud and not loud.pixelColor(0, 0).alpha(), (style, size)
            width, height = SPECTRUM_DEFAULT_SIZES[style]
            pixels = (loud.pixelColor(x, y) for x in range(0, width, 2) for y in range(0, height, 2))
            assert any(c.alpha() > 140 and c.saturation() > 75 for c in pixels), style
            if style == 'particle_sphere':
                assert quiet.copy(0, 0, width, 22) == loud.copy(0, 0, width, 22)
                turned = frame(style, (width, height), active, sphere_angle=.91)
                assert loud != turned and loud.copy(0, 0, width, 22) == turned.copy(0, 0, width, 22)

        width, height = SPECTRUM_DEFAULT_SIZES['crown']
        crown = frame('crown', (width, height), [.12] * BANDS)
        scan = [crown.pixelColor(x, round(height*.78)).alpha() for x in range(width//5, width*4//5)]
        assert sum(alpha >= 85 for alpha in scan) > .70 * len(scan)
        assert 85 < crown.pixelColor(width//2, round(height*.78)).alpha() < 235
        assert frame('crown', (width, height), [.12] * BANDS, crown_angle=.56) != crown
        assert frame('crown', (width, height), [.12] * BANDS, crown_angle=tau) == crown
        loud_crown = frame('crown', (width, height), [1.] * BANDS)
        # The strongest bands reach well above the quiet crown without moving its foot.
        upper = QRectF(width*.34, height*.205, width*.32, height*.035).toAlignedRect()
        assert all(crown.pixelColor(x, y).alpha() < 85
                   for x in range(upper.left(), upper.right()+1) for y in range(upper.top(), upper.bottom()+1))
        assert any(loud_crown.pixelColor(x, y).alpha() > 130
                   for x in range(upper.left(), upper.right()+1) for y in range(upper.top(), upper.bottom()+1))

        width, height = SPECTRUM_DEFAULT_SIZES['peak_bars']
        peaks = [0.] * BANDS
        band = 31
        bars = frame('peak_bars', (width, height), [.7] * BANDS, peaks, dpr=2)
        area = spectrum_area(QRectF(0, 0, width, height), 'peak_bars')
        step = area.width() / BANDS
        gap = int(2 * (area.left() + band * step))
        column = int(2 * (area.left() + (band + .5) * step))
        assert bars.pixelColor(column, height).alpha() > 200
        assert all(bars.pixelColor(gap, y).alpha() == 0 for y in range(bars.height()))

        peaks[band] = .78
        cap = frame('peak_bars', (width, height), [0.] * BANDS, peaks, dpr=2)
        center = round(2 * (9 + (width-18)*(band+.5)/BANDS))
        pixels = [(x, y) for x in range(center-12, center+13) for y in range(0, height)
                  if cap.pixelColor(x, y).alpha() > 146]
        assert pixels
        columns, rows = zip(*pixels)
        assert max(columns)-min(columns)+1 >= 3*(max(rows)-min(rows)+1)

        runtime.dock.cfg['spectrum_style'] = 'peak_bars'
        widget = DesktopSpectrum(runtime)
        try:
            with patch('desktop_spectrum.monotonic', side_effect=(1., 100., 100.5, 100.55, 100.65, 103.)):
                widget.set_levels([.8] * BANDS)
                widget.set_levels([.2] * BANDS)
                assert widget.animation_timer.isActive() and widget.peaks[0] == .8
                widget.advance_bar_peaks()
                assert .56 < widget.peaks[0] < .59
                widget.set_levels([.96] * BANDS)
                assert not widget.animation_timer.isActive() and widget.peaks[0] == .96
                widget.set_levels([0.] * BANDS)
                widget.advance_bar_peaks()
                assert not widget.animation_timer.isActive() and not any(widget.peaks)

            runtime.dock.cfg['spectrum_style'] = 'particle_sphere'
            with patch('desktop_spectrum.monotonic', side_effect=(1. + i*.1 for i in range(25))):
                widget.set_levels([.17] * BANDS)
                assert widget.animation_timer.isActive()
                widget.advance_animation()
                angle, strength = widget.sphere_angle, widget.sphere_strength
                assert angle > 0 and strength > 0
                widget.set_levels([.85] * BANDS)
                widget.advance_animation()
                assert widget.sphere_angle > angle and widget.sphere_strength > strength
                widget.set_levels([])
                for _ in range(15):
                    if not widget.animation_timer.isActive():
                        break
                    widget.advance_animation()
                assert not widget.sphere_strength and not widget.animation_timer.isActive()
        finally:
            widget.close()
            widget.deleteLater()


def check_spectrum_pointer(runtime):
    from ctypes import addressof, wintypes
    from PyQt5 import sip
    from desktop_spectrum import DesktopSpectrum, WM_MOUSEMOVE
    from ui_test_events import Events

    with patch.dict(runtime.dock.cfg, spectrum_style='mirror', spectrum_locked=False,
                    spectrum_manual_size=False, passthrough_mode='custom', component_passthrough={}):
        widget = DesktopSpectrum(runtime)
        area = QApplication.primaryScreen().availableGeometry()
        widget.setGeometry(area.x()+80, area.y()+80, 280, 140)
        widget.show()
        try:
            start = widget.geometry()
            point = widget.mapToGlobal(widget.rect().center())

            def mouse(kind, position, button=Qt.NoButton, buttons=Qt.NoButton):
                event = QMouseEvent(kind, QPointF(widget.mapFromGlobal(position)), QPointF(position),
                                    button, buttons, Qt.NoModifier)
                QApplication.sendEvent(widget, event)

            with patch.object(runtime, 'set_spectrum_options', return_value=True) as save, \
                 patch('card_snap.finish_drag', return_value=False):
                mouse(QEvent.MouseMove, point)
                assert widget.geometry()==start and widget.drag is None
                mouse(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
                assert widget.drag is not None
                # The release can be delivered elsewhere after native capture is lost.
                mouse(QEvent.MouseMove, point+QPoint(29,13))
                assert widget.geometry()==start and widget.drag is None, 'hover continued an abandoned press'
                mouse(QEvent.MouseMove, point+QPoint(38,21), buttons=Qt.LeftButton)
                assert widget.geometry()==start and widget.drag is None
                save.assert_not_called()

                mouse(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
                move = wintypes.MSG()
                move.message = WM_MOUSEMOVE
                # Windows can report the release through the flags of a move
                # which Qt consumes before producing a hover event.
                widget.nativeEvent(b'windows_generic_MSG', sip.voidptr(addressof(move)))
                assert widget.geometry()==start and widget.drag is None
                save.assert_not_called()

                for interruption in ('ungrab', 'hide'):
                    mouse(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
                    mouse(QEvent.MouseMove, point+QPoint(34,18), buttons=Qt.LeftButton)
                    assert widget.pos()!=start.topLeft()
                    if interruption=='ungrab':
                        QApplication.sendEvent(widget, QEvent(QEvent.UngrabMouse))
                    else:
                        widget.hide()
                        widget.show()
                    assert widget.geometry()==start and widget.drag is None
                    save.assert_not_called()

                mouse(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton)
                mouse(QEvent.MouseMove, point+QPoint(12,8), buttons=Qt.LeftButton)
                finish = QPoint(41,24)
                mouse(QEvent.MouseButtonRelease, point+finish, Qt.LeftButton)
                assert widget.geometry()==start.translated(finish) and widget.drag is None
                save.assert_called_once()

                before = widget.geometry()
                Events.drag(widget, QPoint(4, widget.height()//2), QPoint(-17,0))
                assert widget.width()==before.width()+17 and widget.geometry().right()==before.right()
                assert save.call_count==2 and save.call_args.kwargs['spectrum_manual_size']
        finally:
            widget.close()
            widget.deleteLater()


def run(api, runtime, app, output, checks):
    import resource_compact as compact
    from resource_options import DEFAULTS
    service = runtime.resources
    cfg = service.cfg
    saved = copy.deepcopy(cfg)
    reminders = patch.object(service, 'reminders', return_value=())
    reminders.start()
    try:
        check_mirror_damage(runtime)
        check_colorful_spectrum(runtime)
        check_spectrum_pointer(runtime)
        checks.append('Spectrum hover and a native button-up move cannot continue an abandoned press. Capture loss and hide cancel previews. Held move, final release and edge resize still persist the geometry.')
        checks.append('The translucent crown rotates with its columns and spans a larger audio-driven height range. Thin peak caps fall between bridge updates, and the particle sphere scales with audio inside its fixed outer ring.')
        cfg.update(copy.deepcopy(DEFAULTS))
        cfg.update(resource_enabled=True, resource_collapsed=True, resource_auto_hide=False,
                   resource_compact_auto_width=False, resource_compact_width=500,
                   resource_compact_height=35, resource_halo=True, resource_face=False,
                   resource_compact_rotate=False, resource_clock=False,
                   resource_compact_metrics=['cpu', 'memory', 'network'],
                   resource_compact_pinned=['cpu', 'memory', 'network'])
        service.sync()
        window = service.window

        def readings(cpu):
            service.accept_sample(dict(time=time.monotonic(), cpu=cpu, memory=(40, 8, 20),
                                       gpu=10, network=(1000, 2000)))

        def render(cached=True, scroll=None, dpr=None, damage=None):
            dpr=window.devicePixelRatioF() if dpr is None else dpr
            image = QImage(round(window.width()*dpr), round(window.height()*dpr), QImage.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(dpr)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            painter.setFont(window.font())
            if damage is not None:painter.setClipRegion(damage)
            try:
                if cached:
                    compact.paint_compact(window, painter, scroll, damage)
                else:
                    compact.paint_compact_body(window, painter, compact.plan(window, window.width()), scroll)
            finally:
                painter.end()
            return image

        readings(12)
        app.processEvents()
        # The layer uses the actual render target's DPI for sharp labels.
        for dpr in (1, 1.25, 1.5, 2):
            with patch.object(window, 'devicePixelRatioF', return_value=dpr):
                expected = render(False, dpr=dpr)
                assert render(dpr=dpr) == expected
                with patch.object(compact, 'paint_compact_body', wraps=compact.paint_compact_body) as layout:
                    for _ in range(10):
                        assert render(dpr=dpr) == expected
                    assert layout.call_count == 0
        before = render()
        readings(89)
        assert render() != before
        assert len(window.compact_bounds) == len(window.compact_shown)
        assert all(window.rect().contains(rect.toAlignedRect()) for rect in window.compact_bounds)
        original_colors = window.colors
        window.colors = dict(original_colors, ink='#ffffff', muted='#dddddd', light=False)
        actual, expected = render(), render(False)
        if actual != expected:
            actual.save(str(output/'compact-cached-theme.png'))
            expected.save(str(output/'compact-direct-theme.png'))
        assert actual == expected
        window.colors = original_colors

        title = '项目会议与设备联调验收工作安排'
        with patch.object(compact, 'compact_badges', return_value=([('agenda', title)], 1)):
            window._compact_cache = None
            window.marquee_title = title
            window.marquee_since = time.monotonic()-1
            first = render()
            surface = window._compact_surface
            window.marquee_since -= 2
            assert render() != first and window._compact_surface is surface
            assert window.reminder_kinds == ['agenda'] and len(window.reminder_bounds) == 1
        window._compact_cache = None
        window.marquee_title = ''

        # Face motion remains outside the static layer, including cache hits.
        cfg.update(resource_face=True, resource_face_interactive=True)
        service.sync()
        render()
        with patch.object(window.liquid, 'paint_face', wraps=window.liquid.paint_face) as face:
            for _ in range(5): render()
            assert face.call_count == 5

        from resource_runner import capsule_rect
        cfg['resource_runner_enabled']=True
        service.sync()
        render()
        hit_targets=list(window.compact_bounds)
        damage=QRegion(capsule_rect(window))
        with patch.object(window.liquid,'paint_face',wraps=window.liquid.paint_face) as face:
            partial=render(damage=damage)
            face.assert_not_called()
        assert partial==render(False,damage=damage) and window.compact_bounds==hit_targets

        # The dirty halo region must include every changed pixel, including corners.
        for folded, size in ((True, (500, 35)), (False, (500, 280))):
            service.auto_compact = folded
            window.resize(*size)
            def halo(phase):
                image = QImage(*size, QImage.Format_ARGB32_Premultiplied)
                image.fill(Qt.transparent)
                p = QPainter(image)
                p.setRenderHint(QPainter.Antialiasing)
                window.halo_phase = phase
                compact.paint_halo(window, p)
                p.end()
                return image
            a, b = halo(0), halo(.19)
            region = compact.halo_damage(window)
            assert not region.contains(QPoint(size[0]//2,size[1]//2))
            for y in range(size[1]):
                for x in range(size[0]):
                    if a.pixel(x, y) != b.pixel(x, y):
                        assert region.contains(QPoint(x, y)), (folded, x, y)

        service.auto_compact = None
        cfg.update(resource_collapsed=False, resource_open_page='resources')
        service.sync()
        window.select_page('resources')
        window.animation.stop()
        app.processEvents()
        settled = QEventLoop()
        QTimer.singleShot(400, settled.quit)
        settled.exec_()
        class PaintCount(QObject):
            def __init__(self):
                super().__init__()
                self.count = 0
                self.regions = []
            def eventFilter(self, watched, event):
                if event.type() == QEvent.Paint:
                    self.count += 1
                    self.regions.append(event.region().boundingRect().getRect())
                return False
        content = PaintCount()
        shell = PaintCount()
        window.graph.installEventFilter(content)
        window.installEventFilter(shell)
        try:
            for _ in range(12):
                window.animate()
                loop = QEventLoop()
                QTimer.singleShot(12, loop.quit)
                loop.exec_()
            assert shell.count >= 6 and content.count == 0, (shell.count, content.count, shell.regions, content.regions)
            with patch.object(window, 'update') as repaint:
                window.update_music_levels()
                repaint.assert_not_called()
        finally:
            window.removeEventFilter(shell)
            window.graph.removeEventFilter(content)
        checks.append('CPU rendering: stationary capsule content reused at 1/1.25/1.5/2 DPI, pixel-equivalent labels and fresh values/theme, live marquee and face on cache hits, preserved click targets; halo damage covers changed corners and avoids repainting expanded charts; hidden music does not repaint resource cards.')
    finally:
        reminders.stop()
        cfg.clear()
        cfg.update(saved)
        service.auto_compact = None
        service.sync()
        api.save_config(cfg)
