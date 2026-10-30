# For you Ranked Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a For you tab that ranks every saved HigherEdJobs job by fit against `data/resume.json`, adjusted for posting age, with reasons in the row and a side panel.

**Architecture:** A pure rules module `backend/app/fit.py` scores a job from its title, description, sponsorship status, and seniority flags against a resume-derived skill vocabulary. Scores are stored on `jobs` with a version that includes a resume hash, refreshed on save, after reanalyze, and at startup. Age adjustment runs at query time through a registered SQLite function so paging stays correct. The frontend adds a third board, `foryou`, in new component files.

**Tech Stack:** Python 3.11 standard library, FastAPI, SQLite, React/TypeScript/Vite, pytest, Playwright (browser test).

**Spec:** `docs/superpowers/specs/2026-10-30-for-you-ranking-design.md`

## Global Constraints

- Free and offline: no new Python or npm dependencies, no network calls, no ML models.
- `data/resume.json` is personal: never commit it, never copy its contents into tests or fixtures; tests use a small synthetic resume dict.
- HigherEdJobs only: AIR jobs are not scored (`fit_score` stays NULL) and never appear in For you.
- Nothing hidden by score: low fit, seniority flags, and "Not Worth It" only lower rank. The For you defaults show every HigherEdJobs job except Skipped ones.
- "No Mention Found" never counts as sponsorship granted.
- Existing HigherEdJobs and AIR tabs keep their current behavior and defaults, including the default seniority `hide`.
- Every score is explainable: `fit_details` names each matched skill, missing skill, declined gap, seniority flag, sponsorship status, and role-type reason that moved the number.
- PRODUCT.md palette and type: `#09090b` canvas, `#18181b` / `#27272a` surfaces, `#fafafa` / `#a1a1aa` text, muted green/amber for signals, system fonts, `tabular-nums` for numbers.
- AGENTS.md: any shown total must be reachable through the pager; tests seed more than 50 rows.
- Python: four-space indent, `snake_case`. TypeScript: two-space indent, `camelCase` functions, `PascalCase` components.

## Review Focus

- **Resume file missing or invalid JSON:** the app still starts, other tabs work, all HigherEdJobs `fit_score` stay NULL, and For you shows "Add your resume at data/resume.json to rank jobs." Tested in Task 3 and Task 6.
- **Short skill names inside other words or symbols:** `Go`, `C`, `R`, `SQL` must not match "go to", "C++", "C#", "R&D", or "NoSQL" as the wrong skill. Tested in Task 1.
- **Jobs with no captured description (Pending/Failed):** still scored from the title, with reason "Description not captured; skills not checked", never a crash, never NULL. Tested in Task 2.
- **Resume edited after scoring:** next startup rescores every job because the resume hash changed. Tested in Task 3.
- **Rows past the first page in For you:** ordering stays stable across pages (tie-break on `j.id`), and the 51st job is reachable in the browser. Tested in Task 4 and Task 7.

---

### Task 1: Skill vocabulary and extraction

**Files:**
- Create: `backend/app/skills_vocab.py`
- Create: `backend/app/fit.py` (extraction half)
- Test: `backend/tests/test_fit_skills.py`

**Interfaces:**
- Produces:
  - `skills_vocab.SYNONYMS: dict[str, tuple[str, ...]]` maps a canonical skill to its alternate spellings (e.g. `"JavaScript": ("JS", "ECMAScript")`, `"PostgreSQL": ("Postgres",)`, `"Kubernetes": ("k8s",)`).
  - `skills_vocab.COMMON_SKILLS: tuple[str, ...]` holds about 150 common tech skills seen in university IT postings (SAS, Argos, Banner, PeopleSoft, Workday, Salesforce, Slate, Angular, Ruby, .NET, C#, PHP, …). It lets "missing" work for skills the resume lacks.
  - `fit.Resume` dataclass with fields `skills: frozenset[str]` (canonical names the user has), `backed: frozenset[str]` (subset found in `projects[].technologies` or `work[].highlights`), `declined: frozenset[str]` (from `skill_check.declined`), and `digest: str` (first 12 hex chars of the file's sha256, or `"dict"` when built from a dict).
  - `fit.load_resume(path: Path) -> Resume | None` returns None when the file is missing or the JSON is invalid. It never raises.
  - `fit.resume_from_dict(data: dict) -> Resume`
  - `fit.asked_skills(description: str) -> dict[str, str]` maps canonical skill to `"required"` or `"preferred"`. The vocabulary is module-level COMMON_SKILLS plus SYNONYMS keys.
  - `fit.asked_skills_for(description: str, resume: Resume) -> dict[str, str]`: same, with the resume's own skills and declined terms added to the vocabulary.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_fit_skills.py`, using a synthetic `RESUME = {"skills": [{"name": "Languages", "keywords": ["Python", "JavaScript", "SQL", "Go", "C", "Accessibility-compliant interface development"]}], "projects": [{"technologies": ["Python", "React"]}], "work": [{"highlights": ["Built ETL pipelines in SQL"]}], "skill_check": {"declined": ["Salesforce", "Slate"]}}`:

```python
def test_resume_collects_skills_backed_and_declined():
    resume = resume_from_dict(RESUME)
    assert {"Python", "JavaScript", "SQL", "React"} <= resume.skills
    assert {"Python", "React", "SQL"} <= resume.backed
    assert resume.declined == {"Salesforce", "Slate"}
    assert "Accessibility-compliant interface development" not in resume.skills  # >3 words skipped

def test_synonyms_map_to_canonical():
    assert asked_skills("Experience with JS and Postgres required.") == {"JavaScript": "required", "PostgreSQL": "required"}

def test_short_names_do_not_match_inside_other_tokens():
    asked = asked_skills_for("Familiar with C++ and C#, R&D, NoSQL stores. Go to the office.", resume_from_dict(RESUME))
    assert "C" not in asked and "Go" not in asked and "SQL" not in asked

def test_preferred_section_and_soft_sentences():
    text = "Required Qualifications\nPython and SQL.\nPreferred Qualifications\nReact.\nTableau experience is a plus."
    assert asked_skills(text) == {"Python": "required", "SQL": "required", "React": "preferred", "Tableau": "preferred"}

def test_unsectioned_text_counts_as_required():
    assert asked_skills("You will build tools in Python.") == {"Python": "required"}

def test_load_resume_missing_or_invalid(tmp_path):
    assert load_resume(tmp_path / "nope.json") is None
    (tmp_path / "bad.json").write_text("{not json")
    assert load_resume(tmp_path / "bad.json") is None
```

- [ ] **Step 2: Run** `pytest backend/tests/test_fit_skills.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement `skills_vocab.py` and the extraction half of `fit.py`.** Match with one compiled alternation per vocabulary, longest names first. Use lookarounds `(?<![\w+#.])` and `(?![\w+#])` so `C` doesn't match `C++`/`C#` and `SQL` doesn't match `NoSQL`. Names of 2 characters or fewer, plus `Go` and `R`, match case-sensitively; all others are case-insensitive. Section state comes from heading lines matching `required|minimum|basic` and `preferred|desired|desirable|additional`. A sentence with `prefer|desir|a plus|nice to have` marks its skills preferred. When a skill appears in both, required wins. Resume names longer than 3 words are dropped.
- [ ] **Step 4: Run** `pytest backend/tests/test_fit_skills.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git add backend/app/skills_vocab.py backend/app/fit.py backend/tests/test_fit_skills.py && git commit -m "Extract asked-for skills from job descriptions"`

### Task 2: Fit score

**Files:**
- Modify: `backend/app/fit.py`
- Test: `backend/tests/test_fit_score.py`

**Interfaces:**
- Consumes: Task 1 `Resume`, `asked_skills_for`.
- Produces:
  - `fit.VERSION = "fit-1"`
  - `fit.score_job(title: str | None, description: str | None, sponsorship_status: str | None, seniority_flags: list[dict], resume: Resume) -> dict` returns `{"score": int 0–100, "matched": [str], "missing": [str], "declined": [str], "required_total": int, "required_matched": int, "parts": {"skills": float, "role": int, "sponsorship": int, "seniority": int}, "reasons": [str]}`.
  - `fit.version_for(resume: Resume) -> str` returns `f"{VERSION}:{resume.digest}"`.

Starting weights (tuned in Task 5; the tests pin only ordering and caps):
- **skills, 0–70:** `70 × Σw(matched) / Σw(asked)`. Required weighs 1.0 and preferred 0.5. A matched skill not in `resume.backed` counts ×0.7. Each declined skill the job requires subtracts 5, up to −15. When the job asks for no known skills: 30, reason "No listed skills recognised". When there's no description: 20, reason "Description not captured; skills not checked".
- **role, 0–10:** 10 when the title matches software, developer, programmer, engineer, web, data, analyst, database, systems, or cloud. 5 for other CS titles (`relevance.is_cs_title`). Otherwise 0.
- **sponsorship:** Sponsorship Possible +20, No Mention Found +12, Unsure - Review +8, Likely No Sponsorship 0, None/Unavailable +10. **Not Worth It caps the final score at 15.**
- **seniority:** −12 per flag, up to −36.
- Final score is clamped to 0–100 and rounded to an int.

- [ ] **Step 1: Write the failing tests:**

```python
def test_better_skill_match_scores_higher(): ...  # same title/status; description asking Python+SQL vs Angular+Ruby → first > second
def test_required_outweighs_preferred(): ...      # Python required + Tableau preferred, resume has only Tableau < resume has only Python
def test_declined_required_skill_is_a_gap(): ...  # "Salesforce required" → "Salesforce" in result["declined"], score lower than same text without it
def test_backed_skills_count_more(): ...          # React (backed) vs JavaScript (listed only), each sole asked skill → React score higher
def test_not_worth_it_caps_at_15(): ...           # perfect skill match + "Not Worth It" → score <= 15, job still gets a score
def test_no_mention_is_not_a_yes(): ...           # identical job: "Sponsorship Possible" > "No Mention Found"
def test_seniority_flags_lower_score(): ...       # one flag vs none → lower by 12 (before clamping)
def test_data_role_can_beat_software_role(): ...  # data analyst with strong match > software engineer with weak match
def test_missing_description_still_scores(): ...  # description=None → int score, "Description not captured; skills not checked" in reasons
def test_version_includes_resume_digest(): ...    # version_for(resume) == f"fit-1:{resume.digest}"
```

- [ ] **Step 2: Run** `pytest backend/tests/test_fit_score.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `score_job` and `version_for`.** `reasons` gets one short phrase per part that moved the score, e.g. "9 of 11 required skills", "Sponsorship possible", "Senior / Lead".
- [ ] **Step 4: Run** `pytest backend/tests/test_fit_skills.py backend/tests/test_fit_score.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -am "Score job fit against the resume"` (add the new test file first).

### Task 3: Store and refresh fit scores

**Files:**
- Modify: `backend/app/config.py` (Settings), `.env.example`, `backend/app/database.py` (`__init__`, `_migrate_columns`, `upsert_job`, `reanalyze`, new `rescore_fit`), `backend/app/main.py` (startup)
- Test: `backend/tests/test_fit_storage.py`

**Interfaces:**
- Consumes: Task 1 `load_resume`, Task 2 `score_job` and `version_for`.
- Produces:
  - `Settings.resume: Path = ROOT / os.getenv("HEJ_RESUME", "data/resume.json")`. Add `HEJ_RESUME=data/resume.json` to `.env.example` with a comment that the file stays local.
  - `Database(path: Path, resume_path: Path | None = None)` loads the resume once into `self.resume: Resume | None`.
  - New columns in `jobs`: `fit_score INTEGER`, `fit_details TEXT NOT NULL DEFAULT '{}'`, `fit_version TEXT`.
  - `Database._store_fit(job_id: int)`: HigherEdJobs rows only, and only when `self.resume` is set. Runs after `_store_analysis` and `_store_flags` in both `upsert_job` and `reanalyze`.
  - `Database.rescore_fit(only_outdated: bool = False) -> int`: when `only_outdated`, it rescores rows where `fit_version` is NULL or differs from `version_for(self.resume)`. It returns 0 and does nothing when `self.resume` is None.
  - `main.py` builds `Database(settings.database, settings.resume)`, and `relabel_on_startup` also calls `db.rescore_fit(only_outdated=True)` inside its existing try.

- [ ] **Step 1: Write the failing tests:**

```python
def test_upsert_scores_higheredjobs_jobs(tmp_path): ...       # resume file written from synthetic dict → fit_score is int, fit_details JSON has "matched"
def test_air_jobs_are_not_scored(tmp_path): ...               # source="air" → fit_score IS NULL
def test_no_resume_leaves_scores_null(tmp_path): ...          # resume_path missing → fit_score NULL, upsert does not raise
def test_resume_change_rescores_on_startup(tmp_path): ...     # score, edit resume file, new Database(...) + rescore_fit(only_outdated=True) == 1, details changed
def test_reanalyze_refreshes_fit(tmp_path): ...               # set fit_version NULL, reanalyze() → fit_version == version_for(resume)
```

- [ ] **Step 2: Run** `pytest backend/tests/test_fit_storage.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the setting, migration columns (in the existing `migrations["jobs"]` dict), `_store_fit`, `rescore_fit`, the constructor parameter, and the startup call.
- [ ] **Step 4: Run** `pytest -q`. Expected: whole suite PASS, including the existing seniority and pagination tests.
- [ ] **Step 5: Commit** `git commit -m "Store fit scores and rescore when the resume changes"`

### Task 4: Age-weighted ranking in the jobs API

**Files:**
- Modify: `backend/app/fit.py` (add `rank_value`), `backend/app/database.py` (`__init__` registers the function; `jobs()`), `backend/app/main.py` (`/api/jobs` params)
- Test: `backend/tests/test_fit_ranking.py`

**Interfaces:**
- Produces:
  - `fit.rank_value(score: int | None, age_days: float | None) -> float`. NULL score sorts last, so return `-10_000`. Body (pinned, satisfies the spec's acceptance table):

```python
if age_days is None or age_days > 30:
    return score / 100 - 1000          # below every job from the last 30 days
if age_days <= 14:
    return score - 0.2 * age_days      # fit decides; newer wins near-ties
return score - 2.8 - 3 * (age_days - 14)  # after day 14 age takes charge (continuous at 14)
```

  - SQLite function `fit_rank(score, age_days)`, registered with `deterministic=True`. Age expression: `julianday(date('now','localtime')) - julianday(COALESCE(j.posted_date, substr(j.first_seen_at,1,10)))`.
  - `jobs()` gains `min_fit: int | None = None`. New `sort` values:
    - `fit` orders by `fit_rank(...) DESC, j.id DESC`
    - `fit_only` orders by `j.fit_score IS NULL, j.fit_score DESC, j.id DESC`
  - `application_status` gains:
    - `open`: excludes Skipped, applied regardless of `days`
    - `unapplied`: excludes Applied and Skipped
    - `any`: no status clause
  - Each item gains `fit_score`, `fit_details` (parsed dict), `rank_value` (float, rounded to 1 decimal), and `age_days` (int or null).
  - `/api/jobs` passes `min_fit` through.

- [ ] **Step 1: Write the failing tests:**

```python
@pytest.mark.parametrize("a, b", [((90, 1), (60, 0)), ((90, 13), (60, 0)), ((70, 0), (70, 3)),
                                  ((60, 0), (90, 30)), ((20, 29), (95, 45)), ((90, 20), (30, 2))])
def test_rank_value_acceptance_table(a, b):
    assert rank_value(*a) > rank_value(*b)

def test_null_score_sorts_last(): ...                     # rank_value(None, 0) < rank_value(0, 200)
def test_api_sort_fit_orders_by_rank(database): ...        # seed 3 jobs with fit_score/posted_date set via UPDATE; ?source=higheredjobs&sort=fit&days=all → expected order
def test_api_min_fit_filters(database): ...                # &min_fit=50 → only jobs with fit_score >= 50; total matches
def test_api_status_open_excludes_skipped_with_days_all(database): ...
def test_api_fit_paging_reaches_every_job(database): ...   # 61 jobs, equal scores → pages 1+2 with sort=fit return 61 distinct ids
def test_api_items_carry_fit_fields(database): ...         # fit_score, fit_details dict, rank_value, age_days present
```

- [ ] **Step 2: Run** `pytest backend/tests/test_fit_ranking.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `rank_value`, function registration, and the `jobs()` and `/api/jobs` changes.
- [ ] **Step 4: Run** `pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "Rank jobs by age-weighted fit in the jobs API"`

### Task 5: CHECKPOINT: weight review with the user

**Files:**
- Create: `scripts/fit-report.py`

- [ ] **Step 1: Write `scripts/fit-report.py`.** It opens `Settings().database`, runs `rescore_fit()`, and prints the top 20 and bottom 10 by `sort=fit` (days all, status open). Each line shows rank value, fit, age in days, title, institution, and `reasons`. It's read-only apart from the rescore.
- [ ] **Step 2: Run** `python scripts/fit-report.py` against the real database. Expected: 40 lines of output, with no exceptions.
- [ ] **Step 3: STOP.** Show the user the output. Adjust the weights in `score_job` from their feedback, rerun, and repeat until they approve. Bump `fit.VERSION` on every weight change so saved scores refresh. Tests from Task 2 must still pass.
- [ ] **Step 4: Commit** `git commit -m "Add fit report and tune fit weights"`

### Task 6: For you tab: table, filters, pager

**Files:**
- Create: `frontend/src/forYou.ts` (types, default filters, parameter building), `frontend/src/ForYouBoard.tsx` (table and filter chips)
- Modify: `frontend/src/main.tsx` (`Board` type, tab list, render `ForYouBoard` when `board === 'foryou'`), `frontend/src/index.css`
- Test: `backend/tests/test_for_you_dashboard.py` (browser, reuses `serve_dashboard` / `browser_page` from `test_dashboard_pagination.py`)

**Interfaces:**
- Consumes: the Task 4 API fields and params.
- Produces:
  - `Board = 'foryou' | 'higheredjobs' | 'air'`. The tab is first and labelled "For you"; default `board` is `'foryou'`.
  - `forYouDefaults: Filters = { query: '', sponsorship: '', hide: '', application_status: 'open', days: 'all', sort: 'fit', min_fit: '' }`. The request always sends `source=higheredjobs`.
  - `FitDetails` type mirrors `score_job`'s dict, and `Job` gains `fit_score`, `fit_details`, `rank_value`, `age_days`.
  - `ForYouBoard` props: `{ jobs: Job[]; total: number; page: number; pageCount: number; loading: boolean; selectedId: number | null; onSelect(id: number): void; filters: Filters; update(key: string, value: string): void; goToPage(n: number): void }`.

Table columns: **Fit** (number + 44px meter), **Role** (title, then institution · location), **Why** (up to 3 tags + "+N"). Tag order: matched skills (green), declined/missing (muted red), seniority flags (amber). Rows with fit below 40 get the class `low-fit` (opacity .55). Filters:
- posted window select: 7 / 14 / 30 / all
- sponsorship chips (reuse existing)
- seniority chips labelled "Exclude roles", none on by default
- minimum fit select: any / 40 / 60 / 80
- status select: Open work / Not applied / New / Opened / Applied / Skipped / All
- sort select: Best fit / Newest / Fit only

The pager reuses the existing pattern. Empty states:
- every `fit_score` null: "Add your resume at data/resume.json to rank jobs."
- no rows: "No jobs match these filters."

- [ ] **Step 1: Write the failing browser test** `test_for_you_ranks_and_pages`. Seed 61 HigherEdJobs jobs with a synthetic resume file passed to `Database(..., resume_path)`. Job "Python SQL Developer" with a description asking for Python and SQL must be the first row. "Page 1 of 2" is visible, and after Next the 61st job is reachable. Then switch to the HigherEdJobs tab and assert its default seniority hide still applies (seed one "Director of IT" and check it's absent there but present in For you).
- [ ] **Step 2: Run** `cd frontend && npm run build && cd .. && pytest backend/tests/test_for_you_dashboard.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `forYou.ts`, `ForYouBoard.tsx`, the `main.tsx` wiring, and the CSS.
- [ ] **Step 4: Run** the build and `pytest -q`. Expected: PASS, and the existing browser tests still pass.
- [ ] **Step 5: Commit** `git commit -m "Add For you tab with ranked table"`

### Task 7: Side panel, keyboard, collapse

**Files:**
- Create: `frontend/src/FitPanel.tsx`
- Modify: `frontend/src/ForYouBoard.tsx`, `frontend/src/index.css`
- Test: `backend/tests/test_for_you_dashboard.py`

**Interfaces:**
- Consumes: `Job`, `FitDetails` from Task 6.
- Produces:
  - `FitPanel` props: `{ job: Job | null; onCollapse(): void; onOpen(job: Job): void; onApplied(job: Job): void }`.
  - localStorage key `hej.forYou.panel` holds `'open'` or `'closed'`. Wrap reads and writes in try/catch; the default is open.

The panel shows:
- title, institution · location · "posted N days ago"
- large fit number
- three parts: "N of M required skills", sponsorship status, and seniority ("No seniority flags" or the labels)
- Matched and Missing tag lists
- sponsorship evidence sentence, or "No sponsorship wording found. Not a guarantee; check before applying."
- age line "Fit 90, posted 14 days ago, ranked as 87.2", shown only when the rank value differs from the fit
- buttons **Open listing** (calls the existing `opened` then opens `source_url`) and **Mark applied**

Layout: a two-column grid (`minmax(0,1.35fr) minmax(300px,1fr)`); the panel is sticky at `top: 12px`, stacks below the table under 900px, and the selected row gets an inset 2px left bar. Behavior:
- the first row is selected on load and on page change
- `j`/`ArrowDown` and `k`/`ArrowUp` move the selection and scroll the row into view; `Enter` opens the listing; `a` marks it applied; `Esc` collapses the panel
- keys are ignored while focus is in an input, select, or textarea
- clicking a row selects it and reopens a collapsed panel

- [ ] **Step 1: Write the failing browser test** `test_for_you_panel_keyboard_and_collapse`. On load the panel shows the first row's title. Pressing `j` makes it show the second row's title. `Esc` hides the panel, a reload keeps it hidden, and clicking a row shows it again.
- [ ] **Step 2: Run** the build and `pytest backend/tests/test_for_you_dashboard.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `FitPanel.tsx`, the keyboard handling, and the collapse state.
- [ ] **Step 4: Run** the build and `pytest -q`. Expected: PASS. Then use the tab yourself on the real database (AGENTS.md): apply filters, page to the end, and check that the row counts match the total. Take a screenshot for the PR.
- [ ] **Step 5: Commit** `git commit -m "Add fit panel with keyboard navigation"`, and update the README with a short For you section that covers the `HEJ_RESUME` setting.
