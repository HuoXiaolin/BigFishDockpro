"""Current-user Windows Credential Manager records, separate from config export."""
import ctypes as C
from ctypes import wintypes as W
import json
from mail_accounts import account_binding


GENERIC = 1
LOCAL_MACHINE = 2
NOT_FOUND = 1168
BLOB_MAX = 2560


class Credential(C.Structure):
    _fields_ = [('flags', W.DWORD), ('type', W.DWORD), ('target', W.LPWSTR), ('comment', W.LPWSTR),
                ('written', W.FILETIME), ('size', W.DWORD), ('blob', C.POINTER(C.c_ubyte)),
                ('persist', W.DWORD), ('attributes_count', W.DWORD), ('attributes', C.c_void_p),
                ('alias', W.LPWSTR), ('username', W.LPWSTR)]


def target_name(identity):
    return 'BigFishDockpro/mail/' + identity


def read(identity):
    vault = C.WinDLL('advapi32', use_last_error=True)
    pointer = C.POINTER(Credential)()
    vault.CredReadW.argtypes = (W.LPCWSTR, W.DWORD, W.DWORD, C.POINTER(C.POINTER(Credential)))
    vault.CredReadW.restype = W.BOOL
    if not vault.CredReadW(target_name(identity), GENERIC, 0, C.byref(pointer)):
        if C.get_last_error() == NOT_FOUND:
            return {}
        raise OSError('无法读取 Windows 凭据库。')
    vault.CredFree.argtypes = (C.c_void_p,)
    try:
        credential = pointer.contents
        try:
            value = json.loads(C.string_at(credential.blob, credential.size)) if credential.size <= BLOB_MAX else None
        except (UnicodeError, ValueError):
            value = None
        if not isinstance(value, dict):
            raise OSError('邮箱凭据无法读取，请重新授权。')
        return value
    finally:
        vault.CredFree(pointer)


def write(identity, value):
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > BLOB_MAX:
        raise OSError('授权数据过长，无法保存到 Windows 凭据库。')
    vault = C.WinDLL('advapi32', use_last_error=True)
    vault.CredWriteW.argtypes = (C.POINTER(Credential), W.DWORD)
    vault.CredWriteW.restype = W.BOOL
    blob = (C.c_ubyte * len(payload)).from_buffer_copy(payload)
    credential = Credential(type=GENERIC, target=target_name(identity), size=len(payload), blob=blob,
                            persist=LOCAL_MACHINE, username='BigFishDockpro')
    try:
        if not vault.CredWriteW(C.byref(credential), 0):
            raise OSError('无法保存到 Windows 凭据库。')
    finally:
        C.memset(blob, 0, len(payload))


def remove(identity):
    vault = C.WinDLL('advapi32', use_last_error=True)
    vault.CredDeleteW.argtypes = (W.LPCWSTR, W.DWORD, W.DWORD)
    vault.CredDeleteW.restype = W.BOOL
    if not vault.CredDeleteW(target_name(identity), GENERIC, 0) and C.get_last_error() != NOT_FOUND:
        raise OSError('无法清理 Windows 凭据库中的邮箱授权。')


def load_bound(account):
    stored = read(account['id'])
    value = stored.get('secret')
    return value if stored.get('binding') == account_binding(account) and isinstance(value, dict) else {}


def save_bound(account, secret):
    write(account['id'], dict(binding=account_binding(account), secret=secret))
