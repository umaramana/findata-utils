# Receipt Generator — Feature Spec
**Insight Fitness Data Services | Utility v0.1**

---

## 1. Overview

A standalone utility for generating branded monthly PT service receipts. The trainer selects a client, enters payment details, previews the receipt, and exports a PDF. One utility within the broader Insight Fitness platform.

---

## 2. User Flow

```
Client lookup (from Sheets)
        ↓
Fill receipt form (Month/Year, Amount, Payment Method, Transaction ID)
        ↓
Preview receipt (HTML render)
        ↓
Generate PDF → Download
```

---

## 3. Inputs

### 3.1 From Google Sheets (auto-populated on client selection)
| Field | Sheets Column | Fallback |
|---|---|---|
| Client full name | `name` | — |
| Contact / phone | `phone` | Trainer-entered |
| Email | `email` | Trainer-entered |
| Address | `address` | Trainer-entered if blank |

A receipt can cover one or two clients. The **primary client** is the one paying — their details appear in the Billed To block. A **secondary client** (optional) adds a second line item to the table but does not change the Billed To block. Both must be selected from the client directory.

### 3.2 Trainer-entered (per receipt)

**Default (single-client) mode:**
| Field | Type | Required |
|---|---|---|
| Month + Year | Dropdown (Month) + Year input | Yes |
| Amount paid | Numeric (Rs.) | Yes |
| Payment method | Dropdown: Cash / Bank Transfer / Card / Other | Yes |
| Transaction ID | Text | No — blank if not provided |

**Joint receipt mode** (activated by "Joint receipt" checkbox — hidden by default):
| Field | Type | Required |
|---|---|---|
| Secondary client | Autocomplete search from directory | Yes, once checkbox ticked |
| Amount — primary client | Numeric (Rs.) | Yes |
| Amount — secondary client | Numeric (Rs.) | Yes |
| *(Month, Payment method, Transaction ID shared across both)* | | |

When the checkbox is unticked, the secondary client slot and per-client amount fields are hidden and the single Amount field is shown. Ticking the checkbox replaces the single Amount field with two per-client amount inputs and reveals the secondary client search.

### 3.3 Static config (set once, not per receipt)
| Field | Value |
|---|---|
| Receipt number | Auto-incremented from `receipts` Sheets tab; manual override allowed |
| Date issued | Auto: current date |
| Trainer name | ARUN ALEX DAVID |
| Trainer title | Personal Trainer |
| Business phone | +91-97911 72562 |
| Business email | arunalexdavid1991@gmail.com |

---

## 4. Receipt Layout

Dynamic content overlaid on a full-page background PNG using absolute positioning (HTML/CSS preview) and coordinate-based drawing (Puppeteer PDF render).

### 4.1 Background image
- File: `Insight_Receipt_BG_Only.png`
- Dimensions: **1410 × 2000 px**, RGB
- Contains (static — do not re-render in code): dot grid corners, decorative rule lines, "RECEIPT" heading + rule, "BROUGHT TO YOU FROM" label, Insight logo, "Holistic fitness.." tagline, contact details, "Thank You for Your Payment!", trainer name + title
- Dynamic content overlaid on dark centre body area

### 4.2 Typography

| Zone | Font | Size | Color |
|---|---|---|---|
| Receipt No., Date | Cooper Hewitt | 7pt | #880e4f |
| Billed To label | Poppins Bold | 9pt | Black |
| Billed To values | Poppins | 7pt | Black |
| Payment Summary label | Poppins Bold | 9pt | Black |
| Payment Summary values | Poppins | 7pt | Black |
| Table header | Poppins Bold | 8pt | Black |
| Table body | Poppins | 8pt | Black |
| Table border | — | — | #ba9138 |

Both fonts available via Google Fonts. Load via `@import` in HTML preview; embed as TTF in Puppeteer PDF render.

### 4.3 Dynamic content blocks with approximate overlay coordinates
(Origin: top-left of 1410 × 2000px image. Fine-tune during build.)

**Receipt No. + Date** — `x: 90, y: 380`
- Receipt No.: `<id>`
- Date: `<DD MMM YYYY>`

**Billed To** — `x: 90, y: 530`
- "**Billed To:**" label
- Name, Contact, Email, Address of the **primary client** (the one paying)
- Unchanged whether the receipt covers one or two clients

**Payment Summary** — `x: 720, y: 530`
- "**Payment Summary:**" label
- Total Paid: Rs. `<amount>`/-
- Payment Method: `<method>`
- Transaction ID: `<id or blank>`

**Line items table** — `x: 90, y: 780`, width: `1230px`
- Header row: Description | Amount
- **Single-client mode:** one data row — "Personal Trainer services for `<Client Name>` — `<Month Year>`" | Rs. `<amount>`/-
- **Joint receipt mode:** two data rows, one per client, each with their own name and amount:
  - "Personal Trainer services for `<Primary Client Name>` — `<Month Year>`" | Rs. `<amount1>`/-
  - "Personal Trainer services for `<Secondary Client Name>` — `<Month Year>`" | Rs. `<amount2>`/-
- Border colour: #ba9138

**Footer (static — in background image):**
- "Thank You for Your Payment!" — bottom left
- "ARUN ALEX DAVID / Personal Trainer" — bottom right

---

## 5. UI

Single-screen utility (HTML/JS, local or served):

1. **Client search** — text input with autocomplete dropdown populated from Sheets (primary client — always required)
2. **Auto-filled fields** — Name, Contact, Email, Address populate on client selection; Address editable if blank
3. **"Joint receipt" checkbox** — unchecked by default; ticking it:
   - Reveals a second client search (secondary client)
   - Replaces the single Amount field with two per-client amount inputs (Primary amount / Secondary amount)
   - Unticking clears the secondary client and reverts to single Amount field
4. **Receipt form** — Month/Year pickers, Amount (or per-client amounts in joint mode), Payment Method dropdown, Transaction ID (optional), Receipt No. (pre-filled, system-generated)
5. **Preview pane** — live HTML render; in joint mode shows two rows in the line items table
6. **Actions:**
   - `Generate PDF` — Puppeteer renders HTML preview to PDF
   - `Download` — saves as `Receipt_<PrimaryClientName>_<MonthYear>.pdf`

---

## 6. Google Sheets Integration

- **Source:** Client directory sheet (one row per client)
- **Columns used:** `client_id`, `name`, `email`, `phone`, `address`
- **Access:** Read + write; Google OAuth via Sheets API
- **Read:** client directory tab — for client lookup and autocomplete
- **Write:** `receipts` tab — one row appended per generated receipt (see Section 8)

---

## 7. PDF Generation

- Method: Puppeteer (headless Chrome) renders the HTML preview to PDF
- Page size: A4
- Background image printed: yes (`-webkit-print-color-adjust: exact`)
- Output filename:
  - Single-client: `Receipt_<ClientName>_<MonthYear>.pdf`
  - Joint receipt: `Receipt_<PrimaryClientName>_<SecondaryClientName>_<MonthYear>.pdf`

---

## 8. Receipts Log — Google Sheets Write-back

On every PDF generation, rows are appended to the `receipts` tab in the same Google Sheet — **one row per client on the receipt**.

**Columns written:**
| Column | Value |
|---|---|
| `receipt_no` | Auto-incremented receipt number — same value across both rows for a joint receipt |
| `date_issued` | Current date |
| `client_id` | From client record (each client's own ID) |
| `client_name` | From client record (each client's own name) |
| `month_year` | e.g. "May 2026" |
| `amount` | That client's amount (Rs.) |
| `payment_method` | Cash / Bank Transfer / Card / Other |
| `transaction_id` | Trainer-entered or blank |

A joint receipt therefore writes two rows with the same `receipt_no`, `date_issued`, `month_year`, `payment_method`, and `transaction_id`, but different `client_id`, `client_name`, and `amount`.

**Receipt number sequence:** Read last `receipt_no` from `receipts` tab → increment by 1. Persists across sessions.

---

## 9. Scope — This Version

| In scope | Out of scope |
|---|---|
| Single receipt per run | Batch generation |
| PDF download | Email sending (v0.2) |
| Read + write to Sheets | — |
| Single currency (Rs. INR) | Multi-currency |
| Gross amount only | GST / tax lines |
| Single line item | Session breakdown |

---

## 10. Assets

| Asset | File | Status |
|---|---|---|
| Background PNG | `Insight_Receipt_BG_Only.png` (1410 × 2000px) | ✅ Ready |
| Cooper Hewitt font | Google Fonts / TTF | ✅ Confirmed |
| Poppins font | Google Fonts / TTF | ✅ Confirmed |
| Overlay coordinates | See Section 4.3 | ✅ Estimated — fine-tune during build |

---

## 11. Build Notes

### Recommended build sequence
1. **Visual layer first** — render HTML preview with hardcoded dummy data against the background image; confirm all text blocks land correctly before wiring any data
2. **Coordinate calibration** — adjust x/y values in Section 4.3 until layout matches the Canva template exactly
3. **Sheets read** — wire up client lookup and autocomplete
4. **Form + preview wiring** — connect form inputs to live preview updates
5. **PDF generation** — Puppeteer render from confirmed HTML preview
6. **Sheets write-back** — append receipt row on PDF generation
7. **Receipt number sequencing** — read last receipt_no from Sheets, increment, allow override

