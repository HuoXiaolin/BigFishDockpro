"""Capture compatibility checks with synthetic pixels and fake Windows APIs."""
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtCore import QRect,Qt,QRectF
from PyQt5.QtGui import QPixmap,QColor,QImage,QPainter,QPainterPath,QLinearGradient
import glass_capture as capture


class Function:
    def __init__(self,call):self.call=call
    def __call__(self,*args):return self.call(*args)


def run(checks):
    bright=QPixmap(240,120);bright.fill(QColor('#d9eaff'));bright.setDevicePixelRatio(1.5)
    black=QPixmap(240,120);black.fill(QColor('#000000'))
    transparent=QPixmap(10,10);transparent.fill(QColor(255,255,255,0))
    dark=QPixmap(10,10);dark.fill(QColor('#101820'))
    assert capture.valid_backdrop(bright) and capture.valid_backdrop(dark)
    assert not capture.valid_backdrop(black) and not capture.valid_backdrop(transparent)
    assert not capture.valid_backdrop(QPixmap())
    from wallpaper_source import render
    from PyQt5.QtCore import QSize
    image=QImage(200,100,QImage.Format_ARGB32);p=QPainter(image);g=QLinearGradient(0,0,200,0);g.setColorAt(0,QColor('red'));g.setColorAt(1,QColor('blue'));p.fillRect(image.rect(),g);p.end()
    monitor=QRect(-1920,0,1920,1080);bounds=QRect(-1920,0,3840,1080);region=QRectF(-1000,100,160,80)
    for mode in range(6):
        result=render(image,mode,QColor('#d8eaff'),monitor,bounds,region,QSize(240,120));assert result.size()==QSize(240,120)
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        from pathlib import Path
        path=Path(directory)/'wallpaper.png';image.save(str(path))
        import wallpaper_source as source
        source._metadata.clear()
        screen=SimpleNamespace(name=lambda:'wallpaper-test',geometry=lambda:monitor,grabWindow=lambda *args:(_ for _ in ()).throw(AssertionError('Foreground capture forbidden')))
        window=SimpleNamespace(frameGeometry=lambda:QRect(-1850,20,160,80),devicePixelRatioF=lambda:1.5)
        with patch.object(capture.QApplication,'screenAt',return_value=screen),patch.object(source,'desktop_wallpaper',return_value=(str(path),2,QColor('white'),monitor,bounds)):
            result=capture.capture_behind(window,[]);assert result is not None and result.devicePixelRatio()==1.5 and result.width()==240
        from card_file_ui import picture_thumbnail
        thumb=picture_thumbnail(str(path),54);assert thumb is not None and thumb.size()==QSize(54,54)
        assert thumb.toImage().pixelColor(27,27).alpha()>0 and thumb.toImage().pixelColor(27,0).alpha()==0
        path.write_text('invalid image',encoding='utf-8');assert picture_thumbnail(str(path),54) is None
    checks.append('wallpaper-only material source: six Windows positioning modes, negative monitor origin, spanning bounds and 150% DPR crop; foreground grab forbidden; bounded image thumbnail with preserved aspect and invalid-image fallback')
    from PyQt5.QtWidgets import QApplication
    native_window=next(widget for widget in QApplication.topLevelWidgets() if widget.__class__.__name__=='Dock')
    metadata=source.desktop_wallpaper(native_window)
    assert len(metadata)==5 and not metadata[3].isEmpty()
    checks.append('native Windows wallpaper interface read on isolated desktop: monitor, image path, fit mode and desktop color returned without displaying or capturing foreground applications')
    # Explicit source rectangles are in physical pixels, not logical Qt units.
    # A half-width sample of a 200%-DPR gradient gives 64 instead of 128.
    from liquid_glass import paint_liquid_glass
    for ratio in (1,1.5,2):
        pm=QPixmap(round(100*ratio),round(50*ratio));p=QPainter(pm)
        gradient=QLinearGradient(0,0,pm.width(),0);gradient.setColorAt(0,QColor(0,0,0));gradient.setColorAt(1,QColor(255,255,255));p.fillRect(pm.rect(),gradient);p.end();pm.setDevicePixelRatio(ratio)
        target=QImage(100,50,QImage.Format_ARGB32);target.fill(Qt.transparent)
        painter=QPainter(target);rect=QRectF(0,0,100,50);path=QPainterPath();path.addRect(rect)
        surface=SimpleNamespace(cfg={'glass':True,'dock_material':'liquid'},backdrop=pm,spec_alpha=0,spec_x=0)
        colors={'tint':QColor('white'),'border':QColor(0,0,0,0)}
        paint_liquid_glass(surface,painter,path,rect,rect,colors,0,[(0,0),(1,0)]);painter.end()
        assert 124<=target.pixelColor(50,25).red()<=132,(ratio,target.pixelColor(50,25).red())
        assert target.pixelColor(90,25).red()>225,(ratio,target.pixelColor(90,25).red())
    checks.append('glass DPR drawing: full gradient extent and midpoint preserved at 100/150/200 percent instead of sampling only the top-left fraction')

