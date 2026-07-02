# F04-S06 — Speed, Agility, Multi-Trial Strength (NEXT WEEK — not for this week's deliverable)

**Status: backlog placeholder, not scoped, not estimated.** Captured from Uma's sample review (2026-06-27) so it doesn't get lost — confirmed explicitly out of scope for Saturday's report.

**Context**
Karthik's real sample (the only one of the 7 reviewed with this data) shows two patterns not currently in `metric_master` or any built chart type:
- **Speed (35m) and Agility**, each shown with side-by-side **"Trial 1" / "Trial 2"** columns for a single date — doesn't fit the current unique key model (`date+component+metric+client_id`) without adding a trial-number dimension.
- **1RM Strength** (single value, e.g. bench press in kg) — straightforward as a new metric, but pair it with the trial-column question since both surfaced from the same sample.

This was already noted as an open question in the handoff doc (Section 1) before this review; this card exists so it has a home of its own rather than staying a buried bullet.

**Open questions for next week, not decided here**
1. Does the trial dimension get added to the unique key (`date+component+metric+trial+client_id`), or handled as a side-table/JSON blob per reading? Changing the unique key touches the data model Uma has called genuinely locked elsewhere (upsert/delete semantics) — needs care, not a quick patch.
2. Is multi-trial display a new chart mode on `render_bar`/`render_table_heatmap`, or its own small renderer? Two trials side-by-side per metric resembles `stacked_pair`'s shape (two values, one bar/row) but is conceptually different — trials aren't being compared as parts of a whole, they're repeated attempts.
3. Only Karthik's sample shows this — confirm whether VIP/Thilak/the other 2 pilot clients are expected to ever have multi-trial data, or whether this is genuinely Karthik-specific and can stay deferred indefinitely without affecting the pilot.

**Dependencies**
None for Saturday. Likely touches `metric_master` (new metrics), the unique-key model (trial dimension), and either `F04-S02_S03_S04` or a new renderer.
