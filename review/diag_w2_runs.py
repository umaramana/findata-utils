"""Diagnostic (16 Nov 2026), SYNTHETIC DOCUMENTS ONLY: runs the real extract_local N times on one document and writes,
per run, the model's raw reply, the fields after the verbatim gate, their confidence, and truth vs result.
Refuses any document outside test_docs/ and test_docs_irs/ - values are printed in full, so never point this at a client document.

    python diag_w2_runs.py --doc test_docs/employer_a_w2.pdf --runs 3 --out diag_output/w2_diag.txt
    python diag_w2_runs.py --doc test_docs_irs/acme_1099-int.pdf --runs 1 --out diag_output/int.txt

Truth is the document's entry in truth.json beside it (harness.py's format).

The 16 Nov fix trial (JSON-schema reply format + field template, patched in at run time) is now in extract.py.
"""
import argparse
import json
from pathlib import Path

import requests

import extract


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="qwen2.5vl:3b")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    doc = Path(args.doc).resolve()
    if doc.parent.name not in ("test_docs", "test_docs_irs"):
        raise SystemExit("synthetic documents in test_docs/ or test_docs_irs/ only")
    entries = json.loads((doc.parent / "truth.json").read_text(encoding="utf-8"))["documents"]
    truth = {k.lower(): v for k, v in entries.items()}[doc.name.lower()]["fields"]

    raw_replies = []
    real_post = requests.post

    def recording_post(*a, **kw):
        resp = real_post(*a, **kw)
        raw_replies.append(resp.json().get("response", ""))
        return resp

    extract.requests.post = recording_post
    out = [f"document {doc.name} | model {args.model} | truth {truth}", ""]
    for i in range(1, args.runs + 1):
        try:
            r = extract.extract_local(doc, model=args.model, form_hint=extract.guess_form_type(doc.name))
        except Exception as e:
            out += [f"=== run {i}: {type(e).__name__}: {e}", f"raw reply: {raw_replies[-1] if raw_replies else '-'}", ""]
            continue
        out += [f"=== run {i} ({r.extraction_time_ms} ms) form_type={r.form_type}",
                f"raw reply: {raw_replies[-1]}",
                f"fields after gate: {json.dumps(r.fields)}",
                f"confidence: {json.dumps(r.field_confidence)}",
                f"verification failures: {r.verification_failures} | missing required: {r.missing_required}"]
        for k, v in truth.items():
            got = r.fields.get(k, "<absent>")
            ok = isinstance(got, (int, float)) and abs(got - float(v)) < 0.005
            out.append(f"  {k}: truth {v} | got {got} | {'OK' if ok else 'WRONG'}")
        out.append("")
    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"written: {args.out}")


if __name__ == "__main__":
    main()
