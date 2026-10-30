"""Verify actual popup alpha and interaction on a private Windows desktop."""
import sys,json
from pathlib import Path

def run(output):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from PyQt5.QtCore import Qt,QPoint
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtTest import QTest
    from ui_style import AlignedMenu,apply_theme,shutdown_ui
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    checks=[]
    try:
        for light in (True,False):
            apply_theme(app,light)
            menu=AlignedMenu()
            menu.addAction('打开应用')
            submenu=menu.addMenu('Dock 布局');submenu.addAction('底部')
            menu.addSeparator()
            action=menu.addAction('设置…');triggered=[]
            action.triggered.connect(lambda:triggered.append(True))
            menu.popup(QPoint(100,100))
            for _ in range(4):app.processEvents()
            for popup in (menu,submenu):
                if popup is submenu:
                    popup.popup(QPoint(400,100))
                    for _ in range(4):app.processEvents()
                image=popup.grab().toImage()
                w,h=image.width(),image.height()
                assert all(image.pixelColor(x,y).alpha()==0 for x,y in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)])
                assert image.pixelColor(w//2,h//2).alpha()==255
                assert popup.windowFlags() & Qt.FramelessWindowHint
                image.save(str(output/('light' if light else 'dark'))+('-submenu.png' if popup is submenu else '-menu.png'))
                if popup is submenu:popup.hide()
            QTest.mouseClick(menu,Qt.LeftButton,pos=menu.actionGeometry(action).center())
            assert triggered and not menu.isVisible()
            menu.deleteLater();app.processEvents()
            checks.append(('light' if light else 'dark')+': menu/submenu transparent corners, opaque surface, click dispatch')
        (output/'result.json').write_text(json.dumps(dict(passed=True,checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
    finally:shutdown_ui(app)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    for folder in ('app','tools'):sys.path.insert(0,str(root/folder))
    run(sys.argv[-1])
