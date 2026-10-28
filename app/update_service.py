"""Opt-in, asynchronous update checks against this project's own manifest."""
import json
import re
import threading
from urllib.parse import urlparse
from PyQt5.QtCore import QObject, pyqtSignal
from app_version import VERSION, PROJECT_ID


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('版本清单中的版本必须是三段数字。')
    return tuple(map(int, value.split('.')))


def parse_manifest(payload, current=VERSION):
    if not isinstance(payload, dict) or payload.get('product_id') != PROJECT_ID:
        raise ValueError('版本清单不属于 BigFishDockpro，已拒绝使用。')
    version = payload.get('version')
    newer = version_tuple(version) > version_tuple(current)
    release_url = payload.get('release_url') or payload.get('download_url') or ''
    if release_url and urlparse(release_url).scheme != 'https':
        raise ValueError('更新链接必须使用 HTTPS。')
    return {'newer': newer, 'version': version, 'release_url': release_url,
            'notes': str(payload.get('release_notes', ''))[:4000]}


def fetch_manifest(url, use_proxy):
    import urllib.request
    if urlparse(url).scheme != 'https':
        raise ValueError('更新源必须是本项目的 HTTPS 版本清单地址。')
    handlers = [] if use_proxy else [urllib.request.ProxyHandler({})]
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={'User-Agent': 'BigFishDockpro/'+VERSION, 'Accept':'application/json'})
    with opener.open(request, timeout=12) as response:
        if urlparse(response.geturl()).scheme != 'https':
            raise ValueError('更新源重定向到了非 HTTPS 地址。')
        content = response.read(512*1024+1)
        if len(content) > 512*1024:
            raise ValueError('版本清单超过大小限制。')
    return parse_manifest(json.loads(content.decode('utf-8-sig')))


class UpdateWorker(QObject):
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, source, proxy, fetcher=fetch_manifest):
        super().__init__()
        self.source, self.proxy, self.fetcher = source, proxy, fetcher
        self.cancelled = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def isRunning(self):
        return bool(self.thread and self.thread.is_alive())

    def wait(self, milliseconds):
        if self.thread:
            self.thread.join(milliseconds/1000)

    def run(self):
        try:
            result = self.fetcher(self.source, self.proxy)
            if not self.cancelled.is_set():
                self.ready.emit(result)
        except Exception as error:
            if not self.cancelled.is_set():
                self.failed.emit(str(error))


class UpdateService(QObject):
    changed = pyqtSignal(str)

    def __init__(self, runtime):
        super().__init__()
        self.runtime = runtime
        self.worker = None
        self.message = '尚未配置更新源'
        self.release_url = ''

    def check(self):
        if self.worker and self.worker.isRunning():
            return
        cfg = self.runtime.dock.cfg
        if not cfg['update_source']:
            self.set_message('尚未配置更新源；没有发起网络请求。')
            return
        self.set_message('正在检查更新…')
        self.worker = UpdateWorker(cfg['update_source'], cfg['update_use_proxy'])
        self.worker.ready.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.start()

    def set_message(self, message):
        self.message = message
        self.changed.emit(message)

    def completed(self, result):
        self.release_url = result['release_url'] if result['newer'] else ''
        self.set_message('发现新版本 '+result['version'] if result['newer'] else '当前已是最新版本（'+VERSION+'）')
        if result['newer']:
            self.runtime.tray.showMessage('大肥鱼Dock 更新', self.message+'，可在设置中查看下载页面。', self.runtime.tray.icon(), 5000)

    def failed(self, error):
        self.release_url = ''
        self.runtime.api.log('检查更新失败: ' + error)
        self.set_message('检查失败：'+error[:160])

    def close(self):
        if self.worker:
            self.worker.cancelled.set()
            self.worker.wait(500)
