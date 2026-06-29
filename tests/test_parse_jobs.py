"""
Unit tests for JobTrackerSync core logic.

Run with:
    python -m pytest tests/ -v
or:
    python tests/test_parse_jobs.py
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse_jobs import (
    is_valid_company,
    compute_priority,
    classify_job_type,
    detect_provider,
    evaluate_job,
    parse_job_cards_from_text,
)


# ---------------------------------------------------------------------------
# is_valid_company
# ---------------------------------------------------------------------------

class TestIsValidCompany(unittest.TestCase):

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
        self.assertFalse(is_valid_company("We are hiring."))


# ---------------------------------------------------------------------------
# compute_priority
# ---------------------------------------------------------------------------

class TestComputePriority(unittest.TestCase):

    def test_p1_apply_now_five_stars(self):
        self.assertEqual(
            compute_priority("★★★★★ Apply Now", "Apply"),
            "P1 \u2013 Apply today"
        )

    def test_p2_apply_four_stars(self):
        self.assertEqual(
            compute_priority("★★★★☆ Strong", "Apply"),
            "P2 \u2013 Apply this week"
        )

    def test_p2_contact_recruiter(self):
        self.assertEqual(
            compute_priority("★★★★★ Apply Now", "Contact Recruiter"),
            "P2 \u2013 Apply this week"
        )

    def test_p3_review(self):
        self.assertEqual(
            compute_priority("★★★☆☆ Maybe", "Review"),
            "P3 \u2013 Investigate"
        )

    def test_p4_ignore(self):
        self.assertEqual(
            compute_priority("★☆☆☆☆ Skip", "Ignore"),
            "P4 \u2013 Ignore"
        )

    def test_p1_requires_apply_action(self):
        # Five stars but not Apply action should be P2
        self.assertEqual(
            compute_priority("★★★★★ Apply Now", "Review"),
            "P3 \u2013 Investigate"
        )

    def test_priority_uses_en_dash_not_hyphen(self):
        result = compute_priority("★★★★★ Apply Now", "Apply")
        self.assertIn("\u2013", result)   # en-dash
        self.assertNotIn("-", result)    # no plain hyphen


# ---------------------------------------------------------------------------
# classify_job_type
# ---------------------------------------------------------------------------

class TestClassifyJobType(unittest.TestCase):

    def test_software_engineer_title(self):
        self.assertEqual(classify_job_type("Senior Software Engineer", ""), "Software Engineer")

    def test_backend_engineer(self):
        self.assertEqual(classify_job_type("Senior Backend Engineer", ""), "Software Engineer")

    def test_full_stack_engineer(self):
        self.assertEqual(classify_job_type("Full Stack Developer", ""), "Software Engineer")

    def test_lead_engineer(self):
        self.assertEqual(classify_job_type("Lead Software Engineer", ""), "Software Engineer")

    def test_operations_manager(self):
        self.assertEqual(classify_job_type("Operations Manager", ""), "Operations")

    def test_operations_supervisor(self):
        self.assertEqual(classify_job_type("Night Operations Department Supervisor", ""), "Operations")

    def test_manufacturing_engineer_is_operations(self):
        self.assertEqual(classify_job_type("Senior Manufacturing Engineer", ""), "Operations")

    def test_default_is_software_engineer(self):
        # Unknown title defaults to Software Engineer
        self.assertEqual(classify_job_type("Some Random Title", ""), "Software Engineer")


# ---------------------------------------------------------------------------
# Job ID determinism (deduplication key)
# ---------------------------------------------------------------------------

class TestJobIdDeterminism(unittest.TestCase):
    """Verify that MD5 job IDs are stable across identical inputs."""

    def _make_job_id(self, company, title, location):
        import hashlib
        return hashlib.md5(
            f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}"
            .encode('utf-8')
        ).hexdigest()[:12]

    def test_same_inputs_produce_same_id(self):
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        self.assertEqual(id1, id2)

    def test_different_company_produces_different_id(self):
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Citi", "Senior Backend Engineer", "Remote")
        self.assertNotEqual(id1, id2)

    def test_different_title_produces_different_id(self):
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Alivia Analytics", "Lead Software Engineer", "Remote")
        self.assertNotEqual(id1, id2)

    def test_case_insensitive(self):
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("ALIVIA ANALYTICS", "SENIOR BACKEND ENGINEER", "REMOTE")
        self.assertEqual(id1, id2)

    def test_whitespace_trimmed(self):
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("  Alivia Analytics  ", "  Senior Backend Engineer  ", "  Remote  ")
        self.assertEqual(id1, id2)

    def test_id_is_12_chars(self):
        job_id = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        self.assertEqual(len(job_id), 12)


# ---------------------------------------------------------------------------
# detect_provider
# ---------------------------------------------------------------------------

class TestDetectProvider(unittest.TestCase):

    def test_linkedin_in_text(self):
        self.assertEqual(detect_provider("Find jobs on LinkedIn today", ""), "LinkedIn")

    def test_indeed_in_text(self):
        self.assertEqual(detect_provider("Indeed Job Alert notification", ""), "Indeed")

    def test_glassdoor_in_text(self):
        self.assertEqual(detect_provider("glassdoor company review listings", ""), "Glassdoor")

    def test_ziprecruiter_in_text(self):
        self.assertEqual(detect_provider("ZipRecruiter daily digest", ""), "ZipRecruiter")

    def test_provider_detected_from_filename(self):
        self.assertEqual(detect_provider("", "linkedin_export.pdf"), "LinkedIn")

    def test_unknown_content(self):
        self.assertEqual(detect_provider("random unrelated content here", "random.pdf"), "Unknown/Other")

    def test_case_insensitive(self):
        self.assertEqual(detect_provider("LINKEDIN JOBS ALERT", ""), "LinkedIn")


# ---------------------------------------------------------------------------
# evaluate_job — helper
# ---------------------------------------------------------------------------

def _make_job(title="Senior Software Engineer", company="Acme Corp", location="Remote",
              context=None, url="https://example.com/job"):
    """Build a minimal job dict suitable for evaluate_job tests."""
    if context is None:
        context = f"{title} {company} {location}"
    return {
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "provider": "LinkedIn",
        "source_pdf": "test.pdf",
        "raw_context": context,
    }


class TestEvaluateJob(unittest.TestCase):

    def test_remote_dotnet_job_recommended_p1(self):
        job = _make_job(
            title="Senior .NET Developer",
            company="Acme Corp",
            location="Remote",
            context="senior .net developer acme corp remote c# backend legacy",
        )
        should_rec, confidence, notes, fit_score, priority, company_type, rec, reason, matched, missing, job_type = evaluate_job(job)
        self.assertTrue(should_rec)
        self.assertEqual(confidence, "🟢 High")
        self.assertEqual(rec, "★★★★★ Apply Now")
        self.assertEqual(priority, "P1 – Apply today")
        self.assertEqual(job_type, "Software Engineer")

    def test_out_of_state_is_rejected(self):
        job = _make_job(location="Chicago, IL", context="senior software engineer acme corp chicago il")
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("Rule 6", notes)

    def test_degree_required_is_rejected(self):
        job = _make_job(
            location="Remote",
            context="senior software engineer acme corp remote bachelor's degree required for this position",
        )
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("Rule 7", notes)

    def test_invalid_company_is_rejected(self):
        job = _make_job(company="Unknown")
        should_rec, *_ = evaluate_job(job)
        self.assertFalse(should_rec)

    def test_conversational_fragment_is_rejected(self):
        job = _make_job(company="Your background as a developer", location="Remote")
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("conversational", notes.lower())

    def test_recruiting_firm_company_type(self):
        job = _make_job(
            company="Robert Half Staffing",
            location="Remote",
            context="robert half staffing senior software engineer remote .net c#",
        )
        _, _, _, _, _, company_type, *_ = evaluate_job(job)
        self.assertEqual(company_type, "Recruiting Firm")

    def test_faang_company_type(self):
        job = _make_job(
            company="Google",
            location="Remote",
            context="google senior software engineer remote .net c#",
        )
        _, _, _, _, _, company_type, *_ = evaluate_job(job)
        self.assertEqual(company_type, "Enterprise")

    def test_utah_location_is_accepted(self):
        job = _make_job(
            location="Salt Lake City, UT",
            context="senior software engineer acme corp salt lake city ut .net c#",
        )
        should_rec, *_ = evaluate_job(job)
        self.assertTrue(should_rec)

    def test_onsite_restriction_reduces_fit_score(self):
        unrestricted = _make_job(
            title="Senior .NET Developer",
            context="senior .net developer acme corp remote c# backend",
        )
        restricted = _make_job(
            title="Senior .NET Developer",
            context="senior .net developer acme corp remote c# backend local candidate only",
        )
        _, _, _, score_open, *_ = evaluate_job(unrestricted)
        _, _, notes_restricted, score_restricted, *_ = evaluate_job(restricted)
        self.assertLess(score_restricted, score_open)
        self.assertIn("Local/Onsite restriction detected", notes_restricted)

    def test_operations_job_type_and_penalty(self):
        job = _make_job(
            title="Operations Manager",
            location="Remote",
            context="operations manager acme corp remote logistics inventory supply chain",
        )
        _, _, _, fit_score, _, _, _, _, _, _, job_type = evaluate_job(job)
        self.assertEqual(job_type, "Operations")
        self.assertEqual(fit_score, 75)

    def test_java_role_scores_less_than_dotnet(self):
        java_job = _make_job(
            title="Senior Java Developer",
            context="senior java developer acme corp remote spring microservices",
        )
        dotnet_job = _make_job(
            title="Senior .NET Developer",
            context="senior .net developer acme corp remote c# microservices",
        )
        _, _, _, java_score, *_ = evaluate_job(java_job)
        _, _, _, dotnet_score, *_ = evaluate_job(dotnet_job)
        self.assertLess(java_score, dotnet_score)


# ---------------------------------------------------------------------------
# parse_job_cards_from_text
# ---------------------------------------------------------------------------

class TestParseJobCards(unittest.TestCase):

    def test_basic_title_company_location(self):
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Acme Corp")

    def test_company_before_title_pattern(self):
        # LinkedIn sometimes puts the company name on the line before the title
        text = "Acme Corp\nSenior Software Engineer\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Acme Corp")

    def test_heading_lines_are_filtered(self):
        text = "Recommended Jobs\nSenior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")

    def test_provider_and_source_attached_to_job(self):
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="jobs.pdf")
        self.assertEqual(jobs[0]["provider"], "Indeed")
        self.assertEqual(jobs[0]["source_pdf"], "jobs.pdf")

    def test_consecutive_titles_parsed_separately(self):
        text = "Senior Software Engineer\nLead Developer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="test.pdf")
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Software Engineer", titles)
        self.assertIn("Lead Developer", titles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
