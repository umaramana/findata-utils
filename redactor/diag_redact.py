"""Diagnostic dump for pages redact.py reports as FAIL. Prints NO client text.

All text is masked (letters -> A/a, digits -> 9, punctuation/spaces kept), so
the output shows structure only: page geometry, where pdfplumber vs PyMuPDF
find each match, how the text is split into words/chars, and which matches
survive redaction. Safe to paste back for debugging.

    python diag_redact.py --prompt   # recommended: asks for file/pages/names/SSNs interactively

Output also goes to diag_output/diag_<date-time>.txt (gitignored), or --out FILE.
    python diag_redact.py --file "x.pdf" --pages 1,47,48,49 --names "A B, C D" [--ssns "..."]
"""
import argparse
import io
import re
import sys
import tempfile
import time
from pathlib import Path

import fitz
import pdfplumber

import intake
import redact
import redact_ocr
from redact import (
    _char_streams, _fitz_streams, _match_rects, _ocr_streams, build_patterns, find_hits, match_span,
    redact_and_verify,
)


HERE = Path(__file__).parent


class Tee:
    """Write to the console and a file at once."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def mask(s):
    return re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", s))).replace("\n", "⏎")


def rnd(r):
    return tuple(round(v, 1) for v in r)


def wsl_path(p):
    """A Windows path pasted into WSL ("C:\\Users\\x\\a.pdf") as its /mnt/c/... form; anything else as given."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if m and not Path(p).exists():
        return f"/mnt/{m[1].lower()}/" + m[2].replace("\\", "/")
    return p


def prompt_for_target():
    """Interactive intake so the file path / page(s) / names / SSNs never sit on a command line,
    in shell history, or get pasted anywhere - same reasoning as redact.py's --prompt."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("--prompt needs a real terminal - run this yourself in your own shell, not piped or scripted.")
    import getpass

    while True:
        path = wsl_path(input("PDF file path> ").strip().strip('"'))
        if Path(path).is_file():
            break
        print("  Not a file - give the full path to the PDF itself (a Windows C:\\... path is fine).")
    pages_raw = input("Page number(s), 1-indexed, comma-separated> ").strip()
    pages = [int(p.strip()) - 1 for p in pages_raw.split(",") if p.strip()]
    print("Entries as given when this file was redacted (same list).\n" + intake.INSTRUCTIONS)
    names, ssns = intake.read_entries()
    print("Known SSNs, if any (hidden input). Blank line when done.")
    while True:
        raw = getpass.getpass("  SSN (hidden)> ").strip()
        if not raw:
            break
        ssns.append(raw)
    return path, pages, names, [re.sub(r"\D", "", s) for s in ssns]  # build_patterns wants digits only


def stream_hits(streams, patterns):
    """(label, masked match, [rects]) found in a list of (text, char_boxes) streams."""
    out, seen = [], set()
    for text, boxes in streams:
        for label, rx in patterns:
            for m in rx.finditer(text):
                start, end = match_span(m)
                rects = [rnd(r) for r in _match_rects([b for b in boxes[start:end] if b])]
                if (label, tuple(rects)) not in seen:
                    seen.add((label, tuple(rects)))
                    out.append((label, mask(m.group()), rects))
    return out


def fitz_hits(page, patterns):
    """(label, masked match, [rects]) found by PyMuPDF's own text extraction."""
    return stream_hits(list(_fitz_streams(page)), patterns)


def verify_view_hits(page, patterns, labels):
    """Masked lines for every match in verify()'s own view of a page (get_text, both orderings): the rule
    that matched (several share the ADDRESS label), the match, and the line before and after it."""
    rule_names = {id(rx): name for name, rx in vars(redact).items() if name.endswith("_RE")}
    out = []
    for view, text in (("get_text", page.get_text()), ("get_text-sort", page.get_text(sort=True))):
        for label, rx in patterns:
            for m in rx.finditer(text):
                before = text.rfind("\n", 0, m.start())
                s = text.rfind("\n", 0, before) + 1 if before > 0 else 0
                after = text.find("\n", m.end())
                e = text.find("\n", after + 1) if after != -1 else -1
                ctx = text[s:e if e != -1 else len(text)]
                rule = rule_names.get(id(rx), labels[label])
                out.append(f"   {view} {rule} match={mask(m.group())!r} context={mask(ctx)!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--pages", help="1-indexed, comma-separated")
    ap.add_argument("--names", default="")
    ap.add_argument("--ssns", default="")
    ap.add_argument("--out", help="Output file (default: diag_output/diag_<date-time>.txt next to this script)")
    ap.add_argument("--prompt", action="store_true",
                     help="Ask for file/pages/names/SSNs interactively instead of via flags "
                          "(recommended - keeps them off the command line and out of shell history).")
    a = ap.parse_args()
    if a.prompt:
        if a.file or a.pages or a.names or a.ssns:
            sys.exit("--prompt cannot be combined with --file/--pages/--names/--ssns.")
        file, pages, names, ssns = prompt_for_target()
    else:
        if not a.file or not a.pages:
            sys.exit("--file and --pages are required (or pass --prompt instead).")
        file = a.file
        pages = [int(p.strip()) - 1 for p in a.pages.split(",") if p.strip()]
        names = [n.strip() for n in a.names.split(",") if n.strip()]
        ssns = [re.sub(r"\D", "", s) for s in a.ssns.split(",") if s.strip()]
    out_file = Path(a.out) if a.out else HERE / "diag_output" / f"diag_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"Working - this redacts the whole file, so it takes about as long as a real run. Output: {out_file}",
          flush=True)
    with open(out_file, "w", encoding="utf-8") as fh:
        stdout = sys.stdout
        sys.stdout = Tee(stdout, fh)  # everything below is masked; the prompts above are not written
        try:
            run(file, pages, names, ssns)
        finally:
            sys.stdout = stdout
    print(f"\nSaved to {out_file} - attach or paste that file.")


def run(file, pages, names, ssns):
    patterns = build_patterns(names, ssns)
    labels = {lbl: f"PAT{i}" for i, (lbl, _) in enumerate(patterns)}  # don't echo names/SSNs

    ocr = redact_ocr.available()
    if not ocr:
        print("NOTE: tesseract not on PATH - OCR (image-only page) diagnostics will be skipped.")

    boxes, _, _ = find_hits(file, patterns, ocr=ocr)
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.pdf"
        ocr_pages = []
        counts, no_text, leftovers, passes = redact_and_verify(file, out_path, patterns, ocr=ocr, ocr_pages=ocr_pages)
        safe_leftovers = [f"{page}:{labels.get(label, label)}" for page, _, label in
                          (l.partition(":") for l in leftovers)]
        print(f"\nredact_and_verify() final result: {'FAIL' if leftovers else ('REVIEW' if no_text else 'OK')}"
              f", {passes} pass(es), ocr_pages={ocr_pages}, leftovers={safe_leftovers}\n")
        orig, src, out = fitz.open(file), fitz.open(file), fitz.open(out_path)
        for doc in (src, out):
            for p in doc:
                p.set_rotation(0)  # compare everything in unrotated coords
        plumber = pdfplumber.open(io.BytesIO(src.tobytes()))
        upright_src = io.BytesIO(src.tobytes())  # same rotation-reset view find_hits() detects in
        upright_out = io.BytesIO(out.tobytes())
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

                print("SURVIVING in redacted output (text layer):")
                for label, s, rects in fitz_hits(po, patterns):
                    print(f"   {labels[label]} {s!r} at {rects}")

                # verify() reads get_text() / get_text(sort=True), not the rawdict streams above, so a
                # leftover can show up only here. Masked match plus the masked line before and after it.
                print("SURVIVING in redacted output (verify()'s own view, match + 1 line of context):")
                for line in verify_view_hits(po, patterns, labels):
                    print(line)

                if ocr and not pp.chars:  # image-only page: text-layer sections above are N/A
                    print("Page has no text layer - OCR diagnostics:")
                    src_streams = _ocr_streams(upright_src, i)
                    if src_streams is None:
                        print("   OCR could not read this page well (too few words / low confidence) - "
                              "redact.py would leave it REVIEW, not redact it.")
                    else:
                        n_words, mean_conf = redact_ocr.readable(redact_ocr.read_words(src[i]))[1:]
                        print(f"   OCR read {n_words} word(s), mean confidence {round(mean_conf, 1)}")
                        print("   OCR finds in ORIGINAL:")
                        for label, s, rects in stream_hits(src_streams, patterns):
                            print(f"      {labels[label]} {s!r} at {rects}")
                    out_streams = _ocr_streams(upright_out, i)
                    print("   SURVIVING in redacted output (OCR re-read, what verify() itself checks):")
                    if out_streams is None:
                        print("      OCR could not read the redacted output well either - cannot confirm clean")
                    else:
                        survivors = stream_hits(out_streams, patterns)
                        if not survivors:
                            print("      none - OCR found nothing matching on re-read")
                        for label, s, rects in survivors:
                            print(f"      {labels[label]} {s!r} at {rects}")
        finally:
            plumber.close()
            for doc in (orig, src, out):
                doc.close()


if __name__ == "__main__":
    main()
