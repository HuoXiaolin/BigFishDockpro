"""Independent merge groups and local calendar clock styles on a private desktop."""
import copy,datetime
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication,QMessageBox


def run(api,runtime,root,output,checks):
    from desktop_panels import DesktopPanels
    from panel_management import GroupDialog
    from feature_config import normalize
    from clock_appearance import STYLES,normalize as clock_options
    from desktop_clock import ClockOptions,draw_clock
    from PyQt5.QtGui import QPixmap,QPainter
    from PyQt5.QtCore import QRectF
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    previous=runtime.panels;roots=list(previous.roots);previous.close();manager=None
    fixture=Path(root)/'merge-groups';fixture.mkdir();sample=fixture/'group.txt';sample.write_text('reference only',encoding='utf-8')
    try:
        cfg.update(panel_enabled=True,panels_visible=True,desktop_auto_sort=False,panel_auto_hide=False,panel_locked=False,
                   merged_panels=False,merge_initialized=False,merge_groups=[],merged_active='',merged_geometry=[],merged_collapsed=False,
                   desktop_entries=[],disabled_categories=[],desktop_excluded=[],display_layout={},
                   desktop_panels=[{'id':key,'name':title,'geometry':[80+index*70,80+index*40,320,240]} for index,(key,title) in enumerate([('a','办公'),('b','文件'),('c','资料'),('d','收藏')])])
        cfg.update(normalize(cfg));assert api.save_config(cfg)
        assert len(cfg['merge_groups'])==1 and all(row['merge_group']=='default' for row in cfg['desktop_panels'])
        manager=runtime.panels=DesktopPanels(runtime,roots=[]);manager.apply_settings();app.processEvents()
        assert len([w for w in manager.windows.values() if w.isVisible()])==4
        assert manager.set_merged('a',True);app.processEvents()
        assert len([w for w in manager.windows.values() if w.isVisible()])==1
        assert manager.windows['a'].tabs.count()==4 and cfg['merge_initialized']
        # The gradient's content edge must follow actual tab/search geometry.
        old_design=cfg.get('card_design','aurora');cfg['card_design']='gradient'
        panel=manager.windows['a'];panel.apply_options()
        for width,height in [(610,386),(340,280)]:
            panel.resize(width,height);app.processEvents();panel.layout().activate()
            edge=panel.design_body_top();tab_bottom=panel.tabs.mapTo(panel,panel.tabs.rect().bottomLeft()).y()
            search_top=panel.query.mapTo(panel,panel.query.rect().topLeft()).y()
            assert tab_bottom<edge<search_top,(tab_bottom,edge,search_top)
            panel.grab().save(str(Path(output)/('panel-gradient-merged-%d.png'%width)))
        assert manager.set_merged('a',False);app.processEvents();panel.layout().activate()
        assert not panel.tabs.isVisible() and panel.design_body_top()<edge
        panel.grab().save(str(Path(output)/'panel-gradient-independent.png'))
        old_collapse_style=cfg.get('panel_collapse_style','bar');cfg['panel_collapse_style']='bar'
        panel.set_collapsed_geometry(False);panel.layout().activate();app.processEvents()
        expanded_radius=panel.surface_radius();expanded=panel.grab().toImage()
        panel.set_collapsed_geometry(True);panel.layout().activate();app.processEvents()
        assert panel.surface_radius()==expanded_radius
        collapsed=panel.grab().toImage()
        for x,y in [(2,2),(5,5),(10,2)]:assert abs(expanded.pixelColor(x,y).alpha()-collapsed.pixelColor(x,y).alpha())<=2
        panel.grab().save(str(Path(output)/'panel-gradient-collapsed-bar.png'))
        panel.set_collapsed_geometry(False);panel.layout().activate();app.processEvents()
        panel.grab().save(str(Path(output)/'panel-gradient-expanded-corners.png'))
        cfg['panel_collapse_style']=old_collapse_style
        checks.append('bar and expanded card share exact glass/design corner radius and top-corner alpha; capsule retains its distinct radius')
        cfg['card_design']=old_design;panel.apply_options()
        assert manager.set_merged('a',True);app.processEvents()
        checks.append('gradient collection surface follows live header/tabs/search boundary at wide and narrow sizes; independent cards omit tab gap')
        second=manager.new_merge_group('资料组');assert second
        assert manager.assign_group('c',second) and manager.assign_group('d',second)
        manager.select_page('a');manager.select_page('c');app.processEvents()
        assert {key for key,w in manager.windows.items() if w.isVisible()}=={'a','c'}
        assert [manager.windows['a'].tabs.tabData(i) for i in range(2)]==['a','b']
        assert [manager.windows['c'].tabs.tabData(i) for i in range(2)]==['c','d']
        host=manager.windows['a'];host_id=int(host.winId());host_geometry=host.geometry();before_state=host.page_state()
        with patch.object(host,'capture_backdrop') as capture:
            manager.select_page('b');assert manager.windows['b'].isVisible() and manager.windows['c'].isVisible()
            assert manager.windows['b'] is host and int(host.winId())==host_id and host.geometry()==host_geometry
            assert not host.refresh_timer.isActive() and not capture.called
            assert host.page_transition.frame is not None
            from desktop_panel_tests import wait_for
            wait_for(app,lambda:host.page_transition.frame is None)
            assert host.page_transition.animation.state()==host.page_transition.animation.Stopped
        with patch.object(api,'save_config',return_value=False):manager.select_page('a')
        assert manager.windows['b'] is host and manager.active_for('b')=='b'
        manager.select_page('a');manager.select_page('b');app.processEvents()
        assert manager.windows['b'] is host and int(host.winId())==host_id
        checks.append('merged tabs retain visible native window/geometry, no new backdrop capture; finite crisp content slide releases snapshots, rapid switching works, failed save preserves page')
        manager.select_page('d');assert manager.windows['b'].isVisible() and manager.windows['d'].isVisible()
        # Persist different real widget sizes and group-relative monitor records.
        first=manager.windows['b'];first.set_collapsed_geometry(False);first.move(90,100);first.resize(360,230);first.store_geometry();first.resize_timer.stop()
        other=manager.windows['d'];other.set_collapsed_geometry(False);other.move(510,160);other.resize(300,210);other.store_geometry();other.resize_timer.stop()
        first_geometry=copy.deepcopy(cfg['merged_geometry']);other_geometry=copy.deepcopy(manager.group_value('d','geometry'))
        assert first_geometry[2:]!=other_geometry[2:]
        assert 'merged' in cfg['display_layout'] and second in cfg['display_layout']['merge_groups']
        manager.select_page('c');assert [manager.windows['c'].width(),manager.windows['c'].height()]==other_geometry[2:]
        assert cfg['merged_geometry']==first_geometry
        runtime.layout.apply();app.processEvents();assert manager.windows['b'].size()!=manager.windows['c'].size()
        manager.windows['b'].tabs.moveTab(0,1);app.processEvents()
        assert [m['id'] for m in manager.merged_models('a')]==['b','a'] and [m['id'] for m in manager.merged_models('c')]==['c','d']
        assert manager.add_paths('a',[str(sample)]) and manager.add_paths('c',[str(sample)])
        manager.select_page('a');host=manager.windows['a'];host.query.setText('group')
        manager.select_page('b');host.query.setText('empty-page-filter')
        manager.select_page('a');assert manager.windows['a'] is host and host.query.text()=='group' and host.list.count()==1
        host.page_transition.animation.setCurrentTime(80);host.grab().save(str(Path(output)/'panel-tab-transition.png'))
        wait_for(app,lambda:host.page_transition.frame is None)
        host.grab().save(str(Path(output)/'panel-tab-transition-finished.png'))
        host.query.clear();manager.select_page('b');assert host.query.text()=='empty-page-filter'
        host.query.clear()
        entries=copy.deepcopy(cfg['desktop_entries'])
        dialog=GroupDialog(manager);dialog.show();app.processEvents()
        third=dialog.create_group('临时合并组');assert third!=second and third!='default'
        assert dialog.move_cards(['a','b'],second)
        assert dialog.find_card('a').parent().data(0,Qt.UserRole)==second and manager.group_id('a')=='default'
        assert dialog.move_cards(['a','b'],'default')
        # Exercise the real drop-event entry with the same MIME payload as startDrag.
        from PyQt5.QtCore import QMimeData
        import json
        mime=QMimeData();mime.setData('application/x-bigfishdock-panel-groups',json.dumps(['d']).encode())
        dialog.tree.scrollToItem(dialog.nodes[third]);app.processEvents()
        class Drop:
            accepted=False
            def source(self):return dialog.tree
            def mimeData(self):return mime
            def pos(self):return dialog.tree.visualItemRect(dialog.nodes[third]).center()
            def acceptProposedAction(self):self.accepted=True
            def ignore(self):self.accepted=False
        drop=Drop();dialog.tree.dropEvent(drop);assert drop.accepted and dialog.find_card('d').parent() is dialog.nodes[third]
        dialog.nodes[third].setText(0,'创意收藏');assert next(g for g in dialog.merge_groups if g['id']==third)['name']=='创意收藏'
        before=copy.deepcopy(cfg)
        with patch.object(api,'save_config',return_value=False):dialog.commit()
        assert cfg==before
        dialog.commit();app.processEvents()
        assert manager.group_id('d')==third and len([w for w in manager.windows.values() if w.isVisible()])==3
        dialog.grab().save(str(Path(output)/'multiple-merge-groups.png'))
        dialog.reject();dialog.deleteLater()
        # Removing a group only changes membership, and defaults to cancellation.
        dialog=GroupDialog(manager)
        with patch('panel_group_view.QMessageBox.question',return_value=QMessageBox.No):dialog.remove_group(third)
        assert third in {g['id'] for g in dialog.merge_groups}
        with patch('panel_group_view.QMessageBox.question',return_value=QMessageBox.Yes):dialog.remove_group(third)
        dialog.commit();dialog.reject();dialog.deleteLater();app.processEvents()
        assert manager.group_id('d')=='default' and cfg['desktop_entries']==entries and sample.read_text(encoding='utf-8')=='reference only'
        assert manager.set_merged('d',False);assert manager.windows['d'].isVisible() and not manager.windows['d'].tabs.isVisible()
        saved=api.load_config();manager.close();cfg.clear();cfg.update(saved)
        manager=runtime.panels=DesktopPanels(runtime,roots=[]);manager.apply_settings();app.processEvents()
        assert len([w for w in manager.windows.values() if w.isVisible()])==3 and manager.group_id('c')==second
        assert manager.active_for('c')=='c' and manager.windows['c'].isVisible()
        from config_transfer import normalize as normalize_import
        imported=normalize_import(copy.deepcopy(cfg),api)
        assert imported['merge_groups']==cfg['merge_groups'] and imported['display_layout']['merge_groups']==cfg['display_layout']['merge_groups']
        checks.append('multiple merged groups: old config migrates to default; first merge includes all cards; two groups switch/reorder independently and persist separate real widget dimensions and monitor anchors; third group created by one click, multi-card moves and real drop-event MIME routing and inline rename checked, failed save preserves settings, deletion cancel/move-to-default preserves references; detached card and active pages survive reload/import')
        # Render every new composition in light/dark, portrait/landscape and small frames.
        choices=dict(STYLES);assert {'calendar','orbit','month'}<={value for _,value in STYLES}
        from clock_faces import period_progress
        assert period_progress(datetime.datetime(2028,1,1))['year']==0
        assert abs(period_progress(datetime.datetime(2028,2,29,12))['year']-59.5/366)<1e-12
        assert 0.99<period_progress(datetime.datetime(2027,12,31,23,59))['year']<1
        clock=runtime.clock
        for style in ('calendar','orbit','month'):
            for theme in ('light','dark'):
                for width,height in ((360,220),(180,240),(250,150),(160,100)):
                    image=QPixmap(width,height);image.fill(Qt.transparent);painter=QPainter(image)
                    options=clock_options(dict(theme=theme,material='liquid',color='#7a9fca',text_effect='clear',opacity=80))
                    draw_clock(painter,QRectF(0,0,width,height),runtime.dock,options,style);painter.end()
                    if (width,height)==(360,220):image.save(str(Path(output)/('clock-'+style+'-'+theme+'.png')))
                    assert not image.isNull()
                cfg['clock_style']=style;assert api.save_config(cfg) and api.load_config()['clock_style']==style
                assert normalize_import(copy.deepcopy(cfg),api)['clock_style']==style
        # Reproduce the reported transparent blue desktop at its actual aspect ratio.
        backdrop=QPixmap(624,280);backdrop.fill(api.QColor('#2477d7'))
        sample=QPixmap(624,280);sample.fill(api.QColor('#2477d7'));painter=QPainter(sample)
        options=clock_options(dict(material='clear',opacity=0,highlight=0,text_color='#ffffff',font='Segoe UI',font_scale=110,typography_version=2,color='#b8d9ef'))
        draw_clock(painter,QRectF(0,0,624,280),runtime.dock,options,'orbit',backdrop);painter.end()
        sample.save(str(Path(output)/'clock-orbit-blue-desktop.png'))
        pixels=sample.toImage()
        # Bottom metric card keeps a visible six-pixel progress fill in the new layout.
        visible=sum(abs(pixels.pixelColor(60,y).green()-pixels.pixelColor(180,y).green())>8 for y in range(247,260))
        assert visible>=5,visible
        checks.append('reported progress clock: 624x280 transparent blue desktop render, visible fill at least six pixels thick, larger wide numerals, explicit Chinese sans-serif labels, aligned percentages and theme-family pastel gradients')
        dialog=ClockOptions(clock);dialog.show();app.processEvents()
        for style in ('calendar','orbit','month'):
            field=dialog.fields['style'];field.setCurrentIndex(field.findData(style));dialog.preview.update();app.processEvents()
            assert dialog.commit() and cfg['clock_style']==style
        dialog.grab().save(str(Path(output)/'clock-style-options.png'));dialog.reject();dialog.deleteLater()
        assert clock.tick.isSingleShot() and clock.tick.interval()<=60000
        checks.append('new clock styles: calendar week overview, day/week/month/year progress rings and full monthly calendar; all rendered light/dark at four dimensions; style dropdown/preview/save and configuration reload/import accepted, existing minute tick reused, no network or second animation')
    finally:
        if manager:manager.close()
        cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings()
