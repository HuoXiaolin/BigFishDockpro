"""Crisp tab slide and far-right category click regressions."""
import copy
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QEvent,QPoint,QPointF
from PyQt5.QtGui import QMouseEvent,QPixmap,QColor
from PyQt5.QtWidgets import QApplication,QToolButton


def run(api,runtime,root,output,checks):
    from desktop_panels import DesktopPanels
    from desktop_catalog import CATEGORIES
    from desktop_panel_tests import wait_for
    from ui_test_events import Events, check_edge_resize
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
            assert pager.parentWidget() is panel.notice.parentWidget() is panel.list
            assert abs(pager.geometry().center().x() - panel.list.rect().center().x()) <= 1
            assert not pager.geometry().intersects(panel.notice.geometry())
            assert panel.content.layout().indexOf(pager) == panel.content.layout().indexOf(panel.notice) == -1
            assert panel.list.viewport().geometry()==panel.list.rect()
            assert pager.geometry().bottom()==panel.list.rect().bottom()
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
        checks.append('Collection navigation: unoutlined text, transparent controls and a mouse-transparent hint in the full-height list viewport, no footer allocation; click and wheel wrap through pages.')
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
        files=[]
        for index in range(24):
            path=Path(root)/f'edge-test-{index}.txt'
            path.write_text('list scroll fixture',encoding='utf-8')
            files.append(str(path))
        assert manager.add_paths('other',files)
        panel.list.doItemsLayout()
        scroll=panel.list.verticalScrollBar()
        assert scroll.maximum()>0 and not scroll.isVisible() and not panel.list.horizontalScrollBar().isVisible()
        scroll.setValue(0)
        assert not panel.notice.has_room()
        assert Events.wheel(panel.list.viewport(),-120)
        assert scroll.value()>0
        from PyQt5.QtWidgets import QSizeGrip
        assert not panel.findChildren(QSizeGrip)
        check_edge_resize(panel)
        assert panel.bounds()==list(panel.geometry().getRect())
        assert panel.list.verticalScrollBarPolicy()==Qt.ScrollBarAlwaysOff
        assert panel.grab().save(str(Path(output)/'collection-dense.png'))
        checks.append('Collection edges: all four sides and four corners resize at the native widget margin, merged geometry persists, wheel scroll works while both rails and the resize grip are absent.')
        from PyQt5.QtWidgets import QAbstractItemView
        for mode in ('small','large'):
            assert manager.update_panel('other',view=mode)
            for width in (430,590):
                panel.resize(width,300);app.processEvents();panel.fit_content()
                view=panel.list
                rows={}
                for index in range(view.count()):
                    rect=view.visualItemRect(view.item(index))
                    rows.setdefault(rect.top(),[]).append(rect)
                assert len(rows)>1
                for row in rows.values():
                    assert abs(row[0].left()-(view.viewport().width()-1-row[-1].right()))<=1, (mode,width,row)
                item=view.item(view.count()-1)
                view.scrollToItem(item,QAbstractItemView.EnsureVisible)
                spot=view.visualItemRect(item).center()
                assert view.viewport().rect().contains(spot) and view.itemAt(spot) is item
                Events.drag(view.viewport(),spot,QPoint())
                assert view.currentItem() is item and item.isSelected()
        assert manager.update_panel('other',view='list')
        app.processEvents();assert panel.list.visualItemRect(panel.list.item(0)).left()==0
        assert manager.update_panel('other',view='small')
        manager.status('');panel.list.verticalScrollBar().setValue(0);app.processEvents()
        assert panel.grab().save(str(Path(output)/'collection-centered.png'))
        checks.append('Collection grid: full and short rows centered at two widths in small and large icon modes, item click targets follow the icons, list mode remains aligned to the left.')

        from glass_panel import PanelOptions
        with patch.object(manager,'manage_groups') as groups, patch.object(runtime,'open_card_sizing') as sizing:
            options=PanelOptions(panel)
            options.show();app.processEvents()
            try:
                bounds=panel.geometry();before=copy.deepcopy(cfg['card_sizing'])
                options.fields['appearance_source'].setCurrentIndex(options.fields['appearance_source'].findData('app'))
                assert options.text_size.isEnabled()
                options.text_size.setValue(23)
                options.groups_button.click();groups.assert_called_once()
                options.sizing_button.click();sizing.assert_called_once_with('panel','other')
                assert options.text_size.value()==23
                assert options.commit()
                assert cfg['card_sizing']==dict(before,font_size=23)
                assert api.load_config()['card_sizing']==cfg['card_sizing']
                assert panel.geometry()==bounds and panel.text_pixels()>12
                assert options.grab().save(str(Path(output)/'collection-management-settings.png'))
            finally:
                options.reject();options.deleteLater()
        checks.append('Collection appearance: shared font field saves with Follow Dock enabled, dimensions are preserved, and both existing management dialogs are reachable.')
    finally:
        if manager:manager.close()
        cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings()
