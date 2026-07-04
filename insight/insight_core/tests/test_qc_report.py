"""Tests for qc_report.find_nearby_images() (F04-S09 follow-up, 2026-07-04).

Real bug: without column bounds, an unrelated image anywhere on the page at
roughly the same height as a title (e.g. the footer's decorative dot-grid
graphics on a short, single-metric report) was miscounted as "the icon near
this chart" — chart_render_checks() returned 0 issues for a report that had
no icon at all. Caught only by directly rendering the PDF to an image and
looking, not by the QC script itself.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import qc_report
from qc_report import find_nearby_images, bar_thickness_consistency_check

TITLE_POS = (100, 200, 1)  # (x0, top, page_number)


def _img(x0, x1, top):
    return {"x0": x0, "x1": x1, "top": top}


class TestFindNearbyImages:
    def test_image_in_column_and_vertical_window_matches(self):
        images = [_img(110, 160, 220)]
        assert find_nearby_images(TITLE_POS, images, col_bounds=(90, 300)) == images

    def test_image_outside_column_bounds_excluded(self):
        # Same vertical position as a real icon, but a different column
        # entirely — this is the exact footer-dot-grid false positive.
        images = [_img(700, 750, 220)]
        assert find_nearby_images(TITLE_POS, images, col_bounds=(90, 300)) == []

    def test_image_outside_vertical_window_excluded(self):
        images = [_img(110, 160, 500)]
        assert find_nearby_images(TITLE_POS, images, col_bounds=(90, 300)) == []

    def test_no_col_bounds_falls_back_to_vertical_only(self):
        # Backward-compatible default — callers that don't pass col_bounds
        # keep the old (looser) behavior.
        images = [_img(700, 750, 220)]
        assert find_nearby_images(TITLE_POS, images) == images

    def test_image_partially_outside_column_excluded(self):
        images = [_img(280, 350, 220)]  # x1=350 spills past right=300
        assert find_nearby_images(TITLE_POS, images, col_bounds=(90, 300)) == []


# ── bar_thickness_consistency_check (F04-S07/F04-S09 regression guard) ───────
# Real bug this catches: a chrome-band layout change silently made a
# low-date-count chart's bars render thinner than a same-page chart with
# more dates, because a fixed-inch element (the new title/unit-note band)
# ate a bigger FRACTION of a shorter figure. Validated 2026-07-04 by
# reverting the fix via monkeypatch and confirming this check fires.

class _FakeWord(dict):
    pass


def _word(text, x0, top):
    return {"text": text, "x0": x0, "top": top}


def _rect(x0, x1, top, height, fill=True, stroke=False):
    return {"x0": x0, "x1": x1, "top": top, "width": x1 - x0, "height": height,
            "fill": fill, "stroke": stroke}


class _FakePage:
    def __init__(self, words, rects, width=900, page_number=1):
        self._words = words
        self.rects = rects
        self.width = width
        self.page_number = page_number

    def extract_words(self):
        return self._words


class _FakePDF:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestBarThicknessConsistencyCheck:
    def _run(self, monkeypatch, words, rects):
        page = _FakePage(words, rects)
        monkeypatch.setattr(qc_report.pdfplumber, "open", lambda path: _FakePDF([page]))
        return bar_thickness_consistency_check("fake.pdf")

    def _title_words(self, title, x0, top):
        return [_word(tok, x0 + i * 60, top) for i, tok in enumerate(title.split())]

    def test_flags_mismatched_bar_thickness(self, monkeypatch):
        words = (self._title_words("Body Weight", 100, 100)
                  + self._title_words("Waist to Hip Ratio", 400, 100))
        rects = [
            _rect(110, 300, 150, 19.1),   # Body Weight's bar
            _rect(410, 600, 150, 12.0),   # WHR's bar — visibly thinner
        ]
        issues = self._run(monkeypatch, words, rects)
        assert any("Waist to Hip Ratio" in i for i in issues)

    def test_no_issue_when_thickness_matches(self, monkeypatch):
        words = (self._title_words("Body Weight", 100, 100)
                  + self._title_words("Waist to Hip Ratio", 400, 100))
        rects = [
            _rect(110, 300, 150, 19.1),
            _rect(410, 600, 150, 19.1),
        ]
        assert self._run(monkeypatch, words, rects) == []

    def test_single_title_on_page_skipped_not_flagged(self, monkeypatch):
        # Nothing to compare against — must not false-positive.
        words = self._title_words("Body Weight", 100, 100)
        rects = [_rect(110, 300, 150, 19.1)]
        assert self._run(monkeypatch, words, rects) == []

    def test_unfilled_stroked_rect_ignored_as_axis_outline(self, monkeypatch):
        # An axis-box outline (stroke=True, fill=False) must not be
        # mistaken for a bar — only fill=True/stroke=False rects count.
        words = (self._title_words("Body Weight", 100, 100)
                  + self._title_words("Waist to Hip Ratio", 400, 100))
        rects = [
            _rect(110, 300, 150, 19.1),
            _rect(90, 310, 140, 40, fill=False, stroke=True),   # BW's axis box
            _rect(410, 600, 150, 19.1),
            _rect(390, 610, 140, 40, fill=False, stroke=True),  # WHR's axis box
        ]
        assert self._run(monkeypatch, words, rects) == []
