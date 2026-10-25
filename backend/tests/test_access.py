import asyncio

import pytest

from backend.app.access import wait_for_access
from backend.app.parser import AccessBlocked

BLOCKED = "<p>Verify you are human</p>"
OK = "<p>Job</p>"


class FakePage:
    def __init__(self, pages):
        self.pages = list(pages)

    async def content(self):
        return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]


def run_wait(pages, **options):
    calls = {"alert": 0, "save": 0}

    def alert():
        calls["alert"] += 1

    async def save_state():
        calls["save"] += 1

    options.setdefault("timeout_s", 1)
    options.setdefault("poll_s", 0)
    try:
        asyncio.run(wait_for_access(FakePage(pages), alert=alert, save_state=save_state, **options))
    finally:
        run_wait.calls = calls
    return calls


def test_wait_for_access_passes_through_without_alert():
    assert run_wait([OK]) == {"alert": 0, "save": 0}


def test_wait_for_access_waits_then_saves():
    assert run_wait([BLOCKED, BLOCKED, OK]) == {"alert": 1, "save": 1}


def test_wait_for_access_times_out():
    with pytest.raises(AccessBlocked):
        run_wait([BLOCKED], timeout_s=0.05, poll_s=0.01)
    assert run_wait.calls == {"alert": 1, "save": 0}


class NavigatingPage(FakePage):
    async def content(self):
        page = self.pages.pop(0)
        if page is None:
            from playwright.async_api import Error
            raise Error("Unable to retrieve content because the page is navigating")
        return page


def test_wait_for_access_survives_navigation_while_polling():
    calls = {"alert": 0, "save": 0}

    async def save_state():
        calls["save"] += 1

    asyncio.run(wait_for_access(
        NavigatingPage([BLOCKED, None, OK]), timeout_s=1, poll_s=0,
        alert=lambda: calls.__setitem__("alert", calls["alert"] + 1), save_state=save_state,
    ))
    assert calls == {"alert": 1, "save": 1}
