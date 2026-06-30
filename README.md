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

Each run prints a sync report followed by a live application pipeline dashboard:

```text
=========================================
          JOB TRACKER SYNC REPORT        
=========================================
New jobs: 18
Existing jobs: 61
Already applied: 3
Closed jobs: 2
Need review: 24
=========================================

=========================================
          APPLICATION PIPELINE           
=========================================
Active Pipeline
  Phone Screen:         1
  Technical Interview:  0
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

- **Robust PDF extraction** with pytesseract OCR fallback for image-only PDFs
- **Glassdoor reverse-layout parsing** — handles alert formats where location follows the title
- **Deterministic dedup** via MD5 hash of Company + Position + Location — stable across daily imports, allowing identical postings to be re-imported as new opportunities after 90 days (with a date-suffixed ID)
- **Idempotent re-scoring** — editing `config.json` and re-running automatically recalculates all historic rows
- **Company type detection** — classifies Recruiting Firm, Consulting, Defense, Healthcare, Financial, Enterprise, or Small/Medium from the company name
- **Local/onsite warnings** — 30-point deduction when postings contain "local candidates", "onsite only", "must relocate", or "no remote"
- **Persistent workflow state** — Parsed job data is regenerated on every sync while user-managed workflow state (status, notes, actions, follow-up dates, etc.) is preserved independently in SQLite and restored automatically during imports.

---

## File Structure

```
JobTrackerSync/
├── parse_jobs.py              # Main CLI entry point
├── config.json                # Resume skills and scoring criteria (git-ignored)
├── config.json.example        # Template for new installations
├── master_tracker.csv         # Master tracking spreadsheet (git-ignored)
├── master_tracker.csv.example # Schema reference
├── jobs.db                    # SQLite mirror (git-ignored)
└── docs/
    ├── architecture.md        # Pipeline diagram, data model, design decisions
    ├── scoring.md             # Scoring algorithm reference
    └── screenshots/           # CLI and spreadsheet screenshots
```

---

## Setup & Usage

**1. Install dependencies**

```bash
pip install pdfplumber pytesseract rich
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

- [ ] Unit tests for parsing and scoring logic
- [ ] Sample PDFs with expected parser outputs
- [ ] AI-assisted classification for fuzzy job postings
- [ ] AI resume tailoring suggestions based on skill gap analysis
- [ ] Cross-provider duplication detection (same listing on ZipRecruiter and LinkedIn)
- [ ] Automatic degree requirement detection via NLP
- [ ] Company historical interaction tracking
