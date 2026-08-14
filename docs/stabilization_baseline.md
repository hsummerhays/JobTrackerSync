# Recovery Baseline — 2026-08-14 (supersedes 2026-08-12 for data)

Approved as the new data recovery baseline after the 2026-08-13 concurrent-
session incident (see below). The 2026-08-12 baseline's own history is kept
intact further down this file for reference, but `master_tracker.csv` /
`jobs.db` restoration should use the 2026-08-14 snapshot.

## What's frozen (2026-08-14)

- **Data**: point-in-time copies of the live tracker, approved as the new
  4,112-record recovery baseline:
  - `baseline/master_tracker.recovery-baseline-20260814.csv`
    (sha256 `26a6183660a60c0727b30936f2f84aec646b9abcbd8e230062fa6908512fa40b`)
  - `baseline/jobs.recovery-baseline-20260814.db`
    (sha256 `b3c098c3bcc2b7481c1b805a05211e019a76bdc7abdd550554fcf95f7bef4cc2`)
- **Code**: not yet tagged/committed as a baseline — pending separate review
  of the code changes below (git history still shows working-tree changes
  only, nothing committed this session).

## 2026-08-13 concurrent-session incident and recovery

A production run on 2026-08-13 surfaced a Wheeler Machinery duplicate and
several parser mis-extractions (see "Known parser-quality issues" below,
now folded into this section since all but one item was resolved). Recovery
investigation found the working tree had been modified by a second,
uncoordinated concurrent session mid-fix (contradictory `locations_compatible()`
fuzzy-matching changes, a rewritten CSV-side dedup pass using a day-window
instead of exact-fingerprint matching) — reconciled by reverting to the
narrower, exact-match design already documented in `.agents/AGENTS.md`.

Recovery path: restored `master_tracker.csv`/`jobs.db` from a
`master_tracker(20260813-143913).csv` snapshot (all 4,039 IDs treated as
immutable except where a reviewed loser-to-survivor mapping or PDF-verified
field correction applied), then replayed the 2026-08-13 PDF folder through
the ordinary pipeline to re-ingest that day's legitimate opportunities.

**Corrections applied against direct source-PDF evidence** (not guessed):
- Wheeler Machinery Co. duplicate (`WestV alley City, UT` — a raw-extraction
  artifact of "West Valley City, UT") merged into the existing
  Applied/manual-95 record `8921e8b7319b46b5ba7d368c2c610a7f`.
- Casne Engineering, Inc. (4 instances, IDs `62e6e5b6ecc7`, `1f417c9bc270`,
  `bc73b0bc8c9e4caf9f0af19eb6e3b8be`, `24fa58bec5f44461ae2d9fda97bba62d`):
  Company/Position were swapped by a ZipRecruiter "is looking for candidates
  like you!" digest layout bug; corrected against raw PDF text
  (`Software Developer II / Casne Engineering, Inc. / Bellevue, W  A • Remote`).
- `talentarchitect.com` (2 instances): same swap pattern, corrected against
  raw PDF text.
- Two "Staff Software Engineer" Ladders-digest rows: the raw source never
  discloses a real company (a salary-teaser digest); corrected to the
  aggregator placeholder `Ladders-DailyDigest`, matching this dataset's
  existing convention.
- `GenAI` → `CVS Health` and `Inventory & Food Cost Platform(Only on W2)` →
  `Resource Innovative Technologies LLC`: title-fragment/subtitle text had
  been mis-captured as the company field; corrected against raw PDF text.
  Both had been silently excluded from every prior sync by
  `is_valid_company()` before this correction.
- `FullStack` and bare `MRI`: real company names wrongly rejected by
  `is_valid_company()` heuristics (composed-of-role-words check, and an
  exact-match junk pattern respectively) — whitelisted with source evidence,
  no field correction needed.
- `1872 Consulting`: a legitimate Rejected/Closed/Closed/Ignore/P4 decision
  made between the 14:39 snapshot and the start of recovery had been
  collaterally discarded by the baseline restore; restored from a
  pre-restore `jobs.db` snapshot that still had it.
- `Vacation & Paid Time Off`: confirmed not a real job (benefits/nav text
  misparsed as a card from a multi-job digest) — quarantined, never
  persisted to either file.
- 11 same-day ("Re-listed on X; originally seen X.") noise notes removed,
  and the underlying bug fixed in `normalize_ocr_spacing`'s relisting-note
  cleanup regex (couldn't match the current note format across the
  semicolon before "originally seen", so stale tags only ever accumulated)
  in both places it's used, plus a same-day-specific gap in the
  `REAPPLY_STATUSES` branch.

**Known limitation, not fixed**: `main()` assigns freshly-parsed postings a
random `uuid.uuid4().hex` Job ID with no dependency on source identity (PDF
path/position) — a deliberate choice (see the ID-assignment comment in
`main()`) so a later field correction can't orphan a row's history. The
practical consequence: re-running a *full* baseline-restore-and-replay cycle
does not reproduce the same IDs for newly-ingested postings, only ordinary
incremental syncs against already-ingested data are guaranteed stable
(verified: re-running the pipeline against this baseline produces zero
diffs). Deriving new IDs from stable source identity instead would be a
separate, larger design change, not attempted here.

**Reviewed and closed**: 14 additional Tracker Status mismatches between the
14:39 snapshot and the pre-restore `jobs.db` state were found alongside the
1872 Consulting case (same root cause: legitimate updates made between
14:39 and the start of recovery, collaterally discarded by the baseline
restore). Reviewed individually with the user; none were restored, each for
a specific, verified reason:

- **5 rows** (Swan Island Networks, Circle, Billee Technologies, Franki,
  LemonEdge) showed baseline=Cancelled / pre-restore=Applied. Billee's
  baseline Notes explicitly read *"Auto-Cancelled (<60 days)"* — a real
  (pre-existing, not touched this session) bug where a relisted posting
  gets auto-cancelled against its own prior Applied record. Left as
  baseline's Cancelled: each cancelled relisting row has a *separate*
  sibling row already correctly tracking the real Applied history;
  restoring the relisting row to Applied would have duplicated it.
- **7 rows** (Fast growing, Onset Group, Einstellen.io, Oddball, VoTech
  Recruiting, Ag reeYa Solutions, Studio McGee) showed baseline=Expired /
  pre-restore=Cancelled, with Review Status/Disposition/Action identical in
  both. Left as baseline's Expired — no evidence of a human cancellation.
- **Sunwest Bank** showed baseline=New / pre-restore=Rejected/Apply (an
  internally contradictory combination on its own). Left as baseline's New
  — verified 3 *other* Sunwest Bank IDs already correctly carry `Rejected`;
  this specific ID is a separate malformed/location-variant listing, not
  the same opportunity.
- **Amazon** showed baseline=New / pre-restore=Cancelled for a West Jordan,
  UT posting. Left as baseline's New/Ignore — verified a separate North
  Salt Lake, UT Amazon ID already correctly carries `Cancelled`; different
  locations, no normalization needed.

# Recovery Baseline — 2026-08-12 (superseded above for data; code history below still applies)

Frozen as the starting point for the tracker stabilization effort, after a
run of regressions where fixes validated by unit tests (stable IDs,
application history, Weave chronology/dedup, Yapi/1872 confirmation
reconstruction, same-run SQLite/CSV sync, defense/clearance scoring,
manual-score preservation, score provenance) still surfaced the next
problem in the production tracker. Local unit tests check implementation
logic; this baseline exists so future changes can also be checked against
an end-to-end contract of what must never change in the real tracker.

## What's frozen

- **Code**: git tag `v1.3.2-recovery-baseline-20260812`, commit `465a3e88b5bb`.
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

## Known parser-quality issues flagged 2026-08-13 (resolved 2026-08-14)

A production run on 2026-08-13 surfaced several rows where the parser
extracted the wrong field into the wrong column (Casne Engineering,
`Inventory & Food Cost Platform`, `GenAI`) plus two `is_valid_company()`
false positives (bare `MRI`, bare `FullStack`). All were corrected against
direct source-PDF evidence during the 2026-08-14 recovery — see that
section above for the full list and evidence. The underlying
`parse_job_cards_from_text()` provider-layout bug that produced the Casne
swap was not fixed at the source (only the already-tracked instances were
corrected); a recurrence from a future ZipRecruiter "is looking for
candidates like you!" email would need the same manual correction again
until that layout-parsing gap is fixed directly.

## Restoring from this baseline

Data (current, 2026-08-14):

```
cp baseline/master_tracker.recovery-baseline-20260814.csv master_tracker.csv
cp baseline/jobs.recovery-baseline-20260814.db jobs.db
```

Code (2026-08-12, still the last tagged baseline — the 2026-08-13/14 code
changes are not yet tagged, pending separate review):

```
git checkout v1.3.2-recovery-baseline-20260812 -- parse_jobs.py
```
