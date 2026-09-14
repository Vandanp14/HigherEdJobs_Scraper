# Product Requirements Document: HigherEdJobs Job Scraper & Sponsorship Review Dashboard

## 1. Product Summary

Build a local web application that automates job discovery on HigherEdJobs.com, collects job listings from a fixed set of keyword searches, analyzes sponsorship/work-authorization language, and presents all results in one unified table-style dashboard.

The main purpose is to reduce the time spent manually searching HigherEdJobs and opening individual listings just to discover that a role likely does not support visa sponsorship.

The tool must preserve direct links to the original HigherEdJobs listing and employer application page so every result can be manually verified.

---

## 2. Primary User Goal

The user wants to quickly identify relevant U.S.-based higher-education jobs in software, data, systems, web, database, cloud, and research computing while avoiding unnecessary manual review of jobs with restrictive sponsorship language.

The system should answer:

- What new relevant jobs were posted?
- Which search query found each job?
- Does the listing mention visa sponsorship or work authorization?
- How strong is that signal?
- What exact wording caused the classification?
- When was the job posted?
- Where is it located?
- What university posted it?
- Has the user already opened, applied to, or skipped it?
- Can the original job be opened immediately for verification?

---

## 3. V1 Scope

V1 will include:

- HigherEdJobs advanced search automation
- fixed keyword search groups
- execution of all search groups
- pagination through all result pages
- extraction of job metadata
- opening and parsing individual job pages
- sponsorship/work-authorization language detection
- confidence/status classification
- exact evidence sentence extraction
- job deduplication
- date normalization
- database persistence
- one unified dashboard
- dense CSV/spreadsheet-style table
- filtering
- sorting
- search
- direct job URLs
- application status tracking
- manual reruns
- job history retention

V1 will not include:

- automatic job applications
- automatic resume tailoring
- automatic cover-letter generation
- automatic email outreach
- LinkedIn scraping
- other job boards
- AI-based ranking as the primary classifier
- legal determinations about visa eligibility

---

## 4. Target Website

Primary site:

```text
https://www.higheredjobs.com/
```

Advanced search:

```text
https://www.higheredjobs.com/search/advanced.cfm
```

The scraper should modify only the **Keyword** field.

Other HigherEdJobs search filters should remain untouched in V1.

---

## 5. Search Queries

V1 contains exactly eight predefined search groups.

### 5.1 Data & Analytics

```text
"data analyst" OR "data analytics" OR "business intelligence"
```

### 5.2 Software Development

```text
"software developer" OR "application developer" OR "programmer analyst"
```

### 5.3 Web Development

```text
"web developer" OR "web application" OR "full stack"
```

### 5.4 Database

```text
"database administrator" OR "database analyst" OR "database developer"
```

### 5.5 Systems & Applications

```text
"systems analyst" OR "business systems analyst" OR "applications analyst"
```

### 5.6 Cloud & DevOps

```text
"cloud engineer" OR AWS OR DevOps
```

### 5.7 Research Computing

```text
"research programmer" OR "research software" OR "research computing"
```

### 5.8 University IT Titles

```text
"programmer analyst" OR "applications analyst" OR "systems analyst"
```

Overlap between searches is intentional.

A job may match multiple search groups.

---

## 6. Search Execution Behavior

All enabled search groups should run independently.

The system must:

1. Open HigherEdJobs Advanced Search.
2. Enter the query in the Keyword field.
3. Submit the search.
4. Process the full result set.
5. Continue through pagination until no additional pages remain or a configured cutoff is reached.
6. Collect all job URLs.
7. Repeat for the next search group.
8. Merge all results into one dataset.
9. Deduplicate jobs.
10. Preserve all matched search groups for each job.

Search groups are collection sources, not separate result pages.

---

## 7. Unified Results Model

All jobs must appear in one unified dashboard.

The main dashboard must not split results into eight separate views.

Example:

```text
Programmer Analyst
University Example

Matched Search Groups:
Software Development
Systems & Applications
University IT Titles
```

The job appears only once.

Filtering by any matched search group should still include it.

---

## 8. Deduplication

The same job may appear in multiple keyword searches.

The system must deduplicate by the most reliable identifier available.

Preferred order:

1. HigherEdJobs unique job ID
2. canonical HigherEdJobs job URL
3. employer URL
4. normalized combination of:
   - job title
   - institution
   - location

When duplicates are found:

- keep one job record
- merge matched search groups
- preserve earliest first-seen date
- update latest seen date
- preserve existing application status

---

## 9. Pagination

The scraper must not stop after the first page.

It must process all available pages.

Preferred behavior:

1. Detect HigherEdJobs pagination structure.
2. Identify the next-page mechanism.
3. Continue automatically.
4. Stop when:
   - no next page exists, or
   - configured date cutoff has been reached and older pages are no longer useful.

The implementation should not depend on visual scrolling if the results already exist in the DOM.

---

## 10. Playwright Discovery Strategy

Playwright should be used during initial integration discovery.

Recommended process:

```bash
npx playwright codegen https://www.higheredjobs.com/search/advanced.cfm
```

A developer manually performs:

- entering a keyword query
- submitting the search
- navigating to page 2
- opening a job
- identifying the job description
- identifying posting date
- locating employer/application URL

The generated actions are used to understand the site structure.

Recorded selectors must then be cleaned up.

Selector preference:

1. stable IDs
2. stable `name` attributes
3. labels
4. accessible roles
5. stable href patterns
6. stable CSS classes
7. positional selectors only as a last resort

The production scraper should not blindly replay brittle codegen output.

---

## 11. Job Data Collection

Each job record should attempt to store:

```text
HigherEdJobs ID
Job Title
Institution
Location
City
State
Salary
Posted Date
First Seen Date
Last Seen Date
HigherEdJobs URL
Employer Application URL
Matched Search Groups
Raw Description
Normalized Description
Sponsorship Status
Sponsorship Confidence
Evidence Sentence
Matched Sponsorship Terms
Application Status
Notes
Classifier Version
```

Missing fields should be allowed.

---

## 12. Date Handling

Two separate concepts must be stored.

### Posted Date

The date HigherEdJobs says the job was posted.

### First Seen

The first date the scraper discovered the job.

These must not be treated as the same value.

All posting dates should be normalized to:

```text
YYYY-MM-DD
```

If HigherEdJobs provides relative dates such as `2 days ago`, they should be converted into an absolute date based on scrape time.

---

## 13. Sponsorship Detection Goal

The system should detect language related to:

- visa sponsorship
- H-1B
- H1B
- work authorization
- employment authorization
- employer sponsorship
- current or future sponsorship
- immigration sponsorship

The goal is not to make a legal determination.

The goal is to help prioritize or deprioritize jobs based on wording in the posting.

---

## 14. Sponsorship Trigger Terms

The system should recognize terms including:

```text
visa
visa sponsorship
sponsorship
sponsor
H-1B
H1B
work authorization
employment authorization
authorized to work
legally authorized
current sponsorship
future sponsorship
employer sponsorship
immigration sponsorship
```

Trigger terms alone must not determine classification.

Context is required.

---

## 15. Sponsorship Evidence Extraction

Whenever a relevant phrase is found, the system should save the full surrounding sentence.

Example source text:

```text
Candidates must have valid U.S. work authorization at the time of application; UNC cannot provide H-1B sponsorship at this time.
```

Stored evidence:

```text
UNC cannot provide H-1B sponsorship at this time.
```

The dashboard should allow the full surrounding paragraph to be expanded if needed.

---

## 16. Sponsorship Classification

V1 should use five statuses.

### 16.1 Not Worth It

Strong negative language with high confidence.

Examples:

```text
cannot provide H-1B sponsorship
will not sponsor
visa sponsorship is not available
this position is not eligible for sponsorship
must work without current or future sponsorship
unable to provide sponsorship
```

### 16.2 Likely No Sponsorship

Negative language exists, but the meaning is somewhat less explicit.

Example:

```text
Applicants must already possess unrestricted U.S. work authorization.
```

### 16.3 Unsure - Review

Relevant authorization language exists, but the wording is ambiguous.

Example:

```text
Applicants must be legally authorized to work in the United States.
```

This should not automatically be treated as a rejection.

### 16.4 No Mention Found

No sponsorship or work-authorization language was detected.

This does not mean sponsorship is available.

It simply means the posting did not explicitly discuss it.

### 16.5 Sponsorship Possible

Explicitly positive language.

Examples:

```text
Visa sponsorship may be available.
```

```text
H-1B sponsorship is available for qualified candidates.
```

---

## 17. Confidence

The system should store confidence separately from status.

For V1, use:

```text
High
Medium
Low
```

A percentage score may be added later.

---

## 18. Rule Hierarchy

Sponsorship analysis should occur in layers.

### Layer 1: Strong Exact Patterns

Examples:

```text
cannot provide H-1B sponsorship
without current or future sponsorship
visa sponsorship is not available
```

These should produce high-confidence results.

### Layer 2: Phrase Combinations

Examples:

```text
cannot + sponsor
unable + sponsorship
not eligible + sponsorship
without + sponsorship
```

### Layer 3: Context Trigger

Examples:

```text
work authorization
authorized to work
visa
H-1B
```

These should extract evidence and usually result in `Unsure - Review` unless stronger wording is found nearby.

If multiple signals appear, stronger evidence wins.

---

## 19. Preserve Raw Content

The system must retain the full job description.

Store:

```text
raw_description
normalized_description
```

This allows sponsorship rules to be improved later without rescraping every historical job.

Each sponsorship analysis should also store:

```text
classifier_version
```

so old job descriptions can be reprocessed when rules improve.

---

## 20. Main Dashboard

The dashboard must use one primary table-style view.

The experience should resemble:

- CSV
- spreadsheet
- Airtable
- database table

The dashboard should prioritize information density over cards.

---

## 21. Dashboard Table Columns

Recommended V1 columns:

| Column | Description |
|---|---|
| Job Title | Job title |
| Institution | University or college |
| Location | City and state |
| Posted Date | Job posting date |
| First Seen | First scraper discovery |
| Search Group | One or more matched searches |
| Sponsorship | Classification |
| Confidence | High / Medium / Low |
| Evidence | Sponsorship wording |
| Salary | If available |
| Application Status | New / Opened / Applied / Skipped |
| HigherEdJobs | Direct original listing |
| Apply | Employer application URL |

---

## 22. Table Behavior

The table must support:

- sticky header
- horizontal scrolling
- column sorting
- column filtering
- text search
- row expansion
- multi-select filters
- dense rows
- large result sets
- pagination or virtualized scrolling

The main job data should remain visible in one view.

---

## 23. Evidence Column

The evidence cell should show a shortened excerpt.

Example:

```text
"UNC cannot provide H-1B sponsorship..."
```

Clicking the cell or expanding the row should show the full evidence sentence or paragraph.

---

## 24. Dashboard Filters

Required V1 filters:

```text
Search
Date Posted
Search Group
Sponsorship Status
Confidence
Application Status
Institution
State
```

Optional salary filtering may be included if salary extraction is reliable.

Search group filtering should use OR logic by default.

---

## 25. Default Dashboard View

Recommended default:

```text
Date: Last 7 days
Search Groups: All
Sponsorship: All
Application Status: All except Skipped
Sort: Newest Posted First
```

Quick date filters:

```text
Today
Last 3 Days
Last 7 Days
Last 14 Days
Last 30 Days
All Time
Custom Range
```

Sorting options:

```text
Newest Posted
Oldest Posted
Newest First Seen
Highest Sponsorship Confidence
Lowest Sponsorship Confidence
Institution
Job Title
State
```

---

## 26. Direct Links

Each row must contain a direct HigherEdJobs listing link.

Example:

```text
Open HEJ ↗
```

If an employer application URL is available:

```text
Apply ↗
```

These must open in a new tab.

---

## 27. Application Status Tracking

V1 should support:

```text
New
Opened
Applied
Skipped
```

Application status should be editable directly from the table.

When a user clicks the HigherEdJobs or application URL, the job may automatically transition:

```text
New -> Opened
```

The user must still be able to change it manually.

---

## 28. Search Configuration

The dashboard should include a simple search configuration area.

For V1, the eight queries are predefined.

The user may:

- enable a query
- disable a query
- run one query
- run all enabled queries

Editing the actual query strings is not required in V1.

---

## 29. Run Controls

Dashboard controls:

```text
Run All Searches
Run Selected Search
Refresh Jobs
Re-analyze Sponsorship
```

The interface should show:

```text
Last scrape completed
Jobs found
New jobs
```

During scraping, show progress by search group.

One failed query must not stop the entire scrape.

---

## 30. Error Handling

If a search fails:

- record the error
- continue other searches
- allow retry

If a job page fails to load:

- preserve listing metadata
- mark description scrape as failed
- leave sponsorship status as unavailable
- allow retry later

Jobs should not be automatically deleted just because they disappear from HigherEdJobs.

Track:

```text
first_seen
last_seen
active
```

A previously known job that disappears may become:

```text
Inactive / No Longer Listed
```

---

## 31. Database Behavior

Recommended V1 database:

```text
SQLite
```

Possible future migration:

```text
PostgreSQL
```

### Suggested Data Model

#### jobs

```text
id
higheredjobs_id
title
institution
location
city
state
salary
posted_date
first_seen_at
last_seen_at
higheredjobs_url
apply_url
raw_description
normalized_description
active
application_status
notes
created_at
updated_at
```

#### search_groups

```text
id
name
query
enabled
priority
```

#### job_search_matches

```text
job_id
search_group_id
first_matched_at
last_matched_at
```

#### sponsorship_analysis

```text
job_id
status
confidence
evidence
matched_terms
classifier_version
analyzed_at
```

---

## 32. Recommended Technical Architecture

The PRD does not require one exact implementation stack, but the recommended architecture is:

```text
Frontend:
React
TypeScript

Backend:
FastAPI
Python

Scraping:
Playwright
HTML parsing library

Database:
SQLite

Future:
PostgreSQL
```

Preferred scraper architecture:

```text
HigherEdJobs Advanced Search
        ↓
Playwright
        ↓
Search Result HTML
        ↓
Result Parser
        ↓
Job URLs + Metadata
        ↓
Job Page Loader
        ↓
Job Parser
        ↓
Raw Description
        ↓
Sponsorship Classifier
        ↓
Database
        ↓
FastAPI
        ↓
React Dashboard
```

---

## 33. Avoid Excessive Browser Automation

The scraper should not simulate human behavior unnecessarily.

Bad approach:

```text
Open result
Scroll
Click job
Back
Scroll
Click job
Back
```

Preferred:

```text
Open result page
Extract every job URL
Process URLs directly
```

Playwright is used where browser execution is actually required.

---

## 34. Rate Limiting and Site Respect

The scraper should use conservative request behavior.

Requirements:

- avoid excessive parallel requests
- include small delays when appropriate
- cache existing jobs
- avoid repeatedly fetching unchanged jobs
- respect applicable site rules and access restrictions

The goal is efficient automation, not aggressive crawling.

---

## 35. Rescraping Strategy

Existing jobs should not always require full reprocessing.

Recommended logic:

```text
New Job
-> scrape full page
-> analyze sponsorship

Existing Job
-> check whether content changed
-> reprocess only if needed
```

This reduces load and runtime.

---

## 36. Search Run History

Each scrape should record:

```text
run_id
started_at
completed_at
queries_run
jobs_discovered
new_jobs
updated_jobs
errors
```

---

## 37. Manual Verification

Every sponsorship decision must be verifiable.

The dashboard must make it easy to:

1. inspect detected wording
2. expand the surrounding text
3. open the original HigherEdJobs page
4. open the employer page

The system should never imply that a classification is guaranteed.

---

## 38. V1 User Flow

```text
Open Dashboard
     ↓
Click Run All Searches
     ↓
Eight searches execute
     ↓
All results collected
     ↓
Duplicate jobs merged
     ↓
Descriptions analyzed
     ↓
Dashboard refreshes
     ↓
Filter Last 7 Days
     ↓
Review Sponsorship Status
     ↓
Open promising job
     ↓
Verify original listing
     ↓
Apply manually
     ↓
Mark Applied
```

---

## 39. Example Table

| Job Title | Institution | Location | Posted | Search Group | Sponsorship | Conf. | Evidence | Status | Links |
|---|---|---|---|---|---|---|---|---|---|
| Data Analyst | UNC | Chapel Hill, NC | Sep 14 | Data & Analytics | Not Worth It | High | “cannot provide H-1B sponsorship...” | New | HEJ ↗ |
| Programmer Analyst | Example University | Buffalo, NY | Sep 13 | Software Dev, University IT | No Mention | - | No relevant wording found | New | HEJ ↗ Apply ↗ |
| Web Developer | Example College | Boston, MA | Sep 12 | Web Development | Unsure | Medium | “must be legally authorized...” | Opened | HEJ ↗ |

---

## 40. V1 Acceptance Criteria

V1 is complete when all of the following work:

1. The system can run all eight predefined HigherEdJobs keyword searches.
2. Each query correctly populates the HigherEdJobs Keyword field.
3. The system traverses multiple result pages.
4. Jobs from all queries are combined into one dataset.
5. Duplicate jobs do not appear as duplicate rows.
6. Each job retains every search group that matched it.
7. Job title, institution, location, posting date, and URL are captured where available.
8. Individual job descriptions are retrieved.
9. Sponsorship-related language is detected.
10. The exact evidence sentence is preserved.
11. Explicit negative wording can produce `Not Worth It`.
12. Ambiguous wording produces `Unsure - Review`.
13. Missing sponsorship language produces `No Mention Found`.
14. Positive wording can produce `Sponsorship Possible`.
15. Every classification includes appropriate confidence.
16. All jobs appear in one table.
17. The table supports filtering by search group.
18. The table supports filtering by sponsorship status.
19. The table supports date filtering.
20. The table supports sorting.
21. Every job contains a HigherEdJobs verification link.
22. Employer application links are shown when available.
23. Application status can be changed.
24. Jobs remain stored between sessions.
25. Failed searches do not crash the entire run.
26. Previously seen jobs are deduplicated on later runs.

---

## 41. Future Enhancements

Not required for V1, but compatible with the design:

```text
Automatic scheduled daily scraping
Email digest
Push notifications
LLM fallback for ambiguous sponsorship wording
Job match score
Experience requirement extraction
Degree requirement extraction
Security clearance detection
Citizenship requirement detection
Salary normalization
Resume matching
Resume tailoring
Cover letter generation
Application deadline detection
Multiple job boards
Export CSV
Export Excel
Saved dashboard views
Analytics
Application funnel tracking
```

---

## 42. Product Principle

The system should optimize for:

```text
Find everything relevant
Keep everything visible
Explain why something was flagged
Make verification one click away
Reduce wasted application time
```

It should not silently remove opportunities simply because a classifier is uncertain.

The tool is a **job discovery and review assistant**, not an automatic decision-maker.
