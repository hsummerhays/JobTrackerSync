import os
import sys
import io
import sqlite3
import tempfile
import unittest
import pathlib
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import find_pdf
from find_pdf import find_matches, find_csv_matches, path_to_file_uri

class TestFindPdf(unittest.TestCase):

    def test_find_matches_nonexistent_db(self):
        # Should return empty dictionary if db doesn't exist
        results = find_matches("nonexistent_db_file.db", "test")
        self.assertEqual(results, {})

    def test_find_matches_with_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_jobs.db")
            
            # Setup temporary test database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create a mock jobs table
            cursor.execute("""
                CREATE TABLE jobs (
                    job_id TEXT,
                    company TEXT,
                    position TEXT,
                    source_pdf TEXT
                )
            """)
            
            # Insert some dummy records
            cursor.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", (
                "id123", "Franki Corp", "Software Engineer", "C:\\postings\\Franki_hiring.pdf"
            ))
            cursor.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", (
                "id456", "Other Corp", "Backend Developer", "C:\\postings\\other.pdf"
            ))
            
            # Create a mock processed_files table
            cursor.execute("""
                CREATE TABLE processed_files (
                    file_path TEXT,
                    status TEXT
                )
            """)
            cursor.execute("INSERT INTO processed_files VALUES (?, ?)", (
                "C:\\postings\\Franki_hiring.pdf", "success"
            ))
            
            conn.commit()
            conn.close()
            
            # 1. Search for "Franki" - should find matches in both tables
            results = find_matches(db_path, "Franki")
            
            self.assertIn("jobs", results)
            self.assertEqual(len(results["jobs"]), 1)
            self.assertEqual(results["jobs"][0]["company"], "Franki Corp")
            self.assertEqual(results["jobs"][0]["job_id"], "id123")
            # Check URI generation for source_pdf
            self.assertIn("source_pdf_uri", results["jobs"][0])
            self.assertEqual(
                results["jobs"][0]["source_pdf_uri"],
                "file:///C:/postings/Franki_hiring.pdf"
            )
            
            self.assertIn("processed_files", results)
            self.assertEqual(len(results["processed_files"]), 1)
            self.assertEqual(results["processed_files"][0]["status"], "success")
            self.assertIn("file_path_uri", results["processed_files"][0])
            
            # 2. Search for a term that does not exist
            no_results = find_matches(db_path, "NonexistentTerm")
            self.assertEqual(no_results, {})

    def test_find_matches_rejects_substring_not_at_word_boundary(self):
        # "rank" is a LIKE-substring of "Frankie Corp" but not a word-boundary
        # match, so it should be filtered out and yield no results.
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_jobs.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE jobs (job_id TEXT, company TEXT)")
            cursor.execute("INSERT INTO jobs VALUES (?, ?)", ("id1", "Frankie Corp"))
            conn.commit()
            conn.close()

            results = find_matches(db_path, "rank")
            self.assertEqual(results, {})

    def test_find_matches_handles_query_exception(self):
        # Simulate a table whose data query raises mid-scan; find_matches
        # should swallow it and return results gathered from other tables
        # rather than crashing.
        class FakeCursor:
            def __init__(self):
                self._result = []

            def execute(self, query, params=None):
                if query.startswith("SELECT name FROM sqlite_master"):
                    self._result = [("broken",), ("ok",)]
                elif query.startswith('PRAGMA table_info("broken")'):
                    self._result = [(0, "col", "TEXT", 0, None, 0)]
                elif query.startswith('PRAGMA table_info("ok")'):
                    self._result = [(0, "company", "TEXT", 0, None, 0)]
                elif query.startswith('SELECT * FROM "broken"'):
                    raise sqlite3.OperationalError("simulated failure")
                elif query.startswith('SELECT * FROM "ok"'):
                    self._result = [("Acme Corp",)]
                else:
                    self._result = []

            def fetchall(self):
                return self._result

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        with patch("find_pdf.os.path.exists", return_value=True), \
             patch("find_pdf.sqlite3.connect", return_value=FakeConnection()):
            results = find_matches("fake.db", "Acme")

        self.assertNotIn("broken", results)
        self.assertIn("ok", results)
        self.assertEqual(results["ok"][0]["company"], "Acme Corp")

    def test_find_matches_debug_prints_query_exception(self):
        class FakeCursor:
            def execute(self, query, params=None):
                if query.startswith("SELECT name FROM sqlite_master"):
                    self._result = [("broken",)]
                elif query.startswith('PRAGMA table_info'):
                    self._result = [(0, "col", "TEXT", 0, None, 0)]
                elif query.startswith('SELECT * FROM "broken"'):
                    raise sqlite3.OperationalError("simulated failure")

            def fetchall(self):
                return self._result

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

            def close(self):
                pass

        buf = io.StringIO()
        with patch("find_pdf.os.path.exists", return_value=True), \
             patch("find_pdf.sqlite3.connect", return_value=FakeConnection()), \
             patch("find_pdf.DEBUG", True), \
             redirect_stderr(buf):
            find_matches("fake.db", "Acme")

        self.assertIn("Database query error in table broken", buf.getvalue())

    def test_windows_path_to_file_uri(self):
        self.assertEqual(
            path_to_file_uri(r"C:\postings\Franki hiring.pdf"),
            "file:///C:/postings/Franki%20hiring.pdf"
        )

    def test_posix_path_to_file_uri(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = pathlib.Path(tmp_dir).resolve() / "posting.pdf"
            self.assertEqual(
                path_to_file_uri(str(test_file)),
                test_file.as_uri()
            )

class TestFindCsvMatches(unittest.TestCase):

    def test_missing_csv_returns_empty_list(self):
        self.assertEqual(find_csv_matches("nonexistent_tracker.csv", "test"), [])

    def test_finds_matching_rows_and_generates_uri(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "tracker.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                f.write("Company,Position,Source PDF\n")
                f.write("Franki Corp,Software Engineer,C:\\postings\\Franki_hiring.pdf\n")
                f.write("Other Corp,Backend Developer,C:\\postings\\other.pdf\n")

            matches = find_csv_matches(csv_path, "Franki")
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["Company"], "Franki Corp")
            self.assertEqual(
                matches[0]["Source PDF_uri"],
                "file:///C:/postings/Franki_hiring.pdf"
            )

    def test_no_match_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "tracker.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                f.write("Company,Position\n")
                f.write("Other Corp,Backend Developer\n")

            self.assertEqual(find_csv_matches(csv_path, "Nonexistent"), [])

    def test_rejects_substring_not_at_word_boundary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "tracker.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                f.write("Company,Position\n")
                f.write("Frankie Corp,Backend Developer\n")

            self.assertEqual(find_csv_matches(csv_path, "rank"), [])

    def test_read_exception_is_swallowed(self):
        # Passing a directory instead of a file makes open() raise
        # IsADirectoryError, exercising the except branch without mocking.
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(find_csv_matches(tmp_dir, "test"), [])

    def test_read_exception_debug_prints_to_stderr(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("find_pdf.DEBUG", True), redirect_stderr(buf):
                find_csv_matches(tmp_dir, "test")

        self.assertIn("CSV read error", buf.getvalue())


class TestMain(unittest.TestCase):

    def test_no_args_prints_usage_and_exits_1(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["find_pdf.py"]):
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    find_pdf.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Usage: python find_pdf.py", buf.getvalue())

    def test_no_matches_prints_message(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["find_pdf.py", "Nonexistent"]), \
             patch("find_pdf.find_matches", return_value={}), \
             patch("find_pdf.find_csv_matches", return_value=[]):
            with redirect_stdout(buf):
                find_pdf.main()
        self.assertIn("No matches found for: 'Nonexistent'", buf.getvalue())

    def test_prints_db_and_csv_results(self):
        db_results = {"jobs": [{"job_id": "id1", "company": "Acme Corp"}]}
        csv_results = [{"Company": "Acme Corp", "Position": "Engineer"}]

        buf = io.StringIO()
        with patch.object(sys, "argv", ["find_pdf.py", "Acme"]), \
             patch("find_pdf.find_matches", return_value=db_results), \
             patch("find_pdf.find_csv_matches", return_value=csv_results):
            with redirect_stdout(buf):
                find_pdf.main()

        out = buf.getvalue()
        self.assertIn("--- Matches in Table: jobs ---", out)
        self.assertIn("Acme Corp", out)
        self.assertIn("--- Matches in CSV: master_tracker.csv ---", out)
        self.assertIn("Engineer", out)


if __name__ == '__main__':
    unittest.main()
