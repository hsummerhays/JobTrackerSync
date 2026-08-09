---
name: update_docs
description: Review the project and update all documentation (.md files, agent skills, AGENTS.md) to reflect recent code changes.
---

# Update Docs Skill

Use this skill when the user asks to "review and update docs", "update the .md files", or "keep documentation in sync".

## Scope

The following files must be reviewed and updated as needed:

| File | What to check |
|------|---------------|
| `CHANGELOG.md` | Add a new version section for any unreleased changes. Follow the existing format (version, date, categorized bullet points). |
| `README.md` | Features list, file structure, Setup & Usage steps (CLI flags), agent skills list, roadmap test count. |
| `docs/scoring.md` | Fit Score criteria table, Recommendation thresholds, Priority table, Action logic, aggregator cap. |
| `docs/architecture.md` | Pipeline diagram, Key Files table, Data Model fields, Design Decisions. |
| `.agents/AGENTS.md` | Workspace rules covering deduplication, manual correction, scoring/priority, git, and rescore. |
| `.agents/skills/*.md` | Each skill's commands, flags, and critical notes. |

## Process

1. **Inventory what changed** since the last commit:
   ```bash
   git diff --stat HEAD~1
   ```
   Or check all docs vs. the current code to find stale content.

2. **Review each file in scope** — look for:
   - Stale CLI flags (compare to `python parse_jobs.py --help`)
   - Wrong test counts (run `pytest --co -q | tail -3` to get current total)
   - Missing features or flags introduced since last doc update
   - Wrong priority/scoring rules vs. the actual `compute_priority` and `evaluate_job` logic
   - Skills referencing outdated commands or missing new flags

3. **Update surgical sections** — do NOT rewrite entire files. Use targeted replacements to keep diffs minimal and reviewable.

4. **Verify accuracy**:
   - CLI flags: always cross-check against `python parse_jobs.py --help`
   - Priority rules: cross-check against `compute_priority()` in `parse_jobs.py`
   - Test count: cross-check against actual `pytest` output

5. **Do not commit** until the user confirms. Summarize all changes made and flag anything that requires a decision.

## Key Invariants to Always Verify

- **Priority table in `docs/scoring.md`**: Recommendation governs first. Skip/Low → P4 always, regardless of Action.
- **Aggregator cap**: `jobs.utah.gov`, `Ladders`, `DailySummary`, `DailyDigest` → capped at ★★★☆☆ Maybe (P3).
- **`--rescore` flag**: Must appear in `sync_jobs` skill, `manage_config` skill, `AGENTS.md`, and README usage.
- **Test count in README roadmap**: Update to match actual `pytest` collected item count.
- **Agent skill list in README**: Must match actual directories in `.agents/skills/`.
