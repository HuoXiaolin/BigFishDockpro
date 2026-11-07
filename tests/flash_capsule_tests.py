"""Flash capture, recovery and colour profiles on a private Windows desktop."""
import copy
import time
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt, QEvent, QPoint, QPointF, QMimeData, QUrl
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication, QToolButton


def key(widget,code,mods=Qt.NoModifier,text=''):
    for kind in (QEvent.KeyPress,QEvent.KeyRelease):
        QApplication.sendEvent(widget,QKeyEvent(kind,code,mods,text))


def drop(widget,mime):
    point=QPoint(8,8);actions=Qt.CopyAction|Qt.MoveAction
    enter=QDragEnterEvent(point,actions,mime,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(widget,enter)
    event=QDropEvent(QPointF(point),actions,mime,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(widget,event)
    return event.isAccepted() and event.dropAction()==Qt.CopyAction


def run(api,runtime,root,app,output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from appearance_profiles import selected_mode,switch_profile,snapshot
    from appearance_presets import VIVID_BLUE,VIVID_RED,VIVID_GREEN
    from flash_view import palette_for
    from dock_extras import DockQuickSettings
    from command_search import matches
    from config_transfer import export_configuration,read_configuration,normalize
    service=runtime.flash;cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    cfg.update(flash_enabled=False,flash_entries=[],flash_draft={},flash_palette='theme',flash_auto_hide=True,flash_drop=True,flash_side='right')
    old_game=runtime.game_active;runtime.game_active=False
    popup=None
    try:
        service.sync()
        assert service.edge is None and service.panel is None and service.reminder is None
        popup=DockQuickSettings(runtime.dock.extras);popup.refresh()
        tile = popup.tiles['flash']
        assert tile.value == '已关闭' and not tile.active
        tile.click();app.processEvents()
        assert cfg['flash_enabled'] and service.edge.isVisible() and service.panel is None
        assert tile.value == '已开启' and tile.active and api.load_config()['flash_enabled']
        tile.click()
        assert not cfg['flash_enabled'] and service.edge is None and not api.load_config()['flash_enabled']
        assert tile.value == '已关闭' and not tile.active
        with patch.object(api, 'save_config', return_value=False):
            tile.click()
        assert not cfg['flash_enabled'] and '失败' in popup.status.text()
        tile.click()
        service.open(compose=True)
        panel=service.panel;edge=service.edge
        assert cfg['flash_enabled'] and panel.editing and edge.isVisible()
        service.open(compose=True);assert service.panel is panel
        for _ in range(3):app.processEvents()
        assert panel.composer.isVisible() and not panel.browse.isVisible() and not panel.empty.isVisible() and not panel.status.isVisible()
        compact_height=panel.height()
        assert compact_height<150 and panel.composer.height()<=panel.composer.sizeHint().height()+1
        assert panel.grab().save(str(Path(output)/'flash-compose-fixed.png'))
        panel.editor.setPlainText('测试自动换行和草稿。'*90);app.processEvents()
        assert compact_height<panel.height()<220 and panel.editor.verticalScrollBar().maximum()>0
        panel.editor.clear();app.processEvents();assert panel.height()==compact_height
        panel.submit();app.processEvents();panel.input_region()
        status_center=panel.status.mapTo(panel,panel.status.rect().center())
        assert panel.status.isVisible() and panel.mask().contains(status_center)
        assert panel.status.height()>=panel.status.heightForWidth(panel.status.width())
        panel.hide_notice()
        panel.editor.insertPlainText('明天核对新版图标')
        key(panel.editor,Qt.Key_Return,Qt.ShiftModifier,'\r')
        panel.editor.insertPlainText('记得看小尺寸效果')
        key(panel.editor,Qt.Key_Return)
        row=cfg['flash_entries'][0];identity=row['id']
        assert '小尺寸效果' in row['text'] and '\n' in row['text'] and not cfg['flash_draft'] and not panel.editing
        item=panel.list.item(0);box=panel.list.itemDelegate().bubble(panel.list.visualItemRect(item),panel.list.fontMetrics(),item.text(),0)
        for kind,buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
            QApplication.sendEvent(panel.list.viewport(),QMouseEvent(kind,box.center(),Qt.LeftButton,buttons,Qt.NoModifier))
        assert panel.expanded==identity and panel.list.itemWidget(panel.list.item(0))
        panel.begin_edit(identity);panel.editor.setPlainText('保留这段还没写完的草稿')
        panel.fold_if_idle();assert service.panel is panel
        assert service.collapse() and service.panel is None
        service.open(compose=True);panel=service.panel
        assert panel.editor.toPlainText()==api.load_config()['flash_draft']['text']
        with patch.object(api,'save_config',return_value=False):
            panel.submit();assert panel.editing and service.item(identity)['text']==row['text']
        panel.submit();assert service.item(identity)['text']=='保留这段还没写完的草稿'
        note=QMimeData();note.setText('读完一章，记下一个问题')
        assert service.collapse() and drop(edge,note)
        file=QMimeData();file.setUrls([QUrl.fromLocalFile(str(Path(root)/'demo.txt'))])
        assert not drop(edge,file)
        cfg['flash_drop']=False;assert not drop(edge,note);cfg['flash_drop']=True
        service.open();panel=service.panel
        for _ in range(3):app.processEvents()
        assert panel.list.count()==2 and panel.list.verticalScrollBar().maximum()==0,'Two short notes must not create an extra scrollbar'
        panel.grab().save(str(Path(output)/'flash-two-notes-no-scrollbar.png'))
        assert drop(panel,note) and len(cfg['flash_entries'])==3
        service.modify(cfg['flash_entries'][1]['id'],text='下次散步带上相机')
        red=service.add('周五整理旅行照片','red');green=service.add('给阳台的薄荷浇水','green')
        service.modify(identity,pinned=True)
        panel.swatches['red'].click();assert set(panel.rows)=={red}
        panel.all_colors.click();panel.search.setText('薄荷');assert set(panel.rows)=={green}
        panel.search.clear();panel.reveal_item(red)
        with patch.object(panel,'menu_choice',return_value='short'):panel.remind(red,panel.add)
        assert 599<=service.item(red)['due']-int(time.time())<=601
        service.modify(red,due=int(time.time())-1)
        service.deliver_due();assert service.item(red)['notified'] and service.toast
        toast=service.toast;service.deliver_due();assert service.toast is toast
        service.modify(red,done=True);panel.view.setCurrentIndex(1);assert red in panel.rows
        service.modify(red,deleted=True);panel.view.setCurrentIndex(2);assert red in panel.rows
        service.modify(red,deleted=False,done=False,due=0);panel.view.setCurrentIndex(0)
        assert red in panel.rows
        found,_=matches(cfg,[],[],'薄荷',scope='flash');assert found[0]['payload']==green
        cfg['flash_palette']='theme'
        custom=snapshot(cfg)
        vivid=switch_profile(cfg,'vivid','custom')
        assert vivid['flash_palette']=='vivid' and vivid['dock_material']==vivid['panel_material']=='liquid'
        assert vivid['theme_color']==vivid['panel_color']==VIVID_BLUE and vivid['clock_appearance']['design']==vivid['calendar_appearance']['design']=='vivid'
        assert selected_mode(vivid)=='vivid' and snapshot(switch_profile(vivid,'custom','vivid'))==custom
        cfg.update(vivid);service.sync();colors=palette_for(service)['fills']
        assert [colors[k] for k in ('blue','green','red')]==[VIVID_BLUE,VIVID_GREEN,VIVID_RED]
        panel.reveal_item(identity);app.processEvents()
        panel.hide_notice();panel.launch_shell.hide();panel.toolbar.hide();panel.input_region()
        app.processEvents()
        assert not panel.toolbar.isVisible()
        gap=QPoint(8,panel.height()-32)
        assert not panel.mask().contains(gap)
        image=panel.grab().toImage()
        assert image.pixelColor(round(gap.x()*image.devicePixelRatio()),round(gap.y()*image.devicePixelRatio())).alpha()==0
        assert image.save(str(Path(output)/'flash-vivid.png'))
        panel.toggle_tools();app.processEvents();assert panel.toolbar.isVisible() and panel.toolbar.width()<155
        assert panel.grab().save(str(Path(output)/'flash-tools.png'))
        panel.toolbar.hide();panel.input_region()
        edge.clear_notice();assert edge.grab().save(str(Path(output)/'flash-edge.png'))
        panel.resize(320,380);cfg.update(panel_theme='dark',flash_palette='theme');service.sync()
        panel.resize(320,380);app.processEvents()
        assert panel.grab().save(str(Path(output)/'flash-compact-dark.png'))
        panel.filters_bar.show();app.processEvents()
        assert panel.swatches['purple'].mapTo(panel,QPoint(0,0)).x()+panel.swatches['purple'].width()<=panel.width()
        target=Path(root)/'flash-export.json';export_configuration(target,cfg,api)
        restored=read_configuration(target,api);assert restored['flash_entries']==cfg['flash_entries']
        try:normalize(dict(cfg,flash_entries=[dict(cfg['flash_entries'][0],color='bogus')]),api)
        except ValueError:pass
        else:raise AssertionError('Invalid flash data was accepted')
        cfg['flash_side']='left';service.reposition()
        assert edge.geometry().left()==edge.work_area.left()+2
        edge_rows=copy.deepcopy(cfg['flash_entries']);service.collapse();edge.clear_notice();cfg['motion_enabled']=True
        outside=QPoint(edge.work_area.center().x(),edge.work_area.top()+1)
        with patch('flash_panel.QCursor.pos',return_value=outside):
            edge.hide_if_idle();edge.slide.setCurrentTime(edge.slide.duration())
        assert edge.width()==6 and edge.work_area.contains(edge.geometry())
        edge.grab().save(str(Path(output)/'flash-edge-hidden.png'))
        app.sendEvent(edge,QEvent(QEvent.Enter));edge.slide.setCurrentTime(edge.slide.duration())
        assert edge.width()==29
        edge.grab().save(str(Path(output)/'flash-edge-revealed.png'))
        with patch('flash_panel.QCursor.pos',return_value=edge.geometry().center()):edge.open_on_hover()
        assert service.panel and not service.panel.editing
        with patch('flash_panel.QCursor.pos',return_value=outside):service.panel.fold_if_idle()
        assert not service.panel and edge.hide_timer.isActive()
        edge.toggle_edge_hide(False);edge.slide.setCurrentTime(edge.slide.duration())
        with patch('flash_panel.QCursor.pos',return_value=outside):edge.hide_if_idle()
        assert edge.width()==29 and api.load_config()['flash_edge_hide'] is False
        edge.toggle_edge_hide(True)
        start=edge.mapToGlobal(QPoint(14,20));finish=QPoint(edge.work_area.right()-8,edge.work_area.center().y())
        for kind,global_point,held in [(QEvent.MouseButtonPress,start,Qt.LeftButton),(QEvent.MouseMove,finish,Qt.LeftButton),(QEvent.MouseButtonRelease,finish,Qt.NoButton)]:
            app.sendEvent(edge,QMouseEvent(kind,QPointF(edge.mapFromGlobal(global_point)),QPointF(global_point),Qt.LeftButton,held,Qt.NoModifier))
        assert cfg['flash_side']=='right' and api.load_config()['flash_side']=='right' and cfg['flash_layout']
        with patch('flash_panel.QCursor.pos',return_value=outside):edge.hide_if_idle();edge.slide.setCurrentTime(edge.slide.duration())
        assert edge.width()==6 and edge.work_area.contains(edge.geometry())
        assert cfg['flash_entries']==edge_rows
        checks.append('Flash edge hide: 6-pixel target, hover slide-out, panel hover/open/leave collapse, independent persisted off switch, drag across left/right edges, saved anchor, and geometry stays inside the selected screen.')
        runtime.game_active=True;service.sync()
        assert not service.edge and not service.panel and service.reminder is None and not edge.slide.state() and not edge.hide_timer.isActive()
        runtime.game_active=False;service.sync();assert service.edge and not service.panel
        assert service.set_enabled(False) and not service.edge and not service.panel
        checks.append('Flash capsule: real Quick Settings button, editor/Enter and clipboard-free text drops, inline expansion, filters, draft reopen and failed saves, completion/trash restoration, one reminder, import/export, game suspension and both edges. Exact reference RGB and global/custom roundtrip checked; no physical OLE drag or foreground UI.')
    finally:
        if popup:popup.close();popup.deleteLater()
        service.collapse(force=True)
        runtime.game_active=old_game
        cfg.clear();cfg.update(original);service.sync(reload=True);api.save_config(cfg)
