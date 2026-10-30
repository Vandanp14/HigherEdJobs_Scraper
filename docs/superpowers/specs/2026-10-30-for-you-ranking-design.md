# "For you" Ranked Tab — Design

Date: 2026-10-30 · Status: approved

## Intent

The user is an F-1 international student finishing a BS in Computer Science (SUNY Oswego,
December 2026) and applying as a new grad. The dashboard today finds jobs and filters them; it
does not say which saved job the user has the best real chance at. Add a **For you** tab that
ranks every saved job against the user's master resume (`data/resume.json`) and shows why each
job sits where it does. AIR Career Center listings are out of scope. The goal is to answer, at a glance: "of everything here, which recent
job is closest to ideal for me?"

The tool suggests; it does not hide. Every job that is saved today stays reachable in the tab.
Poor fits sink and are dimmed, never removed.

## Goals

- Score every saved HigherEdJobs job 0–100 for fit against `data/resume.json`, with stored reasons.
- Rank the For you tab by fit, adjusted for posting age (rule below).
- Show the reasons inline (tags) and in full (side panel), including the exact sponsorship
  sentence and which resume skills matched or are missing.
- Make every part filterable so the user can re-slice the ranking.
- Keep the existing HigherEdJobs and AIR tabs exactly as they are.
- Stay free, offline, and add no heavy dependencies.

## Non-goals

- No AI APIs and no local ML models (ruled out: must be free; no extra storage). A local
  embedding model may be considered later only if the keyword matcher proves inadequate.
- No change to the sponsorship classifier or its five statuses.
- No change to scrape-time filtering: off-field jobs (chemistry, faculty, teaching) are still
  dropped before saving by `scraper.py:91`, as today.
- No resume editing UI; the user edits `data/resume.json` directly.
- Does not apply to jobs or judge legal eligibility.

## Anti-goals (failure even if it works)

- A job disappears from For you because of a low score, a seniority flag, or a sponsorship
  status.
- A score the panel cannot explain. Every point must trace to a named skill, flag, sponsorship
  status, or age.
- "No Mention Found" treated as sponsorship granted.
- The resume gets committed (`data/` is gitignored; keep it that way) or sent anywhere.

## Constraints

- Free, local, offline. Python standard library plus existing dependencies only.
- Follows repo patterns: rules module with a `VERSION`, results stored on the job, refreshed on
  save and at startup (as `classifier.py` and `seniority.py` do).
- PRODUCT.md interface direction (palette `#09090b` / `#18181b` / `#27272a`, `#fafafa` /
  `#a1a1aa`, muted green/amber for sponsorship signals, system fonts, tabular numbers).
- AGENTS.md API contract rules: any total shown must be reachable (pager), and tests seed more
  rows than the page size.
- 1,834 saved jobs today, all with descriptions; scoring all of them must take seconds.

## Approaches

- **A. Skill matcher from the resume (chosen).** Build a skill vocabulary from the resume plus a
  synonym list and a common-tech vocabulary; detect which skills each description asks for,
  weight required over preferred, subtract for declined skills, weight skills the user has used
  in projects or work above listed-only ones. Free, instant, fully explainable, matches how
  the classifier and seniority rules work. Weakness: only knows what the vocabulary knows.
- B. Local embedding model (`sentence-transformers`). Better at loose wording, but adds PyTorch
  (1–2 GB), produces unexplainable scores, and drifts with model versions. Rejected for now:
  storage and explainability.
- C. A plus B as a bonus. Rejected for now for B's reasons.

The user chose A, with B as a possible later addition if A does not work well enough.

## What the user decided

### Fit score (0–100)

Fit is about the user's real chances. Resume match dominates: a data or analyst role that
matches the resume well ranks as high as a software or web role.

Inputs, in order of weight:

1. **Skills match** (dominant). Overlap between the job's asked-for skills and the resume.
   Required-section skills count more than preferred-section skills. A skill appearing in
   `skill_check.declined` that the job requires is an explicit gap and lowers the score.
   Skills backed by `projects[].technologies` or work highlights count more than ones only in
   `skills[].keywords`.
2. **Sponsorship workability** (from the existing `sponsorship_analysis.status`).
   "Sponsorship Possible" helps; "No Mention Found" is neutral-to-slightly-below and never
   counts as a yes; "Unsure - Review" is a small penalty; "Likely No Sponsorship" a large
   penalty; "Not Worth It" (explicit denial) caps fit at a low ceiling (about 15), so it loses
   to any clean match of similar age. There are no separate bands: one age-adjusted number
   orders the list, so the panel's "ranked as" value always agrees with row order (Claude's
   call). None remove the job.
3. **Seniority flags** (existing `jobs.seniority_flags`). Each flag (Senior / Lead, 5+ years,
   Master's required, etc.) lowers the score. In For you nothing is hidden by these flags.
4. **Role type** (small). Typical CS roles (software, web, data, systems) score slightly above
   help desk / support / admin IT roles, but never enough to outrank a clearly better resume
   match.

### Ranking rule (fit adjusted for age)

Age is measured from `posted_date`, falling back to the date in `first_seen_at` (same fallback
the existing "newest" sort uses).

- **Days 0–14:** fit decides. A small nudge toward newer jobs breaks near-ties, but a much
  better match always beats a newer one. Confirmed examples: fit 90 posted yesterday ranks above
  fit 60 posted today; fit 90 posted 13 days ago ranks above fit 60 posted today.
- **After day 14:** age takes charge. Scores fade steeply, so older jobs only rank above recent
  ones when the recent ones are poor matches.
- **Older than 30 days or undated:** below every job from the last 30 days.

(Early in the conversation the user said a fit-90 job from 14 days ago should rank below a
fit-60 job from today; they later settled on "within the last two weeks, much better match
always wins." The later answer governs. Day 14 is inside the fit-decides window.)

Acceptance cases the ordering must satisfy:

| A | B | Expected |
|---|---|---|
| fit 90, 1 day | fit 60, 0 days | A above B |
| fit 90, 13 days | fit 60, 0 days | A above B |
| fit 70, 3 days | fit 70, 0 days | B above A (newer wins a tie) |
| fit 90, 30 days | fit 60, 0 days | B above A |
| fit 95, 45 days | fit 20, 29 days | B above A |
| fit 90, 20 days | fit 30, 2 days | A above B (recent one is a poor match) |

### The For you tab

- A new tab, first in the tab row, beside **HigherEdJobs** and **AIR**. Those two tabs keep
  their current behavior, filters, and seniority hiding unchanged.
- Covers HigherEdJobs listings only. AIR listings are excluded from For you (the user finds
  them straightforward to review on the AIR tab) and are not scored.
- **Layout:** today's dense table, ranked, with columns Fit (number + small meter), Role
  (title, institution, location), Why (up to 3 reason tags + "+N"). Matched skills in green,
  gaps (missing/declined) in muted red, seniority flags in amber. Low-fit rows dimmed.
- **Side panel, always open by default**, docked right, sticky while scrolling. Shows the
  selected job: fit number, the three parts (required skills matched N / M, sponsorship status,
  seniority flags), matched skills, missing skills, the exact sponsorship evidence sentence (or
  "No sponsorship wording found. Not a guarantee; check before applying."), the age effect
  ("fit 90, posted 14 days ago, ranked as 72" or equivalent), and Open listing / Mark applied.
- Top row is selected on load so the panel is never empty.
- **Collapse:** a collapse control and `Esc` hide the panel; clicking a row or moving with the
  keyboard brings it back. Open/closed state is remembered across visits.
- **Keyboard:** `j`/`k` and `↑`/`↓` move the selection (panel follows), `Enter` opens the
  listing, `a` marks applied, `Esc` collapses the panel.
- On narrow screens the panel stacks below the table.
- Mockup: `.superpowers/brainstorm/93231-1793383284/content/for-you-hybrid.html`.

### Filters and sorting (everything filterable)

- Chips: posted window (7 / 14 / 30 days / any time), sponsorship status, seniority flags (as
  include/exclude filters, all included by default), minimum fit, application
  status (so Skipped jobs stay reachable here; Skipped excluded by default as on other tabs),
  Hide applied.
- Sort switch: **Best fit (age-weighted)** default, **Newest**, **Fit only** (ignores age).
- Defaults show everything (any time, all statuses, all flags).

## Builder's calls (Claude's proposals, flagged for review)

- **Module:** new `backend/app/fit.py` with `VERSION`, a pure `score_job(...)` function returning
  `{score, matched, missing, declined_hits, parts}`; resume loading separate from scoring so tests
  pass a resume dict directly.
- **Storage:** `jobs.fit_score INTEGER`, `jobs.fit_details TEXT NOT NULL DEFAULT '{}'` (JSON
  breakdown), `jobs.fit_version TEXT`. Version string = module `VERSION` + short hash of the
  resume file contents, so editing the resume or the rules rescores at startup (same pattern as
  `relabel_seniority(only_outdated=True)`). Scored in `upsert_job` and after `reanalyze`, after
  sponsorship and seniority are stored, since fit reads both.
- **Age adjustment at query time**, not stored, because it changes daily. Implement as a
  deterministic SQLite function (like `cs_title`) or a SQL expression; pick whichever keeps
  pagination correct. Exact curve is the builder's choice provided it satisfies the acceptance
  table above.
- **Resume path:** new setting `HEJ_RESUME` (default `data/resume.json`) in `config.py` and
  `.env.example`. If the file is missing or invalid, jobs are left unscored, the For you tab
  shows an explicit empty state naming the path to add, and other tabs are unaffected.
- **Vocabulary:** resume `skills[].keywords`, `projects[].technologies`, and terms in
  `skill_check.declined`, plus a checked-in synonym map (JS↔JavaScript, Postgres↔PostgreSQL,
  k8s↔Kubernetes, …) and a checked-in common-tech list so the matcher can see skills a job asks
  for that the resume lacks (needed for "missing"). Long descriptive resume phrases (more than
  about three words, e.g. "Accessibility-compliant interface development") are not matched
  literally. Word-boundary matching; case-insensitive except short acronyms.
- **Required vs preferred:** detect by section headings ("Required/Minimum Qualifications" vs
  "Preferred/Desired") and, inside sentences, reuse the soft-wording idea from `seniority.py`
  (`prefer`, `desired`, `a plus`). Unsectioned text counts as required.
- **API:** extend `/api/jobs` rather than adding an endpoint: `sort=fit` (age-weighted) and
  `sort=fit_only`, and `min_fit`; the For you tab always sends `source=higheredjobs`. Return `fit_score`, `fit_details`, and
  the age-adjusted rank value per item. The frontend must send every new parameter it relies
  on. Keep the existing off-field title clause and the default exclusion of "Skipped" jobs.
- **Exact weights** (skills vs sponsorship vs seniority vs role type) are the builder's, tuned
  against the user's real 1,834 jobs. The plan pauses after backend scoring and before the
  frontend: show the user the top 20 and bottom 10, tune weights on their feedback, then
  continue.
- **Panel state** persists in `localStorage`, wrapped in try/catch.
- **Tests:** unit tests for skill extraction (synonyms, required vs preferred, declined gaps,
  project-backed weighting, no-description jobs), every row of the acceptance table, rescore on
  resume change, missing-resume empty state, API sort and filters, and a browser test that seeds
  51+ jobs, ranks them in For you, moves with `j`/`k`, collapses the panel, and reaches the job
  past the page limit.

## Left to the builder

- Synonym and common-tech list contents.
- Score curve, weights, and the age-fade curve within the stated rules.
- Component structure in `frontend/src/main.tsx` (may split files).
- Visual details within PRODUCT.md direction and the mockup.
