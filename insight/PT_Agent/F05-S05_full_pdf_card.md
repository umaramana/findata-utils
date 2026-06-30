# F05-S05 — Full PDF Export

**⚠️ APPROACH PIVOT — 2026-06-30**
The matplotlib compositor (`report_pdf.py`) was built and smoke-tested (17/17 pass, v14 PDF generated). Visual output matched the layout grid spec but the approach hit a fundamental wall: `fig.add_axes()` has no layout engine — every y-axis tick label, icon inset, and cell boundary required manual pixel arithmetic with a slow PDF→image→crop preview cycle. Fine-grained polish (bleeding tick labels, icon alignment, bar proportions) was not converging.

**New approach: HTML/CSS → PDF via Puppeteer.** Same pattern already running for the receipt generator. The chart renderers (`chart_renderer.py`, `table_heatmap.py`) stay — they can emit PNG bytes or SVG strings. The compositor is a Jinja2 HTML template + Puppeteer print. Full CSS box model eliminates the pixel-arithmetic problem entirely.

**What the current `report_pdf.py` encodes (don't rebuild blind — read it):**
- Exact pixel geometry (COL1_W=440, COL2_W=474, VITAL_H=140, MID_H=155, THIRD_W=311, all confirmed)
- The 3-band layout (BM+BW/WHR | BMI+BP+Pulse | heatmaps)
- Asset wiring: icon inset inside BW/WHR axes; image placeholder outside chart for BMI/BP/Pulse/BM
- Date label format: "Jun\n2026" two-line in compact cells
- Bar mode per metric: BW/WHR = horizontal_single; BMI/Pulse = horizontal_single; BP = stacked_pair; BM = grouped_multi
- Heatmap badge position: right edge of content area, not heatmap width
- All these decisions are correct — only the rendering engine changes

**Context**
The final assembly step. Pulls together everything else built this week: F05-S01/S02's selected data, F04-S02/03/04/05's rendered charts, F05-S04's page layout, F05-S06's images (or gracefully none), and the existing Canva cover/content/closing templates — exports one PDF file per client. This is the last card in the sequence because it depends on every other card's output existing first.

**Status update 2026-06-29:** F05-S04's bucket model is rewritten and its WHR/BMI bucket-assignment bug is patched. Canva content-area dimensions are measured. The 3 confirmed F04 patches (decimal precision, "-", scorecard label) are written but not yet applied to code — apply those first. Cover template asset gap (flagged 2026-06-29 from the `vip_001` smoke test) is now resolved — see the chrome asset spec below.

**Chrome assets — decomposed into individual pieces, confirmed 2026-06-29.** Not one flat background per page type — individual reusable pieces, composited at render time, so the same pieces work across this week's Pagewise PDF and future template types (`F06-S01`):

| Piece | File | Size | Use |
|---|---|---|---|
| Header zone (black) | part of left strip | height = that page's header content height, not fixed | Top of left strip, every page |
| Footer zone (magenta #741b47) | left strip, flexi-height | fixed width (~12px at 1024×768 scale), stretches to fill remaining page height | Rest of left strip, every page. **2-tone confirmed — no 3rd "midrib" zone.** |
| Cover logo, left | `insight_leftlogo.png` | 310×180 | Cover page only, top-left |
| Cover seal, right | `insight_rightlogo.png` | 174×189 | Cover page only, top-right. **Text confirmed: "BUILDING A STRONGER" — do not use `Insight_Green_Circle_Logo.png`, it has stale text ("FOR A STRONGER")** |
| Content header logo | `Insight__200_X_100_Px__logo.png` | 200×100 | Every content page, top-left, bare wordmark only — no seal on content pages |
| Corner dots | `insight_corner.png` | 100×155 | Content pages — same corner positions as already measured in `Insight_BG.png` (top-right/bottom-left/bottom-right, no top-left) |
| Closing page | `Insight_Thank_you_Page.png` | 1024×768 | Closing page, used as-is |
| Cover hero logo | `Insight__400___400_px__logo.png` | 400×400 | Full lockup (icon+wordmark+tagline), cover page centerpiece |

**Client name + page number — confirmed 2026-06-29, real gap, must be drawn by this card:** every content page shows client name top-right and page number bottom-right, on top of the chrome above. Not baked into F04's rendered images — this card draws it.

**No wireframe** — this is an export/assembly step, not a UI.

**Input data**

```
generate_full_report(client_id, date_from, date_to, components[], grid_density)
  1. Calls F05-S02's query engine → structured data payload
  2. Calls F04-S02/03/04/05's render functions per component → rendered images
  3. Calls F05-S06 → optional image per section
  4. Calls F05-S04 → arranges everything into page layouts
  5. Injects cover page (client name, date range, Insight branding — 400×400
     square logo with full icon+wordmark+tagline lockup) into the existing
     Canva cover template
  6. Injects each page layout's content into the existing Canva content
     template — one content-template instance per page produced by F05-S04
     (200×100 rectangle logo, bare wordmark, top-left on every content page)
  7. Injects closing page (thank you, trainer contact) into the existing
     Canva closing template
  8. Exports the assembled result as a single PDF file
```

**Build**
1. Orchestration function calling the 4 prior cards' outputs in sequence — this card should contain minimal new logic itself, mostly wiring.
2. Confirm exact Canva template injection mechanism (API call, template variable substitution, or image overlay — whichever the existing F06 Canva templates expose) before building the injection step blind.
3. File naming: `{client_id}_{date_to}_full_report_v{n}.pdf` — auto-increment `v{n}` if regenerated for the same client+date, don't silently overwrite.
4. If any single component's render fails (e.g. F05-S06 returns null for an image, or a component has zero readings in range), the report still generates — that section either omits the missing piece or shows a clear "no data for this period" placeholder, never blocks the whole PDF.
5. Confirm with a real end-to-end run against at least one of the 3 pilot clients before considering this done — not just unit tests in isolation.

**Technical requirements**
1. Unit tests — pytest: full pipeline with complete data, full pipeline with one component missing data entirely, full pipeline with zero images available
2. Regression suite — runs everything built this week
3. Health check — validates the assembled payload references real component_ids/metric_ids before attempting Canva injection
4. Error handling — any single step's failure (chart render, image lookup) degrades that section gracefully rather than aborting the whole export
5. Auth — reuse existing Sheets auth; Canva API auth if the injection mechanism requires it (confirm whether F06 already established this)
6. PWA — n/a, this likely runs from an admin/laptop context, not a phone-first screen
7. Output versioning — **applies directly here** — auto-incrementing filename, first card this week where this actually matters

**Acceptance criteria**
1. Produces one PDF per client containing cover, content pages per F05-S04's layout, and closing page
2. Regenerating for the same client+date range produces a new versioned file, not an overwrite
3. A component with zero readings in the selected range renders a clear placeholder, doesn't break the export
4. A missing image (asset_library empty or partial) doesn't block export — section renders without it
5. End-to-end run against real data for at least one of the 3 pilot clients produces a PDF that opens correctly and contains the expected sections

**Dependencies**
F05-S01/S02, F04-S02/03/04/05, F05-S04, F05-S06 — all must exist first. This is genuinely last in the sequence, not parallelizable with the others.
