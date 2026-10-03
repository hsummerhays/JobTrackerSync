# Workspace Rules for JobTrackerSync

- When the user types `List`, `Show`, or `Find` followed by a company name, run:
  ```bash
  python query_jobs.py "<Company Name>"
  ```
  Only include old/terminal/archived listings if the user specifically asks for them (e.g. `List all <Company>` or asking for old listings), by adding `--all`:
  ```bash
  python query_jobs.py --all "<Company Name>"
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
  - **Full Institutional Memory**: `jobs.db` holds complete history across active and archived records (`archived = 'Yes'`); `load_tracker()` loads all records from SQLite so historical rejections, applications, and sightings are never lost during deduplication.
  - **Two-Stage Identity Matching**: Matching evaluates both exact literal `canonical_job_key` and `canonical_job_key_relaxed` (stripping purely legal corporate suffixes like `LLC`, `Inc`, `Corp`, `Co`, `Ltd` and normalizing remote location variations such as `OR Remote` ↔ `Remote`). Meaningful corporate words like `Consulting` or `Technologies` are never stripped.
  - Three distinct cases, not one rule:
    - **Same logical posting, seen again (relisting):** identical normalized company + title + location:
      - If matched against an active/applied posting within 60 days: merge sightings into existing row and advance Last Seen.
      - If matched against a closed/rejected posting within 180 days: suppress resurrection, retain closed/rejected status, and update Last Seen/sightings.
      - If matched against a closed/rejected posting older than 180 days: treat as a legitimate re-opening (`New`/`Apply`), create a new row, and link to prior record via `previous_job_id`.
    - **Physical duplicate cleanup (e.g. a one-off cleanup script re-scanning the tracker itself):** only collapse two rows automatically when they match on normalized company, normalized title, date, source PDF, *and* tracker status all at once (`python parse_jobs.py --dedup-physical`).
    - **Similar but not identical titles** (e.g. "Senior Software Engineer" vs "...II"): never auto-merge or auto-cancel -- flag for manual review only.
    - **Title Level Normalization (Roman Numerals)**: `utils.normalize_title()` normalizes standalone Roman numerals (`I`, `II`, `III`, `IV`, `V`) to Arabic digits (`1`, `2`, `3`, `4`, `5`) in canonical keys (e.g. `Senior Developer I` ↔ `Senior Developer 1`) while retaining original displayed titles.

- **Tracker Mutation Rules & One-Command Rule:**
  - `jobs.db` is the authoritative system of record. Supported `parse_jobs.py` mutation commands (`--update`, `--update-from-text`, `--add`, `--add-from-text`) maintain all required persistent state, updating `jobs.db` and updating `master_tracker.csv` automatically. Never edit `master_tracker.csv` manually.
  - **One-Command Rule**: For ordinary add/update/note operations, execute the appropriate `parse_jobs.py` mutation command. A successful mutation updates all required persistent state. Stop after success unless the user explicitly requests verification or the command reports an error or ambiguity.
  - Do not run a second synchronization (`clean_existing_tracker()`, `sync_jobs`), cleanup, rescore, database inspection, CSV comparison, PDF reparse, or verification query merely "to be safe." The command's own successful completion/output is sufficient verification for deterministic updates.
  - If the Job ID is already known, resolve to exactly one mutation command:
    ```bash
    python parse_jobs.py --update "<job-id>" --status <Status> [--append-notes "<notes>"]
    ```
    After that command succeeds, stop. If the Job ID is not known, query once first (`python query_jobs.py "<Company Name>"`) to identify the correct opportunity, then perform one mutation command and stop.
  - **Structured Job Updates**: Follow the established Tier A / Tier B hierarchy:
    - Prefer direct CLI arguments for simple deterministic updates (e.g. `python parse_jobs.py --update "<job-id>" --status Applied --append-notes "..."`).
    - For structured or pipe-delimited updates that can safely be supplied directly, use the supported inline structured CLI form:
      ```bash
      python parse_jobs.py --update "<Company> | <Position> | <Location> | <Comp> | ..."
      ```
    - Use `scratch/update.txt` only for complex multiline input or input where shell quoting/interpolation would make direct invocation cumbersome or unsafe:
      ```bash
      python parse_jobs.py --update-from-text "scratch/update.txt"
      ```
      Clean up `scratch/update.txt` and stop after success.
    - Do not create a scratch file merely because input is pipe-delimited or contains structured fields.

- **Workspace Cleanup:**
  - Do not place temporary text files (like `wgu_list2.txt`), intermediate data dumps, or one-off python scripts in the main project folder. All temporary work must be done inside the `scratch/` directory and should ideally be deleted when no longer needed.

- **Git Rules:**
  - Always run tests before a commit.
  - If there are both staged and unstaged changes, explicitly warn the user before committing to avoid accidental partial commits or unnecessary merges.

- **Scoring & Priority Rules:**
  - Priority is always governed by Recommendation first, then Action. `Action = Apply` cannot elevate a Skip or Low job into P1/P2. The order is: Skip/Low → P4, Maybe → P3, Strong/Apply Now + Apply → P1/P2.
  - Aggregator listings (`Jobs.utah.gov-DailySummary`, `Ladders-DailyDigest`, any company name containing "DailySummary" or "DailyDigest") are capped at ★★★☆☆ Maybe (P3) regardless of fit score.
  - After any change to `config.json` (adding skills, aliases, or keywords), run `python parse_jobs.py --rescore` so existing database records are updated (manual score overrides with `score_source = manual` are preserved unless `--rescore-all` or `--clear-score-override` is used).

