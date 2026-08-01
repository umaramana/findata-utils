# Insight Core — Parking Lot

Deferred items surfaced during coding sessions, not yet scoped into a full card. See also `S3.3_whatsapp_nudge_card.md` for the original nudge concept.

## Report Config redesign — built, not yet pushed to live Apps Script (opened 2026-07-25, built 2026-07-31)

What looked like a small "add date chips to the nudge picker" fix turned out to be a structural mismatch: Full Report needs a date range, Nudge needs a single date, and both currently shared one date-picker control. Scoped into a problem stub, sent to Claude chat as a design pass (per the chat-designs/code-builds protocol) — chat's handoff came back same-day with all four problems answered, descoped back down (user didn't want the bundled visual report redesigns), then built same session: Date card swap, Components card-grid (single-select Nudge / multi-select Full Report), and Nudge extended to render any of the 7 components. All code + tests done (218 passed); still needs a manual push to the live Apps Script project + Cloud Run redeploy before Arun sees it. Details: [F06-S02_report_config_redesign_card.md](F06-S02_report_config_redesign_card.md).

## Nudge body_vitals scope — only shows Check-In's 3 metrics, not the full 7 (opened 2026-07-31)

`body_vitals` has 7 possible metrics in `METRIC_MAP` (`Code.gs`): `weight_kg`, `fat_pct`, `muscle_pct`, `bp_systol`, `bp_diastol`, `bpm`, `height_cm`. The Check-In tab only ever writes the first 3 (`submitReadings()` in `Code.gs` hardcodes `weight_kg`/`fat_pct`/`muscle_pct`); Full Assessment writes all 7. The Nudge card's `NUDGE_METRIC_CONFIG["body_vitals"]` in `report_query.py` only surfaces those same 3 (headline: weight_kg, boxes: fat_pct/muscle_pct) — so a client with BP/heart rate/height logged via Full Assessment never sees them on their Nudge, even though the data exists. Needs a design decision before touching code: does Nudge's fixed 3-stat-box layout expand to fit more, rotate/prioritize which 3 show, or is "Check-In's 3" the intentional scope for a nudge (quick glance) vs. Full Report (everything)? Don't guess at this — bring it back for discussion first.

## Check-In / Full Assessment tab naming (opened 2026-07-31)

"Full Assessment" reads oddly now that Check-In and Full Assessment both write to some overlapping components (see body_vitals item above) — "Full" no longer clearly distinguishes it. User wants better names for the two tabs. No proposal yet — needs a naming discussion, not a code change.

## Nudge PNG — start-of-next-session action

User has not yet visually eyeballed the generated nudge PNG from the successful end-to-end Cloud Run test (2026-07-25) — output landed at a Drive link during that session. **Bring this up at the start of the next session** (per user's explicit request) before doing any further nudge work.

## Also confirmed working this session (for context, not open items)

- Cloud Run `report-service` switched from `--no-allow-unauthenticated` to `--allow-unauthenticated` (see `report_service/DEPLOY.md`) — the service had zero IAM invoker bindings, which likely means the pre-existing Full Report "Download Report" button never actually completed successfully before. Worth a real end-to-end Full Report test next session too, now that the IAM block is gone.
- OAuth refresh token expiry (`invalid_grant`) traced to the GCP OAuth consent screen likely still being in "Testing" mode (7-day auto-expiry) — re-minting fixed it this session, but will recur weekly unless the consent screen is published to "Production". Flagged in `DEPLOY.md`, not yet acted on.
