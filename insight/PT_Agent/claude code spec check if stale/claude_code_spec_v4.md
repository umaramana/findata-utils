# Fitness Assessment Report Generator — Claude Code Spec v3

## What this app does
A Python app with a simple UI. Trainer picks a client and a date range. App reads data from a public Google Sheet, generates a professionally branded PDF report (charts, tables, illustrations) that replicates the Insight dashboard layout, and saves it to a Google Drive folder. No Looker Studio dependency for PDF generation — Looker remains the live dashboard tool only.

---

## Architecture

```
Google Sheets (source of truth)
        ↓ reads via Sheets API (public, no auth)
Python App (UI + orchestration + PDF generation)
        ↓ reads gym_config.json + platform assets
Branding Layer (Insight logos, gym badge, illustrations)
        ↓ assembles into pages
PDF Output (matplotlib charts + reportlab/fpdf layout)
        ↓ saves via Drive API
Google Drive Folder (output)
```

---

## Branding Architecture — Two Layers

### Layer 1: Insight (Platform) — ALWAYS ON, NEVER CHANGES

These are fixed assets. Hardcoded into the app. Trainer cannot modify.

- **Insight logo** — top left on every content page (small), large center on back page
- **Color palette for data visualisation (3-shade gradient):**
  - Primary: Deep Magenta/Burgundy `#8B1A4A` — main bars, table headers, title text
  - Secondary: Pink `#E8729A` — second date/series in grouped charts
  - Tertiary: Lavender/Light pink `#D4A5C9` — third date/series
- **Decorative elements (replicate exactly):**
  - Dot grids in all 4 corners of every page (multicolored, matching logo dots)
  - Left edge vertical stripe in deep magenta on every page
- **Typography (confirmed):**
  - Titles: **Bubblegum Sans** (Google Font)
  - Body / data / table text: **Roboto Condensed** (Google Font)
- **Back page static text:**
  - "Thank You!!"
  - Insight large logo
  - Tagline: "Holistic fitness.."
  - Mission: "No matter what age or goal you have, you feel confident in your own body. You can feel that beautiful being, both Inside and Outside!"

### Layer 2: Gym — Config-driven, changes per gym

Everything in this layer comes from `gym_config.json`. App renders only what's populated. No code changes needed to add a new gym in Phase 2.

**Gym badge logo — two options, both supported:**
- **Option A (Uploaded):** Gym provides their own logo image file. App drops it into position as-is. Trainer or admin just places the file in the gym's asset folder.
- **Option B (Auto-generated):** App generates a circular badge at runtime using a template. Gym provides: name, city, and a primary color. App renders text onto the badge programmatically. Uses same circular layout as the Insight Chennai badge in the PDF.

The config field `logo.type` switches between these. Both supported from day one.

**Trainer info (on back page):**
- Name
- Certifications (array — renders each on its own line)
- Contact icons (see below)

**Contact icons — provisioned for extensibility:**
The back page renders contact info below the trainer name. Phase 1 uses phone only. App provisions for all of these from day one — only populated fields render:

| Icon Type | Example Value |
|---|---|
| phone | 97911 72562 |
| email | trainer@gym.com |
| whatsapp | 97911 72562 |
| instagram | @gymhandle |
| facebook | facebook.com/gym |
| website | www.gym.com |
| address | Chennai, Tamil Nadu |

Each icon is a standard SVG or PNG asset bundled with the app. Config just specifies type + value. If a field is empty or missing, that icon doesn't render. Adding a new icon type in future = add the asset + add one entry to the supported list. No structural code change.

---

## gym_config.json — Full Structure

```json
{
  "gym_name": "Insight Chennai",
  "city": "Chennai",
  "logo": {
    "type": "generated",
    "color": "#1B4332",
    "uploaded_path": null
  },
  "trainer": {
    "name": "Arun Alex David",
    "certifications": [
      "ACE Certified Personal Trainer",
      "NASM Certified Youth Exercise Specialist"
    ]
  },
  "contact_icons": [
    { "type": "phone", "value": "97911 72562" },
    { "type": "email", "value": "" },
    { "type": "whatsapp", "value": "" },
    { "type": "instagram", "value": "" },
    { "type": "facebook", "value": "" },
    { "type": "website", "value": "" },
    { "type": "address", "value": "" }
  ],
  "back_page": {
    "thank_you_text": "Thank You!!",
    "mission_text": "No matter what age or goal you have, you feel confident in your own body. You can feel that beautiful being, both Inside and Outside!"
  }
}
```

Phase 1: one config file, some fields empty. Phase 2: one config file per gym, each gym fills what they want.

---

## Data Source: Google Sheets

**Sheet ID:** `14km--5g-bCnzhkPotmaVbWNGxio09lOiJ3GsYWAFSCE`
**Public sheet** — no OAuth for reading.

### Schema

Row 1 = headers. Data starts Row 2. Grouped column structure — each assessment group has its own date column.

**Col A:** Client Name
**Col B:** Gender (M / F)

| Group | Date Col | Data Columns |
|---|---|---|
| Body Vitals | C | E: Weight (KG), F: BP Systol, G: BP Diastol, H: BPM, I: Height, J: BMI |
| Body Measurements | K | L: Neck, M: Waist, N: Abdomen, O: Hips, P: Thighs, Q: Calves, R: Arms, S: Fore Arms, T: Chest, U: WHR |
| Physio Assessment 1 | V | W: Pushups, X: Squats, Y: Crunches, Z: Pullups w/ weights, AA: Pullups Total |
| Physio Assessment 2 | AB | AC: Plank, AD: Right Side Plank, AE: Left Side Plank, AF: 40* hold, AG: Sorenso hold |
| Physio Assessment 3 | AH | AI: Cooper Test (KMs), AJ: Flexibility (cms), AK: Coordination |
| Strength | AL | AM: Bench Press, AN: Leg Press, AO: Deadlift, AP: Squat RM |
| Balance Eyes Open | AQ | AR-AZ: 9 balance metrics |
| Balance Eyes Closed | BA | BB-BJ: same 9 metrics with (C) suffix |
| Skinfold Measurements | BK | BL: Chest, BM: Abdomen, BN: Thighs |

### Data quirks the app MUST handle:
1. **Per-group dates** — each group has its own date. Filter per group independently.
2. **Sparse cells** — many empty. Skip empty groups entirely in output.
3. **Annotated values** — e.g. `14 (M)`, `33 (130 lbs)`, `7 (No weights)`. Strip parenthetical, extract numeric. Store annotation separately for display if needed.
4. **Client name variants** — e.g. "Anupama Baskar Prev" vs "Anupama Baskar". Show as-is in dropdown. Do not auto-merge.
5. **Date format** — "Mon YYYY" (e.g. "Oct 2022"). Parse with month name.
6. **Trend arrows** — app must calculate direction (▲/▼) by comparing latest value to previous value in the selected range. Render on table section headers where applicable.

---

## Page Composition Logic — Three Layers

Three concerns, applied in this exact order. Get the order wrong and the page layout breaks.

### Layer 1: Gender (determines layout templates)

Picked once from Col B. Affects which page templates are used — not what's included.

**Body Measurements page(s):**
- Female → 2 pages: standalone grouped bar chart, then dense dashboard (Weight, BP, Pulse donut, WHR, BMI)
- Male → 1 combined page: grouped bar chart left, Body Weight right, WHR bottom-left, BMI bottom-right. No BP. No Pulse donut.

**Body Measurements chart categories:**
- Female: Neck, Waist, Abdomen, Hips, Thighs, Calves, Arms, Fore Arms (8)
- Male: Neck, Waist, Chest, Abdomen, Hips, Thighs, Calves, Arms, Fore Arms (9 — adds Chest)

**Illustration sets:**
- Female pages → female cartoon illustrations
- Male pages → male cartoon illustrations
- Male Strength standalone → black silhouette illustrations
- Male Skinfold section → doctor/measurement illustration

### Layer 2: Data Availability Gate (automatic, runs before UI renders)

App scans the sheet for the selected client + date range. For each assessment group: if ALL data cells are empty in that range → group is dead. Does not exist. No checkbox, no page, nothing.

This applies uniformly to every group. Balance Eyes Open with no data in range = invisible. Skinfold with no data = invisible. Any group.

**Two categories of groups with different behaviour at this layer:**

*Mandatory groups (no checkbox, always included — no conditions):*
- Body Vitals (Weight, BP, Pulse, WHR, BMI) — ALWAYS in the report. Even if every cell is empty for the selected range. Empty metrics render as blank/no data. No data availability check. No checkbox.
- Body Measurements — included if data exists. No checkbox. Trainer cannot exclude it.

*Toggleable groups (checkbox appears if data exists):*
- Physio Assessment 1
- Physio Assessment 2
- Physio Assessment 3
- Strength
- Balance Eyes Open
- Balance Eyes Closed
- Skinfold Measurements

If data exists → checkbox appears, pre-checked. If no data → no checkbox shown at all.

### Layer 3: Trainer Selection (manual, checkbox UI)

Trainer sees only the checkboxes that passed Layer 2. Can uncheck any toggleable group to exclude it from the report. Mandatory groups have no checkbox — they're just included.

**This is the final input.** Everything downstream (page composition, Skinfold/Strength split, page count, page numbering) is calculated AFTER Layer 3 resolves.

### Skinfold / Strength Split — resolved last

This runs after all three layers have resolved. The decision is based on the EFFECTIVE state — meaning: does Skinfold appear in the final report (data exists AND trainer left it checked)?

- Skinfold is in the final report → Skinfold takes a slot on the Physio 3 page, Strength gets its own standalone page
- Skinfold is NOT in the final report (either no data, or trainer unchecked it) → Strength stays grouped on the Physio 3 page

Example: Pranav 2025 has Skinfold data. Trainer leaves it checked → Strength standalone page appears. Same client, trainer unchecks Skinfold → Strength moves back to grouped page. No Skinfold page in output.

### Execution order (the app does this in sequence):
1. Read gender → pick template set
2. Scan all groups for data in selected range → build "available groups" list
3. Render UI: mandatory groups silently included, toggleable groups shown as checkboxes (only if available)
4. Trainer checks/unchecks → "selected groups" list
5. Resolve Skinfold/Strength split based on selected groups
6. Compose pages, assign page numbers, generate PDF

---

## PDF Page Templates — Full Structure

### Page: Cover (both genders — identical)
- Top left: Insight logo + "BROUGHT TO YOU FROM" label + "Holistic fitness.."
- Top right: Gym badge logo (Option A or B) + "IN THE SERVICE OF" label
- Center: "Fitness Dashboard for" + **[Client Name]** + period text
  - Single year: "Summary Details of [YYYY]"
  - Multi-year range: "Fitness Assessment Reports [Mon YYYY] to [Mon YYYY]"
- Decorative dots all 4 corners, magenta left stripe

### Page: Body Measurements — FEMALE TEMPLATE (2 pages)

**Page F-BM1: Grouped Bar Chart (standalone)**
- Title: "Body Measurements –1" center top
- "No data" + date range label top right (if any date missing data)
- Units note: "Measurement units: Inches / Decimal Precision - 0"
- Full-width grouped bar chart: 8 measurement categories (Neck, Waist, Abdomen, Hips, Thighs, Calves, Arms, Fore Arms), up to 3 date clusters each
- Insight logo top left

**Page F-BM2: Dashboard Grid**
- Title: "Body Measurements –2" center top
- Client name + "Fitness Assessment [YYYY]" top right
- Grid layout with stock illustrations interspersed:
  - Body Weight — horizontal bar chart
  - Blood Pressure — grouped vertical bar (Systolic dark, Diastolic light)
  - Pulse/BPM — donut chart
  - Waist to Hip Ratio — horizontal bar chart
  - BMI — vertical bar chart

### Page: Body Measurements — MALE TEMPLATE (1 combined page)

- Title: "Body Measurements, Weight" center top
- Client name + date range top right
- Left half top: grouped bar chart with 9 measurement categories (adds Chest vs Female)
- Right half top: Body Weight horizontal bar chart + male body illustrations next to each bar
- Bottom left: Waist to Hip Ratio horizontal bar chart + male body illustration
- Bottom right: BMI vertical bar chart + male body illustration
- Units note on the chart

### Page: Physiological Assessment 1 & 2 (both genders — same structure, different illustrations)
- Title: "Physiological Assessment – 1, 2"
- Client name + date range top right
- Gender-appropriate exercise illustrations across the top (4 illustrations: pushup, squat, crunch, pullup)
- **Table 1 — Physio 1:** Header label "Number of Reps (Max 1 Min)". Columns: Pushups, Squats, Crunches, Pullups Total, Pullups Max weight (lbs). Rows: dates in range. Trend arrow on section header.
- Gap + 2 illustrations (plank, side plank)
- **Table 2 — Physio 2:** Header label "Duration (In HH:MM:SS)". Columns: Plank, Right Side Plank, Left Side Plank, 40* hold, Sorenso hold. Rows: dates. Trend arrow on section header.
- Page number bottom right (e.g. "4/6")

### Page: Physio 3 + Strength + Balance — NO SKINFOLD scenario
Used when: Skinfold data does NOT exist for this client in this range.

- Title: "Physiological Assessment 3, Strength and Balance Test"
- Client name + date range top right
- Illustrations left side (runner, flexibility pose, balance pose)
- **Table: Physio Assessment 3** — Cooper Test (KMs), Flexibility (cms). Trend arrow.
- **Table: Strength** — Bench Press, Deadlift, Squat RM. Header label "1 RM (In KGs)". Trend arrow. Illustrations (lifter silhouettes for Male, illustrated for Female).
- **Table: Balance Eyes Closed** — Normal, Tandem Stance (Right Front), Tandem Stance (Left Front), Right Up, Left Up. Header label "Duration (In HH:MM:SS)". Trend arrow.
- Page number bottom right

### Page: Physio 3 + Skinfold + Balance — SKINFOLD scenario (replaces above)
Used when: Skinfold data EXISTS for this client in this range.

- Title: "Physiological Assessment 3, Skinfold and Balance Test"
- Client name + date range top right
- Illustrations left side (runner, flexibility, balance)
- **Table: Physio Assessment 3** — same as above
- **Table: Skinfold Measurements** — Chest, Abdomen, Thighs. Header label "In Inches". Trend arrow. Doctor/measurement illustration.
- **Table: Balance Eyes Closed** — same as above
- Page number bottom right

### Page: Strength Test — STANDALONE (only appears when Skinfold exists)
Used when: Skinfold data exists AND Strength data exists.

- Title: "Strength Test" center top
- Client name + date range top right
- Large black silhouette illustrations (overhead press, seated press) top half
- **Table: Strength** — Bench Press, Deadlift, Squat RM. Header label "1 RM (In KGs)". Trend arrow (▼ if declining).
- Bench press illustration below table
- Page number bottom right

### Page: Back / Thank You (both genders — identical)
- Top corners: Gym badge logo (both left and right) + "IN THE SERVICE OF"
- Center: Large Insight logo
- "Thank You!!" text (from config)
- "Holistic fitness.." tagline
- Mission statement text (from config)
- Decorative circles (○ ○ ○ ○ ○)
- "Contact: [Trainer Name]"
- Certifications (one per line)
- Contact icons row — rendered from config, only populated icons show
- Dot grids bottom corners

---

## Static Asset Folders — Structure

```
assets/
├── platform/                       # Insight brand — never changes
│   ├── insight_logo.png            # small, for content page headers
│   ├── insight_logo_large.png      # large, for back page center
│   ├── dot_grid.png                # corner decoration (or generated programmatically)
│   └── contact_icons/
│       ├── phone.svg
│       ├── email.svg
│       ├── whatsapp.svg
│       ├── instagram.svg
│       ├── facebook.svg
│       ├── website.svg
│       └── address.svg
├── gyms/
│   └── insight_chennai/            # one folder per gym
│       ├── gym_config.json
│       └── badge_logo.png          # only if Option A (uploaded)
├── illustrations/
│   ├── female/                     # Female illustration set
│   │   ├── body_meas/
│   │   │   ├── weight_scale.png
│   │   │   ├── bp_check.png
│   │   │   ├── pulse.png
│   │   │   ├── whr.png
│   │   │   └── bmi.png
│   │   ├── physio/
│   │   │   ├── pushup.png
│   │   │   ├── squat.png
│   │   │   ├── crunch.png
│   │   │   ├── pullup.png
│   │   │   ├── plank.png
│   │   │   └── side_plank.png
│   │   └── physio3/
│   │       ├── runner.png
│   │       ├── flexibility.png
│   │       └── balance.png
│   ├── male/                       # Male illustration set
│   │   ├── body_meas/
│   │   │   ├── body_standing_1.png  # next to each Weight bar
│   │   │   ├── body_standing_2.png
│   │   │   └── body_standing_3.png
│   │   ├── physio/
│   │   │   ├── pushup.png
│   │   │   ├── squat.png
│   │   │   ├── crunch.png
│   │   │   ├── pullup.png
│   │   │   ├── plank.png
│   │   │   └── side_plank.png
│   │   ├── physio3/
│   │   │   ├── runner.png
│   │   │   ├── flexibility.png
│   │   │   ├── balance.png
│   │   │   └── skinfold_doctor.png
│   │   └── strength/
│   │       ├── overhead_press_silhouette.png
│   │       ├── seated_press_silhouette.png
│   │       └── bench_press.png
│   └── shared/                     # used by both genders if needed
│       └── ...
└── fonts/
    ├── BubbleGumSans-Regular.ttf   # title font
    └── RobotoCondensed-Regular.ttf # body/data font (also get Bold variant)
```

User drops illustration images into the right gender subfolder. App maps them to page sections by folder path. No code change to swap illustrations.

---

## UI (On-demand, Simple)

Streamlit app. Two-step flow — scan first, then generate.

**Step 1: Selection**
1. **Gym selector** — dropdown (Phase 1: only one gym, but provisioned). Loads that gym's config.
2. **Client dropdown** — populated from Column A of the sheet
3. **Date range picker** — Start Month/Year + End Month/Year
4. **Scan button** — app reads the sheet, checks data availability per group for this client + range. UI updates immediately after.

**Step 2: Review & Generate (appears after Scan)**

App shows what it found, split into two sections:

*Always included (no checkbox):*
- Body Vitals — always shown here, no toggle. Even if empty.
- Body Measurements — shown here if data exists.

*Select assessments to include (checkboxes):*
Only groups that have data in the selected range appear here. Each is a checkbox, pre-checked. Trainer unchecks whatever they want out.
- [ ] Physio Assessment 1
- [ ] Physio Assessment 2
- [ ] Physio Assessment 3
- [ ] Strength
- [ ] Balance Eyes Open
- [ ] Balance Eyes Closed
- [ ] Skinfold Measurements

Groups with no data in range do not appear in this list at all.

5. **Generate Report button** — runs page composition based on final selections, generates PDF.

**Status log (appears during generation):**
- Reading sheet data...
- Gender: M → Male templates
- Body Vitals: included (mandatory)
- Body Measurements: data found, included
- Physio 1: selected ✓
- Physio 2: selected ✓
- Skinfold: selected ✓ → Strength will be on standalone page
- Balance Eyes Open: no data in range, skipped
- Composing pages... (1: Cover, 2: Body Meas, 3: Physio 1&2, 4: Physio 3 + Skinfold + Balance, 5: Strength, 6: Back)
- Saving to Google Drive...
- Done. PDF: [filename]

---

## Output

- PDF saved to Google Drive folder (via Drive API — OAuth required, one-time consent on first run)
- Filename: `[ClientName]_[StartDate]_to_[EndDate]_Assessment_Report.pdf`

---

## Tech Stack

- **Python 3.10+**
- **matplotlib** — all charts (bar, grouped bar, horizontal bar, donut)
- **reportlab** or **fpdf2** — PDF page assembly and layout
- **Pillow (PIL)** — image handling (logos, illustrations, badge generation)
- **google-sheets-api via requests** — read public sheet (no auth)
- **google-api-python-client** — Google Drive upload (OAuth)
- **Streamlit** — UI
- **pandas** — sheet data parsing

---

## Out of Scope (Phase 1)

- Form-based data entry (Phase 2)
- Email delivery to clients (Phase 2)
- Multi-gym switching with separate sheets (Phase 2 — but config is provisioned)
- Scheduled/automatic generation
- Client-facing portal

---

## How to use this spec with Claude Code

Sprint order — do NOT do all at once. Paste only the relevant sprint context each session.

1. **Sprint 1:** Project setup, dependencies, folder structure, font downloads, asset placeholders
2. **Sprint 2:** Google Sheets reader — parse data, handle quirks (annotations, sparse cells, per-group dates, gender detection)
3. **Sprint 3:** gym_config.json reader + badge logo generator (Option B)
4. **Sprint 4:** Cover page + Back page generators (branding-heavy, good visual test early)
5. **Sprint 5:** Female Body Measurements pages (F-BM1 chart page + F-BM2 dashboard page)
6. **Sprint 6:** Male Body Measurements combined page
7. **Sprint 7:** Physio 1 & 2 table page (shared structure, swap illustrations by gender)
8. **Sprint 8:** Physio 3 page — both variants (with Skinfold, without Skinfold) + Strength standalone page
9. **Sprint 9:** Data availability scan — per-group empty check for selected client + date range. Returns availability map. This is Layer 2.
10. **Sprint 10:** Checkbox UI + selection logic — mandatory vs toggleable split, pre-check based on scan results, trainer uncheck handling. This is Layer 3.
11. **Sprint 11:** Page composition router — takes final selection state, resolves Skinfold/Strength split, composes page order, assigns page numbers. This is where all three layers come together.
12. **Sprint 12:** Streamlit UI assembly + Drive upload + end-to-end test with real data
13. **Sprint 13:** Visual comparison against actual PDFs, pixel-level fixes
