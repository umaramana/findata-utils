# F04-S05 — Table Heatmap (corrected to match real samples)

**Context**
**Implementation: Python (matplotlib), not D3.** Corrected 2026-06-26 — D3 was the original pick (made 2026-05-15, before this card's pytest + PNG-bytes output contract existed) on the sole basis that "D3 has a heatmap table type." No D3-specific capability (interaction, transition) is actually required here, and D3 can't satisfy the pytest unit tests or return PNG bytes directly from Python — same issue that moved the bar-chart family off Chart.js. Proportional fill bars are `Rectangle` patches per cell, same approach as `render_bar`. Renders physio_1, physio_2, physio_3, balance_open, balance_closed as tables — confirmed correct against 4 real samples. **Visual style corrected this round**: the actual default isn't discrete green/amber/red colour bands, it's a **continuous proportional bar-fill inside each cell** (darker fill = higher value, lighter = lower, within that row's own range) — same teal/maroon palette as the rest of the report, not a traffic-light scheme. Missing data shows literal **"-"** (corrected 2026-06-27, was "No data" — see below), not a blank cell.

**Balance table format — DECIDED 2026-06-27, standardize on Format A.** Full sample audit found the real reports actually split into two incompatible structures: Praveena/Uma/Thilak use two separate tables ("Balance Eyes Open" / "Balance Eyes Closed" as distinct headers, rows = dates only — **Format A**, what this card already builds); Reshma/Karthik/Ramesh use one combined table with an `Eyes` column and rows = date+eyes-state combos (**Format B**). The original "confirmed correct against 4 real samples" claim checked component naming, not actual table structure — half the original 4 samples were actually Format B. **Decision: Format A is the standard going forward, no change needed to what's already built.** Format B samples are legacy-only, not replicated. Not revisiting this.

**Missing-data text — DECIDED 2026-06-27, "-" not "No data".** This only changes the literal text shown in an individual missing cell within an otherwise-populated table (matches Dr Praveena's Cooper Test 2019 column, which shows a literal "-"). It does **not** change the full-empty-payload error-handling fallback (Technical Requirement #3) — an entirely empty table still shows a centered "No data" message; that's a different state, not modeled on any real sample. **Future:** trainer-configurable choice between "-" and "No data" per report — captured as an idea in `F05-S03_visual_theme_appearance_card.md`, not built this week.

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
  → missing cell = "-" text, no fill
```

**Build**
1. One rendering function per component, same as before. **Share font, color palette, and DPI settings with `render_bar`** (same teal/maroon palette, same rendering engine) — both chart types are matplotlib now, no reason for them to drift visually.
2. Per-row min-max scaling for the fill bar — compute across the dates actually being rendered, not a fixed global scale.
3. Direction-of-improvement lookup (higher vs lower is better per metric) still matters for any future colour-coding, but isn't needed for the proportional-fill style itself — fill intensity just reflects relative magnitude within the row, doesn't need a "good/bad" judgment to render correctly. Keep the lookup table for later use (F04-S01 exploration), just don't gate this card's correctness on it.
4. "-" renders as plain text in the cell, no fill bar, consistent with how the samples handle gaps (Dr Praveena's 2019 Cooper Test column).
5. Return an embeddable static image, same contract as the bar-family renderer's output.

**Technical requirements**
1. Unit tests — pytest: proportional fill scales correctly within a row, a row with only one date (no meaningful range — render without a fill bar, value only), missing cells show "-" text exactly
2. Regression suite — runs everything built so far
3. Error handling — empty payload renders a clear "no data" table, not a crash
4. Auth — n/a
5. PWA — n/a
6. Output versioning — n/a here

**Acceptance criteria**
1. Cell fill intensity is proportional within its row's own range, not an absolute or baseline-relative scale
2. Missing data shows literal "-" text, not a blank or coloured cell
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

---

**Known issues from smoke-test review (2026-06-27) — confirm before F05-S04 starts consuming these outputs**

1. **Single-metric + single-date cell renders at full colour saturation** (Cooper Test, Flexibility smoke tests) — there's no range to normalize against, so it defaults to max-intensity fill. Cosmetic-only, not a correctness bug, still open — not addressed in this round's decisions.
2. **DECIDED (2026-06-27): missing-cell text is "-", not "No data"** — see Context section above. No smoke-test image yet demonstrates this case visually (only the full-table empty-fallback was tested) — recommend one targeted render of a partial "-" cell before sign-off, now using the corrected text.
3. **DECIDED (2026-06-27): balance table format standardized to Format A** — see Context section above. No further action, what's already built matches the decision.

---

**As-built — HTML table renderer specifically (session 2026-07-01, post-rollback)**

Note: the report actually uses `render_table_html()` (a real HTML `<table>`), not `render_table_heatmap()` (the matplotlib PNG version this card otherwise describes) — `report_pdf.py` imports `render_table_html`. The matplotlib version still exists and is tested, but isn't what's in the rendered PDF. The items below are about the HTML path specifically.

- **Column width now fits the data, not the header text.** HTML tables default to `table-layout:auto`, which stretches every column to fit its *widest* cell — including long header labels like "1. Modified Pushups", even though the actual data values are 2-3 digit numbers. Fixed via `.hm-header { max-width: 70px; white-space: normal; word-wrap: break-word }` — headers now wrap onto multiple lines instead of forcing the column (and the whole table) wider.
- **UOM badge position — two real bugs, not one.** (1) `overflow-x: auto` without an explicit `overflow-y: visible` makes browsers silently force `overflow-y:auto` too, clipping anything positioned above the box. (2) Even after fixing that, the badge still didn't render — **Chromium's *print* rendering (Puppeteer's `page.pdf()`) drops content that overflows *upward* past its container via negative offset, even with `overflow-y:visible` set — a different, print-specific quirk from normal screen rendering.** Final fix: give the container real `padding-top` space and position the badge inside that allocated space (`top: 0`), never a negative offset escaping the box. A `qc_report.py` check (`heatmap_unit_badge_presence_check`) and a template-level pytest test (`test_heatmap_unit_note_badge_renders`) both guard this now — the pytest one alone would NOT have caught the print-specific clipping (it doesn't invoke Puppeteer), only the QC check running against a real generated PDF does.
- **Table centering vs. badge alignment is a genuine structural conflict, not a one-line fix.** Centering the table within its full row needs a `flex:1` container; pinning the badge to the table's own (possibly narrower) right edge needs a shrink-wrapped container. Resolved with two nested divs (`.heatmap-block` flex:1 + centers, `.heatmap-table-wrapper` shrink-wraps + holds the badge) — this is the minimum, not three as first built.
- **Per-metric icon row, new (2026-07-01)**: `section["metric_icons"]` (list, built in `report_pdf.py`'s bucket-3 loop) renders as `.heatmap-icon-row` above the table — one consistent layout for every bucket-3 section rather than replicating the samples' inconsistent per-section flanking/above mix. Metrics with no registered asset are simply skipped (not blanked) — see `F05-S06_gender_image_card.md` for the asset-lookup side of this.

**Patch instructions (ready for Claude Code) — 2026-06-28**

**Decided, apply directly.**

```python
# Before:
cell_text = "No data" if value is None else _fmt_value(value)

# After:
cell_text = "-" if value is None else _fmt_value(value)
```

**Critical — do not touch the full-table empty-payload fallback.** That's a different state (Technical Requirement #3, an entirely empty table renders a centered "No data" message) and must stay "No data". If the current code uses the same string constant or variable for both the per-cell text and the full-table fallback, **split them into two distinct constants first** (e.g. `MISSING_CELL_TEXT = "-"` vs `EMPTY_TABLE_FALLBACK_TEXT = "No data"`) before changing either — a careless single find-replace across the file risks breaking the wrong one.

**Test updates required:** pytest assertions checking for `"No data"` in a per-cell context (a populated table with one missing value) need updating to `"-"`. The separate test for a fully empty payload should be unchanged — still expects `"No data"`.
