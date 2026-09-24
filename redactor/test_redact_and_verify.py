"""Unit tests for redact_and_verify()'s retry/confirm state machine.

redact_file() and verify() are mocked - no real PDF, OCR, or tesseract needed - so the
state machine (when it retries, when it re-confirms, when it gives up) can be checked
deterministically instead of depending on tesseract's actual run-to-run variance.

    python -m unittest test_redact_and_verify -v
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import redact

PATTERNS = [("SSN", redact.SSN_RE)]


class RedactAndVerifyTests(unittest.TestCase):
    def _run(self, verify_results, **kwargs):
        """verify_results: return values for successive verify() calls, in order."""
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "dst.pdf"

            def fake_redact_file(src, dst_path, patterns, ocr=False, ocr_pages=None):
                Path(dst_path).touch()  # redact_and_verify replace()s/unlink()s this for real
                return {}, []

            with patch.object(redact, "redact_file", side_effect=fake_redact_file) as rf, \
                 patch.object(redact, "verify", side_effect=verify_results) as vf:
                result = redact.redact_and_verify(
                    "src.pdf", dst, PATTERNS, ocr=True, ocr_pages=[1], **kwargs)
        return (*result, vf.call_count, rf.call_count)

    def test_clean_first_read_is_confirmed_before_trusted(self):
        # initial verify clean, one confirmation re-read also clean -> done.
        _, _, leftovers, passes, vcalls, rcalls = self._run([[], []])
        self.assertEqual(leftovers, [])
        self.assertEqual(vcalls, 2)  # initial + 1 confirmation (default confirm_passes=1)
        self.assertEqual(rcalls, 1)  # no retry redaction needed

    def test_confirmation_catching_a_miss_triggers_a_fresh_redaction_and_reconfirms(self):
        # clean, then the confirmation re-read DOES find something (the exact failure mode this
        # guards against) -> must redact again, then re-clean, then confirm clean once more.
        _, _, leftovers, passes, vcalls, rcalls = self._run([[], ["p1-ocr:SSN"], [], []])
        self.assertEqual(leftovers, [])
        self.assertEqual(rcalls, 2)  # original + one retry redaction
        self.assertEqual(vcalls, 4)  # clean, catch, re-verify clean, re-confirm clean

    def test_non_ocr_leftover_is_never_retried_or_confirmed(self):
        # a text-layer/metadata/annotation leftover is not OCR variance - stop immediately.
        _, _, leftovers, passes, vcalls, rcalls = self._run([["p1:SSN"]])
        self.assertEqual(leftovers, ["p1:SSN"])
        self.assertEqual(rcalls, 1)
        self.assertEqual(vcalls, 1)

    def test_retry_budget_exhausted_still_reports_the_real_leftover(self):
        _, _, leftovers, passes, vcalls, rcalls = self._run([["p1-ocr:SSN"]] * 10, extra_passes=2)
        self.assertEqual(leftovers, ["p1-ocr:SSN"])
        self.assertEqual(rcalls, 3)  # original + 2 retries (extra_passes), then gives up

    def test_no_page_used_ocr_skips_confirmation(self):
        # ocr=True was passed but nothing on the page needed it (ocr_pages stays empty) - a
        # text-layer result is deterministic, so there is nothing to re-confirm.
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "dst.pdf"

            def fake_redact_file(src, dst_path, patterns, ocr=False, ocr_pages=None):
                Path(dst_path).touch()
                return {}, []

            with patch.object(redact, "redact_file", side_effect=fake_redact_file), \
                 patch.object(redact, "verify", side_effect=[[]]) as vf:
                _, _, leftovers, passes = redact.redact_and_verify(
                    "src.pdf", dst, PATTERNS, ocr=True, ocr_pages=[])
        self.assertEqual(leftovers, [])
        self.assertEqual(vf.call_count, 1)

    def test_confirm_passes_zero_matches_old_single_verify_behavior(self):
        _, _, leftovers, passes, vcalls, rcalls = self._run([[]], confirm_passes=0)
        self.assertEqual(leftovers, [])
        self.assertEqual(vcalls, 1)


if __name__ == "__main__":
    unittest.main()
