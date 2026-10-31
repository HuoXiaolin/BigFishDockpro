"""Store launch references and Shell-link metadata; never copy source files."""
import os
from pathlib import Path
from urllib.parse import urlsplit

TEXT_FIELDS=('arguments','working_directory','source_path','verb','app_user_model_id')

def metadata(item,strict=False):
    result={}
    for key in TEXT_FIELDS:
        value=item.get(key,'')
        if not isinstance(value,str) or '\x00' in value or len(value)>32768 or (key=='verb' and value not in ('','open','runas')):
            if strict:raise ValueError('快捷入口字段无效：'+key)
            continue
        if value:result[key]=value
    for key,valid in [('icon_index',lambda x:-65535<=x<=65535),('show_command',lambda x:x in (1,3,7))]:
        if key in item:
            value=item[key]
            if type(value) is not int or not valid(value):
                if strict:raise ValueError('快捷入口字段无效：'+key)
            elif (key=='icon_index' and value) or (key=='show_command' and value!=1):result[key]=value
    return result

def is_reference(path):
    if path.lower().startswith('shell:'):return True
    try:
        parsed=urlsplit(path)
        return bool(parsed.scheme and len(parsed.scheme)>1 and not parsed.scheme.startswith('\\'))
    except ValueError:return False

def map_entry(item,validate=True):
    path=str(item.get('path','')).strip()
    if not path:return None
    original=path;info={};seen=set()
    for _ in range(8):
        if is_reference(path) or not path.lower().endswith('.lnk'):break
        key=os.path.normcase(os.path.abspath(path))
        if key in seen:return None
        seen.add(key)
        from shortcut_targets import lnk_metadata
        details=lnk_metadata(path)
        if not details:return None
        target=details['path']
        if not is_reference(target) and not os.path.isabs(target):target=os.path.abspath(os.path.join(os.path.dirname(path),target))
        info['arguments']=(details.get('arguments','')+' '+info.get('arguments','')).strip()
        for field in ('working_directory','icon','icon_index','show_command','verb','app_user_model_id'):
            if field not in info and details.get(field):info[field]=details[field]
        path=target
    if path.lower().endswith('.lnk'):return None
    if not is_reference(path) and path.lower().endswith('.url'):
        from configparser import ConfigParser,Error
        try:
            data=Path(path).read_bytes()[:65536]
            try:text=data.decode('utf-8-sig')
            except UnicodeDecodeError:text=data.decode('mbcs')
            parser=ConfigParser(interpolation=None);parser.read_string(text)
            address=parser.get('InternetShortcut','URL',fallback='').strip()
            if not address:return None
            if address.lower().startswith('file:'):
                from shortcut_targets import shortcut_target
                address=shortcut_target(path)
                if not address:return None
            icon=parser.get('InternetShortcut','IconFile',fallback='').strip()
            if icon:info.setdefault('icon',os.path.expandvars(icon))
            path=address
        except (OSError,ValueError,UnicodeError,Error):return None
    prefix='shell:::{4234d49b-0245-4df3-b780-3893943456e1}\\'
    if path.casefold().startswith(prefix):path='shell:AppsFolder\\'+path[len(prefix):]
    if validate and not is_reference(path) and not os.path.exists(path):return None
    result=dict(item,path=path if is_reference(path) else os.path.abspath(path))
    if original!=path:
        result.setdefault('name',Path(original).stem)
        result['source_path']=original
    for key,value in info.items():
        if key not in result and value:result[key]=value
    clean=metadata(result)
    for key in TEXT_FIELDS+('icon_index','show_command'):result.pop(key,None)
    result.update(clean)
    return result

def map_items(items):
    return [dict(item) if item.get('sep') else (map_entry(item,validate=False) or dict(item)) for item in items]
