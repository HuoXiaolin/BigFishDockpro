"""Independent fold styles and centered expanded-geometry restoration."""
import copy
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


def run(api,runtime,root,output,checks):
    from desktop_panels import DesktopPanels
    from fold_options import settings
    cfg=runtime.dock.cfg;saved=copy.deepcopy(cfg);app=QApplication.instance();previous=runtime.panels;roots=list(previous.roots);previous.close();manager=None
    try:
        cfg.update(panel_enabled=True,panels_visible=True,desktop_auto_sort=False,panel_auto_hide=False,panel_locked=False,merged_panels=False,merge_initialized=False,merge_groups=[],desktop_entries=[],desktop_excluded=[],disabled_categories=[],display_layout={},desktop_panels=[{'id':'a','name':'独立一','geometry':[100,100,360,280]},{'id':'b','name':'独立二','geometry':[500,100,320,240]}])
        cfg.update(api.normalize_features(cfg));api.save_config(cfg);manager=runtime.panels=DesktopPanels(runtime,roots=[]);manager.apply_settings();app.processEvents()
        a,b=manager.windows['a'],manager.windows['b'];before=list(a.bounds())
        assert manager.update_panel('a',fold={'style':'capsule','ratio':40})
        a.collapse();app.processEvents();assert abs(a.geometry().center().x()-(before[0]+before[2]/2))<=2 and a.y()==before[1],(before,a.geometry().getRect(),a.bounds(),settings(a),a.minimumSize(),a.maximumSize(),a.layout().sizeConstraint(),a.ui_factor)
        assert a.fold_badge.isVisible() and not a.fold_badge.text()
        a.grab().save(str(Path(output)/'panel-fold-capsule.png'))
        a.expand();app.processEvents();assert list(a.bounds())==before
        assert manager.update_panel('a',fold={'style':'ball','ratio':1});a.collapse();app.processEvents();assert a.width()==a.height() and a.fold_badge.isVisible() and not a.fold_badge.text()
        a.grab().save(str(Path(output)/'panel-fold-ball.png'));a.move(a.x()+30,a.y()+20);a.store_geometry();a.expand();app.processEvents();assert a.x()==before[0]+30 and a.y()==before[1]+20 and a.width()==before[2]
        assert settings(b)!=settings(a)
        manager.set_merged('a',True);app.processEvents();assert manager.update_panel('a',fold={'style':'capsule','ratio':20})
        assert settings(manager.windows['a'])==settings(manager.windows['b'])=={'style':'capsule','ratio':20}
        manager.windows[manager.active_for('a')].collapse();app.processEvents();manager.select_page('b');app.processEvents();assert settings(manager.windows['b'])['ratio']==20
        cfg.update(notes_enabled=True,notes_visible=True,note_style='glass');runtime.notes.reload();identity=runtime.notes.new();other=runtime.notes.new();note=runtime.notes.windows[identity];original=note.geometry().getRect()
        assert runtime.notes.update_and_save(identity,fold={'style':'ball','ratio':1});note.set_collapsed(True);app.processEvents()
        assert note.width()==note.height() and note.fold_badge.isVisible() and not note.fold_badge.text();assert abs(note.geometry().center().x()-(original[0]+original[2]/2))<=2 and note.y()==original[1]
        note.grab().save(str(Path(output)/'note-fold-ball.png'));note.move(note.x()+25,note.y()+15);note.save_geometry();note.set_collapsed(False);app.processEvents()
        assert note.width()==original[2] and note.height()==original[3] and note.x()==original[0]+25 and note.y()==original[1]+15
        assert settings(runtime.notes.windows[other])['style']=='bar'
        loaded=api.load_config();assert next(row for row in loaded['sticky_notes'] if row['id']==identity)['fold']['style']=='ball'
        from config_transfer import normalize
        assert normalize(copy.deepcopy(cfg),api)['merge_groups']==cfg['merge_groups']
        checks.append('per-object folding: title-bar centered capsule/ball bounds; card and note expanded dimensions restored after dragging collapsed form; independent styles isolated, merged members share group setting, compact badges render and persisted note/group settings survive reload/import')
    finally:
        if manager:manager.close()
        cfg.clear();cfg.update(saved);api.save_config(cfg);runtime.notes.reload();runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings();app.processEvents()
