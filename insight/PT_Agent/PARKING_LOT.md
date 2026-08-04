# Insight Core — Parking Lot

Deferred items surfaced during coding sessions, not yet scoped into a full card. See also `S3.3_whatsapp_nudge_card.md` for the original nudge concept.

## Report Config redesign — built, not yet pushed to live Apps Script (opened 2026-07-25, built 2026-07-31)

What looked like a small "add date chips to the nudge picker" fix turned out to be a structural mismatch: Full Report needs a date range, Nudge needs a single date, and both currently shared one date-picker control. Scoped into a problem stub, sent to Claude chat as a design pass (per the chat-designs/code-builds protocol) — chat's handoff came back same-day with all four problems answered, descoped back down (user didn't want the bundled visual report redesigns), then built same session: Date card swap, Components card-grid (single-select Nudge / multi-select Full Report), and Nudge extended to render any of the 7 components. All code + tests done (218 passed); still needs a manual push to the live Apps Script project + Cloud Run redeploy before Arun sees it. Details: [F06-S02_report_config_redesign_card.md](F06-S02_report_config_redesign_card.md).

## Nudge body_vitals scope — RESOLVED 2026-08-04

`NUDGE_METRIC_CONFIG["body_vitals"]["boxes"]` in `report_query.py` changed from a fixed 2-item list to a 5-item priority-ordered candidate pool (`fat_pct`, `muscle_pct`, `bp` combined pair, `bpm`, `height_cm`); the fill loop takes the first 2 slots' worth of whatever actually has data. Deployed to live Cloud Run (`report-service-00014-zvh`) and smoke-tested end-to-end. Details in `project_insight_core.md` Session 12.

## Check-In / Full Assessment tab naming — RESOLVED 2026-08-04

Renamed via a short naming discussion (verb-parallel, avoided clash with the existing "Generate" button): **Log / Assess / Share** (was Check-In / Full Assessment / Report Config). Changed in `apps_script/index.html`'s 3 `tab-btn` labels only — internal ids/comments left as-is. **Not yet pushed to live Apps Script** — needs the usual manual copy-paste + redeploy in the Apps Script editor.

## Nudge PNG — start-of-next-session action

User has not yet visually eyeballed the generated nudge PNG from the successful end-to-end Cloud Run test (2026-07-25) — output landed at a Drive link during that session. **Bring this up at the start of the next session** (per user's explicit request) before doing any further nudge work.

## Also confirmed working this session (for context, not open items)

- Cloud Run `report-service` switched from `--no-allow-unauthenticated` to `--allow-unauthenticated` (see `report_service/DEPLOY.md`) — the service had zero IAM invoker bindings, which likely means the pre-existing Full Report "Download Report" button never actually completed successfully before. Worth a real end-to-end Full Report test next session too, now that the IAM block is gone.
- OAuth refresh token expiry (`invalid_grant`) traced to the GCP OAuth consent screen likely still being in "Testing" mode (7-day auto-expiry) — re-minting fixed it this session, but will recur weekly unless the consent screen is published to "Production". Flagged in `DEPLOY.md`, not yet acted on.
