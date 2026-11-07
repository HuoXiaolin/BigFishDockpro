"""Register an early interactive logon task, with the existing Run entry as fallback."""
import ctypes
import os
import subprocess
import winreg
from startup_task import LogonTask, SWITCH, task_xml

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
TASK_ERRORS = (OSError, ValueError, SyntaxError, subprocess.SubprocessError)


def split_command(command):
    if not isinstance(command, str) or not command.strip(): return []
    shell = ctypes.windll.shell32
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    values = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not values: return []
    try: return [values[index] for index in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(values, ctypes.c_void_p))


def read_entry(api):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, api.RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            command, kind = winreg.QueryValueEx(key, api.COMPAT_NAME)
        return {'exists': True, 'command': command, 'kind': kind, 'error': ''}
    except FileNotFoundError:
        return {'exists': False, 'command': '', 'kind': winreg.REG_SZ, 'error': ''}
    except OSError as error:
        return {'exists': False, 'command': '', 'kind': winreg.REG_SZ, 'error': str(error)}


def scheduler(api):
    if api.RUN_KEY == RUN_KEY and not os.environ.get('FISHDOCK_TEST_DESKTOP'):
        return LogonTask()


def set_run(api, entry=None):
    if entry is not None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, api.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, api.COMPAT_NAME, 0, entry['kind'], entry['command'])
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, api.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, api.COMPAT_NAME)
        except FileNotFoundError:pass


def run_disabled(api):
    if api.RUN_KEY != RUN_KEY:return False
    approved = r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, approved) as key:
            value, _ = winreg.QueryValueEx(key, api.COMPAT_NAME)
        return isinstance(value, bytes) and len(value)>0 and value[0] in (3,7)
    except OSError:
        return False


def evaluate(api, entry, task=None):
    if task:
        entry = dict(exists=True, command=task['command'], kind=winreg.REG_SZ, error='')
    result = dict(entry, expected=api.autostart_command(), path='', status='missing', message='尚未登记自启动项。')
    result['method'] = 'task' if task else 'run'
    if entry['error']:
        result.update(status='unreadable', message='无法读取自启动项，请检查当前用户的注册表权限。')
        return result
    if not entry['exists']: return result
    if entry['kind'] not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(entry['command'], str):
        result.update(status='invalid', message='启动命令格式无效，需要修复。')
        return result
    actual = split_command(os.path.expandvars(entry['command']))
    expected = split_command(api.autostart_command())
    if task:expected.append(SWITCH)
    if not actual:
        result.update(status='invalid', message='启动命令为空，需要修复。')
        return result
    result['path'] = actual[0]
    # Both the interpreter and script must exist for the source edition.
    targets = [actual[0]]
    if not api.IS_FROZEN and len(actual)>1 and not actual[1].startswith('-'): targets.append(actual[1])
    if any(not os.path.isfile(path) for path in targets):
        result.update(status='missing_file', message='登记的启动文件不存在，可能已移动或改名。')
        return result
    path_count = 1 if api.IS_FROZEN else 2
    def path_key(path): return os.path.normcase(os.path.abspath(path))
    if len(actual) < path_count or any(path_key(actual[index]) != path_key(expected[index]) for index in range(path_count)):
        result.update(status='different_path', message='启动项指向其他位置，与当前运行版本不一致。')
        return result
    if actual[path_count:] != expected[path_count:]:
        result.update(status='arguments', message='自启动参数不正确，需要修复。')
        return result
    if task and (not task['valid'] or path_key(task['directory']) != path_key(os.path.dirname(expected[path_count-1]))):
        result.update(status='invalid', message='登录任务的触发或运行设置已更改，需要修复。')
        return result
    if (task and not task['enabled']) or (not task and run_disabled(api)):
        result.update(status='disabled', message='Windows 中已禁用此启动项，可点击修复并启用。')
        return result
    result.update(status='ok', message=('登录时尽早启动 · 路径与当前运行版本一致。' if task else
                                      'Windows 兼容启动项 · 路径正确，启动时间由 Windows 决定。'))
    return result


def inspect_startup(api):
    task = None
    try:
        service=scheduler(api)
        if service:task=service.read()
    except TASK_ERRORS:pass
    return evaluate(api,read_entry(api),task)


def configure(api, enabled, *, automatic=False, save=None):
    previous = read_entry(api)
    if previous['error']:raise OSError('读取启动项失败。')
    service = previous_task = None
    try:
        service = scheduler(api)
        if service:previous_task=service.read()
    except TASK_ERRORS as error:
        if not enabled:raise
        api.log('登录任务暂不可用: '+str(error));service=None
    if automatic and ((run_disabled(api) and previous['exists']) or (previous_task and not previous_task['enabled'])):
        return 'disabled'
    command = api.autostart_command()
    argv = split_command(command)
    targets = argv[:1 if api.IS_FROZEN else 2]
    if enabled and (not targets or any(not os.path.isfile(path) for path in targets)):
        raise OSError('当前启动文件不存在。')
    task_changed = run_changed = False
    mode = 'disabled'
    try:
        if enabled and service:
            if previous_task and evaluate(api,previous,previous_task)['status']=='ok':
                mode='task'
            else:
                try:
                    service.write(task_xml(service.sid,argv,os.path.dirname(targets[-1])))
                except TASK_ERRORS as error:
                    if previous_task:raise
                    api.log('无法注册登录任务，保留 Windows 兼容启动项: '+str(error))
                else:
                    task_changed=True
                    registered=service.read()
                    if not registered or evaluate(api,previous,registered)['status']!='ok':
                        raise OSError('登录任务注册后校验失败。')
                    mode='task'
        elif not enabled and previous_task:
            service.remove();task_changed=True
        wanted = dict(command=command,kind=winreg.REG_SZ) if enabled and mode!='task' else None
        if wanted is not None:
            if run_disabled(api):raise OSError('兼容启动项已在 Windows 中禁用，请在系统启动应用中启用。')
            mode='run'
        if (wanted is None and previous['exists']) or (wanted is not None and any(previous[k]!=v for k,v in wanted.items())):
            set_run(api,wanted);run_changed=True
        if save is not None and save() is False:raise OSError('软件配置保存失败。')
    except TASK_ERRORS:
        try:
            if task_changed:
                if previous_task:service.write(previous_task['xml'])
                else:service.remove()
            if run_changed:set_run(api,previous if previous['exists'] else None)
        except TASK_ERRORS as error:
            api.log('自启动恢复失败: '+str(error))
            raise OSError('原启动项未能完全恢复，请重新检测。') from error
        raise
    return mode


def set_enabled(api, enabled, *, automatic=False):
    try:
        mode = configure(api, enabled, automatic=automatic)
        if mode!='disabled' or not automatic:api.log('自启动方式：'+mode)
        return True
    except TASK_ERRORS as error:
        api.log('设置自启动失败: '+str(error));return False


def repair_startup(api, cfg):
    try:
        mode = configure(api, True, save=lambda:api.save_config(dict(cfg, autostart=True)))
    except TASK_ERRORS as error:
        api.log('自启动修复失败: '+str(error))
        return False, '修复失败：'+str(error)
    return True, '已修复并启用自启动。' if mode=='run' else '已修复并启用登录时尽早启动。'


def remove_owned(api):
    expected=split_command(api.autostart_command())
    try:
        service=scheduler(api)
        task=service.read() if service else None
        if task and split_command(task['command'])==expected+[SWITCH]:service.remove()
    except TASK_ERRORS as error:
        api.log('移除登录任务失败: '+str(error))
    try:
        entry=read_entry(api)
        if entry['exists'] and split_command(entry['command'])==expected:set_run(api)
    except OSError as error:
        api.log('移除兼容启动项失败: '+str(error))
