"""Bounded atomic settings storage with protected recovery after read failures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile

MAX_BYTES = 8 * 1024 * 1024


def _read(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('配置文件超过 8 MiB，已保留原文件。')
    return path.read_bytes()


def _decode(payload):
    if len(payload) > MAX_BYTES:
        raise ValueError('配置文件超过 8 MiB。')
    value = json.loads(payload.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('配置内容不是 JSON 对象。')
    return value


def _atomic(path, payload):
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ConfigStore:
    def __init__(self, path, log):
        self.path = Path(path)
        self.backup = self.path.with_name('config.last-good.json')
        self.damaged = self.path.with_name('config.corrupt.json')
        self.log = log
        self.blocked = False
        self.message = ''
        self._preserved = None

    def status(self):
        return {'blocked': self.blocked, 'message': self.message,
                'backup': str(self.backup), 'damaged': str(self.damaged)}

    def _protect(self, error, payload=None):
        self.blocked = True
        self.message = '配置读取失败，已暂停自动覆盖；请在设置中恢复配置。'
        self.log(self.message+' '+str(error))
        if payload is not None:
            try:
                _atomic(self.damaged, payload)
                self._preserved = hashlib.sha256(payload).digest()
            except OSError as failure:
                self.log('无法保留损坏配置：'+str(failure))

    def load(self, defaults, missing_defaults=None):
        self.blocked = False
        self.message = ''
        self._preserved = None
        payload = None
        try:
            payload = _read(self.path)
            data = _decode(payload)
        except FileNotFoundError:
            return copy.deepcopy(defaults)
        except (OSError, ValueError, UnicodeError, RecursionError) as error:
            self._protect(error, payload)
            try:
                recovered = _decode(_read(self.backup))
            except (OSError, ValueError, UnicodeError, RecursionError):
                return copy.deepcopy(defaults)
            # Recovery is writable only after the exact failed source was preserved.
            if self._preserved is not None:
                self.blocked = False
                self.message = '已恢复最近有效配置；原配置保留在 config.corrupt.json。'
                self.log(self.message)
            else:
                self.message = '已读取最近有效配置；原文件无法读取或保留，暂不自动覆盖。'
            data = recovered
        result = copy.deepcopy(defaults)
        for key,value in (missing_defaults or {}).items():
            if key in defaults and key not in data:result[key]=copy.deepcopy(value)
        for key in defaults:
            if key in data:
                result[key] = data[key]
        return result

    def save(self, data, explicit_recovery=False):
        try:
            payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
            _decode(payload)
            if self.blocked and not explicit_recovery:
                self.log('配置处于保护状态，未覆盖原文件。')
                return False
            current = None
            try:
                current = _read(self.path)
            except FileNotFoundError:
                pass
            if current is not None:
                try:
                    _decode(current)
                except (ValueError, UnicodeError, RecursionError) as error:
                    if hashlib.sha256(current).digest() != self._preserved:
                        self._protect(error, current)
                    if not explicit_recovery and (self.blocked or hashlib.sha256(current).digest() != self._preserved):
                        return False
                    # A failed preservation must never be bypassed by explicit reset.
                    if hashlib.sha256(current).digest() != self._preserved:
                        return False
                else:
                    # Existing installations may not yet have a recovery copy.
                    if not self.backup.exists():
                        _atomic(self.backup, current)
                    if current == payload:
                        self.blocked=False
                        return True
            _atomic(self.path, payload)
            self.blocked = False
            self._preserved = None
            # The newest successfully committed state is the recovery baseline.
            try:
                _atomic(self.backup, payload)
            except OSError as error:
                self.log('配置已保存，恢复副本尚未更新：'+str(error))
            if explicit_recovery:
                self.message = '配置已恢复并保存；原损坏文件仍保留。'
            return True
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as error:
            self.log('保存配置失败：'+str(error))
            return False
