import os
import sys
import io
import csv
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs


class FakePage:
    """Minimal stand-in for a pypdf page object."""
    def __init__(self, text):
        self._text = text
        self.annotations = None

    def extract_text(self, extraction_mode='layout'):
        return self._text


class FakeReader:
    def __init__(self, *args, **kwargs):
        self.pages = [FakePage("Senior Software Engineer\nAcme Corp\nSalt Lake City, UT\n")]


class TestMainDispatch(unittest.TestCase):
    """The early-return dispatch branches in main() -- these should route to
    the appropriate handler and never fall through to the PDF-scan pipeline."""

    def _run(self, argv):
        buf = io.StringIO()
        with patch.object(sys, "argv", argv):
            with redirect_stdout(buf):
                parse_jobs.main()
        return buf.getvalue()

    def test_add_dispatches_to_handle_manual_add(self):
        with patch("parse_jobs.handle_manual_add") as mock_add:
            self._run(["parse_jobs.py", "--add", "--company", "Acme", "--position", "Engineer"])
        mock_add.assert_called_once()
        self.assertEqual(mock_add.call_args.kwargs["company"], "Acme")
        self.assertEqual(mock_add.call_args.kwargs["position"], "Engineer")

    def test_today_dispatches_to_print_today_queue(self):
        with patch("parse_jobs.print_today_queue") as mock_today:
            self._run(["parse_jobs.py", "--today"])
        mock_today.assert_called_once()

    def test_update_with_no_value_launches_interactive_menu(self):
        with patch("parse_jobs.handle_interactive_update") as mock_interactive:
            self._run(["parse_jobs.py", "--update"])
        mock_interactive.assert_called_once()

    def test_update_with_company_but_no_status_errors(self):
        with patch("parse_jobs.handle_status_update") as mock_status:
            out = self._run(["parse_jobs.py", "--update", "Acme"])
        mock_status.assert_not_called()
        self.assertIn("Error: --status is required", out)

    def test_update_with_status_dispatches_handle_status_update(self):
        with patch("parse_jobs.handle_status_update") as mock_status:
            self._run(["parse_jobs.py", "--update", "Acme", "--status", "Applied", "--notes", "test note"])
        mock_status.assert_called_once_with("Acme", "Applied", "test note")

    def test_dashboard_dispatches_to_print_dashboard(self):
        with patch("parse_jobs._print_dashboard") as mock_dash:
            self._run(["parse_jobs.py", "--dashboard"])
        mock_dash.assert_called_once()

    def test_analytics_dispatches_to_print_analytics(self):
        with patch("parse_jobs.print_analytics") as mock_analytics:
            self._run(["parse_jobs.py", "--analytics"])
        mock_analytics.assert_called_once()


class TestMainPdfDirGuards(unittest.TestCase):

    def test_no_directory_selected_exits(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py"]), \
             patch("parse_jobs.select_pdf_directory", return_value=None):
            with redirect_stdout(buf):
                parse_jobs.main()
        self.assertIn("No directory selected. Exiting.", buf.getvalue())

    def test_nonexistent_directory_exits(self):
        buf = io.StringIO()
        missing_dir = os.path.join(tempfile.gettempdir(), "definitely_missing_pdf_dir_xyz")
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", missing_dir]):
            with redirect_stdout(buf):
                parse_jobs.main()
        self.assertIn("Directory not found", buf.getvalue())


class TestMainPdfPipeline(unittest.TestCase):
    """End-to-end coverage of the PDF-scan/review/save pipeline in main().
    pypdf.PdfReader is mocked (no real PDF bytes needed); everything downstream
    -- parsing, scoring, dedup, sqlite/CSV persistence -- runs for real."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)
        self.pdf_dir = os.path.join(self.tmp_dir.name, "pdfs")
        os.makedirs(self.pdf_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()

    def _write_dummy_pdf(self, name="listing.pdf"):
        path = os.path.join(self.pdf_dir, name)
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4 dummy content for hashing only")
        return path

    def test_no_pdfs_in_directory_prints_message_and_returns(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]):
            with redirect_stdout(buf):
                parse_jobs.main()
        self.assertIn("No PDF files found", buf.getvalue())

    def test_sync_complete_box_rows_are_aligned(self):
        """Regression: the "New ★★★★★/★★★★☆ ..." rows in the SYNC COMPLETE
        box previously used a longer label ("... recommendations this run:")
        than every other row's hand-padded template accounted for, pushing
        those two rows 13 characters past the box's right border. Every
        content row between the box's top and bottom borders must render at
        the same width."""
        self._write_dummy_pdf()

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        out = buf.getvalue()
        box_lines = [line for line in out.splitlines() if line.startswith("║") and line.endswith("║")]
        self.assertTrue(box_lines, "expected at least one SYNC COMPLETE box content row")
        lengths = {len(line) for line in box_lines}
        self.assertEqual(len(lengths), 1, f"box rows have mismatched widths: {box_lines}")

    def test_full_pipeline_creates_tracker_and_db_rows(self):
        self._write_dummy_pdf()

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        out = buf.getvalue()
        self.assertIn("SYNC COMPLETE", out)

        self.assertTrue(os.path.exists("master_tracker.csv"))
        with open("master_tracker.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Company"], "Acme Corp")
        self.assertEqual(rows[0]["Position"], "Senior Software Engineer")

        self.assertTrue(os.path.exists("jobs.db"))
        conn = sqlite3.connect("jobs.db")
        db_rows = conn.execute("SELECT company, position FROM jobs").fetchall()
        conn.close()
        self.assertEqual(len(db_rows), 1)
        self.assertEqual(db_rows[0][0], "Acme Corp")

    def test_application_confirmation_pdf_is_skipped(self):
        self._write_dummy_pdf(name="Your application was sent to Acme.pdf")
        self._write_dummy_pdf(name="Application received - Beta Corp.pdf")
        self._write_dummy_pdf(name="listing.pdf")

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        out = buf.getvalue()
        self.assertIn("Skipping application confirmation: Your application was sent to Acme.pdf", out)
        self.assertIn("Skipping application confirmation: Application received - Beta Corp.pdf", out)

        with open("master_tracker.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Company"], "Acme Corp")

    def test_rerun_skips_unchanged_pdf_via_incremental_sync(self):
        self._write_dummy_pdf()

        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(io.StringIO()):
                parse_jobs.main()

            buf = io.StringIO()
            with redirect_stdout(buf):
                parse_jobs.main()

        self.assertIn("Skipping listing.pdf (unchanged)", buf.getvalue())

    def test_pdf_parse_error_is_recorded_and_reported(self):
        self._write_dummy_pdf()

        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=RuntimeError("corrupt pdf")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                parse_jobs.main()

        self.assertIn("Error parsing listing.pdf: corrupt pdf", buf.getvalue())

    def test_seeds_master_tracker_from_existing_csv(self):
        self._write_dummy_pdf()
        with open("old_export.csv", "w", newline="", encoding="utf-8") as f:
            f.write("Job ID,Company,Position\nabc123,Old Corp,Old Role\n")

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        self.assertIn("Seeded new master_tracker.csv from old_export.csv", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
