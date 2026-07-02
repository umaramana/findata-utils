# F02-S02 — Full Assessment Form (v3 — updated post-build 2026-06-24, handed to Arun for testing)

**Status: ✅ Built and shipped 2026-06-24.** Sections below marked "v2 spec" are the original card; "As-built" notes capture what shipped, including additions made live in response to Arun's feedback the same day.

**Step 0 / Dependency — shell merge first** ✅ done 2026-06-24 (`shell_merge_card.md`)
S1.2 shipped as a standalone Apps Script deployment with no navigation shell, which diverges from the wireframes' single-app-shell structure. Before building this form, complete [shell_merge_card.md](shell_merge_card.md): retrofit S1.2's check-in form into a shared shell (one `index.html`, one `Code.gs`, one deployed URL, tab-switcher per `insight_wireframes_v6.html`). This form must then be added as a **second tab inside that same shell** — it must never become its own separate Apps Script deployment.

**Context**
Extended form covering all components beyond the simple 3-field check-in (S1.2). Trainer fills in whatever was assessed that day — body vitals, measurements, physio 1/2/3, balance, strength — leaves the rest blank. Same handover model as S1.2: trainer owns this once live. Ankle assessment fields render but stay pending until video processing lands (separate pipeline, expected Wed) — the form supports it now so nothing needs rebuilding later.

**This version aligns to what S1.2 actually implemented**, not the original assumptions:
- `readings` is the 9-column schema (`client_id, date, component, metric, value, unit, source, notes, recorded_at`) — not 7
- Submit is **upsert/delete**, not append-only: existing row for `client_id+date+component+metric` gets updated in place; a field cleared on a date that has an existing row **deletes** that row; a never-existing blank field writes nothing
- **Pre-fill**: selecting client + date loads any existing readings for that combination into the form before the trainer edits anything
- **Paired metrics no longer block on incomplete pairs** — each metric (including reps/weight pairs) is upserted/deleted independently. The old "both filled or both blank" validation is dropped; it conflicted with editing pre-filled data (clearing just `weight` on an existing entry should delete that row, not get blocked as a broken pair)

**No new wireframe** — reuses the `form-field` input pattern from S1.2 and the accordion pattern from the Deviation wireframe screen.

**Input data — as-built (10 sections, 59 active metrics + 3 pending)**

Original v2 spec was 8 components / 46 metrics. During the build, Arun's same-day feedback added `mile_test`, `coordination`, 4 stork balance tests ×2 eye states (8 metrics), and a new `skinfold_measurements` component (3 metrics) — applied live to `metric_master`/`component_master` via `migrate_v2_metrics.py` (62 metric rows, 12 component rows total now). New totals: **9 active components + 1 pending (ankle) = 10 rendered sections, 59 metrics that actually save + 3 pending.**

```
Section: Body Vitals
weight_kg, fat_pct, muscle_pct, bp_systol, bp_diastol, bpm, height_cm
→ plain number inputs

Section: Body Measurements
neck, waist, abdomen, hips, thighs, calves, arms, forearms, chest
→ plain number inputs, inches

Section: Physiological 1
pushups, squats, crunches, pullups_reps, pullups_weight (shown side by side, no pair-block)
→ plain number inputs

Section: Physiological 2
plank, right_side_plank, left_side_plank, hold_40deg, sorenson_hold
→ number input, seconds. hint: "in seconds, e.g. 45"

Section: Physiological 3
cooper_test (km, 2 decimals), mile_test [ADDED], flexibility (cm, 1 decimal), coordination (cm, 1 decimal) [ADDED]
→ plain number inputs, except mile_test → type "time" (hh:mm:ss UI), stored as total seconds — same "duration in seconds" convention as Physio 2, not a new exception

Section: Balance — Eyes Open
balance_normal_open, balance_tandem_right_open, balance_tandem_left_open, balance_right_up_open, balance_left_up_open,
stork_stand_left_open, stork_stand_right_open, stork_toes_left_open, stork_toes_right_open [4 ADDED]
→ number input, seconds

Section: Balance — Eyes Closed
balance_normal_closed, balance_tandem_right_closed, balance_tandem_left_closed, balance_right_up_closed, balance_left_up_closed,
stork_stand_left_closed, stork_stand_right_closed, stork_toes_left_closed, stork_toes_right_closed [4 ADDED]
→ number input, seconds

Section: Strength
bench_press_reps, bench_press_weight (side by side)
leg_press_reps, leg_press_weight (side by side)
deadlift_reps, deadlift_weight (side by side)
squat_reps, squat_weight (side by side)
→ reps as number, weight as number (lbs)

Section: Ankle Assessment (renders, stays pending until video pipeline delivers findings)
ankle_right_mobility, ankle_left_mobility, ankle_pronation
→ toggle/checkbox — Pass/Fail or Yes/No. Shows "Pending — awaiting video review" placeholder when no value exists yet for that client+date.

Section: Skinfold Measurements [NEW COMPONENT, renders last — after Ankle Assessment]
skinfold_chest, skinfold_abdomen, skinfold_thighs
→ plain number inputs, mm (shipped as a cm placeholder, confirmed mm by Arun same day — unit fixed via fix_skinfold_unit.py; no live readings existed yet so no data needed re-tagging)
```

`anthropometric` component is excluded entirely — 0 metrics seeded, not relevant to render.

**As-built UI additions (beyond original v2 spec, driven by Arun's live feedback 2026-06-24)** — these are now the form's actual behavior, not just the v2 spec below:
- **Compact-row layout**: every field is one line (label left, small input right) instead of label-above-input — original spec assumed label-above-input; changed once Arun flagged the 9+-field sections as too long to scan. See `.acc-row` family in `index.html`.
- **View/Edit toggle per section**: a section with existing data renders as small read-only widget cards (value + label) instead of input boxes; tap "✏ Edit" to flip to editable rows. Auto-switches back to view after pre-fill or after Save — also fixes "post-save, numbers shouldn't sit in input fields."
- **"Logged dates" chips**: after picking a client, up to 10 most-recent dates with existing readings show as tappable chips below the date field (`getClientDates()` in `Code.gs`) — lets the trainer find an existing entry without remembering the date. Applied to both Check-In and Full Assessment tabs.
- **Body capped to `max-width: 480px`** — the mobile-first layout was stretching unstyled across wide desktop browsers.
- These four patterns are reusable — apply to S3.1 (report config UI) rather than re-deriving from scratch.

**Addition (2026-06-25) — "What are you testing today?" picker — ✅ implemented in `index.html`**
Insight is moving to a continuous-assessment model: Arun typically logs 1-2 tests per session, not all 10 sections at once. The existing single "Save Assessment" button already handles this correctly (only filled metrics write — see Build step 5), but scrolling past unused sections to reach the button at the bottom is real friction for a 1-2-test session.
- Added a chip per section (10 chips — `buildTestPicker()`, one per `SECTIONS` entry including Ankle Assessment) above the accordion. Tapping a chip expands/collapses *only that section* — chips toggle independently, there is no "collapse the rest" behavior. A chip's active state stays in sync with its section's open/closed state no matter what triggered it (chip tap, header tap, or auto-open after prefill), via a shared `setSectionOpen(sectionId, open)` helper.
- **Found and fixed during implementation**: the picker would have been pointless without this — `setSectionMode()` previously force-opened *every* section (data-bearing or empty) after every prefill, which is what actually caused the scroll fatigue, not the single bottom Save button. Fixed so only sections **with existing data** auto-open (as a compact view-mode widget strip — cheap, worth seeing without a tap); empty sections now stay collapsed after prefill unless picked via a chip or the header. Sections with data still auto-open exactly as before (AC14 unaffected).
- **Save behavior is unchanged** — it still saves whatever has values regardless of which chips are selected. The picker is a navigation/scroll convenience only; it must never gate or filter what `submitFullAssessment` writes, so filling in an unpicked section (e.g. trainer changes their mind mid-session) still saves normally — every `[data-metric]` field stays in the DOM (just visually hidden when collapsed) and is collected on submit regardless of picker/open state.
- Out of scope for this addition: per-section save buttons and autosave-on-blur were both considered and rejected — see `fluffy-bubbling-curry.md` plan for the full options/roast. Reasons: per-section buttons are coarser than "one test" and risk a trainer saving one edited section while forgetting another; autosave trades one reliable batch submit for many small calls on unreliable gym wifi and breaks the existing `{saved, removed}` confirmation-count behavior (AC 11).
- The actual "nudge right after 1-2 tests" need is a separate, not-yet-built feature — tracked in `S3.3_whatsapp_nudge_card.md`, not solved by this picker.

**Build**
0. **Architecture correction — do this first:** S1.2 was built as a standalone Apps Script deployment with no navigation shell, diverging from the wireframe's unified-app structure. Before adding this form, wrap S1.2's existing `index.html` content as the first tab ("Quick Log") inside a minimal tab-switcher — reuse the exact pattern `insight_wireframes_v6.html` already uses: one HTML file, content blocks, a small JS function toggling which block is visible. Add "Full Assessment" as the second tab. **Same `Code.gs`, same deployed URL, no new deployment.** S1.2's form logic is unchanged, just wrapped.
1. Within the "Full Assessment" tab: single-page form, 10 collapsible accordion sections (one per component, ankle_assessment second-last, skinfold_measurements last).
2. Each section header shows component display_name + a live "X of Y filled" count.
3. Client dropdown and date picker are shared across both tabs — selecting a client/date in one tab keeps it selected when switching to the other (don't reset state on tab switch).
4. **Pre-fill**: on client+date selection, query `readings` for that client_id+date across all 59 active metric_ids (+3 pending ankle), populate matching fields.
5. **On submit**, for each of the 59 active fields:
   - Has a value, no existing row for that client_id+date+component+metric → append new row with all 9 columns, `recorded_at` = IST timestamp
   - Has a value, existing row found → update `value` and `recorded_at` in place
   - Empty, existing row found → delete that row
   - Empty, no existing row → skip
6. No pair-completeness validation — every metric (including pair members) follows the same independent upsert/delete logic.
7. Ankle Assessment section: same upsert/delete logic applies once values exist; shows "Pending" placeholder when absent. This card doesn't build the video-to-form pipeline — just makes the form capable of accepting values once they're ready, typed in manually or by that pipeline later.
8. Confirmation message: "Logged for [full_name] on [DD/MM/YYYY] — [N] readings saved, [M] removed." (counts both upserts and deletions so the trainer can confirm what actually changed)

**Technical requirements**
1. Unit tests — pytest: new-row insert, in-place update, delete-on-clear, pre-fill load, all-blank submit (no-op), ankle section pending state
2. Regression suite — runs S1.1/S1.2 tests too
3. Health check — validates no duplicate client_id+date+component+metric keys exist in readings after any submit (enforces the locked uniqueness rule)
4. Error handling — Sheets API calls in try/catch, errors to `errors` tab
5. Auth — reuse `sheets_auth.py` / the GAS auth pattern from S1.2, don't reimplement
6. PWA — yes, same as S1.2
7. Output versioning — n/a, no file output, just sheet rows

**Acceptance criteria**
1. Same deployed URL as S1.2 — no second Apps Script deployment exists
2. "Quick Log" and "Full Assessment" appear as switchable tabs at the top of the same page; S1.2's original form behaviour is unchanged inside its tab
3. Selecting a client and date in one tab persists when switching to the other tab
4. All 10 sections render, collapsed by default, expand on tap
5. Each section shows a live "X of Y filled" count
6. Selecting an existing client+date pre-fills all matching existing readings into the form
7. Submitting with only Body Vitals filled writes only those rows — other 9 sections contribute nothing
8. Re-submitting a date with bench_press_weight changed updates that row in place — no duplicate created
9. Clearing bench_press_weight while leaving bench_press_reps filled deletes only the weight row — reps row untouched, no pair-block error shown
10. Ankle Assessment section shows "Pending — awaiting video review" on all 3 rows when no value exists for that client+date
11. Confirmation message shows correct counts of readings saved and removed
12. Usable on iPhone Safari and Android Chrome without horizontal scroll, even with 10 sections expanded
13. Every field within a section renders as a single compact row (label left, input right) — no field wraps to a label-above-input layout, even on narrow phone widths
14. A section with at least one existing reading for the selected client+date renders in view mode (read-only widget cards showing value + label) by default, not as open input rows; tapping "✏ Edit" switches that section to editable rows
15. After Save, every section that was in Edit mode reverts to view mode — no input field is left showing a raw value post-save
16. Selecting a client shows up to 10 tappable "logged date" chips (most recent first) below the date field, populated from that client's existing readings; tapping a chip selects that date and triggers pre-fill, on both the Check-In and Full Assessment tabs
17. Page content is capped at 480px max-width and stays centered on desktop browsers — does not stretch unstyled edge-to-edge on wide viewports
18. The "what are you testing today?" picker shows one chip per section (10 chips, matching all 10 accordion sections including Ankle Assessment); selecting a chip expands only that section, deselecting collapses it; no other section's expand/collapse state changes
19. With zero chips selected and no client/date chosen yet, all sections remain collapsed by default (unchanged from today's behavior). Once an existing client+date is selected, sections with existing data still auto-open as view-mode widget summaries (per AC14) — this is independent of chip selection. Empty sections stay collapsed regardless of prefill, until picked via a chip or the header
20. Submitting after filling only an unpicked section (no chip selected for it) still saves that section's values — the picker never blocks or filters what gets written

**Dependencies**
S1.1 complete (schema + metric_master, 9-column readings). S1.2 complete (client_info populated via add-client flow, upsert/pre-fill pattern established) — this form follows the same pattern, not a separate design. **shell_merge_card.md complete** (single app shell with tab-switcher) — this form is built as a tab inside that shell, not a standalone deployment. **migrate_v2_metrics.py run once 2026-06-24** against the live `insight_pilot` sheet to append the 13 new metric rows + 1 new component row (`metric_master` 49→62, `component_master` 11→12) — do not re-run; it's a one-off append, not idempotent.
