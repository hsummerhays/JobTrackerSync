"""
Unit tests for BHE Career Site parser logic.

Run with:
    python -m pytest tests/test_bhe_parser.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse_jobs import detect_provider, parse_job_cards_from_text

class TestBHEProviderDetection(unittest.TestCase):
    """Test cases for BHE provider detection."""

    def test_bhe_in_text(self):
        """Detect BHE from text content."""
        self.assertEqual(detect_provider("Welcome to the BHE Career Site", ""), "BHE")

    def test_bhe_in_filename(self):
        """Detect BHE from filename."""
        self.assertEqual(detect_provider("", "Gmail - New job opportunities at BHE Career Site.pdf"), "BHE")

class TestBHEJobParsing(unittest.TestCase):
    """Test cases for parsing BHE job listings."""

    def test_basic_bhe_job(self):
        """Parse BHE job listings from text email template."""
        text = (
            "We have new jobs that might interest you. Have a look.\n"
            "Assoc IT Environment Mgr/IT Environment Mgr\n"
            "You can also view all the jobs available at our company .\n"
        )
        jobs = parse_job_cards_from_text(text, provider="BHE", source_pdf="bhe.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Assoc IT Environment Mgr/IT Environment Mgr")
        self.assertEqual(jobs[0]["company"], "BHE")
        self.assertEqual(jobs[0]["location"], "Unknown")
        self.assertEqual(jobs[0]["provider"], "BHE")

if __name__ == '__main__':
    unittest.main()
