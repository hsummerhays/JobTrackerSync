import os
import sys
import sqlite3
import csv
import tempfile
import unittest
from unittest.mock import MagicMock

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import (
    handle_manual_add,
    handle_status_update,
    detect_provider,
    extract_job_urls_from_page
)

class TestCliHandlers(unittest.TestCase):

    def setUp(self):
        # Create temp directory and switch to it to avoid messing up workspace files
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)

        # Set up a mock master_tracker.csv
        self.tracker_path = "master_tracker.csv"
        with open(self.tracker_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider", 
                "Source PDF", "Confidence", "Fit Score", "Priority", "Company Type", 
                "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company", 
                "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Notes", "Recruiter", "Hiring Manager"
            ])
            writer.writeheader()

        # Set up SQLite database schema and close connection so it's not locked
        self.db_path = "jobs.db"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, review_status TEXT, job_type TEXT, company TEXT, position TEXT, location TEXT, 
                url TEXT, provider TEXT, source_pdf TEXT, confidence TEXT, fit_score INTEGER, priority TEXT, 
                company_type TEXT, recommendation TEXT, tracker_status TEXT, disposition TEXT, action TEXT, 
                existing_company TEXT, reason TEXT, matched_skills TEXT, missing_skills TEXT, date_added TEXT, 
                notes TEXT, recruiter TEXT, hiring_manager TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_workflow (
                job_id TEXT PRIMARY KEY, tracker_status TEXT, review_status TEXT, action TEXT, disposition TEXT, 
                notes TEXT, updated_at TEXT, updated_by TEXT, follow_up_date TEXT, last_contact_date TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def test_handle_manual_add_success(self):
        # Call handle_manual_add non-interactively
        handle_manual_add(
            company="Test Manual Company",
            position="Manual QA Engineer",
            location="Remote",
            job_type="Software Engineer",
            provider="Manual",
            recruiter="John Recruiter",
            hiring_manager="Jane Manager",
            url="https://example.com/manual",
            fit_score=85,
            recommendation="★★★★☆ Strong",
            status="New",
            notes="Manually added for testing",
            interactive=False
        )

        # Verify SQL row was created
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT company, position, recruiter, hiring_manager, notes FROM jobs")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Test Manual Company")
        self.assertEqual(row[1], "Manual QA Engineer")
        self.assertEqual(row[2], "John Recruiter")
        self.assertEqual(row[3], "Jane Manager")
        self.assertEqual(row[4], "Manually added for testing")
        conn.close()

        # Verify CSV row was appended
        with open(self.tracker_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Company"], "Test Manual Company")
            self.assertEqual(rows[0]["Position"], "Manual QA Engineer")

    def test_handle_status_update_success(self):
        # Insert a job to be updated
        job_id = "testjob12345"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status)
            VALUES (?, ?, ?, ?, ?)
        """, (job_id, "Fast Growth Inc", "Staff Developer", "Remote", "New"))
        conn.commit()
        conn.close()

        # Update status
        success = handle_status_update(
            query=job_id,
            status="Applied",
            notes="Updated through CLI"
        )
        self.assertTrue(success)

        # Verify database update in jobs
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        self.assertEqual(row[0], "Applied")
        self.assertEqual(row[1], "Applied")
        self.assertEqual(row[2], "Already Applied")
        self.assertEqual(row[3], "Waiting")

        # Verify database update in job_workflow
        cursor.execute("SELECT tracker_status, notes FROM job_workflow WHERE job_id = ?", (job_id,))
        row_w = cursor.fetchone()
        self.assertIsNotNone(row_w)
        self.assertEqual(row_w[0], "Applied")
        self.assertEqual(row_w[1], "Updated through CLI")
        conn.close()

    def test_detect_provider(self):
        self.assertEqual(detect_provider("", "linkedin_report.pdf"), "LinkedIn")
        self.assertEqual(detect_provider("Welcome to jobs.utah.gov!", ""), "jobs.utah.gov")
        self.assertEqual(detect_provider("BHE Career Site postings", ""), "BHE")
        self.assertEqual(detect_provider("The Ladders Daily Alert", ""), "Ladders")
        self.assertEqual(detect_provider("Random search on Indeed", ""), "Indeed")
        self.assertEqual(detect_provider("ZipRecruiter Alert", ""), "ZipRecruiter")
        self.assertEqual(detect_provider("Glassdoor Jobs", ""), "Glassdoor")
        self.assertEqual(detect_provider("Some text", "arbitrary_name.pdf"), "Unknown/Other")

    def test_extract_job_urls_from_page(self):
        # Mock a pdf page with annotations where obj['/A'] is a mock returning the URI dict from get_object()
        mock_page = MagicMock()
        
        mock_annot1 = MagicMock()
        mock_action1 = MagicMock()
        mock_action1.get_object.return_value = {'/URI': 'https://example.com/job1'}
        mock_annot1.get_object.return_value = {
            '/Rect': [100, 500, 200, 520],
            '/A': mock_action1
        }
        
        mock_annot2 = MagicMock()
        mock_action2 = MagicMock()
        mock_action2.get_object.return_value = {'/URI': 'https://example.com/job2'}
        mock_annot2.get_object.return_value = {
            '/Rect': [100, 200, 200, 220],
            '/A': mock_action2
        }
        
        mock_annot3 = MagicMock()
        mock_action3 = MagicMock()
        mock_action3.get_object.return_value = {'/URI': 'https://example.com/privacy'}
        mock_annot3.get_object.return_value = {
            '/Rect': [100, 300, 200, 320],
            '/A': mock_action3
        }
        
        mock_page.annotations = [mock_annot1, mock_annot2, mock_annot3]

        urls = extract_job_urls_from_page(mock_page)
        # Order should be sorted by Y coordinate descending (500, then 200)
        self.assertEqual(urls, ['https://example.com/job1', 'https://example.com/job2'])

if __name__ == '__main__':
    unittest.main()
