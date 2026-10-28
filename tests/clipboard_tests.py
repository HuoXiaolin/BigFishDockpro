"""Real Shell file transfers using only a private window station and fixture files."""
import ctypes,json,os,tempfile,time,traceback
from pathlib import Path


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);checks=[];app=None;fixture=None
    try:
        print('checking isolation',flush=True)
        from run_isolated_test import assert_isolated,desktop_name
        desktop=assert_isolated();station=os.environ.get('FISHDOCK_TEST_STATION')
        if not station:raise RuntimeError('Private clipboard station is required.')
        user=ctypes.windll.user32;user.GetProcessWindowStation.restype=ctypes.c_void_p
        if desktop_name(user.GetProcessWindowStation())!=station:raise RuntimeError('Not on the private clipboard station.')
        print('isolation verified',flush=True)
        from PyQt5.QtWidgets import QApplication,QWidget
        from shell_file_clipboard import set_file_clipboard,clipboard_paths,preferred_effect,paste_into_folder,COPY,MOVE
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        owner=QWidget();owner.setWindowTitle('isolated file transfer fixture');owner.show();app.processEvents()
        fixture=tempfile.TemporaryDirectory(prefix='fishdock-clipboard-');root=Path(fixture.name)
        source=root/'source';source.mkdir();target=root/'target';target.mkdir()
        def await_file(path,exists=True):
            until=time.monotonic()+8
            while time.monotonic()<until:
                app.processEvents()
                if path.exists()==exists:return
                time.sleep(.03)
            raise AssertionError('Timed out waiting for test file operation')
        first=source/'复制内容.txt';first.write_text('copy test',encoding='utf-8')
        # Build the actual Shell menu on an isolated desktop and verify its Copy verb.
        from native_file_menu import NativeFileMenu,APP_FIRST
        selected=[];menu=NativeFileMenu(int(owner.winId()),[str(first)])
        try:
            assert menu.command_count>0
            verbs={menu.command_verb(i):i for i in range(min(menu.command_count,512))}
            assert {'copy','rename','delete','properties'}<=set(verbs),sorted(verbs)
            menu.add_card_commands([('测试卡片操作',lambda:selected.append('card'))])
            assert menu.user.GetMenuItemCount(menu.menu)>0 and menu.invoke(APP_FIRST)=='card' and selected==['card']
            from unittest.mock import patch
            import external_launch
            with patch('external_launch.clean_environment',wraps=external_launch.clean_environment) as safe_environment:
                assert menu.invoke(1+verbs['copy'])=='shell';assert safe_environment.called
            app.processEvents()
            copied=clipboard_paths(app.clipboard().mimeData());assert len(copied)==1 and os.path.samefile(copied[0],first)
        finally:menu.close()
        checks.append('native Windows context menu: real Shell menu exposed Copy/Rename/Delete/Properties; custom card callback routed separately')
        folder_menu=NativeFileMenu(int(owner.winId()),[str(source)])
        try:
            assert folder_menu.command_count>0 and folder_menu.user.GetMenuItemCount(folder_menu.menu)>0
        finally:folder_menu.close()
        checks.append('native Windows context menu: folder item exposed a real Shell menu')
        # Selection from different physical folders uses a desktop-root context menu.
        other=root/'other';other.mkdir();other_file=other/'第二个.txt';other_file.write_text('other',encoding='utf-8')
        menu=NativeFileMenu(int(owner.winId()),[str(first),str(other_file)])
        try:
            assert menu.command_count>0
            menu.add_card_commands([('测试卡片操作',lambda:None)])
            assert menu.user.GetMenuItemCount(menu.menu)>0
            verbs={menu.command_verb(i):i for i in range(min(menu.command_count,512))};assert 'copy' in verbs
            assert menu.invoke(1+verbs['copy'])=='shell';app.processEvents()
            copied=clipboard_paths(app.clipboard().mimeData())
            assert len(copied)==2 and all(any(os.path.samefile(value,path) for value in copied) for path in (first,other_file))
            from PyQt5.QtCore import QTimer
            cancel=QTimer();cancel.setSingleShot(True);cancel.timeout.connect(menu.user.EndMenu);cancel.start(100)
            assert menu.track()=='cancelled';cancel.stop()
        finally:menu.close()
        checks.append('native Windows context menu: mixed-parent selection copied both files through the actual Shell menu; popup cancellation preserved files')
        set_file_clipboard([str(first)],owner=int(owner.winId()));app.processEvents()
        data=app.clipboard().mimeData();assert preferred_effect(data)==COPY and clipboard_paths(data)==[str(first)]
        assert paste_into_folder(str(target),int(owner.winId()),COPY,clipboard_paths(data))=='completed'
        await_file(target/first.name);assert first.exists() and (target/first.name).read_text(encoding='utf-8')=='copy test'
        checks.append('native clipboard copy: CF_HDROP and copy effect copied fixture while preserving original')
        # Same-name copy is renamed by the Shell rather than overwriting.
        assert paste_into_folder(str(target),int(owner.winId()),COPY,[str(first)])=='completed'
        copies=list(target.glob('*.txt'));assert len(copies)==2 and all(path.read_text(encoding='utf-8')=='copy test' for path in copies)
        before={path.name for path in copies};assert paste_into_folder(str(target),int(owner.winId()),MOVE,[str(target/first.name)])=='same-folder'
        assert {path.name for path in target.glob('*.txt')}==before
        checks.append('native same-name copy: original preserved and a new file created; moving into the same folder is a no-op')
        second=source/'剪切内容.txt';second.write_text('move test',encoding='utf-8')
        set_file_clipboard([str(second)],True,int(owner.winId()));app.processEvents()
        data=app.clipboard().mimeData();assert preferred_effect(data)==MOVE and clipboard_paths(data)==[str(second)]
        assert paste_into_folder(str(target),int(owner.winId()),MOVE,clipboard_paths(data))=='completed'
        await_file(target/second.name);await_file(second,False)
        assert (target/second.name).read_text(encoding='utf-8')=='move test'
        checks.append('native clipboard cut: Windows preferred move format drove real Shell move of fixture')
        folder=source/'文件夹';folder.mkdir();(folder/'内容.txt').write_text('nested',encoding='utf-8')
        extra=source/'多选.txt';extra.write_text('multiple',encoding='utf-8')
        set_file_clipboard([str(folder),str(extra)],owner=int(owner.winId()));app.processEvents()
        data=app.clipboard().mimeData();assert set(clipboard_paths(data))=={str(folder),str(extra)} and preferred_effect(data)==COPY
        assert paste_into_folder(str(target),int(owner.winId()),COPY,clipboard_paths(data))=='completed'
        await_file(target/'文件夹'/'内容.txt');await_file(target/'多选.txt')
        assert (target/'文件夹'/'内容.txt').read_text(encoding='utf-8')=='nested' and folder.exists()
        try:set_file_clipboard([str(source/'missing.txt')],True,int(owner.winId()));raise AssertionError('missing source accepted')
        except ValueError:pass
        app.processEvents();assert set(clipboard_paths(app.clipboard().mimeData()))=={str(folder),str(extra)}
        checks.append('multi-file and folder copy: nested contents preserved; invalid selection leaves clipboard unchanged')
        assert station and desktop;result={'passed':True,'scope':'private-window-station-native-clipboard','checks':checks,'limits':['test-owned local files only; no real Explorer clipboard, remote clipboard, large-file or interactive conflict dialog']}
    except Exception:result={'passed':False,'scope':'private-window-station-native-clipboard','checks':checks,'error':traceback.format_exc()}
    finally:
        if app:
            try:app.clipboard().clear();app.processEvents()
            except Exception:pass
        if fixture:
            try:fixture.cleanup()
            except OSError:pass
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result.get('passed') else 1
