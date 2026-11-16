"""Crisp tab slide and far-right category click regressions."""
import copy
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QEvent,QPointF
from PyQt5.QtGui import QMouseEvent,QPixmap,QColor
from PyQt5.QtWidgets import QApplication,QToolButton


def run(api,runtime,root,output,checks):
    from desktop_panels import DesktopPanels
    from desktop_catalog import CATEGORIES
    from desktop_panel_tests import wait_for
    from ui_test_events import Events
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    previous=runtime.panels;roots=list(previous.roots);previous.close();manager=None
    try:
        cfg.update(panel_enabled=True,panels_visible=True,panel_auto_hide=False,panel_locked=False,
                   merged_panels=False,merge_initialized=False,merge_groups=[],merged_active='',merged_geometry=[],merged_collapsed=False,
                   desktop_auto_sort=False,desktop_entries=[],desktop_excluded=[],disabled_categories=[],display_layout={},
                   desktop_panels=[{'id':key,'name':name,'geometry':[90,90,760,300]} for key,name in CATEGORIES])
        cfg.update(api.normalize_features(cfg));assert api.save_config(cfg)
        manager=runtime.panels=DesktopPanels(runtime,roots=[]);manager.apply_settings();manager.set_merged('apps',True);app.processEvents()
        for width in (760,430):
            manager.select_page('apps');panel=manager.windows['apps'];panel.page_transition.cancel()
            panel.resize(width,300);app.processEvents();panel.layout().activate()
            last=next(i for i in range(panel.tabs.count()) if panel.tabs.tabData(i)=='other')
            # Reveal the far-right tab using the real overflow button.
            for _ in range(30):
                arrows=[b for b in panel.tabs.findChildren(QToolButton) if b.isVisible()]
                right=min((b.x() for b in arrows),default=panel.tabs.width())
                rect=panel.tabs.tabRect(last)
                if rect.left()>=0 and rect.right()<right:break
                if not arrows:break
                max(arrows,key=lambda b:b.x()).click();app.processEvents()
            rect=panel.tabs.tabRect(last);point=rect.center()
            assert panel.tabs.rect().contains(point),rect
            before=[panel.tabs.tabRect(i) for i in range(panel.tabs.count())];geometry=panel.geometry();handle=int(panel.winId())
            QApplication.sendEvent(panel.tabs,QMouseEvent(QEvent.MouseButtonPress,QPointF(point),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier));app.processEvents()
            QApplication.sendEvent(panel.tabs,QMouseEvent(QEvent.MouseButtonRelease,QPointF(point),Qt.LeftButton,Qt.NoButton,Qt.NoModifier));app.processEvents()
            assert manager.windows['other'] is panel and panel.identity=='other'
            assert panel.geometry()==geometry and int(panel.winId())==handle
            assert before==[panel.tabs.tabRect(i) for i in range(panel.tabs.count())],(width,before,[panel.tabs.tabRect(i) for i in range(panel.tabs.count())])
            wait_for(app,lambda:panel.page_transition.frame is None)
            panel.grab().save(str(Path(output)/('other-tab-stable-%d.png'%width)))
            pager = panel.page_pager
            assert (pager.width(), pager.height()) == (110, 20)
            assert pager.previous.text() == pager.next.text() == '' and not pager.previous.icon().isNull()
            assert pager.isVisible() and pager.name.text() == panel.model['name']
            assert abs(pager.geometry().center().x() - panel.content.rect().center().x()) <= 1
            assert not pager.geometry().intersects(panel.notice.geometry())
            assert panel.content.layout().indexOf(pager) == panel.content.layout().indexOf(panel.notice) == -1
            assert panel.list.geometry().bottom() == pager.geometry().bottom()
            app.sendEvent(pager, QEvent(QEvent.Leave))
            assert pager.visibility_effect.opacity() == 0 and panel.notice.isVisible()
            app.sendEvent(pager, QEvent(QEvent.Enter))
            assert pager.visibility_effect.opacity() == 1
            pager.next.click()
            assert panel.identity == 'apps' and pager.name.text() == panel.model['name']
            assert Events.wheel(pager.name, 120) and panel.identity == 'other'
            pager.previous.click()
            assert panel.identity == 'archives'
            assert Events.wheel(pager.next, -120) and manager.windows['other'] is panel
            assert panel.geometry()==geometry and int(panel.winId())==handle
            wait_for(app,lambda:panel.page_transition.frame is None)
            assert panel.grab().save(str(Path(output)/('collection-footer-pager-%d.png'%width)))
            app.sendEvent(pager, QEvent(QEvent.Leave))
            assert pager.visibility_effect.opacity() == 0 and panel.notice.isVisible()
        checks.append('Collection floating page navigation: transparent, shown on pointer entry and hidden on exit; no layout row; drop hint remains; click and wheel wrap through pages.')
        transition=panel.page_transition;size=panel.list.viewport().size();ratio=panel.list.viewport().devicePixelRatioF()
        front=QPixmap(round(size.width()*ratio),round(size.height()*ratio));front.setDevicePixelRatio(ratio);front.fill(QColor('#d53d4b'))
        back=QPixmap(front.size());back.setDevicePixelRatio(ratio);back.fill(QColor('#36aa79'))
        with patch.object(transition,'capture',return_value=back):transition.begin(front,1)
        transition.animation.pause();transition.advance(.5);app.processEvents()
        image=transition.grab().toImage();assert not panel.list.viewport().isVisible()
        assert image.pixelColor(image.width()//4,image.height()//2).name()=='#d53d4b'
        assert image.pixelColor(image.width()*3//4,image.height()//2).name()=='#36aa79'
        transition.cancel();assert transition.back is None and transition.frame is None and panel.list.viewport().isVisible()
        checks.append('tab slide: opaque one-to-one DPR snapshots, no crossfade/color blending, viewport restored and snapshots released; real mouse clicks on far-right Other preserve all tab rectangles, native window and geometry at wide/overflow sizes')
    finally:
        if manager:manager.close()
        cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings()
