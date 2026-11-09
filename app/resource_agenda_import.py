"""Manual import from authorized calendar API responses, with setup guidance."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json

from resource_agenda import SOURCES

PROVIDERS={
    'dingtalk':(
        'https://dingtalk.apifox.cn/api-141374914',
        '如果已取得钉钉「查询日程视图」的响应 JSON，可粘贴到下方。有下一页时可继续导入。'
    ),
    'feishu':(
        'https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/list',
        '如果已取得飞书「获取日程列表」的响应 JSON，可粘贴到下方。有下一页时可继续导入。'
    ),
}


def event_time(raw):
    if not isinstance(raw,dict):raise ValueError('时间字段无效。')
    timestamp=raw.get('timestamp')
    if type(timestamp) is int or isinstance(timestamp,str) and timestamp.isascii() and timestamp.isdigit() and len(timestamp)<=10:
        return int(timestamp)
    if raw.get('dateTime'):
        value=datetime.fromisoformat(raw['dateTime'].replace('Z','+00:00'))
        if value.tzinfo is None:
            zone=raw.get('timeZone') or raw.get('timezone')
            if zone in ('UTC','GMT'):
                value=value.replace(tzinfo=timezone.utc)
            elif zone in ('Asia/Shanghai','China Standard Time'):
                value=value.replace(tzinfo=timezone(timedelta(hours=8)))
            elif zone:
                raise ValueError('时间需要包含时区偏移。')
        return int(value.timestamp())
    if raw.get('date'):
        return int(datetime.combine(date.fromisoformat(raw['date']),time.min).timestamp())
    raise ValueError('缺少日程时间。')


def parse_response(source,payload):
    if source not in PROVIDERS:
        raise ValueError('请选择钉钉或飞书。')
    if len(payload)>1024*1024:
        raise ValueError('响应超过 1 MiB，请缩小查询日期范围。')
    try:
        body=json.loads(payload.strip().lstrip('\ufeff'))
    except json.JSONDecodeError as error:
        raise ValueError(f'JSON 第 {error.lineno} 行、第 {error.colno} 列格式有误。') from error
    except RecursionError as error:
        raise ValueError('JSON 嵌套过深。') from error
    if not isinstance(body,dict):
        raise ValueError('请粘贴接口返回的完整 JSON 对象。')
    if source=='feishu':
        if body.get('code')!=0:
            raise ValueError('请先在飞书调试台成功读取日程，再复制响应 JSON。')
        body=body.get('data')
        if not isinstance(body,dict):raise ValueError('飞书响应缺少 data。')
        rows=body.get('items');more=bool(body.get('has_more'))
    else:
        rows=body.get('events');more=bool(body.get('nextToken'))
    if not isinstance(rows,list):
        raise ValueError(f'未找到{SOURCES[source]}的日程列表，请核对接口和所选来源。')
    events,skipped=parse_rows(source,rows)
    return events,skipped,more


def parse_rows(source,rows,strict=False):
    events={};skipped=0
    for row in rows:
        try:
            if not isinstance(row,dict):raise ValueError()
            if str(row.get('status','')).lower() in ('cancelled','canceled','deleted'):
                skipped+=1;continue
            if source=='feishu':
                key=row['event_id'];start=event_time(row['start_time']);end=event_time(row['end_time'])
                occurrence=''
            else:
                key=row['id'];start=event_time(row['start']);end=event_time(row['end'])
                occurrence=''
                if row.get('seriesMasterId'):
                    original=row.get('originStart')
                    occurrence=original.get('dateTime') if isinstance(original,dict) else None
                    occurrence=occurrence or start
            if not isinstance(key,str) or not key or not 0<=start<end<10**10:raise ValueError()
            title=' '.join(str(row.get('summary') or '私人日程').split())[:120]
            if not title or not title.isprintable():raise ValueError()
            identity=hashlib.sha256(json.dumps([source,key,occurrence],ensure_ascii=True).encode()).hexdigest()[:32]
            events[identity]=dict(id=identity,title=title,start=start,end=end,lead=5,ack=False,source=source)
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError):
            if strict:
                raise ValueError('日程数据格式有误。') from None
            skipped+=1
    return list(events.values()),skipped


def merge_import(existing,incoming):
    merged={event['id']:event for event in existing}
    for event in incoming:
        previous=merged.get(event['id'])
        if previous:
            event=dict(event,lead=previous['lead'],ack=previous['ack'] and previous['start']==event['start'])
        merged[event['id']]=event
    return list(merged.values())


def show_import(owner,service):
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices
    from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout
    from ui_style import ModernComboBox, button, compact_dialog, exec_dialog

    dialog=QDialog(owner);dialog.setWindowTitle('手动导入日程');dialog.resize(560,405)
    layout=QVBoxLayout(dialog);layout.setSpacing(7)
    row=QHBoxLayout()
    source=ModernComboBox();source.setAccessibleName('日程来源')
    for key in PROVIDERS:source.addItem(SOURCES[key],key)
    row.addWidget(source,1)
    row.addWidget(button('打开接口文档',lambda:QDesktopServices.openUrl(QUrl(PROVIDERS[source.currentData()][0]))))
    layout.addLayout(row)
    steps=QLabel();steps.setWordWrap(True);layout.addWidget(steps)
    editor=QPlainTextEdit();editor.setPlaceholderText('粘贴调试台返回的日程 JSON')
    editor.setAccessibleName('日程响应 JSON');layout.addWidget(editor,1)
    status=QLabel();status.setWordWrap(True);layout.addWidget(status)

    def connected():
        return service.calendar_sync and source.currentData() in service.calendar_sync.states

    def refresh_steps():
        steps.setText(PROVIDERS[source.currentData()][1])
        status.setText('手动记录保存在本机，断开该来源的自动同步后显示。' if connected()
                       else '手动导入到本机，按导入的时间安排提醒。')

    def commit():
        try:
            rows,skipped,more=parse_response(source.currentData(),editor.toPlainText())
        except ValueError as error:
            status.setText(str(error));return
        if not rows:
            status.setText('这页没有可导入的日程。');return
        model=service.get_agenda()
        if not model.save(merge_import(model.local_events,rows)):
            status.setText(model.error);return
        editor.clear()
        suffix=f'跳过 {skipped} 条无效或已取消的日程。' if skipped else ''
        if connected():
            suffix+='手动记录将在断开该来源的自动同步后显示。'
        status.setText(f'已导入或更新 {len(rows)} 条日程。'+suffix+('可继续导入下一页。' if more else ''))

    source.currentIndexChanged.connect(refresh_steps);refresh_steps()
    actions=QHBoxLayout();actions.addStretch()
    actions.addWidget(button('关闭',dialog.reject));actions.addWidget(button('导入日程',commit,'primary'));layout.addLayout(actions)
    compact_dialog(dialog);exec_dialog(dialog)
