"""HTTP for public job boards: one polite client, with blocks reported instead of worked around."""
import asyncio
import json
import time
from urllib.parse import urlsplit

import httpx

# Generic on purpose: no personal contact details are sent to job boards.
USER_AGENT = "job-board-reader/1.0"
TIMEOUT_S = 30


class BoardMissing(Exception):
    """The board answered 404: the company slug no longer exists there."""


class BoardError(Exception):
    """Any other failure: server error, timeout, unreadable response. Retried on a later run."""


class BoardBlocked(Exception):
    """403, 429 or a challenge page. The caller stops requesting this host for the run."""

    def __init__(self, host: str, retry_after: str | None = None, status: int | None = None):
        self.host, self.retry_after, self.status = host, retry_after, status
        wait = f", Retry-After {retry_after}" if retry_after else ""
        super().__init__(f"{host} blocked automated requests ({status or 'challenge page'}{wait})")


class BoardClient:
    """Requests sharing a `key` (an ATS name) run one at a time with `delay` seconds between them."""

    def __init__(self, delay: float, transport: httpx.AsyncBaseTransport | None = None):
        self.delay = delay
        self._http = httpx.AsyncClient(
            transport=transport, timeout=TIMEOUT_S, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._http.aclose()

    async def get_json(self, url: str, key: str):
        return self._decode(await self._send("GET", url, key))

    async def post_json(self, url: str, body: dict, key: str):
        return self._decode(await self._send("POST", url, key, json=body))

    async def get_text(self, url: str, key: str) -> str:
        return (await self._send("GET", url, key)).text

    async def _send(self, method: str, url: str, key: str, **kwargs) -> httpx.Response:
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            wait = self._last.get(key, 0) + self.delay - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self._http.request(method, url, **kwargs)
            except httpx.HTTPError as error:
                raise BoardError(f"{method} {url} failed: {error!r}") from error
            finally:
                self._last[key] = time.monotonic()
        host = urlsplit(url).hostname or url
        if response.status_code in (403, 429):
            raise BoardBlocked(host, response.headers.get("Retry-After"), response.status_code)
        if response.status_code == 404:
            raise BoardMissing(f"{url} answered 404")
        if response.status_code >= 400:
            raise BoardError(f"{url} answered {response.status_code}")
        if "html" in response.headers.get("content-type", "").lower():
            raise BoardBlocked(host)
        return response

    @staticmethod
    def _decode(response: httpx.Response):
        try:
            return response.json()
        except json.JSONDecodeError as error:
            raise BoardError(f"{response.request.url} sent unreadable JSON") from error
