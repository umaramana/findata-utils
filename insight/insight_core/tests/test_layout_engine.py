"""Tests for layout_engine.layout_report() — F05-S04."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from layout_engine import (
    layout_report, _partition, _chunk, _group_to_rows,
    USABLE_HEIGHT_PX, BUCKET_1_IDS, BUCKET_2_IDS, BUCKET_3_IDS,
    BUCKET_2_DERIVED_METRIC_IDS,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _sec(component_id, height_px=400, **kwargs):
    """Minimal section dict for layout tests."""
    return {"component_id": component_id, "rendered_height_px": height_px,
            "rendered_width_px": 964, **kwargs}


def _b1(**kw): return _sec("body_measurements", **kw)
def _b2(**kw): return _sec("body_vitals", **kw)
def _b3(**kw): return _sec("physio_1", **kw)

def _all_section_ids(pages):
    """Flatten all component_ids from a page list, in order."""
    ids = []
    for p in pages:
        for row in p["rows"]:
            for s in row["sections"]:
                ids.append(s["component_id"])
    return ids


# ── _partition ────────────────────────────────────────────────────────────────

class TestPartition:
    def test_body_measurements_goes_to_bucket1(self):
        b1, b2, b3 = _partition([_sec("body_measurements")])
        assert len(b1) == 1 and not b2 and not b3

    def test_body_vitals_goes_to_bucket2(self):
        b1, b2, b3 = _partition([_sec("body_vitals")])
        assert len(b2) == 1 and not b1 and not b3

    def test_strength_goes_to_bucket2(self):
        b1, b2, b3 = _partition([_sec("strength")])
        assert len(b2) == 1

    def test_physio_components_go_to_bucket3(self):
        sections = [_sec(c) for c in ("physio_1", "physio_2", "physio_3")]
        b1, b2, b3 = _partition(sections)
        assert not b1 and not b2 and len(b3) == 3

    def test_balance_components_go_to_bucket3(self):
        sections = [_sec("balance_open"), _sec("balance_closed")]
        _, _, b3 = _partition(sections)
        assert len(b3) == 2

    def test_unknown_component_id_is_dropped(self):
        b1, b2, b3 = _partition([_sec("unknown_component")])
        assert not b1 and not b2 and not b3

    def test_mixed_input_sorted_to_correct_buckets(self):
        sections = [_sec("body_vitals"), _sec("physio_1"), _sec("body_measurements")]
        b1, b2, b3 = _partition(sections)
        assert len(b1) == 1 and len(b2) == 1 and len(b3) == 1

    def test_selection_order_preserved_within_bucket(self):
        # b2 receives body_vitals before strength, preserving selection order
        sections = [_sec("body_vitals", metric_id="weight"),
                    _sec("physio_1"),
                    _sec("strength", metric_id="bench")]
        _, b2, _ = _partition(sections)
        assert b2[0]["metric_id"] == "weight"
        assert b2[1]["metric_id"] == "bench"

    def test_waist_hip_ratio_goes_to_bucket2_despite_body_measurements_component_id(self):
        # Regression 2026-06-29: WHR is derived from body_measurements but must
        # render in Bucket 2 alongside vitals, never alone on a Bucket 1 page.
        s = _sec("body_measurements", metric_id="waist_hip_ratio")
        b1, b2, b3 = _partition([s])
        assert s in b2 and not b1 and not b3

    def test_bmi_goes_to_bucket2_with_no_component_id(self):
        # Regression 2026-06-29: bmi is derived, may arrive with no component_id.
        s = {"component_id": None, "metric_id": "bmi",
             "rendered_height_px": 300, "rendered_width_px": 964}
        b1, b2, b3 = _partition([s])
        assert s in b2 and not b1 and not b3


# ── _chunk ────────────────────────────────────────────────────────────────────

class TestChunk:
    def test_exact_multiple(self):
        items = list(range(4))
        assert _chunk(items, 2) == [[0, 1], [2, 3]]

    def test_partial_last_group(self):
        items = list(range(5))
        result = _chunk(items, 2)
        assert result == [[0, 1], [2, 3], [4]]

    def test_single_item_with_large_n(self):
        # Single item with n=4 (2×2) → one group of 1, not padded
        result = _chunk(["only"], 4)
        assert result == [["only"]]

    def test_empty_list(self):
        assert _chunk([], 2) == []


# ── _group_to_rows ────────────────────────────────────────────────────────────

class TestGroupToRows:
    def test_1x1_single_item_one_row_full_width(self):
        group = [_sec("body_vitals", height_px=400)]
        rows = _group_to_rows(group, "1x1")
        assert len(rows) == 1
        assert rows[0]["cols"] == 1
        assert rows[0]["row_height_px"] == 400

    def test_1x2_two_items_one_row_two_cols(self):
        group = [_sec("body_vitals", height_px=400), _sec("body_vitals", height_px=350)]
        rows = _group_to_rows(group, "1x2")
        assert len(rows) == 1
        assert rows[0]["cols"] == 2
        assert rows[0]["row_height_px"] == 400   # max of 400 and 350

    def test_2x1_two_items_two_rows_full_width(self):
        group = [_sec("body_vitals", height_px=400), _sec("body_vitals", height_px=300)]
        rows = _group_to_rows(group, "2x1")
        assert len(rows) == 2
        assert rows[0]["cols"] == 1 and rows[1]["cols"] == 1
        assert rows[0]["row_height_px"] == 400
        assert rows[1]["row_height_px"] == 300

    def test_2x2_four_items_two_rows_two_cols(self):
        group = [_sec("body_vitals", height_px=h) for h in [400, 380, 360, 340]]
        rows = _group_to_rows(group, "2x2")
        assert len(rows) == 2
        assert rows[0]["cols"] == 2
        assert rows[0]["row_height_px"] == 400   # max(400, 380)
        assert rows[1]["row_height_px"] == 360   # max(360, 340)

    def test_partial_last_row_in_2x2(self):
        # 3 items at 2×2: row1=2items, row2=1item — not padded to 2
        group = [_sec("body_vitals", height_px=400) for _ in range(3)]
        rows = _group_to_rows(group, "2x2")
        assert len(rows) == 2
        assert len(rows[1]["sections"]) == 1

    def test_sections_passed_through_unchanged(self):
        s = _sec("body_vitals", height_px=400, extra_field="hello")
        rows = _group_to_rows([s], "1x1")
        assert rows[0]["sections"][0]["extra_field"] == "hello"


# ── layout_report — bucket rules ──────────────────────────────────────────────

class TestBucketRules:
    def test_b1_always_full_width_regardless_of_density(self):
        pages = layout_report([_b1(height_px=588)], "2x2")
        assert pages[0]["rows"][0]["cols"] == 1

    def test_b3_always_full_width_regardless_of_density(self):
        pages = layout_report([_b3(height_px=200)], "2x2")
        assert pages[0]["rows"][0]["cols"] == 1

    def test_grid_density_1x2_applies_only_to_b2(self):
        sections = [_b2(height_px=400), _b2(height_px=350)]
        pages = layout_report(sections, "1x2")
        # Both b2 items should appear in one row with 2 columns
        row = pages[0]["rows"][0]
        assert row["cols"] == 2 and len(row["sections"]) == 2

    def test_grid_density_2x2_gives_b2_items_two_cols(self):
        sections = [_b2(height_px=300) for _ in range(4)]
        pages = layout_report(sections, "2x2")
        # All 4 fit on one page (4×300=1200>728 so will split → 2 pages of 2 rows each)
        # Just verify all rows have 2 cols
        for p in pages:
            for row in p["rows"]:
                assert row["cols"] == 2

    def test_b3_never_gridded_even_at_2x2(self):
        sections = [_sec("physio_1", height_px=200), _sec("physio_2", height_px=200)]
        pages = layout_report(sections, "2x2")
        for p in pages:
            for row in p["rows"]:
                assert row["cols"] == 1


# ── layout_report — hard page break ──────────────────────────────────────────

class TestHardPageBreak:
    def test_b3_always_starts_new_page_after_b2(self):
        # b2 item uses 200px (< 728), b3 item uses 174px — together 374 < 728 → would fit
        # but hard break must force b3 onto its own page
        sections = [_b2(height_px=200), _b3(height_px=174)]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 2
        # Page 1 has only the b2 section
        assert pages[0]["rows"][0]["sections"][0]["component_id"] == "body_vitals"
        # Page 2 has only the b3 section
        assert pages[1]["rows"][0]["sections"][0]["component_id"] == "physio_1"

    def test_b3_starts_new_page_even_when_height_trivially_fits(self):
        # b2 uses 1px — maximally undersized, b3 uses 1px; still must hard-break
        sections = [_b2(height_px=1), _b3(height_px=1)]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 2

    def test_b1_b2_can_share_a_page_when_height_allows(self):
        # b1=100px, b2=100px → 200px total < 728 → share page
        sections = [_b1(height_px=100), _b2(height_px=100)]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 1
        assert len(pages[0]["rows"]) == 2


# ── layout_report — height-based pagination ───────────────────────────────────

class TestPagination:
    def test_b2_overflow_starts_new_page(self):
        # Two 1x1 b2 items each at 400px: 400+400=800 > 728 → 2 pages
        sections = [_b2(height_px=400), _b2(height_px=400)]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 2

    def test_b2_items_exactly_at_limit_stay_on_one_page(self):
        # Two items whose combined height equals USABLE_HEIGHT_PX → stays on 1 page
        h = USABLE_HEIGHT_PX // 2
        sections = [_b2(height_px=h), _b2(height_px=h)]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 1

    def test_b3_multi_date_overflow_continues_correctly(self):
        # 3 heatmaps each 300px: 300+300=600<728 (page1 gets 2), 300 → page2
        sections = [_sec(cid, height_px=300) for cid in ("physio_1", "physio_2", "physio_3")]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 2
        # Total sections across all pages = 3, no loss
        assert sum(len(r["sections"]) for p in pages for r in p["rows"]) == 3

    def test_no_sections_duplicated(self):
        # 5 b2 items at 200px each at 1×1: fits 3 on page1 (600<728), then 2 on page2
        sections = [_b2(height_px=200) for _ in range(5)]
        pages = layout_report(sections, "1x1")
        total = sum(len(r["sections"]) for p in pages for r in p["rows"])
        assert total == 5

    def test_oversized_group_placed_on_own_page_without_infinite_loop(self):
        # Single item taller than USABLE_HEIGHT_PX — must still render, not loop
        sections = [_b2(height_px=USABLE_HEIGHT_PX + 100)]
        pages = layout_report(sections, "1x1")
        assert len(pages) == 1
        assert pages[0]["rows"][0]["row_height_px"] == USABLE_HEIGHT_PX + 100

    def test_selection_order_preserved_across_pages(self):
        # b2 sections with distinct metric_ids, overflow to 2 pages
        sections = [
            _sec("body_vitals", height_px=400, metric_id="weight"),
            _sec("body_vitals", height_px=400, metric_id="bmi"),
        ]
        pages = layout_report(sections, "1x1")
        flat = [s for p in pages for r in p["rows"] for s in r["sections"]]
        assert [s["metric_id"] for s in flat] == ["weight", "bmi"]


# ── layout_report — edge cases ────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_list_returns_error_page(self):
        pages = layout_report([], "1x1")
        assert len(pages) == 1
        assert pages[0].get("error") == "empty_report"
        assert pages[0]["rows"] == []

    def test_all_unknown_ids_returns_error_page(self):
        pages = layout_report([_sec("unknown")], "1x1")
        assert pages[0].get("error") == "empty_report"

    def test_empty_b1_no_pages_for_b1(self):
        # Only b2 — should work with 1 page, no crash
        pages = layout_report([_b2(height_px=300)], "1x1")
        assert len(pages) == 1
        assert pages[0]["rows"][0]["sections"][0]["component_id"] == "body_vitals"

    def test_empty_b3_no_b3_pages(self):
        # Only b1 — only 1 page, no phantom b3 page
        pages = layout_report([_b1(height_px=300)], "1x1")
        assert len(pages) == 1
        assert all(s["component_id"] in BUCKET_1_IDS
                   for p in pages for r in p["rows"] for s in r["sections"])

    def test_only_b3_sections_produce_pages(self):
        # b1 and b2 empty — b3 still creates a page
        pages = layout_report([_b3(height_px=200)], "1x1")
        assert len(pages) == 1
        assert pages[0]["rows"][0]["sections"][0]["component_id"] == "physio_1"

    def test_invalid_grid_density_raises(self):
        with pytest.raises(ValueError, match="grid_density"):
            layout_report([_b2()], "3x3")

    def test_page_nums_are_sequential_and_one_indexed(self):
        # Create enough sections to force 3+ pages
        sections = [_b2(height_px=400) for _ in range(3)] + [_b3(height_px=400)]
        pages = layout_report(sections, "1x1")
        assert [p["page_num"] for p in pages] == list(range(1, len(pages) + 1))
