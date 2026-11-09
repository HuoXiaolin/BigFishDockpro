"""Bounded refresh and legacy preferences on the isolated desktop."""
import copy,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def run(api,runtime,main,app,output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QImage,QColor
    from app_catalog import path_key
    from desktop_catalog import file_state,scan_desktop
    from card_file_ui import picture_thumbnail
    from sticky_notes import NotesManager
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);manager=runtime.panels
    previous_metadata=manager.file_metadata;previous_rows=manager.scanned_rows;previous_message=manager.message
    previous_scan_again=manager.scan_again
    manager.scan_timer.stop()
    if manager.worker:
        manager.worker.ready.disconnect(manager.scanned);manager.worker.close();manager.worker=None
    manager.scan_again=False
    try:
        with tempfile.TemporaryDirectory(prefix='bigfish-resource-') as directory:
            root=Path(directory);paths=[]
            for name in ('alpha.txt','bravo.txt','charlie.txt'):
                path=root/name;path.write_text(name,encoding='utf-8');paths.append(path)
            rows=[{'path':str(path),'name':path.name,'panel':'documents','source':'desktop'} for path in paths]
            cfg.update(panel_enabled=True,panels_visible=True,desktop_auto_sort=True,merged_panels=False,
                       panel_auto_hide=False,disabled_categories=[],desktop_excluded=[],
                       desktop_panels=[{'id':'documents','name':'文档','view':'small','geometry':[60,70,420,280]}],
                       desktop_entries=copy.deepcopy(rows[:2]))
            manager.file_metadata={path_key(str(path)):file_state(str(path)) for path in paths[:2]}
            manager.sync_windows();panel=manager.windows['documents'];panel.query.setText('')
            panel.set_collapsed_geometry(False);panel.render(prepare=True);panel.list.doItemsLayout()
            panel.list.setCurrentRow(1);focused=panel.list.currentItem();focused.setSelected(True)
            with patch.object(panel,'render',wraps=panel.render) as render:
                manager.worker=SimpleNamespace(metadata=dict(manager.file_metadata))
                manager.scanned(copy.deepcopy(rows[:2]),[])
                assert render.call_count==0,render.call_count
            assert panel.list.currentItem() is focused and focused.isSelected()
            with patch.object(manager,'sync_windows',wraps=manager.sync_windows) as sync:
                manager.worker=SimpleNamespace(metadata={path_key(str(path)):file_state(str(path)) for path in paths})
                manager.scanned(copy.deepcopy(rows),[])
                assert sync.call_count==1,sync.call_count
            assert panel.list.count()==3 and panel.list.currentItem() is focused and focused.isSelected()
            old_icon=focused.icon().cacheKey()
            paths[0].write_text('modified sample',encoding='utf-8')
            with patch.object(runtime.dock.icons,'get',wraps=runtime.dock.icons.get) as icons:
                manager.worker=SimpleNamespace(metadata={path_key(str(path)):file_state(str(path)) for path in paths})
                manager.scanned(copy.deepcopy(rows),[])
                assert icons.call_count==1,icons.call_count
            assert focused.icon().cacheKey()==old_icon and panel.list.currentItem() is focused
            with patch.object(runtime.dock.icons,'get',wraps=runtime.dock.icons.get) as icons:
                panel.render(force=True)
                assert icons.call_count==3 and panel.list.currentItem() is focused
            manager.file_metadata={path_key(str(path)):file_state(str(path)) for path in paths}
            cfg['desktop_panels'][0]['sort']='modified_desc'
            with patch('desktop_panels.os.path.getmtime',side_effect=AssertionError('UI stat')):
                assert manager.rows('documents')[0]['path']==str(paths[0])
            metadata={};scanned,errors=scan_desktop([directory],metadata=metadata)
            assert not errors and len(scanned)==3 and len(metadata)==3
            assert all(set(row)=={'path','name','panel','source'} for row in scanned)
            with patch('card_file_ui.os.stat',side_effect=AssertionError('Non-image stat')):
                assert picture_thumbnail(str(paths[0]),32) is None
            image=QImage(32,24,QImage.Format_ARGB32);image.fill(QColor('#8dc9ec'))
            picture=root/'sample.png';assert image.save(str(picture))
            state=file_state(str(picture))
            with patch('card_file_ui.os.stat',side_effect=AssertionError('Duplicate thumbnail stat')):
                assert picture_thumbnail(str(picture),32,state) is not None
            checks.append('unchanged scans keep QListWidgetItems and keyboard focus; changed scan synchronizes once; unchanged icons reused; scan metadata supplies time sorting and thumbnails')
        legacy=dict(cfg,merged_collapsed=True,lite_enabled=True,runtime_lite=True,lite_restore={'__merged__':False},
                    dock_quick_order=['notes','lite','clock'],game_mode=True,fullscreen_detection=False)
        from config_transfer import normalize
        for restored in (api.normalize_features(legacy), normalize(legacy, api)):
            assert restored['merged_collapsed'] and not {'lite_enabled','runtime_lite','lite_restore'} & restored.keys()
            assert restored['dock_quick_order'][:2]==['notes','clock'] and 'lite' not in restored['dock_quick_order']
            assert restored['game_mode'] and not restored['fullscreen_detection']
        checks.append('legacy preferences drop the retired mode and tile while preserving folds, custom quick order and independent pause flags')
        notes=SimpleNamespace(pending={'one':{'id':'one','title':'pending','appearance':{'color':'blue'}}},
                              runtime=SimpleNamespace(dock=SimpleNamespace(cfg={'sticky_notes':[{'id':'one','title':'saved'}]})))
        notes.rows=lambda:(_ for _ in ()).throw(AssertionError('cloned every note'))
        row=NotesManager.row(notes,'one');assert row['title']=='pending'
        row['appearance']['color']='changed';assert notes.pending['one']['appearance']['color']=='blue'
        checks.append('single-note reads avoid cloning the collection and preserve detached editable result semantics')
    finally:
        manager.scan_timer.stop();manager.worker=None;manager.file_metadata=previous_metadata
        manager.scanned_rows=previous_rows;manager.scan_again=previous_scan_again;manager.message=previous_message
        cfg.clear();cfg.update(before);runtime.apply_settings();runtime.layout.apply();manager.restore_layout_state()
        # Layout methods may normalize session hints; restore the persisted input too.
        cfg.clear();cfg.update(before);api.save_config(cfg)
