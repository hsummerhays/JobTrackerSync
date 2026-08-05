import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse_jobs import parse_job_cards_from_text


class TestLaddersFormatC(unittest.TestCase):
    """Format C: 'Remote Jobs for You:' pipe-delimited single-line listings."""

    def test_three_part_line_title_location_company(self):
        text = (
            "Remote Jobs for You:\n"
            "Senior Backend Engineer | Remote | Acme Corp | $150K - $190K\n"
            "Do these jobs match what you're looking for?\n"
        )
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Backend Engineer")
        self.assertEqual(jobs[0]["company"], "Acme Corp")
        self.assertEqual(jobs[0]["location"], "Remote")

    def test_two_part_line_defaults_location_to_remote(self):
        text = (
            "Remote Jobs for You:\n"
            "Frontend Engineer | Beta Corp | $120K - $140K\n"
            "Find more jobs\n"
        )
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Frontend Engineer")
        self.assertEqual(jobs[0]["company"], "Beta Corp")
        self.assertEqual(jobs[0]["location"], "Remote")

    def test_one_part_line_defaults_company_unknown(self):
        text = (
            "Remote Jobs for You:\n"
            "Data Scientist | $200K - $250K\n"
            "Find more jobs\n"
        )
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Data Scientist")
        self.assertEqual(jobs[0]["company"], "Unknown")
        self.assertEqual(jobs[0]["location"], "Remote")


class TestLaddersFormatA(unittest.TestCase):
    """Format A: 'Title    $Salary' then 'Company | Location' on the next line."""

    def test_title_salary_then_company_location(self):
        text = "Applied Scientist             $165K - $206K*\nBrightAI | Salt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Applied Scientist")
        self.assertEqual(jobs[0]["company"], "BrightAI")
        self.assertEqual(jobs[0]["location"], "Salt Lake City, UT")


class TestLaddersFormatB(unittest.TestCase):
    """Format B: '$Salary | Company | Location' with title scanned backward
    and location continuation scanned forward."""

    def test_basic_salary_company_location_line(self):
        text = "Senior Software Engineer\n$180K - $210K* | Teladoc | Remote\nApply Now\n"
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Teladoc")
        self.assertEqual(jobs[0]["location"], "Remote")

    def test_location_continues_across_lines_until_apply_now(self):
        text = "Senior Software Engineer\n$180K - $210K* | Teladoc | UT\nAdditional loc detail\nApply Now\n"
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "UT Additional loc detail")

    def test_backward_title_scan_skips_metadata_lines(self):
        text = "http://example.com/tracking\nSenior Software Engineer\n$180K - $210K* | Teladoc | Remote\nApply Now\n"
        jobs = parse_job_cards_from_text(text, provider="Ladders", source_pdf="ladders.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")


class TestGenericParserGaps(unittest.TestCase):
    """Gaps in the default (non-provider-specific) title/company/location parser."""

    def test_invalid_potential_company_falls_back_to_unknown(self):
        text = (
            "please apply now for this opportunity today\n"
            "Senior Software Engineer\n"
            "Salt Lake City, UT\n"
        )
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Unknown/Other")
        self.assertEqual(jobs[0]["location"], "Salt Lake City, UT")

    def test_title_as_last_line_has_no_next_line(self):
        text = "Senior Software Engineer\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")
        self.assertEqual(jobs[0]["company"], "Unknown/Other")

    def test_location_gains_hybrid_qualifier_from_continuation_line(self):
        text = "Senior Software Engineer\nCompany Name Inc\nSalt Lake City, UT\nRemote (Hybrid)\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "Salt Lake City, UT Remote (Hybrid)")

    def test_url_detected_in_lookahead_window(self):
        text = "Senior Software Engineer\nAcme Corp\nRemote\nwww.acme.com/careers/123\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], "www.acme.com/careers/123")

    def test_location_fallback_uses_line_two_positions_after_title(self):
        text = "Senior Software Engineer\nAcme Corp\nSan Francisco Bay Area\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "San Francisco Bay Area")

    def test_bullet_separated_company_location_prefix_already_in_location(self):
        text = "Senior Software Engineer\nAcme Corp • Salt Lake\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme Corp")
        self.assertEqual(jobs[0]["location"], "Salt Lake City, UT")

    def test_bullet_separated_company_location_contained_in_prefix(self):
        text = "Senior Software Engineer\nAcme Corp • Building 5 North Campus\nNorth Campus\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme Corp")
        self.assertEqual(jobs[0]["location"], "Building 5 North Campus")

    def test_bullet_separated_company_location_combined_when_disjoint(self):
        text = "Senior Software Engineer\nAcme Corp • Downtown Office\nSalt Lake City, UT\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme Corp")
        self.assertEqual(jobs[0]["location"], "Downtown Office Salt Lake City, UT")

    def test_bullet_separated_company_location_used_when_no_location_found(self):
        text = "Senior Software Engineer\nAcme Corp • HQ Office\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Acme Corp")
        self.assertEqual(jobs[0]["location"], "HQ Office")

    def test_title_strips_ziprecruiter_trailing_new_badge(self):
        text = "Senior Software Engineer New\nAcme Corp\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="ZipRecruiter", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")

    def test_title_new_badge_strip_is_case_insensitive(self):
        text = "Senior Software Engineer NEW\nAcme Corp\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="ZipRecruiter", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")

    def test_title_drops_unmatched_trailing_paren(self):
        text = "Senior Software Engineer (Remote)\nAcme Corp\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer (Remote)")

    def test_title_unmatched_paren_stripped_when_opening_paren_wrapped_away(self):
        text = "Senior Software Engineer)\nAcme Corp\nRemote\n"
        jobs = parse_job_cards_from_text(text, provider="Indeed", source_pdf="test.pdf")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Senior Software Engineer")


if __name__ == "__main__":
    unittest.main()
