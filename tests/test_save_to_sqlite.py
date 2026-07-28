import os
import sys
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs


class TestSaveToSqliteReapplyCleanup(unittest.TestCase):
    """Regression coverage for the tuple-vs-scalar job_id bug: existing_jobs is
    keyed by (job_id, date_added), and returned_applied_ids/returned_expired_ids
    must be populated with the plain job_id string, not that tuple, or the
    DELETE ... WHERE job_id = ? executemany calls raise sqlite3.ProgrammingError
    and abort the rest of save_to_sqlite silently."""

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

    def test_returned_applied_ids_as_plain_strings_does_not_raise(self):
        self._seed_job_workflow("abc123", "Applied")
        jobs_list = [{
            "Job ID": "abc123", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New",
        }]

        # This must not raise sqlite3.ProgrammingError.
        parse_jobs.save_to_sqlite(self.db_path, jobs_list, returned_applied_ids={"abc123"})

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM job_workflow WHERE job_id = ?", ("abc123",))
        row = cursor.fetchone()
        conn.close()
        # The stale "Applied" workflow row was cleared, so the fresh "New" upsert wins.
        self.assertEqual(row[0], "New")

    def test_returned_expired_ids_as_plain_strings_does_not_raise(self):
        self._seed_job_workflow("def456", "Expired")
        jobs_list = [{
            "Job ID": "def456", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New",
        }]

        parse_jobs.save_to_sqlite(self.db_path, jobs_list, returned_expired_ids={"def456"})

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM job_workflow WHERE job_id = ?", ("def456",))
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "New")

    def test_tuple_job_id_silently_aborts_the_rest_of_the_sync(self):
        """Documents the bug this test file guards against: binding a tuple
        (the un-fixed value of ej_id, before it's unpacked to ej_id[0]) into
        the executemany DELETE raises sqlite3.ProgrammingError. The inner
        except only catches sqlite3.OperationalError, so it propagates up to
        save_to_sqlite's own catch-all `except Exception`, which swallows it
        without re-raising -- but only after aborting every upsert that would
        have run afterward, so the "New" status below never gets written and
        jobs.db silently drifts from master_tracker.csv."""
        self._seed_job_workflow("ghi789", "Applied")
        jobs_list = [{
            "Job ID": "ghi789", "Company": "Acme", "Position": "Engineer",
            "Location": "Remote", "Tracker Status": "New",
        }]

        parse_jobs.save_to_sqlite(
            self.db_path, jobs_list,
            returned_applied_ids={("ghi789", "2026-01-01")},
        )

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM job_workflow WHERE job_id = ?", ("ghi789",))
        row = cursor.fetchone()
        conn.close()
        # With the tuple bug, the sync aborts before the upsert runs, so the
        # stale "Applied" status is left in place instead of becoming "New".
        self.assertEqual(row[0], "Applied")


if __name__ == "__main__":
    unittest.main(verbosity=2)
