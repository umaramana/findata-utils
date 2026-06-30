"""Tests for gender_image — F05-S06."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gender_image import get_metric_visuals, resolve_asset_group_key


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _img(key, ref):
    return {"asset_group_key": key, "gender": "ANY", "role": "image", "image_ref": ref}

def _icon(key, gender, ref):
    return {"asset_group_key": key, "gender": gender, "role": "icon", "image_ref": ref}

def _grp(metric_id, key):
    return {"metric_id": metric_id, "asset_group_key": key}


# ── resolve_asset_group_key ───────────────────────────────────────────────────

class TestResolveAssetGroupKey:
    def test_no_override_defaults_to_metric_id(self):
        assert resolve_asset_group_key("weight_kg", []) == "weight_kg"

    def test_override_row_returns_asset_group_key(self):
        groups = [_grp("balance_normal_open", "pose_normal")]
        assert resolve_asset_group_key("balance_normal_open", groups) == "pose_normal"

    def test_balance_open_and_closed_map_to_same_shared_key(self):
        groups = [
            _grp("balance_normal_open",   "pose_normal"),
            _grp("balance_normal_closed",  "pose_normal"),
        ]
        assert resolve_asset_group_key("balance_normal_open",  groups) == "pose_normal"
        assert resolve_asset_group_key("balance_normal_closed", groups) == "pose_normal"

    def test_bmi_synthetic_key_defaults_to_self(self):
        # bmi has no metric_master row but uses its own id as the key
        assert resolve_asset_group_key("bmi", []) == "bmi"

    def test_waist_hip_ratio_synthetic_key_defaults_to_self(self):
        assert resolve_asset_group_key("waist_hip_ratio", []) == "waist_hip_ratio"

    def test_empty_override_table_always_defaults(self):
        for mid in ("weight_kg", "bmi", "bp_systol", "physio_1"):
            assert resolve_asset_group_key(mid, []) == mid

    def test_unrelated_override_rows_do_not_affect_other_metrics(self):
        groups = [_grp("balance_normal_open", "pose_normal")]
        assert resolve_asset_group_key("weight_kg", groups) == "weight_kg"

    def test_malformed_override_row_missing_key_falls_back_to_metric_id(self):
        groups = [{"metric_id": "weight_kg", "asset_group_key": ""}]
        assert resolve_asset_group_key("weight_kg", groups) == "weight_kg"


# ── get_metric_visuals — image resolution ─────────────────────────────────────

class TestImageResolution:
    def test_image_found_returns_ref(self):
        lib = [_img("weight_kg", "https://cdn.example.com/scale.jpg")]
        result = get_metric_visuals("weight_kg", "M", lib, [])
        assert result["image_ref"] == "https://cdn.example.com/scale.jpg"

    def test_image_not_found_returns_none(self):
        result = get_metric_visuals("weight_kg", "M", [], [])
        assert result["image_ref"] is None

    def test_image_is_not_gendered_same_ref_for_m_and_f(self):
        lib = [_img("weight_kg", "scale.jpg")]
        assert get_metric_visuals("weight_kg", "M", lib, [])["image_ref"] == "scale.jpg"
        assert get_metric_visuals("weight_kg", "F", lib, [])["image_ref"] == "scale.jpg"

    def test_empty_image_ref_string_returns_none(self):
        lib = [{"asset_group_key": "weight_kg", "gender": "ANY", "role": "image", "image_ref": ""}]
        assert get_metric_visuals("weight_kg", "M", lib, [])["image_ref"] is None

    def test_image_uses_resolved_override_key(self):
        # balance_normal_open → pose_normal; image registered under pose_normal
        lib    = [_img("pose_normal", "pose_normal.jpg")]
        groups = [_grp("balance_normal_open", "pose_normal")]
        result = get_metric_visuals("balance_normal_open", "M", lib, groups)
        assert result["image_ref"] == "pose_normal.jpg"


# ── get_metric_visuals — icon resolution ─────────────────────────────────────

class TestIconResolution:
    def test_exact_gender_match_returns_ref(self):
        lib = [_icon("weight_kg", "M", "icon_m.png"), _icon("weight_kg", "F", "icon_f.png")]
        assert get_metric_visuals("weight_kg", "M", lib, [])["icon_ref"] == "icon_m.png"
        assert get_metric_visuals("weight_kg", "F", lib, [])["icon_ref"] == "icon_f.png"

    def test_any_fallback_used_when_exact_gender_absent(self):
        lib = [_icon("weight_kg", "ANY", "icon_any.png")]
        assert get_metric_visuals("weight_kg", "M", lib, [])["icon_ref"] == "icon_any.png"
        assert get_metric_visuals("weight_kg", "F", lib, [])["icon_ref"] == "icon_any.png"

    def test_exact_gender_preferred_over_any(self):
        lib = [_icon("weight_kg", "ANY", "any.png"), _icon("weight_kg", "M", "male.png")]
        assert get_metric_visuals("weight_kg", "M", lib, [])["icon_ref"] == "male.png"

    def test_icon_not_found_returns_none(self):
        assert get_metric_visuals("weight_kg", "M", [], [])["icon_ref"] is None

    def test_no_icon_for_other_key_does_not_bleed_over(self):
        lib = [_icon("bmi", "M", "bmi_m.png")]
        assert get_metric_visuals("weight_kg", "M", lib, [])["icon_ref"] is None

    def test_icon_uses_resolved_override_key(self):
        lib    = [_icon("pose_normal", "M", "pose_m.png")]
        groups = [_grp("balance_normal_closed", "pose_normal")]
        result = get_metric_visuals("balance_normal_closed", "M", lib, groups)
        assert result["icon_ref"] == "pose_m.png"

    def test_empty_icon_ref_string_returns_none(self):
        lib = [{"asset_group_key": "weight_kg", "gender": "M", "role": "icon", "image_ref": ""}]
        assert get_metric_visuals("weight_kg", "M", lib, [])["icon_ref"] is None


# ── get_metric_visuals — combined / edge cases ────────────────────────────────

class TestGetMetricVisualsCombined:
    def test_returns_both_when_both_present(self):
        lib = [_img("weight_kg", "scale.jpg"), _icon("weight_kg", "F", "f_icon.png")]
        result = get_metric_visuals("weight_kg", "F", lib, [])
        assert result["image_ref"] == "scale.jpg"
        assert result["icon_ref"]  == "f_icon.png"

    def test_returns_both_none_when_library_empty(self):
        result = get_metric_visuals("weight_kg", "M", [], [])
        assert result == {"image_ref": None, "icon_ref": None}

    def test_derived_metric_bmi_resolves_via_own_key(self):
        lib = [_img("bmi", "bmi_chart.png"), _icon("bmi", "M", "bmi_icon_m.png")]
        result = get_metric_visuals("bmi", "M", lib, [])
        assert result["image_ref"] == "bmi_chart.png"
        assert result["icon_ref"]  == "bmi_icon_m.png"

    def test_report_succeeds_with_partially_populated_library(self):
        # Only an image present, no icon — icon_ref must be None, not an error
        lib = [_img("bp_systol", "bp.jpg")]
        result = get_metric_visuals("bp_systol", "F", lib, [])
        assert result["image_ref"] == "bp.jpg"
        assert result["icon_ref"]  is None

    def test_icon_row_does_not_satisfy_image_lookup(self):
        # A row with role='icon' must not be returned as the image_ref
        lib = [_icon("weight_kg", "M", "icon.png")]
        assert get_metric_visuals("weight_kg", "M", lib, [])["image_ref"] is None
