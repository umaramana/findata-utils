# F04-S05 — Table Heatmap (corrected to match real samples)

**Context**
**Implementation: Python (matplotlib), not D3.** Corrected 2026-06-26 — D3 was the original pick (made 2026-05-15, before this card's pytest + PNG-bytes output contract existed) on the sole basis that "D3 has a heatmap table type." No D3-specific capability (interaction, transition) is actually required here, and D3 can't satisfy the pytest unit tests or return PNG bytes directly from Python — same issue that moved the bar-chart family off Chart.js. Proportional fill bars are `Rectangle` patches per cell, same approach as `render_bar`. Renders physio_1, physio_2, physio_3, balance_open, balance_closed as tables — confirmed correct against 4 real samples. **Visual style corrected this round**: the actual default isn't discrete green/amber/red colour bands, it's a **continuous proportional bar-fill inside each cell** (darker fill = higher value, lighter = lower, within that row's own range) — same teal/maroon palette as the rest of the report, not a traffic-light scheme. Missing data shows literal **"No data"** text, not a blank cell.

**No wireframe** — table-row visual language already established.

**Input data**

Takes F05-S02's payload, sliced to physio_1/2/3 + balance_open/closed. Rows = metrics, columns = dates (unchanged from prior draft).

```
render_table_heatmap(component_metrics_data, options)
  → row per metric, column per date
  → cell = value + a proportional fill bar behind/within the cell, scaled to
    that ROW's own min-max range (not an absolute or baseline-relative scale —
    correcting last round's baseline-relative assumption, which doesn't match
    what the samples actually show)
  → missing cell = "No data" text, no fill
```

**Build**
1. One rendering function per component, same as before. **Share font, color palette, and DPI settings with `render_bar`** (same teal/maroon palette, same rendering engine) — both chart types are matplotlib now, no reason for them to drift visually.
2. Per-row min-max scaling for the fill bar — compute across the dates actually being rendered, not a fixed global scale.
3. Direction-of-improvement lookup (higher vs lower is better per metric) still matters for any future colour-coding, but isn't needed for the proportional-fill style itself — fill intensity just reflects relative magnitude within the row, doesn't need a "good/bad" judgment to render correctly. Keep the lookup table for later use (F04-S01 exploration), just don't gate this card's correctness on it.
4. "No data" renders as plain text in the cell, no fill bar, consistent with how the samples handle gaps (Dr Praveena's 2019 Cooper Test, 2019/2020 balance "No data" cells).
5. Return an embeddable static image, same contract as the bar-family renderer's output.

**Technical requirements**
1. Unit tests — pytest: proportional fill scales correctly within a row, a row with only one date (no meaningful range — render without a fill bar, value only), missing cells show "No data" text exactly
2. Regression suite — runs everything built so far
3. Error handling — empty payload renders a clear "no data" table, not a crash
4. Auth — n/a
5. PWA — n/a
6. Output versioning — n/a here

**Acceptance criteria**
1. Cell fill intensity is proportional within its row's own range, not an absolute or baseline-relative scale
2. Missing data shows literal "No data" text, not a blank or coloured cell
3. A metric with only one date renders its value without a meaningless fill bar
4. Output format matches the bar-family renderer's embeddable image contract

**Dependencies**
F05-S02's query payload shape. Does not depend on F04-S01.

---

**As-built visual standards (session 2026-06-27)**
- **Layout**: dates as **rows**, metrics as **columns** (transposed from original spec — matches Looker samples)
- **Cell fill**: full-cell magenta fill via `Rectangle` patch (not a proportional sub-bar); cell borders removed (`edgecolor="none"`)
- **Gradient**: 8-stop brand palette `#f8bbd0 → #f06292 → #f538a0 → #ce5a92 → #ab4e5f → #bf1d6f → #ad1457 → #880e4f`; `f538a0` placed before `ce5a92` to avoid R-channel brightness spike; equal-spaced `LinearSegmentedColormap`
- **Normalization (dual-mode)**: 1 date → normalise across the row (first-assessment snapshot); 2+ dates → normalise per column (each metric vs its own history)
- **`value_format` option**: `"g"` (default) or `"hms"` (integer seconds → `"HH:MM:SS"`) — used for Physio 2 and Balance tables
- **Text colour**: luminance-based — white on dark cells, `#1a1a1a` on light cells
- **Date labels**: `"Mon YYYY"` format (same helper as bar charts)
- **Same-unit rule**: layout engine must call `render_table_heatmap` separately for each unit group — do **not** mix metrics with different units in one call
