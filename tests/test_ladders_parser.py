"""
Unit tests for Ladders (theladders.com) parser logic.

Run with:
    python -m pytest tests/test_ladders_parser.py -v
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import detect_provider, parse_job_cards_from_text


class TestLaddersProviderDetection(unittest.TestCase):
    """Test cases for Ladders provider detection."""

    def test_ladders_in_text(self):
        """Detect Ladders from text content."""
        self.assertEqual(detect_provider("Find jobs on Ladders today", ""), "Ladders")

    def test_ladders_in_filename(self):
        """Detect Ladders from filename."""
        self.assertEqual(detect_provider("", "Gmail - Your Skills are in High Demand_ Job Openings Available.pdf"), "Ladders")


class TestLaddersJobParsing(unittest.TestCase):
    """Test cases for parsing Ladders job listings."""

    def test_basic_ladders_job(self):
        """Parse a basic Ladders job listing."""
        text = "                   Principal Software Engineer            / Salt Lake City          , UT  /  $180K - $279K*\n"
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Principal Software Engineer")
        self.assertEqual(jobs[0]["company"], "Ladders-DailyDigest")
        self.assertEqual(jobs[0]["location"], "Salt Lake City, UT")

    def test_virtual_travel_to_remote(self):
        """Convert 'Virtual / Travel' in Ladders location to 'Remote'."""
        text = "                   Senior C# Back-End Developer                / V      irtual / Travel  /  $165K - $180K*       Remote\n"
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior C# Back-End Developer")
        self.assertEqual(jobs[0]["company"], "Ladders-DailyDigest")
        self.assertEqual(jobs[0]["location"], "Remote")
