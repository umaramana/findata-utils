"""
Migration: add asset_library and metric_asset_groups tabs to the live insight_pilot sheet.
Safe to run multiple times — skips creation if a tab already exists.

Usage:
    python migrate_asset_tables.py

Both tabs start empty (headers only). Populate via Sheets UI or a future seeding script
once asset sourcing is complete (M+F icon set, ungendered images).

asset_library columns    : asset_group_key | gender | role | image_ref
metric_asset_groups cols : metric_id | asset_group_key
"""

import sys
import os
# 1. FIX: Added the missing gspread import
import gspread 

sys.path.insert(0, os.path.dirname(__file__))

from sheets_auth import get_credentials

SHEET_NAME = "insight_pilot"
TABS = {
    "asset_library":      ["asset_group_key", "gender", "role", "image_ref"],
    "metric_asset_groups": ["metric_id", "asset_group_key"],
}


def run():
    print(f"Connecting to '{SHEET_NAME}'...")
    
    # 2. FIX: Named this 'creds' to match what you pass to authorize
    creds = get_credentials()
    
    # 3. FIX: Authorized gspread with the creds variable to build the client
    client = gspread.authorize(creds)
    
    # 4. Open your spreadsheet using the authorized client
    ss = client.open(SHEET_NAME)
    
    existing    = {ws.title for ws in ss.worksheets()}

    for tab_name, headers in TABS.items():
        if tab_name in existing:
            print(f"  '{tab_name}' already exists — skipped.")
            continue
        ws = ss.add_worksheet(title=tab_name, rows=200, cols=len(headers))
        ws.append_row(headers)
        print(f"  '{tab_name}' created with headers: {headers}")

    print("Done.")


if __name__ == "__main__":
    run()
