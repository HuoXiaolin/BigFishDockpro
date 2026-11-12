"""Keep account UI checks runnable when the isolated Windows profile cannot use DPAPI."""
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4


@contextmanager
def private_storage(checks):
    import resource_calendar_sync as calendar

    probe = b'BigFishDock private storage test'
    try:
        assert calendar.protect(calendar.protect(probe, True), False) == probe
    except OSError as error:
        if getattr(error, 'winerror', None) != 2:
            raise
    else:
        yield
        return

    from run_isolated_test import assert_isolated
    assert_isolated()
    note = ('Native DPAPI unavailable in the isolated Windows profile (WinError 2). '
            'Account storage tests use opaque handles for synthetic data; native encryption is unverified.')
    if note not in checks:
        checks.append(note)
    payloads = {}

    def protect(payload, encrypt):
        if encrypt:
            handle = b'BigFishDock-test\0' + uuid4().bytes
            payloads[handle] = payload
            return handle
        try:
            return payloads[payload]
        except KeyError as error:
            raise ValueError('Invalid test storage handle') from error

    with patch.object(calendar, 'protect', protect):
        yield
