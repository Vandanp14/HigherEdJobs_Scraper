# Seniority / Eligibility Labels — Design

Date: 2026-10-28 · Status: awaiting approval

## Intent

The user is an international F-1 student finishing a BS in Computer Science, applying as a new
grad. Many saved CS roles need seniority, a doctorate, or years of experience the user does not
have. Label those roles so they can be hidden by default and toggled back into view per category.
Labels never delete jobs or change application status.

## Goals

- Label each job with zero or more ineligibility categories, each with the exact matched text.
- Hide labelled jobs by default on both boards; let the user toggle each category back on.
- Show a badge on every labelled row naming why it was flagged.
- Label saved jobs at startup without rescraping; relabel when rules change.

## Non-goals / anti-goals

- Not part of the sponsorship classifier; the five sponsorship statuses stay unchanged.
- Never drop or delete jobs; this is a view filter only.
- Do not flag on "preferred" wording (e.g. "5+ years preferred", "master's preferred").

## Categories (user-chosen)

| Label | Source | Rule (case-insensitive, bounded windows) |
|---|---|---|
| Director | title | `director`, incl. Assistant/Associate/Executive Director |
| Postdoc / PhD | title + description | title: `postdoc`, `post-doctoral`, `doctoral`; description: PhD / doctorate *required* |
| Leadership | title | `chief`, `vice president`, `VP`, `CIO`/`CTO`, `head of`, `manager`, `supervisor` |
| Senior / Lead | title | `senior`, `sr.`, `lead`, `principal`, `architect` |
| Level III+ | title | Roman pay-grade `III`/`IV`/`V` (and `3`/`4`/`5` as a trailing level) |
| 5+ years | description | 5 or more years of experience stated as required/minimum, not preferred |
| Master's required | description | master's degree stated as required, without an "or equivalent experience"/bachelor's alternative in the same sentence |

## Approaches

- **A. Stored labels (chosen).** New `backend/app/seniority.py` rules module; flags stored on the
  job with a rules version and refreshed at save time and on startup. Fast queries, badges come
  free, matches how classifier output is stored and versioned.
- B. Compute at query time via SQLite functions (like `teaching_title`). No schema change, but
  runs description regexes on every request; this repo already hit slow regex once (`27842d0`).
- C. Fold into the sponsorship classifier. Rejected: mixes two questions and breaks the PRD's
  five-status model.

## Decided how

- `jobs.seniority_flags TEXT NOT NULL DEFAULT '[]'` — JSON list of `{label, evidence}`.
- `jobs.seniority_version TEXT` — startup relabels rows whose version differs from the module's.
- Labels computed in `upsert_job` and whenever `reanalyze` runs.
- `/api/jobs` gains `hide` (comma list of labels to exclude). Default from the UI: all labels.
  Empty `hide` shows everything.
- UI: a chip row "Hide roles" like the sponsorship chips, every category on by default, plus
  "Show all". Labelled rows get a small badge per flag; hovering shows the evidence text.

## Builder's calls (Claude's proposals, flagged for review)

- Applies to both HigherEdJobs and AIR boards (titles share the same patterns).
- Hide state is per board, like the other filters.
- Regex windows bounded (≤80 chars) to avoid quadratic matching.
- Tests: rule unit tests per category incl. "preferred" negatives, API filter test, startup
  relabel test; extend the browser test to toggle a category.
