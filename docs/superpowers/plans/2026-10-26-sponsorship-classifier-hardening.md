# Sponsorship Classifier Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accurate sponsorship labels for an F-1 → OPT → STEM OPT → cap-exempt H-1B job seeker. The work covers:
- clean description text
- signal badges
- automatic re-labelling of saved jobs
- a multi-select sponsorship filter sorted by date
- wrapped evidence

**Architecture:**
- Parser normalization becomes two reusable functions, one per source, that also undo HigherEdJobs' double-escaped HTML.
- The classifier stays rule-based (VERSION 2.0.0) and adds a noise filter, refusal and form-field rules, an authorization-only neutral rule, and `signals`.
- Database re-analysis re-normalizes from `raw_description` and runs automatically at startup when the version changes.
- The dashboard gets badges, a multi-select filter, and wrapping.

**Tech Stack:** Python 3.13, BeautifulSoup, SQLite, FastAPI, React + Vite (TS), pytest.

**Spec:** `docs/superpowers/specs/2026-10-26-sponsorship-classifier-hardening-design.md`

## Global Constraints

- Statuses stay exactly: `Not Worth It`, `Likely No Sponsorship`, `Unsure - Review`, `No Mention Found`, `Sponsorship Possible`.
- Evidence is always an exact substring of the clean `normalized_description`.
- When unsure, never choose `Not Worth It`. A hedge ("may", "might", "not guaranteed") in a sentence makes that sentence `Likely No Sponsorship` at most.
- `raw_description` is never modified.
- Classifier `VERSION = "2.0.0"`.
- Schema change: `sponsorship_analysis.signals TEXT NOT NULL DEFAULT '[]'` (a JSON list of `"E-Verify"`, `"Cap-exempt"`, `"Non-college employer"`).
- Tests: `.venv/bin/pytest`; Python four-space indent; TS two-space.

## Review Focus

- A posting with a flat refusal **and** a hedged sentence must be `Not Worth It`; one with only the hedge must be `Likely No Sponsorship`. Test `test_hedge_alone_is_likely_no_but_flat_refusal_elsewhere_wins` (Task 2).
- A form label whose Yes/No answer is on the **next** line, with blank lines between. Test `test_form_field_answer_on_next_line` (Task 2).
- Jobs compacted earlier (`raw_description` NULL) must still re-label without crashing, using tag-stripped stored text. Test `test_reanalyze_without_raw_strips_tags` (Task 3).
- `sponsorship=` (empty) and a single value must keep working alongside comma lists. Test `test_sponsorship_filter_accepts_list_and_single` (Task 4).
- A startup with nothing to re-label must not rewrite rows: `analyzed_at` stays unchanged. Test `test_startup_relabel_only_touches_old_versions` (Task 3).

---

### Task 1: Clean description text

**Files:**
- Modify: `backend/app/parser.py` (`parse_job` ~255-315, `parse_air_job` ~370-420)
- Test: `backend/tests/test_normalize.py`

**Interfaces:**
- Produces:
  - `normalize_hej_description(raw: str) -> str`: if `raw` contains `&lt;`, apply `html.unescape` once before parsing. Drop `script, style, noscript`. Put a newline after `p, div, li, br, h1-h4, center, tr`. Collapse whitespace per line and drop empty lines.
  - `normalize_air_description(raw: str) -> str`: today's AIR logic, moved into a function unchanged.
  - Both are used by `parse_job` and `parse_air_job` respectively, and called by Task 3.

- [ ] **Step 1: Write failing tests**

```python
def test_double_escaped_hej_html_becomes_plain_lines():
    raw = "&lt;p&gt;Duties include analysis.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;li&gt;Visa sponsorship is not available.&lt;/li&gt;&lt;/ul&gt;"
    assert normalize_hej_description(raw) == "Duties include analysis.\nSQL\nVisa sponsorship is not available."

def test_plain_hej_html_unchanged_behaviour():
    assert normalize_hej_description("<p>A &amp; B</p><p>C</p>") == "A & B\nC"

def test_air_normalization_matches_saved_fixture():
    # fixture: backend/tests/fixtures/air_detail.html via parse_air_job; same text as before the refactor
    ...assert parse_air_job(...).normalized_description == normalize_air_description(job.raw_description)
```

- [ ] **Step 2:** `.venv/bin/pytest backend/tests/test_normalize.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement both functions and use them in the two parsers.
- [ ] **Step 4:** `.venv/bin/pytest -q`. Expected: all pass, including `test_air.py`.
- [ ] **Step 5:** Commit `Undo double-escaped HTML in job descriptions`.

### Task 2: Classifier 2.0.0

**Files:**
- Modify: `backend/app/classifier.py`
- Modify: `backend/tests/test_classifier.py` (existing `test_authorization_requirement_alone_remains_reviewable` now expects `No Mention Found`, with that sentence as evidence; rename it `test_authorization_requirement_alone_is_neutral_for_opt`)
- Test: `backend/tests/test_classifier_v2.py`

**Interfaces:**
- Produces:
  - `Analysis` gains `signals: list[str]` (default empty).
  - `classify(description: str, institution: str | None = None) -> Analysis`.
  - `VERSION = "2.0.0"`.

Rules, in sentence or clause order. Each sentence gets one result; the posting takes the highest by precedence: Not Worth It > Sponsorship Possible > Likely No > Unsure > authorization-only neutral > none.

1. **Noise:** remove matches of `sponsored\s+(?:research|projects?|programs?|events?|activities|volunteer)`, `\w+-sponsored`, and visa for another country (`visa.{0,60}\bin\s+(?:china|canada|the\s+uk|united\s+kingdom|qatar|uae|singapore)` and similar). Remove them before trigger detection.
2. **Triggers:** today's triggers, plus `u\.?s\.?\s+citizen(?:s|ship)?`, `permanent\s+resident`, `green\s+card`, `security\s+clearance`, `e-?verify`, `cap[\s-]exempt`.
3. **Not Worth It:**
   - today's NEGATIVE patterns
   - `(?:now\s+or\s+in\s+the\s+future|current\s+or\s+future)` together with `sponsor` in a sentence that has no hedge
   - citizens-only and permanent-residents-only wording (`only\s+(?:u\.?s\.?\s+)?citizens`, `must\s+be\s+a\s+u\.?s\.?\s+citizen`, `(?:u\.?s\.?\s+)?citizenship\s+(?:is\s+)?required`, `permanent\s+residents?\s+only`, `green\s+card\s+required`)
   - clearance required (`(?:must|required\s+to)\s+(?:have|hold|obtain)\b.{0,40}security\s+clearance`, `security\s+clearance\s+(?:is\s+)?required`)
4. **Form field:** a line ending in `:` that contains `sponsor` (or `visa`), answered on the same line's tail or the next non-empty line. `No` makes it Not Worth It and `Yes` makes it Sponsorship Possible. The evidence is the label line plus the answer, kept exact (`"Sponsorship Available:\nNo"` must be a substring). The context is the paragraph.
5. **Hedge:** a sentence containing `\bmay\b|\bmight\b|not\s+guaranteed` with sponsorship wording becomes `Likely No Sponsorship` (Medium), never Not Worth It.
6. **Possible:** today's POSITIVE patterns. Exclude any match where the same sentence ends in `:\s*no\b`.
7. **Authorization-only:** a trigger sentence that only requires current work authorization ("authorized to work in the United States", "lawfully authorized") with no future or sponsor refusal. It does not create Unsure. If nothing outranks it, the result is `No Mention Found` (Low), with that sentence as the evidence.
8. **Signals:** `E-Verify` if `e-?verify` appears anywhere; `Cap-exempt` if `cap[\s-]exempt` appears. `Non-college employer` when `institution`, after `html.unescape`, matches none of `university|college|institute|school|academy|seminary|conservatory|poly|tech|state|suny|cuny|community college|board of regents|system|medicine|medical|health|hospital|campus|william & mary|cornell|arts center` (case-insensitive). No institution means no warning.

- [ ] **Step 1: Write failing tests**, each asserting `status` and `evidence in description`:

| Test | Input (real wording) | Expected |
|---|---|---|
| `test_form_field_no_on_same_line` | `A visa sponsorship is available for the position listed in this vacancy: No` | Not Worth It |
| `test_form_field_answer_on_next_line` | `Sponsorship Available:\n\nNo` | Not Worth It |
| `test_form_field_yes` | `Sponsorship Available:\nYes` | Sponsorship Possible |
| `test_without_sponsorship_now_or_future` | `The selected candidate for this position must be authorized to work in the United States at the time of hire without employer assistance or sponsorship now or in the future.` | Not Worth It |
| `test_hedge_is_likely_no` | `Please note that this position may not be eligible for visa sponsorship now or in the future.` | Likely No Sponsorship |
| `test_hedge_alone_is_likely_no_but_flat_refusal_elsewhere_wins` | the hedge sentence + `\nVisa sponsorship is not available.` | Not Worth It |
| `test_noise_is_ignored` (parametrize) | `Paid leave for new parents and IU-sponsored volunteer events`; `The incumbent is also expected to carry out sponsored research and projects involving students.`; `XJTLU sponsors working visa and residence permit in China for the staff.` | No Mention Found, evidence None |
| `test_authorization_only_is_neutral` | `California State University, Chico employs only individuals lawfully authorized to work in the United States.` | No Mention Found, evidence = that sentence |
| `test_citizens_only` (parametrize) | `Applicants must be a U.S. citizen.`; `U.S. citizenship is required.`; `Candidates must obtain a security clearance.` | Not Worth It |
| `test_possible_still_detected` | `Employment visa sponsorship may be considered for this position.` | Sponsorship Possible |
| `test_signals` | `Employer participates in E-Verify. The university is H-1B cap-exempt.` | signals == `["E-Verify", "Cap-exempt"]` |
| `test_non_college_employer` (parametrize) | Not warned: `Penn State Harrisburg`, `Virginia Tech`, `SUNY Oneonta`, `Cal Poly San Luis Obispo`, `William &amp; Mary`, `Weill Cornell Medicine`, `UC Davis Health`, `The Clarice Smith Performing Arts Center`. Warned: `Acme Analytics LLC` | `"Non-college employer" in signals` False / True |

- [ ] **Step 2:** `.venv/bin/pytest backend/tests/test_classifier_v2.py backend/tests/test_classifier.py -v`. Expected: the new tests FAIL; the old tests still pass, except the renamed one, which fails.
- [ ] **Step 3:** Implement the rules above in `classifier.py`.
- [ ] **Step 4:** `.venv/bin/pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit `Harden sponsorship classifier for OPT to cap-exempt H-1B`.

### Task 3: Storage, re-analysis, startup re-label

**Files:**
- Modify: `backend/app/database.py` (`_migrate_columns`, `upsert_job` analysis insert, `reanalyze`, `jobs` SELECT), `backend/app/main.py` (startup)
- Test: `backend/tests/test_reanalyze.py`

**Interfaces:**
- Consumes: `normalize_hej_description`, `normalize_air_description` (Task 1); `classify(description, institution)` and `Analysis.signals` (Task 2).
- Produces:
  - column `sponsorship_analysis.signals`
  - `Database.reanalyze(only_outdated: bool = False) -> int`: re-normalize from `raw_description` per `source`, else strip tags from the stored text with `BeautifulSoup(...).get_text("\n")`. Then write `normalized_description`, classify with the institution, and upsert the analysis including `signals`. With `only_outdated`, only jobs whose analysis `classifier_version != VERSION` or that have no analysis.
  - `/api/jobs` rows include `signals` as a JSON string (the frontend parses it).
  - `main.py` calls `database.reanalyze(only_outdated=True)` at startup, after `close_interrupted_runs()`.

- [ ] **Step 1: Write failing tests:**
  - `test_reanalyze_renormalizes_from_raw`: upsert an HEJ draft whose `raw_description` is double-escaped and whose `normalized_description` contains `<p>`. After `reanalyze()`, the stored text has no `<`, `raw_description` is unchanged, and the status is from the clean text.
  - `test_reanalyze_without_raw_strips_tags`: `raw_description=None`, normalized `"<p>Visa sponsorship is not available.</p>"`. Expect `Not Worth It`.
  - `test_signals_column_round_trips`: after upsert with E-Verify text, `json.loads(row["signals"]) == ["E-Verify"]` via `db.jobs(days="all")`.
  - `test_startup_relabel_only_touches_old_versions`: one analysis at `"1.1.0"` and one at the current VERSION. `reanalyze(only_outdated=True) == 1`, and the current row's `analyzed_at` is unchanged.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. The migration adds the column for existing databases.
- [ ] **Step 4:** `.venv/bin/pytest -q`. Expected: all pass. Then check the real data without writing to it: `cp data/jobs.sqlite3 <scratch>` and run `reanalyze(only_outdated=True)` on the copy. Print the status counts and the count of evidence containing `<`; the latter must be 0.
- [ ] **Step 5:** Commit `Store sponsorship signals and re-label saved jobs on upgrade`.

### Task 4: Multi-select filter, badges, wrapping

**Files:**
- Modify: `backend/app/database.py` (`jobs()` sponsorship clause), `frontend/src/main.tsx`, `frontend/src/index.css`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `signals` in `/api/jobs` rows (Task 3).
- Backend: `sponsorship` accepts a comma-separated list, giving `sa.status IN (…)`. An empty value means no filter. Sort is unchanged (default newest by `COALESCE(posted_date, first_seen)`).
- Frontend:
  - The Sponsorship select becomes a multi-select. Follow the existing multi-group pattern (`selectedGroups = filters.group.split(',')`).
  - The filter value stays a comma-joined string, and the default is all (empty).
  - Badges go under the status in the Sponsorship cell: `E-Verify` and `Cap-exempt` in the existing `signal-positive` style, `Non-college employer` in `signal-caution`.
  - Evidence wraps: `.evidence button { white-space: normal; overflow-wrap: anywhere; }`.
  - Table `min-width` goes from 1420px to 1100px so the table fits a laptop without sideways scrolling. This is the spec intent "never scroll sideways to read it".

- [ ] **Step 1: Write failing test** `test_sponsorship_filter_accepts_list_and_single`:
  - Insert three jobs whose analyses are Not Worth It, Unsure and Possible.
  - `?sponsorship=Unsure%20-%20Review,Sponsorship%20Possible&days=all` returns 2, newest first by `posted_date`.
  - `?sponsorship=Not%20Worth%20It` returns 1.
  - `?sponsorship=` returns 3.
- [ ] **Step 2:** Run. Expected: the list case FAILs.
- [ ] **Step 3:** Implement the backend, then the frontend. Update the README dashboard section to describe the badges and the multi-select filter.
- [ ] **Step 4:**
  - `.venv/bin/pytest -q`, expecting everything to pass.
  - `cd frontend && npm run build`, expecting success.
  - Manual check: run `./view.sh`, pick two labels, and confirm the rows are newest first, the badges appear, and long evidence wraps without sideways scroll.
- [ ] **Step 5:** Commit `Add multi-select sponsorship filter, signal badges, wrapped evidence`.
