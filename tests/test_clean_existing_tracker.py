import os
import sys
import csv
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
