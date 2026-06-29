"""
Test runner for JobTrackerSync test suite.

This module imports and runs all focused test modules:
- test_company_validation.py
- test_scoring.py
- test_deduplication.py
- test_glassdoor_parser.py
- test_linkedin_parser.py

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
            parse_jobs.save_to_sqlite = lambda *_args, **_kwargs: None
            try:
                parse_jobs.clean_existing_tracker(tracker_path)
            finally:
                parse_jobs.save_to_sqlite = original_save_to_sqlite

            with open(tracker_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(rows[0]["Company"], "Futran Tech Solutions Pvt. Ltd.")


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
