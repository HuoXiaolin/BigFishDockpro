"""Bounded RSS/Atom and Bing picture metadata readers."""
from urllib.parse import urljoin, urlsplit


BING='https://www.bing.com'


def web_url(value):
    if not isinstance(value,str) or not value or len(value)>2048 or any(c.isspace() or ord(c)<32 for c in value):
        return ''
    try:
        parts=urlsplit(value)
        return value if parts.scheme in ('https','http') and parts.hostname and not parts.username and not parts.password else ''
    except ValueError:
        return ''


def clean_feeds(value,strict=False):
    if isinstance(value,list) and len(value)<=5 and all(web_url(url) for url in value):
        return list(dict.fromkeys(value))
    if strict:raise ValueError('新闻订阅最多 5 个，请使用 HTTP 或 HTTPS 订阅链接。')
    return []


def fetch(url,maximum):
    from urllib.request import Request,urlopen
    if not web_url(url):raise ValueError('无效网址')
    with urlopen(Request(url,headers={'User-Agent':'BigFishDockpro/1.2 (https://github.com/HuoXiaolin/BigFishDockpro)'}),timeout=5) as stream:
        data=stream.read(maximum+1)
    if len(data)>maximum:raise ValueError('内容过大')
    return data


def read_feed(data,url):
    import datetime
    import xml.etree.ElementTree as xml
    from email.utils import parsedate_to_datetime

    root=xml.fromstring(data)
    for node in root.iter():node.tag=node.tag.rsplit('}',1)[-1]
    channel=root.find('channel')
    source=channel if channel is not None else root
    name=' '.join((source.findtext('title') or urlsplit(url).hostname or '').split())[:48]
    rows=[]
    for item in (source.findall('item') or root.findall('item') or root.findall('entry'))[:12]:
        title=item.find('title')
        name_text=' '.join(''.join(title.itertext()).split())[:240] if title is not None else ''
        link=next((node.get('href') or node.text for node in item.findall('link')
                   if node.get('rel','alternate')=='alternate' and (node.get('href') or node.text)),None)
        link=web_url(urljoin(url,link.strip())) if link else ''
        if not name_text or not link:continue
        raw=item.findtext('pubDate') or item.findtext('published') or item.findtext('updated') or ''
        stamp=None
        if raw:
            try:stamp=parsedate_to_datetime(raw)
            except (ValueError,TypeError):
                try:stamp=datetime.datetime.fromisoformat(raw.strip().replace('Z','+00:00'))
                except ValueError:pass
        if stamp is not None:
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=datetime.timezone.utc)
            stamp=stamp.timestamp()
        rows.append(dict(title=name_text,url=link,source=name,stamp=stamp))
    return rows


def read_bing(data):
    import json,re
    raw=json.loads(data)
    rows=[]
    for image in raw.get('images',[])[:8] if isinstance(raw,dict) else []:
        if not isinstance(image,dict):continue
        base=image.get('urlbase','')
        date=image.get('startdate','')
        if not isinstance(base,str) or not re.fullmatch(r'/th\?id=OHR\.[\w.-]{1,180}',base,re.ASCII):continue
        if not isinstance(date,str) or not re.fullmatch(r'\d{8}',date):continue
        picture=web_url(BING+base+'_640x360.jpg')
        title=image.get('title') or image.get('copyright') or '必应每日图片'
        credit=image.get('copyright') or ''
        story=image.get('copyrightlink') or 'https://www.bing.com/'
        if picture and isinstance(title,str) and isinstance(credit,str) and isinstance(story,str):
            rows.append(dict(picture=picture,original=BING+base+'_UHD.jpg',title=title[:140],credit=credit[:220],date=date,
                             story=web_url(urljoin(BING,story))))
    return rows


def download_bing_original(url,destination,cancelled):
    """Stream the UHD response to a same-folder temporary file, then commit it."""
    import os,re,tempfile
    from pathlib import Path
    from urllib.request import Request,urlopen
    from PyQt5.QtGui import QImageReader

    if not re.fullmatch(r'https://www\.bing\.com/th\?id=OHR\.[\w.-]{1,180}_UHD\.jpg',url,re.ASCII):
        raise ValueError('原图网址无效')
    path=Path(destination)
    maximum=24*1024*1024
    temporary=None
    try:
        request=Request(url,headers={'User-Agent':'BigFishDockpro/1.2','Accept':'image/jpeg'})
        with urlopen(request,timeout=10) as response:
            if urlsplit(response.geturl()).hostname not in ('www.bing.com','bing.com','cn.bing.com','th.bing.com'):
                raise ValueError('原图来源无效')
            length=response.headers.get('Content-Length','')
            expected=int(length) if length.isdecimal() else None
            if expected is not None and expected>maximum:raise ValueError('原图过大')
            with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.jpg',delete=False) as target:
                temporary=target.name
                total=0
                while not cancelled.is_set():
                    block=response.read(64*1024)
                    if not block:break
                    total+=len(block)
                    if total>maximum:raise ValueError('原图过大')
                    target.write(block)
        if cancelled.is_set():return False
        reader=QImageReader(temporary,b'jpeg');size=reader.size()
        del reader
        if (expected is not None and total!=expected) or not size.isValid() or max(size.width(),size.height())>12000:
            raise ValueError('原图数据无效')
        os.replace(temporary,path)
        return True
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def read_local_pictures(paths,cancelled):
    from pathlib import Path
    from itertools import islice

    allowed={'.jpg','.jpeg','.png','.webp','.bmp'}
    rows={}
    for source in paths:
        if cancelled.is_set() or len(rows)>=512:break
        path=Path(source).expanduser()
        try:
            if path.is_dir():
                matches=(item for item in path.iterdir() if item.suffix.lower() in allowed and item.is_file())
                choices=sorted(islice(matches,512-len(rows)),key=lambda item:item.name.casefold())
            else:choices=[path]
            for item in choices:
                if cancelled.is_set():break
                if item.suffix.lower() not in allowed or not item.is_file():continue
                full=str(item.resolve());rows.setdefault(full.casefold(),dict(picture=full,title=item.stem[:140],credit=item.parent.name,story=''))
        except (OSError,RuntimeError):continue
    return list(rows.values())
