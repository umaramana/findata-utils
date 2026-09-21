"""Synthetic edge-case matrix for redact.py — no client data.

Builds PDFs in a temp folder, runs redact.py as the CLI, then checks each
output: sensitive text gone (true positives), look-alikes kept (false
positives), expected status per file, exit codes, and the same-folder guard.

    python test_redact.py
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz

HERE = Path(__file__).parent
NAMES = "John Smith, Jane Doe"
SSNS = "123-45-6789, 987-65-4321"

# Must NOT appear in any output text layer.
FORBIDDEN = {
    "SSN#1 any format": re.compile(r"(?<!\d)123[\s-]*45[\s-]*6789(?!\d)"),
    "SSN#1 masked": re.compile(r"[Xx*]{3}[\s-]*[Xx*]{2}[\s-]*6789"),
    "SSN#2": re.compile(r"987-65-4321"),
    "other SSN": re.compile(r"222-33-4444"),
    "John Smith": re.compile(r"john\s+smith", re.I),
    "Jane Doe": re.compile(r"jane\s+do-?\s*e\b", re.I),
    # other written forms of the same two people (name_variant_patterns)
    "Smith, John": re.compile(r"smith,\s*john", re.I),
    "SMITH JOHN": re.compile(r"smith\s+john\b", re.I),
    "J. Smith": re.compile(r"\bj\.\s*smith", re.I),
    "John Q. Smith": re.compile(r"john\s+q\.?\s+smith", re.I),
    "Doe, Jane": re.compile(r"doe,\s*jane", re.I),
    "undashed 9-digit": re.compile(r"(?<![\d.,$-])\d{9}(?!\d)(?![.,]\d)"),
}
XMP = ("<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
       "<rdf:Description xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:creator>John Smith</dc:creator>"
       "<dc:title>Jane Doe return</dc:title></rdf:Description></rdf:RDF></x:xmpmeta>")
# Source filenames that carry a client name; the redacted copies must not.
NAMED_FILES = ["W2 - John Smith.pdf", "W2 - John_Smith.pdf", "1099_Jane_Doe.pdf", "JohnSmith 1040.pdf"]
EXPECTED_OUT_NAMES = {"W2 - REDACTED.pdf", "W2 - REDACTED_2.pdf", "1099_REDACTED.pdf", "REDACTED 1040.pdf"}
BASE_KEEP = ["555-123-4567", "1234-56-7890", "123-45-67890"]
SPLIT_KEEP = ["John Adams", "Mary Smith", "Jane Doeman"]


def base_page(p):
    p.insert_text((72, 100), "Taxpayer: John Smith  SSN 123-45-6789")
    p.insert_text((72, 130), "Spouse: jane   doe  SSN: 987-65-4321  Dep: 222-33-4444")
    p.insert_text((72, 160), "Phone 555-123-4567  Acct 1234-56-7890  Ref 123-45-67890")


def split_page(p):
    p.insert_text((72, 100), "The return was signed by taxpayer John")   # name across line break
    p.insert_text((72, 115), "Smith on April 10.")
    p.insert_text((72, 145), "Spouse name: Jane Do-")                      # hyphenated across lines
    p.insert_text((72, 160), "e, filing jointly.")
    p.insert_text((72, 190), "SSN on file 123-45-")                         # SSN across lines
    p.insert_text((72, 205), "6789 verified.")
    p.insert_text((72, 300), "Prepared for John")                           # two-column layout
    p.insert_text((72, 315), "Smith, 2025 year.")
    p.insert_text((330, 300), "Right column note")
    p.insert_text((72, 400), "KEEP: John Adams met Mary Smith; Jane Doeman.")


def variants_page(p):
    p.insert_text((72, 100), "Payee: Smith, John   Ref SMITH JOHN A")     # reordered
    p.insert_text((72, 130), "Signed J. Smith and John Q. Smith")          # initial / middle initial
    p.insert_text((72, 160), "Spouse Doe, Jane M.")
    p.insert_text((72, 200), "KEEP: Jane Smith paid Johnny Doe and Roberta")  # different people


def sideways_page(p, rot):
    """Upright page (/Rotate 0) whose text is drawn rotated, e.g. a landscape schedule."""
    x0, step = (100, 15) if rot == 90 else (500, -15)
    y = 700 if rot == 90 else 100
    lines = ["Taxpayer: John Smith  SSN 123-45-6789",
             "Spouse: jane   doe  SSN: 987-65-4321  Dep: 222-33-4444",
             "Phone 555-123-4567  Acct 1234-56-7890  Ref 123-45-67890",
             "Signed by taxpayer John",   # name across line break
             "Smith on April 10."]
    for n, line in enumerate(lines):
        p.insert_text((x0 + n * step * 2, y), line, rotate=rot)


def known_ssn_page(p):
    p.insert_text((72, 100), "Unformatted 123456789  Spaced 123 45 6789")
    p.insert_text((72, 130), "Masked XXX-XX-6789  Stars ***-**-6789  Compact XXXXX6789")
    p.insert_text((72, 160), "KEEP: Card ending 6789  Invoice 00123456789  Other XXX-XX-1111")


def nine_digit_page(p):
    # Digits differ from the known test SSNs on purpose: a known SSN is matched in any format, which would
    # hide whether the standalone 9-digit rule (ID9) is what removed something.
    p.insert_text((72, 100), "Employer identification number 246813579  Employee code 135792468")
    p.insert_text((72, 130), "KEEP: ten digits 2468135790, eight digits 24681357")
    p.insert_text((72, 145), "KEEP: amount 246813579.50, ZIP+4 24681-3579, grouped 1,246813579")
    p.insert_text((72, 160), "KEEP: negative -246813579 and ref W2-246813579")


def build(d):
    def save(name, fill, rotate=0, crop=None, metadata=None, scan=False, xmp=None):
        doc = fitz.open()
        p = doc.new_page()
        fill(p)
        if rotate:
            p.set_rotation(rotate)
        if crop:
            p.set_cropbox(fitz.Rect(*crop))
        if metadata:
            doc.set_metadata(metadata)
        if xmp:
            doc.set_xml_metadata(xmp)
        if scan:  # image-only page containing an SSN
            img = fitz.open()
            ip = img.new_page()
            ip.insert_text((72, 100), "SSN 111-22-3333")
            doc.new_page().insert_image(fitz.Rect(0, 0, 612, 792), pixmap=ip.get_pixmap())
        doc.save(d / name)

    # name -> (expected status, strings that must survive)
    save("plain.pdf", base_page, metadata={"author": "John Smith", "title": "Jane Doe 1040"}, xmp=XMP)
    save("rotated.pdf", base_page, rotate=90)
    save("cropped.pdf", base_page, crop=(20, 30, 580, 800))
    save("scanned_page.pdf", base_page, scan=True)
    save("split.pdf", split_page)
    save("split_rotated.pdf", split_page, rotate=90)
    save("sideways_90.pdf", lambda p: sideways_page(p, 90))
    save("sideways_270.pdf", lambda p: sideways_page(p, 270))
    save("variants.pdf", variants_page)
    save("known_ssn.pdf", known_ssn_page)
    save("nine_digit.pdf", nine_digit_page)
    save("known_ssn_rotated.pdf", known_ssn_page, rotate=270)
    for named in NAMED_FILES:
        save(named, base_page)
    return {
        "plain.pdf": ("OK", BASE_KEEP), "rotated.pdf": ("OK", BASE_KEEP),
        "cropped.pdf": ("OK", BASE_KEEP), "scanned_page.pdf": ("REVIEW", BASE_KEEP),
        "split.pdf": ("OK", SPLIT_KEEP), "split_rotated.pdf": ("OK", SPLIT_KEEP),
        "sideways_90.pdf": ("OK", BASE_KEEP), "sideways_270.pdf": ("OK", BASE_KEEP),
        "variants.pdf": ("OK", ["Jane Smith paid Johnny Doe and Roberta"]),
        "nine_digit.pdf": ("OK", ["ten digits 2468135790", "eight digits 24681357", "amount 246813579.50",
                                  "ZIP+4 24681-3579", "grouped 1,246813579", "negative -246813579",
                                  "ref W2-246813579"]),
        "known_ssn.pdf": ("OK", ["Card ending 6789", "Invoice 00123456789", "Other XXX-XX-1111"]),
        "known_ssn_rotated.pdf": ("OK", ["Card ending 6789", "Invoice 00123456789", "Other XXX-XX-1111"]),
    }


def run(*args):
    return subprocess.run([sys.executable, str(HERE / "redact.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


SCAN_LINES = ["Form W-2 Wage and Tax Statement 2025",
              "Employee: John Smith   SSN 123-45-6789",
              "Spouse: Doe, Jane  Dependent SSN 222-33-4444",
              "Employer EIN 12-3456789  Acme Widgets Incorporated",
              "Employer identification number 987654321",
              "Box 1 Wages 85000.00   Box 2 Federal tax withheld 12000.00",
              "KEEP: Mary Smith and John Adams are other people"]
SCAN_FORBIDDEN = {"John Smith": r"john\s+smith", "Jane Doe": r"doe,?\s+jane|jane\s+doe", "SSN": r"\d{3}-\d{2}-\d{4}",
                  "EIN": r"\d{2}-\d{7}", "undashed 9-digit": r"(?<![\d.,$-])\d{9}(?!\d)"}


def scan_pdf(path, lines, rotate=0, pixel_rotate=0):
    """Image-only PDF (no text layer): the lines are drawn, rendered to a picture, and only the picture kept."""
    src = fitz.open()
    p = src.new_page()
    for k, line in enumerate(lines):
        p.insert_text((72, 100 + 30 * k), line, fontsize=13)
    png = p.get_pixmap(dpi=200).tobytes("png")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=png)
    if pixel_rotate:  # the picture itself is sideways, as from a badly fed scanner
        pix = fitz.Pixmap(png)
        doc = fitz.open()
        page = doc.new_page(width=pix.height * 72 / 200, height=pix.width * 72 / 200)
        page.insert_image(page.rect, stream=png, rotate=pixel_rotate)
    if rotate:
        page.set_rotation(rotate)
    doc.save(path)


def ocr_checks(check):
    """--ocr: image-only pages are read, redacted and re-read; unreadable ones stay REVIEW. Needs tesseract."""
    sys.path.insert(0, str(HERE))
    import redact_ocr
    if not redact_ocr.available():
        print("  SKIP  OCR checks (tesseract not installed)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        src, out, out_plain = Path(tmp, "in"), Path(tmp, "out"), Path(tmp, "out_plain")
        src.mkdir()
        scan_pdf(src / "scan.pdf", SCAN_LINES)
        scan_pdf(src / "scan_rot90.pdf", SCAN_LINES, rotate=90)
        scan_pdf(src / "scan_sideways.pdf", SCAN_LINES, pixel_rotate=90)
        scan_pdf(src / "scan_few_words.pdf", ["Hi John Smith"])
        blank = fitz.open()
        blank.new_page()
        blank.save(src / "blank.pdf")
        mixed = fitz.open()
        mixed.new_page().insert_text((72, 100), "Taxpayer John Smith SSN 123-45-6789 and some more words")
        mixed.insert_pdf(fitz.open(src / "scan.pdf"))
        mixed.save(src / "mixed.pdf")

        plain = run("--input", str(src), "--output", str(out_plain), "--names", NAMES, "--ssns", SSNS)
        statuses = {l.split()[1].rstrip(":"): l.split()[0] for l in plain.stdout.splitlines()
                    if l.split()[:1] and l.split()[0] in ("OK", "REVIEW", "FAIL")}
        check("OCR off: an image-only page still makes the file REVIEW", statuses.get("scan.pdf") == "REVIEW", str(statuses))

        r = run("--input", str(src), "--output", str(out), "--names", NAMES, "--ssns", SSNS, "--ocr")
        statuses = {l.split()[1].rstrip(":"): l.split()[0] for l in r.stdout.splitlines()
                    if l.split()[:1] and l.split()[0] in ("OK", "REVIEW", "FAIL")}
        for name, want in {"scan.pdf": "OK", "scan_rot90.pdf": "OK", "mixed.pdf": "OK", "blank.pdf": "REVIEW",
                           "scan_few_words.pdf": "REVIEW", "scan_sideways.pdf": "REVIEW"}.items():
            check(f"OCR on, {name}: status {want}", statuses.get(name) == want, r.stdout)
        check("OCR on: console reports which pages OCR read", "OCR read page(s) [1]" in r.stdout, r.stdout)
        for name in ("scan.pdf", "scan_rot90.pdf", "mixed.pdf"):
            with fitz.open(out / name) as doc:
                check(f"OCR on, {name}: no text layer was added", not any(pg.get_text().strip() for pg in doc if pg.number == len(doc) - 1))
                seen = " ".join(" ".join(w["text"] for w in redact_ocr.read_words(pg)) for pg in doc)
            leaked = [k for k, rx in SCAN_FORBIDDEN.items() if re.search(rx, seen, re.I)]
            check(f"OCR on, {name}: sensitive text gone from the pixels", not leaked, f"leaked {leaked}")
            if name != "mixed.pdf":
                check(f"OCR on, {name}: look-alikes and other content kept",
                      all(w in seen for w in ("Mary", "Adams", "Acme", "85000.00")), "over-redacted")

def main():
    results = []

    def check(label, ok, detail=""):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail and not ok else ""))

    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp, "in"), Path(tmp, "out")
        src.mkdir()
        expected = build(src)
        originals = {p.name: p.read_bytes() for p in src.iterdir()}
        r = run("--input", str(src), "--output", str(out), "--names", NAMES, "--ssns", SSNS)
        check("exit code 0 (no FAIL files)", r.returncode == 0, r.stdout + r.stderr)
        check("console output never prints a supplied SSN", "6789" not in r.stdout and "4321" not in r.stdout)

        for name, (status, keep) in expected.items():
            line = next((l for l in r.stdout.splitlines() if l.strip().endswith(name + ":") or f" {name}:" in l), "")
            check(f"{name}: status {status}", line.split()[:1] == [status], line.strip())
            with fitz.open(out / name) as doc:
                texts = [pg.get_text(sort=s) for pg in doc for s in (False, True)]
                # "format"/"encryption" describe the file itself, not user-entered metadata
                meta = " ".join(v for k, v in doc.metadata.items() if v and k not in ("format", "encryption"))
            leaked = [k for k, rx in FORBIDDEN.items() if any(rx.search(t) for t in texts)]
            check(f"{name}: nothing sensitive left", not leaked, f"leaked {leaked}")
            missing = [k for k in keep if not any(k in " ".join(t.split()) for t in texts)]
            check(f"{name}: look-alikes kept", not missing, f"over-redacted {missing}")
            check(f"{name}: metadata cleared", not meta, meta)
            with fitz.open(out / name) as doc:
                xmp_left = doc.get_xml_metadata() or ""
            check(f"{name}: XMP metadata cleared", not re.search(r"john\s+smith|jane\s+doe", xmp_left, re.I), xmp_left[:80])
            check(f"{name}: original untouched", (src / name).read_bytes() == originals[name])

        out_names = {p.name for p in out.iterdir()}
        check("named source files written under scrubbed names", EXPECTED_OUT_NAMES <= out_names,
              f"got {sorted(n for n in out_names if 'REDACTED' in n or 'W2' in n)}")
        squashed = [re.sub(r"[^a-z]", "", n.lower()) for n in out_names]
        check("no output filename carries a supplied name",
              not any("johnsmith" in n or "janedoe" in n for n in squashed))
        shown_names = [m.group(1) for m in re.finditer(r"^\s+(?:OK|REVIEW|FAIL|ERROR)\s+(.*?):", r.stdout, re.M)]
        check("console status lines never print a client name from a filename",
              shown_names and not any(re.search(r"john[\s_]*smith|jane[\s_]*doe", n, re.I) for n in shown_names),
              str(shown_names))
        check("same input/output folder refused", run("--input", str(src), "--output", str(src)).returncode != 0)
        check("malformed --ssns refused",
              run("--input", str(src), "--output", str(out), "--ssns", "12-345").returncode != 0)

    ocr_checks(check)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
