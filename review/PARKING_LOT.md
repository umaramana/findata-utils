# Tax Review Pipeline — Parking Lot

Known gaps and deferred work for `review/` and `redactor/`. Status log of record is
`SPEC-revision-extraction.md`; this file is the open-items list. Last updated 21 Sep 2026.

---

## Redactor (`redactor/redact.py`, wrapper `review/redact.py`)

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
  (73 checks). `unittest` finds 0 tests there.

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
- Not built: the §5 eligibility gate, the §7.2 GROUP 1/GROUP 2 report.
- Check 4 has never run on the real return and its source docs.

---

## Docs

- `ARCHITECTURE.md` §2/§7 still lists checks 2a/3, dropped as out of scope (user's file, not edited).
- `README.md` top "Status" paragraph is stale (says nothing has run live). Table and Known gaps are current.
