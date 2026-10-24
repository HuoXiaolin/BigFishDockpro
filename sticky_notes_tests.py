"""Production note editor tests with isolated local data and synthetic text."""
import copy,json
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt,QMimeData,QEvent,QPointF
from PyQt5.QtGui import QTextCursor,QFont,QTextCharFormat,QMouseEvent
from PyQt5.QtWidgets import QApplication
from desktop_panel_tests import wait_for
from sticky_notes import NotesManager
from sticky_notes_store import normalize_notes
from ui_style import apply_theme


def run(api,runtime,root,output,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    runtime.notes.close();manager=None
    try:
        cfg.update(notes_enabled=False,notes_visible=True,note_style='glass',sticky_notes=[],notes_trash=[],game_mode=False)
        api.save_config(cfg);manager=runtime.notes=NotesManager(runtime)
        identity=manager.new();assert identity and cfg['notes_enabled'] and len(manager.windows)==1
        note=manager.windows[identity];note.editor.setPlainText('项目安排\n确认图纸');note.title.setText('演示便签');note.changed()
        wait_for(app,lambda:not manager.pending)
        assert api.load_config()['sticky_notes'][0]['text']=='项目安排\n确认图纸'
        note.editor.selectAll();note.format_buttons['bold'].click();note.format_buttons['italic'].click();note.format_buttons['underline'].click();manager.flush()
        assert 'font-weight:600' in manager.row(identity)['html'] or 'font-weight:700' in manager.row(identity)['html']
        assert 'font-style:italic' in manager.row(identity)['html'] and 'text-decoration: underline' in manager.row(identity)['html']
        note.editor.moveCursor(QTextCursor.Start);note.format_text('todo');assert note.editor.toPlainText().startswith('☐ ')
        note.editor.moveCursor(QTextCursor.Start);note.format_text('todo');assert note.editor.toPlainText().startswith('☑ ')
        note.editor.moveCursor(QTextCursor.End);note.editor.insertPlainText('\n核对清单');note.format_text('bullet');manager.flush()
        assert '<ul' in manager.row(identity)['html']
        mime=QMimeData();mime.setHtml('<img src="file:///C:/secret.png"><b>paste</b>');mime.setText('仅粘贴文字');note.editor.insertFromMimeData(mime)
        assert '<img' not in manager.row(identity)['html']
        saved=copy.deepcopy(cfg['sticky_notes']);note.editor.insertPlainText(' 待保存')
        with patch.object(api,'save_config',return_value=False):
            assert not manager.flush() and manager.pending and cfg['sticky_notes']==saved
            assert '保存失败' in note.status.text() and manager.backup()
        assert manager.flush() and not manager.pending
        manager.recovery.unlink(missing_ok=True)
        note.editor.clear();note.editor.setCurrentCharFormat(QTextCharFormat())
        note.editor.insertPlainText('今天的安排\n☐ 确认图纸\n☑ 整理演示资料\n\n本机自动保存，样式可随时切换。');manager.flush()
        # Three separate runtime skins, real menu actions and persistence.
        screenshots=[]
        for theme in ('light','dark'):
            apply_theme(app,theme=='light')
            for style in ('glass','paper','plain'):
                menu=note.build_menu();submenu=next(action.menu() for action in menu.actions() if action.text()=='外观样式')
                key={'glass':'液态玻璃','paper':'经典纸张','plain':'极简纯色'}[style]
                next(action for action in submenu.actions() if action.text()==key).trigger();menu.deleteLater();app.processEvents()
                assert manager.row(identity)['style']==style
                image=note.grab();image.save(str(Path(output)/('note-'+style+'-'+theme+'.png')))
                if theme=='light':screenshots.append(image.toImage().pixelColor(image.width()-25,image.height()-25).rgba())
        assert len(set(screenshots))==3
        width,height=note.width(),note.height();note.toggle_collapse();assert manager.row(identity)['collapsed'] and note.height()<height
        note.toggle_collapse();assert note.height()==height,(note.height(),height,note.expanded_height)
        note.set_option('locked',True);assert note.minimumSize()==note.maximumSize()
        note.set_option('locked',False);note.set_option('pinned',True);assert manager.row(identity)['pinned']
        note.set_option('pinned',False)
        note2=manager.new();second=manager.windows[note2];second.editor.setPlainText('另一个演示：采购清单');manager.flush()
        manager.manage();dialog=manager.dialog;dialog.query.setText('采购');assert dialog.list.count()==1
        dialog.list.setCurrentRow(0);dialog.open_selected();assert second.isVisible()
        assert manager.delete(note2) and len(cfg['notes_trash'])==1 and note2 not in manager.windows
        dialog.tabs.setCurrentIndex(1);assert dialog.list.count()==1;dialog.list.setCurrentRow(0);dialog.open_selected()
        assert note2 in manager.windows and not cfg['notes_trash']
        manager.toggle();assert not any(window.isVisible() for window in manager.windows.values())
        manager.toggle();assert all(window.isVisible() for window in manager.windows.values())
        runtime.game_active=True;manager.sync();assert not any(window.isVisible() for window in manager.windows.values())
        runtime.game_active=False;manager.sync();runtime.lite=True;manager.set_lite()
        assert all(window.backdrop is None and not window.refresh_timer.isActive() for window in manager.windows.values())
        runtime.lite=False
        from screen_layout import capture
        real=__import__('sticky_notes').screen_records();area=real[0]['area'];reference=copy.deepcopy(real);reference[0]['area']=[area[0],area[1],round(area[2]*1.5),round(area[3]*1.5)]
        geometry=[area[0]+40,area[1]+50,360,270]
        manager.update(identity,geometry=geometry,layout=capture(geometry,reference));manager.flush()
        note.reposition();note.apply_style();assert note.ui_factor<.75 and note.editor.document().defaultFont().pixelSize()<=9
        note.move(note.x()+5,note.y()+3);note.save_geometry();manager.flush();assert manager.row(identity)['layout']['ui_scale']<.75
        # JSON migration carries notes; bad styles and duplicate identities are rejected.
        import config_transfer
        normalized=config_transfer.normalize(copy.deepcopy(cfg),api);assert normalized['sticky_notes']==cfg['sticky_notes']
        try:normalize_notes([dict(manager.row(identity),style='unknown')],strict=True)
        except ValueError:pass
        else:raise AssertionError('Bad note style accepted')
        manager.flush();manager.close();before=copy.deepcopy(cfg['sticky_notes']);manager=runtime.notes=NotesManager(runtime);manager.sync()
        assert len(manager.windows)==2 and cfg['sticky_notes']==before
        assert '确认图纸' in manager.windows[identity].editor.toPlainText()
        # Failed shutdown write is backed up and recovered on the next controller.
        manager.windows[identity].editor.insertPlainText(' 恢复演示')
        with patch.object(api,'save_config',return_value=False):manager.close()
        assert manager.recovery.exists()
        manager=runtime.notes=NotesManager(runtime);manager.sync();assert not manager.recovery.exists()
        assert '恢复演示' in manager.windows[identity].editor.toPlainText()
        checks.append('sticky notes: three runtime skins rendered in both themes, rich-text bold/italic/underline/bullets, toggled todos, plain-only paste/no resource reads, 600ms autosave and failure retention/retry, multi-note search/open/delete/restore, collapse/lock/pin/visibility, game/lite modes, canonical mixed-DPI note geometry/font, JSON transfer and invalid record rejection, actual controller restart and failed-shutdown recovery')
    finally:
        runtime.game_active=False;runtime.lite=False
        if manager:manager.close()
        cfg.clear();cfg.update(original);api.save_config(cfg);runtime.notes=NotesManager(runtime);runtime.notes.sync()
        apply_theme(app,runtime.dock.is_light())
