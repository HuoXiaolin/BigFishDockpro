"""Round-trip custom quick presets and native-resolution glass preparation."""
import copy
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRectF,QSize
from PyQt5.QtGui import QImage,QPixmap,QPainter,QPainterPath,QColor,QLinearGradient
from quick_cycles import next_cycle,normalize_custom,APPEARANCE_FIELDS
from appearance_presets import DOCK_PRESETS


def run(api,runtime,root,output,checks):
    base=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
    base.update(theme='light',dock_material='liquid',theme_color='#9acbd9',transparency=79,blur_px=9,dock_highlight=31,icon_size=53,position='custom',custom_bottom=137)
    custom={key:base[key] for key in APPEARANCE_FIELDS}
    for key,rounds,fields in [('appearance',len(DOCK_PRESETS)+1,APPEARANCE_FIELDS),('size',5,('icon_size',)),('position',3,('position','custom_bottom'))]:
        cfg=copy.deepcopy(base);original={field:cfg[field] for field in fields};before_other=cfg['dock_quick_order'][:]
        for turn in range(rounds):
            cfg.update(next_cycle(cfg,key))
            cfg=api.normalize_features(copy.deepcopy(cfg))  # JSON/profile reload boundary.
        assert {field:cfg[field] for field in fields}==original,(key,cfg)
        assert cfg['dock_quick_order']==before_other
        if key=='appearance':assert cfg['dock_quick_custom']['appearance']==custom
    cfg=copy.deepcopy(base);cfg.update(next_cycle(cfg,'appearance'));cfg['magnify']=False
    for _ in range(len(DOCK_PRESETS)):cfg.update(next_cycle(cfg,'appearance'))
    assert not cfg['magnify'] and all(cfg[field]==value for field,value in custom.items())
    # A new manual custom value supersedes the previous one.
    cfg['icon_size']=57;cfg.update(next_cycle(cfg,'size'));assert cfg['dock_quick_custom']['size']['icon_size']==57
    cfg.update(position='top',custom_bottom=333);cfg.update(next_cycle(cfg,'position'));assert cfg['position']=='custom' and cfg['custom_bottom']==333
    assert normalize_custom({'size':{'icon_size':999},'position':{'custom_bottom':-1},'appearance':dict(custom,dock_material=[])})=={}
    from wallpaper_source import image_file,MAX_WALLPAPER_PIXELS
    directory=Path(root)/'glass-quality';directory.mkdir()
    path=directory/'native-stripes.png';image=QImage(2048,128,QImage.Format_RGB32);image.fill(Qt.white)
    p=QPainter(image);p.setPen(QColor('black'))
    for x in range(0,2048,2):p.drawLine(x,0,x,127)
    p.end();image.save(str(path));image_file.cache_clear()
    native=image_file(str(path),path.stat().st_mtime_ns)
    assert native.size()==image.size() and abs(native.pixelColor(1000,64).red()-native.pixelColor(1001,64).red())>250
    assert image_file.cache_info().maxsize==1
    import wallpaper_source as wallpaper
    image_file.cache_clear()
    with patch.object(wallpaper,'MAX_WALLPAPER_PIXELS',20000):
        bounded=image_file(str(path),path.stat().st_mtime_ns);assert bounded.width()*bounded.height()<=20000
    image_file.cache_clear()
    from glass_capture import smooth_backdrop
    from card_design import paint_design
    from desktop_clock import draw_clock
    for ratio in (1,1.25,1.5,2):
        width,height=round(180*ratio),round(80*ratio)
        pm=QPixmap(width,height);pm.fill(Qt.black);p=QPainter(pm);p.fillRect(width//2,0,width-width//2,height,Qt.white);p.end();pm.setDevicePixelRatio(ratio)
        blurred=smooth_backdrop(pm,6)
        assert blurred.size()==pm.size() and blurred.devicePixelRatio()==ratio
        result=blurred.toImage();line=[result.pixelColor(x,height//2).red() for x in range(width)]
        assert line[0]<3 and line[-1]>250 and max(abs(a-b) for a,b in zip(line,line[1:]))<90,(ratio,line)
        assert result.pixelColor(0,0).alpha()>245 and result.pixelColor(width-1,height-1).alpha()>245
        blurred.save(str(output/('glass-native-blur-'+str(ratio)+'.png')))
        # Draw fractional-DPR rounded outlines, without clipping off half a stroke.
        frame=QImage(round(320*ratio),round(160*ratio),QImage.Format_ARGB32_Premultiplied);frame.setDevicePixelRatio(ratio);frame.fill(Qt.transparent)
        p=QPainter(frame);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.SmoothPixmapTransform)
        paint_design(p,QRectF(1,1,318,158),runtime.dock.cfg,'aurora',body_top=159,corner_radius=22)
        p.end();assert frame.pixelColor(0,0).alpha()==0 and any(0<frame.pixelColor(x,y).alpha()<255 for x in range(round(25*ratio)) for y in range(round(25*ratio)))
        preview=QImage(frame.size(),QImage.Format_ARGB32_Premultiplied);preview.setDevicePixelRatio(ratio);preview.fill(QColor('#287dd4'))
        p=QPainter(preview);p.drawImage(0,0,frame);p.end();preview.save(str(output/('glass-edge-'+str(ratio)+'.png')))

        # Clocks/calendar share the same native-pixel source path.
        options=dict(runtime.dock.cfg['clock_appearance'],theme='light',opacity=0,highlight=36,material='liquid',text_color='#ffffff',text_effect='clear')
        canvas=QImage(round(420*ratio),round(210*ratio),QImage.Format_ARGB32_Premultiplied);canvas.setDevicePixelRatio(ratio);canvas.fill(QColor('#287dd4'))
        p=QPainter(canvas);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.SmoothPixmapTransform)
        draw_clock(p,QRectF(1,1,418,208),runtime.dock,options,'analog',QPixmap.fromImage(canvas));p.end();canvas.save(str(output/('glass-clock-'+str(ratio)+'.png')))
    checks.append('custom cycles: appearance/custom53px/custom offset round-trip through profile normalization, updated manual values and unrelated options preserved; malformed snapshots rejected. Glass: native 2048px one-pixel wallpaper detail retained, shared decode budget and single-entry cache, smooth full-size blur/opaque edges at 100/125/150/200 percent; fractional-DPR rounded edges and clocks rendered; no physical monitor switching')
