# Architecture

JobTrackerSync is a local-first Python CLI tool that ingests job alert PDFs, scores them against a configurable resume profile, and keeps a persistent CSV + SQLite master tracker in sync.

---

## Pipeline Overview

```
PDF Alerts (Gmail / Glassdoor / LinkedIn)
        │
        ▼
  parse_jobs.py
        │
        ├─ 1. PDF Extraction      (pdfplumber)
        │       └─ Raw text per page
        │
        ├─ 2. Job Card Parsing    (parse_job_cards_from_text)
        │       └─ Company, Title, Location, URL
        │
        ├─ 3. Validation          (is_valid_company)
        │       └─ Rejects location-only names, sentences, etc.
        │
        ├─ 4. Deduplication       (CanonicalKey = normalize(employer) + normalize(position) + normalize(location))
        │       └─ Merges metadata (multiple job boards and PDF sources) into the existing record if matched within 90 days. Non-duplicate listings generate a fresh, permanent 12-char UUID as their Job ID.
        │
        ├─ 5. Evaluation          (evaluate_job)
        │       ├─ Fit Score (0-100)
        │       ├─ Recommendation (1-5 stars)
        │       ├─ Priority (P1 - P4)
        │       ├─ Action (Apply / Contact Recruiter / Review / Ignore)
        │       ├─ Company Type
        │       ├─ Matched / Missing Skills
        │       ├─ Source Index Trace (e.g. 2-17 prepended to Notes)
        │       └─ Reason (human-readable summary)
        │
        ├─ 6. Existing Tracker Migration  (clean_existing_tracker)
        │       └─ Re-scores all existing rows on every run
        │           so resume changes propagate automatically
        │
        ├─ 7. Merge & Sort
        │       └─ New + existing rows sorted by Fit Score desc
        │
        ├─ 8. Workflow Restore & SQLite Sync (save_to_sqlite -> jobs.db)
        │       └─ Restores persisted workflow state from job_workflow
        │
        └─ 9. CSV Write           (master_tracker.csv)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `parse_jobs.py` | Main CLI entry point and all pipeline logic |
| `find_pdf.py` | Database and CSV search utility for PDFs and jobs |
| `query_jobs.py` | Permanent SQLite lookup utility for jobs |
| `dedup_utils.py` | Shared status-ranking, merge, and file-URI helpers used by the above |
| `config.json` | Resume skills, job type criteria, keyword weights |
| `config.json.example` | Template for new installations |
| `master_tracker.csv` | Primary working spreadsheet (git-ignored) |
| `master_tracker.csv.example` | Schema reference committed to git |
| `jobs.db` | SQLite mirror containing `jobs` and `job_workflow` tables (git-ignored) |
| `docs/scoring.md` | Scoring algorithm documentation |
| `docs/screenshots/` | CLI and CSV screenshots for README |

---

## Data Model

Each job record in the main `jobs` table carries these fields:

| Field | Description |
|-------|-------------|
| `Job ID` | Stable 12-char UUID generated once and never recalculated |
| `Fingerprint` | Normalized canonical key (company + title + location) used for deduplication |
| `Previous Job ID` | Links a newly created tracker record to an older record if re-listed outside the window |
| `Review Status` | Workflow state: New, Applied, Imported, Closed |
| `Job Type` | Software Engineer or Operations (drives scoring criteria) |
| `Company` | Extracted company name (cleaned of subject/email subject formatting artifacts) |
| `Position` | Job title |
| `Location` | City/State or "Remote" |
| `URL` | Direct application link when available |
| `Provider` | Source board (Glassdoor, LinkedIn, etc., slash-separated if discovered on multiple) |
| `Source PDF` | Original filename for traceability (slash-separated if discovered on multiple) |
| `Confidence` | Percentage value representing metadata accuracy (100%, 90%, 70%, 40%, 20%) |
| `Fit Score` | 0-100 numeric score |
| `Priority` | P1 - Apply today ... P4 - Ignore |
| `Company Type` | Recruiting Firm / Consulting / Defense / Healthcare / Financial / Enterprise / Small/Medium |
| `Recommendation` | 1-5 stars (Skip to Apply Now) |
| `Tracker Status` | New, Applied, Phone Screen, Technical Interview, Recruiter Submitted, Waiting, Rejected, Cancelled, Ghosted |
| `Disposition` | Free-text outcome notes |
| `Action` | Apply, Contact Recruiter, Review, Already Applied, Ignore |
| `Existing Company` | Yes/No -- same employer already in tracker |
| `Reason` | Short human-readable explanation of the recommendation |
| `Matched Skills` | Resume keywords found in the posting |
| `Missing Skills` | Desired keywords not found |
| `Date Added` | ISO date first seen |
| `Notes` | Parser-generated analyst comments |

### Persistent User Workflow Table (`job_workflow`)

To ensure user-managed workflow state is never lost even if the main `jobs` table list is cleared, we maintain a separate `job_workflow` table:

| Column | Type | Description |
|--------|------|-------------|
| `job_id` | TEXT PRIMARY KEY | Relates to the unique `Job ID` |
| `tracker_status` | TEXT | Current workflow status (e.g. Applied, Rejected) |
| `review_status` | TEXT | Review status (e.g. Imported, Applied, Closed) |
| `action` | TEXT | Current action (e.g. Apply, Contact Recruiter) |
| `disposition` | TEXT | Free-text outcome/disposition |
| `updated_at` | TEXT | ISO timestamp when the workflow was last changed |
| `updated_by` | TEXT | Who changed it (e.g. `'system'` or a user name) |
| `notes` | TEXT | Custom user notes (preserved on import) |
| `follow_up_date` | TEXT | User-managed follow up date (preserved on import) |
| `last_contact_date` | TEXT | User-managed last contact date (preserved on import) |
| `status_source` | TEXT | Origin of the status ('user', 'system', 'migration') to prevent parser overrides of manual states |

---

## Workflow Synchronization

Parsed job attributes (company, title, location, score, recommendation) are treated as derived data and may be regenerated at any time. User-managed workflow attributes (status, notes, follow-up dates, contact history, etc.) are stored independently in `job_workflow` and restored after every synchronization. This separation allows parser improvements and rescoring without losing user history.

---

## Configuration (config.json)

```json
{
  "job_type_criteria": {
    "Software Engineer": {
      "resume_skills": [".net", "c#", "azure", "sql", "react"],
      "priority_keywords": ["senior", "lead", "principal"],
      "tech_keywords": [".net", "c#", "java", "python"]
    },
    "Operations": {}
  }
}
```

Resume skill lists drive both skill matching and fit scoring. Editing `config.json` and re-running the sync will automatically re-score all existing rows.

---

### Company Validation

To protect data integrity from extraction artifacts, the `is_valid_company` function enforces several rules:
- Rejects location-only company names (city/state strings, state abbreviation suffixes).
- Rejects UI element strings: `View Details`, `Learn More`, `Apply Now`, `Easy Apply`, `Save Job`, `Show More`.
- Rejects placeholder names: `Unknown`, `Undisclosed`, sentences, strings >7 words.
- Rejects job board aggregator names: `Ladders`, `Indeed`, `LinkedIn`, `ZipRecruiter`, `Actively recruiting` (prevents them from being misidentified as employers in digest emails).

---

## Known Parsing Challenges

Job alert PDFs are semi-structured documents, not stable APIs. The parser is designed around repeatable provider patterns, but it also expects messy extraction artifacts:

- Providers format job cards differently, including title-first and company-first layouts.
- Some alerts concatenate card UI text, such as `View Details` or `1-Click Apply`, into company or location fields.
- Indeed recommendation banners (e.g., `Based on your title and location. Update`, `Recommended for you`) or digest artifacts (e.g., ending in `...`, `more ...`, `view more`, `see more`) can leak into company names.
- Adjacent cards can bleed together when extracted text loses visual boundaries.
- OCR is only used when embedded PDF text is unavailable.
- Some providers require reverse-layout parsing because the company can appear before the title.

These cases are covered incrementally with parser regression tests so provider-specific fixes do not break existing layouts.

---

## Design Decisions

- **Local-first**: No cloud dependency. All data stays on disk.
- **Idempotent**: Re-running the sync is safe -- existing rows are re-scored but never duplicated.
- **Git-ignored secrets**: `config.json`, `master_tracker.csv`, and `jobs.db` are excluded from version control. Templates are committed instead.
- **Stable Tracking Architecture**: The discovery hash identifies a particular parsed occurrence. The deduplication engine associates that occurrence with a stable tracker record (UUID) via fingerprint matching when it represents an existing job. Listings outside the relisting window receive a new tracker record with a new stable ID, optionally linked to the earlier record as a relisting.
- **Persistent User State separation**: Separating user-edited attributes (like workflow status, review status, actions, notes, and dates) into the `job_workflow` table isolates imported raw data from user modifications, operating like a clean production sync engine. Manual status updates are stamped with `status_source = 'user'` to protect them from being downgraded by the parser.
- **Schema migration**: `clean_existing_tracker` auto-upgrades older CSV rows to the current schema on every run, and SQLite schema migrations are applied dynamically to add new user-state columns if they are missing.
- **Single shared-helpers module**: `dedup_utils.py` holds both generic helpers (`normalize_string`, `path_to_file_uri`, `split_multivalue_field`) and dedup-specific ones (`canonical_key`, `merge_delimited_field`, status ranking) in one file rather than splitting into `utils.py` + `dedup.py`. At its current size (~140 lines, 3 consumers) a split would mostly add import indirection -- `dedup.py` would immediately import `normalize_string` from `utils.py` anyway -- without making anything easier to find. Revisit if the module keeps growing or a script needs the generic helpers without the dedup-specific logic.
