"""HTML parsing isolated from browser navigation for fixture-based regression tests."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from dateutil.parser import ParserError, parse

BASE = "https://www.higheredjobs.com"
ADVANCED = f"{BASE}/search/advanced.cfm"
AIR_BASE = "https://www.airweb.org"
AIR_CAREER_CENTER = f"{AIR_BASE}/community/Career-Center/"


class ParseError(ValueError):
    pass


class AccessBlocked(ParseError):
    pass


@dataclass
class JobDraft:
    source: str = "higheredjobs"
    source_job_id: str | None = None
    source_url: str | None = None
    title: str | None = None
    higheredjobs_url: str | None = None
    higheredjobs_id: str | None = None
    institution: str | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    salary: str | None = None
    posted_date: str | None = None
    apply_url: str | None = None
    raw_description: str | None = None
    normalized_description: str | None = None
    application_due_date: str | None = None
    description_status: str | None = None

    def __post_init__(self):
        if self.source_url is None:
            self.source_url = self.higheredjobs_url
        if self.source_job_id is None:
            self.source_job_id = self.higheredjobs_id


def safe_url(value: str | None, base: str = BASE) -> str | None:
    if not value:
        return None
    absolute = urljoin(base, value.strip())
    parsed = urlparse(absolute)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username:
        return None
    return absolute


def is_hej(value: str) -> bool:
    return urlparse(value).hostname in ("www.higheredjobs.com", "higheredjobs.com")


def is_air(value: str) -> bool:
    return urlparse(value).hostname in ("www.airweb.org", "airweb.org")


def job_id(url: str) -> str | None:
    params = {key.lower(): value for key, value in parse_qs(urlparse(url).query).items()}
    value = params.get("jobcode", [None])[0]
    return value if value and value.isdigit() else None


def air_job_id(url: str) -> str | None:
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"/community/Career-Center/([^/]+)$", path, re.I)
    return match[1] if match else None


def canonical_url(url: str) -> str:
    identifier = job_id(url)
    if identifier and is_hej(url):
        return f"{BASE}/search/details.cfm?JobCode={identifier}"
    parsed = urlparse(url)
    query = {k: v for k, v in parse_qs(parsed.query).items() if not k.lower().startswith("utm_")}
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", urlencode(query, doseq=True), ""))


def canonical_air_url(url: str) -> str:
    parsed = urlparse(url)
    if not is_air(url) or not air_job_id(url):
        raise ParseError(f"Invalid AIR listing URL: {url}")
    return urlunparse((parsed.scheme.lower(), "www.airweb.org", parsed.path.rstrip("/"), "", "", ""))


def normalize_date(value: str | None, now: datetime) -> str | None:
    if not value:
        return None
    value = re.sub(r"^(?:posted|date posted|posting date)\s*:?\s*", "", value.strip(), flags=re.I)
    lower = value.lower()
    if lower == "today" or re.fullmatch(r"\d+\s+(?:minutes?|hours?)\s+ago", lower):
        return now.date().isoformat()
    if lower == "yesterday":
        return (now - timedelta(days=1)).date().isoformat()
    relative = re.fullmatch(r"(\d+)\s+(days?|weeks?)\s+ago", lower)
    if relative:
        days = int(relative[1]) * (7 if relative[2].startswith("week") else 1)
        return (now - timedelta(days=days)).date().isoformat()
    # Do not turn incomplete or unrecognizable text into invented dates.
    if not re.search(r"\d", value):
        return None
    try:
        return parse(value, fuzzy=False, default=now.replace(month=1, day=1)).date().isoformat()
    except (ParserError, ValueError, OverflowError):
        return None


def checked_soup(html: str, portal: str = "HigherEdJobs") -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    if soup.select_one('iframe[src*="_Incapsula_Resource"], iframe[src*="captcha"]') or any(
        phrase in text for phrase in ("request unsuccessful. incapsula", "verify you are human", "access denied", "pardon our interruption")
    ):
        if portal == "HigherEdJobs":
            raise AccessBlocked(
                "HigherEdJobs access check blocked this request. Open the site normally and use "
                "scripts/codegen.sh to verify access and selectors; no bypass is attempted."
            )
        raise AccessBlocked(f"{portal} access check blocked this request. Open the site normally and verify access and selectors; no bypass is attempted.")
    return soup


def text_at(node, selectors: str) -> str | None:
    found = node.select_one(selectors)
    return found.get_text(" ", strip=True) or None if found else None


def parse_results(html: str, url: str, now: datetime) -> list[JobDraft]:
    soup = checked_soup(html)
    jobs = {}
    for anchor in soup.select('a[href*="details.cfm" i]'):
        target = safe_url(anchor.get("href"), url)
        if not target or not is_hej(target) or not job_id(target):
            continue
        target = canonical_url(target)
        if target in jobs:
            continue
        row = anchor.find_parent(class_=re.compile(r"^(?:row|job-result|result-item)$")) or anchor.find_parent("tr") or anchor.parent
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        institution = text_at(row, '.institution, .company, [itemprop="hiringOrganization"]')
        location = text_at(row, '.location, [itemprop="jobLocation"]')
        # HigherEdJobs commonly places title, employer, and location on separate lines.
        lines = [line.strip() for line in row.get_text("\n", strip=True).splitlines() if line.strip()]
        if title in lines:
            remaining = lines[lines.index(title) + 1:]
            if not institution and remaining and not re.match(r"Posted|Category|\d+\s+days?", remaining[0], re.I):
                institution = remaining[0]
            if not location and len(remaining) > 1 and re.search(r",\s*[A-Z]{2}\b", remaining[1]):
                location = remaining[1]
        posted = text_at(row, '.job-date, .posted-date, .date, [itemprop="datePosted"]')
        if not posted:
            posted = next((line for line in lines if re.match(r"Posted\s*:?", line, re.I)), None)
        city, state = split_location(location)
        jobs[target] = JobDraft(
            source="higheredjobs",
            source_job_id=job_id(target),
            source_url=target,
            higheredjobs_url=target,
            higheredjobs_id=job_id(target),
            title=title,
            institution=institution,
            location=location,
            city=city,
            state=state,
            posted_date=normalize_date(posted, now),
            description_status="Pending",
        )
    if not jobs and not re.search(r"(?:no\s+(?:(?:matching|job|search)\s+)?(?:jobs|results|positions)|0\s+(?:jobs|results|positions)|no\s+jobs\s+found)", soup.get_text(" ", strip=True), re.I):
        raise ParseError("No recognizable results or explicit empty-result message. The site's markup may have changed; capture results with scripts/codegen.sh.")
    return list(jobs.values())


def next_page(html: str, url: str) -> str | None:
    soup = checked_soup(html)
    for anchor in soup.select("a[href]"):
        label = " ".join([anchor.get_text(" ", strip=True), str(anchor.get("aria-label", "")), str(anchor.get("title", ""))])
        rel = anchor.get("rel", [])
        if "next" in rel or re.search(r"\bnext\b|^\s*[›»]\s*$", label, re.I):
            parent = anchor.parent
            if anchor.get("aria-disabled") == "true" or "disabled" in anchor.get("class", []) or "disabled" in parent.get("class", []):
                continue
            target = safe_url(anchor.get("href"), url)
            if target and is_hej(target) and target != url and urlparse(target).path.startswith("/search/"):
                return target
    # Numeric pagination sometimes has no explicit Next link.
    current = soup.select_one('.pagination [aria-current="page"], .pagination .active')
    if current:
        match = re.search(r"\d+", current.get_text())
        if match:
            for anchor in soup.select('.pagination a[href]'):
                if anchor.get_text(strip=True) == str(int(match[0]) + 1):
                    target = safe_url(anchor.get("href"), url)
                    if target and is_hej(target):
                        return target
    return None


def split_location(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    match = re.match(r"^(.+),\s*([A-Z]{2})(?:\s+\d{5})?(?:,?\s+(?:United States|USA|US))?$", location)
    return (match[1], match[2]) if match else (None, None)


def job_postings(soup):
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if types == "JobPosting" or isinstance(types, list) and "JobPosting" in types:
                yield value
            if "@graph" in value:
                yield from walk(value["@graph"])
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            yield from walk(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue


def labeled_value(soup, label: str) -> str | None:
    for node in soup.select("b, strong, dt, label"):
        if re.fullmatch(label + r"\s*:?", node.get_text(" ", strip=True), re.I):
            if node.name == "dt":
                dd = node.find_next_sibling("dd")
                return dd.get_text(" ", strip=True) if dd else None
            values = []
            for sibling in node.next_siblings:
                if getattr(sibling, "name", None) in ("br", "b", "strong", "div"):
                    break
                values.append(sibling.get_text(" ", strip=True) if hasattr(sibling, "get_text") else str(sibling))
            result = " ".join(values).strip(" :\n")
            if result:
                return result
    return None


def parse_job(html: str, url: str, now: datetime) -> JobDraft:
    soup = checked_soup(html)
    data = next(job_postings(soup), {})
    raw = data.get("description")
    if not raw:
        node = soup.select_one('#jobDescription, #job-description, .job-description, [itemprop="description"]')
        raw = str(node) if node else None
    if not raw or not BeautifulSoup(raw, "html.parser").get_text(strip=True):
        raise ParseError("Job description not found. Listing metadata was retained; verify the description selector with codegen.")
    description_soup = BeautifulSoup(raw, "html.parser")
    for unwanted in description_soup.select("script, style, noscript"):
        unwanted.decompose()
    # Keep paragraphs intact for evidence, even when the sentence contains inline tags.
    for node in description_soup.select("p, div, li, br, h1, h2, h3, h4"):
        node.insert_after("\n")
    normalized = "\n".join(" ".join(line.split()) for line in description_soup.get_text().splitlines() if line.strip())
    organization = data.get("hiringOrganization") or {}
    institution = organization.get("name") if isinstance(organization, dict) else None
    institution = institution or text_at(soup, '.institution, .job-institution, [itemprop="hiringOrganization"]')
    job_location = data.get("jobLocation") or {}
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else {}
    address = job_location.get("address", {}) if isinstance(job_location, dict) else {}
    address = address if isinstance(address, dict) else {}
    city, state = address.get("addressLocality"), address.get("addressRegion")
    location = ", ".join(filter(None, [city, state])) or text_at(soup, '.location, .job-location') or labeled_value(soup, "Location")
    if not city and not state:
        city, state = split_location(location)
    salary = labeled_value(soup, "Salary")
    if not salary and isinstance(data.get("baseSalary"), dict):
        base_salary = data["baseSalary"]
        value = base_salary.get("value", {})
        if isinstance(value, dict):
            amount = value.get("value") or " – ".join(str(value[k]) for k in ("minValue", "maxValue") if value.get(k) is not None)
            if amount:
                salary = " ".join(str(v) for v in [base_salary.get("currency"), amount, value.get("unitText")] if v)
    apply_url = None
    for anchor in soup.select('a[href]'):
        if re.search(r"\bapply\b|application\s+(?:url|link|website)", anchor.get_text(" ", strip=True), re.I):
            target = safe_url(anchor.get("href"), url)
            if target and (not is_hej(target) or re.search(r"(?:apply|clickthru|redirect)", urlparse(target).path, re.I)):
                apply_url = target
                break
    return JobDraft(
        source="higheredjobs",
        source_job_id=job_id(url),
        source_url=canonical_url(url),
        higheredjobs_url=canonical_url(url),
        higheredjobs_id=job_id(url),
        title=data.get("title") or text_at(soup, 'h1, [itemprop="title"]'),
        institution=institution, location=location, city=city, state=state, salary=salary,
        posted_date=normalize_date(data.get("datePosted") or labeled_value(soup, "Posted|Date Posted|Posting Date"), now),
        apply_url=apply_url, raw_description=raw, normalized_description=normalized,
        description_status="Complete",
    )


def _air_cell(row, *labels: str) -> str | None:
    wanted = {label.casefold() for label in labels}
    for cell in row.select("[data-th]"):
        label = re.sub(r"\s+", " ", cell.get("data-th", "")).strip().casefold()
        if label in wanted:
            value = re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
            return value or None
    return None


def parse_air_results(html: str, url: str, now: datetime) -> list[JobDraft]:
    soup = checked_soup(html, "AIR")
    table = soup.select_one("table.job-listing-table")
    if not table:
        raise ParseError("AIR listing table was not found. The Career Center markup may have changed.")
    headers = {
        re.sub(r"\s+", " ", header.get_text(" ", strip=True)).casefold()
        for header in table.select("thead th")
    }
    expected = {"job title", "institution", "location", "application due date"}
    if not expected.issubset(headers):
        raise ParseError("AIR listing table headers changed; expected Job Title, Institution, Location, and Application Due Date.")
    rows = table.select("tbody tr.job-item")
    if not rows:
        text = soup.get_text(" ", strip=True)
        if re.search(r"(?:total jobs:\s*0|no\s+(?:jobs|results|positions))", text, re.I):
            return []
        raise ParseError("AIR listing table contained no recognizable job rows.")
    jobs: dict[str, JobDraft] = {}
    for row in rows:
        anchor = row.select_one('[data-th="Job Title"] a[href], td.title a[href], a[href]')
        target = safe_url(anchor.get("href"), url) if anchor else None
        if not target or not is_air(target) or not air_job_id(target):
            continue
        target = canonical_air_url(target)
        if target in jobs:
            continue
        due = _air_cell(row, "Application Due Date")
        jobs[target] = JobDraft(
            source="air",
            source_job_id=air_job_id(target),
            source_url=target,
            title=_air_cell(row, "Job Title") or (anchor.get_text(" ", strip=True) if anchor else None),
            institution=_air_cell(row, "Institution"),
            location=_air_cell(row, "Location"),
            salary=_air_cell(row, "Salary", "Salary Range"),
            application_due_date=normalize_date(due, now) or due,
            description_status="Pending",
        )
    if not jobs and not re.search(r"(?:total jobs:\s*0|no\s+(?:jobs|results|positions))", soup.get_text(" ", strip=True), re.I):
        raise ParseError("AIR listing rows did not contain valid detail links.")
    return list(jobs.values())


def parse_air_job(html: str, url: str, now: datetime) -> JobDraft:
    soup = checked_soup(html, "AIR")
    detail = soup.select_one("section.module.jobs.detail")
    if not detail:
        raise ParseError("AIR job detail section was not found.")
    sections = detail.select("section[aria-label]")
    content_sections = [section for section in sections if section.select_one(".clearfix")]
    if not content_sections:
        raise ParseError("AIR job description was not found.")
    raw = "\n".join(str(section.select_one(".clearfix")) for section in content_sections)
    description_soup = BeautifulSoup(raw, "html.parser")
    for unwanted in description_soup.select("script, style, noscript"):
        unwanted.decompose()
    normalized = "\n".join(" ".join(line.split()) for line in description_soup.get_text("\n").splitlines() if line.strip())
    if not normalized:
        raise ParseError("AIR job description was empty.")
    title = text_at(detail, "h1.title, h1")
    institution = labeled_value(detail, "Institution")
    location = labeled_value(detail, "Location")
    city = labeled_value(detail, "City")
    state = labeled_value(detail, "State/Province/Region")
    if not location:
        location = ", ".join(filter(None, [city, state])) or None
    due = labeled_value(detail, "Application Due Date")
    salary = labeled_value(detail, "Salary")
    apply_url = None
    for anchor in detail.select("a[href]"):
        target = safe_url(anchor.get("href"), url)
        if target and target != canonical_air_url(url) and re.search(r"\bapply\b|application|careers|apptrkr", target, re.I):
            apply_url = target
            break
    return JobDraft(
        source="air",
        source_job_id=air_job_id(url),
        source_url=canonical_air_url(url),
        title=title,
        institution=institution,
        location=location,
        city=city,
        state=state,
        salary=salary,
        application_due_date=normalize_date(due, now) or due,
        apply_url=apply_url,
        raw_description=raw,
        normalized_description=normalized,
        description_status="Complete",
    )
