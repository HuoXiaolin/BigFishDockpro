from pathlib import Path
import sys,copy,datetime,json,time,traceback
actual=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(actual/name) for name in ('app','tests','tools')]
from run_isolated_test import assert_isolated
assert_isolated()
import dock as api
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QPainter,QPixmap,QColor,QFont,QLinearGradient
from clock_appearance import normalize,PRESETS,STYLES
from desktop_clock import draw_clock

class Palette:
    cfg={'theme':'light','card_design':'aurora','theme_color':'#b8d9ef'}
    _sys_light=True
    base_theme_colors=api.Dock.base_theme_colors
    merged_grad_stops=api.Dock.merged_grad_stops
    _stop_alpha=staticmethod(api.Dock._stop_alpha)

def backdrop(width,height,kind='blue',dpr=1.5):
    pix=QPixmap(round(width*dpr),round(height*dpr));pix.setDevicePixelRatio(dpr)
    pix.fill(QColor({'light':'#f3f7fb','dark':'#15283d','blue':'#1b8edb'}.get(kind,'#1b8edb')))
    if kind=='blue':
        p=QPainter(pix);g=QLinearGradient(0,0,width,height);g.setColorAt(0,QColor('#27ace3'));g.setColorAt(.55,QColor('#2975d4'));g.setColorAt(1,QColor('#7457bf'));p.fillRect(QRectF(0,0,width,height),g);p.end()
    return pix

def render(width,height,options,style,bg='blue',dpr=1.5):
    wallpaper=backdrop(width,height,bg,dpr);image=QPixmap(wallpaper)
    p=QPainter(image);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.SmoothPixmapTransform)
    draw_clock(p,QRectF(0,0,width,height),Palette(),dict(options,_now=datetime.datetime(2026,11,4,16,24),_header_controls=True),style,wallpaper)
    p.end();return image

def main():
    app=QApplication([]);root=Path(sys.argv[-1]);root.mkdir(exist_ok=True,parents=True);start=time.perf_counter()
    for n,(name,preset) in enumerate(PRESETS):
        sheet=QPixmap(1320,1404);sheet.setDevicePixelRatio(1.5);sheet.fill(QColor('#edf3f8'));p=QPainter(sheet);p.setRenderHint(QPainter.SmoothPixmapTransform);p.setFont(QFont('Microsoft YaHei UI',11))
        for i,(title,style) in enumerate(STYLES):
            x=12+(i%2)*438;y=42+(i//2)*306;p.setPen(QColor('#1a354b'));p.drawText(x,y-12,name+' · '+title)
            tile=render(420,260,normalize(preset),style);p.drawPixmap(QRectF(x,y,420,260),tile,QRectF(0,0,tile.width(),tile.height()))
        p.end();sheet.save(str(root/('theme-%d.png'%n)))
    results={'passed':True,'checks':['all six faces rendered across all five theme presets, using simulated blue wallpaper'],'seconds':round(time.perf_counter()-start,2)}
    if (actual/'tests'/'clock_visibility_tests.py').exists():
        from clock_visibility_tests import run
        run(Palette(),render,root,results['checks'])
    from taskbar_text_tests import run as check_taskbar_text
    check_taskbar_text(root,results['checks'])
    results['seconds']=round(time.perf_counter()-start,2);(root/'result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()


