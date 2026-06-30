"""Tests for report_pdf.generate_full_report() — F05-S05 (HTML/Puppeteer)."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report_pdf import generate_full_report, _versioned_path, _label_unit, _render_template
from chart_renderer import render_bar_svg
from layout_engine import layout_report

PDF_MAGIC = b"%PDF"


def is_valid_pdf(b):
    return isinstance(b, bytes) and b[:4] == PDF_MAGIC


# ── Shared test fixtures ──────────────────────────────────────────────────────

def _reading(client_id, component, metric, date, value):
    return {"client_id": client_id, "component": component, "metric": metric,
            "date": date, "value": value}


def _vitals_readings(client_id="vip_001"):
    return [
        _reading(client_id, "body_vitals", "weight_kg",  "2026-01-01", 82.0),
        _reading(client_id, "body_vitals", "weight_kg",  "2026-06-01", 80.5),
        _reading(client_id, "body_vitals", "height_cm",  "2026-01-01", 175.0),
        _reading(client_id, "body_vitals", "height_cm",  "2026-06-01", 175.0),
        _reading(client_id, "body_vitals", "pulse",      "2026-01-01", 72),
        _reading(client_id, "body_vitals", "fat_pct",    "2026-01-01", 26.9),
        _reading(client_id, "body_vitals", "muscle_pct", "2026-01-01", 29.4),
        _reading(client_id, "body_vitals", "bp_systol",  "2026-01-01", 120),
        _reading(client_id, "body_vitals", "bp_diastol", "2026-01-01", 80),
    ]


def _measurements_readings(client_id="vip_001"):
    return [
        _reading(client_id, "body_measurements", "neck_cm",    "2026-01-01", 38),
        _reading(client_id, "body_measurements", "waist",      "2026-01-01", 88),
        _reading(client_id, "body_measurements", "hips",       "2026-01-01", 96),
        _reading(client_id, "body_measurements", "neck_cm",    "2026-06-01", 37.5),
        _reading(client_id, "body_measurements", "waist",      "2026-06-01", 85),
        _reading(client_id, "body_measurements", "hips",       "2026-06-01", 94),
    ]


def _physio_readings(client_id="vip_001"):
    return [
        _reading(client_id, "physio_1", "pushups",   "2026-01-01", 20),
        _reading(client_id, "physio_1", "situps",    "2026-01-01", 25),
        _reading(client_id, "physio_1", "pushups",   "2026-06-01", 24),
        _reading(client_id, "physio_1", "situps",    "2026-06-01", 28),
    ]


def _full_readings(client_id="vip_001"):
    return _vitals_readings(client_id) + _measurements_readings(client_id) + _physio_readings(client_id)


def _client_profile():
    return {"gender": "male", "dob": "1990-06-15"}


# ── Full pipeline — valid PDF output ─────────────────────────────────────────

class TestFullPipeline:
    def test_complete_data_produces_pdf(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals", "body_measurements", "physio_1"],
            grid_density="1x1",
            all_readings=_full_readings(),
            client_profile=_client_profile(),
            output_dir=str(tmp_path),
        )
        assert "error" not in result, result
        assert "path" in result
        assert os.path.exists(result["path"])
        with open(result["path"], "rb") as f:
            assert is_valid_pdf(f.read())

    def test_result_includes_page_count_and_version(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"],
            grid_density="1x1",
            all_readings=_vitals_readings(),
            output_dir=str(tmp_path),
        )
        assert result["version"] == 1
        assert result["pages"] >= 1

    def test_vitals_only_produces_pdf(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"],
            grid_density="2x2",
            all_readings=_vitals_readings(),
            client_profile=_client_profile(),
            output_dir=str(tmp_path),
        )
        assert "error" not in result
        assert os.path.exists(result["path"])

    def test_physio_only_produces_pdf(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["physio_1"],
            grid_density="1x1",
            all_readings=_physio_readings(),
            output_dir=str(tmp_path),
        )
        assert "error" not in result
        assert os.path.exists(result["path"])


# ── Graceful degradation ──────────────────────────────────────────────────────

class TestGracefulDegradation:
    def test_missing_component_data_still_generates(self, tmp_path):
        # physio_1 selected but has no readings → body_vitals still renders
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals", "physio_1"],
            grid_density="1x1",
            all_readings=_vitals_readings(),   # no physio readings
            output_dir=str(tmp_path),
        )
        assert "error" not in result
        assert os.path.exists(result["path"])

    def test_empty_asset_library_does_not_block(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"],
            grid_density="1x1",
            all_readings=_vitals_readings(),
            asset_library=[],
            metric_asset_groups=[],
            output_dir=str(tmp_path),
        )
        assert "error" not in result
        assert os.path.exists(result["path"])

    def test_no_client_profile_skips_bmr_gracefully(self, tmp_path):
        # No client_profile → BMR not computed, but report still generates
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"],
            grid_density="1x1",
            all_readings=_vitals_readings(),
            client_profile=None,
            output_dir=str(tmp_path),
        )
        assert "error" not in result

    def test_female_client_produces_pdf(self, tmp_path):
        readings = _vitals_readings(client_id="vip_002")
        result = generate_full_report(
            client_id="vip_002", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"],
            grid_density="1x1",
            all_readings=readings,
            client_profile={"gender": "female", "dob": "1985-03-20"},
            output_dir=str(tmp_path),
        )
        assert "error" not in result


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_no_readings_returns_error_dict(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"],
            grid_density="1x1",
            all_readings=[],
            output_dir=str(tmp_path),
        )
        assert "error" in result
        assert "path" not in result

    def test_no_components_selected_returns_error(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=[],
            grid_density="1x1",
            all_readings=_vitals_readings(),
            output_dir=str(tmp_path),
        )
        assert "error" in result

    def test_out_of_range_readings_returns_error(self, tmp_path):
        # All readings are from 2025, but date range is 2026
        readings = [_reading("vip_001", "body_vitals", "weight_kg", "2025-01-01", 82)]
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-12-31",
            component_ids=["body_vitals"],
            grid_density="1x1",
            all_readings=readings,
            output_dir=str(tmp_path),
        )
        assert "error" in result


# ── Versioning ────────────────────────────────────────────────────────────────

class TestVersioning:
    def test_first_run_is_v1(self, tmp_path):
        result = generate_full_report(
            client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
            component_ids=["body_vitals"], grid_density="1x1",
            all_readings=_vitals_readings(), output_dir=str(tmp_path),
        )
        assert result["version"] == 1
        assert result["path"].endswith("_v1.pdf")

    def test_second_run_increments_to_v2(self, tmp_path):
        kw = dict(client_id="vip_001", date_from="2026-01-01", date_to="2026-06-30",
                  component_ids=["body_vitals"], grid_density="1x1",
                  all_readings=_vitals_readings(), output_dir=str(tmp_path))
        generate_full_report(**kw)
        result2 = generate_full_report(**kw)
        assert result2["version"] == 2
        assert result2["path"].endswith("_v2.pdf")

    def test_different_clients_dont_interfere(self, tmp_path):
        kw = dict(date_from="2026-01-01", date_to="2026-06-30",
                  component_ids=["body_vitals"], grid_density="1x1",
                  output_dir=str(tmp_path))
        r1 = generate_full_report(client_id="vip_001",
                                   all_readings=_vitals_readings("vip_001"), **kw)
        r2 = generate_full_report(client_id="vip_002",
                                   all_readings=_vitals_readings("vip_002"), **kw)
        assert r1["version"] == 1
        assert r2["version"] == 1  # different client, version resets

    def test_versioned_path_helper(self, tmp_path):
        path1, v1 = _versioned_path(str(tmp_path), "vip_001", "2026-06-30")
        assert v1 == 1 and not os.path.exists(path1)
        open(path1, "w").close()   # simulate first file
        path2, v2 = _versioned_path(str(tmp_path), "vip_001", "2026-06-30")
        assert v2 == 2 and path2 != path1


# ── SVG quality regression — charts must be vector, not raster ───────────────
# Catching the PNG-quality regression by construction: SVG cannot blur the way
# the old PNG-resize path did.

class TestSvgOutput:
    def test_render_bar_svg_returns_svg_string(self):
        readings = [{"date": "2026-01-01", "value": 80.5},
                    {"date": "2026-06-01", "value": 78.0}]
        result = render_bar_svg(
            {"label": "Body Weight", "unit": "kg", "readings": readings},
            "horizontal_single",
        )
        assert isinstance(result, str)
        assert "<svg" in result

    def test_render_bar_svg_grouped_multi_returns_svg(self):
        result = render_bar_svg(
            {"metrics": [{"label": "Waist", "unit": "cm",
                          "readings": [{"date": "2026-01-01", "value": 88}]}]},
            "grouped_multi",
        )
        assert "<svg" in result

    def test_svg_embedded_in_html_template(self):
        readings = [{"date": "2026-01-01", "value": 80.5}]
        svg = render_bar_svg(
            {"label": "Body Weight", "unit": "kg", "readings": readings},
            "horizontal_single",
        )
        layout = {
            "bucket1": [],
            "bucket2_groups": [[{"component_id": "body_vitals", "metric_id": "weight_kg",
                                  "title": "Body Weight", "chart_svg": svg}]],
            "bucket3": [],
            "cols_per_row": 1,
        }
        html = _render_template("Test Client", "Jun 2026", layout)
        assert "<svg" in html   # SVG is embedded inline, not as a raster image src

    def test_render_bar_png_still_returns_bytes(self):
        """render_bar() (PNG path) must be unaffected by the SVG flag toggle."""
        from chart_renderer import render_bar
        readings = [{"date": "2026-01-01", "value": 80.5}]
        result = render_bar(
            {"label": "Body Weight", "unit": "kg", "readings": readings},
            "horizontal_single",
        )
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_render_circular_gauge_returns_svg(self):
        """Pulse must render as a donut/ring, not a bar — corrected 2026-06-30."""
        readings = [{"date": "2026-01-01", "value": 72}]
        result = render_bar_svg(
            {"label": "Pulse", "unit": "bpm", "readings": readings},
            "circular_gauge",
        )
        assert isinstance(result, str)
        assert "<svg" in result


# ── _label_unit ───────────────────────────────────────────────────────────────

class TestLabelUnit:
    def test_known_metric_returns_correct_tuple(self):
        assert _label_unit("weight_kg") == ("Body Weight", "kg")
        assert _label_unit("bmi") == ("BMI", "kg/m²")
        assert _label_unit("pulse") == ("Pulse", "bpm")

    def test_unknown_metric_returns_title_cased_id_and_empty_unit(self):
        label, unit = _label_unit("some_custom_metric")
        assert label == "Some Custom Metric"
        assert unit == ""
