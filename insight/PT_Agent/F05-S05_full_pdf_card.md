# F05-S05 — Full Report Export (REWRITTEN 2026-06-30 — single-flow infographic → PDF via Puppeteer)

**⚠️ APPROACH PIVOT — 2026-06-30**
Two decisions locked this session, both downstream of the matplotlib-compositor wall hit in the prior session:

1. **Rendering engine: HTML/CSS → Puppeteer**, not matplotlib `fig.add_axes()`. Reuses the pattern already running for the receipt generator — one rendering engine across both products, not two.
2. **Output shape: single continuous infographic-style document, not paginated pages.** No Canva-cover/content/closing per-page template injection. One chrome wrapper around one continuous flow. Pagination logic (F05-S04's old height-accumulation/page-break model) is dropped entirely, not deferred.
3. **Export format: PDF via `page.pdf()`, not PNG via `page.screenshot()`.** Considered and rejected PNG — reasons: (a) the platform already has a PNG product (WhatsApp nudges) and giving the full report the same format blurs a distinction the terminology doc is built around; (b) a single tall PNG is hard to navigate on a phone — no scroll-stop equivalent, just continuous pinch-zoom; (c) PDF keeps text selectable/searchable and is the expected deliverable format for an "assessment report"; (d) printing, if ever needed, works natively with PDF and not with a giant PNG.

**Chart asset format — also locked this session (was previously open, flagged as the thing that bit the original PNG-quality problem):**
- Charts (bar family, scorecards): matplotlib → **SVG**, not PNG. Fixes the resolution/quality issue from the matplotlib-PNG attempt — SVG scales losslessly to whatever size CSS gives it, no DPI guesswork.
- Heatmap tables: native HTML `<table>` with inline CSS, not an image at all. Simpler for Puppeteer, avoids a PNG round-trip, and tables are the right semantic element for tabular data anyway.

**⚠️ SPEC CORRECTION 2026-06-30 — Pulse is not a bar chart.** The original (pre-pivot) card's per-metric chart-mode table listed Pulse as `horizontal_single`, same as Body Weight/WHR/BMI. Checked directly against the real Reshma sample: Pulse renders as a circular gauge/donut (a ring with the value centered inside — see Reshma page 2, bottom-right), not a bar at all. Confirmed this is the only mismatch in that table — Body Weight, WHR, BMI (`horizontal_single`), Blood Pressure (`stacked_pair`), and Body Measurements (`grouped_multi`) all check out against the samples with no aberration. **Corrected mode table:**

| Metric | Mode |
|---|---|
| Body Weight | horizontal_single |
| Waist to Hip Ratio | horizontal_single |
| BMI | horizontal_single |
| Blood Pressure | stacked_pair |
| Body Measurements | grouped_multi |
| **Pulse** | **circular_gauge (donut), not a bar** |

This also retroactively explains part of why vip_001's Pulse looked "bloated and vertical" — it was very likely being forced through the bar-rendering path (`horizontal_single`) per the wrong spec, not just suffering from the page-width-stretch problem noted below. Both issues may be compounding; re-check Pulse specifically after both fixes land.

**What `report_pdf.py`'s geometry work is still worth (don't discard):** COL1_W/COL2_W/VITAL_H/MID_H/THIRD_W and friends were measured pixel constants for the old 3-band matplotlib layout. That old 3-band layout (BM+BW/WHR sharing a row | BMI+BP+Pulse | heatmaps) is **superseded by the bucket model** (BM alone, full-width | bucket 2 gridded | bucket 3 stacked) — confirmed this session as the correct model, the 3-band sketch was a regression to the old layout and has been corrected. The pixel constants themselves can inform relative proportions (e.g. column width ratios) when translating to CSS, but the band structure they describe should not be rebuilt.

**Context**
Final assembly step. Pulls together F05-S02's data, F04-S02/03/04/05's rendered charts (now SVG/HTML), F05-S04's section ordering (now single-flow, not paginated), F05-S06's images, and chrome assets — exports one PDF file per client.

**Chrome — simplified by dropping pagination.** No more per-page cover/content/closing template injection loop. One wrapper: header/branding zone once at the top, footer/closing zone once at the bottom, the three bucket sections in between. The previously-decomposed chrome pieces (logo, seal, corner dots, footer color zone) still apply — they just get placed once each, not repeated per page.

| Piece | File | Size | Use |
|---|---|---|---|
| Cover logo, left | `insight_leftlogo.png` | 310×180 | Top of document |
| Cover seal, right | `insight_rightlogo.png` | 174×189 | Top of document, "BUILDING A STRONGER" text confirmed |
| Hero lockup | `Insight__400___400_px__logo.png` | 400×400 | Top banner centerpiece |
| Closing | `Insight_Thank_you_Page.png` | 1024×768 | Bottom of document, used as-is |
| Footer color zone | maroon `#741b47` | flexi-height | Side strip running the full document height, not per-page |

**⚠️ SPEC GAP FOUND 2026-06-30 — content sections currently render edge-to-edge, should be constrained.** vip_001 smoke test shows every bucket section stretching to the full page width — this is the most visually obvious problem with the current render. Reshma's sample (and every real sample reviewed) keeps a constrained content column with visible left/right margin, even within the same overall canvas width; nothing spans edge-to-edge. **Fix:** define a max-width content container, centered horizontally, that all three bucket sections render inside — not the full page width. Suggested starting point: reuse the previously-measured safe content rectangle from the old paginated model (x:30→994 within a 1024px canvas, i.e. ~30px margin each side, ~94% of page width) as the initial constraint, then tune against real samples once rendered — this is a starting value, not a final measurement. This single change should also reduce the "bloated" look on individual charts (BP, Pulse) reported separately, since bars/heatmaps stretching to fill an over-wide container is part of why they read as oversized — though the Pulse chart's wrong orientation (vertical instead of horizontal_single) is a separate bug, not fixed by this alone.

Client name + generation date: shown once near the top banner, not repeated per page (no pages to repeat across).

**Input data**

```
generate_full_report(client_id, date_from, date_to, components[], grid_density)
  1. F05-S02 query engine → structured data payload
  2. F04-S02/03/04/05 render functions → SVG strings (charts) / HTML fragments (heatmaps)
  3. F05-S06 → optional image per section
  4. F05-S04 → ordered bucket sections (single flow, no pages)
  5. Render one Jinja2 HTML template: header banner → bucket 1 section →
     bucket 2 grid section → divider → bucket 3 stacked section → closing banner
  6. Puppeteer loads the HTML, calls page.pdf({ printBackground: true,
     preferCSSPageSize: false }) — height follows content, no fixed page size
  7. Exports as a single PDF file
```

**Build**
1. Orchestration function wiring the 4 prior cards' outputs into one Jinja2 template render + one Puppeteer PDF call — minimal new logic, mostly wiring (unchanged intent from before, simpler in practice since there's no per-page loop).
2. File naming: `{client_id}_{date_to}_full_report_v{n}.pdf`, auto-increment if regenerated (unchanged).
3. If any single component's render fails (no data, no image), that section omits the missing piece or shows a placeholder — never blocks the export (unchanged).
4. Confirm with a real end-to-end run against at least one pilot client before considering this done.

**Technical requirements**
1. Unit tests — pytest: full pipeline with complete data; full pipeline with one component missing data; full pipeline with zero images available; **new** — SVG chart output renders correctly inside the HTML template at its CSS-assigned size (catches the PNG-quality regression by construction, since SVG can't blur the way the old PNG path did)
2. Regression suite — runs everything built this week
3. Error handling — any single step's failure degrades that section gracefully, never aborts the whole export
4. Output versioning — auto-incrementing filename (unchanged)

**Acceptance criteria**
1. Produces one PDF per client: header banner, bucket 1, bucket 2 (gridded by density), divider, bucket 3 (stacked), closing — all in one continuous flow, no internal page breaks
2. Regenerating for the same client+date range produces a new versioned file, not an overwrite
3. A component with zero readings renders a clear placeholder, doesn't break the export
4. A missing image doesn't block export
5. End-to-end run against real pilot data produces a PDF that opens correctly with all expected sections present and chart resolution sharp at any zoom level (SVG check)
6. All three bucket sections render inside a constrained, centered content width with visible margin on both sides — no section stretches edge-to-edge

**Dependencies**
F05-S01/S02, F04-S02/03/04/05 (now emitting SVG/HTML, not PNG), F05-S04 (now single-flow, not paginated), F05-S06 — all must exist first.
