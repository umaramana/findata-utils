"""
F05-S07 — Cloud Run bridge: POST /generate-report.

Called directly by Apps Script's "Download Report" button (Code.gs ->
UrlFetchApp), synchronously, no polling/queue. Reuses F04-S08's
fetch_client_readings/fetch_client_profile and report_pdf.generate_full_report
unchanged — this file is only the HTTP wrapper + auth + Drive upload.

Auth: a shared secret header, checked before any Sheets/Drive work starts.
Sheets/Drive access uses a stored OAuth user token (oauth_user_auth.py),
minted once locally (mint_oauth_token.py) and mounted as a Cloud Run
secret — not a service account, because service accounts have no Drive
storage quota and can't create files at all (see DEPLOY.md).
"""

import logging
import os
import sys
import tempfile

import gspread
from flask import Flask, jsonify, request

_HERE = os.path.dirname(os.path.abspath(__file__))
_INSIGHT_CORE = os.path.dirname(_HERE)
if _INSIGHT_CORE not in sys.path:
    sys.path.insert(0, _INSIGHT_CORE)

from generate_report import fetch_client_readings, fetch_client_profile  # noqa: E402
from report_pdf import generate_full_report  # noqa: E402
from layout_engine import _VALID_DENSITIES  # noqa: E402

import oauth_user_auth  # noqa: E402
import drive_upload  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)

SHEET_NAME = "insight_pilot"
_ALL_COMPONENTS = {
    "body_measurements", "body_vitals", "physio_1", "physio_2",
    "physio_3", "balance_open", "balance_closed",
}

SHARED_SECRET_ENV = "REPORT_SHARED_SECRET"
ARUN_EMAIL = os.environ.get("ARUN_EMAIL", "arunalexdavid1991@gmail.com")


def _validate_request(body):
    """Returns (ok, error_message). Never raises — every bad shape is a clean 400."""
    if not isinstance(body, dict):
        return False, "Request body must be a JSON object."

    client_id = body.get("client_id")
    date_from = body.get("date_from")
    date_to = body.get("date_to")
    component_ids = body.get("component_ids")
    layout = body.get("layout")

    if not client_id or not isinstance(client_id, str):
        return False, "client_id is required."
    if not date_from or not isinstance(date_from, str):
        return False, "date_from is required (YYYY-MM-DD)."
    if not date_to or not isinstance(date_to, str):
        return False, "date_to is required (YYYY-MM-DD)."
    if not component_ids or not isinstance(component_ids, list):
        return False, "component_ids must be a non-empty list."
    unknown = [c for c in component_ids if c not in _ALL_COMPONENTS]
    if unknown:
        return False, f"Unknown component_ids: {unknown}"
    if not layout or layout not in _VALID_DENSITIES:
        return False, f"layout must be one of {sorted(_VALID_DENSITIES)}."

    return True, None


@app.route("/generate-report", methods=["POST"])
def generate_report_endpoint():
    # 1. Auth check first — before touching Sheets/Drive at all.
    expected_secret = os.environ.get(SHARED_SECRET_ENV)
    if not expected_secret:
        log.error("%s is not configured on this deployment.", SHARED_SECRET_ENV)
        return jsonify(status="error", error_message="Server misconfigured."), 500

    given_secret = request.headers.get("X-Report-Secret")
    if given_secret != expected_secret:
        return jsonify(status="error", error_message="Unauthorized."), 401

    # 2. Validate request shape.
    body = request.get_json(silent=True) or {}
    ok, err = _validate_request(body)
    if not ok:
        return jsonify(status="error", error_message=err), 400

    client_id = body["client_id"]
    date_from = body["date_from"]
    date_to = body["date_to"]
    component_ids = body["component_ids"]
    layout = body["layout"]

    # 3. Run the pipeline. Every external call wrapped — always return a response.
    try:
        creds = oauth_user_auth.get_credentials()
        gc = gspread.authorize(creds)
        spreadsheet = gc.open(SHEET_NAME)

        all_readings = fetch_client_readings(spreadsheet, client_id)
        client_profile = fetch_client_profile(spreadsheet, client_id)
    except Exception:
        log.exception("Failed to read Sheets data for client_id=%s", client_id)
        return jsonify(status="error", error_message="Could not read client data from Sheets."), 502

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = generate_full_report(
                client_id=client_id,
                date_from=date_from,
                date_to=date_to,
                component_ids=component_ids,
                grid_density=layout,
                all_readings=all_readings,
                client_profile=client_profile,
                asset_library=None,       # F04-S10's job — same local fallback F04-S08 uses today
                metric_asset_groups=None,
                output_dir=tmp_dir,
            )

            if "error" in result:
                return jsonify(status="error", error_message=result["error"]), 422

            pdf_path = result["path"]
            filename = os.path.basename(pdf_path)

            drive_service = drive_upload.build_drive_service(creds)
            parent_id = drive_upload.find_sheet_parent_folder_id(drive_service, SHEET_NAME)
            folder_id = drive_upload.find_or_create_client_reports_folder(drive_service, parent_id)
            file_id, web_link = drive_upload.upload_pdf(drive_service, folder_id, pdf_path, filename)
            drive_upload.share_with_email(drive_service, file_id, ARUN_EMAIL)

    except Exception:
        log.exception("Report generation/upload failed for client_id=%s", client_id)
        return jsonify(status="error", error_message="Report generation failed."), 500

    return jsonify(status="done", output_url=web_link)


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
