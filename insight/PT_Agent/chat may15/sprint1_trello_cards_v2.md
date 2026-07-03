# Insight Fitness — Sprint 1 Trello Cards v2
**Sprint goal: Clean normalised sheet with Thilak's historical data + trainer check-in form live**
**One story per card. Paste directly into Claude Code.**

---

## F01-S01 — Define Google Sheets schema

**Context**
Platform data lives entirely in Google Sheets. One spreadsheet per client. This card creates the file structure — tabs and column headers only. No data is seeded here. All other Sprint 1 cards depend on this existing first.

**Input data**

File name: `insight_thilak`

Tab 1: `readings`
```
date | component | metric | value | unit | source | notes
```
- date: string DD/MM/YYYY
- component: string
- metric: string
- value: float
- unit: string
- source: string ("form" / "migration" / "manual")
- notes: string (nullable)

Tab 2: `component_master`
```
component_id | display_name | assessment_type
```

Tab 3: `metric_master`
```
metric_id | component_id | display_name | unit | display_unit | decimal_precision | paired_metric_id
```

Tab 4: `client_info`
```
client_id | full_name | gender | dob | height_cm | client_type | active
```

Tab 5: `admin_config`
```
metric_id | default_chart_type | aggregation_period | active | colour_scale_min | colour_scale_max
```

**Build**
Create a Google Sheets file named `insight_thilak` with exactly 5 tabs in the order listed above. Each tab must have the correct column headers in row 1. All tabs are empty except for headers. Share with trainer Gmail (read/write) and admin Gmail (owner). Return the sheet URL.

**Acceptance criteria**
1. File `insight_thilak` exists in Google Drive
2. File has exactly 5 tabs named: readings, component_master, metric_master, client_info, admin_config — in that order
3. Each tab has correct column headers in row 1 exactly as specified — no extra columns, no renamed columns
4. All tabs are empty below the header row
5. Trainer Gmail has read/write access, admin Gmail is owner

**Dependencies**
None — this is the foundation card.

---

## F01-S02 — Seed component and metric master data

**Context**
With the sheet structure from F01-S01 in place, this card seeds the two reference tabs — component_master and metric_master — with all platform data. These rows define what can be measured and how. No code required — this is a data population task using the Sheets API or direct entry.

**Input data**

`component_master` rows:
```
component_id        | display_name           | assessment_type
body_vitals         | Body Vitals            | composition
body_measurements   | Body Measurements      | composition
anthropometric      | Anthropometric         | composition
physio_1            | Physiological 1        | performance
physio_2            | Physiological 2        | performance
physio_3            | Physiological 3        | performance
balance_open        | Balance Eyes Open      | performance
balance_closed      | Balance Eyes Closed    | performance
strength            | Strength               | performance
ankle_assessment    | Ankle Assessment       | movement
apley_scratch       | Apley Scratch          | movement
```

`metric_master` rows:
```
metric_id                  | component_id       | display_name          | unit    | display_unit | decimal_precision | paired_metric_id
weight_kg                  | body_vitals        | Body Weight           | kg      | kg           | 1                 |
fat_pct                    | body_vitals        | Body Fat %            | %       | %            | 1                 |
muscle_pct                 | body_vitals        | Muscle Mass %         | %       | %            | 1                 |
bp_systol                  | body_vitals        | BP Systolic           | mmHg    | mmHg         | 0                 |
bp_diastol                 | body_vitals        | BP Diastolic          | mmHg    | mmHg         | 0                 |
bpm                        | body_vitals        | Pulse                 | bpm     | bpm          | 0                 |
height_cm                  | body_vitals        | Height                | cm      | cm           | 1                 |
neck                       | body_measurements  | Neck                  | inches  | in           | 1                 |
waist                      | body_measurements  | Waist                 | inches  | in           | 1                 |
abdomen                    | body_measurements  | Abdomen               | inches  | in           | 1                 |
hips                       | body_measurements  | Hips                  | inches  | in           | 1                 |
thighs                     | body_measurements  | Thighs                | inches  | in           | 1                 |
calves                     | body_measurements  | Calves                | inches  | in           | 1                 |
arms                       | body_measurements  | Arms                  | inches  | in           | 1                 |
forearms                   | body_measurements  | Forearms              | inches  | in           | 1                 |
chest                      | body_measurements  | Chest                 | inches  | in           | 1                 |
pushups                    | physio_1           | Pushups               | reps    | reps         | 0                 |
squats                     | physio_1           | Squats                | reps    | reps         | 0                 |
crunches                   | physio_1           | Crunches              | reps    | reps         | 0                 |
pullups_reps               | physio_1           | Pullups               | reps    | reps         | 0                 | pullups_weight
pullups_weight             | physio_1           | Pullups Weight        | lbs     | lbs          | 0                 | pullups_reps
plank                      | physio_2           | Plank                 | seconds | s            | 0                 |
right_side_plank           | physio_2           | Right Side Plank      | seconds | s            | 0                 |
left_side_plank            | physio_2           | Left Side Plank       | seconds | s            | 0                 |
hold_40deg                 | physio_2           | 40° Hold              | seconds | s            | 0                 |
sorenson_hold              | physio_2           | Sorenson Hold         | seconds | s            | 0                 |
cooper_test                | physio_3           | Cooper Test           | km      | km           | 2                 |
flexibility                | physio_3           | Flexibility           | cm      | cm           | 1                 |
balance_normal_open        | balance_open       | Normal                | seconds | s            | 0                 |
balance_tandem_right_open  | balance_open       | Tandem Right          | seconds | s            | 0                 |
balance_tandem_left_open   | balance_open       | Tandem Left           | seconds | s            | 0                 |
balance_right_up_open      | balance_open       | Right Up              | seconds | s            | 0                 |
balance_left_up_open       | balance_open       | Left Up               | seconds | s            | 0                 |
balance_normal_closed      | balance_closed     | Normal                | seconds | s            | 0                 |
balance_tandem_right_closed| balance_closed     | Tandem Right          | seconds | s            | 0                 |
balance_tandem_left_closed | balance_closed     | Tandem Left           | seconds | s            | 0                 |
balance_right_up_closed    | balance_closed     | Right Up              | seconds | s            | 0                 |
balance_left_up_closed     | balance_closed     | Left Up               | seconds | s            | 0                 |
bench_press_reps           | strength           | Bench Press           | reps    | reps         | 0                 | bench_press_weight
bench_press_weight         | strength           | Bench Press Weight    | lbs     | lbs          | 0                 | bench_press_reps
leg_press_reps             | strength           | Leg Press             | reps    | reps         | 0                 | leg_press_weight
leg_press_weight           | strength           | Leg Press Weight      | lbs     | lbs          | 0                 | leg_press_reps
deadlift_reps              | strength           | Deadlift              | reps    | reps         | 0                 | deadlift_weight
deadlift_weight            | strength           | Deadlift Weight       | lbs     | lbs          | 0                 | deadlift_reps
squat_reps                 | strength           | Squat                 | reps    | reps         | 0                 | squat_weight
squat_weight               | strength           | Squat Weight          | lbs     | lbs          | 0                 | squat_reps
```

Also seed `client_info` with one placeholder row:
```
client_id | full_name  | gender | dob        | height_cm | client_type | active
thilak    | Mr Thilak  | M      | 1985-01-01 | 170       | adult       | TRUE
```
Note: dob is a placeholder — confirm actual DOB with trainer before using reference ranges.

**Build**
Write a script that populates component_master, metric_master, and client_info tabs of `insight_thilak` with exactly the rows specified above. Leave readings and admin_config empty.

**Acceptance criteria**
1. component_master has exactly 11 data rows, no duplicates, no blank component_id values
2. metric_master has exactly 46 data rows, no duplicates, no blank metric_id values
3. All paired_metric_id values in metric_master reference an existing metric_id in the same tab
4. Every metric_id in metric_master has a matching component_id in component_master
5. client_info has exactly 1 row for Mr Thilak with gender=M, client_type=adult, active=TRUE
6. readings and admin_config tabs remain empty (headers only)

**Dependencies**
F01-S01 must be complete

---

## F02-S03 — Historical data migration script

**Context**
Trainer has existing client data in a wide-format Excel file. This script reads that file, converts it to normalised rows, and writes to the `readings` tab of `insight_thilak`. Duration values in the old sheet are stored as Excel day fractions (e.g. 0.000289 = 25 seconds) and must be converted to integers representing seconds. Only Thilak's rows should be migrated. BMI and waist_hip_ratio are derived metrics — skip them entirely.

**Input data**

Old sheet: `/mnt/user-data/uploads/Claude_AssessmentImportSample.xlsx`
Filter: rows where `Client Name` = "Mr Thilak"

Column mapping — old sheet → new schema:
```
Old column           → metric_id               | component_id      | conversion
Body Weight In KGs   → weight_kg               | body_vitals       | direct
BP Systol            → bp_systol               | body_vitals       | direct
BP Diastol           → bp_diastol              | body_vitals       | direct
BPM                  → bpm                     | body_vitals       | direct
Height               → height_cm               | body_vitals       | direct
BMI                  → SKIP                    | —                 | derived at report time
a Neck               → neck                    | body_measurements | direct
b Waist              → waist                   | body_measurements | direct
c2 Abdomen           → abdomen                 | body_measurements | direct
d Hips               → hips                    | body_measurements | direct
e Thighs             → thighs                  | body_measurements | direct
f Calves             → calves                  | body_measurements | direct
g Arms               → arms                    | body_measurements | direct
h Fore Arms          → forearms                | body_measurements | direct
c1 Chest             → chest                   | body_measurements | direct
Waist to Hip Ratio   → SKIP                    | —                 | derived at report time
Pushups              → pushups                 | physio_1          | strip non-numeric text, take integer
Squats               → squats                  | physio_1          | direct integer
Crunches             → crunches                | physio_1          | direct integer
Pullups Total        → pullups_reps            | physio_1          | direct integer
Pullups with weights → pullups_reps + pullups_weight | physio_1   | "33 (130 lbs)" → reps=33, weight=130 as two separate rows
5. Plank             → plank                   | physio_2          | value × 86400 → round to int seconds
6. Right Side Plank  → right_side_plank        | physio_2          | same
7. Left side Plank   → left_side_plank         | physio_2          | same
8. 40* hold          → hold_40deg              | physio_2          | same
9. Sorenso hold      → sorenson_hold           | physio_2          | same
12 min Cooper Test   → cooper_test             | physio_3          | direct float
Flexibility          → flexibility             | physio_3          | direct float
Balance Eyes Open × 5 → balance_*_open        | balance_open      | value × 86400 → round to int seconds
Balance Eyes Closed × 5 → balance_*_closed    | balance_closed    | same
```

Date conversion rules:
- Excel serial number (e.g. 46082): `datetime(1899,12,30) + timedelta(days=serial)` → DD/MM/YYYY string
- Year integer (e.g. 2019, 2020, 2021, 2026): treat as 01/01/YYYY
- Already a date string: parse and reformat to DD/MM/YYYY

Source field for all migrated rows: `"migration"`

**Build**
Write a Python script `migrate_thilak.py` that:
1. Reads the xlsx from the path above
2. Filters to Mr Thilak rows only
3. For each component group, extracts date and values using the column mapping above
4. Applies all conversion rules
5. Skips null values entirely — no null rows written
6. Skips BMI and waist_hip_ratio entirely
7. Parses "33 (130 lbs)" style values into two separate rows
8. Writes one row per metric per date to the readings tab of insight_thilak
9. Is idempotent — running twice does not duplicate rows (deduplicate on date+metric_id)
10. Prints a summary: total rows written, rows skipped (null), conversion errors

**Acceptance criteria**
1. Script runs without errors on the provided xlsx
2. All duration values (physio_2, balance) are integers in seconds — not fractions
3. No BMI or waist_hip_ratio rows exist in readings tab
4. No waist_hip_ratio rows exist in readings tab
5. "Pullups with weights" entries produce two rows per date: one pullups_reps, one pullups_weight — both numeric
6. All dates in readings tab are valid DD/MM/YYYY strings
7. source column = "migration" for all rows
8. Running the script twice produces the same number of rows as running it once
9. Summary printout shows rows written, rows skipped, any conversion errors

**Dependencies**
F01-S01 and F01-S02 must be complete

---

## F02-S01 — Trainer check-in form

**Context**
This is the primary handover point — where the trainer becomes the data owner. Trainer opens a saved link on his phone after a client weigh-in and logs weight, fat%, and muscle%. Must be dead simple — 3 fields, one submit, done in under 30 seconds. Writes directly to the readings tab. Built as a Google Apps Script web app — zero infrastructure, no server needed.

**Input data**

Form fields:
```
client_id   → dropdown, values from client_info tab (display full_name, value client_id)
date        → date picker, defaults to today
weight_kg   → number, step=0.1, min=20, max=200, placeholder="e.g. 82.4"
fat_pct     → number, step=0.1, min=1, max=60, placeholder="e.g. 22.1"
muscle_pct  → number, step=0.1, min=1, max=80, placeholder="e.g. 36.8"
```

On submit, write one row per non-empty metric to readings tab:
```
date      | component   | metric     | value | unit | source | notes
{date}    | body_vitals | weight_kg  | {val} | kg   | form   |
{date}    | body_vitals | fat_pct    | {val} | %    | form   |
{date}    | body_vitals | muscle_pct | {val} | %    | form   |
```
Only write rows for fields the trainer actually filled in. Empty field = no row.

Design:
- Mobile-first, large touch targets (min 44px height on inputs)
- Primary colour #1A6B72 teal
- No login required — URL is the access control
- After submit: show "Logged for [full_name] on [date]", clear numeric fields, keep client and date selected

**Build**
Build a mobile-first HTML/CSS/JS form deployed as a Google Apps Script web app on `insight_thilak`. The form reads client list from client_info tab on load. On submit it appends rows to readings tab. Deploy as accessible to anyone with the link (no Google login required). Return the deployed URL.

**Acceptance criteria**
1. Form loads on mobile browser in under 3 seconds
2. Client dropdown shows full_name values from client_info tab
3. Date field defaults to today
4. Submitting weight=82.4, fat=22.1, muscle=36.8 for Thilak creates exactly 3 rows in readings with correct values, units, source="form"
5. Submitting with fat_pct empty creates exactly 2 rows — no null row for fat_pct
6. Submitting with weight empty shows inline validation error and does not submit
7. Confirmation message shows full_name and date after successful submit
8. Form is usable on iPhone Safari and Android Chrome without horizontal scrolling
9. Duplicate submissions on same date are allowed — appended, not overwritten (duplicates handled at query time)

**Dependencies**
F01-S01 and F01-S02 must be complete

---
