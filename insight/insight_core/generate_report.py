"""
F04-S08 — Live-sheet orchestration script.

Authenticates, pulls live readings/client_info/asset_library/metric_asset_groups
from the insight_pilot Google Sheet, and calls generate_full_report(). This is
the entry point missing until now: every prior report used fixture data
(smoke_report_pdf.py's hardcoded 2-date rows).

Usage:
    python generate_report.py <client_id> <date_from> <date_to> [--components ...] [--grid-density ...]

Assets stay local this week by design (F04-S08 card, 2026-07-02) — no live
asset_library/metric_asset_groups tabs exist yet, so an empty read falls back
to report_pdf._local_asset_library() with a logged warning, never a crash.
"""

import argparse
import logging

import gspread

import sheets_auth
from report_pdf import generate_full_report

log = logging.getLogger(__name__)

SHEET_NAME = "insight_pilot"

_ALL_COMPONENTS = [
    "body_measurements", "body_vitals", "physio_1", "physio_2",
    "physio_3", "balance_open", "balance_closed",
]

_READINGS_TAB = "readings"
_CLIENT_INFO_TAB = "client_info"


def _load_tab_rows(spreadsheet, tab_name, columns):
    """Read a named tab and return rows as list of dicts keyed by columns.
    Mirrors gender_image._load_tab's case-insensitive header lookup."""
    try:
        ws = spreadsheet.worksheet(tab_name)
        rows = ws.get_all_values()
    except Exception as exc:
        log.warning("Could not load tab %r: %s", tab_name, exc)
        return []

    if len(rows) < 2:
        return []

    header = [c.strip().lower() for c in rows[0]]
    col_idx = {col: header.index(col) for col in columns if col in header}

    result = []
    for row in rows[1:]:
        if not any(row):
            continue
        result.append({col: (row[idx] if idx < len(row) else "")
                       for col, idx in col_idx.items()})
    return result


def fetch_client_readings(spreadsheet, client_id):
    """Read the `readings` tab, filter to client_id, return
    [{client_id, date, component, metric, value}, ...] — the shape
    report_query.build_report_payload() expects."""
    rows = _load_tab_rows(spreadsheet, _READINGS_TAB,
                          ["client_id", "date", "component", "metric", "value"])
    readings = []
    for row in rows:
        if row.get("client_id") != client_id:
            continue
        value = row.get("value", "")
        try:
            value = float(value)
        except (ValueError, TypeError):
            continue  # unparseable value — skip rather than crash the run
        readings.append({
            "client_id": client_id,
            "date": row.get("date", ""),
            "component": row.get("component", ""),
            "metric": row.get("metric", ""),
            "value": value,
        })
    return readings


def fetch_client_profile(spreadsheet, client_id):
    """Read the `client_info` tab, return {gender, dob, client_type} for client_id."""
    rows = _load_tab_rows(spreadsheet, _CLIENT_INFO_TAB,
                          ["client_id", "gender", "dob", "client_type"])
    for row in rows:
        if row.get("client_id") == client_id:
            return {
                "gender": row.get("gender", ""),
                "dob": row.get("dob", ""),
                "client_type": row.get("client_type", ""),
            }
    return {}


def main():
    parser = argparse.ArgumentParser(description="Generate a full Insight report from live Sheets data.")
    parser.add_argument("client_id")
    parser.add_argument("date_from")
    parser.add_argument("date_to")
    parser.add_argument("--components", nargs="+", default=_ALL_COMPONENTS)
    parser.add_argument("--grid-density", default="3x2")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    creds = sheets_auth.get_credentials()
    gc = gspread.authorize(creds)
    spreadsheet = gc.open(SHEET_NAME)

    all_readings   = fetch_client_readings(spreadsheet, args.client_id)
    client_profile = fetch_client_profile(spreadsheet, args.client_id)

    # Assets stay local this week, deliberately (F04-S08 card, 2026-07-02) —
    # do NOT read the live asset_library/metric_asset_groups tabs here even
    # though they now exist. Found live 2026-07-04: the tab has been
    # populated with raw relative filenames (e.g. "male/weight_male.png"),
    # not the base64 data URIs Puppeteer requires (file:// is blocked by
    # Chromium's cross-origin rules — see report_pdf._local_asset_library's
    # docstring), and several entries don't match real files on disk at all
    # (wrong name, wrong extension). Wiring that data in is F04-S10's job,
    # not this week's — pass None so generate_full_report() always uses
    # _local_asset_library().
    result = generate_full_report(
        client_id=args.client_id,
        date_from=args.date_from,
        date_to=args.date_to,
        component_ids=args.components,
        grid_density=args.grid_density,
        all_readings=all_readings,
        client_profile=client_profile,
        asset_library=None,
        metric_asset_groups=None,
        output_dir=args.output_dir,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        raise SystemExit(1)

    print(result["path"])


if __name__ == "__main__":
    main()
