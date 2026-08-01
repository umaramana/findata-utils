"""
Nudge PNG — live-sheet orchestration script (local test path, no Cloud Run needed).

Authenticates, pulls a client's real readings from the live insight_pilot
Google Sheet, and calls generate_nudge_png(). Mirrors generate_report.py's
pattern for the full report.

Usage:
    python generate_nudge.py <client_id> <date_to>
"""

import argparse
import logging

import gspread

import sheets_auth
from nudge_png import generate_nudge_png
from generate_report import fetch_client_readings

log = logging.getLogger(__name__)

SHEET_NAME = "insight_pilot"


def main():
    parser = argparse.ArgumentParser(description="Generate a Nudge PNG from live Sheets data.")
    parser.add_argument("client_id")
    parser.add_argument("date_to")
    parser.add_argument("--component-id", default="body_vitals")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    creds = sheets_auth.get_credentials()
    gc = gspread.authorize(creds)
    spreadsheet = gc.open(SHEET_NAME)

    all_readings = fetch_client_readings(spreadsheet, args.client_id)

    result = generate_nudge_png(
        client_id=args.client_id,
        date_to=args.date_to,
        all_readings=all_readings,
        component_id=args.component_id,
        output_dir=args.output_dir,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        raise SystemExit(1)

    print(result["path"])


if __name__ == "__main__":
    main()
