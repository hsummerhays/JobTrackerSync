# Recovery Baseline — 2026-08-12

Frozen as the starting point for the tracker stabilization effort, after a
run of regressions where fixes validated by unit tests (stable IDs,
application history, Weave chronology/dedup, Yapi/1872 confirmation
reconstruction, same-run SQLite/CSV sync, defense/clearance scoring,
manual-score preservation, score provenance) still surfaced the next
problem in the production tracker. Local unit tests check implementation
logic; this baseline exists so future changes can also be checked against
an end-to-end contract of what must never change in the real tracker.

## What's frozen

- **Code**: git tag `recovery-baseline-20260812`, commit `465a3e88b5bb`.
- **Data**: point-in-time copies of the live tracker, stored locally
  (untracked — same PII/size reasons `jobs.db` and `master_tracker.csv`
  are already gitignored):
  - `baseline/master_tracker.recovery-baseline-20260812.csv`
    (sha256 `ab2368f44bd88ae94ef2047c0a1461110390db3c2cbf345a9b7ef21abed5e431`)
  - `baseline/jobs.recovery-baseline-20260812.db`
    (sha256 `48fe581bd48c26ace2f5c368f5092eabe74bc9ccfdc0fae7e4cafc1a2312c11c`)

These filenames intentionally don't match the `*.bak.*` pattern that
`backup_file_if_exists()` prunes, so they won't be rotated away.

## Known discrepancy at freeze time (resolved 2026-08-12)

At freeze time `jobs.db` had 4179 job rows against 4018 in
`master_tracker.csv`. Investigation (not a quick assumption — the first
report of this, made before checking all 161 rows individually, wrongly
called one of them a lost curated record) found none of the 161 DB-only
rows were genuine missing data:

- 20 were leftover rows under a legacy/old Job ID hash for a job already
  correctly present in the CSV under a different Job ID (same
  fingerprint, same status). Writing them into the CSV would have
  created duplicate rows for jobs already tracked.
- 141 were mis-parsed junk (`Actively recruiting`, `Ladders`, `(Backend)`,
  `$130,000 - $145,000 a year`, etc.) that the CSV-write path's
  `is_valid_company()` filter correctly excludes by design. `jobs.db`
  had no equivalent filter on its write path, so it kept them.

Fix applied: pruned all 161 rows from `jobs.db` (not the CSV — the CSV
was already correct) after per-row confirmation that each was a
duplicate or a junk parse. `jobs.db` and `master_tracker.csv` now agree
exactly (4018 rows each, 0 IDs missing in either direction). All 400
tests pass post-prune. A pre-prune copy of `jobs.db` is kept at
`baseline/jobs.pre_prune_20260812.db` for reference.

**Follow-up fix applied 2026-08-12**: `save_to_sqlite()`'s `_upsert_all_jobs()`
now rejects, before any write, (a) rows whose company fails
`is_valid_company()` (mirroring the gate `evaluate_job()` already applies)
and (b) rows whose `(fingerprint, date_added)` pair already belongs to a
different Job ID already in the DB (mirroring the CSV-side fingerprint
dedup pass's same-date rule — a different `date_added` is a legitimate
relisting, not a duplicate, and is left alone). Manually-added jobs
(`_status_source == "user"`) are exempt from both checks, since a human
typing a company name directly shouldn't be second-guessed by heuristics
built to catch auto-parse junk. Covered by
`tests/test_save_to_sqlite.py::TestSaveToSqliteValidityDedupFilter`.

Replaying the 161 pruned rows (from `baseline/jobs.pre_prune_20260812.db`)
back through the new filter (against a throwaway DB copy, not the live
one) confirms 147/161 (the 20 duplicates + 127 of the 141 junk rows) are
now rejected automatically. The remaining 14 pass `is_valid_company()`'s
heuristics despite being junk (e.g. `$130,000 - $145,000 a year`,
`(Backend)`) — this is a pre-existing limitation of `is_valid_company()`
shared by the CSV path too, not a gap introduced by this fix; those 14
needed the same manual judgment call during the original prune and would
slip past the CSV-side filter identically if ever encountered there.

## Known parser-quality issues (flagged 2026-08-13, not yet fixed)

A production run on 2026-08-13 surfaced several rows where the parser
extracted the wrong field into the wrong column. Diagnosing *why* requires
the original source PDF text (not available in this environment), so these
are documented here rather than guessed at blindly — fixing the underlying
`parse_job_cards_from_text()` layout logic without the source risks
introducing new mis-parses elsewhere. Two related bugs *were* fixed this
same session (see `normalize_ocr_spacing()`'s `WestV alley`/`Technolog
ies`/split-state-abbreviation corrections, and the `possible_duplicate_note`
company-suffix-matching fix) — the items below are the ones that still need
source-PDF-in-hand investigation:

- **Company/Position reversed — ZipRecruiter "X is looking for candidates
  like you!" digest format.** Job IDs `62e6e5b6ecc7`, `1f417c9bc270`,
  `bc73b0bc8c9e4caf9f0af19eb6e3b8be`, `9302f8c16c0b49f687c49dde40e5de2d`: all
  four have `Company = "Software Developer II"` and `Position = "Casne
  Engineering, Inc. – Bellevue, W A –"` (or a near variant) — title and
  company are swapped, and the location fragment is glued onto the end of
  the position field. This has reproduced identically across at least 4
  separate PDFs from 2026-06-14 through 2026-08-13, so it's a stable
  provider-layout bug, not a one-off OCR glitch — worth fixing once a
  sample PDF from this provider/format is available.
- **Non-company metadata captured as Company** — Job ID `8e14f158e5d944b9a3a432d535ae8784`:
  `Company = "Inventory & Food Cost Platform(Only on W2)"` (an
  employment-type disclaimer, not an employer name), from an "IntelliSearch
  Alert" digest PDF.
- **Ambiguous/truncated company names** — Job IDs `3065db7477f44571bdee5c932432a2a1`
  (`Company = "MRI"`, from a "MRI is looking for candidates like you!"
  ZipRecruiter digest) and `031f8ca9455348faba639e93c8d0434c` (`Company =
  "GenAI"`, from the same IntelliSearch Alert PDF as the metadata-as-company
  row above). Unclear whether these are genuinely truncated real company
  names or the provider's own placeholder text; needs the source PDF to
  confirm.

These rows are otherwise valid, trackable jobs (not deleted or hidden) —
they just have swapped/wrong Company or Position text and should be reviewed
manually until the underlying parser layout gap is fixed.

## Restoring from this baseline

```
git checkout recovery-baseline-20260812 -- parse_jobs.py
cp baseline/master_tracker.recovery-baseline-20260812.csv master_tracker.csv
cp baseline/jobs.recovery-baseline-20260812.db jobs.db
```
