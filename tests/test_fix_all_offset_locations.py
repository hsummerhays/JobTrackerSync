import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fix_all_offset_locations import plan_fixes


class TestPlanFixes(unittest.TestCase):
    def test_fixes_confirmed_offset_location(self):
        rows = [{"Job ID": "1", "Location": "Filevine · United States (Remote)", "Source PDF": ""}]
        fixes, skipped = plan_fixes(rows)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0][2], "United States (Remote)")
        self.assertEqual(skipped, [])

    def test_skips_when_right_side_is_not_a_location(self):
        """A '·' that isn't a company/location offset (e.g. legitimate text)
        must not be mutated -- only confirmed offsets are safe to touch."""
        rows = [{"Job ID": "2", "Location": "Spring Boot · Distributed Systems", "Source PDF": ""}]
        fixes, skipped = plan_fixes(rows)
        self.assertEqual(fixes, [])
        self.assertEqual(len(skipped), 1)

    def test_ignores_clean_locations(self):
        rows = [{"Job ID": "3", "Location": "United States (Remote)", "Source PDF": ""}]
        fixes, skipped = plan_fixes(rows)
        self.assertEqual(fixes, [])
        self.assertEqual(skipped, [])

    def test_source_pdf_filter_scopes_rows(self):
        rows = [
            {"Job ID": "4", "Location": "Franki · Remote", "Source PDF": r"D:\pdfs\omada.pdf"},
            {"Job ID": "5", "Location": "Filevine · Remote", "Source PDF": r"D:\pdfs\other.pdf"},
        ]
        fixes, skipped = plan_fixes(rows, source_pdf_contains="omada")
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0][0]["Job ID"], "4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
