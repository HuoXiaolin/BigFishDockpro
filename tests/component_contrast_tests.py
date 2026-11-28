"""Exercise the actual compact, photo and collection widgets on controlled backgrounds."""
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QApplication


def compact_materials(window):
    from PyQt5.QtCore import QRectF
    from capsule_indicators import ACTIVE_INK
    from compact_colors import area_colors,badge_fill
    from resource_compact import paint_clock,paint_status,paint_values
    from resource_pomodoro_view import reminder_ink
    colors=window.colors
    layer=QImage(200,32,QImage.Format_ARGB32_Premultiplied)
    layer.fill(Qt.transparent)
    painter=QPainter(layer)
    try:
        with patch('resource_compact.draw_stacked_text'),patch('resource_compact.draw_clock'), \
             patch('resource_compact.clock_rows',return_value=('11/27 周五','14:21')),patch('resource_compact.draw_status_icon'):
            paint_values(window,painter,[('traffic','本月流量','382.46 GB',None)],0,16,74,True,[74])
            paint_clock(window,painter,('time','time'),74,62,16)
            for i,key in enumerate(('bluetooth','battery')):
                paint_status(window,painter,(key,'','',None),140+i*24,22,16)
    finally:painter.end()
    assert all(layer.pixelColor(x,y).alpha()==0 for x in range(layer.width()) for y in range(layer.height()))
    from resource_compact import draw_status_icon
    for light in (True,False):
        for state in ('charging','battery'):
            for level in (0,35,65,100,None):
                frame=QImage(100,100,QImage.Format_ARGB32_Premultiplied)
                frame.fill(Qt.transparent)
                p=QPainter(frame)
                p.setRenderHint(QPainter.Antialiasing)
                p.translate(50,50);p.scale(4,4)
                draw_status_icon(p,('battery','','',(level,state)),dict(colors,light=light,hover='#ffffff'))
                p.end()
                # The unfilled upper-left arc is transparent. Full readings and
                # the existing zero-charge warning still use their own ring ink.
                assert bool(frame.pixelColor(24,24).alpha())==(level in (0,100))
                if level is not None:
                    assert frame.pixelColor(86,50).alpha()>0
    swatches=(('almanac',reminder_ink),('agenda',reminder_ink),('water',reminder_ink),('focus',reminder_ink),
              *((key,lambda k,light:ACTIVE_INK[k][int(not light)]) for key in ('bluetooth_link','network_link','brightness')))
    for key,accent in swatches:
        light=badge_fill(accent(key,True),dict(colors,light=True))
        dark=badge_fill(accent(key,False),dict(colors,light=False))
        for color,original in ((light,accent(key,True)),(dark,accent(key,False))):
            assert color.hslSaturationF()>.25 and abs(color.hslHue()-QColor(original).hslHue())<=1
            assert 0<color.alpha()<100
        for daylight,old in ((True,56),(False,77)):
            base=dict(colors, light=daylight)
            active=[badge_fill(accent(key,daylight),dict(base,badge_strength=n)).alpha() for n in (0,20,40,70,100)]
            quiet=[badge_fill(accent(key,daylight),dict(base,badge_strength=n),False).alpha() for n in (0,20,40,70,100)]
            assert active[0]==quiet[0]==0 and active[2]>old
            assert all(a<b for a,b in zip(active,active[1:])) and all(a<b for a,b in zip(quiet,quiet[1:]))
            assert all(a>b for a,b in zip(active[1:],quiet[1:])) and active[-1]<255
        assert light.lightness()>dark.lightness()
    width=window.width()
    assert area_colors(window,QRectF(0,0,width/8,window.height()),colors)['light']
    assert not area_colors(window,QRectF(width*7/8,0,width/8,window.height()),colors)['light']


def badge_settings(api,runtime,output,checks):
    from resource_options import DEFAULT_BADGE_STRENGTH
    from resource_settings import BadgeFillPreview, ResourceOptions
    from settings_design import NumericControl
    service=runtime.resources
    field='resource_badge_strength'
    original=service.cfg[field]
    dialog=ResourceOptions(service)
    try:
        dialog.tabs.setCurrentIndex(4)
        dialog.show();QApplication.processEvents()
        spin=dialog.fields[field]
        control=spin.parentWidget()
        assert isinstance(control,NumericControl) and (spin.minimum(),spin.maximum())==(0,100)
        preview=dialog.findChild(BadgeFillPreview)
        assert preview is not None and preview.isVisible()
        images=[]
        for n in (0,DEFAULT_BADGE_STRENGTH,100):
            control.slider.setValue(n);QApplication.processEvents()
            assert spin.value()==n and service.cfg[field]==original
            img=preview.grab().toImage()
            images.append(img)
            assert img.save(str(Path(output)/f'compact-badge-strength-{n}.png'))
        assert images[0]!=images[1] and images[1]!=images[2]
        spin.setValue(72)
        dialog.tabs.setCurrentIndex(2);dialog.tabs.setCurrentIndex(4)
        assert dialog.fields[field].value()==72 and dialog.commit()
        assert api.load_config()[field]==service.cfg[field]==72
        if service.window:assert service.window.colors['badge_strength']==72
        dialog.fields[field].setValue(DEFAULT_BADGE_STRENGTH)
        from ui_test_events import Events
        from PyQt5.QtWidgets import QScrollArea
        Events.qWait(100)
        spin=dialog.fields[field]
        ancestor=spin.parentWidget()
        while ancestor and not isinstance(ancestor,QScrollArea):
            ancestor=ancestor.parentWidget()
        assert ancestor is not None
        ancestor.ensureWidgetVisible(spin,8,60);QApplication.processEvents()
        assert spin.isVisibleTo(dialog) and dialog.grab().save(str(Path(output)/'compact-badge-settings.png'))
        dialog.reject()
        reopened=ResourceOptions(service)
        try:
            reopened.tabs.setCurrentIndex(4)
            assert reopened.fields[field].value()==72
        finally:reopened.close();reopened.deleteLater()
        checks.append('Compact badge intensity previews both backgrounds from 0 to 100, preserves the draft across pages, applies on Save and reloads the saved value after discarding a later edit.')
    finally:
        dialog.close();dialog.deleteLater()
        service.set_options(**{field:original})


def check_widgets(api,runtime,output,checks):
    from appearance_presets import CONTENT_MODES
    from background_contrast import contrast
    from calendar_almanac import ASSETS
    from component_contrast import card_text_ink
    from daily_picture_card import DailyPictureCard
    from resource_panel import ResourceWindow
    from resource_settings import ResourceOptions
    from component_preferences import ComponentPreferences
    from glass_panel import PanelOptions
    cfg=runtime.dock.cfg
    panels=list(runtime.panels.windows.values())
    panel=next((window for window in panels if window.isVisible()),panels[0])
    service=runtime.resources
    assert card_text_ink('#193747',True,(237,245,249)).name()=='#193747'
    assert card_text_ink('#193747',False,(57,23,129)).name()=='#ffffff'
    assert card_text_ink('#f1f6fa',True,(237,245,249)).name()=='#101b25'
    from PyQt5.QtCore import QRect
    from background_contrast import wallpaper_samples
    from tempfile import TemporaryDirectory
    from wallpaper_source import _window_monitor, invalidate_source
    with TemporaryDirectory() as folder:
        bands=QImage(40,24,QImage.Format_RGB32)
        bands.fill(QColor('#451687'))
        p=QPainter(bands);p.fillRect(0,0,20,24,QColor('#d5eafa'));p.end()
        source=str(Path(folder)/'split.png')
        assert bands.save(source)
        geometry=panel.screen().geometry()
        native_rect=_window_monitor(panel).monitor
        monitor=QRect(native_rect.left,native_rect.top,native_rect.right-native_rect.left,native_rect.bottom-native_rect.top)
        origin=panel.mapFromGlobal(geometry.topLeft())
        def sample_at(fraction):
            rect=QRect(origin.x()+round(geometry.width()*fraction),origin.y()+geometry.height()//2,8,8)
            return wallpaper_samples(panel,rect,allow_fallback=True)[0]
        invalidate_source()
        try:
            with patch('wallpaper_source.desktop_wallpaper',side_effect=OSError('per-monitor API unavailable')), \
                 patch('wallpaper_source.system_wallpaper',return_value=(source,2,QColor('black'),monitor,monitor)) as system:
                assert sample_at(.25)==(213,234,250) and sample_at(.75)==(69,22,135)
                assert system.call_count==1
        finally:invalidate_source()
    backgrounds={'purple':('#391781','#64369f'),'blue':('#169bdb','#3071dd'),
                 'light':('#eef4fa','#cce3fa'),'mixed':('#dceaf9','#46248e')}
    pixels=()
    def sample(widget,rect,*,allow_fallback):
        assert rect==widget.rect()
        return pixels
    def picture(window,name):
        pixmap=window.grab()
        frame=QImage(pixmap.size(),QImage.Format_ARGB32_Premultiplied)
        frame.setDevicePixelRatio(pixmap.devicePixelRatioF())
        p=QPainter(frame)
        for i in range(16):
            lo=window.width()*i//16;hi=window.width()*(i+1)//16
            p.fillRect(lo,0,hi-lo,window.height(),QColor(*pixels[i]))
        p.drawPixmap(0,0,pixmap);p.end()
        assert frame.save(str(Path(output)/('contrast-'+name+'.png')))
    with patch.dict(cfg,theme='light',panel_material='clear',panel_opacity=0,panel_highlight=0,
                    panel_appearance_source='custom',panel_backdrop_mode='wallpaper',card_design='crystal',
                    panel_content_mode='auto',resource_content_mode='auto',resource_background='global',
                    daily_picture_appearance_source='custom',daily_picture_material='clear',daily_picture_content_mode='auto',
                    resource_fold='pill',resource_collapsed=True,resource_face=True,resource_clock=True,resource_clock_format='seconds',
                    resource_layer='bottom',resource_compact_metrics=['cpu','memory','traffic']):
        with patch('component_contrast.wallpaper_samples',side_effect=sample):
            pixels=(QColor('#391781').getRgb()[:3],)*256
            daily=DailyPictureCard(runtime)
            window=service.window
            old_fold=service.auto_compact
            was_collapsed=panel.collapsed
            files=[dict(name=name,path=str(ASSETS/'pictures'/f'{key}.jpg')) for name,key in
                   [('雪里山茶.jpg','winter-2'),('春日溪桥.jpg','spring-1'),('端午龙舟.jpg','festivals-a-4'),
                    ('秋山远眺.jpg','autumn-1'),('小满麦田.jpg','summer-2'),('元宵灯市.jpg','festivals-a-2')]]
            owned=window is None
            if owned:window=ResourceWindow(service)
            service.auto_compact=None
            try:
                daily.sync();daily.content.next_fetch=float('inf')
                daily.content.items=[dict(title='霜雪间的朱果',credit='节气插画 · 小雪',published='20261127',story='https://dailybing.com/bing/zh-cn/20261127.html',original='demo')]*8
                daily.content.set_picture(QImage(str(ASSETS/'pictures'/'winter-2.jpg')))
                daily.content.update_controls();daily.fit_height()
                panel.set_collapsed_geometry(False)
                panel.refresh_content_style();window.sync_window();window.show()
                app=QApplication.instance();app.processEvents()
                for name,pair in backgrounds.items():
                    pixels=tuple(QColor(pair[int(x >= (4 if name=='mixed' else 8))]).getRgb()[:3]
                                 for y in range(16) for x in range(16))
                    for widget in (panel,window,daily):
                        widget._content_contrast.refresh()
                        light=widget._content_contrast.result
                        assert light==(name in ('blue','light')), (name,type(widget).__name__,light)
                    if name=='mixed':
                        compact_materials(window)
                        for x,ground in ((0,pixels[0]),(panel.width()-20,pixels[15])):
                            for muted in (False,True):
                                color=panel.text_ink_at(panel,QRect(x,0,16,18),muted)
                                assert contrast(ground,color)>=4.5
                        with patch.object(panel.manager,'rows',return_value=files):
                            panel.set_collapsed_geometry(False);panel.resize(550,241)
                            panel.render();panel.layout().activate();panel.list.doItemsLayout()
                            assert panel.list.isVisible() and panel.list.count()==len(files) and panel.width()>300
                            panel.refresh_content_style()
                            picture(panel,'files-mixed')
                            from fold_options import settings as fold_settings
                            with patch('fold_options.settings',return_value=dict(fold_settings(panel),style='bar')):
                                panel.set_collapsed_geometry(True)
                                panel.layout().activate();panel.refresh_content_style()
                                assert panel.title.isVisible() and panel.height()<60
                                picture(panel,'files-folded')
                            panel.set_collapsed_geometry(False)
                    if name=='purple':
                        assert all(button.property('iconInk')=='#ffffff' for button in daily.content.picture_icons)
                        assert daily.content.title.isVisible() and daily.content.credit.isVisible() and '11/27' in daily.content.position.text()
                        picture(daily,'photo-purple')
                    if name in ('purple','blue'):
                        from types import SimpleNamespace
                        from capsule_indicators import Indicators
                        indicator=Indicators(service)
                        indicator.selected=('volume','bluetooth_link')
                        indicator.values={'volume':(45,False),'bluetooth_link':(('buds','耳机'),)}
                        readings=[('ai','Codex','33%',dict(provider={'id':'Codex'},reading=SimpleNamespace(remaining=33,stale=False,daily=None))),
                                  ('traffic','本年流量','382.46 GB','')]
                        left=['ai','alert_almanac','traffic']
                        right=['battery','clock','volume','device_bluetooth_link']
                        with patch('resource_compact.compact_values',return_value=readings), \
                             patch('resource_compact.compact_badges',return_value=([('almanac','大雪10天'),('agenda','周五例会')],0)), \
                             patch('resource_compact.almanac_badge_lines',return_value={'大雪10天':('大雪','10天')}), \
                             patch('resource_compact.status_values',return_value=[('battery','电量','68%',(68,'charging'))]), \
                             patch.object(service,'indicators',indicator),patch.object(service,'window',window), \
                             patch.dict(cfg,resource_compact_order=left+['agenda']+right,resource_face=False,
                                        resource_compact_zones={**dict.fromkeys(left,'left'),'agenda':'center',**dict.fromkeys(right,'right')}):
                            window.resize(540,32);window._compact_cache=window._compact_surface=None
                            picture(window,'capsule-'+name)
                        indicator.deleteLater()
                for mode,light in [('light',True),('dark',False),('app',True)]:
                    cfg.update({key+'_content_mode':mode for key in ('panel','resource','daily_picture')})
                    daily.sync();window.sync_palette();panel.refresh_content_style()
                    assert all(w._content_contrast.result==light for w in (panel,window,daily))
                cfg['theme']='dark'
                daily.sync();window.sync_palette();panel.refresh_content_style()
                assert all(not w._content_contrast.result for w in (panel,window,daily))
                for dialog,field in ((PanelOptions(panel),'content_mode'),
                                     (ComponentPreferences(runtime,'daily_picture',1),'daily_picture_content_mode'),
                                     (ResourceOptions(service),'resource_content_mode')):
                    if field=='resource_content_mode':dialog.tabs.setCurrentIndex(4)
                    control=dialog.fields[field]
                    assert control.isEnabled() and [control.itemData(i) for i in range(control.count())]==[v for _,v in CONTENT_MODES]
                    dialog.close();dialog.deleteLater()
            finally:
                service.auto_compact=old_fold
                panel.set_collapsed_geometry(was_collapsed)
                if owned:window.close();window.deleteLater()
                daily.close();daily.deleteLater()
    panel.apply_options()
    if not owned:window.sync_window()
    checks.append('Desktop collection, folded capsule and daily picture render adaptive controls on purple, blue, light and split wallpapers; checked local foreground contrast for plain filenames, both manual modes, Dock theme changes and all three settings entry points.')
