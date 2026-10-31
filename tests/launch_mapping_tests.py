"""Shortcut mappings and on-click activation with temporary native fixtures."""
import os,sys,copy,json,base64,subprocess,ctypes
from pathlib import Path
from unittest.mock import patch

def run(api,runtime,root,output,checks):
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from desktop_panel_tests import wait_for
    from app_catalog import merge_items,launch_identity,common_windows_tools,unique_apps,path_key
    from shortcut_targets import lnk_metadata
    from shortcut_mapping import map_entry
    from icon_settings import IconSettings
    from ui_style import compact_dialog
    import window_activation as activation
    app=QApplication.instance();folder=Path(root)/'launch-mapping';folder.mkdir()
    program=folder/'real.exe';program.write_bytes(b'synthetic reference')
    cwd=folder/'Working Folder';cwd.mkdir()
    link=folder/'Desktop Shortcut.lnk';normal=folder/'Normal.lnk'
    specs=[dict(link=str(link),target=str(program),arguments='--profile "space value"',cwd=str(cwd)),dict(link=str(normal),target=str(program),arguments='',cwd=str(cwd))]
    def make_links(rows):
        data=folder/'links.json';data.write_text(json.dumps(rows),encoding='utf-8')
        script="$shell=New-Object -ComObject WScript.Shell; $rows=Get-Content -LiteralPath '"+str(data).replace("'","''")+"' -Raw -Encoding UTF8 | ConvertFrom-Json; foreach($r in $rows){$l=$shell.CreateShortcut($r.link);$l.TargetPath=$r.target;$l.Arguments=$r.arguments;$l.WorkingDirectory=$r.cwd;$l.IconLocation=$env:WINDIR+'\\System32\\shell32.dll,3';$l.Save()}"
        task=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,timeout=20)
        assert task.returncode==0,task.stderr.decode(errors='replace')
    make_links(specs)
    original=program.read_bytes()
    mapped=map_entry(dict(path=str(link),name='Mapped application'))
    assert path_key(mapped['path'])==path_key(str(program)) and mapped['arguments']=='--profile "space value"',mapped
    assert path_key(mapped['working_directory'])==path_key(str(cwd)) and mapped['icon_index']==3,mapped
    assert launch_identity(mapped)==launch_identity(str(link))
    assert merge_items([mapped],[dict(path=str(link))])[1:3]==(0,1)
    assert merge_items([mapped],[dict(path=str(normal))])[1:3]==(1,0)
    snapshot=Path(api.CONFIG_PATH).read_bytes()
    legacy=copy.deepcopy(api.DEFAULT_CONFIG);legacy.update(items=[dict(path=str(link),name='Legacy alias',group='Test')],reorder=False)
    assert api.save_config(legacy)
    migrated=api.load_config()
    assert path_key(migrated['items'][0]['path'])==path_key(str(program)) and migrated['items'][0]['arguments']==mapped['arguments']
    assert not migrated['reorder'] and json.loads(Path(api.CONFIG_PATH).read_text(encoding='utf-8'))['items'][0]['path']==migrated['items'][0]['path']
    Path(api.CONFIG_PATH).write_bytes(snapshot)
    link.unlink();normal.unlink()
    assert map_entry(mapped)==mapped and program.read_bytes()==original
    internet=folder/'web.url';internet.write_text('[InternetShortcut]\nURL=https://example.com/CaseSensitive\n',encoding='utf-8')
    web=map_entry(dict(path=str(internet)));assert web['path']=='https://example.com/CaseSensitive'
    assert launch_identity(web)==launch_identity(str(internet));internet.unlink()
    mapped['group']='未分类';web['group']='未分类'
    cfg=copy.deepcopy(api.DEFAULT_CONFIG);cfg['items']=[mapped,web];cfg['reorder']=False
    saved=Path(api.CONFIG_PATH).read_bytes();assert api.save_config(cfg)
    loaded=api.load_config();assert loaded['items']==cfg['items'] and not loaded['reorder']
    from config_transfer import normalize
    assert normalize(loaded,api)['items']==cfg['items']
    Path(api.CONFIG_PATH).write_bytes(saved)
    assert api.DEFAULT_CONFIG['reorder'] and '不复制' in api.EMPTY_DOCK_HINT
    entries=common_windows_tools();names={row['name'] for row in entries}
    assert {'网络','用户文件夹','桌面','下载','文档','图片','音乐','视频'}<=names
    assert len(unique_apps(entries))==len(entries)
    # Parse namespace entries; do not open Explorer or modify the user's desktop.
    shell=ctypes.WinDLL('shell32');ole=ctypes.WinDLL('ole32')
    shell.SHParseDisplayName.argtypes=[ctypes.c_wchar_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),ctypes.c_ulong,ctypes.c_void_p]
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    for row in entries:
        if row['path'].startswith('shell:'):
            pointer=ctypes.c_void_p();status=shell.SHParseDisplayName(row['path'],None,ctypes.byref(pointer),0,None)
            try:assert status>=0 and pointer,row
            finally:
                if pointer:ole.CoTaskMemFree(pointer)
    checks.append('pin references: real Shell links resolved with arguments/cwd/icon index; deletion of source link leaves target metadata intact; no file copying; URL mapping, dedup, restart and export/import preserved; Windows namespace entries parsed and new reorder default checked')
    # Preview geometry must fit its actual control after compacting/resizing.
    old_items=copy.deepcopy(runtime.dock.cfg['items'])
    runtime.dock.cfg['items']=[mapped]
    try:
        dialog=IconSettings(runtime.dock,0);dialog.show();app.processEvents()
        for size in (18,28,44,70):
            dialog.preview.setFixedSize(size,size);app.processEvents()
            image=dialog.preview.pixmap();ratio=image.devicePixelRatioF()
            assert image.width()/ratio<=size+1 and image.height()/ratio<=size+1
        dialog.grab().save(str(Path(output)/'icon-mapping-settings.png'))
        dialog.reject();dialog.deleteLater()
    finally:runtime.dock.cfg['items']=old_items
    target=activation.activation_target(dict(path=str(program)))
    other=folder/'other'/'real.exe'
    assert activation.matching_window(target,[dict(hwnd=1,path=str(other)),dict(hwnd=2,path=str(program))])['hwnd']==2
    assert activation.activation_target(mapped) is None # parameterized launch keeps its semantics
    chrome=dict(path=str(folder/'chrome.exe'),arguments='--profile-directory="Profile 1"',app_user_model_id='Chrome.Profile1')
    chrome_target=activation.activation_target(chrome)
    assert chrome_target and activation.matching_window(chrome_target,[dict(hwnd=3,path=chrome['path'],window_aumid='Chrome'),dict(hwnd=4,path=chrome['path'],window_aumid='Chrome.Profile1')])['hwnd']==4
    assert activation.matching_window(chrome_target,[dict(hwnd=3,path=chrome['path'],window_aumid='Chrome')]) is None
    assert activation.matching_window(chrome_target,[dict(hwnd=3,path=chrome['path'])]) is None
    for arguments in ('https://example.com','--incognito','--new-window','--profile-directory="Profile 1" https://example.com'):
        assert activation.activation_target(dict(chrome,arguments=arguments)) is None
    with patch.object(activation,'native_windows',return_value=[dict(hwnd=99,path=str(program))]),patch.object(activation,'activate_window',return_value=True) as restore:
        assert activation.activate_existing(dict(path=str(program)));restore.assert_called_once_with(99)
    with patch('explorer_launch.launch') as shell_launch:
        import external_launch
        external_launch.launch(mapped['path'],arguments=mapped['arguments'],working_directory=mapped['working_directory'])
        assert shell_launch.call_args.args[1:3]==(str(cwd),mapped['arguments'])
    checks.append('window reuse matches full executable path, skips parameterized/document actions, delegates mapping arguments/cwd; icon preview fits 18/28/44/70px native controls')
    fixture=os.environ.get('FISHDOCK_ACTIVATION_FIXTURE')
    if not fixture:return
    report=folder/'window.report';stop=folder/'window.stop';process=None;dock=None
    try:
        process=subprocess.Popen([fixture,str(report),str(stop)],creationflags=subprocess.CREATE_NO_WINDOW)
        wait_for(app,lambda:report.exists() and report.stat().st_size>5)
        hwnd,pid=map(int,report.read_text().split())
        make_links([dict(link=str(normal),target=fixture,arguments='',cwd=str(Path(fixture).parent))])
        entry=map_entry(dict(path=str(normal),name='Already running native fixture'));normal.unlink()
        cfg=api.normalize_features(copy.deepcopy(api.DEFAULT_CONFIG));cfg.update(items=[entry],theme='light',running_dots=False,lite_enabled=False)
        # The external window already exists before this new Dock is constructed.
        dock=api.Dock(cfg,preview=True)
        with patch('external_launch.launch') as launch_new:
            dock.launch(dock.items[0]);assert not launch_new.called
        assert any(w['hwnd']==hwnd and w['pid']==pid for w in activation.native_windows())
        stop.touch();assert process.wait(timeout=4)==0;process=None
        with patch('external_launch.launch') as launch_new:
            dock.launch(dock.items[0]);assert launch_new.call_count==1
        checks.append('real separate native app opened before new Dock: mapped shortcut deleted, click reuses existing process/window without a new launch; after exit normal launching resumes; private Windows desktop only')
    finally:
        stop.touch()
        if process is not None:process.wait(timeout=4)
        if dock:dock.extras.close();dock.hide();dock.deleteLater()
