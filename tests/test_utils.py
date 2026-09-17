import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    canonical_key,
    canonical_job_key,
    is_clean_location,
    locations_compatible,
    merge_delimited_field,
    normalize_company_for_matching,
    normalize_location,
    normalize_title,
    normalize_string,
    normalize_ocr_spacing,
    should_prefer_status,
    title_similarity,
    word_boundary_pattern,
    clean_company_name,
    is_aggregator_placeholder,
    compute_priority,
    classify_workplace,
    classify_job_type,
    detect_provider,
    path_to_file_uri,
    hash_file,
    hash_pdf_file,
    backup_timestamp,
    backup_file_if_exists,
    write_csv_atomic,
    ensure_db_columns,
    generate_calendar_url,
    create_vcard_entry,
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

    def test_canonical_job_key_does_not_strip_company_suffixes(self):
        key1 = canonical_job_key("Wheeler Machinery Company", "Senior Full Stack Software Engineer", "Salt Lake City, UT")
        key2 = canonical_job_key("Wheeler Machinery Co", "Senior Full Stack Software Engineer", "Salt Lake City, UT")
        self.assertNotEqual(key1, key2)


class TestNormalizeCompanyForMatching(unittest.TestCase):
    def test_strips_trailing_corporate_suffix(self):
        self.assertEqual(normalize_company_for_matching("Wheeler Machinery Company"), "Wheeler Machinery")
        self.assertEqual(normalize_company_for_matching("Wheeler Machinery Co"), "Wheeler Machinery")
        self.assertEqual(normalize_company_for_matching("Cox Automotive Inc."), "Cox Automotive")

    def test_leaves_non_suffixed_names_unchanged(self):
        self.assertEqual(normalize_company_for_matching("Podium"), "Podium")
        self.assertEqual(normalize_company_for_matching("Zions Bancorporation"), "Zions Bancorporation")


class TestTitleSimilarity(unittest.TestCase):
    def test_identical_titles_score_high(self):
        self.assertEqual(title_similarity("Staff Software Engineer", "Staff Software Engineer"), 1.0)

    def test_unrelated_titles_score_low(self):
        self.assertLess(title_similarity("Staff Software Engineer", "Product Developer, Sr."), 0.5)


class TestConsolidatedStringAndPatternHelpers(unittest.TestCase):
    def test_word_boundary_pattern(self):
        pattern = word_boundary_pattern("Franki")
        self.assertTrue(pattern.search("Franki_hiring.pdf"))
        self.assertTrue(pattern.search("Hello Franki"))
        self.assertFalse(pattern.search("Frankified"))

    def test_clean_company_name(self):
        self.assertEqual(clean_company_name("Jobs at Brady Corporation"), "Brady Corporation")
        self.assertEqual(clean_company_name("(Remote) at Globe Life"), "Globe Life")
        self.assertEqual(clean_company_name("Informativ is hiring for Sr. PHP Engineer"), "Informativ")
        self.assertEqual(clean_company_name(""), "")

    def test_normalize_ocr_spacing(self):
        self.assertEqual(normalize_ocr_spacing("firs t"), "first")
        self.assertEqual(normalize_ocr_spacing("p hoto"), "photo")
        self.assertEqual(normalize_ocr_spacing("PorchSoftware"), "Porch Software")

    def test_is_aggregator_placeholder(self):
        self.assertTrue(is_aggregator_placeholder("Ladders-DailyDigest"))
        self.assertTrue(is_aggregator_placeholder("Jobs.utah.gov-DailySummary"))
        self.assertFalse(is_aggregator_placeholder("Google"))


class TestConsolidatedDomainHelpers(unittest.TestCase):
    def test_classify_workplace(self):
        self.assertEqual(classify_workplace("Remote"), "Remote")
        self.assertEqual(classify_workplace("Salt Lake City, UT", "Hybrid Engineer"), "Hybrid")
        self.assertEqual(classify_workplace("Salt Lake City, UT"), "Onsite")
        self.assertEqual(classify_workplace(""), "Unknown")

    def test_classify_job_type(self):
        self.assertEqual(classify_job_type("Software Engineer"), "Software Engineer")
        self.assertEqual(classify_job_type("Manufacturing Engineer"), "Operations")
        self.assertEqual(classify_job_type("Warehouse Coordinator"), "Operations")

    def test_detect_provider(self):
        self.assertEqual(detect_provider("Welcome to jobs.utah.gov", ""), "jobs.utah.gov")
        self.assertEqual(detect_provider("", "linkedin_report.pdf"), "LinkedIn")
        self.assertEqual(detect_provider("BHE Career Site", ""), "BHE")
        self.assertEqual(detect_provider("Random text", "other.pdf"), "Unknown/Other")

    def test_compute_priority(self):
        self.assertEqual(compute_priority("★★★★★ Apply Now", "Apply"), "P1 – Apply today")
        self.assertEqual(compute_priority("★★★★☆ Strong", "Apply"), "P2 – Apply this week")
        self.assertEqual(compute_priority("★★★☆☆ Maybe", "Review"), "P3 – Investigate")
        self.assertEqual(compute_priority("★☆☆☆☆ Skip", "Ignore"), "P4 – Ignore")


class TestConsolidatedFileAndDbHelpers(unittest.TestCase):
    def test_hash_file_and_hash_pdf_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            f_path = f.name
        try:
            h_sha256 = hash_file(f_path)
            h_md5 = hash_pdf_file(f_path)
            self.assertIsNotNone(h_sha256)
            self.assertIsNotNone(h_md5)
            self.assertNotEqual(h_sha256, h_md5)
            self.assertIsNone(hash_file("non_existent_file_path.pdf"))
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_backup_file_if_exists(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("backup test")
            f_path = f.name
        try:
            bak_path = backup_file_if_exists(f_path)
            self.assertIsNotNone(bak_path)
            self.assertTrue(os.path.exists(bak_path))
            self.assertTrue(backup_timestamp(bak_path))
            if bak_path and os.path.exists(bak_path):
                os.remove(bak_path)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_write_csv_atomic(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "test.csv")
            write_csv_atomic(csv_path, ["A", "B"], [{"A": "1", "B": "2"}])
            self.assertTrue(os.path.exists(csv_path))
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("1,2", content)

    def test_ensure_db_columns(self):
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test_tab (id INTEGER PRIMARY KEY)")
        ensure_db_columns(cursor, "test_tab", [("col1", "TEXT"), ("col2", "INTEGER")])
        cursor.execute("PRAGMA table_info(test_tab)")
        cols = [r[1] for r in cursor.fetchall()]
        self.assertIn("col1", cols)
        self.assertIn("col2", cols)
        conn.close()

    def test_generate_calendar_url(self):
        url = generate_calendar_url("Interview", "Screen with Recruiter", "20260920T120000Z", "20260920T130000Z")
        self.assertIn("calendar.google.com", url)
        self.assertIn("Interview", url)

    def test_create_vcard_entry(self):
        vcard = create_vcard_entry("Jane Doe", "jane@example.com", "555-0199", "Acme", "Lead Dev")
        self.assertIn("BEGIN:VCARD", vcard)
        self.assertIn("FN:Jane Doe", vcard)
        self.assertIn("EMAIL;TYPE=INTERNET,HOME:jane@example.com", vcard)
        self.assertIn("END:VCARD", vcard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
