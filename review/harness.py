"""Step §4.0.9 - repeatability + model-selection harness.

Answers two questions in one run: is extraction stable across repeated calls
on the same document, and (when comparing --models) which local model to use
for Path B. Reuses extract.py's own extraction calls - no separate PDF-to-
image step is reimplemented here.

    python harness.py --docs test_docs --runs 3 --truth truth_w2.json,truth_1099int.json,truth_1099div.json
    python harness.py --doc test_docs/employer_a_w2.pdf --models qwen2.5vl:3b,other-model

The report is grouped by form type (guessed from the filename; UNKNOWN when
no guess), each section scored against the truth file whose __form_type__
matches. It is MASKED: no field value, file name or error message is ever
written - only STABLE/VARIED/CORRECT/WRONG counts and timings - so the same
report is safe on a real document. It goes to a file under diag_output/;
the console shows only the verdict and the report path.

Exit code is non-zero if any *value* field varied across runs, or any run
raised, for any (document, model) combination tested - free-text fields
(e.g. confidence_notes) are counted but excluded from that verdict.
"""
import argparse
import json
import sys
from datetime import datetime
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
    mode-specific setup lives in main(). Returns (field_dicts, errors,
    results) - errors is a list of (run_index, exception) for runs that
    raised, so a crashing run doesn't silently vanish from the count; results
    are the successful ExtractionResults (for timing and UNREAD pages). Each
    field_dicts entry also carries "__form_type__" alongside the real fields,
    so form_type's own stability is checked the same way as any other field -
    it's model output too (§4.0 step 4), not just metadata."""
    field_dicts, errors, results = [], [], []
    for i in range(runs):
        try:
            result = extract_fn()
            field_dicts.append({"__form_type__": result.form_type, **result.fields})
            results.append(result)
        except Exception as e:
            errors.append((i, e))
    return field_dicts, errors, results


def _expected_names(form: str) -> set:
    """Field names the report may print for a form type: its schema fields plus __form_type__. UNKNOWN has none."""
    return set(extract._FORM_FIELDS.get(form, [])) | {"__form_type__"}


def _doc_lines(doc_no: int, field_dicts: list, errors: list, results: list, truth: dict | None,
               expected: set) -> tuple:
    """Masked report lines for one (document, model). Returns (lines, clean)
    - clean = no VARIED value field and no failed run. Never writes a value,
    the file name, an error message, or a field name outside `expected`
    (any of them can carry client data) - other fields are only counted."""
    n_runs = len(field_dicts) + len(errors)
    head = f"--- document {doc_no} | {len(field_dicts)}/{n_runs} runs succeeded"
    seconds = [r.extraction_time_ms / 1000 for r in results]
    if seconds:
        head += f" | seconds per run: mean {sum(seconds) / len(seconds):.0f}, slowest {max(seconds):.0f}"
    lines = [head]
    for i, e in errors:
        lines.append(f"  RUN {i + 1}: FAILED - {type(e).__name__}")
    if not field_dicts:
        lines.append("  no successful runs - cannot assess repeatability")
        return lines, False

    clean = not errors
    extra = 0
    for field_name, d in diff_runs(field_dicts).items():
        if field_name not in expected:
            extra += 1
            if d["status"] != "STABLE" and field_name not in _FREE_TEXT_FIELDS:
                clean = False  # verdict unchanged: a varied field still fails the run, named or not
            continue
        if d["status"] == "STABLE":
            lines.append(f"  {field_name}: STABLE")
            continue
        counts = ", ".join(f"{v['count']}/{len(field_dicts)}" for v in d["values"])
        tag = " [free-text, excluded from verdict]" if field_name in _FREE_TEXT_FIELDS else ""
        lines.append(f"  {field_name}: VARIED, {len(d['values'])} distinct values ({counts}){tag}")
        if field_name not in _FREE_TEXT_FIELDS:
            clean = False

    if extra:
        lines.append(f"  extra fields: {extra}")
    if truth:
        lines.append("  vs truth:")
        for field_name, results_ok in score_against_truth(field_dicts, truth).items():
            n_ok, n = sum(results_ok), len(results_ok)
            verdict = f"CORRECT {n_ok}/{n}" if n_ok == n else f"WRONG on {n - n_ok}/{n} runs"
            lines.append(f"  {field_name}: {verdict}")
    return lines, clean


_READ_STATES = ("read", "partial", "UNREAD")  # worst last


def _read_state(errors: list, results: list) -> str | None:
    """Which of read / partial / UNREAD a document is, by its worst run:
    UNREAD = no text layer on any page, or the file won't open; partial =
    text pages extracted but a page UNREAD or a required field missing;
    read = every page extracted. None when no run got that far (every run
    raised another error - the document is then only counted as failed)."""
    states = ["UNREAD" for _, e in errors if isinstance(e, extract.UnreadableDocument)]
    for r in results:
        if "text" not in r.page_routes:
            states.append("UNREAD")
        elif r.unread_pages or r.missing_required:
            states.append("partial")
        else:
            states.append("read")
    return max(states, key=_READ_STATES.index) if states else None


def build_report(model: str, docs: list, fn_for, runs: int, truths: dict) -> tuple:
    """One masked report for one model over all docs. fn_for(doc) returns
    the zero-arg extract callable for that doc. Sections are form types
    (filename guess, UNKNOWN if none), in first-seen order. Returns
    (text, clean)."""
    sections, counts, n_failed, clean = {}, dict.fromkeys(_READ_STATES, 0), 0, True
    for doc_no, doc in enumerate(docs, 1):
        form = extract.guess_form_type(doc.name) or "UNKNOWN"
        field_dicts, errors, results = run_harness(fn_for(doc), runs)
        state = _read_state(errors, results)
        if state:
            counts[state] += 1
        if any(not isinstance(e, extract.UnreadableDocument) for _, e in errors):
            n_failed += 1
        lines, doc_clean = _doc_lines(doc_no, field_dicts, errors, results, truths.get(form),
                                     _expected_names(form))
        sections.setdefault(form, []).extend(lines)
        clean = clean and doc_clean

    out = [f"model {model} | documents {len(docs)} | "
           + " | ".join(f"{k} {v}" for k, v in counts.items()) + f" | failed {n_failed}"]
    for form, lines in sections.items():
        out += ["", f"=== {form} ==="] + ([] if form in truths else [f"no truth file for {form}"]) + lines
    return "\n".join(out) + "\n", clean


def _load_truths(csv: str | None) -> dict:
    """{form type: truth dict}, keyed by each file's own __form_type__."""
    truths = {}
    for path in _to_list(csv or ""):
        truth = json.loads(Path(path).read_text(encoding="utf-8"))
        if "__form_type__" not in truth:
            sys.exit(f"truth file {path} has no __form_type__")
        truths[truth["__form_type__"]] = truth
    return truths


def _parse_args(argv=None):
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
    ap.add_argument("--truth", default=None, help="Comma-separated truth JSON files (synthetic docs only); each is matched to a form type by its __form_type__")
    ap.add_argument("--out", default="diag_output", help="Folder for the report file")
    return ap.parse_args(argv)


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


def main(argv=None):
    args = _parse_args(argv)
    if not args.doc and not args.docs:
        sys.exit("pass --doc <file> or --docs <folder>")

    docs = [Path(args.doc).resolve()] if args.doc else sorted(
        p.resolve() for p in Path(args.docs).iterdir() if p.suffix.lower() == ".pdf"
    )
    truths = _load_truths(args.truth)

    reports, all_clean = [], True
    if args.mode == "api":
        api_model = args.model or extract.DEFAULT_API_MODEL
        extract_fns = _build_api_extract_fns(docs, api_model, args.api_key, args.names, args.ssns)
        text, all_clean = build_report(api_model, docs, extract_fns.__getitem__, args.runs, truths)
        reports.append(text)
    else:
        models = [m.strip() for m in args.models.split(",")] if args.models else [
            extract.resolve_local_vision_model(args.ollama_url, override=args.model)
        ]
        for model in models:
            fn_for = lambda d, m=model: (lambda: extract.extract_local(
                d, ollama_url=args.ollama_url, model=m, form_hint=extract.guess_form_type(d.name)))
            text, clean = build_report(model, docs, fn_for, args.runs, truths)
            reports.append(text)
            all_clean = all_clean and clean

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"harness_{datetime.now():%Y%m%d-%H%M%S}.txt"
    report_path.write_text("\n".join(reports), encoding="utf-8")
    print(f"{'PASS' if all_clean else 'FAIL'} - report: {report_path}")
    sys.exit(0 if all_clean else 1)


if __name__ == "__main__":
    main()
