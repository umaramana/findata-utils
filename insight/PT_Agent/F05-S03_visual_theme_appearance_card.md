# F05-S03 — Visual Theme & Appearance Configuration (IDEAS DUMP — not for this week's build)

**Status: not scoped, not estimated, not ready for Claude Code.** This is a context capture from Uma's review session (2026-06-27) so the ideas survive until next week's planning. Treat everything below as raw material, not a spec — Build/Acceptance sections are intentionally thin or absent.

**Sleeve mechanism — decided shape, not yet built (2026-06-28)**
"Canva template" in the current build is just 4 standalone chrome assets the code injects, not a complex per-template Canva project: **logo, side vertical strip, background (4-dotted-corner pattern), thank-you-page image.** **Default magenta set received and measured 2026-06-28** — see `insight_context_handoff_v2.md` Section 1 for exact pixel dimensions (1024×768 canvas, chrome footprint). **Logo placement resolved (2026-06-28):** the 400×400 square carries the full lockup (yoga-pose icon + wordmark + "Holistic fitness.." tagline) — that's the cover-page hero logo. The 200×100 rectangle is the bare wordmark only — that's the compact header logo on every content page. Both supplied, use whichever fits the placement. A future Male/Female/Child sleeve would still need both size variants per client_type, not just one.

**Header/footer system decomposed into individual pieces, confirmed 2026-06-29 — see `F05-S05`'s card for the implementation spec.** Same left strip already measured, now split into reusable parts for the future infographic/mobile templates (`F06-S01`) rather than one flat fixed-size background: **2-tone, header (black) + flexi-height footer (magenta #741b47).** Explicitly **not** 3-tone — a third "midrib" zone was considered and rejected, no defined purpose, would be net-new scope for no stated reason. **Seal text confirmed final: "BUILDING A STRONGER"** — `Insight_Green_Circle_Logo.png` (standalone, says "FOR A STRONGER") is a stale/wrong variant, don't use it; use `insight_rightlogo.png` or any asset with "BUILDING A STRONGER" baked in.

A "sleeve" swap is therefore just swapping which files get injected in `F05-S05` — same renderers, same layout, same Pagewise PDF template, just different chrome. This reuses `F05-S06`'s exact `asset_library` pattern rather than inventing a new mechanism:

```
theme_assets: client_type | asset_role | image_ref
  client_type: M | F | CHILD
  asset_role: logo | side_strip | background | thank_you_page
```

Three client_types × four roles = 12 rows once populated. Lookup logic mirrors `F05-S06`'s exactly (exact match → fallback → null-safe).

**Open question, not decided — chrome-only or chrome+charts?** Does the sleeve swap *just* the 4 chrome assets (charts stay magenta regardless of client type), or do chart colours need to switch too, so a blue sleeve doesn't have magenta bars sitting inside it looking mismatched? Chrome-only is close to free — a lookup + injection step, no changes to already-built `F04` renderers. Chrome+charts means reopening `F04-S02_S03_S04` and `F04-S05` to parameterize colour, which is real rework, not a quick add. Uma's "Male/Female/Child" framing suggests both moving together, but this hasn't been explicitly confirmed — don't build either direction without checking.

**Still-open gap, now more load-bearing:** "Child" isn't a tracked client attribute anywhere in the data model (no age/category field exists). It was already flagged as a gap for the gendered Physio icons; now it also decides which sleeve (including which thank-you-page graphic) gets picked. Needs an actual field, not an inference, before this is buildable.

**Relationship to template architecture (see `F06-S01_template_architecture_vision_card.md`):** sleeve theming is an orthogonal axis to template *type*. A sleeve swap (logo/strip/background/thank-you by client type) should work the same way whether the underlying report is this week's Pagewise PDF, or a future Infographic or Mobile template — it's "what chrome wraps the content," not "how the content is arranged." Keep these two cards' scopes separate even though they were raised in the same conversation.

**Context — why this exists**
Current default is a single magenta gradient theme (locked, built into `F04-S02_S03_S04` and `F04-S05`, not changing this week). Confirmed direction from Uma: **the theme should eventually be client-type-driven** — magenta for women, blue for men, green for children — applied to header/footer and presumably chart colours together. Separately, **nudge cards specifically should let the trainer pick a colour scheme** (different control surface than the full-report default). Neither is in scope for Saturday's deliverable; both are flagged as next priority after.

**Real-world evidence this is needed:** Uma's sample review surfaced one real PDF using a blue theme instead of magenta — this isn't speculative, an actual report already exists in a non-default palette.

**Open question Uma raised, to think about before next week:** should colour be purely client-type-driven (one theme per client, everything in the report matches), or should individual **components** also carry their own colour identity (e.g. physio is always teal, balance is always a different hue, body composition another) so a trainer flipping through pages gets visual consistency/memorability across different clients' reports, independent of which client-type theme is active? These are two different axes (client theme vs. component identity) and could coexist or conflict — worth deciding which problem is actually being solved before designing the mechanism.

**Alternative directions — none chosen, for discussion next week**

| Option | How it works | Pros | Cons |
|---|---|---|---|
| A — Pure client-type theme | One of 3 fixed palettes (magenta/blue/green) applied globally based on client gender/age category; everything (header, footer, charts) swaps together | Simplest to build and reason about; matches Uma's stated direction directly | No per-component visual identity; a children's green report looks structurally identical to an adult one besides hue |
| B — Per-component colour identity | Each `component_master` row gets an assigned hue, consistent across all clients/themes (e.g. physio = teal always) | Builds visual memory/scanability across reports regardless of client | Conflicts with "header/footer matches client type" unless layered carefully; more moving parts |
| C — Hybrid (client-type hue family + per-component shade) | Client-type picks a base hue family (magenta/blue/green); each component gets a different *shade* within that family, similar to how the heatmap's existing 8-stop gradient already assigns shades by value | Gets both client-type branding and some component consistency; reuses the gradient-generation pattern already built for the heatmap | More design work to get shade assignments that read well; needs care to avoid the gradient brightness-spike issue already solved once for magenta |
| D — Trainer-picks-per-report override | Trainer selects a theme at report-generation time (like the existing grid-density picker), independent of client-type defaults | Matches the nudge-card request directly; simplest mental model for the trainer | Loses the "visual memory" auto-association Uma is exploring; pure preference, no semantic meaning |
| E — Layered (client-type default + trainer override) | Client-type theme auto-selected as default; trainer can override per-report or per-nudge from a picker | Covers both the auto-association goal and the nudge-card flexibility request in one system | Most complete, also the most build effort — two systems instead of one |

**Technical groundwork worth knowing about next week, not decided here:**
- The existing 8-stop magenta gradient (`F04-S05`'s as-built notes) is hand-tuned to avoid an R-channel brightness spike. If 3+ themes are needed, **a parameterized gradient generator (given a base hue, produce N visually-even stops) is worth building once**, rather than hand-tuning 3 separate palettes the same way.
- Theme presumably needs to cover **both** matplotlib chart colours **and** the Canva cover/content/closing template assets — those are separate files per theme unless Canva supports a parameterized recolour. This is a bigger scope than just changing hex codes in the Python renderer; check what F05-S05's Canva injection mechanism actually allows before assuming a simple swap.
- `F05-S06`'s `asset_library` already keys gender-aware images on `M`/`F`/`ANY` per client — **client gender is already a tracked attribute** if client-type theming keys off the same field. A "children" category doesn't have an existing attribute (age isn't currently part of the gender key) — would need a new field or a derived age-band lookup.
- **Missing-data display ("-" vs "No data") is also a candidate for this same trainer-configurable-appearance system** — Uma flagged wanting the trainer to eventually choose between the two, which is the same shape of problem as a theme picker (a per-report or per-trainer appearance preference). Worth bundling into whichever mechanism gets built here rather than a separate one-off toggle.

**Dependencies**
None for Saturday — explicitly deferred. Whatever gets decided here will likely touch already-built `F04-S02_S03_S04` and `F04-S05` (colour is hardcoded in both), plus `F05-S05`'s Canva injection step.
