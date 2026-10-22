"""Interaction regression on the isolated desktop with disposable fixture data."""
import copy
import json
import os
import subprocess
import base64
from pathlib import Path
from PyQt5.QtCore import Qt, QEventLoop, QTimer
from PyQt5.QtGui import QImage, QColor
from PyQt5.QtWidgets import QApplication
from desktop_catalog import category, scan_desktop, reconcile
from ui_style import apply_theme


def run(api, dock, importer, root, output, checks):
    app = QApplication.instance()
    root, output = Path(root), Path(output)
    fixture = root/'shortcut_targets'
    fixture.mkdir()
    targets = ['资料文件夹', 'report.pdf', 'photo.png', 'music.mp3', 'archive.zip', 'program.exe', 'unknown.dat']
    (fixture/targets[0]).mkdir()
    for name in targets[1:]: (fixture/name).write_text('fixture', encoding='utf-8')
    pairs = [(str(fixture/(str(i)+'.lnk')), str(fixture/name)) for i,name in enumerate(targets)]
    pairs += [(str(fixture/'chain.lnk'), pairs[0][0])]
    pairs += [(str(fixture/'program-alias.lnk'),str(fixture/'program.exe')),
              (str(fixture/'program-special.lnk'),str(fixture/'program.exe'),'--profile secondary')]
    data = fixture/'pairs.json'
    data.write_text(json.dumps(pairs), encoding='utf-8')
    # Fixture creation only; no launching shortcuts or changing the user's desktop.
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $pairs=Get-Content -LiteralPath '"+str(data).replace("'","''")+"' -Raw -Encoding UTF8 | ConvertFrom-Json; $shell=New-Object -ComObject WScript.Shell; foreach($pair in $pairs){$link=$shell.CreateShortcut($pair[0]);$link.TargetPath=$pair[1];if($pair.Count -gt 2){$link.Arguments=$pair[2]};$link.Save()}"
    process = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],
                   timeout=25, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
    assert process.returncode == 0, process.stderr.decode('utf-8',errors='replace')
    expected = ['folders','documents','images','media','archives','apps','other']
    for (shortcut,target), result in zip(pairs, expected):
        assert category(shortcut) == result, (shortcut,category(shortcut))
        assert Path(shortcut).exists() and Path(target).exists()
    assert category(str(fixture/'chain.lnk')) == 'folders'
    import shortcut_targets
    original_target = shortcut_targets.shortcut_target
    try:
        shortcut_targets.shortcut_target = lambda path: str(fixture/('cycle2.lnk' if path.endswith('cycle1.lnk') else 'cycle1.lnk'))
        assert category(str(fixture/'cycle1.lnk')) == 'apps'
    finally: shortcut_targets.shortcut_target = original_target
    (fixture/'broken.lnk').write_bytes(b'broken link')
    assert category(str(fixture/'broken.lnk')) == 'apps'
    local = fixture/'local.url'
    local.write_text('[InternetShortcut]\nURL='+Path(pairs[0][1]).as_uri(),encoding='utf-8')
    assert category(str(local)) == 'folders'
    rows, errors = scan_desktop([str(fixture)])
    assert not errors and next(row for row in rows if row['path']==pairs[0][0])['panel'] == 'folders'
    original={'path':pairs[0][0],'name':'0.lnk','source':'desktop','panel':'apps'}
    incoming=[dict(original,panel='folders')]
    assert reconcile([original],incoming,[])[0]['panel']=='folders'
    assert reconcile([dict(original,source='manual')],incoming,[])[0]['panel']=='apps'
    assert reconcile([dict(original,panel='custom')],incoming,[])[0]['panel']=='custom'
    checks.append('shortcuts: real Windows folder/document/image/media/archive/program targets, chained and cyclic links, broken fallback, file URL, existing auto classification and manual override preservation')
    from app_catalog import launch_identity, unique_apps, discover_apps, merge_items, common_windows_tools
    program = str(fixture/'program.exe')
    alias, special = str(fixture/'program-alias.lnk'), str(fixture/'program-special.lnk')
    assert launch_identity(program) == launch_identity(alias)
    assert launch_identity(program) != launch_identity(special)
    assert len(unique_apps([dict(name='Program',path=program),dict(name='Alias',path=alias),dict(name='Profile',path=special)])) == 2
    assert merge_items([dict(name='Program',path=program)],[dict(path=alias)])[1:3] == (0,1)
    old_output = subprocess.check_output
    try:
        subprocess.check_output=lambda *args,**kwargs: json.dumps([
            {'Name':'不显示系统组件','AppID':'Microsoft.XboxGameOverlay_test!App'},
            {'Name':'计算器','AppID':'Microsoft.WindowsCalculator_test!App'},
            {'Name':'第三方商店程序','AppID':'Vendor.Sample_test!App'}]).encode('utf-8')
        catalog=discover_apps([str(fixture)],include_store=True)
    finally: subprocess.check_output=old_output
    assert len(catalog)==len({launch_identity(row['path']) for row in catalog})
    assert not any(row['name']=='不显示系统组件' for row in catalog)
    assert next(row for row in catalog if row['name']=='第三方商店程序')['column']=='apps'
    tools=common_windows_tools()
    assert {'回收站','此电脑','控制面板','文件管理'} <= {row['name'] for row in tools}
    assert sum(launch_identity(row['path'])==('windows','calculator') for row in catalog)==1
    batch=importer.dialog
    original_apps=copy.deepcopy(batch.apps)
    original_items=copy.deepcopy(dock.cfg['items'])
    batch.discovered(catalog)
    batch.reveal()
    batch.tabs.setCurrentIndex(2)
    assert batch.list.count() > 3 and all(batch.list.item(i).data(Qt.UserRole)['column']=='windows' for i in range(batch.list.count()))
    for theme in ('light','dark'):
        apply_theme(app, theme=='light');app.processEvents()
        batch.grab().save(str(output/('windows-tools-'+theme+'.png')))
    last_item=batch.list.item(batch.list.count()-1)
    batch.list.scrollToItem(last_item)
    loop=QEventLoop();QTimer.singleShot(40,loop.quit);loop.exec_()
    assert not last_item.icon().isNull()
    assert len(batch.icon_rows)<batch.list.count() or batch.list.count()<12
    batch.select_visible();batch.perform()
    assert dock.cfg['items'] == original_items and batch.pending_add
    batch.commit()
    assert batch.isVisible() and any(row['path'].startswith('shell:::') for row in api.load_config()['items'])
    for tool in tools[:3]:
        picture=dock.icons.get(tool['path'],56).toImage()
        assert any(picture.pixelColor(x,y).alpha() for x in range(picture.width()) for y in range(picture.height())),tool['name']
    importer.apply_items([dict(name='Program',path=program),dict(name='Alias',path=alias),dict(name='Profile',path=special)])
    batch.tabs.setCurrentIndex(1)
    assert batch.list.count()==2
    for i in range(batch.list.count()): batch.list.item(i).setCheckState(Qt.Checked if len(batch.list.item(i).data(Qt.UserRole)['_paths'])==2 else Qt.Unchecked)
    batch.perform();batch.commit()
    assert len(dock.cfg['items'])==1 and dock.cfg['items'][0]['path']==special
    importer.apply_items(original_items)
    batch.discovered(original_apps)
    batch.tabs.setCurrentIndex(0)
    batch.reject()
    checks.append('application dedup: real shortcut target/arguments, native/store tool aliases, curated Windows tab, third-party Store retained, shell tool icons and save/reload, grouped duplicate removal')
    from icon_settings import IconSettings
    saved = copy.deepcopy(dock.cfg['items'])
    icon = fixture/'custom.png'
    image = QImage(48,48,QImage.Format_ARGB32)
    image.fill(QColor('#cc7042')); image.save(str(icon))
    # A large custom image workload must not leave an unbounded icon cache.
    large=fixture/'large-icon.png'
    picture=QImage(512,512,QImage.Format_ARGB32);picture.fill(QColor('#cc7042'));picture.save(str(large))
    provider=api.IconProvider()
    for size in range(512,652): provider.get(str(large),size,True)
    estimated=sum(pm.width()*pm.height()*pm.depth()//8 for pm in provider.cache.values())
    assert len(provider.cache)<140 and estimated<=12*1024*1024
    assert provider.get(str(large),512,True).toImage().pixelColor(5,5).red()==204
    provider.clear();assert not provider.cache and provider.cache_bytes==0
    dialog=IconSettings(dock,0)
    dialog.show()
    dialog.name.setText('自定义入口')
    dialog.path.setText(str(fixture/targets[1]))
    dialog.icon.setText(str(icon))
    dialog.reject()
    assert dock.cfg['items']==saved
    dialog=IconSettings(dock,0)
    dialog.show()
    dialog.name.setText('项目文档')
    dialog.path.setText(str(fixture/targets[1]))
    dialog.icon.setText(str(icon))
    save=importer.save
    importer.save=lambda _:False
    dialog.commit()
    assert dock.cfg['items']==saved
    importer.save=save
    dialog.commit()
    assert dialog.isVisible() and api.load_config()['items'][0]['icon']==str(icon)
    assert dock.items[0]['name']=='项目文档' and dock.items[0]['pixmap'].toImage().pixelColor(5,5).red()==204
    dialog.path.setText('https://[bad')
    dialog.commit()
    assert dock.cfg['items'][0]['path']==str(fixture/targets[1])
    dialog.path.setText(str(fixture/targets[1]))
    dialog.status.setText('图标设置已保存并生效，可继续调整。')
    dialog.path.setText(r'C:\Users\Demo\Documents\report.pdf')
    dialog.icon.blockSignals(True)
    dialog.icon.setText(r'C:\Users\Demo\Pictures\custom.png')
    dialog.icon.blockSignals(False)
    dialog.path.setCursorPosition(0)
    dialog.icon.setCursorPosition(0)
    for theme in ('light','dark'):
        apply_theme(app, theme=='light'); app.processEvents()
        dialog.grab().save(str(output/('icon-settings-'+theme+'.png')))
    dialog.reject()
    assert '图标设置…' in [action.text() for action in dock.icon_context_menu(0).actions()]
    before_remove=copy.deepcopy(dock.cfg['items'])
    importer.save=lambda _:False
    next(action for action in dock.icon_context_menu(0).actions() if action.text()=='移除').trigger()
    assert dock.cfg['items']==before_remove
    importer.save=save
    next(action for action in dock.icon_context_menu(0).actions() if action.text()=='移除').trigger()
    assert len(dock.cfg['items'])==len(before_remove)-1 and Path(before_remove[0]['path']).exists()
    assert api.load_config()['items']==dock.cfg['items']
    importer.apply_items(saved)
    batch=importer.dialog
    batch.reveal()
    batch.tabs.setCurrentIndex(1)
    assert all(not batch.list.item(i).icon().isNull() for i in range(batch.list.count()))
    batch.tabs.setCurrentIndex(0)
    assert all(not batch.list.item(i).icon().isNull() for i in range(batch.list.count()))
    finished=[]
    batch.finished.connect(finished.append)
    batch.header.minimize.click(); app.processEvents()
    assert batch.isMinimized() and not finished
    importer.show(); app.processEvents()
    assert batch.isVisible() and not batch.isMinimized()
    for theme in ('light','dark'):
        apply_theme(app, theme=='light'); app.processEvents()
        batch.grab().save(str(output/('batch-modern-'+theme+'.png')))
        batch.resize(620,480); app.processEvents()
        batch.grab().save(str(output/('batch-compact-'+theme+'.png')))
        batch.resize(740,580)
    batch.header.close.click()
    assert finished and not batch.isVisible()
    # Hidden batch data is released in lite mode and rebuilt on the next open.
    dock.lite_mode=True
    importer.release_memory()
    assert batch.list.count()==0 and not batch.apps and batch.catalog_released
    dock.lite_mode=False
    importer.show()
    batch.worker.wait(27000);app.processEvents()
    assert batch.isVisible() and batch.apps and not batch.catalog_released
    batch.reject()
    checks.append('Dock icon editor: cancel and save failure, name/link/custom image save-reload, malformed URL, context menu; modern batch: both modes have icons, minimize/restore/close and compact light/dark views')
