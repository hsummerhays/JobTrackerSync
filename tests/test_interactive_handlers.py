import os
import sys
import csv
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import handle_manual_add, handle_status_update, handle_interactive_update

TRACKER_HEADERS = [
    "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider",
    "Source PDF", "Confidence", "Fit Score", "Priority", "Company Type",
    "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company",
    "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes", "Recruiter", "Hiring Manager"
]


class HandlerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.tracker_path = "master_tracker.csv"
        self.db_path = "jobs.db"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _init_tracker(self, rows=None):
        with open(self.tracker_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TRACKER_HEADERS, restval="")
            writer.writeheader()
            for row in (rows or []):
                writer.writerow(row)

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY, review_status TEXT, job_type TEXT, company TEXT, position TEXT, location TEXT,
                url TEXT, provider TEXT, source_pdf TEXT, confidence TEXT, fit_score INTEGER, priority TEXT,
                company_type TEXT, recommendation TEXT, tracker_status TEXT, disposition TEXT, action TEXT,
                existing_company TEXT, reason TEXT, matched_skills TEXT, missing_skills TEXT, date_added TEXT, last_seen TEXT,
                notes TEXT, recruiter TEXT, hiring_manager TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE job_workflow (
                job_id TEXT PRIMARY KEY, tracker_status TEXT, review_status TEXT, action TEXT, disposition TEXT,
                notes TEXT, updated_at TEXT, updated_by TEXT, follow_up_date TEXT, last_contact_date TEXT
            )
        """)
        conn.commit()
        return conn


class TestHandleManualAdd(HandlerTestBase):

    def test_non_interactive_missing_company_returns_false(self):
        self.assertFalse(handle_manual_add(company=None, position="Engineer", interactive=False))

    def test_non_interactive_missing_position_returns_false(self):
        self.assertFalse(handle_manual_add(company="Acme Corp", position=None, interactive=False))

    def test_interactive_flow_with_retry_and_all_defaults(self):
        self._init_tracker()
        # Company prompt: first empty entry triggers the "required" retry loop.
        responses = iter([
            "",              # Company: empty -> retry
            "Acme Corp",     # Company: valid
            "Engineer",      # Position
            "",              # Location -> default Remote
            "",              # Job Type -> default Software Engineer
            "",              # Provider -> default Manual
            "",              # Recruiter
            "",              # Hiring Manager
            "",              # URL
            "not-a-number",  # Fit Score -> ValueError -> default 70
            "",              # Recommendation -> default Strong
            "n",             # Applied? -> status "New"
            "",              # Notes
        ])
        with patch("builtins.input", side_effect=lambda *_: next(responses)):
            result = handle_manual_add(interactive=True)
        self.assertIsNone(result)  # falls through to end of function, no explicit return

        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Company"], "Acme Corp")
        self.assertEqual(rows[0]["Location"], "Remote")
        self.assertEqual(rows[0]["Job Type"], "Software Engineer")
        self.assertEqual(rows[0]["Provider"], "Manual")
        self.assertEqual(rows[0]["Fit Score"], "70")
        self.assertEqual(rows[0]["Recommendation"], "★★★★☆ Strong")
        self.assertEqual(rows[0]["Tracker Status"], "New")

    def test_interactive_operations_job_type_and_status_selection(self):
        self._init_tracker()
        responses = iter([
            "Beta Corp", "Warehouse Lead", "Remote",
            "2",             # Job Type -> Operations
            "Manual", "", "", "",
            "80",
            "★★★★★ Apply Now",
            "y",             # Applied? -> yes, prompts status list
            "Rejected",      # valid status selection
            "Didn't work out",
        ])
        with patch("builtins.input", side_effect=lambda *_: next(responses)):
            handle_manual_add(interactive=True)

        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["Job Type"], "Operations")
        self.assertEqual(rows[0]["Tracker Status"], "Rejected")
        self.assertEqual(rows[0]["Review Status"], "Closed")
        self.assertEqual(rows[0]["Action"], "Ignore")

    def test_interactive_invalid_status_choice_defaults_to_applied(self):
        self._init_tracker()
        responses = iter([
            "Gamma Corp", "Engineer", "", "", "", "", "", "",
            "70", "",
            "y",
            "NotARealStatus",  # invalid -> defaults to Applied
            "",
        ])
        with patch("builtins.input", side_effect=lambda *_: next(responses)):
            handle_manual_add(interactive=True)

        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["Tracker Status"], "Applied")

    def test_existing_company_marked_yes_when_already_in_tracker(self):
        self._init_tracker(rows=[{"Company": "Acme Corp", "Job ID": "existing1"}])
        handle_manual_add(company="Acme Corp", position="New Role", interactive=False)
        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        new_row = next(r for r in rows if r["Position"] == "New Role")
        self.assertEqual(new_row["Existing Company"], "Yes")

    def test_existing_company_check_exception_is_reported(self):
        self._init_tracker()
        original_dictreader = csv.DictReader
        state = {"calls": 0}

        def flaky_dictreader(f, *a, **kw):
            state["calls"] += 1
            if state["calls"] == 1:
                raise RuntimeError("boom")
            return original_dictreader(f, *a, **kw)

        with patch("parse_jobs.csv.DictReader", side_effect=flaky_dictreader):
            with patch("parse_jobs.console.print") as mock_print:
                handle_manual_add(company="Acme Corp", position="Engineer", interactive=False)
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Could not read" in c for c in calls))

    def test_rerun_same_day_updates_existing_row_instead_of_duplicating(self):
        self._init_tracker()
        handle_manual_add(company="Acme Corp", position="Engineer", location="Remote",
                           status="New", notes="first", interactive=False)
        handle_manual_add(company="Acme Corp", position="Engineer", location="Remote",
                           status="Applied", notes="second", interactive=False)

        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        acme_rows = [r for r in rows if r["Company"] == "Acme Corp"]
        self.assertEqual(len(acme_rows), 1)
        self.assertEqual(acme_rows[0]["Tracker Status"], "Applied")
        self.assertEqual(acme_rows[0]["Notes"], "second")


class TestHandleStatusUpdate(HandlerTestBase):

    def test_invalid_status_rejected(self):
        self.assertFalse(handle_status_update("Acme", "NotAStatus"))

    def test_missing_db_returns_false(self):
        self.assertFalse(handle_status_update("Acme", "Applied"))

    def test_no_matches_returns_false(self):
        conn = self._init_db()
        conn.commit()
        conn.close()
        self.assertFalse(handle_status_update("Nonexistent", "Applied"))

    def test_multiple_matches_returns_false(self):
        conn = self._init_db()
        conn.execute("INSERT INTO jobs (job_id, company, position) VALUES ('id1', 'Acme Corp', 'Engineer A')")
        conn.execute("INSERT INTO jobs (job_id, company, position) VALUES ('id2', 'Acme Corp', 'Engineer B')")
        conn.commit()
        conn.close()
        self.assertFalse(handle_status_update("Acme", "Applied"))

    def test_rejected_status_sets_closed_review_and_ignore_action(self):
        conn = self._init_db()
        conn.execute(
            "INSERT INTO jobs (job_id, company, position, date_added) VALUES ('id1', 'Acme Corp', 'Engineer', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        self.assertTrue(handle_status_update("id1", "Rejected", "Not a fit"))

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id='id1'").fetchone()
        conn.close()
        self.assertEqual(row, ("Rejected", "Closed", "Ignore", "Closed"))

    def test_appends_new_row_to_tracker_with_computed_age(self):
        conn = self._init_db()
        conn.execute(
            "INSERT INTO jobs (job_id, company, position, date_added) VALUES ('id1', 'Acme Corp', 'Engineer', '2020-01-01')"
        )
        conn.commit()
        conn.close()
        self._init_tracker(rows=[])

        handle_status_update("id1", "Applied", "note")

        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertTrue(int(rows[0]["Age (days)"]) > 1000)

    def test_updates_existing_tracker_row_in_place(self):
        conn = self._init_db()
        conn.execute(
            "INSERT INTO jobs (job_id, company, position, date_added) VALUES ('id1', 'Acme Corp', 'Engineer', '2026-01-01')"
        )
        conn.commit()
        conn.close()
        self._init_tracker(rows=[{"Job ID": "id1", "Company": "Acme Corp", "Position": "Engineer", "Tracker Status": "New"}])

        handle_status_update("id1", "Applied", "note")

        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tracker Status"], "Applied")


class TestHandleInteractiveUpdate(HandlerTestBase):

    def test_missing_db_returns_false(self):
        self.assertFalse(handle_interactive_update())

    def test_no_active_jobs_returns_false(self):
        conn = self._init_db()
        conn.commit()
        conn.close()
        self.assertFalse(handle_interactive_update())

    def _seed_active_job(self, conn):
        conn.execute(
            "INSERT INTO jobs (job_id, company, position, tracker_status, priority) "
            "VALUES ('id1', 'Acme Corp', 'Engineer', 'New', 'P1 – Apply Today')"
        )
        conn.commit()
        conn.close()

    def test_empty_job_choice_returns_false(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=[""]):
            self.assertFalse(handle_interactive_update())

    def test_out_of_range_job_choice_returns_false(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=["99"]):
            with patch("parse_jobs.console.print") as mock_print:
                self.assertFalse(handle_interactive_update())
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Invalid selection" in c for c in calls))

    def test_non_numeric_job_choice_is_cancelled(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=["abc"]):
            with patch("parse_jobs.console.print") as mock_print:
                self.assertFalse(handle_interactive_update())
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Operation cancelled" in c for c in calls))

    def test_keyboard_interrupt_during_job_choice_is_cancelled(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertFalse(handle_interactive_update())

    def test_empty_status_choice_returns_false(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=["1", ""]):
            self.assertFalse(handle_interactive_update())

    def test_out_of_range_status_choice_returns_false(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=["1", "99"]):
            self.assertFalse(handle_interactive_update())

    def test_successful_selection_dispatches_to_handle_status_update(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        # 1 -> select the only job; 2 -> "Applied" is index 2 in valid_statuses; then notes.
        with patch("builtins.input", side_effect=["1", "2", "Looks promising"]), \
             patch("parse_jobs.handle_status_update", return_value=True) as mock_update:
            result = handle_interactive_update()
        self.assertTrue(result)
        mock_update.assert_called_once_with("id1", "Applied", "Looks promising")

    def test_empty_notes_passed_as_none(self):
        conn = self._init_db()
        self._seed_active_job(conn)
        with patch("builtins.input", side_effect=["1", "2", ""]), \
             patch("parse_jobs.handle_status_update", return_value=True) as mock_update:
            handle_interactive_update()
        mock_update.assert_called_once_with("id1", "Applied", None)


if __name__ == "__main__":
    unittest.main()
