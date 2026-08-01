# Generating a report

`generate_report.py` pulls a client's real readings and profile from the live `insight_pilot` Google Sheet and produces a full PDF report.

## Prerequisites (one-time / per-machine)

- Python environment with this folder's dependencies installed (`pip install -r requirements.txt`)
- Node + the Puppeteer install this script depends on (borrowed from the sibling `insight_receiptgenerator` project's `node_modules` — see `render_report.js`)
- A Google OAuth token authorized as `umanatraj@gmail.com`, stored at `token.json` in this folder

If `token.json` is missing or its refresh token has expired/been revoked, delete it and re-run any script that calls `sheets_auth.get_credentials()` — this opens a browser for a fresh sign-in:

```
Remove-Item token.json
python -c "import sheets_auth; sheets_auth.get_credentials(); print('Auth OK')"
```

## Running it

```
cd C:\Users\UN\fractals\VibeCoding\ClaudeCode\insight\insight_core
python generate_report.py <client_id> <date_from> <date_to>
```

Example — a client with a single assessment date:
```
python generate_report.py champion_mr_abhay_singh 2026-06-22 2026-06-22
```

Example — a client with multiple dates (uses all readings in that range):
```
python generate_report.py uma 2025-06-26 2026-06-25
```

On success it prints the output PDF path (written to `reports/` by default).

## Optional flags

| Flag | Default | Purpose |
|---|---|---|
| `--components` | all 8 (`body_measurements body_vitals physio_1 physio_2 physio_3 balance_open balance_closed strength`) | Space-separated list to generate only specific sections, e.g. `--components body_measurements body_vitals` |
| `--grid-density` | `3x2` | Bucket 2 (Body Vitals/Strength) grid layout — one of `1x1`, `1x2`, `2x1`, `2x2`, `3x2` |
| `--output-dir` | `insight_core/reports/` | Where the PDF is written |

## Notes

- `client_id`/`date_from`/`date_to` must match real values in the `readings`/`client_info` sheet tabs — there's no client picker, this is a CLI script.
- Assets (gender icons/images) are pulled from the LOCAL asset library (`report_pdf._local_asset_library()`) this week, not the live `asset_library` sheet tab — that tab exists but currently has broken entries (see `PT_Agent/F04-S09_male_icon_wiring_card.md`).
- A trainer-facing "Download Report" button (Apps Script -> Cloud Run bridge) is now **live** (deployed 2026-07-06, `PT_Agent/F05-S07_report_generation_trigger_card.md`, code in `report_service/`). Arun/Uma can generate a real PDF from the Sheet's web app without this CLI or a dev machine — see `report_service/DEPLOY.md` for the deployed architecture (Cloud Run + OAuth-delegated Sheets/Drive access, not a service account, since service accounts have no Drive storage quota). This CLI remains useful for local debugging/one-off runs, but is no longer the only path.
- **Nudge PNG** (2026-07-25, design handoff `2c`; component-selectable since F06-S02, 2026-07-31): the Report Config tab's "Nudge PNG" output type has a real generation path — `nudge_png.py` via the same Cloud Run service's `/generate-nudge` route. Nudge is **single-select across all 8 components**, not fixed to Body Vitals — the card always keeps the same visual shape (one big headline stat + up to 3 stat boxes, or Body Measurements' waist/hips bar list), but the metric(s) behind it depend on which component is picked (`NUDGE_METRIC_CONFIG` in `report_query.py`). `--grid-density` still doesn't apply (Nudge is one fixed-layout card, not a multi-section report). Local test against live Sheet data (same prerequisites as above, no Cloud Run deploy needed):
  ```
  python generate_nudge.py <client_id> <date_to> [--component-id <component>]
  # e.g. (defaults to body_vitals if --component-id omitted)
  python generate_nudge.py champion_mr_abhay_singh 2026-06-22 --component-id physio_2
  ```
  Prints the output PNG path (written to `reports/` by default) — open it to check the render.
