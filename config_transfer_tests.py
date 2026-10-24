"""Config import/export with preview, backups and failure recovery on temporary data only."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication,QFileDialog,QLabel,QPushButton
from config_transfer import export_configuration,read_configuration


def run(api,runtime,root,output,checks):
    app=QApplication.instance();cfg=runtime.dock.cfg;original=copy.deepcopy(cfg)
    folder=Path(root)/'ConfigTransfer';folder.mkdir(exist_ok=True)
    example=folder/'配置示例.json';raw=folder/'旧格式.json'
    runtime.show_settings();settings=runtime.tray.settings_dialog
    previous_settings_api=settings.api;settings.api=api
    assert Path(api.CONFIG_DIR).resolve().is_relative_to(Path(root).resolve())
    before=copy.deepcopy(cfg)
    export_configuration(example,cfg,api);loaded=read_configuration(example,api)
    assert loaded['items']==cfg['items'] and loaded['desktop_panels']==cfg['desktop_panels']
    assert json.loads(example.read_text(encoding='utf-8'))['project_id']=='BigFishDockpro'
    raw.write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8-sig');assert read_configuration(raw,api)['items']==cfg['items']
    bad=folder/'损坏.json'
    for document in ['{"items": [], "items": []}', '{"project_id":"OtherApp","format_version":1,"configuration":{}}',
                     '{"project_id":"BigFishDockpro","format_version":99,"configuration":{}}', '[]', '{bad']:
        bad.write_text(document,encoding='utf-8');assert not settings.stage_import(bad) and cfg==before
    malformed=copy.deepcopy(cfg);malformed['icon_size']='huge';bad.write_text(json.dumps(malformed),encoding='utf-8')
    assert not settings.stage_import(bad) and cfg==before
    old_bytes=Path(api.CONFIG_PATH).read_bytes()
    assert not settings.export_to(api.CONFIG_PATH) and Path(api.CONFIG_PATH).read_bytes()==old_bytes
    backup_export=folder/'export-failure.json';backup_export.write_bytes(b'original')
    with patch('config_transfer.os.replace',side_effect=OSError('simulated replace failure')):
        assert not settings.export_to(backup_export)
    assert backup_export.read_bytes()==b'original' and not list(folder.glob('export-failure.json.*.tmp'))
    appfile=folder/'演示程序.url';appfile.write_text('[InternetShortcut]\nURL=https://example.invalid/\n',encoding='utf-8')
    candidate=copy.deepcopy(cfg)
    candidate.update(items=[{'path':str(appfile),'name':'导入演示','group':'办公'}],panel_enabled=True,desktop_auto_sort=False,
                     desktop_panels=[{'id':'transfer-demo','name':'导入面板','geometry':[70,85,380,260],'compact':False,'locked':True}],
                     desktop_entries=[],display_layout={},merged_panels=False,panels_visible=True,dock_visible=True,
                     hide_tray=False,game_mode=False,theme='light',icon_size=48)
    export_configuration(example,candidate,api)
    buttons={button.text():button for button in settings.findChildren(QPushButton)}
    ui_export=folder/'按钮导出.json'
    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(ui_export),'JSON')):buttons['导出配置…'].click()
    assert read_configuration(ui_export,api)['items']==cfg['items']
    with patch.object(QFileDialog,'getOpenFileName',return_value=(str(example),'JSON')):buttons['导入配置…'].click()
    assert settings.import_candidate is not None and cfg==before
    with patch.object(QFileDialog,'getOpenFileName',return_value=('','')):buttons['导入配置…'].click()
    assert settings.import_candidate is not None and cfg==before
    setter=api.set_autostart;autostart_calls=[];api.set_autostart=lambda value:autostart_calls.append(value) or True
    try:
        assert settings.stage_import(example) and cfg==before
        assert settings.fields['icon_size'].value()==48 and settings.import_candidate is not None
        settings.reject();assert settings.import_candidate is None and cfg==before
        runtime.show_settings();assert '已载入' not in settings.transfer_status.text();settings.stage_import(example)
        importer=runtime.tray.importer;previous_dialog=importer.dialog
        importer.dialog=SimpleNamespace(pending_add=[{'path':'pending'}],pending_remove=set())
        try:settings.commit();assert cfg==before and '批量管理' in settings.status.text()
        finally:importer.dialog=previous_dialog
        save=api.save_config;api.save_config=lambda value:False
        try:settings.commit();assert cfg==before and settings.import_candidate is not None,([key for key,value in cfg.items() if before.get(key)!=value],settings.status.text(),settings.import_candidate is not None)
        finally:api.save_config=save
        assert (Path(api.CONFIG_DIR)/'config.before-import.json').read_bytes()==old_bytes
        settings.commit();app.processEvents()
        assert settings.isVisible() and settings.import_candidate is None
        assert cfg['items'][0]['name']=='导入演示' and cfg['icon_size']==48
        assert runtime.panels.windows['transfer-demo'].geometry().getRect()==(70,85,380,260)
        assert api.load_config()['items']==cfg['items']
        # Import the same panel id with different geometry: force the actual window to follow.
        changed=copy.deepcopy(cfg);changed['desktop_panels'][0]['geometry']=[95,100,400,250];changed['display_layout']={}
        export_configuration(example,changed,api);settings.stage_import(example);settings.commit();app.processEvents()
        assert runtime.panels.windows['transfer-demo'].geometry().getRect()==(95,100,400,250)
        saved=copy.deepcopy(cfg);disk=Path(api.CONFIG_PATH).read_bytes()
        changed=copy.deepcopy(cfg);changed['icon_size']=58;export_configuration(example,changed,api);settings.stage_import(example)
        reload_dock=runtime.dock.reload;failures=[]
        def fail_once():
            if not failures:failures.append(True);raise RuntimeError('simulated apply error')
            return reload_dock()
        runtime.dock.reload=fail_once
        try:settings.commit()
        finally:runtime.dock.reload=reload_dock
        assert cfg==saved and api.load_config()['items']==saved['items'] and settings.import_candidate is not None
        assert '原配置已恢复' in settings.status.text()
        assert (Path(api.CONFIG_DIR)/'config.before-import.json').read_bytes()==disk
        # Explicit startup preference changes remain staged; failure rolls back the mocked registration.
        changed=copy.deepcopy(cfg);changed['autostart']=not cfg['autostart'];export_configuration(example,changed,api);settings.stage_import(example)
        autostart_calls.clear();api.save_config=lambda value:False
        try:settings.commit()
        finally:api.save_config=save
        assert autostart_calls==[changed['autostart'],saved['autostart']] and cfg==saved
        settings.reject();runtime.show_settings()
        settings.tabs.setCurrentIndex(settings.tabs.count()-1)
        labels=[]
        for widget in settings.findChildren(QLabel):
            if widget.text()==api.CONFIG_DIR:labels.append((widget,widget.text()));widget.setText(r'D:\BigFishDockpro\data')
        settings.tabs.pages.currentWidget().verticalScrollBar().setValue(settings.tabs.pages.currentWidget().verticalScrollBar().maximum())
        app.processEvents();settings.grab().save(str(Path(output)/'configuration-transfer.png'))
        for widget,text in labels:widget.setText(text)
        checks.append('configuration transfer: JSON envelope/raw/BOM roundtrip, wrong app/schema/duplicate/type rejection, atomic export protects existing/live files; staged preview/cancel, pending-batch conflict, import backup, same-id geometry, save/apply-failure rollback and mocked startup rollback; save stays open, no application launch or real registry changes')
    finally:
        api.set_autostart=setter;settings.import_candidate=None;settings.import_path=None;settings.reject()
        cfg.clear();cfg.update(original);api.save_config(cfg);settings.apply_imported_state();settings.api=previous_settings_api
