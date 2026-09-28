# F06-S06 — Gym Challenge: Per-Visit Hero Photo on the Grip Card

**Status: specced 2026-09-28, not started.**
Sequence: 2 of 3 in the Gym Challenge batch (F06-S05 challenge clients → **F06-S06** → F06-S07 receipt generator move). Technically independent of F06-S05; built after it only so the Gym Challenge form is changed once, in order.

**Context**
The grip card (`templates/grip_nudge_template.html`, 1024x1536) has a V-edged hero panel that always shows the bundled template image (`assets/grip/man.png`, set in `nudge_png._render_grip_template()`). Arun wants the card to work as the participant's social-media share. That means a photo **from that visit** (e.g. mid-grip on the dynamometer) in the hero slot, falling back to the template image when none is given. The behaviour mirrors the gym logo: shown when present, house default when absent.

**Decision (user, 2026-09-28): per visit, not per client.** The photo belongs to one entry, not one person.
This is also **less** engineering than a per-client photo: nothing is stored. The photo travels with the one generate call, the same way `gym_logo` already does, and the generated PNG in Drive is the only lasting copy. A per-client photo would need a Drive folder, a file-id column and lookup code, like the gym logo has.

---

## Scope

### Flow (Gym Challenge tab only)
Form photo picker → downscaled in the browser → base64 `data:image/jpeg` → `generateWalkinNudge(params.hero_image)` → Apps Script passes it through unchanged → Cloud Run `/generate-walkin-nudge` → `nudge_png` puts it in the hero `<img>`.
**Not** sent to `submitWalkinGrip`: the photo never goes into the sheet or a Drive folder.

### `apps_script/index.html` — Gym Challenge tab
1. New optional row under the participant: **"Photo (optional)"**, `<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment">`. On a phone this offers camera or gallery.
2. **Downscale in the browser before upload** (a phone photo is 3–8 MB): draw onto a `<canvas>`, long edge capped at **1200 px** (the hero is 527x478 CSS px, so this covers 2x), export `image/jpeg` quality 0.85, which comes to ~150–400 KB. If the browser can't decode the file (e.g. HEIC on some Android builds), show "Couldn't read this photo — try a JPG" and keep going without a photo.
3. **Framing preview:** a small thumbnail using the **same `clip-path` polygon and gradient** as the card's hero panel, so Arun sees exactly what gets cut off by the V and darkened under the tagline before generating. To reframe, re-pick or retake the photo. No in-app crop tool.
4. **Consent checkbox**, shown and required only when a photo is attached: "Participant agreed to their photo on a shareable card." Generate stays disabled until it's ticked.
5. "Remove" link to clear the photo (same pattern as `clearGymLogo()`).
6. The photo clears after each successful submit (it's per visit), like the participant picker in F06-S05.

### `apps_script/Code.gs`
1. `generateWalkinNudge(params)`: add `hero_image: params.hero_image || ""` to the outgoing payload. Nothing else changes; no Drive access.
2. `submitWalkinGrip(data)`: append a trailing `photo_consent` column (via `_ensureTrailingColumns`), `TRUE` when a photo was used for that entry, else blank. This keeps a record of which shared cards show a person's face and that consent was given, without storing the photo.

### `report_service/app.py`
1. `/generate-walkin-nudge` validation accepts an optional `hero_image`, with the same rule as `gym_logo`: string, must start with `data:image/`, otherwise 400.
2. Add a size cap of **~2 MB after base64**, returning 400 "hero_image too large" above that. The browser downscale keeps real uploads far below this; the cap guards against a payload that skipped the downscale.
3. Pass `hero_image=` through to `generate_walkin_nudge_png`.

### `nudge_png.py`
1. `generate_walkin_nudge_png(..., hero_image=None)` → `_render_and_save` → `_render_template` → `_render_grip_template(..., hero_image=None)`.
2. `hero_b64 = _safe_data_uri(hero_image) or _asset_b64("grip/man.png")`. Generalise `_safe_logo` into `_safe_data_uri(value, what)` (same check, same warning), used for both the logo and the hero image.
3. Pass a `hero_is_custom` flag to the template.

### `templates/grip_nudge_template.html`
1. Hero `<img>` `object-position`: keep `left center` for the template image (it was traced to fit); use **`center center`** for a custom photo, since a person is usually centred in a phone shot. That's one conditional on `hero_is_custom`.
2. Gradient overlay and tagline unchanged. The tagline sits on the right half of the photo; the preview (index.html item 3) is how Arun avoids putting a face under it.

### Tests (Python)
- `tests/test_nudge_png.py`: custom photo renders in the hero `<img>`; no photo → template image; a non-`data:` value → template image + warning; `object-position` switches with `hero_is_custom`.
- `tests/test_report_service_validation.py`: `hero_image` accepted when blank or a data URI; rejected when a URL, a non-string or over the size cap.
- The tracked-client grip nudge (Share tab) is unchanged; an existing test should confirm it still renders the template hero.

---

## Out of scope
- **Storing the photo** anywhere (sheet, Drive folder). The only copy is inside the generated PNG in the "Walk-In Nudges" folder.
- **Per-client profile photos.** Revisit only if tracked PT clients ever want a photo on their card.
- **Photo on the Share tab's tracked-client grip nudge,** or on any other component's card.
- **In-app crop, zoom or focal-point controls.** The preview + retake covers it at pilot scale.
- **Moving or hiding the tagline** when a photo is used.
- **Posting to social media.** The trainer still downloads or shares the PNG manually.

## Acceptance criteria
1. Entry with a photo → the card's hero shows that photo, V-clipped, centred.
2. Entry without a photo → the card is identical to today's (template image, left-anchored).
3. A 5 MB phone photo uploads and generates without error; the payload sent is < 500 KB.
4. Generate is blocked until consent is ticked, but only when a photo is attached.
5. The walk-in row records `photo_consent = TRUE` for photo entries; no image data is in the sheet or in any Drive folder except the generated PNG.
6. The preview thumbnail matches the crop on the final card.
7. The Share tab's tracked-client grip nudge is unchanged.

## Deploy
Both halves, **as one batch**: Cloud Run (`gcloud builds submit` + `gcloud run deploy` **from PowerShell**, then verify the `/secrets/oauth_token.json` mount) and the Apps Script paste. Afterwards, check that "Execute as: Me" is still set. Deploy Cloud Run first: the old Apps Script ignores the new field, but the new Apps Script sending `hero_image` to the old service would still work too (unknown keys are ignored), so the order isn't risky, just tidy.

## Dependencies
None blocking. Build after F06-S05 so both form changes land in one Apps Script paste if convenient.
