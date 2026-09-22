"""Tests for eligibility.py - synthetic PDFs only.

    python -m unittest test_eligibility -v
"""
import tempfile
import unittest
from pathlib import Path

import fitz

import eligibility


def _pdf(path, lines):
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 100 + i * 20), line, fontsize=11)
    doc.save(path)
    doc.close()


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def _make(self, name, lines):
        path = self.root / name
        _pdf(path, lines)
        return path

    def test_standalone_1099_int_is_eligible(self):
        path = self._make("int.pdf", ["Form 1099-INT Interest Income", "Box 1  Interest income:  1,200.00"])
        self.assertIsNone(eligibility.classify(path))

    def test_standalone_w2_is_eligible(self):
        path = self._make("w2.pdf", ["Form W-2 Wage and Tax Statement", "Box 1  Wages:  75,000.00"])
        self.assertIsNone(eligibility.classify(path))

    def test_consolidated_1099_b_excluded(self):
        path = self._make("cons.pdf", [
            "CONSOLIDATED FORM 1099", "1099-DIV  Dividends and Distributions",
            "1099-B  Proceeds From Broker and Barter Exchange Transactions",
        ])
        reason = eligibility.classify(path)
        self.assertIsNotNone(reason)
        self.assertIn("1099-B", reason)

    def test_consolidated_statement_without_1099b_excluded(self):
        path = self._make("cons2.pdf", ["Consolidated Tax Statement", "1099-INT  Interest Income", "1099-DIV Dividends"])
        reason = eligibility.classify(path)
        self.assertIsNotNone(reason)
        self.assertIn("consolidated statement", reason)

    def test_schedule_k1_excluded(self):
        path = self._make("k1.pdf", ["Schedule K-1 (Form 1065)", "Partner's Share of Income, Deductions, Credits"])
        reason = eligibility.classify(path)
        self.assertIsNotNone(reason)
        self.assertIn("K-1", reason)

    def test_1099_oid_excluded(self):
        path = self._make("oid.pdf", ["Form 1099-OID", "Original issue discount:  500.00"])
        reason = eligibility.classify(path)
        self.assertIsNotNone(reason)
        self.assertIn("OID", reason)

    def test_image_only_page_not_excluded(self):
        # No text layer at all - classify() must not guess; leave it to the redaction gate.
        doc = fitz.open()
        doc.new_page()  # blank page, no insert_text -> no text layer
        path = self.root / "blank.pdf"
        doc.save(path)
        doc.close()
        self.assertIsNone(eligibility.classify(path))

    def test_unopenable_file_not_excluded(self):
        path = self.root / "not_a_pdf.pdf"
        path.write_bytes(b"not a pdf at all")
        self.assertIsNone(eligibility.classify(path))


if __name__ == "__main__":
    unittest.main()
