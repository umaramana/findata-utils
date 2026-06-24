"""
One-off migration — appends the post-launch metric additions (Arun's feedback,
2026-06-24) to the LIVE insight_pilot sheet's component_master/metric_master tabs.

Does NOT recreate the sheet (unlike setup_insight_pilot.py) — appends to the
existing sheet in place, plus relabels cooper_test's display_name.

Run once:
    python migrate_v2_metrics.py
"""

from googleapiclient.discovery import build
from sheets_auth import get_credentials

SHEET_ID = "1B76UiwVHRYuj3B0gClnc-dSxgnKIF52kBcFJQ7IVxEA"  # insight_pilot

NEW_COMPONENT_ROWS = [
    ["skinfold_measurements", "Skinfold Measurements", "composition"],
]

# unit is cm as a placeholder for skinfold — pending confirmation with Arun (may become mm)
NEW_METRIC_ROWS = [
    ["mile_test",                "physio_3",        "1 Mile Test",                    "seconds", "hh:mm:ss", 0, ""],
    ["coordination",             "physio_3",        "Coordination",                   "cm",      "cm",       1, ""],
    ["stork_stand_left_open",    "balance_open",     "Stork Balance Stand (Left)",     "seconds", "s",        0, ""],
    ["stork_stand_right_open",   "balance_open",     "Stork Balance Stand (Right)",    "seconds", "s",        0, ""],
    ["stork_toes_left_open",     "balance_open",     "Stork Balance On Toes (Left)",   "seconds", "s",        0, ""],
    ["stork_toes_right_open",    "balance_open",     "Stork Balance On Toes (Right)",  "seconds", "s",        0, ""],
    ["stork_stand_left_closed",  "balance_closed",   "Stork Balance Stand (Left)",     "seconds", "s",        0, ""],
    ["stork_stand_right_closed", "balance_closed",   "Stork Balance Stand (Right)",    "seconds", "s",        0, ""],
    ["stork_toes_left_closed",   "balance_closed",   "Stork Balance On Toes (Left)",   "seconds", "s",        0, ""],
    ["stork_toes_right_closed",  "balance_closed",   "Stork Balance On Toes (Right)",  "seconds", "s",        0, ""],
    ["skinfold_chest",           "skinfold_measurements", "Chest",   "cm", "cm", 1, ""],
    ["skinfold_abdomen",         "skinfold_measurements", "Abdomen", "cm", "cm", 1, ""],
    ["skinfold_thighs",          "skinfold_measurements", "Thighs",  "cm", "cm", 1, ""],
]

RELABEL = {"cooper_test": "12 min Cooper Test"}  # display_name, column C


def main():
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)

    # 1. Relabel cooper_test's display_name in place
    metric_data = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="metric_master!A:A"
    ).execute().get("values", [])
    for i, row in enumerate(metric_data):
        if row and row[0] in RELABEL:
            cell = f"metric_master!C{i + 1}"
            sheets.spreadsheets().values().update(
                spreadsheetId=SHEET_ID, range=cell,
                valueInputOption="RAW", body={"values": [[RELABEL[row[0]]]]}
            ).execute()
            print(f"Relabeled {row[0]} -> {RELABEL[row[0]]}")

    # 2. Append new component_master + metric_master rows
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range="component_master!A:A",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": NEW_COMPONENT_ROWS}
    ).execute()
    print(f"Appended {len(NEW_COMPONENT_ROWS)} component_master row(s).")

    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID, range="metric_master!A:A",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": NEW_METRIC_ROWS}
    ).execute()
    print(f"Appended {len(NEW_METRIC_ROWS)} metric_master row(s).")

    # 3. Reconciliation
    result = sheets.spreadsheets().values().batchGet(
        spreadsheetId=SHEET_ID,
        ranges=["component_master!A:A", "metric_master!A:A"]
    ).execute()
    ranges = result.get("valueRanges", [])
    names = ["component_master", "metric_master"]
    expected = [12, 62]
    print("\n── Reconciliation ─────────────────────────────────────────────")
    for name, vr, exp in zip(names, ranges, expected):
        data_rows = max(0, len(vr.get("values", [])) - 1)
        status = "✓" if data_rows == exp else "✗"
        print(f"  {status} {name}: {data_rows} data rows (expected {exp})")
    print("────────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
