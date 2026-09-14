"""Diagnostic dump for pages redact.py reports as FAIL. Prints NO client text.

All text is masked (letters -> A/a, digits -> 9, punctuation/spaces kept), so
the output shows structure only: page geometry, where pdfplumber vs PyMuPDF
find each match, how the text is split into words/chars, and which matches
survive redaction. Safe to paste back for debugging.

    python diag_redact.py --file "x.pdf" --pages 1,47,48,49 --names "A B, C D" [--ssns "..."]
"""
import argparse
import io
import re
import tempfile
from pathlib import Path

import fitz
import pdfplumber

from redact import _char_streams, _fitz_streams, _match_rects, build_patterns, find_hits, redact_file


def mask(s):
    return re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", s))).replace("\n", "⏎")


def rnd(r):
    return tuple(round(v, 1) for v in r)


def fitz_hits(page, patterns):
    """(label, masked match, [rects]) found by PyMuPDF's own text extraction."""
    out, seen = [], set()
    for text, boxes in _fitz_streams(page):
        for label, rx in patterns:
            for m in rx.finditer(text):
                rects = [rnd(r) for r in _match_rects([b for b in boxes[m.start():m.end()] if b])]
                if (label, tuple(rects)) not in seen:
                    seen.add((label, tuple(rects)))
                    out.append((label, mask(m.group()), rects))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--pages", required=True, help="1-indexed, comma-separated")
    ap.add_argument("--names", default="")
    ap.add_argument("--ssns", default="")
    a = ap.parse_args()
    names = [n.strip() for n in a.names.split(",") if n.strip()]
    ssns = [re.sub(r"\D", "", s) for s in a.ssns.split(",") if s.strip()]
    patterns = build_patterns(names, ssns)
    labels = {lbl: f"PAT{i}" for i, (lbl, _) in enumerate(patterns)}  # don't echo names/SSNs
    pages = [int(p) - 1 for p in a.pages.split(",")]

    boxes, _, _ = find_hits(a.file, patterns)
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.pdf"
        redact_file(a.file, out_path, patterns)
        orig, src, out = fitz.open(a.file), fitz.open(a.file), fitz.open(out_path)
        for doc in (src, out):
            for p in doc:
                p.set_rotation(0)  # compare everything in unrotated coords
        plumber = pdfplumber.open(io.BytesIO(src.tobytes()))
        try:
            print(f"pages={len(src)} producer={mask(src.metadata.get('producer') or '')!r} "
                  f"patterns={list(labels.values())}")
            for i in pages:
                p, po, pp, po_orig = src[i], out[i], plumber.pages[i], orig[i]
                print(f"\n=== page {i + 1} ===")
                print(f"rotation={po_orig.rotation} mediabox={rnd(p.mediabox)} cropbox={rnd(p.cropbox)} "
                      f"plumber_bbox={rnd(pp.bbox)} widgets={len(list(po_orig.widgets()))} "
                      f"annots={len(list(po_orig.annots()))} plumber_chars={len(pp.chars)} "
                      f"non_upright={sum(not c['upright'] for c in pp.chars)} images={len(po_orig.get_images())}")
                dx, dy = p.cropbox.x0 - p.mediabox.x0, p.cropbox.y0 - p.mediabox.y0
                print(f"redact.py boxes placed ({len(boxes.get(i, []))}), in PyMuPDF coords:")
                for b in boxes.get(i, []):
                    print(f"   {rnd((b[0] - dx, b[1] - dy, b[2] - dx, b[3] - dy))}")

                words = pp.extract_words(return_chars=True)
                print("PyMuPDF finds in ORIGINAL (+ pdfplumber words at the same spot):")
                for label, s, rects in fitz_hits(p, patterns):
                    print(f"   {labels[label]} {s!r} at {rects}")
                    near = [w for w in words if any(
                        fitz.Rect(w["x0"], w["top"], w["x1"], w["bottom"]).intersects(
                            fitz.Rect(r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)) for r in rects)]
                    for w in near:
                        gaps = [round(c2["x0"] - c1["x1"], 1) for c1, c2 in zip(w["chars"], w["chars"][1:])]
                        print(f"      plumber {mask(w['text'])!r} bbox={rnd((w['x0'], w['top'], w['x1'], w['bottom']))} "
                              f"size={round(w['chars'][0]['size'], 1)} upright={w['upright']} "
                              f"font={mask(w['chars'][0]['fontname'])!r} char_gaps={gaps}")
                    if not near:
                        print("      plumber: NO words at this spot")

                print("pdfplumber streams (masked, first 400 chars of each ordering):")
                for n, (text, _) in enumerate(_char_streams(pp)):
                    hits = [labels[lbl] for lbl, rx in patterns if rx.search(text)]
                    print(f"   order{n} hits={hits}: {mask(text)[:400]!r}")

                print("SURVIVING in redacted output:")
                for label, s, rects in fitz_hits(po, patterns):
                    print(f"   {labels[label]} {s!r} at {rects}")
        finally:
            plumber.close()
            for doc in (orig, src, out):
                doc.close()


if __name__ == "__main__":
    main()
