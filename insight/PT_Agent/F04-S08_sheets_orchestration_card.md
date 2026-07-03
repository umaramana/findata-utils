# F04-S08 -- Live-sheet orchestration script -- NEW 2026-07-02

**Status: does not exist. Nothing in the repo authenticates, pulls live sheet data, and calls the report pipeline.**

**Context**
`generate_full_report()` (report_pdf.py) takes `all_readings` / `client_profile` / `asset_library` / `metric_asset_groups` as pre-fetched parameters. Every real run so far (`smoke_report_pdf.py`) hardcodes these as fixture data. `sheets_auth.get_credentials()` exists and works (used elsewhere), and `gender_image.load_asset_library()` / `load_metric_asset_groups()` exist and read the right tab shape -- but nothing calls them. There is no script that goes: authenticate -> open `insight_pilot` -> read `readings`/`client_info`/`asset_library`/`metric_asset_groups` -> call `generate_full_report()`.

This is the actual blocker for generating real reports for `champion_mr_abhay_singh`, `master_jay`, `dr_hemalatha` -- not a code-quality gap, a missing entry point.

**Input data**
```
sheets_auth.get_credentials() -> Credentials (existing, working)
gspread.authorize(creds).open("insight_pilot") -> Spreadsheet (existing pattern, used elsewhere in setup_insight_pilot.py -- reuse, don't reinvent)

Need to build:
  fetch_client_readings(spreadsheet, client_id) -> list[dict]
    reads `readings` tab, filters to client_id, returns same shape
    smoke_report_pdf.py's `_ROWS` fixture uses: {client_id, date, component, metric, value}
  fetch_client_profile(spreadsheet, client_id) -> dict
    reads `client_info` tab, returns {gender, dob, client_type}
  gender_image.load_asset_library(spreadsheet) -- already exists, call it
  gender_image.load_metric_asset_groups(spreadsheet) -- already exists, call it
```

**Scope**
1. New script, e.g. `generate_report.py` in `insight_core/`. CLI: `python generate_report.py <client_id> <date_from> <date_to> [--components ...]`.
2. Auth via `sheets_auth.get_credentials()`, open `insight_pilot`.
3. Fetch readings + client_profile + asset_library + metric_asset_groups from live sheet -- not the local `_local_asset_library()` fallback. Pass all four into `generate_full_report()`.
4. Fallback: if `load_asset_library()` returns empty (sheet unreachable, tab missing), fall back to `_local_asset_library()` and log a warning -- do not crash. Matches existing "must not block on incomplete assets" principle from F05-S06.
5. Output: PDF to `insight_core/output/` (or wherever `report_pdf.py`'s `_versioned_path` already points), print the path.

**Test data**
Run against real `champion_mr_abhay_singh` data once F04-S07 (date-count fix) lands -- this is the actual end-to-end test, not a separate fixture. No new mock data needed.

**Acceptance criteria**
`python generate_report.py champion_mr_abhay_singh 2026-06-01 2026-06-01` produces a real PDF using live sheet data, with real icons if assets resolve, iconless sections if they don't -- no crash either way.

**No wireframe** -- backend script, no UI.

**Dependencies**: F04-S07 (date-count fix) should land first -- this script's first real test is single-date, and there's no point debugging orchestration against a renderer that's already broken at N=1.

**Out of scope**: male/child icon content correctness (separate card), nudge, Apps Script side (already writes to Sheets correctly, untouched by this card).
