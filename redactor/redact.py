"""RASRICH PDF Redactor — local SSN + name redaction for a folder of PDFs.

Usage:
    python redact.py --input ./docs --output ./redacted --names "John Smith, Jane Doe"
    python redact.py --input ./docs --output ./redacted --names "John Smith" --ssns "123-45-6789"

Detection uses pdfplumber (text + positions); redaction uses PyMuPDF, which
removes the underlying text (not just a black box drawn over it). Originals
are never modified. Fully local — no network calls.

Reconciliation: after redacting, every output file is re-read and checked for
any remaining SSN / name text. Files with no text layer (scans) are flagged
because they cannot be redacted without OCR. Exit code is 1 if any file fails.
"""
import argparse
import io
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

# Tolerates a line break after either hyphen ("123-45-\n6789").
SSN_RE = re.compile(r"(?<!\d)\d{3}-\s*\d{2}-\s*\d{4}(?!\d)")


MASK = r"[Xx*#•]"


def build_patterns(names, ssns=()):
    """SSN pattern + known-SSN patterns + one case-insensitive pattern per name.

    Known SSNs match in any separator style (123-45-6789, 123 45 6789,
    123456789) and as masked last-4 (XXX-XX-6789, ***-**-6789). Labels never
    contain the SSN itself, so console output stays safe to share.

    Name tokens may be separated by any whitespace (incl. line breaks), and a
    token may be hyphenated across a line break ("Smi-\\nth").
    """
    patterns = [("SSN", SSN_RE)]
    for n, ssn in enumerate(ssns, 1):
        a, b, c = ssn[:3], ssn[3:5], ssn[5:]
        patterns.append((f"SSN#{n}", re.compile(rf"(?<!\d){a}[\s-]*{b}[\s-]*{c}(?!\d)")))
        patterns.append((f"SSN#{n} last-4",
                         re.compile(rf"{MASK}{{3}}[\s-]*{MASK}{{2}}[\s-]*{c}(?!\d)")))
    for name in names:
        tokens = name.split()
        if tokens:
            token_rx = [r"(?:-\s+)?".join(map(re.escape, t)) for t in tokens]
            rx = re.compile(r"\b" + r"\s+".join(token_rx) + r"\b", re.IGNORECASE)
            patterns.append((name, rx))
    return patterns


def _char_streams(page):
    """Yield (text, char_boxes) with words joined by spaces across ALL lines.

    Two orderings: visual (top-to-bottom) and PDF content-stream order, which
    follows columns in multi-column layouts. char_boxes[i] is the pdfplumber
    char dict behind text[i] (None for inserted spaces).
    """
    for flow in (False, True):
        text, boxes = [], []
        for w in page.extract_words(use_text_flow=flow, return_chars=True):
            if text:
                text.append(" ")
                boxes.append(None)
            for c in w["chars"]:
                text.append(c["text"])
                boxes.extend([c] * len(c["text"]))  # ligatures ("fi") span >1 index
        yield "".join(text), boxes


def _match_rects(chars):
    """One rectangle per line the match touches (a split name gets two boxes)."""
    rects = []
    for c in chars:
        r = rects[-1] if rects else None
        if r and abs(c["top"] - r[1]) < (c["bottom"] - c["top"]) / 2:
            rects[-1] = (min(r[0], c["x0"]), min(r[1], c["top"]), max(r[2], c["x1"]), max(r[3], c["bottom"]))
        else:
            rects.append((c["x0"], c["top"], c["x1"], c["bottom"]))
    return rects


def find_hits(pdf_path, patterns):
    """Return ({page_index: [bbox, ...]}, {label: count}, pages_without_text).

    Detection runs on an in-memory copy with every page's rotation reset to 0:
    on rotated pages pdfplumber sees sideways chars and scrambles line/word
    order, which breaks names split across lines. Boxes come back in
    unrotated coordinates, which is what PyMuPDF's redact annots expect.
    """
    boxes, counts, no_text = {}, {}, []
    with fitz.open(pdf_path) as src:
        for page in src:
            page.set_rotation(0)
        upright = io.BytesIO(src.tobytes())
    with pdfplumber.open(upright) as pdf:
        for i, page in enumerate(pdf.pages):
            if not (page.extract_text() or "").strip():
                no_text.append(i + 1)
                continue
            seen = set()  # the same match found in both orderings counts once
            for text, char_boxes in _char_streams(page):
                for label, rx in patterns:
                    for m in rx.finditer(text):
                        rects = _match_rects([c for c in char_boxes[m.start():m.end()] if c])
                        key = tuple(tuple(round(v) for v in r) for r in rects)
                        if key in seen:
                            continue
                        seen.add(key)
                        boxes.setdefault(i, []).extend(rects)
                        counts[label] = counts.get(label, 0) + 1
    return boxes, counts, no_text


def redact_file(src, dst, patterns):
    boxes, counts, no_text = find_hits(src, patterns)
    doc = fitz.open(src)
    try:
        for i, rects in boxes.items():
            page = doc[i]
            # pdfplumber coords are relative to the mediabox; PyMuPDF's to the cropbox.
            dx, dy = page.mediabox.x0 - page.cropbox.x0, page.mediabox.y0 - page.cropbox.y0
            for x0, top, x1, bottom in rects:
                r = fitz.Rect(x0 + dx, top + dy, x1 + dx, bottom + dy)
                page.add_redact_annot(r + (-1, -1, 1, 1), fill=(0, 0, 0))
            page.apply_redactions()
        doc.set_metadata({})  # names often sit in Author/Title
        doc.save(dst, garbage=4, deflate=True)
    finally:
        doc.close()
    return counts, no_text


def verify(dst, patterns):
    """Reconciliation: re-read the output and list any sensitive text still present."""
    leftovers = []
    with fitz.open(dst) as doc:
        for i, page in enumerate(doc):
            texts = (page.get_text(), page.get_text(sort=True))  # stream + visual order
            for label, rx in patterns:
                if any(rx.search(t) for t in texts):
                    leftovers.append(f"p{i + 1}:{label}")
    return leftovers


def main():
    ap = argparse.ArgumentParser(description="Redact SSNs and names from a folder of PDFs.")
    ap.add_argument("--input", required=True, help="Folder of source PDFs")
    ap.add_argument("--output", required=True, help="Folder for redacted copies")
    ap.add_argument("--names", default="", help='Comma-separated names, e.g. "John Smith, Jane Doe"')
    ap.add_argument("--ssns", default="",
                    help='Comma-separated known SSNs (any format) — also redacts masked last-4, e.g. XXX-XX-6789')
    args = ap.parse_args()

    ssns = []
    for raw in filter(None, (s.strip() for s in args.ssns.split(","))):
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 9:
            sys.exit(f"--ssns: entry #{len(ssns) + 1} is not 9 digits")
        ssns.append(digits)

    src_dir, out_dir = Path(args.input).resolve(), Path(args.output).resolve()
    if not src_dir.is_dir():
        sys.exit(f"Input folder not found: {src_dir}")
    if out_dir == src_dir:
        sys.exit("Output folder must differ from input folder (originals are never overwritten).")
    out_dir.mkdir(parents=True, exist_ok=True)

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    patterns = build_patterns(names, ssns)
    pdfs = sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        sys.exit(f"No PDFs in {src_dir}")

    print(f"Redacting {len(pdfs)} PDF(s); patterns: SSN, {len(ssns)} known SSN(s)"
          + (", " + ", ".join(names) if names else ""))
    failures, needs_review = [], []
    for src in pdfs:
        dst = out_dir / src.name
        try:
            counts, no_text = redact_file(src, dst, patterns)
            leftovers = verify(dst, patterns)
        except Exception as e:  # keep going on a bad file, but report it
            failures.append(src.name)
            print(f"  ERROR  {src.name}: {e}")
            continue
        summary = ", ".join(f"{k}={v}" for k, v in counts.items()) or "no matches"
        status = "OK"
        if leftovers:
            status = "FAIL"
            failures.append(src.name)
            summary += f" | STILL PRESENT: {', '.join(leftovers)}"
        if no_text:
            status = "REVIEW" if status == "OK" else status
            needs_review.append(src.name)
            summary += f" | no text layer on page(s) {no_text} — scanned? NOT redacted"
        print(f"  {status:<6} {src.name}: {summary}")

    print("\nReconciliation")
    print(f"  Files in:        {len(pdfs)}")
    print(f"  Verified clean:  {len(pdfs) - len(failures) - len(needs_review)}")
    print(f"  Needs review:    {len(needs_review)}  (image-only pages; OCR/manual check required)")
    print(f"  Failed:          {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
