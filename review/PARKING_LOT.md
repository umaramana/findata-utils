# Tax Review Pipeline — Parking Lot

Known gaps and deferred work for `review/` and `redactor/`. Status log of record is
`SPEC-revision-extraction.md`; this file is the open-items list. Last updated 24 Sep 2026.

---

## Redactor (`redactor/redact.py`, wrapper `review/redact.py`)

**PLANNED (24 Sep): scan -> confirm -> redact -> purge flow, later a nightly batch.** Design, issues and 4 open
questions in `SPEC-revision-extraction.md` § "Session 24 Sep". Not built.
Alternative there too: harvest the details from the Drake return first, confirm, redact, erase on exit.

**OPEN (24 Sep): still exposed after today's fixes** - found by the user running the redacted `client_bt2024`
returns through a separate Claude chat (CPA return + Drake return). Everything fixed today held; these did not.
Likely cause is a guess until probed (`probe_labels.py` with the label added) - fix the general class, not the file:

| # | Item | Where | Risk | Likely cause | Proposed fix |
|---|---|---|---|---|---|
| 1 | Full bank account no. (direct deposit) | CA 540 Side 5 (CPA) | High | Comb boxes: digits printed one per box ("1 2 3 4 ..."), so neither the bare-digit rule nor the label rule sees a number | Treat single-spaced digit runs (11+ digits) as one number; probe CA 540 Side 5 first |
| 2 | Third-party designee PIN | 1040 p2 (CPA) | Medium | 5 digits; PIN rule wants 6 | Label rule: "Personal identification number (PIN)" + 5 digits, also Self-select PIN |
| 3 | Preparer PTIN | 1040 + CA 540 (CPA; Drake masks it) | Medium | No rule for it | Always-on shape: `P` + 8 digits |
| 4 | Partial PAN-style IDs | Karvy payer line, Sch B, both returns | Medium | PAN rule wants all 10 characters in exact shape; masked/partial ones slip | PAN shape allowing mask characters / truncation; probe the Sch B line |
| 5 | ICICI account designation | Form 8938 (CPA) | Medium | Label is "Account number or other designation" - extra words break the account-label rule; value may be on the next line or alphanumeric | Add that label (same line or next line); allow letters in the value |
| 6 | Employer name, county, occupation, DOB | both | Low alone, identifying combined | Employer name: entry only. County/occupation: no rule. DOB: likely in boxes/columns, not right after its label | Ask user which to redact (occupation/county may be wanted for review); return-first harvest (spec) would cover names and DOBs |

**FIXED (24 Sep, later session): 2 address false positives made the Drake 2024 return FAIL** (`p30/p31/p90:ADDRESS`).
(a) `ADDRESS_NEXT_LINE_RE` took the next empty field's number + label ("12  State") as the address and blacked it
out; `verify()` then read the following label in its place. Such lines are now skipped. (b) `CITY_STATE_ZIP_RE`: after
a 9-digit number went, a checkbox "X" + state code + 5 digits read as city/state/ZIP; a city now needs 2+ letters.
Test page `field_labels.pdf` in `test_redact.py`. Limit: "12 Shivaji Chowk" (number + words, no comma/suffix) under
an address label is now caught only if entered. **User to check:** p90 of that return has a state code + 5 digits
on a dependent-style row after a 9-digit number, never redacted - is it a real ZIP?

**OPEN (24 Sep, later session): re-review after the fix above - both returns `OK`, the outside Claude review still
found these.** Shapes only here, never values (the review's table held real values; ask it next time to report
item / page / masked shape only). Rows 1, 2, 6, 8, 9 overlap the table above; 3, 4, 5, 7 are new.

| # | Item | Where | Risk | General class | Planned fix |
|---|---|---|---|---|---|
| 1 | Refund account no., 8 digits visible (not just last 4) | CA 540 Side 5 l.116, CPA return | High | Comb boxes, one digit per box | Join single digits separated only by box gaps into one number, then the account rules (last 4 kept). Probe the layout first |
| 2 | Near-complete PAN, joined with `&` to a second one | Sch B Karvy line (both); Drake overflow stmt | High | Masked / truncated / joined PAN | PAN shape allowing mask chars or missing tail, only near a PAN label or payer line (5 letters + 4 digits elsewhere stays). Probe first |
| 3 | NC D-400 scan line: name control, house no., ZIP, city | Drake D-400 p1 | High | Machine-readable lines repeating header values with no labels/punctuation | From entered values: also match the entered address's house number, ZIP and city as separate tokens, and the name control (below) |
| 4 | Phone, bare 10 digits after `PN` | Drake D-400 p1 | High | Unseparated phone | Bare 10 digits right after a phone label (Phone/Ph/PN/Tel/Mobile/Cell); keep `Order 5551234567` test |
| 5 | Name control (surname's first 4 letters, capitals); a 2-letter fragment too | CA 540 p1, both | Med | IRS name control | Derived from each entered surname: first 4 letters upper-case as a standalone word. 2-letter fragment: NOT matched (user decision 24 Sep: too many false positives) |
| 6 | Third-party designee PIN, 5 digits | CPA 1040 p2 | Med | PIN after its label, same or next line | Label rule: "Personal identification number (PIN)", "Designee ... PIN", "Self-select PIN" + 5 digits |
| 7 | Ages | Drake diagnostic summary | Low | Age values | **Remove** (user decision 24 Sep). Label rule (Age/Ages + 1-3 digit value) - probe the summary layout first |
| 8 | Occupations, county | 1040 p2, CA 540 p1 | Low | Labelled free text | **Remove** (user decision 24 Sep). Value after "occupation" / "County" labels - probe first |
| 9 | Other preparer's name + PTIN | CPA 1040 p2, CA 540 Side 6 | Low (third party) | Preparer IDs | Always-on `P` + 8 digits as a standalone word. Name: user enters it at the prompt (user decision 24 Sep) |

Order: 6, 9, then 4, 3 + 5, 2, 7 + 8, 1 (most probing). Each: masked probe of the real layout (output to a file),
synthetic tests incl. look-alikes to keep, full suites, then the user re-runs both files and the outside review
re-checks with masked reporting. Fallback for the long tail: return-first harvest (spec).

**DONE (25 Sep): 8 of the 9 items above, as rules** (synthetic tests incl. look-alikes; redactor 144/144, all suites
pass; NOT yet re-run on the real returns). One batched masked probe (`probe_labels.py`, now writes to
`redactor/diag_output/`, has NEAR/WIDGET geometry output) drove them. Probe showed item 1 is NOT comb boxes: an 8-digit
account in the row under an "Account number" table header.

| # | Rule | General? |
|---|---|---|
| 9 | `PTIN_RE`: P + 8 digits | Yes (fixed format) |
| 5 | `name_controls()`: first 4 letters from each word of an entered name, capitals, standalone. <4 letters skipped | Yes |
| 3 | `address_part_patterns()`: entered address's ZIP/PIN + city anywhere; house no. only on a line with that ZIP/city (80 chars) | Yes; 80 is arbitrary |
| 2 | `PAN_LOOSE_RE`: PAN with masked digits (2+ real) + anything joined by `&`; `PAN_LABEL_RE`: short PAN after a PAN label | Shape yes; `&` joiner from sample |
| 6 | `PIN5_RE`: 5 digits after a PIN label (same/next line). "Self-select PIN 12345" test flipped to redacted | Only when value follows label |
| 4 | `PHONE_LABEL_RE`: 10 bare digits after Phone/PN/Tel/Cell/Mobile | Same; spaced/dotted digits after a label not covered |
| 7 | `AGE_RE`: `Age[s] [on date]: ## ##` (colon required) | Sample-derived (Drake summary); table Age columns not caught |
| 1 | `ACCT_TABLE_RE`: first bare 5-17 digit run within 3 lines under an "Account number" header, last 4 kept | Partly; column not checked |
| 8 | Occupation, county: NOT done - values not next to labels. Superseded by harvest (below) | - |

Open: Drake D-400 p71/p73 have unlabelled bare 10-digit numbers - user to say whether they are phones.

**DECIDED (25 Sep): pattern rules can't be generic across untemplated broker/bank docs -> build HARVEST, replace the
scan->confirm flow.** User decisions (spec § "Session 25 Sep"): nightly batch over a queue folder, double blind, no
prompts, no confirm step; values from the Drake return in memory only; every file **overwritten in place** (temp file
then replace), return last; FAIL -> quarantine folder; REVIEW -> overwrite + flag folder for visual check; no backup.
Build: (1) harvest reader, 1040 header + refund account, synthetic return; (2) masked probe on a real Drake return;
(3) batch driver; (4) more forms: state -> Sch E -> 8938 -> rest (build order, not a limit).

**DONE (25 Sep): steps 1+2.** `redactor/harvest.py` (`harvest(pdf).entries()` -> `build_patterns`), 12 tests in
`redactor/test_harvest.py` (synthetic only). Reads by position: a label's box = up to the next label on its row and
the next label row on the page; value = first line, cut at a wide gap. Real full Drake print (masked report,
`harvest.py <pdf>`): all 1040 header fields, occupations, 2 phones found; apt/foreign/refund MISSING = empty on that
client (no direct deposit - comb boxes are letter glyphs). Not yet: dependents, state return, Sch E, 8938.

**DECIDED (25 Sep) for step 3 (batch driver):** queue = `review/redaction_queue/`, quarantine = `review/quarantine/`.
D-400 p71/p73 bare 10-digit footer numbers = Drake per-state form code + page, NOT phone, NOT a client code (user) -
LONGNUM blacking out part of it is harmless, leave it; no folder rename to a code. Folder and file names are still
scrubbed against the harvested names (a queue folder may be named after the client). Reuse from `review/redact.py`:
`redact_and_verify`, `safe_filename`, `scrub_text`, the OK/REVIEW/FAIL rule (`leftovers` -> FAIL, `no_text` -> REVIEW).
In-place overwrite must bypass the redactor CLI's "same input/output folder" guard (driver's own path, temp + replace).

**TODO (24 Sep): re-redact folders redacted before 24 Sep** (e.g. `client_bh1`) - the check-4 gate now also
flags phone, email, labelled DOB, PAN, Aadhaar, CA employer ID, account numbers and US addresses.

**GAP (24 Sep): label rules need the value right after the label.** Table layouts (1095-C DOB column, 1040 line
35 comb boxes) may not be caught - enter those values. Not yet tried on the two real files that showed the
account-number/address leaks.

**OPEN, UNRESOLVED (22 Sep): OCR-redacted pages can report `OK` with a real SSN/EIN/name still
visible.** Confirmed twice on the same real phone-photo W-2, two different ways:

1. First occurrence: `verify()`'s OCR re-read missed a spot that the *initial* detection pass also
   missed - an independent double-miss in the same run. Root-caused with `diag_redact.py` (not a
   coordinate/box-placement bug - box math checked out on every occurrence it did find, including 3
   stacked copies of the same W-2 in one photo). Mitigated by adding `confirm_passes` to
   `redact_and_verify()` (default 1, see its docstring): once `verify()` first comes back clean on a
   page that used OCR, one more independent OCR re-read must also come back clean before the result is
   trusted; a catch feeds back into the existing retry (capped at `extra_passes`). Regression-tested:
   `redactor/test_redact_and_verify.py` (6 tests, mocked, no tesseract needed) and two tests in
   `review/test_redact_wrapper.py::OcrTests` using the existing `_flaky_reader` harness, incl.
   `test_confirmation_pass_catches_a_miss_that_first_verify_also_missed`.
2. **Second occurrence, same file, AFTER the fix above landed: `passes=3, leftovers=[]` ("OK"), but the
   user visually confirmed the SSN was still exposed on the page.** `counts` showed `ID9: 1` while every
   other pattern on the page (EIN, the 4 matched name variants) showed `3` - i.e. one instance per each
   of the 3 stacked copies - meaning 2 of the page's 3 SSN occurrences were never detected AT ALL, by
   detection, the retry, or either confirmation read. This is not the same failure as (1): a random
   intermittent miss would eventually get caught by *some* pass; this looks like OCR consistently
   failing to read that specific occurrence every time (e.g. glare/skew/contrast at that exact spot in
   the photo) - more re-reads do not help a deterministic failure. `confirm_passes` does not fix this
   class of miss and no further fix has been attempted.

**Conclusion: an `OK` status on any OCR'd (image-only) page must not be trusted by itself.** A human
must visually check every OCR'd page before it is considered safe, full stop - this is no longer framed
as a "weaker guarantee," it is a confirmed, reproduced gap. Do not remove or weaken this requirement
without a fix that has been verified against this same real file.

**Next steps (not started):** likely needs image preprocessing before OCR (contrast/sharpen/deskew a
phone photo, distinct from a clean scanner image) to raise Tesseract's actual read reliability at the
source, rather than only re-reading the same weak signal more times. Possibly also a
lower-confidence-but-still-flag heuristic (e.g. any region tesseract read with very low per-word
confidence near a label like "SSN"/"social security" gets a mandatory REVIEW instead of being silently
trusted). Neither is built.

**Action for the user:** treat every OCR'd/image-only page across every client as needing a manual
visual check before delivery, regardless of status - not optional, not just for this one file.

**`diag_redact.py` (masked, safe-to-paste diagnostic dump) extended 22 Sep:** added `--prompt` (asks for
file/pages/names/SSNs interactively - keeps them off the command line and out of shell history, same
reasoning as `redact.py --prompt`) and full OCR-path diagnostics for image-only pages (previously it only
checked the text-layer path, which is silently a no-op on a scanned/photographed page) - shows OCR words
read, their computed boxes, and an independent OCR re-read of the output, plus a top-line
`redact_and_verify()` final verdict (status/passes/leftovers) using the real production function so the
tool's answer matches what a live run would report.

**Image-only pages: `--ocr` built 21 Sep (Tesseract + pixel black-out).** Opt-in. First real folder: 11 of 11 OK
with it (14 OCR'd pages in 5 files). Weaker guarantee than a text layer (OCR can miss text, verify uses the same
engine); a sideways picture or an unreadable page still makes the file `REVIEW`. Not handled: OCR digit misreads,
an unknown SSN whose dashes OCR lost (the standalone 9-digit rule only catches 9 contiguous digits).

**Solo first/last names are not removed from page text.** Deliberate: "Mary Smith" would collide with
other people, and existing tests require it to survive. Optional strict mode (redact a lone entered
first or last name in page text, accept false positives) was floated, not built. Until then only
full-name forms and literal addresses are removed.

**Not removed by design:** employer/payer names, phone numbers, DOB, account numbers. Only entered
names/addresses plus SSN/EIN patterns. Decide whether an optional "also redact these literals" list
(entered at the prompt, memory-only) is wanted.

**Morgan Stanley files show "expected object number" source warnings** (all three). PDF quirk, not
investigated. It is a warning, not a status change.

**Name-variant and filename scrubbing only exercised on one real run** (10 files + the Drake return).
Watch for a variant that survives on the next client. Printed filename lines are still treated as
sensitive.

**Housekeeping**
- `review_runs_redacted/` and `review_runs_names.json` are not in `.gitignore`. Ask before editing it.
- `review/` is still untracked, including the `--prompt` wrapper `review/redact.py` and its tests.
- Redactor changes (XMP, annotations, name variants, filenames, `.PDF` discovery) are committed
  separately once the git identity is set. Files are now LF (were CRLF in the working tree).
- Redactor test suite is a script: `cd redactor && ../review/.venv/bin/python test_redact.py`
  (95 checks). `redactor/test_redact_and_verify.py` is a real `unittest` module (6 tests) added 22 Sep -
  run it separately: `../review/.venv/bin/python -m unittest test_redact_and_verify`.

---

## Drake parser (`review/drake.py`)

Validated on ONE real return (TY2025, 2 pages, 48/48 lines, 13/13 identities). Unverified:
- TY2024 line map (never met a real return).
- Itemized returns (Schedule A lines).
- Refund return that carries an estimated-tax penalty. Line 37 includes line 38 on the owe side; how
  Drake prints the refund side is unknown, so a self-check failure there is a real flag.
- Returns longer than 2 pages.

---

## Extraction and comparison (check 4)

- Path B (local Ollama vision) fails on real multi-page docs: 4096-token context overflow,
  truncated JSON. `num_ctx` is never set in `extract_local`. About 7 min/page on CPU.
- Path A (Claude API) is blocked: no API key, and no third-party names may go out while the redactor
  is regex-only.
- **§5 eligibility gate, document-level: built (22 Sep) — `eligibility.py`.** Content-based detection
  (pdfplumber text, no model) of consolidated 1099s (1099-B present, or generic "consolidated
  statement" wording), Schedule K-1, 1099-OID. Wired into `check4_run.py` ahead of the redaction
  gate, so excluded files are never OCR'd or sent — real saving confirmed on `client_bh1`'s dry run:
  3 Morgan Stanley consolidated statements (2 pages each, all image-only) skipped, only 7 of 10
  files gated. Reported through the existing `unread` list (`step="eligibility gate"`), no report.py
  change needed. Return-level eligibility (Sch E/F, Sch C home office, 1099-S, seller-financed
  mortgage interest — the rest of SPEC.md §5.2) is **not** covered — those are properties of the
  return, not a document, and need more Drake-return parsing than `drake.py` has. Tests:
  `test_eligibility.py`, 8/8.
- Not built: the §7.2 GROUP 1/GROUP 2 report (user decision 22 Sep: v2, once Sch C/E/F workings are
  in scope — Group 1's value depends on there being a "workings" source to check against).
- **IRS copy-duplicate page filtering: built (22 Sep) — `page_filter.py`.** W-2/1099-INT/1099-DIV all
  legally print 2-4 numbered copies (Copy A/B/C/D/1/2 - same box values, different footer text).
  Sending every copy to the model wastes payload and risked double-counting a repeatable field
  (`box_17_state_income_tax`) if the model read duplicate copies as distinct entries. Wired into both
  `extract_api` and `extract_local` (`extract.py`'s `_drop_copy_pages`) - drops every copy after the
  first, before the model call, not relying on the model to notice. Dropped page indices are recorded
  on `ExtractionResult.dropped_pages` and printed by `check4_run.py` per file - never silent.
  **Known unresolved risk:** a genuinely multi-state W-2 can print a *different* state's box 17 on a
  state-specific copy (e.g. "Copy 2") rather than a true duplicate - a page-designator-only rule can't
  tell that apart from a real duplicate without reading box 17 first, which is what this runs ahead of.
  Only text-layer pages are checked; an image-only copy page isn't caught (would need the redaction
  OCR pass reused here). Tests: `test_page_filter.py`, 7/7; logic-only end-to-end check with a
  synthetic 2-copy W-2, no live model call.

---

## Docs

- `ARCHITECTURE.md` §2/§7 still lists checks 2a/3, dropped as out of scope (user's file, not edited).
- `README.md` top "Status" paragraph is stale (says nothing has run live). Table and Known gaps are current.
