"""Entry point for the tax document review pipeline.

    python run.py --docs ./client_docs --drake ./return.pdf --mode api
    python run.py --docs ./client_docs --drake ./return.pdf --mode local
    python run.py --docs ./client_docs --drake ./return.pdf --mode both

Pipeline: redact (Step 0, always) -> extract (Step 1, Claude API and/or local
Ollama) -> compare to the Drake return (Step 2) -> write one HTML report
(Step 3). No document that fails to produce an extraction is ever dropped
silently - it's recorded under "Unread documents" in the report.
"""
import importlib
import json
import sys
import time
from pathlib import Path

_REQUIRED = [
    ("anthropic", "anthropic"),
    ("fitz", "pymupdf"),
    ("pdfplumber", "pdfplumber"),
    ("pdf2image", "pdf2image"),
    ("PIL", "pillow"),
    ("requests", "requests"),
]


def _can_import(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def check_dependencies():
    missing = [pip_name for mod_name, pip_name in _REQUIRED if not _can_import(mod_name)]
    if missing:
        print("Missing required packages. Install them with:")
        print(f"  pip install {' '.join(missing)}")
        sys.exit(1)


def _to_list(csv: str) -> list:
    return [x.strip() for x in csv.split(",") if x.strip()]


def _write_extraction_json(dir_path: Path, result) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    out = dir_path / f"{Path(result.source_file).stem}.json"
    out.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")


def _parse_args():
    import argparse

    ap = argparse.ArgumentParser(description="Tax document review pipeline - Claude API vs. local vision A/B test")
    ap.add_argument("--docs", required=True, help="Folder of source tax documents (PDFs)")
    ap.add_argument("--drake", required=True, help="Path to the Drake return PDF")
    ap.add_argument("--mode", choices=["api", "local", "both"], required=True)
    ap.add_argument("--output", default=None, help="Output folder (default: review/review_runs/<timestamp>)")
    ap.add_argument("--names", default="", help='Comma-separated taxpayer names to redact, e.g. "John Smith"')
    ap.add_argument("--ssns", default="", help='Comma-separated known SSNs to redact, e.g. "123-45-6789"')
    ap.add_argument("--api-model", default=None, help="Claude model for Path A (default: claude-sonnet-4-6)")
    ap.add_argument("--api-key", default=None, help="Anthropic API key (default: resolved from environment)")
    ap.add_argument("--ollama-url", default=None, help="Ollama base URL (default: http://localhost:11434)")
    ap.add_argument("--local-model", default=None, help="Exact Ollama model name for Path B (default: auto-detect an installed LFM2.5 Vision model)")
    return ap.parse_args()


def main():
    check_dependencies()
    # Import review's own modules only after dependencies are confirmed present -
    # they import fitz/pdfplumber/requests/anthropic at module level.
    import redact
    import extract
    import compare
    import report

    args = _parse_args()
    api_model = args.api_model or extract.DEFAULT_API_MODEL
    ollama_url = args.ollama_url or extract.DEFAULT_OLLAMA_URL

    docs_dir = Path(args.docs).resolve()
    drake_path = Path(args.drake).resolve()
    if not docs_dir.is_dir():
        sys.exit(f"--docs folder not found: {docs_dir}")
    if not drake_path.is_file():
        sys.exit(f"--drake file not found: {drake_path}")

    source_pdfs = sorted(p for p in docs_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not source_pdfs:
        sys.exit(f"No PDFs found in {docs_dir}")

    out_dir = Path(args.output).resolve() if args.output else (
        Path(__file__).resolve().parent / "review_runs" / time.strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    redacted_dir = out_dir / "redacted"
    extractions_dir = out_dir / "extractions"

    print(f"Step 0: redacting {len(source_pdfs)} document(s) -> {redacted_dir}")
    try:
        redaction_results = redact.redact_folder(docs_dir, redacted_dir, _to_list(args.names), _to_list(args.ssns))
    except ValueError as e:
        sys.exit(str(e))
    redaction_by_file = {r.source_file: r for r in redaction_results}
    for r in redaction_results:
        print(f"  {r.status:<6} {r.source_file}")

    modes = ["api", "local"] if args.mode == "both" else [args.mode]
    extractions_by_mode = {}
    unread = []
    local_model = None

    if "api" in modes:
        print(f"Step 1: extracting via Claude API ({api_model})")
        import anthropic

        client = anthropic.Anthropic(api_key=args.api_key) if args.api_key else anthropic.Anthropic()
        results, auth_failed = [], False
        for pdf in source_pdfs:
            redaction = redaction_by_file.get(pdf.name)
            if auth_failed:
                unread.append({"source_file": pdf.name, "mode": "api", "step": "extraction",
                                "reason": "skipped after earlier auth/connection failure"})
                continue
            if redaction is None:
                unread.append({"source_file": pdf.name, "mode": "api", "step": "redaction",
                                "reason": "no redaction result (unexpected)"})
                continue
            form_hint = extract.guess_form_type(pdf.name)
            try:
                result = extract.extract_api(redaction, client, model=api_model, form_hint=form_hint)
                results.append(result)
                _write_extraction_json(extractions_dir / "api", result)
                print(f"  {result.status.upper():<9} {pdf.name} ({result.extraction_time_ms} ms)")
            except extract.RedactionGateError as e:
                unread.append({"source_file": pdf.name, "mode": "api", "step": "redaction gate", "reason": str(e)})
                print(f"  BLOCKED {pdf.name}: {e}")
            except extract.UnreadableDocument as e:
                # §3.1 - a first-class output category, not lumped in with a
                # model/network extraction failure.
                unread.append({"source_file": pdf.name, "mode": "api", "step": "file open", "reason": str(e)})
                print(f"  UNREADABLE {pdf.name}: {e}")
            except (anthropic.AuthenticationError, anthropic.APIConnectionError) as e:
                auth_failed = True
                unread.append({"source_file": pdf.name, "mode": "api", "step": "extraction",
                                "reason": f"{type(e).__name__}: {e}"})
                print(f"  FAIL   {pdf.name}: {e} - aborting remaining API calls")
            except Exception as e:
                unread.append({"source_file": pdf.name, "mode": "api", "step": "extraction",
                                "reason": f"{type(e).__name__}: {e}"})
                print(f"  FAIL   {pdf.name}: {e}")
        extractions_by_mode["api"] = results

    if "local" in modes:
        print(f"Step 1: extracting via local Ollama ({ollama_url})")
        results = []
        try:
            local_model = extract.resolve_local_vision_model(ollama_url, override=args.local_model)
            print(f"  using local model: {local_model}")
        except RuntimeError as e:
            print(f"  {e}")
            for pdf in source_pdfs:
                unread.append({"source_file": pdf.name, "mode": "local", "step": "model resolution", "reason": str(e)})
        if local_model:
            for pdf in source_pdfs:
                form_hint = extract.guess_form_type(pdf.name)
                try:
                    result = extract.extract_local(pdf, ollama_url=ollama_url, model=local_model, form_hint=form_hint)
                    results.append(result)
                    _write_extraction_json(extractions_dir / "local", result)
                    print(f"  {result.status.upper():<9} {pdf.name} ({result.extraction_time_ms} ms)")
                except extract.UnreadableDocument as e:
                    unread.append({"source_file": pdf.name, "mode": "local", "step": "file open", "reason": str(e)})
                    print(f"  UNREADABLE {pdf.name}: {e}")
                except Exception as e:
                    unread.append({"source_file": pdf.name, "mode": "local", "step": "extraction",
                                    "reason": f"{type(e).__name__}: {e}"})
                    print(f"  FAIL   {pdf.name}: {e}")
        extractions_by_mode["local"] = results

    print("Step 2: comparing to Drake return")
    comparisons_by_mode = {
        mode: compare.compare(results, drake_path)
        for mode, results in extractions_by_mode.items() if results
    }

    ab_rows = None
    if args.mode == "both":
        ab_rows = report.compute_ab_summary(extractions_by_mode.get("api", []), extractions_by_mode.get("local", []), unread)

    run_meta = {
        "docs folder": docs_dir,
        "drake return": drake_path,
        "mode": args.mode,
        "generated at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api model": api_model if "api" in modes else "-",
        "local model": local_model if "local" in modes and local_model else "-",
    }
    report_path = out_dir / "review_report.html"
    print("Step 3: writing report")
    report.build_report(run_meta=run_meta, redaction_results=redaction_results,
                         extractions_by_mode=extractions_by_mode, unread=unread,
                         comparisons_by_mode=comparisons_by_mode, ab_rows=ab_rows,
                         out_path=report_path)

    print(f"\nDone. Report: {report_path}")
    if unread:
        print(f"WARNING: {len(unread)} document(s) unread - see report for details.")

    total_extracted = sum(len(results) for results in extractions_by_mode.values())
    if total_extracted == 0:
        sys.exit(
            f"ERROR: 0 documents extracted across {len(modes)} mode(s) run "
            f"({', '.join(modes)}) - the report was written but is empty of "
            "results. Aborting with a non-zero exit so a batch/overnight run "
            "doesn't look clean when it wasn't."
        )


if __name__ == "__main__":
    main()
