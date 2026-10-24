"""Running window discovery and staged pinning, only on the private test desktop."""
import copy
import os
from pathlib import Path
from PyQt5.QtWidgets import QApplication,QWidget
from PyQt5.QtCore import Qt
from running_apps import collect_apps,discover_running_apps
from app_catalog import path_key
from batch_import import BatchImporter
from desktop_panel_tests import wait_for
from ui_style import apply_theme


def run(api,runtime,root,output,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    data=Path(root)/'RunningApps';data.mkdir(exist_ok=True)
    paths=[]
    for name in ['演示绘图.exe','演示办公.exe','演示通信.exe']:
        file=data/name;file.write_text('synthetic application fixture',encoding='utf-8');paths.append(str(file))
    lookup={1:{'name':'演示绘图','path':paths[0]},2:{'name':'演示绘图副本','path':paths[0]},
            3:{'name':'演示商店应用','path':r'shell:AppsFolder\Demo.Package!App'},
            4:{'name':'卸载演示','path':str(data/'unins000.exe')},5:{'name':'宿主','path':r'C:\Windows\System32\ApplicationFrameHost.exe'}}
    windows=[{'pid':pid,'visible':True} for pid in range(1,7)]
    windows += [{'pid':1,'visible':True},{'pid':1,'visible':False},{'pid':3,'visible':True,'cloaked':True}]
    calls=[]
    def describe(pid):calls.append(pid);return lookup.get(pid)
    rows=collect_apps(windows,describe,exclude_pid=99)
    assert len(rows)==2 and calls.count(1)==1 and any(row['path'].startswith('shell:') for row in rows)
    assert not collect_apps(windows,describe,cancelled=lambda:True)
    window1=QWidget();window1.setWindowTitle('运行列表测试窗口 A');window1.show()
    window2=QWidget();window2.setWindowTitle('运行列表测试窗口 B');window2.showMinimized();app.processEvents()
    native=discover_running_apps(exclude_pid=0)
    assert len(native)==1 and os.path.isfile(native[0]['path']) and native[0]['name'],native
    assert not discover_running_apps() and not discover_running_apps(cancelled=lambda:True)
    window1.close();window2.close();window1.deleteLater();window2.deleteLater()
    import batch_import
    native_rows=[];native_errors=[]
    worker=batch_import.RunningDiscovery(0)
    worker.ready.connect(lambda generation,rows:native_rows.append(rows))
    worker.failed.connect(lambda generation,error:native_errors.append(error))
    worker.start();wait_for(app,lambda:not worker.isRunning());app.processEvents()
    assert not native_errors and native_rows==[[]],(native_errors,native_rows)
    worker.deleteLater()
    discovery=batch_import.discover_running_apps
    fixtures=[{'name':Path(path).stem,'path':path,'column':'running'} for path in paths]
    fixtures.append(dict(fixtures[0]))
    batch_import.discover_running_apps=lambda cancelled=lambda:False:copy.deepcopy(fixtures)
    importer=BatchImporter(runtime.dock,runtime.tray,api.save_config,api.log)
    try:
        runtime.set_lite(False)
        cfg['items']=[{'path':paths[1],'name':'演示办公','group':'未分类'}];api.save_config(cfg);runtime.dock.reload()
        importer.show();dialog=importer.dialog;dialog.tabs.setCurrentIndex(3)
        wait_for(app,lambda:dialog.running_worker is None)
        assert dialog.tabs.tabText(3)=='正在运行' and dialog.list.count()==3
        assert dialog.refresh_running_button.isVisible() and not dialog.pick.isVisible()
        dialog.select_visible();assert len(dialog.selected[3])==2
        dialog.query.setText('绘图');dialog.perform()
        assert len(dialog.pending_add)==1 and len(cfg['items'])==1
        dialog.reject();assert len(cfg['items'])==1 and not dialog.pending_add
        dialog.reveal();dialog.query.clear();wait_for(app,lambda:dialog.running_worker is None)
        dialog.query.setText('绘图');dialog.select_visible();dialog.perform();dialog.commit()
        assert len(cfg['items'])==2 and dialog.isVisible() and not dialog.pending_add
        dialog.query.setText('通信');dialog.select_visible();dialog.perform()
        save=importer.save;importer.save=lambda value:False
        try:dialog.commit();assert len(cfg['items'])==2 and len(dialog.pending_add)==1
        finally:importer.save=save
        dialog.commit();assert len(cfg['items'])==3 and api.load_config()['items']==cfg['items'],(cfg['items'],api.load_config()['items'])
        dialog.query.clear();dialog.refresh_running()
        wait_for(app,lambda:dialog.running_worker is None)
        assert not dialog.visible_selected() and not dialog.action.isEnabled()
        current=copy.deepcopy(dialog.running_apps)
        dialog.running_discovered(dialog.running_generation-1,[{'path':'bad','name':'stale'}]);assert dialog.running_apps==current
        for theme in ('light','dark'):
            apply_theme(app,theme=='light');app.processEvents();dialog.grab().save(str(Path(output)/('running-apps-'+theme+'.png')))
        def failed(cancelled=lambda:False):raise OSError('simulated read failure')
        batch_import.discover_running_apps=failed;dialog.refresh_running()
        wait_for(app,lambda:dialog.running_worker is None)
        assert '读取失败' in dialog.status.text() and len(cfg['items'])==3
        import time
        def delayed(cancelled=lambda:False):
            while not cancelled():time.sleep(.003)
            return fixtures
        batch_import.discover_running_apps=delayed
        dialog.refresh_running();dialog.refresh_running();dialog.reject()
        wait_for(app,lambda:dialog.running_worker is None)
        assert not dialog.running_apps and not dialog.pending_add
        assert all(Path(path).exists() for path in paths)
        checks.append('running applications: real visible/minimized private HWNDs and native background-thread desktop isolation read through limited process query and deduplicated; shell app identities, protected/host/uninstaller/cancel filters; fourth tab refresh, icons, pin dedup, filter selection, staged cancel/save/failure retry and stale-generation/close cancellation, light/dark screenshots')
    finally:
        batch_import.discover_running_apps=discovery
        importer.close();app.aboutToQuit.disconnect(importer.close)
        if importer.dialog:importer.dialog.deleteLater()
        cfg.clear();cfg.update(original);api.save_config(cfg);runtime.dock.reload();apply_theme(app,runtime.dock.is_light())
