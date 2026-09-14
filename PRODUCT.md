# Product truth

HigherEdJobs Review helps a person discover technical higher-education jobs and inspect sponsorship wording before applying manually. `HigherEdJobs_PRD.md` is the specification.

The primary surface is one dense, filterable job table. Eight overlapping searches feed it; jobs retain every match. Evidence, original listings, and application tracking are central. A missing or uncertain signal must never silently remove a job.

V1 uses React/TypeScript, FastAPI, Playwright, and SQLite locally. It does not apply to jobs, send outreach, or determine legal eligibility.

## Interface direction

Use a near-black canvas (#09090b), charcoal table and controls (#18181b, #27272a), white primary text (#fafafa), and readable secondary text (#a1a1aa). Reserve muted green and amber for sponsorship signals. Native system typography carries headings and body; tabular numbers clarify dates and counts. Tailwind 4 and daisyUI 5 provide components.

The hierarchy is toolbar → search and filters → unified table → pagination. Evidence expands in place, keeping the source and decision together. Search configuration and run history are secondary collapsible panels. Favor a useful table over ornamental cards or a marketing hero. Empty, loading, failed, and stale-description states must be explicit. Keyboard focus, labels, responsive horizontal scrolling, and reduced-motion support are required.
