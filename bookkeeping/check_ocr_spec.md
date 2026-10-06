# Check Image OCR Extractor — Module Spec

## Overview

Local-only Streamlit tool for extracting structured data from handwritten check images. No cloud APIs — all processing runs on-device using Surya OCR.

**Target machine:** Windows, 16GB RAM, CPU-only

---

## Module: `check_extractor.py`

**Location:** Add to existing RASRICH Streamlit app suite

### Architecture

```
Upload check images or PDF pages (drag & drop, multi-file)
    ↓
Page segmentation (detect individual checks per page via OpenCV contour detection)
    ↓
Surya OCR (local, CPU)
    ↓
Field extraction (position + regex pattern matching on OCR output)
    ↓
Review Table (editable in Streamlit)
    ↓
Export to Excel/CSV
```

### Dependencies

```
streamlit
surya-ocr
Pillow
opencv-python-headless
openpyxl
pdf2image
numpy
```

**System dependency (Windows):** `poppler` for PDF rendering — install via conda or download Windows binaries and add to PATH.

### OCR Approach

Surya provides text detection, recognition, and layout analysis. Checks have a predictable layout:
- **Check number:** top-right
- **Date:** top area
- **Payee:** "Pay to the order of" line, mid-left
- **Amount:** numeric value, right side
- **Purpose/Memo:** bottom-left

Field extraction maps OCR'd text to fields using position within the image (x/y ratios) combined with regex patterns (date formats, dollar amounts, keywords like "pay to", "memo").

### Check Segmentation

For pages with multiple checks: OpenCV edge detection + contour finding to isolate individual check rectangles. Filter by aspect ratio (~2:1 to 3:1, wider than tall) and minimum area (at least 5% of page). Sort top-to-bottom.

Fallback: if segmentation finds 0 checks, treat the whole image as one check.

### UI Flow

**Screen 1: Upload**
- Multi-file uploader: PNG, JPG, JPEG, PDF
- Toggle: "Multiple checks per page" (enables segmentation)
- PDF pages auto-converted to images
- Thumbnail grid preview
- "Extract All" button with progress bar

**Screen 2: Review**
- Click any row → shows source check image alongside fields
- `st.data_editor` with columns:
  - Check No. (text)
  - Date (text — don't force date parsing on handwriting)
  - Amount (number)
  - Payee (text)
  - Purpose (text)
  - Confidence (selectbox: HIGH / MEDIUM / LOW)
  - Flag (checkbox)
- "Raw OCR text" expander per row for debugging
- Sidebar: HIGH/MEDIUM/LOW counts

**Screen 3: Export**
- Excel (.xlsx) with color-coded confidence, filters, frozen header — same style as invoice extractor
- CSV option

### Error Handling

- Model fails to load (RAM) → clear message, suggest closing other apps
- Segmentation finds 0 checks → treat whole page as one check
- OCR returns no text → flag "OCR FAILED", show image for manual entry
- Field extraction empty → show raw OCR text, manual fill

### Data Safety

- 100% local processing — no network requests during OCR
- No data persistence beyond the Streamlit session
- Display note: "All processing runs locally. No data sent to any external service."

### Assumptions

- Standard US check layout
- Checks on page are separated (not overlapping)
- Surya models download (~1-2GB) on first run, cached locally after

---

## Phase 2: Payee Matching (vendor list + aliases) — NOT BUILT YET

**Problem:** the same handwritten vendor reads differently on every check
("KLMB", "KAL MB", "KLNB" are all KLMN). On a 17-check sample, raw OCR got
4/17 payees exactly right; fuzzy matching against the client's 6 vendors (stdlib
`difflib.SequenceMatcher` on letters only, uppercased) got 17/17. Lowest
correct score 0.44, highest wrong runner-up 0.64. That's one sample; thresholds
must be tested on variations, not fitted to it.

### Sources

| Source | File | Access |
|---|---|---|
| Tagger lookup | `stock_processor/lookups/{client_id}_lookup.csv`, `vendor_name` column | **Read only.** Never written by Check Extractor |
| Check aliases (new) | `stock_processor/lookups/{client_id}_check_aliases.csv` (already gitignored) | Read + write |

Alias columns: `ocr_text_norm, vendor_name, date_saved`.

Why separate: tagger rows mean "vendor → tag"; OCR misreads have no tag and
would pollute the tagger review table, and `_save_lookup` dedupes on
`vendor_name` (keep last), so the two tools could overwrite each other.

### Matching order (per payee)

1. Exact alias hit on normalized OCR text → that vendor, payee conf HIGH
2. Fuzzy match vs tagger `vendor_name` + alias vendors → best if score ≥ threshold and clear margin over runner-up
3. Otherwise keep OCR text, flag the row

Matching must handle bank-style names with extra tokens ("ACME SUPPLY CO NC"
vs handwritten "ACME"): token / partial matching, not whole-string only.

### UI

- Client picker (same `client_id` list as tagger) — optional; no client = no matching (current behaviour)
- Review table: show `Payee (OCR)` raw next to matched `Payee`
- "Save payee corrections" button → writes changed payees to the aliases file only

### Tests

- The 17 sample misreads → correct vendors
- Collisions: short names (KLMN vs other 4-letter vendors), two vendors sharing a word
- No client selected → unchanged behaviour
- Tagger lookup file is byte-identical after a run + save

### Open — confirm before building

| Point | Default unless told otherwise |
|---|---|
| Matched payee written as | Tagger's exact `vendor_name` (so check rows tag automatically later) |
| Show tagger's tag (e.g. COGS) as Purpose/category? | No (out of scope for Phase 2) |
| Data Safety line "No data persistence beyond the session" | Amend: aliases file persists locally (gitignored), no check images or amounts stored |
| Privacy | Claude must not open real lookup/alias files — they hold client vendor names; test with synthetic files only |
