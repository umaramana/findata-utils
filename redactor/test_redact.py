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
}
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


def known_ssn_page(p):
    p.insert_text((72, 100), "Unformatted 123456789  Spaced 123 45 6789")
    p.insert_text((72, 130), "Masked XXX-XX-6789  Stars ***-**-6789  Compact XXXXX6789")
    p.insert_text((72, 160), "KEEP: Card ending 6789  Invoice 00123456789  Other XXX-XX-1111")


def build(d):
    def save(name, fill, rotate=0, crop=None, metadata=None, scan=False):
        doc = fitz.open()
        p = doc.new_page()
        fill(p)
        if rotate:
            p.set_rotation(rotate)
        if crop:
            p.set_cropbox(fitz.Rect(*crop))
        if metadata:
            doc.set_metadata(metadata)
        if scan:  # image-only page containing an SSN
            img = fitz.open()
            ip = img.new_page()
            ip.insert_text((72, 100), "SSN 111-22-3333")
            doc.new_page().insert_image(fitz.Rect(0, 0, 612, 792), pixmap=ip.get_pixmap())
        doc.save(d / name)

    # name -> (expected status, strings that must survive)
    save("plain.pdf", base_page, metadata={"author": "John Smith", "title": "Jane Doe 1040"})
    save("rotated.pdf", base_page, rotate=90)
    save("cropped.pdf", base_page, crop=(20, 30, 580, 800))
    save("scanned_page.pdf", base_page, scan=True)
    save("split.pdf", split_page)
    save("split_rotated.pdf", split_page, rotate=90)
    save("known_ssn.pdf", known_ssn_page)
    save("known_ssn_rotated.pdf", known_ssn_page, rotate=270)
    return {
        "plain.pdf": ("OK", BASE_KEEP), "rotated.pdf": ("OK", BASE_KEEP),
        "cropped.pdf": ("OK", BASE_KEEP), "scanned_page.pdf": ("REVIEW", BASE_KEEP),
        "split.pdf": ("OK", SPLIT_KEEP), "split_rotated.pdf": ("OK", SPLIT_KEEP),
        "known_ssn.pdf": ("OK", ["Card ending 6789", "Invoice 00123456789", "Other XXX-XX-1111"]),
        "known_ssn_rotated.pdf": ("OK", ["Card ending 6789", "Invoice 00123456789", "Other XXX-XX-1111"]),
    }


def run(*args):
    return subprocess.run([sys.executable, str(HERE / "redact.py"), *args],
                          capture_output=True, text=True, encoding="utf-8")


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
            check(f"{name}: original untouched", (src / name).read_bytes() == originals[name])

        check("same input/output folder refused", run("--input", str(src), "--output", str(src)).returncode != 0)
        check("malformed --ssns refused",
              run("--input", str(src), "--output", str(out), "--ssns", "12-345").returncode != 0)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
