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

import parse_jobs
from dedup_utils import canonical_job_key, normalize_string, locations_compatible, title_similarity


class TestJobIdDeterminism(unittest.TestCase):
    """Verify that MD5 job IDs are stable across identical inputs."""

    def _make_job_id(self, company, title, location, date_added="2026-01-01"):
        """Helper to generate job ID matching the implementation.

        date_added is included for every job (not just daily-digest rows) --
        see the parse_jobs.py fix for the collision this used to cause when a
        job reappeared more than 90 days after it was first seen."""
        return hashlib.md5(
            f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}|{date_added}"
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

    def test_different_date_produces_different_id(self):
        """Regression: a job re-listed after the reapply/merge windows lapse
        must not collide with the stale row's Job ID (previously only
        daily-digest rows folded date into the hash)."""
        id1 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote", "2026-01-01")
        id2 = self._make_job_id("Alivia Analytics", "Senior Backend Engineer", "Remote", "2026-06-01")
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
        """Duplicate detection is driven by the canonical (company/title/location)
        key, not by Job ID equality -- so it doesn't matter that Job IDs now
        include date_added. This models is_duplicate using that canonical key,
        matching parse_jobs.py's get_canonical_key."""
        from datetime import date

        existing_jobs = {
            ("6bdb241ddc24", "2026-03-01"): {
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

        def canonical(comp, pos, loc):
            return f"{comp.strip().lower()}|{pos.strip().lower()}|{loc.strip().lower()}"

        current_canonical = canonical(job["company"], job["title"], job["location"])

        # Test case 1: within 90 days (e.g. 2026-04-01 is 31 days after 2026-03-01)
        date_added_within = "2026-04-01"
        is_duplicate = False
        for ej in existing_jobs.values():
            if canonical(ej["Company"], ej["Position"], ej["Location"]) == current_canonical:
                existing_date = date.fromisoformat(ej["Date Added"])
                current_date = date.fromisoformat(date_added_within)
                if (current_date - existing_date).days <= 90:
                    is_duplicate = True

        self.assertTrue(is_duplicate)

        # Test case 2: after 90 days (e.g. 2026-06-29 is 120 days after 2026-03-01)
        date_added_after = "2026-06-29"
        is_duplicate = False
        for ej in existing_jobs.values():
            if canonical(ej["Company"], ej["Position"], ej["Location"]) == current_canonical:
                existing_date = date.fromisoformat(ej["Date Added"])
                current_date = date.fromisoformat(date_added_after)
                if (current_date - existing_date).days <= 90:
                    is_duplicate = True

        self.assertFalse(is_duplicate)

        # Not a duplicate, so it gets a fresh Job ID -- which, now that date_added
        # is always part of the hash, differs from the stale row's ID even though
        # company/title/location are identical.
        old_job_id = "6bdb241ddc24"
        new_job_id = hashlib.md5(
            f"{job['company'].strip().lower()}|{job['title'].strip().lower()}|{job['location'].strip().lower()}|{date_added_after}".encode('utf-8')
        ).hexdigest()[:12]
        self.assertNotEqual(old_job_id, new_job_id)
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
        
        if existing_match:
            from dedup_utils import merge_delimited_field
            existing_match["Provider"] = merge_delimited_field(
                existing_match.get("Provider", ""),
                new_provider
            )
            existing_match["Source PDF"] = merge_delimited_field(
                existing_match.get("Source PDF", ""),
                new_pdf
            )
            
        # They should be merged with the | delimiter
        self.assertEqual(existing_match["Provider"], "LinkedIn|Indeed")
        self.assertEqual(existing_match["Source PDF"], "alert1.pdf|alert2.pdf")
        self.assertEqual(existing_match["Notes"], "Original note")


class TestAggregatorPlaceholderGuard(unittest.TestCase):
    """Aggregator/digest placeholder "companies" (e.g. "Ladders-DailyDigest")
    must never participate in canonical-key matching -- parse_jobs.py's main
    loop skips the matching loop entirely when is_aggregator_placeholder()
    returns True for a job's company."""

    def test_known_aggregator_placeholders_are_flagged(self):
        for company in ["Ladders-DailyDigest", "Jobs.utah.gov-DailySummary", "ladders", "LinkedIn"]:
            self.assertTrue(parse_jobs.is_aggregator_placeholder(company), company)

    def test_real_company_names_are_not_flagged(self):
        for company in ["Acme Corp", "Alivia Analytics", "Citi"]:
            self.assertFalse(parse_jobs.is_aggregator_placeholder(company), company)

    def test_two_aggregator_postings_would_not_be_treated_as_the_same_job(self):
        """Two unrelated postings surfaced through the same digest placeholder
        "company" must not look like the same job just because they share that
        placeholder name -- documents why the main loop gates matching on
        `not is_aggregator_placeholder(...)` rather than relying on the
        canonical key alone (which would otherwise treat them as duplicates
        whenever the placeholder title/location also happened to coincide)."""
        company = "Ladders-DailyDigest"
        self.assertTrue(parse_jobs.is_aggregator_placeholder(company))
        key_a = canonical_job_key(company, "Software Engineer", "Remote")
        key_b = canonical_job_key(company, "Software Engineer", "Remote")
        # Same canonical key -- without the is_aggregator_placeholder gate this
        # would incorrectly merge two distinct digest-sourced postings.
        self.assertEqual(key_a, key_b)


class TestFuzzyTitleMatchCondition(unittest.TestCase):
    """The main PDF-scan loop in parse_jobs.py never auto-merges on title
    similarity alone -- two different requisitions ("Senior Software
    Engineer" vs "...II") can legitimately share a title, so only an exact
    canonical-key match reuses an existing Job ID. A fuzzy title match (same
    company, compatible location, title_similarity >= 0.7) instead adds a
    "possible duplicate ... needs manual review" note to the new row and
    still creates it as a separate record. This exercises that exact
    flagging condition using the real dedup_utils helpers parse_jobs.py
    calls."""

    def _is_fuzzy_match(self, ej_company, ej_title, ej_location, new_company, new_title, new_location):
        ej_canonical = canonical_job_key(ej_company, ej_title, ej_location)
        current_canonical = canonical_job_key(new_company, new_title, new_location)
        return (
            ej_canonical != current_canonical
            and normalize_string(ej_company) == normalize_string(new_company)
            and locations_compatible(ej_location, new_location)
            and title_similarity(ej_title, new_title) >= 0.7
        )

    def test_minor_title_correction_is_flagged_for_review(self):
        self.assertTrue(self._is_fuzzy_match(
            "Acme Corp", "Senior Software Engineer", "Remote",
            "Acme Corp", "Senior Software Engineer II", "Remote",
        ))

    def test_unrelated_title_at_same_company_is_not_flagged(self):
        self.assertFalse(self._is_fuzzy_match(
            "Acme Corp", "Senior Software Engineer", "Remote",
            "Acme Corp", "Marketing Manager", "Remote",
        ))

    def test_same_title_different_company_is_not_flagged(self):
        self.assertFalse(self._is_fuzzy_match(
            "Acme Corp", "Senior Software Engineer", "Remote",
            "Globex Inc", "Senior Software Engineer", "Remote",
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
