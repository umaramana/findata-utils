"""Tests for nudge_png.py's template-rendering layer (_render_template, _format_date).

Deliberately doesn't touch _puppeteer_png / generate_nudge_png's Node subprocess call —
those need Node.js + Puppeteer installed and produce a real PNG, out of scope for a
fast unit test. This covers the Jinja2 HTML output only: given a build_nudge_payload()-
shaped dict, does the rendered card show the right kicker/date/headline text.

Added 2026-08-21 alongside the fix for the "nudge showed CHECK-IN UPDATE and no date
for a body_vitals card with only BP+Pulse logged" bug — until this file existed, the
kicker/date fix was verified only by a one-off manual PNG, not a repeatable test.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nudge_png import _render_template, _format_date


def _payload(**overrides):
    base = {
        "componentId":     "body_vitals",
        "displayName":     "Body Vitals",
        "date":            "2026-08-21",
        "headlineCaption": "First pulse reading",
        "headlineValue":   "64 bpm",
        "statBoxes":       [
            {"label": "PULSE", "unit": "bpm", "value": 64},
            {"label": "BLOOD PRESSURE", "unit": "mmHg", "value": "118/76"},
        ],
        "measurementBars": [],
    }
    base.update(overrides)
    return base


class TestFormatDate:
    def test_formats_iso_date_for_display(self):
        assert _format_date("2026-08-21") == "Aug 21, 2026"

    def test_single_digit_day_has_no_leading_zero(self):
        assert _format_date("2026-08-05") == "Aug 5, 2026"


class TestRenderTemplate:
    def test_kicker_shows_selected_component_not_hardcoded_checkin(self):
        # Regression test: nudge_template.html used to hardcode "CHECK-IN
        # UPDATE" regardless of component_id. Every component's kicker must
        # now come from the payload's displayName.
        html = _render_template("Uma", _payload(displayName="Body Vitals"))
        assert "BODY VITALS UPDATE" in html
        assert "CHECK-IN UPDATE" not in html

    def test_kicker_reflects_non_body_vitals_component(self):
        html = _render_template("Uma", _payload(displayName="Physiological 1"))
        assert "PHYSIOLOGICAL 1 UPDATE" in html
        assert "CHECK-IN UPDATE" not in html

    def test_date_rendered_on_card(self):
        # Regression test: date_to was previously never passed into the
        # template context at all — the card had no date anywhere on it.
        html = _render_template("Uma", _payload(date="2026-08-21"))
        assert "Aug 21, 2026" in html

    def test_client_name_and_headline_rendered(self):
        html = _render_template(
            "Uma", _payload(headlineCaption="First pulse reading", headlineValue="64 bpm")
        )
        assert "Uma" in html
        assert "First pulse reading" in html
        assert "64 bpm" in html

    def test_stat_boxes_rendered(self):
        html = _render_template("Uma", _payload(statBoxes=[
            {"label": "PULSE", "unit": "bpm", "value": 64},
            {"label": "BLOOD PRESSURE", "unit": "mmHg", "value": "118/76"},
        ]))
        assert "64" in html
        assert "PULSE" in html
        assert "118/76" in html
        assert "BLOOD PRESSURE" in html

    def test_measurement_bars_rendered_for_body_measurements(self):
        html = _render_template("Uma", _payload(
            displayName="Body Measurements",
            statBoxes=[],
            measurementBars=[{"label": "Waist", "value": '30.5"', "pct": 68}],
        ))
        assert "Waist" in html
        assert '30.5"' in html
        assert "BODY MEASUREMENTS UPDATE" in html
