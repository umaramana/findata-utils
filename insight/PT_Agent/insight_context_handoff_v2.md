# Insight Fitness Data Services — Context Handoff v2
**Updated 2026-06-30 | Paste this at the start of every Claude Code session**

---

## 0. LATEST — 2026-06-30 (read this first)

**Full PDF compositor built, smoke-tested, then abandoned — pivoting to HTML/Puppeteer.**

`report_pdf.py` was written using matplotlib `fig.add_axes()`. It produced correct output (17/17 smoke tests pass, v14 PDF generated) but the approach hit a hard wall: no layout engine means every pixel of tick-label bleeding, icon alignment, and cell boundary is manual arithmetic + slow PDF→image→crop feedback cycle. Visual polish was not converging.

**New plan: rebuild the compositor as HTML/CSS → Puppeteer PDF.** This replaces only `report_pdf.py`. Everything else stays:

| What | Status |
|---|---|
| `chart_style.py` | ✅ Done — style spec, magenta palette, metric colors |
| `chart_renderer.py` | ✅ Done — horizontal_single, vertical_single, stacked_pair, grouped_multi, scorecard |
| `table_heatmap.py` | ✅ Done — proportional fill, HH:MM:SS format, natural-width columns |
| `gender_image.py` | ✅ Done — `get_metric_visuals()` |
| `report_pdf.py` | ⚠️ Reference only — correct geometry constants + data wiring, wrong rendering engine |
| `report_pdf.py` → HTML compositor | 🔲 To build in Claude Chat |

**Key geometry already measured and confirmed in `report_pdf.py`** (reuse in HTML build, don't re-derive):
- Page: 1024px wide, variable height; DPI=200
- Top band: COL1_W=440 (BM chart+photos), COL2_W=474 (BW+WHR), COL_GAP=20, VITAL_H=140, BM_H=280
- Mid band: THIRD_W=311 (3 equal cols), MID_H=155
- Heatmaps: full width, stacked, title+badge row above each
- Date pad: 40px left of horizontal-bar axes for "Jun\n2026" y-label
- Bar modes: BW/WHR=horizontal_single; BMI/Pulse=horizontal_single; BP=stacked_pair; BM=grouped_multi

**For Claude Chat:** provide `F05-S04_layout_engine_card.md`, `F05-S05_full_pdf_card.md`, and the smoke output PNGs from `insight_core/smoke_output/` as visual references for chart shapes.

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
- **Smoke-test review against real samples (2026-06-27) — two real issues found, both now decided:**
  1. **DECIDED: natural precision, not `:.1f` always.** Round to bare integer when the value has no meaningful fraction; keep natural decimals (ratios, BMI) otherwise. Fix is spec'd on `F04-S02_S03_S04_chart_rendering_card.md`'s known-issues section, pending implementation — applies to every bar mode's value labels and the scorecard number. `render_table_heatmap`'s existing `"g"` format already does this correctly, used as the reference behavior.
  2. **Scorecard repeats its metric name twice** (title at top, then again as a body label below the unit) — looks unintentional, not in the as-built spec. Matters for F05-S04 since repeated text wastes grid space. **Confirmed 2026-06-28 — drop the repeated body label.** Patch instructions on the card.
  3. Minor/cosmetic only, not blocking: a single-metric+single-date heatmap cell renders at full colour saturation (no range to normalize against). No smoke-test image yet demonstrates a partial "No data" cell inside an otherwise-populated table (only the full-table empty fallback was tested) — recommend one targeted render before sign-off, since that's the exact case this round's heatmap correction was about.
  Full detail in the "Known issues" sections appended to `F04-S02_S03_S04_chart_rendering_card.md` and `F04-S05_table_heatmap_card.md`.
- **Sample review against final PDF outputs (2026-06-27) — Reshma, Karthik, Thilak, Dr Uma, Dr Praveena, Dr Ramesh, blue-theme sample — 4 decisions made:**
  1. **Balance table format standardized to Format A** (separate Eyes-Open/Eyes-Closed tables) — already what's built in `F04-S05`. Audit found 3 of the original 4 samples (Reshma, Karthik, Ramesh) actually use a combined single-table format with an `Eyes` column — that's now explicitly legacy, not replicated. No rebuild needed.
  2. **Missing-data text corrected to "-", not "No data"** — matches Dr Praveena's Cooper Test gap. Patch needed in already-built `F04-S05` (was tested/locked as "No data"). Does not touch the separate full-empty-payload fallback message, which stays "No data".
  3. **Colour theme stays magenta-only for Saturday.** Confirmed direction for later: client-type-driven theme (magenta=women, blue=men, green=children), plus trainer-pickable colour specifically for nudge cards. Real evidence this is needed — the blue-theme sample is an actual existing report, not hypothetical. Ideas and alternatives captured in new card `F05-S03_visual_theme_appearance_card.md` — explicitly an ideas dump, not ready to build, pick up next week.
  4. **Speed/Agility (multi-trial columns) and 1RM Strength (Karthik's sample) — confirmed deferred, own card now exists:** `F04-S06_speed_agility_strength_card.md`. Not for this week.
- **Sleeve theming and template architecture (2026-06-28) — two new ideas captured, both explicitly deferred:**
  1. **Sleeve mechanism decided in shape** (not built): "Canva template" is just 4 chrome assets (logo, side strip, background, thank-you page) — Uma will supply these directly. Swapping them by client type (M/F/Child) reuses `F05-S06`'s `asset_library` pattern exactly. Folded into `F05-S03`. Open question inside that card: chrome-only swap, or chrome+chart-colour together (the latter reopens built `F04` cards). "Child" client attribute gap (already noted for gendered Physio icons) is now also load-bearing for sleeve selection — still not a tracked field anywhere.
  2. **New card: `F06-S01_template_architecture_vision_card.md`** — long-horizon vision for supporting multiple report *template types* (today's Pagewise PDF, future Infographic dashboard, future Mobile dashboard) as parallel pipelines, not variations on one pipeline. Explicitly not for Saturday or even next week — vision capture only, no committed timeline. One near-free seed for later: a `template_type` enum field on report config, not yet added.
- **F05-S06 standardized to 1 image + 1 icon per metric (2026-06-28), replacing the metric-level-but-still-variable contract from earlier the same day.** Direct pixel inspection of 4 real samples (Praveena/Reshma female, Ramesh/Thilak male) found the originals were inconsistent in a way not worth replicating: Weight and WHR had a non-gendered hero photo *plus* a gendered icon repeated once per date column; BMI/BP/Pulse had only the non-gendered photo; Physio/Balance had yet another pattern. **New uniform rule: every metric gets exactly one image (never gendered) and one icon (gendered M/F, shown once regardless of date count).** Kills the per-row icon repetition and the per-component fallback function entirely — every metric now resolves identically via one function, `get_metric_visuals(metric_id, gender)`. **Generalized further (same day):** Balance's 9 shared poses (eyes-open/closed pairs) are handled via a small override table (`metric_asset_groups: metric_id → asset_group_key`), not hardcoded pose logic — default behavior is "key = metric_id," override rows redirect specific metrics to a shared key. This same mechanism could express full component-level sharing later if ever needed, without a separate toggle/mode. Derived metrics (`bmi`, `waist_hip_ratio`) need no override row — they already default to their own synthetic key.
- **F05-S06 contract corrected to metric-level (2026-06-28) — confirmed against real `metric_master` IDs and Google Sheets access (now working — account added).** Original contract was one image per *component*; checked against the samples and that's only correct for `physio_3`/`balance_open`/`balance_closed` (one image slot for the whole table). `body_vitals` and `physio_1`/`physio_2` are actually per-metric (or per-metric-pair) — `weight_kg`→scale photo, `bp_systol`+`bp_diastol`→one BP photo, each exercise column in Physio 1/2 gets its own icon. Card now has two functions: `get_metric_image(metric_id, gender)` (direct lookup) and `get_component_representative_image(component_id, gender)` (walks a component's metric list, returns first resolvable asset — used only for the 3 single-image-slot components). Asset key is `metric_id`, not `component_id`. **Confirmed via the actual `client_info` sheet: Saturday's 3 real pilot clients are `champion_mr_abhay_singh` (M), `master_jay` (M), `dr_hemalatha` (F)** — 2 male, 1 female, both genders now load-bearing for Saturday, not "whichever gets sourced first." Child not needed (no child clients in this pilot). `gender` and `client_type` (adult/child) fields confirmed present in `client_info`, no schema gap there.
- **F05-S04 fully rewritten (2026-06-28) — bucket/pagination model, not single-grid.** The single-grid-density model couldn't produce what the samples actually do (it would happily place a heatmap next to a bar chart). New model, derived from a full page-audit of all 7 samples: **3 fixed content buckets in fixed order** — Body Measurements (always full-width, alone) → Body Vitals/Strength (grid density applies *only* here) → Physio/Balance heatmaps (always full-width stacked, never gridded). **Hard rule, zero exceptions across all 7 samples: heatmaps never share a page with bar charts.** Pagination is height-based within buckets, not a hardcoded split — explains both "FirstTime fits on 1 page" and "PastYears splits across pages" as the same algorithm at different content heights. **This also resolves the previously-open aspect-ratio question for free** — heatmaps no longer enter a grid at all, so the lossy "5.26-ratio table forced into a near-square cell" problem doesn't arise; Bucket 2's items are all within a narrow ~1.0–2.0 ratio range, low-risk to grid. **Canva content-area dimensions measured 2026-06-28** (from the actual 4 chrome assets Uma supplied): canvas 1024×768 (4:3, confirmed against real exported reports), left strip 12px full-height, three corner dot boxes (69×109 top-right, 84×148 bottom-left, 69×108 bottom-right), recommended safe content rectangle x:30→994/y:20→748 (≈728px usable height). **Logo placement resolved (2026-06-28):** 400×400 square = full lockup (icon+wordmark+tagline), cover page only. 200×100 rectangle = bare wordmark, top-left on every content page. Both confirmed available, no further decision needed. **Header/footer decomposed into individual pieces (2026-06-29):** 2-tone left strip confirmed (header black zone, dynamic height + flexi-height magenta #741b47 footer zone) — explicitly not 3-tone, a "midrib" zone was considered and rejected. Seal text confirmed final: "BUILDING A STRONGER" — `Insight_Green_Circle_Logo.png` is stale, don't use. Full asset table and sizes on `F05-S05`'s card — this also closes the cover-template-asset gap found in the `vip_001` smoke test. **Last piece still needed:** the rendered height of one bar-row/heatmap-row at this same scale, to complete the height-accumulation comparison. (Grid-slot-count for image+chart pairs was decided 2026-06-27 — one slot, image inset — and carries forward unchanged into this rewrite.)

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
- **Corrected (2026-06-27):** missing data within an otherwise-populated table renders as literal **"-"** — was "No data" in the prior round, changed to match Dr Praveena's real sample. The separate full-empty-payload error fallback still shows a centered "No data" message — different state, unchanged.
- **New:** any single section's failure (no image, no data) degrades that section gracefully — never blocks the whole report

---

## 6. Chart types

| Type | Library | Status |
|---|---|---|
| Bar-chart family (`horizontal_single`, `vertical_single`, `stacked_pair`, `grouped_multi`) | **Python (matplotlib)**, server-side, pytest-tested | ✅ **Built** (`F04-S02_S03_S04`). Visual standards locked: `"Measurement units: {unit}"` note top-right, `:.1f` precision, scorecard split elements, grouped_multi dynamic font, stacked_pair legend above axes. **Known issues found in smoke-test review, not yet patched** — see Section 1. |
| table_heatmap (full-cell fill, brand gradient, `hms` format, dual-mode norm) | **Python (matplotlib)**, server-side, pytest-tested | ✅ **Built** (`F04-S05`). Dates as rows, metrics as columns. 8-stop gradient. 1 date → row norm; 2+ dates → per-column norm. **Known issues found in smoke-test review, not yet patched** — see Section 1. |
| line_area, multi_line | — | **Dropped from Saturday's scope** — no evidence they're used in the actual default style. Available later via F04-S01 if Arun wants alternatives. |
| slope, dot_timeline, calendar_heatmap, radar, bullet | — | Not needed for Saturday. **Open:** if any of these get scoped later, same PNG/pytest contract question applies — not resolved here. |

F04-S01's comparison session can revisit any of this per-component *after* Saturday — doesn't block this week.

---

## 7. Sprint plan — remaining 6 cards, 3 sessions/day × 2 days

| Day | Session | Card | Status |
|---|---|---|---|
| Day 1 | 1 | `F05-S01_S02_report_config_card.md` | ✅ **Built** — confirmed 2026-06-28 |
| Day 1 | 2 | `F04-S02_S03_S04_chart_rendering_card.md` | ✅ **Built** — 73 tests pass, visual standards locked, **known issues flagged for patch** |
| Day 1 | 3 | `F04-S05_table_heatmap_card.md` | ✅ **Built** — 73 tests pass, visual standards locked, **known issues flagged for patch** |
| Day 2 | 4 | `F05-S04_layout_engine_card.md` | **Rewritten 2026-06-28** — bucket/pagination model. Canva content-area dimensions now measured (see Section 1). One small piece left: rendered height of one bar-row/heatmap-row at the same scale. |
| Day 2 | 5 | `F05-S06_gender_image_card.md` | Written — asset sourcing must start, in parallel; grid-slot question cross-referenced with F05-S04 |
| Day 2 | 6 | `F05-S05_full_pdf_card.md` | Written — last, depends on all 5 above; flagged as dependent on F05-S04's open questions and the F04 patch |

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
| `F05-S01_S02_report_config_card.md` | Report config UI + query engine | ✅ **Built** — confirmed 2026-06-28, query payload shape is now real, not assumed |
| `F04-S02_S03_S04_chart_rendering_card.md` | **Built**, 73/73 tests. One bar-chart-family function (4 modes) in Python (matplotlib, pytest-tested). **All known issues confirmed and patch-ready (2026-06-28): decimal precision, scorecard duplicate label** — exact before/after code on the card. | Built, all patches confirmed |
| `F04-S05_table_heatmap_card.md` | **Built**, 73/73 tests. Moved D3 → Python (matplotlib, pytest-tested). **Known issues appended (2026-06-27): single-cell saturation, missing partial-No-data visual test** — minor, confirm before sign-off. | Built, patch pending |
| `F05-S04_layout_engine_card.md` | Page layout. **Fully rewritten 2026-06-28** — 3-bucket model (Measurements/Vitals+Strength/Physio-Balance), height-based pagination, grid density scoped to Bucket 2 only, heatmaps never gridded/never share a page with bar charts. Aspect-ratio question resolved by construction. Canva content-area dimensions measured. | Rewritten — one small piece left, see Section 1 |
| `F05-S06_gender_image_card.md` | Metric-level image+icon, standardized contract. **Finalized 2026-06-28** — 1 image (ungendered) + 1 icon (gendered) per metric, no row-repetition, no component fallback. Balance poses shared across open/closed. | Written — **asset sourcing is the parallel risk, now urgent** |
| `F05-S05_full_pdf_card.md` | Full PDF export, orchestrates everything above. **Reviewed 2026-06-27** — noted dependency on F05-S04's open questions and the F04 patch before its end-to-end run is meaningful. | Written — last in sequence |
| `insight_wireframes_v6.html` | v5 + WF-04 + WF-06 extension | — |
| `F05-S03_visual_theme_appearance_card.md` | **New (2026-06-27).** Ideas dump — client-type colour theming (magenta/blue/green), trainer-pickable nudge-card colour, missing-data text ("-" vs "No data") as trainer config. Not scoped, not for this week. | Ideas only, pick up next week |
| `F04-S06_speed_agility_strength_card.md` | **New (2026-06-27).** Backlog placeholder — Karthik's multi-trial Speed/Agility columns and 1RM Strength. Not scoped, not for this week. | Backlog only, pick up next week |
| `F06-S01_template_architecture_vision_card.md` | **New (2026-06-28).** Vision capture — multiple report template types (Pagewise PDF / Infographic / Mobile) as parallel pipelines. No committed timeline. | Vision only, no timeline |

---

## 12. Immediate next actions

1. ~~Hand `F05-S01_S02_report_config_card.md` to Claude Code — Day 1, Session 1~~ ✅ **Confirmed built 2026-06-28** — query payload shape is real, F05-S04 can build against it directly
2. ~~F04-S02/S03/S04 bar charts~~ ✅ Done
3. ~~F04-S05 table heatmap~~ ✅ Done
4. **All 3 F04 patches now confirmed (2026-06-28) — ready for Claude Code, no remaining sign-off needed:** decimal precision (natural precision), missing-data "-", and scorecard duplicate-label removal. See "Patch instructions" sections in both cards for exact before/after code and required test updates. Balance table format needs no patch (already matches the decision).
5. **F05-S04's aspect-ratio question is resolved by construction, and Canva content-area dimensions are now measured (see Section 1)** — neither is a blocker anymore. **One small piece left: the rendered height of one bar-row/heatmap-row at the same 1024×768 scale** — needed to complete the height-accumulation comparison before the bucket model's pagination thresholds can be coded.
6. **Next: `F05-S04_layout_engine_card.md`** — hand to Claude Code once 4 above (F04 patches) and the height measurement above are resolved.
7. In parallel: confirm with Arun which components need gendered images, start sourcing.
8. **Not for this week, don't lose track of them:** `F05-S03_visual_theme_appearance_card.md` (colour theming ideas) and `F04-S06_speed_agility_strength_card.md` (multi-trial data) — both new 2026-06-27, both explicitly next-week planning material.
9. After Saturday: revisit F04-S01 (chart comparison), F05-S07/S08 (report log, ankle section), F03-S06 (targets), admin UI, the multi-trial-column gap (now tracked in F04-S06 instead of a buried bullet).
