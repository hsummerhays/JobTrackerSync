---
name: manage_jobs
description: Add new jobs to the tracker or update the status of existing jobs (e.g., mark as rejected or cancelled) using the CLI.
---

# Manage Jobs Skill

This skill allows the agent to add new jobs or update the status of existing jobs using `parse_jobs.py` CLI commands.

> **Critical rule:** Any status change must update BOTH `master_tracker.csv` AND `jobs.db`. Using `--update` handles this automatically. If you ever manually edit the CSV without going through `parse_jobs.py`, you must also call `parse_jobs.clean_existing_tracker('master_tracker.csv')` to sync the database — otherwise `clean_existing_tracker` will revert your changes on the next run.

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
