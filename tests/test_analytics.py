import os
import sys
import sqlite3
import csv
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import print_analytics, handle_status_update

class TestAnalytics(unittest.TestCase):

    def setUp(self):
        # Create temp directory and CWD
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)

        # Set up SQLite database schema
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

    def test_analytics_empty(self):
        # With empty db, it should print that no jobs were found
        with patch('parse_jobs.console.print') as mock_print:
            print_analytics(db_path=self.db_path)
            mock_print.assert_any_call("[yellow]No jobs found to analyze.[/yellow]")

    def test_analytics_with_data(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert a job with high fit score and an applied status
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status, provider, fit_score, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("job1", "Test Company A", "Senior Backend Engineer", "Remote", "Applied", "Indeed", 95, "2026-07-10"))
        
        cursor.execute("""
            INSERT INTO job_workflow (job_id, tracker_status, updated_at)
            VALUES (?, ?, ?)
        """, ("job1", "Applied", "2026-07-12 12:00:00"))

        # Insert a job with medium fit score and technical interview status
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status, provider, fit_score, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("job2", "Test Company B", "Software Developer", "Utah", "Technical Interview", "LinkedIn", 75, "2026-07-11"))
        
        cursor.execute("""
            INSERT INTO job_workflow (job_id, tracker_status, updated_at)
            VALUES (?, ?, ?)
        """, ("job2", "Technical Interview", "2026-07-15 14:00:00"))

        # Insert a job with low fit score and ignored/New status
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status, provider, fit_score, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("job3", "Test Company C", "QA Engineer", "Onsite", "New", "ZipRecruiter", 25, "2026-07-15"))

        conn.commit()
        conn.close()

        with patch('parse_jobs.console.print') as mock_print:
            print_analytics(db_path=self.db_path)
            
            # Verify it printed headings
            mock_print.assert_any_call("\n[bold magenta]=========================================[/bold magenta]")
            mock_print.assert_any_call("[bold magenta]          JOB PIPELINE ANALYTICS         [/bold magenta]")
            
            # Check that table outputs were called (which happens when Rich tables/panels are printed)
            self.assertTrue(mock_print.called)

    def test_new_statuses_handling(self):
        # Insert a job to update
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status)
            VALUES (?, ?, ?, ?, ?)
        """, ("job_offer_test", "Offer Company", "Lead Engineer", "Remote", "New"))
        conn.commit()
        conn.close()

        # Update status to "Offer"
        success = handle_status_update("job_offer_test", "Offer", "Received formal offer letter")
        self.assertTrue(success)

        # Verify DB updates for Offer status
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id = ?", ("job_offer_test",))
        row = cursor.fetchone()
        self.assertEqual(row[0], "Offer")
        self.assertEqual(row[1], "Applied")
        self.assertEqual(row[2], "Already Applied")
        self.assertEqual(row[3], "Active")

        # Update status to "Accepted"
        success_accept = handle_status_update("job_offer_test", "Accepted", "Accepted the offer!")
        self.assertTrue(success_accept)

        cursor.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id = ?", ("job_offer_test",))
        row_accept = cursor.fetchone()
        self.assertEqual(row_accept[0], "Accepted")
        self.assertEqual(row_accept[1], "Applied")
        self.assertEqual(row_accept[2], "Already Applied")
        self.assertEqual(row_accept[3], "Closed")
        conn.close()

if __name__ == '__main__':
    unittest.main()
