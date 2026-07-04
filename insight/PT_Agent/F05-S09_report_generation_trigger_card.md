# F05-S09 — Report generation trigger (trainer/client-facing) — NEW 2026-07-04

**Status: not scoped, not built. Scope-only card — captures the gap and the real architecture options, no build yet.**

**Context**
Found while wrapping up F04-S07/S08/S09: there is currently NO way for Arun (or Uma, outside a local dev session) to trigger a report. The GAS web app (Check-In + Full Assessment tabs) only writes readings to the `insight_pilot` sheet. Its `generateReportPayload()` function (Code.gs) builds a JSON data preview for the Report Config UI — it does NOT and CANNOT produce a PDF, because Google Apps Script has no access to Python (matplotlib, the chart renderer) or Node (Puppeteer, the PDF export). The only existing path to a real PDF is `python generate_report.py <client_id> <date_from> <date_to>`, run locally by Uma/Claude Code, requiring Python + Node + Puppeteer + a Google OAuth token authorized as `umanatraj@gmail.com`.

This has been fine for the pilot so far (Uma running it by hand for 3 clients), but it means Arun cannot self-serve a report for a client sitting in front of him, and every report requires Uma's laptop + dev environment.

**Input data**
```
Existing local pipeline (all Python/Node, no changes needed to the pipeline itself):
  generate_report.py <client_id> <date_from> <date_to>
    -> sheets_auth.get_credentials() (OAuth, needs a browser once per token refresh)
    -> gspread reads readings/client_info from insight_pilot
    -> report_pdf.generate_full_report() (matplotlib SVG + Jinja2 + Puppeteer)
    -> PDF written to insight_core/reports/

GAS web app (Code.gs + index.html) — check-in/full-assessment forms only,
no report-triggering UI exists anywhere in it yet.
```

**Real architecture question — three options, not decided here**

1. **Stay manual (do nothing new).** Uma runs `generate_report.py` locally whenever a report is needed. Zero build cost. Fine at current pilot volume (3 clients, occasional runs). Doesn't scale past Uma being available and having her dev machine.

2. **Hosted backend service.** Deploy the existing Python/Node pipeline behind a small hosted service (e.g. a container on Cloud Run, since Puppeteer needs a real Chromium + Node runtime that GAS can't provide) with an HTTP endpoint. GAS's web app gets a "Generate Report" button that POSTs `client_id`/date range to that service; the service runs the same pipeline and returns a PDF (or a link to one, e.g. stored in Drive). This is the only path to letting Arun self-serve from his phone/browser. Real costs: hosting (Cloud Run has a free tier but this needs evaluating for Puppeteer's memory footprint), auth (the service needs its own service-account credentials, not Uma's personal OAuth token, to run unattended), and a build to actually wire it up (GAS button → HTTP call → service → response handling).

3. **Scheduled/batch generation.** A periodic job (Cloud Scheduler + Cloud Function, or similar) checks for clients with new readings since their last report and generates one automatically, notifying Arun/the client when ready (email, WhatsApp — ties into the still-unscoped `S3.3_whatsapp_nudge_card.md`). No manual trigger needed at all, but less real-time than a button, and still needs the same hosted-service groundwork as option 2.

**Scope (once a direction is picked — NOT scoped yet)**
1. Decide manual vs. hosted vs. scheduled with Uma — this is a cost/complexity/timeline call, not a technical one.
2. If hosted: pick a host (Cloud Run is the natural fit given Puppeteer's Node/Chromium requirement), containerize `generate_report.py`'s pipeline, set up a service account (not personal OAuth) for unattended Sheets access, add the endpoint.
3. If any trigger UI is needed: add a "Generate Report" affordance to the GAS web app, wire it to call the new endpoint, handle the response (download link, in-app preview, etc.).

**Test data**: the same 3 real pilot clients (`champion_mr_abhay_singh`, `master_jay`, `dr_hemalatha`) plus `uma`.

**Acceptance criteria**: not defined yet — depends entirely on which option is chosen.

**No wireframe yet** — depends on chosen option (a button in the existing GAS app, vs. no UI at all for the scheduled option).

**Dependencies**: none technically blocking — this is additive to the already-working local pipeline (F04-S07/S08/S09). Should be scoped with Uma before any build starts, since it's mostly a decision, not a coding task.

**Out of scope**: any change to the rendering pipeline itself (chart_renderer.py, report_pdf.py, generate_report.py) — this card is purely about *who/what calls* the existing pipeline, not the pipeline itself.
