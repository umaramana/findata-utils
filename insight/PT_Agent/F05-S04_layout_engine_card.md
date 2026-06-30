# F05-S04 — Section Layout Engine (REWRITTEN 2026-06-30 — single-flow infographic, pagination dropped)

**⚠️ APPROACH PIVOT — 2026-06-30**
Two pivots stacked on this card, in order:
1. Rendering engine: matplotlib `fig.add_axes()` → HTML/CSS via Puppeteer (see F05-S05).
2. Output shape: paginated multi-page PDF → single continuous infographic-style flow, exported via Puppeteer's `page.pdf()` (not `page.screenshot()` — see F05-S05 for why PDF over PNG).

Dropping pagination removes most of this card's original complexity. **What stays unchanged: the bucket model and its ordering rules.** Buckets are no longer "groups of pages" — they're CSS sections stacked in one continuous document flow. Every content decision below (bucket order, grid_density scope, the bucket 2/3 separation rule) still applies; only the page-break mechanics are gone.

**What this card no longer needs to do (removed by the pagination drop):**
- Height-accumulation-until-overflow math
- "Start a new page when X" logic
- Bucket-spans-multiple-pages continuation handling
- Partial-last-grid-group-on-its-own-page handling
- Per-page chrome injection (cover/content/closing as separate Canva template instances)

These aren't deferred — they're gone. Don't rebuild them speculatively "in case pagination comes back." If a print/PDF page-size constraint resurfaces later, that's a new card, not a revival of this logic.

**What this card still needs to do:**
- Partition `rendered_sections` into 3 ordered buckets (unchanged from prior version)
- Preserve report-config selection order within each bucket (unchanged)
- Chunk bucket 2 into grid_density groups (N=1,2,2,4, plus new 3x2 → N=6, see spec-gap note below)
- Render buckets in fixed order (1 → 2 → 3) as stacked CSS sections, full document height
- Bucket 1 and bucket 3 items: always full-width, one per row, in document flow
- Bucket 2 items: laid out via CSS grid at grid_density, within its own section
- No page-break logic of any kind — the document is one flow, Puppeteer handles overflow by just making the page tall

**The core finding — three fixed content buckets, in fixed order (unchanged):**
1. **Body Measurements** — `body_measurements`, always alone, full-width
2. **Body Vitals** (+ Strength, + derived metrics `bmi` and `waist_hip_ratio` which have no `component_id` — explicit override, same bug fix as before) — gridded by `grid_density`
3. **Physio/Balance** — every heatmap (`physio_1/2/3`, `balance_open`, `balance_closed`) — always full-width, never gridded

**Grid density still scopes to bucket 2 only.** Bucket 1 has exactly one item, so density doesn't apply. Bucket 3 is never gridded regardless of density — same reasoning as before (5.26-ratio heatmaps don't belong in a near-square grid cell), it's just no longer also an aspect-ratio argument about page-sharing, since there's no page-sharing concept anymore.

**⚠️ SPEC GAP FOUND 2026-06-30 — bucket 2 density options don't cover its actual item count.** Bucket 2 now holds 6 items in practice (`body_weight`, `waist_hip_ratio`, `bmi`, `blood_pressure`, `pulse`, `body_composition` — `waist_hip_ratio` and `bmi` landed here via the derived-metric bucket-assignment fix). The original density set (1×1/1×2/2×1/2×2 → N=1,2,2,4) tops out at 4 per group, so 6 items either force an awkward 4+2 split or get crammed into a 2×2 that doesn't fit. Fix: add a `3x2` density option (N=6, 3 columns × 2 rows) to the picker, specifically for this bucket's real shape. This is a new option alongside the existing four, not a replacement — trainers may still want fewer items shown depending on what's selected for a given report; `3x2` only applies when bucket 2 has up to 6 items selected, same chunking logic as the others (chunk into groups of 6, partial last group renders normally per existing rule 6 below).

**Bucket 2/3 visual separation — still real, now expressed as CSS not a page break.** The original "heatmap never shares a page with a bar chart" rule becomes: bucket 3's section starts with a clear visual break (margin/divider/section header) from bucket 2's grid. Same intent — don't let a heatmap visually blend into a grid row — different mechanism (CSS `margin-top` / divider element instead of a forced page break).

**Image/icon placement, unit/date labels baked into chart SVGs — unchanged.** Every chart is self-contained (title, unit note, date labels included); this card places sections, it doesn't re-render labels around them.

**Build**
1. Bucket-partition function — unchanged from prior version, including the `bmi`/`waist_hip_ratio` explicit-mapping fix (resolved key defaults to `component_id`, with an override map for the two derived metrics).
2. Bucket 2 chunking by grid_density — N=1,2,2,4 for the original four densities; **new** 3x2 density chunks into groups of 6 (3 columns × 2 rows) — see spec-gap note above for why this was added.
3. Render as HTML: one top-level container, three child sections in fixed order. Bucket 1 section = single full-width chart. Bucket 2 section = CSS grid (`grid-template-columns` set by density). Bucket 3 section = stacked full-width blocks, one per heatmap, separated by a visual divider from bucket 2's section.
4. No page-size constraint — container height is intrinsic to content (sum of all sections), Puppeteer's `page.pdf()` with `printBackground: true` and no fixed page height (or `preferCSSPageSize` off) lets the rendered height define the export.
5. Zero sections selected in a bucket → that bucket's section simply doesn't render (no empty container, no error). Zero sections across all buckets → empty-report message (unchanged from before).

**Technical requirements**
1. Unit tests — pytest/equivalent on the partition and chunking logic only (unchanged from prior version's relevant tests): bucket partitioning correctness, `bmi`/`waist_hip_ratio` regression test, grid chunking at each density including partial last group, bucket 3 never grids. **New:** `3x2` density chunks exactly 6 items into one 3-column-2-row group; bucket 2 with the full 6-item set (body_weight, waist_hip_ratio, bmi, blood_pressure, pulse, body_composition) selected and `3x2` density produces one clean group, not a 4+2 split. **Drop:** any test about page breaks, multi-page continuation, or partial-group-on-its-own-page — those don't exist anymore.
2. Regression suite — runs everything built so far
3. Error handling — zero sections across all buckets produces a clear empty-report message
4. Output versioning — n/a here, applies in F05-S05

**Acceptance criteria**
1. `body_measurements` always renders full-width, alone, first in flow
2. Heatmaps always render full-width, one per row, last in flow, visually separated from bucket 2
3. `grid_density` visibly affects only bucket 2's arrangement
4. Section order within each bucket matches report-config selection order
5. Zero sections selected across all buckets produces a clear message, not a malformed empty render
6. With all 6 bucket-2 metrics selected and `3x2` density chosen, renders one clean 3-column-2-row grid — not 4+2, not a stretched 2x2

**Dependencies**
F04-S02/03/04/05 must produce rendered chart assets — now as SVG strings or HTML fragments (heatmaps), not PNG bytes (quality decision locked 2026-06-30, see F05-S05). F05-S01's grid-picker UI field is still the input source for `grid_density`, scoped to bucket 2.
