# Handoff: Insight Core Report Config — Output & Style Picker + 3 Report Designs

## Overview
Insight Core is a trainer toolkit (Check-In / Assessment / Report Config tabs) backed by a Google Apps Script web app, with data living in Google Sheets. This handoff covers a redesign of the **Report Config tab** and the **report/nudge output it generates**: a picker for Output Type (Nudge PNG vs Full Report PDF) and, for Full Report, a Report Style picker (Editorial Ledger vs Scorecard Deck), plus the three locked visual designs those choices render.

## About the Design Files
The bundled file (`Insight Core.dc.html`) is an **HTML design reference/prototype**, built in a prototyping tool, not production code to copy directly. It uses a custom templating syntax (`{{ }}`, `<sc-for>`, `<sc-if>`) specific to that tool — this is NOT React/Vue syntax and won't run as-is anywhere else. The task is to **recreate these designs inside the existing Apps Script web app** (`apps_script/index.html` and friends), reusing its existing JS/CSS patterns, and wiring the picker + report rendering to real data from `google.script.run` calls into the Sheet — not to embed this HTML file directly.

`ios-frame.jsx` / `android-frame.jsx` are device-bezel mockup wrappers used only to preview the design in a phone frame during design review. Ignore them for implementation — the real app is a responsive web page, not a native app in a device frame.

## Fidelity
**High-fidelity.** Exact colors, spacing, typography, and layout are final for all three report designs and the Report Config controls. Implement pixel-close, adapting only where the existing Apps Script HTML/CSS structure requires it.

## Screens / Views

### 1. Report Config tab — Output & Style pickers
Existing tab, two controls added/changed at the bottom, above the "Generate" button:
- **Output Type** — segmented control, 2 options: `Nudge PNG`, `Full Report (PDF)`.
- **Report Style** — segmented control, 2 options: `Editorial Ledger`, `Scorecard Deck`. **Only visible when Output Type = Full Report.**
- Existing "Page Layout" segmented control (1x1/1x2/2x1/2x2/3x2) and "Components" checklist (Body Measurements, Body Vitals, Physiological 1/2/3, Balance Eyes Open/Closed, with reading counts per client) are unchanged.
- Segmented control component: flush-left radio-style pills, no rounded corners on the control container's outer shape isn't critical here — visually these use the existing Apps Script segmented-control CSS already in the app (labels not centered, per Modernist convention used elsewhere in this app's trainer UI — but the **report output itself uses the client-facing Insight brand, not Modernist**, see Design Tokens below).
- Clicking **Generate** renders the chosen output (Nudge PNG, Editorial Ledger, or Scorecard Deck) using the currently selected client + date range + reading data.

### 2. Full Report — Editorial Ledger
Static, single-column ledger-style report. Width reference 380px card (scale up for real print/PDF page).
- **Header** (single row): logo (`insight_leftlogo.png`) left, 42px tall · client label stack next to it: "FITNESS DASHBOARD" kicker (9px, letter-spacing 0.14em, weight 700, color `#880e4f`) above client name (16px, weight 800) · date range right-aligned, 9px, `#6b7280`, two lines (from – to). 6px solid `#880e4f` top border on the whole card. 1px `#e8e0e6` bottom border under header.
- **Body Measurements** section: 10px uppercase kicker (`#880e4f`, weight 700, letter-spacing 0.1em) then rows: label (11px weight 600, 42px fixed width) → bar track (12px tall, 1px bottom border `#ccc`, fill `#880e4f` solid, width = value/45in as %) → value (11px weight 700, right-aligned). One row per measurement (Waist, Hips, Chest — extend to more if the component list includes more).
- **Body Vitals** section: same kicker style, then a 2×2 grid, each cell divided by 1px `#eee` right/bottom borders: 9px uppercase gray label (`#6b7280`) then 22px weight-800 value (with a smaller unit suffix inline, e.g. "68.2 kg", "72 bpm"). Cells: Weight, BMI, Blood Pressure, Pulse.
- **Balance** section: kicker, then a plain HTML-style table — header row with 2px bottom border `#880e4f`, weight 700 column labels (Test / Open / Closed), then data rows with 1px `#eee` row dividers, 11px text, Open/Closed columns center-aligned.
- **Left strip**: a thin (6px) solid magenta (`#880e4f`) vertical strip runs the full height of the card, flush against the left edge — flat color, no pattern (matches the header's accent weight).
- **Footer**: no longer a single footer photo. Centered trainer block — name (13px weight 800, `#880e4f`), credentials line (10px, neutral gray), phone number (12px weight 800, `#880e4f`) — flanked left and right by the `insight_corner.png` dot-pattern art (right side horizontally mirrored), each ~36px wide.

### 3. Full Report — Scorecard Deck
Rounded, card-based report. Same 380px reference width, same header pattern (logo + kicker/name + date), 6px `#880e4f` top border, but background `#fdfbfc`.
- **Weight Trend hero card**: white rounded card (14px radius, `box-shadow: 0 4px 16px rgba(136,14,79,.1)`), margin 16px from card edges. Inside: 10px uppercase gray label "Weight trend" → big number row (30px weight-800 value + 13px gray "kg" unit) with a right-aligned delta label (12px weight 700, color `#ad1457`, e.g. "↓ 1.8 kg since first visit") → a 4-bar mini trend chart below (14px wide bars, varying heights, 3px radius, colors ramping light pink `#f8bbd0` → mid `#f06292` → dark `#880e4f` for the most recent/tallest bar).
- **Body Measurements**: 10px uppercase gray kicker, then rows: label (10.5px, 40px width) → rounded track (11px tall, 5px radius, bg `#f5f5f5`) with a solid rounded fill bar (colors vary per row: `#880e4f`, `#ad1457`, `#ce5a92`) → value right-aligned (10.5px).
- **2×2 metric tiles**: white rounded cards (12px radius) each with a 4px colored top border (varying magenta shades `#ad1457`/`#bf1d6f`/`#ce5a92`/`#f06292`), 9px uppercase gray label, 20px weight-800 value. Tiles: BMI, Blood Pressure, Pulse, Waist–Hip Ratio.
- **Balance — Normal Stand**: gray kicker, then two rounded bars (Eyes Open / Eyes Closed) same track/fill pattern as Body Measurements, values right-aligned in seconds.
- **Poster footer**: solid `#880e4f` background block, centered text — trainer name (13px weight 800 white), credentials line (10px, `#f8bbd0`), phone number (12px weight 800 white).

### 4. Nudge PNG — WhatsApp Card
Compact single card meant to be exported as a PNG and sent via chat. Outer frame 300px wide, solid `#880e4f` background acting as a mat/border, padding 18px, containing a white rounded card (18px radius, padding 22px 18px).
- **Header row**: logo (`insight_leftlogo.png`, 46px tall) + text stack: "CHECK-IN UPDATE" kicker (10px gray) above client name (16px weight 800).
- **Headline stat**: centered, "Since last check-in" (11px gray) then a large delta value (34px weight 800, color `#880e4f`, e.g. "↓ 1.8 kg").
- **Scorecard row** (leads the metrics — matches daily check-in fields): 3 equal tinted pill cards (bg `#f4eef1`, 10px radius) side by side — Weight (kg), Body Fat %, Muscle % — each with a 14px weight-800 magenta value and an 8px gray uppercase label underneath.
- **Body Measurements**: same small-bar pattern as the other reports, compact (8px track height), 2 rows shown (Waist, Hips) — no duplicate metrics from the scorecard row above.
- **Quote line**: centered italic 11px text, e.g. a short encouragement line.
- **Footer**: centered, trainer name (10px weight 700) + phone number (9px gray), separated from content above by a 1px `#eee` top border.

### 5. Report Config tab — picker redesign (Output Type + Date + Components)
**This replaces the old checklist-style Components picker and the shared date field described informally above — this section is the source of truth for that part of the tab; the segmented Output Type / Report Style controls in Screen 1 are unchanged.** Locked direction: **"two distinct tracks + selectable card grid."** Reference width 340px (mobile column). Three cards top-to-bottom, in this order:
- **Output card**: segmented control, 2 options, single-line pills — `Nudge` / `Full Report` (short labels; avoid "Nudge PNG"/"Full Report (PDF)" here, they wrap in the existing segmented-control CSS at this width). This selection drives both cards below.
- **Session/Date card**: 
  - When Output = **Nudge**: one field, label "Date", single date input.
  - When Output = **Full Report**: two fields side by side (flex, 10px gap), labels "From" / "To", each a date input.
  - Same card position/kicker in both states — the field set swaps, the card doesn't move or duplicate.
- **Components card**:
  - Card kicker text swaps: "Component" (Nudge) vs "Components" (Full Report).
  - A small badge top-right of the kicker row shows selection state: "1 of 1" (Nudge) or "N selected" (Full Report), where N updates live.
  - One line of helper text under the kicker, swapping by mode: Nudge → "Tap one to pick it — single-select, no longer locked to Body Vitals."; Full Report → "Tap any number to include — multi-select."
  - Below that: a 2-column CSS grid (`grid-template-columns: 1fr 1fr`, 8px gap) of component cards, one per component (Body Measurements, Body Vitals, Physiological 1/2/3, Balance — Eyes Open, Balance — Eyes Closed — same 7 components as the old checklist). Each card: 10px padding, label (12px weight 700), reading count below it (10.5px, neutral gray, e.g. "4 readings", pulled from the same per-client counts the old checklist showed).
  - Selected-card style: `border: 2px solid` accent, tinted accent background (accent-100 step). Unselected: `border: 2px solid` divider color, transparent background.
  - Click behavior: **Nudge = single-select** — clicking a card selects it and deselects any other (radio-group behavior, but rendered as cards, not radio buttons). **Full Report = multi-select** — clicking toggles that card independently; any number 0–7 can be selected.
  - Switching Output from Full Report → Nudge with multiple selected: collapse selection down to just the first previously-selected component (don't lose all selection state, don't error).
- **Generate button**: unchanged position/style, full-width primary button below the Components card.

## Interactions & Behavior
- Output Type and Report Style are mutually-exclusive single-select segmented controls (radio behavior) — selecting one option deselects the other in its group.
- The Components card grid (Screen 5) is a fully separate selection model from Report Style: Nudge is single-select (radio-like), Full Report is multi-select (independent toggles) — implement as two distinct interaction modes sharing one grid, not one generic multi-select with a cap of 1.
- Report Style control only renders/is only relevant when Output Type = "Full Report (PDF)".
- Generate button triggers rendering of the selected output using current Report Config selections (client, date range, checked components) — no loading/error states are designed yet; add per the existing app's conventions for async Apps Script calls.
- No hover/focus states beyond the existing Modernist‑styled trainer-tool controls (segmented control, checkboxes, buttons) already used elsewhere in this app.

## State Management
Report Config screen needs, minimum:
- `outputType`: `'nudge' | 'full_report'`
- `reportStyle`: `'ledger' | 'scorecard'` (only meaningful when `outputType === 'full_report'`)
- Existing: `client`, `dateFrom`, `dateTo`, `layout`, `components` (checked component ids)
- Derived report data per client/date-range (see Data Shape below) — pull this from the Sheet via existing Apps Script read functions, not hardcoded.

## Data Shape Expected (per report render)
```
{
  clientName: string,
  dateLabel: string,          // "26 Jun 2025 – 25 Jun 2026" or similar, formatted
  weightVal: number,          // kg
  fatPct: number,             // %
  musclePct: number,          // %
  weightDeltaLabel: string,   // e.g. "↓ 1.8 kg since last check-in" (nudge) or "since first visit" (report)
  bodyMeasurements: [ { label: string, value: string /* e.g. 30.5" */, pct: number /* 0-100, for bar fill width */ } ],
  bodyVitals: [ { label: string, value: string } ],           // Weight, BMI, Blood Pressure, Pulse — ledger style
  scorecardTiles: [ { label: string, value: string } ],       // BMI, Blood Pressure, Pulse, Waist–Hip Ratio — scorecard style
  balanceRows: [ { label: string, open: string, closed: string } ],   // ledger table
  balanceBars: [ { label: string, valueLabel: string, pct: number } ] // scorecard bars
}
```
`pct` for measurement/balance bars in the prototype is computed client-side as `value / referenceMax * 100` (e.g. waist/45in, balance seconds/60s) — replicate that formula or replace with real normalization ranges if the trainer has better reference values.

## Design Tokens

### Modernist (app-wide — tabs, forms, buttons, Report Config controls)
Full token sheet is bundled at `design-system/styles.css` (with `design-system/readme.md` explaining usage) — the `var(--color-*)`, `var(--font-*)`, `var(--space-*)`, `var(--radius-*)`, `var(--shadow-*)` custom properties used throughout the app and referenced in the design markup resolve against that file's `:root` block. Key values:
- `--color-bg`: `#f3f2f2`, `--color-text`: `#201e1d`, accent: `#ec3013` (single accent, no second hue — treat `--color-accent-2-*` as identical to `--color-accent-*`)
- Neutral/accent ramps run 100–900 (light tints → dark/pressed), generated in OKLCH — see `styles.css` `:root` for exact hex per step
- `--font-heading` / `--font-body`: Archivo (both)
- `--radius-*`: 0 across the board (no rounded corners) — density 1.00×, this token set stays flat
- Divider rule: `var(--color-divider)`, 2px
Implement these as real CSS variables (or your app's equivalent token file) with the exact values from `styles.css` — don't approximate.

### Insight brand (report/nudge output only)
**These tokens apply ONLY to the report/nudge output — the rest of the trainer app (tabs, forms, buttons) stays in the app's existing Modernist system above and should NOT be restyled.**

- Insight brand magenta: `#880e4f` (primary), `#ad1457` (secondary/delta accent), `#ce5a92`, `#bf1d6f`, `#f06292`, `#f8bbd0` (light tint), `#f4eef1` (pale tint fill)
- Neutral gray text: `#6b7280`; dark ink: `#1a1a1a`; hairline borders: `#e8e0e6`, `#eee`, `#ccc`
- Font: system-ui / system default sans (matches real PDF templates) — not Archivo
- Radii: Ledger = 0 everywhere (flat, matches print ledger style); Scorecard/Nudge = 10–18px rounded throughout
- Card shadow (Scorecard hero card only): `0 4px 16px rgba(136,14,79,0.1)`
- Spacing: 14–20px section padding, 8–10px gaps between rows/tiles is consistent across all three designs

## Assets
All in `assets/` in this bundle, sourced from the client's real brand materials (already in the app's uploads):
- `insight_leftlogo.png` — primary logo, used in every report/nudge header
- `insight_corner.png` — magenta dot-pattern corner art, used flanking the Editorial Ledger footer text (right side mirrored)
- `footer_visual.png` — trainer credential/footer art, used in Scorecard/Nudge-era drafts; no longer used in Editorial Ledger's footer (replaced by `insight_corner.png` + "Text" placeholder)
- `insight_rightlogo.png`, `header_visual.png` — available brand assets, not currently used in the three locked designs but may be useful for future variants
- A green seal logo previously existed in early drafts and was **intentionally removed** (illegible at small scale) — do not reintroduce it.

## Screenshots
`screenshots/3b-nudge-state.png` and `screenshots/3b-full-report-state.png` — the locked picker redesign (Screen 5) in both live states, useful as a visual reference for smoke-testing the implementation (not automated assertions — just what "correct" looks like in each mode).

## Files
- `Insight Core.dc.html` — full design reference: turn 3 (`id="3b"` is the **locked** picker redesign — live and clickable, toggle Output between Nudge/Full Report to see both states; `3a`/`3c` are two rejected alternate directions, kept for context only) has the Report Config picker redesign from Screen 5; turn 2 (`id="2a"`/`"2b"`/`"2c"`) has the three static report/nudge mockups with exact markup/styles to reference; turn 1 (`id="1a"`/`"1b"`) has the live, wired Report Config tab + Generate flow with real sample data switching (see the `buildFrame()` / `SAMPLE` / `COMPONENT_DEFS` objects, and `buildT3()` / `t3Default()` for the picker redesign's state logic, in the `<script data-dc-script>` block for the exact data transformations and formatting logic — e.g. date formatting, delta-arrow logic, percent-fill math, single-vs-multi-select toggling).
- `ios-frame.jsx` / `android-frame.jsx` — device bezel mockups, reference only, not for implementation.
- `assets/` — brand imagery referenced above.
- `design-system/styles.css` + `design-system/readme.md` — the Modernist design system's real token values and component CSS, backing every `var(--*)` used in the design markup (tabs, buttons, forms, segmented controls, cards). Implement the trainer-tool chrome against these exact values.
