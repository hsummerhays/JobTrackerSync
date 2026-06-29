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
        ├─ 4. Deduplication       (job_id = MD5 of company+title+location)
        │       └─ Skips jobs already in master_tracker.csv
        │
        ├─ 5. Evaluation          (evaluate_job)
        │       ├─ Fit Score (0-100)
        │       ├─ Recommendation (1-5 stars)
        │       ├─ Priority (P1 - P4)
        │       ├─ Action (Apply / Contact Recruiter / Review / Ignore)
        │       ├─ Company Type
        │       ├─ Matched / Missing Skills
        │       └─ Reason (human-readable summary)
        │
        ├─ 6. Existing Tracker Migration  (clean_existing_tracker)
        │       └─ Re-scores all existing rows on every run
        │           so resume changes propagate automatically
        │
        ├─ 7. Merge & Sort
        │       └─ New + existing rows sorted by Fit Score desc
        │
        ├─ 8. CSV Write           (master_tracker.csv)
        │
        └─ 9. SQLite Sync         (save_to_sqlite -> jobs.db)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `parse_jobs.py` | Main CLI entry point and all pipeline logic |
| `config.json` | Resume skills, job type criteria, keyword weights |
| `config.json.example` | Template for new installations |
| `master_tracker.csv` | Primary working spreadsheet (git-ignored) |
| `master_tracker.csv.example` | Schema reference committed to git |
| `jobs.db` | SQLite mirror of the tracker (git-ignored) |
| `docs/scoring.md` | Scoring algorithm documentation |
| `docs/screenshots/` | CLI and CSV screenshots for README |

---

## Data Model

Each job record carries these fields:

| Field | Description |
|-------|-------------|
| `Job ID` | MD5 hash of company + title + location (stable dedup key) |
| `Review Status` | Workflow state: New, Applied, Imported, Closed |
| `Job Type` | Software Engineer or Operations (drives scoring criteria) |
| `Company` | Extracted company name |
| `Position` | Job title |
| `Location` | City/State or "Remote" |
| `URL` | Direct application link when available |
| `Provider` | Source board (Glassdoor, LinkedIn, etc.) |
| `Source PDF` | Original filename for traceability |
| `Confidence` | High / Medium / Low |
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

## Known Parsing Challenges

Job alert PDFs are semi-structured documents, not stable APIs. The parser is designed around repeatable provider patterns, but it also expects messy extraction artifacts:

- Providers format job cards differently, including title-first and company-first layouts.
- Some alerts concatenate card UI text, such as `View Details` or `1-Click Apply`, into company or location fields.
- Adjacent cards can bleed together when extracted text loses visual boundaries.
- OCR is only used when embedded PDF text is unavailable.
- Some providers require reverse-layout parsing because the company can appear before the title.

These cases are covered incrementally with parser regression tests so provider-specific fixes do not break existing layouts.

---

## Design Decisions

- **Local-first**: No cloud dependency. All data stays on disk.
- **Idempotent**: Re-running the sync is safe -- existing rows are re-scored but never duplicated.
- **Git-ignored secrets**: `config.json`, `master_tracker.csv`, and `jobs.db` are excluded from version control. Templates are committed instead.
- **MD5 dedup key**: Stable across runs so manually-annotated rows (Tracker Status, Disposition, Notes) are always preserved.
- **Schema migration**: `clean_existing_tracker` auto-upgrades older CSV rows to the current schema on every run.
