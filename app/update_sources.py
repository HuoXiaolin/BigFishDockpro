"""This project's release source and strict installer selection."""
from urllib.parse import urlparse,unquote

REPOSITORY='https://github.com/HuoXiaolin/BigFishDockpro'
DEFAULT_SOURCE=REPOSITORY+'/releases/latest'
GITHUB_API='https://api.github.com/repos/HuoXiaolin/BigFishDockpro/releases/latest'
INSTALLER='BigFishDockpro-Setup-x64.exe'


def resolve_source(url):
    value=url.strip().rstrip('/')
    aliases=(REPOSITORY,REPOSITORY+'/releases',DEFAULT_SOURCE,GITHUB_API)
    if value.lower() in {item.lower() for item in aliases}:return GITHUB_API,True
    return url,False


def parse_github_release(payload,current,version_tuple):
    if not isinstance(payload,dict):raise ValueError('GitHub 发布信息格式不正确。')
    if payload.get('draft') or payload.get('prerelease'):raise ValueError('更新源未返回正式发布版本。')
    tag=payload.get('tag_name','')
    if not isinstance(tag,str):raise ValueError('GitHub 发布标签格式不正确。')
    version=tag[1:] if tag.startswith(('v','V')) else tag
    newer=version_tuple(version)>version_tuple(current)
    page=payload.get('html_url','')
    parsed=urlparse(page)
    prefix='/HuoXiaolin/BigFishDockpro/releases/tag/'
    if (parsed.scheme!='https' or parsed.netloc.lower()!='github.com' or
            not parsed.path.startswith(prefix) or unquote(parsed.path[len(prefix):])!=tag):
        raise ValueError('发布页面不属于本项目或版本不匹配。')
    selected=''
    assets=payload.get('assets',[])
    if not isinstance(assets,list):raise ValueError('GitHub 安装包列表格式不正确。')
    for asset in assets:
        if not isinstance(asset,dict) or asset.get('name')!=INSTALLER:continue
        if asset.get('state')!='uploaded' or not isinstance(asset.get('size'),int) or asset['size']<=0:continue
        link=asset.get('browser_download_url','');target=urlparse(link)
        expected='/HuoXiaolin/BigFishDockpro/releases/download/'+tag+'/'+INSTALLER
        if target.scheme=='https' and target.netloc.lower()=='github.com' and unquote(target.path)==expected:
            selected=link;break
    return {'newer':newer,'version':version,'release_url':selected or page,
            'installer_available':bool(selected),'notes':str(payload.get('body') or '')[:4000]}
