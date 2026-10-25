import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable

from playwright.async_api import Error as PlaywrightError

from .parser import AccessBlocked, checked_soup


def alert_user() -> None:
    print(
        "\a⚠ HigherEdJobs needs verification — solve it in the open browser window. "
        "The run will continue automatically.",
        file=sys.stderr,
        flush=True,
    )
    try:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
    except OSError:
        pass


async def wait_for_access(
    page,
    *,
    timeout_s: float,
    poll_s: float = 3.0,
    alert: Callable[[], None],
    save_state: Callable[[], Awaitable[None]],
) -> None:
    """Return once the page is past HigherEdJobs' access check, waiting for a person to solve it."""
    try:
        checked_soup(await page.content())
        return
    except AccessBlocked:
        alert()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        await asyncio.sleep(poll_s)
        try:
            checked_soup(await page.content())
        except (AccessBlocked, PlaywrightError):
            # Solving the check reloads the page; content() fails while it navigates.
            if loop.time() >= deadline:
                raise
            continue
        await save_state()
        return
