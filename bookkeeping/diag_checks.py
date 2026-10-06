"""
Masked layout diagnostic for check pages — safe to paste back to Claude.

  python bookkeeping/diag_checks.py "C:\\path\\to\\page.pdf"          (segmentation only, seconds)
  python bookkeeping/diag_checks.py "C:\\path\\to\\page.pdf" --ocr    (+ full-page Surya OCR, minutes)

Writes bookkeeping/diag_output/diag_<name>.txt. Letters are masked to x/X and
every digit to #, except dates, $amounts and "Check# 961"-style numbers
(house numbers, ZIPs, phone and account numbers are all masked). Also writes diag_<name>_boxes.png with every
candidate rectangle drawn — that image is NOT masked, view it yourself only.
"""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import check_extractor as ce  # noqa: E402

OUT_DIR = Path(__file__).parent / "diag_output"


KEEP_RE = re.compile(  # numbers that survive: dates, $amounts, "Check# 961"
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\$\s*-?\d[\d,]*(?:\.\d{2})?|(?:check|chk|ck)?\s*(?:#|no\.?)\s*\d{1,6}\b", re.I)


def mask(text):
    """Letters -> x/X, every digit -> # except inside a KEEP_RE match."""
    out, pos = [], 0
    for m in KEEP_RE.finditer(text):
        out.append(_mask_all(text[pos:m.start()]))
        out.append(re.sub(r"[A-Za-z]", lambda c: "X" if c.group(0).isupper() else "x", m.group(0)))
        pos = m.end()
    out.append(_mask_all(text[pos:]))
    return "".join(out)


def _mask_all(text):
    text = re.sub(r"\d", "#", text)
    text = re.sub(r"[a-z]", "x", text)
    return re.sub(r"[A-Z]", "X", text)


def contour_report(page_img, out):
    """Every sizeable rectangle, with the reason segment_checks would reject it."""
    import cv2
    from PIL import ImageDraw
    gray = cv2.cvtColor(np.array(page_img), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ph, pw = gray.shape
    rows = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        frac = w * h / (pw * ph)
        if frac < 0.002:
            continue  # specks
        aspect = w / h if h else 0
        why = []
        if frac < ce.MIN_AREA_FRAC:
            why.append(f"area<{ce.MIN_AREA_FRAC:.0%}")
        if frac > 0.98:
            why.append("whole page")
        if not ce.MIN_ASPECT <= aspect <= ce.MAX_ASPECT:
            why.append(f"aspect not {ce.MIN_ASPECT}-{ce.MAX_ASPECT}")
        rows.append((y, x, w, h, frac, aspect, ", ".join(why) or "KEPT"))
    rows.sort()
    out.append(f"page {pw}x{ph}px, {len(contours)} contours, {len(rows)} >= 0.2% of page")
    out.append(f"{'x':>6}{'y':>6}{'w':>6}{'h':>6}{'area%':>7}{'aspect':>7}  verdict")
    for y, x, w, h, frac, aspect, why in rows[:80]:
        out.append(f"{x:>6}{y:>6}{w:>6}{h:>6}{frac * 100:>7.2f}{aspect:>7.2f}  {why}")
    out.append(f"segment_checks() returns {len(ce.segment_checks(page_img))} crop(s)")

    boxed = page_img.copy()
    d = ImageDraw.Draw(boxed)
    for y, x, w, h, _, _, why in rows:
        d.rectangle((x, y, x + w, y + h), outline="green" if why == "KEPT" else "red", width=3)
    return boxed


def ocr_report(page_img, out):
    eng = ce.SuryaEngine()
    lines = eng.ocr(page_img)
    pw, ph = page_img.size
    out.append(f"\nfull-page OCR: {len(lines)} lines (x0,y0,x1,y1 as % of page)")
    for ln in sorted(lines, key=lambda l: (round(l.bbox[1] / ph, 2), l.bbox[0])):
        x0, y0, x1, y1 = ln.bbox
        out.append(f"  {x0 / pw * 100:5.1f} {y0 / ph * 100:5.1f} {x1 / pw * 100:5.1f} {y1 / ph * 100:5.1f}"
                   f"  {ln.confidence:.2f}  {mask(ln.text)}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    path = Path(args[0].strip('"'))
    OUT_DIR.mkdir(exist_ok=True)
    out = [f"file type: {path.suffix.lower()}"]
    for n, img in ce.load_pages(path.name, path.read_bytes()):
        out.append(f"\n===== page {n} =====")
        boxed = contour_report(img, out)
        boxed.save(OUT_DIR / f"diag_{path.stem}_p{n}_boxes.png")
        if "--ocr" in sys.argv:
            ocr_report(img, out)
    report = OUT_DIR / f"diag_{path.stem}.txt"
    report.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
