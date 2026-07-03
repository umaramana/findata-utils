# Insight Fitness Data Services — Product Backlog
**Version 0.3 | Admin: Uma | Actor legend: [A]=Admin(Uma) [T]=Trainer(Arun) [S]=System [H]=Handover point**

---

| ID | Feature | Story | Description | User Journey | Priority | Scope |
|---|---|---|---|---|---|---|
| F01-S01 | Data Model | Define Google Sheets schema | One sheet per client, normalised rows: date, component, metric, value, unit, source, notes, is_baseline | [A] Phase 1 — Admin creates sheet structure once before any data is logged | P1 | Now |
| F01-S02 | Data Model | Seed component + metric master | All components and metrics with unit, display_unit, decimal_precision, paired_metric_id, assessment_type | [A] Phase 1 — Admin seeds master data once. Trainer reads component list at report config | P1 | Now |
| F01-S03 | Data Model | Duration value conversion | Convert Excel day fractions from old sheet to seconds on import | [A] Phase 1 — Admin runs migration script once on old sheet data | P1 | Now |
| F01-S04 | Data Model | Baseline auto-assignment | MIN(date) per client+metric is automatically baseline — derived on query, no manual flag | [S] Phase 2 — System derives baseline silently on first reading per metric per client | P1 | Now |
| F01-S05 | Data Model | Derived metrics at report time | BMI and waist_hip_ratio computed at render from stored readings — not stored as readings | [S] Phase 3 — System computes at query time; trainer never sees this step | P2 | Now |
| F01-S06 | Data Model | Multi-trainer support | Trainer entity added, client belongs to trainer, permissions scoped per trainer | [A] Vision — Admin onboards additional trainers onto platform | — | Vision |
| F01-S07 | Data Model | Session entity | Group readings by session for clinic/group assessment contexts | [T] Vision — Trainer runs group session, readings grouped | — | Vision |
| F02-S01 | Data Input | Simple check-in form | Web form for trainer: weight, fat%, muscle% for one client, submits to Google Sheet tab | [H→T] Phase 2 — Primary handover. Trainer opens saved link after weigh-in, logs 3 values, submits. Admin no longer involved in data entry | P1 | Now |
| F02-S02 | Data Input | Full assessment form | All components — trainer fills what was assessed, nulls not stored | [T] Phase 2 — Trainer logs full assessment day via extended form. Same handover as F02-S01 | P2 | Now |
| F02-S03 | Data Input | Historical data migration | Parse old wide-format sheet → normalised schema including duration conversion | [A] Phase 1 — Admin runs once to migrate existing client history before platform goes live | P2 | Now |
| F02-S04 | Data Input | Input method config | Per-trainer setting for preferred input method | [A] Vision — Admin sets input preference when onboarding new trainer | — | Vision |
| F02-S05 | Data Input | WhatsApp chat parser | Claude API parses .txt export → sheet with parse_confidence flag (sheet only, not in report) | [T] Vision — Trainer exports chat, drops file, system parses. parse_confidence stays in sheet | — | Vision |
| F02-S06 | Data Input | App CSV import | HealthifyMe/MyFitnessPal CSV → normalised sheet rows | [T] Vision — App-first trainer imports CSV export | — | Vision |
| F03-S01 | Admin Config | Chart type assignment | Admin assigns default chart_type per metric after sampler session | [A] Phase 1 — Admin locks defaults after F04-S01 chart sampler session with trainer | P1 | Now |
| F03-S02 | Admin Config | Chart metric grouping | Which metrics combine into one chart vs separate — paired metrics always together | [A] Phase 1 — Admin configures grouping. Trainer never sees this; system uses at render | P1 | Now |
| F03-S03 | Admin Config | Aggregation period config | Admin sets aggregation_period per chart (daily/weekly/monthly/yearly) | [A] Phase 1 — Admin sets once. Affects how readings are grouped in all charts | P1 | Now |
| F03-S04 | Admin Config | Colour scale config | Admin sets colour_scale_config for table_heatmap — min/max + colour ramp | [A] Phase 1 — Admin configures for physio and balance components | P2 | Now |
| F03-S05 | Admin Config | Asset library | Gender-keyed images per component stored + mapped in admin config | [A] Phase 1 — Admin uploads images once. System selects at render based on client gender | P2 | Now |
| F03-S06 | Admin Config | Target values per client | Admin sets target value per metric per client — unlocks bullet chart | [A] Phase 1/ongoing — Admin sets composition goals per client. Unlocks bullet chart (F04-S11) | P3 | Now |
| F03-S07 | Admin Config | Trainer chart override | Trainer changes default chart type for a specific report | [H→T] Vision — Handover: trainer takes chart selection ownership per report | — | Vision |
| F03-S08 | Admin Config | Active metric toggle | Admin deactivates metrics within a component for a specific client | [A] Vision — Admin handles special client protocols (e.g. child client, no BMI) | — | Vision |
| F04-S01 | Chart Rendering | Chart sampler per component | All chart types rendered with Thilak's real data — trainer picks defaults, admin records in config | [A+T] Phase 1 — One joint session. Trainer points, admin configures. Decisions feed F03-S01 | P1 | Now |
| F04-S02 | Chart Rendering | Line area chart | Single metric over time, smooth curve, gradient fill | [S] Phase 3 — System renders for body vitals weight trend nudge | P1 | Now |
| F04-S03 | Chart Rendering | Multi-line chart | Multiple metrics on one chart, dual axis where units differ | [S] Phase 3 — System renders for weight + fat% + muscle% combined view | P1 | Now |
| F04-S04 | Chart Rendering | Grouped bar chart | Multiple time periods per metric — body measurements across dates | [S] Phase 3 — System renders for body measurements full report page | P1 | Now |
| F04-S05 | Chart Rendering | Table heatmap | Colour-scaled table rows — physio 1/2/3, balance, ankle assessment | [S] Phase 3 — System renders for all performance and movement assessment pages | P1 | Now |
| F04-S06 | Chart Rendering | Bar + rolling average | Bars per check-in with 7-day rolling average overlay | [S] Phase 3 — System renders for continuous tracking nudge | P2 | Now |
| F04-S07 | Chart Rendering | Slope chart (before/after) | Two vertical axes, start/end date, metric as slope — D3 custom | [S] Phase 3 — System renders for milestone full report | P2 | Now |
| F04-S08 | Chart Rendering | Dot timeline | Each reading a dot, size = deviation, colour = direction — D3 custom | [S] Phase 3 — System renders for outlier spotting nudge | P2 | Now |
| F04-S09 | Chart Rendering | Calendar heatmap | Month grid, cell intensity = metric value — D3 custom | [S] Phase 3 — System renders for monthly consistency view | P3 | Now |
| F04-S10 | Chart Rendering | Radar chart | Two time periods as polygons on shared axes | [S] Phase 3 — System renders for quarterly comparison full report | P3 | Now |
| F04-S11 | Chart Rendering | Bullet chart | Current vs target vs baseline — requires F03-S06 targets set | [S] Phase 3 — System renders only when admin has set targets for that client | P3 | Now |
| F05-S01 | Report Generation | Report config UI | Select: client, date range, output type, components, layout per page | [H→T] Phase 3 — Handover. Admin does this now on trainer's behalf. UI designed for trainer to take over | P1 | Now |
| F05-S02 | Report Generation | Data query engine | Pulls readings, derives BMI/WHR, resolves baseline, handles nulls | [S] Phase 3 — Fully automated. Trainer waits for render | P1 | Now |
| F05-S03 | Report Generation | Nudge output — WhatsApp PNG | Single page, WhatsApp safe zone, header=client/date, footer=trainer contact | [S→T] Phase 4 — System generates PNG. Trainer reviews and shares on WhatsApp | P1 | Now |
| F05-S04 | Report Generation | Page layout engine | Places sections in grid (1x1/1x2/2x1/2x2) — code handles placement, no Canva dependency | [S] Phase 3 — Fully automated. Grid config set by admin in F05-S01 | P1 | Now |
| F05-S05 | Report Generation | Full report — PDF | Cover + content pages + closing, Canva template injected, PDF exported | [S→T] Phase 4 — System generates PDF. Trainer reviews and shares | P2 | Now |
| F05-S06 | Report Generation | Gender-aware image selection | Correct asset pulled from library at render based on client gender + component | [S] Phase 3 — Fully automated lookup. Failure here silently breaks section — needs error handling | P2 | Now |
| F05-S07 | Report Generation | Report log | Every generated report stored as Report entity — client, date range, type, components, timestamp | [S] Phase 4 — System logs automatically. Admin reviews history | P2 | Now |
| F05-S08 | Report Generation | Assessment report sections | Ankle, Apley and postural assessments — observation text + table heatmap + corrective exercise list | [T] Phase 3 — Trainer selects assessment component in report config UI | P2 | Now |
| F05-S09 | Report Generation | Scheduled delivery | Auto-generates on cadence, notifies admin/trainer for review before send | [S→T] Vision — System generates, trainer reviews + approves before client receives | — | Vision |
| F05-S10 | Report Generation | Hosted report link | Platform generates URL for client to view in browser | [S→T] Vision — System generates link, trainer shares directly | — | Vision |
| F05-S11 | Report Generation | Multi-client batch | Same config generated for multiple clients in one action | [T] Vision — Trainer runs monthly reports for all active clients | — | Vision |
| F06-S01 | Canva Templates | Design nudge template | Single page — header with client/date, footer with trainer contact, empty content area | [A] Phase 1 — Admin designs once. Defines WhatsApp safe zone dimensions for F05-S03 | P1 | Now |
| F06-S02 | Canva Templates | Design cover template | Full report cover — client name, date range, Insight branding | [A] Phase 1 — Admin designs once | P2 | Now |
| F06-S03 | Canva Templates | Design content template | Content page — header, footer, empty content area for code-placed sections | [A] Phase 1 — Admin designs once. Slot positions must match grid_config options | P2 | Now |
| F06-S04 | Canva Templates | Design closing template | Closing page — thank you, trainer contact details | [A] Phase 1 — Admin designs once | P2 | Now |
| F06-S05 | Canva Templates | Multi-template support | Trainer selects from multiple Canva templates per report type | [T] Vision — Trainer customises branding per client tier | — | Vision |
