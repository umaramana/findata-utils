# F05-S07 — Report Generation Trigger: App-to-Python Bridge — NEW 2026-07-06

**Status: code built 2026-07-06, NOT deployed.** `report_service/` (Flask app, Dockerfile, service-account auth, Drive upload) plus `Code.gs`'s `generateReport()` bridge and the "Download Report" button in `index.html` are written and unit-tested (9/9 new tests + 187/187 existing insight_core tests still green). What's NOT done: no Cloud Run deployment has happened, no service account has been created in GCP, no Script Properties are set — see `insight_core/report_service/DEPLOY.md` for the exact steps, all of which require Uma's GCP access and haven't been run yet. Do not mark this card done until DEPLOY.md's smoke test (step 6) has actually succeeded against the live project.

**Verified by:** Claude Chat, 2026-07-06 — confirmed directly against the repo (not assumed): `generateReportPayload()`'s dead-end at JSON preview in `index.html`, `generate_report.py`'s CLI-only/interactive-OAuth pattern, and that F04-S07/S08/S09 landed on `main` Sat 2026-07-04 (resolves the "unconfirmed push" open item from the prior session). The Cloud Run bridge itself is new design, not yet built or tested — treat it as a spec, not a verified working path.

**Context**
Two disconnected pieces exist today:
1. `apps_script/index.html` (Report Config tab, F05-S01_S02) — client/date/component picker, calls `generateReportPayload()`, shows JSON. Preview only; the card that built it explicitly scoped out actual rendering.
2. `generate_report.py` (F04-S08, landed 2026-07-04) — real pipeline, but CLI-only, requires a shell and `sheets_auth.get_credentials()`'s interactive OAuth flow on first run.

Apps Script runs server-side in Google's sandbox — can't invoke Python, Puppeteer, or matplotlib. Needs a bridge. **Locked: Cloud Run, called directly on the Generate button click** — Apps Script calls a Cloud Run endpoint via `UrlFetchApp` (token-authenticated, not public); the container spins up per request, runs `generate_full_report()` + Puppeteer, uploads to Drive, returns the link, scales back to zero. Rejected alternative: a Sheets-based poll worker on an always-on VM — needs a server running 24/7 plus someone to maintain it, doesn't fit two users generating reports occasionally. Cloud Run's free tier (2M requests/mo) covers this easily; cold start (~5-15s Chromium boot) is an acceptable tradeoff.

**Output type — locked: full_report only.** Nudge is deferred per the feature register. `generate_full_report()` already handles either type internally, so adding nudge later is a small extension to this same endpoint, not a new bridge.

**Input data**
```
Cloud Run endpoint: POST /generate-report
  Request body: { client_id, date_from, date_to, component_ids[], layout }
  Response (synchronous, held open through Chromium render):
    success -> { status: "done", output_url }
    failure -> { status: "error", error_message }
```
Endpoint auth: shared secret in the request header, checked before any work starts.

Output storage — locked: Drive, same parent folder as `insight_pilot`, new subfolder **"Client Reports"** (service creates it if missing). Sharing restricted to **Arun's account only** — never anyone-with-link.

Layout mapping — **OPEN.** Report Config's picker offers 1×1/1×2/2×1/2×2; `generate_full_report()` takes a `grid_density` string (e.g. `"3x2"`). Confirm the exact value set against F05-S04 before building — don't guess the translation.

**Scope**

*Apps Script side:*
1. New function `generateReport(params)` (same shape as `generateReportPayload()`, minus `output_type`) — calls the Cloud Run endpoint via `UrlFetchApp.fetch()` with the shared-secret header.
2. UI: keep the existing preview button as-is. Add "Download Report" — enabled after preview succeeds — that calls `generateReport`, shows a spinner for the call's duration (~5-20s), then a download link or error message. No polling; the HTTP call blocks until done.
3. No new deployment — same URL, same tab.

*Cloud Run service (new, e.g. `report_service/`):*
1. `POST /generate-report` — validates the shared secret before touching Sheets/Drive.
2. Reuses F04-S08's `fetch_client_readings`/`fetch_client_profile` directly — not the Apps Script JS query logic, which is a separate, independent path.
3. Calls `generate_full_report(...)` as `generate_report.py`'s `main()` does (`asset_library=None` fallback, same as today).
4. Success: find-or-create "Client Reports" subfolder, upload, share to Arun's account only, return `{status: "done", output_url}`.
5. Failure: catch, return `{status: "error", error_message}` with a proper HTTP status — never hang or crash silently.
6. **New auth requirement:** a service account for Sheets/Drive access — a container can't complete `sheets_auth.py`'s interactive OAuth consent. Share `insight_pilot` + the Drive folder with the service account's email once created.
7. Container: package Python + Puppeteer/Chromium. Reuse the receipt generator's existing Puppeteer base image if one exists — don't design packaging from scratch.

**Technical requirements**
1. Unit tests — request validation (missing/malformed params, bad auth), success path against fixtures, failure returns structured error not a raw 500
2. Every external call (Sheets, Drive, `generate_full_report`) in try/catch — container always returns a response
3. Auth: shared secret at the endpoint, service account inside the container — both new, neither reuses `sheets_auth.py`'s interactive flow
4. Set an explicit Cloud Run timeout above worst-case render time — confirm that number against real data, don't guess
5. Cold start is expected — surface "first request may take longer" in the UI copy

**Acceptance criteria**
1. Trainer selects client/dates/components, previews JSON as today, clicks "Download Report"
2. Cloud Run endpoint is invoked directly — no intermediate row/queue/polling
3. Response returns a real PDF using live Sheet data — same as running `generate_report.py` manually would — landing in the "Client Reports" subfolder alongside `insight_pilot`, shared to Arun's account only
4. Trainer's UI shows a working download link on success, no shell access required at any point
5. A bad request (e.g. zero readings in range) surfaces as a clear in-app error, not a stuck spinner or a raw stack trace
6. Endpoint rejects calls without the shared secret

**Dependencies**
F04-S08 (live orchestration — done, Sat build). F04-S07 (date-count fix — done, Sat build). Confirm F05-S04's grid_density value set before mapping the layout picker.

**Out of scope**
- F04-S10 (live asset_library wiring) — endpoint uses the same `asset_library=None` local fallback F04-S08 uses today
- Nudge PNG generation — `output_type` handling stays out of this card's request/response shape entirely; adding it later is a small extension to this same endpoint, not a new bridge
- Async/queue-based triggering — not needed at this usage scale; revisit only if render times or concurrent usage grow enough to make synchronous HTTP calls impractical
