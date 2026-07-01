# Image mapping (client_type) + live-sheet integration (scoping note, 2026-07-01)

**Status: partially built.** Stage 1 *and* Stage 2 below were both completed in this same session (originally staged as "Stage 2 later" — turned out to be small enough to do immediately once scoped). Live-sheet integration and Child art are still not built — those remain the open scope. This card is not a full build spec for the remaining work; it exists to lock in decisions made during ideation so later work isn't designed around the wrong assumptions.

**Why this note exists**
Two things surfaced while wiring up Physio 1/2/3 heatmap images: (1) images need a client-type dimension beyond Male/Female, and (2) the code that would read image mappings from the live sheet exists but has never been connected to anything.

**Locked decisions**

1. **Client type, not age-derived.** "Child" is determined by an explicit `client_type` field (already present in the live `client_master` tab, currently only ever set to `"adult"`), not computed from DOB/age. A trainer can override it manually; nothing infers it automatically.

2. **Two-tier image scope.**
   - **Client-type-based** (needs Male/Female/Child variants): Body Weight, Waist-to-Hip Ratio, Physio 1, Physio 2, Physio 3.
   - **Common** (one image regardless of client type): BP, Pulse, Body Composition, Balance (open/closed).

3. **Live-sheet integration is bigger than images.** `gender_image.py` has `load_asset_library()`/`load_metric_asset_groups()` — functions that would read the live sheet's `asset_library`/`metric_asset_groups` tabs — but nothing in the codebase calls them. `report_pdf.py` always uses a hardcoded local Python fallback (`_local_asset_library()`), which has already drifted from the live sheet's actual content (fewer rows, different filenames in places). This isn't just an images problem: `generate_full_report()` takes `all_readings`/`client_profile` as pre-fetched *parameters* — there is no orchestration script anywhere in the repo that actually authenticates, pulls live sheet data, and calls it. That gap needs its own scoping session covering all data, not just assets.

4. **Physio 3 splits from Balance, confirmed across two independent samples.** Both `Reshma - First Assessment Dashboard.pdf` (1 date) and `DrPraveena_Dashboard_2019to2026.pdf` (3 dates: 2019/2021/2020 shown for this section) show "12 min Cooper Test" + "Flexibility" as their own small 2-column table, distinct from Balance, flanked by running/stretching icons in both. Not a 1-date-only artifact.

5. **Icon count/placement is date-count-independent.** Table *width* is driven by metric count/label length, not date count (dates only add rows). Confirmed empirically: Dr Praveena's 3-date tables show the identical icon count/placement as Reshma's 1-date version. This validates a fixed image slot per component rather than "fit icons into whatever space is left" (which was Looker's apparent approach, but never actually needed to vary — it just happened to look that way).

**Done this session (both originally-staged steps)**
- Per-metric icon row above each bucket-3 table (Physio 1/2/3), not a single component-level icon — see `F04-S05_table_heatmap_card.md`'s as-built notes for the template/CSS side, `F05-S06_gender_image_card.md` for the asset-lookup side.
- Two silent-failure asset-mapping bugs found and fixed (`situps`→`crunches`, `cooper_12min`→`cooper_test` key mismatches) plus two filename typos (`women-situps.jpg`→`women-squats.jpg`, `flexibilitywomen.jpg`→`women-flex.jpg`), all guarded now by `test_local_asset_library_has_no_silently_dropped_entries`.

**Still open (not built)**
- Live-sheet reading for `asset_library`/`metric_asset_groups` (still using the local hardcoded fallback) — and more broadly, there is no orchestration script anywhere that pulls live sheet data at all (`generate_full_report()` takes already-fetched data as parameters). This needs its own scoping session covering all data, not just assets.
- `client_type` "child" value + actually reading it (code currently only reads `gender`).
- Child-specific art (none exists yet for any client-type-based component).
- Balance pose icons (no assets exist).

**Explicitly not decided here**: whether Child rows with no image should render blank or fall back to a generic/adult image as a stopgap; whether `client_type` should also gate anything beyond images (e.g. exercise selection, target ranges); the actual orchestration script design for live-sheet reads.

**Related**: `F04-S05_table_heatmap_card.md`, `F05-S06_gender_image_card.md` — as-built sections both updated 2026-07-01 with this session's specifics.
