"""
One-off fix — updates skinfold_chest/abdomen/thighs unit + display_unit from cm to mm
in the live insight_pilot metric_master tab. Confirmed with Arun (2026-06-24): skinfold
caliper readings are mm, not cm.

Run once:
    python fix_skinfold_unit.py
"""

from googleapiclient.discovery import build
from sheets_auth import get_credentials

SHEET_ID = "1B76UiwVHRYuj3B0gClnc-dSxgnKIF52kBcFJQ7IVxEA"  # insight_pilot
TARGET_METRICS = {"skinfold_chest", "skinfold_abdomen", "skinfold_thighs"}


def main():
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)

    metric_data = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="metric_master!A:A"
    ).execute().get("values", [])

    updated = []
    for i, row in enumerate(metric_data):
        if row and row[0] in TARGET_METRICS:
            range_ = f"metric_master!D{i + 1}:E{i + 1}"
            sheets.spreadsheets().values().update(
                spreadsheetId=SHEET_ID, range=range_,
                valueInputOption="RAW", body={"values": [["mm", "mm"]]}
            ).execute()
            updated.append(row[0])

    print(f"Updated unit/display_unit to mm for: {updated}")
    if len(updated) != len(TARGET_METRICS):
        missing = TARGET_METRICS - set(updated)
        print(f"⚠ Not found in metric_master: {missing}")


if __name__ == "__main__":
    main()
