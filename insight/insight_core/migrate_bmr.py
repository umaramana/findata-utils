"""
One-off migration — appends bmr (Basal Metabolic Rate) to metric_master
in the live insight_pilot sheet, bringing the total to 63 rows.

Idempotent: checks for an existing bmr row before appending.

Run once:
    python migrate_bmr.py
"""

from googleapiclient.discovery import build
from sheets_auth import get_credentials

SHEET_ID = "1B76UiwVHRYuj3B0gClnc-dSxgnKIF52kBcFJQ7IVxEA"

BMR_ROW = ["bmr", "body_vitals", "Basal Metabolic Rate", "kcal", "kcal", 0, ""]


def main():
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)

    # Read existing metric_ids to guard against double-append
    existing = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="metric_master!A:A"
    ).execute().get("values", [])
    existing_ids = [r[0] for r in existing if r]

    if "bmr" in existing_ids:
        print("bmr already exists in metric_master — nothing to do.")
    else:
        sheets.spreadsheets().values().append(
            spreadsheetId=SHEET_ID, range="metric_master!A:A",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": [BMR_ROW]}
        ).execute()
        print("Appended bmr to metric_master.")

    # Reconciliation
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="metric_master!A:A"
    ).execute().get("values", [])
    data_rows = max(0, len(result) - 1)
    status = "✓" if data_rows == 63 else "✗"
    print(f"\n── Reconciliation ──────────────────────────────────────────")
    print(f"  {status} metric_master: {data_rows} data rows (expected 63)")
    print(f"────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
