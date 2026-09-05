---
name: add_manual_opportunity
description: Quickly ingest and track a manually shared job opportunity, recruiter message, or interview debrief from structured or unstructured text.
---

# Add Manual Opportunity Skill

Use this skill whenever the user asks to add or log a new job opportunity that was not imported via PDF (such as a recruiter message, direct contact, LinkedIn message, or phone screen debrief).

## Workflow

### 1. Ingest via CLI `--add-from-text`

You can pass raw multiline text or a file path directly to `parse_jobs.py --add-from-text`:

```bash
# Option A: Save text block to scratch file and ingest
python parse_jobs.py --add-from-text "scratch/opportunity.txt"

# Option B: Pass text directly (or override specific fields)
python parse_jobs.py --add-from-text "scratch/opportunity.txt" [--status "Technical Interview"] [--fit-score 95]
```

`--add-from-text` automatically parses:
- **Company / Employer**
- **Position / Title**
- **Location**
- **Recruiter / Hiring Manager**
- **Status** (intelligently matches phrases like `Recruiter Screen Completed — Technical Interview Pending` to valid tracker statuses)
- **Fit / Score / Recommendation** (e.g. `High / Priority` -> 95 / `★★★★★ Apply Now`)
- **Notes / Compensation / Stack / Role Details** (aggregates remaining bullet points into the `Notes` field)
- Updates both `jobs.db` and `master_tracker.csv` atomically with `_status_source='user'`.

### 2. Recruiter Contact Generation (Optional / Automatic)

If the opportunity provides recruiter details (name, title, email, or phone):
1. Offer or generate a `.vcf` file using [generate_vcf.py](file:///c:/HughApps/JobTrackerSync/generate_vcf.py):
   ```bash
   python generate_vcf.py --name "[Recruiter Name]" --title "[Title]" --org "[Company]" --output "scratch/[name].vcf"
   ```
2. Provide the clickable link to the `.vcf` file and the [Google Contacts Import](https://contacts.google.com/) link.

### 3. Verification & Output

1. Confirm addition by running:
   ```bash
   python query_jobs.py "<Company Name>"
   ```
2. Clean up any temporary files in `scratch/`.
