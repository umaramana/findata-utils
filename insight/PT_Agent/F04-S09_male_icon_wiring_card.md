# F04-S09 -- Male icon wiring + registration -- NEW 2026-07-02

**Status: assets exist locally (Uma's folder), not registered anywhere the renderer can find them. Untested.**

**Verified: 2026-07-03 -- `git log -p -- report_pdf.py` + `python -m pytest tests/test_report_pdf.py -k asset_library` -> CONTRADICTS status line above. All 10 male icon entries (weight_kg, waist_hip_ratio, pushups, squats, crunches, plank, right_side_plank, left_side_plank, flexibility, cooper_test) have existed in `_local_asset_library()` since the file's first commit (75cefe4, 2026-06-30) -- registered alongside female, not added later. `assets/male/` has all referenced files on disk. `test_local_asset_library_has_no_silently_dropped_entries` asserts exactly 25 entries resolve (10 male + 10 female + 5 common) and is green right now. Registration + silent-drop test coverage (scope steps 1-2) are already done. Only step 3 -- a real end-to-end PDF render for a male client -- is genuinely outstanding, and it's already gated on F04-S08 per this card's own Dependencies line.**

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
