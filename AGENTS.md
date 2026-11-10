# Repository Guidelines

## Project Structure & Module Organization

`HigherEdJobs_PRD.md` defines the HigherEdJobs scraper and sponsorship review dashboard; read its V1 scope and acceptance criteria before implementing changes. Later scope is specified in `docs/superpowers/specs/` (for example Company boards, `2026-11-05-company-boards-design.md`). The backend lives in `backend/app` (FastAPI, Playwright, SQLite; Company boards sources in `backend/app/sources/`), tests in `backend/tests`, the React dashboard in `frontend/`, and helper scripts in `scripts/`. See `README.md` for setup.

The PRD recommends React/TypeScript, FastAPI/Python, Playwright, and SQLite; these are recommendations, not installed dependencies. When scaffolding, keep frontend, backend, scraping, parsing, classification, and persistence responsibilities separate. Document the chosen directory layout and setup in a README.

## Build, Test, and Development Commands

Commands and dependencies are documented in `README.md`: `./run.sh`, `./view.sh`, `.venv/bin/pytest`, and `npm run build` in `frontend/`.

The PRD suggests this command for interactive site discovery once Playwright is available:

```bash
npx playwright codegen https://www.higheredjobs.com/search/advanced.cfm
```

Clean up recorded selectors before production use; prefer stable IDs, names, labels, and accessible roles over positional selectors.

## Coding Style & Naming Conventions

For new code, use four-space indentation and `snake_case` for Python functions/modules; use two-space indentation, `camelCase` functions, and `PascalCase` React components in TypeScript. Keep database field names consistent with the PRD, such as `raw_description` and `classifier_version`. No formatter or linter is configured; establish shared configuration with the initial scaffold.

## Testing Guidelines

No testing framework or coverage threshold exists yet. Add deterministic tests alongside implementation, using saved HTML fixtures for parser tests. Suggested naming: `test_*.py` for Python and `*.test.ts` for TypeScript.

Cover pagination, cross-query deduplication, matched-group merging, date normalization, all five sponsorship statuses, evidence extraction, and preservation of application status across reruns. Verify failed page loads remain distinguishable from descriptions with no sponsorship mention. Document how to run the selected test suite.

### API Contracts & Volume

- Every API parameter that limits or splits results (`page`, `per_page`, filters) must have a frontend caller that sends it. When reviewing an endpoint or the code that calls it, check both sides of the contract, not only the diff.
- Any screen that shows a total must let the user reach every item in that total. If `items.length < total`, the UI needs a pager or "load more".
- Seed tests with more rows than every limit (for example, 51+ jobs for a 50-row page) and assert the user can reach the item past the limit. `backend/tests/test_dashboard_pagination.py` does this through the built dashboard in a browser. Run `npm run build` in `frontend/` first, or the browser test is skipped.
- Before calling a dashboard change done, use it like a user: apply filters, scroll to the end, and confirm the rows match the count.

## Commit & Pull Request Guidelines

No Git history is available to establish existing conventions. Use concise, imperative commit subjects, such as `Add sponsorship classifier fixtures`. Keep changes focused.

PRs should explain behavior changes, reference relevant PRD sections or issues, report validation performed, and include screenshots for dashboard changes. Call out schema and configuration changes explicitly.

## Scraping & Data Integrity

On HigherEdJobs, modify only the Keyword search field and the Category (`JobCat`) filter. Company boards read public ATS job data (Greenhouse, Lever, Ashby, Workday, SmartRecruiters) found from free public company lists; no search engine is scraped. On `403`, `429` or a challenge page, back off and stop requesting that host for the run; never bypass a block (no CAPTCHA solving, fingerprint spoofing or proxy rotation). Use conservative request rates, caching, and applicable access restrictions. Preserve raw descriptions, exact classification evidence, original links, and historical records. Never interpret missing sponsorship language as guaranteed eligibility.
