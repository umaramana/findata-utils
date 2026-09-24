"""Step §4.0.9 - repeatability + model-selection harness.

Answers two questions in one run: is extraction stable across repeated calls
on the same document, and (when comparing --models) which local model to use
for Path B. Reuses extract.py's own extraction calls - no separate PDF-to-
image step is reimplemented here.

    python harness.py --doc test_docs/employer_a_w2.pdf --runs 3 --truth truth_w2.json
    python harness.py --docs test_docs --runs 3
    python harness.py --doc test_docs/employer_a_w2.pdf --models qwen2.5vl:3b,other-model

Exit code is non-zero if any *value* field varied across runs, for any
(document, model) combination tested - free-text fields (e.g.
confidence_notes) are shown but excluded from that verdict.
"""
import argparse
import json
import sys
from pathlib import Path

import extract

_FREE_TEXT_FIELDS = {"confidence_notes"}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _values_equal(a, b) -> bool:
    if a == b:
        return True
    na, nb = _num(a), _num(b)
    return na is not None and nb is not None and na == nb


def diff_runs(field_dicts: list) -> dict:
    """field_dicts: the `fields` dict from each of N runs on the same
    (document, model). Returns {field_name: {"status": STABLE|VARIED,
    "values": [{"value": v, "count": n}, ...]}}. Works for scalar or
    list-valued fields (e.g. W-2 box 17) - comparison is by JSON identity,
    not by field shape, so it needs no schema knowledge."""
    all_keys = set()
    for d in field_dicts:
        all_keys.update(d.keys())
    out = {}
    for key in sorted(all_keys):
        raw_values = [d.get(key, "<missing>") for d in field_dicts]
        buckets = {}
        for v in raw_values:
            bucket_key = json.dumps(v, sort_keys=True, default=str)
            buckets.setdefault(bucket_key, {"value": v, "count": 0})
            buckets[bucket_key]["count"] += 1
        out[key] = {
            "status": "STABLE" if len(buckets) == 1 else "VARIED",
            "values": list(buckets.values()),
        }
    return out


def score_against_truth(field_dicts: list, truth: dict) -> dict:
    """{field_name: [bool per run]} - whether each run matched the expected
    value. Numeric-string tolerant (e.g. "75000.00" == 75000.0). Pass
    "__form_type__" in truth (matching run_harness's key) to score form type
    the same way as any other field."""
    return {
        field_name: [_values_equal(d.get(field_name), expected) for d in field_dicts]
        for field_name, expected in truth.items()
    }


def run_harness(extract_fn, runs: int) -> tuple:
    """extract_fn is a zero-arg callable (already bound to a specific
    doc/model/form_hint - or, for api mode, a specific redaction result and
    client) that returns an ExtractionResult. Same loop for both modes -
    mode-specific setup lives in main(). Returns (field_dicts, errors) -
    errors is a list of (run_index, exception) for runs that raised, so a
    crashing run doesn't silently vanish from the count. Each field_dicts
    entry also carries "__form_type__" alongside the real fields, so
    form_type's own stability is checked the same way as any other field -
    it's model output too (§4.0 step 4), not just metadata."""
    field_dicts, errors = [], []
    for i in range(runs):
        try:
            result = extract_fn()
            field_dicts.append({"__form_type__": result.form_type, **result.fields})
        except Exception as e:
            errors.append((i, e))
    return field_dicts, errors


def _print_report(doc_name: str, model: str, field_dicts: list, errors: list, truth: dict | None) -> bool:
    """Prints the report for one (doc, model) pair. Returns True if this
    combination is clean (no VARIED value fields, no failed runs)."""
    print(f"\n=== {doc_name} | model={model} | {len(field_dicts)}/{len(field_dicts) + len(errors)} runs succeeded ===")
    for i, e in errors:
        print(f"  RUN {i}: FAILED - {type(e).__name__}: {e}")
    if not field_dicts:
        print("  no successful runs - cannot assess repeatability")
        return False

    diffs = diff_runs(field_dicts)
    clean = len(errors) == 0
    for field_name, d in diffs.items():
        tag = "[free-text, excluded from verdict]" if field_name in _FREE_TEXT_FIELDS else ""
        print(f"  {field_name}: {d['status']} {tag}")
        if d["status"] == "VARIED":
            if field_name not in _FREE_TEXT_FIELDS:
                clean = False
            for v in d["values"]:
                print(f"      {v['value']!r}  ({v['count']}/{len(field_dicts)} runs)")

    if truth:
        print("  --- vs. truth ---")
        scores = score_against_truth(field_dicts, truth)
        for field_name, results in scores.items():
            n_correct = sum(results)
            status = "CORRECT" if n_correct == len(results) else f"WRONG on {len(results) - n_correct}/{len(results)} runs"
            print(f"  {field_name}: {status} (expected {truth[field_name]!r})")

    return clean


def _parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", help="Single document to test")
    ap.add_argument("--docs", help="Folder of documents to test (all .pdf files)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--mode", choices=["local", "api"], default="local")
    ap.add_argument("--model", default=None, help="Single Ollama model (local) or Claude model (api); default: auto-detect (local) / extract.DEFAULT_API_MODEL (api)")
    ap.add_argument("--models", default=None, help="Comma-separated Ollama models to compare side by side (local mode only)")
    ap.add_argument("--ollama-url", default=extract.DEFAULT_OLLAMA_URL)
    ap.add_argument("--api-key", default=None, help="Anthropic API key (api mode; default: resolved from environment)")
    ap.add_argument("--names", default="", help='api mode only - passed to the redaction gate, e.g. "John Smith"')
    ap.add_argument("--ssns", default="", help='api mode only - passed to the redaction gate, e.g. "123-45-6789"')
    ap.add_argument("--truth", default=None, help="JSON file of expected field values (synthetic docs only)")
    return ap.parse_args()


def _build_api_extract_fns(docs: list, model: str, api_key: str | None, names: str, ssns: str) -> dict:
    """Redacts each doc's folder once (redaction is deterministic given the
    same --names/--ssns, so there's no point re-redacting per run) and
    returns {doc: zero-arg callable} for run_harness. Path A's hard gate
    (extract.RedactionGateError) still applies inside extract_api itself -
    this harness doesn't bypass it, so a doc that doesn't verify "OK" will
    surface as a run failure, same as any other extraction error."""
    import tempfile

    import anthropic
    import redact

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    redact_dir = Path(tempfile.mkdtemp(prefix="harness_redact_"))
    redaction_by_doc = {}
    for src_dir in {doc.parent for doc in docs}:
        for r in redact.redact_folder(src_dir, redact_dir, _to_list(names), _to_list(ssns)):
            redaction_by_doc[r.source_file] = r

    fns = {}
    for doc in docs:
        redaction = redaction_by_doc.get(doc.name)
        form_hint = extract.guess_form_type(doc.name)
        fns[doc] = (lambda r=redaction: extract.extract_api(r, client, model=model, form_hint=form_hint))
    return fns


def _to_list(csv: str) -> list:
    return [x.strip() for x in csv.split(",") if x.strip()]


def main():
    args = _parse_args()
    if not args.doc and not args.docs:
        sys.exit("pass --doc <file> or --docs <folder>")

    docs = [Path(args.doc).resolve()] if args.doc else sorted(
        p.resolve() for p in Path(args.docs).iterdir() if p.suffix.lower() == ".pdf"
    )
    truth = json.loads(Path(args.truth).read_text(encoding="utf-8")) if args.truth else None

    all_clean = True
    if args.mode == "api":
        api_model = args.model or extract.DEFAULT_API_MODEL
        extract_fns = _build_api_extract_fns(docs, api_model, args.api_key, args.names, args.ssns)
        for doc in docs:
            field_dicts, errors = run_harness(extract_fns[doc], args.runs)
            doc_truth = truth if (truth and len(docs) == 1) else None
            clean = _print_report(doc.name, api_model, field_dicts, errors, doc_truth)
            all_clean = all_clean and clean
    else:
        models = [m.strip() for m in args.models.split(",")] if args.models else [
            extract.resolve_local_vision_model(args.ollama_url, override=args.model)
        ]
        for doc in docs:
            form_hint = extract.guess_form_type(doc.name)
            for model in models:
                extract_fn = lambda d=doc, m=model, fh=form_hint: extract.extract_local(
                    d, ollama_url=args.ollama_url, model=m, form_hint=fh
                )
                field_dicts, errors = run_harness(extract_fn, args.runs)
                doc_truth = truth if (truth and len(docs) == 1) else None
                clean = _print_report(doc.name, model, field_dicts, errors, doc_truth)
                all_clean = all_clean and clean

    print(f"\n{'PASS' if all_clean else 'FAIL'} - {'all fields stable' if all_clean else 'instability or failures found, see above'}")
    sys.exit(0 if all_clean else 1)


if __name__ == "__main__":
    main()
