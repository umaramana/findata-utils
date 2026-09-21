"""Tests for review/redact.py's wrapper around redactor/redact.py - synthetic data only.

    python -m unittest test_redact_wrapper -v

Covers: an address supplied as a names-file entry, name scrubbing of folder and
file names in redact_tree, that the wrapper CLI never prints a supplied name or
address, and the --prompt intake (terminal-only, in-memory, SSN forms it adds).
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

import redact
import redactor.redact as redactor_redact
import redactor.redact_ocr as redact_ocr

HERE = Path(__file__).parent
NAME = "John Smith"
ADDRESS = "42 Maple Street, Springfield IL 62701"


def make_pdf(path, xmp=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), f"Employee: {NAME}   SSN 123-45-6789")
    p.insert_text((72, 130), "Address: 42 Maple Street,")            # address wrapped across two lines
    p.insert_text((72, 145), "Springfield IL 62701")
    p.insert_text((72, 200), "KEEP: 42 Maple Avenue is a different address")
    if xmp:
        doc.set_xml_metadata(f"<x:xmpmeta xmlns:x='adobe:ns:meta/'><dc>{NAME}</dc></x:xmpmeta>")
    doc.save(path)


class _Tty(io.StringIO):
    def isatty(self):
        return True


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src, self.out = self.root / "in", self.root / "out"
        make_pdf(self.src / f"folder {NAME}" / f"W2 - {NAME}.pdf", xmp=True)
        make_pdf(self.src / "neutral.pdf")
        self.names_file = self.root / "names.json"
        self.names_file.write_text(json.dumps({
            f"folder {NAME}/W2 - {NAME}.pdf": [NAME, ADDRESS],
            "neutral.pdf": [NAME, ADDRESS],
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def redacted_text(self, path):
        with fitz.open(path) as doc:
            return " ".join(doc[0].get_text().split()), (doc.get_xml_metadata() or "")

    def test_address_entry_is_redacted_but_a_similar_address_is_kept(self):
        names = json.loads(self.names_file.read_text(encoding="utf-8"))
        results = redact.redact_tree(self.src, self.out, names)
        self.assertEqual([r.status for r in results], ["OK", "OK"])
        text, _ = self.redacted_text(next(r.redacted_path for r in results if r.source_file == "neutral.pdf"))
        self.assertNotIn("Maple Street", text)
        self.assertNotIn("Springfield", text)
        self.assertIn("42 Maple Avenue", text)

    def test_folder_and_file_names_and_xmp_are_scrubbed(self):
        names = json.loads(self.names_file.read_text(encoding="utf-8"))
        results = redact.redact_tree(self.src, self.out, names)
        written = sorted(str(p.relative_to(self.out)) for p in self.out.rglob("*.pdf"))
        self.assertEqual(written, sorted(["neutral.pdf", str(Path("folder REDACTED") / "W2 - REDACTED.pdf")]))
        named = next(r for r in results if r.source_file != "neutral.pdf")
        self.assertNotIn(NAME.lower(), self.redacted_text(named.redacted_path)[1].lower())

    def test_two_files_scrubbing_to_the_same_name_do_not_overwrite(self):
        make_pdf(self.src / f"folder {NAME}" / "W2 - John_Smith.pdf")
        results = redact.redact_tree(self.src, self.out, {}, default_names=[NAME])
        outs = [r.redacted_path for r in results]
        self.assertEqual(len(outs), len(set(outs)))
        self.assertEqual(len(list(self.out.rglob("*.pdf"))), 3)

    def test_cli_output_never_prints_a_name_or_address(self):
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", str(HERE / "redact.py"), "--src", str(self.src),
             "--out", str(self.out), "--names-file", str(self.names_file)],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for secret in ("John", "Smith", "Maple", "Springfield", "62701"):
            self.assertNotIn(secret, proc.stdout)
        self.assertIn("2 OK", proc.stdout)


    # --- --prompt intake ------------------------------------------------------

    def run_prompt(self, typed, hidden):
        with mock.patch.object(sys, "stdin", _Tty()), mock.patch.object(sys, "stdout", _Tty()), \
                mock.patch("builtins.input", side_effect=typed), \
                mock.patch("getpass.getpass", side_effect=hidden):
            return redact.prompt_for_client_details(self.src)

    def test_prompt_returns_entries_and_valid_ssns_only(self):
        entries, ssns = self.run_prompt([NAME, ADDRESS, "", "yes"], ["987-65-4321", "12-34", ""])
        self.assertEqual(entries, [NAME, ADDRESS])
        self.assertEqual(ssns, ["987-65-4321"])  # the malformed one is skipped

    def test_prompt_cancel_and_empty_exit_without_returning(self):
        with self.assertRaises(SystemExit):
            self.run_prompt([NAME, "", "no"], [""])
        with self.assertRaises(SystemExit):
            self.run_prompt([""], [""])

    def test_prompt_refuses_without_a_terminal(self):
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", str(HERE / "redact.py"), "--src", str(self.src),
             "--out", str(self.out), "--prompt"],
            input=f"{NAME}\n\n\nyes\n", capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("interactive terminal", proc.stdout + proc.stderr)
        self.assertNotIn("Smith", proc.stdout + proc.stderr)
        self.assertFalse(self.out.exists() and list(self.out.rglob("*.pdf")))

    def test_prompt_cannot_be_mixed_with_a_names_file(self):
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", str(HERE / "redact.py"), "--src", str(self.src), "--out", str(self.out),
             "--prompt", "--names-file", str(self.names_file)], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(proc.returncode, 0)

    def test_known_ssn_forms_the_dashed_pattern_misses_are_caught(self):
        odd = self.root / "odd" / "ssn.pdf"
        odd.parent.mkdir()
        doc = fitz.open()
        doc.new_page().insert_text((72, 100), "Nodash 987654321  Spaced 987 65 4321  Masked XXX-XX-4321  KEEP Ref 1234567")
        doc.save(odd)
        results = redact.redact_tree(odd.parent, self.root / "odd_out", {}, [NAME], ["987-65-4321"])
        self.assertEqual(results[0].status, "OK")
        text, _ = self.redacted_text(results[0].redacted_path)
        for gone in ("987654321", "987 65 4321", "XXX-XX-4321"):
            self.assertNotIn(gone, text)
        self.assertIn("1234567", text)

    # --- annotations (e.g. a vendor's /FOSINDEX that MuPDF cannot render) -------

    def make_annotated(self, name, contents=None, hex_title=None, indirect_array=False):
        path = self.root / "annot_in" / name
        path.parent.mkdir(exist_ok=True)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), f"Employee: {NAME}   SSN 123-45-6789")
        fields = "/Rect [400 100 450 120]" + (f" /Contents ({contents})" if contents else "")
        if hex_title:
            fields += " /T <FEFF" + hex_title.encode("utf-16-be").hex().upper() + ">"
        xrefs = []
        for subtype in ("FOSINDEX", "Text"):
            x = doc.get_new_xref()
            doc.update_object(x, f"<< /Type /Annot /Subtype /{subtype} {fields} >>")
            xrefs.append(x)
        arr = "[" + " ".join(f"{x} 0 R" for x in xrefs) + "]"
        if indirect_array:
            a = doc.get_new_xref()
            doc.update_object(a, arr)
            arr = f"{a} 0 R"
        doc.xref_set_key(page.xref, "Annots", arr)
        doc.save(path)
        return path.parent

    def run_annotated(self, folder):
        return redact.redact_tree(folder, self.root / "annot_out", {}, default_names=[NAME])

    @staticmethod
    def all_object_text(path):
        """Every object dictionary in the file, including any left unreferenced."""
        parts = []
        with fitz.open(path) as d:
            for x in range(1, d.xref_length()):
                try:
                    parts.append(d.xref_object(x, compressed=False))
                except Exception:
                    pass
        return " ".join(parts)

    def test_name_inside_an_annotation_is_removed_from_the_copy(self):
        hex_name = "FEFF" + NAME.encode("utf-16-be").hex().upper()
        for label, kw in (("literal", dict(contents=NAME)), ("hex utf-16", dict(hex_title=NAME)),
                          ("indirect array", dict(contents=NAME, indirect_array=True))):
            with self.subTest(label):
                folder = self.make_annotated("a.pdf", **kw)
                (r,) = self.run_annotated(folder)
                self.assertEqual(r.status, "OK", r.leftovers)
                blob = self.all_object_text(r.redacted_path)
                self.assertNotIn(NAME, blob)
                self.assertNotIn(hex_name, blob)
                with fitz.open(r.redacted_path) as d:
                    self.assertEqual(redactor_redact._annotation_xrefs(d, d[0]), [])

    def test_verify_still_detects_annotation_text_in_an_unredacted_file(self):
        folder = self.make_annotated("a.pdf", contents=NAME)
        leftovers = redactor_redact.verify(folder / "a.pdf", redactor_redact.build_patterns([NAME], []))
        self.assertTrue(any("annot" in l for l in leftovers), leftovers)

    def make_widget(self, value):
        path = self.root / "widget_in" / "w.pdf"
        path.parent.mkdir(exist_ok=True)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Form")
        x = doc.get_new_xref()
        doc.update_object(x, f"<< /Type /Annot /Subtype /Widget /FT /Tx /T (f1) /V ({value}) /Rect [72 200 200 220] >>")
        doc.xref_set_key(page.xref, "Annots", f"[{x} 0 R]")
        doc.save(path)
        return path.parent

    def test_form_fields_are_kept_and_fail_the_file_if_they_hold_a_name(self):
        (r,) = self.run_annotated(self.make_widget(NAME))
        self.assertEqual(r.status, "FAIL")
        self.assertTrue(any("annot" in l for l in r.leftovers), r.leftovers)
        with fitz.open(r.redacted_path) as d:
            self.assertEqual(len(redactor_redact._annotation_xrefs(d, d[0])), 1)  # widget not deleted
        (ok,) = redact.redact_tree(self.make_widget("Jane Doe"), self.root / "widget_out2", {}, default_names=[NAME])
        self.assertEqual(ok.status, "OK")

    def test_leftover_label_from_an_annotation_never_prints_the_name(self):
        (r,) = self.run_annotated(self.make_widget(NAME))
        _, safe_leftovers = redact._anonymize_for_display(r.counts, r.leftovers, [NAME])
        self.assertTrue(safe_leftovers)
        self.assertNotIn("John", " ".join(safe_leftovers))

    def test_harmless_unknown_annotation_is_ok_and_noted_once(self):
        folder = self.make_annotated("a.pdf")
        (r,) = self.run_annotated(folder)
        self.assertEqual(r.status, "OK")
        self.assertEqual(len(r.mupdf_notes), 1, r.mupdf_notes)
        self.assertRegex(r.mupdf_notes[0], r"^\d+x .*FOSINDEX")

    def test_cli_shows_the_note_once_and_says_it_is_not_a_failure(self):
        folder = self.make_annotated("a.pdf")
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", str(HERE / "redact.py"), "--src", str(folder),
             "--out", str(self.root / "cli_out"), "--names-file", str(self._names_for(folder))],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("FOSINDEX"), 1)
        self.assertNotIn("FOSINDEX", proc.stderr)
        self.assertIn("do not by themselves mean redaction failed", proc.stdout)

    def _names_for(self, folder):
        f = self.root / "annot_names.json"
        f.write_text(json.dumps({"a.pdf": [NAME]}), encoding="utf-8")
        return f

    # --- name variants / stricter filenames -------------------------------------

    def test_filename_scrub_catches_parts_and_truncated_forms_of_a_name(self):
        names = ["Priya Ramachandran"]
        self.assertEqual(redact.scrub_text("w2 rama 1", names), "w2 REDACTED 1")                    # truncated form
        self.assertEqual(redact.scrub_text("1099-INT priya trust", names), "1099-INT REDACTED trust")  # a single name
        self.assertEqual(redact.scrub_text("MS_2025_1099-CONS ramachandran", names), "MS_2025_1099-CONS REDACTED")
        self.assertEqual(redact.scrub_text("W2_Priya_Ramachandran", names), "W2_REDACTED")

    def test_filename_scrub_leaves_unrelated_and_address_words_alone(self):
        self.assertEqual(redact.scrub_text("1099INT - 2026-01-16 trust", ["Priya Ramachandran"]),
                         "1099INT - 2026-01-16 trust")
        self.assertEqual(redact.scrub_text("Street report", [ADDRESS]), "Street report")

    def test_reordered_and_initial_forms_are_redacted_in_a_tree_run(self):
        src = self.root / "variants_in"
        src.mkdir()
        doc = fitz.open()
        doc.new_page().insert_text((72, 100), "Payee: Smith, John  Signed J. Smith  KEEP: Jane Smith")
        doc.save(src / "v.pdf")
        (r,) = redact.redact_tree(src, self.root / "variants_out", {}, default_names=[NAME])
        self.assertEqual(r.status, "OK")
        text, _ = self.redacted_text(r.redacted_path)
        self.assertNotIn("Smith, John", text)
        self.assertNotIn("J. Smith", text)
        self.assertIn("Jane Smith", text)
        self.assertEqual(r.counts.get(NAME), 2)  # one label per person, however it was written

    # --- file discovery -----------------------------------------------------------

    def test_pdfs_are_found_whatever_the_extension_case(self):
        d = self.root / "case_in"
        d.mkdir()
        for name in ("a.pdf", "B.PDF", "c.Pdf"):
            make_pdf(d / name)
        results = redact.redact_tree(d, self.root / "case_out", {}, default_names=[NAME])
        self.assertEqual(sorted(r.source_file for r in results), ["B.PDF", "a.pdf", "c.Pdf"])

    def test_files_that_are_not_pdfs_are_reported_by_extension_only(self):
        d = self.root / "skip_in"
        d.mkdir()
        make_pdf(d / "a.pdf")
        (d / "scan John Smith.jpeg").write_bytes(b"x")
        (d / "notes.html").write_bytes(b"x")
        (d / "README").write_bytes(b"x")
        self.assertEqual(redact.skipped_files(d), {".jpeg": 1, ".html": 1, "(no extension)": 1})
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", str(HERE / "redact.py"), "--src", str(d), "--out", str(self.root / "skip_out"),
             "--default-names", NAME], capture_output=True, text=True, encoding="utf-8")
        self.assertIn("NOT redacted (not PDFs, left out)", proc.stdout)
        self.assertIn("1 x .jpeg", proc.stdout)
        self.assertNotIn("John", proc.stdout)  # the skipped file's name is never printed


@unittest.skipUnless(redact_ocr.available(), "tesseract not installed")
class OcrTests(unittest.TestCase):
    """redact_tree(ocr=True): an image-only page is read, redacted and reported in ocr_pages."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.src, self.out = root / "in", root / "out"
        self.src.mkdir()
        page = fitz.open().new_page()
        for k, line in enumerate([f"Employee: {NAME}   SSN 123-45-6789", "Employer EIN 12-3456789 Acme Widgets Incorporated",
                                  "Box 1 Wages 85000.00 Box 2 Federal tax withheld 12000.00"]):
            page.insert_text((72, 100 + 30 * k), line, fontsize=13)
        doc = fitz.open()
        doc.new_page().insert_image(fitz.Rect(0, 0, 612, 792), stream=page.get_pixmap(dpi=200).tobytes("png"))
        doc.save(self.src / "scan.pdf")

    def tearDown(self):
        self._tmp.cleanup()

    def test_off_is_review_on_is_ok(self):
        off = redact.redact_tree(self.src, self.root_out("off"), default_names=[NAME])
        self.assertEqual((off[0].status, off[0].ocr_pages), ("REVIEW", []))
        on = redact.redact_tree(self.src, self.root_out("on"), default_names=[NAME], ocr=True)
        self.assertEqual((on[0].status, on[0].ocr_pages, on[0].no_text_pages), ("OK", [1], []))
        self.assertTrue({"SSN", "EIN", NAME} <= set(on[0].counts))
        with fitz.open(on[0].redacted_path) as doc:
            seen = " ".join(w["text"] for w in redact_ocr.read_words(doc[0]))
        self.assertNotIn("Smith", seen)
        self.assertNotIn("6789", seen)
        self.assertIn("Acme", seen)

    def _flaky_reader(self, hide_on):
        """read_words that drops every digit-bearing word on the calls whose 1-based number satisfies hide_on -
        a stand-in for OCR reading a photo differently from one pass to the next."""
        real, calls = redact_ocr.read_words, [0]

        def flaky(page, dpi=redact_ocr.OCR_DPI):
            calls[0] += 1
            words = real(page, dpi)
            return [w for w in words if not any(c.isdigit() for c in w["text"])] if hide_on(calls[0]) else words
        return flaky

    def test_ocr_miss_on_first_read_is_caught_by_a_second_pass(self):
        with mock.patch.object(redact_ocr, "read_words", self._flaky_reader(lambda n: n == 1)):
            res = redact.redact_tree(self.src, self.root_out("miss"), default_names=[NAME], ocr=True)
        self.assertEqual((res[0].status, res[0].passes, res[0].leftovers), ("OK", 2, []))
        with fitz.open(res[0].redacted_path) as doc:
            seen = " ".join(w["text"] for w in redact_ocr.read_words(doc[0]))
        self.assertNotIn("6789", seen)
        self.assertNotIn("Smith", seen)

    def test_ocr_that_never_converges_stays_fail(self):
        with mock.patch.object(redact_ocr, "read_words", self._flaky_reader(lambda n: n % 2 == 1)):
            res = redact.redact_tree(self.src, self.root_out("never"), default_names=[NAME], ocr=True)
        self.assertEqual((res[0].status, res[0].passes), ("FAIL", 3))
        self.assertTrue(res[0].leftovers and all("-ocr:" in item for item in res[0].leftovers))

    def root_out(self, tag):
        return Path(self._tmp.name) / f"out_{tag}"


if __name__ == "__main__":
    unittest.main()
