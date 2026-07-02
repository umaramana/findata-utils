# F06-S01 — Report Template Architecture: Multi-Format Vision (IDEAS DUMP — not for this week or next week's build)

**Status: vision capture only.** From Uma's review session (2026-06-28). Confirmed: this stays part of the long-term roadmap, explicitly not for Saturday's deliverable, and not the same priority as `F05-S03`'s sleeve theming (which IS picked up next week). This card has no committed timeline — it's here so the vision isn't lost between now and whenever it's prioritized.

**Context — why this is a separate card from F05-S03**
Uma's framing: today's report is a "Looker-style pagewise PDF," but that's one *template type* among several the platform should eventually support — different page-wise styled reports, an infographic-style single-composite dashboard, and a mobile-friendly dashboard. This is a different and larger axis of variation than `F05-S03`'s sleeve/colour theming (which swaps chrome assets within one template type). Conflating the two risks scope creep into either card — kept separate on purpose.

**What actually varies between template types — bigger than layout alone**

| | Pagewise PDF (this week's build) | Infographic dashboard | Mobile-friendly dashboard |
|---|---|---|---|
| Chart render shapes | Landscape, PDF-page-sized bar/heatmap images | Likely compact/dense — sparklines, stat tiles, not full-size bar charts | Portrait, narrow-width, stacked vertically |
| Arrangement logic | Multi-page, bucket-based pagination (`F05-S04`'s model) | Single tall composite, no pagination | Scrollable sections, not fixed "pages" at all |
| Assembly mechanism | Canva chrome injection + code-placed content → PDF | Probably a single matplotlib/PIL composite image, no Canva involved | Likely HTML/JSON-driven, not a static raster image at all |
| Output format | PDF file | PNG/JPEG | Interactive web view |

The point of this table: a new template type isn't "reuse `F05-S04` with different numbers" — it likely needs different render shapes from `F04`, a different assembly step from `F05-S05`, and a different output format entirely. Treat a future template type as a parallel pipeline, not a parameter on this week's pipeline.

**What this week's build should do to stay future-proof, at near-zero cost:** add a `template_type` field to report config (`F05-S01_S02`), enum with a single valid value today (`looker_pagewise_pdf_v1`). Costs nothing now; means a future template type is a new enum value + new code path later instead of a schema migration on live data. Not yet added — the report-config card wasn't in hand when this was raised; revisit when convenient, low urgency since it's cheap to retrofit either way.

**Relationship to F05-S03 (sleeve theming):** orthogonal, not overlapping. Sleeve/colour theming should ideally work the same way *inside* any template type — a Male/Female/Child sleeve concept doesn't go away if the report becomes a mobile dashboard instead of a PDF. Don't merge these two cards' scopes even though they're both "appearance" in casual conversation.

**Dependencies**
None for Saturday or next week. Genuinely long-horizon — flagged here so it resurfaces deliberately rather than getting reinvented from scratch later.
