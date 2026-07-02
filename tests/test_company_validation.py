"""
Unit tests for company validation logic.

Run with:
    python -m pytest tests/test_company_validation.py -v
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import is_valid_company


class TestIsValidCompany(unittest.TestCase):
    """Test cases for is_valid_company function."""

    # --- Should ACCEPT ---

    def test_normal_company(self):
        self.assertTrue(is_valid_company("Alivia Analytics"))

    def test_company_with_llc(self):
        self.assertTrue(is_valid_company("Capstone Logistics LLC"))

    def test_company_with_period_abbreviation(self):
        self.assertTrue(is_valid_company("Futran Tech Solutions Pvt. Ltd."))

    def test_company_with_ampersand(self):
        self.assertTrue(is_valid_company("Smith & Jones Software"))

    def test_two_word_company(self):
        self.assertTrue(is_valid_company("Sunwest Bank"))

    def test_single_word_company(self):
        self.assertTrue(is_valid_company("Weave"))

    def test_company_with_numbers_in_name(self):
        self.assertTrue(is_valid_company("H10 Capital"))

    def test_company_with_dot_net_in_name(self):
        # Company names that contain tech terms are fine
        self.assertTrue(is_valid_company("ResolveNet Technologies"))

    def test_rejects_ui_label_concatenated(self):
        # PDF parser occasionally glues a UI button onto the company name;
        # is_valid_company should reject the raw mangled string so
        # clean_existing_tracker can strip it and re-insert the clean name.
        self.assertFalse(is_valid_company("Futran Tech Solutions Pvt. Ltd.View Details"))

    # --- Should REJECT: placeholders ---

    def test_rejects_unknown(self):
        self.assertFalse(is_valid_company("Unknown"))

    def test_rejects_undisclosed(self):
        self.assertFalse(is_valid_company("Undisclosed"))

    def test_rejects_undisclosed_company(self):
        self.assertFalse(is_valid_company("Undisclosed Company"))

    def test_rejects_empty_string(self):
        self.assertFalse(is_valid_company(""))

    def test_rejects_none(self):
        self.assertFalse(is_valid_company(None))

    def test_rejects_whitespace_only(self):
        self.assertFalse(is_valid_company("   "))

    # --- Should REJECT: UI element labels ---

    def test_rejects_view_details(self):
        self.assertFalse(is_valid_company("View Details"))

    def test_rejects_learn_more(self):
        self.assertFalse(is_valid_company("Learn More"))

    def test_rejects_apply_now(self):
        self.assertFalse(is_valid_company("Apply Now"))

    def test_rejects_easy_apply(self):
        self.assertFalse(is_valid_company("Easy Apply"))

    def test_rejects_save_job(self):
        self.assertFalse(is_valid_company("Save Job"))

    def test_rejects_show_more(self):
        self.assertFalse(is_valid_company("Show More"))

    # --- Should REJECT: location-as-company ---

    def test_rejects_city_state(self):
        self.assertFalse(is_valid_company("Salt Lake City"))

    def test_rejects_slc(self):
        self.assertFalse(is_valid_company("slc"))

    def test_rejects_remote(self):
        self.assertFalse(is_valid_company("Remote"))

    def test_rejects_utah(self):
        self.assertFalse(is_valid_company("Utah"))

    def test_rejects_state_suffix_ut(self):
        # e.g. "Eagle Mountain, UT" parsed as company
        self.assertFalse(is_valid_company("Eagle Mountain, UT"))

    def test_rejects_state_suffix_ca(self):
        self.assertFalse(is_valid_company("San Francisco, CA"))

    # --- Should REJECT: exclusion keywords ---

    def test_rejects_word_apply_in_name(self):
        self.assertFalse(is_valid_company("Apply Here"))

    def test_rejects_gmail_fragment(self):
        self.assertFalse(is_valid_company("Gmail Support"))

    def test_rejects_compensation_fragment(self):
        self.assertFalse(is_valid_company("Based Compensation"))

    # --- Should REJECT: lowercase start ---

    def test_rejects_lowercase_start(self):
        self.assertFalse(is_valid_company("jobright.ai"))

    # --- Should REJECT: too long (sentence-like) ---

    def test_rejects_too_many_words(self):
        self.assertFalse(is_valid_company("This is a long sentence that looks like a paragraph of text"))

    def test_rejects_ends_with_question_mark(self):
        self.assertFalse(is_valid_company("Looking for a job?"))

    def test_rejects_ends_with_period_sentence(self):
        self.assertFalse(is_valid_company("We are hiring."))    # --- Should REJECT: slash-containing and pure tech keywords ---

    def test_rejects_slashes(self):
        self.assertFalse(is_valid_company("Java/Typescript/AWS"))
        self.assertFalse(is_valid_company("Python\\C#"))

    def test_rejects_pure_tech_keywords(self):
        self.assertFalse(is_valid_company("Java AWS"))
        self.assertFalse(is_valid_company("Python .NET Azure"))

    # --- New Validation Checks (UI Elements / Header leaks / Normalization) ---

    def test_rejects_be_seen_first(self):
        self.assertFalse(is_valid_company("Be Seen First"))

    def test_rejects_easy(self):
        self.assertFalse(is_valid_company("Easy"))

    def test_rejects_do_not_share_this_email(self):
        self.assertFalse(is_valid_company("Do not share this email"))

    def test_rejects_date_timestamps(self):
        self.assertFalse(is_valid_company("6/30/26"))
        self.assertFalse(is_valid_company("8:17 AM"))

    def test_accepts_double_spaces_normalized(self):
        self.assertTrue(is_valid_company("Alivia  Analytics"))
        self.assertTrue(is_valid_company("Cox  Automotive"))

    def test_rejects_be_seen_first_fragmented(self):
        self.assertFalse(is_valid_company("Be Seen Firs t"))

    def test_accepts_insurance_office_fragmented(self):
        self.assertTrue(is_valid_company("Insurance Of fice of America"))

    def test_accepts_foureyes_fragmented(self):
        self.assertTrue(is_valid_company("Fourey es"))

    # --- Indeed Recommendation Banners and Digest Artifacts ---

    def test_rejects_indeed_recommendation_banners(self):
        self.assertFalse(is_valid_company("Based on your title and location. Update"))
        self.assertFalse(is_valid_company("Recommended for you"))
        self.assertFalse(is_valid_company("Update your profile"))

    def test_rejects_truncated_digest_artifacts(self):
        self.assertFalse(is_valid_company("Company Name..."))
        self.assertFalse(is_valid_company("Company Name More ..."))
        self.assertFalse(is_valid_company("Company Name View more"))
        self.assertFalse(is_valid_company("Company Name See more"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

