"""Tests for report_query.build_report_payload()"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report_query import build_report_payload

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
