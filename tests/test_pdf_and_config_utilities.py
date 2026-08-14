import os
import sys
import csv
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parse_jobs
from parse_jobs import (
    hash_pdf_file,
    write_tracker_csv_atomic,
    load_config,
    save_config,
    select_pdf_directory,
    extract_pdf_text,
    perform_ocr,
    normalize_ocr_spacing,
    _clean_location,
    detect_provider,
)


class UtilityTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp_dir.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp_dir.cleanup()


class TestHashPdfFile(UtilityTestBase):

    def test_hash_is_stable_for_same_content(self):
        with open("a.pdf", "wb") as f:
            f.write(b"same content")
        with open("b.pdf", "wb") as f:
            f.write(b"same content")
        self.assertEqual(hash_pdf_file("a.pdf"), hash_pdf_file("b.pdf"))

    def test_missing_file_returns_none(self):
        self.assertIsNone(hash_pdf_file("does_not_exist.pdf"))


class TestWriteTrackerCsvAtomic(UtilityTestBase):

    def test_writes_rows_and_no_temp_file_left_behind(self):
        write_tracker_csv_atomic("out.csv", ["A", "B"], [{"A": "1", "B": "2"}])
        with open("out.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows, [{"A": "1", "B": "2"}])
        self.assertEqual([f for f in os.listdir(".") if f.startswith(".tmp_tracker_")], [])

    def test_failure_cleans_up_temp_file_and_reraises(self):
        with patch("parse_jobs.os.replace", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                write_tracker_csv_atomic("out.csv", ["A"], [{"A": "1"}])
        self.assertEqual([f for f in os.listdir(".") if f.startswith(".tmp_tracker_")], [])
        self.assertFalse(os.path.exists("out.csv"))


class TestLoadSaveConfig(UtilityTestBase):

    def test_load_config_creates_defaults_when_missing(self):
        config = load_config()
        self.assertIn("job_type_criteria", config)
        self.assertTrue(os.path.exists(parse_jobs.CONFIG_PATH))

    def test_load_config_recovers_from_corrupt_json(self):
        with open(parse_jobs.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        with patch("parse_jobs.console.print") as mock_print:
            config = load_config()
        self.assertIn("job_type_criteria", config)
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Failed to read" in c for c in calls))

    def test_load_config_write_failure_is_reported(self):
        with patch("builtins.open", side_effect=[OSError("locked")]):
            with patch("parse_jobs.console.print") as mock_print:
                config = load_config()
        self.assertIn("job_type_criteria", config)
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Failed to write default config" in c for c in calls))

    def test_save_config_persists_last_pdf_dir(self):
        save_config("C:\\some\\dir")
        with open(parse_jobs.CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        self.assertEqual(config["last_pdf_dir"], "C:\\some\\dir")

    def test_save_config_failure_is_reported(self):
        with patch("builtins.open", side_effect=OSError("locked")):
            with patch("parse_jobs.console.print") as mock_print:
                save_config("C:\\some\\dir")
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("Failed to save config" in c for c in calls))


class TestSelectPdfDirectory(UtilityTestBase):

    def test_gui_cancelled_exits(self):
        with patch("tkinter.Tk") as mock_tk, \
             patch("tkinter.filedialog.askdirectory", return_value=""):
            mock_tk.return_value = MagicMock()
            with self.assertRaises(SystemExit) as cm:
                select_pdf_directory()
        self.assertEqual(cm.exception.code, 0)

    def test_gui_selection_returns_absolute_path_and_saves_config(self):
        chosen = os.path.join(self.tmp_dir.name, "chosen_dir")
        with patch("tkinter.Tk") as mock_tk, \
             patch("tkinter.filedialog.askdirectory", return_value=chosen):
            mock_tk.return_value = MagicMock()
            result = select_pdf_directory()
        self.assertEqual(result, os.path.abspath(chosen))
        with open(parse_jobs.CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        self.assertEqual(config["last_pdf_dir"], os.path.abspath(chosen))

    def test_gui_unavailable_falls_back_to_saved_default(self):
        save_config(self.tmp_dir.name)
        with patch("tkinter.Tk", side_effect=RuntimeError("no display")):
            result = select_pdf_directory()
        self.assertEqual(result, os.path.abspath(self.tmp_dir.name))

    def test_gui_unavailable_and_no_default_falls_back_to_input(self):
        typed_dir = os.path.join(self.tmp_dir.name, "typed_dir")
        with patch("tkinter.Tk", side_effect=RuntimeError("no display")), \
             patch("builtins.input", return_value=typed_dir):
            result = select_pdf_directory()
        self.assertEqual(result, os.path.abspath(typed_dir))


class TestExtractPdfTextAndOcr(UtilityTestBase):

    def test_extract_pdf_text_success(self):
        fake_page = MagicMock()
        fake_page.extract_text.return_value = "Some job text"
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page]
        with patch("parse_jobs.pypdf.PdfReader", return_value=fake_reader):
            text = extract_pdf_text("anything.pdf")
        self.assertIn("Some job text", text)

    def test_extract_pdf_text_reader_exception_falls_back_to_ocr(self):
        with patch("parse_jobs.pypdf.PdfReader", side_effect=RuntimeError("corrupt")):
            with patch("parse_jobs.console.print"):
                text = extract_pdf_text("anything.pdf")
        self.assertEqual(text, "")

    def test_extract_pdf_text_empty_falls_back_to_ocr(self):
        fake_page = MagicMock()
        fake_page.extract_text.return_value = ""
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page]
        with patch("parse_jobs.pypdf.PdfReader", return_value=fake_reader):
            with patch("parse_jobs.perform_ocr", return_value="ocr text") as mock_ocr:
                text = extract_pdf_text("anything.pdf")
        mock_ocr.assert_called_once_with("anything.pdf")
        self.assertEqual(text, "ocr text")

    def test_perform_ocr_when_easyocr_available(self):
        self.assertEqual(perform_ocr("anything.pdf"), "")

    def test_perform_ocr_when_easyocr_missing(self):
        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name == "easyocr":
                raise ImportError("no easyocr")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with patch("parse_jobs.console.print") as mock_print:
                result = perform_ocr("anything.pdf")
        self.assertEqual(result, "")
        calls = [c.args[0] for c in mock_print.call_args_list if c.args]
        self.assertTrue(any("not fully configured" in c for c in calls))


class TestNormalizeOcrSpacingAndCleanLocation(unittest.TestCase):

    def test_normalize_ocr_spacing_empty_input(self):
        self.assertEqual(normalize_ocr_spacing(""), "")
        self.assertEqual(normalize_ocr_spacing(None), "")

    def test_normalize_ocr_spacing_fixes_split_words(self):
        self.assertIn("first", normalize_ocr_spacing("firs t"))

    def test_normalize_ocr_spacing_fixes_west_valley_split(self):
        """2026-08-13 production regression: a real LinkedIn digest rendered
        Wheeler Machinery Co.'s location as 'WestV alley City    , UT
        (On-site)' -- the stray space lands mid-word between two multi-letter
        fragments ('WestV' / 'alley'), which the existing single-stray-letter
        heuristics don't catch, so the corrupted location never matched the
        already-tracked 'Salt Lake City, UT' Wheeler row's canonical key and
        the posting was silently re-added as an unrecognized duplicate."""
        self.assertIn("West Valley", normalize_ocr_spacing("WestV alley City    , UT (On-site)"))

    def test_normalize_ocr_spacing_fixes_technologies_split(self):
        self.assertIn("Technologies", normalize_ocr_spacing("Red Hawk Technolog ies LLC"))

    def test_normalize_ocr_spacing_fixes_split_state_abbreviation(self):
        """2026-08-13 production regression: 'Seattle, W A Remote' and
        'Bellevue, W A' -- a state abbreviation split into two single letters
        by the same kerning artifact. Neither existing general heuristic
        catches this (both require one side to be a 2+ letter word, but here
        both fragments are single letters)."""
        self.assertIn(", WA", normalize_ocr_spacing("Seattle, W A Remote"))
        self.assertIn(", WA", normalize_ocr_spacing("Bellevue, W A – Remote"))
        # Unaffected: a state code that was never split shouldn't be touched.
        self.assertIn(", TX", normalize_ocr_spacing("Houston, TX"))

    def test_clean_location_strips_trailing_ui_labels(self):
        self.assertEqual(_clean_location("Remote View Details"), "Remote")

    def test_clean_location_returns_empty_when_it_looks_like_a_title(self):
        # A location field that's actually a job title (parser misalignment)
        # should be discarded rather than kept as a bogus location.
        self.assertEqual(_clean_location("Senior Engineer"), "")


class TestDetectProviderGaps(unittest.TestCase):

    def test_utah_alternate_phrase(self):
        self.assertEqual(detect_provider("Utah's Daily Job Summary", ""), "jobs.utah.gov")

    def test_ladders_alternate_phrase(self):
        self.assertEqual(detect_provider("Your skills are in high demand", ""), "Ladders")


if __name__ == "__main__":
    unittest.main()
