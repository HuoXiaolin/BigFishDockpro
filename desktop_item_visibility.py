"""Recoverable, opt-in hiding of collected files directly on configured desktops."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from app_catalog import path_key


class CollectedDesktopItems:
    def __init__(self, roots, journal=None):
        self.roots={path_key(str(root)) for root in roots}
        self.journal=Path(journal) if journal else None
        self.records={};self.handles={};self.message='';self.recovery_invalid=False
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.SetFileAttributesW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD]
        self.kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        self.kernel.CreateFileW.restype=wintypes.HANDLE
        self.kernel.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        if self.journal and self.journal.exists():
            try:
                data=json.loads(self.journal.read_text(encoding='utf-8'))
                if data.get('project')!='BigFishDockpro' or not isinstance(data.get('items'),list):raise ValueError('invalid visibility journal')
                for row in data['items'][:4096]:
                    if not isinstance(row,dict) or not isinstance(row.get('path'),str):continue
                    if path_key(str(Path(row['path']).parent)) not in self.roots:continue
                    if type(row.get('dev')) is not int or type(row.get('ino')) is not int:continue
                    self.records[path_key(row['path'])]=row
                self.restore()
            except (OSError,ValueError,TypeError):
                self.recovery_invalid=True
                self.message='无法读取桌面项目恢复记录，未隐藏新项目。'

    def persist(self):
        if not self.journal:raise OSError('A durable visibility journal is required')
        self.journal.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.journal.with_suffix('.tmp')
        temporary.write_text(json.dumps({'project':'BigFishDockpro','items':list(self.records.values())},ensure_ascii=False),encoding='utf-8')
        os.replace(temporary,self.journal)

    @staticmethod
    def same(path,row):
        try:
            stat=os.stat(path,follow_symlinks=False)
            return (stat.st_dev,stat.st_ino)==(row['dev'],row['ino'])
        except OSError:return False

    def actual_path(self,key,row):
        if key in self.handles:
            buffer=ctypes.create_unicode_buffer(32768)
            if self.kernel.GetFinalPathNameByHandleW(self.handles[key],buffer,len(buffer),0):
                actual=buffer.value
                if self.same(actual,row):return actual
        if self.same(row['path'],row):return row['path']
        # Recover a rename after an interrupted session, without traversing folders.
        parent=Path(row['path']).parent
        if path_key(str(parent)) in self.roots:
            try:
                with os.scandir(parent) as entries:
                    for number,entry in enumerate(entries):
                        if number>=4096:break
                        if self.same(entry.path,row):return entry.path
            except OSError:pass
        return None

    def restore(self, keep=()):
        if self.recovery_invalid:return False
        keep=set(keep);failed=False
        for key,row in list(self.records.items()):
            if key in keep and self.same(row['path'],row):continue
            path=self.actual_path(key,row)
            if path:
                try:
                    attrs=os.stat(path,follow_symlinks=False).st_file_attributes
                    if attrs&2 and not self.kernel.SetFileAttributesW(path,(attrs&~2) or 0x80):raise ctypes.WinError(ctypes.get_last_error())
                except OSError:failed=True;continue
            self.records.pop(key,None)
            handle=self.handles.pop(key,None)
            if handle:self.kernel.CloseHandle(handle)
        try:
            if self.records:self.persist()
            elif self.journal:self.journal.unlink(missing_ok=True)
        except OSError:failed=True
        self.message='部分桌面项目未恢复，请检查数据目录的 desktop_items_visibility.json。' if failed else ''
        return not failed

    def apply(self,paths):
        if self.recovery_invalid:return False
        desired={path_key(str(path)):os.path.abspath(path) for path in paths if path_key(str(Path(path).parent)) in self.roots}
        self.restore(desired)
        errors=[];prepared={};added=[]
        for key,path in list(desired.items())[:4096]:
            try:
                stat=os.stat(path,follow_symlinks=False);attrs=stat.st_file_attributes
                if key in self.records:
                    if not attrs&2:prepared[key]=(path,attrs)
                    continue
                if not stat.st_ino or attrs&(2|4|0x400):continue
                self.records[key]={'path':path,'dev':stat.st_dev,'ino':stat.st_ino}
                added.append(key);prepared[key]=(path,attrs)
            except OSError:errors.append(path)
        if added:
            try:self.persist()  # Durable batch snapshot before the first attribute change.
            except OSError:
                for key in added:self.records.pop(key,None)
                self.message='无法保存恢复记录，未隐藏新项目。'
                return False
        for key,(path,attrs) in prepared.items():
            handle=self.kernel.CreateFileW(path,0x80,7,None,3,0x02000000,None)
            if handle and handle!=ctypes.c_void_p(-1).value:
                previous=self.handles.pop(key,None)
                if previous:self.kernel.CloseHandle(previous)
                self.handles[key]=handle
            if not self.kernel.SetFileAttributesW(path,attrs|2):errors.append(path)
        if errors:self.message='部分项目无法隐藏，仍保留在桌面；未移动或删除文件。'
        return not errors

    def close(self):
        self.restore()
        for handle in self.handles.values():self.kernel.CloseHandle(handle)
        self.handles.clear()
