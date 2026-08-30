# Insight Fitness Data Services — Context Handoff v2
**Updated 2026-08-29 | Paste this at the start of every Claude Code session**

**Rebuild note (2026-08-29):** This doc had become an append-only stack of six superseded "read this first" sessions plus a long historical sprint narrative — genuinely stale and too long to be useful at the start of a session. Rebuilt from scratch as a current-state snapshot, sourced from `git log`/live code (verifiable) + `PARKING_LOT.md` (Claude Code's own deferred-items log). One real gap: Claude Code's session memory (previously referenced here as `project_insight_core.md`) could not be located in the repo or on Uma's machine — `.claude/` is gitignored by design, and the file itself may never have existed as a persisted artifact rather than shorthand for in-session context. Sessions 9–13 (2026-07-25 → 2026-08-21) are reconstructed from commits + `PARKING_LOT.md` only, not from that source. Flagged inline anywhere confidence is lower than "verified against live code."

---

## Current state (read this first)

**Live and working, confirmed against code/commits, not narrative:**
- **Cloud Run report-generation bridge is deployed and live** (`F05-S07`/`F05-S09`, 2026-07-14). Apps Script's "Share" tab calls it directly on button click — no polling, no queue. Free-tier, scales to zero between requests.
- **Nudge PNG generation is built and working** (2026-07-25 initial build, several fix rounds through 2026-08-21: body_vitals fallback boxes, pulse/bpm label fix, headline/kicker/date/footer fixes). Renders via `nudge_png.py` + `nudge_template.html`.
- **Full Report PDF pipeline** (`report_pdf.py` + Puppeteer) — built, deployed, reachable via the same Cloud Run service.
- **Report Config redesigned** (`F06-S02`, 2026-08-01): single UI ("Share" tab) with an Output Type toggle — Nudge (single-select component, single date) vs Full Report (multi-select components, date range). Both currently pull the same component list from `getComponentsWithCounts()` — **no per-output-type filtering exists yet**; this is exactly the mechanism `F06-S04` (in progress, see below) needs to build for the first time.
- **App shell reskinned** ("Modernist," 2026-07-25) and **tabs renamed**: Log / Assess / Share (was Check-In / Full Assessment / Report Config), landed 2026-08-04.
- **Full Report component whitelist**: `report_service/app.py`'s `_ALL_COMPONENTS` — 8 components, confirmed `ankle_assessment`/`skinfold_measurements` are absent from it (already excluded server-side). Not yet mirrored client-side in Apps Script's Full Report grid — components still display there regardless of server-side eligibility.

**Confirmed NOT built (checked live code directly, not assumed):**
- Log tab still shows only 3 body-vitals fields (Weight, Fat%, Muscle%) — `F06-S03` (show all 7) has not landed.
- No WhatsApp send integration exists anywhere in the codebase. Every Nudge is a manually-downloaded-and-sent PNG. ("WhatsApp Card" in code comments is a design-reference name only.)
- No 3+ option form field type exists yet — only 2-option `toggle` (binary-encoded) and `time`.

**In progress, not yet reviewed or built:** `F06-S04_grip_strength_component_card.md` (2026-08-29) — new Grip Strength component (tracked clients, feeds Nudge/history) **plus** a new standalone "Walk-In" tab (untracked gym-challenge entries: name+phone, inline PNG generation, no client record, `wa.me` link for manual send). Surfaced a real, previously-unaddressed gap: nothing in the current build or the future 4-tab vision (Clients/Assess/Reports/Admin — see the wireframe-integration conversation) has a concept of non-client data. Leaderboard view explicitly deferred (schema kept ready for it). Video capture + collage-reel idea flagged by Arun for later, not scoped. **Awaiting Uma's review before handoff to Claude Code.**

**Known open items** (full detail in `PARKING_LOT.md`, kept current by Claude Code):
- `F06-S03` Log tab all-7-vitals — not started.
- OAuth refresh token expiry risk — GCP consent screen likely still in "Testing" mode (7-day auto-expiry); needs publishing to Production or this recurs weekly.
- Full Report end-to-end test still owed since the Cloud Run IAM fix (service was previously `--no-allow-unauthenticated` with zero invoker bindings — likely means Full Report never actually completed before that fix).

---

## What we are building

Fitness assessment reporting platform for a single personal trainer (Arun Alex David, Insight Fitness, Chennai). Converts client assessment data into structured reports — WhatsApp-shareable nudge PNGs and full PDFs. Long-term: PT Agent (clinical reasoning partner for the trainer), Layer 1 movement-assessment pipeline (video → MediaPipe → corrective exercise), eventual multi-trainer SaaS.

**Not building now:** client-facing interface, automated WhatsApp send, multi-trainer support — all vision-stage, no committed timeline.

**Stack:** Python (matplotlib for charts, Puppeteer for PDF rendering) on Cloud Run; Google Sheets (`insight_pilot`) as sole data store; Google Apps Script for the web UI; Canva (chrome/shell assets only, code places all content).

---

## Three-layer assessment framework (stable domain reference — see `Insight_Assessment_Framework.docx` for full detail)

| Layer | Type | Examples | Report status |
|---|---|---|---|
| 1 — Foundation | Movement | Ankle assessment, Apley scratch, overhead squat | Excluded from Full Report (chart type undecided); movement pipeline (video/MediaPipe) is vision-stage |
| 2 — Capability | Performance | Physio 1/2/3, Balance, Cooper test, Strength, (new) Grip Strength | Live in both Nudge and Full Report |
| 3 — Composition | Body metrics | Weight, fat%, muscle%, girths, BP, BMI, pulse | Live in both Nudge and Full Report |

Directional relationship: Layer 1 findings → Layer 2 corrective targets → Layer 2 changes contextualized by Layer 3. Reference ranges apply at every layer (see framework doc for sources — ACSM, WHO, IAP 2015 for Indian pediatric standards).

---

## Google Sheets structure — `insight_pilot`

Core tabs: `readings` (client_id+date+component+metric unique key), `component_master`, `metric_master`, `client_info`, `admin_config`, `exercise_library`, `muscle_groups_library`, `charts_config`, `asset_library` (component_id | gender | image_ref). Exact current row counts not re-verified this pass (would need a live Sheets read, not available from the repo) — treat any specific count from before 2026-07-06 as stale.

New from `F06-S04` (pending review, not yet built): `grip_strength_walkins` (name, phone, date, 6 trial values, 2 grades — no `client_id`, deliberately separate from `readings`).

---

## Key rules (stable — do not re-litigate)

- date+component+metric(+client_id) = unique key, no duplicates
- Baseline = MIN(date) per client+metric, auto-derived
- BMI/waist-hip ratio computed at report time, never stored
- Durations always integer seconds
- All reading submission is upsert/delete, not append-only
- table_heatmap fill: continuous proportional bar scaled to each row's own min/max — not discrete threshold bands
- Missing data within an otherwise-populated table: literal "-"; a fully-empty payload shows a centered "No data" message (different states)
- Any single section's failure (no image, no data) degrades that section gracefully, never blocks the whole report
- New components are Full-Report-excluded by default (whitelist, not blacklist) until explicitly added — confirmed working pattern, not just a stated intent

---

## Chart types

| Type | Status |
|---|---|
| Bar-chart family (`horizontal_single`, `vertical_single`, `stacked_pair`, `grouped_multi`) | Built, Python/matplotlib, pytest-tested. `stacked_pair` (Blood Pressure, Body Composition) still missing the reference-slot-width fix already applied to `grouped_multi` — open bug, not fixed this pass. |
| table_heatmap | Built, Python/matplotlib, pytest-tested. 8-stop brand gradient, dual-mode normalization. |
| Pulse | `circular_gauge`, not a bar — confirmed against real sample data. |
| line_area, multi_line, slope, dot_timeline, calendar_heatmap, radar, bullet | Not in current scope — no evidence of use in real report samples. Revisit only if specifically requested. |

`qc_report.py` checks structural rules, chart correctness, and duplicate detection — deliberately not archetype-baseline-driven. Explicitly skips Blood Pressure orientation checks; no Body Composition coverage yet.

---

## Trello / card format

Title, Context, Input data, Wireframe (or "no wireframe, reuses X"), Scope/Build, Technical requirements, Acceptance criteria, Dependencies, Out of scope, Verified by (when claims are checked against live code/tests rather than assumed).

---

## Key decisions locked — do not re-discuss

- Google Sheets is the sole data store; BMI/waist-hip ratio computed at report time, never stored
- Python (matplotlib) for all charts, Puppeteer for PDF — not Chart.js, not D3, not Flourish/Looker
- Single-flow infographic PDF, no pagination; charts as SVG (not PNG); heatmaps as HTML `<table>`
- One app shell, one deployed URL, tabs added incrementally — never a second deployment
- Cloud Run (on-demand, scales to zero) for the report-generation bridge — rejected an always-on poll-worker/VM as over-engineered for a two-person pilot
- Upsert/delete standing pattern for readings, no pair-blocking
- Every card file named by its `F0X-S0X` ID, never a session-label (`S1.1`, `S3.1`, etc.)
- `insight/PT_Agent/*.md` cards are the only source of truth; this doc is the index, kept current by Claude Chat. Claude Code codes, doesn't maintain docs. `PARKING_LOT.md` is Claude Code's own deferred-items log — don't duplicate it with a second "future state" doc.
- Client-facing interface, multi-tenancy, automated WhatsApp send: all deferred, no committed timeline

---

## Files produced — current set (verified against the repo 2026-08-29, not the pre-07-06 snapshot)

| File | Status |
|---|---|
| `F02-S02_full_assessment_form.md` | Built |
| `F04-S02_S03_S04_chart_rendering_card.md`, `F04-S05_table_heatmap_card.md` | Built |
| `F04-S06_speed_agility_strength_card.md` | Backlog, not scoped |
| `F04-S07_date_count_generalization_card.md`, `F04-S08_sheets_orchestration_card.md`, `F04-S09_male_icon_wiring_card.md` | Built, landed 2026-07-04 |
| `F04-S10_live_sheet_asset_reading_card.md` | Not built — next sprint item, still open |
| `F05-S01_S02_report_config_card.md` | Built, later superseded in shape by `F06-S02` |
| `F05-S03_visual_theme_appearance_card.md` | Ideas only, not scoped |
| `F05-S04_layout_engine_card.md`, `F05-S05_full_pdf_card.md`, `F05-S06_gender_image_card.md` | Built |
| `F05-S07_report_generation_trigger_card.md`, `F05-S09_report_generation_trigger_card.md` | Built and deployed live, 2026-07-14 |
| `F06-S01_template_architecture_vision_card.md` | Vision only, no timeline |
| `F06-S02_report_config_redesign_card.md` | Built, 2026-08-01 |
| `F06-S03_log_tab_all_vitals_card.md` | **Not built** — confirmed live (Log tab still 3 fields) |
| `F06-S04_grip_strength_component_card.md` | **New, pending Uma's review** — not yet handed to Claude Code |
| `PARKING_LOT.md` | Live, Claude-Code-maintained — deferred items, open bugs, near-term flags |
| `insight_wireframes_v6.html`, `insight_er_delta_core_model.html`, `er_and_journey_v2.html` | Reference, not re-audited this pass |
| `S3.3_whatsapp_nudge_card.md` | Stub only, superseded in practice by the live Nudge PNG build — confirm with Uma whether to formally retire this file |
| `shell_merge_card.md`, `sprint1_vip_cards_v2.md`, `sprint2_chartsampler_card.md`, `image_mapping_and_sheet_integration_card.md` | Historical/early-build cards — done, kept for record, not active reference |

---

## Immediate next actions

1. Uma reviews `F06-S04_grip_strength_component_card.md` (Grip Strength component + Walk-In tab) — not yet handed to Claude Code.
2. `F06-S03` (Log tab, all 7 vitals) — open, not started, in `PARKING_LOT.md`.
3. OAuth consent screen — confirm whether it's been published to Production; if still "Testing," the weekly `invalid_grant` refresh-token expiry will recur.
4. Full Report end-to-end test — owed since the Cloud Run IAM allow-unauthenticated fix; not confirmed working post-fix.
5. `stacked_pair` chart reference-slot-width fix (Blood Pressure, Body Composition) — known gap, not yet applied.
6. `F04-S10` (live asset_library wiring) — still open, next-sprint item from well before this rebuild, not superseded by anything since.
