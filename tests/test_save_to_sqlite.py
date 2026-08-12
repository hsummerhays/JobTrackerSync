import os
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs


class TestSaveToSqliteExpiredRediscovery(unittest.TestCase):
    """save_to_sqlite() no longer accepts a returned_expired_ids parameter or
    deletes anything: an expired job rediscovered on a later run is linked to
    its old record via Previous Job ID (set by the dedup pass in main()) and
    written as a new row instead, so the old row's job_workflow history is
    never force-deleted. This also removes the tuple-vs-scalar job_id bug
    that used to live in the now-deleted DELETE ... executemany call."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.db_path = "jobs.db"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _seed_job_workflow(self, job_id, tracker_status="Applied"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_workflow (
                job_id TEXT PRIMARY KEY, tracker_status TEXT, review_status TEXT,
                action TEXT, disposition TEXT, notes TEXT, updated_at TEXT,
                updated_by TEXT, follow_up_date TEXT, last_contact_date TEXT
            )
        """)
        cursor.execute(
            "INSERT INTO job_workflow (job_id, tracker_status) VALUES (?, ?)",
            (job_id, tracker_status),
        )
        conn.commit()
        conn.close()

    def test_old_expired_row_history_survives_a_linked_rediscovery(self):
        self._seed_job_workflow("old-expired-id", "Expired")
        jobs_list = [{
            "Job ID": "new-id", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New",
            "Previous Job ID": "old-expired-id",
        }]

        parse_jobs.save_to_sqlite(self.db_path, jobs_list)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM job_workflow WHERE job_id = ?", ("old-expired-id",))
        old_row = cursor.fetchone()
        cursor.execute("SELECT tracker_status, previous_job_id FROM jobs WHERE job_id = ?", ("new-id",))
        new_row = cursor.fetchone()
        conn.close()

        self.assertEqual(old_row[0], "Expired")
        self.assertEqual(new_row, ("New", "old-expired-id"))


class TestSaveToSqliteSchemaRecovery(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.db_path = "jobs.db"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def test_schema_drift_heals_columns_without_dropping_existing_rows(self):
        # Pre-create a jobs table missing columns the INSERT expects, with a
        # pre-existing row that is NOT part of this run's jobs_list, so the
        # upsert raises OperationalError and exercises the additive-repair
        # recovery path.
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY, review_status TEXT, job_type TEXT, company TEXT, position TEXT,
                location TEXT, url TEXT, provider TEXT, source_pdf TEXT, confidence TEXT, fit_score INTEGER,
                priority TEXT, company_type TEXT, recommendation TEXT, tracker_status TEXT, disposition TEXT,
                action TEXT, existing_company TEXT, reason TEXT, date_added TEXT, last_seen TEXT, notes TEXT
            )
        """)
        conn.execute(
            "INSERT INTO jobs (job_id, company, tracker_status) VALUES ('preexisting1', 'OldCo', 'Applied')"
        )
        conn.commit()
        conn.close()

        jobs_list = [{
            "Job ID": "id1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "New", "Matched Skills": "Java", "Missing Skills": "AWS",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT company, matched_skills, missing_skills FROM jobs WHERE job_id = 'id1'"
        ).fetchone()
        wf_row = conn.execute("SELECT tracker_status FROM job_workflow WHERE job_id = 'id1'").fetchone()
        preexisting = conn.execute(
            "SELECT company, tracker_status FROM jobs WHERE job_id = 'preexisting1'"
        ).fetchone()
        conn.close()
        self.assertEqual(row, ("Acme", "Java", "AWS"))
        self.assertEqual(wf_row[0], "New")
        # The pre-existing row -- absent from this run's jobs_list -- must
        # survive the schema-healing retry instead of being dropped along
        # with the whole table.
        self.assertEqual(preexisting, ("OldCo", "Applied"))

    def test_legacy_job_status_table_is_migrated_and_dropped(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE job_status (
                job_id TEXT PRIMARY KEY, tracker_status TEXT, updated_at TEXT, updated_by TEXT,
                notes TEXT, follow_up_date TEXT, last_contact_date TEXT
            )
        """)
        conn.execute(
            "INSERT INTO job_status (job_id, tracker_status, notes) VALUES ('legacy1', 'Applied', 'from old table')"
        )
        conn.commit()
        conn.close()

        parse_jobs.save_to_sqlite(self.db_path, [])

        conn = sqlite3.connect(self.db_path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        wf_row = conn.execute(
            "SELECT tracker_status, notes FROM job_workflow WHERE job_id = 'legacy1'"
        ).fetchone()
        conn.close()
        self.assertNotIn("job_status", tables)
        self.assertEqual(wf_row, ("Applied", "from old table"))

    def _seed_recent_application(self, position="Engineer", location="Remote"):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY, review_status TEXT, job_type TEXT, company TEXT, position TEXT,
                location TEXT, url TEXT, provider TEXT, source_pdf TEXT, confidence TEXT, fit_score INTEGER,
                priority TEXT, company_type TEXT, recommendation TEXT, tracker_status TEXT, disposition TEXT,
                action TEXT, existing_company TEXT, reason TEXT, matched_skills TEXT, missing_skills TEXT,
                date_added TEXT, last_seen TEXT, notes TEXT, recruiter TEXT, hiring_manager TEXT
            )
        """)
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO jobs (job_id, company, position, location, tracker_status, date_added) "
            "VALUES ('old1', 'Acme', ?, ?, 'Applied', ?)",
            (position, location, recent_date),
        )
        conn.commit()
        conn.close()

    def test_recent_application_same_role_is_auto_cancelled(self):
        self._seed_recent_application(position="Engineer", location="Remote")

        jobs_list = [{
            "Job ID": "new1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "New",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT tracker_status, review_status, action, disposition, reason FROM jobs WHERE job_id = 'new1'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "Cancelled")
        self.assertEqual(row[1], "Closed")
        self.assertEqual(row[2], "Ignore")
        self.assertEqual(row[3], "Closed")
        self.assertIn("Already Applied within", row[4])

    def test_recent_application_different_role_stays_new(self):
        # A recent application to one role at a company must not auto-cancel
        # an unrelated role at the same company -- the match now requires
        # company AND position (and a compatible location), not company alone.
        self._seed_recent_application(position="Engineer", location="Remote")

        jobs_list = [{
            "Job ID": "new1", "Company": "Acme", "Position": "Different Role", "Location": "Remote",
            "Tracker Status": "New",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT tracker_status FROM jobs WHERE job_id = 'new1'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "New")


class TestSaveToSqliteWorkflowProvenance(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.db_path = "jobs.db"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def test_last_seen_advances_on_rediscovery(self):
        job = {
            "Job ID": "job1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "New", "Date Added": "2026-01-01", "Last Seen": "2026-01-01",
        }
        parse_jobs.save_to_sqlite(self.db_path, [job])

        job["Last Seen"] = "2026-01-05"
        parse_jobs.save_to_sqlite(self.db_path, [job])

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT last_seen FROM jobs WHERE job_id = 'job1'").fetchone()
        conn.close()
        self.assertEqual(row[0], "2026-01-05")

    def test_parser_write_cannot_downgrade_user_set_status_to_terminal(self):
        # A human set this job to Applied via --update (status_source='user').
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE job_workflow (
                job_id TEXT PRIMARY KEY, tracker_status TEXT, review_status TEXT,
                action TEXT, disposition TEXT, updated_at TEXT, updated_by TEXT,
                notes TEXT, follow_up_date TEXT, last_contact_date TEXT, status_source TEXT
            )
        """)
        conn.execute(
            "INSERT INTO job_workflow (job_id, tracker_status, status_source) VALUES ('job1', 'Applied', 'user')"
        )
        conn.commit()
        conn.close()

        # A later automated parser pass tries to rediscover the same job as a
        # "New" duplicate and cancel it -- this must not overwrite the
        # user-set Applied status with a system-generated Cancelled.
        jobs_list = [{
            "Job ID": "job1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "Cancelled",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT tracker_status FROM job_workflow WHERE job_id = 'job1'").fetchone()
        conn.close()
        self.assertEqual(row[0], "Applied")

    def test_parser_write_cannot_downgrade_historical_row_with_blank_status_source(self):
        # A row that predates the status_source column (or was migrated from
        # an older schema) has status_source = NULL/blank, not 'user'. It
        # must still be protected from an automated parser pass overwriting
        # its active Applied status with a system-generated Cancelled --
        # protection can't depend on provenance being recorded.
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE job_workflow (
                job_id TEXT PRIMARY KEY, tracker_status TEXT, review_status TEXT,
                action TEXT, disposition TEXT, updated_at TEXT, updated_by TEXT,
                notes TEXT, follow_up_date TEXT, last_contact_date TEXT, status_source TEXT
            )
        """)
        conn.execute(
            "INSERT INTO job_workflow (job_id, tracker_status, status_source) VALUES ('job1', 'Applied', NULL)"
        )
        conn.commit()
        conn.close()

        jobs_list = [{
            "Job ID": "job1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "Cancelled",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT tracker_status FROM job_workflow WHERE job_id = 'job1'").fetchone()
        conn.close()
        self.assertEqual(row[0], "Applied")


class TestSaveToSqliteValidityDedupFilter(unittest.TestCase):
    """2026-08-12: jobs.db had no equivalent of the is_valid_company() gate
    evaluate_job() applies, or the CSV-side fingerprint-dedup pass, so junk
    company names and legacy-Job-ID duplicates of already-tracked jobs
    accumulated there indefinitely even though the CSV correctly excluded
    them (see docs/stabilization_baseline.md). These tests cover the write
    path filter added to close that gap."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.db_path = "jobs.db"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _job_ids(self):
        conn = sqlite3.connect(self.db_path)
        ids = {r[0] for r in conn.execute("SELECT job_id FROM jobs").fetchall()}
        conn.close()
        return ids

    def test_invalid_company_row_is_not_written(self):
        jobs_list = [{
            "Job ID": "junk1", "Company": "Actively recruiting", "Position": "Senior Engineer",
            "Location": "Draper, UT", "Tracker Status": "Expired", "Date Added": "2026-07-20",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)
        self.assertEqual(self._job_ids(), set())

    def test_valid_company_row_is_still_written(self):
        jobs_list = [{
            "Job ID": "good1", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New", "Date Added": "2026-07-20",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)
        self.assertEqual(self._job_ids(), {"good1"})

    def test_legacy_id_duplicate_same_fingerprint_and_date_is_skipped(self):
        # "current1" already occupies this (fingerprint, date_added) pair --
        # a second row for the same job under a different (legacy) Job ID
        # must not be written as a second row.
        first = {
            "Job ID": "current1", "Company": "Onebrief, Inc", "Position": "Senior Engineer",
            "Location": "Remote", "Tracker Status": "Applied", "Date Added": "2026-07-20",
            "Fingerprint": "onebriefinc|seniorengineer|remote",
        }
        parse_jobs.save_to_sqlite(self.db_path, [first])

        legacy_dupe = {
            "Job ID": "legacy_old_hash", "Company": "Onebrief, Inc", "Position": "Senior Engineer",
            "Location": "Remote", "Tracker Status": "Applied", "Date Added": "2026-07-20",
            "Fingerprint": "onebriefinc|seniorengineer|remote",
        }
        parse_jobs.save_to_sqlite(self.db_path, [legacy_dupe])

        self.assertEqual(self._job_ids(), {"current1"})

    def test_duplicate_fingerprint_collision_merges_instead_of_silently_dropping(self):
        """2026-08-12 regression: two independently-tracked rows for the same
        real employer (e.g. "Podium" tracked twice, or "Collective Health" vs
        "Collectivehealth, Inc.") had never collided before, so each carried
        its own human-set status and notes. A canonical_job_key() change that
        made them collide caused the loser to vanish with no trace -- including
        a human-Rejected row's status and notes. The loser must never get its
        own row (that's still correct dedup behavior), but its status and
        notes must be merged into the surviving row, not discarded."""
        owner = {
            "Job ID": "owner1", "Company": "Collective Health", "Position": "Lead Backend Engineer",
            "Location": "Lehi, UT", "Tracker Status": "New", "Date Added": "2026-07-08",
            "Fingerprint": "collectivehealth|leadbackendengineer|lehiut",
        }
        parse_jobs.save_to_sqlite(self.db_path, [owner])

        losing = {
            "Job ID": "loser1", "Company": "Collectivehealth, Inc.", "Position": "Lead Backend Engineer",
            "Location": "Lehi, UT", "Tracker Status": "Rejected", "Date Added": "2026-07-08",
            "Notes": "Poor fit in February. Applied and was rejected in July",
            "Fingerprint": "collectivehealth|leadbackendengineer|lehiut",
        }
        parse_jobs.save_to_sqlite(self.db_path, [losing])

        self.assertEqual(self._job_ids(), {"owner1"})
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT tracker_status, notes FROM jobs WHERE job_id = 'owner1'").fetchone()
        conn.close()
        # Rejected (rank 50) outranks New (rank 10) -- the surviving row picks
        # up the more-decided status instead of staying "New".
        self.assertEqual(row[0], "Rejected")
        self.assertIn("loser1", row[1])
        self.assertIn("Poor fit in February. Applied and was rejected in July", row[1])

    def test_duplicate_fingerprint_collision_deletes_preexisting_loser_row(self):
        """2026-08-13 regression: when the loser already has its OWN row in
        jobs.db from an earlier run (not just a freshly-parsed card that never
        got inserted), merging it into the owner must delete that row, not
        just leave it un-refreshed. clean_existing_tracker() restores to the
        CSV any jobs.db row whose Job ID the CSV doesn't already have -- an
        orphaned-but-still-present loser row would get silently resurrected
        as a duplicate on the very next ordinary sync, undoing the merge."""
        owner = {
            "Job ID": "owner1", "Company": "Brady Corporation", "Position": "Senior Engineer",
            "Location": "Salt Lake City, UT", "Tracker Status": "Expired", "Date Added": "2026-06-14",
            "Fingerprint": "bradycorporation|seniorengineer|saltlakecityut",
        }
        parse_jobs.save_to_sqlite(self.db_path, [owner])

        loser = {
            "Job ID": "loser1", "Company": "Brady", "Position": "Senior Engineer",
            "Location": "Salt Lake City, UT", "Tracker Status": "Expired", "Date Added": "2026-06-14",
            "Notes": "Source Index: 17-5", "Fingerprint": "brady|seniorengineer|saltlakecityut",
        }
        parse_jobs.save_to_sqlite(self.db_path, [loser])
        self.assertEqual(self._job_ids(), {"owner1", "loser1"})

        # Now re-submit the loser with a fingerprint forced to collide with
        # the owner -- simulating the consolidation pass that discovered the
        # two rows are the same real employer under different spellings.
        loser_colliding = dict(loser)
        loser_colliding["Fingerprint"] = "bradycorporation|seniorengineer|saltlakecityut"
        parse_jobs.save_to_sqlite(self.db_path, [loser_colliding])

        self.assertEqual(self._job_ids(), {"owner1"})
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT notes FROM jobs WHERE job_id = 'owner1'").fetchone()
        wf_row = conn.execute("SELECT job_id FROM job_workflow WHERE job_id = 'loser1'").fetchone()
        conn.close()
        self.assertIn("Source Index: 17-5", row[0])
        self.assertIsNone(wf_row)

    def test_duplicate_fingerprint_collision_promotes_manual_score_from_losing_row(self):
        """A losing row carrying a manual score override (set via --update
        --fit-score) must not lose that override just because it collided
        with an auto-scored row on the same fingerprint -- 'manual' always
        wins, same precedence as the ordinary ON CONFLICT upsert path."""
        owner = {
            "Job ID": "owner1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "New", "Date Added": "2026-07-20", "Fit Score": 40, "Priority": "P3 – Investigate",
            "Fingerprint": "acme|engineer|remote", "Score Source": "parser",
        }
        parse_jobs.save_to_sqlite(self.db_path, [owner])

        losing = {
            "Job ID": "loser1", "Company": "Acme", "Position": "Engineer", "Location": "Remote",
            "Tracker Status": "New", "Date Added": "2026-07-20", "Fit Score": 95, "Priority": "P1 – Apply today",
            "Recommendation": "★★★★★ Apply Now", "Fingerprint": "acme|engineer|remote", "Score Source": "manual",
        }
        parse_jobs.save_to_sqlite(self.db_path, [losing])

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT fit_score, priority, recommendation, score_source FROM jobs WHERE job_id = 'owner1'"
        ).fetchone()
        conn.close()
        self.assertEqual(row, (95, "P1 – Apply today", "★★★★★ Apply Now", "manual"))

    def test_relisting_same_fingerprint_different_date_is_not_treated_as_duplicate(self):
        # A job that expired and was later reposted gets a new Job ID and a
        # new Date Added but the same fingerprint -- this is legitimate
        # history, not a duplicate, and must not be collapsed away.
        expired = {
            "Job ID": "expired_run1", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "Expired", "Date Added": "2026-06-01",
            "Fingerprint": "acme|engineer|remote",
        }
        reposted = {
            "Job ID": "reposted_run2", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New", "Date Added": "2026-07-15",
            "Fingerprint": "acme|engineer|remote", "Previous Job ID": "expired_run1",
        }
        parse_jobs.save_to_sqlite(self.db_path, [expired])
        parse_jobs.save_to_sqlite(self.db_path, [reposted])

        self.assertEqual(self._job_ids(), {"expired_run1", "reposted_run2"})

    def test_reupserting_the_same_job_id_is_not_treated_as_its_own_duplicate(self):
        job = {
            "Job ID": "job1", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New", "Date Added": "2026-07-20",
            "Fingerprint": "acme|engineer|remote",
        }
        parse_jobs.save_to_sqlite(self.db_path, [job])
        job["Tracker Status"] = "Applied"
        parse_jobs.save_to_sqlite(self.db_path, [job])

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT tracker_status FROM jobs WHERE job_id = 'job1'").fetchone()
        conn.close()
        self.assertEqual(self._job_ids(), {"job1"})
        self.assertEqual(row[0], "Applied")

    def test_manually_added_job_bypasses_the_company_validity_filter(self):
        # The CLI "add manual opportunity" path marks its job dict with
        # _status_source == "user" -- a human typed this company name
        # directly, so is_valid_company()'s auto-parse-junk heuristics
        # (e.g. rejecting names containing "contract") must not apply.
        jobs_list = [{
            "Job ID": "manual1", "Company": "Contract Engineering LLC", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New", "Date Added": "2026-07-20",
            "_status_source": "user",
        }]
        parse_jobs.save_to_sqlite(self.db_path, jobs_list)
        self.assertEqual(self._job_ids(), {"manual1"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
