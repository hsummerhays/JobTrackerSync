# JobTrackerSync

`JobTrackerSync` is an advanced job posting parser and tracking synchronization utility. It processes batches of PDF files containing job alerts (emails, screenshots, search results) from various job boards (ZipRecruiter, LinkedIn, Glassdoor, Indeed, etc.), evaluates them against custom resumes and configurable classification rules, and synchronizes results into a structured master tracker spreadsheet and database.

---

## Motivation

During a software engineering job search, I found myself reviewing hundreds of duplicate job alerts every week from multiple providers. `JobTrackerSync` automates extraction, normalization, scoring, and tracking so I can focus on evaluating opportunities instead of managing spreadsheets. It converts a manual chore into an automated engineering workflow.

---

## Why This Architecture?

The project intentionally separates extraction, normalization, scoring, and workflow management into independent stages. This allows scoring algorithms, resume profiles, and recommendation rules to evolve without changing the parsing pipeline, ensuring long-term maintainability and flexibility.

---

## Output Example

```text
Company                     Position                          Score  Action
──────────────────────────  ────────────────────────────────  ─────  ───────────────
Sunwest Bank                Senior Software Engineer          92     Apply
Harvest Valuations          Senior Software Developer         84     Review
Waystar                     Sr Software Engineer              18     Ignore
```

### Screen Walkthrough

*Below are visual examples of the tool processing listings, managing synchronization databases, and presenting workflows:*

| Workflow Step | Visual Description |
| :--- | :--- |
| **1. Source PDF Alert** | ![Sample PDF Job Alert](docs/screenshots/sample_pdf_alert.png) |
| **2. CLI Sync Report** | ![CLI Sync Report](docs/screenshots/cli_sync_report.png) |
| **3. Master CSV Sheet** | ![Master CSV Sheet](docs/screenshots/master_tracker_sheet.png) |
| **4. SQLite Database** | ![DB Browser for SQLite](docs/screenshots/db_browser_sqlite.png) |

---

## Workflow Diagram

```text
       PDF Alerts (ZipRecruiter, LinkedIn, Glassdoor, etc.)
                                │
                                ▼
                           PDF Parser
                                │
                                ▼
                         Job Extraction ──(pytesseract OCR Fallback)
                                │
                                ▼
                        Evaluation & Scoring
                                │
                                ▼
                       Deterministic Deduplication
                                │
                                ▼
         ┌──────────────────────┴──────────────────────┐
         ▼                                             ▼
  Master Tracker (CSV)                         SQLite Database (jobs.db)
```

---

## Design Philosophy

* **Separation of Concerns**: Machine-generated facts remain separate from human decisions. The parser extracts structured job details (location, URL, company name, skills) while recommendations, application statuses, actions, and workflow decisions remain under user control in the tracker.
* **Idempotent Recalculations**: Configuration changes or resume skill updates automatically recalculate scores and priorities for all historic runs without losing manual review status overrides.

---

## Features

1. **Robust PDF Extraction & Smart Parsing**:
   - Extracts plain selectable text from PDFs natively.
   - Falls back to **pytesseract OCR** automatically if the PDF contains scanned image-only content.
   - Automatically detects job source providers and associates clickable URLs matching job positions.
   - **Glassdoor & Reverse-Layout Parsing**: If the line following the title is a location, the parser automatically pivots, setting that line as the location and looking back to the line *before* the title for the cleaned company name.
   - Resolves consecutive multi-job card listings without combining them.

2. **Deterministic Stable Job IDs**:
   - Jobs are uniquely identified using a deterministic hash of `Company + Position + Location`. This enables stable synchronization across multiple daily imports and prevents duplicate records.

3. **Hybrid Database Sync (SQLite & CSV)**:
   - Maintains [master_tracker.csv](file:///c:/HughApps/JobTrackerSync/master_tracker.csv) as the human-readable canonical source.
   - Automatically synchronizes to a local **SQLite database** (`jobs.db`) on launch.
   - *Why SQLite exists*: SQLite enables long-term tracking, complex querying, relational mapping, deduplication, and future reporting without relying solely on flat CSV files.

4. **Configuration-Driven Matching (`config.json`)**:
   - Distinct filters and criteria based on **Job Type** (e.g., `Software Engineer` vs. `Operations`).
   - Custom keyword scoring systems, skip words (e.g., filtering out crowd-sourced AI annotation tutoring roles), and target resume skills.

5. **Intelligent Score & Priority Mappings**:
   - **Fit Score (0-100)**: Evaluates location, remote flexibility, seniority, tech stack overlap (e.g., .NET/Java priority), degree requirement absence, and company scale.
   - **Local/Onsite Warnings**: Deducts 30 points and flags `Onsite/Local Restriction` in the reason column if keywords like `local candidate`, `onsite only`, `must relocate`, or `no remote` are found in the title or description.
   - **User Action & Priority Mapping**: Standardizes recommendation rankings and maps actions (`Apply`, `Contact Recruiter`, `Review`, `Ignore`) and explicit timelines:
     - `P1 - Apply today`
     - `P2 - Apply this week`
     - `P3 - Investigate`
     - `P4 - Ignore`

6. **Cleaner Company Filtering**:
   - Rejects lowercase anomalies, generic keywords (e.g. `"Unknown/Other"`, `"1 message"`, `"based compensation"`), email conversational fragments, or location-as-company names (e.g. city/state strings like `"Salt Lake City, UT"`).

7. **Canonical Data Separation**:
   - Separates machine-generated facts from human-reviewed decisions.
   - **`Review Status`**: `["Imported", "Reviewed", "Verified", "Applied", "Closed"]` (new jobs default to `Imported`).
   - **`Tracker Status`**: `["New", "Applied", "Phone Screen", "Technical Interview", "Recruiter Submitted", "Waiting", "Rejected", "Cancelled", "Ghosted"]`.
   - **`Already in Tracker`**: Automatically flags duplicate companies (`Yes` or `No`).

---

## File Structure

- [parse_jobs.py](file:///c:/HughApps/JobTrackerSync/parse_jobs.py): The main execution script.
- [config.json](file:///c:/HughApps/JobTrackerSync/config.json): Centralized criteria rules, tech stack keywords, and resume skill inventories.
- [master_tracker.csv](file:///c:/HughApps/JobTrackerSync/master_tracker.csv): Canonical master tracking spreadsheet.
- [jobs.db](file:///c:/HughApps/JobTrackerSync/jobs.db): SQLite relational database synchronized with all CSV records on launch.

---

## How to Run

Execute the parser by providing a folder containing the job posting PDF alerts:

```bash
python parse_jobs.py --pdf-dir "C:\Path\To\Your\PDF\Folder"
```

### Sample Session

```text
> python parse_jobs.py --pdf-dir "C:\JobAlerts"

=========================================
          JOB TRACKER SYNC REPORT        
=========================================
New jobs: 18
Existing jobs: 61
Already applied: 3
Closed jobs: 2
Need review: 24
=========================================
```

---

## Technical Highlights / Skills Demonstrated

**JobTrackerSync** – Built a Python application that extracts job postings from PDFs using native text extraction with OCR fallback, scores opportunities against configurable resume profiles, deduplicates postings across multiple job boards, and synchronizes results into a master CSV and SQLite database for workflow management.

---

## Future Roadmap & AI Integration

- [ ] **AI-Assisted Classification**: Leverage LLMs for parsing fuzzy job postings and company fields.
- [ ] **AI Resume Tailoring Suggestions**: Generate targeted cover letters and resume summaries based on job description overlap.
- [ ] **Automatic Degree Requirement Detection**: High-accuracy extraction using NLP classifiers.
- [ ] ATS keyword extraction based on loaded target resumes.
- [ ] Resume version matching and skill gap visualizations.
- [ ] Cross-provider duplication detection (matching same listing on ZipRecruiter and LinkedIn).
- [ ] Company historical interaction tracking.
- [ ] Automatic job listing expiration / closed status checks.
