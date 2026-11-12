"""Gateway discovery, reported billing, and local credential storage."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs,urlsplit


def run(api,runtime,app,output,checks):
    from private_storage_fixture import private_storage

    with private_storage(checks):
        run_checks(api,runtime,app,output,checks)


def run_checks(api,runtime,app,output,checks):
    from PyQt5.QtWidgets import QLineEdit
    from resource_gateway import ENDPOINTS,UsageError,account_value,config_path,load_accounts,read_gateway
    from resource_gateway_settings import GatewaySettings
    from resource_usage import aggregate

    key='fixture-usage-secret'
    def account(url,kind='auto'):
        return account_value(dict(id='1'*32,name='测试网关',kind=kind,url=url,token=key))

    def go(url,token):
        assert url==ENDPOINTS['opencode'] and token==key
        return dict(planType='go',usage=dict(hourly=dict(percent=0),rolling=dict(percent=25,resetsAt='2026-11-10T09:30:00Z'),
                                             weekly=dict(percent=71),monthly=dict(percent=12)))

    code=read_gateway(account('https://opencode.ai/zen/go/v1/chat/completions'),go)
    assert code['plan']=='go' and not code['usageAvailable']
    assert [(q['label'],q['percent']) for q in code['quotas']]==[
        ('每小时额度',0),('5 小时额度',25),('每周额度',71),('每月额度',12)]

    def command_code(url,token):
        parts=urlsplit(url);assert parts.netloc=='api.commandcode.ai' and token==key
        query=parse_qs(parts.query)
        if parts.path=='/alpha/whoami':return dict(orgId='fixture')
        assert query['orgId']==['fixture']
        if parts.path=='/alpha/billing/credits':
            return dict(credits=dict(monthlyCredits=39,planId='plus'),windowLimits=dict(
                fiveHour=dict(used=1,cap=4,resetAt=1794290000000),weekly=dict(used=8,cap=16)))
        if parts.path=='/alpha/billing/subscriptions':
            return dict(data=dict(planId='plus',currentPeriodStart='2026-11-01T00:00:00Z',currentPeriodEnd='2026-12-01T00:00:00Z'))
        assert parts.path=='/alpha/usage/summary'
        return dict(totalCost=11.24,totalCount=19,totalInputTokens=5200,totalOutputTokens=1200)

    cmd=read_gateway(account('https://api.commandcode.ai/provider/v1'),command_code)
    assert [q.get('percent') for q in cmd['quotas']]==[25,50,None,None]
    assert cmd['quotas'][2]['value']=='$39.00' and cmd['billing']['cost']==11.24
    assert aggregate([cmd])['total']['tokens']==6400
    assert not aggregate([cmd],'week')['available']

    def compatible(url,token):
        assert token==key and url.startswith('https://gateway.example/')
        if url=='https://gateway.example/v1/usage':raise UsageError('HTTP 404')
        if url.endswith('/billing/usage'):return dict(total_usage=625)
        assert url.endswith('/billing/subscription')
        return dict(hard_limit_usd=25)

    generic=read_gateway(account('https://gateway.example/v1/chat/completions'),compatible)
    assert generic['quotas'][0]['value']=='6.25' and generic['quotas'][1]['percent']==25
    assert not aggregate([generic])['available']
    direct=read_gateway(account('https://gateway.example/meters','json'),lambda *_:dict(data=dict(
        quotas=dict(hour=dict(remainingPercent=87)),periods=dict(today=dict(tokens=400,cost=0,requests=6)))))
    assert direct['quotas'][0]['percent']==13 and aggregate([direct])['total']['cost']==0
    try:account('https://user:pass@gateway.example/v1')
    except UsageError:pass
    else:raise AssertionError('Embedded URL credentials must be rejected')

    service=runtime.resources;cfg=service.cfg;original=deepcopy(cfg);dialog=None
    path=config_path(api.CONFIG_DIR)
    assert not path.exists()
    try:
        assert service.set_options(resource_enabled=True,resource_ai=True,resource_ai_providers=[],
                                   resource_music=False,resource_task_music=False,resource_auto_hide=False)
        dialog=GatewaySettings(service,None)
        dialog.url.setText('https://gateway.example/v1')
        dialog.name.setText('自建网关');dialog.token.setText(key)
        assert dialog.token.echoMode()==QLineEdit.Password
        assert dialog.save(),dialog.status.text()
        assert load_accounts(api.CONFIG_DIR)[0]['token']==key
        assert key.encode() not in path.read_bytes()
        assert key not in Path(api.CONFIG_PATH).read_text(encoding='utf-8')
        assert service.deck.gateway.active and not service.deck.signature[0] and service.deck.process.state()==0
        service.deck.gateway.rows=[direct];service.deck.provider_rows_changed()
        assert service.deck.providers==[direct]
        dialog.remove();assert not load_accounts(api.CONFIG_DIR) and not service.deck.providers
        checks.append('AI gateway: inference URL discovery for OpenCode Go, Command Code and compatible billing, explicit JSON, unknown periods and real zero cost, protected add/remove credentials and no managed process for gateway-only AI. HTTP fixtures.')
    finally:
        if dialog:dialog.deleteLater()
        cfg.clear();cfg.update(original);service.sync();api.save_config(cfg)
