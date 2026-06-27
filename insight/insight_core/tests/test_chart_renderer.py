"""Tests for chart_renderer.render_bar()"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chart_renderer import render_bar, _is_scorecard, _fmt_date_label

PNG_MAGIC = b"\x89PNG"


def is_valid_png(b):
    return isinstance(b, bytes) and len(b) > 4 and b[:4] == PNG_MAGIC


# ── Fixture helpers ───────────────────────────────────────────────────────────

def single_data(readings=None):
    return {
        "label": "Body Weight", "unit": "kg",
        "readings": readings if readings is not None else [
            {"date": "2026-06-01", "value": 82},
            {"date": "2026-06-15", "value": 81},
        ],
    }


def stacked_data(r1=None, r2=None):
    return {
        "series": [
            {"label": "Fat %",    "unit": "%",
             "readings": r1 if r1 is not None else [{"date": "2026-06-01", "value": 26.9}]},
            {"label": "Muscle %", "unit": "%",
             "readings": r2 if r2 is not None else [{"date": "2026-06-01", "value": 29.4}]},
        ]
    }


def grouped_data(metrics=None):
    return {
        "metrics": metrics or [
            {"label": "Neck",  "unit": "in",
             "readings": [{"date": "2026-06-01", "value": 14.5}, {"date": "2026-06-15", "value": 14.4}]},
            {"label": "Waist", "unit": "in",
             "readings": [{"date": "2026-06-01", "value": 34},   {"date": "2026-06-15", "value": 33.5}]},
        ]
    }


# ── horizontal_single ─────────────────────────────────────────────────────────

class TestHorizontalSingle:
    def test_returns_valid_png(self):
        assert is_valid_png(render_bar(single_data(), "horizontal_single"))

    def test_single_reading(self):
        result = render_bar(single_data([{"date": "2026-06-01", "value": 82}]), "horizontal_single")
        assert is_valid_png(result)

    def test_empty_readings_no_data_png(self):
        assert is_valid_png(render_bar(single_data([]), "horizontal_single"))

    def test_none_data_no_data_png(self):
        assert is_valid_png(render_bar(None, "horizontal_single"))

    def test_title_option_accepted(self):
        result = render_bar(single_data(), "horizontal_single", options={"title": "Weight trend"})
        assert is_valid_png(result)


# ── vertical_single ───────────────────────────────────────────────────────────

class TestVerticalSingle:
    def test_returns_valid_png(self):
        assert is_valid_png(render_bar(single_data(), "vertical_single"))

    def test_truncate_y_true_does_not_crash(self):
        result = render_bar(single_data(), "vertical_single", options={"truncate_y": True})
        assert is_valid_png(result)

    def test_truncate_y_false_is_default(self):
        # Zero-floor default — renders without error
        assert is_valid_png(render_bar(single_data(), "vertical_single", options={}))

    def test_single_reading_truncate_y(self):
        # truncate_y with 1 reading should not crash (spread=0 edge case)
        data = single_data([{"date": "2026-06-01", "value": 1650}])
        assert is_valid_png(render_bar(data, "vertical_single", options={"truncate_y": True}))


# ── stacked_pair ──────────────────────────────────────────────────────────────

class TestStackedPair:
    def test_returns_valid_png(self):
        assert is_valid_png(render_bar(stacked_data(), "stacked_pair"))

    def test_multi_date_both_series(self):
        data = stacked_data(
            r1=[{"date": "2026-06-01", "value": 26.9}, {"date": "2026-06-15", "value": 26.5}],
            r2=[{"date": "2026-06-01", "value": 29.4}, {"date": "2026-06-15", "value": 30.1}],
        )
        assert is_valid_png(render_bar(data, "stacked_pair"))

    def test_both_series_empty_returns_no_data_png(self):
        # No crash — returns the "No data" placeholder PNG
        assert is_valid_png(render_bar(stacked_data(r1=[], r2=[]), "stacked_pair"))

    def test_single_series_raises(self):
        data = {"series": [{"label": "Fat %", "unit": "%",
                            "readings": [{"date": "2026-06-01", "value": 26.9}]}]}
        with pytest.raises(ValueError, match="2 series"):
            render_bar(data, "stacked_pair")

    def test_no_series_raises(self):
        with pytest.raises(ValueError, match="2 series"):
            render_bar({"series": []}, "stacked_pair")

    def test_asymmetric_dates_handled(self):
        # s1 has data on June 1 only; s2 on June 1 and June 15
        data = stacked_data(
            r1=[{"date": "2026-06-01", "value": 26.9}],
            r2=[{"date": "2026-06-01", "value": 29.4}, {"date": "2026-06-15", "value": 30.1}],
        )
        assert is_valid_png(render_bar(data, "stacked_pair"))


# ── grouped_multi ─────────────────────────────────────────────────────────────
# Layout: X = metric labels, colors = date series (one bar per date per metric)
# Matches Looker Studio body measurements chart exactly.

class TestGroupedMulti:
    def test_multi_date_multi_metric_renders(self):
        # 2 dates × 2 metrics — 4 bars, metrics on X, dates as color series
        assert is_valid_png(render_bar(grouped_data(), "grouped_multi"))

    def test_five_dates_multi_metric_renders(self):
        # Stress test — 5 dates × 8 metrics like Dr Praveena sample
        metrics = [
            {"label": f"Metric {c}", "unit": "in", "readings": [
                {"date": f"202{y}-01-01", "value": 10 + i + y}
                for y in range(5)
            ]}
            for i, c in enumerate(["a Neck","b Waist","c Abdomen","d Hips",
                                    "e Thighs","f Calves","g Arms","h Fore Arms"])
        ]
        assert is_valid_png(render_bar({"metrics": metrics}, "grouped_multi"))

    def test_single_date_multi_metric_renders(self):
        # First-time report: 1 date × many metrics — all bars same colour (date 1 = #880e4f)
        data = {"metrics": [
            {"label": "a Neck",  "unit": "in", "readings": [{"date": "2026-06-01", "value": 14.5}]},
            {"label": "b Waist", "unit": "in", "readings": [{"date": "2026-06-01", "value": 34}]},
        ]}
        assert is_valid_png(render_bar(data, "grouped_multi"))

    def test_unit_note_option_accepted(self):
        result = render_bar(grouped_data(), "grouped_multi",
                            options={"unit_note": "Measurement units: Inches / Decimal Precision - 0"})
        assert is_valid_png(result)

    def test_title_option_accepted(self):
        assert is_valid_png(render_bar(grouped_data(), "grouped_multi",
                                       options={"title": "Body Measurements"}))

    def test_single_date_single_metric_takes_scorecard_path(self):
        data = {"metrics": [
            {"label": "Bench Press", "unit": "reps",
             "readings": [{"date": "2026-06-01", "value": 12}]},
        ]}
        assert is_valid_png(render_bar(data, "grouped_multi"))

    def test_no_readings_returns_no_data_png(self):
        data = {"metrics": [{"label": "Neck", "unit": "in", "readings": []}]}
        assert is_valid_png(render_bar(data, "grouped_multi"))

    def test_empty_metrics_returns_no_data_png(self):
        assert is_valid_png(render_bar({"metrics": []}, "grouped_multi"))


# ── _fmt_date_label ───────────────────────────────────────────────────────────

class TestFmtDateLabel:
    def test_standard_date_formats_as_mon_yyyy(self):
        assert _fmt_date_label("2026-06-15") == "Jun 2026"

    def test_january(self):
        assert _fmt_date_label("2025-01-10") == "Jan 2025"

    def test_invalid_passes_through(self):
        assert _fmt_date_label("2019") == "2019"

    def test_none_passes_through(self):
        assert _fmt_date_label(None) is None


# ── _is_scorecard (pure function) ─────────────────────────────────────────────

class TestIsScorecard:
    def test_one_metric_one_date_is_scorecard(self):
        data = {"metrics": [{"label": "X", "readings": [{"date": "2026-06-01", "value": 12}]}]}
        assert _is_scorecard(data) is True

    def test_one_metric_two_dates_is_not_scorecard(self):
        data = {"metrics": [{"label": "X", "readings": [
            {"date": "2026-06-01", "value": 12},
            {"date": "2026-06-15", "value": 13},
        ]}]}
        assert _is_scorecard(data) is False

    def test_two_metrics_one_date_is_not_scorecard(self):
        data = {"metrics": [
            {"label": "X", "readings": [{"date": "2026-06-01", "value": 12}]},
            {"label": "Y", "readings": [{"date": "2026-06-01", "value": 14}]},
        ]}
        assert _is_scorecard(data) is False

    def test_empty_metrics_is_not_scorecard(self):
        assert _is_scorecard({"metrics": []}) is False

    def test_metric_with_no_readings_ignored(self):
        # Only the populated metric counts — empty-readings metric is ignored
        data = {"metrics": [
            {"label": "X", "readings": []},
            {"label": "Y", "readings": [{"date": "2026-06-01", "value": 12}]},
        ]}
        assert _is_scorecard(data) is True


# ── Unknown mode ──────────────────────────────────────────────────────────────

class TestUnknownMode:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            render_bar(single_data(), "donut")
