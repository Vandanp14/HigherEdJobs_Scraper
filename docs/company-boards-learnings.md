# Company boards: what we learned

Company boards found early-career software jobs on public ATS boards instead of through Google
searches. It was built here (Nov 2026), run against real boards, then removed from this dashboard.
The job pipeline moves to `ATS_Resume_Tailor_Agent`, driven by the SimplifyJobs new-grad list.

The full implementation (code, tests, fixtures, spec and plan) is on the branch
[`archive/company-boards-crawler`](https://github.com/Vandanp14/HigherEdJobs_Scraper/tree/archive/company-boards-crawler).
Useful files there:

- `docs/superpowers/specs/2026-11-05-company-boards-design.md`: design and the decisions behind it
- `backend/app/sources/`: one reader per ATS, URL parsing, discovery, the runner
- `backend/app/early_career.py`: the 18 search queries turned into title, description and location rules
- `backend/tests/fixtures/boards/`: trimmed real responses from each ATS

## Why not Google

- Google's Custom Search JSON API is closed to new customers and shuts down January 1, 2027.
- Paid SERP APIs (Serper, SerpApi, Brave) work, but cost money every month.
- Automating google.com breaks its terms and gets CAPTCHAs. We chose not to build anything that
  solves CAPTCHAs, spoofs browsers or rotates proxies.

## Public job APIs (no key needed)

| ATS | List endpoint | Notes |
|---|---|---|
| Greenhouse | `GET boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | One request returns every job with its description. `content` is HTML escaped once (`&lt;p&gt;`), so unescape it before parsing. `absolute_url` can be a shared company page, so build `job-boards.greenhouse.io/{slug}/jobs/{id}` for a unique link. |
| Lever | `GET api.lever.co/v0/postings/{slug}?mode=json` | A bare JSON array. The full text is `description` plus each `lists[]` section plus `additional`. `createdAt` is epoch milliseconds. |
| Ashby | `GET api.ashbyhq.com/posting-api/job-board/{slug}` | Skip `isListed: false`. Extra places are in `secondaryLocations`. |
| SmartRecruiters | `GET api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset=N` | The list has no descriptions. Detail is `.../postings/{id}`, with text in `jobAd.sections`. An unknown company answers 200 with empty `content`, not 404. |
| Workday (unofficial) | `POST {tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":"..."}` | Search on the server per term. `total` is only right on the first page: later pages report 0. Some entries have only `bulletFields` and no `externalPath`, so skip them. Detail is `GET .../wday/cxs/{tenant}/{site}{externalPath}`. `postedOn` is relative text such as "Posted 30+ Days Ago". |

- Job IDs repeat across companies, especially Workday paths, so prefix every ID with its board
  (`{slug}:{id}`, or `{tenant}/{site}:{path}` for Workday).
- Never use URLs from a board response without checking they are `http(s)`. A `javascript:` URL
  would run when someone clicks the link.
- Most of these APIs are fine at one request per second per ATS. Different ATSes can run side by
  side.

## Finding companies

- Common Crawl's URL index (`index.commoncrawl.org`) is free, but often answers 504. On 2026-11-10
  one refresh got nothing from it, and the next got thousands of companies. Responses can also end
  mid-line, so read each line on its own and skip bad ones.
- Paths from Common Crawl such as `/robots.txt`, `/en` and `/es` were wrongly read as Workday site
  names, which created fake companies. Reject file names and bare language codes.
- The SimplifyJobs `listings.json` is the better source. It is one request (about 13 MB) at
  `raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json`.
  Fields include `company_name, title, url, locations, date_posted` (epoch seconds),
  `active, is_visible, category, sponsorship`. It is maintained daily by Simplify and Coder Quad,
  plus community issues. Its `sponsorship` field is almost always "Other", so it says little about
  sponsorship.

## Results from real runs (2026-11-10)

- Company list: 2,661 companies from SimplifyJobs alone, then 5,058 with Common Crawl working.
- A partial full run checked 3,293 companies, read 213,477 listed jobs and kept 222 early-career
  ones. Of the 359 failures, 353 were `404` boards (moved or closed). Only 2 Workday tenants blocked
  us.
- Workday is the slow part: 1,263+ tenants, several searches each, and detail requests. A full run
  takes many hours.
- Of 235 saved jobs, 147 were also on the SimplifyJobs list. In the last 7 days it was 7 of 13, and
  all 6 extra recent jobs came from one company. Simplify covers most of what a full crawl finds, in
  one request instead of hours.
- In one week Simplify listed 97 new software postings. 59% were on Workday, Ashby, Greenhouse,
  SmartRecruiters or Lever. The rest were company career sites (Amazon, Microsoft, Cisco, iCIMS,
  Workable and others), which need a general page reader or a pasted description.
- Some Simplify links open an application page with no description (Lever/Workday `/apply`, Ashby
  `/application`, Greenhouse `job_app?token=`). For known ATSes, take the job ID from the link and
  use the API. Elsewhere, mark the job "no description at link" rather than reading a form.

## Rules that worked

- Keep a job only if it is a software role, not senior, staff, principal, lead, manager, intern or
  level II and above, and early-career by title (new grad, junior, entry level, associate,
  "Engineer I") or by description (new grad, 2026/2027 graduate, 0-2 years). Write `\b0` so
  "10-20 years" never matches.
- Keep US, remote or unknown locations. Reject only when somewhere outside the US is named and
  nothing in the US is.
- Sponsorship wording never removes a job. It is labelled, and missing wording never means
  eligible.
- A failed fetch never closes jobs. Close a job only after a complete read of its board, and keep
  the row.
