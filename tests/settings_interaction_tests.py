"""Exercise wheel routing and the shared theme transaction on the private test desktop."""
import copy
from unittest.mock import patch

from PyQt5.QtCore import QPoint, QPointF, QEvent, Qt
from PyQt5.QtGui import QMouseEvent, QWheelEvent
from PyQt5.QtWidgets import QApplication


def wheel(widget, delta, modifiers=Qt.NoModifier):
    # Go through QWidgetWindow so the real widget under the pointer receives the event.
    handle = widget.window().windowHandle()
    point = widget.mapToGlobal(widget.rect().center())
    event = QWheelEvent(QPointF(handle.mapFromGlobal(point)), QPointF(point), QPoint(), QPoint(0,delta),
                        Qt.NoButton, modifiers, Qt.NoScrollPhase, False)
    QApplication.sendEvent(handle, event)
    QApplication.processEvents()


def click_at(widget, point):
    for kind, buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
        QApplication.sendEvent(widget, QMouseEvent(kind, QPointF(point), Qt.LeftButton, buttons, Qt.NoModifier))


def check_wheel(main, runtime, checks):
    from card_sizing import CardSizingDialog
    from settings_design import NumericControl
    page = main.tabs.pages.widget(0)
    main.tabs.setCurrentIndex(0)
    bar = page.verticalScrollBar()
    combo = main.fields['taskbar_mode']
    spin = main.fields['taskbar_opacity']
    # The optional backend can be absent. Exercise its UI without invoking it.
    combo.setEnabled(True)
    spin.setEnabled(True)
    slider = next(control.slider for control in main.findChildren(NumericControl) if control.spin is spin)
    spin.setValue(32)
    combo.setCurrentIndex(1)
    edits = []
    spin.valueChanged.connect(edits.append)
    combo.currentIndexChanged.connect(edits.append)
    for target in (combo, slider, spin, spin.lineEdit(), spin.plus):
        for focused in (False, True):
            page.ensureWidgetVisible(target)
            focus = spin if target in (spin.lineEdit(),spin.plus) else target
            (focus if focused else main.setting_query).setFocus()
            QApplication.processEvents()
            before = bar.value()
            delta = 120 if before > bar.minimum() else -120
            wheel(target, delta)
            hit=main.childAt(main.mapFromGlobal(target.mapToGlobal(target.rect().center())))
            assert bar.value() != before, (target.metaObject().className(), focused, before, bar.value(), bar.maximum(),
                                          hit.metaObject().className() if hit else None, target.geometry().getRect())
            assert (combo.currentIndex(),spin.value(),slider.value(),edits)==(1,32,32,[])
    spin.plus.click()
    assert spin.value()==slider.value()==33
    spin.lineEdit().selectAll()
    spin.lineEdit().insert('45')
    spin.interpretText()
    assert spin.value()==slider.value()==45
    page.ensureWidgetVisible(slider)
    click_at(slider,QPoint(slider.width()-3,slider.height()//2))
    assert spin.value()==slider.value() and spin.value()>45

    page.ensureWidgetVisible(combo)
    combo.setMaxVisibleItems(2)
    combo.showPopup()
    QApplication.processEvents()
    view = combo.view()
    start = view.verticalScrollBar().value()
    wheel(view.viewport(),-120 if start==0 else 120)
    assert view.verticalScrollBar().value()!=start and combo.currentIndex()==1
    index=combo.model().index(2,0)
    view.scrollTo(index)
    click_at(view.viewport(),view.visualRect(index).center())
    assert combo.currentIndex()==2 and not view.isVisible()
    auxiliary = CardSizingDialog(runtime)
    auxiliary.show()
    QApplication.processEvents()
    try:
        field=auxiliary.text_field
        field.setFocus()
        before=field.value()
        wheel(field.lineEdit(),120,Qt.ControlModifier)
        assert field.value()==before
    finally:
        auxiliary.reject()
        auxiliary.deleteLater()
    checks.append('Settings wheel scrolls the real page over combo, slider, numeric editor and step buttons with and without focus. Popup list scrolls without selecting; click, numeric entry and slider clicks still edit; auxiliary dialog verified.')


def check_theme(api, runtime, main, checks):
    from appearance_presets import PANEL_PRESETS, PRESET_IDS, DOCK_PRESETS
    from appearance_profiles import selected_mode, snapshot
    from dock_extras import DockQuickSettings
    from quick_cycles import next_cycle
    from sticky_notes_store import normalize_notes, default_note_style

    cfg = runtime.dock.cfg
    cfg.update(DOCK_PRESETS[0][1])  # A Dock preset alone is not a global preset.
    cfg.update(panel_color='#227766', note_style='paper', clock_style='orbit', appearance_custom={})
    cfg['calendar_appearance']=dict(cfg['calendar_appearance'],font='Bahnschrift',text_color='#113377')
    note=normalize_notes([dict(id='quick-style-note',style='paper',color='#ffdce5',text='旧正文',
                               body_font_size=25,visible=False,geometry=[80,90,240,180])])[0]
    cfg['sticky_notes']=[*cfg['sticky_notes'],note]
    before=snapshot(cfg)
    main.reveal()
    main.fields['update_use_proxy'].setChecked(not cfg['update_use_proxy'])
    runtime.notes.update(note['id'],text='待保存的新正文')
    popup=DockQuickSettings(runtime.dock.extras)
    try:
        popup.refresh()
        assert popup.tiles['appearance'].value=='自定义'
        for name, preset in PANEL_PRESETS:
            popup.tiles['appearance'].click()
            loaded=api.load_config()
            for current in (cfg,loaded):
                material=preset['material']
                assert current['dock_material']==current['panel_material']==material
                assert current['note_appearance']['material']==current['clock_appearance']['material']==current['calendar_appearance']['material']==material
                assert all(row['appearance']['material']==material for row in current['sticky_notes'])
                assert selected_mode(current)==PRESET_IDS[[item[0] for item in PANEL_PRESETS].index(name)]
                assert current['appearance_custom']==before
            assert popup.tiles['appearance'].value==main.overall_style.currentText()==name
            assert main.fields['update_use_proxy'].isChecked()!=cfg['update_use_proxy']
        added=normalize_notes([dict(default_note_style(cfg),id='added-under-preset',visible=False,text='另一张便签')])[0]
        cfg['sticky_notes']=[*cfg['sticky_notes'],added]
        assert selected_mode(cfg)=='transparent'
        popup.tiles['appearance'].click()
        assert popup.tiles['appearance'].value==main.overall_style.currentText()=='自定义'
        restored=api.load_config()
        expected=copy.deepcopy(before)
        extra=snapshot(restored)['notes']['added-under-preset']
        assert extra['style']=='paper' and next(row['text'] for row in restored['sticky_notes'] if row['id']==added['id'])=='另一张便签'
        expected['notes'][added['id']]=extra
        assert snapshot(restored)==expected
        row=next(row for row in restored['sticky_notes'] if row['id']==note['id'])
        assert row['text']=='待保存的新正文' and row['geometry']==note['geometry'] and not row['visible']
        live_custom=snapshot(cfg)
        main.overall_style.setCurrentIndex(main.overall_style.findData('paper_glass'))
        main.commit()
        popup.refresh()
        assert popup.tiles['appearance'].value=='浅色纸玻璃'
        popup.tiles['appearance'].click()
        popup.tiles['appearance'].click()
        assert selected_mode(cfg)=='custom' and snapshot(cfg)==live_custom
        popup.tiles['appearance'].click()
        main.overall_style.setCurrentIndex(main.overall_style.findData('custom'))
        main.commit()
        assert snapshot(api.load_config())==live_custom
        saved=copy.deepcopy(cfg)
        with patch.object(api,'save_config',return_value=False):
            popup.tiles['appearance'].click()
        assert cfg==saved and '失败' in popup.status.text()
        legacy=copy.deepcopy(cfg)
        old_dock=dict(DOCK_PRESETS[0][1],theme_color='#906351')
        legacy.update(DOCK_PRESETS[1][1])
        legacy.update(appearance_mode='custom',appearance_custom={},dock_quick_custom={'appearance':old_dock,'size':{'icon_size':53}})
        legacy.update(next_cycle(legacy,'appearance'))
        assert all(legacy['appearance_custom']['values'][k]==v for k,v in old_dock.items())
        assert legacy['dock_quick_custom']=={'size':{'icon_size':53}}
        checks.append('Quick tile cycles all five component themes and restores per-component custom styles after reload, including pending note text, a new note and note geometry. Both directions with main settings, unrelated drafts, old custom Dock slots and a failed save verified.')
    finally:
        popup.close()
        popup.deleteLater()


def run(api,runtime,root,app,output,checks):
    from run_isolated_test import assert_isolated
    from settings_dialog import SettingsDialog
    from settings_effects import apply_changes
    assert_isolated()
    assert runtime.notes.flush()
    tray=runtime.tray
    original=copy.deepcopy(tray.cfg)
    previous_dialog=getattr(tray,'settings_dialog',None)
    main=SettingsDialog(tray,api)
    tray.settings_dialog=main
    try:
        main.reveal()
        app.processEvents()
        check_wheel(main,runtime,checks)
        main.reject()
        check_theme(api,runtime,main,checks)
    finally:
        main.reject()
        tray.settings_dialog=previous_dialog
        main.deleteLater()
        changed=dict(tray.cfg)
        tray.cfg.clear()
        tray.cfg.update(original)
        api.save_config(original)
        apply_changes(tray,api,changed)
