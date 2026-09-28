# F06-S07 — Move the Payment Receipt Generator into Insight Core (new "Receipt" tab)

**Status: specced 2026-09-28, not started.**
Sequence: 3 of 3 in the Gym Challenge batch (F06-S05 challenge clients → F06-S06 hero photo → **F06-S07**). Independent of both; last because it's the largest and touches the Dockerfile.

**Context**
The receipt generator (`insight/insight_receiptgenerator/`, Express + Puppeteer) only runs on localhost. It keeps its own spreadsheet ("Insight PT Agent", `1gOS2Icl48Y427XTT1SBGx7_xXenRIzCLuOx01UheHCM`) with its own client list (`Client Details`) and a receipts log (`receipts`). It has its own OAuth token, which expires weekly. Arun can't use it from his phone. This card moves it into the Insight Core web app as a new tab.

**Decisions (user, 2026-09-28)**
1. **A move, not a redesign.** Same receipt layout, fields, joint mode, RCP-NNN numbering and log columns.
2. **One client list.** Receipts pick PT clients from `client_info`; the separate `Client Details` list is retired, not synced.
3. **Retire the local app once the tab works.**
4. **Migration is one client.** `Client Details` holds test rows plus **one** live client. He is a new PT client who is **not** yet in `client_info` (not yet assessed), and names are written the same way in both sheets. So there's no matching step. The user deletes the test rows; that one client is added through the app and his one receipt row is copied across by hand (see Migration).

**Upcoming context (NOT in this card):** a later card generates receipts for challenge clients (`challenge_clients`, F06-S05) showing the INR amount struck through and marked FREE. Keep the receipt template's amount cell a single block so that card can add a struck-through variant without reworking the layout.

---

## Scope

### Sheet: `client_info` — three trailing columns
`RECEIPT_COLS = ["phone", "email", "address"]`, added with `_ensureTrailingColumns()` the same way as `GYM_COLS`. Existing rows read blank; no migration.
`phone` is stored normalised with the same `_normalisePhone()` F06-S05 adds (last 10 digits). If F06-S07 is built first, this card adds the helper.

### Sheet: new `receipts` tab in `insight_pilot` (lazily created)
Same 8 columns as today, same order: `receipt_no, date_issued, client_id, client_name, month_year, amount, payment_method, transaction_id`. Joint receipts still write **two rows with the same `receipt_no`**. Name is copied onto the row (denormalised), so the log reads correctly even if a client is renamed.

### `apps_script/Code.gs`
1. `RECEIPTS_TAB` + `_getOrCreateReceiptsSheet()`.
2. `getReceiptClients()` → active `client_info` rows as `[{id, name, phone, email, address}]`. (`getClients()` stays `{id, name}`, so Log/Assess/Share are untouched.)
3. `getNextReceiptNo()` → scan column A for the highest `RCP-(\d+)`, return the next one padded to 3 digits (`RCP-001` when empty). This ports `server.js getNextReceiptNo()` exactly, and uses the **highest** number, not the last row, so a hand-edited row can't send numbering backwards.
4. `generateReceipt(params)`:
   - validates the same required fields as `server.js` (client, month, year, amount, payment method; amount2 when joint)
   - **saves phone/email/address back to `client_info`** if the trainer changed them in the form (this is how the fields get filled in, since there's no separate client-edit screen)
   - takes `LockService.getScriptLock()`, recomputes the receipt number **inside the lock** (the number shown on the form is a preview only), calls Cloud Run `/generate-receipt`, and **appends the log row(s) only after Cloud Run returns success**, then releases the lock
   - returns `{receipt_no, output_url}`
   - `date_issued` is today in IST (`TZ`), format `dd MMM yyyy` as today. Do **not** let Cloud Run pick the date: it runs in UTC and would stamp yesterday's date before 05:30 IST.

### `apps_script/index.html` — new "Receipt" tab
Port of `receipt_preview.html`'s form, using the shell's existing styles:
- Client picker (`getReceiptClients`), with Contact / Email / Address fields prefilled and editable.
- "Joint receipt" checkbox: shows a second client picker and splits Amount into two inputs.
- Month, Year, Amount, Payment Method, Transaction ID.
- Read-only "Receipt No." badge from `getNextReceiptNo()`, refreshed after each receipt.
- Generate → `generateReceipt` → result card with **Open PDF** (Drive link), like the Full Report result.
- **No live HTML preview** in this card. The local app's scaled preview (`fitPreview()`) is not ported; the PDF is the preview. Add it later only if Arun misses it.
- No "+ Add client" here. New PT clients are added from the Log tab as today; their contact details are filled in here on their first receipt.

### `report_service/app.py` — new `/generate-receipt` route
Same shape as `/generate-report`:
- validates the payload (strings only, amounts numeric > 0, `receipt_no` matches `RCP-\d+`)
- renders `templates/receipt_template.html`
- produces the A4 PDF
- uploads it to a new **"Receipts"** Drive folder next to `insight_pilot` (`drive_upload.RECEIPTS_FOLDER_NAME`, created through the existing `find_or_create_client_reports_folder(..., folder_name=...)`)
- shares it to Arun only, like reports
- returns `{status: "done", output_url}`

Cloud Run **never writes to the Sheet**: Apps Script owns the number and the log (item 4 above).
File name as today: `Receipt_<Name>[_<Name2>]_<Month><Year>.pdf`.

### `templates/receipt_template.html` (new)
`buildReceiptHTML()` from `server.js`, ported to the same Jinja-style templating `nudge_png`/`generate_report` use:
- same absolute positions, 1410x2000 canvas, scale 0.5631
- same `Rs. 12,345/-` en-IN formatting
- same joint second line-item row

Move `Insight Receipt BG Only.png` into `assets/receipt/` and embed it as base64 with `_asset_b64()`, the same way the grip card embeds its images. Bundle the fonts locally in `assets/`, like the grip card. Today the receipt pulls Poppins/Raleway from Google Fonts and Cooper Hewitt from `fonts.cdnfonts.com` at render time; a CDN hiccup would silently change the receipt's fonts. Confirm the license allows bundling Cooper Hewitt (it's SIL OFL, so it should).

### `render_report.js` — A4 mode
Add `--mode=a4`: viewport 794x1123, `page.pdf({format: 'A4', printBackground: true, margin: 0})`. This is exactly what `server.js` does today. The existing `pdf` mode (1200px continuous page for Full Report) is unchanged.

### Puppeteer independence (so the local folder can be deleted)
- `render_report.js` line 3: change `require('../insight_receiptgenerator/node_modules/puppeteer')` to `require('puppeteer')`.
- Add `insight_core/package.json` (Puppeteer only). Local dev runs `npm install` in `insight_core/` once.
- **Dockerfile:** install Puppeteer into `/app/insight_core` instead of the fake sibling `/app/insight_receiptgenerator`, and delete the comment block explaining the sibling trick. `report_service/package.json` becomes redundant; remove it.
- Container Puppeteer is `^23`, local is `^24.15`. Pin one version (`^24`) in the new `package.json` so local and Cloud Run match.

### Tests (Python)
- `tests/test_report_service_validation.py`: `/generate-receipt` payload rules (missing fields, non-numeric/zero amount, joint without amount2, bad `receipt_no`, non-string injection).
- `report_service/tests/test_app.py`: happy path uploads to the "Receipts" folder and returns `output_url` (mocked Drive, same pattern as the walk-in test).
- A render test: the template renders single and joint receipts, all values HTML-escaped (a client address containing `<script>` comes out inert), and the line breaks in the address are kept.
- Full suite stays green, including existing Full Report/Nudge tests after the `render_report.js` require change.

---

## Migration (one client, by hand)
1. User deletes the test rows from the old `Client Details` and `receipts` tabs.
2. After the new tab is deployed: Arun (or the user) adds the one live client through the **Log** tab's Add Client, then opens the Receipt tab, picks him and fills Contact/Email/Address. These are saved back to `client_info` on the next Generate, or the user types them straight into the three new `client_info` columns.
3. Copy his **existing receipt row(s)** from the old `receipts` tab into the new `receipts` tab in `insight_pilot`, changing `client_id` to his new `client_info` id. This keeps the RCP sequence going: the next receipt continues from his number instead of restarting at RCP-001.
4. **Reconciliation (mandatory):** before retiring the old sheet, check old vs new `receipts`: same count of real rows, same receipt numbers, same total amount. Then check that the Receipt tab's badge shows the next number after the highest copied one.
5. Old spreadsheet: leave it in place, read-only, as an archive. Don't delete it.

## Retiring the local app (after acceptance passes)
- Delete `insight/insight_receiptgenerator/` except `receipt_generator_spec.md`, which moves to `PT_Agent/` as history. Its `credentials.json`/`token.json` are gitignored, so delete them locally too; that removes one of the OAuth tokens that expires weekly.
- Do this in a **separate commit** after the Cloud Run deploy, so a revert is clean.
- Update memory (`project_insight_receipt_generator.md` → marked retired, pointing to this card) and `project_insight_core.md`.

---

## Out of scope
- Challenge-client / FREE receipts (next card).
- Emailing or WhatsApp-sending the receipt. Arun downloads/shares the PDF from Drive.
- Any change to the receipt layout, wording or numbering format.
- Editing or voiding an issued receipt. Fix it in the sheet by hand, as today.
- The live HTML preview (see index.html).
- Publishing the OAuth consent screen to Production. Still worth doing, but it's the report-service token, not this card.

## Acceptance criteria
1. The Receipt tab lists `client_info` clients; the one migrated client shows his contact details prefilled.
2. A single receipt generates a PDF that matches one made by the old local app with the same inputs, compared side by side (layout, fonts, amounts, date format).
3. A joint receipt shows two line items and the correct total, and writes two log rows with one receipt number.
4. The receipt number continues from the migrated row; two Generates in a row get consecutive numbers, never the same one.
5. The PDF lands in the "Receipts" Drive folder next to `insight_pilot`, shared with Arun only.
6. It works from Arun's phone.
7. Full Report and both Nudge routes still work after the Puppeteer/Dockerfile change (smoke-test one of each).
8. Reconciliation (Migration step 4) passes before the local app is removed.

## Deploy
One batch:
1. Cloud Run: `gcloud builds submit` + `gcloud run deploy` **from PowerShell**, then verify the `/secrets/oauth_token.json` mount. Smoke-test Full Report + Nudge + Receipt.
2. Apps Script paste → verify "Execute as: Me" is still set.
3. Migration + reconciliation.
4. Separate commit: retire the local app.

## Dependencies
- None blocking. (F06-S04 is already committed.)
- `_normalisePhone()` is shared with F06-S05; whichever card is built first adds it.
