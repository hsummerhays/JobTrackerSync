import os
import sys
import csv
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import clean_existing_tracker

EXPECTED_HEADERS = [
    "Job ID", "Review Status", "Job Type", "Company", "Position", "Location", "URL", "Provider",
    "Source PDF", "Confidence", "Fit Score", "Priority", "Company Type",
    "Recommendation", "Tracker Status", "Disposition", "Action", "Existing Company",
    "Age (days)", "Reason", "Matched Skills", "Missing Skills", "Date Added", "Last Seen", "Notes", "Recruiter", "Hiring Manager"
]


class CleanExistingTrackerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.tracker_path = "master_tracker.csv"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _write_tracker(self, rows):
        with open(self.tracker_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=EXPECTED_HEADERS, restval="")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _read_tracker(self):
        with open(self.tracker_path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))


class TestCleanExistingTrackerNoop(CleanExistingTrackerTestBase):

    def test_missing_file_is_a_noop(self):
        self.assertIsNone(clean_existing_tracker(self.tracker_path))
        self.assertFalse(os.path.exists(self.tracker_path))

    def test_empty_file_no_header_is_a_noop(self):
        open(self.tracker_path, "w").close()
        clean_existing_tracker(self.tracker_path)
        # File is untouched -- still empty, no crash.
        self.assertEqual(os.path.getsize(self.tracker_path), 0)


class TestCleanExistingTrackerInvalidCompanies(CleanExistingTrackerTestBase):

    def test_invalid_and_placeholder_companies_are_dropped(self):
        rows = [
            {"Company": "Acme Corp", "Position": "Software Engineer", "Location": "Remote"},
            {"Company": "Software Engineer", "Position": "Backend Role", "Location": "Remote"},  # generic role
            {"Company": "*BadCo", "Position": "Backend Role", "Location": "Remote"},  # starts with punctuation
            {"Company": "someone@gmail.com", "Position": "Backend Role", "Location": "Remote"},  # gmail
            {"Company": "Acme Corp", "Position": "Please create a new pipeline", "Location": "Remote"},  # "create" in position
            {"Company": "(Remote)", "Position": "Backend Role", "Location": "Remote"},  # exact placeholder
            {"Company": "https://example.com/job", "Position": "Backend Role", "Location": "Remote"},  # url-looking
            {"Company": "Zeta Corp", "Position": "This could be a great fit for your background", "Location": "Remote"},  # conversational
        ]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()
        companies = {r["Company"] for r in result}
        self.assertEqual(companies, {"Acme Corp"})
        self.assertEqual(len(result), 1)

    def test_ui_label_suffix_is_stripped_from_company_name(self):
        rows = [{"Company": "Acme Corp.View Details", "Position": "Software Engineer", "Location": "Remote"}]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["Company"], "Acme Corp.")


class TestCleanExistingTrackerMigration(CleanExistingTrackerTestBase):

    def test_legacy_status_values_are_normalized(self):
        rows = [
            {"Company": "Acme Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "Recruiter"},
            {"Company": "Beta Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "Interview"},
            {"Company": "Gamma Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "Technical"},
            {"Company": "Delta Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "Skip"},
            {"Company": "Epsilon Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "SomethingWeird"},
        ]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = {r["Company"]: r["Tracker Status"] for r in self._read_tracker()}
        self.assertEqual(result["Acme Corp"], "Recruiter Submitted")
        self.assertEqual(result["Beta Corp"], "Phone Screen")
        self.assertEqual(result["Gamma Corp"], "Technical Interview")
        self.assertEqual(result["Delta Corp"], "Cancelled")
        self.assertEqual(result["Epsilon Corp"], "New")

    def test_job_id_generated_when_missing_and_preserved_when_present(self):
        rows = [
            {"Company": "Acme Corp", "Position": "Engineer", "Location": "Remote", "Job ID": ""},
            {"Company": "Beta Corp", "Position": "Engineer", "Location": "Remote", "Job ID": "custom-id-123"},
        ]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = {r["Company"]: r["Job ID"] for r in self._read_tracker()}
        self.assertEqual(len(result["Acme Corp"]), 32)
        self.assertEqual(result["Beta Corp"], "custom-id-123")

    def test_company_type_detection(self):
        rows = [
            {"Company": "Apex Staffing Group", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Bright Solutions", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Lockheed Systems", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Summit Medical", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Capital Trust", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Google", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Acme Corp", "Position": "Engineer", "Location": "Remote"},
        ]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = {r["Company"]: r["Company Type"] for r in self._read_tracker()}
        self.assertEqual(result["Apex Staffing Group"], "Recruiting Firm")
        self.assertEqual(result["Bright Solutions"], "Consulting")
        self.assertEqual(result["Lockheed Systems"], "Defense")
        self.assertEqual(result["Summit Medical"], "Healthcare")
        self.assertEqual(result["Capital Trust"], "Financial")
        self.assertEqual(result["Google"], "Enterprise")
        self.assertEqual(result["Acme Corp"], "Small / Medium")


class TestCleanExistingTrackerScoring(CleanExistingTrackerTestBase):

    def test_high_score_produces_apply_now_recommendation(self):
        rows = [{
            "Company": "Acme Corp", "Position": "Senior Backend Engineer (C#)",
            "Location": "Remote", "Confidence": "\U0001F7E2 High", "Tracker Status": "New",
            # Notes carries the boilerplate evaluate_job() always appends for a
            # real (non-FAANG) posting -- any row that actually went through
            # scoring once has this, and it's what keeps the CSV's approximated
            # context (there's no persisted posting text to re-evaluate against)
            # long enough for evaluate_job()'s confidence heuristic to trust it.
            "Notes": "Small-to-mid-sized (preferred)",
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        self.assertEqual(result["Recommendation"], "★★★★★ Apply Now")
        self.assertEqual(result["Action"], "Apply")

    def test_onsite_restriction_reduces_score_and_adds_note(self):
        rows = [{
            "Company": "Acme Corp", "Position": "Senior Backend Engineer, onsite only",
            "Location": "Salt Lake City, UT", "Confidence": "\U0001F7E2 High", "Tracker Status": "New",
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        self.assertIn("Local/Onsite restriction detected", result["Notes"])

    def test_operations_job_type_gets_score_penalty(self):
        rows = [{
            "Company": "Acme Corp", "Position": "Warehouse Operations Manager",
            "Location": "Remote", "Confidence": "\U0001F7E2 High", "Tracker Status": "New",
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        self.assertEqual(result["Job Type"], "Operations")

    def test_out_of_state_job_never_recommended_regardless_of_stale_score(self):
        """Regression: a prior duplicate scoring implementation in
        clean_existing_tracker had no equivalent of evaluate_job()'s Rule 6
        relocation gate, so an out-of-state row that had been (mis-)scored as
        Strong/P2 before that gate existed would keep coming back on every
        sync/rescore instead of being corrected to Skip."""
        rows = [{
            "Company": "Charles Schwab", "Position": "Senior Backend Engineer (.NET)",
            "Location": "Southlake, TX (Hybrid)", "Confidence": "\U0001F7E2 High", "Tracker Status": "New",
            "Fit Score": "90", "Priority": "P2 - Apply this week",
            "Recommendation": "★★★★☆ Strong",
            "Reason": "Utah + .NET + Small company", "Matched Skills": ".NET",
            "Notes": "Small-to-mid-sized (preferred)",
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        self.assertEqual(result["Recommendation"], "★☆☆☆☆ Skip")
        self.assertEqual(result["Priority"], "P4 – Ignore")
        self.assertNotIn("Utah", result["Reason"])

    def test_incomplete_listing_capped_at_maybe_regardless_of_stale_score(self):
        """Regression: the same duplicate scoring implementation had no
        equivalent of evaluate_job()'s incomplete-listing cap, so a
        DailySummary/digest posting that had been (mis-)scored as
        Strong/P2 could keep regenerating that score on every sync instead of
        being capped at Maybe/P3."""
        rows = [{
            "Company": "Jobs.utah.gov-DailySummary", "Position": "Senior Software Engineer- Full Stack- Java/Angular",
            "Location": "Salt Lake City, UT", "Provider": "jobs.utah.gov", "Confidence": "\U0001F7E2 High",
            "Tracker Status": "New", "Fit Score": "80", "Priority": "P2 - Apply this week",
            "Recommendation": "★★★★☆ Strong", "Reason": "Utah + Java + Small company",
            "Notes": "Employer not included in daily summary PDF",
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        self.assertEqual(result["Recommendation"], "★★★☆☆ Maybe")
        self.assertEqual(result["Priority"], "P3 – Investigate")

    def test_digest_priority_decay_downgrades_aged_recommendations(self):
        aged_date = (date.today() - timedelta(days=10)).isoformat()
        rows = [{
            "Company": "DailyDigest Alert", "Position": "Senior Backend Engineer (C#)",
            "Location": "Remote", "Confidence": "\U0001F7E2 High", "Tracker Status": "New",
            "Date Added": aged_date,
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        self.assertEqual(result["Recommendation"], "★★☆☆☆ Low")


class TestCleanExistingTrackerActionAndExistingCompany(CleanExistingTrackerTestBase):

    def test_non_new_status_maps_to_already_applied_or_ignore(self):
        # Omit the "Action" column entirely so row.get("Action", <computed default>)
        # actually falls through to the computed default instead of an empty string.
        with open(self.tracker_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Company", "Position", "Location", "Tracker Status"])
            writer.writeheader()
            writer.writerow({"Company": "Acme Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "Applied"})
            writer.writerow({"Company": "Beta Corp", "Position": "Engineer", "Location": "Remote", "Tracker Status": "Rejected"})
        clean_existing_tracker(self.tracker_path)
        result = {r["Company"]: r["Action"] for r in self._read_tracker()}
        self.assertEqual(result["Acme Corp"], "Already Applied")
        self.assertEqual(result["Beta Corp"], "Ignore")

    def test_stale_contact_recruiter_action_corrected_for_non_recruiting_company(self):
        rows = [{
            "Company": "Acme Corp", "Position": "Senior Backend Engineer (C#)",
            "Location": "Remote", "Confidence": "\U0001F7E2 High", "Tracker Status": "Applied",
            "Action": "Contact Recruiter",
            "Notes": "Small-to-mid-sized (preferred)",
        }]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()[0]
        # comp_type is Small/Medium (not Recruiting Firm), and the recomputed
        # recommendation is strong enough that the stale "Contact Recruiter"
        # action gets corrected to "Apply", not left as a recruiter action.
        self.assertEqual(result["Action"], "Apply")

    def test_existing_company_known_list_and_duplicate_counts(self):
        rows = [
            {"Company": "Weave", "Position": "Engineer", "Location": "Remote"},
            {"Company": "Acme Corp", "Position": "Engineer A", "Location": "Remote"},
            {"Company": "Acme Corp", "Position": "Engineer B", "Location": "Remote", "Existing Company": "Yes"},
        ]
        self._write_tracker(rows)
        clean_existing_tracker(self.tracker_path)
        result = self._read_tracker()
        weave = next(r for r in result if r["Company"] == "Weave")
        self.assertEqual(weave["Existing Company"], "Yes")
        # Duplicate companies only carry "Yes" forward for rows that already
        # had an explicit "Yes" -- a bare duplicate with no prior value is "No".
        engineer_a = next(r for r in result if r["Position"] == "Engineer A")
        engineer_b = next(r for r in result if r["Position"] == "Engineer B")
        self.assertEqual(engineer_a["Existing Company"], "No")
        self.assertEqual(engineer_b["Existing Company"], "Yes")


class TestCleanExistingTrackerDuplicateOrphanCleanup(CleanExistingTrackerTestBase):
    """2026-08-13 end-to-end regression: clean_existing_tracker() dedupes its
    row list in memory *before* calling save_to_sqlite(), so a losing
    duplicate whose jobs.db row predates the merge never reaches the ordinary
    upsert loop and its delete-the-loser branch never fires. The row then
    sits orphaned in jobs.db, gets restored into the CSV's row list by the
    "missing from CSV" recovery step on the very next run, and is merged
    away again in memory each time -- so it never becomes visibly wrong, but
    it's never actually cleaned out of jobs.db either. This exercises the
    full pipeline (not save_to_sqlite() directly) so the CSV-side dedup pass
    and the DB cleanup it now triggers are both covered together."""

    def _job_ids_in_db(self):
        conn = sqlite3.connect("jobs.db")
        ids = {r[0] for r in conn.execute("SELECT job_id FROM jobs").fetchall()}
        conn.close()
        return ids

    def test_duplicate_orphan_is_deleted_from_db_and_not_resurrected(self):
        company, position, location = "Podium", "Backend Engineer", "Lehi, UT"
        date_added = "2026-06-01"

        # Two rows for the same real job, each already living in jobs.db
        # under its own legacy fingerprint -- as if scanned twice before a
        # canonical fingerprint existed to catch the collision.
        import parse_jobs as pj
        pj.save_to_sqlite("jobs.db", [{
            "Job ID": "owner1", "Company": company, "Position": position, "Location": location,
            "Date Added": date_added, "Tracker Status": "Applied", "Fingerprint": "legacy-fp-owner",
        }])
        pj.save_to_sqlite("jobs.db", [{
            "Job ID": "loser1", "Company": company, "Position": position, "Location": location,
            "Date Added": date_added, "Tracker Status": "New", "Fingerprint": "legacy-fp-loser",
        }])
        self.assertEqual(self._job_ids_in_db(), {"owner1", "loser1"})

        rows = [
            {"Job ID": "owner1", "Company": company, "Position": position, "Location": location,
             "Date Added": date_added, "Tracker Status": "Applied"},
            {"Job ID": "loser1", "Company": company, "Position": position, "Location": location,
             "Date Added": date_added, "Tracker Status": "New"},
        ]
        self._write_tracker(rows)

        clean_existing_tracker(self.tracker_path)

        csv_ids = {r["Job ID"] for r in self._read_tracker()}
        self.assertEqual(csv_ids, {"owner1"})
        self.assertEqual(
            self._job_ids_in_db(), {"owner1"},
            "loser1's stale jobs.db row must be deleted by the merge, not left orphaned",
        )

        # Run again -- the orphan must not come back. Before the fix, this
        # step alone would not have surfaced anything wrong (the CSV-side
        # dedup pass re-merges the restored loser away every time), which is
        # exactly why the bug was invisible without checking jobs.db directly.
        clean_existing_tracker(self.tracker_path)

        self.assertEqual({r["Job ID"] for r in self._read_tracker()}, {"owner1"})
        self.assertEqual(self._job_ids_in_db(), {"owner1"})

    def test_manual_score_survives_csv_side_dedup_merge(self):
        company, position, location = "Zenith Robotics", "Firmware Engineer", "Draper, UT"
        date_added = "2026-06-10"

        import parse_jobs as pj
        pj.save_to_sqlite("jobs.db", [{
            "Job ID": "owner1", "Company": company, "Position": position, "Location": location,
            "Date Added": date_added, "Tracker Status": "New", "Fingerprint": "legacy-fp-a",
        }])
        pj.save_to_sqlite("jobs.db", [{
            "Job ID": "loser1", "Company": company, "Position": position, "Location": location,
            "Date Added": date_added, "Tracker Status": "New", "Fingerprint": "legacy-fp-b",
            "Fit Score": 97, "Priority": "P1 – Apply today", "Recommendation": "★★★★★ Apply Now",
            "Score Source": "manual",
        }])

        rows = [
            {"Job ID": "owner1", "Company": company, "Position": position, "Location": location,
             "Date Added": date_added, "Tracker Status": "New"},
            {"Job ID": "loser1", "Company": company, "Position": position, "Location": location,
             "Date Added": date_added, "Tracker Status": "New"},
        ]
        self._write_tracker(rows)

        clean_existing_tracker(self.tracker_path)

        result = self._read_tracker()
        self.assertEqual(len(result), 1)
        survivor = result[0]
        self.assertEqual(survivor["Job ID"], "owner1")
        self.assertEqual(survivor["Score Source"], "manual")
        self.assertEqual(survivor["Fit Score"], "97")

        conn = sqlite3.connect("jobs.db")
        db_row = conn.execute(
            "SELECT fit_score, score_source FROM jobs WHERE job_id = 'owner1'"
        ).fetchone()
        conn.close()
        self.assertEqual(db_row, (97, "manual"))


class TestCleanExistingTrackerExceptionHandling(CleanExistingTrackerTestBase):

    def test_exception_during_processing_is_caught_and_reported(self):
        rows = [{"Company": "Acme Corp", "Position": "Engineer", "Location": "Remote"}]
        self._write_tracker(rows)
        with patch("parse_jobs.write_tracker_csv_atomic", side_effect=RuntimeError("disk full")):
            with patch("parse_jobs.console.print") as mock_print:
                clean_existing_tracker(self.tracker_path)
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Failed to clean/migrate existing tracker" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
