---
name: manage_jobs
description: Add new jobs to the tracker or update the status of existing jobs (e.g., mark as rejected or cancelled) using the CLI.
---

# Manage Jobs Skill

This skill allows the agent to add new jobs or update the status of existing jobs (such as marking them as `Rejected` or `Cancelled`) by running the job tracker CLI commands.

## CLI Usage Instructions

### 1. Adding a New Job (Non-interactively)
To add a new job to the tracker, execute the following command:
```bash
python parse_jobs.py --add --company "<company_name>" --position "<position_title>" --location "<location>" --fit-score <1-100> --status "<status>" --notes "<optional_notes>"
```
*Note: If some optional fields are omitted, the script will fall back to default values or prompt for them.*

### 2. Marking a Job as Rejected
To mark a job (by company name or job ID) as Rejected, run:
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status Rejected
```

### 3. Marking a Job as Cancelled
To mark a job (by company name or job ID) as Cancelled, run:
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status Cancelled
```

### 4. Updating a Job to other Statuses
To update a job status to other valid options (e.g. `Applied`, `Phone Screen`, `Technical Interview`, `Recruiter Submitted`, `Waiting`, `Expired`, `Ghosted`, `New`), run:
```bash
python parse_jobs.py --update "<company_name_or_job_id>" --status <status_name>
```
