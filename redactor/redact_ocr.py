"""OCR support for redact.py: locate sensitive text on pages that have no text layer.

A scanned page has nothing for pdfplumber/PyMuPDF to read, so redact.py alone can only mark it
REVIEW. With OCR enabled, the page is rendered, run through the `tesseract` command line (local, no
network), and the words come back as text streams shaped like redact._fitz_streams output: the same
patterns run over them, and the matches' boxes go through the same PyMuPDF redaction (which blanks
the pixels under each box).

Limits, on purpose left visible:
- OCR can miss or misread text, and verify() re-reads the output with the same engine. An OK that
  includes OCR'd pages is a weaker guarantee than one on a text-layer page.
- A page OCR cannot read well (too few words, or low mean confidence) is reported unreadable and the
  caller keeps it REVIEW.
- A word is blacked out whole, so a match inside a word takes the entire word.
"""
import shutil
import subprocess

import fitz

OCR_DPI = 300
MIN_WORDS = 5          # fewer words than this: not enough to trust the page was read
MIN_MEAN_CONF = 60.0   # tesseract word confidence, 0-100; clean scans of forms read ~85-95
PAD = 1.5              # points added around each word box
TIMEOUT = 180          # seconds per page


def available():
    return shutil.which("tesseract") is not None


def require():
    if not available():
        raise RuntimeError("OCR requested but `tesseract` is not on PATH (sudo apt install tesseract-ocr)")


def read_words(page, dpi=OCR_DPI):
    """[{"text", "box": (x0, top, x1, bottom) in page points, "line": (block, par, line), "conf"}]"""
    require()
    rotation = page.rotation
    page.set_rotation(0)  # same view redact.find_hits detects in, so detection and verify agree
    try:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    finally:
        page.set_rotation(rotation)
    proc = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "3", "--dpi", str(dpi), "tsv"],
        input=pix.tobytes("png"), capture_output=True, timeout=TIMEOUT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed (exit {proc.returncode})")
    scale = 72.0 / dpi
    words = []
    for row in proc.stdout.decode("utf-8", "replace").splitlines()[1:]:
        cols = row.split("\t", 11)
        if len(cols) < 12 or cols[0] != "5":  # level 5 = word
            continue
        text, conf = cols[11].strip(), float(cols[10])
        if not text or conf < 0:
            continue
        left, top, w, h = (int(c) for c in cols[6:10])
        words.append({"text": text, "conf": conf, "line": (cols[2], cols[3], cols[4]),
                      "box": (left * scale - PAD, top * scale - PAD,
                              (left + w) * scale + PAD, (top + h) * scale + PAD)})
    return words


def readable(words):
    """(ok, n_words, mean_conf). Not ok = the caller must not treat the page as scanned-and-checked."""
    n = len(words)
    mean = sum(w["conf"] for w in words) / n if n else 0.0
    return n >= MIN_WORDS and mean >= MIN_MEAN_CONF, n, mean


def _rows(words):
    """Words grouped into visual rows (top to bottom, left to right), robust to OCR block order."""
    rows = []
    for w in sorted(words, key=lambda w: (w["box"][1] + w["box"][3]) / 2):
        mid, height = (w["box"][1] + w["box"][3]) / 2, w["box"][3] - w["box"][1]
        if rows and abs(mid - rows[-1]["mid"]) < height * 0.6:
            rows[-1]["words"].append(w)
            rows[-1]["mid"] = mid
        else:
            rows.append({"mid": mid, "words": [w]})
    return [sorted(r["words"], key=lambda w: w["box"][0]) for r in rows]


def _stream(lines, dx, dy):
    text, boxes = [], []
    for n, line in enumerate(lines, 1):
        for k, w in enumerate(line):
            if k:
                text.append(" ")
                boxes.append(None)
            x0, y0, x1, y1 = w["box"]
            box = {"x0": x0 + dx, "top": y0 + dy, "x1": x1 + dx, "bottom": y1 + dy, "line": n}
            text.extend(w["text"])
            boxes.extend([box] * len(w["text"]))
        text.append("\n")
        boxes.append(None)
    return "".join(text), boxes


def streams(words, dx=0.0, dy=0.0):
    """Two (text, char_boxes) streams like redact._fitz_streams: OCR reading order, and visual rows.
    Boxes are shifted by (dx, dy) into pdfplumber's mediabox-relative coordinates."""
    by_line = {}
    for w in words:  # tesseract emits words in reading order, so a line's words stay adjacent
        by_line.setdefault(w["line"], []).append(w)
    return [_stream(list(by_line.values()), dx, dy), _stream(_rows(words), dx, dy)]
