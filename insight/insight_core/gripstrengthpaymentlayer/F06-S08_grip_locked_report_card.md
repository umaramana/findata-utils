# F06-S08 — Walk-In Grip: Locked Report Image with UPI QR — NEW 2026-10-13

**Status: BUILT and smoke-tested by Arun 2026-10-14. Phase 1 of the grip paywall. Keep it minimal. No ledger, no payment tracking, no automation.**

**Revised 2026-10-13:** the locked image now blurs the **entire** card (Arun's requirement), not just the numbers. It is built as a Pillow post-process of the full PNG, not a template change.

**Verified by:** Claude Chat, 2026-10-13, against `main` @ `2af460d`:
- `/generate-walkin-nudge` → `nudge_png.generate_walkin_nudge_png()` → `_render_and_save()` → `_render_grip_template()` → `templates/grip_nudge_template.html` (1024×1536).
- Number slots are `{{right}}` / `{{left}}`; grade slots are `{{right_label}}` / `{{left_label}}`.
- The result PNG uploads to Drive, is shared with `ARUN_EMAIL` and is returned as `output_url`.
- The Walk-In UI (`index.html` `submitWalkinForm()`) shows `Open image · Open WhatsApp`.

---

## What Arun wants

Free grip test, **₹100 to see the report**. Arun sends a **locked** image on WhatsApp with numbers hidden and a UPI QR to pay. When he sees the payment arrive, he sends the normal (full) image by hand.

## What to build

**Walk-In path only.** The tracked-client Share flow is untouched.

### 1. Every walk-in generate produces two images

`/generate-walkin-nudge` renders and uploads:
- **Full image**: exactly today's card. No change.
- **Locked image**: the full image, **entirely blurred**, with a sharp UPI QR panel on top. Filename is today's name with a `_locked` suffix.

The response adds one field:
```json
{"status":"done","output_url":"<full image>","locked_url":"<locked image>"}
```

No toggle. Arun picks which link to use.

### 2. Locked image: blur the whole full PNG, then paste the QR panel (`nudge_png.make_locked_png()`)

**Arun's requirement: the entire report is blurred, not just the numbers.**

Build it as a **post-process of the full PNG with Pillow** (already installed via matplotlib and used in `chart_renderer.py`). There is no template change and no second Puppeteer render.

1. Open the full PNG and apply `ImageFilter.GaussianBlur(radius=28)` to the **whole** 1024×1536 image. The radius must be strong enough that the 100px numbers are unreadable. Confirm by eye in the smoke test, and raise it if any digit is guessable.
2. Paste a **sharp** white rounded panel (about 620×760, centred on the canvas) on top, drawn with `ImageDraw`. The panel holds:
   - "{client name}, your report is ready". The name is the only readable personal detail, so the client knows the report is his.
   - The **UPI QR** at **at least 360×360px**, with a white margin of at least 4 modules (it must still scan after WhatsApp recompresses the image)
   - "Scan to unlock · ₹{UNLOCK_PRICE_INR}"
   - Fonts: use `fonts/Roboto/static/Roboto-Bold.ttf` and `Roboto-Regular.ttf`, which are already in the repo. The card's own fonts in `assets/fonts/` are woff2, which Pillow can't load reliably. Don't use Pillow's default bitmap font.
3. Save as the locked PNG.

The full image and `_render_grip_template()` are **unchanged**. Existing tests must pass unmodified.

### 3. UPI QR

Encode this string as a QR using the `segno` package (add it to requirements), rendered to a PIL image and pasted into the panel:
```
upi://pay?pa=<UPI_VPA>&pn=<UPI_PAYEE_NAME>&am=<UNLOCK_PRICE_INR>&cu=INR&tn=Grip report <client name>
```
- New Cloud Run env vars: `UPI_VPA`, `UPI_PAYEE_NAME`, `UNLOCK_PRICE_INR` (set to `100`). The overlay text uses `UNLOCK_PRICE_INR`, not a hard-coded 100.
- URL-encode the parameter values (spaces in names).
- **If any env var is missing:** still return the full image as today, set `locked_url` to `null`, and log a warning. A paywall config gap must never block the normal report.

### 4. UI (`index.html`, Walk-In result card)

Change the result links to:

`Open locked image · Open full image · Open WhatsApp`

If `locked_url` is null, show `Locked image unavailable (UPI not set up)` in place of the first link.

### 5. Tests

- `make_locked_png()`: the output is 1024×1536. It differs from the full PNG. The QR region decodes (OpenCV `cv2.QRCodeDetector`, already installed; no new test dependency) to the exact UPI string, including `am` and `tn`.
- The full render is unchanged, and existing grip tests pass unmodified.
- The endpoint returns `locked_url` when the env vars are set, and `null` (with the full image still returned) when they are missing.

### 6. Deploy and smoke test

1. Set the three env vars, deploy Cloud Run, then paste the Apps Script.
2. Generate one walk-in and open both images. On the locked image, **no number, grade or text other than the panel should be readable**. Zoom in to check.
3. Send the locked image to a second phone on WhatsApp.
4. On that phone, save the image and scan it via **"scan from gallery"** in GPay or PhonePe. Confirm the payee name, ₹100 and the note. Don't complete the payment.

---

## Out of scope

- The tracked-client paywall
- A payment ledger or a pending/paid list. Arun matches payments in his UPI app, and conversion can be counted from the walk-in sheet rows against ₹100 payments received.
- Razorpay, WhatsApp API or any automation (Phase 2, parked)
- A teaser line on the locked card

## Config values (supplied by Uma, 2026-10-13, from Arun's GPay QR)

| Env var | Value |
|---|---|
| `UPI_VPA` | `arunalexdavid1991@okhdfcbank` |
| `UPI_PAYEE_NAME` | `ARUN ALEX DAVID` (matches the bank-registered name GPay shows) |
| `UNLOCK_PRICE_INR` | `100` |

Generate the QR from these values with `segno` as in section 3. **Don't reuse Arun's GPay QR image:** it's a static QR with no amount and no note, so the client would have to type ₹100 and Arun couldn't tell who paid.

Smoke test addition: scan the locked image's QR in **GPay, PhonePe and Paytm**. Arun's ID is a personal account, not a merchant one, so check that each app opens with ₹100 pre-filled, note whether the amount can be edited, and confirm it doesn't show a risk warning. If one does, flag it to Uma rather than working around it.
