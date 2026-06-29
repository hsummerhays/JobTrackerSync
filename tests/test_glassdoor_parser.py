"""
Unit tests for Glassdoor-specific parser logic.

Run with:
    python -m pytest tests/test_glassdoor_parser.py -v
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import detect_provider, parse_job_cards_from_text


class TestGlassdoorProviderDetection(unittest.TestCase):
    """Test cases for Glassdoor provider detection."""

    def test_glassdoor_in_text(self):
        """Detect Glassdoor from text content."""
        self.assertEqual(detect_provider("glassdoor company review listings", ""), "Glassdoor")

    def test_glassdoor_case_insensitive(self):
        """Provider detection should be case-insensitive."""
        self.assertEqual(detect_provider("GLASSDOOR JOBS ALERT", ""), "Glassdoor")

    def test_glassdoor_in_filename(self):
        """Detect Glassdoor from filename."""
        self.assertEqual(detect_provider("", "glassdoor_export.pdf"), "Glassdoor")

    def test_glassdoor_mixed_case_filename(self):
        """Detect Glassdoor from mixed-case filename."""
        self.assertEqual(detect_provider("", "GlassDoor_Jobs.pdf"), "Glassdoor")


class TestGlassdoorJobParsing(unittest.TestCase):
    """Test cases for parsing Glassdoor job listings."""

    def test_basic_glassdoor_job_card(self):
        """Parse a basic Glassdoor job card."""
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Glassdoor", source_pdf="glassdoor.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Acme Corp")

    def test_glassdoor_provider_attached(self):
        """Ensure Glassdoor provider is attached to parsed jobs."""
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Glassdoor", source_pdf="glassdoor.pdf")
        self.assertEqual(jobs[0]["provider"], "Glassdoor")
        self.assertEqual(jobs[0]["source_pdf"], "glassdoor.pdf")

    def test_glassdoor_heading_filtered(self):
        """Glassdoor-specific headings should be filtered out."""
        text = "Glassdoor Job Alerts\nSenior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Glassdoor", source_pdf="glassdoor.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")

    def test_glassdoor_salary_info_in_location(self):
        """Glassdoor sometimes includes salary in location field."""
        text = "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT - $120K\n"
        jobs = parse_job_cards_from_text(text, provider="Glassdoor", source_pdf="glassdoor.pdf")
        self.assertEqual(len(jobs), 1)
        # Location should be cleaned, salary info may be in notes
        self.assertEqual(jobs[0]["company"], "Acme Corp")

    def test_glassdoor_multiple_jobs(self):
        """Parse multiple Glassdoor job cards."""
        text = (
            "Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n"
            "Backend Developer\nTech Startup\nRemote\n"
        )
        jobs = parse_job_cards_from_text(text, provider="Glassdoor", source_pdf="glassdoor.pdf")
        self.assertGreaterEqual(len(jobs), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
