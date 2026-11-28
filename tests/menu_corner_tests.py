"""Verify actual popup alpha and interaction on a private Windows desktop."""
import sys,json
from pathlib import Path


def check_tray_rows(runtime, app, output, checks):
    from unittest.mock import patch
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent, QPoint, QTimer
    from PyQt5.QtGui import QColor, QImage, QPainter
    from PyQt5.QtWidgets import QDialog
    from desktop_panel_tests import wait_for
    from menu_paths import action_at
    from settings_interaction_tests import click_at

    screen = app.primaryScreen().availableGeometry()
    root = runtime.tray.menu
    points = (screen.topLeft() + QPoint(40, 45), screen.topRight() + QPoint(-3, 45))
    alive_in_dialog = []
    def open_modal(checked=False):
        dialog = QDialog()
        def inspect():
            alive_in_dialog.append(bool(root.actions()) and not sip.isdeleted(action) and not sip.isdeleted(parent))
            dialog.accept()
        QTimer.singleShot(10,inspect)
        dialog.exec_()
    with patch.object(runtime.productivity, 'open_layouts',side_effect=open_modal) as open_layouts:
        for index, anchor in enumerate(points):
            root.popup(anchor)
            app.processEvents()
            menus = [root]
            try:
                for title in ('Dock 与应用', '查找与整理', '桌面布局方案…'):
                    parent = menus[-1]
                    action = action_at(parent, title)
                    row = parent.actionGeometry(action)
                    left = QPoint(3, row.center().y()); right = QPoint(parent.width()-4, row.center().y())
                    assert parent.actionAt(left) is action and parent.actionAt(right) is action, (title, parent.width(), row)
                    assert row.height() >= parent.fontMetrics().height()+9
                    if action.menu():
                        click_at(parent, right if index==0 else left)
                        child = action.menu()
                        wait_for(app, child.isVisible)
                        parent_box, child_box = parent.frameGeometry(), child.frameGeometry()
                        assert screen.contains(child_box)
                        if index == 0: assert child_box.left() == parent_box.right()+1, (parent_box,child_box)
                        else: assert child_box.right()+1 == parent_box.left(), (parent_box,child_box)
                        menus.append(child)
                    else:
                        assert parent.width() <= parent.fontMetrics().horizontalAdvance(title)+52
                        if index:
                            bounds = menus[0].frameGeometry()
                            for popup in menus[1:]: bounds = bounds.united(popup.frameGeometry())
                            image = QImage(bounds.size(), QImage.Format_ARGB32_Premultiplied)
                            image.fill(QColor('#e5ebef')); painter = QPainter(image)
                            for popup in menus:
                                painter.drawPixmap(popup.pos()-bounds.topLeft(),popup.grab())
                            painter.end(); image.save(str(Path(output)/'tray-menu-cascade.png'))
                        click_at(parent, left if index==0 else right)
                        assert open_layouts.call_count == index+1 and not root.isVisible()
                        assert alive_in_dialog[-1]
                        wait_for(app,lambda:not root.actions())
                        app.sendPostedEvents(None,QEvent.DeferredDelete)
                        assert sip.isdeleted(action) and sip.isdeleted(parent)
            finally:
                root.close(); app.processEvents()
    checks.append('Tray context menu: left and right row edges open two nested menus and trigger the leaf; compact content widths and outward cascades at both screen edges')
    checks.append('Nested tray mouse release keeps its selected action and menus alive throughout a modal dialog, then frees the hidden tree after dispatch.')

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
