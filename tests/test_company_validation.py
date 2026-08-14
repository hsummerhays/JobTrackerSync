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

    def test_rejects_subject_header_artifacts(self):
        self.assertFalse(is_valid_company("Your job listings for June 22, 2026"))
        self.assertFalse(is_valid_company("Job listings for you"))

    # --- clean_company_name tests ---

    def test_clean_company_name_jobs_at(self):
        from parse_jobs import clean_company_name
        self.assertEqual(clean_company_name("Jobs at Brady Corporation"), "Brady Corporation")
        self.assertEqual(clean_company_name("  Jobs at Brady Corporation  "), "Brady Corporation")

    def test_clean_company_name_remote_at(self):
        from parse_jobs import clean_company_name
        self.assertEqual(clean_company_name("(Remote) at Globe Life"), "Globe Life")
        self.assertEqual(clean_company_name("at Globe Life"), "Globe Life")

    def test_clean_company_name_hiring_for(self):
        from parse_jobs import clean_company_name
        self.assertEqual(clean_company_name("Informativ is hiring for Sr. PHP Engineer"), "Informativ")
        self.assertEqual(clean_company_name("PlayOn Sports is looking for candidates"), "PlayOn Sports")

    def test_clean_company_name_empty_input(self):
        from parse_jobs import clean_company_name
        self.assertEqual(clean_company_name(""), "")
        self.assertEqual(clean_company_name(None), "")

    def test_rejects_company_composed_entirely_of_tech_keywords(self):
        self.assertFalse(is_valid_company("Java, AWS"))
        self.assertFalse(is_valid_company("React"))

    def test_rejects_company_name_over_100_chars(self):
        self.assertFalse(is_valid_company("A" + "b" * 100))

    def test_rejects_company_containing_date_pattern(self):
        self.assertFalse(is_valid_company("Acme Corp 3/15/2024"))
        self.assertFalse(is_valid_company("Acme Corp 3:15 PM"))

    def test_rejects_trailing_period_on_long_word(self):
        self.assertFalse(is_valid_company("Acme Corporation."))

    def test_accepts_trailing_period_on_short_abbreviation(self):
        self.assertTrue(is_valid_company("Acme Corp."))

    def test_rejects_job_board_provider_names_as_company(self):
        for name in [
            "Ladders", "TheLadders", "The Ladders",
            "LinkedIn", "Indeed", "Glassdoor", "ZipRecruiter",
            "jobs.utah.gov", "Actively Recruiting",
        ]:
            self.assertFalse(is_valid_company(name), f"expected {name!r} to be rejected")

    def test_dailydigest_allowance_takes_priority_over_provider_name_rejection(self):
        # The dailysummary/dailydigest allowance is checked before the bare
        # provider_names rejection, so these known digest-placeholder rows
        # (not real employers, but valid tracker rows) are let through even
        # though their un-suffixed provider name is separately rejected by
        # test_rejects_job_board_provider_names_as_company above.
        self.assertTrue(is_valid_company("ladders-DailyDigest"))
        self.assertTrue(is_valid_company("Jobs.Utah.Gov-DailySummary"))

    def test_unrelated_dailydigest_company_is_still_allowed(self):
        # The dailysummary/dailydigest allowance should still let through
        # names that aren't in the explicit provider_names reject set.
        self.assertTrue(is_valid_company("Acme DailyDigest"))

    def test_rejects_posted_prefix(self):
        self.assertFalse(is_valid_company("Posted: 2 days ago"))
        self.assertFalse(is_valid_company("posted:Yesterday"))

    def test_rejects_bare_corporate_suffix_fragment(self):
        # A PDF/email layout wrap can leave only the trailing suffix line
        # behind when the real company name (e.g. "TURING") is captured into
        # an adjacent field instead -- these fragments must not pass as a
        # real employer name on their own.
        self.assertFalse(is_valid_company("ENTERPRISES, INC.."))
        self.assertFalse(is_valid_company("Corp. LLC"))
        self.assertFalse(is_valid_company("Holdings Group"))
        # A real name combined with a suffix is still valid.
        self.assertTrue(is_valid_company("Acme Corp."))
        self.assertTrue(is_valid_company("Capstone Logistics LLC"))

    def test_rejects_job_alert_subject_leakage(self):
        self.assertFalse(is_valid_company("Your IntelliSearch Alert"))
        self.assertFalse(is_valid_company("Your IntelliSearch Alert: Remote Senior Software Engineer at TURING"))
        self.assertFalse(is_valid_company("Your Ladders Alert"))

    def test_rejects_pure_job_title(self):
        self.assertFalse(is_valid_company("Senior Software Engineer"))
        self.assertFalse(is_valid_company("Full Stack Developer"))
        self.assertFalse(is_valid_company("Lead Backend Engineer"))

    def test_rejects_junk_benefit_and_ui_terms(self):
        self.assertFalse(is_valid_company("Vacation & Paid Time Off"))
        self.assertFalse(is_valid_company("Inventory & Food Cost Platform(Only on W2)"))
        self.assertFalse(is_valid_company("Full-Time • Positive Culture & Values"))
        self.assertFalse(is_valid_company("More jobs ➞ More remote jobs"))
        self.assertFalse(is_valid_company("GenAI"))

    def test_bare_mri_is_a_legitimate_company_name(self):
        """2026-08-13: a ZipRecruiter posting ('Compass21 Application
        Developer / MRI / Houston, TX - Remote') showed this is a real,
        unambiguously-bounded employer name, not junk -- confirmed against
        the raw extracted PDF text, not guessed. The exact-match '^mri$'
        rejection this test used to assert was a false positive with no
        counter-evidence of a junk 'MRI' company ever appearing in this
        dataset."""
        self.assertTrue(is_valid_company("MRI"))

    def test_bare_fullstack_is_a_legitimate_company_name(self):
        """2026-08-13: confirmed against raw source text ('Principal Agentic
        Engineer - Remote - USA / FullStack . Salt Lake City, UT (Remote)',
        the same Title/Company/Location digest layout as its correctly-parsed
        neighbors in the same card) that 'FullStack' is a real company name
        here, not a mis-swapped skill keyword -- the JOB_TITLE_ROLE_WORDS
        rejection ('fullstack' is in that set as a skill term) was a false
        positive on this specific single-word company name."""
        self.assertTrue(is_valid_company("FullStack"))

    def test_lowercase_domain_style_company_name_is_legitimate(self):
        """2026-08-13: confirmed against raw source text ('Senior Software
        Engineering Consultant / talentarchitect.com / Remote') that
        'talentarchitect.com' is the real company name in a Title/Company/
        Location swap, not junk -- the generic starts-with-lowercase-letter
        rejection would otherwise reject this deliberately-lowercase,
        domain-styled real company name."""
        self.assertTrue(is_valid_company("talentarchitect.com"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

