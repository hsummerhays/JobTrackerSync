import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedup_utils import (
    canonical_key,
    is_clean_location,
    locations_compatible,
    merge_delimited_field,
    should_prefer_status,
    title_similarity,
)


class TestCanonicalKey(unittest.TestCase):
    def test_key_distinguishes_different_positions_same_company_and_date(self):
        """A company posting multiple jobs the same day must not collide into
        one group (the bug that let unrelated requisitions get merged)."""
        key1 = canonical_key("Epicor", "Staff Software Engineer", "2026-07-01")
        key2 = canonical_key("Epicor", "Product Developer, Sr.", "2026-07-01")
        self.assertNotEqual(key1, key2)

    def test_key_same_for_equivalent_inputs(self):
        key1 = canonical_key("Epicor Inc.", "Staff Software Engineer", "2026-07-01")
        key2 = canonical_key("epicor inc", "Staff  Software-Engineer", "2026-07-01")
        self.assertEqual(key1, key2)


class TestShouldPreferStatus(unittest.TestCase):
    def test_reviewed_status_replaces_unreviewed_status(self):
        self.assertTrue(should_prefer_status("New", "Cancelled"))
        self.assertTrue(should_prefer_status("Imported", "Rejected"))

    def test_unreviewed_status_does_not_replace_reviewed_status(self):
        self.assertFalse(should_prefer_status("Cancelled", "New"))
        self.assertFalse(should_prefer_status("Rejected", "Imported"))

    def test_unreviewed_does_not_overwrite_active_progress(self):
        self.assertFalse(should_prefer_status("Interviewing", "New"))
        self.assertFalse(should_prefer_status("Applied", "Imported"))

    def test_higher_ranked_reviewed_status_wins(self):
        self.assertTrue(should_prefer_status("Applied", "Offer"))
        self.assertTrue(should_prefer_status("New", "Applied"))

    def test_lower_ranked_reviewed_status_does_not_win(self):
        self.assertFalse(should_prefer_status("Offer", "Applied"))

    def test_terminal_status_is_not_overwritten_by_active_status(self):
        """Regression: Applied (rank 60) used to outrank Rejected (rank 10)
        under plain rank comparison, silently reviving a job the user had
        already rejected."""
        self.assertFalse(should_prefer_status("Rejected", "Applied"))
        self.assertFalse(should_prefer_status("Ghosted", "Waiting"))

    def test_terminal_status_beats_active_status(self):
        self.assertTrue(should_prefer_status("Applied", "Rejected"))
        self.assertTrue(should_prefer_status("Waiting", "Ghosted"))


class TestLocationsCompatible(unittest.TestCase):
    def test_identical_clean_locations_are_compatible(self):
        self.assertTrue(locations_compatible("Remote", "remote"))

    def test_distinct_clean_locations_are_not_compatible(self):
        self.assertFalse(locations_compatible("Remote", "Salt Lake City, UT"))

    def test_malformed_location_is_always_compatible(self):
        self.assertTrue(locations_compatible("Franki · United States (Remote)", "United States (Remote)"))
        self.assertTrue(locations_compatible("United States (Remote)", "Franki · United States (Remote)"))


class TestMergeDelimitedField(unittest.TestCase):
    def test_windows_paths_survive_intact(self):
        base = r"D:\Current\Personal\Job Postings\a.pdf"
        merged = merge_delimited_field(base, r"D:\Current\Personal\Job Postings\b.pdf")
        self.assertIn(r"D:\Current\Personal\Job Postings\a.pdf", merged)
        self.assertIn(r"D:\Current\Personal\Job Postings\b.pdf", merged)

    def test_no_duplicates(self):
        merged = merge_delimited_field("a.pdf", "a.pdf")
        self.assertEqual(merged, "a.pdf")

    def test_empty_other(self):
        self.assertEqual(merge_delimited_field("a.pdf", ""), "a.pdf")


class TestIsCleanLocation(unittest.TestCase):
    def test_dot_separator_is_dirty(self):
        self.assertFalse(is_clean_location("Filevine · United States (Remote)"))

    def test_plain_location_is_clean(self):
        self.assertTrue(is_clean_location("United States (Remote)"))


class TestTitleSimilarity(unittest.TestCase):
    def test_identical_titles_score_high(self):
        self.assertEqual(title_similarity("Staff Software Engineer", "Staff Software Engineer"), 1.0)

    def test_unrelated_titles_score_low(self):
        self.assertLess(title_similarity("Staff Software Engineer", "Product Developer, Sr."), 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
