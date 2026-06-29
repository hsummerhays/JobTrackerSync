"""
Unit tests for scoring and priority logic.

Run with:
    python -m pytest tests/test_scoring.py -v
"""
import sys
import os
import unittest

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import compute_priority, classify_job_type


class TestComputePriority(unittest.TestCase):
    """Test cases for compute_priority function."""

    def test_p1_apply_now_five_stars(self):
        self.assertEqual(
            compute_priority("★★★★★ Apply Now", "Apply"),
            "P1 – Apply today"
        )

    def test_p2_apply_four_stars(self):
        self.assertEqual(
            compute_priority("★★★★☆ Strong", "Apply"),
            "P2 – Apply this week"
        )

    def test_p2_contact_recruiter(self):
        self.assertEqual(
            compute_priority("★★★★★ Apply Now", "Contact Recruiter"),
            "P2 – Apply this week"
        )

    def test_p3_review(self):
        self.assertEqual(
            compute_priority("★★★☆☆ Maybe", "Review"),
            "P3 – Investigate"
        )

    def test_p4_ignore(self):
        self.assertEqual(
            compute_priority("★☆☆☆☆ Skip", "Ignore"),
            "P4 – Ignore"
        )

    def test_p1_requires_apply_action(self):
        # Five stars but not Apply action should be P2
        self.assertEqual(
            compute_priority("★★★★★ Apply Now", "Review"),
            "P3 – Investigate"
        )

    def test_priority_uses_en_dash_not_hyphen(self):
        result = compute_priority("★★★★★ Apply Now", "Apply")
        self.assertIn("\u2013", result)   # en-dash
        self.assertNotIn("-", result)    # no plain hyphen


class TestClassifyJobType(unittest.TestCase):
    """Test cases for classify_job_type function."""

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
