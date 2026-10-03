---
name: manage_jobs
description: Add new jobs to the tracker or update the status of existing jobs (e.g., mark as rejected or cancelled) using the CLI.
---

# Manage Jobs Skill

This skill allows the agent to add new jobs or update the status of existing jobs using `parse_jobs.py` CLI commands.

> **One-command rule:** For ordinary add/update/note operations, execute the appropriate `parse_jobs.py` mutation command. A successful mutation updates all required persistent state (both `jobs.db` and `master_tracker.csv`). Stop after success unless the user explicitly requests verification or the command reports an error or ambiguity.
>
> Do not run a second synchronization (`clean_existing_tracker()`, `sync_jobs`), cleanup, rescore, database inspection, CSV comparison, PDF reparse, or verification query merely "to be safe." The command's own output (`✓ Updated ...`) is sufficient verification for deterministic updates.

## Operational Model

- **Authoritative System of Record**: `jobs.db` is the primary store of truth. `master_tracker.csv` is an exported view maintained by `parse_jobs.py`.
- **Atomic Persistent Updates**: Mutation CLI commands (`--update`, `--update-from-text`, `--add`, `--add-from-text`) update `jobs.db` directly and refresh `master_tracker.csv` in place.
- **Single Mutation Workflow**:
  - If the Job ID or exact company is known: execute one mutation command and stop.
  - If ambiguous or unknown: run `query_jobs.py "<Company>"` once to identify the ID/position, then execute the mutation command and stop.
- **Exceptional Workflows Only**: Rescoring (`--rescore`), deduplication (`--dedup-physical`), and archiving (`--archive`) are distinct maintenance tools, never routine post-mutation steps. Never edit `master_tracker.csv` manually.



## CLI Usage Instructions

### 1. Adding a New Job (Non-interactively)
```bash
python parse_jobs.py --add --company "<company_name>" --position "<position_title>" --location "<location>" --fit-score <1-100> --status "<status>" --notes "<optional_notes>" [--date "YYYY-MM-DD"]
```

### 1b. Adding a New Job from a Structured Text Block or File
```bash
# Ingest structured text directly (auto-extracts Company, Position, Location, Recruiter, Status, Fit, and Notes):
python parse_jobs.py --add-from-text "scratch/opportunity.txt" [--date "YYYY-MM-DD"]
```

### 1c. Updating a Job from a Structured Block or Pipe-Delimited String
When updating a job using a pipe-delimited one-liner (e.g. `Update: Company | Position | Location | Comp | Employment | Resume tailored | Ready to Apply`) or a key-value text block:
```bash
# Option A: Save text to scratch file and update directly (safely avoids shell escaping with $, quotes, etc.)
python parse_jobs.py --update-from-text "scratch/update.txt"

# Option B: Pass pipe-delimited string directly via --update or --update-from-text
python parse_jobs.py --update "AlignRx LLC | Software Developer II | Remote | $86,400/year | Full-time | Resume tailored 2026-10-03 | Ready to Apply"
```
Automatically maps:
- **Company / Job ID / Position**: Queries and disambiguates the target record.
- **Location**: Updates location (e.g., `Remote`, `Salt Lake City, UT`).
- **Status & Review Status**: Intelligently handles phrases like `Ready to Apply` (sets `Review Status = Reviewed`, `Action = Apply`, preserves `Status = New`) or `Applied`, `Rejected`, `Technical Interview`, etc.
- **Structured Notes**: Organizes compensation, employment type, tailoring dates, and notes into clean paragraphs and appends to existing notes.


### 2. Marking a Job as Rejected
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status Rejected
```

### 3. Marking a Job as Cancelled
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status Cancelled
```

### 4. Updating to Other Statuses
Valid statuses: `New`, `Applied`, `Phone Screen`, `Manager Interview Pending`, `Technical Interview`, `Onsite Interview Pending`, `Final Interview Scheduled`, `Assessment Pending`, `Reference Check`, `Recruiter Submitted`, `Waiting`, `Offer`, `Accepted`, `Expired`, `Ghosted`, `Cancelled`, `Rejected`

```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status <status_name>
```

### 5. Appending or Setting Notes
```bash
# Append note to existing notes (preserves prior notes and current status)
python parse_jobs.py --update "<company_name_or_job_id>" --append-notes "<note_to_append>"

# Or set/replace notes:
python parse_jobs.py --update "<company_name_or_job_id>" --notes "<new_notes>"

# Set or append notes from a file (safely preserves characters like $, quotes, and multiline text without shell interpolation):
python parse_jobs.py --update "<company_name_or_job_id>" --notes-file "scratch/notes.txt" [--append]

# Update status, action, recruiter, hiring manager, review status, location, provider, and append notes at the same time:
python parse_jobs.py --update "<company_name_or_job_id>" --status <status_name> --review-status "<review_status>" --action "<action_name>" --recruiter "<recruiter>" --hiring-manager "<manager>" --location "<location>" --provider "<provider>" --append-notes "<note_to_append>"
```

### 6. Rescoring Jobs (Maintenance Workflow Only)
*(Only run when config.json is modified to update skill/keyword weights; never run as part of a routine status or note update)*

```bash
# Recalculate scores for all active parser-scored jobs (preserves manual score overrides)
python parse_jobs.py --rescore

# Force rescoring of ALL active jobs, including manual score overrides
python parse_jobs.py --rescore-all

# Clear manual score override for a specific company or all jobs
python parse_jobs.py --clear-score-override "<company_name_or_job_id>"
```
