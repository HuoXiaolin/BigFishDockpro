"""Compact card controls survive font saves, theme restores and old configurations."""
import copy,json
from pathlib import Path
from unittest.mock import patch


def run(api,runtime,root,app,output,checks):
    from PyQt5.QtCore import Qt,QRectF
    from PyQt5.QtGui import QPixmap,QPainter,QColor,QFont
    from card_metrics import normalize_profile,metrics,new_geometry,font_pixels
    from card_sizing import CardSizingDialog
    from appearance_profiles import snapshot,apply_snapshot,apply_profile
    from appearance_presets import PRESET_IDS
    from screen_layout import screen_records
    cfg=runtime.dock.cfg;original=copy.deepcopy(cfg);dialog=None
    legacy={'width':256,'height':256,'font_size':10,'area':[1536,816],'density':.8,'ui_scale':.9876543209876543}
    fixed=normalize_profile(legacy)
    assert fixed['ui_scale']==.8 and fixed['font_size']==10
    assert normalize_profile(fixed)==fixed
    screens=[{'screen':'test','area':[0,0,1536,816]}]
    sample=dict(card_scale=80,card_sizing=legacy)
    rect,factor,text=metrics(sample,[40,50,502,290],screens)
    assert factor==.8 and text==10 and font_pixels(sample,factor)==10 and rect==[40,50,502,290]
    assert new_geometry(sample,rect,screens)[2:]==[256,256]
    # Fresh installs show 10 logical pixels at the default compact density.
    fresh=dict(card_scale=70,card_sizing={})
    _,factor,text=metrics(fresh,rect,screens)
    assert text==font_pixels(fresh,factor)==10
    for size in ((1920,1020),(2560,1360),(1536,816)):
        changed=[dict(screen='test',area=[0,0,*size])]
        _,factor,text=metrics(sample,rect,changed)
        ratio=min(size[0]/1536,size[1]/816)
        assert abs(factor-.8*ratio)<1e-8 and text==max(8,round(10*ratio))
        assert font_pixels(sample,factor)==text
    try:
        cfg.update(card_sizing=fixed)
        runtime.apply_settings();panel=runtime.panels.windows[runtime.panels.active_for('apps')]
        panel.expand();panel.apply_options();app.processEvents()
        bounds=list(panel.bounds());icon=panel.list.iconSize();reference=panel.ui_factor
        def ball():
            runtime.panels.update_panel(panel.identity,fold={'style':'ball','ratio':1});panel.collapse();app.processEvents()
            size=(panel.width(),panel.height());assert size[0]==size[1]
            panel.expand();app.processEvents();return size
        compact_ball=ball()
        dialog=CardSizingDialog(runtime);dialog.show();app.processEvents()
        for font in (18,10):
            dialog.text_field.setValue(font);assert dialog.commit();app.processEvents()
            assert abs(panel.ui_factor-reference)<1e-8 and panel.list.iconSize()==icon,(panel.ui_factor,reference,panel.list.iconSize(),icon)
            assert panel.text_pixels()==font and list(panel.bounds())==bounds
            assert ball()==compact_ball
        candidate=copy.deepcopy(cfg);dialog.text_field.setValue(17)
        with patch.object(api,'save_config',return_value=False):assert not dialog.commit()
        assert cfg==candidate and panel.text_pixels()==10 and panel.ui_factor==reference
        dialog.reject();dialog.deleteLater();dialog=None
        legacy_style=snapshot(cfg);legacy_style['typography']={'font_size':10,'ui_scale':3.0}
        candidate=apply_snapshot(cfg,legacy_style)
        assert candidate['card_sizing']['ui_scale']==reference
        defaults=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
        for mode in ('default',*PRESET_IDS,'default'):
            candidate=apply_profile(cfg,mode,defaults)
            assert candidate['card_sizing']['ui_scale']==reference
            assert candidate['card_sizing']['width']==cfg['card_sizing']['width']
            assert candidate['card_sizing']['height']==cfg['card_sizing']['height']
            cfg.clear();cfg.update(candidate);runtime.apply_settings();app.processEvents()
            assert abs(panel.ui_factor-reference)<1e-8 and panel.list.iconSize()==icon,(panel.ui_factor,reference,panel.list.iconSize(),icon)
            assert ball()==compact_ball and list(panel.bounds())==bounds
        assert api.save_config(cfg);loaded=api.load_config()
        assert loaded['card_sizing']==cfg['card_sizing']
        # Use only native-rendered test icons for the visual check.
        paths=[]
        for index,color in enumerate(('#428fce','#efac40','#65bca3','#c788c9','#e67782','#8e9bd7')):
            pixmap=QPixmap(64,64);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen);painter.setBrush(QColor(color));painter.drawRoundedRect(QRectF(2,2,60,60),14,14)
            font=QFont('Segoe UI');font.setPixelSize(34);font.setWeight(QFont.DemiBold);painter.setFont(font);painter.setPen(Qt.white);painter.drawText(pixmap.rect(),Qt.AlignCenter,chr(65+index));painter.end()
            path=Path(root)/('演示应用'+chr(65+index)+'.png');assert pixmap.save(str(path));paths.append(str(path))
        assert runtime.panels.add_paths('apps',paths);panel.render();app.processEvents()
        panel.grab().save(str(Path(output)/'card-expanded-compact.png'))
        values={'ui_factor':panel.ui_factor,'text':panel.text_pixels(),'file_icon':panel.list.iconSize().width(),'header_icon':panel.header_icon.width(),'header_height':panel.header_layout.geometry().height(),'tab_height':panel.tabs.height(),'tab_widths':[panel.tabs.tabRect(i).width() for i in range(panel.tabs.count())],'expanded':list(panel.bounds()),'ball':compact_ball}
        panel.collapse();app.processEvents();panel.grab().save(str(Path(output)/'card-ball-compact.png'))
        (Path(output)/'card-density-metrics.json').write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
        checks.append('card density: inflated legacy reference repaired idempotently; default font is 10 logical pixels; file icons and round badge stay compact through shared-font save, save failure, all themes/default restore and legacy custom-style restore; width/height/position retained; synthetic screen scaling and reload validated')
    finally:
        if dialog:dialog.reject();dialog.deleteLater()
        cfg.clear();cfg.update(original);api.save_config(cfg);runtime.apply_settings();app.processEvents()
