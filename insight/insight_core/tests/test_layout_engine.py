"""Tests for layout_engine.layout_report() — F05-S04 (single-flow, no pagination)."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from layout_engine import (
    layout_report, _partition, _chunk,
    BUCKET_1_IDS, BUCKET_2_IDS, BUCKET_3_IDS,
    BUCKET_2_DERIVED_METRIC_IDS,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _sec(component_id, **kwargs):
    return {"component_id": component_id, **kwargs}

def _b1(**kw): return _sec("body_measurements", **kw)
def _b2(**kw): return _sec("body_vitals", **kw)
def _b3(**kw): return _sec("physio_1", **kw)


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
        sections = [_sec("body_vitals", metric_id="weight"),
                    _sec("physio_1"),
                    _sec("strength", metric_id="bench")]
        _, b2, _ = _partition(sections)
        assert b2[0]["metric_id"] == "weight"
        assert b2[1]["metric_id"] == "bench"

    def test_waist_hip_ratio_goes_to_bucket2_despite_body_measurements_component_id(self):
        s = _sec("body_measurements", metric_id="waist_hip_ratio")
        b1, b2, b3 = _partition([s])
        assert s in b2 and not b1 and not b3

    def test_bmi_goes_to_bucket2_with_no_component_id(self):
        s = {"component_id": None, "metric_id": "bmi"}
        b1, b2, b3 = _partition([s])
        assert s in b2 and not b1 and not b3


# ── _chunk ────────────────────────────────────────────────────────────────────

class TestChunk:
    def test_exact_multiple(self):
        assert _chunk(list(range(4)), 2) == [[0, 1], [2, 3]]

    def test_partial_last_group(self):
        assert _chunk(list(range(5)), 2) == [[0, 1], [2, 3], [4]]

    def test_single_item_with_large_n(self):
        assert _chunk(["only"], 4) == [["only"]]

    def test_empty_list(self):
        assert _chunk([], 2) == []


# ── layout_report — bucket placement ─────────────────────────────────────────

class TestBucketRules:
    def test_b1_lands_in_bucket1(self):
        layout = layout_report([_b1()], "2x2")
        assert "error" not in layout
        assert len(layout["bucket1"]) == 1
        assert not layout["bucket2_groups"]
        assert not layout["bucket3"]

    def test_b3_lands_in_bucket3(self):
        layout = layout_report([_b3()], "2x2")
        assert len(layout["bucket3"]) == 1
        assert not layout["bucket1"]
        assert not layout["bucket2_groups"]

    def test_b3_never_gridded_regardless_of_density(self):
        sections = [_sec("physio_1"), _sec("physio_2")]
        layout = layout_report(sections, "2x2")
        assert len(layout["bucket3"]) == 2
        assert not layout["bucket2_groups"]

    def test_density_1x2_chunks_b2_into_pairs(self):
        sections = [_b2(), _b2(), _b2()]
        layout = layout_report(sections, "1x2")
        assert len(layout["bucket2_groups"]) == 2   # [[b2,b2],[b2]]
        assert len(layout["bucket2_groups"][0]) == 2
        assert len(layout["bucket2_groups"][1]) == 1
        assert layout["cols_per_row"] == 2

    def test_density_2x2_chunks_b2_into_groups_of_4(self):
        sections = [_b2() for _ in range(5)]
        layout = layout_report(sections, "2x2")
        assert len(layout["bucket2_groups"]) == 2   # [[4],[1]]
        assert len(layout["bucket2_groups"][0]) == 4
        assert layout["cols_per_row"] == 2

    def test_density_1x1_one_item_per_group(self):
        sections = [_b2(), _b2()]
        layout = layout_report(sections, "1x1")
        assert len(layout["bucket2_groups"]) == 2
        assert layout["cols_per_row"] == 1

    def test_density_2x1_two_items_per_group_one_col(self):
        sections = [_b2(), _b2(), _b2()]
        layout = layout_report(sections, "2x1")
        assert len(layout["bucket2_groups"]) == 2   # [[b2,b2],[b2]]
        assert layout["cols_per_row"] == 1

    def test_sections_passed_through_unchanged(self):
        s = _b2(extra_field="hello")
        layout = layout_report([s], "1x1")
        assert layout["bucket2_groups"][0][0]["extra_field"] == "hello"

    def test_selection_order_preserved_across_buckets(self):
        s1 = _sec("body_vitals", metric_id="weight")
        s2 = _sec("body_vitals", metric_id="bmi")
        layout = layout_report([s1, s2], "1x1")
        flat = [s for g in layout["bucket2_groups"] for s in g]
        assert [s["metric_id"] for s in flat] == ["weight", "bmi"]


# ── layout_report — edge cases ────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_list_returns_error(self):
        layout = layout_report([], "1x1")
        assert layout.get("error") == "empty_report"
        assert layout["bucket1"] == []
        assert layout["bucket2_groups"] == []
        assert layout["bucket3"] == []

    def test_all_unknown_ids_returns_error(self):
        layout = layout_report([_sec("unknown")], "1x1")
        assert layout.get("error") == "empty_report"

    def test_only_b2_no_b1_or_b3(self):
        layout = layout_report([_b2()], "1x1")
        assert "error" not in layout
        assert not layout["bucket1"]
        assert len(layout["bucket2_groups"]) == 1
        assert not layout["bucket3"]

    def test_only_b1_no_b2_or_b3(self):
        layout = layout_report([_b1()], "1x1")
        assert "error" not in layout
        assert len(layout["bucket1"]) == 1
        assert not layout["bucket2_groups"]
        assert not layout["bucket3"]

    def test_only_b3_no_b1_or_b2(self):
        layout = layout_report([_b3()], "1x1")
        assert "error" not in layout
        assert len(layout["bucket3"]) == 1

    def test_all_three_buckets_populated(self):
        layout = layout_report([_b1(), _b2(), _b3()], "1x1")
        assert len(layout["bucket1"]) == 1
        assert len(layout["bucket2_groups"]) == 1
        assert len(layout["bucket3"]) == 1

    def test_invalid_grid_density_raises(self):
        with pytest.raises(ValueError, match="grid_density"):
            layout_report([_b2()], "3x3")


# ── 3x2 density ──────────────────────────────────────────────────────────────

class TestDensity3x2:
    def test_3x2_chunks_6_items_into_one_group(self):
        # All 6 real Bucket-2 items selected → one clean 3-col × 2-row group.
        sections = [
            _sec("body_vitals",       metric_id="weight_kg"),
            _sec("body_measurements", metric_id="waist_hip_ratio"),
            _sec("body_vitals",       metric_id="bmi"),
            _sec("body_vitals",       metric_id="bp_systol"),
            _sec("body_vitals",       metric_id="pulse"),
            _sec("body_vitals",       metric_id="fat_pct"),
        ]
        layout = layout_report(sections, "3x2")
        assert len(layout["bucket2_groups"]) == 1
        assert len(layout["bucket2_groups"][0]) == 6
        assert layout["cols_per_row"] == 3

    def test_3x2_partial_last_group(self):
        # 7 items → [6, 1] not a stretched [4+3] or similar.
        sections = [_b2() for _ in range(7)]
        layout = layout_report(sections, "3x2")
        assert len(layout["bucket2_groups"]) == 2
        assert len(layout["bucket2_groups"][0]) == 6
        assert len(layout["bucket2_groups"][1]) == 1

    def test_3x2_with_full_b2_set_no_b1_b3_overlap(self):
        sections = [_b1()] + [_b2() for _ in range(6)] + [_b3()]
        layout = layout_report(sections, "3x2")
        assert len(layout["bucket1"]) == 1
        assert len(layout["bucket2_groups"]) == 1
        assert len(layout["bucket2_groups"][0]) == 6
        assert len(layout["bucket3"]) == 1
