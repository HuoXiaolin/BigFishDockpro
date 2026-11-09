"""Download and invoke verified calendar tools only when a provider needs them."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.request import urlopen

from resource_calendar_api import CalendarError, MAX_RESPONSE

CHUNK = 256 * 1024


def verified(path, expected):
    try:
        with path.open('rb') as file:
            return hashlib.file_digest(file, 'sha256').hexdigest() == expected
    except OSError:
        return False


def check_cancelled(job):
    if job.cancelled.is_set():
        raise CalendarError('已取消本次操作。')


def download_bundle(job, target, url, size, checksum, label):
    check_cancelled(job)
    job.progress.emit('download', 0, size)
    digest = hashlib.new('sha512' if len(checksum) == 128 else 'sha256')
    received = 0
    last_report = time.monotonic()
    try:
        with urlopen(url, timeout=12) as response:
            while chunk := response.read1(CHUNK):
                check_cancelled(job)
                received += len(chunk)
                if received > size:
                    raise CalendarError(f'{label}组件下载大小异常，请重试。')
                target.write(chunk)
                digest.update(chunk)
                now = time.monotonic()
                if now - last_report >= .08 or received == size:
                    job.progress.emit('download', received, size)
                    last_report = now
    except OSError as error:
        raise CalendarError(f'{label}组件下载失败，请检查网络后重试。') from error
    check_cancelled(job)
    job.progress.emit('install', received, size)
    if received != size or digest.hexdigest() != checksum:
        raise CalendarError(f'{label}组件下载校验失败，请重试。')
    target.seek(0)


def install_program(job, source, target, checksum, label):
    pending = None
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as output:
            pending = Path(output.name)
            while chunk := source.read(CHUNK):
                check_cancelled(job)
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != checksum:
            raise CalendarError(f'{label}授权程序校验失败，请重试。')
        check_cancelled(job)
        os.replace(pending, target)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def run_tool(job, program, args, env, timeout, label, *, scan=None, watch_stdout=False):
    """Stream the provider's authorization link and keep command output bounded."""
    check_cancelled(job)
    expired = threading.Event()
    with tempfile.TemporaryFile() as captured:
        stdout, stderr = (subprocess.PIPE, captured) if watch_stdout else (captured, subprocess.PIPE)
        with subprocess.Popen([str(program), *args], cwd=program.parent, env=env,
                              stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                              creationflags=subprocess.CREATE_NO_WINDOW) as process:
            job.own_process(process)

            def stop():
                expired.set()
                try:
                    process.kill()
                except OSError:
                    pass

            timer = threading.Timer(timeout, stop)
            timer.daemon = True
            timer.start()
            output = bytearray()
            stream = process.stdout if watch_stdout else process.stderr
            too_large = False
            try:
                while line := stream.readline(4096):
                    output.extend(line)
                    if watch_stdout and len(output) > MAX_RESPONSE:
                        too_large = True
                        stop()
                        break
                    if not watch_stdout and len(output) > 16384:
                        del output[:-16384]
                    if scan:
                        scan(line.decode('utf-8', 'replace').strip())
                code = process.wait()
            finally:
                timer.cancel()
                job.release_process(process)
        captured.seek(0)
        data = captured.read(16384 if watch_stdout else MAX_RESPONSE + 1)
    check_cancelled(job)
    if too_large or not watch_stdout and len(data) > MAX_RESPONSE:
        raise CalendarError(f'{label}返回的数据过大，已保留上次同步结果。')
    if expired.is_set():
        raise CalendarError(f'{label}操作超时，请重试。')
    raw, diagnostic = (bytes(output), data) if watch_stdout else (data, bytes(output))
    return code, raw, diagnostic.decode('utf-8', 'replace')
