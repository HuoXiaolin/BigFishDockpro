"""Check real window layering, stationary repaint and folded drag on a private desktop."""
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QApplication, QWidget

from desktop_panel_tests import wait_for
from ui_test_events import Events
from window_layers import place_desktop, restack


class TestBackground(QWidget):
    def __init__(self, color):
        super().__init__(None, Qt.FramelessWindowHint)
        self.colors = (color, color)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.colors[0]))
        painter.fillRect(self.width()//2, 0, self.width(), self.height(), QColor(self.colors[1]))


def run(runtime, output, checks):
    from custom_card_data import normalize_cards
    from custom_cards import CustomCard, CustomCards
    from daily_picture_card import DailyPictureCard
    from desktop_clock import DesktopClock
    from desktop_calendar import DesktopCalendar
    from desktop_spectrum import DesktopSpectrum, draw_spectrum
    from spectrum_palettes import SPECTRUM_PALETTES
    from desktop_watermark import WatermarkWindow
    from flash_panel import EdgeHandle
    from resource_desktop_card import ResourceDesktopCard
    from resource_panel import ResourceWindow
    from sticky_notes import NoteWindow
    from sticky_notes_store import normalize_notes
    from window_backdrop import desktop_backdrop
    app = QApplication.instance()
    dock, cfg = runtime.dock, runtime.dock.cfg
    runtime.panels.sync_windows()
    panel = next(iter(runtime.panels.windows.values()))
    original_geometry, folded = panel.geometry(), panel.collapsed
    day, night = '#f6f7f9', '#171e28'
    a, b = TestBackground(day), TestBackground(night)
    bounds = app.primaryScreen().availableGeometry()
    for base in (a,b):
        base.setGeometry(bounds)
    note = normalize_notes([dict(id='underlaynote',title='取色验证',style='glass',appearance_source='app')])[0]
    card = normalize_cards([dict(id='underlaycard',title='取色验证',appearance_source='app',rows=[dict(kind='time')])])[0]
    options = dict(desktop_layer_mode='top',panel_layer='bottom',resource_layer='bottom',card_snap=False,
                   panel_backdrop_mode='dynamic',resource_backdrop_mode='dynamic',panel_appearance_source='app',
                   theme='light',clear_background=True,dock_material='clear',panel_auto_hide=False,
                   panel_face=False,resource_background='global',resource_collapsed=True,
                   panel_collapse_style='bar',panel_locked=False,resource_auto_hide=False,card_edge_hide=False,
                   sticky_notes=[note],note_content_mode='auto',daily_picture_content_mode='auto',
                   daily_picture_appearance_source='app',watermark_auto_contrast=True,watermark_color='#c5d5e7',
                   spectrum_appearance_source='custom',spectrum_color_mode='mono',spectrum_mono_color='#c5d5e7',
                   clock_appearance=dict(cfg['clock_appearance'],material='clear',auto_contrast=True,content_mode='auto'),
                   calendar_appearance=dict(cfg['calendar_appearance'],material='clear',auto_contrast=True,content_mode='auto'),
                   clock_flipped=False,clock_style='digital',calendar_style='calendar_card')
    windows = []
    with patch.dict(cfg,options), patch.object(runtime.api,'save_config',return_value=True):
        try:
            a.show()
            restack(int(a.winId()),0)
            panel.apply_options()
            panel.set_collapsed_geometry(True)
            capsule = ResourceWindow(runtime.resources)
            photo = DailyPictureCard(runtime)
            photo.content.next_fetch = float('inf')
            detached = ResourceDesktopCard(runtime.resources,'traffic')
            clock, calendar = DesktopClock(runtime), DesktopCalendar(runtime)
            sticky = NoteWindow(runtime.notes,note['id'])
            custom = CustomCard(CustomCards(runtime),card,0)
            flash, spectrum = EdgeHandle(runtime.flash), DesktopSpectrum(runtime)
            watermark = WatermarkWindow()
            watermark.runtime = runtime
            watermark.setProperty('desktopLayerKey','watermark')
            windows = [capsule,photo,detached,clock,calendar,sticky,custom,flash,spectrum,watermark]
            capsule.sync_window()
            photo.sync()
            detached.sync_window()
            custom.sync(card)
            spectrum.sync()
            watermark.configure(cfg,app.primaryScreen())
            for window in [panel,*windows]:
                window.show()
                window.move(bounds.center()-window.rect().center())
                place_desktop(window,cfg)
                assert desktop_backdrop(window,cfg)=='dynamic'
            def backgrounds(light):
                return all(getattr(getattr(w,'_content_contrast',None),'result',None) is light for w in [panel,*windows] if w is not spectrum)
            def expect(light):
                try:wait_for(app,lambda:backgrounds(light),3)
                except AssertionError:
                    raise AssertionError([(type(w).__name__,w.isVisible(),getattr(getattr(w,'_content_contrast',None),'result',None))
                                          for w in [panel,*windows]])
                assert capsule.colors['light']==photo.colors['light']==detached.colors['light']==sticky.content_light==light
                ink=panel.text_ink_at(panel.title,panel.title.rect())
                assert ink in panel.title.styleSheet() and (QColor(ink).lightness()<128)==light
                assert (QColor(clock._control_ink).lightness()<128)==light
                with patch('desktop_spectrum.draw_spectrum',wraps=draw_spectrum) as draw:
                    spectrum.grab()
                    assert draw.call_args.args[4].name()==cfg['spectrum_mono_color'] and not draw.call_args.args[5]
                    for preset,(_,stops) in SPECTRUM_PALETTES.items():
                        with patch.dict(cfg,spectrum_color_mode=preset):
                            spectrum.grab()
                            assert draw.call_args.args[5] and draw.call_args.kwargs['palette']==stops
                    with patch.dict(cfg,spectrum_appearance_source='app',theme_color='#a86c40'):
                        spectrum.grab()
                        assert draw.call_args.args[4].name()=='#a86c40' and not draw.call_args.args[5]
                    assert getattr(spectrum,'_content_contrast',None) is None
                with patch.object(watermark.stamp,'draw',wraps=watermark.stamp.draw) as draw:
                    watermark.grab()
                    ink=draw.call_args.args[2]
                    assert (ink.name()!=cfg['watermark_color'])==light and ink.alpha()==watermark.stamp.color.alpha()
            expect(True)
            b.show()
            restack(int(b.winId()),0)
            expect(False)
            b.colors=(day,day)
            b.repaint()
            expect(True)
            checks.append('Real windows below a stationary topmost capsule, collection, photo, detached resource, clock, calendar, note, custom card, flash and watermark switch polarity on z-order and same-window repaint. Spectrum keeps its mono ink, every preset and the chosen app accent.')
            for w in windows:w.hide()
            b.colors=(day,night)
            b.repaint()
            panel.move(bounds.center()-panel.rect().center())
            def split():
                state=panel._content_contrast
                return (state.background_at(QRectF(0,0,5,5))==QColor(day).getRgb()[:3] and
                        state.background_at(QRectF(panel.width()-6,0,5,5))==QColor(night).getRgb()[:3])
            wait_for(app,split)
            delta=max(80,min(bounds.width()//3,panel.width()//2+20))
            Events.drag(panel,panel.rect().center(),QPoint(delta,0))
            wait_for(app,lambda:panel.collapsed and not panel._content_contrast.result)
            assert panel.isVisible()
            assert panel.grab().save(str(Path(output)/'folded-panel-on-dark.png'))
            Events.drag(panel,panel.rect().center(),QPoint(-2*delta,0))
            wait_for(app,lambda:panel.collapsed and panel._content_contrast.result)
            assert panel.grab().save(str(Path(output)/'folded-panel-on-light.png'))
            with patch.dict(cfg,panel_collapse_style='ball'):
                panel.set_collapsed_geometry(True)
                badge=panel.fold_badge
                assert badge.isVisible()
                Events.drag(badge,badge.rect().center(),QPoint(2*delta,0))
                wait_for(app,lambda:panel.collapsed and not panel._content_contrast.result)
            cfg.update(clear_background=False,dock_material='crystal',transparency=78,dock_highlight=38)
            panel.apply_options()
            b.colors=(night,night)
            b.repaint()
            wait_for(app,lambda:not panel._content_contrast.result)
            b.colors=(day,day)
            b.repaint()
            wait_for(app,lambda:panel._content_contrast.result)
            with patch('component_contrast.wallpaper_samples',return_value=((242,244,248),)*256):
                cfg['panel_backdrop_mode']='wallpaper'
                panel.apply_options()
                assert panel._content_contrast.result and not panel._content_contrast.live
                cfg.update(panel_backdrop_mode='dynamic',desktop_layer_mode='bottom')
                runtime.apply_settings({'desktop_layer_mode'})
                wait_for(app,lambda:not panel._content_contrast.live and panel._content_contrast.result)
            checks.append('Mixed light/dark regions, folded header mouse drag, folded ball drag, wallpaper-only mode and a global layer change use their final positions and saved policies.')
        finally:
            for w in windows:
                w.hide()
                w.deleteLater()
            for base in (a,b):
                base.hide();base.deleteLater()
    panel.set_collapsed_geometry(folded)
    panel.setGeometry(original_geometry)
    panel.apply_options()
    runtime.apply_settings({'desktop_layer_mode'})
