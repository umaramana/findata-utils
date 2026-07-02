# F04-S01 — Chart Comparison Session (one-time tool, not an app tab)

**Context**
This is a **disposable, one-time decision-making tool**, not a permanent app feature. The only thing that needs to outlive this session is the `charts_config` data it produces. Admin (Uma) + Trainer (Arun) look at chart options side by side using VIP's real data, agree on defaults, done. No navigable tab, no resumable session state, no skip-button complexity — that kind of polish only matters if trainers need to revisit chart choices repeatedly, which is Vision scope (F03-S07), not this week.

**Design note — this writes to a NEW tab, not `admin_config`**
The ER diagram's `Chart` entity (component_id, chart_type, metrics[], aggregation_period) is a grouping concept — multiple metrics combined into one chart (e.g. weight+fat%+muscle% as one multi-line chart). `admin_config` is per-metric and doesn't cleanly hold that grouping. Add a new tab:

```
Tab 8: charts_config
chart_id | component_id | chart_type | metrics_list | aggregation_period
```
`metrics_list` is pipe-separated metric_ids, e.g. `weight_kg|fat_pct|muscle_pct`.

This tab is the only thing that matters surviving past today's session. Rows can be typed in directly by Uma after the comparison, or saved via a simple one-click action on the comparison page — either is fine.

**Input data**

Render these as real side-by-side comparisons — not a dropdown to click through one at a time:

```
component_id | options to render side by side | rationale
body_vitals | multi_line | weight_kg + fat_pct + muscle_pct combined
body_vitals | grouped_bar | bp_systol + bp_diastol combined
body_vitals | line_area | bpm
body_measurements | grouped_bar | each metric separate
anthropometric | — | 0 metrics seeded — leave out entirely, not relevant to render
physio_1 | table_heatmap AND slope, side by side | let real comparison decide, don't default silently to old Looker style
physio_2 | table_heatmap AND slope, side by side | same
physio_3 | slope AND line_area, side by side | trend over months likely wins regardless
balance_open | table_heatmap AND slope, side by side | same comparison
balance_closed | table_heatmap AND slope, side by side | same
strength | grouped_bar | reps+weight pairs combined
ankle_assessment | table_heatmap AND trend-bar, side by side | trend-bar matches tpl-progress's existing Apley Scratch pattern
apley_scratch | table_heatmap AND trend-bar, side by side | same
```

Chart type → library (locked decision, no Flourish/Looker):
```
line_area, multi_line, grouped_bar, bar_rolling_avg, radar, bullet → Chart.js
table_heatmap, slope, dot_timeline, calendar_heatmap → D3 custom
```

**Build**
1. Create `charts_config` tab in `insight_pilot` per schema above.
2. Build a single static-ish page — not part of the app's tab navigation — that renders each component's option(s) using real readings if they exist for the client, or a labeled sample dataset if not.
3. Next to each rendered option, a simple "use this" click writes one row to `charts_config` and visually marks it chosen. No dropdown, no separate navigation, no save/skip/resume flow — just scroll down the page, click your picks.
4. Page can be deleted or ignored after this session — it has no role in the running app.

**Technical requirements**
1. Unit tests — only for the `charts_config` write action, not the whole page (it's disposable)
2. Error handling — Sheets API write wrapped in try/catch
3. Auth — reuse `sheets_auth.py`
4. Everything else from the standard 7 (PWA, output versioning, regression suite, health check) — **not applicable**, this isn't a persistent feature

**Acceptance criteria**
1. Each component's chart option(s) render with real data if available, labeled sample data otherwise
2. Clicking "use this" writes exactly 1 row to `charts_config` with correct component_id, chart_type, metrics_list
3. `anthropometric` is not rendered at all
4. Page works once, correctly — no requirement to handle re-visits, partial completion, or session resume

**Dependencies**
S1.1 complete (schema + metric_master). Real readings improve the comparison but aren't a hard blocker — sample data fallback covers it.
