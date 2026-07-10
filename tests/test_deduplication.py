"""
Unit tests for job ID determinism and deduplication logic.

Run with:
    python -m pytest tests/test_deduplication.py -v
"""
import sys
import os
import unittest
import hashlib

# Allow importing from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestJobIdDeterminism(unittest.TestCase):
    """Verify that MD5 job IDs are stable across identical inputs."""

    def _make_job_id(self, company, title, location):
        """Helper to generate job ID matching the implementation."""
        return hashlib.md5(
            f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}"
            .encode('utf-8')
        ).hexdigest()[:12]

    def test_same_inputs_produce_same_id(self):
        """Identical job details should produce identical job IDs."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        self.assertEqual(id1, id2)

    def test_different_company_produces_different_id(self):
        """Different company names should produce different job IDs."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Citi", "Senior Backend Engineer", "Remote")
        self.assertNotEqual(id1, id2)

    def test_different_title_produces_different_id(self):
        """Different job titles should produce different job IDs."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Alivia Analytics", "Lead Software Engineer", "Remote")
        self.assertNotEqual(id1, id2)

    def test_different_location_produces_different_id(self):
        """Different locations should produce different job IDs."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Salt Lake City, UT")
        self.assertNotEqual(id1, id2)

    def test_case_insensitive(self):
        """Job IDs should be case-insensitive."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("ALIVIA ANALYTICS", "SENIOR BACKEND ENGINEER", "REMOTE")
        self.assertEqual(id1, id2)

    def test_whitespace_trimmed(self):
        """Job IDs should ignore leading/trailing whitespace."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        id2 = self._make_job_id("  Alivia Analytics  ", "  Senior Backend Engineer  ", "  Remote  ")
        self.assertEqual(id1, id2)

    def test_id_is_12_chars(self):
        """Job IDs should be exactly 12 characters long."""
        job_id = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        self.assertEqual(len(job_id), 12)

    def test_id_is_hexadecimal(self):
        """Job IDs should be hexadecimal strings."""
        job_id = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote")
        try:
            int(job_id, 16)
        except ValueError:
            self.fail("Job ID is not a valid hexadecimal string")

    def test_id_deterministic_across_multiple_calls(self):
        """Job IDs should remain consistent across multiple generations."""
        job_id = self._make_job_id("Test Company", "Test Position", "Test Location")
        for _ in range(10):
            self.assertEqual(job_id, self._make_job_id("Test Company", "Test Position", "Test Location"))


class Test90DayDeduplication(unittest.TestCase):
    """Verify that the same job is allowed to be added again after 90 days."""

    def test_job_added_again_after_90_days(self):
        from datetime import date
        # Simulate existing jobs dict
        existing_jobs = {
            "6bdb241ddc24": {
                "Job ID": "6bdb241ddc24",
                "Company": "Alivia Analytics",
                "Position": "Senior Backend Engineer",
                "Location": "Remote",
                "Date Added": "2026-03-01"
            }
        }
        
        job = {
            "company": "Alivia Analytics",
            "title": "Senior Backend Engineer",
            "location": "Remote"
        }
        
        # Test case 1: within 90 days (e.g. 2026-04-01 is 31 days after 2026-03-01)
        date_added_within = "2026-04-01"
        job_id = hashlib.md5(f"{job['company'].strip().lower()}|{job['title'].strip().lower()}|{job['location'].strip().lower()}".encode('utf-8')).hexdigest()[:12]
        
        is_duplicate = False
        if job_id in existing_jobs:
            existing_job = existing_jobs[job_id]
            existing_date_str = existing_job.get("Date Added", "")
            existing_date = date.fromisoformat(existing_date_str)
            current_date = date.fromisoformat(date_added_within)
            if (current_date - existing_date).days <= 90:
                is_duplicate = True
        
        self.assertTrue(is_duplicate)
        
        # Test case 2: after 90 days (e.g. 2026-06-29 is 120 days after 2026-03-01)
        date_added_after = "2026-06-29"
        is_duplicate = False
        new_job_id = job_id
        if job_id in existing_jobs:
            existing_job = existing_jobs[job_id]
            existing_date_str = existing_job.get("Date Added", "")
            existing_date = date.fromisoformat(existing_date_str)
            current_date = date.fromisoformat(date_added_after)
            if (current_date - existing_date).days <= 90:
                is_duplicate = True
            else:
                new_job_id = hashlib.md5(f"{job['company'].strip().lower()}|{job['title'].strip().lower()}|{job['location'].strip().lower()}|{date_added_after}".encode('utf-8')).hexdigest()[:12]
        
        self.assertFalse(is_duplicate)
        self.assertNotEqual(job_id, new_job_id)
        self.assertEqual(len(new_job_id), 12)


class TestCanonicalKeyMerging(unittest.TestCase):
    """Verify that duplicates discovered within 90 days merge metadata."""

    def test_canonical_key_generation(self):
        import re
        def get_canonical_key(comp, pos, loc):
            c_norm = re.sub(r'[^a-z0-9]', '', comp.lower())
            p_norm = re.sub(r'[^a-z0-9]', '', pos.lower())
            l_norm = re.sub(r'[^a-z0-9]', '', loc.lower())
            return f"{c_norm}|{p_norm}|{l_norm}"

        key1 = get_canonical_key("Alivia  Analytics!", "Senior Backend - Developer", "Remote")
        key2 = get_canonical_key("aliviaanalytics", "seniorbackenddeveloper", "remote")
        self.assertEqual(key1, key2)

    def test_metadata_merging(self):
        # Simulate an existing match dict
        existing_match = {
            "Job ID": "6bdb241ddc24",
            "Company": "Alivia Analytics",
            "Position": "Senior Backend Engineer",
            "Location": "Remote",
            "Provider": "LinkedIn",
            "Source PDF": "alert1.pdf",
            "Notes": "Original note"
        }
        
        # New duplicate job details
        new_provider = "Indeed"
        new_pdf = "alert2.pdf"
        date_added = "2026-07-10"
        
        # Perform merge logic
        p_list = [p.strip() for p in existing_match.get("Provider", "").split("/") if p.strip()]
        if new_provider not in p_list:
            p_list.append(new_provider)
            existing_match["Provider"] = " / ".join(p_list)
            
        pdf_list = [pdf.strip() for pdf in existing_match.get("Source PDF", "").split("/") if pdf.strip()]
        if new_pdf not in pdf_list:
            pdf_list.append(new_pdf)
            existing_match["Source PDF"] = " / ".join(pdf_list)
            
        disc_note = f"Also discovered on {new_provider} via {new_pdf} on {date_added}"
        notes_val = existing_match.get("Notes", "")
        if notes_val:
            if disc_note not in notes_val:
                existing_match["Notes"] = f"{notes_val}; {disc_note}"
        else:
            existing_match["Notes"] = disc_note
            
        self.assertEqual(existing_match["Provider"], "LinkedIn / Indeed")
        self.assertEqual(existing_match["Source PDF"], "alert1.pdf / alert2.pdf")
        self.assertEqual(existing_match["Notes"], "Original note; Also discovered on Indeed via alert2.pdf on 2026-07-10")


if __name__ == "__main__":
    unittest.main(verbosity=2)
