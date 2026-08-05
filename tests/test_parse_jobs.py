"""
Core unit tests for parse_jobs.py: evaluate_job scoring, tracker cleanup,
and general job-card parsing. Provider-specific parsing has its own focused
modules (test_linkedin_parser.py, test_glassdoor_parser.py, etc.) alongside
this file in tests/; pytest discovers and runs all of them together.

Run with:
    python -m pytest tests/ -v
or:
    python tests/test_parse_jobs.py
"""
import sys
import os
import csv
import tempfile
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs

from parse_jobs import (
    evaluate_job,
    parse_job_cards_from_text,
)


# ---------------------------------------------------------------------------
# clean_existing_tracker (integration test)
# ---------------------------------------------------------------------------

class TestCleanExistingTracker(unittest.TestCase):

    def test_strips_ui_label_without_losing_abbreviation_period(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # clean_existing_tracker() operates on a hardcoded "jobs.db" (and,
            # via backup_file_if_exists, on the tracker path) relative to cwd
            # -- chdir into the sandbox so neither can ever touch the real
            # project files, on top of the save_to_sqlite mock below.
            old_cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                tracker_path = os.path.join(tmp_dir, "master_tracker.csv")
                with open(tracker_path, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["Company", "Position", "Location"])
                    writer.writeheader()
                    writer.writerow({
                        "Company": "Futran Tech Solutions Pvt. Ltd.View Details",
                        "Position": ".NET Full Stack Engineer - Remote",
                        "Location": "Remote",
                    })

                original_save_to_sqlite = parse_jobs.save_to_sqlite
                parse_jobs.save_to_sqlite = lambda *_args, **_kwargs: True
                try:
                    parse_jobs.clean_existing_tracker(tracker_path)
                finally:
                    parse_jobs.save_to_sqlite = original_save_to_sqlite

                with open(tracker_path, newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))

                self.assertEqual(rows[0]["Company"], "Futran Tech Solutions Pvt. Ltd.")
            finally:
                os.chdir(old_cwd)


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
        self.assertEqual(confidence, "100%")
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
        # 20 (remote) + 15 (manager) + 20 (logistics/inventory/supply chain) + 10 (no degree)
        # + 10 (small/medium company) - 15 (Operations penalty) = 60.
        # "manager" alone no longer counts toward score_experience (that's a SWE-seniority
        # signal now), so this no longer double-counts with the Operations score_backend_fs bonus.
        self.assertEqual(fit_score, 60)

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

    def test_title_stack_takes_precedence_over_noisy_context(self):
        job = _make_job(
            title="PHP / Zend / Laravel",
            company="Integrity Resources",
            location="Remote",
            context="php zend laravel integrity resources remote unrelated nearby text mentions .net azure",
        )
        _, _, _, fit_score, _, _, _, _, matched, missing, _ = evaluate_job(job)
        self.assertNotIn(".NET", matched)
        self.assertNotIn("Azure", matched)
        self.assertIn("PHP", missing)
        self.assertIn("Zend", missing)
        self.assertIn("Laravel", missing)
        self.assertLess(fit_score, 80)

    def test_operations_profile_ignores_software_noise(self):
        job = _make_job(
            title="Operations Manager",
            company="Capstone Logistics LLC",
            location="Salt Lake City, UT",
            context="operations manager logistics inventory salt lake city ut nearby text mentions .net c# azure",
        )
        _, _, _, _, _, _, _, reason, matched, missing, job_type = evaluate_job(job)
        self.assertEqual(job_type, "Operations")
        self.assertIn("Logistics", matched)
        self.assertNotIn(".NET", missing)
        self.assertNotIn("Azure", missing)
        self.assertIn("Operations role", reason)

    def test_email_metadata_leak_is_rejected(self):
        job = _make_job(title="Apply Now for this role", company="Acme Corp")
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("email metadata", notes.lower())

    def test_timestamp_in_title_is_rejected(self):
        job = _make_job(title="Senior Engineer 3:45 PM", company="Acme Corp")
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("timestamp", notes.lower())

    def test_missing_title_or_company_is_rejected(self):
        job = _make_job(title="", company="Acme Corp")
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("Rule 4", notes)

    def test_skip_keyword_without_compelling_tech_is_rejected(self):
        job = _make_job(
            title="AI Trainer",
            company="Acme Corp",
            location="Remote",
            context="ai trainer acme corp remote no relevant tech mentioned here",
        )
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertFalse(should_rec)
        self.assertIn("Rule 8", notes)

    def test_utah_gov_provider_gets_fixed_confidence_and_note(self):
        job = _make_job(location="Remote", context="senior software engineer acme corp remote .net")
        job["provider"] = "jobs.utah.gov"
        should_rec, confidence, notes, *_ = evaluate_job(job)
        self.assertEqual(confidence, "40%")
        self.assertIn("not included in daily summary", notes)

    def test_low_confidence_from_short_context_is_not_recommended(self):
        job = _make_job(location="Remote", context="short")
        should_rec, confidence, *_ = evaluate_job(job)
        self.assertEqual(confidence, "20%")
        self.assertFalse(should_rec)

    def test_digest_company_without_url_gets_70_percent_confidence(self):
        # "DailySummary" is explicitly allowed through is_valid_company, but the
        # confidence heuristic still treats digest placeholders as low-trust.
        job = _make_job(
            company="DailySummary Digest",
            location="Remote",
            url="N/A",
            context="senior software engineer remote .net enough context to pass the length check here",
        )
        should_rec, confidence, *_ = evaluate_job(job)
        self.assertEqual(confidence, "70%")

    def test_defense_company_type(self):
        job = _make_job(
            company="Lockheed Systems",
            location="Remote",
            context="lockheed systems senior software engineer remote .net c#",
        )
        _, _, _, _, _, company_type, *_ = evaluate_job(job)
        self.assertEqual(company_type, "Defense")

    def test_healthcare_company_type(self):
        job = _make_job(
            company="Summit Medical",
            location="Remote",
            context="summit medical senior software engineer remote .net c#",
        )
        _, _, _, _, _, company_type, *_ = evaluate_job(job)
        self.assertEqual(company_type, "Healthcare")

    def test_financial_company_type(self):
        job = _make_job(
            company="Capital Trust",
            location="Remote",
            context="capital trust senior software engineer remote .net c#",
        )
        _, _, _, _, _, company_type, *_ = evaluate_job(job)
        self.assertEqual(company_type, "Financial")

    def test_low_recommendation_band_for_moderate_fit_score(self):
        # No remote/utah, no experience/role keywords, no stack match --
        # low fit score but still Utah-based so it passes Rule 6.
        job = _make_job(
            title="Coordinator",
            company="Acme Corp",
            location="Salt Lake City, UT",
            context="coordinator acme corp salt lake city ut",
        )
        _, _, _, fit_score, _, _, rec, *_ = evaluate_job(job)
        self.assertLess(fit_score, 40)
        self.assertIn(rec, ["★★☆☆☆ Low", "★☆☆☆☆ Skip"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
