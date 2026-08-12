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
            f.write(f"%PDF-1.4 dummy content for hashing: {name}".encode("utf-8"))
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

    def test_application_confirmation_pdf_ingested(self):
        self._write_dummy_pdf(name="Your application was sent to Acme.pdf")
        self._write_dummy_pdf(name="Application received - Beta Corp.pdf")
        self._write_dummy_pdf(name="listing.pdf")

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        out = buf.getvalue()
        self.assertIn("Ingested application confirmation event: Your application was sent to Acme.pdf", out)
        self.assertIn("Ingested application confirmation event: Application received - Beta Corp.pdf", out)

        conn = sqlite3.connect("jobs.db")
        events = conn.execute("SELECT company FROM application_events").fetchall()
        event_companies = {e[0] for e in events}
        self.assertIn("Acme", event_companies)
        self.assertIn("Beta Corp", event_companies)

        acme_job = conn.execute("SELECT tracker_status, action FROM jobs WHERE company LIKE '%Acme%'").fetchone()
        self.assertIsNotNone(acme_job)
        self.assertEqual(acme_job[0], "Applied")
        self.assertEqual(acme_job[1], "Already Applied")
        conn.close()

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

    def test_application_event_evidence_neutral_reconstruction_yapi_and_1872(self):
        self._write_dummy_pdf(name="Gmail - Hugh, your application was sent to Yapi.pdf")
        self._write_dummy_pdf(name="Gmail - Application received - 1872 Consulting.pdf")

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        conn = sqlite3.connect("jobs.db")
        yapi = conn.execute("SELECT company, tracker_status, action, fit_score, location, company_type, recommendation, reason FROM jobs WHERE company LIKE '%Yapi%'").fetchone()
        self.assertIsNotNone(yapi)
        self.assertEqual(yapi[0], "Yapi")
        self.assertEqual(yapi[1], "Applied")
        self.assertEqual(yapi[2], "Already Applied")
        self.assertEqual(yapi[3], 0)  # Evidence-neutral fit score
        self.assertEqual(yapi[4], "Unknown")  # Evidence-neutral location
        self.assertEqual(yapi[5], "Unknown")  # Evidence-neutral company type
        self.assertEqual(yapi[6], "★★★☆☆ Maybe")
        self.assertIn("Reconstructed from application confirmation PDF", yapi[7])

        c_1872 = conn.execute("SELECT company, tracker_status, action, fit_score, location FROM jobs WHERE company LIKE '%1872%'").fetchone()
        self.assertIsNotNone(c_1872)
        self.assertEqual(c_1872[0], "1872 Consulting")
        self.assertEqual(c_1872[1], "Applied")
        self.assertEqual(c_1872[3], 0)
        self.assertEqual(c_1872[4], "Unknown")
        conn.close()

        # The standalone reconstruction must reach the CSV in this same run --
        # not just jobs.db -- or it's invisible until some later rebuild.
        with open("master_tracker.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        csv_companies = {row["Company"] for row in rows}
        self.assertIn("Yapi", csv_companies)
        self.assertIn("1872 Consulting", csv_companies)
        yapi_row = next(row for row in rows if row["Company"] == "Yapi")
        self.assertEqual(yapi_row["Tracker Status"], "Applied")

    def test_matched_application_event_confirmation_reaches_csv_same_run(self):
        """A confirmation PDF that matches an *already-tracked* job (created in
        a prior run) writes its Source PDF/Notes/status straight to jobs.db.
        existing_jobs is loaded from the CSV before that write happens, so
        without merging the event back in, the stale in-memory row would
        overwrite those fields right back out when combined_jobs is saved --
        losing the confirmation note/PDF from both jobs.db and the CSV in the
        very run that recorded them."""
        self._write_dummy_pdf(name="listing.pdf")
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(io.StringIO()):
                parse_jobs.main()

        os.remove(os.path.join(self.pdf_dir, "listing.pdf"))
        self._write_dummy_pdf(name="Your application was sent to Acme.pdf")
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(io.StringIO()):
                parse_jobs.main()

        conn = sqlite3.connect("jobs.db")
        db_row = conn.execute(
            "SELECT tracker_status, source_pdf, notes FROM jobs WHERE company LIKE '%Acme%'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(db_row)
        self.assertEqual(db_row[0], "Applied")
        self.assertIn("Acme.pdf", db_row[1])
        self.assertIn("Employer confirmation received", db_row[2])

        with open("master_tracker.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        acme_row = next(row for row in rows if "Acme" in row["Company"])
        self.assertEqual(acme_row["Tracker Status"], "Applied")
        self.assertIn("Acme.pdf", acme_row["Source PDF"])
        self.assertIn("Employer confirmation received", acme_row["Notes"])

    def test_failed_final_save_leaves_confirmation_pdf_eligible_for_retry(self):
        """Confirmation PDFs must follow the same deferred-processing contract
        as regular job PDFs: only marked 'processed' once the final jobs.db/CSV
        save actually lands. If the save fails, the PDF must remain eligible
        for retry on the next run instead of being silently skipped forever."""
        self._write_dummy_pdf(name="Your application was sent to Acme.pdf")

        # Pre-create jobs.db's schema for real so mocking save_to_sqlite below
        # only suppresses the final write -- not schema creation that
        # process_application_event's mid-scan queries depend on.
        parse_jobs.save_to_sqlite("jobs.db", [])

        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader), \
             patch("parse_jobs.save_to_sqlite", return_value=False):
            with redirect_stdout(io.StringIO()):
                parse_jobs.main()

        conn = sqlite3.connect("jobs.db")
        processed = conn.execute(
            "SELECT status FROM processed_files"
        ).fetchall()
        conn.close()
        self.assertFalse(
            any(status == "success" for (status,) in processed),
            "confirmation PDF was marked processed even though the final save failed",
        )

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=FakeReader):
            with redirect_stdout(buf):
                parse_jobs.main()

        self.assertNotIn("Skipping Your application was sent to Acme.pdf (unchanged)", buf.getvalue())
        self.assertIn("Ingested application confirmation event", buf.getvalue())

    def test_application_event_multiple_roles_disambiguation(self):
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('wgu1', 'WGU', 'Senior Software Engineer', 'New', 'Apply', 'Unreviewed', 'orig.pdf', 'Initial note')")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('wgu2', 'WGU', 'Data Analyst', 'New', 'Apply', 'Unreviewed', 'orig.pdf', 'Initial note')")
        conn.commit()
        conn.close()

        # Confirmation email specifically for Senior Software Engineer
        parse_jobs.process_application_event(None, "conf.pdf", "Gmail - Hugh, your application was sent to WGU.pdf", "2026-08-12", full_text="Thank you for applying for the Senior Software Engineer position at WGU.")

        conn = sqlite3.connect("jobs.db")
        wgu1 = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='wgu1'").fetchone()
        wgu2 = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='wgu2'").fetchone()
        conn.close()

        self.assertEqual(wgu1[0], "Applied")
        self.assertEqual(wgu1[1], "Already Applied")
        self.assertEqual(wgu2[0], "New")  # Data Analyst untouched!
        self.assertEqual(wgu2[1], "Apply")

    def test_application_event_preserves_interview_states(self):
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('dutch1', 'Dutchie', 'Backend Engineer', 'Phone Screen', 'Contact Recruiter', 'Interview Scheduled', 'orig.pdf', 'Screen with HR')")
        conn.commit()
        conn.close()

        parse_jobs.process_application_event(None, "conf.pdf", "Gmail - Hugh, your application was sent to Dutchie.pdf", "2026-08-12", full_text="Application received for Backend Engineer at Dutchie.")

        conn = sqlite3.connect("jobs.db")
        dutch = conn.execute("SELECT tracker_status, action, disposition, notes FROM jobs WHERE job_id='dutch1'").fetchone()
        conn.close()

        self.assertEqual(dutch[0], "Phone Screen")  # Preserved!
        self.assertEqual(dutch[1], "Contact Recruiter")  # Preserved!
        self.assertEqual(dutch[2], "Interview Scheduled")  # Preserved!
        self.assertIn("Employer confirmation received", dutch[3])

    def test_application_event_preserves_terminal_states_and_actions(self):
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('weave1', 'Weave', 'Staff Engineer', 'Rejected', 'Ignore', 'Closed', 'orig.pdf', 'Not selected')")
        conn.commit()
        conn.close()

        parse_jobs.process_application_event(None, "conf.pdf", "Gmail - Hugh, your application was sent to Weave.pdf", "2026-08-12", full_text="Your application was sent to Weave for Staff Engineer.")

        conn = sqlite3.connect("jobs.db")
        weave = conn.execute("SELECT tracker_status, action, disposition FROM jobs WHERE job_id='weave1'").fetchone()
        conn.close()

        self.assertEqual(weave[0], "Rejected")  # Preserved!
        self.assertEqual(weave[1], "Ignore")    # Preserved!
        self.assertEqual(weave[2], "Closed")    # Preserved!

    def test_application_event_rerun_idempotency(self):
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('test1', 'Acme', 'Software Engineer', 'New', 'Apply', 'Unreviewed', 'orig.pdf', '')")
        conn.commit()
        conn.close()

        parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Acme.pdf", "2026-08-12", full_text="Application confirmation Acme.")
        parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Acme.pdf", "2026-08-12", full_text="Application confirmation Acme.")

        conn = sqlite3.connect("jobs.db")
        notes = conn.execute("SELECT notes FROM jobs WHERE job_id='test1'").fetchone()[0]
        events_count = conn.execute("SELECT COUNT(*) FROM application_events WHERE company='Acme'").fetchone()[0]
        conn.close()

        self.assertEqual(notes.count("Employer confirmation received"), 1)  # No duplicate note text!
        self.assertEqual(events_count, 1)

    def test_application_event_preserves_recruiter_submitted_waiting_and_accepted(self):
        """Regression: the pipeline used to protect a hand-rolled interview/terminal
        status list that didn't match the tracker's real vocabulary (it said
        "Recruiter Contact" when the tracker actually uses "Recruiter Submitted",
        and omitted "Waiting"/"Accepted" entirely), so a stray confirmation email
        could silently downgrade any of these back to Applied."""
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('rs1', 'Northgate', 'QA Engineer', 'Recruiter Submitted', 'Contact Recruiter', 'Pending', 'orig.pdf', '')")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('wt1', 'Cornix', 'DevOps Engineer', 'Waiting', 'Waiting', 'Pending', 'orig.pdf', '')")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('ac1', 'Bramble', 'Platform Engineer', 'Accepted', 'Ignore', 'Closed', 'orig.pdf', '')")
        conn.commit()
        conn.close()

        parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Northgate.pdf", "2026-08-12", full_text="Application confirmation Northgate.")
        parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Cornix.pdf", "2026-08-12", full_text="Application confirmation Cornix.")
        parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Bramble.pdf", "2026-08-12", full_text="Application confirmation Bramble.")

        conn = sqlite3.connect("jobs.db")
        rs = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='rs1'").fetchone()
        wt = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='wt1'").fetchone()
        ac = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='ac1'").fetchone()
        conn.close()

        self.assertEqual(rs, ("Recruiter Submitted", "Contact Recruiter"))
        self.assertEqual(wt, ("Waiting", "Waiting"))
        self.assertEqual(ac, ("Accepted", "Ignore"))

    def test_application_event_ambiguous_multiple_roles_no_title_left_unlinked(self):
        """When a company has multiple tracked roles and the confirmation email
        gives no title to disambiguate with, neither existing job should be
        touched, and the event should be logged with job_id NULL rather than
        guessing (which risks marking the wrong role Applied) or fabricating a
        duplicate placeholder job for a company that's already tracked."""
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('mr1', 'Weave', 'Backend Engineer', 'New', 'Apply', 'Unreviewed', 'orig.pdf', '')")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('mr2', 'Weave', 'Frontend Engineer', 'New', 'Apply', 'Unreviewed', 'orig.pdf', '')")
        conn.commit()
        conn.close()

        job_id, comp_name = parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Weave.pdf", "2026-08-12", full_text="Application confirmation Weave.")

        self.assertIsNone(job_id)

        conn = sqlite3.connect("jobs.db")
        mr1 = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='mr1'").fetchone()
        mr2 = conn.execute("SELECT tracker_status, action FROM jobs WHERE job_id='mr2'").fetchone()
        job_count = conn.execute("SELECT COUNT(*) FROM jobs WHERE company LIKE '%Weave%'").fetchone()[0]
        event_job_id = conn.execute("SELECT job_id FROM application_events WHERE company='Weave'").fetchone()[0]
        conn.close()

        self.assertEqual(mr1, ("New", "Apply"))
        self.assertEqual(mr2, ("New", "Apply"))
        self.assertEqual(job_count, 2)  # No duplicate placeholder created
        self.assertIsNone(event_job_id)

    def test_application_event_tied_title_similarity_left_ambiguous(self):
        """Two roles at the same company with the same title (e.g. a reposted
        listing) tie on title similarity with no way to break the tie -- picking
        whichever happened to be scanned first risks marking the wrong one
        Applied, so this must be left unlinked instead of guessed."""
        parse_jobs.save_to_sqlite("jobs.db", [])
        conn = sqlite3.connect("jobs.db")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('t1', 'Dutchie', 'Software Engineer', 'New', 'Apply', 'Unreviewed', 'orig.pdf', '')")
        conn.execute("INSERT INTO jobs (job_id, company, position, tracker_status, action, disposition, source_pdf, notes) VALUES ('t2', 'Dutchie', 'Software Engineer', 'New', 'Apply', 'Unreviewed', 'orig.pdf', '')")
        conn.commit()
        conn.close()

        job_id, comp_name = parse_jobs.process_application_event(None, "conf.pdf", "Your application was sent to Dutchie.pdf", "2026-08-12", full_text="Thank you for applying for the Software Engineer position at Dutchie.")

        self.assertIsNone(job_id)

        conn = sqlite3.connect("jobs.db")
        t1 = conn.execute("SELECT tracker_status FROM jobs WHERE job_id='t1'").fetchone()[0]
        t2 = conn.execute("SELECT tracker_status FROM jobs WHERE job_id='t2'").fetchone()[0]
        conn.close()

        self.assertEqual(t1, "New")
        self.assertEqual(t2, "New")

    def test_application_event_standalone_reconstruction_infers_operations_job_type(self):
        """Evidence-neutral reconstruction shouldn't hardcode job_type to
        'Software Engineer' regardless of the actual role -- an Operations-style
        title should classify as Operations so downstream scoring treats it
        correctly, not as an SWE role it never claimed to be."""
        self._write_dummy_pdf(name="Gmail - Hugh, your application was sent to Praxis.pdf")

        buf = io.StringIO()
        with patch.object(sys, "argv", ["parse_jobs.py", "--pdf-dir", self.pdf_dir]), \
             patch("parse_jobs.pypdf.PdfReader", side_effect=lambda *a, **k: type("R", (), {"pages": [FakePage("Thank you for applying for the Warehouse Coordinator position at Praxis.")]})()):
            with redirect_stdout(buf):
                parse_jobs.main()

        conn = sqlite3.connect("jobs.db")
        row = conn.execute("SELECT job_type, position FROM jobs WHERE company LIKE '%Praxis%'").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[1], "Warehouse Coordinator")
        self.assertEqual(row[0], "Operations")


if __name__ == "__main__":
    unittest.main()
