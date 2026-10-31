"""Native Qt README scenes with public demo icons and temporary fictional data.

Run through tools/run_isolated_test.py. Does not capture the user's desktop,
change installed configuration, or launch any of the illustrated applications.
"""
import sys,copy,json,datetime,tempfile,gc
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
for directory in ('app','tests','tools'):sys.path.insert(0,str(ROOT/directory))

def run(output):
    from run_isolated_test import assert_isolated
    assert_isolated();gc.disable()
    import dock as api
    from PyQt5.QtCore import Qt,QRectF,QPoint,QSize
    from PyQt5.QtGui import QImage,QPixmap,QPainter,QColor,QLinearGradient,QRadialGradient,QPainterPath,QFont,QIcon,QImageWriter
    from PyQt5.QtWidgets import QApplication,QWidget
    from runtime_controller import RuntimeController
    from batch_import import BatchImporter,BatchDialog
    from ui_style import apply_theme,shutdown_ui
    from desktop_clock import draw_clock
    from clock_appearance import normalize as clock_options
    from glass_capture import smooth_backdrop
    from desktop_catalog import CATEGORIES
    from settings_dialog import SettingsDialog
    from dock_extras import DockQuickSettings
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app,True)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    data=ROOT/'docs/demo-assets';sources=json.loads((data/'icons.json').read_text(encoding='utf-8'))
    order=['firefox','vscode','telegram','vlc','7zip','keepassxc','git','python']
    by_key={row['key']:row for row in sources}
    icons={key:QIcon(str(data/by_key[key]['file'])).pixmap(256,256) for key in order}
    assert all(not pixmap.isNull() for pixmap in icons.values())
    for key,pixmap in icons.items():
        if pixmap.width()<96:raise ValueError('Demo icon is too small: '+key)
    now=datetime.datetime(2026,10,30,17,17)
    generated=[];runtime=None;dock=None
    def settle():
        for _ in range(5):app.processEvents()
    def background(width,height):
        image=QImage(width*2,height*2,QImage.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(2);image.fill(Qt.transparent)
        p=QPainter(image);p.setRenderHint(QPainter.Antialiasing)
        clip=QPainterPath();clip.addRoundedRect(QRectF(0,0,width,height),20,20);p.setClipPath(clip)
        gradient=QLinearGradient(0,0,width,height);gradient.setColorAt(0,QColor('#119fd7'));gradient.setColorAt(.48,QColor('#2879d5'));gradient.setColorAt(1,QColor('#4b37a8'));p.fillRect(QRectF(0,0,width,height),gradient)
        glow=QRadialGradient(width*.15,height*.12,width*.82);glow.setColorAt(0,QColor(91,226,245,130));glow.setColorAt(1,QColor(42,100,230,0));p.fillRect(QRectF(0,0,width,height),glow)
        for offset,alpha in ((0,36),(.12,29),(.25,22)):
            path=QPainterPath();path.moveTo(width*(.56+offset),-80)
            path.cubicTo(width*(.43+offset),height*.38,width*(.98+offset),height*.32,width*(.59+offset),height*1.2)
            path.lineTo(width*1.35,height*1.2);path.lineTo(width*1.35,-80);path.closeSubpath()
            grad=QLinearGradient(width*.5,0,width,height);grad.setColorAt(0,QColor(181,228,255,alpha));grad.setColorAt(.6,QColor(210,197,255,alpha));grad.setColorAt(1,QColor(129,105,239,0))
            p.fillPath(path,grad)
        p.end();return image
    def label(image,x,y,text,size=18,color='#ffffff'):
        p=QPainter(image);font=QFont('Microsoft YaHei UI');font.setPixelSize(size);font.setWeight(QFont.DemiBold);p.setFont(font);p.setPen(QColor(color));p.drawText(QRectF(x,y,image.width()/2-x,40),Qt.AlignLeft|Qt.AlignVCenter,text);p.end()
    def save(image,name):
        path=output/name;assert image.save(str(path),'PNG',0);generated.append(name)
    def backdrop(image,x,y,width,height,blur=8):
        cropped=image.copy(round(x*2),round(y*2),round(width*2),round(height*2));cropped.setDevicePixelRatio(2)
        return smooth_backdrop(QPixmap.fromImage(cropped),blur)
    def widget_on(image,widget,x,y,resize=None,glass=True):
        if resize:
            widget.setMinimumSize(1,1);widget.setMaximumSize(16777215,16777215);widget.resize(*resize)
        widget.show();settle()
        if hasattr(widget,'refresh_timer'):widget.refresh_timer.stop()
        if hasattr(widget,'geometry_timer'):widget.geometry_timer.stop()
        if hasattr(widget,'fit_timer'):widget.fit_timer.stop()
        if hasattr(widget,'resize_timer'):widget.resize_timer.stop()
        if glass and hasattr(widget,'backdrop'):widget.backdrop=backdrop(image,x,y,widget.width(),widget.height())
        widget.update();settle()
        p=QPainter(image);p.save();p.translate(x,y);QWidget.render(widget,p);p.restore();p.end()
    def clock_on(image,x,y,width,height,style='orbit',clear=False):
        settings=clock_options(dict(material='clear' if clear else 'liquid',theme='light',color='#cee9fc',opacity=0 if clear else 32,blur=10,highlight=0 if clear else 32,
            font='Segoe UI',font_scale=110,text_color='#ffffff',auto_contrast=False,accent_color='#e1f6ff',font_weight=63,
            bar_width=11,ring_width=11,corner_radius=22,work={'start':'08:30','end':'18:00'}))
        settings['_now']=now
        p=QPainter(image);draw_clock(p,QRectF(x,y,width,height),dock,settings,style,None if clear else backdrop(image,x,y,width,height));p.end()
    try:
        with tempfile.TemporaryDirectory(prefix='bigfish-readme-') as folder:
            root=Path(folder);api.CONFIG_DIR=folder;api.CONFIG_PATH=str(root/'config.json');api.LOG_PATH=str(root/'dock.log')
            entries=[]
            for key in order:
                path=root/(key+'.exe');path.write_bytes(b'demo reference, never executed')
                entries.append(dict(path=str(path),name=by_key[key]['name'],icon=str(data/by_key[key]['file']),group='演示应用'))
            items=entries[:3]+[{'sep':True}]+entries[3:6]+[{'sep':True}]+entries[6:]
            cfg=copy.deepcopy(api.DEFAULT_CONFIG)
            cfg.update(items=items,icon_size=64,theme='light',theme_color='#b8dff5',dock_material='liquid',dock_highlight=36,transparency=100,glass=True,blur_px=9,
                running_dots=False,hide_tray=True,check_updates_on_start=False,lite_enabled=False,screen_corners=False,desktop_middle_toggle=False,
                panel_enabled=True,panels_visible=True,panel_auto_hide=False,panel_locked=False,panel_opacity=28,panel_blur=10,panel_highlight=40,panel_theme='light',panel_material='liquid',
                panel_color='#cee9fc',desktop_auto_sort=False,desktop_icon_mode='both',card_scale=100,settings_size='medium',card_design='aurora',
                merged_panels=True,merge_initialized=True,merged_active='apps',merged_geometry=[100,100,740,370],merged_compact=False,
                desktop_panels=[dict(id=key,name=name,enabled=True,merged=True,merge_group='default',compact=False,geometry=[100,100,740,370]) for key,name in CATEGORIES],
                desktop_entries=[dict(path=item['path'],name=item['name'],source='manual',panel='apps') for item in entries],notes_enabled=False,clock_enabled=False,calendar_enabled=False)
            cfg=api.normalize_features(cfg);api.save_config(cfg)
            base_get=api.IconProvider.get
            def icon_get(provider,path,pixels,*args,**kwargs):
                key=Path(path).stem
                if key in icons:return icons[key]
                if str(path).lower().endswith('.png') and Path(path).parent==root:return QPixmap(str(path))
                return base_get(provider,path,pixels,*args,**kwargs)
            with patch.object(api.IconProvider,'get',icon_get):
                dock=api.Dock(cfg,preview=True);tray=api.DockTray(dock);dock.tray=tray
                tray.importer=BatchImporter(dock,tray,api.save_config)
                runtime=tray.runtime=RuntimeController(dock,tray,api)
                panel=runtime.panels.windows['apps'];panel.ui_factor=1.0;panel.apply_options();panel.collapse_timer.stop()
                # Three real note materials with fictional, reusable content.
                notes=[]
                for title,style,color,html in [
                    ('今日灵感','glass','#cfe8fa','<p><b>给桌面留一点呼吸</b></p><p>把常用的放在手边，<br>把重要的记录下来。</p><p>☐ 整理本周资料<br>☑ 留出阅读时间</p>'),
                    ('本周清单','paper','#fff1c9','<p><b>让计划变得简单</b></p><p>☑ 清理下载目录<br>☐ 完成一次专注阅读<br>☐ 整理灵感与素材</p>'),
                    ('阅读摘记','plain','#e8eaf7','<p><b>少一点切换，多一点专注。</b></p><p>随手写下一个想法，<br>让工作与生活各得其所。</p>')]:
                    identity=runtime.notes.new();runtime.notes.update(identity,title=title,style=style,color=color,html=html,text=title,body_font_size=16,body_font_scale=1.0)
                    runtime.notes.flush();note=runtime.notes.windows[identity];note.loading=True;note.title.setText(title);note.editor.setHtml(html);note.loading=False;note.apply_style();notes.append(note)
                # Desktop overview, close to the user's reference composition.
                scene=background(1920,1080)
                clock_on(scene,520,48,880,305,clear=True)
                widget_on(scene,notes[0],105,452,(315,295))
                widget_on(scene,panel,480,396,(820,390))
                clock_on(scene,1370,426,420,342,'calendar_card')
                dock.resize(dock.total_size());dock._recalc(uniform=True)
                widget_on(scene,dock,(1920-dock.width())//2,830,None)
                save(scene,'readme-desktop.png')
                # Dock comparison: same official icons, actual segmented renderer.
                scene=background(1440,610);label(scene,62,38,'轻透液态 · 分组与图标倒影',20)
                dock.cfg.update(clear_background=False,dock_material='liquid');dock.reload();dock.show();settle()
                widget_on(scene,dock,(1440-dock.width())//2,105)
                label(scene,62,285,'全透明 · 保留图标与快捷操作',20)
                dock.cfg.update(clear_background=True,dock_material='clear');dock.reload();widget_on(scene,dock,(1440-dock.width())//2,335,glass=False)
                save(scene,'readme-dock.png');dock.cfg.update(clear_background=False,dock_material='liquid');dock.reload()
                # Collections and a separate real thumbnail panel.
                image_rows=[]
                for i,name in enumerate(('海岸','晴空','暮色','远山')):
                    path=root/(name+'.png');art=background(420,280)
                    p=QPainter(art);p.setPen(Qt.NoPen);p.setBrush(QColor(['#ceeaf5','#f0dcbd','#bdbde8','#9cd0c3'][i]));p.drawEllipse(QRectF(230,30,70,70))
                    path_shape=QPainterPath();path_shape.moveTo(0,280);path_shape.lineTo(0,220);path_shape.cubicTo(110,100,150,210,260,150);path_shape.lineTo(420,230);path_shape.lineTo(420,280);path_shape.closeSubpath();p.setBrush(QColor('#537eac'));p.drawPath(path_shape);p.end();art.save(str(path))
                    image_rows.append(dict(path=str(path),name=name+'.png',source='manual',panel='images'))
                cfg['desktop_entries']+=image_rows
                next(row for row in cfg['desktop_panels'] if row['id']=='images')['merged']=False
                runtime.panels.sync_windows();panel=runtime.panels.windows[runtime.panels.active_for('apps')];pictures=runtime.panels.windows['images']
                scene=background(1440,740);label(scene,55,30,'分类收纳 · 合并切换',20);widget_on(scene,panel,50,92,(810,400))
                label(scene,930,30,'独立图片面板',20);widget_on(scene,pictures,920,92,(460,310))
                cfg['desktop_panels'].append(dict(id='fold-demo',name='灵感素材',merged=False,enabled=True,compact=False,geometry=[100,100,400,250],fold=dict(style='capsule',ratio=65)))
                runtime.panels.sync_windows();fold=runtime.panels.windows['fold-demo'];fold.set_collapsed_geometry(True)
                label(scene,80,560,'胶囊收起',18);widget_on(scene,fold,80,610)
                cfg['desktop_panels'][-1]['fold']=dict(style='ball',ratio=1);fold.set_collapsed_geometry(True)
                label(scene,600,560,'圆球收起',18);widget_on(scene,fold,620,610)
                save(scene,'readme-panels.png')
                # Notes retain native text layout, title controls and their three materials.
                scene=background(1440,550)
                for i,(note,title) in enumerate(zip(notes,('液态玻璃','经典纸张','极简纯色'))):
                    label(scene,75+i*460,34,title,20);widget_on(scene,note,65+i*460,105,(390,350),glass=i==0)
                save(scene,'readme-notes.png')
                scene=background(1440,900)
                for title,x,y,w,h,style,clear in [('时光进度',45,30,865,300,'orbit',True),('独立日历',980,30,410,365,'calendar_card',False),
                    ('现代数字',45,465,410,240,'digital',False),('现代表盘',515,465,410,240,'analog',False),('纵向时间',985,465,410,300,'stacked',False)]:
                    label(scene,x+8,y,title,19);clock_on(scene,x,y+58,w,h,style,clear)
                save(scene,'readme-clocks.png')
                # Real settings and real quick grid, not hand-drawn UI replicas.
                scene=background(1440,920);main=SettingsDialog(tray,api);main.reveal();main.resize(855,690);settle()
                widget_on(scene,main,40,100,None,False)
                popup=DockQuickSettings(dock.extras);popup.refresh();widget_on(scene,popup,995,170,None,False)
                label(scene,60,35,'轻透分组设置',22);label(scene,1005,100,'快捷设置',22)
                save(scene,'readme-settings.png');popup.close();popup.deleteLater();main.reject();main.deleteLater()
                with patch('batch_import.discover_apps',return_value=[dict(path=e['path'],name=e['name'],source='演示应用',column='apps') for e in entries]):
                    dialog=BatchDialog(tray.importer)
                    from desktop_panel_tests import wait_for
                    wait_for(app,lambda:not dialog.worker.isRunning())
                    dialog.discovered([dict(path=e['path'],name=e['name'],source='演示应用',column='apps') for e in entries]);dialog.tabs.setCurrentIndex(1);dialog.render()
                    wait_for(app,lambda:not dialog.icon_timer.isActive())
                    scene=background(1440,820);label(scene,285,35,'批量管理 · 常用应用',22);widget_on(scene,dialog,285,100,(870,630),False)
                    save(scene,'readme-apps.png');dialog.reject();dialog.worker.wait(3000);dialog.worker.deleteLater();dialog.deleteLater()
                runtime.close();runtime=None;dock.hide();dock.deleteLater();dock=None;settle()
        (output/'result.json').write_text(json.dumps(dict(passed=True,images=generated,source='native Qt components and original synthetic wallpaper; public demo icons only',limits='documentation rendering only; no production configuration changes'),ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        import traceback
        (output/'result.json').write_text(json.dumps(dict(passed=False,error=traceback.format_exc()),ensure_ascii=False,indent=2),encoding='utf-8');raise
    finally:
        if runtime:runtime.close()
        shutdown_ui(app)
    return 0

if __name__=='__main__':raise SystemExit(run(sys.argv[-1]))
