import unittest
from parse_jobs import parse_manual_job_block

class TestParseManualJobBlock(unittest.TestCase):
    def test_parse_manual_job_block_full(self):
        sample_text = """Add: Company: 66degrees
Position: Application Development Architect
Recruiter: Ashley Martin — Talent Acquisition Partner / Team Lead
Employment: Full-time
Location: Remote / North America
Status: Recruiter Screen Completed — Technical Interview Pending
Recruiter Interview: Completed Sep. 4, 2026 — went well
Next Step: Technical interview; final round with department VPs
Compensation: Targeted $150,000 base with recruiter; annual bonus also available, percentage TBD
Travel: Approximately 2–3 times/year may be required
Role: Hands-on Architect + Team Lead; solution design, technical roadmaps, architectural decisions, mentoring/code reviews, client/stakeholder collaboration and delivery.
Primary Stack: Java/Spring Boot + C#/.NET; GCP; containers; microservices; event-driven architecture; REST APIs; relational/NoSQL; React; CI/CD; Terraform/Helm.
AI: Agentic architectures, APIs, state/memory, agent observability, error handling, human-in-the-loop governance.
Company: AI/cloud/data transformation consultancy formed through combination/acquisition of multiple firms.
Benefits: Medical, dental, vision, life/AD&D, short-/long-term disability; benefits eligibility begins first day of full-time employment.
Fit: High / Priority opportunity
Primary Prep Gap: GCP depth; refresh Helm, Istio/service mesh and agentic-AI architecture.
Notes: Ashley indicated awareness of a role needing the Java + C#/.NET combination; company expects architect to remain hands-on. Degree listed in JD but recruiter has reviewed resume and advanced candidacy."""

        parsed = parse_manual_job_block(sample_text)
        self.assertEqual(parsed["company"], "66degrees")
        self.assertEqual(parsed["position"], "Application Development Architect")
        self.assertEqual(parsed["recruiter"], "Ashley Martin — Talent Acquisition Partner / Team Lead")
        self.assertEqual(parsed["location"], "Remote / North America")
        self.assertEqual(parsed["status"], "Technical Interview")
        self.assertEqual(parsed["fit_score"], 95)
        self.assertEqual(parsed["recommendation"], "★★★★★ Apply Now")
        self.assertIn("Targeted $150,000 base", parsed["notes"])
        self.assertIn("Primary Stack: Java/Spring Boot", parsed["notes"])

    def test_parse_manual_job_block_minimal(self):
        text = """Company: Initech
Position: Senior Developer
Status: Phone Screen
Location: Salt Lake City, UT"""
        parsed = parse_manual_job_block(text)
        self.assertEqual(parsed["company"], "Initech")
        self.assertEqual(parsed["position"], "Senior Developer")
        self.assertEqual(parsed["status"], "Phone Screen")
        self.assertEqual(parsed["location"], "Salt Lake City, UT")

if __name__ == "__main__":
    unittest.main()
