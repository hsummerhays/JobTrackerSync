---
name: manage_jobs
description: Add new jobs to the tracker or update the status of existing jobs (e.g., mark as rejected or cancelled) using the CLI.
---

# Manage Jobs Skill

This skill allows the agent to add new jobs or update the status of existing jobs using `parse_jobs.py` CLI commands.

> **Critical rule:** `jobs.db` is the primary source of truth. All job additions, status updates, and note edits must be written directly to `jobs.db`. `master_tracker.csv` is an exported view generated from `jobs.db`. Using `--update` or `--add` updates `jobs.db` and rebuilds the CSV export automatically.

## Database-to-CSV Synchronization Mechanics

`jobs.db` serves as the primary persisted store of truth. `master_tracker.csv` is generated from `jobs.db`:

1. **DB-Driven CSV Generation:**
   - Every time `parse_jobs.py` runs (PDF parsing, `--rescore`, `--dedup-physical`, or `clean_existing_tracker`), the CSV export is compiled from `jobs.db`.
   - All stored field values (scores, priorities, recommendations, notes, locations) in `jobs.db` take precedence when building `master_tracker.csv`.

2. **Direct DB Updates & Auto-Sync:**
   - CLI commands (`parse_jobs.py --update`, `--add`) update `jobs.db` directly and export the refreshed data to `master_tracker.csv`.

3. **Direct CSV Edits Prohibited:**
   - Do not edit `master_tracker.csv` manually. Any manual changes made to the CSV file will be overwritten on the next sync run with data from `jobs.db`.



## CLI Usage Instructions

### 1. Adding a New Job (Non-interactively)
```bash
python parse_jobs.py --add --company "<company_name>" --position "<position_title>" --location "<location>" --fit-score <1-100> --status "<status>" --notes "<optional_notes>"
```

### 2. Marking a Job as Rejected
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status Rejected
```

### 3. Marking a Job as Cancelled
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status Cancelled
```

### 4. Updating to Other Statuses
Valid statuses: `Applied`, `Phone Screen`, `Technical Interview`, `Recruiter Submitted`, `Waiting`, `Expired`, `Ghosted`, `New`, `Cancelled`, `Rejected`

```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status <status_name>
```

### 5. Appending a Note
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --notes "<note_to_append>"
```

### 6. Interactive Update (no company specified)
Launches an interactive menu:
```bash
python parse_jobs.py --update
```
