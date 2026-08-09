---
name: db_query
description: Run read-only ad-hoc SQL queries against the jobs.db SQLite database.
---
# DB Query Skill

Use this skill to inspect or analyze the `jobs.db` database directly.

## Preferred: Use `query_jobs.py` for company lookups

For looking up jobs by company name, **always use the existing helper script** instead of writing raw SQL:

```bash
python query_jobs.py "<Company Name>"
```

This returns a nicely formatted result with clickable PDF links. The only permitted change to the output is on a `Source PDF:` line: replace the displayed filename with a clickable Markdown link using its `file:///` URL. Keep the visible filename unchanged.

## Fallback: Raw SQL for ad-hoc analysis

For more complex queries not covered by `query_jobs.py`, use the `run_sql.py` helper script:

```bash
python run_sql.py "SELECT company, position, tracker_status FROM jobs LIMIT 10"
```

Use this sparingly — prefer `query_jobs.py` for any user-facing lookup.
