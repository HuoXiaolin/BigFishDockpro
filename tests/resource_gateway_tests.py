"""Gateway discovery, reported billing, and local credential storage."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch


def balance_cases():
    from resource_gateway import UsageError,account_value,read_gateway
    from resource_quota import capsule_reading
    from resource_usage import aggregate

    def read(url, responses, *, kind='auto', extra=''):
        account=account_value(dict(id='a'*32,name='自建网关',kind=kind,url=url,balance_url=extra,token='fixture'))
        calls=[]
        def fetch(target,token):
            assert target in responses and token=='fixture',target
            calls.append(target)
            result=responses[target]
            if isinstance(result,UsageError):raise result
            return result
        row=read_gateway(account,fetch)
        assert calls==list(responses),calls
        return row

    deep='https://api.deepseek.com/user/balance'
    wallets=dict(is_available=False,balance_infos=[
        dict(currency='CNY',total_balance='0.00',granted_balance='0.00',topped_up_balance='0.00'),
        dict(currency='USD',total_balance='-1.25')])
    bilingual=read('https://api.deepseek.com/v1', {deep:wallets},kind='json')
    assert [(q['label'],q['value']) for q in bilingual['quotas']]==[('账户余额（CNY）','¥0.00'),('账户余额（USD）','−$1.25')]
    assert not aggregate([bilingual])['available'] and not capsule_reading(bilingual,allow_balance=False)
    for domain,symbol in [('cn','¥'),('ai','$')]:
        base=f'https://api.moonshot.{domain}/v1'
        row=read(base+'/chat/completions',{base+'/users/me/balance':dict(code=0,data=dict(
            available_balance=12.3,cash_balance=5.3,voucher_balance=7))})
        assert row['brand']=='kimi' and row['quotas'][0]['value']==symbol+'12.30'
    credits='https://openrouter.ai/api/v1/credits'
    router=read('https://openrouter.ai/api/v1',{credits:dict(data=dict(total_credits=5,total_usage=5.01))})
    assert router['quotas'][0]['value']=='−$0.01' and not router['usageAvailable']
    for invalid in (dict(balance=None),dict(balance=False),dict(balance='NaN'),dict(balance=3,unit='tokens'),dict(cost=13),
                    dict(limit=100,remainingPercent=80),dict(total_credits=10),dict(error='denied',balance=0)):
        target=credits if 'total_credits' in invalid else 'https://example.test/balance'
        try:row=read(target,{target:invalid},kind='json')
        except UsageError:continue
        assert not any(m.get('kind')=='balance' for m in row['quotas'])

    usage='https://gateway.example/v1/usage'
    balance='https://gateway.example/v1/balance'
    report=dict(quotas=dict(hour=dict(remainingPercent=87)),today=dict(tokens=400,cost=1.25))
    mixed=read('https://gateway.example/v1',{usage:report,balance:dict(data=dict(balance=dict(amount=12.34,currency='EUR')))})
    assert [q.get('value') for q in mixed['quotas']]==['€12.34',None]
    assert capsule_reading(mixed,allow_balance=False).remaining==87 and aggregate([mixed])['total']['cost']==1.25
    single=read(usage,{usage:dict(report,balance=0,currency='USD')})
    assert [q.get('value') for q in single['quotas']]==['$0.00',None]
    unavailable=UsageError('HTTP 503')
    partial=read(usage,{usage:report,balance:unavailable},kind='json',extra='/v1/balance')
    assert partial['balanceStatus']=='余额暂不可用' and partial['quotas']==mixed['quotas'][1:]
    tiny=read(usage,{usage:unavailable,balance:dict(amount=0.005,currency='USD')},kind='json',extra=balance)
    assert tiny['quotas'][0]['value']=='$0.005' and tiny['status']=='仅余额可用'
    bare=read('',{balance:dict(data=dict(amount='6.71'))},extra=balance)
    assert bare['quotas'][0]['value']=='6.71'
    for kind in ('auto','json'):
        try:read('https://api.openai.com/v1',{},kind=kind,extra='https://unrelated.example/wallet')
        except UsageError as error:assert '账单总览' in str(error)
        else:raise AssertionError('Official OpenAI API base cannot report a prepaid balance')
    return mixed


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
        if url in ('https://gateway.example/v1/usage','https://gateway.example/v1/balance'):raise UsageError('HTTP 404')
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

    mixed=balance_cases()
    service=runtime.resources;cfg=service.cfg;original=deepcopy(cfg);dialog=None
    path=config_path(api.CONFIG_DIR)
    assert not path.exists()
    try:
        assert service.set_options(resource_enabled=True,resource_ai=True,resource_ai_providers=[],
                                   resource_music=False,resource_task_music=False,resource_auto_hide=False)
        dialog=GatewaySettings(service,None)
        dialog.kind.setCurrentIndex(dialog.kind.findData('openrouter'))
        assert dialog.url.text()==ENDPOINTS['openrouter'] and '管理密钥' in dialog.hint.text()
        dialog.kind.setCurrentIndex(dialog.kind.findData('json'))
        dialog.url.setText('https://api.openai.com/v1')
        assert 'https://platform.openai.com/settings/organization/billing/overview' in dialog.hint.text()
        dialog.url.setText('https://gateway.example/v1')
        dialog.balance_url.setText('/v1/balance')
        dialog.name.setText('自建网关');dialog.token.setText(key)
        assert dialog.token.echoMode()==QLineEdit.Password
        assert dialog.save(),dialog.status.text()
        saved=load_accounts(api.CONFIG_DIR)[0]
        assert saved['token']==key and dialog.balance_url.text()==saved['balance_url']=='https://gateway.example/v1/balance'
        assert key.encode() not in path.read_bytes()
        assert key not in Path(api.CONFIG_PATH).read_text(encoding='utf-8')
        assert service.deck.gateway.active and not service.deck.signature[0] and service.deck.process.state()==0
        service.deck.gateway.rows=[mixed];service.deck.provider_rows_changed()
        assert service.deck.providers==[mixed] and service.deck.ball_quota.remaining==87
        import resource_statistics
        overview=service.window.ai_view.statistics.quotas
        service.window.ai_view.statistics.refresh()
        with patch.object(resource_statistics,'text',wraps=resource_statistics.text) as painted:
            overview.grab().save(str(output/'gateway-account-balance.png'))
        labels={call.args[2] for call in painted.call_args_list}
        assert {'账户余额','€12.34','87%'} <= labels,labels
        dialog.remove();assert not load_accounts(api.CONFIG_DIR) and not service.deck.providers
        checks.append('AI gateway: inference URL discovery for OpenCode Go, Command Code and compatible billing, explicit JSON, unknown periods and real zero cost, protected add/remove credentials and no managed process for gateway-only AI. HTTP fixtures.')
        checks.append('Custom balance: official DeepSeek, both Kimi regions and OpenRouter response fixtures, mixed quotas, failure of either endpoint, zero and debt, no invented OpenAI credit, encrypted address round-trip and rendered account currency on the capsule AI card.')
    finally:
        if dialog:dialog.deleteLater()
        cfg.clear();cfg.update(original);service.sync();api.save_config(cfg)
