import asyncio
from datetime import datetime, timezone

from playwright.async_api import BrowserContext, async_playwright

from .config import Settings
from .database import Database
from .parser import ADVANCED, AccessBlocked, ParseError, checked_soup, parse_job, parse_results


class HigherEdJobsScraper:
    def __init__(self, database: Database, settings: Settings): self.database, self.settings = database, settings

    async def run(self, group_ids: list[str] | None = None):
        groups = [group for group in self.database.groups() if group["enabled"] and (not group_ids or group["id"] in group_ids)]
        run_id = self.database.start_run([group["id"] for group in groups]); errors=[]; discovered=new=updated=0
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=self.settings.headless, channel=self.settings.browser_channel)
                context = await browser.new_context(storage_state=self.settings.storage_state) if self.settings.storage_state else await browser.new_context()
                try:
                    for group in groups:
                        try:
                            counts = await self._run_group(context, group); discovered += counts[0]; new += counts[1]; updated += counts[2]
                        except Exception as error:
                            errors.append({"group":group["name"],"error":str(error)})
                finally:
                    await context.close(); await browser.close()
        finally:
            self.database.finish_run(run_id, discovered, new, updated, errors)
        return self.database.latest_run()

    async def _run_group(self, context: BrowserContext, group: dict):
        page = await context.new_page(); page.set_default_timeout(self.settings.timeout_ms)
        try:
            await page.goto(ADVANCED, wait_until="domcontentloaded"); await self._ensure_access(page)
            keyword = page.get_by_role("textbox", name="Keyword Use quotes to search")
            await keyword.fill(group["query"]); await page.get_by_role("button", name="Search Jobs").click()
            await page.wait_for_load_state("domcontentloaded"); await self._ensure_access(page)
            seen=set(); discovered=new=updated=0
            while True:
                html=await page.content(); now=datetime.now(timezone.utc); listings=parse_results(html, page.url, now)
                for listing in listings:
                    key=listing.higheredjobs_url
                    if key in seen: continue
                    seen.add(key); discovered += 1
                    detail=await context.new_page()
                    try:
                        await detail.goto(key, wait_until="domcontentloaded"); await self._ensure_access(detail)
                        full=parse_job(await detail.content(), detail.url, now)
                        for field in ("title","institution","location","city","state","salary","posted_date"):
                            setattr(full, field, getattr(full, field) or getattr(listing, field))
                        is_new=self.database.upsert(full,group["id"]); new += int(is_new); updated += int(not is_new)
                    except (ParseError, AccessBlocked) as error:
                        self.database.upsert(listing,group["id"]); updated += 1
                    finally: await detail.close(); await asyncio.sleep(self.settings.request_delay)
                next_link=page.get_by_role("link", name="Next page")
                if await next_link.count() and await next_link.is_visible():
                    await next_link.click(); await page.wait_for_load_state("domcontentloaded"); await self._ensure_access(page); await asyncio.sleep(self.settings.request_delay)
                else: break
            return discovered,new,updated
        finally: await page.close()

    async def _ensure_access(self, page):
        content=await page.content()
        checked_soup(content)
