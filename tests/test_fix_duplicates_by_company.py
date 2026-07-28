import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fix_duplicates_by_company

FIELDNAMES = ["Job ID", "Company", "Position", "Location", "Tracker Status",
              "Review Status", "Action", "Disposition", "Provider",
              "Source PDF", "Notes"]


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


class TestFixDuplicatesByCompany(unittest.TestCase):
    def setUp(self):
        self.orig_cwd = os.getcwd()
        self._tmpdir_ctx = tempfile.TemporaryDirectory()
        os.chdir(self._tmpdir_ctx.name)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        self._tmpdir_ctx.cleanup()

    def test_distinct_same_day_postings_are_not_merged(self):
        """Regression: grouping only by company+date used to merge unrelated
        requisitions from the same company posted on the same day."""
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Epicor", "Position": "Staff Software Engineer",
             "Location": "United States (Remote)", "Tracker Status": "New"},
            {"Job ID": "2", "Company": "Epicor", "Position": "Product Developer, Sr.",
             "Location": "United States (Remote)", "Tracker Status": "New"},
        ])
        fix_duplicates_by_company.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 2)
        positions = {r["Position"] for r in rows}
        self.assertEqual(positions, {"Staff Software Engineer", "Product Developer, Sr."})

    def test_malformed_row_merges_into_matching_clean_row_only(self):
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Filevine", "Position": "Senior Backend Engineer",
             "Location": "United States (Remote)", "Tracker Status": "New"},
            {"Job ID": "2", "Company": "Filevine", "Position": "Senior Backend Engineer",
             "Location": "Franki · United States (Remote)", "Tracker Status": "Imported",
             "Source PDF": r"D:\jobs\dup.pdf"},
        ])
        fix_duplicates_by_company.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Location"], "United States (Remote)")
        self.assertIn(r"D:\jobs\dup.pdf", rows[0]["Source PDF"])

    def test_terminal_status_is_not_resurrected_by_imported(self):
        """Regression: a Cancelled/Rejected row must not flip back to New/Imported
        just because the duplicate being merged in was freshly re-imported."""
        _write_csv("master_tracker.csv", [
            {"Job ID": "1", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "United States (Remote)", "Tracker Status": "Cancelled"},
            {"Job ID": "2", "Company": "Acme", "Position": "Backend Engineer",
             "Location": "Other Co · United States (Remote)", "Tracker Status": "Imported"},
        ])
        fix_duplicates_by_company.main()
        rows = _read_csv("master_tracker.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Tracker Status"], "Cancelled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
