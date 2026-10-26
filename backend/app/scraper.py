import asyncio
import time
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
from .progress import elapsed, report

HEJ = "HigherEdJobs"


class HigherEdJobsScraper:
    def __init__(self, database: Database, settings: Settings):
        self.database, self.settings = database, settings
        # Set after one unsolved verification so the rest of the run fails fast instead of
        # waiting the full timeout again for every group and listing.
        self.verification_abandoned = False
        # One search tab and one job tab per browser context, reused for the whole run. Opening a
        # tab activates the browser and pulls the user to its desktop, so tabs are never opened per job.
        self._tabs: dict[BrowserContext, tuple] = {}

    async def run(self, group_ids: list[str] | None = None):
        groups = [group for group in self.database.groups() if group["enabled"] and (not group_ids or group["id"] in group_ids)]
        run_id = self.database.start_run([group["id"] for group in groups], source="higheredjobs"); errors=[]; discovered=new=updated=0
        started = time.monotonic()
        report(HEJ, f"Starting {len(groups)} search groups: " + ", ".join(group["name"] for group in groups))
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=self.settings.headless, channel=self.settings.browser_channel)
                context = await browser.new_context(storage_state=self.settings.storage_state) if self.settings.storage_state else await browser.new_context()
                # Listing URL -> job id for this run, so a job matched by several groups is opened once.
                fetched: dict[str, int] = {}
                try:
                    for index, group in enumerate(groups, 1):
                        report(HEJ, f"Group {index}/{len(groups)}: {group['name']}")
                        try:
                            counts = await self._run_group(context, group, fetched, errors); discovered += counts[0]; new += counts[1]; updated += counts[2]
                        except Exception as error:
                            errors.append({"group":group["name"],"error":str(error)})
                            report(HEJ, f"{group['name']} stopped: {error}")
                finally:
                    await context.close(); await browser.close()
        finally:
            self.database.finish_run(run_id, discovered, new, updated, errors)
            report(HEJ, f"Finished in {elapsed(time.monotonic() - started)}: {discovered} listings, {new} new, {len(errors)} errors")
        return self.database.latest_run()

    async def _run_group(self, context: BrowserContext, group: dict, fetched: dict[str, int], errors: list[dict]):
        name = group["name"]
        report(HEJ, f"{name}: searching")
        page, detail = await self._tabs_for(context)
        await page.goto(ADVANCED, wait_until="domcontentloaded"); await self._ensure_access(page)
        keyword = page.get_by_role("textbox", name="Keyword Use quotes to search")
        await keyword.fill(group["query"]); await page.get_by_role("button", name="Search Jobs").click()
        await page.wait_for_load_state("domcontentloaded"); await self._ensure_access(page)
        seen=set(); discovered=new=updated=failed=0; page_number=1
        while True:
            html=await page.content(); now=datetime.now(timezone.utc); listings=parse_results(html, page.url, now)
            report(HEJ, f"{name} page {page_number}: {len(listings)} listings")
            for listing in listings:
                key=listing.higheredjobs_url
                if key in seen: continue
                seen.add(key); discovered += 1
                label = listing.title or key
                if key in fetched:
                    self.database.add_match(fetched[key], group["id"])
                    report(HEJ, f"  ↺ {label} — already fetched; added to {name}"); continue
                try:
                    await detail.goto(key, wait_until="domcontentloaded"); await self._ensure_access(detail)
                    full=parse_job(await detail.content(), detail.url, now)
                    for field in ("title","institution","location","city","state","salary","posted_date"):
                        setattr(full, field, getattr(full, field) or getattr(listing, field))
                    fetched[key], is_new = self.database.upsert_job(full,group["id"]); new += int(is_new); updated += int(not is_new)
                    report(HEJ, f"  ✓ {full.title or label} — {full.institution or 'unknown institution'}")
                except Exception as error:
                    # One bad page (timeout, block, unparseable) must not end the group.
                    listing.description_status = "Failed"
                    fetched[key], _ = self.database.upsert_job(listing,group["id"]); updated += 1; failed += 1
                    errors.append({"group":name,"listing_url":key,"error":str(error)})
                    report(HEJ, f"  ✗ {label} — {str(error).splitlines()[0] if str(error) else type(error).__name__}")
                finally: await asyncio.sleep(self.settings.request_delay)
            next_link=page.get_by_role("link", name="Next page")
            if await next_link.count() and await next_link.is_visible():
                await next_link.click(); await page.wait_for_load_state("domcontentloaded"); await self._ensure_access(page); await asyncio.sleep(self.settings.request_delay)
                page_number += 1
            else: break
        report(HEJ, f"{name} done: {discovered} listings, {new} new, {failed} failed")
        return discovered,new,updated

    async def _tabs_for(self, context: BrowserContext):
        if context not in self._tabs:
            tabs = (await context.new_page(), await context.new_page())
            for tab in tabs: tab.set_default_timeout(self.settings.timeout_ms)
            self._tabs[context] = tabs
        return self._tabs[context]

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
                save_state=lambda: self._save_session(page, state_path),
            )
        except AccessBlocked:
            self.verification_abandoned = True
            report(HEJ, "Verification not completed in time; skipping HigherEdJobs pages for the rest of this run.")
            raise

    async def _save_session(self, page, state_path: str):
        await page.context.storage_state(path=state_path)
        report(HEJ, "Verification passed; session saved. Continuing.")


class AIRScraper:
    def __init__(self, database: Database, settings: Settings):
        self.database, self.settings = database, settings

    async def run(self):
        run_id = self.database.start_run([], source="air")
        errors = []
        discovered = new = updated = 0
        started = time.monotonic()
        report("AIR", "Loading AIR Career Center board")
        try:
            async with async_playwright() as playwright:
                # AIR has no human verification, so it never needs a window that would steal focus.
                browser = await playwright.chromium.launch(
                    headless=True,
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
                        report("AIR", f"Found {discovered} listings")
                        detail = await context.new_page()
                        detail.set_default_timeout(self.settings.timeout_ms)
                        for index, listing in enumerate(listings, 1):
                            label = f"({index}/{discovered})"
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
                                report("AIR", f"  {label} ✓ {full.title or listing.source_url} — {full.institution or 'unknown institution'}")
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
                                report("AIR", f"  {label} ✗ {listing.title or listing.source_url} — {error}")
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
                                report("AIR", f"  {label} ✗ {listing.title or listing.source_url} — {error}")
                            finally:
                                await asyncio.sleep(self.settings.request_delay)
                    finally:
                        await page.close()
                finally:
                    await context.close()
                    await browser.close()
        except Exception as error:
            errors.append({"source": "air", "error": str(error)})
            report("AIR", f"Stopped: {error}")
        finally:
            self.database.finish_run(run_id, discovered, new, updated, errors)
            report("AIR", f"Finished in {elapsed(time.monotonic() - started)}: {discovered} listings, {new} new, {len(errors)} errors")
        return self.database.latest_run()

    async def _ensure_access(self, page):
        checked_soup(await page.content(), "AIR")
