# S3.1 — Report Config UI + Query Engine

**Context**
The genuine PDF-blocking prerequisite. Trainer/admin selects a client, date range, components, and output type — this drives everything S4.1 (full PDF) needs. Without this, there's no way to specify what goes into a report. Third tab in the existing shell.

**Reuses Section 15's 4 UI patterns from F02-S02** — compact-row layout, view/edit toggle where relevant, logged-dates chips for date range bounds, 480px max-width cap. Don't re-derive.

**No new wireframe** — `tpl-reportconfig` already exists in `insight_wireframes_v5.html`: client+period selector, component checklist with reading counts, output type toggle (nudge PNG / full PDF), page layout grid picker (1×1/1×2/2×1/2×2).

**Input data**

```
Form fields:
client_id     → dropdown from client_info
date_from     → date picker
date_to       → date picker, defaults to today
components[]  → multi-select checklist, one row per component_master entry (12 rows)
                each row shows a live count: "X readings in range" — query readings
                for that client+component+date range, don't just list components blind
output_type   → toggle: Nudge (WhatsApp PNG) | Full Report (PDF)
layout        → grid picker, only shown if output_type = Full Report
                options: 1×1, 1×2, 2×1, 2×2 sections per page
```

**Query engine**
Given client_id + date_from + date_to + components[]:
1. Pull all `readings` rows matching client_id, component in components[], date between date_from and date_to
2. Group by component, then by metric
3. Resolve baseline per metric: MIN(date) for that client+metric across ALL history, not just the selected range — baseline is a property of the metric's full history, not the report window
4. Compute derived metrics at this point if relevant components are selected: BMI (needs weight_kg + height_cm), waist_hip_ratio (needs waist + hips) — computed here, never stored
5. Return a structured payload: `{component: {metric: [{date, value}], baseline, derived: {...}}}`

**Build**
1. Add "Report Config" as a third tab in the existing shell (alongside Quick Log, Full Assessment).
2. Client dropdown — shared state with other tabs if a client is already selected elsewhere in the session.
3. Date range — reuse the logged-dates-chips pattern for quick bounds (e.g. tapping a chip sets date_to to that date).
4. Component checklist — query `readings` for live counts per component before rendering, so the trainer sees "Physio 1 — 4 readings" not just a blank checkbox.
5. Output type toggle — Nudge vs Full Report. Layout grid picker only renders for Full Report.
6. "Generate" button triggers the query engine, returns the structured payload — this card stops at producing that payload. Actual PDF/PNG rendering is S4.1/S4.2's job, not this card's.
7. Show a simple preview of what will be included (component names + reading counts + date range) before generating, so a trainer can catch "oh I picked the wrong date range" before committing.

**Technical requirements**
1. Unit tests — pytest: query engine with empty range, single component, multiple components, baseline resolution reaching outside the selected date range, BMI/WHR computed correctly when inputs present, gracefully skipped when inputs absent
2. Regression suite — runs S1.1/S1.2/F02-S02 tests too
3. Health check — validates component_id values in the checklist match `component_master` exactly (catches the `anthropometric`-style empty-component problem before it surfaces in a report)
4. Error handling — Sheets API calls in try/catch
5. Auth — reuse existing auth pattern, don't reimplement
6. PWA — not required, this is closer to an admin/laptop tool like the chart comparison session, not phone-first
7. Output versioning — n/a for this card specifically (the payload isn't a file yet — versioning matters once S4.1 actually renders one)

**Acceptance criteria**
1. Same deployed URL, third tab — no new deployment
2. Component checklist shows a live reading count per component for the selected client + date range, not a blind list
3. Selecting Nudge hides the layout grid picker; selecting Full Report shows it
4. Baseline resolves from full client history, not clipped to the selected date range
5. BMI computes only when both weight_kg and height_cm exist in the pulled readings; absent otherwise, no error
6. Preview shows component names, reading counts, and date range before "Generate" is pressed
7. Generate returns a structured payload grouped by component → metric → readings, with baseline and derived metrics included
8. Empty result (zero readings in range for all selected components) shows a clear message, not a blank/broken screen

**Dependencies**
S1.1, S1.2, shell_merge, F02-S02 complete. Does not depend on F04-S01's chart-type decision or S3.3's nudge scoping — report config is the data-selection layer, chart rendering happens after, in S4.1/S4.2.
