# F05-S06 — Metric-Level Image & Icon Selection (REWRITTEN 2026-06-30 — HTML/CSS placement, status update)

**⚠️ STATUS UPDATE 2026-07-01 — Physio 1/2/3 partially built; deviates from this card in three ways, all deliberate.** Session on 2026-07-01 built per-metric icons for Physio 1/2/3 (pushups/squats/crunches, plank/side-planks, cooper test/flexibility), driven by re-checking `Reshma...pdf` and `DrPraveena_Dashboard_2019to2026.pdf` directly. Real, working icons now render for these three components. Three departures from this card's original spec, recorded here so they aren't "corrected" back by accident:

1. **Placement is a row of icons *above* the table, not "inset within the section's container."** The samples show icons sitting above each heatmap table (sometimes flanking, inconsistently, per section — the row-above pattern was chosen as the one consistent rule that works regardless of date count, see `image_mapping_and_sheet_integration_card.md`).
2. **Still reading from the local hardcoded `_local_asset_library()` in `report_pdf.py`, not the live sheet's `asset_library`/`metric_asset_groups` tabs.** `load_asset_library()`/`load_metric_asset_groups()` (this card's original spec) exist in `gender_image.py` but are still never called anywhere. Confirmed today: the live sheet's `asset_library` tab has drifted from the local fallback (fewer rows, some different filenames) — do not assume they match.
3. **Balance still has zero icons** — no balance-pose assets exist in `assets/male`/`assets/female` yet. This card's "9 shared poses via `metric_asset_groups`" design is unbuilt, not wrong — just blocked on sourcing the actual art.

**Also found and fixed today**: two silent-failure bugs in the *old* local asset entries — `"situps"` and `"cooper_12min"` were used as lookup keys but neither is a real `metric_id` (the real ones are `crunches` and `cooper_test`), so those entries never matched anything, ever. A bad `image_ref` path also fails silently (`_b64()` returns `None`, the entry is just dropped, no error) — bit twice in one session (typo'd `women-situps.jpg`/`flexibilitywomen.jpg` instead of the real `women-squats.jpg`/`women-flex.jpg`). A regression test (`test_local_asset_library_has_no_silently_dropped_entries`, test_report_pdf.py) now asserts the loaded count matches expectations, so a future typo fails loudly instead of just rendering an iconless section.

**Client type is wider than gender.** Ideation on 2026-07-01 confirmed the live `client_master` tab already has a `client_type` column (currently only `"adult"` in sample data) — this needs a `"child"` value and to actually be read (today's code only reads `gender`, ignores `client_type` entirely). Client-type-specific components: Body Weight, WHR, Physio 1/2/3. Everything else (BP, Pulse, Body Composition, Balance) is common/ungendered. Decided: `client_type` is an **explicit field**, not derived from age/DOB. Not built yet — recorded in `image_mapping_and_sheet_integration_card.md`.

---

**⚠️ STATUS UPDATE 2026-06-30 — confirmed not yet implemented.** QC run against the `vip_001` smoke test (this week's pivot build) found zero icons and zero decorative images rendering anywhere in the report — every metric section came back with "no icon image found near its title." This isn't a regression; this card's actual build hasn't landed yet. Listing it explicitly here so it isn't mistaken for a bug introduced by the rendering-engine pivot — it's pre-existing, unbuilt scope.

**⚠️ PLACEMENT MECHANISM PIVOT — 2026-06-30.** This card's logic (resolution, lookup order, override table) is unaffected by the rendering-engine pivot and stays exactly as designed. What changes is *how* the resolved image/icon gets placed on the page:
- **Old assumption:** inset within "the section's existing box" inside a Canva content-template grid slot (matplotlib/ReportLab era).
- **New mechanism:** inset within the section's HTML container — an `<img>` tag positioned via CSS inside the same `<div>` that holds the metric's SVG chart (or HTML table, for Balance). `image_ref`/`icon_ref` should resolve to a path or URL usable directly in an `<img src="...">`, not a Canva asset-overlay reference.
- The "inset, not a separate grid slot" decision **still holds** — this is a placement-API change only, not a design change. One icon per metric, never repeated per row, image ungendered/icon gendered — all unchanged.
- No per-page concept anymore (single-flow infographic, not paginated) — irrelevant to this card either way, since image/icon placement was always per-metric-section, never per-page.

**Context**
Pulls exactly **one decorative image and one pictogram icon per metric**, at render time. **Standardized 2026-06-28** — earlier drafts of this card tracked the real samples' organic inconsistency too faithfully: some metrics got a single non-gendered photo, some got that photo *plus* a gendered icon repeated once per date column, some components got one shared image across all their metrics. That variation wasn't a deliberate design system in the original Looker reports, it was years of ad-hoc Canva edits — not worth replicating. **New rule, applies uniformly, no exceptions:**

- **Image** — one per metric, shown once. **Not gendered** (confirmed across 4 real samples: identical stock photo used regardless of client gender).
- **Icon** — one per metric, shown once (never repeated per date/row, regardless of how many dates are in the chart). **Gendered** — M/F variant required.

This removes the per-row repetition and the component-level fallback entirely. Every metric resolves independently and identically through one override mechanism (see below) — no hardcoded per-component logic anywhere in the renderer.

**Balance is the one place uniform-per-metric needs a small adjustment — generalized as an override mechanism, not a special case.** `balance_open` and `balance_closed` each have 9 stance metrics that are the same physical pose, eyes open vs. closed. Rather than hardcoding "Balance shares poses" as one-off logic, this uses a general override table: `metric_asset_groups: metric_id | asset_group_key`. Default behavior (no row present) is `asset_group_key = metric_id` — exactly today's per-metric rule. Balance gets 18 override rows mapping its open/closed pairs onto 9 shared keys (`balance_normal_open`→`pose_normal`, `balance_normal_closed`→`pose_normal`, etc.). **This same mechanism covers "fully shared at the component level" too, as a special case, without a separate mode/toggle:** point every metric in a component at the same `asset_group_key` and it behaves exactly like one shared asset for that whole component. No binary "component vs. metric" flag anywhere in the code — just one lookup table, one resolution step, applied uniformly. Confirm this matches intent before sourcing Balance's icon set (9 poses, not 18).

**Derived metrics need a synthetic key.** `waist_hip_ratio` and `bmi` aren't real rows in `metric_master` — both are computed at render time (from `body_measurements` and from `weight_kg`+`height_cm` respectively). Use `waist_hip_ratio` and `bmi` as recognized synthetic metric keys in `asset_library` even though no `metric_master` row exists for them. **Note the parallel:** this is the same synthetic-key pattern F05-S04 needed for its bucket-assignment fix — both `bmi` and `waist_hip_ratio` lack a `component_id` *and* a `metric_master` row, so both cards independently need a default-to-self / explicit-override mechanism rather than relying on a real backing record. Worth keeping these two cards' handling consistent if either changes.

**This has a real non-coding dependency: the actual assets don't exist yet, and 2 of Saturday's 3 pilot clients are male, 1 is female — both genders are load-bearing for the icon set, not nice-to-have.** Confirmed via `client_info`: `champion_mr_abhay_singh` (M), `master_jay` (M), `dr_hemalatha` (F). Child not needed — no child clients in this pilot.

**Build must not block on incomplete assets** — missing images/icons are a near-certainty given the timeline, so the fallback path matters as much as the happy path. **This remains true and is exactly what's happening right now** — the vip_001 smoke test rendering with zero icons is this fallback path working correctly, not failing. The QC script's "no icon found" findings are expected until asset sourcing + this card's build actually land, not an error state.

**No wireframe** — decorative placement within the metric's own HTML section container, not a new screen.

**Input data**

```
get_metric_visuals(metric_id, gender)
  → resolve_asset_group_key(metric_id): look up metric_id in
    metric_asset_groups; if a row exists, use its asset_group_key;
    otherwise default to metric_id itself (today's behavior for
    every metric with no override row)
  → looks up BOTH an image_ref (ungendered) and an icon_ref (gendered) for
    the resolved key in one call
  → image_ref: exact key match → null if none (no per-gender lookup —
    images are never gendered)
  → icon_ref: exact key+gender match → fallback to key+ANY →
    null if neither exists
  → returns {image_ref: str|null, icon_ref: str|null} — either or both
    may be null; section renders with whatever's available.
    Both refs should resolve to a path/URL directly usable in an
    HTML <img src="..."> tag.
```

Asset storage: two tables. `asset_library`: `asset_group_key | gender | role | image_ref` (`role` is `image` or `icon`; `gender` is `M`/`F` for `icon` rows, `ANY`/blank for `image` rows). `metric_asset_groups`: `metric_id | asset_group_key` — sparse, only needs rows where a metric doesn't use its own `metric_id` as the key (Balance's 18 rows today; empty for everything else).

**Build**
1. Add `asset_library` tab: `asset_group_key | gender | role | image_ref`. Add `metric_asset_groups` tab: `metric_id | asset_group_key`.
2. `resolve_asset_group_key(metric_id)`: look up in `metric_asset_groups`; row exists → use its key; no row → default to `metric_id` itself. This single step is what makes Balance's sharing (or any future full-component sharing) "just data," not a code branch.
3. Lookup order for icons: exact key+gender → key+`ANY` → null. Images: exact key → null (no gender dimension).
4. Wire into F05-S04's layout so each section in the report carries its optional image+icon alongside its chart/table, rendered as an `<img>` inset inside that section's HTML container via CSS (`position: relative`/`absolute` within the section's own box, not a separate grid cell — see placement-mechanism pivot above).
5. Build and test against an **empty or partially-empty** `asset_library`/`metric_asset_groups` — the realistic starting state — confirming the report still renders correctly with zero or few assets present. (This is the exact state vip_001 is in right now — use it as a live fixture.)

**Technical requirements**
1. Unit tests — pytest: image found/not found, icon exact-gender/ANY-fallback/not-found, `resolve_asset_group_key` defaults to `metric_id` when no override row exists, resolves correctly for Balance's open/closed pairs via override rows, derived-metric synthetic keys (`bmi`, `waist_hip_ratio`) resolve correctly (also via the same default-to-self path, no override row needed since they're already standalone keys), malformed/missing image_ref, **new** — resolved `image_ref`/`icon_ref` is a valid path/URL an `<img>` tag can consume (not a Canva asset-overlay reference)
2. Regression suite — runs everything built so far
3. Error handling — a broken/unreachable image_ref should fail gracefully (skip that visual) not break the whole report generation
4. Auth — reuse Sheets auth for the new tab
5. PWA — n/a
6. Output versioning — n/a here

**Acceptance criteria**
1. Every metric resolves its image and icon independently via `resolve_asset_group_key` — no hardcoded per-component special-casing anywhere in code
2. Icon never repeats per date/row — exactly one per resolved key regardless of how many dates are in that metric's chart
3. Image is never gendered — same `image_ref` regardless of client gender
4. Balance's 9 poses each resolve correctly for both eyes-open and eyes-closed variants via `metric_asset_groups` override rows, not a special function
5. `bmi` and `waist_hip_ratio` resolve correctly despite having no `metric_master` row (they default to using their own synthetic key, same as any other metric)
6. Report generation succeeds end-to-end against a completely empty `asset_library`/`metric_asset_groups` — images/icons are additive polish, never a hard requirement to ship
7. **New** — once assets exist, the QC script's per-metric icon-presence check (in `qc_report.py`) passes for every metric with a sourced icon, and continues to pass-with-no-error for metrics still missing one (per acceptance criterion 6)

**Dependencies**
None blocking on other cards for the resolution logic itself. F05-S04 must be rendering each metric inside its own HTML container before this card's `<img>` insertion has anywhere to attach. **Real dependency is non-technical: source/create the M+F icon set (9 Balance poses + Weight + WHR + whichever other metrics get icons) and the ungendered image set** — start today, in parallel with this week's coding sessions.
