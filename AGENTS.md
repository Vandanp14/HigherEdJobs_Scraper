# Repository Guidelines

## Project Structure & Module Organization

This project is currently specification-only. `HigherEdJobs_PRD.md` defines the HigherEdJobs scraper and sponsorship review dashboard; read its V1 scope and acceptance criteria before implementing changes. No source, test, or asset directories exist yet.

The PRD recommends React/TypeScript, FastAPI/Python, Playwright, and SQLite; these are recommendations, not installed dependencies. When scaffolding, keep frontend, backend, scraping, parsing, classification, and persistence responsibilities separate. Document the chosen directory layout and setup in a README.

## Build, Test, and Development Commands

No build, development, test, or lint commands are configured yet. Add reproducible commands and dependency manifests when introducing the implementation.

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

## Commit & Pull Request Guidelines

No Git history is available to establish existing conventions. Use concise, imperative commit subjects, such as `Add sponsorship classifier fixtures`. Keep changes focused.

PRs should explain behavior changes, reference relevant PRD sections or issues, report validation performed, and include screenshots for dashboard changes. Call out schema and configuration changes explicitly.

## Scraping & Data Integrity

Modify only the Keyword search field in V1. Use conservative request rates, caching, and applicable access restrictions. Preserve raw descriptions, exact classification evidence, original links, and historical records. Never interpret missing sponsorship language as guaranteed eligibility.
