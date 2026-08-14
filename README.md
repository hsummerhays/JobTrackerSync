# JobTrackerSync

`JobTrackerSync` is a local-first Python CLI tool that processes batches of PDF job alerts (from ZipRecruiter, LinkedIn, Glassdoor, Indeed, etc.), scores them against a configurable resume profile, and synchronizes results into a master CSV spreadsheet and SQLite database.

---

## Motivation

During a software engineering job search, I found myself reviewing hundreds of duplicate job alerts every week from multiple providers. `JobTrackerSync` automates extraction, normalization, scoring, and tracking so I can focus on evaluating opportunities instead of managing spreadsheets.

---

## How It Works

PDFs are parsed → jobs extracted → validated → scored → deduplicated → written to CSV and SQLite.

See **[docs/architecture.md](docs/architecture.md)** for the full pipeline diagram, data model, and design decisions.

---

## Output

Each run prints a sync report followed by a live pipeline health summary and application pipeline dashboard:

```text
=========================================
          JOB TRACKER SYNC REPORT
=========================================
Jobs tracked:        199
New this run:        18

P1 – Apply today:     4
P2 – Apply this week: 39
P3 – Investigate:     36
P4 – Ignore:          95

Applied:             6
Closed:              18
Need review:         24

Top Missing Skills:
  React (8 roles)
  Docker (5 roles)
=========================================

=========================================
            PIPELINE HEALTH
=========================================
Tracked:               199
Active:                181
Applied:                 6
Interviewing:            1
Closed:                 18

Application Rate:      3.0%
Interview Rate:       14.3% (1 of 7 active applications)
=========================================

=========================================
          APPLICATION PIPELINE
=========================================
Active Pipeline
  Phone Screen:         0
  Technical Interview:  1
  Recruiter Contact:    1
  Waiting:              0

New Opportunities
  P1 – Apply Today:     4
  P2 – Apply This Week: 39
  P3 – Investigate:     36

Closed / History
  Applied (Pending):    3
  Rejected:             1
  Cancelled:            0
  Ghosted:              0
=========================================
```

New job recommendations are then printed in a sorted table (Fit Score descending).

---

## Scoring

Fit Score is a 0–100 weighted sum across criteria including location, seniority, tech stack, company size, and local/onsite restrictions.

See **[docs/scoring.md](docs/scoring.md)** for the full scoring table, Priority and Action rules, and the Reason vs. Notes field distinction.

---

## Features

- **Pipeline Health Dashboard**: Real-time conversion metrics including Application Rate and Interview Rate to track process trends over time.
- **Robust PDF extraction** with pytesseract OCR fallback for image-only PDFs
- **Glassdoor reverse-layout parsing** — handles alert formats where location follows the title
- **Stable Tracking Architecture**: Tracker records use stable, permanently generated UUIDs. Fingerprint-based deduplication (Company + Position + Location) associates newly parsed occurrences with existing tracker records if found within the relisting window, preserving historical application states without relying on unstable hashes.
- **Exact-match deduplication safety**: Rows are only merged or cancelled when the normalized company, title, date, source PDF, and status are all identical. Generic aggregator labels (e.g. `Jobs.utah.gov-DailySummary`) are never trusted as employer identities for merging.
- **Idempotent re-scoring** — editing `config.json` and re-running automatically recalculates all historic rows. Run `python parse_jobs.py --rescore` to recalculate scores for all active jobs without re-parsing any PDFs.
- **Aggregator queue protection** — jobs sourced from digest providers (`jobs.utah.gov`, Ladders, DailySummary) receive a 30-point penalty and are capped at ★★★☆☆ Maybe (P3) so they never flood the P1/P2 application queue.
- **Company type detection** — classifies Recruiting Firm, Consulting, Defense, Healthcare, Financial, Enterprise, or Small/Medium from the company name
- **Local/onsite warnings** — 30-point deduction when postings contain "local candidates", "onsite only", "must relocate", or "no remote"
- **Persistent workflow state** — Parsed job data is regenerated on every sync while user-managed workflow state (status, notes, actions, follow-up dates, etc.) is preserved independently in SQLite and restored automatically during imports.

---

## Parser Improvements

- OCR spacing normalization
- Multi-job email support
- Persistent workflow synchronization
- Wrapped LinkedIn title detection
- Company/location normalization
- Provider-specific metadata filtering

---

## File Structure

```
JobTrackerSync/
├── parse_jobs.py              # Main CLI entry point and full pipeline
├── find_pdf.py                # Database and CSV search utility for PDFs and jobs
├── query_jobs.py              # Permanent SQLite lookup utility for jobs
├── dedup_utils.py             # Shared status-ranking, merge, and file-URI helpers
├── run_sql.py                 # Ad-hoc read-only SQL helper (used by db_query skill)
├── create_calendar_event.py   # Generates pre-filled Google Calendar event links
├── config.json                # Resume skills and scoring criteria (git-ignored)
├── config.json.example        # Template for new installations
├── master_tracker.csv         # Master tracking spreadsheet (git-ignored)
├── master_tracker.csv.example # Schema reference
├── jobs.db                    # SQLite mirror (git-ignored)
├── scratch/                   # Temporary one-off scripts (not committed)
└── docs/
    ├── architecture.md        # Pipeline diagram, data model, design decisions
    ├── scoring.md             # Scoring algorithm reference
    ├── stabilization_baseline.md # Recovery baseline documentation and snapshot guide
    └── screenshots/           # CLI and spreadsheet screenshots
```

---

## Setup & Usage

**1. Install dependencies**

```bash
pip install pdfplumber pytesseract rich pytest pypdf
```

**2. Copy and configure**

```bash
cp config.json.example config.json
# Edit config.json to add your resume skills and preferences
```

**3. Run**

```bash
python parse_jobs.py --pdf-dir "C:\Path\To\Your\PDF\Folder"
```

**4. Update Job Status**

You can update any job's tracking status directly from the command line by providing the company name (or a unique substring/Job ID) and the new status:

```bash
python parse_jobs.py --update "Hire Feed" --status "Expired"
```

This will automatically find the matching job, update the database and CSV, and recalculate all derived fields (such as `Review Status`, `Action`, and `Disposition`).

**5. Manually Add Jobs**

You can add a new job to the tracker manually. Run the command without arguments to start the interactive prompt, or provide arguments for a non-interactive addition:

```bash
# Interactive mode
python parse_jobs.py --add

# Non-interactive mode (requires at least --company and --position)
python parse_jobs.py --add --company "Example Corp" --position "Software Engineer" --location "Remote" --status "New" --notes "First contact"
```

**6. Search PDF & Job Records**

You can quickly query both the SQLite database and the CSV tracker to locate all jobs, processed files, or CSV entries matching a specific term (like a company name, position, or PDF filename):

```bash
python find_pdf.py "<search_term>"
```

**7. Permanent SQLite Lookup Utility**

You can query the SQLite database directly for jobs matching a specific company using the `query_jobs.py` utility. This provides a quick, human-readable summary of matched jobs directly in your terminal. If you omit the query string, it will list all tracked jobs:

```bash
# Query for a specific company
python query_jobs.py "Company Name"

# List all tracked jobs
python query_jobs.py
```

**8. View Dashboards & Analytics**

```bash
# Today's P1/P2 action queue + active pipeline
python parse_jobs.py --dashboard

# Compact apply-now list only
python parse_jobs.py --today

# Full analytics: conversion rates, weekly volume, funnel metrics
python parse_jobs.py --analytics
```

**9. Bulk Rescore After Config Changes**

After updating `config.json` (e.g., adding a new resume skill or alias), recalculate scores for all active jobs without re-parsing any PDFs:

```bash
python parse_jobs.py --rescore
```

Manual fields (`Tracker Status`, `Notes`, `Recruiter`, `Hiring Manager`) are preserved.

**10. Running Tests**

Run the complete test suite using `pytest`:

```bash
python -m pytest tests/ -v
```

**11. AI Agent Integration**

This project includes built-in AI agent skills (located in `.agents/skills/`) to automate common workflows using AI assistants:

- **`git_manager`**: Streamlines daily git commits, squashing, and pushing. Always runs `pytest` before committing.
- **`sync_jobs`**: Automates the parsing pipeline (opens a folder picker or accepts `--pdf-dir`).
- **`daily_dashboard`**: Displays formatted analytics and action queues.
- **`db_query`**: Looks up jobs via `query_jobs.py`; falls back to raw SQL for ad-hoc analysis.
- **`manage_jobs`**: Adds new jobs or updates the status of existing ones via the CLI.
- **`calendar_events`**: Generates pre-filled Google Calendar links for interviews.
- **`find_pdf`**: Locates and links PDF source files by filename or substring.
- **`manage_config`**: Safely reads and updates `config.json` (skills, aliases, tech keywords).
- **`deduplicate_jobs`**: Identifies and safely collapses physical duplicate rows.
- **`update_docs`**: Reviews and updates all project documentation (.md files, agent skills, AGENTS.md).

Workspace rules are defined in `.agents/AGENTS.md` and cover deduplication safety, mandatory dual-update (CSV + DB), temp file hygiene, and the test-before-commit policy. To persist new rules, use the `/learn` command.

**12. Deduplicate Physical Rows**

Find and safely combine exact physical duplicate rows in the tracker (e.g., missed during manual edits or parsing overlaps):

```bash
python parse_jobs.py --dedup-physical
```

---

## Technical Highlights

Built a Python application that extracts job postings from PDFs using native text extraction with OCR fallback, scores opportunities against configurable resume profiles, deduplicates postings across multiple job boards, and synchronizes results into a master CSV and SQLite database for workflow management.

---

## Interesting Findings

JobTrackerSync reconstructs job postings from PDF layout rather than relying on filenames or simple text searches. During development, it successfully extracted job cards from Gmail-generated PDF digests that were not found using Windows Search or raw PDF text searches, highlighting the value of layout-aware parsing for semi-structured documents.

Indeed digest emails frequently contain multiple independent job cards, even though the email subject and PDF filename reference only the primary listing. For example, a digest named after a Foureyes position also contained a Planetary Talent Senior Backend .NET Developer opportunity on page two. JobTrackerSync identified both jobs as separate opportunities and added them independently to the tracker.

This discovery reinforced an important architectural principle: job providers often package multiple independent opportunities into a single document. Treating each detected job card as a separate record produced a more accurate and resilient synchronization pipeline.

---

## Future Roadmap

The roadmap focuses on making parsed data more actionable and improving workflow visibility.

### 1. Polish and Reliability

- [x] **More unit tests** around parsing and merge logic. _(439 tests across 25 modules as of v1.3.6)_
- [ ] **Better logging** for unexpected PDFs.
- [ ] **Continue reducing edge cases** and normalizing layout extraction.
- [ ] **Batch Database Writes**: Wrap updates in single, large transactions to speed up SQLite updates on large directory trees.
- [ ] **Pipeline Parallelism**: Refactor parser into a pipeline separating file discovery, PDF extraction (bounded worker pools to prevent Windows hangs), normalization, single-stage deduplication, and database writing.

### 2. Analytics Dashboard

- [ ] **Best sources by conversion**: Compare response, interview, and offer rates by source job board (Indeed, LinkedIn, Glassdoor, etc.).
- [ ] **Applications by week**: Weekly volume metrics to monitor application consistency.
- [ ] **Average time from discovery to application**: Measure response latency from finding a job to applying.
- [ ] **Score Correlation**: Determine which recommendation/fit scores actually lead to interviews.
- [ ] **Pipeline Funnel**: CRM-style conversion stages (Tracked → Applied → Recruiter Screen → Technical → Final → Offer → Accepted) and Eligible Application Rate metrics.

### 3. Workflow Enhancements

- [ ] **Repost Detection**: Detect reposts of previously closed/rejected positions.
- [ ] **Reopened Hiring Highlights**: Flag companies that have reopened hiring after a previous rejection.
- [ ] **Company Status Separation**: Surface "companies hiring again" separately from "new companies."
- [ ] **Aging & Follow-up Alerts**: Flag stale opportunities (e.g., New > 30 days, Applied > 14 days, Interview > 7 days) to prompt follow-ups.

### 4. Nice-to-Have

- [ ] **Small Local Web UI**: A lightweight local web interface (e.g., Flask/FastAPI backend with a clean HTML/JS dashboard) instead of opening CSVs directly.
- [ ] **Search and Filtering**: Live search, status filters, and fit score thresholds.
- [ ] **Charts Over Time**: Visualizations of application volume and funnel conversion rates.
- [ ] **AI Tailoring & Analysis**: AI resume tailoring suggestions based on skill gap analysis and automated degree requirement detection.

### 5. Scoring Enhancements

- [ ] **Title Exclusions / Penalty**: Observe recommendations over time, and consider adding a penalty (e.g. `score_role -= 10`) for roles with frequently mismatched titles (like `qa`, `test`, `salesforce`, `servicenow`, `wordpress`, `php`, `ios`, `android`) if false positives become an issue.
