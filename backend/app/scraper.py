import asyncio
from datetime import datetime, timezone

from playwright.async_api import BrowserContext, async_playwright

from .access import alert_user, wait_for_access
from .config import Settings
from .database import Database
from .parser import (
    ADVANCED,
    AIR_CAREER_CENTER,
    AccessBlocked,
    ParseError,
    checked_soup,
    parse_air_job,
    parse_air_results,
    parse_job,
    parse_results,
)


class HigherEdJobsScraper:
    def __init__(self, database: Database, settings: Settings):
        self.database, self.settings = database, settings
        # Set after one unsolved verification so the rest of the run fails fast instead of
        # waiting the full timeout again for every group and listing.
        self.verification_abandoned = False

    async def run(self, group_ids: list[str] | None = None):
        groups = [group for group in self.database.groups() if group["enabled"] and (not group_ids or group["id"] in group_ids)]
        run_id = self.database.start_run([group["id"] for group in groups], source="higheredjobs"); errors=[]; discovered=new=updated=0
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=self.settings.headless, channel=self.settings.browser_channel)
                context = await browser.new_context(storage_state=self.settings.storage_state) if self.settings.storage_state else await browser.new_context()
                # Listing URL -> job id for this run, so a job matched by several groups is opened once.
                fetched: dict[str, int] = {}
                try:
                    for group in groups:
                        try:
                            counts = await self._run_group(context, group, fetched); discovered += counts[0]; new += counts[1]; updated += counts[2]
                        except Exception as error:
                            errors.append({"group":group["name"],"error":str(error)})
                finally:
                    await context.close(); await browser.close()
        finally:
            self.database.finish_run(run_id, discovered, new, updated, errors)
        return self.database.latest_run()

    async def _run_group(self, context: BrowserContext, group: dict, fetched: dict[str, int]):
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
                    if key in fetched:
                        self.database.add_match(fetched[key], group["id"]); continue
                    detail=await context.new_page()
                    try:
                        await detail.goto(key, wait_until="domcontentloaded"); await self._ensure_access(detail)
                        full=parse_job(await detail.content(), detail.url, now)
                        for field in ("title","institution","location","city","state","salary","posted_date"):
                            setattr(full, field, getattr(full, field) or getattr(listing, field))
                        fetched[key], is_new = self.database.upsert_job(full,group["id"]); new += int(is_new); updated += int(not is_new)
                    except (ParseError, AccessBlocked) as error:
                        listing.description_status = "Failed"
                        fetched[key], _ = self.database.upsert_job(listing,group["id"]); updated += 1
                    finally: await detail.close(); await asyncio.sleep(self.settings.request_delay)
                next_link=page.get_by_role("link", name="Next page")
                if await next_link.count() and await next_link.is_visible():
                    await next_link.click(); await page.wait_for_load_state("domcontentloaded"); await self._ensure_access(page); await asyncio.sleep(self.settings.request_delay)
                else: break
            return discovered,new,updated
        finally: await page.close()

    async def _ensure_access(self, page):
        if self.settings.headless:
            checked_soup(await page.content()); return
        if self.verification_abandoned:
            checked_soup(await page.content()); return
        state_path = self.settings.storage_state or str(self.settings.state_path)
        try:
            await wait_for_access(
                page,
                timeout_s=self.settings.verification_timeout_s,
                alert=alert_user,
                save_state=lambda: page.context.storage_state(path=state_path),
            )
        except AccessBlocked:
            self.verification_abandoned = True
            raise


class AIRScraper:
    def __init__(self, database: Database, settings: Settings):
        self.database, self.settings = database, settings

    async def run(self):
        run_id = self.database.start_run([], source="air")
        errors = []
        discovered = new = updated = 0
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self.settings.headless,
                    channel=self.settings.browser_channel,
                )
                context = (
                    await browser.new_context(storage_state=self.settings.storage_state)
                    if self.settings.storage_state
                    else await browser.new_context()
                )
                try:
                    page = await context.new_page()
                    page.set_default_timeout(self.settings.timeout_ms)
                    try:
                        await page.goto(AIR_CAREER_CENTER, wait_until="domcontentloaded")
                        await self._ensure_access(page)
                        listings = parse_air_results(
                            await page.content(), page.url, datetime.now(timezone.utc)
                        )
                        discovered = len(listings)
                        for listing in listings:
                            detail = await context.new_page()
                            try:
                                await detail.goto(
                                    listing.source_url, wait_until="domcontentloaded"
                                )
                                await self._ensure_access(detail)
                                full = parse_air_job(
                                    await detail.content(),
                                    detail.url,
                                    datetime.now(timezone.utc),
                                )
                                for field in (
                                    "title",
                                    "institution",
                                    "location",
                                    "city",
                                    "state",
                                    "salary",
                                    "application_due_date",
                                ):
                                    setattr(
                                        full,
                                        field,
                                        getattr(full, field) or getattr(listing, field),
                                    )
                                is_new = self.database.upsert(full)
                                new += int(is_new)
                                updated += int(not is_new)
                            except (ParseError, AccessBlocked) as error:
                                listing.description_status = "Failed"
                                self.database.upsert(listing)
                                updated += 1
                                errors.append(
                                    {
                                        "source": "air",
                                        "listing_url": listing.source_url,
                                        "error": str(error),
                                    }
                                )
                            except Exception as error:
                                listing.description_status = "Failed"
                                self.database.upsert(listing)
                                updated += 1
                                errors.append(
                                    {
                                        "source": "air",
                                        "listing_url": listing.source_url,
                                        "error": str(error),
                                    }
                                )
                            finally:
                                await detail.close()
                                await asyncio.sleep(self.settings.request_delay)
                    finally:
                        await page.close()
                finally:
                    await context.close()
                    await browser.close()
        except Exception as error:
            errors.append({"source": "air", "error": str(error)})
        finally:
            self.database.finish_run(run_id, discovered, new, updated, errors)
        return self.database.latest_run()

    async def _ensure_access(self, page):
        checked_soup(await page.content(), "AIR")
