# Seniority / Eligibility Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Label jobs a BS new grad does not qualify for, hide them by default, and let the user toggle each category back into view.

**Architecture:** A pure rules module (`backend/app/seniority.py`) returns flags with evidence. The database stores them as JSON on `jobs` with a rules version, refreshes them on save and at startup, and filters them out via a `hide` API parameter. The dashboard adds a "Hide roles" chip row and per-row badges.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (json1), React + TypeScript (Vite), pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-28-seniority-labels-design.md`

## Global Constraints

- Labels, exact strings: `Director`, `Postdoc / PhD`, `Leadership`, `Senior / Lead`, `Level III+`, `5+ years`, `Master's required`.
- Never flag on "preferred" wording; never delete jobs or change `application_status`.
- Regex windows bounded to ≤80 chars (no unbounded `.*` across descriptions).
- Sponsorship classifier and its five statuses are untouched.
- Python: 4-space, `snake_case`; TS: 2-space, `camelCase`.

## Review Focus

- Jobs saved before this change (no `seniority_version`) must be labelled at startup, including ones with no description → Task 2 startup test.
- Words containing a keyword ("Leadership Program Analyst", "Directory Services Engineer", "Management Information Systems", "Data Steward IV" vs "Help Desk Specialist I") must not misfire → Task 1 negatives.
- "Bachelor's with 5 years or Master's with 3" and "Master's preferred" must not flag Master's → Task 1.
- Empty `hide` shows everything; unknown hide label is ignored, not an error → Task 2 API test.
- Toggling a chip must reset to page 1 (pagination just added) → Task 3 browser test (via existing `update()`).

---

### Task 1: Rules module

**Files:**
- Create: `backend/app/seniority.py`
- Test: `backend/tests/test_seniority.py`

**Interfaces:**
- Produces: `LABELS: tuple[str, ...]` (order above); `VERSION: str = "seniority-1"`; `flag_role(title: str | None, description: str | None) -> list[dict]` returning `[{"label": str, "evidence": str}]`, one entry per label at most, in `LABELS` order; evidence is the exact matched substring.

- [ ] **Step 1: Write failing parametrized tests** — positives per label (`"Assistant Director of IT"`→Director; `"Postdoctoral Researcher"`→Postdoc / PhD; description `"PhD required"`→Postdoc / PhD; `"IT Manager"`, `"Chief Data Officer"`, `"Help Desk Supervisor"`, `"Head of Analytics"`→Leadership; `"Sr. Data Analyst"`, `"Data Engineer Lead"`, `"Principal Data Architect"`→Senior / Lead; `"Applications Programmer V"`, `"BI Analyst IV - R109565"`→Level III+; description `"Minimum of 5 years of experience"`, `"seven (7) years of experience required"`→5+ years; `"Master's degree required"`→Master's required). Negatives: `"Software Developer I"`, `"Directory Services Engineer"`, `"Leadership Program Analyst"`, `"Management Information Systems Analyst"`, `"5 years of experience preferred"`, `"3 years of experience required"`, `"Master's degree preferred"`, `"Bachelor's degree and 5 years, or Master's degree required and 3 years"` must not yield Master's. Assert evidence is a substring of input.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_seniority.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement** title regexes per spec table; description rules split into sentences first, then search each sentence (bounds the window), skipping sentences containing `preferred|desired|a plus`; Master's also skipped when sentence has `bachelor|equivalent experience`. Years: digits 5–30 or words five–twenty.
- [ ] **Step 4: Run** same command → PASS.
- [ ] **Step 5: Commit** `Add seniority eligibility rules`.

### Task 2: Storage, startup relabel, API filter

**Files:**
- Modify: `backend/app/database.py` (`_migrate_columns`, `upsert_job`, `jobs`, new `relabel_seniority`)
- Modify: `backend/app/main.py` (`relabel_on_startup`, `/api/jobs` `hide` param)
- Test: `backend/tests/test_seniority_api.py`

**Interfaces:**
- Consumes: `flag_role`, `VERSION` from Task 1.
- Produces: columns `jobs.seniority_flags TEXT NOT NULL DEFAULT '[]'`, `jobs.seniority_version TEXT`; `Database.relabel_seniority(only_outdated: bool = False) -> int`; `Database.jobs(..., hide: str = "")`; `/api/jobs?hide=<comma labels>`; each item has `seniority_flags: list[dict]`.

- [ ] **Step 1: Failing tests** — (a) upsert `"Senior Data Analyst"` → item `seniority_flags == [{"label":"Senior / Lead","evidence":"Senior"}]`; (b) `hide=Senior / Lead` excludes it, `hide=` includes it, `hide=Bogus` includes it; (c) row inserted with `seniority_version` NULL and no description gets labelled by `relabel_seniority(only_outdated=True)` and returns count 1; second call returns 0; (d) `reanalyze()` keeps flags for description-based labels after description changes.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add columns in `_migrate_columns`; private `_store_flags(job_id)` reads current title + normalized_description from row and writes flags + version; call at end of `upsert_job` and per row in `reanalyze`; `relabel_seniority` selects rows where version differs (or all). Filter clause: `NOT EXISTS (SELECT 1 FROM json_each(j.seniority_flags) f WHERE json_extract(f.value,'$.label') IN (...))`. Decode `seniority_flags` JSON in response. Call `db.relabel_seniority(only_outdated=True)` inside `relabel_on_startup`'s try.
- [ ] **Step 4: Run** full `.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `Store seniority labels and filter them in the jobs API`.

### Task 3: Dashboard chips and badges

**Files:**
- Modify: `frontend/src/main.tsx`, `frontend/src/index.css`
- Test: `backend/tests/test_dashboard_pagination.py` (add browser test)

**Interfaces:**
- Consumes: `hide` param and `seniority_flags` from Task 2.

- [ ] **Step 1: Failing browser test** `test_dashboard_hides_flagged_roles_until_toggled`: seed `"Software Engineer"` + `"Director of IT"` (posted today); page shows 1 role; click chip `Director` → 2 roles and row shows badge text `Director`.
- [ ] **Step 2: Build + run** → FAIL.
- [ ] **Step 3: Implement** — `Job.seniority_flags: { label: string; evidence: string }[]`; `seniorityLabels` const mirroring `LABELS`; both boards' `defaultFilters` get `hide: seniorityLabels.join(',')`; chip row "Hide roles" (pressed = hidden) with "Show all" (sets `''`), reusing `.query-filter`; badge per flag under title with `title={evidence}` tooltip, class `signal signal-caution signal-badge`.
- [ ] **Step 4: Typecheck, build, run** `npx tsc --noEmit -p . && npm run build` then full pytest → PASS.
- [ ] **Step 5: Commit** `Hide senior and PhD roles by default with toggles`.
