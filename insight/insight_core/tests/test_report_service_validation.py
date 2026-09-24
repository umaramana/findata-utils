"""Tests for report_service/app.py's request validators (F06-S04 gym fields).

Only the pure validation layer — no Flask test client, no Sheets/Drive, no
renderer. Those need live credentials and a Node/Puppeteer install, out of
scope here for the same reason test_nudge_png.py stops at the HTML.

Added 2026-09-24 with the gym registry: the gym name and logo arrive from
Apps Script as free-form payload fields, so the shapes this endpoint accepts
are worth pinning down.
"""
import sys
import os

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", "report_service"))

from app import _validate_gym_fields, _validate_nudge_request, _validate_walkin_request

_LOGO = "data:image/png;base64,iVBORw0KGgo="


def _nudge(**overrides):
    body = {"client_id": "dr_pavan", "date_to": "2026-09-24", "component_id": "grip_strength"}
    body.update(overrides)
    return body


def _walkin(**overrides):
    body = {
        "name": "Ramesh", "phone": "9791172562", "date": "2026-09-24",
        "values": {"grip_right_trial_1": "48.1", "grip_left_trial_1": "42.7",
                   "grip_right_grade": "Good", "grip_left_grade": "Average"},
    }
    body.update(overrides)
    return body


class TestValidateGymFields:
    def test_no_gym_at_all_is_valid(self):
        # Every nudge sent before the gym registry existed has this shape,
        # and a client with no gym still has it — the card falls back.
        assert _validate_gym_fields({}) == (True, None)

    def test_blank_gym_fields_are_valid(self):
        assert _validate_gym_fields({"gym_name": "", "gym_logo": ""}) == (True, None)

    def test_name_and_data_uri_logo_accepted(self):
        assert _validate_gym_fields({"gym_name": "Iron Peak", "gym_logo": _LOGO}) == (True, None)

    def test_gym_name_without_a_logo_accepted(self):
        # A registry row with no uploaded logo file.
        assert _validate_gym_fields({"gym_name": "Iron Peak"}) == (True, None)

    def test_remote_logo_url_rejected(self):
        # The rendered card must stay self-contained — a URL here would make
        # the Puppeteer render fetch from an outside host.
        ok, err = _validate_gym_fields({"gym_logo": "https://example.com/logo.png"})
        assert not ok
        assert "data:image/" in err

    def test_non_string_fields_rejected(self):
        assert not _validate_gym_fields({"gym_name": 42})[0]
        assert not _validate_gym_fields({"gym_logo": {"b64": "..."}})[0]


class TestGymFieldsReachBothEndpoints:
    def test_tracked_client_request_accepts_gym(self):
        assert _validate_nudge_request(_nudge(gym_name="Iron Peak", gym_logo=_LOGO)) == (True, None)

    def test_tracked_client_request_rejects_bad_logo(self):
        assert not _validate_nudge_request(_nudge(gym_logo="ftp://x/logo.png"))[0]

    def test_walkin_request_accepts_gym(self):
        assert _validate_walkin_request(_walkin(gym_name="Iron Peak", gym_logo=_LOGO)) == (True, None)

    def test_walkin_request_rejects_bad_logo(self):
        assert not _validate_walkin_request(_walkin(gym_logo="ftp://x/logo.png"))[0]

    def test_existing_validation_still_runs_before_the_gym_check(self):
        # A request that is bad for an older reason must still fail on that
        # reason, not silently pass because the gym fields are fine.
        assert not _validate_nudge_request(_nudge(client_id="", gym_name="Iron Peak"))[0]
        assert not _validate_walkin_request(
            _walkin(values={"grip_right_trial_1": "heavy"}, gym_name="Iron Peak")
        )[0]


class TestNudgeAndFullReportWhitelistsDiffer:
    """grip_strength has a Nudge card but no Full Report treatment.

    Both endpoints validated against the same set until 2026-09-24, which
    meant every tracked-client grip nudge was rejected as an unknown
    component_id while Full Report's (correct) rejection was the only one
    anyone had tested.
    """

    def test_nudge_accepts_grip_strength(self):
        assert _validate_nudge_request(_nudge(component_id="grip_strength")) == (True, None)

    def test_full_report_still_rejects_grip_strength(self):
        from app import _validate_request
        ok, err = _validate_request({
            "client_id": "dr_pavan", "date_from": "2026-01-01", "date_to": "2026-09-24",
            "component_ids": ["grip_strength"], "layout": "comfortable",
        })
        assert not ok
        assert "grip_strength" in err

    def test_nudge_still_rejects_a_genuinely_unknown_component(self):
        assert not _validate_nudge_request(_nudge(component_id="vo2max"))[0]
