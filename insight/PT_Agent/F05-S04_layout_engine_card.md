# F05-S04 — Page Layout Engine (REWRITTEN 2026-06-28 — bucket/pagination model, not single-grid)

**⚠️ COMPOSITOR APPROACH PIVOT — 2026-06-30**
Layout engine was built in `report_pdf.py` using matplotlib `fig.add_axes()`. Smoke-tested (v14 PDF). Decision: rebuild compositor as HTML/CSS → Puppeteer. The bucket model, geometry constants, and all decisions below remain correct and unchanged — only the rendering engine changes. When rebuilding, read `report_pdf.py` for the measured constants (COL1_W, COL2_W, VITAL_H, MID_H, THIRD_W, _DATE_PAD, etc.) before coding — they're all already derived and working.

**Chart outputs for HTML build:** `chart_renderer.py` can produce PNG bytes (current) or SVG strings (`format="svg"` option — add if not present). `table_heatmap.py` can produce PNG bytes or be rewritten to produce HTML `<table>` with inline CSS (simpler for Puppeteer, avoids a PNG round-trip). Either approach works — decide in the HTML compositor session.

**This replaces the original single-grid-density model entirely.** The original card treated every selected section uniformly — pick one grid density (1×1/1×2/2×1/2×2), chunk the whole selection-order list into pages of that size. That model can't produce what the real samples actually do, and would happily place a heatmap table next to a bar chart if selection order put it there. Rewritten from a full page-by-page audit of all 7 real samples (Reshma, Karthik, Thilak, Dr Uma, Dr Praveena, Dr Ramesh ×2).

**Context**
Places rendered chart/table images onto report pages — code handles placement entirely, no manual Canva alignment. Confirmed from the sample audit: there's a structural pattern underneath the apparent "FirstTime = 1 page, PastYears = splits" variation, and it's a single rule, not two.

**The core finding — three fixed content buckets, in fixed order:**

1. **Body Measurements** — the big multi-category bar chart (`body_measurements`)
2. **Body Vitals** (+ Strength) — weight, WHR, BMI, BP, pulse, bmr; strength metrics render via the same compact bar-family shapes, bucketed here too (assumption, not strongly evidenced from samples — none of the 3 real Saturday clients have multi-trial strength, flag if this placement turns out wrong)
3. **Physio/Balance** — every heatmap table (`physio_1`, `physio_2`, `physio_3`, `balance_open`, `balance_closed`)

**The one rule with zero exceptions across all 7 samples: a heatmap table never shares a page with a bar chart.** Bucket 3 never mixes with buckets 1/2 on the same page, regardless of remaining space. This is a hard page break, not a height check.

**Why "FirstTime = 1 page, PastYears = splits" was never actually two rules:** it's height-based pagination within these 3 buckets, processed in order. A `horizontal_single` chart (weight, WHR) adds one bar-row per date; each heatmap table adds one row per date. FirstTime reports (1 date) are short enough that Buckets 1+2 fit on one page and Bucket 3 fits on another. PastYears reports (multiple dates) grow taller per bucket — once a bucket's stacked height exceeds one page, it spills to a new page **at that point**, not via a hardcoded "if too much, split in 2." Praveena (5 dates) needed 2 heatmap pages; Ramesh (4 dates) needed 2; Uma (2 dates, no Physio tracked) fit Vitals in one 2×2 page and Balance in another.

**Where grid density actually applies — narrower than originally scoped:** the trainer's 1×1/1×2/2×1/2×2 picker applies **only within Bucket 2 (Vitals/Strength)** — that's the only place a real sample shows an actual grid (Dr Uma's 4-chart 2×2 page). Bucket 1 (Measurements) is always exactly one full-width item — the grid density doesn't apply to it since there's only ever one. Bucket 3 (heatmaps) is **never gridded** — heatmaps always stack full-width, one per row, regardless of density setting.

**This also resolves the aspect-ratio question previously open on this card.** That problem was specifically "forcing a 5.26-ratio heatmap into a near-square grid cell built for a 1.4-ratio scorecard." Heatmaps never enter a grid now — they stack full-width at their natural height. Bucket 2's items (the only ones gridded) are all within a much narrower shape range (~1.0–2.0 aspect ratio from the smoke-test measurements), so equal-size grid cells there are low-risk. No separate aspect-ratio handling decision needed — it falls out of the bucket model.

**Confirmed from F04-S02/03/04/05's actual smoke-test output (2026-06-27):** every rendered image is fully self-contained — title, `"Measurement units: {unit}"` note, and date labels are already baked into the PNG by the renderer. **This card must not re-render a title, unit label, or date header around each image.**

**Image/icon placement — decided, asset-driven, no threshold:** every chart/section that resolves an image and/or icon via `F05-S06`'s `get_metric_visuals()` gets it inset within its own box — no separate grid slot (confirmed 2026-06-27 against every real sample: decorative visuals always sit inside the same panel as their chart, never as a standalone box), and no minimum-per-page floor (rejected 2026-06-28 — `body_measurements` has zero images in every sample, a floor would force fabricating decoration there with no asset backing it).

**Confirmed 2026-06-29 — content-page chrome gap, add this:** every content page draws client name top-right and page number bottom-right, on top of the existing `BG.png` chrome. Missing from `vip_001`'s smoke test, real samples have it. This is page-level chrome the assembler draws, not something baked into `F04`'s rendered images.

**No wireframe** — `tpl-reportconfig` already shows the grid picker control; this card is the rendering logic behind that existing choice, now scoped to Bucket 2 only.

**Input data**

```
layout_report(rendered_sections[], grid_density, options)
  rendered_sections: ordered list of {component_id, metric_id, image, icon,
    rendered_height_px, rendered_width_px} — one entry per selected
    component/metric, already rendered by F04-S02/03/04/05 with its
    image/icon already inset by F05-S06
  grid_density: "1x1" | "1x2" | "2x1" | "2x2" — applies to Bucket 2 only

  1. Partition rendered_sections into 3 ordered buckets:
     - Bucket 1: body_measurements
     - Bucket 2: body_vitals, strength, AND any derived/computed metric
       with no real component_id of its own — explicitly: bmi,
       waist_hip_ratio. **Bug found 2026-06-29 (vip_001 smoke test):**
       these two have no `component_id` at all (computed at render
       time, not stored), so a partition keyed purely on `component_id`
       silently drops them through to a default/ungrouped path —
       observed as WHR rendering alone on its own page instead of
       grouping with the rest of Bucket 2. Fix: partition by a resolved
       key that defaults to `component_id`, but explicitly maps
       `bmi`→Bucket 2 and `waist_hip_ratio`→Bucket 2 when no
       `component_id` is present. Same shape as F05-S06's
       `resolve_asset_group_key` — don't invent a second mechanism,
       reuse the pattern.
     - Bucket 3: physio_1, physio_2, physio_3, balance_open, balance_closed
  2. Within each bucket, preserve report-config selection order — don't
     re-sort by component_id or alphabetically.
  3. Walk buckets in fixed order (1 → 2 → 3), accumulating rendered_height_px
     onto the current page:
     - Bucket 1 items: always full-width, one per page-row
     - Bucket 2 items: chunked per grid_density (N=1,2,2,4 per page-row group)
     - Bucket 3 items: always full-width, one per page-row, never gridded
  4. Start a new page when:
     (a) adding the next item/group would exceed the page's usable content
         height, OR
     (b) the bucket boundary between 2 and 3 is crossed — hard break,
         regardless of remaining space (heatmaps never share a page with
         bar charts)
  → returns ordered list of page layouts, each containing its grouped
    sections positioned within the page per the bucket/grid rules above
```

**Build**
1. Bucket-partition step first — pure classification, no rendering logic. Sorts `rendered_sections` into the 3 fixed lists, keyed on `component_id` **with an explicit override for `bmi` and `waist_hip_ratio`** (no `component_id` exists for either — map both to Bucket 2 directly, don't rely on a fallback/default path).
2. Pure layout/grouping function within Bucket 2 — chunk into groups of N based on grid_density (N = 1, 2, 2, or 4), same logic as the original card's chunking, just scoped to this bucket only.
3. **Canva content-area dimensions — measured 2026-06-28, no longer a blocker.** Canvas is 1024×768px (4:3) — confirmed against the real exported reports (same ratio at higher raster resolution). Chrome footprint: left strip 12px wide, full height (black y:0–141, maroon y:141–768); top-right dots 69×109px box; bottom-left dots 84×148px box; bottom-right dots 69×108px box; no top-left dots (strip occupies that corner). **Recommended safe content rectangle: x:30→994, y:20→748 → usable content height ≈728px** at this scale. One caveat: measured from the flat background asset — if the live Canva template defines its own tighter placeholder frame, that takes precedence over this derived rectangle. Still needed before finalizing: the rendered height of one bar-row/heatmap-row at this same scale, so the height-accumulation math has both sides of the comparison.
4. Position each group's images within the page according to bucket/grid shape — Bucket 1 full-width, Bucket 2 per grid_density (1×2 side-by-side, 2×1 stacked, 2×2 grid), Bucket 3 full-width stacked. Positions are fixed offsets within the Canva content template's content area.
5. A bucket may itself span multiple pages if its content doesn't fit on one (Praveena's 2 heatmap pages) — when this happens, continue the same bucket on the next page rather than forcing remaining sections into a cramped fit.
6. Last page within any bucket may have fewer items than a full grid group (e.g. 5 Vitals charts at 2×2 = 1 full page + 1 page with a single chart) — render the partial group normally, not stretched to fill empty slots.
7. Zero sections selected in a bucket → that bucket simply produces no pages, not an error — only zero sections selected across *all* buckets is the actual empty-report case.

**Technical requirements**
1. Unit tests — pytest: bucket partitioning correctly sorts known component_ids into the 3 buckets; **`bmi` and `waist_hip_ratio` explicitly land in Bucket 2 despite having no `component_id`** (regression test for the 2026-06-29 bug — these must never fall through to a standalone/default page); Bucket 2 grid chunking at each density (exact multiple, partial last group, single item at 2×2 not stretched); Bucket 3 never groups into a grid regardless of density setting; hard page break enforced at the Bucket 2/3 boundary even when both would technically fit by height; a bucket spanning multiple pages continues correctly without losing or duplicating sections; zero sections in one bucket produces no pages for that bucket without erroring
2. Regression suite — runs everything built so far
3. Error handling — zero sections selected across all buckets produces a clear empty-report message, not an empty PDF page
4. Auth — n/a
5. PWA — n/a
6. Output versioning — n/a here, applies once F05-S05 exports the actual file

**Acceptance criteria**
1. `body_measurements` always renders full-width, alone in its page-row, regardless of grid_density
2. Heatmap components (`physio_1/2/3`, `balance_open/closed`) always render full-width, one per page-row, never arranged in a grid, regardless of grid_density
3. `grid_density` visibly affects only Body Vitals/Strength chart arrangement
4. No page ever contains both a heatmap and a bar-type chart together
5. A bucket whose content exceeds one page's height continues correctly onto subsequent pages, in order, without skipping or duplicating sections
6. A non-exact multiple of Bucket-2 sections renders a correctly-populated partial final group, not stretched or broken
7. Section order within each bucket matches selection order from report config, not re-sorted
8. Zero sections selected across all buckets produces a clear message, not a malformed empty page

**Dependencies**
F04-S02/03/04/05 must produce the rendered images this card arranges, each already carrying its F05-S06 image/icon inset. F05-S01's existing grid-picker UI field is the input source for `grid_density`, now understood to scope to Bucket 2 only. **Canva content-area dimensions are now measured (see Build step 3) — the one remaining piece is the rendered height of one bar-row/heatmap-row at the same scale, needed to complete the height-accumulation comparison.**
