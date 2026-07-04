"""Tests for generate_report.py's Sheets-fetch functions (F04-S08).

Uses a fake gspread-like spreadsheet (worksheet(name).get_all_values())
so these run without live credentials — matches gender_image.py's own
_load_tab() contract, which these functions mirror.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from generate_report import fetch_client_readings, fetch_client_profile


class FakeWorksheet:
    def __init__(self, rows):
        self._rows = rows

    def get_all_values(self):
        return self._rows


class FakeSpreadsheet:
    def __init__(self, tabs):
        self._tabs = tabs

    def worksheet(self, name):
        if name not in self._tabs:
            raise Exception(f"no such tab: {name}")
        return FakeWorksheet(self._tabs[name])


READINGS_ROWS = [
    ["client_id", "date", "component", "metric", "value", "unit", "source", "notes", "recorded_at"],
    ["dr_hemalatha", "2026-06-01", "body_vitals", "weight_kg", "65", "kg", "form", "", "2026-06-01T10:00:00"],
    ["dr_hemalatha", "2026-06-01", "body_vitals", "pulse", "72", "bpm", "form", "", "2026-06-01T10:00:00"],
    ["master_jay", "2026-06-01", "body_vitals", "weight_kg", "80", "kg", "form", "", "2026-06-01T10:00:00"],
    ["dr_hemalatha", "2026-06-01", "body_vitals", "bad_value", "not_a_number", "", "form", "", ""],
]

CLIENT_INFO_ROWS = [
    ["client_id", "full_name", "gender", "dob", "height_cm", "client_type", "active"],
    ["dr_hemalatha", "Dr Hemalatha", "female", "1980-01-01", "160", "adult", "TRUE"],
    ["master_jay", "Master Jay", "male", "2010-05-01", "150", "child", "TRUE"],
]


class TestFetchClientReadings:
    def test_filters_to_requested_client(self):
        sh = FakeSpreadsheet({"readings": READINGS_ROWS})
        result = fetch_client_readings(sh, "dr_hemalatha")
        assert all(r["client_id"] == "dr_hemalatha" for r in result)

    def test_returns_expected_shape_and_values(self):
        sh = FakeSpreadsheet({"readings": READINGS_ROWS})
        result = fetch_client_readings(sh, "dr_hemalatha")
        weight = next(r for r in result if r["metric"] == "weight_kg")
        assert weight == {
            "client_id": "dr_hemalatha", "date": "2026-06-01",
            "component": "body_vitals", "metric": "weight_kg", "value": 65.0,
        }

    def test_unparseable_value_skipped_not_crashed(self):
        sh = FakeSpreadsheet({"readings": READINGS_ROWS})
        result = fetch_client_readings(sh, "dr_hemalatha")
        assert not any(r["metric"] == "bad_value" for r in result)

    def test_missing_tab_returns_empty_list(self):
        sh = FakeSpreadsheet({})
        assert fetch_client_readings(sh, "dr_hemalatha") == []

    def test_unknown_client_returns_empty_list(self):
        sh = FakeSpreadsheet({"readings": READINGS_ROWS})
        assert fetch_client_readings(sh, "nonexistent_client") == []


class TestFetchClientProfile:
    def test_returns_gender_dob_client_type(self):
        sh = FakeSpreadsheet({"client_info": CLIENT_INFO_ROWS})
        assert fetch_client_profile(sh, "master_jay") == {
            "gender": "male", "dob": "2010-05-01", "client_type": "child",
        }

    def test_unknown_client_returns_empty_dict(self):
        sh = FakeSpreadsheet({"client_info": CLIENT_INFO_ROWS})
        assert fetch_client_profile(sh, "nonexistent_client") == {}

    def test_missing_tab_returns_empty_dict(self):
        sh = FakeSpreadsheet({})
        assert fetch_client_profile(sh, "master_jay") == {}
