"""Selected-file keyboard, transactional rename and three-line card checks."""
import copy
from pathlib import Path
from unittest.mock import patch,MagicMock
from PyQt5.QtCore import Qt,QEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication,QMessageBox
from app_catalog import path_key


def run(api,runtime,root,checks,output):
    from desktop_panels import DesktopPanels
    from card_file_ui import file_name_lines,extract_card_hicon
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    previous=runtime.panels;roots=list(previous.roots);previous.close();manager=None
    fixture=Path(root)/'card-file-actions';fixture.mkdir()
    first=fixture/'三行文件名自动换行示例文档与很长的英文filename-example.txt';first.write_text('unchanged',encoding='utf-8')
    conflict=fixture/'collision.txt';conflict.write_text('keep',encoding='utf-8')
    try:
        cfg.update(panel_enabled=True,panels_visible=True,desktop_auto_sort=False,merged_panels=False,
                   panel_auto_hide=False,panel_locked=False,disabled_categories=[],desktop_excluded=[],desktop_entries=[],
                   desktop_panels=[{'id':'documents','name':'文档','geometry':[100,80,400,320]},
                                   {'id':'other','name':'其他','geometry':[600,80,320,260]}])
        assert api.save_config(cfg)
        manager=runtime.panels=DesktopPanels(runtime,roots=[str(fixture)]);manager.apply_settings()
        assert manager.add_paths('documents',[str(first),str(conflict)]) and manager.add_paths('other',[str(first)])
        manager.pin_entries({path_key(str(first))},True,'documents')
        panel=manager.windows['documents']
        def select(path):
            panel.list.clearSelection()
            for i in range(panel.list.count()):
                item=panel.list.item(i)
                if path_key(item.data(Qt.UserRole)['path'])==path_key(str(path)):item.setSelected(True);panel.list.setCurrentItem(item);return item
            raise AssertionError('fixture not listed: '+str(path))
        select(first)
        from shell_file_clipboard import paste_popup_point
        import ctypes
        from ctypes import wintypes
        bounds=wintypes.RECT()
        user=ctypes.windll.user32
        user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        assert user.GetWindowRect(int(panel.winId()),ctypes.byref(bounds))
        point=paste_popup_point(int(panel.winId()))
        assert (point.x,point.y)==((bounds.left+bounds.right)//2,(bounds.top+bounds.bottom)//2)
        assert (point.x,point.y)!=(0,0)
        # A secondary monitor can have negative screen coordinates.
        class NativeCall:
            def __init__(self,callback):self.callback=callback
            def __call__(self,*args):return self.callback(*args)
        class User:
            GetWindowRect=NativeCall(lambda hwnd,out: set_bounds(out))
            GetCursorPos=NativeCall(lambda out: set_cursor(out))
        def set_bounds(out):
            rect=ctypes.cast(out,ctypes.POINTER(wintypes.RECT)).contents
            rect.left=-1800;rect.top=180;rect.right=-1200;rect.bottom=580
            return 1
        def set_cursor(out):
            pt=ctypes.cast(out,ctypes.POINTER(wintypes.POINT)).contents;pt.x=725;pt.y=416
            return 1
        with patch('shell_file_clipboard.ctypes.WinDLL',return_value=User()):
            pt=paste_popup_point(1);assert (pt.x,pt.y)==(-1500,380)
            pt=paste_popup_point(0);assert (pt.x,pt.y)==(725,416)
        checks.append('native paste popup coordinates: real card HWND center in Windows screen units, negative monitor coordinates and cursor fallback; no fixed screen origin')
        # RDP data objects need not expose any local URLs to Qt.
        from PyQt5.QtCore import QMimeData
        class Clipboard:
            def mimeData(self):return QMimeData()
            def clear(self):raise AssertionError('Remote clipboard must remain owned by Windows')
        with patch('glass_panel.QApplication.clipboard',return_value=Clipboard()),patch('shell_file_clipboard.preferred_effect',return_value=1),patch('shell_file_clipboard.paste_shell_clipboard',return_value='shell-submitted') as receive:
            assert panel.paste_files()
            assert receive.call_args.args[:2]==(str(fixture),int(panel.winId()))
            assert panel.paste_files(str(fixture))
        with patch('glass_panel.QApplication.clipboard',return_value=Clipboard()),patch('shell_file_clipboard.preferred_effect',return_value=1),patch('shell_file_clipboard.paste_shell_clipboard',return_value='cancelled'):
            assert not panel.paste_files()
        checks.append('remote clipboard card routing: no Qt local URLs reaches Shell receiver for desktop and folder destinations; cancellation handled; clipboard never cleared')
        with patch.object(panel,'rename_file') as rename,patch.object(panel,'shell_file_action') as native,patch.object(panel,'launch_item') as launch:
            for key,mods in [(Qt.Key_F2,Qt.NoModifier),(Qt.Key_Delete,Qt.NoModifier),(Qt.Key_Return,Qt.AltModifier),(Qt.Key_Return,Qt.NoModifier)]:
                QApplication.sendEvent(panel.list,QKeyEvent(QEvent.KeyPress,key,mods))
            assert rename.call_count==1 and [call.args[0] for call in native.call_args_list]==['delete','properties'] and launch.call_count==1
        QApplication.sendEvent(panel.list,QKeyEvent(QEvent.KeyPress,Qt.Key_A,Qt.ControlModifier));assert len(panel.list.selectedItems())==2
        with patch('card_file_actions.QInputDialog.getText') as ask:assert not panel.rename_file() and not ask.called
        select(first)
        before=copy.deepcopy(cfg)
        for name,accept in [('ignored.txt',False),('collision.txt',True),('../escape.txt',True),('CON.txt',True)]:
            with patch('card_file_actions.QInputDialog.getText',return_value=(name,accept)):assert not panel.rename_file()
            assert cfg==before and first.read_text(encoding='utf-8')=='unchanged' and conflict.read_text(encoding='utf-8')=='keep'
        with patch('card_file_actions.QInputDialog.getText',return_value=('failed-save.txt',True)),patch.object(api,'save_config',return_value=False):
            assert not panel.rename_file()
        assert first.exists() and not (fixture/'failed-save.txt').exists() and cfg==before
        renamed=fixture/'成功重命名.txt'
        with patch('card_file_actions.QInputDialog.getText',return_value=(renamed.name,True)):assert panel.rename_file()
        assert not first.exists() and renamed.read_text(encoding='utf-8')=='unchanged' and not manager.message
        refs=[row for row in cfg['desktop_entries'] if path_key(row['path'])==path_key(str(renamed))]
        assert len(refs)==2 and all(row['name']==renamed.name for row in refs)
        assert path_key(str(renamed)) in manager.model('documents')['pinned_paths']
        saved=api.load_config();assert len([row for row in saved['desktop_entries'] if path_key(row['path'])==path_key(str(renamed))])==2
        select(renamed)
        with patch('card_file_actions.QMessageBox.question',return_value=QMessageBox.No),patch('native_file_menu.NativeFileMenu') as factory:
            assert not panel.shell_file_action('delete') and not factory.called and renamed.exists()
        native=MagicMock();native.invoke_verb.return_value='shell'
        with patch('native_file_menu.NativeFileMenu',return_value=native):assert panel.shell_file_action('properties')
        assert native.invoke_verb.call_args.args==('properties',) and native.close.called
        def simulated_delete(verb):
            assert verb=='delete';renamed.unlink();return 'shell'
        native=MagicMock();native.invoke_verb.side_effect=simulated_delete
        with patch('card_file_actions.QMessageBox.question',return_value=QMessageBox.Yes),patch('native_file_menu.NativeFileMenu',return_value=native):
            assert panel.shell_file_action('delete')
        assert not any(path_key(row['path'])==path_key(str(renamed)) for row in cfg['desktop_entries']) and conflict.exists()
        checks.append('file keyboard: actual Qt F2/Delete/Enter/Alt+Enter/Ctrl+A events; rename updates both references and pin, persists/reloads; cancel, collision, invalid names and failed save preserve fixtures; Delete cancellation and successful reference cleanup with Shell invocation mocked')
        # Real system icon APIs, bounded line breaking and actual card rendering.
        hicon=extract_card_hicon(api,str(conflict),34);assert hicon
        image=api.hicon_to_qimage(hicon);assert image is not None and not image.isNull()
        image.save(str(Path(output)/'shell-card-icon.png'))
        api_pm=runtime.dock.icons.get(str(conflict),34,shell_state=True);api_pm.save(str(Path(output)/'provider-card-icon.png'))
        for view in ('small','large','list'):
            manager.update_panel('documents',view=view);panel=manager.windows['documents'];app.processEvents()
            select(conflict);size=panel.list.iconSize()
            lines=file_name_lines(first.name,panel.list.font(),64)
            assert len(lines)==3 and lines[-1].endswith('…'),lines
            item=panel.list.item(0);item.setText(first.name);app.processEvents()
            assert panel.list.iconSize()==size
            panel.grab().save(str(Path(output)/('card-file-'+view+'.png')))
            # A copied option's QIcon field is a live SIP reference; clearing it
            # must not clear our saved decoration. Compare the painted icon area.
            item=panel.list.item(0);item.setText(first.name)
            rect=panel.list.visualItemRect(item);margin=max(2,round(panel.list.fontMetrics().height()*.2))
            x=rect.left()+margin if view=='list' else rect.center().x()-size.width()//2
            y=rect.top()+(rect.height()-size.height())//2 if view=='list' else rect.top()+margin
            diagnostic=api.QPixmap(size);diagnostic.fill(api.QColor('#cb3748'));item.setIcon(api.QIcon(diagnostic))
            # Paint synchronously: processing unrelated geometry timers here may
            # legitimately rebuild the list and replace this diagnostic item.
            from PyQt5.QtWidgets import QStyleOptionViewItem
            from PyQt5.QtCore import QRect
            option=QStyleOptionViewItem();option.initFrom(panel.list);option.widget=panel.list;option.rect=QRect(0,0,rect.width(),rect.height())
            painted=api.QPixmap(option.rect.size());painted.fill(Qt.transparent);painter=api.QPainter(painted)
            panel.list.itemDelegate().paint(painter,option,panel.list.indexFromItem(item));painter.end()
            local_x=margin if view=='list' else option.rect.center().x()-size.width()//2
            local_y=(option.rect.height()-size.height())//2 if view=='list' else margin
            center=painted.toImage().pixelColor(local_x+size.width()//2,local_y+size.height()//2)
            assert center.name()=='#cb3748',(view,center.name())
            # Focus must not add a native empty-label glyph over the custom filename.
            from PyQt5.QtWidgets import QStyle
            item.setText('文析助手');option.state|=QStyle.State_Selected|QStyle.State_Enabled
            def selected_image(focused):
                option.state=option.state|QStyle.State_HasFocus if focused else option.state&~QStyle.State_HasFocus
                image=api.QPixmap(option.rect.size());image.fill(api.QColor('#d9edfa'));painter=api.QPainter(image)
                panel.list.itemDelegate().paint(painter,option,panel.list.indexFromItem(item));painter.end();return image
            focused=selected_image(True);unfocused=selected_image(False)
            assert focused.toImage()==unfocused.toImage(),view
            focused.save(str(Path(output)/('file-selected-'+view+'.png')))

        from card_file_ui import card_display_name,card_overlay_index
        assert card_display_name({'name':'报告.docx','path':str(fixture/'报告.docx')},True)=='报告'
        assert card_display_name({'name':'应用.lnk','path':str(fixture/'应用.lnk')},True)=='应用'
        assert card_display_name({'name':'archive.tar.gz','path':str(fixture/'archive.tar.gz')},True)=='archive.tar'
        dotted=fixture/'资料.v2';dotted.mkdir()
        assert card_display_name({'name':dotted.name,'path':str(dotted)},True)==dotted.name
        assert card_overlay_index(2,2,True)==0 and card_overlay_index(3,2,True)==3 and card_overlay_index(2,2,False)==2
        for view in ('small','large','list'):
            manager.update_panel('documents',view=view);panel.render()
            text=next(panel.list.item(i).text() for i in range(panel.list.count()) if panel.list.item(i).data(Qt.UserRole)['path']==str(conflict))
            assert text==('collision.txt' if view=='list' else 'collision'),(view,text)
        checks.append('selected file labels: small/large/list render identical with and without native focus; selection remains visible, custom name and icon dimensions retained; screenshots captured')
        checks.append('icon views hide only filename suffix and standard shortcut arrow; list retains full names; dotted folders and non-shortcut state overlays retained')
        # Inject a Shell-composed image to ensure a cached plain Dock icon cannot win.
        provider=runtime.dock.icons;provider.clear();marker=api.QPixmap(34,34);marker.fill(api.QColor('#eb8d24'))
        with patch('card_file_ui.extract_card_hicon',return_value=123) as get_icon,patch.object(api,'hicon_to_qimage',return_value=marker.toImage()):
            provider.get(str(conflict),34,shell_state=True);assert get_icon.call_count==1
            provider.get(str(conflict),34,shell_state=True);assert get_icon.call_count==1
            conflict.write_text('changed',encoding='utf-8');provider.get(str(conflict),34,shell_state=True);assert get_icon.call_count==2
            provider.get(str(conflict),34,shell_state=True,hide_shortcut=True);assert get_icon.call_count==3 and get_icon.call_args.kwargs['hide_shortcut']
        provider.clear()
        checks.append('card names/icons: real Shell overlay image API returned a valid icon; Shell-composed icon takes priority and metadata change invalidates cache; three-line capped text at small/large/list sizes, unchanged icon dimensions; screenshots captured; third-party encryption handler requires the affected PC')
    finally:
        if manager:manager.close()
        cfg.clear();cfg.update(original);api.save_config(cfg)
        runtime.panels=DesktopPanels(runtime,roots=roots);runtime.apply_settings()
