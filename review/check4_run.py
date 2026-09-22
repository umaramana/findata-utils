"""Check 4 (source documents vs the Drake return) over Path A, with masked console output.

    export ANTHROPIC_API_KEY=...            # in this shell only
    python check4_run.py --docs <redacted folder> [--docs <another>] --drake <the return> --out <folder> --dry-run
    python check4_run.py --docs <redacted folder> [--docs <another>] --drake <the return> --out <folder>

--docs takes folders of REDACTED PDFs (redact.py --prompt --ocr output). The Drake return is excluded from
the source documents if it sits in one of them. Nothing leaves this machine except the redacted pages of
files that pass the gate below, to the Claude API.

Gate. extract_api refuses anything whose RedactionResult is not "OK". redact.py's status is only printed, not
saved, so this driver re-checks each file itself with the redactor's own primitives: SSN / EIN / standalone
9-digit shapes, metadata, annotations, and OCR of every image-only page (which must also be readable). It
cannot re-check client NAMES - it does not know them; that check ran in the terminal where you typed them.

Console output never names a file or prints an amount: files are shown by position (A#1, B#2, ...), amounts
only with --show-amounts. Full results (fields, amounts, filenames) go to --out on disk: extraction JSON per
file, errors.log, and review_report.html - open those yourself.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import fitz

import redact  # puts the repo root on sys.path
from redactor import redact_ocr
from redactor.redact import build_patterns, verify

import compare
import drake
import eligibility
import extract
import report


def source_files(folders, drake_path):
    """[(label, path)] - A#1, A#2 ... per folder, in sorted order, minus the Drake return."""
    out = []
    for letter, folder in zip("ABCDEFGH", folders):
        pdfs = sorted(p for p in Path(folder).resolve().rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"
                      and p.resolve() != drake_path)
        out += [(f"{letter}#{n}", p) for n, p in enumerate(pdfs, 1)]
    return out


def gate(path, ocr_verify=True):
    """RedactionResult for a redacted file, from the redactor's generic checks (see module docstring)."""
    patterns = build_patterns([], [])
    ocr_pages, unreadable, leftovers = [], [], []
    with fitz.open(path) as doc:
        image_only = [i for i, pg in enumerate(doc) if not pg.get_text().strip()]
        for i in image_only:
            if not ocr_verify:
                unreadable.append(i + 1)
                continue
            words = redact_ocr.read_words(doc[i])
            if not redact_ocr.readable(words)[0]:
                unreadable.append(i + 1)
                continue
            ocr_pages.append(i + 1)
            texts = [t for t, _ in redact_ocr.streams(words)]
            leftovers += [f"p{i + 1}-ocr:{label}" for label, rx in patterns if any(rx.search(t) for t in texts)]
    leftovers += verify(path, patterns)  # text layers, metadata, annotations
    status = "FAIL" if leftovers else ("REVIEW" if unreadable else "OK")
    return redact.RedactionResult(path.name, path, status, {}, unreadable, ocr_pages, leftovers)


def main():
    ap = argparse.ArgumentParser(description="Check 4 over Path A, masked output.")
    ap.add_argument("--docs", action="append", required=True, help="Folder of redacted source PDFs (repeatable)")
    ap.add_argument("--drake", required=True, help="The Drake return PDF (original or redacted; read locally only)")
    ap.add_argument("--out", required=True, help="Folder for full results (JSON, errors.log, HTML report)")
    ap.add_argument("--model", default=extract.DEFAULT_API_MODEL)
    ap.add_argument("--max-tokens", type=int, default=extract.DEFAULT_MAX_TOKENS,
                    help=f"Per-call output token cap (default {extract.DEFAULT_MAX_TOKENS}); "
                         "raise it if a long document's JSON is coming back truncated")
    ap.add_argument("--dry-run", action="store_true", help="Run the gate and show what would be sent; no API call")
    ap.add_argument("--no-ocr-verify", action="store_true",
                    help="Skip the OCR re-check of image pages (they are then treated as unreadable = not sent)")
    ap.add_argument("--show-amounts", action="store_true", help="Also print source total / return amount per row")
    args = ap.parse_args()

    drake_path = Path(args.drake).resolve()
    if not drake_path.is_file():
        sys.exit("--drake file not found")
    files = source_files(args.docs, drake_path)
    if not files:
        sys.exit("no PDFs found in --docs")
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in this shell (read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY)")
    out = Path(args.out).resolve()
    (out / "extractions" / "api").mkdir(parents=True, exist_ok=True)

    ret = drake.parse_drake(drake_path)
    integrity = drake.verify_arithmetic(ret)
    print(f"Drake return: arithmetic self-check {integrity.status} ({integrity.lines_with_values} lines with values)")
    if integrity.status != "PASS":
        print("  the Drake side of the comparison cannot be trusted - stopping")
        sys.exit(1)

    print(f"\nEligibility (SPEC.md §5.2, document-level): {len(files)} source file(s)")
    ineligible = []
    for label, path in files:
        reason = eligibility.classify(path)
        if reason:
            ineligible.append((label, path, reason))
            print(f"  {label}: SKIPPED - ineligible ({reason})")
    excluded_labels = {el for el, _, _ in ineligible}
    eligible_files = [(l, p) for l, p in files if l not in excluded_labels]
    if ineligible:
        print(f"  {len(ineligible)} of {len(files)} file(s) excluded; not gated, not sent")

    print(f"\nGate: {len(eligible_files)} source file(s)")
    t0, gated = time.monotonic(), []
    for label, path in eligible_files:
        red = gate(path, ocr_verify=not args.no_ocr_verify)
        gated.append((label, red))
        with fitz.open(path) as doc:
            pages = len(doc)
        print(f"  {label}: {red.status:<6} pages={pages} ocr_pages={red.ocr_pages} unreadable_pages={red.no_text_pages} "
              f"leftovers={len(red.leftovers)} form_hint={extract.guess_form_type(path.name)}")
    print(f"  gate took {int(time.monotonic() - t0)}s")
    sendable = [(l, r) for l, r in gated if r.status == "OK"]
    print(f"\n{len(sendable)} of {len(gated)} gated file(s) would be sent to {args.model}"
          f" ({len(ineligible)} more excluded as ineligible, see above)")
    if args.dry_run:
        return
    if len(sendable) != len(gated):
        print("Some files did not pass the gate; they are reported as unread and not sent.")

    import anthropic
    client = anthropic.Anthropic()
    results, errlog = [], []
    unread = [{"source_file": path.name, "mode": "api", "step": "eligibility gate", "reason": f"ineligible: {reason}"}
              for _, path, reason in ineligible]
    print("\nExtraction (Path A)")
    for label, red in gated:
        if red.status != "OK":
            unread.append({"source_file": red.source_file, "mode": "api", "step": "redaction gate",
                           "reason": f"gate status {red.status}"})
            print(f"  {label}: NOT SENT (gate {red.status})")
            continue
        try:
            res = extract.extract_api(red, client, model=args.model, form_hint=extract.guess_form_type(red.source_file),
                                       max_tokens=args.max_tokens)
        except Exception as e:  # details on disk only: a parse error can quote the model's output
            unread.append({"source_file": red.source_file, "mode": "api", "step": "extraction", "reason": type(e).__name__})
            errlog.append(f"{label} {red.source_file}: {type(e).__name__}: {e}")
            print(f"  {label}: FAIL ({type(e).__name__})")
            continue
        results.append(res)
        (out / "extractions" / "api" / f"{label.replace('#', '_')}.json").write_text(
            json.dumps(res.to_dict(), indent=2), encoding="utf-8")
        dropped_note = f" dropped_copy_pages={res.dropped_pages}" if res.dropped_pages else ""
        print(f"  {label}: {res.status.upper():<18} form={res.form_type} fields={len(res.fields)} "
              f"missing={res.missing_required} rejected={res.verification_failures} routes={''.join(r[0].upper() for r in res.page_routes)} "
              f"{res.extraction_time_ms} ms{dropped_note}")
    if errlog:
        (out / "errors.log").write_text("\n".join(errlog), encoding="utf-8")

    print("\nComparison to the Drake return (source totals vs return; $1 tolerance)")
    rows = compare.compare(results, drake_path)
    for row in rows:
        line = f"  {row.category:<24} {row.status:<14} docs_contributing={len({c[0] for c in row.contributions})}"
        if row.diff is not None and row.status == "FLAG":
            line += f"  source {'>' if row.diff > 0 else '<'} return"
        if args.show_amounts:
            line += f"  source={row.source_total} return={row.drake_line}"
        print(line)
    n_unsent = len(gated) - len(results)
    if n_unsent:
        print(f"\n  NOTE: {n_unsent} of {len(gated)} source file(s) produced no extraction; their amounts are missing "
              "from the totals, so a FLAG above can be a coverage gap and not a return error.")

    report_path = out / "review_report.html"
    report.build_report(
        run_meta={"docs": ", ".join(args.docs), "drake return": drake_path, "mode": "api", "api model": args.model,
                  "max tokens": args.max_tokens, "generated at": time.strftime("%Y-%m-%d %H:%M:%S"), "local model": "-"},
        redaction_results=[r for _, r in gated], extractions_by_mode={"api": results}, unread=unread,
        comparisons_by_mode={"api": rows}, ab_rows=None, out_path=report_path)
    print(f"\nFull results (amounts, filenames) on disk only: {out}")


if __name__ == "__main__":
    main()
