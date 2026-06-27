"""Tests for table_heatmap.render_table_heatmap()"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from table_heatmap import render_table_heatmap, _row_range, _prepare_cells

PNG_MAGIC = b"\x89PNG"


def is_valid_png(b):
    return isinstance(b, bytes) and len(b) > 4 and b[:4] == PNG_MAGIC


def _data(*metrics):
    return {"metrics": list(metrics)}


def _metric(label, readings, unit="reps"):
    return {"label": label, "unit": unit, "readings": readings}


def _r(date, value):
    return {"date": date, "value": value}


# ── PNG validity ──────────────────────────────────────────────────────────────

class TestRendersValidPng:
    def test_single_metric_multi_date(self):
        data = _data(_metric("Physio 1", [_r("2026-01-01", 20), _r("2026-02-01", 30)]))
        assert is_valid_png(render_table_heatmap(data))

    def test_multi_metric_multi_date(self):
        data = _data(
            _metric("Physio 1", [_r("2026-01-01", 20), _r("2026-02-01", 30)]),
            _metric("Balance Open", [_r("2026-01-01", 45)], unit="s"),
            _metric("Physio 2", [_r("2026-02-01", 15)]),
        )
        assert is_valid_png(render_table_heatmap(data))

    def test_title_option_accepted(self):
        data = _data(_metric("Physio 1", [_r("2026-01-01", 20)]))
        assert is_valid_png(render_table_heatmap(data, options={"title": "Strength"}))

    def test_custom_color_accepted(self):
        data = _data(_metric("P1", [_r("2026-01-01", 10), _r("2026-02-01", 20)]))
        assert is_valid_png(render_table_heatmap(data, options={"colors": ["#880e4f"]}))


# ── _row_range ────────────────────────────────────────────────────────────────

class TestRowRange:
    def test_multi_date_returns_min_max(self):
        m = _metric("P1", [_r("2026-01-01", 10), _r("2026-02-01", 40), _r("2026-03-01", 25)])
        rmin, rmax = _row_range(m)
        assert rmin == 10
        assert rmax == 40

    def test_single_date_returns_none_none(self):
        m = _metric("P1", [_r("2026-01-01", 35)])
        assert _row_range(m) == (None, None)

    def test_zero_readings_returns_none_none(self):
        m = _metric("P1", [])
        assert _row_range(m) == (None, None)

    def test_equal_values_max_equals_min(self):
        m = _metric("P1", [_r("2026-01-01", 30), _r("2026-02-01", 30)])
        rmin, rmax = _row_range(m)
        # rmax == rmin → fill bar suppressed (rmax > rmin is False)
        assert rmin == rmax == 30


# ── _prepare_cells ────────────────────────────────────────────────────────────

class TestPrepareCells:
    def test_min_value_has_fill_prop_zero(self):
        m = _metric("P1", [_r("2026-01-01", 10), _r("2026-02-01", 50)])
        cells = _prepare_cells([m], ["2026-01-01", "2026-02-01"])
        min_cell = next(c for c in cells if c["date"] == "2026-01-01")
        assert min_cell["fill_prop"] == pytest.approx(0.0)

    def test_max_value_has_fill_prop_one(self):
        m = _metric("P1", [_r("2026-01-01", 10), _r("2026-02-01", 50)])
        cells = _prepare_cells([m], ["2026-01-01", "2026-02-01"])
        max_cell = next(c for c in cells if c["date"] == "2026-02-01")
        assert max_cell["fill_prop"] == pytest.approx(1.0)

    def test_midpoint_value_has_fill_prop_half(self):
        m = _metric("P1", [_r("2026-01-01", 0), _r("2026-02-01", 50), _r("2026-03-01", 100)])
        cells = _prepare_cells([m], ["2026-01-01", "2026-02-01", "2026-03-01"])
        mid_cell = next(c for c in cells if c["date"] == "2026-02-01")
        assert mid_cell["fill_prop"] == pytest.approx(0.5)

    def test_missing_date_is_no_data_type(self):
        m = _metric("P1", [_r("2026-01-01", 20), _r("2026-03-01", 40)])
        cells = _prepare_cells([m], ["2026-01-01", "2026-02-01", "2026-03-01"])
        missing = next(c for c in cells if c["date"] == "2026-02-01")
        assert missing["type"] == "no_data"
        assert missing["value"] is None
        assert missing["fill_prop"] is None

    def test_single_value_fill_prop_is_one(self):
        # Single value in table → no range → fill_prop defaults to 1.0 (full shade)
        m = _metric("P1", [_r("2026-01-01", 35)])
        cells = _prepare_cells([m], ["2026-01-01"])
        assert cells[0]["type"] == "value"
        assert cells[0]["fill_prop"] == pytest.approx(1.0)

    def test_equal_values_fill_prop_is_one(self):
        # All values identical → no range → fill_prop defaults to 1.0
        m = _metric("P1", [_r("2026-01-01", 30), _r("2026-02-01", 30)])
        cells = _prepare_cells([m], ["2026-01-01", "2026-02-01"])
        assert all(c["fill_prop"] == pytest.approx(1.0) for c in cells)

    def test_col_i_matches_date_position(self):
        m = _metric("P1", [_r("2026-01-01", 10), _r("2026-03-01", 20)])
        all_dates = ["2026-01-01", "2026-02-01", "2026-03-01"]
        cells = _prepare_cells([m], all_dates)
        assert cells[0]["col_i"] == 0
        assert cells[1]["col_i"] == 1  # no_data
        assert cells[2]["col_i"] == 2


# ── Empty / degenerate input ──────────────────────────────────────────────────

class TestEmptyInput:
    def test_none_data(self):
        assert is_valid_png(render_table_heatmap(None))

    def test_empty_metrics_list(self):
        assert is_valid_png(render_table_heatmap({"metrics": []}))

    def test_no_metrics_key(self):
        assert is_valid_png(render_table_heatmap({}))

    def test_metric_with_no_readings(self):
        data = _data(_metric("P1", []))
        assert is_valid_png(render_table_heatmap(data))
