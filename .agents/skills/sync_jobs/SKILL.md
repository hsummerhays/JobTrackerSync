---
name: sync_jobs
description: Parse new job alert PDFs from a directory and sync them into the SQLite database and CSV tracker.
---
# Sync Jobs Skill

Use this skill to run the main job parsing pipeline.

## Command

Run the following command. `parse_jobs.py` will open a folder-selection dialog (via tkinter) for the user to pick their PDF directory. No arguments are needed for normal use:

```bash
python parse_jobs.py
```

If you need to pass the directory non-interactively (e.g., in a script), use:

```bash
python parse_jobs.py --pdf-dir "<path_to_pdf_directory>"
```

## Rescoring Without New PDFs

If `config.json` was updated (e.g., new resume skills or aliases added) but no new PDFs are available, use `--rescore` to recalculate fit scores, priorities, and recommendations for all active jobs **without re-parsing any PDFs**. Manual fields (tracker_status, notes, recruiter, hiring_manager) are preserved:

```bash
python parse_jobs.py --rescore
```

## Important Notes

- The script skips PDFs whose content hasn't changed since the last run (incremental sync).
- After parsing, it automatically syncs `master_tracker.csv` and `jobs.db`.
- **Never manually edit only the CSV** — always sync both the CSV and the database together via `parse_jobs.clean_existing_tracker('master_tracker.csv')`.

