# Workspace Rules for JobTrackerSync

- When the user types `List`, `Show`, or `Find` followed by a company name, run:
  ```bash
  python query_jobs.py "<Company Name>"
  ```
  Return the command output exactly as produced. Do not add commentary, bolding, headings, or alter its spacing or layout.

- The only permitted change to `query_jobs.py` output is on a `Source PDF:` line: replace the displayed filename with a clickable Markdown link using its `file:///` URL. Keep the visible filename unchanged.

- When the user asks to find, query, or link a PDF file—for example, `Link "some.pdf"`—do not create a temporary Python script or query the database directly.

- Instead, use the provided helper:
  ```bash
  python find_pdf.py "<pdf_filename_or_substring>"
  ```

- Use the helper's output to identify matching files and their `file:///` URIs. Return clickable Markdown links, preserving the filename as the link text.

- When the user asks to add an event to their calendar, do not create the event directly. Generate a pre-filled Google Calendar event link:
  ```text
  https://calendar.google.com/calendar/r/eventedit?text=...&details=...&dates=...
  ```
  URL-encode all values, include the date, time, and timezone when provided, and return the clickable link directly.

- **Deduplication / Cleanup Rules:**
  - Never automatically cancel or merge jobs based on similarity alone.
  - Generic aggregator names (e.g., `Jobs.utah.gov-DailySummary`, `Ladders`, `Actively recruiting`) should never be trusted as employers for deduplication or merging.
  - Three distinct cases, not one rule:
    - **Same logical posting, seen again (relisting):** identical normalized company + title + location, rediscovered within the relisting window (90 days for a new sighting; 60 days for a re-apply match against an Applied/Interview row) -- merge sightings into the existing row and advance Last Seen instead of creating a new row.
    - **Physical duplicate cleanup (e.g. a one-off cleanup script re-scanning the tracker itself):** only collapse two rows automatically when they match on normalized company, normalized title, date, source PDF, *and* tracker status all at once.
    - **Similar but not identical titles** (e.g. "Senior Software Engineer" vs "...II"): never auto-merge or auto-cancel -- flag for manual review only.

- **Manual Data Correction Rules:**
  - When making a manual status correction to a job (e.g., reverting a status from `Cancelled` back to `New`), you must update BOTH `master_tracker.csv` AND the SQLite database (`jobs.db` and `job_workflow` tables). If you only update the CSV, the `clean_existing_tracker` sync function will aggressively overwrite your CSV changes with the persisted state from the database.

- **Workspace Cleanup:**
  - Do not place temporary text files (like `wgu_list2.txt`), intermediate data dumps, or one-off python scripts in the main project folder. All temporary work must be done inside the `scratch/` directory and should ideally be deleted when no longer needed.

- **Git Rules:**
  - Always run tests before a commit.

- **Scoring & Priority Rules:**
  - Priority is always governed by Recommendation first, then Action. `Action = Apply` cannot elevate a Skip or Low job into P1/P2. The order is: Skip/Low → P4, Maybe → P3, Strong/Apply Now + Apply → P1/P2.
  - Aggregator listings (`Jobs.utah.gov-DailySummary`, `Ladders-DailyDigest`, any company name containing "DailySummary" or "DailyDigest") are capped at ★★★☆☆ Maybe (P3) regardless of fit score.
  - After any change to `config.json` (adding skills, aliases, or keywords), run `python parse_jobs.py --rescore` so existing database records are updated (manual score overrides with `score_source = manual` are preserved unless `--rescore-all` or `--clear-score-override` is used).

