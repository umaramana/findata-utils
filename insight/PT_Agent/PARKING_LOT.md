# Insight Core — Parking Lot

Deferred items surfaced during coding sessions, not yet scoped into a full card. See also `S3.3_whatsapp_nudge_card.md` for the original nudge concept.

## Nudge PNG — date selection UX (opened 2026-07-25)

Nudge PNG generation (design handoff `2c`, built 2026-07-25) currently defaults silently to the most recent logged reading on or before "Date To" — no picker. User feedback mid-session flagged this as wrong, but the exact ask wasn't pinned down before the session ended testing the deploy pipeline instead. Two open questions for next session:

1. **Date chips for the nudge's single date** — should the trainer explicitly pick which of the client's existing logged dates the nudge is based on (reusing the same "logged dates" chip pattern already in Check-In/Assessment/Report Config), instead of silently taking the latest? Leading option, not yet confirmed.
2. **"Checklist to select the components"** — user's exact phrase; unclear whether this meant the date-chip picker above, or an actual metric checklist (trainer checks/unchecks which of weight/fat%/muscle%/waist/hips appear on the card, mirroring Full Report's Components checklist). Needs a direct answer before building — don't assume.

## Nudge PNG — start-of-next-session action

User has not yet visually eyeballed the generated nudge PNG from the successful end-to-end Cloud Run test (2026-07-25) — output landed at a Drive link during that session. **Bring this up at the start of the next session** (per user's explicit request) before doing any further nudge work.

## Also confirmed working this session (for context, not open items)

- Cloud Run `report-service` switched from `--no-allow-unauthenticated` to `--allow-unauthenticated` (see `report_service/DEPLOY.md`) — the service had zero IAM invoker bindings, which likely means the pre-existing Full Report "Download Report" button never actually completed successfully before. Worth a real end-to-end Full Report test next session too, now that the IAM block is gone.
- OAuth refresh token expiry (`invalid_grant`) traced to the GCP OAuth consent screen likely still being in "Testing" mode (7-day auto-expiry) — re-minting fixed it this session, but will recur weekly unless the consent screen is published to "Production". Flagged in `DEPLOY.md`, not yet acted on.
