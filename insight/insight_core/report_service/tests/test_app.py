"""
Request validation + success/failure-path tests for report_service/app.py.
Every external call (Sheets, Drive, generate_full_report) is mocked — these
tests verify the HTTP contract, not the rendering pipeline itself (that's
covered by insight_core's own test suite).
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["REPORT_SHARED_SECRET"] = "test-secret"

import app as app_module  # noqa: E402

VALID_BODY = {
    "client_id": "champion_mr_abhay_singh",
    "date_from": "2026-06-22",
    "date_to": "2026-06-22",
    "component_ids": ["body_measurements", "body_vitals"],
    "layout": "1x1",
}


@pytest.fixture
def client():
    app_module.app.testing = True
    return app_module.app.test_client()


def _post(client, body, secret="test-secret"):
    headers = {"X-Report-Secret": secret} if secret is not None else {}
    return client.post("/generate-report", json=body, headers=headers)


def test_rejects_missing_secret(client):
    resp = _post(client, VALID_BODY, secret=None)
    assert resp.status_code == 401
    assert resp.get_json()["status"] == "error"


def test_rejects_wrong_secret(client):
    resp = _post(client, VALID_BODY, secret="wrong")
    assert resp.status_code == 401


def test_rejects_missing_client_id(client):
    body = dict(VALID_BODY)
    del body["client_id"]
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "client_id" in resp.get_json()["error_message"]


def test_rejects_empty_component_ids(client):
    body = dict(VALID_BODY, component_ids=[])
    resp = _post(client, body)
    assert resp.status_code == 400


def test_rejects_unknown_component_id(client):
    body = dict(VALID_BODY, component_ids=["not_a_real_component"])
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "Unknown component_ids" in resp.get_json()["error_message"]


def test_rejects_invalid_layout(client):
    body = dict(VALID_BODY, layout="9x9")
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "layout" in resp.get_json()["error_message"]


@patch("app.drive_upload")
@patch("app.generate_full_report")
@patch("app.fetch_client_profile")
@patch("app.fetch_client_readings")
@patch("app.gspread")
@patch("app.oauth_user_auth")
def test_success_path_returns_output_url(
    mock_auth, mock_gspread, mock_readings, mock_profile, mock_generate, mock_drive, client, tmp_path
):
    mock_auth.get_credentials.return_value = MagicMock()
    mock_gspread.authorize.return_value.open.return_value = MagicMock()
    mock_readings.return_value = [{"client_id": "x", "date": "2026-06-22",
                                    "component": "body_measurements", "metric": "waist", "value": 32.0}]
    mock_profile.return_value = {"gender": "M", "dob": "", "client_type": ""}

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    mock_generate.return_value = {"path": str(pdf_path), "version": 1, "pages": 1}

    mock_drive.find_sheet_parent_folder_id.return_value = "parent123"
    mock_drive.find_or_create_client_reports_folder.return_value = "folder123"
    mock_drive.upload_pdf.return_value = ("file123", "https://drive.google.com/file/d/file123/view")

    resp = _post(client, VALID_BODY)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "done"
    assert data["output_url"] == "https://drive.google.com/file/d/file123/view"
    mock_drive.share_with_email.assert_called_once()


@patch("app.generate_full_report")
@patch("app.fetch_client_profile")
@patch("app.fetch_client_readings")
@patch("app.gspread")
@patch("app.oauth_user_auth")
def test_pipeline_error_returns_structured_422(
    mock_auth, mock_gspread, mock_readings, mock_profile, mock_generate, client
):
    mock_auth.get_credentials.return_value = MagicMock()
    mock_gspread.authorize.return_value.open.return_value = MagicMock()
    mock_readings.return_value = []
    mock_profile.return_value = {}
    mock_generate.return_value = {"error": "No data available for the selected components"}

    resp = _post(client, VALID_BODY)
    assert resp.status_code == 422
    data = resp.get_json()
    assert data["status"] == "error"
    assert "No data available" in data["error_message"]


@patch("app.oauth_user_auth")
def test_sheets_auth_failure_returns_502_not_500_crash(mock_auth, client):
    mock_auth.get_credentials.side_effect = RuntimeError("key not found")
    resp = _post(client, VALID_BODY)
    assert resp.status_code == 502
    assert resp.get_json()["status"] == "error"
