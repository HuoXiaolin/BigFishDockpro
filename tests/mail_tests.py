"""Mailbox contracts and real capsule widgets with local message fixtures."""
from base64 import urlsafe_b64encode
import copy
from email.message import EmailMessage
from threading import Event
import time
from unittest.mock import Mock, patch


def accounts():
    from mail_accounts import clean_accounts
    return clean_accounts([
        dict(id='1'*32, provider='qq', address='123456@qq.com', name='测试 QQ'),
        dict(id='2'*32, provider='gmail', address='tester@example.com', name='测试 Gmail'),
        dict(id='3'*32, provider='netease', address='tester@126.com', name='测试网易'),
    ], strict=True)


def transport_checks(checks):
    from gmail_mail import GmailSession
    from mail_accounts import clean_accounts, imap_endpoint
    from mail_messages import message_code, summary_subject, verification_code
    from mail_transport import ImapSession, MAX_TEXT

    qq, google, netease = accounts()
    assert imap_endpoint(netease) == ('imap.126.com', 993)
    assert imap_endpoint(qq) == ('imap.qq.com', 993)
    assert clean_accounts([dict(qq, provider=[]), dict(qq, id=123)]) == []
    assert 'password' not in clean_accounts([dict(qq, password='fixture-password')])[0]
    assert verification_code('84 订单号 654321') == ''
    assert verification_code('654321 is your verification code') == '654321'
    assert verification_code('验证码（654 321）') == '654321'
    assert verification_code('验证码 123456，旧验证码 567890') == ''
    assert '654321' not in summary_subject('【邮箱】验证码：654321')
    html = EmailMessage()
    html.set_content('<script>验证码 111111</script><p>验证码：<strong>654321</strong></p>', subtype='html')
    assert message_code(html.as_bytes(), '验证邮箱') == '654321'

    now = time.time()
    header = EmailMessage()
    header['From'] = '测试发件人 <sender@example.com>'
    header['Subject'] = '登录提醒'
    header.set_content('内容')
    metadata = header.as_bytes().split(b'\n\n', 1)[0].replace(b'\n', b'\r\n') + b'\r\n\r\n'
    client = Mock()
    client.capabilities = ('IMAP4REV1', 'ID')
    client.login.return_value = ('OK', [b'Logged in'])
    client.select.return_value = ('OK', [b'21'])
    client.response.return_value = ('UIDVALIDITY', [b'42'])
    uids = list(range(2, 22))
    client.fetch.side_effect = lambda *_: ('OK', [f'{i} (UID {i})'.encode() for i in uids])

    def fetch(operation, ids, query):
        assert operation == 'FETCH' and 'BODY.PEEK' in query
        if query == f'(BODY.PEEK[]<0.{MAX_TEXT}>)':
            return 'OK', [(f'21 (UID {ids} BODY[]<0>'.encode(), html.as_bytes()), b')']
        return 'OK', [(f'{uid} (UID {uid} INTERNALDATE "19-Nov-2026 17:00:00 +0800"'.encode(), metadata)
                      for uid in ids.split(',')]

    client.uid.side_effect = fetch
    with patch('mail_transport.imaplib.IMAP4_SSL', return_value=client) as connect:
        session = ImapSession(qq, dict(password='fixture-password'), Event())
        rows, new = session.snapshot(True)
        assert len(rows) == 20 and not new and rows[0].sender.startswith('测试发件人') and rows[0].stamp > 0
        client.select.assert_called_with('INBOX', readonly=True)
        client.fetch.assert_called_with('2:21', '(UID)')
        client.xatom.assert_called_once()
        session.close()
        uids[:] = range(3, 23)
        rows, new = session.snapshot(True)
        assert connect.call_count == 2 and len(rows) == 20 and [(r.uid, code) for r, code in new] == [('22', '654321')]
        assert session.snapshot(True)[1] == []
        client.response.return_value = ('UIDVALIDITY', [b'43'])
        assert session.snapshot(True)[1] == []
        session.close()

    session = GmailSession(google, dict(client_id='fixture', client_secret='fixture', refresh_token='fixture'), Event())
    old, arrived = 'abcdef127102abc0', 'abcdef127102abc1'
    ids, history = [old], []

    def gmail(route, fields):
        if route == 'profile':
            return dict(emailAddress=google['address'], historyId='100')
        if route == 'history':
            return dict(historyId='101' if history else '100', history=history)
        if route == 'messages':
            return {'messages': [{'id': identity} for identity in ids]}
        if fields['format'] == 'full':
            body = urlsafe_b64encode('您的验证码是 654321'.encode()).decode()
            return dict(payload=dict(mimeType='text/plain', body=dict(data=body)))
        return dict(internalDate=str(round(now*1000)), payload={'headers': [{'name': 'Subject', 'value': '认证提醒'}]})

    with patch.object(session, 'api', side_effect=gmail):
        assert len(session.snapshot(True)[0]) == 1
        ids.insert(0, arrived)
        assert not session.snapshot(True)[1]  # The list can see delivery before history observes it.
        history.append(dict(id='101', messagesAdded=[{'message': {'id': arrived}}]))
        rows, new = session.snapshot(True)
        assert [item.uid for item in rows] == ids and [(item.uid, code) for item, code in new] == [(arrived, '654321')]
        assert rows[0].url.endswith('#all/' + arrived)
        history.clear()
        assert not session.snapshot(True)[1]
    checks.append('Mail transport: account/provider validation, TLS IMAP read-only inbox, UID reconnect and validity reset, Gmail history delivery race, HTML verification codes and masked subjects.')


def run(api, runtime, app, output, checks):
    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QApplication, QDialog
    from mail_accounts import inbox_url
    from mail_messages import MailItem
    from resource_mail_settings import MailAccountEditor, MailAccountsDialog
    from resource_settings import ResourceOptions
    from ui_test_events import Events

    transport_checks(checks)
    service = runtime.resources
    cfg = service.cfg
    before = copy.deepcopy(cfg)
    qq, google, netease = records = accounts()
    credential_store = {}
    clipboard = Mock()
    editor = management = settings = None
    try:
        cfg.update(resource_enabled=True, resource_mail=True, resource_mail_icon=False, resource_collapsed=False,
                   resource_auto_hide=False, resource_fold='capsule', resource_compact_width=520,
                   resource_alert_mail_code=True, resource_mail_notifications=False, resource_mail_interval=30,
                   resource_mail_accounts=records[1:], resource_component_locations={})
        service.auto_compact = None
        service.sync()
        mailbox = service.get_mail()
        window = service.window
        with (patch('mail_credentials.read', side_effect=lambda identity: credential_store.get(identity, {})),
              patch('mail_credentials.write', side_effect=credential_store.__setitem__),
              patch('mail_credentials.remove', side_effect=lambda identity: credential_store.pop(identity, None)),
              patch('mail_transport.open_session') as connection,
              patch('resource_mail.desktop_unlocked', return_value=True) as unlocked,
              patch('resource_panel.QToolTip.showText') as copy_tip,
              patch.object(QApplication, 'clipboard', return_value=clipboard)):
            editor = MailAccountEditor(mailbox, window)
            editor.show()
            editor.provider.setCurrentIndex(editor.provider.findData('gmail'))
            editor.method.setCurrentIndex(editor.method.findData('google'))
            assert not editor.import_google.isHidden() and editor.password.isHidden()
            editor.provider.setCurrentIndex(editor.provider.findData('imap'))
            assert not editor.server.isHidden() and not editor.password.isHidden()
            editor.provider.setCurrentIndex(editor.provider.findData('qq'))
            assert editor.server.isHidden() and editor.form.labelForField(editor.server).isHidden()
            editor.address.setText(qq['address'])
            editor.name.setText(qq['name'])
            editor.password.setText('fixture-password')
            editor.save.click()
            until = time.monotonic() + 3
            while editor.isVisible() and time.monotonic() < until:
                Events.qWait(15)
            assert editor.result() == QDialog.Accepted, editor.status.text()
            connection.return_value.test.assert_called_once()
            qq = next(row for row in mailbox.accounts() if row['provider'] == 'qq')
            assert credential_store[qq['id']]['secret']['password'] == 'fixture-password'
            assert 'fixture-password' not in repr(api.load_config())
            management = MailAccountsDialog(mailbox, window)
            management.show();app.processEvents()
            assert management.list.count() == 3
            management.grab().save(str(output/'mail-accounts.png'))
            management.reject()

            stamp = time.time()
            for index, row in enumerate(mailbox.accounts()):
                messages = [MailItem(f'{index}-{n}', f'{row["name"]} · 测试邮件 {n}', '测试发件人', stamp-n-index/10,
                                     inbox_url(row)) for n in range(9)]
                mailbox.accept_snapshot(row['id'], messages, [])
            window.select_page('mail')
            app.processEvents()
            view = window.view('mail').content
            assert view.isVisible() and view.rows.count() == 20 and view.filter.count() == 4
            assert (view.filter.width(), view.filter.height(), view.reload.height()) == (112, 22, 22)
            assert view.filter.geometry().center().y() == view.reload.geometry().center().y()
            assert len({view.rows.itemAt(i).widget().accent for i in range(view.rows.count())}) == 3
            window.grab().save(str(output/'mail-capsule.png'))
            view.filter.setCurrentIndex(view.filter.findData(netease['id']))
            assert view.rows.count() == 9
            with patch('resource_content.QDesktopServices.openUrl', return_value=True) as open_url:
                view.rows.itemAt(0).widget().click()
                assert open_url.call_args.args[0].toString() == 'https://mail.126.com/'

            settings = ResourceOptions(service)
            settings.show();settings.tabs.setCurrentIndex(9);app.processEvents()
            period = settings.fields['resource_mail_interval']
            assert (period.value(), period.minimum(), period.maximum()) == (30, 10, 900)
            period.setValue(45)
            assert settings.commit() and api.load_config()['resource_mail_interval'] == 45
            settings.tabs.setCurrentIndex(2);app.processEvents()
            settings.fields['resource_mail_icon'].setChecked(True)
            assert settings.commit() and api.load_config()['resource_mail_icon']
            settings.reject()

            service.fold(True);app.processEvents()
            idle = window.grab().toImage()
            assert 'mail' in window.status_bounds and not mailbox.unseen
            target = MailItem('new', '验证码：••••••', '测试发件人', time.time(), inbox_url(qq))
            mailbox.accept_snapshot(qq['id'], [target], [(target, '654321')])
            notice = window.grab()
            assert notice.toImage() != idle and mailbox.unseen[qq['id']]
            assert 'mail_code' in window.reminder_kinds
            point = window.reminder_bounds[window.reminder_kinds.index('mail_code')].center().toPoint()
            notice.save(str(output/'mail-code-capsule.png'))
            window.expand_from(point, automatic=True)
            clipboard.setText.assert_not_called()
            Events.drag(window, point, QPoint())
            clipboard.setText.assert_called_once_with('654321')
            assert copy_tip.call_args.args[1] == '验证码已复制'
            assert service.compact and not mailbox.current_code()
            window.grab()
            point = window.status_bounds['mail'].center().toPoint()
            Events.drag(window, point, QPoint());app.processEvents()
            assert not service.compact and window.page_key == 'mail'
            assert mailbox.unseen[qq['id']]  # Filtering a different mailbox does not mark QQ seen.
            view = window.view('mail').content
            view.filter.setCurrentIndex(view.filter.findData(''))
            assert not mailbox.unseen

            mailbox.accept_snapshot(qq['id'], [target], [(target, '654321')])
            assert mailbox.current_code()
            mailbox.session_locked()
            unlocked.return_value = False
            mailbox.accept_snapshot(qq['id'], [target], [(target, '654321')])
            assert not mailbox.current_code() and not mailbox.copy_code()
            clipboard.setText.assert_called_once()
            mailbox.remove_account(qq['id'])
            assert not mailbox.account(qq['id']) and qq['id'] not in credential_store
        checks.append('Mail UI: account creation and vault isolation, 20 recent sorted mails, account color and filter, webmail click, refresh interval persistence, compact envelope and one-click code copy with lock handling.')
    finally:
        for dialog in (settings, management, editor):
            if dialog:
                dialog.reject();dialog.deleteLater()
        cfg.clear();cfg.update(before);service.auto_compact=None;service.sync();api.save_config(cfg)
