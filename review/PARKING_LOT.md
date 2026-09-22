# Tax Review Pipeline — Parking Lot

Known gaps and deferred work for `review/` and `redactor/`. Status log of record is
`SPEC-revision-extraction.md`; this file is the open-items list. Last updated 22 Sep 2026.

---

## Redactor (`redactor/redact.py`, wrapper `review/redact.py`)

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
