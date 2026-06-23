# Insight Core — Sprint 1 Cards (VIP Pilot) v2
**Updated 2026-06-23 | Reflects what was actually built and verified**
**Supersedes the version pasted at session start**

---

## S1.1 — Define Google Sheets schema + seed all master data

**Context**
Creates `insight_pilot` Google Sheet with 7 tabs and seeds all master reference data. VIP starts fresh — no migration.

**Script**
`insight/insight_core/setup_insight_pilot.py` — run once. Prints sheet URL and reconciliation on completion.

**Input data**

File name: `insight_pilot`

### Tab 1: `readings` (schema only, empty)
```
client_id | date | component | metric | value | unit | source | notes | recorded_at
STRING    | DATE | STRING    | STRING | FLOAT | STRING | STRING | STRING | DATETIME
```
- `client_id`: links reading to a row in `client_info`
- `date`: stored as YYYY-MM-DD string
- `date + client_id + component + metric` = unique key (no duplicate per client per day)
- `recorded_at`: IST timestamp written by the form on every insert or update (format: `yyyy-MM-dd HH:mm:ss`)

### Tab 2: `component_master` (11 rows)
*(unchanged from original card)*

### Tab 3: `metric_master` (49 rows)
*(unchanged from original card — 46 original + 3 ankle)*

### Tab 4: `client_info` (empty — headers only)
```
client_id | full_name | gender | dob | height_cm | client_type | active
```
Populated via check-in form add-client flow. No seeded rows.

### Tab 5: `admin_config` (schema only, empty)
*(unchanged)*

### Tab 6: `exercise_library` (**41 rows**, not 39)
*(data unchanged from original card — 11 Foam Roll + 2 Static Stretching + 2 PNF + 26 General)*

### Tab 7: `muscle_groups_library` (11 rows)
*(unchanged)*

**Acceptance criteria**
1. File `insight_pilot` exists with exactly 7 tabs: readings, component_master, metric_master, client_info, admin_config, exercise_library, muscle_groups_library — in that order
2. `readings` tab has 9 column headers in row 1: client_id, date, component, metric, value, unit, source, notes, recorded_at — no data rows
3. `component_master` has exactly 11 data rows, no blank component_id
4. `metric_master` has exactly 49 data rows, no blank metric_id, all paired_metric_id values reference an existing metric_id
5. `client_info` has 0 data rows (headers only)
6. `admin_config` has 0 data rows (headers only)
7. `exercise_library` has exactly 41 data rows, all deviation_id = "ankle_pronation"
8. `muscle_groups_library` has exactly 11 data rows, group_type is "tighten" or "lengthen"
9. Trainer (arunalexdavid1991@gmail.com) has writer access; admin (uma.nat.raj@gmail.com) is owner
10. Script prints reconciliation: ✓ for each tab count on completion

**Dependencies**
None — foundation card.

---

## S1.2 — Check-in form (trainer-facing)

**Context**
Trainer opens a saved link on his phone after a session and logs weight, fat%, muscle% for one client. Writes to `readings` tab of `insight_pilot`. Built as Google Apps Script web app bound to the spreadsheet.

**Files**
- `insight/insight_core/apps_script/Code.gs` — server-side GAS functions
- `insight/insight_core/apps_script/index.html` — mobile form UI

**Deployment**
1. Open `insight_pilot` → Extensions → Apps Script
2. Paste Code.gs; add HTML file named `index`, paste index.html
3. Deploy → Web app → Execute as Me (uma.nat.raj@gmail.com) → Anyone with link
4. Deployed URL: https://script.google.com/macros/s/AKfycbxwDg_tBz4nDQaxDyN2i5TUnc9hW1bVVso3xm9_1g2vzobY0DHubIdVzklpkuJDEg6NpQ/exec

**Form fields**
```
client_id   → dropdown from client_info (displays full_name) + "+ Add new client" at top
date        → date picker, defaults to today, max = today (future dates blocked)
weight_kg   → number, step=0.1, min=20, max=200 — required
fat_pct     → number, step=0.1, min=1, max=60 — optional
muscle_pct  → number, step=0.1, min=1, max=80 — optional
```

**Inline add-client flow**
Selecting "+ Add new client" reveals an inline form:
```
full_name  → text, required
gender     → M/F toggle (radio styled as segmented control)
dob        → three-select dropdowns: Day / Month / Year (years 1940–current, descending)
             stored as YYYY-MM-DD; all three must be filled or dob stored as empty string
height_cm  → number, step=0.1 — optional
```
On save: generates `client_id` (slugified full_name, deduped with numeric suffix if collision), appends to `client_info` with `client_type=adult`, `active=TRUE`. Dropdown reloads with new client pre-selected.

**Reading submit behaviour (upsert)**
On submit, for each metric with a value:
- If a row exists for `client_id + date + component + metric`: update `value` and `recorded_at` in-place
- If no row exists: append new row with all 9 columns including `recorded_at`

For each metric field that is **cleared** (empty on submit):
- If a row exists for that metric on that date: **delete the row**
- If no row exists: skip

Weight is required — form will not submit if empty. fat_pct and muscle_pct are optional.

**Pre-fill behaviour**
Selecting a client or changing the date triggers a lookup of existing readings for that client+date. Any existing values are pre-filled into the input fields so the trainer can see and correct them.

**Readings written**
```
client_id | date | component   | metric     | value | unit | source | notes | recorded_at
{id}      | {d}  | body_vitals | weight_kg  | {val} | kg   | form   |       | {IST timestamp}
{id}      | {d}  | body_vitals | fat_pct    | {val} | %    | form   |       | {IST timestamp}
{id}      | {d}  | body_vitals | muscle_pct | {val} | %    | form   |       | {IST timestamp}
```

**Acceptance criteria**
1. Form loads on mobile browser within 3 seconds
2. Client dropdown shows full_name values from client_info, with "+ Add new client" as the first option
3. Selecting "+ Add new client" reveals the inline form without navigating away
4. Submitting add-client with full_name="Test Person", gender=F, DOB day=1/month=Jan/year=2000, height=165 creates exactly 1 row in client_info: client_id=test_person, dob=2000-01-01, client_type=adult, active=TRUE
5. After adding a client, dropdown returns to main form with new client pre-selected
6. Date defaults to today; selecting a future date is blocked by the date picker
7. Selecting a client and date pre-fills any existing readings for that client+date into the input fields
8. Submitting weight=82.4, fat=22.1, muscle=36.8 creates exactly 3 rows in readings with correct values, units, source="form", and a recorded_at IST timestamp; each row has the client_id in column A
9. Re-submitting with weight=83.0 on the same date updates the existing weight row value and recorded_at in-place — no duplicate row created
10. Re-submitting with fat_pct cleared (empty) deletes the existing fat_pct row for that date — row count drops by 1
11. Submitting with weight empty shows inline validation error; form does not submit
12. Confirmation message shows client full_name and date (DD/MM/YYYY) after successful submit; numeric fields clear; client and date remain selected
13. Multiple clients can submit readings independently — readings are correctly separated by client_id in the readings tab
14. Usable on iPhone Safari and Android Chrome without horizontal scroll

**Dependencies**
S1.1 complete; readings tab header updated to 9-column schema before first GAS deployment.
