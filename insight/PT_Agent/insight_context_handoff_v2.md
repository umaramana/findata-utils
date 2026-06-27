# Insight Fitness Data Services — Context Handoff v2
**Updated 2026-06-27 | Paste this at the start of every Claude Code session**

---

## 1. What changed since the last handoff doc

- Pilot client is **VIP**, not Thilak. File is `insight_pilot`.
- Migration dropped — **all 3 pilot clients are fresh**, no historical import for any of them.
- `client_info` starts empty. Clients added via inline "+ Add new client" in the check-in form.
- Single app shell, one deployed URL, tabs added incrementally — never a second deployment. Corrected once already (S1.2 shipped standalone, retrofitted via `shell_merge_card.md`).
- `metric_master` is **62 rows**, `component_master` is **12** — grew live during F02-S02's build.
- **Card files renamed to their real backlog IDs** (2026-06-26) — `S2.2`→`F04-S02_S03_S04_chart_rendering_card.md`, `S3.1`→`F05-S01_S02_report_config_card.md`. No session-label filenames should exist going forward — name every card by its `F0X-S0X` ID, never by calendar session.
- **F04-S01 (chart comparison) deferred until after the default report works.** Locked default for Saturday: **table_heatmap**, colour relative to each metric's own baseline (not an absolute clinical threshold — none exist, and defining ~50 of them in 2 days isn't realistic). F04-S01 can override per-component later via `charts_config`, doesn't block anything this week.
- **Scope dropped for Saturday's report:** ankle/video assessment (F05-S08) — video explicitly out of scope. Report log/audit trail (F05-S07) — not needed for a client-facing report, can come later.
- **New non-coding risk:** F05-S06 needs actual gender-keyed image assets, which don't exist yet. Confirm with Arun which components genuinely need gendered images vs. a shared neutral one, then source them — this runs in parallel with coding, not blocking a session, but can become the real bottleneck if left to the last day.
- **Pace change:** 3 sessions/day for the final 2 days (was 2/day) — the remaining card count didn't fit at the old pace once the grid-picker and gender images stayed full-scope rather than simplified.
- **Real Looker sample reports reviewed (4 clients: Reshma, Karthik, Dr Praveena, Dr Ramesh)** — this replaced guesswork with ground truth and changed the chart plan materially:
  - **No line/area chart appears anywhere in any sample.** `line_area`/`multi_line` (F04-S02/S03) are dropped from this week's scope — every metric renders as some form of bar. F04-S02_S03_S04's card is rewritten as one bar-chart-family function with a `mode` parameter (`horizontal_single`, `vertical_single`, `stacked_pair`, `grouped_multi`), not three separate chart types.
  - **Correction (2026-06-26, post-handoff):** `table_heatmap` is also moving from D3 → **Python (matplotlib)**, same reasoning as the bar-chart family. Checked the origin: D3 was picked on 2026-05-15 purely because "D3 has a heatmap table type" — no D3-specific capability was ever required (no interaction, no transition). That pick predates yesterday's pytest + PNG-bytes output contract by over a month. Proportional fill + "No data" text is `Rectangle` patches in matplotlib — same approach as `render_bar`. **Net effect: one rendering engine (matplotlib) for both chart types in scope this week, not two.** D3's status for *future-only* types (slope, dot_timeline, calendar_heatmap — not needed for Saturday) is left open, not decided here.
  - Weight and waist-hip-ratio: horizontal bar. BMI: vertical bar. **New metric `bmr`** (Basal Metabolic Rate) also vertical bar, with a truncated y-axis in the sample (1.6K–1.8K, not 0) — replicated by default, **flagged to confirm with Arun**, since truncated axes can exaggerate small differences.
  - Fat% and muscle% are a **stacked bar, on their own chart — never combined with weight.** Blood pressure (systolic+diastolic) uses the same stacked-bar pattern.
  - Pulse used a donut in the originals — banned by the locked no-donut rule. Replacement: same vertical-bar pattern as BMI/BMR, not a new one-off shape.
  - `metric_master` is now **63 rows**, not 62 — `bmr` added.
  - **Table_heatmap's colour rule corrected** — it's a continuous proportional fill scaled to each row's own min/max, not the discrete baseline-relative green/amber/red bands assumed last round. Missing data shows literal **"No data"** text, not a blank cell.
  - Confirmed correct, no change: body_measurements as multi-date grouped/clustered bars.
  - Two things noted for later, not blocking Saturday: Karthik's report has Speed/Agility (2 trials) and 1RM Strength metrics not in `metric_master` — same "grows organically per client" pattern already embraced for VIP. Dr Praveena's report shows side-by-side "Trial 1/Trial 2" columns for one date, which doesn't fit the current unique-key model without a trial-number dimension — open question for the other 2 clients if they have multi-trial tests.
- **Source-of-truth model:** `insight/PT_Agent/*.md` cards are the only source of truth. This doc is the shared index — kept current here, copied into PT_Agent by Uma. Claude Code codes only, doesn't maintain docs.
- **F04-S02/S03/S04 and F04-S05 built and done (2026-06-27).** 73/73 tests pass. Visual standards locked — see "As-built visual standards" sections in each card. Key decisions: `"Measurement units: {unit}"` top-right on all chart types; `:.1f` everywhere; scorecard number/unit split into separate text elements; grouped_multi dynamic font scaling (7.5/6.0/5.0pt based on bar pixel width); heatmap full-cell fill, 8-stop brand gradient, dual-mode normalisation, `hms` value format option.

---

## 2. What we are building (unchanged)

Fitness assessment reporting platform for a single personal trainer (Arun Alex David, Insight Fitness, Chennai). Converts client assessment data into structured reports — WhatsApp nudges (PNG) and full PDFs.

**Not building:** client-facing interface, WhatsApp parsing pipeline, multi-trainer support (all Vision).

**Stack:** Python (matplotlib — bar-chart family + table_heatmap, both pytest-tested), Google Sheets, Google Apps Script (check-in form), Canva (template shell only). D3's status for future-only custom types (slope/dot_timeline/calendar_heatmap) is open — not needed for Saturday, not decided.

---

## 3. Three-layer assessment framework (unchanged)

| Layer | Type | Examples |
|---|---|---|
| 1 — Foundation | Movement | Ankle assessment, Apley scratch — **out of scope for Saturday** |
| 2 — Capability | Performance | Physio 1/2/3, Balance, Cooper test, Strength |
| 3 — Composition | Body metrics | Weight, fat%, muscle%, girths, BP, BMI |

---

## 4. Google Sheets structure — `insight_pilot`

8 tabs: `readings` (9 cols, client_id+date+component+metric unique key), `component_master` (12), `metric_master` (**63**, includes `bmr` added this round), `client_info` (starts empty), `admin_config`, `exercise_library` (41 rows, ankle_pronation — out of scope for Saturday but data exists), `muscle_groups_library` (11), `charts_config` (from F04-S01, deferred).

**New this round, from F05-S06:** `asset_library` — `component_id | gender | image_ref`, gender can be M/F/ANY. Starts empty or near-empty — that's expected, not a bug.

`migrate_v2_metrics.py` already run once — not idempotent, do not re-run.

---

## 5. Key rules (unchanged)

- date+component+metric (+client_id) = unique key, no duplicates
- Baseline = MIN(date) per client+metric, auto-derived
- BMI/WHR never stored, computed at report time
- Durations always integer seconds
- Paired metrics upserted/deleted independently, no pair-blocking
- All reading submission is upsert/delete, not append-only
- **Corrected:** table_heatmap fill is a continuous proportional bar scaled to each row's own min/max range — not a discrete baseline-relative green/amber/red band as assumed last round.
- **Corrected:** missing data renders as literal **"No data"** text, not a blank cell.
- **New:** any single section's failure (no image, no data) degrades that section gracefully — never blocks the whole report

---

## 6. Chart types

| Type | Library | Status |
|---|---|---|
| Bar-chart family (`horizontal_single`, `vertical_single`, `stacked_pair`, `grouped_multi`) | **Python (matplotlib)**, server-side, pytest-tested | ✅ **Built** (`F04-S02_S03_S04`). Visual standards locked: `"Measurement units: {unit}"` note top-right, `:.1f` precision, scorecard split elements, grouped_multi dynamic font, stacked_pair legend above axes. |
| table_heatmap (full-cell fill, brand gradient, `hms` format, dual-mode norm) | **Python (matplotlib)**, server-side, pytest-tested | ✅ **Built** (`F04-S05`). Dates as rows, metrics as columns. 8-stop gradient. 1 date → row norm; 2+ dates → per-column norm. |
| line_area, multi_line | — | **Dropped from Saturday's scope** — no evidence they're used in the actual default style. Available later via F04-S01 if Arun wants alternatives. |
| slope, dot_timeline, calendar_heatmap, radar, bullet | — | Not needed for Saturday. **Open:** if any of these get scoped later, same PNG/pytest contract question applies — not resolved here. |

F04-S01's comparison session can revisit any of this per-component *after* Saturday — doesn't block this week.

---

## 7. Sprint plan — remaining 6 cards, 3 sessions/day × 2 days

| Day | Session | Card | Status |
|---|---|---|---|
| Day 1 | 1 | `F05-S01_S02_report_config_card.md` | Written, **next to hand off** |
| Day 1 | 2 | `F04-S02_S03_S04_chart_rendering_card.md` | ✅ **Built** — 73 tests pass, visual standards locked |
| Day 1 | 3 | `F04-S05_table_heatmap_card.md` | ✅ **Built** — 73 tests pass, visual standards locked |
| Day 2 | 4 | `F05-S04_layout_engine_card.md` | Written — **next to build** |
| Day 2 | 5 | `F05-S06_gender_image_card.md` | Written — asset sourcing must start, in parallel |
| Day 2 | 6 | `F05-S05_full_pdf_card.md` | Written — last, depends on all 5 above |

**Earlier, unconfirmed:** F04-S01 (chart comparison) and the original S2.2 slot from Tuesday — never confirmed run either way. Doesn't block the above; revisit after Saturday.

**Dropped for Saturday:** F05-S07 (report log), F05-S08 (ankle/video assessment section). F03-S06 (targets), admin UI, advanced P3 charts — all deferred past Saturday, not on this critical path.

---

## 8. Trello card format (unchanged)

Title, Context, Input data, Wireframe (or "no wireframe, reuses X"), Build, Technical requirements, Acceptance criteria, Dependencies.

---

## 9. Wireframes — status

WF-01/02/03/07 exist in v5. WF-04/06 added in v6. WF-05 (Canva) is Uma's own work, confirmed ready. WF-02 (chart comparison) isn't used this week — F04-S01 stays a disposable tool, not a permanent screen, whenever it does run.

---

## 10. Key decisions locked — do not re-discuss

- Sheets-only, **Python (matplotlib) for bar-chart family + table_heatmap — one rendering engine for both, this week's scope**, no Flourish/Looker, no Chart.js. D3's status for future-only types is open, not decided.
- BMI/WHR never stored, parse_confidence sheet-only, DOB not age, client interface out of scope
- VIP is the pilot, all 3 clients fresh, no migration for any of them
- One app shell, one URL, tabs added incrementally
- Upsert/delete standing pattern, no pair-blocking
- **Bar-chart family AND table_heatmap are both Python (matplotlib), pytest-tested, PNG-bytes output — not Chart.js, not D3. Table_heatmap uses proportional fill, not discrete colour bands. F04-S01 can override later, doesn't block now.**
- **Ankle/video and report-log are out of scope for Saturday.**
- **Every card file is named by its `F0X-S0X` ID. No session-label filenames (`S1.1`, `S3.1`, etc.) — that naming caused a real "where is this card" confusion once already.**
- `insight/PT_Agent/*.md` is the only source of truth; this doc is the index.

---

## 11. Files produced — current set, correctly named

| File | Description | Status |
|---|---|---|
| `sprint1_vip_cards.md` / `_v2.md` | F01-S01/S02 (schema+seed) + F02-S01 (check-in form) | ✅ Done |
| `shell_merge_card.md` | Single-app-shell retrofit | ✅ Done |
| `F02-S02_full_assessment_form.md` | Full assessment form, 10 sections/62 active metrics (now 63 with `bmr`), chip picker | ✅ Done |
| `S3.3_whatsapp_nudge_card.md` | WhatsApp nudge — stub only | Not scoped, doesn't block Saturday |
| `sprint2_chartsampler_card.md` | F04-S01, chart comparison, disposable tool | Deferred past Saturday |
| `F05-S01_S02_report_config_card.md` | Report config UI + query engine | **Written, next to hand off** |
| `F04-S02_S03_S04_chart_rendering_card.md` | **Rewritten** — one bar-chart-family function (4 modes) in Python (matplotlib, pytest-tested), not Chart.js, not 3 separate chart types. Includes new `bmr` metric. | Rewritten against real samples |
| `F04-S05_table_heatmap_card.md` | **Corrected** — proportional fill per row, "No data" text for gaps. **Also moved D3 → Python (matplotlib), pytest-tested** — same contract as `render_bar`. | Rewritten against real samples |
| `F05-S04_layout_engine_card.md` | Page layout, full grid picker | Written |
| `F05-S06_gender_image_card.md` | Gender-aware images + new `asset_library` tab | Written — **asset sourcing is the parallel risk** |
| `F05-S05_full_pdf_card.md` | Full PDF export, orchestrates everything above | Written — last in sequence |
| `insight_wireframes_v6.html` | v5 + WF-04 + WF-06 extension | — |

---

## 12. Immediate next actions

1. ~~Hand `F05-S01_S02_report_config_card.md` to Claude Code — Day 1, Session 1~~ (pending)
2. ~~F04-S02/S03/S04 bar charts~~ ✅ Done
3. ~~F04-S05 table heatmap~~ ✅ Done
4. **Next: `F05-S04_layout_engine_card.md`** — hand to Claude Code now
5. In parallel: confirm with Arun which components need gendered images, start sourcing
6. After Saturday: revisit F04-S01 (chart comparison), F05-S07/S08 (report log, ankle section), F03-S06 (targets), admin UI, the multi-trial-column gap (Dr Praveena's report)
