"""
Unit tests for jobs.utah.gov (Utah's Daily Job Summary) parser logic.

Run with:
    python -m pytest tests/test_utah_jobs_parser.py -v
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import detect_provider, parse_job_cards_from_text


class TestUtahJobsProviderDetection(unittest.TestCase):
    """Test cases for jobs.utah.gov provider detection."""

    def test_utah_jobs_in_text(self):
        """Detect jobs.utah.gov from text content."""
        self.assertEqual(detect_provider("Find jobs on jobs.utah.gov today", ""), "jobs.utah.gov")

    def test_utah_jobs_summary_in_text(self):
        """Detect jobs.utah.gov from email summary title in text."""
        self.assertEqual(detect_provider("Utah's Daily Job Summary is here", ""), "jobs.utah.gov")

    def test_utah_jobs_case_insensitive(self):
        """Provider detection should be case-insensitive."""
        self.assertEqual(detect_provider("JOBS.UTAH.GOV ALERT", ""), "jobs.utah.gov")

    def test_utah_jobs_in_filename(self):
        """Detect jobs.utah.gov from filename."""
        self.assertEqual(detect_provider("", "Gmail - Utah's Daily Job Summary.pdf"), "jobs.utah.gov")


class TestUtahJobsParsing(unittest.TestCase):
    """Test cases for parsing jobs.utah.gov job listings."""

    def test_basic_utah_job(self):
        """Parse a basic jobs.utah.gov job listing."""
        text = "     Software Engineer {SOUTH JORDAN}\n"
        jobs = parse_job_cards_from_text(text, provider="jobs.utah.gov", source_pdf="utah_jobs.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Engineer")
        self.assertEqual(jobs[0]["company"], "Jobs.utah.gov-DailySummary")
        self.assertEqual(jobs[0]["location"], "South Jordan")

    def test_spacing_cleanup_in_location(self):
        """Parse a jobs.utah.gov job listing and clean up spacing in location."""
        text = "     Software Developer Intern: Data Ingestion and Integration {SAL    T LAKE CITY}\n"
        jobs = parse_job_cards_from_text(text, provider="jobs.utah.gov", source_pdf="utah_jobs.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Software Developer Intern: Data Ingestion and Integration")
        self.assertEqual(jobs[0]["company"], "Jobs.utah.gov-DailySummary")
        self.assertEqual(jobs[0]["location"], "Salt Lake City")
