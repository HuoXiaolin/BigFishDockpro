"""Global style round trips must not roll back live notes, files or work schedules."""
import copy,json
from appearance_profiles import snapshot,apply_profile,apply_snapshot,clean_snapshot,PRESET_IDS,selected_mode

def run(api,runtime,main,app,output,checks):
    from PyQt5.QtTest import QTest
    from PyQt5.QtCore import Qt
    from unittest.mock import patch
    from settings_design_tests import settle
    from appearance_presets import PANEL_PRESETS,DOCK_PRESETS
    from clock_appearance import PRESETS
    assert [n for n,_ in PANEL_PRESETS]==[n for n,_ in DOCK_PRESETS]==[n for n,_ in PRESETS]
    defaults=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
    cfg=copy.deepcopy(defaults)
    cfg.update(clock_style='orbit',card_design='paper',theme_color='#236798',notes_enabled=False,
        sticky_notes=[dict(id='style-fixture',title='主题切换测试',html='<p>正文保留</p>',text='正文保留',style='paper',color='#ffdce5',font_size=15,font_scale=1.0,body_font_size=25,body_font_scale=1.0,visible=False,geometry=[80,90,400,280])],
        clock_layout={'screen':'unmodified'},items=[{'path':'shell:Downloads','name':'下载'}])
    cfg['clock_appearance'].update(font='Bahnschrift',font_scale=147,design='minimal',layout='portrait')
    cfg['clock_appearance']['work']['start']='08:45'
    original=snapshot(cfg);assert clean_snapshot(original)==original
    cfg['appearance_custom']=original
    reset=apply_profile(cfg,'default',defaults)
    assert reset['clock_style']=='digital' and reset['clock_appearance']['layout']=='auto'
    assert reset['clock_appearance']['work']==cfg['clock_appearance']['work']
    assert reset['sticky_notes'][0]['text']==cfg['sticky_notes'][0]['text'] and 'body_font_size' not in reset['sticky_notes'][0]
    assert reset['clock_layout']==cfg['clock_layout'] and reset['items']==cfg['items'] and reset['notes_enabled']==cfg['notes_enabled']
    for key in ('id','html','text','title','geometry','visible'):assert reset['sticky_notes'][0][key]==cfg['sticky_notes'][0][key]
    restored=apply_profile(reset,'custom',defaults);assert snapshot(restored)==original
    for mode in PRESET_IDS:
        styled=apply_profile(cfg,mode,defaults)
        styled['appearance_mode']=mode;styled['appearance_applied']=snapshot(styled)
        assert selected_mode(styled)==mode
        styled['sticky_notes'][0]['text']='切换后新编辑的正文'
        restored=apply_profile(styled,'custom',defaults)
        assert restored['sticky_notes'][0]['text']=='切换后新编辑的正文' and snapshot(restored)==original
        assert clean_snapshot(json.loads(json.dumps(snapshot(styled))))==snapshot(styled)
    invalid=copy.deepcopy(original);invalid['notes']['style-fixture']['style']=[]
    assert not clean_snapshot(invalid)['notes']
    checks.append('five common theme names; default resets clock layout; custom roundtrip preserves geometry, content, switches, work schedule and newer note edits')
    # Exercise the actual Save transaction and failure branch using the live dialog.
    before=copy.deepcopy(runtime.dock.cfg)
    main.fields['theme_color'].setText('#3b789a');main.fields['panel_highlight'].setValue(61)
    pending=main.profile_candidate();saved=snapshot(pending)
    QTest.mouseClick(main.restore_style,Qt.LeftButton);settle(app)
    assert runtime.dock.cfg==before and main._profile_mode=='default'
    main.grab().save(str(output/'settings-global-default.png'))
    with patch.object(api,'save_config',return_value=False):main.commit()
    assert runtime.dock.cfg==before and main._profile_dirty
    main.commit();assert main.isVisible() and selected_mode(runtime.dock.cfg)=='default'
    # Reopening and reloading JSON retains the stored custom slot.
    loaded=api.load_config();assert clean_snapshot(loaded['appearance_custom'])==saved
    main.reject();main.reveal();settle(app)
    main.overall_style.setCurrentIndex(main.overall_style.findData('custom'));settle(app);main.commit()
    assert snapshot(runtime.dock.cfg)==saved
    assert main.fields['theme_color'].text()=='#3b789a' and main.fields['panel_highlight'].value()==61
    # Disabled numeric fields never expose an enabled slider.
    from settings_design import NumericControl
    field=main.fields['panel_highlight'];control=next(w for w in main.findChildren(NumericControl) if w.spin is field)
    field.setEnabled(False);assert not control.slider.isEnabled();field.setEnabled(True);assert control.slider.isEnabled()
    checks.append('real default/custom controls: pending until Save, write failure retains config, saved custom survives close and JSON reload, slider follows disabled state')
