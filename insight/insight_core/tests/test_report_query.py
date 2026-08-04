"""Tests for report_query.build_report_payload()"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report_query import build_report_payload, build_nudge_payload

CLIENT = "vip"
COMP_BV = "body_vitals"
COMP_BM = "body_measurements"
COMP_P1 = "physio_1"

RANGE_FROM = "2026-06-01"
RANGE_TO   = "2026-06-30"


def _r(date, component, metric, value, client_id=CLIENT):
    return {"client_id": client_id, "date": date, "component": component, "metric": metric, "value": value}


class TestEmptyRange:
    def test_no_readings_in_range_returns_error(self):
        readings = [_r("2026-01-01", COMP_BV, "weight_kg", 80)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        assert "error" in result

    def test_no_components_selected_returns_error(self):
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [], [])
        assert "error" in result

    def test_readings_for_other_client_not_included(self):
        readings = [_r(RANGE_FROM, COMP_BV, "weight_kg", 80, client_id="other_client")]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        assert "error" in result


class TestSingleComponent:
    def test_readings_returned_sorted_by_date(self):
        readings = [
            _r("2026-06-15", COMP_BV, "weight_kg", 81),
            _r("2026-06-01", COMP_BV, "weight_kg", 82),
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        assert "error" not in result
        wkg = result["components"][COMP_BV]["metrics"]["weight_kg"]
        assert wkg["readings"][0]["date"] == "2026-06-01"
        assert wkg["readings"][1]["date"] == "2026-06-15"
        assert len(wkg["readings"]) == 2

    def test_reading_outside_range_excluded(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 82),
            _r("2026-07-01", COMP_BV, "weight_kg", 79),  # outside range
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        wkg = result["components"][COMP_BV]["metrics"]["weight_kg"]
        assert len(wkg["readings"]) == 1
        assert wkg["readings"][0]["date"] == "2026-06-01"


class TestMultipleComponents:
    def test_both_components_populated(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 82),
            _r("2026-06-01", COMP_BM, "waist", 34),
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV, COMP_BM], readings)
        assert "error" not in result
        assert COMP_BV in result["components"]
        assert COMP_BM in result["components"]
        assert "weight_kg" in result["components"][COMP_BV]["metrics"]
        assert "waist" in result["components"][COMP_BM]["metrics"]

    def test_unselected_component_not_in_payload(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 82),
            _r("2026-06-01", COMP_P1, "pushups", 30),
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        assert COMP_P1 not in result["components"]


class TestBaselineResolution:
    def test_baseline_uses_full_history_not_clipped_to_range(self):
        readings = [
            _r("2025-01-10", COMP_BV, "weight_kg", 90),  # historical — outside range
            _r("2026-06-01", COMP_BV, "weight_kg", 82),  # in range
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        wkg = result["components"][COMP_BV]["metrics"]["weight_kg"]
        assert wkg["baseline"] == "2025-01-10"   # earliest across all history
        assert len(wkg["readings"]) == 1          # only in-range reading returned

    def test_baseline_is_none_when_metric_has_no_history(self):
        readings = [_r("2026-06-01", COMP_BV, "weight_kg", 82)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        fat = result["components"][COMP_BV]["metrics"].get("fat_pct")
        assert fat is None  # metric not present at all — not an empty dict entry


class TestBMIComputed:
    def test_bmi_computed_when_both_inputs_present_same_date(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 80),
            _r("2026-06-01", COMP_BV, "height_cm", 175),
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        bmi = result["components"][COMP_BV]["derived"].get("bmi")
        assert bmi is not None
        assert len(bmi) == 1
        # 80 / 1.75^2 = 26.122... → rounds to 26.1
        assert bmi[0]["value"] == pytest.approx(26.1, abs=0.1)
        assert bmi[0]["date"] == "2026-06-01"

    def test_bmi_absent_when_height_missing(self):
        readings = [_r("2026-06-01", COMP_BV, "weight_kg", 80)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        bmi = result["components"][COMP_BV]["derived"].get("bmi")
        assert bmi is None

    def test_bmi_absent_when_weight_missing(self):
        readings = [_r("2026-06-01", COMP_BV, "height_cm", 175)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        bmi = result["components"][COMP_BV]["derived"].get("bmi")
        assert bmi is None

    def test_bmi_only_computed_for_dates_where_both_present(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 80),
            _r("2026-06-01", COMP_BV, "height_cm", 175),
            _r("2026-06-15", COMP_BV, "weight_kg", 79),  # height missing on this date
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV], readings)
        bmi = result["components"][COMP_BV]["derived"]["bmi"]
        assert len(bmi) == 1
        assert bmi[0]["date"] == "2026-06-01"


MALE_PROFILE   = {"gender": "male",   "dob": "1985-06-01"}   # age = 41 on 2026-06-01
FEMALE_PROFILE = {"gender": "female", "dob": "1985-06-01"}


class TestBMRComputed:
    def _bv_readings(self):
        return [
            _r("2026-06-01", COMP_BV, "weight_kg", 80),
            _r("2026-06-01", COMP_BV, "height_cm", 175),
        ]

    def test_bmr_computed_for_male(self):
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV],
                                      self._bv_readings(), client_profile=MALE_PROFILE)
        bmr = result["components"][COMP_BV]["derived"].get("bmr")
        assert bmr is not None
        # Male: 10*80 + 6.25*175 - 5*41 + 5 = 800 + 1093.75 - 205 + 5 = 1693.75 → 1694
        assert bmr[0]["value"] == 1694
        assert bmr[0]["date"] == "2026-06-01"

    def test_bmr_computed_for_female(self):
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV],
                                      self._bv_readings(), client_profile=FEMALE_PROFILE)
        bmr = result["components"][COMP_BV]["derived"].get("bmr")
        assert bmr is not None
        # Female: 10*80 + 6.25*175 - 5*41 - 161 = 800 + 1093.75 - 205 - 161 = 1527.75 → 1528
        assert bmr[0]["value"] == 1528

    def test_bmr_absent_without_client_profile(self):
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV],
                                      self._bv_readings())
        bmr = result["components"][COMP_BV]["derived"].get("bmr")
        assert bmr is None

    def test_bmr_absent_when_height_missing(self):
        readings = [_r("2026-06-01", COMP_BV, "weight_kg", 80)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV],
                                      readings, client_profile=MALE_PROFILE)
        assert result["components"][COMP_BV]["derived"].get("bmr") is None

    def test_bmi_still_computed_alongside_bmr(self):
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BV],
                                      self._bv_readings(), client_profile=MALE_PROFILE)
        assert result["components"][COMP_BV]["derived"].get("bmi") is not None
        assert result["components"][COMP_BV]["derived"].get("bmr") is not None


class TestWHRComputed:
    def test_whr_computed_when_both_inputs_present_same_date(self):
        readings = [
            _r("2026-06-01", COMP_BM, "waist", 34),
            _r("2026-06-01", COMP_BM, "hips",  40),
        ]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BM], readings)
        whr = result["components"][COMP_BM]["derived"].get("waist_hip_ratio")
        assert whr is not None
        # 34 / 40 = 0.85
        assert whr[0]["value"] == pytest.approx(0.85, abs=0.001)
        assert whr[0]["date"] == "2026-06-01"

    def test_whr_absent_when_hips_missing(self):
        readings = [_r("2026-06-01", COMP_BM, "waist", 34)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BM], readings)
        whr = result["components"][COMP_BM]["derived"].get("waist_hip_ratio")
        assert whr is None

    def test_whr_absent_when_waist_missing(self):
        readings = [_r("2026-06-01", COMP_BM, "hips", 40)]
        result = build_report_payload(CLIENT, RANGE_FROM, RANGE_TO, [COMP_BM], readings)
        whr = result["components"][COMP_BM]["derived"].get("waist_hip_ratio")
        assert whr is None


class TestBuildNudgePayload:
    """F06-S02: Nudge is single-select across all 7 components, not just body_vitals.
    Payload shape: {componentId, headlineCaption, headlineValue, statBoxes, measurementBars}."""

    def test_no_weight_history_returns_error(self):
        result = build_nudge_payload(CLIENT, "2026-06-30", [])
        assert "error" in result

    def test_first_checkin_shows_value_not_delta(self):
        readings = [_r("2026-06-01", COMP_BV, "weight_kg", 80)]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert result["statBoxes"][0] == {"label": "WEIGHT", "unit": "kg", "value": 80}
        assert result["headlineCaption"] == "First check-in"
        assert result["headlineValue"] == "80 kg"

    def test_weight_loss_delta_uses_down_arrow(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 80),
            _r("2026-06-15", COMP_BV, "weight_kg", 78.2),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert result["statBoxes"][0]["value"] == 78.2
        assert result["headlineCaption"] == "Since last check-in"
        assert result["headlineValue"] == "↓ 1.8 kg"

    def test_weight_gain_delta_uses_up_arrow(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 78),
            _r("2026-06-15", COMP_BV, "weight_kg", 79.5),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert result["headlineValue"] == "↑ 1.5 kg"

    def test_reading_after_date_to_ignored_for_latest(self):
        readings = [
            _r("2026-06-01", COMP_BV, "weight_kg", 80),
            _r("2026-06-15", COMP_BV, "weight_kg", 78),
            _r("2026-07-05", COMP_BV, "weight_kg", 76),  # after date_to
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert result["statBoxes"][0]["value"] == 78
        assert result["headlineValue"] == "↓ 2.0 kg"

    def test_delta_uses_previous_checkin_outside_any_range(self):
        # "Previous" reading predates any Report Config date window — the
        # nudge must still find it via full history, not an in-range slice.
        readings = [
            _r("2025-01-01", COMP_BV, "weight_kg", 90),
            _r("2026-06-15", COMP_BV, "weight_kg", 85),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert result["headlineValue"] == "↓ 5.0 kg"

    def test_fat_and_muscle_pct_picked_up(self):
        readings = [
            _r("2026-06-15", COMP_BV, "weight_kg", 78),
            _r("2026-06-15", COMP_BV, "fat_pct", 24.5),
            _r("2026-06-15", COMP_BV, "muscle_pct", 31.0),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        by_label = {b["label"]: b for b in result["statBoxes"]}
        assert by_label["BODY FAT"]["value"] == 24.5
        assert by_label["MUSCLE"]["value"] == 31.0

    def test_fat_and_muscle_pct_omitted_when_absent(self):
        readings = [_r("2026-06-15", COMP_BV, "weight_kg", 78)]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert len(result["statBoxes"]) == 1  # weight only

    def test_full_assessment_metrics_fill_boxes_when_fat_muscle_absent(self):
        # Full-Assessment-only client: no fat_pct/muscle_pct, but has BP/height/bpm.
        # Boxes must fall back through the priority list, not go blank.
        readings = [
            _r("2026-06-15", COMP_BV, "weight_kg", 78),
            _r("2026-06-15", COMP_BV, "bp_systol", 118),
            _r("2026-06-15", COMP_BV, "bp_diastol", 76),
            _r("2026-06-15", COMP_BV, "bpm", 64),
            _r("2026-06-15", COMP_BV, "height_cm", 175),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        by_label = {b["label"]: b for b in result["statBoxes"]}
        assert by_label["BLOOD PRESSURE"]["value"] == "118/76"
        assert by_label["BLOOD PRESSURE"]["unit"] == "mmHg"
        assert by_label["HEART RATE"]["value"] == 64
        assert "HEIGHT" not in by_label  # box budget is headline + 2 (BP counts as one)
        assert len(result["statBoxes"]) == 3  # weight headline + BP pair + heart rate

    def test_bp_box_omitted_when_only_one_of_pair_present(self):
        readings = [
            _r("2026-06-15", COMP_BV, "weight_kg", 78),
            _r("2026-06-15", COMP_BV, "bp_systol", 118),
            _r("2026-06-15", COMP_BV, "bpm", 64),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        by_label = {b["label"]: b for b in result["statBoxes"]}
        assert "BLOOD PRESSURE" not in by_label
        assert by_label["HEART RATE"]["value"] == 64

    def test_body_measurements_waist_hips_with_pct(self):
        readings = [
            _r("2026-06-15", COMP_BM, "waist", 30.5),
            _r("2026-06-15", COMP_BM, "hips", 38.2),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings, component_id=COMP_BM)
        assert "error" not in result
        by_label = {m["label"]: m for m in result["measurementBars"]}
        assert by_label["Waist"]["value"] == '30.5"'
        assert by_label["Hips"]["value"] == '38.2"'
        assert 0 < by_label["Waist"]["pct"] <= 100
        assert result["statBoxes"] == []

    def test_body_measurements_no_waist_returns_error(self):
        result = build_nudge_payload(CLIENT, "2026-06-30", [], component_id=COMP_BM)
        assert "error" in result

    def test_other_client_readings_excluded(self):
        readings = [_r("2026-06-15", COMP_BV, "weight_kg", 78, client_id="someone_else")]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings)
        assert "error" in result

    def test_physio_1_headline_is_pushups(self):
        readings = [
            _r("2026-06-01", COMP_P1, "pushups", 20),
            _r("2026-06-15", COMP_P1, "pushups", 25),
            _r("2026-06-15", COMP_P1, "squats", 30),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings, component_id=COMP_P1)
        assert result["headlineValue"] == "↑ 5.0 reps"
        assert result["statBoxes"][0] == {"label": "PUSHUPS", "unit": "reps", "value": 25}
        assert result["statBoxes"][1] == {"label": "SQUATS", "unit": "reps", "value": 30}

    def test_balance_open_no_data_returns_error(self):
        result = build_nudge_payload(CLIENT, "2026-06-30", [], component_id="balance_open")
        assert "error" in result

    def test_strength_headline_is_bench_press_weight(self):
        readings = [
            _r("2026-06-01", "strength", "bench_press_weight", 135),
            _r("2026-06-15", "strength", "bench_press_weight", 145),
            _r("2026-06-15", "strength", "squat_weight", 185),
        ]
        result = build_nudge_payload(CLIENT, "2026-06-30", readings, component_id="strength")
        assert result["headlineValue"] == "↑ 10.0 lbs"
        assert result["statBoxes"][0] == {"label": "BENCH PRESS", "unit": "lbs", "value": 145}
        assert result["statBoxes"][1] == {"label": "SQUAT", "unit": "lbs", "value": 185}
