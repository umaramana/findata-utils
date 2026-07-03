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
