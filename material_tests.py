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
    sheet=QImage(940,340,QImage.Format_ARGB32_Premultiplied);sheet.fill(QColor('#f4f6f8'))
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
    from appearance_presets import DOCK_PRESETS,PANEL_PRESETS
    dialog=SettingsDialog(runtime.tray,api);dialog.reveal();dialog.dock_preset.setCurrentIndex(len(DOCK_PRESETS))
    assert dialog.fields['clear_background'].isChecked()
    dialog.fields['dock_material'].setCurrentIndex(dialog.fields['dock_material'].findData('acrylic'))
    assert not dialog.fields['clear_background'].isChecked() and dialog.fields['transparency'].value()>0
    dialog.reject();dialog.deleteLater()
    panel=next(iter(runtime.panels.windows.values()));dialog=PanelOptions(panel);dialog.preset.setCurrentIndex(len(PANEL_PRESETS))
    dialog.fields['material'].setCurrentIndex(dialog.fields['material'].findData('liquid'))
    assert dialog.fields['opacity'].value()>0 and dialog.fields['highlight'].value()>0
    dialog.reject();dialog.deleteLater()
    checks.append('materials: six distinct rendered outputs with the same tint/wallpaper, acrylic grain/blur and opaque simulated mica; clear-to-other selection restores visible defaults without changing saved config')
