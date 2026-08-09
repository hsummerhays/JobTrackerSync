# Changelog

All notable changes to this project are documented here.

## v1.3.2 — 2026-08-09

### Scoring & Priority Fixes
- **Utah detection hardened**: `is_utah` now uses word-boundary regex (`\b`) so strings like "Southlake" or "Sutter" never falsely match the two-letter state abbreviation `ut`. Salt Lake City, UT continues to score as local; Southlake, TX now correctly triggers the relocation penalty.
- **Priority follows recommendation**: `compute_priority` now unconditionally returns P4 for Skip/Low recommendations and P3 for Maybe, regardless of the job's `Action` field. Previously, `Action = Apply` could silently elevate a low-score job to P2.
- **Aggregator cap**: Jobs originating from `jobs.utah.gov`, `Ladders`, or any provider whose company name contains "DailySummary" / "DailyDigest" receive a 30-point fit-score penalty and are capped at ★★★☆☆ Maybe (P3). They can no longer flood the P1/P2 application queue.
- **Backup rotation**: `backup_file_if_exists` now keeps the most recent `MAX_BACKUPS_TO_KEEP` (3) backups instead of deleting all but the newest one. This prevents the first backup in a multi-file run from being erased before the run finishes.

### Parser Fixes
- **Email metadata leak**: The generic card parser now detects "Years Exp Required" (an Indeed email header) when it appears in the company-name position and skips back one more line to retrieve the true employer name. The `clean_company_name` hardcoded override has been removed; the fix now lives in the parser where it can apply to any future re-import of the same PDF.
- **Skill boundary matching**: Extracted `_skill_boundary_pattern()` helper so skills whose name begins or ends with punctuation (e.g. `.NET`, `C#`) use asymmetric lookarounds instead of the blanket `(?<![a-z0-9])` prefix that previously blocked matches like "ASP.NET".

### Bulk Rescoring
- **`--rescore` flag**: Running `python parse_jobs.py --rescore` recalculates fit score, priority, recommendation, matched/missing skills, and reason for every active job in `jobs.db` without re-parsing any PDFs. Manual fields (`tracker_status`, `notes`, `recruiter`, `hiring_manager`) are preserved.

### Regression Tests
- Added `tests/test_fix_regression_suite.py` with 6 targeted tests covering: Utah detection, aggregator cap, priority/action interaction, Vue alias normalisation, Porch Software metadata parsing, and `--rescore` idempotency plus field preservation.

### Agent Skills
- Added `.agents/skills/manage_config/`, `.agents/skills/deduplicate_jobs/`, and `.agents/skills/find_pdf/` skill directories.
- Added `create_calendar_event.py` and `run_sql.py` standalone helpers.

## v1.3.1 — 2026-08-05


### Data Integrity
- Deferred successful PDF processing records until SQLite and CSV writes complete.
- Prevented CSV updates following SQLite failures.
- Preserved Offer, Accepted, and other user-managed workflow states.
- Corrected expiration and relisting calculations using Last Seen.
- Repaired legacy aggregator occurrence fingerprints.

### Manual Jobs
- Added Last Seen, Fingerprint, Previous Job ID, and Source Index.
- Persisted manual status provenance as status_source='user'.

### Reliability
- Added unique microsecond backup names.
- Closed database connections on all final-write paths.
- Added regression coverage for SQLite failures, CSV failures, and processed-PDF state.

## v1.3.0 — 2026-08-05

### Audit & Architecture
- **Stable Identifiers & Audit Fields**: Transitioned to `uuid.uuid4().hex`-based (32-character hex) UUIDs for stable job tracking. Added `Last Seen`, `Fingerprint`, `Previous Job ID`, and `Source Index` to better track deduplication and source lineage.

### Deduplication Enhancements
- **Intelligent Relisting Windows**: Split relisting windows into two distinct behaviors:
  - 60-day reapplication window (measured from `Date Added`) for previously Applied/Interviewing roles.
  - 90-day general rediscovery window (measured from `Last Seen`) for all other roles to prevent persistent postings from artificially resetting their expiration.

### CLI & UI Improvements
- **Query Tool UI**: `query_jobs.py` now outputs `Last Seen` and converts `Source PDF:` lines into clickable Markdown `file:///` links while preserving the visible filename.
- Improved `query_jobs.py` output formatting: cleaner labels (`Source PDF` instead of `PDF`), em-dashes in titles, and regex-based position normalization (strips stray leading words).
- Made the `query` CLI argument in `query_jobs.py` optional — omitting it lists all tracked jobs.

### Bug Fixes
- Removed spammy "Also discovered on … via … .pdf on …" discovery notes that were being appended to the `Notes` field every time a job reappeared in a new PDF. Retroactively cleaned 379 affected historical records from `master_tracker.csv` and `jobs.db`.
- Fixed a resource leak: `_db_conn.close()` is now called when no PDF files are found in the selected directory.
- Added a blocklist to `is_valid_company()` to prevent known job aggregator/provider names (e.g. `Ladders`, `Indeed`, `LinkedIn`) from being incorrectly stored as employer names when they appear within the body of digest emails.
- Corrected 3 stale records in the database and CSV where `Ladders` had been incorrectly listed as the hiring company.

### Data Integrity
- **Strict deduplication pass**: Identified and physically deleted 15 exact-match duplicate rows (same normalized company, title, date, source PDF, and status) from both `master_tracker.csv` and `jobs.db`. Two groups were aggregator (`Jobs.utah.gov-DailySummary`) Expired entries; the others were Cancelled rows that had been missed by prior cleanup runs.
- Corrected Mitratech (`b7af764d5fd8`) status from `Cancelled` to `Applied / Waiting / Already Applied` after confirming application confirmation was received.

### Agent Skills & Workspace Rules
- Added workspace rules to `.agents/AGENTS.md` covering: deduplication safety (exact-match only, no aggregator trust), the mandatory dual-update rule (both CSV and DB must be updated together), workspace cleanliness (temporary files go in `scratch/`), and running tests before every commit.
- Updated all four agent skills (`db_query`, `sync_jobs`, `manage_jobs`, `git_manager`) to prefer existing helper scripts (`query_jobs.py`, `parse_jobs.py`), document the dual-update requirement, and enforce the `pytest`-first commit workflow.
- Added custom AI agent skills in `.agents/skills/` for `git_manager`, `sync_jobs`, `daily_dashboard`, `db_query`, `manage_jobs`, and `calendar_events`.

### Test Suite
- Added 7 new test modules covering: `clean_existing_tracker`, interactive CLI handlers, Ladders/generic parser gaps, main CLI, PDF/config utilities, `query_jobs.py`, and reporting.
- Expanded 5 existing test modules with additional cases for scoring, save_to_sqlite, company validation, find_pdf, and parse_jobs.

### Code Cleanup & Maintenance
- Extracted shared utility functions (`path_to_file_uri`, `split_multivalue_field`, `canonical_job_key`) into `dedup_utils.py` to reduce duplication across `find_pdf.py`, `parse_jobs.py`, and `query_jobs.py`.

## v1.2.8 — 2026-07-29

### New Features
- Added `query_jobs.py` as a permanent SQLite lookup utility for jobs.

## v1.2.7 — 2026-07-28

### Stability & Data Integrity
- Implemented atomic writes (`os.replace`) for all `master_tracker.csv` updates in `parse_jobs.py` to eliminate the risk of truncated files during interruptions.
- Fixed a `sqlite3.ProgrammingError` crash during the DB sync phase when a job reappeared and was being removed from the "Applied" or "Expired" buckets.
- Prevented Job ID collisions on re-listed jobs by always hashing `date_added` into the MD5 job identifier.
- Solidified status deduplication in `dedup_utils.py` by defining `TERMINAL_STATUSES` (e.g. Rejected, Ghosted). These sticky human-reviewed states are no longer silently overwritten by "Applied" just because "Applied" has a higher numerical ranking.
- Added a `locations_compatible` guard in the deduplication scripts to prevent distinct, clean locations from merging into one record and dropping data.
- Added automatic `.bak` backups before modifying the tracker file in `fix_duplicates.py` and `fix_duplicates_by_company.py`.

## v1.2.6 — 2026-07-28
### Core Enhancements & Fixes
- Fixed cross-platform generation of Windows absolute file URIs in `find_pdf.py` so they work correctly even when run on Linux hosts.
- Implemented fully symmetrical logic for deduplication status merging (`should_prefer_status`), ensuring that human-reviewed terminal statuses (e.g. Cancelled, Rejected) are never silently overwritten by unreviewed statuses regardless of merge order.
- Standardized the multi-value field delimiter to `|` across both the main parsing pipeline and cleanup scripts, safely migrating legacy `/` separated values without corrupting valid file paths.

### Code Cleanup & Maintenance
- Refactored `parse_jobs.py` to remove unused imports and improve sqlite3 connection handling (added robust try/finally blocks).
- Updated `requirements.txt` to pin dependencies (`pypdf`, `rich`, `pytest`) and conditionally support `easyocr`.
- Refactored test suite to separate core evaluation/cleanup tests from provider-specific parsers.

### Parser & Deduplication Fixes
- Fixed an offset bug in the LinkedIn PDF parser where job titles were incorrectly assigned the company and location of the subsequent job card when they shared the same line (e.g. `Company · Location`).
- Added regression tests targeting the LinkedIn PDF parser for company/location mapping.
- Cleaned up and deduplicated historical malformed records in the tracker, merging correct locations and preserving the most advanced job status.

### Search Utility Improvements
- Improved `find_pdf.py` search to use regex word boundaries, preventing short terms from falsely matching substrings embedded inside long URLs or IDs.

> Version note: No v1.1.x releases were published. Version numbering resumed at v1.2.2; the omitted numbers do not represent missing public releases.

## v1.2.2 — 2026-07-21

### Search Utility Improvements
- Enhanced `find_pdf.py` to query both the SQLite database (`jobs.db`) and the master tracking spreadsheet (`master_tracker.csv`) case-insensitively, returning consolidated matches from both sources.

### CLI Improvements
- Added support for non-interactive job addition (`--add`) using command-line arguments (e.g. `--company`, `--position`, `--location`, `--fit-score`, `--status`, `--notes`).
- Automatically detect interactive vs. non-interactive modes to bypass prompts and use default values when sufficient fields are supplied.
- Added `--update`, `--status`, and `--notes` CLI options to enable updating any job's tracking status directly from the command line.
- Automatic recalculation of derived workflow attributes (e.g. `Review Status`, `Action`, `Disposition`) upon status updates.
- Synchronized database records and master tracking spreadsheet outputs on CLI status updates.

### Parser & Board Integrations
- Implemented dedicated layout-aware text parsers for **jobs.utah.gov** (Utah's Daily Job Summary) and **Ladders** daily digest email PDFs.
- Standardized parser extraction to use source-specific company markers: `Jobs.utah.gov-DailySummary` and `Ladders-DailyDigest`.
- Cleaned email subject line/notification artifacts (e.g. `Jobs at Brady Corporation` ➔ `Brady Corporation`) from extracted company names.
- Excluded email headers (e.g. `Your job listings for [Date]`, `job summary`) from valid company name candidates.
- Implemented wrapped LinkedIn title detection to prevent multiline job titles from splitting into incorrect company names.
- Normalized whitespace surrounding commas in job locations to resolve OCR/text-extraction spacing artifacts.

### Deduplication & Reconciliation
- Implemented **CanonicalKey Deduplication & Merging**: Groups identical opportunities by `normalize(employer) + normalize(position) + normalize(location)` within a 90-day window.
- Rather than discarding duplicates, the system now merges metadata across multiple discovery job boards and source PDF documents (slash-separating values) and appends a chronological discovery trail to `Notes`.
- Added logic to automatically re-suggest jobs that were previously marked as "Expired" if they return on a different day.
- Clears the historical "Expired" status from the SQLite database (`jobs` and `job_workflow` tables) and re-evaluates the role as a new job recommendation.
- Prevents immediate same-day re-suggestions of active expired jobs to avoid duplicate alerts during consecutive runs on the same day.
- Allow identical jobs (same Company + Position + Location) to be re-imported as new opportunities after 90 days.
- Appended `Date Added` to the MD5 hash for re-imported older opportunities to generate unique Job IDs and avoid primary key collisions in the SQLite database.

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

### Parser & Company Name Validation
- Blacklisted "just posted" (case-insensitive) to prevent UI posting timestamps from being extracted as company names.
- Blacklisted exactly "systems" (case-insensitive) to filter out suspicious, truncated company name extraction artifacts.
- Added validation rules to reject Indeed recommendation banners (e.g. "Based on your title and location. Update", "Recommended for you", "Update your profile").
- Added validation rules to reject digest/truncation artifacts at the end of company names (e.g. ending in "...", "more ...", "view more", "see more").

### Persistent User Workflow & DB Schema Separation
- Introduced a separate `job_workflow` table in SQLite (`jobs.db`) to store user-managed workflow state (`tracker_status`, `review_status`, `action`, `disposition`, `updated_at`, `updated_by`, `notes`, `follow_up_date`, `last_contact_date`) independently from the main `jobs` list.
- User-managed workflow state now persists in SQLite even if the imported `jobs` table list is cleared or recreated.
- Implemented automatic database migration to dynamically transition old `job_status` tables to the expanded `job_workflow` structure.
- Upsert logic only modifies `updated_at` and `updated_by` when any tracking status, review status, action, or disposition changes, preventing overwrite of user-managed fields like `notes` and `follow_up_date` during routine PDF imports.
- Re-ordered synchronization so that restored workflow states are written back to `master_tracker.csv` on run.

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

## v0.9.x — 2026-06 (Pre-release iterations)

- Initial PDF parser for ZipRecruiter, LinkedIn, Glassdoor job alerts
- CSV export with basic company/position/location extraction
- Configurable resume skill matching via `config.json`
- SQLite sync introduced
- Git repository initialized and pushed to GitHub
