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

    def test_no_headline_omits_headline_block_but_keeps_date(self):
        # F06-S04 — grip_strength has no headline metric.
        html = _render_template("Uma", _payload(
            displayName="Hand Grip Strength",
            headlineCaption=None,
            headlineValue=None,
            statBoxes=[
                {"label": "RIGHT HAND", "unit": "kg", "value": 34, "grade": "Good"},
                {"label": "LEFT HAND", "unit": "kg", "value": 25, "grade": "Average"},
            ],
        ))
        assert "First pulse reading" not in html
        assert "None" not in html
        assert "Aug 21, 2026" in html

    def test_stat_box_grade_line_rendered_when_present(self):
        html = _render_template("Uma", _payload(
            displayName="Hand Grip Strength",
            headlineCaption=None,
            headlineValue=None,
            statBoxes=[{"label": "RIGHT HAND", "unit": "kg", "value": 34, "grade": "Good"}],
        ))
        assert "RIGHT HAND" in html
        assert "Good" in html

    def test_stat_box_without_grade_key_still_renders(self):
        # Existing components' boxes have no "grade" key at all — must not error.
        html = _render_template("Uma", _payload(statBoxes=[
            {"label": "PULSE", "unit": "bpm", "value": 64},
        ]))
        assert "PULSE" in html


# ── F06-S04 redesign (2026-09-24) — grip_strength's own 1024x1536 card ────────
# grip_nudge_template.html replaces the generic card for this one component.
# These cover the routing decision and the slot mapping; the rendered PNG
# itself is verified by eye (Puppeteer subprocess is out of scope here, same
# reason as the rest of this file).

from nudge_png import _render_grip_template, _font_face_css, _kg, _hand


def _grip_payload(**overrides):
    base = dict(
        componentId="grip_strength",
        displayName="Hand Grip Strength",
        date="2026-09-18",
        headlineCaption=None,
        headlineValue=None,
        statBoxes=[
            {"label": "RIGHT HAND", "unit": "kg", "value": 48.1, "grade": "Average"},
            {"label": "LEFT HAND",  "unit": "kg", "value": 42.7, "grade": "Good"},
        ],
    )
    base.update(overrides)
    return _payload(**base)


class TestGripTemplateRouting:
    def test_grip_component_uses_the_new_card(self):
        html = _render_template("Dr Pavan", _grip_payload())
        assert 'id="nudge-card"' in html
        assert "1024px" in html and "1536px" in html
        # Generic card markers must be gone.
        assert "UPDATE" not in html

    def test_other_components_keep_the_generic_card(self):
        html = _render_template("Uma", _payload(displayName="Body Vitals"))
        assert "BODY VITALS UPDATE" in html
        assert "1536px" not in html


class TestGripTemplateSlots:
    def test_hand_values_and_grades_land_in_the_right_panels(self):
        html = _render_grip_template("Dr Pavan", _grip_payload())
        assert "48.1" in html and "Average" in html
        assert "42.7" in html and "Good" in html
        # Crimson = right hand, pine = left hand: the value must sit in its own colour.
        assert html.index("48.1") < html.index("42.7")

    def test_name_and_date_rendered(self):
        html = _render_grip_template("Dr Pavan", _grip_payload())
        assert "Dr Pavan" in html
        assert "Sep 18, 2026" in html

    def test_values_always_formatted_to_one_decimal(self):
        # The template does no rounding — an int reading must not print as "48".
        html = _render_grip_template("Dr Pavan", _grip_payload(statBoxes=[
            {"label": "RIGHT HAND", "unit": "kg", "value": 48, "grade": "Good"},
            {"label": "LEFT HAND",  "unit": "kg", "value": 42, "grade": "Good"},
        ]))
        assert "48.0" in html and "42.0" in html

    def test_three_digit_value_still_formats(self):
        assert _kg(100) == "100.0"

    def test_missing_grade_renders_blank_not_none(self):
        html = _render_grip_template("Dr Pavan", _grip_payload(statBoxes=[
            {"label": "RIGHT HAND", "unit": "kg", "value": 48.1, "grade": None},
            {"label": "LEFT HAND",  "unit": "kg", "value": 42.7, "grade": "Good"},
        ]))
        assert "None" not in html

    def test_missing_hand_raises_rather_than_rendering_half_a_card(self):
        # Both hands are mandatory at data entry; if that ever breaks, fail
        # loudly instead of shipping a card with one blank 100px numeral.
        import pytest
        with pytest.raises(ValueError, match="LEFT HAND"):
            _render_grip_template("Dr Pavan", _grip_payload(statBoxes=[
                {"label": "RIGHT HAND", "unit": "kg", "value": 48.1, "grade": "Good"},
            ]))

    def test_hand_lookup_is_by_label_not_position(self):
        payload = _grip_payload(statBoxes=[
            {"label": "LEFT HAND",  "unit": "kg", "value": 42.7, "grade": "Good"},
            {"label": "RIGHT HAND", "unit": "kg", "value": 48.1, "grade": "Average"},
        ])
        assert _hand(payload, "RIGHT HAND")["value"] == 48.1


class TestBundledFonts:
    def test_all_four_families_are_embedded_not_network_loaded(self):
        css = _font_face_css()
        for family in ("Archivo", "Archivo Black", "Barlow Semi Condensed", "Dancing Script"):
            assert f"font-family: '{family}'" in css
        assert "data:font/woff2;base64," in css

    def test_template_never_reaches_out_to_google_fonts(self):
        # Cloud Run's image ships only fonts-liberation — a network <link> that
        # silently fails would ship a visibly broken card with no error.
        html = _render_grip_template("Dr Pavan", _grip_payload())
        assert "fonts.googleapis.com" not in html
        assert "fonts.gstatic.com" not in html

    def test_assets_are_inlined_not_relative_paths(self):
        # The render HTML is written to a system temp dir, so any relative
        # asset path resolves to nothing.
        html = _render_grip_template("Dr Pavan", _grip_payload())
        assert 'src="assets/' not in html
        assert html.count("data:image/png;base64,") >= 2


class TestGymSlots:
    """F06-S04 gym registry (2026-09-24) — meta column 3 and the footer corner.

    Apps Script resolves the gym and ships the logo as an inline data: URI;
    this layer only places them, and falls back per-slot when either is absent.
    """

    _LOGO = "data:image/png;base64,iVBORw0KGgo="

    def test_gym_name_replaces_the_test_name_in_the_meta_strip(self):
        html = _render_grip_template("Dr Pavan", _grip_payload(),
                                     gym_name="Iron Peak Fitness")
        assert ">GYM<" in html
        assert "Iron Peak Fitness" in html
        # The test name survives only in the <title> and the file header
        # comment — never in the meta cell, which is now the gym's.
        assert ">Hand Grip Strength<" not in html

    def test_no_gym_keeps_the_test_name(self):
        html = _render_grip_template("Dr Pavan", _grip_payload())
        assert ">TEST<" in html
        assert "Hand Grip Strength" in html
        assert ">GYM<" not in html

    def test_logo_replaces_the_footer_strapline(self):
        html = _render_grip_template("Dr Pavan", _grip_payload(),
                                     gym_name="Iron Peak", gym_logo=self._LOGO)
        assert self._LOGO in html
        assert "MOVE BETTER" not in html

    def test_gym_without_a_logo_keeps_the_footer_strapline(self):
        # A gym row with no uploaded logo file is valid — name slot fills,
        # footer doesn't.
        html = _render_grip_template("Dr Pavan", _grip_payload(), gym_name="Iron Peak")
        assert "Iron Peak" in html
        assert "MOVE BETTER" in html

    def test_remote_logo_url_is_refused_and_falls_back(self):
        # The card must stay self-contained: a URL here would make the
        # Puppeteer render reach out to an outside host.
        html = _render_grip_template("Dr Pavan", _grip_payload(), gym_name="Iron Peak",
                                     gym_logo="https://example.com/logo.png")
        assert "example.com" not in html
        assert "MOVE BETTER" in html

    def test_long_gym_name_prints_in_full_at_the_designed_size(self):
        # The strip grows to fit the name rather than the name shrinking to
        # fit the strip (2026-09-24): no clamp, no ellipsis, no step-down.
        # The card's own height is a min-height for the same reason.
        name = "Anna Nagar Strength & Conditioning Centre"
        html = _render_grip_template("Dr Pavan", _grip_payload(), gym_name=name)
        assert name in html
        assert "font-size: 25px" in html
        assert "line-clamp" not in html
        assert "min-height: 129px" in html
        assert "min-height: 1536px" in html

    def test_generic_card_ignores_gym_arguments(self):
        html = _render_template("Uma", _payload(displayName="Body Vitals"),
                                gym_name="Iron Peak", gym_logo=self._LOGO)
        assert "Iron Peak" not in html
        assert "BODY VITALS UPDATE" in html
