"""A small declarative format for native desktop cards."""
import datetime
import json
import math
import re
from uuid import uuid4

from screen_layout import valid_record


MAX_CARDS = 8
MAX_ROWS = 6
KINDS = {
    'text':'自定义文字', 'time':'时间', 'date':'日期', 'countdown':'倒计时',
    'cpu':'CPU 使用率', 'gpu':'GPU 使用率', 'memory':'内存使用率',
    'download':'下载速率', 'upload':'上传速率',
    'data':'本地 JSON 字段', 'remote':'在线 JSON 字段',
}
STYLES = {'follow':'跟随全局', 'solid':'纯色', 'clear':'全透明'}
ARRANGEMENTS={'list':'纵向列表','grid':'双列网格','image_left':'左图右文','image_right':'左文右图'}
TOOLS={'':'无','search':'浏览器搜索','pomodoro':'番茄钟','history':'历史上的今天','rates':'汇率与换算',
       'feed':'自定义在线数据','convert':'自定义单位换算'}
ENGINES={'bing':'必应','baidu':'百度','google':'Google','duckduckgo':'DuckDuckGo'}
CURRENCIES=('CNY','USD','EUR','JPY','HKD','GBP','AUD','CAD','KRW','SGD','CHF')
SAMPLERS = {'cpu':'cpu', 'gpu':'gpu', 'memory':'memory', 'download':'network', 'upload':'network'}
TEMPLATE = {
    'title':'桌面速览', 'style':'follow', 'width':240,
    'rows':[
        {'kind':'time','label':'本机时间'},
        {'kind':'cpu','label':'CPU'},
        {'kind':'countdown','label':'生日','value':'2027-06-18'},
    ],
}
PATH_TOKENS = re.compile(
    r'("(?:path|data_file)"\s*:\s*)("[A-Za-z]:\\[^"\r\n]*")(?=\s*[,}])'
    r'|"(?:[^"\\\r\n]|\\[^\r\n])*"'
)


def developer_prompt():
    return (
        '为大肥鱼 Dock 原生卡片编辑器生成配置。请只输出一个 JSON 对象，直接粘贴到编辑器的「导入 JSON」。\n'
        'title 是卡片名称，最多 28 字。style 取 follow（跟随全局）、solid（纯色）或 clear（透明）。'
        'width 是 190 到 640 的整数。rows 最多 6 行，每行使用 kind、label 和 value，label 可留空。\n'
        'kind 可选 '+ '、'.join(KINDS) +'。text 的 value 最多 260 字，可用 JSON 的 \\n 分行。'
        'countdown 的 value 是 YYYY-MM-DD。data 的 value 是 data_file 中的字段名；data_file 是本地 JSON 对象文件。\n'
        'arrangement 可取 list、grid、image_left、image_right。image 可省略，或填写对象 {"path":"本地图片路径","height":120,"fit":"contain"}，fit 也可用 cover。\n'
        'fonts 可设置 title、label、body 的像素字号。colors 可设置 surface、text、accent，值为 #RRGGBB。header_date 为 true 时显示当天日期。\n'
        'tool 可省略，或通过 kind 选择 search（engine 可为 bing、baidu、google、duckduckgo；也可提供含 {query} 的 HTTPS url）、pomodoro（minutes 和 break_minutes）、'
        'history（lang 为 zh 或 en，limit 为 1–5）、rates（from、to、amount）。\n'
        '可生成类似的新功能。feed 的 url 是公开 HTTPS JSON 地址，可用 {date}、{month}、{day} 表示当天日期。'
        '用 remote 行的 value 绑定点分隔路径，例如 current.temperature 或 items.0.title。interval 是刷新分钟数，15–1440，默认 1440。\n'
        'convert 接收 units 数组，每项有 name、factor，代表一单位等于多少基准单位，可选 offset。'
        '例如 [{"name":"千米","factor":1000},{"name":"米","factor":1}]。\n'
        'Windows 文件路径用正斜杠，例如 D:/图片/配图.png。相对文件路径从应用配置目录解析。只生成 JSON。\n'
        '我的卡片需求（替换此行）\n'
        '示例\n'+json.dumps(TEMPLATE,ensure_ascii=False,indent=2)
    )


def parse_card_json(raw):
    if len(raw)>8192:raise ValueError('卡片配置超过 8192 字符。')

    def quote_path(match):
        field, value = match.groups()
        if field is None:
            return match[0]
        try:
            if all(ord(char)>=32 for char in json.loads(value)):
                return match[0]
        except json.JSONDecodeError:
            pass
        # A path pasted from Explorer can have single separators, even before n or t.
        return field+re.sub(r'\\{1,2}',lambda _:r'\\',value)

    return validate_card(json.loads(PATH_TOKENS.sub(quote_path,raw)))


def local_path(value):
    if not isinstance(value,str) or len(value)>1024 or '\0' in value or '://' in value or value.startswith(('//','\\\\')):
        raise ValueError('请输入本机文件路径。')
    return value.strip()


def integer(value,low,high,message):
    if type(value) is not int or not low<=value<=high:raise ValueError(message)
    return value


def settings_object(value,name):
    if not isinstance(value,dict):raise ValueError(f'{name} 需要 JSON 对象。')
    return value


def validate_tool(raw):
    raw=settings_object(raw,'tool')
    kind=raw.get('kind','')
    if not isinstance(kind,str) or kind not in TOOLS:raise ValueError('卡片工具类型无效。')
    if kind=='search':
        engine=raw.get('engine','bing')
        if not isinstance(engine,str) or engine not in ENGINES:raise ValueError('搜索引擎无效。')
        result=dict(kind=kind,engine=engine)
        if raw.get('url'):
            url=https_url(raw['url'])
            if url.count('{query}')!=1 or '{query}' not in url.partition('?')[2]:raise ValueError('搜索网址的查询参数需要一个 {query}。')
            result['url']=url
        return result
    if kind=='pomodoro':
        work=integer(raw.get('minutes',25),1,180,'专注时间需在 1 到 180 分钟。')
        rest=integer(raw.get('break_minutes',5),1,60,'休息时间需在 1 到 60 分钟。')
        return dict(kind=kind,minutes=work,break_minutes=rest)
    if kind=='history':
        lang=raw.get('lang','zh')
        if lang not in ('zh','en'):raise ValueError('维基百科语言需为 zh 或 en。')
        return dict(kind=kind,lang=lang,limit=integer(raw.get('limit',3),1,5,'事件数量需在 1 到 5。'))
    if kind=='rates':
        source,target=raw.get('from','USD'),raw.get('to','CNY')
        amount=raw.get('amount',100)
        if source not in CURRENCIES or target not in CURRENCIES:raise ValueError('请选择受支持的常用货币。')
        if type(amount) not in (int,float) or not 0<=amount<=10_000_000 or not math.isfinite(amount):raise ValueError('换算金额无效。')
        return {'kind':kind,'from':source,'to':target,'amount':amount}
    if kind=='feed':
        return dict(kind=kind,url=https_url(raw.get('url')),interval=integer(raw.get('interval',1440),15,1440,'刷新间隔需在 15 到 1440 分钟。'))
    if kind=='convert':
        rows=raw.get('units')
        if not isinstance(rows,list) or not 2<=len(rows)<=12:raise ValueError('请选择 2 到 12 个换算单位。')
        units=[]
        for row in rows:
            row=settings_object(row,'units');name=row.get('name');factor=row.get('factor');offset=row.get('offset',0)
            if not isinstance(name,str) or not 1<=len(name.strip())<=10 or any(unit['name']==name.strip() for unit in units):
                raise ValueError('每个换算单位需要不同的简短名称。')
            if type(factor) not in (int,float) or not 1e-12<=factor<=1e12 or type(offset) not in (int,float) or not -1e12<=offset<=1e12:
                raise ValueError('换算系数或偏移无效。')
            units.append(dict(name=name.strip(),factor=factor,offset=offset))
        return dict(kind=kind,units=units)
    return {}


def https_url(value):
    from content_sources import web_url
    if not web_url(value) or not value.startswith('https://'):
        raise ValueError('请输入完整的 HTTPS 地址。')
    return value


def validate_card(raw):
    if not isinstance(raw,dict):raise ValueError('卡片配置需要一个 JSON 对象。')
    title,style,width,rows=raw.get('title'),raw.get('style','follow'),raw.get('width',240),raw.get('rows')
    if not isinstance(title,str) or not 1<=len(title.strip())<=28:raise ValueError('卡片名称需为 1 到 28 个字符。')
    if not isinstance(style,str) or style not in STYLES:raise ValueError('卡片背景样式无效。')
    integer(width,190,640,'卡片宽度需为 190 到 640。')
    arrangement=raw.get('arrangement','list')
    if not isinstance(arrangement,str) or arrangement not in ARRANGEMENTS:raise ValueError('卡片排版无效。')
    picture=settings_object(raw.get('image',{}),'image');path=local_path(picture.get('path',''))
    image={}
    if path:
        fit=picture.get('fit','contain')
        if fit not in ('cover','contain'):raise ValueError('配图显示方式无效。')
        image=dict(path=path,fit=fit,height=integer(picture.get('height',120),48,250,'配图高度需在 48 到 250。'))
    fonts=settings_object(raw.get('fonts',{}),'fonts')
    fonts={key:integer(fonts.get(key,value),9,32,'卡片字号需在 9 到 32。') for key,value in (('title',14),('label',11),('body',12))}
    colors=settings_object(raw.get('colors',{}),'colors')
    colors={key:colors[key] for key in ('surface','text','accent') if key in colors and colors[key]!=''}
    if any(not isinstance(color,str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',color) for color in colors.values()):
        raise ValueError('配色需为 #RRGGBB。')
    tool=validate_tool(raw.get('tool',{}))
    if not isinstance(rows,list) or len(rows)>MAX_ROWS or not (rows or image or tool):
        raise ValueError('每张卡片最多 6 行，需要至少一行、配图或工具。')
    data_file=local_path(raw.get('data_file',''))
    cleaned=[]
    for row in rows:
        if not isinstance(row,dict):raise ValueError('卡片内容行无效。')
        kind=row.get('kind')
        if not isinstance(kind,str) or kind not in KINDS:raise ValueError('卡片内容类型不支持。')
        label,value=row.get('label',KINDS[kind]),row.get('value','')
        if not isinstance(label,str) or len(label.strip())>18:raise ValueError('行名称最多 18 字。')
        if kind in ('text','countdown','data','remote'):
            if not isinstance(value,str) or len(value.strip())>260:raise ValueError('文字内容最多 260 字。')
            value=value.strip()
        else:value=''
        if kind=='countdown':
            try:value=datetime.date.fromisoformat(value).isoformat()
            except ValueError:raise ValueError('倒计时日期请使用 YYYY-MM-DD。') from None
        if kind=='data' and (not data_file or not 1<=len(value)<=64):raise ValueError('本地数据行需要数据文件和字段名。')
        if kind=='remote' and (tool.get('kind')!='feed' or not re.fullmatch(r'[\w-]{1,40}(\.[\w-]{1,40}){0,6}',value)):
            raise ValueError('在线数据行需要 feed 工具与有效字段路径。')
        cleaned.append(dict(kind=kind,label=label.strip(),value=value))
    return dict(title=title.strip(),style=style,width=width,rows=cleaned,arrangement=arrangement,image=image,
                fonts=fonts,colors={k:v.lower() for k,v in colors.items()},data_file=data_file,
                header_date=raw.get('header_date') is True,tool=tool)


def normalize_cards(cards,strict=False):
    if not isinstance(cards,list) or len(cards)>MAX_CARDS:
        if strict:raise ValueError('最多保存 8 张自定义卡片。')
        return []
    seen=set();result=[]
    for row in cards:
        try:card=validate_card(row)
        except ValueError:
            if strict:raise
            continue
        identity=row.get('id')
        if not isinstance(identity,str) or not identity.isalnum() or len(identity)>40 or identity in seen:
            identity=uuid4().hex
        seen.add(identity)
        card.update(id=identity,visible=row.get('visible',True) is True,locked=row.get('locked') is True,
                    layout=valid_record(row.get('layout')))
        result.append(card)
    return result
