# F04-S07 — Date-count generalization (N=1, N≥3) — NEW 2026-07-02

**Status: not built, blocks this week's 3 first-time-client reports.**

**Context**
Every report ever generated so far used the `smoke_report_pdf.py` fixture, which is hardcoded to N=2 dates (Jan/Jun 2026). No code path has been exercised at N=1 or N=3+. This week's real clients — `champion_mr_abhay_singh` (M), `master_jay` (M), `dr_hemalatha` (F) — are all single-date, first-time assessments. N=1 is not an edge case for this deliverable, it is the only case, and it has never run.

`qc_report.py` (~line 253) hardcodes a comment/expectation of "2 dates x 2 narrow bars" as the correct geometry for `horizontal_single`/`stacked_pair` charts. This is a symptom of the same root problem, not a separate one: date count was never treated as a variable.

**Principle -- do not deviate**
Renderer generalizes by construction. `chart_renderer.py` already solved the equivalent problem for *metric* count correctly: `_BUCKET2_WIDTH_IN` / `_BUCKET1_WIDTH_IN` are fixed container widths, and `grouped_multi` reserves a fixed metric-slot count so bar width doesn't shrink/grow with however many metrics a client happens to have (see comment block above `_BUCKET2_WIDTH_IN` in `chart_renderer.py`). Apply the identical pattern to date count. Do NOT write N=1/N=2/N=3 branches, and do not create per-N baseline PDFs in QC -- one sizing rule, one structural rule, holds for any N.

**Input data**
```
chart_renderer.render_bar(data, mode, options)
  data: list of {date: str, value: float, ...} -- length N, N in {1, 2, 3, ...}
  mode: horizontal_single | vertical_single | stacked_pair | grouped_multi
  Currently: bar/segment width implicitly depends on N via matplotlib
  auto-scaling the axis to len(data). Needs: fixed width_in divided by
  reserved slot count, same mechanism as the existing metric-count fix.

table_heatmap -- check separately: heatmap columns are per-date already
(more dates = more columns), confirm this is fine as-is and only the
bar-chart family (chart_renderer.py) has the bug.
```

**Scope**
1. `chart_renderer.py` -- `horizontal_single`, `stacked_pair`, circular gauge (Pulse): bar/segment width driven by fixed container width divided by reserved date-slot count, not auto-scaled to actual N.
2. `layout_engine.py` -- confirm no spacing constant is keyed to N=2 specifically.
3. `qc_report.py` -- delete the "2 dates x 2 narrow bars" hardcoded expectation. Replace with a rule check: `bar_count == len(dates_in_payload)`, true for any N. No per-N baseline files.

**Test data**
Reuse real values already in `smoke_report_pdf.py` -- take the Jan-2026 row set alone for N=1, add one more real value set for N=3 (source from any of the 6 real client PDFs already in the repo, don't fabricate).

Add to `tests/test_chart_renderer.py`: `test_single_date_bar_width_matches_two_date`, `test_three_date_bar_width_matches_two_date` -- assert width_in and font size are identical across N, only bar count differs.

**Acceptance criteria**
Same client rendered at N=1, N=2, N=3 -> identical bar width, identical font size, identical container proportions. Only the number of bars/segments changes.

**No wireframe** -- no new screen, rendering-logic fix only.

**Dependencies**: none -- this blocks the orchestration script and male-icon testing, not the other way around.

**Out of scope**: live-sheet orchestration (separate card, not yet written), male/child icon wiring (separate card, not yet written), nudge (not part of this deliverable).

---

**Verification update — 2026-07-03 (Claude Chat, via real run against repo code)**

Ran `generate_full_report()` at N=1 and N=3 with full production-density metric sets (not the N=2 fixture). Findings that refine this card's scope — do not treat as separate work:

1. **Confirms the diagnosis in this card.** `chart_renderer.py::_draw_stacked_pair` (Blood Pressure, Fat%/Muscle%) has no reference-slot reservation — only `grouped_multi` has `_GROUPED_MULTI_REF_SLOTS`. This is scope item 1, already correctly identified here before this bug was empirically seen. No new root cause, just confirmation.
2. **Scope item 3 needs to explicitly include Body Composition, not just BP.** QC's `EXPECTED_ORIENTATION` dict excludes Blood Pressure by comment but doesn't mention Fat%/Muscle% (Body Composition) at all — it's silently uncovered, not deliberately excluded. When rebuilding this check, both stacked_pair charts need coverage, not just BP.
3. **New, unresolved: possible QC false positive on Body Weight/WHR.** Running current QC against a real N=1 full-density report flagged Body Weight and Waist-to-Hip Ratio as "tall" (expected "wide" per `horizontal_single`). Visual inspection of the same rendered PDF shows both are correctly horizontal. Likely QC's shape-detection is picking up gridline/tick bounding boxes instead of isolating the bar rectangle — a QC measurement bug, not a `chart_renderer.py` bug. Whoever rebuilds the QC orientation check per scope item 3 should verify this isn't still happening in the new version.
4. **Bar-chart-family date-count mechanics (the core of this card) are confirmed working** at N=1 and N=3 for `body_measurements`, `body_vitals`, `physio_1`. Heatmap components (`physio_2/3`, `balance_closed`) and full-density N=3 remain untested.

**Verified by:** Claude Chat, 2026-07-03 — real `generate_full_report()` runs, output rendered to images and visually cross-checked, not asserted from reading code alone.

---

**Status: BUILT and verified — Claude Code, 2026-07-04, against live Sheets data (F04-S08's `generate_report.py`), not just fixtures.**

**Two rounds of fixes were needed, not one — the first round shipped a real regression that a live-data re-check caught, not the original test suite:**

**Round 1 — the two bugs this card originally described:**
1. `horizontal_single`'s `height_in = max(1.5, n*0.60)` floor made N=1 and N=2 render at the identical figure height despite spanning different y-axis unit ranges — inches-per-y-unit (and bar thickness) varied with N. Fixed.
2. `vertical_single`/`stacked_pair` had a fixed `width_in` but an auto-scaled x-axis — bar pixel-width shrank as N grew. Fixed via a reserved date-slot count (`_DATE_REF_SLOTS`), same mechanism as `_GROUPED_MULTI_REF_SLOTS`.
3. `qc_report.py`'s hardcoded "2 dates" comment for Blood Pressure was replaced with an N-general bar-segment-count rule (`STACKED_PAIR_METRICS`).

**Round 2 — a regression introduced by F04-S09's icon-positioning fix, caught by the user manually inspecting `uma`'s report (2 real dates), not by the test suite:**
Moving the gendered icon into the SVG (F04-S09, see that card) required moving `horizontal_single`'s title/unit-note into a fixed-inch "chrome band" above the axes. Two approaches were tried:
- **Abandoned:** grow `height_in` linearly with N and add the chrome band as one additive constant. This required separately discovering and compensating for tight_layout's OWN bottom margin (also fixed-inch, ~0.34in, but not something this session's first attempt accounted for) — every new fixed-size element sharing the figure needed its own calibration constant. Fragile, and symptomatic of the wrong shape of fix.
- **Shipped:** reserved-row-count model — same idea as `_GROUPED_MULTI_REF_SLOTS`/`_DATE_REF_SLOTS` already in this file. `_H_REF_ROWS = 2` pins the figure to one fixed size for any N ≤ 2 (blank y-range reserved via `max(n, _H_REF_ROWS)` when N is smaller), so tight_layout's margins — and every other fixed-inch element sharing that figure — come out identical between N=1 and N=2 **by construction**, not by calibration. Only N > 2 grows the figure (and does need both the top-chrome and tight-layout-bottom-margin constants added explicitly, since figure size is no longer pinned there).

**Real gap found in the regression suite itself:** the original `test_single_date_bar_width_matches_two_date`/`test_three_date_bar_width_matches_two_date` tests called `draw_bar_into` on a hand-built figure, bypassing `_single()` entirely — the only place `tight_layout()` and the (new) chrome-band `subplots_adjust()` actually run. The tests passed while the real regression shipped. Rewritten to call the actual `render_bar()` public entry point and measure real output pixels (`TestDateCountConsistency` in `tests/test_chart_renderer.py`).

**New `qc_report.py` check added:** `bar_thickness_consistency_check` — compares real bar-rect heights (filtered to `fill=True, stroke=False`, excluding axis-box outlines) across all `horizontal_single` titles on a page, flags >10% divergence. Validated to actually fire by reverting the fix via monkeypatch and re-running it against a live-generated report — not just asserted to exist. Unit-tested with synthetic fake-PDF objects in `tests/test_qc_report.py` (doesn't depend on a real PDF fixture).

**New, unresolved finding (separate rabbit hole, not fixed this session):** value labels and unit-note text drawn via `ax.text()` do not reliably extract as searchable words from the Puppeteer-printed PDF (tick labels and titles do; bar values like "82"/"80.5" and "In: kg" do not) — confirmed on both a real client report and the `smoke_report_pdf.py` fixture. Likely a Chromium SVG-text-to-outline-path conversion quirk on print, not investigated further. This is why `qc_report.py`'s `unit_of_measure_position_checks` (searches for "Measurement units"/"Units of measure" — phrasing that doesn't even match the real "In: {unit}" text) and an attempted `icon_unit_note_overlap_check` (searched for the "In:" token) were both effectively non-functional / had to be abandoned. Flag for whoever next touches text-based QC checks: verify a check's target phrase is actually extractable before trusting a "0 issues" result.
