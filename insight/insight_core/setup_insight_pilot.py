"""
S1.1 — Creates the insight_pilot Google Sheet with 7 tabs and seeds all master data.
Run once. Prints the sheet URL on completion.

Usage:
    pip install -r requirements.txt
    python setup_insight_pilot.py

Prerequisites:
    - credentials.json in this folder (see sheets_auth.py)
    - First run opens a browser for OAuth consent (sign in as umanatraj@gmail.com)
"""

from googleapiclient.discovery import build
from sheets_auth import get_credentials

TRAINER_GMAIL = "arunalexdavid1991@gmail.com"
ADMIN_GMAIL = "umanatraj@gmail.com"
SHEET_TITLE = "insight_pilot"

# ── Seed data ────────────────────────────────────────────────────────────────

COMPONENT_MASTER_HEADERS = ["component_id", "display_name", "assessment_type"]
COMPONENT_MASTER_ROWS = [
    ["body_vitals",       "Body Vitals",          "composition"],
    ["body_measurements", "Body Measurements",     "composition"],
    ["anthropometric",    "Anthropometric",        "composition"],
    ["physio_1",          "Physiological 1",       "performance"],
    ["physio_2",          "Physiological 2",       "performance"],
    ["physio_3",          "Physiological 3",       "performance"],
    ["balance_open",      "Balance Eyes Open",     "performance"],
    ["balance_closed",    "Balance Eyes Closed",   "performance"],
    ["strength",          "Strength",              "performance"],
    ["ankle_assessment",  "Ankle Assessment",      "movement"],
    ["apley_scratch",     "Apley Scratch",         "movement"],
    ["skinfold_measurements", "Skinfold Measurements", "composition"],
]

METRIC_MASTER_HEADERS = [
    "metric_id", "component_id", "display_name", "unit",
    "display_unit", "decimal_precision", "paired_metric_id"
]
METRIC_MASTER_ROWS = [
    # body_vitals (7)
    ["weight_kg",   "body_vitals",      "Body Weight",      "kg",      "kg",   1, ""],
    ["fat_pct",     "body_vitals",      "Body Fat %",       "%",       "%",    1, ""],
    ["muscle_pct",  "body_vitals",      "Muscle Mass %",    "%",       "%",    1, ""],
    ["bp_systol",   "body_vitals",      "BP Systolic",      "mmHg",    "mmHg", 0, ""],
    ["bp_diastol",  "body_vitals",      "BP Diastolic",     "mmHg",    "mmHg", 0, ""],
    ["bpm",         "body_vitals",      "Pulse",            "bpm",     "bpm",  0, ""],
    ["height_cm",   "body_vitals",      "Height",           "cm",      "cm",   1, ""],
    # body_measurements (9)
    ["neck",        "body_measurements", "Neck",            "inches",  "in",   1, ""],
    ["waist",       "body_measurements", "Waist",           "inches",  "in",   1, ""],
    ["abdomen",     "body_measurements", "Abdomen",         "inches",  "in",   1, ""],
    ["hips",        "body_measurements", "Hips",            "inches",  "in",   1, ""],
    ["thighs",      "body_measurements", "Thighs",          "inches",  "in",   1, ""],
    ["calves",      "body_measurements", "Calves",          "inches",  "in",   1, ""],
    ["arms",        "body_measurements", "Arms",            "inches",  "in",   1, ""],
    ["forearms",    "body_measurements", "Forearms",        "inches",  "in",   1, ""],
    ["chest",       "body_measurements", "Chest",           "inches",  "in",   1, ""],
    # physio_1 (5)
    ["pushups",         "physio_1", "Pushups",          "reps", "reps", 0, ""],
    ["squats",          "physio_1", "Squats",           "reps", "reps", 0, ""],
    ["crunches",        "physio_1", "Crunches",         "reps", "reps", 0, ""],
    ["pullups_reps",    "physio_1", "Pullups",          "reps", "reps", 0, "pullups_weight"],
    ["pullups_weight",  "physio_1", "Pullups Weight",   "lbs",  "lbs",  0, "pullups_reps"],
    # physio_2 (5)
    ["plank",             "physio_2", "Plank",           "seconds", "s", 0, ""],
    ["right_side_plank",  "physio_2", "Right Side Plank","seconds", "s", 0, ""],
    ["left_side_plank",   "physio_2", "Left Side Plank", "seconds", "s", 0, ""],
    ["hold_40deg",        "physio_2", "40° Hold",        "seconds", "s", 0, ""],
    ["sorenson_hold",     "physio_2", "Sorenson Hold",   "seconds", "s", 0, ""],
    # physio_3 (4 — added mile_test + coordination, relabeled cooper_test, per Arun's feedback)
    ["cooper_test",   "physio_3", "12 min Cooper Test",  "km",      "km",      2, ""],
    ["mile_test",     "physio_3", "1 Mile Test",          "seconds", "hh:mm:ss", 0, ""],
    ["flexibility",   "physio_3", "Flexibility",          "cm",      "cm",      1, ""],
    ["coordination",  "physio_3", "Coordination",         "cm",      "cm",      1, ""],
    # balance_open (9 — added 4 stork tests, per Arun's feedback)
    ["balance_normal_open",        "balance_open", "Normal",      "seconds", "s", 0, ""],
    ["balance_tandem_right_open",  "balance_open", "Tandem Right","seconds", "s", 0, ""],
    ["balance_tandem_left_open",   "balance_open", "Tandem Left", "seconds", "s", 0, ""],
    ["balance_right_up_open",      "balance_open", "Right Up",    "seconds", "s", 0, ""],
    ["balance_left_up_open",       "balance_open", "Left Up",     "seconds", "s", 0, ""],
    ["stork_stand_left_open",      "balance_open", "Stork Balance Stand (Left)",    "seconds", "s", 0, ""],
    ["stork_stand_right_open",     "balance_open", "Stork Balance Stand (Right)",   "seconds", "s", 0, ""],
    ["stork_toes_left_open",       "balance_open", "Stork Balance On Toes (Left)",  "seconds", "s", 0, ""],
    ["stork_toes_right_open",      "balance_open", "Stork Balance On Toes (Right)", "seconds", "s", 0, ""],
    # balance_closed (9 — same 4 stork tests added)
    ["balance_normal_closed",        "balance_closed", "Normal",      "seconds", "s", 0, ""],
    ["balance_tandem_right_closed",  "balance_closed", "Tandem Right","seconds", "s", 0, ""],
    ["balance_tandem_left_closed",   "balance_closed", "Tandem Left", "seconds", "s", 0, ""],
    ["balance_right_up_closed",      "balance_closed", "Right Up",    "seconds", "s", 0, ""],
    ["balance_left_up_closed",       "balance_closed", "Left Up",     "seconds", "s", 0, ""],
    ["stork_stand_left_closed",      "balance_closed", "Stork Balance Stand (Left)",    "seconds", "s", 0, ""],
    ["stork_stand_right_closed",     "balance_closed", "Stork Balance Stand (Right)",   "seconds", "s", 0, ""],
    ["stork_toes_left_closed",       "balance_closed", "Stork Balance On Toes (Left)",  "seconds", "s", 0, ""],
    ["stork_toes_right_closed",      "balance_closed", "Stork Balance On Toes (Right)", "seconds", "s", 0, ""],
    # strength (8)
    ["bench_press_reps",    "strength", "Bench Press",        "reps", "reps", 0, "bench_press_weight"],
    ["bench_press_weight",  "strength", "Bench Press Weight", "lbs",  "lbs",  0, "bench_press_reps"],
    ["leg_press_reps",      "strength", "Leg Press",          "reps", "reps", 0, "leg_press_weight"],
    ["leg_press_weight",    "strength", "Leg Press Weight",   "lbs",  "lbs",  0, "leg_press_reps"],
    ["deadlift_reps",       "strength", "Deadlift",           "reps", "reps", 0, "deadlift_weight"],
    ["deadlift_weight",     "strength", "Deadlift Weight",    "lbs",  "lbs",  0, "deadlift_reps"],
    ["squat_reps",          "strength", "Squat",              "reps", "reps", 0, "squat_weight"],
    ["squat_weight",        "strength", "Squat Weight",       "lbs",  "lbs",  0, "squat_reps"],
    # ankle_assessment (3) — 1=pass/yes, 0=fail/no stored in FLOAT value column
    ["ankle_right_mobility", "ankle_assessment", "Right Ankle Mobility",        "pass/fail", "—", 0, ""],
    ["ankle_left_mobility",  "ankle_assessment", "Left Ankle Mobility",         "pass/fail", "—", 0, ""],
    ["ankle_pronation",      "ankle_assessment", "Ankle Pronation Present",     "yes/no",    "—", 0, ""],
    # skinfold_measurements (3) — mm, confirmed with Arun (2026-06-24, standard caliper unit)
    ["skinfold_chest",   "skinfold_measurements", "Chest",   "mm", "mm", 1, ""],
    ["skinfold_abdomen", "skinfold_measurements", "Abdomen", "mm", "mm", 1, ""],
    ["skinfold_thighs",  "skinfold_measurements", "Thighs",  "mm", "mm", 1, ""],
]

EXERCISE_LIBRARY_HEADERS = [
    "deviation_id", "category", "muscle_group", "exercise_name",
    "instructions", "video_insight", "video_external", "source", "status"
]
# 41 rows from card data (card acceptance criteria said 39 — reconcile with source JSON)
EXERCISE_LIBRARY_ROWS = [
    # Foam Roll (11)
    ["ankle_pronation","Foam Roll","Peroneal Group","Peroneus Longus SMR","","","https://www.youtube.com/watch?v=mNkT0AbkEy4","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Peroneal Group","Peroneus Brevis SMR","","","https://www.youtube.com/watch?v=mNkT0AbkEy4","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Peroneal Group","Peroneus Tertius SMR","","","https://www.youtube.com/watch?v=mNkT0AbkEy4","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Toe Extensors","Extensor Digitorum Longus SMR","","","https://www.youtube.com/watch?v=K20nG3oaxo8","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Toe Extensors","Extensor Digitorum Brevis SMR","","","https://www.youtube.com/watch?v=K20nG3oaxo8","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Toe Extensors","Extensor Hallucis Brevis SMR","","","https://www.youtube.com/watch?v=K20nG3oaxo8","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Toe Extensors","Extensor Hallucis Longus SMR","","","https://www.youtube.com/watch?v=K20nG3oaxo8","NASM","external_only"],
    ["ankle_pronation","Foam Roll","Tibialis Posterior","Tibialis Posterior SMR","","","","","pending_video"],
    ["ankle_pronation","Foam Roll","Toe Flexors","Flexor Digitorum Longus SMR","","","","","pending_video"],
    ["ankle_pronation","Foam Roll","Toe Flexors","Flexor Hallucis Longus SMR","","","","","pending_video"],
    ["ankle_pronation","Foam Roll","Tibialis Anterior","Tibialis Anterior SMR","","","https://www.youtube.com/watch?v=K20nG3oaxo8","NASM","external_only"],
    # Static Stretching (2)
    ["ankle_pronation","Static Stretching","Peroneal Group","Peroneal Static Stretch","Toe pointed down, invert ankle and hold","","","","pending_video"],
    ["ankle_pronation","Static Stretching","Toe Extensors","Toe Extensor Static Stretch","Toe pointed down, pull and hold toe pointing down","","","","pending_video"],
    # PNF (2)
    ["ankle_pronation","PNF","Peroneal Group","Peroneal PNF Stretch","Same as static stretch, added push against resistance","","","","pending_video"],
    ["ankle_pronation","PNF","Toe Extensors","Toe Extensor PNF Stretch","Same as static stretch, with added resistance by partner","","","","pending_video"],
    # General (26)
    ["ankle_pronation","General","—","Foot Foam Rolling","","","https://www.youtube.com/watch?v=6f2LO5EeB0I","NASM","external_only"],
    ["ankle_pronation","General","—","Shin Foam Rolling","","","https://www.youtube.com/watch?v=K20nG3oaxo8","NASM","external_only"],
    ["ankle_pronation","General","—","Peroneal Foam Rolling","","","https://www.youtube.com/watch?v=mNkT0AbkEy4","NASM","external_only"],
    ["ankle_pronation","General","—","Calf Foam Rolling","","","https://www.youtube.com/watch?v=w-e7YIpiok0","NASM","external_only"],
    ["ankle_pronation","General","—","Kneeling Foot Stretch","","","https://redefiningstrength.com/4-exercises-to-prevent-foot-and-ankle-pain/","Redefining Strength","external_only"],
    ["ankle_pronation","General","—","Kneeling Foot Stretch to Bear Squat","","","https://redefiningstrength.com/4-exercises-to-prevent-foot-and-ankle-pain/","Redefining Strength","external_only"],
    ["ankle_pronation","General","—","Peroneal Shin Stretch","","","","","pending_video"],
    ["ankle_pronation","General","—","Single Leg Roll to Toes","","","","","pending_video"],
    ["ankle_pronation","General","—","Roll to Squat","","","","","pending_video"],
    ["ankle_pronation","General","—","Three Way Ankle Mobility","","","https://www.youtube.com/watch?v=PKGwPvuGA9s","Redefining Strength","external_only"],
    ["ankle_pronation","General","—","Three Way Shin Stretch","","","","","pending_video"],
    ["ankle_pronation","General","—","Heel to Toe Rocks","","","","","pending_video"],
    ["ankle_pronation","General","—","Inside / Outside Rocks","","","","","pending_video"],
    ["ankle_pronation","General","—","Standing Calf Stretch","","","https://www.youtube.com/watch?v=w-e7YIpiok0","NASM","external_only"],
    ["ankle_pronation","General","—","Knee Friendly Ankle Mobility","","","","","pending_video"],
    ["ankle_pronation","General","—","Calf Raise Circles","","","https://redefiningstrength.com/4-exercises-to-prevent-foot-and-ankle-pain/","Redefining Strength","external_only"],
    ["ankle_pronation","General","—","Standing Ankle Circles","","","","","pending_video"],
    ["ankle_pronation","General","—","Leg Swings","","","","","pending_video"],
    ["ankle_pronation","General","—","Three Way Calf Raises","","","","","pending_video"],
    ["ankle_pronation","General","—","Toe Scrunches","","","","","pending_video"],
    ["ankle_pronation","General","—","Heel Walks","","","","","pending_video"],
    ["ankle_pronation","General","—","Toe Walks","","","","","pending_video"],
    ["ankle_pronation","General","—","Pronation Walks","","","","","pending_video"],
    ["ankle_pronation","General","—","Supination Walks","","","","","pending_video"],
    ["ankle_pronation","General","—","Foot Circles and Point Flexes (Alphabet)","","","","","pending_video"],
    ["ankle_pronation","General","—","Gravity Drop","","","","","pending_video"],
]

MUSCLE_GROUPS_HEADERS = ["deviation_id", "group_type", "muscle_name"]
MUSCLE_GROUPS_ROWS = [
    ["ankle_pronation", "tighten", "Peroneus Longus"],
    ["ankle_pronation", "tighten", "Peroneus Brevis"],
    ["ankle_pronation", "tighten", "Peroneus Tertius"],
    ["ankle_pronation", "tighten", "Extensor Digitorum Longus"],
    ["ankle_pronation", "tighten", "Extensor Digitorum Brevis"],
    ["ankle_pronation", "tighten", "Extensor Hallucis Brevis"],
    ["ankle_pronation", "tighten", "Extensor Hallucis Longus"],
    ["ankle_pronation", "lengthen", "Tibialis Posterior"],
    ["ankle_pronation", "lengthen", "Flexor Digitorum Longus"],
    ["ankle_pronation", "lengthen", "Flexor Hallucis Longus"],
    ["ankle_pronation", "lengthen", "Tibialis Anterior (possibly)"],
]

# ── Schema-only tabs (headers only, no data rows) ────────────────────────────

READINGS_HEADERS   = ["client_id", "date", "component", "metric", "value", "unit", "source", "notes", "recorded_at"]
CLIENT_INFO_HEADERS = ["client_id", "full_name", "gender", "dob", "height_cm", "client_type", "active"]
ADMIN_CONFIG_HEADERS = ["metric_id", "default_chart_type", "aggregation_period", "active", "colour_scale_min", "colour_scale_max"]

# ── Tab order (must match acceptance criteria) ───────────────────────────────

TABS = [
    "readings",
    "component_master",
    "metric_master",
    "client_info",
    "admin_config",
    "exercise_library",
    "muscle_groups_library",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_range_data(tab, headers, rows):
    return {
        "range": f"{tab}!A1",
        "values": [headers] + rows
    }


def _verify_counts(sheets_service, sheet_id):
    result = sheets_service.spreadsheets().values().batchGet(
        spreadsheetId=sheet_id,
        ranges=[
            "component_master!A:A",
            "metric_master!A:A",
            "client_info!A:A",
            "exercise_library!A:A",
            "muscle_groups_library!A:A",
        ]
    ).execute()

    ranges = result.get("valueRanges", [])
    names = ["component_master", "metric_master", "client_info", "exercise_library", "muscle_groups_library"]
    expected = [12, 62, 0, len(EXERCISE_LIBRARY_ROWS), 11]

    print("\n── Reconciliation ─────────────────────────────────────────────")
    all_ok = True
    for name, vr, exp in zip(names, ranges, expected):
        vals = vr.get("values", [])
        data_rows = max(0, len(vals) - 1)  # subtract header row
        status = "✓" if data_rows == exp else "✗"
        if data_rows != exp:
            all_ok = False
        print(f"  {status} {name}: {data_rows} data rows (expected {exp})")
    print("────────────────────────────────────────────────────────────────")
    return all_ok


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds)
    drive  = build("drive",  "v3", credentials=creds)

    # 1. Create spreadsheet with all 7 tabs in one call
    print(f"Creating '{SHEET_TITLE}'...")
    body = {
        "properties": {"title": SHEET_TITLE},
        "sheets": [{"properties": {"title": t, "index": i}} for i, t in enumerate(TABS)]
    }
    response = sheets.spreadsheets().create(body=body, fields="spreadsheetId").execute()
    sheet_id = response["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    print(f"Created: {sheet_url}")

    # 2. Write all headers + seed data in one batch update
    print("Seeding data...")
    data_ranges = [
        _build_range_data("readings",             READINGS_HEADERS,        []),
        _build_range_data("component_master",     COMPONENT_MASTER_HEADERS, COMPONENT_MASTER_ROWS),
        _build_range_data("metric_master",        METRIC_MASTER_HEADERS,    METRIC_MASTER_ROWS),
        _build_range_data("client_info",          CLIENT_INFO_HEADERS,      []),
        _build_range_data("admin_config",         ADMIN_CONFIG_HEADERS,     []),
        _build_range_data("exercise_library",     EXERCISE_LIBRARY_HEADERS, EXERCISE_LIBRARY_ROWS),
        _build_range_data("muscle_groups_library",MUSCLE_GROUPS_HEADERS,    MUSCLE_GROUPS_ROWS),
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={"valueInputOption": "RAW", "data": data_ranges}
    ).execute()
    print("Data written.")

    # 3. Share with trainer (writer) — admin is already owner as the OAuth user
    print(f"Sharing with trainer ({TRAINER_GMAIL})...")
    drive.permissions().create(
        fileId=sheet_id,
        body={"type": "user", "role": "writer", "emailAddress": TRAINER_GMAIL},
        fields="id",
        sendNotificationEmail=False
    ).execute()
    print("Shared.")

    # 4. Reconciliation
    ok = _verify_counts(sheets, sheet_id)

    print(f"\nSheet URL: {sheet_url}")
    if not ok:
        print("⚠ One or more row counts did not match expected. Check reconciliation above.")
    else:
        print("✓ All row counts match. S1.1 complete.")


if __name__ == "__main__":
    main()
