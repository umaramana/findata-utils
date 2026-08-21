# F06-S03 — Log Tab: Show All 7 Body Vitals Fields

**Status: not started.**

**Context**
Surfaced during a live bug-fix session (2026-08-21) on the Nudge "Could not read client data from Sheets" / "shows a check-in update for BP+Pulse readings" report. Root-causing that bug (fixed in the same session — see `project_insight_core.md` session 13 notes and `report_query.py`'s `build_nudge_payload()`) exposed a wrong assumption baked into the code: a comment claimed the Log tab and Assess tab write disjoint sets of `body_vitals` metrics (Log = weight/fat/muscle, Assess = BP/pulse/height). That's false — checked `apps_script/index.html`: the Assess tab's body_vitals section already has all 7 fields (`weight_kg`, `fat_pct`, `muscle_pct`, `bp_systol`, `bp_diastol`, `bpm`, `height_cm`); Log only exposes 3 of those same 7. There is no metric-id split between the two forms and the readings sheet has no field recording which form wrote a row (`source` column is hardcoded `"form"` by both write paths in `Code.gs`).

User's framing of what Log is actually for: a quick, irregular capture the trainer does regularly, of *whichever* body vitals happen to be relevant that visit — not a fixed 3-metric set, and the relevant set "may also change for each client at any point." The current hardcoded 3-field Log form doesn't match that model; it's an arbitrary historical narrowing (built in F02-S02, before Assess existed as a separate concept).

**Decision (made 2026-08-21, via user-selected option)**
Considered three alternatives:
1. Log always shows all 7 fields (same set as Assess), trainer fills in whichever apply, blanks skipped — **selected**.
2. New per-client configurable field set (new sheet column(s)/tab + admin/edit UI + Log tab reads it dynamically) — rejected as more moving parts than the problem needs.
3. Per-trainer global default + per-client override — rejected, two config layers to design/build for a single-trainer pilot.

Option 1 was chosen because it needs no new config storage or admin UI, and directly satisfies "could be any of the body vitals" (all are always available) and "changes per client at any point" (nothing is fixed — it's just which fields the trainer fills in that visit, same as Assess already works).

**Scope**

*`apps_script/index.html` — Log tab (`panel-checkin`)*
1. Log tab's body_vitals input section grows from 3 fields (weight, fat%, muscle%) to all 7 (weight, fat%, muscle%, BP systolic, BP diastolic, pulse, height) — same field list/order/step values Assess already uses (see `index.html:962-968`'s `fields` array for the canonical set; Log's markup currently hardcodes just the first 3 of these directly rather than sharing that array — reconcile during build, don't fork a second copy of the field list).
2. Apply the existing compact-row / view-edit-widget pattern already used elsewhere in Log and Assess — no new layout pattern needed.
3. Partial-save semantics unchanged: blank field = skip (not stored), matches existing `submitReadings()` upsert behavior already in `Code.gs`.

*`apps_script/Code.gs`*
1. Check `submitReadings()` (the Log tab's write path, `Code.gs:149` today) — currently only reads `weight_kg`/`fat_pct`/`muscle_pct` off the incoming payload. Extend to accept and upsert all 7 `body_vitals` metric ids, reusing `METRIC_MAP` the same way `submitFullAssessment()` already does, rather than keeping Log on its own narrower hardcoded write path.
2. No `component_master`/`metric_master` changes — all 7 metrics already exist there under `body_vitals`.

**Explicitly NOT in scope**
- Any new `source` column tagging ("checkin" vs "assessment") — confirmed not needed for this fix; flagged only as a possible future item if a real need for it shows up.
- Any change to the Assess tab — it already has all 7 fields, this card only brings Log up to parity.
- Any change to Nudge/Full Report rendering logic (`report_query.py`) — already fixed separately this session, unaffected by Log's field count.
- Per-client or per-trainer configurability (rejected alternatives 2/3 above).

**Input data**
No new sheet columns or config. Log tab payload shape grows from `{weight_kg, fat_pct, muscle_pct}` to the same 7-key shape `submitFullAssessment()`'s body_vitals section already sends.

**Technical requirements**
1. Unit/manual test: submitting Log with only a subset of the 7 fields filled (e.g. just BP + pulse, matching the bug report that started this) upserts only those metrics, leaves others untouched — same partial-save behavior Assess already has.
2. Regression: existing Log flows that only fill weight/fat/muscle must keep working unchanged (backward compatible field growth, not a breaking change).
3. Prefill-on-existing-date behavior (`getReadings()`) must populate all 7 fields when reopening a date that has them, not just the original 3.

**Acceptance criteria**
1. Log tab shows 7 body-vitals input rows (compact-row style), matching Assess's field set exactly.
2. Saving Log with any subset of the 7 filled in stores exactly those readings.
3. Reopening a previously-logged date on the Log tab prefills all 7 fields correctly (view-mode widgets where data exists).
4. No regression to Assess tab, Nudge, or Full Report behavior.

**Dependencies**
None blocking — independent of `F06-S02` (already built/live-smoke-tested) and this session's Nudge date/headline fix (already built, pending deploy). Can be picked up any time.

**Open questions for next session**
- Should Log's 7-field layout differ visually from Assess's (e.g. grouped differently) given Log is meant to feel "quicker," or is an identical field list with the existing compact-row pattern quick enough as-is? Not resolved — worth a quick check-in with the user before building if it matters, otherwise default to reusing Assess's layout as-is.
