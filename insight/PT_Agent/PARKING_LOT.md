# Insight Core — Parking Lot

Deferred items surfaced during coding sessions, not yet scoped into a full card. See also `S3.3_whatsapp_nudge_card.md` for the original nudge concept.

## Report Config redesign — built, not yet pushed to live Apps Script (opened 2026-07-25, built 2026-07-31)

What looked like a small "add date chips to the nudge picker" fix turned out to be a structural mismatch: Full Report needs a date range, Nudge needs a single date, and both currently shared one date-picker control. Scoped into a problem stub, sent to Claude chat as a design pass (per the chat-designs/code-builds protocol) — chat's handoff came back same-day with all four problems answered, descoped back down (user didn't want the bundled visual report redesigns), then built same session: Date card swap, Components card-grid (single-select Nudge / multi-select Full Report), and Nudge extended to render any of the 7 components. All code + tests done (218 passed); still needs a manual push to the live Apps Script project + Cloud Run redeploy before Arun sees it. Details: [F06-S02_report_config_redesign_card.md](F06-S02_report_config_redesign_card.md).

## Nudge body_vitals scope — RESOLVED 2026-08-04

`NUDGE_METRIC_CONFIG["body_vitals"]["boxes"]` in `report_query.py` changed from a fixed 2-item list to a 5-item priority-ordered candidate pool (`fat_pct`, `muscle_pct`, `bp` combined pair, `bpm`, `height_cm`); the fill loop takes the first 2 slots' worth of whatever actually has data. Deployed to live Cloud Run (`report-service-00014-zvh`) and smoke-tested end-to-end. Details in `project_insight_core.md` Session 12.

## Check-In / Full Assessment tab naming — RESOLVED 2026-08-04

Renamed via a short naming discussion (verb-parallel, avoided clash with the existing "Generate" button): **Log / Assess / Share** (was Check-In / Full Assessment / Report Config). Changed in `apps_script/index.html`'s 3 `tab-btn` labels only — internal ids/comments left as-is. **Not yet pushed to live Apps Script** — needs the usual manual copy-paste + redeploy in the Apps Script editor.

## Log tab — show all 7 body vitals fields (opened 2026-08-21)

Surfaced while fixing a live Nudge bug: a comment in `report_query.py` wrongly claimed Log and Assess write disjoint metric sets — checked `index.html` and confirmed Assess's body_vitals section already has all 7 fields (Log only exposes 3 of the same 7, not a different set). User wants Log to show all 7 fields too, so it can capture "any of the body vitals, may change per client at any point" without new config storage. Not started. Details: [F06-S03_log_tab_all_vitals_card.md](F06-S03_log_tab_all_vitals_card.md).

## grip_strength missing from live component_master — blocks Nudge picker for tracked clients (opened 2026-08-30)

F06-S04's tracked-client `grip_strength` component (Part A) works end-to-end on the backend (Nudge payload, template, Cloud Run route all built and tested) and is enterable via the Assess tab (client-side `SECTIONS` array, no live-sheet dependency). But the Share tab's Nudge component picker is entirely driven by `Code.gs`'s `getComponentsWithCounts()`, which reads the live `component_master` Sheet tab row-by-row — `grip_strength` has no row there, so it cannot currently be selected as a Nudge component at all, even though a trainer can log readings for it. **Action needed**: add a `grip_strength` row to the live `insight_pilot` → `component_master` tab (component_id, display_name — mirror the existing 8 active rows' shape) before this is usable end-to-end for tracked clients. Not touched this session since it's live-sheet data, not code. Walk-In (Part B) is unaffected — it doesn't go through this picker at all.

## Nudge PNG — start-of-next-session action

User has not yet visually eyeballed the generated nudge PNG from the successful end-to-end Cloud Run test (2026-07-25) — output landed at a Drive link during that session. **Bring this up at the start of the next session** (per user's explicit request) before doing any further nudge work.

## Also confirmed working this session (for context, not open items)

- Cloud Run `report-service` switched from `--no-allow-unauthenticated` to `--allow-unauthenticated` (see `report_service/DEPLOY.md`) — the service had zero IAM invoker bindings, which likely means the pre-existing Full Report "Download Report" button never actually completed successfully before. Worth a real end-to-end Full Report test next session too, now that the IAM block is gone.
- OAuth refresh token expiry (`invalid_grant`) traced to the GCP OAuth consent screen likely still being in "Testing" mode (7-day auto-expiry) — re-minting fixed it this session, but will recur weekly unless the consent screen is published to "Production". Flagged in `DEPLOY.md`, not yet acted on.

## Gym logos live in the accessing user's Drive — single-trainer assumption (opened 2026-09-24)

The Apps Script web app is deployed **"Execute as: User accessing the web app"**, so `DriveApp` acts as whoever opens it, not as the script owner. Gym logos are therefore created in — and readable only from — that person's own Drive: the `Gym Logos` folder is created per-user, and `_gymLogoDataUri()`'s `DriveApp.getFileById()` throws for anyone else, caught and degraded to `""`, so the card silently falls back to the house footer. The gym dropdown still shows the gym as having a logo, because `has_logo` is read from the `gyms` sheet, not from Drive.

**Accepted as-is 2026-09-24 — only Arun runs gym challenges**, so one Drive owns every logo and everything works. This becomes a real bug the day a second person adds or uses a gym logo.

**Fix when needed** (~15 lines in `Code.gs`, one Apps Script paste, no Cloud Run redeploy): stop putting logos in whoever's personal Drive and put them in the same shared folder the reports already use. "The folder next to `insight_pilot`" means exactly that — the `insight_pilot` spreadsheet lives in some Drive folder, and `report_service/drive_upload.py` already locates it (`find_sheet_parent_folder_id`) and creates sibling folders there ("Client Reports", "Walk-In Nudges"). Anyone with access to the sheet has access to that folder, so a logo written there is readable by everyone, regardless of who uploaded it. `_getGymLogoFolder()` currently does `DriveApp.getFoldersByName("Gym Logos")` at the root of the acting user's Drive; it would instead walk from the spreadsheet's own file to its parent and create/find `Gym Logos` inside that. Optionally also `share_with_email`-style explicit sharing, mirroring `drive_upload.share_with_email`.

## Local `token.json` expired again — `invalid_grant` (opened 2026-09-24, recurring)

Local CLI scripts (`generate_nudge.py`, `generate_report.py`, anything calling `sheets_auth.get_credentials()`) fail with `google.auth.exceptions.RefreshError: invalid_grant: Bad Request`. **Live Cloud Run is unaffected** — it uses its own token from Secret Manager, confirmed working during the 2026-09-24 deploy smoke test.

Fix needs the user at a browser: `python report_service/mint_oauth_token.py` (or delete `token.json` and re-run any script that authenticates). This is the third recurrence. The durable fix remains publishing the GCP OAuth consent screen from "Testing" to "Production" — "Testing" auto-expires refresh tokens after 7 days of inactivity. Flagged in `DEPLOY.md` since 2026-08-04, still not acted on.

## F06-S04 amendment — built and deployed but uncommitted in git (opened 2026-09-24)

The 2026-09-24 work (new 1024×1536 grip Nudge card, gym registry, nudge/full-report whitelist split) is **live** — Apps Script pasted by the user, Cloud Run revision `report-service-00021-brp` deployed and smoke-tested — but **nothing is committed**. Modified: `apps_script/Code.gs`, `apps_script/index.html`, `nudge_png.py`, `render_report.js`, `generate_report.py`, `generate_nudge.py`, `report_service/app.py`, `tests/test_nudge_png.py`, `tests/test_generate_report.py`, plus docs (`F06-S04_grip_strength_component_card.md`, `README_reports.md`, `insight_context_handoff_v2.md`). Untracked: `templates/grip_nudge_template.html`, `tests/test_report_service_validation.py`, `assets/` (fonts + grip images), `gripstrengthredesign/`. Note the older uncommitted 2026-08-30 F06-S04 work is in the same set — one commit covers both. Needs the usual file-list-and-confirm-scope pass before staging.
