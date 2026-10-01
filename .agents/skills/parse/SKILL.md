---
name: parse
description: Parse and sync job postings from daily PDF alert directories into the SQLite database and CSV tracker (e.g. today, yesterday, specific dates, or a custom folder).
---

# Parse Skill

Use this skill whenever the user asks to "parse", "parse today", "parse yesterday", "parse [date]", or sync PDFs from the daily job postings repository.

## Base Directory & Folder Structure

Job alert PDFs are organized by date subdirectories in:
```text
D:\Current\Personal\New Job 2026\Resume 2026\Job Postings\<YYYY-MM-DD>
```

## Common Workflows

### 1. Parse Today
Resolve today's local date (`YYYY-MM-DD`) and execute:
```bash
python parse_jobs.py --pdf-dir "D:\Current\Personal\New Job 2026\Resume 2026\Job Postings\<TODAY_YYYY-MM-DD>"
```

### 2. Parse Yesterday
Resolve yesterday's local date (`YYYY-MM-DD`) and execute:
```bash
python parse_jobs.py --pdf-dir "D:\Current\Personal\New Job 2026\Resume 2026\Job Postings\<YESTERDAY_YYYY-MM-DD>"
```

### 3. Parse Yesterday and Today
Run the parsing pipeline sequentially in chronological order:
1. Parse yesterday's directory first.
2. Once complete, parse today's directory.

### 4. Parse Specific Date
When the user specifies a date (e.g., `2026-09-30` or `Sep 30`):
```bash
python parse_jobs.py --pdf-dir "D:\Current\Personal\New Job 2026\Resume 2026\Job Postings\<YYYY-MM-DD>"
```

### 5. Parse Custom Path or Interactive Picker
If a custom path is supplied:
```bash
python parse_jobs.py --pdf-dir "<custom_path>"
```
If no path or date is specified and no defaults apply:
```bash
python parse_jobs.py
```
*(Opens a directory selection dialog via tkinter)*

## Post-Parsing Summary

After parsing completes:
1. Report the number of new jobs created and duplicates merged for each directory processed.
2. Report the updated total number of tracked jobs.
3. Highlight any new high-fit opportunities (e.g. ★★★★★ / ★★★★☆) or summarize the today action queue (`python parse_jobs.py --today`).
