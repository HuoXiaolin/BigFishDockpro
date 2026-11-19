"""Summaries and one-time codes extracted locally from read-only mail fetches."""
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from dataclasses import dataclass
import re


MAX_TEXT = 64 * 1024
KEYWORD = (r'验证码|一次性(?:密码|口令)|登录(?:码|代码)|安全(?:码|代码)|'
           r'(?<![a-z])(?:verification code|(?:sign[ -]?in|login|security|authentication) code|'
           r'one[ -]time (?:code|passcode|password)|OTP)(?![a-z])')
NUMBER = r'([0-9]{4,8}|[0-9]{3}[ \u00a0][0-9]{3})(?![a-z0-9-])'
PUNCTUATION = r'''[\s:：=,，'"“”‘’【】\[\]<>()（）*`—]*'''
CODE_AFTER = re.compile(rf'(?:{KEYWORD}){PUNCTUATION}(?:为|是|如下|is\b)?{PUNCTUATION}{NUMBER}', re.I)
CODE_BEFORE = re.compile(rf'(?<![a-z0-9-]){NUMBER}{PUNCTUATION}(?:是(?:你的|您的)?|is (?:your|the)\s+)?(?:{KEYWORD})', re.I)


@dataclass(frozen=True)
class MailItem:
    uid: str
    title: str
    sender: str
    stamp: float
    url: str


class MailError(Exception):
    def __init__(self, message, *, authorization=False):
        super().__init__(message)
        self.authorization = authorization


def code_matches(text):
    return [match for pattern in (CODE_AFTER, CODE_BEFORE) for match in pattern.finditer(text[:MAX_TEXT])]


def verification_code(subject, body=''):
    # Ambiguous messages stay ordinary notifications.
    for text in (subject, body):
        matches = {match[1].replace(' ', '').replace('\u00a0', '') for match in code_matches(text)}
        if matches:
            return next(iter(matches)) if len(matches) == 1 else ''
    return ''


def summary_subject(subject):
    text = ' '.join(subject.split())[:MAX_TEXT]
    spans = sorted({match.span(1) for match in code_matches(text)}, reverse=True)
    for start, end in spans:
        text = text[:start] + '••••••' + text[end:]
    return text[:320] or '无主题'


class TextFromHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('p', 'div', 'br', 'td', 'tr'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ('p', 'div', 'td', 'tr'):
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(text, mime):
    if mime != 'text/html':
        return text[:MAX_TEXT]
    parser = TextFromHtml()
    try:
        parser.feed(text[:MAX_TEXT])
    except (ValueError, AssertionError):
        return ''
    return ''.join(parser.parts)[:MAX_TEXT]


def message_headers(raw):
    message = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
    subject = str(message.get('Subject', ''))
    sender = ' '.join(str(message.get('From', '')).split())[:180] or '未知发件人'
    return subject, sender


def message_code(raw, subject):
    message = BytesParser(policy=policy.default).parsebytes(raw[:MAX_TEXT])
    for part in message.walk():
        mime = part.get_content_type()
        if mime not in ('text/plain', 'text/html') or part.get_content_disposition() == 'attachment':
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        try:
            text = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
        except LookupError:
            text = payload.decode('utf-8', errors='replace')
        code = verification_code(subject, plain_text(text, mime))
        if code:
            return code
    return ''
