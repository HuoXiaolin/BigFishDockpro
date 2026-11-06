"""Local flash inbox records. All persisted colours are stable category IDs."""
import re
import uuid
import time
from appearance_presets import VIVID_BLUE,VIVID_GREEN,VIVID_RED

COLORS = {'blue':('晴空蓝',VIVID_BLUE), 'green':('青芽绿',VIVID_GREEN),
          'red':('珊瑚红',VIVID_RED), 'amber':('杏橙','#ffaf57'), 'purple':('葡萄紫','#ab85ea')}
PALETTES = [('跟随主题','theme'), ('活力原色','vivid')]
MAX_TEXT = 8192
MAX_ACTIVE = 400
MAX_TRASH = 200
MAX_BYTES = 2 * 1024 * 1024
ID = re.compile(r'[a-zA-Z0-9_-]{1,80}')


def new_entry(text, color):
    if not text.strip():
        raise ValueError('先写下或拖入一段文字。')
    if len(text) > MAX_TEXT:
        raise ValueError(f'每条闪念最多 {MAX_TEXT} 个字，请分条保存。')
    return dict(id=uuid.uuid4().hex, text=text.strip(), color=color, created=int(time.time()),
                done=False, pinned=False, deleted=False, due=0, notified=False)


def normalize_entries(value, strict=False):
    if not isinstance(value, list) or len(value) > MAX_ACTIVE + MAX_TRASH:
        if strict: raise ValueError('闪念列表格式或数量超出限制。')
        value=value[:MAX_ACTIVE+MAX_TRASH] if isinstance(value,list) else []
    rows=[]; seen=set(); active=trash=total=0
    for raw in value:
        try:
            if not isinstance(raw,dict): raise ValueError
            identity=raw['id']; text=raw['text']; color=raw['color']
            if not isinstance(identity,str) or not ID.fullmatch(identity) or identity in seen: raise ValueError
            if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT or color not in COLORS: raise ValueError
            row=dict(id=identity,text=text,color=color)
            for key in ('created','due'):
                stamp=raw.get(key,0)
                if type(stamp) is not int or not 0<=stamp<=4102444800: raise ValueError
                row[key]=stamp
            for key in ('done','pinned','deleted','notified'):
                flag=raw.get(key,False)
                if type(flag) is not bool: raise ValueError
                row[key]=flag
            size=len(text.encode('utf-8'))
            if (trash>=MAX_TRASH if row['deleted'] else active>=MAX_ACTIVE) or total+size>MAX_BYTES:
                if strict: raise OverflowError
                continue
            rows.append(row);seen.add(identity);total+=size
            if row['deleted']: trash+=1
            else: active+=1
        except OverflowError:
            raise ValueError('闪念箱或回收站已满，请导出备份后整理已有记录。') from None
        except (KeyError,TypeError,ValueError):
            if strict: raise ValueError('闪念内容、标识、颜色或提醒时间无效。') from None
    return rows


def normalize_draft(value,strict=False):
    if value == {}: return {}
    if isinstance(value,dict):
        target=value.get('id',''); text=value.get('text','')
        if (isinstance(target,str) and (target=='' or ID.fullmatch(target)) and
                isinstance(text,str) and len(text)<=MAX_TEXT and isinstance(value.get('color','blue'),str) and value.get('color','blue') in COLORS):
            return dict(id=target,text=text,color=value.get('color','blue')) if text or target else {}
    if strict: raise ValueError('闪念草稿无效或过长。')
    return {}


def filtered(rows, view, color, query):
    words=query.casefold().split()
    matches=[r for r in rows if r['deleted']==(view=='trash')
             and (view=='trash' or r['done']==(view=='done'))
             and (not color or color==r['color']) and all(w in r['text'].casefold() for w in words)]
    return sorted(matches,key=lambda r:(r['pinned'],r['created']),reverse=True)
