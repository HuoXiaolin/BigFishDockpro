"""Halo palette persistence, native paint phases and high/low luminance coverage."""
from types import SimpleNamespace

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QScrollArea

from resource_compact import halo_damage, paint_halo
from resource_liquid_shape import body_path
from spectrum_palettes import SPECTRUM_COLOR_MODES, SPECTRUM_PALETTES


def halo_surface(width, height, fold, light, color):
    cfg = dict(resource_halo=True, resource_fold=fold, resource_halo_color_mode='mono', resource_halo_mono_color=color)
    liquid = SimpleNamespace(radii=lambda radius: (radius,) * 4,
                             shape=lambda rect, radius: body_path(rect, (radius,) * 4))
    return SimpleNamespace(rect=lambda: QRect(0, 0, width, height), colors={'light': light}, liquid=liquid,
                           service=SimpleNamespace(cfg=cfg, compact=fold!='expanded'))


def render(window, phase, background=Qt.transparent):
    image = QImage(window.rect().size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(background)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    window.halo_phase = phase
    paint_halo(window, painter)
    painter.end()
    return image


def check_paint():
    from resource_compact import halo_brushes
    for mode, (_, colors) in SPECTRUM_PALETTES.items():
        stops = halo_brushes(mode)[-1][1].gradient().stops()
        assert [color.name() for _, color in stops] == [*colors, colors[0]]
    for light, color in ((True, '#ffffff'), (False, '#000000'), (True, '#e2d8ff'), (False, '#3ce4aa')):
        bg = QColor('#edf1f5' if light else '#202b35')
        for form, size in (('ball', (49, 36)), ('pill', (300, 35)), ('bar', (230, 40)), ('expanded', (380, 172))):
            window = halo_surface(*size, form, light, color)
            frames = [render(window, phase, bg) for phase in (0., .25, .5, .75, 1.)]
            assert frames[0] == frames[-1] and all(a != b for a,b in zip(frames,frames[1:]))
            assert frames[0].pixelColor(*[n // 2 for n in size]) == bg
            # Sample both sides of the rim. Neutral-on-neutral still needs a moving edge.
            path = window.halo_path
            for i in range(4):
                at = (i / 4 - .015) % 1
                center = path.pointAtPercent(path.percentAtLength(at * window.halo_length)).toPoint()
                peak = 0
                for y in range(center.y()-3, center.y()+4):
                    for x in range(center.x()-3, center.x()+4):
                        head = frames[i].pixelColor(x,y).getRgb()[:3]
                        base = frames[(i+2)%4].pixelColor(x,y).getRgb()[:3]
                        delta = max(abs(a-b) for a,b in zip(head,base))
                        peak = max(peak, delta)
                        if delta: assert halo_damage(window).contains(QPoint(x,y))
                assert peak >= 16, (form, light, color, i, peak)
            window.service.cfg['resource_halo'] = False
            off = render(window, .2, bg)
            assert all(off.pixelColor(x,size[1]//2) == bg for x in range(size[0]))


def run(api, service, app, output, checks):
    from resource_options import normalize
    from resource_settings import ResourceOptions
    cfg = service.cfg
    keys = ('resource_halo','resource_halo_color_mode','resource_halo_mono_color')
    before = {key:cfg[key] for key in keys}
    previous_spectrum = (cfg['spectrum_color_mode'],cfg['spectrum_mono_color'])
    legacy = dict(cfg)
    for key in keys[1:]: legacy.pop(key)
    normalize(legacy, strict=True)
    assert legacy[keys[1]] == 'rainbow' and legacy[keys[2]] == ''
    invalid = dict(cfg, resource_halo_color_mode='unknown', resource_halo_mono_color='red')
    normalize(invalid)
    assert invalid[keys[1]] == 'rainbow' and invalid[keys[2]] == ''
    dialog = ResourceOptions(service)
    try:
        dialog.tabs.setCurrentIndex(4)
        dialog.show(); app.processEvents()
        enabled, mode, mono = (dialog.fields[key] for key in keys)
        enabled.setChecked(True)
        choices = [(mode.itemText(i),mode.itemData(i)) for i in range(mode.count())]
        assert choices == [('原版彩虹','rainbow'),*SPECTRUM_COLOR_MODES]
        assert all(not mode.itemIcon(i).isNull() for i in range(mode.count()))
        mode.setCurrentIndex(mode.findData('mono')); mono.setText('invalid')
        assert not dialog.commit() and '#RRGGBB' in dialog.status.text()
        mono.setText('#AAbbFF')
        dialog.tabs.setCurrentIndex(2); dialog.tabs.setCurrentIndex(4)
        enabled, mode, mono = (dialog.fields[key] for key in keys)
        assert mono.isEnabled() and mono.text()=='#AAbbFF'
        assert dialog.commit() and api.load_config()[keys[2]]=='#aabbff'
        app.processEvents()
        scroll = dialog.tabs.currentWidget().layout().itemAt(0).widget()
        assert isinstance(scroll,QScrollArea) and scroll.isAncestorOf(mono)
        scroll.ensureWidgetVisible(mono, 0, 12)
        app.processEvents()
        point = scroll.viewport().mapFromGlobal(mono.mapToGlobal(mono.rect().center()))
        assert mono.isVisibleTo(dialog) and scroll.viewport().rect().contains(point), (point,scroll.viewport().size())
        assert dialog.grab().save(str(output/'halo-settings-single.png'))
        mode.setCurrentIndex(mode.findData('aurora'))
        assert not mono.isEnabled() and dialog.commit()
        assert api.load_config()[keys[1]]=='aurora' and api.load_config()[keys[2]]=='#aabbff'
        enabled.setChecked(False)
        assert not mode.isEnabled() and not dialog.fields['resource_halo_speed'].isEnabled()
        dialog.reject()
        assert api.load_config()[keys[0]] and (cfg['spectrum_color_mode'],cfg['spectrum_mono_color'])==previous_spectrum
        check_paint()
        checks.append('Halo uses all desktop spectrum palettes independently, preserves tab drafts, validates and persists single colours. Its single-hue highlight travels around four shapes on light/dark backgrounds, including white and black, and wraps seamlessly.')
    finally:
        dialog.hide(); dialog.deleteLater()
        service.set_options(**before)
