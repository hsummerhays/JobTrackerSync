"""
Unit tests for LinkedIn-specific parser logic.

Run with:
    python -m pytest tests/test_linkedin_parser.py -v
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import detect_provider, parse_job_cards_from_text


class TestLinkedInProviderDetection(unittest.TestCase):
    """Test cases for LinkedIn provider detection."""

    def test_linkedin_in_text(self):
        """Detect LinkedIn from text content."""
        self.assertEqual(detect_provider("Find jobs on LinkedIn today", ""), "LinkedIn")

    def test_linkedin_case_insensitive(self):
        """Provider detection should be case-insensitive."""
        self.assertEqual(detect_provider("LINKEDIN JOBS ALERT", ""), "LinkedIn")

    def test_linkedin_in_filename(self):
        """Detect LinkedIn from filename."""
        self.assertEqual(detect_provider("", "linkedin_export.pdf"), "LinkedIn")

    def test_linkedin_mixed_case_filename(self):
        """Detect LinkedIn from mixed-case filename."""
        self.assertEqual(detect_provider("", "LinkedIn_Jobs.pdf"), "LinkedIn")


class TestLinkedInJobParsing(unittest.TestCase):
    """Test cases for parsing LinkedIn job listings."""

    def test_basic_linkedin_job_card(self):
        """Parse a basic LinkedIn job card."""
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Acme Corp")

    def test_company_before_title_pattern(self):
        """LinkedIn sometimes puts the company name on the line before the title."""
        text = "Acme Corp\nSenior Software Engineer\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Acme Corp")

    def test_linkedin_provider_attached(self):
        """Ensure LinkedIn provider is attached to parsed jobs."""
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(jobs[0]["provider"], "LinkedIn")
        self.assertEqual(jobs[0]["source_pdf"], "linkedin.pdf")

    def test_linkedin_heading_filtered(self):
        """LinkedIn-specific headings should be filtered out."""
        text = "Recommended Jobs\nSenior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")

    def test_strips_ui_label_from_company_without_losing_abbreviation_period(self):
        """LinkedIn PDF parser can glue UI labels to company names; should strip them."""
        text = ".NET Full Stack Engineer - Remote\nFutran Tech Solutions Pvt. Ltd.View Details\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Futran Tech Solutions Pvt. Ltd.")

    def test_cleans_location_when_next_card_is_glued_to_ui_label(self):
        """LinkedIn can glue job cards together with UI labels; should clean location."""
        text = (
            "Full Stack Project Lead\n"
            "Citi\n"
            "Irving, TX View Details Belva.ai • Bellevue, WA • Remote1-Click Apply\n"
        )
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Citi")
        self.assertEqual(jobs[0]["location"], "Irving, TX")

    def test_does_not_use_next_title_as_location(self):
        """Should not mistake the next job's title as the current job's location."""
        text = (
            "Senior Software Engineer, Backend (AI Agent)\n"
            "Jobright.ai\n"
            "Sr. Software Engineer - Provider Access (Remote)\n"
            "Provider Access Co\n"
            "Remote\n"
        )
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertGreaterEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["company"], "Jobright.ai")
        self.assertEqual(jobs[0]["location"], "")
        self.assertNotIn("Provider Access", jobs[0]["location"])

    def test_consecutive_titles_parsed_separately(self):
        """LinkedIn can have consecutive title lines; should parse separately."""
        text = "Senior Software Engineer\nLead Developer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Software Engineer", titles)
        self.assertIn("Lead Developer", titles)

    def test_linkedin_multiple_jobs(self):
        """Parse multiple LinkedIn job cards."""
        text = (
            "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
            "Backend Developer\nTech Startup\nRemote\n"
        )
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertGreaterEqual(len(jobs), 2)

    def test_wrapped_title_continuation(self):
        """Ensure title wraps correctly when followed by a Company · Location line."""
        text = (
            "Senior Software Engineer- Big Data & MCP, Data\n"
            "Foundations\n"
            "RevSpring · Salt Lake City , UT\n"
        )
        jobs = parse_job_cards_from_text(text, provider="LinkedIn", source_pdf="linkedin.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer- Big Data & MCP, Data Foundations")
        self.assertEqual(jobs[0]["company"], "RevSpring")
        self.assertEqual(jobs[0]["location"], "Salt Lake City, UT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
