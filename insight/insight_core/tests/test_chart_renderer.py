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


# ── Cross-chart-type width consistency (regression) ──────────────────────────
# Every bucket-2 chart (horizontal_single, vertical_single, stacked_pair,
# circular_gauge) is stretched into the SAME fixed-width CSS grid column, so
# they must all render at the same native width_in -- otherwise identical
# point-size fonts/bars come out visibly different sizes once the browser
# scales each SVG to fit. This broke twice in one session: once via
# per-chart-type auto-width formulas, once via circular_gauge's figsize being
# hardcoded to 4.0in while everything else had been unified to 3.0in.

class TestBucket2WidthConsistency:
    def _figsize_used(self, monkeypatch, render_fn):
        # Intercept the real figsize argument passed to matplotlib, instead
        # of measuring the saved PNG's width — a saved PNG uses
        # bbox_inches="tight", which pads outward to include content that
        # overflows the axes (e.g. circular_gauge's legend sits outside the
        # axes via bbox_to_anchor), so its width is NOT the figsize and
        # isn't a reliable regression signal on its own.
        import matplotlib.pyplot as plt
        captured = {}
        real_subplots = plt.subplots
        def spy_subplots(*args, **kwargs):
            captured["figsize"] = kwargs.get("figsize", args[0] if args else None)
            return real_subplots(*args, **kwargs)
        monkeypatch.setattr(plt, "subplots", spy_subplots)
        render_fn()
        return captured["figsize"]

    def test_all_bucket2_chart_types_share_native_width(self, monkeypatch):
        h = self._figsize_used(monkeypatch, lambda: render_bar(single_data(), "horizontal_single"))
        v = self._figsize_used(monkeypatch, lambda: render_bar(single_data(), "vertical_single"))
        sp = self._figsize_used(monkeypatch, lambda: render_bar(stacked_data(), "stacked_pair"))
        cg = self._figsize_used(monkeypatch, lambda: render_bar(single_data(), "circular_gauge"))
        assert h[0] == pytest.approx(v[0]), "horizontal_single vs vertical_single width_in mismatch: {} vs {}".format(h[0], v[0])
        assert h[0] == pytest.approx(sp[0]), "horizontal_single vs stacked_pair width_in mismatch: {} vs {}".format(h[0], sp[0])
        assert h[0] == pytest.approx(cg[0]), "horizontal_single vs circular_gauge width_in mismatch: {} vs {}".format(h[0], cg[0])

    def test_explicit_width_in_override_still_respected(self, monkeypatch):
        # options["width_in"] must still work -- the fix pins the DEFAULT,
        # not the ability to override per-call.
        fs = self._figsize_used(monkeypatch, lambda: render_bar(single_data(), "horizontal_single", {"width_in": 5.0}))
        assert fs[0] == pytest.approx(5.0)


class TestBucket1Bucket2RatioConsistency:
    """Guards the bug that recurred 3 times in one session: _BUCKET1_WIDTH_IN
    was guessed (8.0, then 12.0, then 8.73) without actually being computed
    from the same container_px/width_in ratio as _BUCKET2_WIDTH_IN, so
    Body Measurements' font/bar scale kept drifting from every other chart.
    These container pixel widths are documented in chart_renderer.py's
    "Container widths" comment block — if the CSS layout changes (grid gap,
    .chart-visuals width, .section padding, or .bucket1 .chart-cell
    max-width), update BOTH the comment and these two numbers together."""

    BUCKET2_CONTAINER_PX = 198   # bucket-2 grid cell chart-cell width
    BUCKET1_CONTAINER_PX = 576   # .bucket1 .chart-cell max-width

    def test_bucket_width_ratios_match(self):
        from chart_renderer import _BUCKET1_WIDTH_IN, _BUCKET2_WIDTH_IN
        ratio2 = self.BUCKET2_CONTAINER_PX / _BUCKET2_WIDTH_IN
        ratio1 = self.BUCKET1_CONTAINER_PX / _BUCKET1_WIDTH_IN
        assert ratio1 == pytest.approx(ratio2, rel=0.01), (
            f"bucket-1 px/in ratio ({ratio1:.1f}) != bucket-2's ({ratio2:.1f}) — "
            f"_BUCKET1_WIDTH_IN ({_BUCKET1_WIDTH_IN}) wasn't computed from "
            f"BUCKET1_CONTAINER_PX ({self.BUCKET1_CONTAINER_PX}), fonts/bars will "
            "render at a different scale than every bucket-2 chart"
        )
