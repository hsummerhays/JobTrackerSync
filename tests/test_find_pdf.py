import os
import sys
import sqlite3
import tempfile
import unittest
import pathlib

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from find_pdf import find_matches, path_to_file_uri

class TestFindPdf(unittest.TestCase):

    def test_find_matches_nonexistent_db(self):
        # Should return empty dictionary if db doesn't exist
        results = find_matches("nonexistent_db_file.db", "test")
        self.assertEqual(results, {})

    def test_find_matches_with_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_jobs.db")
            
            # Setup temporary test database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create a mock jobs table
            cursor.execute("""
                CREATE TABLE jobs (
                    job_id TEXT,
                    company TEXT,
                    position TEXT,
                    source_pdf TEXT
                )
            """)
            
            # Insert some dummy records
            cursor.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", (
                "id123", "Franki Corp", "Software Engineer", "C:\\postings\\Franki_hiring.pdf"
            ))
            cursor.execute("INSERT INTO jobs VALUES (?, ?, ?, ?)", (
                "id456", "Other Corp", "Backend Developer", "C:\\postings\\other.pdf"
            ))
            
            # Create a mock processed_files table
            cursor.execute("""
                CREATE TABLE processed_files (
                    file_path TEXT,
                    status TEXT
                )
            """)
            cursor.execute("INSERT INTO processed_files VALUES (?, ?)", (
                "C:\\postings\\Franki_hiring.pdf", "success"
            ))
            
            conn.commit()
            conn.close()
            
            # 1. Search for "Franki" - should find matches in both tables
            results = find_matches(db_path, "Franki")
            
            self.assertIn("jobs", results)
            self.assertEqual(len(results["jobs"]), 1)
            self.assertEqual(results["jobs"][0]["company"], "Franki Corp")
            self.assertEqual(results["jobs"][0]["job_id"], "id123")
            # Check URI generation for source_pdf
            self.assertIn("source_pdf_uri", results["jobs"][0])
            self.assertEqual(
                results["jobs"][0]["source_pdf_uri"],
                "file:///C:/postings/Franki_hiring.pdf"
            )
            
            self.assertIn("processed_files", results)
            self.assertEqual(len(results["processed_files"]), 1)
            self.assertEqual(results["processed_files"][0]["status"], "success")
            self.assertIn("file_path_uri", results["processed_files"][0])
            
            # 2. Search for a term that does not exist
            no_results = find_matches(db_path, "NonexistentTerm")
            self.assertEqual(no_results, {})

    def test_windows_path_to_file_uri(self):
        self.assertEqual(
            path_to_file_uri(r"C:\postings\Franki hiring.pdf"),
            "file:///C:/postings/Franki%20hiring.pdf"
        )

    def test_posix_path_to_file_uri(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = pathlib.Path(tmp_dir).resolve() / "posting.pdf"
            self.assertEqual(
                path_to_file_uri(str(test_file)),
                test_file.as_uri()
            )

if __name__ == '__main__':
    unittest.main()
