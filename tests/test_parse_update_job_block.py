import unittest
from parse_jobs import parse_update_job_block

class TestParseUpdateJobBlock(unittest.TestCase):
    def test_pipe_delimited_ready_to_apply(self):
        text = "Update: AlignRx LLC | Software Developer II | Remote | $86,400/year | Full-time | Resume tailored 2026-10-03 | Ready to Apply"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "AlignRx LLC")
        self.assertEqual(parsed["company"], "AlignRx LLC")
        self.assertEqual(parsed["position"], "Software Developer II")
        self.assertEqual(parsed["location"], "Remote")
        self.assertEqual(parsed["review_status"], "Reviewed")
        self.assertEqual(parsed["action"], "Apply")
        self.assertIsNone(parsed["status"])
        self.assertTrue(parsed["append_notes"])
        self.assertIn("Comp: $86,400/year", parsed["notes"])
        self.assertIn("Employment: Full-Time", parsed["notes"])
        self.assertIn("Resume: Tailored 2026-10-03", parsed["notes"])
        self.assertIn("Status: Ready to Apply", parsed["notes"])

    def test_pipe_delimited_applied_status(self):
        text = "CapTech Consulting | Applied | Application submitted via SmartRecruiters | Resume: Tailored"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "CapTech Consulting")
        self.assertEqual(parsed["status"], "Applied")
        self.assertIsNone(parsed["review_status"])
        self.assertIsNone(parsed["action"])
        self.assertIn("Application submitted via SmartRecruiters", parsed["notes"])
        self.assertIn("Resume: Tailored", parsed["notes"])

    def test_pipe_delimited_hex_job_id(self):
        text = "11078ec9e30742868762cbfb67bc99bb | Rejected | Automated rejection email"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "11078ec9e30742868762cbfb67bc99bb")
        self.assertEqual(parsed["job_id"], "11078ec9e30742868762cbfb67bc99bb")
        self.assertEqual(parsed["status"], "Rejected")
        self.assertIsNone(parsed["review_status"])
        self.assertIsNone(parsed["action"])
        self.assertIn("Automated rejection email", parsed["notes"])

    def test_multiline_key_value_block(self):
        text = """Update: AlignRx LLC
Position: Software Developer II
Location: Remote
Comp: $86,400/year
Employment: Full-time
Resume: Tailored 2026-10-03
Status: Ready to Apply"""
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "AlignRx LLC")
        self.assertEqual(parsed["company"], "AlignRx LLC")
        self.assertEqual(parsed["position"], "Software Developer II")
        self.assertEqual(parsed["location"], "Remote")
        self.assertEqual(parsed["review_status"], "Reviewed")
        self.assertEqual(parsed["action"], "Apply")
        self.assertIn("Comp: $86,400/year", parsed["notes"])
        self.assertIn("Employment: Full-time", parsed["notes"])
        self.assertIn("Resume: Tailored 2026-10-03", parsed["notes"])
        self.assertIn("Status: Ready to Apply", parsed["notes"])

    def test_company_position_dash_in_first_segment(self):
        text = "Initech — Senior Software Engineer | Remote | $140,000/yr | Status: Technical Interview"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "Initech")
        self.assertEqual(parsed["company"], "Initech")
        self.assertEqual(parsed["position"], "Senior Software Engineer")
        self.assertEqual(parsed["location"], "Remote")
        self.assertEqual(parsed["status"], "Technical Interview")
        self.assertIn("Comp: $140,000/yr", parsed["notes"])

    def test_phone_screen_produces_canonical_status(self):
        text = "Globex | Phone Screen | Notes: Screening with recruiter"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "Globex")
        self.assertEqual(parsed["status"], "Phone Screen")

    def test_technical_interview_produces_canonical_status(self):
        text = "Globex | Technical Interview | 2-hour coding session"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "Globex")
        self.assertEqual(parsed["status"], "Technical Interview")

    def test_generic_interview_does_not_set_tracker_status_in_segment(self):
        text = "Globex | Interview | Some interview note"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["query"], "Globex")
        # Generic "Interview" is not a canonical status; it must not become a Tracker Status
        self.assertIsNone(parsed["status"])
        self.assertIn("Interview", parsed["notes"])

    def test_recruiter_contact_handled_as_review_status_not_tracker_status(self):
        # In pipe segment
        text1 = "Globex | Recruiter Contact | Recruiter reached out on LinkedIn"
        parsed1 = parse_update_job_block(text1)
        self.assertEqual(parsed1["review_status"], "Recruiter Contact")
        self.assertIsNone(parsed1["status"])

        # In KV format
        text2 = "Globex\nStatus: Recruiter Contact"
        parsed2 = parse_update_job_block(text2)
        self.assertEqual(parsed2["review_status"], "Recruiter Contact")
        self.assertIsNone(parsed2["status"])

    def test_ready_to_apply_preserves_new_and_sets_reviewed_workflow(self):
        text = "Globex | Ready to Apply"
        parsed = parse_update_job_block(text)
        self.assertEqual(parsed["review_status"], "Reviewed")
        self.assertEqual(parsed["action"], "Apply")
        self.assertIsNone(parsed["status"])


if __name__ == "__main__":
    unittest.main()
