# Bank Statements page: mini-spec (DRAFT, awaiting go-ahead)

Status: nothing built. Written 8 Oct 2026 from the user's answers and the five Regions layout screenshots
(`data/rts-bank/*.png`, `data/rts-cc/*.png`). Names below are invented (ACME, KLMN).

## 1. Goal
One Streamlit page that turns bank statements into the existing Excel layout (Summary / Master / per-month),
for every bank we support, and fills check payees from a check register. GR2: core feature only; flags and
extras only where trivial.

## 2. Page and UI
- New separate page "Bank Statements" in `stock_processor/rasrich_tools.py` (own section, same level as Bookkeeping and Tax).
- Flow: pick format -> upload statements -> (optional) upload check register -> Extract -> review table -> download Excel.
- The user picks the format; the page does NOT guess the bank. Formats: Regions checking/savings, Regions credit card,
  Chase business checking, Chase credit card, Citi checking. (Capital One, Freedom, India: later, not in this build.)
- Input type is decided per file: PDF with a text layer -> read the text; images or a PDF with no text -> existing OCR.
- Review table: date | description | amount | section | status. Status: OK / payee filled / check not in register.
  Per statement: printed totals vs extracted totals, green when equal, red with the gap otherwise.
- Output: Excel, Summary -> Master -> per-month tabs, same as the existing extractors.
- Chase and Citi move onto this page now: their parsers are imported unchanged; only the Tesseract path
  (hardcoded `C:\Program Files\Tesseract-OCR`) must stop breaking an import from Streamlit.

## 3. Regions checking / savings (checking = text PDF; SAVINGS = IMAGE PDF, per user 8 Oct)
Seen in the screenshots:
| Item | Rule |
|---|---|
| Dates | `MM/DD`, no year. Year from the statement period; a Dec -> Jan statement rolls the year. |
| Sections | DEPOSITS & CREDITS (+), WITHDRAWALS (-), CHECKS (-), INTEREST (+, savings). Amounts print unsigned, the section gives the sign. |
| Checks | Two side-by-side blocks of Date / Check No. / Amount; split by column position, not line order. A trailing `*` (break in sequence) is stripped from the number. No description on the statement. |
| Totals | Each section has a printed `Total ...` line: reconcile extracted sum against it. |
| Balance | No running balance. Savings DAILY BALANCE SUMMARY ignored (not needed for the rows). |
| Statement period | Page 1 top, e.g. `<ACCOUNT TYPE TITLE> January 14, 2026 through February 10, 2026` (user, 8 Oct; same on savings). The Chase `_PERIOD_RE` pattern fits it. Year for each row comes from here. |
| Savings = image | The savings PDF has no text layer, so it goes through the OCR path (page images -> Tesseract), not the text reader. The Regions savings parser must therefore tolerate OCR noise, unlike checking. |
| Ignored | SUMMARY box, everything else on the page. |

## 4. Regions credit card (text PDF)
| Item | Rule |
|---|---|
| Columns | Tran Date, Post Date, Category, Reference Number, Transactions (description), Amount. |
| Dates | `MM/DD`, year from the billing date; Dec -> Jan rolls the year (seen: 12/22 ... 01/19). |
| Sign | Amount followed by `CR` is a credit (negative); no suffix is a charge. |
| Totals | Account Summary: Total Activity = Debits/Other Fees - Credits (458.35 - 132.66 = 325.69 in the sample). Reconcile to it. |
| Description | Keep merchant text; drop the reference number from it. |

## 5. Check register fill
- Register = the Check Extractor's Excel export, columns `Source | Page | Check # | Check No. | Date | Amount | Payee | Payee (OCR) | Purpose | Confidence | Flag`.
  Only `Source`, `Check No.`, `Date`, `Amount`, `Payee` are used.
- For each statement check row: look up `Check No.`; description = register `Payee`.
- No match: description stays `Check #911` and the row's status is "not in register" (flagged, nothing dropped).
- Amount cross-check (register amount vs statement amount) only if it is a one-line compare; mismatch -> flag.
- Register optional: without it the checks keep `Check #911`.

## 6. Collator reuse (DECIDED 8 Oct: one shared module)
`excel_utilities_page.py` keeps its collator. Its logic (`_collate_sheets`, `_generate_output`, `_append_recon`) is
moved into one shared module, imported by both pages. One copy of the code, two callers; neither page shows the
other's tab. [FILL] confirm the Summary/Master layout of the existing bank scripts is what the page should write
(vs the collator's Master + reconciliation layout).

## 7. Text-PDF support for Chase / Citi (LATER, user decision 8 Oct)
Chase: `parse_page(text)` is already text-in, so a text PDF just skips `ocr_image` and passes the page text.
Citi: [FILL] not checked whether its parser needs OCR word positions. No text-PDF samples exist yet, so nothing
can be verified; do Chase only, and only when a real text sample is available.

## 8. Out of scope
Redactor changes (the screenshots give the layout; no real PDFs are needed by Claude). Internal-transfer flagging.
Capital One / Freedom / India on the page. Payee fuzzy-matching (the register is exact on check number).

## 9. Open items [FILL]
1. DONE: statement period is on page 1 top (see section 3).
2. DONE: output columns = Chase layout.
3. DECIDED: text-PDF support for Chase/Citi moved to later (section 7).
4. Open: which Regions pages of the savings image PDF are OCR'd cleanly is unknown; needs a real run.

## 10. Build order and tests (after go-ahead)
1. DONE 8 Oct: Regions checking/savings parser `scripts/extract_regions_txns.py` (text in, rows out) + `scripts/test_extract_regions_txns.py` (13 tests, synthetic, incl. noisy savings OCR text and wrapped descriptions). Not yet run on a real PDF; PDF/OCR text extraction is step 4.
2. DONE 8 Oct: Regions credit card parser `scripts/extract_regions_cc_txns.py` + `scripts/test_extract_regions_cc_txns.py` (12 synthetic tests: CR credit, Dec->Jan rollover from Billing Date, summary merged with left column, cardholder Total Activity ignored, reconcile ok/gap). Sign = statement-signed (charge +, CR credit -). Not run on a real PDF; uncommitted.
3. Register fill + tests (match, miss, `*` stripped).
4. Shared Excel/collator module; Streamlit page; move Chase/Citi onto it.
5. Real run by the user on their real PDFs; fix what differs. Samples are shapes, not guarantees.
