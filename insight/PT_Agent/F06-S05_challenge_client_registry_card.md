# F06-S05 — Gym Challenge: Saved Challenge Clients (pick-or-add, like Gyms)

**Status: specced 2026-09-28, not started.**
Sequence: 1 of 3 in the Gym Challenge batch (F06-S05 challenge clients → F06-S06 hero image → F06-S07 receipt generator move).

**Context**
The Gym Challenge tab (`panel-walkin`) takes Name and Phone as free text on every entry. Challenge participants come back for repeat visits, so Arun re-types the same people and the sheet ends up with spelling variants of one person. He wants the same pattern the tab already uses for gyms: a dropdown of saved people with a "+ Add new…" option that opens an inline panel.

**Decisions (user, 2026-09-28)**
1. **No new UI tab.** The change is inside the existing Gym Challenge tab: the Name field becomes a picker.
2. **Parallel track to PT clients.** Challenge clients are **not** added to `client_info`, and their grip entries do **not** go into `readings`. PT assessment (`client_info` + `readings` + Log/Assess/Share) and Gym Challenge (`challenge_clients` + `grip_strength_walkins`) stay separate.
3. **Two independent levels of client type:** program (PT / Challenge) sits above age category (Adult / Child). Program is implied by which registry a person is in; Adult/Child is a column on each registry. `client_info.client_type` already carries it for PT; `challenge_clients` gets its own.
4. **Phone number identifies a person**, not name.
5. **As simple as possible.** No edit UI, no merge tool and no backfill (see Out of scope).

**Upcoming context (NOT in this card):** visits may be free (FOC), including repeat visits. A later card will generate a payment receipt showing the INR amount struck through and marked FREE. That depends on F06-S07 (receipt generator move). Nothing here should block it: `challenge_client_id` on each walk-in row is enough for a receipt to link to later.

---

## Scope

### Sheet: new `challenge_clients` tab (lazily created, same as `gyms`)
| col | name | notes |
|---|---|---|
| A | `challenge_client_id` | slug from name, `_1`/`_2` suffix on clash (same rule as `addGym`/`addClient`) |
| B | `full_name` | |
| C | `phone` | stored normalised: digits only, last 10 digits (drops `+91`/`0` prefix) |
| D | `client_type` | `adult` / `child`; defaults to `adult` |
| E | `active` | `TRUE`; set `FALSE` by hand in the sheet to hide from the dropdown (same as gyms) |
| F | `created_at` | IST timestamp |

No gym column. A person can do the challenge at different gyms, and the gym is already recorded per entry on the walk-in row.

### Sheet: `grip_strength_walkins`
- Append a trailing `challenge_client_id` column via the existing `_ensureTrailingColumns()`. Existing rows read blank; no migration.
- `name` and `phone` stay on every row, **copied from the registry at submit time** (same reasoning as `gym_name`): a past entry still reads correctly if the person's name is later corrected in the registry.

### `apps_script/Code.gs`
1. `CHALLENGE_CLIENTS_TAB` constant + `_getOrCreateChallengeClientSheet()`, modelled on `_getOrCreateGymSheet()`.
2. `getChallengeClients()` → `{ clients: [{id, name, phone, client_type}] }`, active only, sorted by name.
3. `addChallengeClient({full_name, phone, client_type})`:
   - validates name and a 10-digit normalised phone
   - **phone clash:** doesn't create a duplicate. Returns `{id, name, existing: true}` for the person already saved under that phone, so the UI selects them and shows "Already saved as <name>" (same idea as the gym name clash, but it doesn't block the trainer)
   - otherwise appends and returns `{id, name, existing: false}`
4. `_normalisePhone(raw)` helper: shared by add and lookup, and applied to the payload before `submitWalkinGrip` writes.
5. `submitWalkinGrip(data)` accepts `challenge_client_id`, looks up the registry row, writes id + name + phone from the registry (not from the form), and fills the new trailing column. Unknown id throws "Challenge client not found."
6. `generateWalkinNudge(params)`: **no contract change** to the Cloud Run `/generate-walkin-nudge` route. The name and phone sent are still strings, now taken from the registry. No redeploy of `report-service` is needed for this card.

### `apps_script/index.html` — Gym Challenge tab
1. Replace the `walkinName` text input with a `<select id="walkinClient">`: "— select participant —", the saved clients shown as "Name · last 4 digits of phone" (so two people with the same name can be told apart), then "+ Add new participant…".
2. Picking "+ Add new…" opens an inline `addChallengeClientPanel` (reuses the `.add-client-panel` markup/CSS used by Add Gym) with Full Name, Phone and an Adult/Child toggle (reuse `.toggle-pair`, default Adult), plus Save / Cancel.
3. Save → `addChallengeClient` → reload the list and preselect the returned id. If `existing: true`, show "Already saved as <name>" under the picker instead of an error.
4. The `walkinPhone` input becomes **read-only display** of the selected client's phone (still needed for the `wa.me/` link on the result card). To fix a wrong number, edit the sheet (see Out of scope).
5. **No "remember last participant."** Unlike the gym, every entry is a different person, so the picker resets to the placeholder after each successful submit (the gym stays remembered as today).
6. Load the list once per page, when the tab is first opened, the same way `GYMS.loaded` works.
7. Validation: participant required (replaces the "Name is required" error).

### Tests
Apps Script has no automated tests in this repo (as with gyms), so the checks below are manual on the Test deployment. No Python changes, so the Python suite should stay green without edits; run it anyway as a check that nothing else broke.

---

## Out of scope (deliberately)
- **Backfilling existing `grip_strength_walkins` rows** into the registry. They stay as history with a blank `challenge_client_id`. A backfill-by-phone script can come later if a leaderboard or visit history needs it.
- **Edit/rename/deactivate UI.** Fix a typo or deactivate someone directly in the `challenge_clients` sheet, same as gyms today.
- **Converting a challenge client to a PT client.** Parallel tracks. If it's ever needed, it's a manual `addClient` using the same phone.
- **Visit count, FOC/paid flag and receipts:** a later card, after F06-S07.
- **DOB/age and gender.** Not captured. Add them when grip level is auto-calculated instead of read off the dynamometer (trailing columns via `_ensureTrailingColumns`, no migration).
- **Search/typeahead.** A native `<select>` is fine at pilot scale. Revisit if the list passes ~50 people.
- Any change to the Log/Assess/Share tabs, `client_info`, `readings` or report-service.

## Acceptance criteria
1. The Gym Challenge tab shows a participant dropdown of saved challenge clients, with "+ Add new participant…" at the bottom.
2. Adding a new participant saves one row to `challenge_clients` and preselects them.
3. Adding a phone number that already exists (typed with or without `+91`, spaces or a leading 0) creates no new row. It selects the existing person and says so.
4. Submitting an entry writes a `grip_strength_walkins` row with `challenge_client_id`, plus name/phone copied from the registry.
5. The nudge PNG and `wa.me` link still work unchanged.
6. The participant picker resets after submit; the gym stays selected.
7. Existing walk-in rows are untouched; PT client dropdowns (Log/Assess/Share) never show challenge clients.

## Deploy
Apps Script only: paste `Code.gs` + `index.html` into the Test deployment → verify → promote. **After redeploy, check that "Execute as: Me" is still set** (it regressed in Session 16/17).

## Dependencies
- None blocking. (F06-S04 is already committed, 4d69fb2…2ab7040.)
- Doesn't block F06-S06 (photo is per visit, decided 2026-09-28).
- `_normalisePhone()` is shared with F06-S07; whichever card is built first adds it.
