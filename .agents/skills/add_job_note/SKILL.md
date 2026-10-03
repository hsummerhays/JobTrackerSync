---
name: add_job_note
description: Add or append interview notes, recruiter details, or progress notes to an existing job in the tracker.
---

# Add Job Note Skill

Use this skill whenever the user asks to add, append, or update notes on a job (e.g., interview debriefs, contact info, comp details, or next steps).

> **One-command rule:** For ordinary note or status updates, execute the appropriate `parse_jobs.py --update` or `--update-from-text` command. A successful mutation updates all required persistent state (both `jobs.db` and `master_tracker.csv`). Stop after success unless the user explicitly requests verification or the command reports an error or ambiguity. Do not run secondary syncs, database dumps, or verification queries after a successful command. Never edit `master_tracker.csv` directly.

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

### 3. Updating from a Notes File (Recommended for Special Characters & Multiline Text)
To avoid shell escaping issues with characters like `$`, quotes, or rich formatting:

```bash
# Write note content to scratch/notes.txt first, then:
python parse_jobs.py --update "<company_name_or_job_id>" --notes-file "scratch/notes.txt" [--append]
```

### 3b. Updating from Structured or Pipe-Delimited Input
If updating multiple fields at once from a pipe-delimited string (e.g. `Company | Position | Location | Comp | Employment | Resume tailored | Ready to Apply`):
```bash
# Write line to scratch/update.txt (avoids shell escaping), then run:
python parse_jobs.py --update-from-text "scratch/update.txt"
```
Automatically extracts company/job ID, position disambiguation, location, review status, and formats compensation/tailoring details into the notes field with automatic append.

### 4. Updating Status, Metadata, and Adding Notes Simultaneously
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status "<status>" --review-status "<review_status>" --action "<action>" --recruiter "<recruiter>" --hiring-manager "<manager>" --location "<location>" --provider "<provider>" --append-notes "<note_text>"
```

## Behavior & Data Guarantees
- **Status Preservation:** When `--status` is omitted, the job's current status and disposition are preserved.
- **Formatting:** Appended notes are automatically separated from previous notes with clean paragraph breaks (`\n\n`).
- **Persistence & Sync:** Updates both `jobs` and `job_workflow` tables in SQLite (`jobs.db`) and immediately refreshes `master_tracker.csv`.
- **Completion Guarantee:** The CLI command's output (`✓ Updated ...`) confirms successful completion. Stop immediately; no additional query or verification step is needed.
