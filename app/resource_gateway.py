"""Read-only AI quota connections and account snapshots."""
import json
from datetime import date,datetime,timezone
from math import isfinite
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode,urlsplit
from urllib.request import HTTPRedirectHandler,Request,build_opener

from PyQt5.QtCore import QObject,Qt,QTimer,pyqtSlot

from background_worker import BackgroundWorker
from resource_usage import FIELDS


KINDS={'auto':'自动识别','opencode':'OpenCode Go','commandcode':'Command Code','json':'指定用量地址'}
ENDPOINTS={'opencode':'https://opencode.ai/zen/go/v1/usage','commandcode':'https://api.commandcode.ai'}
PERIODS=('today','yesterday','week','month','all')
MAX_ACCOUNTS=5
MAX_RESPONSE=1024*1024


class UsageError(ValueError):
    pass


def object_(value):
    return value if isinstance(value,dict) else {}


def result_object(value):
    value=object_(value)
    return value['data'] if isinstance(value.get('data'),dict) else value


def endpoint(value):
    value=value.strip()
    try:
        url=urlsplit(value)
        host=url.hostname
        url.port
    except ValueError as error:
        raise UsageError('用量地址无效。') from error
    local=host in ('localhost','127.0.0.1','::1')
    if (not host or url.username is not None or url.password is not None or url.fragment
            or not (url.scheme=='https' or url.scheme=='http' and local)
            or len(value)>2048 or any(ch.isspace() for ch in value)):
        raise UsageError('请输入 HTTPS 地址或本机 HTTP 地址。')
    return value


def detected_kind(parts):
    if parts.hostname=='opencode.ai' and (parts.path in ('','/') or parts.path.startswith('/zen/go')):
        return 'opencode'
    if parts.hostname in ('api.commandcode.ai','commandcode.ai'):
        return 'commandcode'
    return None


def account_value(raw):
    kind=raw.get('kind')
    if kind not in KINDS:raise UsageError('用量接口类型无效。')
    name=raw.get('name','').strip()
    token=raw.get('token','').strip()
    if token.lower().startswith('bearer '):token=token[7:].strip()
    if name and (len(name)>48 or not name.isprintable()):raise UsageError('名称最多 48 个字符。')
    if not token or len(token)>4096 or any(not 33<=ord(ch)<=126 for ch in token):
        raise UsageError('请输入有效的 Token。')
    identity=raw.get('id')
    if not isinstance(identity,str) or len(identity)!=32 or any(ch not in '0123456789abcdef' for ch in identity):
        raise UsageError('连接编号无效。')
    url=endpoint(raw.get('url') or ENDPOINTS.get(kind,''))
    if kind=='opencode':
        if url.rstrip('/') in ('https://opencode.ai','https://opencode.ai/zen/go','https://opencode.ai/zen/go/v1'):
            url=ENDPOINTS[kind]
    elif kind=='commandcode':
        parts=urlsplit(url)
        if parts.query:raise UsageError('Command Code 请填写服务根地址。')
        path=parts.path.rstrip('/')
        if path in ('/provider','/provider/v1'):path=''
        url=f'{parts.scheme}://{parts.netloc}{path}'
    if not name:
        parts=urlsplit(url)
        name=KINDS.get(detected_kind(parts) if kind=='auto' else kind) if kind!='json' else None
        name=name or parts.hostname[:48]
    return dict(id=identity,kind=kind,name=name,url=url,token=token)


def config_path(directory):
    return Path(directory)/'resource-gateway-accounts.dat'


def load_accounts(directory):
    path=config_path(directory)
    if not path.is_file():return []
    from resource_calendar_sync import read_private
    raw=read_private(path)
    if not isinstance(raw,list) or len(raw)>MAX_ACCOUNTS:raise UsageError('用量连接文件无效。')
    try:rows=[account_value(item) for item in raw if isinstance(item,dict)]
    except (AttributeError,TypeError) as error:raise UsageError('用量连接文件无效。') from error
    if len(rows)!=len(raw) or len({row['id'] for row in rows})!=len(rows):raise UsageError('用量连接文件无效。')
    return rows


def save_accounts(directory,rows):
    from resource_calendar_sync import write_private
    write_private(config_path(directory),rows)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def fetch_json(url,token):
    request=Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/json',
                                 'User-Agent':'BigFishDock/usage'})
    try:
        with build_opener(NoRedirect()).open(request,timeout=12) as response:
            payload=response.read(MAX_RESPONSE+1)
        if len(payload)>MAX_RESPONSE:raise UsageError('用量响应过大。')
        return json.loads(payload)
    except HTTPError as error:
        raise UsageError('Token 无权限或已失效。' if error.code in (401,403) else f'用量接口 HTTP {error.code}') from None
    except (URLError,TimeoutError,OSError):
        raise UsageError('连接失败或超时。') from None
    except (UnicodeError,json.JSONDecodeError):
        raise UsageError('接口未返回 JSON 用量数据。') from None


def number(*values):
    for value in values:
        if type(value) in (str,int,float):
            try:value=float(value)
            except (ValueError,OverflowError):continue
            if isfinite(value) and 0<=value<1e18:return value
    return None


def iso_time(value):
    try:
        if isinstance(value,str) and not value.isdigit():
            return datetime.fromisoformat(value.replace('Z','+00:00')).isoformat()
        if (stamp:=number(value)) is not None:
            return datetime.fromtimestamp(stamp/(1000 if stamp>=10**11 else 1),timezone.utc).isoformat()
    except (ValueError,OverflowError,OSError):pass
    return None


def quota(label,source):
    row=object_(source)
    percent=number(row.get('usedPercent'),row.get('usagePercent'),row.get('percent'))
    if percent is None:
        left=number(row.get('remainingPercent'))
        used=number(row.get('used'),row.get('spent'))
        limit=number(row.get('limit'),row.get('cap'),row.get('total'))
        if left is not None:percent=100-min(100,left)
        elif used is not None and limit:percent=100*used/limit
    if percent is None:return None
    return dict(label=label,percent=min(100,percent),reset=iso_time(row.get('resetsAt') or row.get('resetAt') or row.get('reset')))


def windows(data):
    quotas=[]
    for label,keys in (('小时额度',('rolling','fiveHour','hourly','hour')),
                       ('每周额度',('weekly','week')),('月度额度',('monthly','month'))):
        for key in keys:
            row=quota('5 小时额度' if key in ('rolling','fiveHour') else label,data.get(key))
            if row:
                quotas.append(row);break
    return quotas


def summary(source):
    row=result_object(source)
    aliases={'tokens':('totalTokens','total_tokens'),'input':('inputTokens','input_tokens','totalInputTokens'),
             'output':('outputTokens','output_tokens','totalOutputTokens'),'cacheRead':('cachedTokens','cache_read_tokens'),
             'cacheWrite':('cache_write_tokens',),'records':('totalCount','requests','requestCount')}
    result={}
    for key in FIELDS:
        value=number(row.get(key),*(row.get(alias) for alias in aliases[key]))
        result[key]=round(value) if value is not None else None
    if result['tokens'] is None and result['input'] is not None and result['output'] is not None:
        result['tokens']=result['input']+result['output']
    result['cost']=number(row.get('cost'),row.get('totalCost'),row.get('cost_usd'))
    if all(value is None for value in result.values()):return None
    result['estimated']=row.get('estimated') is True
    result['unpriced']=round(number(row.get('unpriced')) or 0)
    return result


def provider(account,status='正在读取用量…',**values):
    kind = account['kind']
    url = urlsplit(account.get('url', ''))
    brand = kind if kind in ENDPOINTS else detected_kind(url)
    brand = brand or {'api.deepseek.com': 'deepseek', 'openrouter.ai': 'openrouter'}.get(url.hostname)
    return dict({'id':'gateway-'+account['id'],'name':account['name'],'source':KINDS[kind],'brand':brand,
                 'status':status,'quotas':[],'days':[],'usageAvailable':False,'usageComplete':False},**values)


def decode_gateway(account,data):
    data=result_object(data)
    quotas=windows(object_(data.get('quotas') or data.get('limits') or data.get('usage') or data))
    periods={}
    for key in PERIODS:
        value=summary(object_(data.get('periods')).get(key) or data.get(key))
        if value is not None:periods[key]=value
    if 'all' not in periods and (total:=summary(data.get('summary') or data.get('usage') or data)) is not None:
        periods['all']=total
    days=[]
    raw_days=data.get('days')
    for item in raw_days[:366] if isinstance(raw_days,list) else ():
        row=object_(item);stamp=row.get('date')
        try:stamp=date.fromisoformat(stamp).isoformat()
        except (TypeError,ValueError):continue
        value=summary(row.get('summary') or row)
        if value is not None:days.append(dict(date=stamp,model=str(row.get('model') or '网关汇总')[:96],summary=value))
    if not quotas and not periods and not days:raise UsageError('接口未提供可识别的额度或用量字段。')
    return provider(account,'已连接',quotas=quotas,periods=periods,days=days,usageAvailable=bool(periods or days),
                    usageComplete=bool(days))


def read_gateway(account,fetch=fetch_json,cancelled=lambda:False):
    url=account['url'];token=account['token'];kind=account['kind']
    if kind=='auto':
        return discover_gateway(account,fetch,cancelled)
    if kind=='commandcode':
        return read_command_code(account,fetch,cancelled)
    return decode_gateway(account,fetch(url,token))


def discover_gateway(account,fetch,cancelled):
    url=account['url'];token=account['token'];parts=urlsplit(url)
    if kind:=detected_kind(parts):
        return read_gateway(dict(account,kind=kind,url=ENDPOINTS[kind]),fetch,cancelled)
    path=parts.path.rstrip('/')
    for ending in ('/chat/completions','/responses','/embeddings','/messages','/models'):
        if path.endswith(ending):
            path=path.removesuffix(ending);break
    base=f'{parts.scheme}://{parts.netloc}{path}'
    versioned=base if path.endswith('/v1') else base+'/v1'
    candidates=[base+'/usage',versioned+'/usage']
    if path.endswith(('/usage','/usage/summary')):candidates.insert(0,url)
    for candidate in dict.fromkeys(candidates):
        if cancelled():raise UsageError('已取消')
        try:return decode_gateway(account,fetch(candidate,token))
        except UsageError:pass
    if cancelled():raise UsageError('已取消')
    try:
        usage=result_object(fetch(versioned+'/dashboard/billing/usage',token))
        total=number(usage.get('total_usage'))
        if total is not None:
            quotas=[dict(label='累计消耗（网关单位）',kind='spend',value=f'{total/100:,.2f}')]
            if not cancelled():
                try:
                    limit_data=result_object(fetch(versioned+'/dashboard/billing/subscription',token))
                    limit=number(limit_data.get('hard_limit_usd'))
                    if limit and limit<1e8:
                        quotas.append(dict(label='网关总额度',percent=min(100,total/limit),reset=None))
                except UsageError:pass
            return provider(account,'已连接',quotas=quotas)
    except UsageError as error:
        if 'Token' in str(error):raise
    raise UsageError('未识别到兼容用量接口。可选择「指定用量地址」。')


def read_command_code(account,fetch,cancelled):
    base=account['url'];token=account['token']
    identity=result_object(fetch(base+'/alpha/whoami?limits=1',token))
    org=identity.get('orgId') or object_(identity.get('organization')).get('id')
    params={'orgId':org} if isinstance(org,str) and org else {}

    def read(path,optional=False,**query):
        if cancelled():raise UsageError('已取消')
        query=urlencode(dict(params,**query))
        try:return result_object(fetch(base+path+('?'+query if query else ''),token))
        except UsageError:
            if optional:return {}
            raise

    billing=read('/alpha/billing/credits')
    credits=object_(billing.get('credits'))
    subscription=read('/alpha/billing/subscriptions',True)
    quotas=windows(object_(billing.get('windowLimits')))
    monthly=number(credits.get('monthlyCredits'))
    monthly_limit=number(credits.get('monthlyLimit'),credits.get('monthlyCreditLimit'),subscription.get('monthlyCredits'))
    reset=iso_time(subscription.get('currentPeriodEnd'))
    if monthly is not None:
        if monthly_limit and monthly<=monthly_limit:
            quotas.append(dict(label='月度额度',percent=100*(1-monthly/monthly_limit),reset=reset))
        else:quotas.append(dict(label='本月套餐余额',kind='balance',value=f'${monthly:,.2f}',reset=reset))
    elif (limit:=next((row for row in (identity.get('orgLimits') or ()) if isinstance(row,dict) and row.get('resetInterval')=='monthly'),None)):
        if row:=quota('组织月度额度',limit):quotas.append(row)
    start=iso_time(subscription.get('currentPeriodStart'))
    cycle=summary(read('/alpha/usage/summary',True,**({'since':start} if start else {})))
    today=datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
    daily=summary(read('/alpha/usage/summary',True,since=today))
    if cycle and cycle['cost'] is not None:
        quotas.append(dict(label='当前账期费用',kind='spend',value=f"${cycle['cost']:,.2f}"))
    if not quotas and not daily and not cycle:raise UsageError('账户未返回可识别的用量。')
    plan=subscription.get('planId') or credits.get('planId') or 'Command Code'
    return provider(account,'已连接',plan=str(plan)[:48],quotas=quotas,periods={'today':daily} if daily else {},
                    billing=cycle,usageAvailable=bool(daily),usageComplete=False)


class GatewayJob(BackgroundWorker):
    def __init__(self,accounts):
        super().__init__();self.accounts=accounts;self.rows=[]

    def run(self):
        for account in self.accounts:
            if self.cancelled.is_set():break
            try:self.rows.append(read_gateway(account,cancelled=self.cancelled.is_set))
            except (UsageError,TypeError,ValueError,AttributeError,OverflowError) as error:
                status=str(error) if isinstance(error,UsageError) else '用量响应格式无效。'
                self.rows.append(provider(account,status,failed=True))


class GatewayUsage(QObject):
    def __init__(self,bridge,accounts):
        super().__init__(bridge)
        self.bridge=bridge;self.accounts=accounts;self.active=False;self.job=None
        self.rows=[]
        self.timer=QTimer(self);self.timer.setInterval(300000);self.timer.timeout.connect(self.refresh)

    def set_active(self,active):
        if self.active==active:return
        self.active=active
        self.rows=[provider(row) for row in self.accounts] if active else []
        if active and not self.bridge.owner.runtime.dock.preview:
            self.refresh();self.timer.start()
        elif not active:self.cancel()
        self.bridge.provider_rows_changed()

    def refresh(self):
        if self.active and self.job is None and not self.bridge.owner.runtime.dock.preview:
            self.job=GatewayJob(self.accounts)
            self.job.finished.connect(self.finished,Qt.QueuedConnection);self.job.start()

    @pyqtSlot()
    def finished(self):
        job=self.sender()
        if job is not self.job:return
        self.job=None
        previous={row['id']:row for row in self.rows if row.get('quotas') or row.get('usageAvailable')}
        self.rows=[dict(previous[row['id']],status=row['status'],stale=True)
                   if row.get('failed') and row['id'] in previous else row for row in job.rows]
        job.deleteLater()
        self.bridge.provider_rows_changed()

    def cancel(self):
        self.timer.stop()
        job,self.job=self.job,None
        if job:
            job.requestInterruption();job.deleteLater()
