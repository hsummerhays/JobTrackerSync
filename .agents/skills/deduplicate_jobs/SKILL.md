---
name: deduplicate_jobs
description: Clean up the tracker by safely locating and merging physical duplicates.
---

# Deduplicate Jobs Skill

Use this skill when the user asks to "clean up duplicates", "run deduplication", or "merge physical duplicates".

## Instructions
Run the built-in deduplication command to automatically find, merge, and clean up physical duplicates across the database and tracker:

```bash
python parse_jobs.py --dedup-physical
```

**Rule Adherence**: This script adheres to the deduplication constraints. It only automatically collapses two rows when they match on normalized company, normalized title, date, source PDF, and tracker status simultaneously. For jobs with similar but non-identical titles (e.g., "Senior" vs "Staff"), it will ignore them, allowing you to flag them for manual review as required by the workspace rules.
