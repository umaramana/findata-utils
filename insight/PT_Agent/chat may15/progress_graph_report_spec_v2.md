# Progress Graph Report — Feature Spec
**Insight Fitness Data Services | Section Report v0.2**

---

## Structure of this spec

Each section is split into **Now** (horizontal slice for your friend's setup) and **Vision** (where this goes as the platform scales). Build only Now. Vision is directional — it shapes decisions today so we don't paint into corners.

---

## 1. Overview

A configurable, shareable single-section report the trainer generates on demand. Replaces the quarterly full-report cadence with lightweight nudge reports sent daily or weekly around specific metrics.

The report shell comes from a **Canva template** (brand, layout, typography). Dynamic content — charts, summary numbers, client metadata — is injected programmatically at generation time.

Data source: **Google Sheets**. How data gets into the sheet varies by trainer working style; that is a per-trainer config, not this spec's concern.

---

## 2. Scope

### Now
- Metrics: Weight, Body Fat %, Muscle Mass %
- Single-client view
- Trainer-configured: metric selection, date range, graph type
- Data source: Google Sheets (one named tab per client)
- Output: HTML (self-contained) + PDF export
- Template: Canva-designed shell with defined content slots

### Not now
- Multi-client comparison
- Goal / target line overlays
- Automated scheduling or push delivery
- Client-facing interface
- Multiple data input methods simultaneously

---

## 3. Data Model

One Google Sheet, one tab per client. Each row = one check-in.

| Field | Type | Notes |
|---|---|---|
| `date` | DATE | DD/MM/YYYY |
| `client_name` | STRING | Must match client roster |
| `weight_kg` | FLOAT | Null if not logged |
| `fat_pct` | FLOAT | Null if not logged |
| `muscle_pct` | FLOAT | Null if not logged |
| `source` | STRING | "form" / "manual" / "import" — audit trail |
| `parse_confidence` | ENUM | `high` / `low` — sheet-only data quality flag, never shown in report |

`parse_confidence` is for the trainer to audit data quality in the sheet. It does not surface in the report under any circumstance.

---

## 4. Data Input — Per-Trainer Config

How data lands in the sheet is a trainer working style preference, not a platform assumption. The same platform supports all paths. Input method is set once during trainer onboarding.

| Input style | How it works | Trainer type |
|---|---|---|
| **Simple form** *(Now)* | Saved link → type values → submits to sheet | Pen-and-paper, low-tech |
| **Direct sheet edit** | Trainer edits Google Sheet manually | Spreadsheet-comfortable |
| **Chat export parse** | WhatsApp .txt → Claude API parser → sheet | Chat-based trackers |
| **App CSV import** | HealthifyMe / MyFitnessPal CSV → sheet | App-first trainers |

Note: These input styles cut across trainer experience level — a veteran can be pen-and-paper, a newer trainer might be app-first. It's a working style config, not a persona bucket.

**Current build:** Simple form only (separate utility spec).

### Vision
- Input method is a per-trainer setting, switchable at any time
- A trainer can use multiple input paths for different clients
- The sheet remains the single source of truth regardless of input path
- New input connectors (wearables, clinic software) added as integrations without changing the report layer

---

## 5. Canva Template — Content Slots

The Canva template is the branded shell. These slots receive dynamic content at generation time. The template must be designed with explicit placeholder blocks at exact positions.

| Slot | Content | Type |
|---|---|---|
| `{{client_name}}` | Client name | Text |
| `{{report_title}}` | Cadence label e.g. "3-month progress" | Text |
| `{{date_range}}` | "Feb 12 – May 12 2026" | Text |
| `{{generated_date}}` | Generation date | Text |
| `{{metric_1_label}}` | "Weight" | Text |
| `{{metric_1_value}}` | "82.4 kg" | Text |
| `{{metric_1_delta}}` | "↓ 4.2 kg" | Text |
| `{{metric_1_trend}}` | "Improving / Stable / Watch" | Text |
| *(repeat ×3 for each metric)* | | |
| `{{chart_image}}` | Rendered chart | Image — fixed pixel dimensions TBD |
| `{{trainer_name}}` | Footer attribution | Text |

Chart image slot needs fixed pixel dimensions locked before build — rendered chart must match exactly.

### Vision
- Multiple Canva templates selectable per report — "weekly nudge" (compact, single metric) vs. "quarterly review" (full layout, data table)
- Trainer can clone and customise templates for different client tiers
- White-label template support for when other trainers onboard onto the platform

---

## 6. Trainer Configuration Interface

### Now
Single config panel. Trainer sets options, hits Generate. No live preview in v1.

| Field | Control | Options |
|---|---|---|
| Client | Dropdown | From sheet |
| Metrics | Multi-checkbox | Weight, Fat %, Muscle % |
| Date range | Preset + custom | Last 7 / 30 / 90 days, Custom |
| Graph type | Visual tile picker | 7 types — see Section 7 |
| Trend line | Toggle | On / off |
| Cadence label | Text input | Free text, appears in report header |

### Vision
- Live preview updates as config changes
- Saved report presets — trainer saves "Tilak weekly" config and reuses
- Multi-client batch — same report config generated for a list of clients in one action
- Scheduled generation — auto-generates on cadence, queues for trainer review before send

---

## 7. Graph Types

Trainer picks from a visual tile picker — not a generic dropdown.

### Tier 1 — Core (always available)

**Smooth area** — single metric momentum. Filled curve, Strava/Whoop aesthetic. Best default.

**Multi-line overlay** — all three metrics on one chart. Dual axes auto-configured (weight left, % right). Best for seeing the fat/muscle relationship over time.

**Bar + rolling average** — bars per check-in, 7-day rolling average line overlaid. Shows logging consistency as much as trend. Gaps are visible — accountability baked in.

### Tier 2 — Situational

**Slope chart (before/after)** — two vertical axes, start and end date. Each metric a sloped line between them. Best for milestone share — emotionally immediate, no chart literacy needed from the client.

**Bullet chart** — current value vs. target vs. baseline. Requires target values set in config. Best for weekly nudge. *(Only shown if trainer has set targets)*

**Dot timeline** — each check-in a dot. Dot size = deviation from rolling average. Color = direction (teal = below avg / improving for weight, coral = above). Best for outlier spotting.

**Calendar heatmap** — month grid, cell intensity = metric value. Shows reporting consistency at a glance. Best metric: weight (most frequently logged).

### Tier 3 — Power

**Radar** — one axis per metric, one polygon per time period. Max 2 periods cleanly. Best for week 1 vs. week 12 comparison snapshot.

### Vision
- Trainer-saved favourites float to top of picker
- Smart suggestion — platform recommends graph type based on date range + metric count
- New chart types added as metric library expands

### Technical note
Chart.js or Recharts handles: smooth area, multi-line, bar+avg, bullet, radar.
D3 custom needed for: slope chart, dot timeline, calendar heatmap. No off-the-shelf library covers these cleanly.

---

## 8. Report Layout

### Now

**Hero** — dark (#0f2a2c) header. Client name, cadence label, date range, generated date. Metric badges.

**Summary strip** — 3 cards (one per selected metric). Current value, delta from start, trend chip (Improving / Stable / Watch).

**Chart** — full-width. Title above. Legend below chart, not inside.

**Data table** — collapsed by default, expandable. Columns: Date, Weight, Fat %, Muscle % only. Source and confidence columns stay in the sheet — not shown to client.

**Footer** — "Insight Fitness Data Services · [Trainer name] · [Date]"

### Vision
- "Weekly nudge" compact layout — single metric, mobile screenshot optimised, designed for direct WhatsApp forward
- Client-facing variant — softer language, motivational framing, no raw numbers without context
- Embedded video clip slot — short assessment clip alongside progress data

---

## 9. Chart Design Principles

Applies to all graph types:

- Colors: teal `#1A6B72` primary, coral `#D85A30` secondary, amber `#EF9F27` tertiary
- No chart border — floats on card background
- Gridlines: horizontal only, very light
- Font: DM Sans axis labels, Syne chart title
- Tooltip: dark pill on hover — exact value + date
- Responsive: chart reflows for mobile
- No 3D, no pie, no donut. Ever.

---

## 10. Output & Share

### Now
- **Export PDF** — Canva template rendered with injected content. Chart as embedded image.
- **Download HTML** — self-contained, all assets inlined. No server dependency.

### Vision
- **Hosted link** — platform generates a URL, trainer sends to client. Live report in browser. Requires backend.
- **WhatsApp-optimised image** — single-screen PNG of summary strip + chart. Direct forward without opening a PDF.
- **Scheduled delivery** — auto-generated on cadence, trainer reviews before it goes out.

---

## 11. Open Questions for Trainer

1. **Targets** — does he set weight/fat/muscle targets for clients? Yes = bullet chart unlocks. No = remove it from picker.
2. **Client roster** — how are clients named? First name, full name, nickname? Determines dropdown logic.
3. **Cadence labels** — what does he actually say to clients? Informs preset label options.
4. **Multi-metric preference** — all 3 on one chart, or 3 separate small charts stacked vertically?
5. **Canva** — does he have Canva access? Is he designing the template, or are you?

---

## 12. Build Order

1. Lock Google Sheets schema and tab structure
2. Simple check-in form (separate utility spec) — writes to sheet
3. Report config UI — HTML, trainer-facing, no live preview
4. Chart rendering — Chart.js for Tier 1+2, D3 for slope/dot/heatmap
5. Canva template — design shell, lock slot positions and chart image dimensions
6. Content injection — populate Canva slots programmatically
7. PDF + HTML export

---

## 13. Design References

- Report shell: Canva (to be designed — slots defined in Section 5)
- Design system reference: `ankle_v3.html` (color, typography, card patterns)
- Inspiration: Strava activity detail, Whoop weekly report, Apple Health trends
- Chart libraries: Chart.js (vanilla), D3 for custom types
