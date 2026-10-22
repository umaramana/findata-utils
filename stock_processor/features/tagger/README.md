# Tagger Contract — PROPOSED (22 Oct 2026)

IMP step 1: pin what `stock_processor/tagger_page.py` does **today**, before any change.
Target = tax clients with no accounting software. Bookkeeping (Wave) is parked.
Format = Gherkin, to run later with pytest-bdd (not installed yet; no step code written).
All names are invented (ACME, KLMN).

## Marks

| Mark | Meaning |
|---|---|
| `@keep` | right for tax clients as it is |
| `@generic` | works, but fitted to one client, one bank or Wave; make generic before tax-client use |
| `@client-data` | a per-client choice; move out of shared code/data into the client's files |
| `@parked` | bookkeeping only; pinned so tax work doesn't break it |

## Files

| File | Covers | keep | generic | client-data | parked |
|---|---|---|---|---|---|
| 01_vendor_name | vendor cut from description | 4 | 3 | – | – |
| 02_money_in_out | debit / credit, file combine | 6 | – | – | – |
| 03_rules_and_order | who decides; `docs/auto_rules.csv` | 3 | 1 | 2 | – |
| 04_lookup | client lookup history | 5 | 1 | – | – |
| 05_claude | what Claude gets and returns | 7 | 1 | – | – |
| 06_contra | contra pairing | 3 | – | – | – |
| 07_output | workbook + summary | 3 | – | – | 1 |
| 08_tag_list | `docs/rasrich_tag_lists.csv` | 2 | 1 | – | – |
| 09_wave_parked | `docs/wave_mapping.csv`, Wave fill | – | – | – | 3 |
| 10_ref_no_contra | contra pairing by ref no (NEW, approved, built) | – | – | – | – |

## The `@generic` / `@client-data` items in one list

1. Zelle ref words stay in the vendor, so one payee splits into many vendors.
2. Every check is the vendor "Check" (agreed item b).
3. Capital One / Citibank layouts and a Citibank OCR code are parsed inside the tagger; belongs in the extractor.
4. The bank-fee rule names a Wave category instead of a tax tag.
5. ATM withdrawal = Personal is a shared rule; it is a per-client call (fits item c).
6. Saving to the lookup keeps unreviewed Claude rows (agreed item e).
7. Claude's prompt is framed around Wave categories.
8. One tag list (Form 1120-S lines) for every entity type; Schedule C and 1065 lines differ.

## Ref no for contras (asked 22 Oct)

| Extract | Does it carry a ref no? |
|---|---|
| Regions credit card | The statement prints a Reference Number on every row. The parser reads it and **throws it away** (`extract_regions_cc_txns.py` line 137, `_ref`). |
| Regions checking / savings | No ref column, but the extractor **keeps** the ref inside Description (e.g. `EB to Savings # 0321568960 Ref# 000000 0001028`, pinned by `test_extract_regions_txns.py` line 62). The tagger cuts it from Vendor only; Description still has it. |
| Bank Statements output (`bank_statements.py` `_COLS`) | Date, Description, Amount, Section, Status, Filename. **No ref column.** |
| Chase / Citi legacy parsers | No ref kept. |

The user confirmed (22 Oct) that the two sides of a transfer carry the same ref no. So the
checking/savings ref is usable today (it is in Description); the card Reference Number would need the
card parser to keep it. Pairing by ref no is a new contract, not part of this pin.

## Open questions for the user

1. Are the marks right? In particular #5 (ATM) and #3 (move bank layouts to the extractor).
