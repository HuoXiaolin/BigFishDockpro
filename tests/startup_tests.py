"""Startup checks use a disposable registry key, never the user's Run entry."""
import copy
import winreg
from pathlib import Path
from types import SimpleNamespace
from startup_service import inspect_startup, repair_startup, read_entry, split_command


def run(api, tray, root, checks):
    original_cfg=copy.deepcopy(tray.cfg)
    original=read_entry(api)
    assert not original['error']
    exe=Path(root)/'startup target with spaces.exe';exe.write_bytes(b'fixture')
    previous=Path(root)/'old startup target.exe';previous.write_bytes(b'fixture')
    command='"'+str(exe)+'" --autostart'
    fake=SimpleNamespace(RUN_KEY=api.RUN_KEY,COMPAT_NAME=api.COMPAT_NAME,IS_FROZEN=True,
                         autostart_command=lambda:command,save_config=lambda cfg:True,log=api.log)
    def write(value,kind=winreg.REG_SZ):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,api.RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,api.COMPAT_NAME,0,kind,value)
    def clear():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,api.RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
            try:winreg.DeleteValue(key,api.COMPAT_NAME)
            except FileNotFoundError:pass
    try:
        clear();assert inspect_startup(fake)['status']=='missing'
        write('"'+str(previous)+'" --autostart');assert inspect_startup(fake)['status']=='different_path'
        previous.unlink();assert inspect_startup(fake)['status']=='missing_file'
        write('"'+str(exe)+'"');assert inspect_startup(fake)['status']=='arguments'
        write(7,winreg.REG_DWORD);assert inspect_startup(fake)['status']=='invalid'
        write(command);assert inspect_startup(fake)['status']=='ok'
        assert split_command(command)==[str(exe),'--autostart']
        write('"missing.exe" --autostart');before=read_entry(fake)
        fake.save_config=lambda cfg:False
        assert not repair_startup(fake,original_cfg)[0] and read_entry(fake)==before
        fake.save_config=lambda cfg:True
        assert repair_startup(fake,original_cfg)[0] and inspect_startup(fake)['status']=='ok'
        clear()
        from settings_dialog import SettingsDialog
        dialog=SettingsDialog(tray,api);dialog.reveal()
        pending_icon_size=dialog.fields['icon_size'].value()+1
        dialog.fields['icon_size'].setValue(pending_icon_size)
        write('"missing.exe" --autostart')
        dialog.startup_check.click();assert '不存在' in dialog.startup_status.text()
        save=api.save_config
        try:
            api.save_config=lambda cfg:False
            dialog.startup_repair.click()
            assert tray.cfg==original_cfg and read_entry(api)['command']=='"missing.exe" --autostart'
        finally:api.save_config=save
        dialog.startup_repair.click()
        assert inspect_startup(api)['status']=='ok' and tray.cfg['autostart']
        assert dialog.fields['icon_size'].value()==pending_icon_size and tray.cfg['icon_size']==original_cfg['icon_size']
        assert api.load_config()['autostart'] and '已修复' in dialog.startup_status.text()
        dialog.reject()
    finally:
        tray.cfg.update(original_cfg);api.save_config(original_cfg)
        if original['exists']:write(original['command'],original['kind'])
        else:clear()
    checks.append('startup repair: real private registry key; missing/moved/invalid/argument diagnostics, quoted paths, verified repair and enable, save-failure rollback, staged settings preserved')
