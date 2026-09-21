# Tax document review pipeline

A/B testing pipeline: extracts fields from tax documents via the Claude API
(Path A, redacted copies) and/or a local Ollama vision model (Path B,
originals, fully offline), then compares totals against a Drake tax return
and writes one HTML report.

## Files

| File | Role |
|---|---|
| `redact.py` | Step 0 — thin wrapper around `../redactor/redact.py` (not modified). Only files verified `"OK"` (redacted, no leftover PII, no un-redactable scanned pages) are eligible for Path A. |
| `extract.py` | Step 1 — both extraction paths. `extract_api` hard-refuses (raises `RedactionGateError`) on anything not verified `"OK"` by Step 0. `extract_local` never imports `anthropic`; local model name is auto-detected from what's installed in Ollama, never hardcoded. |
| `drake.py` | **Capability A** - Drake return parser. Reads the Form 1040 face lines (pdfplumber, no model) by line-id marker with a label-line fallback; reports each line as value / blank / not_found / ambiguous. `verify_arithmetic()` re-derives the return's own totals (11 = 9 - 10, 33 - 24 = refund - owed, ...) to confirm the parse matched the layout. `python drake.py return.pdf` prints a masked line-state table (add `--values` for amounts). |
| `compare.py` | Step 2 - source-document totals vs. the Drake return (reads the Drake side through `drake.py`), $1 tolerance, per category (wages, taxable/tax-exempt interest, ordinary dividends, W-2 withholding). |
| `test_drake.py` | `python -m unittest test_drake` - synthetic 1040s in a printed-form layout. |
| `test_redact_wrapper.py` | `python -m unittest test_redact_wrapper` - names-file entries (incl. addresses), scrubbed output names, CLI never prints a name. |
| `img_to_pdf.py` | Turns JPEG/PNG photos of documents into one-page PDFs (EXIF rotation applied, EXIF dropped) so `redact.py` can take them. `python img_to_pdf.py --src <folder> --out <folder>`; then `redact.py --prompt --ocr` on the output folder. Tests: `python -m unittest test_img_to_pdf`. |
| `check4_run.py` | Check 4 over Path A with masked console output: re-checks each redacted file itself (generic SSN/EIN/9-digit, metadata, annotations, OCR readability), sends only files that pass, compares to the return (incl. W-2 box 2 vs line 25a). `--dry-run` shows what would be sent. Full results go to `--out` on disk. |
| `report.py` | Step 3 — single self-contained HTML report: redaction status, extraction trace, comparison table(s), A/B summary (mode=both), and an explicit "Unread documents" section — nothing is ever dropped silently. |
| `run.py` | CLI entry point. Checks all dependencies are importable before doing anything else; prints the `pip install` command and exits cleanly if not. |
| `make_test_docs.py` | Generates synthetic W-2/1099-INT/1099-DIV + a matching fake Drake return, for testing without real client data. Also generates a 1098 as an out-of-scope regression case (SPEC.md §1/§10) - extract.py should report it UNKNOWN, not force it into another form type. |

Status as of this writeup: **built, unit-logic-tested with stubbed dependencies
(no live API/Ollama run performed yet)**, and **not committed to git** —
`review/` is untracked, `.gitignore` has an uncommitted edit adding
`review/review_runs/`, `review/test_docs/`, `review/return.pdf` to the
ignore list (run output can contain real client financial data).

## One-time setup (run inside your WSL Ubuntu shell, not PowerShell)

Get there from PowerShell with:
```powershell
wsl -d Ubuntu
```
Then, inside that bash shell:

```bash
cd /mnt/c/Users/rasri/findata-utils/review

# Python packages
pip install anthropic pymupdf pdfplumber pdf2image pillow requests

# poppler binary (pdf2image needs this on PATH, it's not a pip package)
sudo apt install poppler-utils
```

### Claude API key (Path A)

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx
```
`export` (bash) — not PowerShell's `$env:` syntax, only if you're in bash.
This only lasts the current shell session; add it to `~/.bashrc` to persist.
The machine you run `run.py` on needs outbound internet access to reach
`api.anthropic.com` for this to work.

### Local Ollama vision model (Path B — fully local, zero outbound calls)

```bash
ollama serve &            # if not already running as a service
ollama pull <name>        # any vision-capable model, e.g. qwen2.5vl:3b
```
`run.py` auto-detects the installed model: if exactly one model is present
in `ollama list`, it's used automatically; if there are several, pass
`--local-model <name>` to pick one. Model *choice* (which one to actually use
for Path B) is decided by `harness.py` (§4.0.9), not guessed here.

## Running it

### 1. Smoke test with synthetic data (do this first)

```bash
python make_test_docs.py --out ./test_docs
python run.py --docs ./test_docs --drake ./return.pdf --mode both
```

This writes `review_runs/<timestamp>/review_report.html`. The synthetic
Drake return is constructed to exactly match the synthetic source docs, so
every comparison row should come back MATCH on a clean run.

To view the report from a headless remote box, copy it back:
```bash
scp <user>@<remote-host>:/mnt/c/Users/rasri/findata-utils/review/review_runs/*/review_report.html .
```

### 2. Real client documents

```bash
python run.py --docs /path/to/client_docs --drake /path/to/return.pdf \
    --mode both --names "Jane Client" --ssns "123-45-6789"
```

- `--names` / `--ssns` are passed straight through to the redactor for name
  and known-SSN-format matching. The generic SSN pattern (`###-##-####`) is
  always caught regardless of these flags.
- `--mode api` or `--mode local` run a single path only.
- `--output <dir>` overrides the default `review_runs/<timestamp>` location.
- `--api-model` / `--ollama-url` / `--api-key` override the defaults if needed.

## Redacting a real client folder (do this before anyone or anything else reads it)

Run in your own WSL terminal - **not** through an assistant session. One run = one client folder.

```bash
cd /mnt/c/Users/rasri/findata-utils/review
.venv/bin/python redact.py --src review_runs/client1 --out review_runs_redacted/client1 --prompt --ocr
```

`--ocr` (needs `sudo apt install tesseract-ocr`) reads pages that have no text layer, redacts what OCR finds there
(the pixels under each match are blanked) and re-reads the output page. Without it, one scanned page makes the
whole file `REVIEW`. The status line lists `ocr_pages`. **An OK that includes OCR'd pages is a weaker guarantee**:
OCR can miss or misread text, and the check uses the same engine. A page OCR cannot read (under 5 words, mean
confidence under 60, or a picture that is physically sideways) still makes the file `REVIEW`.

`--prompt` asks, in that terminal, for the client's names and addresses (one per line, exactly as
printed - list every variant, spouse and dependents included) and known SSNs (hidden input). Nothing
is saved to disk or put on the command line, and it refuses to run without a real terminal. Every
file under `--src` is redacted with those entries. Expect `OK` on every line; do not open any file
marked `REVIEW` or `FAIL`.

Removed from the copies: SSNs and EINs (dashed form always; any form for SSNs you enter), any standalone
9-digit number (an EIN or SSN printed without dashes; account numbers and CUSIPs of exactly 9 digits go too), the names
and addresses you enter, PDF metadata including XMP, and the same text in the output filenames.
Not removed: anything you did not enter - employer/payer names, phone, DOB, account numbers.
A `note:` line under a file (e.g. `22x ... cannot create appearance stream for FOSINDEX annotations`) is the PDF
library complaining about a vendor-specific annotation it cannot render. It is a warning, not a failure - the
status column is what counts.

Annotations are **deleted** from the redacted copies (form fields are kept): they are not page text, so the
redactor cannot see what they hold, and in practice a vendor marker carried a client name and an SSN. Names left
in a kept form field are detected and fail the file.

**Name variants are matched automatically.** For "Robert Alan Smith" the redactor also removes Robert Smith,
Robert A. Smith, R. Smith, Smith, Robert, SMITH ROBERT A, and (when you gave no middle name) one middle initial.
A first or last name *on its own* is not removed from page text - it would also hit other people ("Mary Smith").
An entry with a digit (an address) or a single word is matched literally, so list each address as printed.

**Filenames are scrubbed harder than page text:** every part of a name on its own, plus a truncated form of any
long name (a client named "Ramachandran" also loses "rama" in a filename). Still, treat printed filename lines as
sensitive until you have looked at them.

## Running the Drake parser (local, no model, nothing leaves the machine)

```bash
cd /mnt/c/Users/rasri/findata-utils/review
.venv/bin/python drake.py "/path/to/the return.pdf"            # masked: line states only
.venv/bin/python drake.py "/path/to/the return.pdf" --values   # adds amounts (do not paste)
```

It reads the original return - no redaction step is needed for the script itself. The default output has no
filename and no amounts (line id, value/blank/not_found/ambiguous, method, page, and an arithmetic PASS/FAIL), so it
is safe to paste. Redaction is only needed if someone other than you (an assistant) is to open the document.

## Known gaps / things to verify on first real run

- **`drake.py` has been run on one real return (TY2025, 2 pages).** Every line was read
  and all 13 arithmetic identities passed. The TY2024 line map has never met a real
  return, and one return does not cover refunds with a penalty, itemized returns, or
  a return with more pages. On any new return run `python drake.py return.pdf` first: the
  state table shows which lines were read and the arithmetic self-check says whether to
  trust them; a failed self-check means the Drake side of a comparison can't be trusted.
  Each tax year has its own line map (2024, 2025); another year is read with the latest
  map and warned about. What the real print taught the parser: page 1's "FORM" heading is
  rotated (no row starts "Form 1040"); Drake prints no dot leaders, so an empty box is a
  marker with nothing after it; rows must be grouped by vertical centre; and line 37
  includes the line 38 estimated-tax penalty.
- **Local vision inference is slow on constrained hardware.** On a CPU-only,
  8GB WSL box with `qwen2.5vl:3b`, a single-page extraction call took ~7
  minutes at 100 DPI (`extract.DEFAULT_RENDER_DPI`) — and never completed at
  200 DPI within 10+ minutes, because the vision encoder tiles the page image
  into many 512-token batches and that tiling, not generation length, is the
  bottleneck. `extract_local`'s request timeout is set to 900s accordingly.
  If Path B ever runs on beefier hardware (GPU, more RAM), DPI and timeout
  can both go back up. See `harness.py` (§4.0.9) for measured repeatability.
- **Nothing here is committed to git.** Review the diff (`git status`,
  `git diff .gitignore`) and stage/commit when you're ready — I did not do
  this automatically.
