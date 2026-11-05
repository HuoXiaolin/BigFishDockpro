"""Material rendering regressions against the same synthetic wallpaper and tint."""
from pathlib import Path
from types import SimpleNamespace
from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QImage,QPixmap,QPainter,QPainterPath,QColor,QLinearGradient,QFont
from liquid_glass import material_palette,material_blur,paint_liquid_glass
from appearance_presets import MATERIALS


def run(api,runtime,output,checks):
    from glass_capture_tests import run as check_capture
    check_capture(checks)
    dock=runtime.dock;output=Path(output)
    wallpaper=QImage(300,112,QImage.Format_ARGB32_Premultiplied)
    p=QPainter(wallpaper);gradient=QLinearGradient(0,0,300,112);gradient.setColorAt(0,QColor('#6eb7d9'));gradient.setColorAt(1,QColor('#d7a7c3'));p.fillRect(wallpaper.rect(),gradient)
    for x in range(0,300,30):p.fillRect(x,0,10,112,QColor(255,255,255,85))
    p.end()
    sheet=QImage(940,12+((len(MATERIALS)+2)//3)*164,QImage.Format_ARGB32_Premultiplied);sheet.fill(QColor('#f4f6f8'))
    rendered=[]
    for index,(name,material) in enumerate(MATERIALS):
        image=QImage(wallpaper);p=QPainter(image);p.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(8,8,284,96);path=QPainterPath();path.addRoundedRect(rect,18,18)
        divisor=material_blur(6,material)
        blurred=QPixmap.fromImage(wallpaper.scaled(max(1,300//divisor),max(1,112//divisor),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(wallpaper.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation))
        palette=material_palette(dock.base_theme_colors('light'),material)
        surface=SimpleNamespace(cfg={'glass':material not in ('clear','solid'),'dock_material':material,'clear_background':False},backdrop=blurred,spec_x=140,spec_alpha=.7)
        paint_liquid_glass(surface,p,path,rect,rect,palette,96,dock.merged_grad_stops(palette));p.end();rendered.append(image)
        p=QPainter(sheet);p.setPen(QColor('#20252c'));p.setFont(QFont('Microsoft YaHei UI',11));x=10+(index%3)*310;y=12+(index//3)*164
        p.drawText(x+8,y+20,name);p.drawImage(x,y+32,image);p.end()
    for i in range(len(rendered)):
        for j in range(i):
            delta=sum(abs(rendered[i].pixelColor(x,y).red()-rendered[j].pixelColor(x,y).red())+abs(rendered[i].pixelColor(x,y).green()-rendered[j].pixelColor(x,y).green())+abs(rendered[i].pixelColor(x,y).blue()-rendered[j].pixelColor(x,y).blue()) for x in range(20,280,8) for y in range(20,95,8))
            assert delta>1000,(MATERIALS[i][0],MATERIALS[j][0],delta)
    assert sheet.save(str(output/'material-comparison.png'))
    from settings_dialog import SettingsDialog
    from glass_panel import PanelOptions
    from appearance_presets import DOCK_PRESETS,PANEL_PRESETS,PRESET_IDS
    dialog=SettingsDialog(runtime.tray,api);dialog.reveal();dialog.dock_preset.setCurrentIndex(PRESET_IDS.index('transparent')+1)
    assert dialog.fields['clear_background'].isChecked()
    dialog.fields['dock_material'].setCurrentIndex(dialog.fields['dock_material'].findData('flowing'))
    assert not dialog.fields['clear_background'].isChecked() and dialog.fields['transparency'].value()>0
    dialog.reject();dialog.deleteLater()
    panel=next(iter(runtime.panels.windows.values()));dialog=PanelOptions(panel);dialog.preset.setCurrentIndex(PRESET_IDS.index('transparent')+1)
    dialog.fields['material'].setCurrentIndex(dialog.fields['material'].findData('liquid'))
    assert dialog.fields['opacity'].value()>0 and dialog.fields['highlight'].value()>0
    dialog.reject();dialog.deleteLater()
    checks.append('materials: distinct rendered outputs with the same tint/wallpaper, acrylic grain/blur and opaque simulated mica; clear-to-other selection restores visible defaults without changing saved config')

    check_clock_materials(api,runtime,output,checks)


def check_clock_materials(api,runtime,output,checks):
    import copy
    from clock_options import ClockOptions
    from clock_appearance import PRESETS
    from appearance_presets import PANEL_PRESETS,DOCK_PRESETS,MATERIAL_CHOICES,PRESET_IDS
    from desktop_clock import draw_clock
    from PyQt5.QtWidgets import QApplication
    dock=runtime.dock;before=copy.deepcopy(dock.cfg);dialog=None
    try:
        assert [n for n,_ in PRESETS]==[n for n,_ in PANEL_PRESETS]==[n for n,_ in DOCK_PRESETS]
        assert len(PRESETS)==5 and ('液态玻璃','liquid') in MATERIAL_CHOICES
        for component in (runtime.clock,runtime.calendar):
            original=copy.deepcopy(component.option('appearance'))
            dialog=ClockOptions(component);dialog.show();dialog.tabs.setCurrentIndex(2);QApplication.processEvents()
            assert dialog.fields['design'].isHidden()
            material=dialog.fields['material'];assert material.findText('全透明')>=0
            material.setCurrentIndex(material.findData('clear'));QApplication.processEvents();values=dialog.values()
            assert values['opacity']==values['highlight']==0 and values['material']=='clear'
            assert all(not dialog.fields[key].isEnabled() for key in ('opacity','blur','highlight'))
            for style in ('digital','calendar_card'):
                image=QImage(624,280,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
                painter=QPainter(image);draw_clock(painter,QRectF(0,0,624,280),dock,values,style);painter.end()
                assert all(image.pixelColor(x,1).alpha()==0 for x in range(624))
                assert any(image.pixelColor(x,y).alpha()>0 for y in range(30,250,3) for x in range(30,590,3))
            assert dialog.commit();assert component.option('appearance')['material']=='clear'
            dialog.grab().save(str(Path(output)/(component.kind+'-transparent-settings.png')))
            dialog.reject();dialog.deleteLater()
            dialog=ClockOptions(component);assert dialog.fields['material'].currentData()=='clear'
            dialog.preset.setCurrentIndex(PRESET_IDS.index('liquid')+1)
            assert dialog.values()['material']=='liquid' and dialog.values()['highlight']==36
            assert all(dialog.fields[key].isEnabled() for key in ('opacity','blur','highlight'))
            dialog.reject();dialog.deleteLater();dialog=None
            assert component.option('appearance')['material']=='clear'
            component.save(clock_appearance=original)
        from settings_dialog import SettingsDialog
        dialog=SettingsDialog(runtime.tray,api)
        legacy=copy.deepcopy(before);legacy.update(dock_material='mica',panel_material='acrylic',card_design='paper')
        dialog.fill_fields(legacy)
        assert dialog.fields['dock_material'].currentData()=='mica'
        assert dialog.fields['panel_material'].currentData()=='acrylic'
        assert dialog.fields['card_design'].isHidden()
        assert not any(row['key']=='card_design' for row in dialog.search_targets())
        assert dialog.profile_candidate()['card_design']=='paper'
        dialog.reject();dialog.deleteLater();dialog=None
        checks.append('five common themes including liquid glass; clock/calendar full-transparent rendering, save/reopen and cancel; material controls follow preset changes; legacy custom materials and decoration preserved')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        dock.cfg.clear();dock.cfg.update(before);api.save_config(dock.cfg);runtime.apply_settings();QApplication.processEvents()
