# Changelog

All notable changes to this project are documented here.

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
