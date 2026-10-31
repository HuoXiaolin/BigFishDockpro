"""Render native quick-settings tooltips without touching the input desktop."""
import sys,json,copy
from pathlib import Path

def run(output):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from PyQt5.QtCore import QPoint,Qt
    from PyQt5.QtWidgets import QApplication,QWidget,QToolTip
    from PyQt5.QtTest import QTest
    from ui_style import apply_theme,shutdown_ui
    from dock_extras import DockQuickSettings
    from dock import DEFAULT_CONFIG
    from types import SimpleNamespace
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    checks=[]
    try:
        for light in (True,False):
            apply_theme(app,light)
            dock=QWidget();dock.cfg=copy.deepcopy(DEFAULT_CONFIG);dock.tray=SimpleNamespace(runtime=None)
            dock.is_light=lambda:light
            popup=DockQuickSettings(SimpleNamespace(dock=dock));popup.refresh();popup.move(60,60);popup.show()
            for _ in range(4):app.processEvents()
            for key in ('appearance','size','position'):
                tile=popup.tiles[key]
                QToolTip.showText(tile.mapToGlobal(QPoint(15,15)),tile.toolTip(),tile)
                QTest.qWait(250)
                for _ in range(4):app.processEvents()
                tip=next(w for w in app.topLevelWidgets() if w.windowType()==Qt.ToolTip and w.isVisible())
                assert 15<tip.height()<55, (key,tip.size())
                picture=tip.grab().toImage();paper=picture.pixelColor(5,picture.height()//2)
                assert paper.alpha()==255
                assert (paper.lightness()>200) if light else (paper.lightness()<75)
                assert tip.width()<600
                picture.save(str(out/(('light-' if light else 'dark-')+key+'.png')))
                QToolTip.hideText();QTest.qWait(350)
            popup.close();popup.deleteLater();dock.deleteLater();app.processEvents()
            checks.append(('light' if light else 'dark')+': all three tips use compact opaque themed background, no tile minimum height')
        (out/'result.json').write_text(json.dumps(dict(passed=True,checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
    finally:shutdown_ui(app)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    for folder in ('app','tools'):sys.path.insert(0,str(root/folder))
    run(sys.argv[-1])
