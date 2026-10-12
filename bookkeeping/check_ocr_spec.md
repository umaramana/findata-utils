# Check Image OCR Extractor — Module Spec

## Overview

Local-only Streamlit tool for extracting structured data from handwritten check images. No cloud APIs — all processing runs on-device using Surya OCR.

**Target machine:** Windows, 16GB RAM, CPU-only

---

## Module: `check_extractor.py`

**Location:** two parts
- `bookkeeping/check_extractor.py`: core logic, no Streamlit (load, segment, OCR, extract, grade, export)
- `stock_processor/check_extractor_page.py`: Streamlit page in the RASRICH app suite
- Tests: `bookkeeping/test_check_extractor.py` (synthetic OCR lines, no Surya needed)

### Architecture

```
Upload check images or PDF pages (drag & drop, multi-file)
    ↓
Page segmentation (detect individual checks per page via OpenCV contour detection)
    ↓
≥ 2 checks found? ── yes → statement page: ONE Surya pass on the whole page,
    │                      lines assigned to each check box + its caption band
    no → Surya OCR per check (local, CPU)
    ↓
Field extraction (position + regex pattern matching on OCR output)
    ↓
Confidence grading (HIGH / MEDIUM / LOW) + Phase 2 payee matching (optional)
    ↓
Review Table (editable in Streamlit)
    ↓
Export to Excel/CSV
```

### Dependencies

`bookkeeping/requirements.txt`:

```
streamlit>=1.41.0
surya-ocr==0.17.1
transformers>=4.56.1,<5
Pillow>=10.2.0,<11
opencv-python-headless
pymupdf
openpyxl
pandas
numpy
```

- **Python 3.10–3.13 only:** surya-ocr 0.17.1 pins Pillow<11, which has no 3.14 wheel.
- **Surya pinned at 0.17.1:** the last pure-pip release; 0.20+ needs a llama-server/vLLM backend.
- **PDFs via `pymupdf`** at 200 DPI: pip-only, no poppler system install needed.
- Phone photos are rotated from their EXIF tag on load.

### OCR Approach

Surya provides text detection, recognition, and layout analysis. Checks have a predictable layout:
- **Check number:** top-right
- **Date:** top area
- **Payee:** "Pay to the order of" line, mid-left
- **Amount:** numeric value, right side
- **Purpose/Memo:** bottom-left

Field extraction maps OCR'd text to fields using position within the image (x/y ratios) combined with regex patterns (date formats, dollar amounts, keywords like "pay to", "memo").

### Check Segmentation

Only when "Multiple checks per page" is on. OpenCV: grayscale → Gaussian blur → Canny → dilate → external contours → bounding rectangles. Filters (`find_check_boxes`):

| Filter | Value | Why |
|---|---|---|
| Aspect ratio (w/h) | 1.8 – 3.4 | ~2:1 to 3:1 plus slack for skew/cropping |
| Minimum area | 0.8% of page | A 24-check statement grid is ~2% per check |
| Maximum area | 98% of page | Skip the page border |
| Nested boxes | Dropped if > 80% inside a larger box | The amount box inside a check |
| Size band | 0.5× – 2× the median box area (when ≥ 3 boxes) | Checks on a page share a size; drops logos, header bars |

Sort row by row (top-to-bottom in half-check-height bands, then left-to-right), so a few px of skew doesn't reorder a row.

Fallback: if segmentation finds 0 checks, treat the whole image as one check.

### Statement Pages (bank check-image statements)

When segmentation finds **≥ 2 checks** on a page, the page is a statement grid: each check image has a printed caption line under it (`Check# / date / $amount`).

- **One OCR pass for the whole page** (not per check). Each OCR line goes to the check box containing its centre, or to that box's **caption band**: the gap down to the next box in the same column, else half a check height.
- **Check no., date, amount** come from the printed caption (`CAPTION_NO_RE`, `DATE_RE`, `CAPTION_AMT_RE` = `$` + 2 decimals). Caption values override anything read from the handwriting.
- **Payee** is the only field read from handwriting.
- The review image is the check plus its caption band; raw OCR text gets a `[printed] ...` line.

### Confidence Grading (`grade`)

`value_conf` = the weaker OCR confidence of the amount and payee lines (on statement pages: the payee line only).

| Case | HIGH | MEDIUM | LOW |
|---|---|---|---|
| Statement page, all 3 caption fields read | payee found and `value_conf` ≥ 0.85 | payee found and ≥ 0.60 | otherwise |
| Statement page, caption only partly read | — | — | always |
| Single check | amount + payee + date found, `value_conf` ≥ 0.85 | amount + ≥ 2 of (check no., date, payee, purpose), `value_conf` ≥ 0.60 | otherwise |
| No OCR text | — | — | always |

Flag = LOW confidence, OCR failed, or (Phase 2) payee unmatched.

### UI Flow

**Screen 1: Upload**
- Multi-file uploader: PNG, JPG, JPEG, PDF
- Toggle: "Multiple checks per page" (enables segmentation)
- Client picker for payee matching (Phase 2; `(none)` = off)
- PDF pages auto-converted to images
- Thumbnail grid preview (first 24 pages)
- "Extract All" button with progress bar; an OCR error on one image warns and continues the batch

**Screen 2: Review**
- `st.data_editor` with columns:
  - Source, Page, Check # (read only: file, page, position on page)
  - Check No. (text)
  - Date (text — don't force date parsing on handwriting)
  - Amount (number, `$%.2f`)
  - Payee (text)
  - Payee (OCR) (read only; only when a client is picked, see Phase 2)
  - Purpose (text)
  - Confidence (selectbox: HIGH / MEDIUM / LOW)
  - Flag (checkbox)
- "View check" dropdown below the table → check image on the left; Confidence, Flag and a "Raw OCR text" expander for that check on the right (`data_editor` has no row-click event)
- Sidebar: HIGH/MEDIUM/LOW counts + flagged count

**Screen 3: Export**
- Excel (.xlsx) with color-coded confidence, filters, frozen header — same style as invoice extractor
- CSV option

### Error Handling

- Model fails to load (RAM) → clear message, suggest closing other apps
- Model download/read fails (no internet or < ~2 GB free disk on first run) → separate message saying so
- Surya not installed → message with the `pip install -r bookkeeping/requirements.txt` command
- Segmentation finds 0 checks → treat whole page as one check
- OCR returns no text → flag "OCR FAILED", show image for manual entry
- Field extraction empty → show raw OCR text, manual fill

### Data Safety

- 100% local processing — no network requests during OCR
- No data persistence beyond the Streamlit session, except Phase 2 payee aliases: `{client_id}_check_aliases.csv` (local, gitignored) holds OCR text + vendor name only, no check images or amounts
- Display note: "All processing runs locally. No data sent to any external service."

### Assumptions

- Standard US check layout
- Checks on page are separated (not overlapping)
- Surya models download (~1-2GB) on first run, cached locally after

---

## Phase 2: Payee Matching (vendor list + aliases) — BUILT 6 Oct 2026

Code: `bookkeeping/payee_match.py`, hooked in via `check_extractor.apply_payee_match`; tests `bookkeeping/test_payee_match.py` (`--report` writes the threshold table to `diag_output/`).

### PICK UP HERE: real-page run done (as of 7 Oct 2026)

Run on the real statement page with a client picked: **3 of 17 payees wrong**, all misreads of one short vendor name.
The matching thresholds stay as they are; loosening them for these cases would overfit.

**OCR tuning tried and rolled back (7 Oct):** 300 DPI plus a second OCR pass on the cropped, 2× enlarged payee line
made **more** payees wrong. Both changes were tested together, so it's unknown which one hurt. Don't retry them as a pair.

**Corrections:** the bookkeeper edits wrong cells in the review table (like the tagger). "Save payee corrections"
turns corrected payees into aliases, and the download has the edited values.

| # | Still to confirm on the real page | Expect |
|---|---|---|
| 1 | Edit one wrong payee, click "Save payee corrections (1)" | Success message; `{client}_check_aliases.csv` created |
| 2 | Re-run the same page | That payee is now an alias hit: confidence HIGH, not flagged |

Report back **counts only**, never vendor names.
Then: fix anything found, commit the fixes, and close.

**Problem:** the same handwritten vendor reads differently on every check
("KLMB", "KAL MB", "KLNB" are all KLMN). On a 17-check sample, raw OCR got
4/17 payees exactly right; fuzzy matching against the client's 6 vendors (stdlib
`difflib.SequenceMatcher` on letters only, uppercased) got 17/17. Lowest
correct score 0.44, highest wrong runner-up 0.64. That's one sample; thresholds
must be tested on variations, not fitted to it.

### Sources

| Source | File | Access |
|---|---|---|
| Tagger lookup | `stock_processor/lookups/{client_id}_lookup.csv`: `vendor_name` rows whose `tag` is COGS | **Read only.** Never written by Check Extractor |
| Manual lookup | `stock_processor/lookups/{client_id}_lookup.xlsx`: one tab per year; every tab with a `Vendor` and a `Category` column (header in row 1, matched by "vendor" / "category" in the name), COGS rows only; other tabs skipped | **Read only** |
| Check aliases (new) | `stock_processor/lookups/{client_id}_check_aliases.csv` (already gitignored) | Read + write |

**COGS only** (user, 7 Oct 2026): checks are written to COGS vendors, so only those are match candidates. A row is COGS when its tag/category is `COGS` or `Cost of Goods Sold` (any case, extra spaces ignored). Vendors from both files are combined (duplicates across year tabs collapse). The client dropdown lists clients with either file.

Alias columns: `ocr_text_norm, vendor_name, date_saved`.

Why separate: tagger rows mean "vendor → tag"; OCR misreads have no tag and
would pollute the tagger review table, and `_save_lookup` dedupes on
`vendor_name` (keep last), so the two tools could overwrite each other.

### Matching order (per payee)

1. Exact alias hit on normalized OCR text → that vendor, payee conf HIGH
2. Fuzzy match vs tagger `vendor_name` + alias vendors → best if score ≥ 0.60 and ≥ 0.10 over the runner-up
3. Otherwise keep OCR text, flag the row

Score = `difflib` ratio of the OCR letters vs the whole vendor name or any run of its
tokens (≥ 3 letters). OCR text is compared whole: scoring an OCR fragment ("KAL" of
"KAL MB") lifted the look-alike KLAX and erased the margin.

Thresholds (user-approved 6 Oct 2026) come from 400 synthetic misreads of 10 invented
vendors (collision pairs included) + 48 non-vendor payees: 361 matched, 0 wrong, 39
flagged, 0/48 non-vendors matched. The margin is what flags "ACME" when two vendors
start with ACME; the minimum score keeps "CASH" off a vendor ending in "GAS". Limit:
the sample's lowest correct whole-string score was 0.44, so a payee that bad is now
flagged, not matched; once corrected, its alias makes it an exact hit.

Confidence: alias hit → payee confidence 1.0; fuzzy match leaves grading unchanged
(the `Payee (OCR)` column shows what was replaced); unmatched → Flag.

Matching must handle bank-style names with extra tokens ("ACME SUPPLY CO NC"
vs handwritten "ACME"): token / partial matching, not whole-string only.

### UI

- Client picker: dropdown of existing `{client_id}_lookup.csv` files + `(none)`; no client = no matching (Phase 1 behaviour). Changing client re-matches without re-running OCR
- Review table: show `Payee (OCR)` raw next to matched `Payee`
- "Save payee corrections" button → writes changed payees to the aliases file only

### Tests

- The 17 sample misreads → correct vendors
- Collisions: short names (KLMN vs other 4-letter vendors), two vendors sharing a word
- No client selected → unchanged behaviour
- Tagger lookup file is byte-identical after a run + save

### Decided (user, 6 Oct 2026: all defaults accepted)

| Point | Decision |
|---|---|
| Matched payee written as | Tagger's exact `vendor_name` (so check rows tag automatically later) |
| Show tagger's tag (e.g. COGS) as Purpose/category? | No (out of scope for Phase 2) |
| Data Safety line "No data persistence beyond the session" | Amend: aliases file persists locally (gitignored), no check images or amounts stored |
| Privacy | Claude must not open real lookup/alias files — they hold client vendor names; test with synthetic files only |

### Parked (7 Oct 2026)

| Item | Note |
|---|---|
| Payee refinement **without a client** | Same vendor misread differently on every check (a short name like "KLMN" never read right; a longer one read right once, wrong the rest). Idea: group look-alike payees within one run, so one correction (or the one correct reading) applies to the whole group. Risk: two short vendors grouped wrongly. Not started |
