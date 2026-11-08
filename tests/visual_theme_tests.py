"""Native material previews and finite-motion checks on the private test desktop."""
import copy
import datetime
import json
from pathlib import Path
from types import SimpleNamespace


def run(api, runtime, main, app, output, checks):
    from run_isolated_test import assert_isolated
    assert_isolated()
    from PyQt5.QtCore import Qt, QRectF, QEvent
    from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPainterPath, QLinearGradient
    from PyQt5.QtWidgets import QWidget
    from ui_test_events import Events as QTest
    from appearance_presets import NEW_PRESET_IDS, PRESET_IDS, PANEL_PRESETS, DOCK_PRESETS
    from appearance_profiles import apply_profile, snapshot, clean_snapshot, selected_mode
    from clock_appearance import STYLES, normalize
    from desktop_clock import draw_clock
    from liquid_glass import material_palette, tint_palette, paint_liquid_glass
    from card_design import paint_design
    from glass_panel import category_icon
    from interaction_motion import attach
    output=Path(output)
    defaults=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG))
    original=copy.deepcopy(defaults)
    original.update(theme_color='#2b789a',clock_style='orbit',card_design='paper',items=[{'path':'shell:Downloads','name':'下载'}])
    original['clock_appearance'].update(font_scale=147,design='minimal',layout='portrait')
    original['clock_appearance']['work']['start']='08:45'
    custom=snapshot(original);original['appearance_custom']=custom
    assert clean_snapshot(custom)==custom
    assert PRESET_IDS==('crystal','liquid','flowing','vivid','paper_glass','transparent')
    liquid=DOCK_PRESETS[PRESET_IDS.index('liquid')][1]
    assert liquid['dock_highlight']==36 and liquid['transparency']==100
    configs=[]
    for mode in NEW_PRESET_IDS:
        cfg=apply_profile(original,mode,defaults)
        cfg.update(appearance_mode=mode,appearance_applied=snapshot(cfg))
        assert selected_mode(cfg)==mode
        assert clean_snapshot(json.loads(json.dumps(snapshot(cfg))))==snapshot(cfg)
        assert snapshot(apply_profile(cfg,'custom',defaults))==custom
        assert cfg['clock_appearance']['work']==original['clock_appearance']['work'] and cfg['items']==original['items']
        assert cfg['dock_material']==cfg['panel_material']==cfg['note_appearance']['material']==cfg['clock_appearance']['material']==cfg['calendar_appearance']['material']==mode
        configs.append(cfg)
        assert material_palette(runtime.dock.base_theme_colors('dark'),mode)['fg'].name()=='#ffffff'
        assert material_palette(runtime.dock.base_theme_colors('light'),mode)['fg'].hsvSaturationF()>.4
    reset=apply_profile(original,'default',defaults)
    assert reset['card_design']=='crystal' and reset['dock_material']=='crystal' and reset['clock_style']=='digital'
    assert reset['clock_appearance']['layout']=='auto' and reset['clock_appearance']['text_effect']=='clear'

    def make_dock(cfg):
        dock=SimpleNamespace(cfg=cfg,_sys_light=True)
        dock.base_theme_colors=lambda theme=None:api.Dock.base_theme_colors(dock,theme)
        dock._stop_alpha=api.Dock._stop_alpha
        dock.merged_grad_stops=lambda colors:api.Dock.merged_grad_stops(dock,colors)
        return dock

    def backdrop(width,height):
        image=QPixmap(width,height);p=QPainter(image)
        fill=QLinearGradient(0,0,width,height)
        fill.setColorAt(0,QColor('#259aca'));fill.setColorAt(.58,QColor('#539cc6'));fill.setColorAt(1,QColor('#487eae'))
        p.fillRect(image.rect(),fill);p.end();return image

    def surface(dock,width,height,kind):
        image=QImage(width,height,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
        p=QPainter(image);p.setRenderHint(QPainter.Antialiasing);p.setRenderHint(QPainter.TextAntialiasing)
        rect=QRectF(1,1,width-2,height-2);shape=QPainterPath();shape.addRoundedRect(rect,18,18)
        cfg=dock.cfg;material=cfg['panel_material'];colors=material_palette(tint_palette(dock.base_theme_colors(cfg['panel_theme']),cfg['panel_color']),material)
        strength=cfg['panel_highlight']/45
        stops=[(pos,round(alpha*strength)) for pos,alpha in dock.merged_grad_stops(colors)]
        panel=SimpleNamespace(cfg={'glass':True,'dock_material':material},backdrop=backdrop(width,height),spec_x=width*.5,spec_alpha=0)
        paint_liquid_glass(panel,p,shape,rect,rect,colors,round(cfg['panel_opacity']*2.55),stops)
        if kind!='dock':paint_design(p,rect,cfg,body_top=43,corner_radius=18)
        p.setPen(colors['fg']);font=QFont('Microsoft YaHei UI');font.setPixelSize(13);p.setFont(font)
        if kind=='dock':
            for index,category in enumerate(('apps','folders','documents','images','media','archives')):
                p.drawPixmap(20+index*45,16,category_icon(category,('#357ba4','#bd8c31','#379c90','#8c6cb0','#bd6385','#a37642')[index],26,2))
        elif kind=='panel':
            p.drawPixmap(14,12,category_icon('documents','#379c90',17,2));p.drawText(QRectF(39,8,width-55,25),'文档')
            p.setPen(QColor('#000000'))
            for index,title in enumerate(('项目说明','设计参考','工作计划')):
                x=27+index*93;p.drawPixmap(x+14,58,category_icon('documents','#379c90',28,2));p.drawText(QRectF(x-4,96,77,38),Qt.AlignHCenter|Qt.TextWordWrap,title)
        else:
            p.drawText(QRectF(16,10,width-32,25),'今日便签')
            p.setPen(QColor('#000000'))
            p.drawText(QRectF(18,50,width-36,50),Qt.TextWordWrap,'整理桌面，留出专注空间。\n下午完成项目说明。')
        p.end();return image

    sheet=QImage(1100,1048,QImage.Format_RGB32);sheet.fill(QColor('#f0f5f8'));p=QPainter(sheet)
    widths=340;xs=(24,380,736);names=[PANEL_PRESETS[PRESET_IDS.index(mode)][0] for mode in NEW_PRESET_IDS]
    p.setPen(QColor('#18354b'));font=QFont('Microsoft YaHei UI');font.setPixelSize(19);font.setWeight(QFont.DemiBold);p.setFont(font)
    for x,name in zip(xs,names):p.drawText(QRectF(x,15,widths,30),name)
    signatures=[]
    for x,cfg,mode in zip(xs,configs,NEW_PRESET_IDS):
        dock=make_dock(cfg)
        for y,height,kind in ((60,62,'dock'),(140,158,'panel'),(316,120,'note')):
            image=surface(dock,widths,height,kind);p.drawImage(x,y,image)
            if kind=='panel':signatures.append(image.pixelColor(170,140).rgba())
        for y,height,style in ((454,190,'orbit'),(662,360,'calendar_card')):
            image=QImage(widths,height,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
            q=QPainter(image)
            options=normalize(cfg['clock_appearance']);options.update(layout='wide',_now=datetime.datetime(2026,11,5,14,35),_calendar_year=2026,_calendar_month=11,_text_audit=[])
            draw_clock(q,QRectF(0,0,widths,height),dock,options,style,backdrop(widths,height));q.end()
            assert options['_text_audit'] and all(size>=8 and alpha>=235 for _,size,_,alpha,_ in options['_text_audit'])
            p.drawImage(x,y,image)
        faces=QImage(1052,488,QImage.Format_RGB32);faces.fill(QColor('#f0f5f8'));face_painter=QPainter(faces)
        for index,(_,style) in enumerate(STYLES):
            tile=QImage(336,224,QImage.Format_ARGB32_Premultiplied);tile.fill(Qt.transparent);q=QPainter(tile)
            options=normalize(cfg['clock_appearance']);options['_now']=datetime.datetime(2026,11,5,14,35)
            draw_clock(q,QRectF(0,0,336,224),dock,options,style,backdrop(336,224));q.end()
            face_painter.drawImage(10+(index%3)*348,10+(index//3)*238,tile)
        face_painter.end();assert faces.save(str(output/('visual-clock-'+mode+'.png')))
    p.end();assert len(set(signatures))==3
    for theme in ('light','dark'):
        crystal,flowing=(surface(make_dock(dict(cfg,panel_theme=theme)),340,158,'panel').pixelColor(170,140)
                         for cfg in configs[:2])
        assert flowing.red()-crystal.red()>=18 and flowing.green()<crystal.green(),(theme,crystal.name(),flowing.name())
    assert sheet.save(str(output/'visual-themes.png'))

    # Small progress cards keep each period label separate from its percentage.
    compact=QImage(1080,550,QImage.Format_RGB32);compact.fill(QColor('#f0f5f8'));cp=QPainter(compact)
    for index,(width,height) in enumerate(((336,224),(340,265),(520,250),(240,250))):
        cfg=configs[0];dock=make_dock(cfg)
        tile=QImage(width,height,QImage.Format_ARGB32_Premultiplied);tile.fill(Qt.transparent);tp=QPainter(tile)
        audit=[];options=normalize(cfg['clock_appearance']);options.update(_now=datetime.datetime(2026,11,5,14,35),_text_audit=audit)
        draw_clock(tp,QRectF(0,0,width,height),dock,options,'orbit',backdrop(width,height));tp.end()
        for i,entry in enumerate(audit):
            if entry[0] in ('本周','本月','本年'):
                current=QRectF(*entry[4]);following=QRectF(*audit[i+1][4])
                assert not current.intersects(following),(width,height,entry,audit[i+1])
        x,y=((10,10),(360,10),(10,290),(550,290))[index];cp.drawImage(x,y,tile)
    cp.end();assert compact.save(str(output/'visual-orbit-small.png'))

    # Preserve the requested progress face: ring left, work right, three bottom tiles.
    from clock_legibility import monochrome
    assert monochrome([QColor('#102b57')]).name()=='#ffffff'
    assert monochrome([QColor('#e8f0f6')]).name()=='#000000'
    comparison=QImage(1280,316,QImage.Format_RGB32);comparison.fill(QColor('#f0f5f8'));cp=QPainter(comparison)
    for index,(background,expected) in enumerate((('#1763c9',True),('#e8f0f6',False))):
        tile=QImage(624,280,QImage.Format_ARGB32_Premultiplied);tile.fill(QColor(background));tp=QPainter(tile)
        wallpaper=QPixmap(624,280);wallpaper.fill(QColor(background));audit=[]
        options=normalize(configs[0]['clock_appearance']);options.update(material='clear',opacity=0,highlight=0,design='crystal',layout='auto',accent_color='#ff755e',_now=datetime.datetime(2026,11,5,21,12),_text_audit=audit)
        options['work'].update(start='08:30',end='18:00')
        draw_clock(tp,QRectF(0,0,624,280),make_dock(configs[0]),options,'orbit',wallpaper);tp.end()
        from clock_legibility import contrast
        assert all(alpha==255 and (QColor(color).lightness()>150)==expected
                   and contrast(QColor(color),QColor(background))>=4.5 for _,_,color,alpha,_ in audit)
        texts={value:QRectF(*box) for value,_,_,_,box in audit}
        assert texts['21:12'].center().x()<texts['11月5日'].left()
        periods=[texts[name] for name in ('本周','本月','本年')]
        assert periods[0].left()<periods[1].left()<periods[2].left() and max(r.top() for r in periods)-min(r.top() for r in periods)<1
        assert min(r.top() for r in periods)>texts['21:12'].bottom()
        cp.drawImage(8+index*636,24,tile)
    cp.end();assert comparison.save(str(output/'clock-progress-colors.png'))
    checks.append('requested clock layout retained at 624x280: left ring, right work card and three bottom period tiles; actual dark surfaces render white opaque text; light surfaces use saturated theme ink')

    # Real QWidget events on the isolated desktop, with finite animation lifetime.
    cfg={'motion_enabled':True};window=QWidget();window.resize(200,120)
    motion=attach(window,lambda:cfg)
    try:
        window.show();app.processEvents();motion.stop()
        assert motion.trigger('tab')
        QTest.qWait(380)
        assert motion.progress is None and motion.animation.state()==motion.animation.Stopped
        assert motion.trigger();window.hide();app.processEvents()
        assert motion.progress is None and motion.animation.state()==motion.animation.Stopped
        cfg['motion_enabled']=False;window.show();app.processEvents()
        assert not motion.trigger() and motion.animation.state()==motion.animation.Stopped
        assert attach(window,lambda:cfg) is motion
    finally:
        motion.stop();window.close();window.deleteLater();app.processEvents()
    checks.append('three native shared themes: Dock/card/note/clock/calendar material agreement; all six clock styles rendered; legacy material values remain valid; custom snapshot roundtrips preserve content/work/layout; default restores crystal/digital; actual isolated QWidget finite-motion finish/hide/off checks, no idle timer or foreground capture')
