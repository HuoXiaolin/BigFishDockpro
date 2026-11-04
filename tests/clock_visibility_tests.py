"""Regression cases for the actual clock painter, not theme-name assertions."""
import copy
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QColor,QPixmap,QPainter
from clock_appearance import normalize,PRESETS,STYLES
from clock_legibility import contrast,readable,_surfaces,clear_cache

def run(dock,render,output,checks):
    # White-on-white and dark-on-dark must be corrected even for clear material.
    for bg,expected in [('light','dark'),('dark','light')]:
        sheet=QPixmap(1320,1404);sheet.setDevicePixelRatio(1.5);sheet.fill(QColor('#edf3f8'));p=QPainter(sheet)
        for i,(name,style) in enumerate(STYLES):
            audit=[];options=normalize(dict(PRESETS[-1][1],text_color='#ffffff' if bg=='light' else '#132b40'))
            options['_text_audit']=audit
            image=render(420,260,options,style,bg);p.drawPixmap(12+(i%2)*438,24+(i//2)*306,image)
            visible=[QColor(c) for _,_,c,alpha,_ in audit if alpha>=200]
            assert visible and all((color.lightness()<150)==(expected=='dark') for color in visible),(style,bg,audit)
            background=QColor('#f3f7fb' if bg=='light' else '#15283d')
            assert min(contrast(c,background) for c in visible)>=4.5,(style,bg)
        p.end();sheet.save(str(output/('transparent-'+bg+'.png')))
    # Keep one text polarity on a colored wallpaper, including dates and progress.
    for _,style in STYLES:
        audit=[];options=normalize(PRESETS[-1][1]);options['_text_audit']=audit
        render(420,260,options,style)
        assert len({QColor(color).lightness()>150 for _,_,color,alpha,_ in audit if alpha>=200})==1,(style,audit)
    checks.append('six faces: transparent light/dark wallpaper corrects unreadable custom colors; primary and secondary ink >=4.5 contrast on uniform backgrounds; coherent ink on blue wallpaper')
    # Composition must include material opacity, not only the original wallpaper.
    for _,preset in PRESETS:
        for _,style in STYLES:
            for w,h,ratio in [(180,120,1.0),(420,260,1.5),(560,340,2.0)]:
                audit=[];options=normalize(preset);options['_text_audit']=audit
                render(w,h,options,style,'light',ratio)
                assert audit
                for value,size,color,alpha,(x,y,tw,th) in audit:
                    assert x>=-1 and y>=-1 and x+tw<=w+1 and y+th<=h+1,(style,(w,h),value,(x,y,tw,th))
    checks.append('all five presets and six faces at compact/normal/large sizes and 100/150/200% DPR; actual text bounds stay inside the component')
    # Disabling auto contrast preserves explicit colors and text alpha.
    audit=[];options=normalize(dict(PRESETS[-1][1],auto_contrast=False,text_color='#ff4444',text_opacity=55));options['_text_audit']=audit
    render(420,260,options,'digital','light')
    time=next(row for row in audit if row[0]=='16:24');assert time[2]=='#ff4444' and time[3]==140
    # Accent and font controls remain usable; no new background timer is involved.
    for effect in ('clear','glass'):
        options=normalize(dict(PRESETS[0][1],text_effect=effect,font_weight=75,font_scale=140,date_scale=125))
        render(560,340,options,'orbit').save(str(output/('orbit-'+effect+'.png')))
    checks.append('manual contrast-off respects custom color/opacity; clear and glass lettering, larger fonts and work progress render without outlines')
    assert len(_surfaces)<=4 and sum(im.sizeInBytes() for im in _surfaces.values())<=96*64*4*4
    clear_cache();assert not _surfaces
    checks.append('contrast analysis cache capped at four tiny images (96 KiB); cache release verified')
    from types import SimpleNamespace
    from unittest.mock import patch
    from desktop_clock import DesktopClock
    options=normalize(PRESETS[-1][1]);source=QPixmap(1000,600);source.fill(QColor('#f3f7fb'))
    window=SimpleNamespace(option=lambda name:options,dock=SimpleNamespace(preview=False),backdrop=None,isVisible=lambda:True,update=lambda:None)
    with patch('glass_capture.backdrop_key',return_value=('fixture',)),patch('glass_capture.capture_behind',return_value=source) as capture,patch('glass_capture.surface_windows',return_value=()),patch('glass_capture.smooth_backdrop') as blur:
        DesktopClock.capture_backdrop(window);assert window.backdrop.size().width()==96 and window.backdrop.height()==64
        DesktopClock.capture_backdrop(window);assert capture.call_count==1 and not blur.called
    checks.append('transparent clear text retains only a 96x64 wallpaper sample, unchanged capture reuses cache and avoids blur')
