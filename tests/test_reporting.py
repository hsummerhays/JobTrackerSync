import os
import sys
import csv
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import (
    _print_dashboard,
    print_today_queue,
    print_analytics,
    print_todays_highlights,
)

FIELDNAMES = ["Job ID", "Company", "Position", "Location", "Tracker Status",
              "Priority", "Age (days)", "Recommendation", "Fit Score"]


class DashboardTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.tracker_path = "master_tracker.csv"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _write_rows(self, rows):
        with open(self.tracker_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)


class TestPrintDashboard(DashboardTestBase):

    def test_missing_tracker_prints_error(self):
        with patch("parse_jobs.console.print") as mock_print:
            _print_dashboard(self.tracker_path)
        mock_print.assert_any_call(f"[red]Tracker not found: {self.tracker_path}[/red]")

    def test_empty_tracker_shows_none_everywhere(self):
        self._write_rows([])
        with patch("parse_jobs.console.print") as mock_print:
            _print_dashboard(self.tracker_path)
        calls = [c.args[0] for c in mock_print.call_args_list]
        self.assertTrue(any("Apply Today (0)" in c for c in calls))
        self.assertTrue(any("None" in c for c in calls))

    def test_dashboard_sections_and_truncation(self):
        rows = []
        rows.append({"Company": "P1Co", "Position": "P1 Job", "Tracker Status": "New", "Priority": "P1", "Age (days)": "2"})
        for i in range(12):
            rows.append({"Company": f"P2Co{i}", "Position": "P2 Job", "Tracker Status": "New", "Priority": "P2", "Age (days)": "1"})
        rows.append({"Company": "ActiveCo", "Position": "Active Job", "Tracker Status": "Phone Screen", "Priority": "", "Age (days)": ""})
        rows.append({"Company": "WaitCo", "Position": "Waiting Job", "Tracker Status": "Waiting", "Priority": "", "Age (days)": "3"})
        for i in range(7):
            rows.append({"Company": f"RejCo{i}", "Position": "Rejected Job", "Tracker Status": "Rejected", "Priority": "", "Age (days)": ""})
        self._write_rows(rows)

        with patch("parse_jobs.console.print") as mock_print:
            _print_dashboard(self.tracker_path)
        calls = [c.args[0] for c in mock_print.call_args_list]
        joined = "\n".join(calls)

        self.assertIn("Apply Today (1)", joined)
        self.assertIn("Apply This Week (12)", joined)
        self.assertIn("... and 2 more", joined)
        self.assertIn("Active Pipeline (2)", joined)
        self.assertIn("Follow Up (1)", joined)
        self.assertIn("Recently Rejected / Ghosted (7)", joined)


class TestPrintTodayQueue(DashboardTestBase):

    def test_missing_tracker_prints_error(self):
        with patch("parse_jobs.console.print") as mock_print:
            print_today_queue(self.tracker_path)
        mock_print.assert_any_call(f"[red]Tracker not found: {self.tracker_path}[/red]")

    def test_empty_queue_shows_celebration(self):
        self._write_rows([])
        with patch("parse_jobs.console.print") as mock_print:
            print_today_queue(self.tracker_path)
        calls = [c.args[0] for c in mock_print.call_args_list]
        self.assertTrue(any("No jobs remaining in today's queue" in c for c in calls))

    def test_queue_lists_p1_and_p2_new_jobs(self):
        rows = [
            {"Company": "Acme", "Position": "Engineer", "Tracker Status": "New", "Priority": "P1"},
            {"Company": "Beta", "Position": "Developer", "Tracker Status": "New", "Priority": "P2"},
            {"Company": "Gamma", "Position": "Should not show", "Tracker Status": "New", "Priority": "P3"},
            {"Company": "Delta", "Position": "Applied job", "Tracker Status": "Applied", "Priority": "P1"},
        ]
        self._write_rows(rows)
        with patch("parse_jobs.console.print") as mock_print:
            print_today_queue(self.tracker_path)
        calls = [c.args[0] for c in mock_print.call_args_list]
        joined = "\n".join(calls)
        self.assertIn("Acme", joined)
        self.assertIn("Beta", joined)
        self.assertNotIn("Gamma", joined)
        self.assertNotIn("Delta", joined)
        self.assertIn("2 jobs remaining", joined)


class TestPrintAnalyticsGaps(DashboardTestBase):

    def test_missing_db_prints_error(self):
        with patch("parse_jobs.console.print") as mock_print:
            print_analytics(db_path="does_not_exist.db")
        mock_print.assert_any_call(
            "[red]Database not found: does_not_exist.db. Please run sync first to build the database.[/red]"
        )

    def test_missing_jobs_table_prints_error(self):
        conn = sqlite3.connect("empty.db")
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
        conn.commit()
        conn.close()
        with patch("parse_jobs.console.print") as mock_print:
            print_analytics(db_path="empty.db")
        mock_print.assert_any_call("[red]Jobs table not found in database. Please run sync first.[/red]")

    def test_query_exception_is_reported(self):
        # jobs table exists but job_workflow doesn't -- the JOIN in
        # print_analytics raises OperationalError, which should be caught.
        conn = sqlite3.connect("broken.db")
        conn.execute("CREATE TABLE jobs (job_id TEXT)")
        conn.commit()
        conn.close()
        with patch("parse_jobs.console.print") as mock_print:
            print_analytics(db_path="broken.db")
        calls = [c.args[0] for c in mock_print.call_args_list]
        self.assertTrue(any("Error reading database" in c for c in calls))

    def test_diverse_providers_and_missing_latency_data(self):
        conn = sqlite3.connect("analytics.db")
        conn.execute("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY, company TEXT, position TEXT, location TEXT,
                tracker_status TEXT, provider TEXT, fit_score INTEGER, date_added TEXT, last_seen TEXT, notes TEXT
            )
        """)
        conn.execute("CREATE TABLE job_workflow (job_id TEXT PRIMARY KEY, updated_at TEXT, notes TEXT)")
        providers = ["Glassdoor Export", "ZipRecruiter Alert", "jobs.utah.gov", "The Ladders", "Mystery Board", ""]
        for i, prov in enumerate(providers):
            conn.execute(
                "INSERT INTO jobs (job_id, company, position, location, tracker_status, provider, fit_score, date_added) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"job{i}", f"Company{i}", "Engineer", "Remote", "New", prov, 50, "2026")
            )
        conn.commit()
        conn.close()

        with patch("parse_jobs.console.print") as mock_print:
            print_analytics(db_path="analytics.db")
        self.assertTrue(mock_print.called)


class TestPrintTodaysHighlights(DashboardTestBase):

    def test_no_top_jobs_and_no_new_jobs(self):
        with patch("parse_jobs.console.print") as mock_print:
            print_todays_highlights([], [], db_path="missing_highlights.db")
        panels = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any(hasattr(p, "renderable") for p in panels))

    def test_missing_db_reports_gracefully(self):
        with patch("parse_jobs.console.print") as mock_print:
            print_todays_highlights([], [], db_path="totally_missing_highlights.db")
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(
            any(isinstance(c, str) and "Could not load prior-interview companies" in c for c in calls)
        )

    def test_full_highlights_with_new_company_skill_and_reunion(self):
        conn = sqlite3.connect("highlights.db")
        conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, company TEXT)")
        conn.execute("CREATE TABLE job_workflow (job_id TEXT PRIMARY KEY, tracker_status TEXT)")
        conn.execute("INSERT INTO jobs (job_id, company) VALUES ('old1', 'Reunion Corp')")
        conn.execute("INSERT INTO job_workflow (job_id, tracker_status) VALUES ('old1', 'Phone Screen')")
        conn.commit()
        conn.close()

        new_job = {
            "Job ID": "new1", "Tracker Status": "New", "Recommendation": "★★★★★ Apply Now",
            "Fit Score": 95, "Company": "Brand New Co", "Position": "Backend Engineer",
            "Location": "Remote", "Matched Skills": "React, AWS", "Notes": ""
        }
        reunion_job = {
            "Job ID": "new2", "Tracker Status": "New", "Recommendation": "★★★★☆ Strong",
            "Fit Score": 80, "Company": "Reunion Corp", "Position": "Platform Engineer",
            "Location": "Remote", "Matched Skills": "", "Notes": ""
        }
        combined_jobs = [new_job, reunion_job]

        with patch("parse_jobs.console.print") as mock_print:
            print_todays_highlights([new_job, reunion_job], combined_jobs, db_path="highlights.db")

        self.assertTrue(mock_print.called)


if __name__ == "__main__":
    unittest.main()
