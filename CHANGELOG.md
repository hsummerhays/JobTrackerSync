# Changelog

All notable changes to this project are documented here.

## v1.2.1 — 2026-07-11

### CLI Improvements
- Added support for non-interactive job addition (`--add`) using command-line arguments (e.g. `--company`, `--position`, `--location`, `--fit-score`, `--status`, `--notes`).
- Automatically detect interactive vs. non-interactive modes to bypass prompts and use default values when sufficient fields are supplied.

---

## v1.2.0 — 2026-07-10

### Parser & Board Integrations
- Implemented dedicated layout-aware text parsers for **jobs.utah.gov** (Utah's Daily Job Summary) and **Ladders** daily digest email PDFs.
- Standardized parser extraction to use source-specific company markers: `Jobs.utah.gov-DailySummary` and `Ladders-DailyDigest`.
- Cleaned email subject line/notification artifacts (e.g. `Jobs at Brady Corporation` ➔ `Brady Corporation`) from extracted company names.
- Excluded email headers (e.g. `Your job listings for [Date]`, `job summary`) from valid company name candidates.

### Deduplication & Reconciliation
- Implemented **CanonicalKey Deduplication & Merging**: Groups identical opportunities by `normalize(employer) + normalize(position) + normalize(location)` within a 90-day window.
- Rather than discarding duplicates, the system now merges metadata across multiple discovery job boards and source PDF documents (slash-separating values) and appends a chronological discovery trail to `Notes`.

### Traceability & Audit Logs
- Added deterministic sequential **Source Index Tracing** (e.g. `Source Index: 2-17` representing the 17th job card extracted from the 2nd sorted PDF processed in the folder), prepended to the `Notes` field.
- PDF file discovery is now sorted alphabetically before iteration to ensure stable source indexing across sync runs.

### Confidence & Recommendation Algorithm
- Shifted Confidence to a **numeric percentage** representation representing metadata accuracy:
  - `100%`: Direct employer posting + URL available.
  - `90%`: Company identified + URL missing.
  - `70%`: Company name inferred from context.
  - `40%`: Daily digest / summary email listing (Utah Jobs and Ladders).
  - `20%`: OCR fallback with sparse content.
- Updated recommendation rules and `should_recommend` logic to parse and evaluate these numeric confidence values.

### CLI & UI Improvements
- Fixed Tkinter directory selection lockups on Windows by adding `root.update()`.
- Implemented clean exit (`sys.exit(0)`) if the user explicitly cancels or closes the GUI folder dialog.
- Headless console directory selection prompt is bypassed if a valid default directory exists in `config.json`.

---

## v1.1.3 — 2026-07-06

### Parser & Company Name Validation
- Blacklisted "just posted" (case-insensitive) to prevent UI posting timestamps from being extracted as company names.
- Blacklisted exactly "systems" (case-insensitive) to filter out suspicious, truncated company name extraction artifacts.

### Deduplication & Re-suggestion Logic
- Added logic to automatically re-suggest jobs that were previously marked as "Expired" if they return on a different day.
- Clears the historical "Expired" status from the SQLite database (`jobs` and `job_workflow` tables) and re-evaluates the role as a new job recommendation.
- Prevents immediate same-day re-suggestions of active expired jobs to avoid duplicate alerts during consecutive runs on the same day.

---

## v1.1.2 — 2026-07-03

### CLI Status Updates
- Added `--update`, `--status`, and `--notes` CLI options to enable updating any job's tracking status directly from the command line.
- Automatic recalculation of derived workflow attributes (e.g. `Review Status`, `Action`, `Disposition`) upon status updates.
- Synchronized database records and master tracking spreadsheet outputs on CLI status updates.

### Parser Improvements
- Implemented wrapped LinkedIn title detection to prevent multiline job titles from splitting into incorrect company names.
- Normalized whitespace surrounding commas in job locations to resolve OCR/text-extraction spacing artifacts.
- Added unit tests for title wrapping in `test_linkedin_parser.py`.

---

## v1.1.1 — 2026-07-02

### Company Name Validation
- Added validation rules to reject Indeed recommendation banners (e.g. "Based on your title and location. Update", "Recommended for you", "Update your profile").
- Added validation rules to reject digest/truncation artifacts at the end of company names (e.g. ending in "...", "more ...", "view more", "see more").
- Added unit tests for new validation rules in `test_company_validation.py`.

---

## v1.1.0 — 2026-06-30

### Persistent User Workflow & DB Schema Separation
- Introduced a separate `job_workflow` table in SQLite (`jobs.db`) to store user-managed workflow state (`tracker_status`, `review_status`, `action`, `disposition`, `updated_at`, `updated_by`, `notes`, `follow_up_date`, `last_contact_date`) independently from the main `jobs` list.
- User-managed workflow state now persists in SQLite even if the imported `jobs` table list is cleared or recreated.
- Implemented automatic database migration to dynamically transition old `job_status` tables to the expanded `job_workflow` structure.
- Upsert logic only modifies `updated_at` and `updated_by` when any tracking status, review status, action, or disposition changes, preventing overwrite of user-managed fields like `notes` and `follow_up_date` during routine PDF imports.
- Re-ordered synchronization so that restored workflow states are written back to `master_tracker.csv` on run.

---

## v1.0.1 — 2026-06-29

### Deduplication
- Allow identical jobs (same Company + Position + Location) to be re-imported as new opportunities after 90 days.
- Appended `Date Added` to the MD5 hash for re-imported older opportunities to generate unique Job IDs and avoid primary key collisions in the SQLite database.

---

## v1.0.0 — 2026-06-29

Feature-complete initial release.

### Core Pipeline
- PDF extraction via `pdfplumber` with `pytesseract` OCR fallback for image-only PDFs
- Glassdoor reverse-layout parsing (location follows title — parser dynamically pivots)
- Deterministic Job ID via MD5 hash of Company + Position + Location (stable dedup across daily imports)
- Idempotent re-scoring — all existing rows recalculated on every sync run

### Scoring & Classification
- Fit Score (0–100) across 7 weighted criteria: location, seniority, tech stack, company size, degree, legacy modernization, local/onsite restriction
- `.NET`/`C#` prioritized over Java-only roles (20 pts vs 10 pts)
- Operations role penalty (−15 pts) to keep engineering roles ranked above operations management
- Company type detection: Recruiting Firm, Consulting, Defense, Healthcare, Financial, Enterprise, Small/Medium
- Local/onsite restriction detection: −30 pts + reason flag
- Priority standardized to descriptive en-dash format: `P1 – Apply today` … `P4 – Ignore`

### Actions & Workflow
- `Contact Recruiter` reserved for actual recruiting firm companies (checked by company name only, not description)
- Stale `Contact Recruiter` action corrected on re-sync for non-recruiting-firm companies
- Tracker Status pipeline: New → Applied → Phone Screen → Technical Interview → Recruiter Submitted → Waiting → Rejected / Cancelled / Ghosted

### Data Model
- `Age (days)` computed column — recalculated fresh from `Date Added` on every run
- `Existing Company` column — flags same employer already tracked (replaces `Already in Tracker`)
- `Reason` — short user-facing explanation (e.g., `Remote + .NET + small company`)
- `Notes` — parser-generated analyst comments

### Persistence
- Dual persistence: `master_tracker.csv` (human-editable) + `jobs.db` (SQLite, queryable)
- Schema auto-migration in `clean_existing_tracker` — older CSV rows upgraded on every run

### Company Validation
- Rejects location-only company names (city/state strings, state abbreviation suffixes)
- Rejects UI element strings: `View Details`, `Learn More`, `Apply Now`, `Easy Apply`, `Save Job`, `Show More`
- Rejects placeholder names: `Unknown`, `Undisclosed`, sentences, strings >7 words

### CLI Output
- Sync report with jobs tracked, new this run, priority breakdown (P1–P4), applied/closed counts, and top missing skills
- Application pipeline dashboard: Active Pipeline, New Opportunities, Closed/History
- New job recommendations table sorted by Fit Score

### Documentation
- `README.md` — setup, usage, features
- `docs/architecture.md` — pipeline diagram, data model, design decisions
- `docs/scoring.md` — full scoring table, priority/action rules, Reason vs Notes distinction
- `config.json.example` and `master_tracker.csv.example` for clean-install setup

---

## v0.9.x — 2026-06 (Pre-release iterations)

- Initial PDF parser for ZipRecruiter, LinkedIn, Glassdoor job alerts
- CSV export with basic company/position/location extraction
- Configurable resume skill matching via `config.json`
- SQLite sync introduced
- Git repository initialized and pushed to GitHub
