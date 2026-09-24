# F06-S04 — New Component: Hand Grip Strength (+ Walk-In Tab) — NEW 2026-08-29

**Status: does not exist. New component (tracked clients) + new standalone Walk-In tab (untracked/event entries), both needed together per Arun's actual ask.**

**Verified by:** Claude Chat, 2026-08-29 — confirmed directly against the repo: `METRIC_MAP`/`SECTIONS` pattern in `Code.gs`/`index.html` (no 3+ option field type exists — only `toggle` (2-option, binary encoding) and `time`); `NUDGE_METRIC_CONFIG`/`_headline()` in `report_query.py` are numeric-only (fine here — grade is a separate manual field, not the headline metric); `nudge_template.html`'s headline block is unconditional (needs a conditional wrap for the no-headline layout); `report_service/app.py`'s `_ALL_COMPONENTS` is a whitelist of 8 (safe default — new components are Full-Report-excluded until explicitly added); **no WhatsApp send integration exists anywhere in the codebase** — grepped `whatsapp|wa.me|twilio` across `.py`/`.gs`/`.html`, only hit is `nudge_png.py`'s design-reference comment ("WhatsApp Card"). Every Nudge today is a downloadable PNG, sent manually by Arun. Also confirmed against `insight_context_handoff_v2.md`'s referenced planning conversations: the future 4-tab IA (Clients/Assess/Reports/Admin) has no concept of non-client data — this card's Walk-In tab is new ground, not a gap-fill of an existing plan. The build itself is unbuilt — spec only.

**Context**
Two genuinely separate use cases surfaced during scoping, not one:
1. **Tracked clients** — Grip Strength as a normal Layer 2 assessment metric, entered through the existing Assess flow, feeding that client's real history/Nudge/reports like any other component.
2. **Walk-in gym challenge** — untracked people, fast one-row entry, disposable data, needs its own shareable card and (later, not now) a leaderboard. No client record, no `client_id`.

Trying to fold #2 into the existing Assess/Log flow doesn't work — every existing write path assumes a real `client_id`. Decision: **separate top-level tab, "Walk-In,"** not a mode inside an existing tab.

**Wireframe**
Visual reference rendered and shown to Uma this session, matching the actual live `nudge_template.html` styling (300px card, #880e4f magenta, white rounded inner card — not the older, stale WF-04 spec in `insight_wireframes_v6.html`, which uses a different canvas size/color and predates the real build). Same layout serves both Part A (tracked client) and Part B (walk-in) — only the name source and write path differ, the rendered card is identical.

Below is the actual modified template markup, not just a mockup — Claude Code can diff this directly against the live `nudge_template.html` rather than re-deriving the layout from prose:
```html
<!-- headline block removed entirely for this component — no {% if %},
     just don't render it when the payload has no headline_value -->

{% if stat_boxes %}
<div style="display:flex;gap:8px;margin-top:18px;">
  {% for box in stat_boxes %}
  <div style="background:#f4eef1;border-radius:10px;padding:12px 8px;text-align:center;">
    <div style="font-size:9px;color:#6b7280;letter-spacing:0.04em;">{{ box.label }}</div>
    <div style="font-size:22px;font-weight:800;color:#880e4f;margin-top:4px;">{{ box.value }} kg</div>
    {% if box.grade %}
    <div style="font-size:10px;color:#6b7280;margin-top:2px;">{{ box.grade }}</div>
    {% endif %}
  </div>
  {% endfor %}
</div>
{% endif %}
```
Note the existing box markup's `{% if box.unit == '%' %}` / uppercase-unit logic doesn't apply here — Grip Strength boxes always show `kg` and optionally a grade line, simpler than the general-purpose box the template currently supports for other components.

**Part A — Grip Strength component (tracked clients)**

**Input data**
```
New component: grip_strength

New metrics (METRIC_MAP + metric_master):
  grip_right_trial_1, grip_right_trial_2, grip_right_trial_3   (kg, numeric)
  grip_left_trial_1,  grip_left_trial_2,  grip_left_trial_3    (kg, numeric)
  grip_right_grade, grip_left_grade   (Poor | Average | Good — new field type, see below)

Best-of-3 per hand: max(trial_1, trial_2, trial_3), ignoring blanks, computed at
render time — never stored, same pattern as BMI/waist-hip ratio. All 3 blank for
a hand = no reading for that hand, not an error.
```

**New form field type — `select` (`Code.gs`/`index.html`)**
No existing type fits 3+ options: `toggle` is hardcoded to 2 buttons, binary "1"/"0" storage. A new, separate `select` type — native `<select>`, stores the chosen label text directly (`"Poor"`/`"Average"`/`"Good"`), no index encoding — avoids touching the existing `ankle_assessment` toggle decode logic. Config shape: `{ id: "grip_right_grade", label: "Right Hand Grade", type: "select", options: ["Poor","Average","Good"] }`.

**Full assessment form section (`index.html` SECTIONS)**
```
{ id: "grip_strength", label: "Hand Grip Strength", fields: [
    { id: "grip_right_trial_1", label: "Right — Trial 1 (kg)", step: 0.1 },
    { id: "grip_right_trial_2", label: "Right — Trial 2 (kg)", step: 0.1 },
    { id: "grip_right_trial_3", label: "Right — Trial 3 (kg)", step: 0.1 },
    { id: "grip_right_grade",   label: "Right Hand Grade", type: "select", options: ["Poor","Average","Good"] },
    { id: "grip_left_trial_1",  label: "Left — Trial 1 (kg)",  step: 0.1 },
    { id: "grip_left_trial_2",  label: "Left — Trial 2 (kg)",  step: 0.1 },
    { id: "grip_left_trial_3",  label: "Left — Trial 3 (kg)",  step: 0.1 },
    { id: "grip_left_grade",    label: "Left Hand Grade", type: "select", options: ["Poor","Average","Good"] }
]}
```

**Nudge rendering — new special case in `report_query.py`, not a `NUDGE_METRIC_CONFIG` entry**
`NUDGE_METRIC_CONFIG` assumes 1 headline + up to 2 numeric-only boxes via `_headline()`'s delta math. Grip Strength doesn't fit (no single headline; boxes need value *and* grade). Third special case alongside the existing `body_vitals`/`body_measurements` branches:
1. Compute best-of-3 per hand.
2. Return two stat boxes: `{label: "RIGHT HAND", value: <kg>, grade: <text>}`, `{label: "LEFT HAND", value: <kg>, grade: <text>}`.
3. No headline caption/value — payload omits/nulls these.

**Nudge template change (`nudge_template.html`)**
1. Wrap the headline block in a conditional (`{% if headline_value %}`) — currently always renders. Adjust stat-box top margin when headline is absent.
2. Extend the stat-box markup to show a second line (grade) under the kg value — current box only renders `box.value` + `box.label`.

**Full Report exclusion**
Do not add `grip_strength` to `report_service/app.py`'s `_ALL_COMPONENTS` — this alone blocks it server-side (already the working pattern for `ankle_assessment`/`skinfold_measurements`). Additionally mirror that whitelist client-side: new `FULL_REPORT_COMPONENTS` array in `Code.gs`, used to filter `renderComponentGrid()` when `RC.outputType === "full_report"` — today Nudge and Full Report share one unfiltered list; this is the first component that actually needs the split.

**Part B — Walk-In tab (untracked entries)**

**New top-level tab, "Walk-In"** — 4th tab alongside Log/Assess/Share, not a mode inside any of them (no existing tab has a concept of data without a `client_id`).

```
Walk-In tab, single-screen form:
  Name (required, free text — no client lookup, no "+ New Client" panel)
  Phone (required — used for the wa.me link, not stored for any send API, since
         none exists)
  Right: Trial 1 (kg), Trial 2 (kg), Trial 3 (kg), Grade (Poor/Average/Good)
  Left:  Trial 1 (kg), Trial 2 (kg), Trial 3 (kg), Grade (Poor/Average/Good)
  [Generate & Log] button
```

**On submit:**
1. Write one row to a new sheet, e.g. `grip_strength_walkins`: name, phone, date, 6 trial values, 2 grades. Never touches `readings`, never linked to any `client_id`. Schema stores raw trial values (not pre-computed best-of-3) — same "derive at read time" convention as the tracked-client path, so a future leaderboard reads this sheet directly without needing a migration.
2. Generate the Nudge PNG **inline, synchronously, from the submitted form values** — not via `report_query.build_nudge_payload()` (which reads from Sheets by `client_id`). This is a genuinely separate code path: same template/renderer (`nudge_png.py`, same two-box-no-headline layout as Part A), fed directly from the values just submitted. Name field substitutes for `client_name` in the card.
3. Response shows: PNG download link + a `https://wa.me/<phone>?text=...` link (phone digits only, no API call — just opens WhatsApp with that contact, Arun attaches the PNG himself, same manual-send pattern every other Nudge already uses).

**Leaderboard — explicitly out of scope for this card**, per Arun ("not now"). The schema above is deliberately leaderboard-ready (raw trials stored, best-of-3 derivable) so building the ranked view later doesn't require reshaping this sheet.

**Technical requirements**
1. Unit tests: best-of-3 computation (all present / partial blanks / all blank), `select` field type save/decode round-trip, Nudge payload omits headline cleanly, Full Report rejects `grip_strength` (server-side clean-400), Apps Script Full Report grid excludes it while Nudge/Walk-In include it, Walk-In inline generation produces a correct PNG without any Sheets read for the person's data, `wa.me` link correctly strips non-digit characters from phone input
2. Keep `Code.gs`'s `FULL_REPORT_COMPONENTS` and Python's `_ALL_COMPONENTS` in sync manually — same cross-language duplication `METRIC_MAP` already has, not solving that here
3. `qc_report.py` — confirm it doesn't choke on a headline-less Nudge card

**Acceptance criteria**
1. Tracked client: trainer enters 3+3 trials and Right/Left grades via the full assessment form; Nudge for `grip_strength` shows two stat boxes (kg + grade per hand), no headline; Full Report picker never shows "Hand Grip Strength" as selectable; a direct malformed request with it in Full Report's `component_ids` still gets a clean server-side rejection
2. Walk-in: trainer enters name, phone, 3+3 trials, grades on the new Walk-In tab; submit writes to `grip_strength_walkins` (not `readings`); a Nudge PNG renders immediately using the submitted name, no client lookup; download link + working `wa.me` link both appear

**Dependencies**
`F06-S02` (Report Config redesign — component grid pattern this reuses for Part A). `F05-S07`/`F05-S09` (Cloud Run bridge — reused for Part A's report-time rendering; Part B's inline generation is a new, separate path and does not go through the Cloud Run bridge at all — it renders synchronously in Apps Script/report_service directly from submitted values, no client_id round-trip needed).

**Out of scope**
- Leaderboard view/ranking UI — schema is ready for it, view is not being built now
- Any WhatsApp send automation (API/Twilio/etc.) — `wa.me` link only, no integration exists or is being added
- Adding `grip_strength` to Full Report once a chart type is decided — future card
- Retroactively fixing `ankle_assessment`/`skinfold_measurements`'s client-side Full Report exclusion — already excluded server-side; this card's mechanism makes extending that a one-liner later, but confirm with Uma before bundling it in
- Reference-range logic for the grade dropdown (auto-suggesting a grade from the kg value) — trainer's manual judgment call by design
- Converting a Walk-In entry into a real client record later (if a walk-in signs up) — real scenario, not building it unless it actually comes up
- **Noted for future, not scoped:** per-walk-in video capture during the grip test + an auto-generated collage reel highlighting the best performer(s) at each gym. Flagged by Arun 2026-08-29 as a likely next ask, not part of this build. Whatever schema/storage this card lands on for `grip_strength_walkins` should stay mindful that a video reference (Drive file ID or similar) may need to attach to each row later — don't design the sheet in a way that makes adding that column awkward, but do not build video capture/reel generation now.


---

## AMENDMENT — 2026-09-24: card redesign + gym registry

**Status: built, tests green, not yet deployed.** Delivered as a 4-phase plan against the live pipeline. This amendment records what changed from the spec above; where the two disagree, this section is current.

### 1. The Nudge card for `grip_strength` is now its own design

The spec above extended `nudge_template.html` (300×296 generic card) with a conditional headline and a grade line. That shipped and worked, but Arun's redesign replaced it: `grip_strength` now renders from **`templates/grip_nudge_template.html`**, a 1024×1536 portrait card exported from Claude Design — photographic masthead, V-edge clip-path, two fixed hand panels (crimson right / pine left), quote block, contact footer. It shares no markup with the generic card.

Routing is by component, in `nudge_png._render_template()`: `grip_strength` → `_render_grip_template()`, the other six components keep `nudge_template.html` untouched. The generic card's conditional-headline and grade-line changes from the original build stay in place — other components still use them.

Supporting changes:
- **Fonts are bundled, not linked.** The Cloud Run image installs only `fonts-liberation`, and this layout's letter-spacing is load-bearing, so a Google Fonts `<link>` would silently ship a broken card. Five latin-subset `.woff2` files in `assets/fonts/` are inlined as `@font-face` data URIs by `_font_face_css()`.
- **All assets inlined.** The render HTML is written to a system temp dir, so relative paths resolve to nothing; hero/logo/mountain go in as base64 via `_asset_b64()`.
- **Viewport split** in `render_report.js`: png mode 1024×1536, pdf mode unchanged at 1200×900.
- **Real client name.** `fetch_client_profile()` now also returns `full_name`, threaded through as `client_name` — the old `client_id`-derived guess ("dr_pavan" → "Dr Pavan") was acceptable on the small card but reads poorly in the 25px name slot.
- **Both hands are mandatory.** Per Arun: "this case shouldn't and won't happen — always ensure both hands are done." Enforced at data entry on both forms, and `_hand()` raises `ValueError` rather than rendering a card with one blank 100px numeral.

### 2. New: gym registry (Gym Name + Gym Logo)

Added to the card's scope after the redesign. Every walk-in entry and every new client is tied to a gym, and the gym appears on the generated card.

**New `gyms` sheet tab:** `gym_id`, `gym_name`, `logo_file_id`, `active`, `created_at`. Trainer-maintained from the Gym Challenge tab — there is no admin screen.

**Schema changes to existing tabs** — `gym_id`, `gym_name` appended to the **end** of both `grip_strength_walkins` and `client_info`, via `_ensureTrailingColumns()`, so existing rows stay column-aligned and simply read blank. `gym_name` is denormalised next to `gym_id` so a historical row still reads correctly after a gym is renamed or deactivated.

**Logo storage:** the file goes to a `Gym Logos` Drive folder; only the file ID is stored in the sheet (a base64 logo would blow Sheets' 50k-character cell cap). Upload path is browser `FileReader` → base64 → `google.script.run` (which cannot accept a `File` object) → `Utilities.newBlob` → `DriveApp.createFile`. Capped at 1MB client-side.

**Why Apps Script resolves the logo, not the report service:** the logo file is owned by the Apps Script OAuth user, and the Cloud Run service account has no access to that Drive. So `_gymLogoDataUri()` reads the file and ships it in the nudge payload as an inline `data:` URI. An unreadable file (deleted, permissions changed) degrades to `""` and the card falls back to its house footer.

**Card slots:**
| Slot | With gym | Without |
|---|---|---|
| Meta strip, column 3 | `GYM / <gym name>` | `TEST / Hand Grip Strength` (unchanged) |
| Footer, right corner | gym logo, right-aligned, ≤78px tall × ≤200px wide | `MOVE BETTER / FEEL BETTER / LIVE BOLDER` (unchanged) |

The two slots branch independently: a gym row with no uploaded logo fills the name and keeps the house footer.

**Only inline `data:image/...` URIs are accepted** for the logo — rejected at the service boundary (`_validate_gym_fields`) and again at the renderer (`_safe_logo`). A remote URL would make the Puppeteer render reach out to an outside host at render time.

### 3. Meta strip is no longer a fixed-height band

A long gym name ("Anna Nagar Strength & Conditioning Centre") wrapped to three lines and pushed against the bottom edge of the 129px strip. Two rejected fixes, for the record: clamping to two lines with an ellipsis truncated a real gym's name on their own card, and stepping the font down made the gym cell smaller than its neighbours.

Resolved by making the layout yield instead of the content: the strip is `min-height: 129px` (short names still measure exactly 129px, so those cards are byte-identical to before), the footer's padding went 30/34 → 24/24 to fund the growth, the column dividers are centred rather than top-anchored, and the card itself is `min-height: 1536px`. Result: names up to three lines print at the designed 25px inside a standard 1024×1536 PNG; only an extreme name (~80 chars) extends the canvas, which now grows rather than clipping the footer. 1024×1536 was the design's export size, not a constraint.

### 4. UI changes (`apps_script/index.html`)

- Tab label **"Walk-In" → "Gym Challenge"** (element ids unchanged).
- New Gym card at the top of that tab: required gym dropdown + inline add-gym panel (name, logo file picker with thumbnail preview and remove link).
- Gym dropdown (optional) added to the New Client panel.
- The old "Walk-In" section label within the tab is now "Participant".
- **Last-gym memory** via `PropertiesService.getUserProperties()` (`LAST_GYM_ID`) — a gym challenge runs at one venue for a whole session, so re-picking the gym on every entry is pure friction. `localStorage` was rejected as unreliable inside the HtmlService sandboxed iframe.
- Both-hands validation (`_gripHandIssues`) on the Gym Challenge form and, when any grip field is touched, on the full Assess form.

### 5. Bug found and fixed during verification

`_ALL_COMPONENTS` in `report_service/app.py` gated **both** the full-report and the nudge endpoints. Per this spec `grip_strength` is deliberately excluded from it so Full Report rejects it — which meant `/generate-nudge` was returning a clean 400 for every **tracked-client** grip nudge. Part B walk-ins never hit that validator, which is why it went unnoticed through the original build and verification.

Split into two sets: `_ALL_COMPONENTS` (Full Report, unchanged, still rejects `grip_strength`) and `_NUDGE_COMPONENTS = _ALL_COMPONENTS | {"grip_strength"}`. Both behaviours are now pinned by tests.

The spec's `FULL_REPORT_COMPONENTS` client-side mirror was never built and is still not built — the server-side whitelist remains the only enforcement, as it is for `ankle_assessment`/`skinfold_measurements`.

### 6. Tests

`tests/test_nudge_png.py` — grip template routing, slot mapping, 1dp formatting, missing-hand `ValueError`, label-not-position hand lookup, bundled fonts, no network font/asset references, and the gym slots (both fallbacks, remote-URL refusal, full-size long name).
`tests/test_report_service_validation.py` (new) — the gym field validators on both endpoints, and the two whitelists' differing behaviour.
Full suite: **262 passed**. The Node/Puppeteer subprocess stays out of scope, same as the rest of these files; the rendered PNGs were reviewed by eye (`gripstrengthredesign/preview/`).

### 7. Deploy note

The script now uses `DriveApp`, so **Apps Script will prompt to re-authorise the Drive scope on first run** after this deploy.
