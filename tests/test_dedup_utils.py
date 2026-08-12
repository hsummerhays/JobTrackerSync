import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedup_utils import (
    canonical_key,
    canonical_job_key,
    is_clean_location,
    locations_compatible,
    merge_delimited_field,
    normalize_location,
    normalize_title,
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

    def test_roman_numeral_title_normalization_matches_arabic_numeral(self):
        """'Senior Developer I' and 'Senior Developer 1' must produce identical keys."""
        key_roman = canonical_job_key("Verisk", "Senior Developer I", "Lehi, UT")
        key_arabic = canonical_job_key("Verisk", "Senior Developer 1", "Lehi, UT")
        self.assertEqual(key_roman, key_arabic)

        key_roman_ii = canonical_job_key("Verisk", "Software Engineer II", "Remote")
        key_arabic_2 = canonical_job_key("Verisk", "Software Engineer 2", "Remote")
        self.assertEqual(key_roman_ii, key_arabic_2)

        self.assertEqual(normalize_title("Developer III"), "Developer 3")
        self.assertEqual(normalize_title("Analyst IV"), "Analyst 4")
        self.assertEqual(normalize_title("Engineer V"), "Engineer 5")


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

    def test_active_application_status_outranks_closed_status(self):
        """Applied (rank 70) outranks Rejected (rank 50), so automated re-ingestion
        or deduplication never downgrades an active application to a closed state."""
        self.assertTrue(should_prefer_status("Rejected", "Applied"))
        self.assertTrue(should_prefer_status("Ghosted", "Waiting"))

    def test_weaker_closed_status_does_not_beat_active_status(self):
        self.assertFalse(should_prefer_status("Applied", "Rejected"))
        self.assertFalse(should_prefer_status("Waiting", "Ghosted"))



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


class TestNormalizeLocation(unittest.TestCase):
    def test_strips_day_and_hour_alert_age_fragments(self):
        self.assertEqual(normalize_location("Salt Lake City, UT 1d"), "Salt Lake City, UT")
        self.assertEqual(normalize_location("Salt Lake City, UT 7h"), "Salt Lake City, UT")
        self.assertEqual(normalize_location("Salt Lake City, UT 11h"), "Salt Lake City, UT")

    def test_strips_just_posted_fragment(self):
        self.assertEqual(normalize_location("Salt Lake City, UT Just posted"), "Salt Lake City, UT")

    def test_strips_trailing_zip_code(self):
        self.assertEqual(normalize_location("Midvale, UT 84047"), "Midvale, UT")

    def test_plain_location_without_zip_is_unaffected(self):
        self.assertEqual(normalize_location("Midvale, UT"), "Midvale, UT")

    def test_l3harris_alert_age_variants_collapse_to_same_key(self):
        """The specific bug reported in the export: same posting, three
        alert-age-tagged copies of the location, all treated as distinct."""
        key1 = canonical_job_key("L3Harris", "Sr Associate, Software Engineer", "Salt Lake City, UT 1d")
        key2 = canonical_job_key("L3Harris", "Sr Associate, Software Engineer", "Salt Lake City, UT 7h")
        key3 = canonical_job_key("L3Harris", "Sr Associate, Software Engineer", "Salt Lake City, UT")
        self.assertEqual(key1, key2)
        self.assertEqual(key2, key3)

    def test_zions_zip_variant_collapses_to_same_key(self):
        key1 = canonical_job_key("Zions Bancorporation", "Full Stack Developer (Technology Enablement)", "Midvale, UT")
        key2 = canonical_job_key("Zions Bancorporation", "Full Stack Developer (Technology Enablement)", "Midvale, UT 84047")
        self.assertEqual(key1, key2)


class TestTitleSimilarity(unittest.TestCase):
    def test_identical_titles_score_high(self):
        self.assertEqual(title_similarity("Staff Software Engineer", "Staff Software Engineer"), 1.0)

    def test_unrelated_titles_score_low(self):
        self.assertLess(title_similarity("Staff Software Engineer", "Product Developer, Sr."), 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
