"""Inspect and repair only this application's per-user startup command."""
import ctypes
import os
import winreg


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


def inspect_startup(api):
    entry = read_entry(api)
    result = dict(entry, expected=api.autostart_command(), path='', status='missing', message='尚未登记自启动项。')
    if entry['error']:
        result.update(status='unreadable', message='无法读取自启动项，请检查当前用户的注册表权限。')
        return result
    if not entry['exists']: return result
    if entry['kind'] not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(entry['command'], str):
        result.update(status='invalid', message='启动命令格式无效，需要修复。')
        return result
    actual = split_command(os.path.expandvars(entry['command']))
    expected = split_command(api.autostart_command())
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
    result.update(status='ok', message='自启动路径与当前运行版本一致，参数正常。')
    return result


def repair_startup(api, cfg):
    previous = read_entry(api)
    if previous['error']: return False, '读取启动项失败，未修改设置。'
    command = api.autostart_command()
    expected = split_command(command)
    targets = expected[:1 if api.IS_FROZEN else 2]
    if not targets or any(not os.path.isfile(path) for path in targets):
        return False, '当前启动文件不存在，无法登记自启动。'
    changed = False
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, api.RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            winreg.SetValueEx(key, api.COMPAT_NAME, 0, winreg.REG_SZ, command)
            changed = True
            if inspect_startup(api)['status'] != 'ok': raise OSError('启动项写入后校验失败')
            if api.save_config(dict(cfg, autostart=True)) is False: raise OSError('软件配置保存失败')
        return True, '自启动路径已修复并启用，已指向当前运行版本。'
    except OSError as error:
        if changed:
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, api.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    if previous['exists']: winreg.SetValueEx(key, api.COMPAT_NAME, 0, previous['kind'], previous['command'])
                    else:
                        try: winreg.DeleteValue(key, api.COMPAT_NAME)
                        except FileNotFoundError: pass
            except OSError:
                api.log('自启动恢复失败，需要重新检测启动项。')
                return False, '修复失败且原启动项未能恢复，请重新检测；其他设置未保存。'
        api.log('自启动修复失败: '+str(error))
        return False, '修复失败，已保留原设置：'+str(error)
