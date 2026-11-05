"""On-demand checks of saved references; never scan drives or edit source files."""
import copy
import ctypes
import ntpath
import os
from dock_folders import application_entries


def reference_key(path):
    # Do not resolve links here: a disconnected network target must not block the UI.
    return os.path.normcase(os.path.abspath(path))


def candidates(cfg):
    result=[];seen={}
    for kind,rows in (('Dock',application_entries(cfg.get('items',[]))),('桌面卡片',cfg.get('desktop_entries',[]))):
        for row in rows:
            path=row.get('path','')
            if not path or not os.path.isabs(path):continue
            key=reference_key(path)
            if key in seen:
                saved=seen[key];saved['count']+=1
                if kind not in saved['kind'].split(' / '):saved['kind']+=' / '+kind
            else:
                item={'path':path,'name':row.get('name') or os.path.basename(path),'kind':kind,'count':1}
                result.append(item);seen[key]=item
    return result


def drive_kind(path):
    drive=ntpath.splitdrive(path)[0]
    if path.startswith(('\\\\','//')):return 4
    if not drive:return 0
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDriveTypeW.argtypes=[ctypes.c_wchar_p];kernel.GetDriveTypeW.restype=ctypes.c_uint
    return kernel.GetDriveTypeW(drive+'\\')


def inspect(rows,cancelled,progress=None):
    result=[];drives={}
    for index,row in enumerate(rows):
        if cancelled.is_set():break
        path=row['path'];drive=ntpath.splitdrive(path)[0]
        kind=drives.setdefault(drive,drive_kind(path)) if drive not in drives else drives[drive]
        if kind in (2,4,5):
            result.append(dict(row,status='网络或可移动位置，未访问',missing=False))
        elif kind not in (3,6):
            result.append(dict(row,status='驱动器暂不可访问',missing=False))
        else:
            try:os.stat(path)
            except FileNotFoundError:
                try:os.stat(drive+'\\')
                except OSError:result.append(dict(row,status='驱动器暂不可访问',missing=False))
                else:result.append(dict(row,status='目标不存在',missing=True))
            except OSError:result.append(dict(row,status='暂不可访问，未判为失效',missing=False))
        if progress:progress(index+1,len(rows))
    return result


def mapped_replacement(item,new):
    from shortcut_mapping import map_entry,TEXT_FIELDS
    link=new.casefold().endswith(('.lnk','.url'))
    candidate=copy.deepcopy(item)
    if link:
        # A newly selected shortcut owns its parameters, working directory and icon.
        for field in TEXT_FIELDS+('icon','icon_index','show_command'):candidate.pop(field,None)
    else:
        candidate.pop('source_path',None);candidate.pop('app_user_model_id',None)
        if candidate.get('working_directory') and not os.path.isdir(candidate['working_directory']):candidate.pop('working_directory',None)
        if candidate.get('icon') and not os.path.exists(candidate['icon']):candidate.pop('icon',None);candidate.pop('icon_index',None)
    candidate['path']=new
    mapped=map_entry(candidate)
    if mapped is None:raise ValueError('无法读取新的启动目标，请检查快捷方式和目标文件。')
    return mapped


def change(cfg,old,new=None):
    result=copy.deepcopy(cfg);key=reference_key(old)
    if new:
        new=os.path.abspath(new)
        if not os.path.exists(new):raise ValueError('新的文件或文件夹不存在。')
    def replace(item):
        if not item.get('path') or reference_key(item['path'])!=key:return item
        return mapped_replacement(item,new) if new else None
    items=[]
    for item in result.get('items',[]):
        if 'folder' in item:
            children=[value for child in item['folder'] if (value:=replace(child)) is not None]
            items.extend([dict(item,folder=children)] if len(children)>1 else children)
        elif (replacement:=replace(item)) is not None:items.append(replacement)
    result['items']=items
    rows=[]
    for row in result.get('desktop_entries',[]):
        if reference_key(row['path'])!=key:rows.append(row)
        elif new:rows.append(dict(row,path=new,name=os.path.basename(new)))
    result['desktop_entries']=rows
    def keys(values):return list(dict.fromkeys(reference_key(new) if reference_key(value)==key else value for value in values if reference_key(value)!=key or new))
    result['desktop_excluded']=keys(result.get('desktop_excluded',[]))
    for panel in result.get('desktop_panels',[]):
        for field in ('pinned_paths','excluded'):
            if field in panel:panel[field]=keys(panel[field])
    return result
