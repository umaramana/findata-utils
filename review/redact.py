"""Step 0 - redaction gate.

Thin wrapper around the existing redactor/redact.py utility - imported, not
modified or reimplemented. Path A (Claude API) may only ever see a document
that has gone through here and come back with status "OK"; extract.py enforces
that as a hard check, not just a convention (see extract.py: extract_api).
"""
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import fitz

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from redactor import intake
from redactor.redact import (  # existing utility; 21 Sep 2026 added XMP deletion + filename scrubbing
    build_patterns, redact_and_verify, redact_file, safe_filename, scrub_text, unique_name, verify,
)


@dataclass
class RedactionResult:
    source_file: str
    redacted_path: Path | None
    status: str  # "OK" | "REVIEW" | "FAIL"
    counts: dict = field(default_factory=dict)
    no_text_pages: list = field(default_factory=list)
    ocr_pages: list = field(default_factory=list)  # pages redacted from OCR (weaker check than a text layer)
    leftovers: list = field(default_factory=list)
    error: str | None = None
    mupdf_notes: list = field(default_factory=list)  # de-duplicated PDF-library messages, e.g. '22x ...'
    passes: int = 1  # >1: OCR re-read the output and found more to redact (see redactor.redact_and_verify)


def _collect_mupdf_notes() -> list:
    """MuPDF messages since the last call, one line each with a count.

    MuPDF logs the same complaint once per page/object ("cannot create appearance stream for
    <vendor> annotations" x22), and each message appears both with and without an "unsupported
    error:" style prefix. Collapse both.
    """
    lines = [l.strip() for l in fitz.TOOLS.mupdf_warnings(reset=True).splitlines() if l.strip()]
    counts = Counter(lines)
    longest = [l for l in counts if not any(l != o and l in o for o in counts)]
    return [f"{max(c for l, c in counts.items() if l in k)}x {k}" for k in sorted(longest)]


def _normalize_ssns(ssns) -> list:
    """Same digit-only, 9-digit validation as redact.py's own CLI (main()) -
    reimplemented here only because we call build_patterns() directly instead
    of going through that CLI's argument parsing."""
    out = []
    for n, raw in enumerate(ssns, 1):
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 9:
            raise ValueError(f"--ssns: entry #{n} ({raw!r}) is not 9 digits")
        out.append(digits)
    return out


def _names_for(rel_path: Path, names_by_file: dict, default_names) -> list:
    return list(names_by_file.get(str(rel_path)) or names_by_file.get(rel_path.name) or default_names)


def redact_tree(src_root: Path, out_root: Path, names_by_file: dict | None = None,
                 default_names=(), default_ssns=(), ocr: bool = False) -> list[RedactionResult]:
    """Redact every PDF under src_root (recursively, any depth) into a mirrored
    tree under out_root. Unlike redact_folder (one folder = one names list),
    names_by_file maps a file's basename OR its path relative to src_root to
    the names to redact for THAT file specifically - lets one call cover a
    tree where different subfolders/files belong to different clients (e.g.
    review_runs/w2/ has ~10 different clients' W-2s in one folder).

    SSN/EIN are always redacted regardless of the mapping (build_patterns
    includes them unconditionally). A file with no entry in names_by_file
    falls back to default_names - still gets SSN/EIN, just no name redaction,
    so it's REVIEW-worthy rather than silently unsafe.

    ocr=True: pages with no text layer are read with OCR and redacted from what it finds (needs
    `tesseract`); a file can then be OK although some pages were only OCR-checked (ocr_pages)."""
    names_by_file = names_by_file or {}
    results, used = [], set()
    fitz.TOOLS.mupdf_display_errors(False)  # collected per file below instead of flooding the terminal
    try:
        return _redact_tree(src_root, out_root, names_by_file, default_names, default_ssns, results, used, ocr)
    finally:
        fitz.TOOLS.mupdf_display_errors(True)


def _redact_tree(src_root, out_root, names_by_file, default_names, default_ssns, results, used, ocr=False):
    for src in sorted(p for p in src_root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"):
        _collect_mupdf_notes()  # discard anything left over from the previous file
        rel = src.relative_to(src_root)
        names = _names_for(rel, names_by_file, default_names)
        # Folder and file names can carry the client's name too - scrub every path part.
        safe_rel = Path(*[scrub_text(part, names) for part in rel.parts[:-1]], safe_filename(rel.name, names))
        dst = out_root / unique_name(str(safe_rel), used)
        dst.parent.mkdir(parents=True, exist_ok=True)
        patterns = build_patterns(names, _normalize_ssns(default_ssns))
        try:
            ocr_pages = []
            counts, no_text, leftovers, passes = redact_and_verify(src, dst, patterns, ocr=ocr, ocr_pages=ocr_pages)
        except Exception as e:  # keep going on a bad file, report it
            results.append(RedactionResult(str(rel), None, "FAIL", error=str(e)))
            continue
        status = "FAIL" if leftovers else ("REVIEW" if no_text else "OK")
        results.append(RedactionResult(str(rel), dst, status, counts, no_text, ocr_pages, leftovers,
                                       mupdf_notes=_collect_mupdf_notes(), passes=passes))
    return results


def redact_folder(src_dir: Path, out_dir: Path, names=(), ssns=()) -> list[RedactionResult]:
    """Redact every PDF in src_dir into out_dir using redactor/redact.py's own primitives.

    Mirrors redact.py's CLI loop (build_patterns -> redact_file -> verify) exactly,
    so behavior matches `python redactor/redact.py` byte-for-byte; nothing here
    re-implements detection or redaction.

    Status per file:
      OK      - verified clean, safe to send to a cloud API.
      REVIEW  - has page(s) with no text layer (e.g. scanned) that could not be
                redacted; NOT safe for the cloud path.
      FAIL    - sensitive text still present after redaction; NOT safe for the
                cloud path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    patterns = build_patterns(list(names), _normalize_ssns(ssns))
    results, used = [], set()
    for src in sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".pdf"):
        dst = out_dir / unique_name(safe_filename(src.name, names), used)
        try:
            counts, no_text = redact_file(src, dst, patterns)
            leftovers = verify(dst, patterns)
        except Exception as e:  # keep going on a bad file, report it
            results.append(RedactionResult(src.name, None, "FAIL", error=str(e)))
            continue
        status = "FAIL" if leftovers else ("REVIEW" if no_text else "OK")
        results.append(RedactionResult(src.name, dst, status, counts, no_text, [], leftovers))
    return results


def _anonymize_for_display(counts: dict, leftovers: list, names: list) -> tuple:
    """SSN/EIN pattern labels are already anonymous (build_patterns never uses
    the digits themselves as a label - see its docstring: "Labels never
    contain the SSN itself, so console output stays safe to share"). Name
    patterns are NOT anonymous the same way - build_patterns uses the literal
    name as its own label (`patterns.append((name, rx))`), so `counts` and
    `leftovers` would otherwise put the name itself in this CLI's stdout,
    which defeats the whole point of keeping names out of the caller's
    context. Replace each name in `names` with a positional "name#N"
    placeholder wherever it appears as a counts key or inside a leftovers
    "pN:label" entry, before anything gets printed."""
    placeholder = {name: f"name#{i + 1}" for i, name in enumerate(names)}
    safe_counts = {placeholder.get(k, k): v for k, v in counts.items()}
    safe_leftovers = []
    for entry in leftovers:
        page, _, label = entry.partition(":")
        safe_leftovers.append(f"{page}:{placeholder.get(label, label)}")
    return safe_counts, safe_leftovers


def skipped_files(src_root) -> dict:
    """{extension: count} of files under src_root that redact_tree does not process (i.e. not PDFs).

    Extensions only, never names: a skipped file is reported, not silently dropped, but a filename
    can carry the client's name.
    """
    return dict(Counter(p.suffix.lower() or "(no extension)" for p in Path(src_root).rglob("*")
                        if p.is_file() and p.suffix.lower() != ".pdf"))


def prompt_for_client_details(src_root) -> tuple:
    """Interactive intake of one client's names/addresses/SSNs -> (entries, ssns).

    Kept in memory for this run only - never written to disk, never passed on a
    command line (so not in shell history), never echoed back. Refuses to run
    without a real terminal: an assistant session or a pipe would put the client's
    names somewhere they must not go.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("--prompt needs an interactive terminal. Run it yourself in your own shell - not through an "
                 "assistant session, a pipe, or a script - so the names stay on this machine and out of any log.")
    import getpass

    while True:
        print(f"Redacting every PDF under {src_root} for ONE client. Nothing you type is saved.\n{intake.INSTRUCTIONS}\n"
              "Redacted without being entered: phone numbers written 555-123-4567 / (555) 123-4567, every email,\n"
              "a DOB next to a 'Date of birth'/'DOB' label, PAN, Aadhaar, CA employer ID, US street/PO box/city-ZIP\n"
              "lines, and account numbers (11+ digits, or after an 'Account no'/'A/c'/'Folio' label; last 4 kept).\n"
              "Enter India addresses, employer names and any other account number.")
        entries, ssns = intake.read_entries()
        print("\nKnown SSNs (9 digits, any format; input is hidden). Also catches SSNs written without hyphens or "
              "masked to the last 4. Blank line when done.")
        while True:
            raw = getpass.getpass("  SSN (hidden)> ").strip()
            if not raw:
                break
            try:
                _normalize_ssns([raw])
            except ValueError:
                print("    not 9 digits - skipped")
                continue
            ssns.append(raw)
        if not entries:
            sys.exit("No names entered - refusing to run without any name to redact. Nothing written.")
        print("\nEntered (masked):")
        print("\n".join(intake.summary_lines(entries, len(ssns))))
        answer = input("Type 'yes' to redact with these, 'redo' to enter them again, anything else to cancel: ")
        if answer.strip().lower() == "yes":
            break
        if answer.strip().lower() != "redo":
            sys.exit("Cancelled - nothing written.")
        print("\033[2J\033[H", end="")
    print("\033[2J\033[H", end="")  # clear the screen so the names don't sit in view or scrollback
    return entries, ssns


def _main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Redact every PDF under a folder tree (recursively) using redact_tree(). "
                     "For a tree where different files/subfolders belong to different clients, "
                     "pass --names-file with a per-file mapping instead of one flat --names list.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Example --names-file:\n'
               '  {\n'
               '    "int/2025 1099(INT) - Treasury-Jones.pdf": ["Jones"],\n'
               '    "w2/Jane W2.pdf": ["Jane"]\n'
               '  }\n'
               "Keys may be the file's basename or its path relative to --src.",
    )
    ap.add_argument("--src", required=True, help="Root folder of source PDFs (searched recursively)")
    ap.add_argument("--out", required=True, help="Root folder for redacted copies (mirrors --src's structure)")
    ap.add_argument("--prompt", action="store_true",
                     help="Ask for the client's names, addresses and SSNs interactively in this terminal "
                          "(kept in memory only, nothing saved). One run = one client folder. Recommended.")
    ap.add_argument("--ocr", action="store_true",
                     help="Read pages with no text layer with OCR (needs `tesseract`) and redact what it finds. "
                          "Without it those pages make the file REVIEW. OCR can miss text: an OK that includes "
                          "OCR'd pages is a weaker guarantee (see ocr_pages in the output).")
    ap.add_argument("--names-file", default=None,
                     help="JSON file: {\"relative/path.pdf\" or \"filename.pdf\": [\"Name\", ...]}")
    ap.add_argument("--default-names", default="",
                     help='Comma-separated names applied to any file with no entry in --names-file, '
                          'e.g. "John Smith, Jane Doe"')
    args = ap.parse_args()
    if args.prompt and (args.names_file or args.default_names):
        sys.exit("--prompt cannot be combined with --names-file / --default-names.")

    default_ssns = []
    if args.prompt:
        default_names, default_ssns = prompt_for_client_details(Path(args.src).resolve())
        names_by_file = {}
    else:
        names_by_file = json.loads(Path(args.names_file).read_text(encoding="utf-8")) if args.names_file else {}
        default_names = [n.strip() for n in args.default_names.split(",") if n.strip()]

    if args.ocr:
        from redactor import redact_ocr
        redact_ocr.require()
    results = redact_tree(Path(args.src).resolve(), Path(args.out).resolve(), names_by_file, default_names,
                          default_ssns, ocr=args.ocr)
    for r in results:
        names = _names_for(Path(r.source_file), names_by_file, default_names)
        safe_counts, safe_leftovers = _anonymize_for_display(r.counts, r.leftovers, names)
        # r.source_file is the original path and may carry the client's name - print the scrubbed form.
        print(f"{r.status:8} {scrub_text(r.source_file, names)}  counts={safe_counts}  no_text_pages={r.no_text_pages}  ocr_pages={r.ocr_pages}{f' passes={r.passes}' if r.passes > 1 else ''}  leftovers={safe_leftovers}")
        for note in r.mupdf_notes:
            print(f"         note: {note}")
    n_notes = sum(1 for r in results if r.mupdf_notes)
    skipped = skipped_files(Path(args.src).resolve())
    n_ok = sum(1 for r in results if r.status == "OK")
    n_review = sum(1 for r in results if r.status == "REVIEW")
    n_fail = sum(1 for r in results if r.status == "FAIL")
    print(f"\n{len(results)} files: {n_ok} OK, {n_review} REVIEW (no text layer on some page), {n_fail} FAIL (sensitive text still present)")
    if skipped:
        print("NOT redacted (not PDFs, left out): " + ", ".join(f"{n} x {ext}" for ext, n in sorted(skipped.items())))
    if not results:
        print("WARNING: no PDF files found under --src.")
    if n_notes:
        print(f"{n_notes} file(s) carried PDF-library notes (above). They describe unusual content in the source file "
              "and do not by themselves mean redaction failed - the OK/REVIEW/FAIL status is what counts.")


if __name__ == "__main__":
    _main()
