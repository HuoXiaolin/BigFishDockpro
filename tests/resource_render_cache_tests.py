"""Cached layers must retain fresh readings, live overlays and hit targets."""
import copy
import time
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QEventLoop, QObject, QPoint, QPointF, QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QRegion


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
