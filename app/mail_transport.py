"""Small read-only inbox snapshots using the provider's IMAP UID validity."""
from email import errors
import imaplib
import re
import ssl
import time

from mail_accounts import MAIL_LIMIT, imap_endpoint, inbox_url
from mail_messages import MAX_TEXT, MailError, MailItem, message_code, message_headers, summary_subject, verification_code


TIMEOUT = 8
UID = re.compile(rb'\bUID (\d+)', re.I)
GM_UID = re.compile(rb'\bX-GM-MSGID (\d+)', re.I)
HEADER_FIELDS = '(UID INTERNALDATE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM)])'


def expect(response):
    result, data = response
    if result != 'OK':
        raise MailError('邮箱服务器暂时无法读取收件箱。')
    return data


class ImapSession:
    def __init__(self, account, secret, cancelled):
        self.account = account
        self.cancelled = cancelled
        self.client = None
        self.items = {}
        self.validity = None
        self.newest_uid = None
        self.password = secret.get('password')
        if not isinstance(self.password, str) or not self.password:
            raise MailError('需要重新连接邮箱。', authorization=True)

    def connect(self):
        account = self.account
        host, port = imap_endpoint(account)
        try:
            self.client = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
            try:
                expect(self.client.login(account['address'], self.password))
            except imaplib.IMAP4.abort:
                raise
            except (imaplib.IMAP4.error, MailError, UnicodeError):
                raise MailError('邮箱授权失败，请核对地址与客户端授权码。', authorization=True) from None
            if 'ID' in self.client.capabilities:
                try:
                    self.client.xatom('ID', '("name" "BigFishDockpro" "vendor" "BigFishDockpro")')
                except imaplib.IMAP4.abort:
                    raise
                except imaplib.IMAP4.error:
                    pass
        except Exception:
            self.close()
            raise

    def close(self):
        client, self.client = self.client, None
        if client is not None:
            try:
                client.shutdown()
            except (OSError, imaplib.IMAP4.error):
                pass

    def mailbox(self):
        if self.client is None:
            self.connect()
        count = int(expect(self.client.select('INBOX', readonly=True))[0])
        validity = self.client.response('UIDVALIDITY')[1][0]
        if not isinstance(validity, bytes) or not validity.isdigit():
            raise MailError('邮箱服务器没有返回有效的收件箱标识。')
        return count, validity

    def test(self):
        self.mailbox()

    def snapshot(self, detect_codes):
        count, validity = self.mailbox()
        baseline = self.newest_uid if validity == self.validity else None
        cache = self.items if validity == self.validity else {}
        top = expect(self.client.fetch(f'{max(1, count-MAIL_LIMIT+1)}:{count}', '(UID)')) if count else []
        uids = sorted({int(match[1]) for row in top if isinstance(row, bytes) for match in UID.finditer(row)})[-MAIL_LIMIT:]
        missing = [str(uid) for uid in uids if uid not in cache]
        items = {uid: cache[uid] for uid in uids if uid in cache}
        arrivals = []
        if missing:
            headers = HEADER_FIELDS
            if self.account['provider'] == 'gmail' and 'X-GM-EXT-1' in self.client.capabilities:
                headers = headers[:-1] + ' X-GM-MSGID)'
            records = expect(self.client.uid('FETCH', ','.join(missing), headers))
            for record in records:
                if self.cancelled.is_set():
                    return (), ()
                if not isinstance(record, tuple) or not (matched := UID.search(record[0])):
                    continue
                uid = int(matched[1])
                if uid not in uids:
                    continue
                subject, sender = message_headers(record[1][:MAX_TEXT])
                received = imaplib.Internaldate2tuple(record[0])
                gmail_id = GM_UID.search(record[0])
                url = inbox_url(self.account, format(int(gmail_id[1]), 'x') if gmail_id else '')
                item = MailItem(str(uid), summary_subject(subject), sender, time.mktime(received) if received else 0, url)
                items[uid] = item
                if baseline is not None and uid > baseline:
                    code = verification_code(subject)
                    if detect_codes and not code:
                        code = self.fetch_code(uid, subject)
                    arrivals.append((item, code))
        self.validity = validity
        self.newest_uid = max(max(items, default=0), baseline or 0)
        self.items = items
        return tuple(items.values()), arrivals

    def fetch_code(self, uid, subject):
        try:
            result, data = self.client.uid('FETCH', str(uid), f'(BODY.PEEK[]<0.{MAX_TEXT}>)')
            if result == 'OK':
                for record in data:
                    if isinstance(record, tuple):
                        return message_code(record[1], subject)
        except (errors.MessageError, UnicodeError, LookupError, ValueError):
            pass
        return ''


def open_session(account, credentials, cancelled):
    if account['method'] == 'google':
        from gmail_mail import GmailSession
        return GmailSession(account, credentials, cancelled)
    return ImapSession(account, credentials, cancelled)
