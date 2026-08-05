import os
import sys
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import query_jobs


class TestQueryJobs(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.db_path = "jobs.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE jobs (
                job_id TEXT,
                company TEXT,
                position TEXT,
                tracker_status TEXT,
                notes TEXT,
                source_pdf TEXT,
                date_added TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _insert_job(self, job_id, company, position, status="New", notes=None,
                     source_pdf=None, date_added="2024-01-01"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO jobs (job_id, company, position, tracker_status, notes, source_pdf, date_added) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, company, position, status, notes, source_pdf, date_added)
        )
        conn.commit()
        conn.close()

    def _run(self, query_arg=None):
        argv = ["query_jobs.py"] if query_arg is None else ["query_jobs.py", query_arg]
        buf = io.StringIO()
        with patch.object(sys, "argv", argv):
            with redirect_stdout(buf):
                query_jobs.main()
        return buf.getvalue()

    def test_no_results_exits_cleanly(self):
        with self.assertRaises(SystemExit) as cm:
            self._run("Nonexistent")
        self.assertEqual(cm.exception.code, 0)

    def test_no_results_message(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["query_jobs.py", "Nonexistent"]):
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    query_jobs.main()
        self.assertIn("No jobs found matching 'Nonexistent'.", buf.getvalue())

    def test_basic_output_and_position_normalization(self):
        self._insert_job("id1", "Acme Corp", "Engineer Software Engineer",
                          status="Applied", date_added="2024-01-01")
        out = self._run("Acme")
        self.assertIn("Found 1 job(s) matching 'Acme'", out)
        # Leading "Engineer " prefix should be stripped
        self.assertIn("Acme Corp — Software Engineer", out)
        self.assertIn("**ID:** `id1`", out)
        self.assertIn("**Date:** 2024-01-01", out)
        self.assertIn("**Status:** Applied", out)
        self.assertNotIn("Notes:", out)
        self.assertNotIn("Source PDF:", out)

    def test_case_insensitive_match(self):
        self._insert_job("id1", "Acme Corp", "Engineer", date_added="2024-01-01")
        out = self._run("acme")
        self.assertIn("Found 1 job(s)", out)

    def test_notes_are_flattened_and_wrapped(self):
        self._insert_job("id1", "Acme Corp", "Engineer",
                          notes="Line one\r\nLine two\nLine three", date_added="2024-01-01")
        out = self._run("Acme")
        self.assertIn("**Notes:**", out)
        self.assertNotIn("\r", out)
        self.assertIn("Line one", out)
        self.assertIn("Line two Line three", out)

    def test_source_pdf_generates_markdown_link(self):
        self._insert_job("id1", "Acme Corp", "Engineer",
                          source_pdf=r"C:\postings\Acme.pdf", date_added="2024-01-01")
        out = self._run("Acme")
        self.assertIn("**Source PDF:**", out)
        self.assertIn("Acme.pdf", out)
        self.assertIn("file:///C:/postings/Acme.pdf", out)

    def test_source_pdf_multivalue_uses_first_entry(self):
        self._insert_job("id1", "Acme Corp", "Engineer",
                          source_pdf=r"C:\postings\First.pdf|C:\postings\Second.pdf",
                          date_added="2024-01-01")
        out = self._run("Acme")
        self.assertIn("First.pdf", out)
        self.assertNotIn("Second.pdf", out)

    def test_results_ordered_by_date_added_desc(self):
        self._insert_job("id1", "Acme Corp", "Older Job", date_added="2024-01-01")
        self._insert_job("id2", "Acme Corp", "Newer Job", date_added="2024-06-01")
        out = self._run("Acme")
        self.assertLess(out.index("Newer Job"), out.index("Older Job"))

    def test_default_empty_query_matches_all(self):
        self._insert_job("id1", "Acme Corp", "Engineer", date_added="2024-01-01")
        self._insert_job("id2", "Other Corp", "Engineer", date_added="2024-01-02")
        out = self._run()
        self.assertIn("Found 2 job(s)", out)


if __name__ == "__main__":
    unittest.main()
