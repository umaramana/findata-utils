# F06-S02 — Report Config Redesign: Output Type / Date / Components Pickers

**Status: built (2026-07-31).** Implemented in `apps_script/index.html` (Date card swap + Components card grid), `apps_script/Code.gs` (`generateNudge()` component_id passthrough), `report_query.py` (generalized `build_nudge_payload()`), `nudge_png.py` + `templates/nudge_template.html` (generic stat-box/bar rendering), and `report_service/app.py` (`/generate-nudge` component_id validation). Full test suite green (218 passed) including new coverage in `tests/test_report_query.py` and `report_service/tests/test_app.py`. Not yet smoke-tested against the live Apps Script deployment — see "Next" note below. Design reference: `claude_design/Insight Core interactive options v3/design_handoff_report_config/` (README.md, `Insight Core.dc.html` prototype, `design-system/styles.css`, assets, screenshots) — **use Screen 1 and Screen 5 of that handoff only**. The handoff also contains a Report Style picker (Editorial Ledger vs Scorecard Deck) and three fully-redesigned report/nudge visual outputs (Screens 2–4) — **explicitly out of scope for this card**, see "Out of scope" below.

**Context**
Grew out of a live-session bug fix (2026-07-31, `REPORT_SERVICE_URL` Script Property misconfiguration) that surfaced a structural UX problem while trying to patch it: the Nudge date-defaulting issue wasn't a small tweak, it was Full Report and Nudge sharing one date-picker and one component-checklist that don't fit both output types. Scoped into a problem-statement stub (`report_config_ux_rethink_stub.md`) and handed to Claude chat per this project's chat-designs/code-builds protocol. Chat's design pass came back bundling this picker rework together with a separate, bigger report-visual-redesign proposal the user hadn't asked for and doesn't want built now — descoped back down to the original four problems before writing this card. Supersedes the informal picker described in `F05-S01_S02_report_config_card.md` (component checklist, shared date field) — this card is the source of truth for that part of the tab going forward.

**What's in scope from the handoff**
1. **Output Type** segmented control: `Nudge` / `Full Report` (2 options, existing Modernist segmented-control CSS) — same control as today, no visual change needed beyond what already exists.
2. **Session/Date card**: single "Date" field for Nudge; "From"/"To" side-by-side fields for Full Report. Same card position in both states, field set swaps.
3. **Components card**: 2-column card grid (not checklist) replacing the old checklist. Nudge = single-select (radio-like, deselects others), now able to pick **any of the 7 components**, not hardcoded to Body Vitals. Full Report = multi-select (independent toggles). Badge shows "1 of 1" / "N selected". Helper text explains the mode. Switching Full Report → Nudge with multiple selected collapses to the first previously-selected component — never drops to zero/errors.

**Explicitly NOT in scope**
- **Report Style picker** (Editorial Ledger vs Scorecard Deck) — dropped entirely. There is only one Full Report visual output today; this card does not add a style choice for it.
- **Any visual redesign of the report/nudge output itself** — Full Report PDF and Nudge PNG keep their current existing look. The only change to Nudge's *output* is that it can now render whichever single component was picked (reusing the existing Nudge rendering pattern for that component), not a new visual treatment.
- Insight-brand design tokens, new fonts/colors/asset usage from the handoff's Screens 2–4 — none of that applies here.

**Input data**
```
Report Config state (extends existing client/dateFrom/dateTo/layout/components):
  outputType   : 'nudge' | 'full_report'
  components[] : single id (nudge, any of the 7) | any-length array 0-7 (full_report)
```

**Scope**

*Report Config tab (`apps_script/index.html` + `Code.gs`):*
1. Keep the existing Output Type segmented control (`Nudge` / `Full Report`) — no Report Style control is added.
2. Replace the Session/Date field(s) with the swap-by-mode Date card (single date vs. From/To), per handoff Screen 5.
3. Replace the Components checklist with the 2-column selectable-card grid, wired to single-select (Nudge) / multi-select (Full Report) — implement as two distinct interaction modes sharing one grid, not one generic multi-select capped at 1.
4. Wire badge text ("1 of 1" / "N selected") and helper text to live state, per handoff Screen 5.
5. Preserve existing Page Layout grid picker unchanged (Full Report only, as today).

*Nudge rendering (`nudge_png.py`, `report_query.build_nudge_payload()`, Cloud Run `/generate-nudge`):*
1. Extend to accept any of the 7 component ids (currently hardcoded to `body_vitals`) — reuse the existing Nudge card layout/style, just source data for whichever component was selected instead of always Body Vitals.
2. Full Report rendering (`report_pdf.py`) is unchanged by this card — it already handles arbitrary component selection today.

**Technical requirements**
1. Unit tests: single-select collapse behavior (Full Report multi → Nudge single, keeps first-selected, never drops to zero), badge/helper text per mode, Nudge payload/render correctly switches data source per selected component (not just Body Vitals).
2. Regression suite — must still pass existing Report Config + report-generation tests, and the Cloud Run bridge's existing test suite from `F05-S07`/`F05-S09`.
3. Visual smoke test against `screenshots/3b-nudge-state.png` and `screenshots/3b-full-report-state.png` for the picker layout only (ignore anything in those screenshots implying a report-style choice, if present).
4. `Insight Core.dc.html` (`id="3b"`) is the live/clickable reference for the exact picker state-swap logic — read its `<script data-dc-script>` block (`buildT3()`/`t3Default()`) for the precise transformations, but ignore any `reportStyle` state it tracks.

**Acceptance criteria**
1. Output Type control swaps the Date card and Components card modes together, consistently — no stale state from the previous mode.
2. Nudge mode: Components card is single-select across all 7 components, badge reads "1 of 1", selecting a new card deselects the previous one.
3. Full Report mode: Components card is multi-select 0–7, badge reads "N selected" live.
4. Date card shows exactly one date input in Nudge mode, two (From/To) in Full Report mode, same card position both times.
5. Generating a Nudge with a non-Body-Vitals component selected (e.g. Body Measurements) produces a correct PNG for that component, using the existing Nudge card style.
6. Full Report generation is unaffected — same PDF output as before this card.
7. No Report Style control appears anywhere in the UI.

**Dependencies**
`F05-S01_S02` (existing Report Config tab, superseded by this card's picker section), `F05-S07`/`F05-S09` (Cloud Run bridge, generateReport/generateNudge — reused, not rebuilt), `report_service/DEPLOY.md`'s live deployment (Script Properties, shared secret) — no new deployment infra needed, this is a code-path change inside the existing bridge.

**Design decision made during build (not in the original handoff)**
The handoff never specified what a Nudge card should show for the 5 components beyond Body Vitals/Body Measurements (Physio 1/2/3, Balance Open/Closed) — their metrics are reps/seconds/km/cm, not the %/bar shapes the existing card was built for. Confirmed with the user: each of those components gets a headline delta stat (its first/primary metric, e.g. pushups, plank, cooper_test, balance_normal_open/closed) + up to 2 more metrics as latest-value-only stat boxes — same visual slots the existing Body Vitals card already used for weight/fat/muscle. Body Measurements keeps its existing waist/hips bar-list untouched, now also driving a waist-delta headline. See `NUDGE_METRIC_CONFIG`/`NUDGE_METRIC_LABELS` in `report_query.py` for the exact per-component mapping.

**Live smoke-test findings (2026-07-31, post-build)**
- **Bug**: switching Output Type (Nudge ↔ Full Report) left the previous output's payload summary/download banner visible until Generate was clicked again — `setOutputType()` didn't clear them, only `generateReport()` did. Fixed: `setOutputType()` now hides `reportPayloadCard`/`downloadReportWrap`/`downloadReportBanner` immediately on toggle.
- **Bug**: Full Report on a real client (`champion_mr_abhay_singh`) errored `Unknown component_ids: ['strength']`. Root cause: the design handoff's "same 7 components as the old checklist" claim was stale — `component_master` (driving `getComponentsWithCounts()`) has at least one more active component (`strength`, added post-launch per `Code.gs`'s `METRIC_MAP` comments) that `report_service/app.py`'s hardcoded `_ALL_COMPONENTS` and `report_query.py`'s `NUDGE_METRIC_CONFIG` didn't know about. Fixed: added `strength` to both (Nudge headline = bench press weight, boxes = squat/deadlift weight). **Not fully verified** — only confirmed `strength` as the extra component; `ankle_assessment`/`skinfold_measurements` (also in `METRIC_MAP` but historically Full-Assessment-only) may or may not be active in `component_master` too. Check the full `component_id` column once rather than hitting this error again one component at a time.

**Next (not done in this session)**
- Push `index.html` / `Code.gs` to the live Apps Script project (this repo isn't clasp-linked — copy/paste into the Apps Script editor as usual) and smoke-test both Nudge and Full Report pickers live, per the card's Technical Requirements #3.
- Cloud Run needs a rebuild + redeploy for the `strength` component fix (`report_service/app.py` + `report_query.py` changed) — same `gcloud builds submit` / `gcloud run deploy` commands as the original F05-S07 deploy.

**Out of scope**
- Report Style picker (Editorial Ledger / Scorecard Deck) and both of those report visual designs — not being built. If wanted later, scope as a separate card off the same design handoff.
- Nudge WhatsApp Card visual redesign (handoff Screen 4) — Nudge keeps its current existing visual style; only the component-selection logic behind it changes.
- Any new output type beyond Nudge/Full Report (that's `F06-S01`'s long-horizon template-type vision — don't conflate).
- `ios-frame.jsx`/`android-frame.jsx` — device-bezel mockups, reference-only.
- Promoting the Modernist-reskin Test deployment to production for Arun — tracked separately in `project_insight_core.md`, unrelated to this card's scope.
