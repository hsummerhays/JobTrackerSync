import csv
import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fix_duplicates

FIELDNAMES = ["Job ID", "Company", "Position", "Location", "Date Added",
              "Tracker Status", "Review Status", "Action", "Disposition",
              "Provider", "Source PDF", "Notes"]


def _write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            full = {k: "" for k in FIELDNAMES}
            full.update(row)
            writer.writerow(full)


def _read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestFixDuplicates(unittest.TestCase):
    def setUp(self):
        self.orig_cwd = os.getcwd()
        self._tmpdir_ctx = tempfile.TemporaryDirectory()
        os.chdir(self._tmpdir_ctx.name)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        self._tmpdir_ctx.cleanup()

    def test_exact_duplicate_rows_are_merged(self):
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Remote", "Date Added": "2026-07-01", "Tracker Status": "New"},
            {"Job ID": "2", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Remote", "Date Added": "2026-07-01", "Tracker Status": "Applied",
             "Source PDF": "b.pdf"},
        ])
        fix_duplicates.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tracker Status"], "Applied")

    def test_distinct_locations_same_day_are_not_merged(self):
        """Regression: two genuinely different-location postings for the same
        company+title+date must not collapse into one row and lose data."""
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Remote", "Date Added": "2026-07-01", "Tracker Status": "New"},
            {"Job ID": "2", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Salt Lake City, UT", "Date Added": "2026-07-01", "Tracker Status": "New"},
        ])
        fix_duplicates.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 2)
        locations = {r["Location"] for r in rows}
        self.assertEqual(locations, {"Remote", "Salt Lake City, UT"})

    def test_malformed_location_still_merges_into_clean_row(self):
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Filevine", "Position": "Backend Engineer",
             "Location": "United States (Remote)", "Date Added": "2026-07-01", "Tracker Status": "New"},
            {"Job ID": "2", "Company": "Filevine", "Position": "Backend Engineer",
             "Location": "Franki · United States (Remote)", "Date Added": "2026-07-01",
             "Tracker Status": "Imported", "Source PDF": "dup.pdf"},
        ])
        fix_duplicates.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Location"], "United States (Remote)")
        self.assertIn("dup.pdf", rows[0]["Source PDF"])

    def test_terminal_status_is_not_overwritten_by_active_status(self):
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Remote", "Date Added": "2026-07-01", "Tracker Status": "Rejected"},
            {"Job ID": "2", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Remote", "Date Added": "2026-07-01", "Tracker Status": "Applied"},
        ])
        fix_duplicates.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tracker Status"], "Rejected")

    def test_backup_created_only_when_rows_are_merged(self):
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Remote", "Date Added": "2026-07-01", "Tracker Status": "New"},
        ])
        fix_duplicates.main()
        self.assertEqual(glob.glob("master_tracker.csv.bak.*"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
