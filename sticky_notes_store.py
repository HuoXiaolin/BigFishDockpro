"""Bounded note records shared by settings, transfer and the desktop editor."""
import copy
import re
import uuid
from screen_layout import valid_record

STYLES=[('液态玻璃','glass'),('经典纸张','paper'),('极简纯色','plain')]
COLORS=[('暖黄','#fff1a8'),('樱粉','#ffdce5'),('薄荷','#d4eedc'),('冰蓝','#cfe8fa'),('浅紫','#e3ddf6'),('暖杏','#f6dfbf'),('雾白','#eef1f5')]


def normalize_notes(rows,strict=False,limit=64):
    if not isinstance(rows,list):
        if strict:raise ValueError('便签列表格式不正确。')
        return []
    if strict and len(rows)>limit:raise ValueError('便签数量超出限制。')
    result=[];seen=set()
    for raw in rows[:limit]:
        if not isinstance(raw,dict):
            if strict:raise ValueError('便签条目格式不正确。')
            continue
        html=raw.get('html','');text=raw.get('text','')
        if not isinstance(html,str) or not isinstance(text,str) or len(html)>131072 or len(text)>32000:
            if strict:raise ValueError('便签内容格式不正确或过长。')
            continue
        identity=raw.get('id')
        if not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',identity):
            if strict:raise ValueError('便签标识格式不正确。')
            identity=uuid.uuid4().hex
        if identity in seen:
            if strict:raise ValueError('便签标识重复。')
            continue
        seen.add(identity)
        style=raw.get('style','glass');color=raw.get('color','#cfe8fa')
        if style not in {key for _,key in STYLES} or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
            if strict:raise ValueError('便签外观选项不正确。')
            style,color='glass','#cfe8fa'
        row={'id':identity,'title':str(raw.get('title') or '新便签')[:60],'html':html,'text':text,
             'style':style,'color':color.lower(),'updated':str(raw.get('updated',''))[:40]}
        for key in ('pinned','locked','collapsed'):row[key]=raw.get(key) is True
        row['visible']=raw.get('visible',True) is True
        geometry=raw.get('geometry')
        if isinstance(geometry,list) and len(geometry)==4 and all(type(n) is int and abs(n)<1000000 for n in geometry) and 1<=geometry[2]<=10000 and 1<=geometry[3]<=10000:row['geometry']=list(geometry)
        record=valid_record(raw.get('layout'))
        if record:row['layout']=record
        result.append(row)
    return result


def clean_editor_html(html):
    # Font size belongs to the current screen; only text formatting is persisted.
    return re.sub(r'font-size\s*:[^;"}]+;?', '', html,flags=re.I)
