"""Layout-only scenes retain content and are transactional through their dialog."""
import copy
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


def run(api,runtime,main,app,output,checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from layout_profiles import create,apply,normalize_profiles,snapshot
    record={'screen':'demo','area':[0,0,1920,1080],'rect':[100,100,380,260],'ui_scale':1.0,'density':1.0}
    original={'dock_visible':True,'panels_visible':True,'panel_enabled':True,'notes_enabled':True,'notes_visible':True,
              'merged_panels':True,'disabled_categories':[],'theme':'light','panel_collapse_style':'ball','panel_capsule_ratio':50,
              'desktop_panels':[{'id':'a','name':'文件','geometry':[100,100,380,260]}],
              'desktop_entries':[{'path':'demo.txt','panel':'a'}],
              'sticky_notes':[{'id':'n','title':'便签','html':'old','text':'old','visible':True,'layout':record}],
              'display_layout':{'panels':{'a':record}},'merge_groups':[{'id':'default','name':'默认分组'}]}
    profile=create(original,'工作')
    changed=copy.deepcopy(original);changed['theme']='dark';changed['desktop_panels'][0].update(name='新名称',merged=False,geometry=[400,300,500,320])
    changed['sticky_notes'][0].update(text='new',html='new',title='新标题')
    changed['desktop_panels'].append({'id':'later','name':'新卡片','geometry':[600,100,300,220]})
    changed['sticky_notes'].append({'id':'later-note','title':'新便签','text':'keep','html':'keep'})
    changed['display_layout']['panels']['later']=copy.deepcopy(record)
    changed['desktop_entries'].append({'path':'new.txt','panel':'later'})
    restored=apply(changed,profile)
    assert restored['theme']=='dark' and restored['desktop_entries']==changed['desktop_entries']
    assert restored['sticky_notes'][0]['text']=='new' and restored['sticky_notes'][0]['title']=='新标题'
    assert restored['desktop_panels'][0]['name']=='新名称' and restored['desktop_panels'][0]['merged'] is True
    assert restored['desktop_panels'][0]['geometry']==[100,100,380,260]
    assert all(restored['desktop_panels'][-1].get(key)==value for key,value in changed['desktop_panels'][-1].items())
    assert restored['sticky_notes'][-1]==changed['sticky_notes'][-1]
    assert restored['display_layout']['panels']['later']==record
    assert len(normalize_profiles([create(original,str(i)) for i in range(20)]))==12
    unsafe=copy.deepcopy(profile);unsafe['layout']['values'].update(theme='injected',items=['injected'],notes_trash=['injected'])
    assert apply(changed,unsafe)['theme']=='dark' and 'items' not in apply(changed,unsafe)
    assert apply(changed,profile)==restored and original['desktop_panels'][0].get('merged') is None
    checks.append('layout scenes restore geometry/group/fold defaults while retaining current names, themes, note text, references and newly created components; bounded validated profile input')
    from layout_dialog import LayoutDialog
    cfg=runtime.dock.cfg;before=copy.deepcopy(cfg);dialog=None
    try:
        cfg['layout_profiles']=[];cfg['dock_visible']=True
        manager=runtime.panels;cfg['panel_enabled']=True;cfg['panels_visible']=True;runtime.apply_settings()
        identity=next(iter(manager.windows));window=manager.windows[identity]
        if manager.is_merged(identity):manager.update_group(identity,collapsed=False)
        else:manager.model(identity)['collapsed']=False
        manager.restore_layout_state()
        dialog=LayoutDialog(runtime);dialog.show();app.processEvents()
        dialog.name.setText('日常工作');assert dialog.save_current()
        assert len(cfg['layout_profiles'])==1
        saved=copy.deepcopy(cfg['layout_profiles'][0])
        cfg['dock_visible']=False
        if manager.is_merged(identity):manager.update_group(identity,collapsed=True)
        else:manager.model(identity)['collapsed']=True
        manager.restore_layout_state();assert manager.windows[identity].collapsed
        with patch.object(runtime.notes,'flush',return_value=False):
            assert not dialog.apply_selected() and not cfg['dock_visible']
        previous_pending=runtime.layout.pending;runtime.layout.pending=True
        try:assert not dialog.apply_selected() and not cfg['dock_visible']
        finally:runtime.layout.pending=previous_pending
        assert dialog.apply_selected() and cfg['dock_visible']
        assert not manager.windows[identity].collapsed
        dialog.name.setText('专注布局');assert dialog.rename_selected()
        assert cfg['layout_profiles'][0]['name']=='专注布局'
        dialog.name.setText('保存失败')
        with patch.object(runtime.productivity,'commit',return_value=False):assert not dialog.save_current()
        assert len(cfg['layout_profiles'])==1
        dialog.name.setText('演示布局');assert dialog.save_current()
        app.processEvents();dialog.grab().save(str(Path(output)/'layout-profiles.png'))
        with patch.object(dialog,'confirm',return_value=False):assert not dialog.delete_selected()
        assert len(cfg['layout_profiles'])==2
        with patch.object(dialog,'confirm',return_value=True):assert dialog.delete_selected()
        assert len(cfg['layout_profiles'])==1 and cfg['dock_visible']
        dialog.render(cfg['layout_profiles'][0]['id']);dialog.name.setText('专注布局')
        with patch.object(dialog,'confirm',return_value=False):assert not dialog.save_current()
        assert len(cfg['layout_profiles'])==1
        checks.append('layout dialog save/apply/rename/delete works; pending display transition, failed note save, failed config save and cancelled overwrite/delete leave the layout intact')
    finally:
        if dialog:dialog.hide();dialog.deleteLater()
        cfg.clear();cfg.update(before);runtime.apply_settings();runtime.layout.apply();runtime.panels.restore_layout_state();api.save_config(cfg)
