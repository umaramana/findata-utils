# F04-S02/S03/S04 — Bar Chart Family (replaces separate line_area/multi_line/grouped_bar scope)

**Context**
Across all 4 real Looker-style reports reviewed (Reshma, Karthik, Dr Praveena, Dr Ramesh), **every body_vitals/body_measurements/strength metric renders as some form of bar — never a line or area curve.** F04-S02 (line_area) and F04-S03 (multi_line) don't match anything in the actual default style and are dropped from this week's scope — they can return later via F04-S01 if Arun wants to explore alternatives. This card becomes one bar-chart-family renderer with a mode parameter, covering everything the samples actually show.

**No wireframe** — rendering functions consumed by S4.1/F05-S05, not a UI.

**Input data — chart mode per metric, derived directly from the real samples**

```
render_bar(data, mode, options)

mode = "horizontal_single"
  → one horizontal bar per date, metric stands alone
  → used for: weight_kg, waist_hip_ratio (derived, computed not stored)

mode = "vertical_single"
  → one vertical bar per date, metric stands alone
  → used for: BMI (derived), bmr (NEW metric, see below)
  → y-axis may need a non-zero floor when the metric's natural range is narrow
    relative to its value (BMR: 1600-1800 range shown as 1.6K-1.8K, not 0-1.8K) —
    confirm with Arun whether this truncated-axis convention should carry over;
    it matches the sample but can visually exaggerate small differences

mode = "stacked_pair"
  → two metrics in one bar per date, stacked (not summed to a meaningful total —
    just two values sharing one bar for compactness)
  → used for: fat_pct + muscle_pct (NOT combined with weight_kg — separate chart)
  → used for: bp_systol + bp_diastol

mode = "grouped_multi"
  → multiple metrics as clustered/adjacent bars, repeated per date as a date-group
  → used for: body_measurements (all 9-10 metrics, one cluster per date)
  → used for: strength reps+weight pairs, when more than one date exists
  → single-date strength (e.g. one-off 1RM bench press) may render as a simple
    scorecard/table cell instead of forcing a one-bar chart — matches how the
    samples handle genuinely sparse data
```

**New metric needed**
`bmr | body_vitals | Basal Metabolic Rate | kcal | kcal | 0` — add to `metric_master`, bringing the total to **63 rows**, not 62.

**Pulse — explicit non-donut replacement needed**
Original uses a donut (single value as a ring; segmented-by-year for multi-date). Locked rule bans donut/pie. Replacement: `vertical_single` for one date, `grouped_multi`-style single-metric vertical bars per year for multi-date — consistent with how BMI/BMR already render, rather than inventing a third pattern just for pulse.

**Build**
1. One function, `render_bar(data, mode, options)`, not three separate ones — mode determines orientation/stacking/grouping, avoiding three near-duplicate implementations.
2. `horizontal_single` and `vertical_single` share most logic (just axis orientation swapped) — implement as one internal path, not two.
3. `stacked_pair`: two series, one bar, second series' base offset = first series' value. Label each segment with its own value (matches sample — 26.9 and 29.4 both shown, not just a combined total).
4. `grouped_multi`: for body_measurements, cluster width = number of dates; for strength pairs, cluster = reps+weight per date.
5. Confirm with Arun before building the truncated-axis behavior for `vertical_single` — replicate by default since it matches the sample, but flag it as overridable per-metric later if it ever produces a misleading view (e.g. a metric with naturally tiny baseline values).

**Technical requirements**
1. Unit tests — pytest: each mode independently, stacked_pair label correctness (both segments labeled, not just total), grouped_multi with 1 date (still groups correctly, doesn't break), single-date strength falling back to scorecard rendering
2. Regression suite — runs everything built so far
3. Error handling — empty/malformed payload renders a clear "no data" state, not a crash
4. Auth — n/a, pure rendering
5. PWA — n/a
6. Output versioning — n/a here

**Acceptance criteria**
1. `horizontal_single` and `vertical_single` are the same underlying function, oriented correctly per call
2. `stacked_pair` shows both segment values labeled, matching the sample's display (not a single combined number)
3. Weight and fat%/muscle% render as two separate charts — never combined into one
4. `grouped_multi` correctly clusters body_measurements across however many dates are selected
5. A single-date strength metric renders as a scorecard, not a forced one-bar chart
6. `bmr` is queryable and renders via `vertical_single` once added to metric_master

**Dependencies**
F05-S02's query payload shape. Requires `metric_master` updated with `bmr` before this card's strength testing can include it.

---

**As-built visual standards (session 2026-06-27)**
- **Date labels**: all axes/legends use `"Mon YYYY"` (`_fmt_date_label`), centered under vertical bars
- **Unit note**: all chart types show `"Measurement units: {unit}"` top-right in Bubblegum Sans 7pt muted; axis labels no longer duplicate the metric name
- **Decimal precision**: all bar value annotations use `:.1f` (always 1 dp)
- **`grouped_multi` font scaling**: label font steps down (7.5 → 6.0 → 5.0pt) based on computed bar pixel width to prevent overlap; `"Measurement units: {unit}"` auto-derived when all metrics share a unit, per-label unit suffix when mixed
- **`stacked_pair`**: legend above chart (matches `grouped_multi`); unit note auto-derived; title via `fig.suptitle`
- **Scorecard**: number in Roboto Bold (`_fp_num`), unit on its own line in Bubblegum Sans (`_fp_text`) — not concatenated into one string
- **Titles**: component name only — no chart-type suffix

---

**Known issues from smoke-test review (2026-06-27) — fix before F05-S04 starts consuming these outputs**

1. **DECIDED (2026-06-27): natural precision, not `:.1f` always.** Round to a bare integer when the value has no meaningful fraction; keep decimal places only when the underlying value actually has one (ratios, BMI, etc.). Concretely: don't hardcode `:.1f` — format so trailing `.0` never appears (e.g. round-trip through `int()` when `value == round(value)`, otherwise show natural decimal places, capped at 1dp to match the original intent for genuinely fractional values). Applies everywhere a value gets annotated: `horizontal_single`/`vertical_single` bar labels, `stacked_pair` segment labels, `grouped_multi` cluster labels, and the scorecard's big number. **Cross-check:** `render_table_heatmap`'s `"g"` format default already does this correctly (Python's general format strips trailing zeros) — no patch needed there, just confirms the bar-family fix should match that same behavior for consistency across both chart types.
2. **Scorecard repeats the metric name twice.** `bar_scorecard.png`: title "Push-ups" at top (chart title), then number, then unit ("reps"), then **"Push-ups" again** as a body label, then date. Not specified anywhere in the as-built notes above — looks like an unintentional duplication, not a deliberate design choice. Matters for F05-S04 because repeated text wastes vertical space when scorecards get tiled into a grid alongside other chart types. Recommend dropping the repeated body-label, keeping just title → number → unit → date.

Regression suite must be re-run after either fix lands, since both touch every chart type that has already passed its 73/73.

---

**⚠️ Pulse — this card's "no donut/pie" rule was reversed on 2026-07-01.** Line 44 above says pulse should render via `vertical_single`, banning donut/pie. That's no longer correct: re-checking `Reshma...pdf` and `DrPraveena_Dashboard_2019to2026.pdf` directly showed Pulse genuinely is a donut in the real samples — a solid ring with the value centered for 1 date, equal wedges (one per date, NOT proportional to value) for multi-date, with a date-color legend. `_circular_gauge` in `chart_renderer.py` implements this now. The *old* circular_gauge code (proportional-fill against an invented 30–200bpm range) was the actual bug — not the donut shape itself. Whoever locked the original "no donut" rule was working from an incomplete/wrong reference; trust the direct sample check over this card's older text.

**As-built visual standards (session 2026-07-01, post-rollback)**
- **Tick/gridline color**: "major ticks color" in feedback meant the gridlines (`grid_color`/`grid_alpha` in `chart_style.py`), not the tick marks or tick labels — spent real time on the wrong element (`tick_color`) before finding this. `grid_alpha` was a literal 0.7 transparency on an already-pale `#EBEBEB`; now `#b7b7b7` at `alpha=1.0`.
- **Unit-of-measure — one universal rule**: always `"In: {unit}"`, always top-right, inside the chart axes (not sharing a row with any legend, not varying by legend-presence). Replaces the earlier per-type "between title and graph" vs "same row as legend" split, which broke under narrow chart widths.
- **Container width unification (real bug, cost multiple rounds)**: `horizontal_single`/`vertical_single`/`stacked_pair`/`circular_gauge` all now share one fixed native width (`_BUCKET2_WIDTH_IN = 3.0`, chart_renderer.py) because they're stretched into the *same* CSS grid column — any per-type auto-width formula (even one based on date count) breaks font/bar scale consistency across chart types. `circular_gauge` was hardcoded to `figsize=(4.0,4.0)` independent of this and had to be fixed separately. `grouped_multi` (Body Measurements, a different container) has its own matching constant, `_BUCKET1_WIDTH_IN`, derived from the *same* px-per-inch ratio, not guessed independently — see `chart_renderer.py`'s "Container widths" comment block for the derivation, and the two regression tests (`TestBucket2WidthConsistency`, `TestBucket1Bucket2RatioConsistency` in test_chart_renderer.py) that now guard this.
- **`grouped_multi` also reserves a minimum slot count** (`_GROUPED_MULTI_REF_SLOTS = 9`) so bar width doesn't shrink/grow just because a given client has fewer/more recorded metrics than another client.

**Patch instructions (ready for Claude Code) — 2026-06-28**

**Patch 1 — decimal precision. Decided, apply directly.**

```python
# Before (current, at every value-annotation call site):
label = f"{value:.1f}"

# After — one shared helper, used everywhere a value gets annotated:
def _fmt_value(value):
    """Natural precision: bare integer when the value has no meaningful
    fraction, else 1 decimal place. Replaces blanket :.1f across all
    bar modes and the scorecard."""
    if value == round(value, 0):
        return f"{int(round(value))}"
    return f"{value:.1f}"

label = _fmt_value(value)
```

Call sites to update: `horizontal_single`/`vertical_single` bar labels, `stacked_pair` segment labels, `grouped_multi` cluster labels, scorecard's `_fp_num()`. Leave axis tick labels alone — this only affects explicit value annotations, not matplotlib's own tick formatting.

**Test updates required, not optional:** any existing pytest assertion checking literal strings like `"12.0"`, `"30.0"`, `"32.0"` needs updating to `"12"`, `"30"`, `"32"`. Assertions on already-fractional values (`"0.79"`, `"23.6"`) are unaffected.

**Patch 2 — scorecard duplicate label. CONFIRMED 2026-06-28 — drop it.**

```python
# Current structure (inferred from as-built notes):
#   title (top) → _fp_num(value) → _fp_text(unit) → _fp_text(metric_name) [DUPLICATE] → _fp_text(date)
# Remove the duplicate metric-name line:
#   title (top) → _fp_num(value) → _fp_text(unit) → _fp_text(date)
```

Locate the line in the scorecard rendering function that re-renders the metric name as a body label below the unit, and delete it. **Test updates:** any test asserting the scorecard contains the metric name twice, or checking an exact text-element count, needs updating to expect one fewer element. All three patches in this card are now confirmed — Claude Code can apply all of them.
