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
from utils import VALID_STATUSES, VALID_REVIEW_STATUSES, VALID_ACTIONS

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
                "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes", "Recruiter", "Hiring Manager"
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
                existing_company TEXT, reason TEXT, matched_skills TEXT, missing_skills TEXT, date_added TEXT, last_seen TEXT, notes TEXT, recruiter TEXT, hiring_manager TEXT
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

    def test_handle_status_update_with_position_disambiguation(self):
        # Insert two jobs from same company with different titles
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status)
            VALUES ('job1', 'Acme Corp', 'Frontend Engineer', 'Remote', 'New'),
                   ('job2', 'Acme Corp', 'Backend Engineer', 'Remote', 'New')
        """)
        conn.commit()
        conn.close()

        # Update specifying position to disambiguate
        success = handle_status_update(
            query="Acme Corp",
            position="Backend Engineer",
            status="Phone Screen",
            notes="Screen scheduled"
        )
        self.assertTrue(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT job_id, tracker_status FROM jobs WHERE company = 'Acme Corp' ORDER BY job_id")
        rows = cursor.fetchall()
        self.assertEqual(rows[0], ('job1', 'New'))
        self.assertEqual(rows[1], ('job2', 'Phone Screen'))
        conn.close()

    def test_structured_update_idempotency_does_not_duplicate_notes(self):
        job_id = "idem_job_1"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status, notes)
            VALUES (?, 'AlignRx LLC', 'Software Developer II', 'Remote', 'New', 'Source Index: 40-11; Tech matches: .net')
        """, (job_id,))
        conn.commit()
        conn.close()

        structured_notes = "Comp: $86,400/year\nEmployment: Full-Time\nResume: Tailored 2026-10-03\nStatus: Ready to Apply"

        # First execution
        success1 = handle_status_update(
            query=job_id,
            notes=structured_notes,
            review_status="Reviewed",
            action="Apply",
            append_notes=True,
            structured_update=True
        )
        self.assertTrue(success1)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT notes FROM jobs WHERE job_id = ?", (job_id,))
        notes_after_run1 = cursor.fetchone()[0]
        conn.close()

        self.assertIn("Comp: $86,400/year", notes_after_run1)
        self.assertIn("Source Index: 40-11", notes_after_run1)
        self.assertEqual(notes_after_run1.count("Comp:"), 1)
        self.assertEqual(notes_after_run1.count("Resume:"), 1)

        # Second execution (identical structured update)
        success2 = handle_status_update(
            query=job_id,
            notes=structured_notes,
            review_status="Reviewed",
            action="Apply",
            append_notes=True,
            structured_update=True
        )
        self.assertTrue(success2)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT notes FROM jobs WHERE job_id = ?", (job_id,))
        notes_after_run2 = cursor.fetchone()[0]
        conn.close()

        # Must be strictly identical: no duplicated paragraphs or fields
        self.assertEqual(notes_after_run1, notes_after_run2)
        self.assertEqual(notes_after_run2.count("Comp:"), 1)
        self.assertEqual(notes_after_run2.count("Resume:"), 1)
        self.assertEqual(notes_after_run2.count("Status:"), 1)

    def test_structured_update_idempotency_updates_comp_in_place(self):
        job_id = "idem_job_2"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status, notes)
            VALUES (?, 'AlignRx LLC', 'Software Developer II', 'Remote', 'New',
                    'Source Index: 40-11\n\nComp: $80,000/year\nEmployment: Full-Time\nResume: Tailored 2026-10-03\nStatus: Ready to Apply')
        """, (job_id,))
        conn.commit()
        conn.close()

        # Update with new compensation
        updated_notes = "Comp: $86,400/year\nEmployment: Full-Time\nResume: Tailored 2026-10-03\nStatus: Ready to Apply"
        success = handle_status_update(
            query=job_id,
            notes=updated_notes,
            review_status="Reviewed",
            action="Apply",
            append_notes=True,
            structured_update=True
        )
        self.assertTrue(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT notes FROM jobs WHERE job_id = ?", (job_id,))
        notes = cursor.fetchone()[0]
        conn.close()

        self.assertIn("Comp: $86,400/year", notes)
        self.assertNotIn("Comp: $80,000/year", notes)
        self.assertEqual(notes.count("Comp:"), 1)
        self.assertEqual(notes.count("Employment:"), 1)

    def test_ambiguous_company_without_position_fails_closed(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status)
            VALUES ('j_a1', 'Multi Corp', 'Software Engineer', 'Remote', 'New'),
                   ('j_a2', 'Multi Corp', 'Product Manager', 'Remote', 'New')
        """)
        conn.commit()
        conn.close()

        # Update without specifying position must fail closed
        success = handle_status_update(
            query="Multi Corp",
            status="Applied"
        )
        self.assertFalse(success)

        # Neither job should have been modified
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM jobs WHERE company = 'Multi Corp'")
        statuses = [r[0] for r in cursor.fetchall()]
        self.assertEqual(statuses, ['New', 'New'])
        conn.close()

    def test_ambiguous_company_with_undiscriminating_position_fails_closed(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status)
            VALUES ('j_b1', 'Split Corp', 'Senior Software Engineer', 'Remote', 'New'),
                   ('j_b2', 'Split Corp', 'Staff Software Engineer', 'Remote', 'New')
        """)
        conn.commit()
        conn.close()

        # Position "Software Engineer" matches BOTH jobs and is undiscriminating -> must fail closed
        success = handle_status_update(
            query="Split Corp",
            position="Software Engineer",
            status="Applied"
        )
        self.assertFalse(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM jobs WHERE company = 'Split Corp'")
        statuses = [r[0] for r in cursor.fetchall()]
        self.assertEqual(statuses, ['New', 'New'])
        conn.close()

    def test_company_with_conflicting_position_fails_closed(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, company, position, location, tracker_status)
            VALUES ('j_c1', 'Solo Corp', 'Frontend Engineer', 'Remote', 'New')
        """)
        conn.commit()
        conn.close()

        # Conflicting position "Data Scientist" on Solo Corp must fail closed and not mutate
        success = handle_status_update(
            query="Solo Corp",
            position="Data Scientist",
            status="Applied"
        )
        self.assertFalse(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM jobs WHERE company = 'Solo Corp'")
        self.assertEqual(cursor.fetchone()[0], 'New')
        conn.close()

    def test_phone_screen_produces_canonical_tracker_status(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status) VALUES ('ps_job', 'Initech', 'Dev', 'Remote', 'New')")
        conn.commit()
        conn.close()

        success = handle_status_update(query="ps_job", status="Phone Screen")
        self.assertTrue(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id = 'ps_job'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Phone Screen")
        self.assertIn(row[0], VALID_STATUSES)
        self.assertIn(row[1], VALID_REVIEW_STATUSES)
        self.assertIn(row[2], VALID_ACTIONS)
        conn.close()

    def test_technical_interview_produces_canonical_tracker_status(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status) VALUES ('ti_job', 'Hooli', 'Dev', 'Remote', 'New')")
        conn.commit()
        conn.close()

        success = handle_status_update(query="ti_job", status="Technical Interview")
        self.assertTrue(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id = 'ti_job'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "Technical Interview")
        self.assertIn(row[0], VALID_STATUSES)
        self.assertIn(row[1], VALID_REVIEW_STATUSES)
        self.assertIn(row[2], VALID_ACTIONS)
        conn.close()

    def test_generic_interview_does_not_become_status_and_fails_safely(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status) VALUES ('int_job', 'Pied Piper', 'Dev', 'Remote', 'New')")
        conn.commit()
        conn.close()

        # Generic 'Interview' is not a canonical status and must fail safely without mutating
        success = handle_status_update(query="int_job", status="Interview")
        self.assertFalse(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM jobs WHERE job_id = 'int_job'")
        self.assertEqual(cursor.fetchone()[0], "New")
        conn.close()

    def test_recruiter_contact_handled_as_review_status_not_tracker_status(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status, review_status) VALUES ('rc_job', 'Dunder Mifflin', 'Dev', 'Remote', 'New', 'Imported')")
        conn.commit()
        conn.close()

        # Setting review_status = 'Recruiter Contact' succeeds and leaves tracker_status as 'New'
        success = handle_status_update(query="rc_job", review_status="Recruiter Contact")
        self.assertTrue(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status, review_status FROM jobs WHERE job_id = 'rc_job'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "New")
        self.assertEqual(row[1], "Recruiter Contact")
        self.assertIn(row[0], VALID_STATUSES)
        self.assertIn(row[1], VALID_REVIEW_STATUSES)

        # Attempting to supply 'Recruiter Contact' as a Tracker Status must fail closed
        fail_success = handle_status_update(query="rc_job", status="Recruiter Contact")
        self.assertFalse(fail_success)
        conn.close()

    def test_ready_to_apply_preserves_new_tracker_status(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status, review_status, action) VALUES ('rta_job', 'Stark Industries', 'Dev', 'Remote', 'New', 'Imported', 'Review')")
        conn.commit()
        conn.close()

        # 'Ready to Apply' sets review_status='Reviewed', action='Apply', and preserves status='New'
        success = handle_status_update(query="rta_job", review_status="Reviewed", action="Apply")
        self.assertTrue(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status, review_status, action, disposition FROM jobs WHERE job_id = 'rta_job'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "New")
        self.assertEqual(row[1], "Reviewed")
        self.assertEqual(row[2], "Apply")
        self.assertIn(row[0], VALID_STATUSES)
        self.assertIn(row[1], VALID_REVIEW_STATUSES)
        self.assertIn(row[2], VALID_ACTIONS)
        conn.close()

    def test_cannot_persist_tracker_status_outside_valid_statuses(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status) VALUES ('inv_s_job', 'Wayne Ent', 'Dev', 'Remote', 'New')")
        conn.commit()
        conn.close()

        success = handle_status_update(query="inv_s_job", status="NonExistentStatus")
        self.assertFalse(success)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tracker_status FROM jobs WHERE job_id = 'inv_s_job'")
        self.assertEqual(cursor.fetchone()[0], "New")
        conn.close()

    def test_cannot_persist_review_status_outside_valid_review_statuses(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status) VALUES ('inv_r_job', 'Wayne Ent', 'Dev', 'Remote', 'New')")
        conn.commit()
        conn.close()

        success = handle_status_update(query="inv_r_job", review_status="NonExistentReviewStatus")
        self.assertFalse(success)

    def test_cannot_persist_action_outside_valid_actions(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jobs (job_id, company, position, location, tracker_status) VALUES ('inv_a_job', 'Wayne Ent', 'Dev', 'Remote', 'New')")
        conn.commit()
        conn.close()

        success = handle_status_update(query="inv_a_job", action="NonExistentAction")
        self.assertFalse(success)

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
