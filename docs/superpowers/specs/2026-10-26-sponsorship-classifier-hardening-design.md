# Sponsorship classifier hardening — design

## Intent

The user is on F-1, with a CS (STEM) degree. Their path is OPT, then STEM OPT, then **cap-exempt H-1B**
through a college or university. That is why they search higher-ed boards. Every job answers one
question for them: *will this employer sponsor H-1B later?*

They read jobs by date and sponsorship signal, and still open every listing to be sure. Labels
therefore don't decide what they see. They decide what the user expects before opening a job, and
wrong labels erode trust. The costliest error is **hiding or discouraging a job that would actually
sponsor** (a false "Not Worth It").

## What is wrong today (found in 451 real saved jobs)

1. **HTML is in the classified text.** In 333 of 451 jobs, HigherEdJobs JSON-LD descriptions are
   HTML-escaped twice (`&lt;p&gt;`). One BeautifulSoup pass leaves literal `<p>` and `<li>` in
   `normalized_description`. Sentence splitting then runs across bullets, matches land in the wrong
   clause, and evidence quotes contain tags.
2. **False "Sponsorship Possible":** "A visa sponsorship is available for the position listed in this
   vacancy: No" is classified as Possible.
3. **Refusals classified "Unsure":** "authorized to work … without employer assistance or sponsorship
   now or in the future"; "may not be eligible for visa sponsorship now or in the future".
4. **Noise classified "Unsure":** "IU-sponsored volunteer events", "sponsored research", a China job's
   "sponsors working visa … in China", and long run-on clauses with no visa meaning.
5. **Form-style fields not read:** "Sponsorship Available:" with Yes/No on the next line.
6. **Missing refusal types:** "U.S. citizens only", "permanent residents only", and "security
   clearance required" are not triggers at all.

## Goals

- Clean text first: descriptions are plain text with real line breaks, with no HTML tags or entities.
- Correct labels for the user's situation (rules below). Evidence stays an **exact substring** of the
  clean description (PRD §15).
- Show **signal badges** separate from the status: `E-Verify`, `Cap-exempt`, and a warning
  `Non-college employer`.
- Re-label all saved jobs without rescraping, re-normalizing from `raw_description` where present.
- A regression suite built from the real misclassified sentences above.
- **Multi-select sponsorship filter** (user's decision). The user can pick several labels at once
  (for example everything except Not Worth It). Results are always sorted newest by posted date within the
  selection, which is the existing default sort. Choosing nothing means all labels. The API takes
  `sponsorship` as a comma-separated list, the same way `group` already does; a single value keeps
  working. The existing single-label filter and date sort must not regress.
- **Evidence text wraps** (user's decision). Long evidence in the table's Evidence column wraps onto
  several lines inside the column instead of widening the table, so the user never has to scroll
  sideways to read it. The full text stays visible; it is not truncated.

## Non-goals

- LLM or Claude classification. Approach C may be added later if *Unsure* stays large.
- Ranking or scoring jobs. The user reads by date and opens everything.
- Hiding jobs by default. Dashboard filter defaults are unchanged.

## Anti-goals

- A job that would sponsor labelled "Not Worth It". **When unsure, never choose Not Worth It.**
- Evidence that is paraphrased or rebuilt instead of quoted from the description.
- Treating missing sponsorship language as eligibility (AGENTS.md). "No Mention Found" stays neutral.

## Labelling rules (user's decisions, from the conversation)

The statuses are unchanged; the PRD's five are kept.

| Posting says | Status |
|---|---|
| Unconditional refusal: "will not / cannot / unable to sponsor", "sponsorship is not available", "not eligible for sponsorship", "without (current or) future sponsorship", "now or in the future" combined with refusal or without-sponsorship wording, a form field "Sponsorship available: No" | **Not Worth It** (High) |
| "U.S. citizens only", "must be a U.S. citizen", "permanent residents only", "green card required", "security clearance required/must obtain" | **Not Worth It** (High) |
| Hedged: "may not be eligible for sponsorship", "might not", "sponsorship is not guaranteed", "employs only individuals lawfully authorized to work" combined with refusal hints | **Likely No Sponsorship** (Medium) |
| "Sponsorship is available / may be considered / will be provided", "H-1B sponsorship provided", form field "Sponsorship available: Yes" | **Sponsorship Possible** |
| Only "must be authorized to work in the U.S. (at time of hire)" with no future-sponsorship refusal | **neutral**: OK for OPT. It does not create Unsure. Status stays as if there were no mention, and the sentence is recorded as context. |
| Trigger words used for something else: "sponsored research/projects/events/programs", "IU-sponsored", a visa for another country | **ignored** |
| Real visa or sponsorship language that matches no rule | **Unsure - Review** |

**Hedges win within a sentence** (my call, from the user's priority that false Not Worth It is the
costliest error). A sentence containing "may", "might" or "not guaranteed" next to the sponsorship
wording is Likely No, even with "now or in the future". Example: "this position may not be eligible for
visa sponsorship now or in the future" (Loyola Marymount) is **Likely No**. The posting still becomes Not
Worth It if a *different* sentence refuses flatly, by precedence.

Precedence (highest first): Not Worth It, Sponsorship Possible, Likely No, Unsure, No Mention Found.
This matches the current ranking. A refusal anywhere outranks a possible elsewhere, because an explicit
"No" form answer must beat boilerplate.

**Form fields:** a line ending with a sponsorship question or label ("Sponsorship Available:", "Visa
sponsorship is available for this position:") whose answer is the same line's tail or the next
non-empty line, with `Yes`/`No` (case-insensitive) mapped as above. The evidence is the label line; the
context includes the answer line.

## Signals (badges, independent of status)

- **E-Verify**: the description mentions E-Verify. It is positive for STEM OPT.
- **Cap-exempt**: the description mentions "cap-exempt" or "cap exempt".
- **Non-college employer**: a warning only, because such employers are often not H-1B cap-exempt. It never
  changes status. Decode HTML entities in the institution name first (`William &amp; Mary`). Warn only
  when the name matches none of: `university|college|institute|school|academy|seminary|conservatory|
  poly|tech|state|suny|cuny|community college|board of regents|system|medicine|medical|health|hospital|
  campus|william & mary|cornell|arts center` (case-insensitive). My call: the builder check found that
  the shorter list wrongly warned on 14 of 15 university employers in today's data (Penn State, Virginia
  Tech, SUNY campuses, Cal Poly, Weill Cornell Medicine, UC Davis Health, and others). University
  hospitals and medical schools are usually cap-exempt too. A regression test pins those 14 as *not*
  warned. The builder may extend the list further, but must not shrink it.

## Approaches considered

- **A. Harden the rules (chosen).** Deterministic, offline, free, exact evidence. Its limit is that
  unusual wording stays Unsure, which is acceptable because the user opens every job.
- **B. Claude classifies every job.** Better at nuance, but costs money, needs a key, is
  nondeterministic, and risks paraphrased evidence. Rejected.
- **C. A + Claude for Unsure only.** Deferred; reconsider if Unsure stays large after A.

## How (decided)

- **Parser:** when the JSON-LD description text, once parsed, still contains escaped or literal tags,
  unescape and parse again before building `normalized_description`. Block elements still become line
  breaks.
- **Re-analysis:** `Database.reanalyze()` re-normalizes from `raw_description` when present, using each
  source's own normalization (HigherEdJobs and AIR differ), then classifies. Jobs without raw HTML
  (compacted) reuse the stored `normalized_description` after a tag-strip pass. The cleaned text
  **overwrites** `normalized_description` (my call). It is derived data, and the evidence must be a
  substring of the text the dashboard shows. `raw_description`, the preserved record that AGENTS.md
  protects, is never changed.
- **Automatic re-label** (my call): on server startup, any analysis whose `classifier_version` differs
  from the current `VERSION` is re-analyzed once. Existing saved jobs then get the new labels and
  badges without the user clicking anything. Later runs skip it, because versions then match. The
  "Re-analyze saved jobs" button keeps working.
- **Classifier:** bump `VERSION` to 2.0.0. Keep clause-level matching on clean text. Add the noise
  filter before triggers, the new refusal patterns, the form-field rule, and the authorization-only
  neutral rule.
- **Storage:** add a `signals TEXT NOT NULL DEFAULT '[]'` column (a JSON list) to
  `sponsorship_analysis` via `_migrate_columns`. **This is a schema change.**
- **API and dashboard:** `/api/jobs` returns `signals`. Each row's Sponsorship cell shows small badges
  next to the status. The non-college badge is styled as a warning.
- **Tests:**
  - one regression test per real sentence in "What is wrong today", asserting the status and that the
    evidence is a substring of the input
  - the double-escaped HTML fixture
  - the signal detection rules

## Left to the builder

- Exact regex wording and the noise-word list, provided the regression tests pass.
- Badge styling, within the existing dashboard look.
- Whether neutral authorization-only sentences are shown as the evidence when nothing else matched.
  Recommended: yes, with status "No Mention Found", so the user sees why.
