import unittest
from unittest.mock import patch, MagicMock
import os
import sqlite3
import tempfile
import csv
from datetime import date

import parse_jobs

class TestFixRegressions(unittest.TestCase):

    def test_save_to_sqlite_returns_boolean(self):
        # We use a real sqlite database in a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            job = {"Job ID": "123", "Date Added": "2024-01-01", "Last Seen": "2024-01-01", "Tracker Status": "New", "Company": "C", "Position": "P", "Location": "L"}
            
            # Normal save should return True
            result = parse_jobs.save_to_sqlite(db_path, [job])
            self.assertTrue(result)
            
            # Failed save should return False (by passing an invalid path like a directory)
            result = parse_jobs.save_to_sqlite(tmpdir, [job])
            self.assertFalse(result)

    def _write_empty_tracker(self, path):
        with open(path, mode='w', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=["Job ID", "Company", "Position", "Location"]).writeheader()

    def test_main_prevents_csv_write_on_db_failure(self):
        # We can test handle_manual_add preventing CSV write
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                self._write_empty_tracker("master_tracker.csv")
                with patch('parse_jobs.save_to_sqlite', return_value=False):
                    with patch('parse_jobs.write_tracker_csv_atomic') as mock_write:
                        with patch('parse_jobs.console.print'):
                            parse_jobs.handle_manual_add(
                                company="Test", position="Dev", location="NY",
                                interactive=False
                            )
                        mock_write.assert_not_called()

                with patch('parse_jobs.save_to_sqlite', return_value=True):
                    with patch('parse_jobs.write_tracker_csv_atomic') as mock_write:
                        with patch('parse_jobs.console.print'):
                            parse_jobs.handle_manual_add(
                                company="Test", position="Dev", location="NY",
                                interactive=False
                            )
                        mock_write.assert_called_once()
            finally:
                os.chdir(old_cwd)

    def test_manual_add_audit_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                self._write_empty_tracker("master_tracker.csv")
                with patch('parse_jobs.save_to_sqlite', return_value=True):
                    with patch('parse_jobs.write_tracker_csv_atomic') as mock_write:
                        with patch('parse_jobs.console.print'):
                            parse_jobs.handle_manual_add(
                                company="ManualCompany", position="Dev", location="Remote",
                                interactive=False
                            )
                        args, kwargs = mock_write.call_args
            finally:
                os.chdir(old_cwd)

            rows = args[2]
            row = next(r for r in rows if r["Company"] == "ManualCompany")
            self.assertIn("Last Seen", row)
            self.assertIn("Fingerprint", row)
            self.assertIn("Previous Job ID", row)
            self.assertIn("Source Index", row)
            self.assertEqual(row["_status_source"], "user")
            self.assertEqual(row["Previous Job ID"], "")
            self.assertEqual(row["Source Index"], "")

    def test_manual_add_persists_status_source_user_to_db(self):
        # The in-memory job dict having _status_source="user" isn't enough --
        # save_to_sqlite must actually write it into job_workflow.status_source
        # instead of the hardcoded 'parser' used by the parser-driven sync path.
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                self._write_empty_tracker("master_tracker.csv")
                with patch('parse_jobs.write_tracker_csv_atomic'):
                    with patch('parse_jobs.console.print'):
                        parse_jobs.handle_manual_add(
                            company="StatusSourceCo", position="Dev", location="Remote",
                            interactive=False
                        )
                conn = sqlite3.connect("jobs.db")
                row = conn.execute(
                    "SELECT w.status_source FROM job_workflow w "
                    "JOIN jobs j ON j.job_id = w.job_id WHERE j.company = ?",
                    ("StatusSourceCo",)
                ).fetchone()
                conn.close()
            finally:
                os.chdir(old_cwd)

            self.assertIsNotNone(row)
            self.assertEqual(row[0], "user")

    def test_backup_uniqueness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.csv")
            with open(file_path, "w") as f:
                f.write("test")
                
            b1 = parse_jobs.backup_file_if_exists(file_path)
            b2 = parse_jobs.backup_file_if_exists(file_path)
            
            self.assertIsNotNone(b1)
            self.assertIsNotNone(b2)
            self.assertNotEqual(b1, b2)

    def test_initial_header_completeness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "new_tracker.csv")
            parse_jobs.initialize_tracker(file_path)
            
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                
            self.assertIn("Source Index", header)
            self.assertIn("Fingerprint", header)
            self.assertIn("Last Seen", header)

    def test_aggregator_missing_source_index_preserves_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker_path = os.path.join(tmpdir, "tracker.csv")
            with open(tracker_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Job ID", "Company", "Position", "Tracker Status", "Fingerprint", "Source PDF", "Date Added"])
                writer.writeheader()
                writer.writerow({
                    "Job ID": "legacy1",
                    "Company": "Jobs.utah.gov-DailySummary",
                    "Position": "Engineer",
                    "Tracker Status": "New",
                    "Fingerprint": "valid_fingerprint",
                    "Source PDF": "",
                    "Date Added": "2024-01-01"
                })
                
            parse_jobs.clean_existing_tracker(tracker_path)
            jobs = parse_jobs.load_tracker(tracker_path)
            self.assertEqual(jobs[("legacy1", "2024-01-01")]["Fingerprint"], "valid_fingerprint")

if __name__ == '__main__':
    unittest.main()
