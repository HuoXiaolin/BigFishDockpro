"""Card density, explicit geometry/font controls and adaptive settings regressions."""
import copy
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QRect,QSize
from PyQt5.QtWidgets import QApplication
from desktop_panels import DesktopPanels
from sticky_notes import NotesManager
from settings_dialog import SettingsDialog
from settings_layout import automatic_mode
from card_sizing import CardSizingDialog
from desktop_panel_tests import wait_for
from ui_style import apply_theme


def run(api,runtime,root,output,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg);roots=list(runtime.panels.roots)
    runtime.panels.close();runtime.notes.close();dialog=dense=None
    try:
        from screen_layout import initial_card_factor
        assert initial_card_factor([0,0,3840,2160])==2.5
        assert initial_card_factor([0,0,1536,816])==1.0
        assert automatic_mode(QRect(0,0,3840,2160))=='large'
        assert automatic_mode(QRect(0,0,1920,1080))=='medium'
        assert automatic_mode(QRect(0,0,1366,768))=='small'
        cfg.update(card_scale=70,settings_size='small',notes_enabled=False,sticky_notes=[],notes_trash=[],display_layout={},panel_enabled=True,desktop_auto_sort=False,merged_panels=False,disabled_categories=[],desktop_excluded=[],desktop_entries=[],desktop_panels=[{'id':'sizing','name':'尺寸演示','geometry':[40,50,320,240],'compact':False,'view':'list'}])
        api.save_config(cfg);runtime.panels=DesktopPanels(runtime,roots=[]);runtime.notes=NotesManager(runtime);runtime.apply_settings();app.processEvents()
        card=runtime.panels.windows['sizing'];assert abs(card.ui_factor-.7)<.005 and abs(card.width()-224)<=1,(card.ui_factor,card.size())
        baseline=copy.deepcopy(cfg['display_layout']);runtime.layout.apply();runtime.layout.apply();assert cfg['display_layout']==baseline
        # Concrete width/height and displayed text size; save remains open.
        dialog=CardSizingDialog(runtime,'panel','sizing');dialog.show();app.processEvents()
        dialog.auto_height.setChecked(False);dialog.width_field.setValue(360);dialog.height_field.setValue(280);dialog.text_field.setValue(18)
        assert dialog.commit() and dialog.isVisible();app.processEvents()
        assert card.width()==360 and card.height()==280 and card.text_pixels()==18,(card.size(),card.text_pixels())
        assert cfg['display_layout']['panels']['sizing']['density']==.7
        assert cfg['desktop_panels'][0]['font_size']==18
        # Larger fonts retain all eleven list rows, with scrolling to the final row.
        files=[]
        for index in range(11):
            path=Path(root)/('sizing-%02d.txt'%index);path.write_text('demo',encoding='utf-8');files.append(str(path))
        runtime.panels.add_paths('sizing',files);card.render();app.processEvents()
        rectangles=[card.list.visualItemRect(card.list.item(i)) for i in range(11)]
        assert len({rect.y() for rect in rectangles})==11 and all(rect.height()>=card.list.fontMetrics().height() for rect in rectangles)
        card.list.scrollToBottom();app.processEvents();assert card.list.visualItemRect(card.list.item(10)).intersects(card.list.viewport().rect())
        before=copy.deepcopy(cfg);dialog.width_field.setValue(420)
        with patch.object(api,'save_config',return_value=False):assert not dialog.commit()
        assert cfg==before and card.width()==360
        dialog.reject();dialog=None
        # Changing the global density twice preserves the initial anchor and manual font choice.
        cfg['card_scale']=100;runtime.apply_settings();assert abs(card.width()-round(360/.7))<=1 and card.text_pixels()==26
        cfg['card_scale']=70;runtime.apply_settings();assert card.width()==360 and card.text_pixels()==18
        card.move(card.x()+5,card.y()+3);card.store_geometry();stable=copy.deepcopy(cfg['display_layout']);runtime.layout.apply();assert cfg['display_layout']==stable and card.width()==360
        runtime.panels.status('');card.grab().save(str(Path(output)/'card-custom-size-font.png'))
        # The same dimensions/text dialog controls notes and retains rich text/content.
        identity=runtime.notes.new();note=runtime.notes.windows[identity];assert abs(note.ui_factor-.7*initial_card_factor(list(QApplication.primaryScreen().availableGeometry().getRect())))<.01
        note.editor.setPlainText('独立字号与尺寸演示');runtime.notes.flush()
        dialog=CardSizingDialog(runtime,'note',identity);dialog.show();dialog.width_field.setValue(350);dialog.height_field.setValue(290);dialog.text_field.setValue(19)
        result=dialog.commit();assert result and note.width()==350 and note.height()==290 and note.text_pixels()==19,(result,note.size(),note.text_pixels(),note.ui_factor,runtime.notes.row(identity))
        assert note.editor.toPlainText()=='独立字号与尺寸演示'
        dialog.grab().save(str(Path(output)/'card-sizing-dialog.png'));dialog.reject();dialog=None
        record=copy.deepcopy(runtime.notes.row(identity)['layout'])
        runtime.layout.changed();assert not note.geometry_timer.isActive();runtime.layout.apply();note.save_geometry()
        # A no-op geometry save must preserve the reference visual scale/density.
        assert runtime.notes.row(identity)['layout']==record and note.text_pixels()==19
        note.grab().save(str(Path(output)/'note-custom-size-font.png'))
        # Settings modes scale controls and fonts; switching and themes do not accumulate.
        runtime.layout.timer.stop();note.geometry_timer.stop();runtime.notes.flush()
        dense=SettingsDialog(runtime.tray,api);dense.reveal();app.processEvents();saved_cfg=copy.deepcopy(cfg)
        with patch.object(dense,'available_interface_area',return_value=QRect(0,0,3840,2160)):
            sizes=[];fonts=[]
            for mode in ('small','medium','large'):
                dense.size_mode.setCurrentIndex(dense.size_mode.findData(mode));app.processEvents();sizes.append(dense.size());fonts.append(dense.fields['icon_size'].font().pixelSize())
                assert dense.size_mode.currentData()==mode
                dense.grab().save(str(Path(output)/('settings-preset-'+mode+'.png')))
            assert sizes==[QSize(560,448),QSize(800,640),QSize(1200,960)],sizes
            assert fonts[0]<fonts[1]<fonts[2],fonts
            dense.size_mode.setCurrentIndex(dense.size_mode.findData('auto'));assert float(dense.property('interfaceScale'))==1.5
            for _ in range(2):
                apply_theme(app,False);apply_theme(app,True);assert dense.size()==QSize(1200,960) and dense.size_mode.currentData()=='auto'
            dense.reject();assert cfg==saved_cfg,{key:(saved_cfg.get(key),cfg.get(key)) for key in set(saved_cfg)|set(cfg) if saved_cfg.get(key)!=cfg.get(key)}
            dense.reveal();dense.size_mode.setCurrentIndex(dense.size_mode.findData('medium'));dense.resize(910,710);app.processEvents()
            assert dense.size_mode.currentData()=='custom'
            dense.commit();assert cfg['settings_size']=='custom' and cfg['settings_manual_size']==[910,710]
        dense.reject();dense.reveal();area=dense.available_interface_area()
        assert dense.size()==QSize(min(910,area.width()-24),min(710,area.height()-24)),dense.size()
        assert cfg['settings_manual_size']==[910,710]
        checks.append('card sizing and adaptive settings: 70 percent card/frame/text density without anchor drift, per-card exact width/height/text including notes, rich content retained, eleven large-font list rows, atomic save failure, global density reversible, resize-transition timer guard; settings auto/small/medium/large scale all controls/fonts, high-resolution 1200x960, theme idempotence, cancel and manual 910x710 save/reopen')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        if dense:
            dense.reject();runtime.updater.changed.disconnect(dense.update_changed);dense.deleteLater()
        runtime.panels.close();runtime.notes.close();cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);runtime.notes=NotesManager(runtime);runtime.apply_settings();apply_theme(app,runtime.dock.is_light())
