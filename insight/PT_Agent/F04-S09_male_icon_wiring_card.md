# F04-S09 -- Male icon wiring + registration -- NEW 2026-07-02

**Status: assets exist locally (Uma's folder), not registered anywhere the renderer can find them. Untested.**

**Verified: 2026-07-03 -- `git log -p -- report_pdf.py` + `python -m pytest tests/test_report_pdf.py -k asset_library` -> CONTRADICTS status line above. All 10 male icon entries (weight_kg, waist_hip_ratio, pushups, squats, crunches, plank, right_side_plank, left_side_plank, flexibility, cooper_test) have existed in `_local_asset_library()` since the file's first commit (75cefe4, 2026-06-30) -- registered alongside female, not added later. `assets/male/` has all referenced files on disk. `test_local_asset_library_has_no_silently_dropped_entries` asserts exactly 25 entries resolve (10 male + 10 female + 5 common) and is green right now. Registration + silent-drop test coverage (scope steps 1-2) are already done. Only step 3 -- a real end-to-end PDF render for a male client -- is genuinely outstanding, and it's already gated on F04-S08 per this card's own Dependencies line.**

**Step 3 completed 2026-07-04, end-to-end against live sheet data (`generate_report.py`, F04-S08). Male icon renders correctly for `champion_mr_abhay_singh` (weight_kg, the only component with live data this week); female re-run on `dr_hemalatha` confirmed no regression. Both visually verified by rendering the PDF to PNG and cropping the chart region -- not just checking image count.**

**Real bug found and fixed during this verification, NOT a male-icon-specific issue -- flagging because it briefly looked like this card's bug:** the live `asset_library` sheet tab is NOT empty (contradicts `insight_context_handoff_v2.md`'s "no live asset_library sheet tab exists yet" -- that line is now stale, someone populated it since 2026-07-02). Its 9 rows use raw relative filenames (e.g. `male/weight_male.png`) instead of base64 data URIs, and several don't match real files on disk at all (`common/bmi.jpg` vs actual `bmi_common100X200px.png` -- wrong name AND wrong extension). `generate_report.py`'s original `load_asset_library(spreadsheet) or None` fallback only triggers on an empty/unreadable tab, so this non-empty-but-broken data silently passed through and the icon didn't render -- looked exactly like a male-icon wiring bug until traced. Fixed by having `generate_report.py` never read the live asset_library/metric_asset_groups tabs this week (always pass `None`, forcing `_local_asset_library()`) -- matches F04-S08's card intent ("assets stay local this week, deliberately") more literally than the original opportunistic-if-present logic. **The live tab's broken content is real and unresolved -- flag to Uma/Arun before F04-S10 (live-sheet asset reading) starts, since that card will need to either fix this data or add validation, not just wire the loader in.**

**Context**
Female adult icons were wired and tested 2026-07-01 (`image_mapping_and_sheet_integration_card.md`). Male assets exist as files but the resolution path -- `_local_asset_library()` in `report_pdf.py` -- has never had male entries added or tested. Two of this week's three clients (`champion_mr_abhay_singh`, `master_jay`) are male. This is a registration + test gap, not a sourcing gap.

The last time gender-keyed assets were wired (female), two silent-failure bugs were found: lookup-key mismatches (`situps` vs real metric_id `crunches`) and filename typos (`women-situps.jpg` should have been `women-squats.jpg`). Both failed silently -- no error, icon just didn't render. Expect the same class of bug on the male side; do not assume "file exists" means "wired correctly."

**Input data**
```
gender_image.get_metric_visuals(metric_id, gender, asset_library, metric_asset_groups)
  gender: must be "male" for these entries -- confirm the exact string
  used elsewhere (grep for "female" in report_pdf.py's local library --
  match casing/format exactly, do not introduce "M"/"Male"/"m" variants)

Client-type-based components needing male variants (per
image_mapping_and_sheet_integration_card.md, tier 1):
  Body Weight, Waist-to-Hip Ratio, Physio 1, Physio 2, Physio 3
Common components (no gender variant needed): BP, Pulse, Body
Composition, Balance (open/closed) -- do not add male entries for these.
```

**Scope**
1. Add male entries to `_local_asset_library()` in `report_pdf.py` for the 5 client-type-based components, pointing at Uma's local asset files (get exact paths from Uma before starting -- do not guess filenames).
2. Reuse the existing `test_local_asset_library_has_no_silently_dropped_entries` pattern -- extend it to assert male entries load with the same count as female, catching the same silent-drop failure mode before it ships.
3. Manually verify against real client data: generate a report for `champion_mr_abhay_singh` (male) and confirm icons actually render, not just that the dict lookup returns non-null.

**Test data**
`champion_mr_abhay_singh`, `master_jay` -- both real, both male, both this week's actual clients. No synthetic test client needed; use the real ones as the test.

**Acceptance criteria**
Male-client report shows icons for all 5 client-type-based components (or explicitly, provably absent ones are logged, not silently blank). Female-client rendering unaffected (re-run `dr_hemalatha` after this change, confirm no regression).

**No wireframe** -- asset registration + test, no UI change.

**Dependencies**: none technically, but only testable end-to-end once F04-S08 (orchestration script) exists -- otherwise this is unit-tested against the local library only, not proven in a real generated PDF.

**Out of scope**: child assets (no child clients this pilot), live-sheet asset_library reading (still using local fallback deliberately -- separate, larger card, not this week).

---

**Follow-on bug found and fixed 2026-07-04, same session, user-reported from a live-generated report (`uma`, 2 real dates):** icon rendering "worked" (visible, right gender) but had two real, compounding positioning defects — both now fixed:

1. **Icon rendered below the x-axis at N=1, above it at N=2.** Root cause: the icon was an HTML/CSS overlay (`position:absolute; top:50%` on the whole chart-cell box), never actually anchored to the chart's axis — its "correct" look at N=2 was a coincidence of F04-S07's *original* height_in bug giving every N the same box proportions. Fixed by moving the icon into the SVG itself, drawn via matplotlib in axes-fraction coordinates (`ax.transAxes`) — same mechanism already used for title/value-labels/unit-note, so it stays pinned to the actual plot rectangle regardless of N. See `chart_renderer._draw_icon_inset`.
2. **Icon rendered ~1.4x too large, reaching up far enough to overlap the unit note.** Root cause: the icon's `zoom` factor was computed using `ax.figure.dpi` (100 at figure-creation time), but matplotlib's `OffsetImage` actually scales against a FIXED 72 points/inch regardless of the figure's dpi setting — a real, non-obvious matplotlib quirk, not a design choice. Fixed by using the literal constant `72` in the zoom formula. Empirically verified with a synthetic known-size test icon before and after (measured rendered height matched the intended 22px-equivalent to within rounding only after the fix).

**Also moved as part of the same fix:** `horizontal_single`'s title and unit-note ("In: kg") were moved from inside-axes text to a fixed-inch "chrome band" above the axes (figure-level `fig.text()`, not `ax.text()`), per user request, so they structurally can't share vertical space with the icon at all, regardless of N. This interacted with F04-S07's height formula — see that card's "Round 2" section for the full fix (reserved-row-count model) and the regression-suite gap it exposed. **This card's icon fix and F04-S07's height-formula fix are two halves of one interconnected change — read both cards together if touching `horizontal_single` again.**

**Scope explicitly limited to `horizontal_single`** (Body Weight, BMI, Waist-to-Hip Ratio) — confirmed via direct code read that `stacked_pair` (Blood Pressure, Body Composition), `circular_gauge` (Pulse), `grouped_multi` (Body Measurements), and `table_heatmap.py`'s heatmaps all have their own independent title/unit-note code, untouched by this fix. Verified no regression by rendering the full `smoke_report_pdf.py` fixture (covers every chart type) after the change.

**New QC coverage:** `qc_report.bar_thickness_consistency_check` (see F04-S07 card) guards the bar-thickness half of this bug going forward. The icon/unit-note overlap half has no PDF-level QC check — see F04-S07 card's note on the text-extraction gap that blocked one from being built reliably; the geometric invariant is instead covered by `TestIconInset.test_icon_anchored_in_axes_fraction_for_n1_and_n2` in `tests/test_chart_renderer.py`.
