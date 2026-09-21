"""RASRICH PDF Redactor — local SSN + name redaction for a folder of PDFs.

Usage:
    python redact.py --input ./docs --output ./redacted --names "John Smith, Jane Doe"
    python redact.py --input ./docs --output ./redacted --names "John Smith" --ssns "123-45-6789"

Detection uses pdfplumber (text + positions) plus PyMuPDF's own text reader
as a second detector — PyMuPDF reads sideways text (landscape schedules on
portrait pages) that pdfplumber scrambles. Redaction uses PyMuPDF, which
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

try:
    from . import redact_ocr  # imported as redactor.redact
except ImportError:
    import redact_ocr  # run as a script from this folder

# Tolerates a line break after either hyphen ("123-45-\n6789").
SSN_RE = re.compile(r"(?<!\d)\d{3}-\s*\d{2}-\s*\d{4}(?!\d)")

# Employer/payer EIN, ##-####### grouping (distinct from SSN's 3-2-4), same
# line-break tolerance. Structural, catches unknown EINs same as SSN_RE does
# for unknown SSNs - no name/EIN list needs to be passed in.
EIN_RE = re.compile(r"(?<!\d)\d{2}-\s*\d{7}(?!\d)")

# Any standalone run of exactly 9 digits: an SSN or EIN printed with no dashes (some W-2s print the employer
# EIN as 123456789). Not part of a longer number, and not a whole-dollar figure with a decimal ("123456789.50")
# or thousands group. Also redacts 9-digit account numbers and CUSIPs, which no check needs.
NINE_RE = re.compile(r"(?<![\d.,$-])\d{9}(?!\d)(?![.,]\d)")

MASK = r"[Xx*#•]"


def _clean_tokens(text):
    return [t for t in (re.sub(r"[.,]", "", w) for w in text.split()) if t]


def _word_rx(word):
    return r"(?:-\s+)?".join(map(re.escape, word))  # a word may be hyphenated across a line break


def _atom_rx(atom):
    kind, val = atom
    if kind == "w":  # a whole name part (a tuple of words: a multi-word surname is one atom)
        return r"\s+".join(_word_rx(w) for w in val)
    if kind == "i":  # an initial, period optional
        return re.escape(val) + r"\.?"
    return r"(?:[A-Za-z]\.?(?:\s+|(?<=\.)))?"  # "o": optional single-letter middle initial, with its own separator


def _form_rx(atoms, reversed_order=False):
    parts = []
    for n, atom in enumerate(atoms):
        if n and atoms[n - 1][0] != "o":
            if reversed_order and n == 1:
                parts.append(r"(?:\s*,\s*|\s+)")          # "Smith, John" / "Smith John"
            elif atoms[n - 1][0] == "i":
                parts.append(r"(?:\s+|(?<=\.))")           # "J. Smith" / "J.Smith"
            else:
                parts.append(r"\s+")
        parts.append(_atom_rx(atom))
    return re.compile(r"(?<!\w)" + "".join(parts) + r"(?!\w)", re.IGNORECASE)


def name_variant_patterns(name):
    """Other written forms of the SAME person's name, as regexes.

    "Robert Alan Smith" also matches: Robert Smith / Robert A Smith / Robert A. Smith / R. Smith /
    R A Smith / Smith, Robert / Smith Robert Alan / Smith, R. - any case. If the entry has no middle
    name, "Robert J. Smith" (one middle initial) matches too.

    Deliberately NOT included: a first or last name on its own. Those also match other people
    ("Mary Smith"), and the redactor keeps look-alikes. Entries containing a digit (addresses) or
    a single word are left literal.
    """
    if re.search(r"\d", name):
        return []
    if "," in name:  # "Smith, Robert A"
        left, _, right = name.partition(",")
        last, given = tuple(_clean_tokens(left)), _clean_tokens(right)
    else:
        toks = _clean_tokens(name)
        last, given = (toks[-1],) if toks else (), toks[:-1]
    if not last or not given:
        return []
    first, mids = given[0], given[1:]
    F, L = ("w", (first,)), ("w", last)
    ini = lambda w: ("i", w[0])
    middles, initials = [("w", (m,)) for m in mids], [ini(m) for m in mids]
    forward = [[F, L], [ini(first), L]]
    backward = [[L, F], [L, ini(first)]]
    if mids:
        forward += [[F, *initials, L], [ini(first), *initials, L]]
        backward += [[L, F, *middles], [L, F, *initials], [L, ini(first), *initials]]
    else:
        forward.append([F, ("o", ""), L])
    return [_form_rx(a) for a in forward] + [_form_rx(a, reversed_order=True) for a in backward]


def build_patterns(names, ssns=()):
    """SSN, EIN and 9-digit patterns + known-SSN patterns + one case-insensitive pattern per name.

    Known SSNs match in any separator style (123-45-6789, 123 45 6789,
    123456789) and as masked last-4 (XXX-XX-6789, ***-**-6789). Labels never
    contain the SSN itself, so console output stays safe to share.

    Name tokens may be separated by any whitespace (incl. line breaks), and a
    token may be hyphenated across a line break ("Smi-\\nth"). Each name also gets
    the other ways the same person's name is written - reordered, initials, a
    middle initial (see name_variant_patterns).
    """
    patterns = [("SSN", SSN_RE), ("EIN", EIN_RE), ("ID9", NINE_RE)]
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
            # Same label for every form of one person, so counts/leftovers stay one line per name
            # and the label-anonymizing callers keep working.
            patterns.extend((name, vrx) for vrx in name_variant_patterns(name))
    return patterns


# Output filenames are scrubbed with looser matching than page text: in a filename
# a name is usually joined by _ - . + or nothing ("W2_John_Smith", "JohnSmith"), and
# \b does not fire next to "_".
_FILENAME_SEP = r"[\s_.+\-]*"


def scrub_text(text, names):
    """text with any SSN/EIN-shaped string and any supplied name replaced by REDACTED."""
    out = SSN_RE.sub("REDACTED", text)
    out = EIN_RE.sub("REDACTED", out)
    out = NINE_RE.sub("REDACTED", out)
    for name in names:
        tokens = name.split()
        if tokens:
            rx = re.compile(r"(?<![A-Za-z0-9])" + _FILENAME_SEP.join(map(re.escape, tokens))
                            + r"(?![A-Za-z0-9])", re.IGNORECASE)
            out = rx.sub("REDACTED", out)
        if re.search(r"\d", name):
            continue  # an address: its words ("Street") are not identifying on their own
        # A filename is cosmetic, so it can be stricter than page text: every part of the name on its
        # own, and - for long names - a truncated form ("Ramachandran" -> "Rama"), which is how a
        # client's name usually turns up in a filename.
        for word in _clean_tokens(name):
            if len(word) >= 6:
                out = re.sub(r"(?<![A-Za-z0-9])" + re.escape(word[:4]) + r"[A-Za-z]*", "REDACTED", out, flags=re.I)
            elif len(word) >= 3:
                out = re.sub(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", "REDACTED", out, flags=re.I)
    return out


def safe_filename(filename, names):
    """Filename for the redacted copy: the original with names/SSNs/EINs scrubbed out (extension kept)."""
    p = Path(filename)
    return scrub_text(p.stem, names) + p.suffix


def unique_name(name, used):
    """Scrubbing can make two names collide ("W2 - REDACTED.pdf" twice); number the later one."""
    p = Path(name)
    candidate, n = name, 2
    while candidate.lower() in used:
        candidate = str(p.with_name(f"{p.stem}_{n}{p.suffix}"))
        n += 1
    used.add(candidate.lower())
    return candidate


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


def _fitz_streams(page, dx=0.0, dy=0.0):
    """Yield (text, char_boxes) from PyMuPDF, lines joined by newlines.

    PyMuPDF builds lines along the text's own direction, so sideways text
    reads correctly. Boxes are shifted by (dx, dy) into pdfplumber's
    mediabox-relative coords and tagged with their line number.
    """
    for sort in (False, True):
        text, boxes, line_no = [], [], 0
        for block in page.get_text("rawdict", sort=sort)["blocks"]:
            for line in block.get("lines", []):
                line_no += 1
                for span in line["spans"]:
                    for ch in span["chars"]:
                        x0, y0, x1, y1 = ch["bbox"]
                        text.append(ch["c"])
                        boxes.append({"x0": x0 + dx, "top": y0 + dy, "x1": x1 + dx,
                                      "bottom": y1 + dy, "line": line_no})
                text.append("\n")
                boxes.append(None)
        yield "".join(text), boxes


def _match_rects(chars):
    """One rectangle per line the match touches (a split name gets two boxes).

    PyMuPDF chars carry their line number; pdfplumber chars are grouped by
    vertical position.
    """
    rects, prev = [], None
    for c in chars:
        if prev is None:
            same_line = False
        elif "line" in c:
            same_line = c["line"] == prev["line"]
        else:
            same_line = abs(c["top"] - prev["top"]) < (c["bottom"] - c["top"]) / 2
        if same_line:
            r = rects[-1]
            rects[-1] = (min(r[0], c["x0"]), min(r[1], c["top"]), max(r[2], c["x1"]), max(r[3], c["bottom"]))
        else:
            rects.append((c["x0"], c["top"], c["x1"], c["bottom"]))
        prev = c
    return rects


def _ocr_streams(upright, index):
    """OCR text streams for page `index` of the rotation-reset in-memory copy, or None if unreadable."""
    with fitz.open("pdf", upright.getvalue()) as doc:
        page = doc[index]
        words = redact_ocr.read_words(page)
        if not redact_ocr.readable(words)[0]:
            return None
        return redact_ocr.streams(words, page.cropbox.x0 - page.mediabox.x0, page.cropbox.y0 - page.mediabox.y0)


def find_hits(pdf_path, patterns, ocr=False, ocr_pages=None):
    """Return ({page_index: [bbox, ...]}, {label: count}, pages_without_text).

    ocr=True: a page with no text layer is read with OCR (redact_ocr) instead of being reported.
    Its 1-based number is appended to ocr_pages (if given); a page OCR cannot read well stays in
    pages_without_text.

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
        fitz_streams = [list(_fitz_streams(p, p.cropbox.x0 - p.mediabox.x0, p.cropbox.y0 - p.mediabox.y0))
                        for p in src]
    with pdfplumber.open(upright) as pdf:
        for i, page in enumerate(pdf.pages):
            streams = list(_char_streams(page)) + fitz_streams[i]
            if not any(text.strip() for text, _ in streams):
                streams = _ocr_streams(upright, i) if ocr else None
                if streams is None:
                    no_text.append(i + 1)
                    continue
                if ocr_pages is not None:
                    ocr_pages.append(i + 1)
            found = []  # (label, rects) already counted
            for text, char_boxes in streams:
                for label, rx in patterns:
                    for m in rx.finditer(text):
                        rects = [fitz.Rect(r) for r in _match_rects([c for c in char_boxes[m.start():m.end()] if c])]
                        if not rects:
                            continue
                        # Always redact every box (overlap is harmless); count a match only
                        # once even when several orderings/detectors find it.
                        boxes.setdefault(i, []).extend(tuple(r) for r in rects)
                        if not any(lbl == label and all(any(r.intersects(q) for q in prev) for r in rects)
                                   for lbl, prev in found):
                            found.append((label, rects))
                            counts[label] = counts.get(label, 0) + 1
    return boxes, counts, no_text


def redact_file(src, dst, patterns, ocr=False, ocr_pages=None):
    if ocr:
        redact_ocr.require()
    boxes, counts, no_text = find_hits(src, patterns, ocr=ocr, ocr_pages=ocr_pages)
    doc = fitz.open(src)
    try:
        strip_annotations(doc)
        for i, rects in boxes.items():
            page = doc[i]
            # pdfplumber coords are relative to the mediabox; PyMuPDF's to the cropbox.
            dx, dy = page.mediabox.x0 - page.cropbox.x0, page.mediabox.y0 - page.cropbox.y0
            for x0, top, x1, bottom in rects:
                r = fitz.Rect(x0 + dx, top + dy, x1 + dx, bottom + dy)
                page.add_redact_annot(r + (-1, -1, 1, 1), fill=(0, 0, 0))
            page.apply_redactions()
        doc.set_metadata({})  # names often sit in Author/Title
        doc.del_xml_metadata()  # the XMP packet is separate from the Info dict and can hold the same names
        doc.save(dst, garbage=4, deflate=True)
    finally:
        doc.close()
    return counts, no_text


def redact_and_verify(src, dst, patterns, ocr=False, ocr_pages=None, extra_passes=2):
    """redact_file + verify, re-passing when only an OCR re-read of the output still finds something.

    OCR is not repeatable: a photo can be read one way when detecting and another way when verifying, so a
    string the first read missed shows up as "pN-ocr:..." after redaction. Then the output itself is redacted
    again from what OCR sees in it (at most `extra_passes` times). Leftovers on a text layer, in metadata or in
    an annotation are never retried - those are not OCR variance.
    Returns (counts, pages_without_text, leftovers, passes)."""
    dst = Path(dst)
    ocr_pages = [] if ocr_pages is None else ocr_pages
    counts, no_text = redact_file(src, dst, patterns, ocr=ocr, ocr_pages=ocr_pages)
    leftovers = verify(dst, patterns, ocr_pages)
    passes = 1
    while ocr and leftovers and all("-ocr:" in item for item in leftovers) and passes <= extra_passes:
        again = dst.with_name(dst.name + ".pass.tmp")
        try:
            more, _ = redact_file(dst, again, patterns, ocr=True, ocr_pages=[])
            again.replace(dst)
        finally:
            again.unlink(missing_ok=True)
        for label, n in more.items():
            counts[label] = counts.get(label, 0) + n
        leftovers = verify(dst, patterns, ocr_pages)
        passes += 1
    return counts, no_text, leftovers, passes


_ANNOT_TEXT_KEYS = ("Contents", "T", "Subj", "RC", "V", "DV", "TU")


def _annotation_xrefs(doc, page):
    """xrefs of the page's annotations, read from its /Annots array itself.

    Not page.annot_xrefs(): that silently skips annotation types MuPDF does not know
    (e.g. a vendor's /FOSINDEX) - exactly the ones that would go unchecked.
    """
    kind, val = doc.xref_get_key(page.xref, "Annots")
    if kind == "null":
        return []
    if kind == "xref":  # the array is an indirect object
        val = doc.xref_object(int(val.split()[0]), compressed=False)
    return [int(m) for m in re.findall(r"(\d+)\s+0\s+R", val)]


def strip_annotations(doc):
    """Remove every annotation except form-field widgets from every page.

    Annotations are not page text, so the redactor cannot see what they hold - and they can hold a
    lot: comments, and vendor markers such as /FOSINDEX, which in practice carried a client name and
    an SSN. They have no value for extraction. Widgets (fillable form fields) are document content,
    so they stay; verify() still scans them and fails the file if one holds a pattern.
    Call before adding redaction annotations. The dropped objects are unreferenced afterwards and
    disappear on save(garbage=4).
    """
    for page in doc:
        xrefs = _annotation_xrefs(doc, page)
        if not xrefs:
            continue
        keep = [x for x in xrefs if doc.xref_get_key(x, "Subtype")[1] == "/Widget"]
        doc.xref_set_key(page.xref, "Annots", "[" + " ".join(f"{x} 0 R" for x in keep) + "]" if keep else "null")


def _annotation_text(doc, page):
    """Text held in the page's annotation dictionaries (form fields that survive strip_annotations,
    or anything in a file that has not been through redact_file)."""
    parts = []
    for xref in _annotation_xrefs(doc, page):
        parts.append(doc.xref_object(xref, compressed=False))
        for key in _ANNOT_TEXT_KEYS:  # decoded (a hex UTF-16 string does not match the raw dict text)
            k_kind, k_val = doc.xref_get_key(xref, key)
            if k_kind == "string":
                parts.append(k_val)
    return " ".join(parts)


def verify(dst, patterns, ocr_pages=()):
    """Reconciliation: re-read the output and list any sensitive text still present.

    ocr_pages: 1-based pages that were redacted from OCR; they have no text layer, so they are re-read
    with OCR too (leftover label "pN-ocr:...")."""
    leftovers = []
    with fitz.open(dst) as doc:
        # "format"/"encryption" describe the file itself, not user-entered metadata
        meta = " ".join(v for k, v in doc.metadata.items() if v and k not in ("format", "encryption"))
        meta += " " + (doc.get_xml_metadata() or "")
        for label, rx in patterns:
            if rx.search(meta):
                leftovers.append(f"meta:{label}")
        for i, page in enumerate(doc):
            annot = _annotation_text(doc, page)
            for label, rx in patterns:
                if rx.search(annot):
                    leftovers.append(f"p{i + 1}-annot:{label}")  # "pN-annot" keeps the label parseable as "page:label"
            texts = (page.get_text(), page.get_text(sort=True))  # stream + visual order
            for label, rx in patterns:
                if any(rx.search(t) for t in texts):
                    leftovers.append(f"p{i + 1}:{label}")
            if i + 1 in ocr_pages:
                ocr_texts = [t for t, _ in redact_ocr.streams(redact_ocr.read_words(page))]
                for label, rx in patterns:
                    if any(rx.search(t) for t in ocr_texts):
                        leftovers.append(f"p{i + 1}-ocr:{label}")
    return leftovers


def main():
    ap = argparse.ArgumentParser(description="Redact SSNs and names from a folder of PDFs.")
    ap.add_argument("--input", required=True, help="Folder of source PDFs")
    ap.add_argument("--output", required=True, help="Folder for redacted copies")
    ap.add_argument("--names", default="", help='Comma-separated names, e.g. "John Smith, Jane Doe"')
    ap.add_argument("--ssns", default="",
                    help='Comma-separated known SSNs (any format) — also redacts masked last-4, e.g. XXX-XX-6789')
    ap.add_argument("--ocr", action="store_true",
                    help="OCR pages with no text layer (needs `tesseract`) and redact what it finds there. "
                         "Weaker than a text-layer check: OCR can miss text.")
    args = ap.parse_args()
    if args.ocr:
        redact_ocr.require()

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
    failures, needs_review, used = [], [], set()
    for src in pdfs:
        shown = unique_name(safe_filename(src.name, names), used)  # original name may contain the client's
        dst = out_dir / shown
        try:
            ocr_pages = []
            counts, no_text, leftovers, passes = redact_and_verify(src, dst, patterns, ocr=args.ocr, ocr_pages=ocr_pages)
        except Exception as e:  # keep going on a bad file, but report it
            failures.append(shown)
            print(f"  ERROR  {shown}: {e}")
            continue
        summary = ", ".join(f"{k}={v}" for k, v in counts.items()) or "no matches"
        status = "OK"
        if leftovers:
            status = "FAIL"
            failures.append(shown)
            summary += f" | STILL PRESENT: {', '.join(leftovers)}"
        if ocr_pages:
            summary += f" | OCR read page(s) {ocr_pages}" + (f", {passes} passes" if passes > 1 else "")
        if no_text:
            status = "REVIEW" if status == "OK" else status
            needs_review.append(shown)
            summary += f" | no text layer on page(s) {no_text} — scanned? NOT redacted"
        print(f"  {status:<6} {shown}: {summary}")

    print("\nReconciliation")
    print(f"  Files in:        {len(pdfs)}")
    print(f"  Verified clean:  {len(pdfs) - len(failures) - len(needs_review)}")
    print(f"  Needs review:    {len(needs_review)}  (image-only pages; OCR/manual check required)")
    print(f"  Failed:          {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
