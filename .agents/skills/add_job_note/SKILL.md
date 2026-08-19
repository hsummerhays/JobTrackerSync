---
name: add_job_note
description: Add or append interview notes, recruiter details, or progress notes to an existing job in the tracker.
---

# Add Job Note Skill

Use this skill whenever the user asks to add, append, or update notes on a job (e.g., interview debriefs, contact info, comp details, or next steps).

> **Critical rule:** All updates must be made via `parse_jobs.py` CLI or direct updates to `jobs.db`. Never edit `master_tracker.csv` directly.

## CLI Usage Instructions

### 1. Appending a Note (Preserves Existing Notes)
To append a new note (e.g. interview summary, follow-up notes) to any existing notes on the job:

```bash
python parse_jobs.py --update "<company_name_or_job_id>" --append-notes "<note_text>"
```

Or using the `--append` flag:
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --notes "<note_text>" --append
```

### 2. Overwriting / Setting Notes Completely
To replace the entire notes field for a job with a new value:

```bash
python parse_jobs.py --update "<company_name_or_job_id>" --notes "<new_notes_content>"
```

### 3. Updating Status and Adding Notes Simultaneously
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status "<status>" --append-notes "<note_text>"
```

## Behavior & Data Guarantees
- **Status Preservation:** When `--status` is omitted, the job's current status and disposition are preserved.
- **Formatting:** Appended notes are automatically separated from previous notes with clean paragraph breaks (`\n\n`).
- **Persistence & Sync:** Updates both `jobs` and `job_workflow` tables in SQLite (`jobs.db`) and immediately refreshes `master_tracker.csv`.
