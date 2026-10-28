"""Stable glass stays inside paths without extra compositor windows."""
import sys
from pathlib import Path
from types import SimpleNamespace
from PyQt5.QtCore import Qt,QRectF
from PyQt5.QtGui import QPainter,QPainterPath,QPixmap,QColor
from PyQt5.QtWidgets import QApplication


def run(runtime,output,checks):
    from feature_config import normalize
    from liquid_glass import paint_liquid_glass
    assert 'realtime_glass' not in normalize({'realtime_glass':True})
    assert 'realtime_glass' not in runtime.dock.cfg
    assert 'live_glass' not in sys.modules
    assert not any(w.__class__.__name__=='GlassSurface' for w in QApplication.topLevelWidgets())
    before={id(w) for w in QApplication.topLevelWidgets()}
    for material in ('liquid','gloss','acrylic'):
        image=QPixmap(500,220);image.fill(Qt.transparent);painter=QPainter(image)
        backdrop=QPixmap(500,220);backdrop.fill(QColor('#9bcce8'))
        surface=SimpleNamespace(cfg={'glass':True,'clear_background':False,'dock_material':material},backdrop=backdrop,spec_x=150,spec_alpha=.2)
        colors=runtime.dock.base_theme_colors('light')
        for box in (QRectF(30,70,200,110),QRectF(265,70,200,110)):
            path=QPainterPath();path.addRoundedRect(box,18,18)
            paint_liquid_glass(surface,painter,path,box,box,colors,100,runtime.dock.merged_grad_stops(colors))
        painter.end();pixels=image.toImage()
        for x,y in ((0,0),(250,100),(40,20),(499,219)):assert pixels.pixelColor(x,y).alpha()==0,(material,x,y)
        assert pixels.pixelColor(100,100).alpha()>0
        image.save(str(Path(output)/('stable-glass-'+material+'.png')))
    assert before=={id(w) for w in QApplication.topLevelWidgets()}
    checks.append('live glass removed: enabled legacy field discarded, no compositor module or auxiliary GlassSurface windows; original liquid/gloss/acrylic glass stays within rounded segment paths and leaves animation margins/gaps transparent')
