"""Show the SHAPE of the text after form labels, never the text itself - safe to paste into a chat.

    python probe_labels.py <pdf or folder> [--after 160] [--out FILE]

For every page with a text layer, finds form labels such as "Physical address of each property" or "Personal
identification number (PIN)" and prints what follows each one with every word masked unless it is common form
wording: every letter becomes *, every digit # ("## ** ****, ****"). It also lists, with masked context, any
leftover token shaped like an ID a rule may be missing (see SHAPES). Files are shown as file#1, file#2 (a
filename can carry the client's name); the page number is shown. Output goes to the console and to
diag_output/probe_<date-time>.txt (gitignored), or --out FILE.

Purpose: decide how far past a label a redaction rule has to reach, without anyone reading a client's value.
Text layer only - a scanned page is reported as such and skipped.
"""
import argparse
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF

from diag_redact import wsl_path

# Standard IRS/bank wording that sits above or before an address. Matched case-insensitively, any whitespace.
LABELS = [
    "Physical address of each property",
    "Mailing address of financial institution",
    "City or town, state or province, country, and ZIP or foreign postal code",
    "City, town, or post office",
    "Home address (number and street)",
    "Foreign country name",
    "Foreign province/state/county",
    "Foreign postal code",
    "Description of asset",
    "Name and address of",
    "Employer's name, address, and ZIP code",
    "street address, city or town",
    "Street address",
    "Mailing address",
    "Address",
    "City",
    # PIN / preparer / phone / occupation / county / age / PAN / refund account (PARKING_LOT 24 Sep, later session)
    "Personal identification number",
    "Self-select PIN",
    "Designee",
    "PIN",
    "PTIN",
    "Preparer",
    "Phone",
    "Ph",
    "PN",
    "Tel",
    "Mobile",
    "Cell",
    "Occupation",
    "County",
    "Ages",
    "Age",
    "PAN",
    "Karvy",
    "Routing number",
    "Account number",
    "Direct deposit",
]

# Form wording shown unmasked, so the output reads as a layout. Nothing here identifies a person.
VOCAB = set("""
a an and or of the in to for on at by if no not see is are be with from as each any all other this that
address addresses street city town post office state province country zip code postal foreign county number
name names mailing physical property properties description asset assets financial institution account
accounts maintained issuer counterparty employer employee payer recipient apt apartment suite unit type
form part line box schedule rental real estate income expenses yes no check here instructions total
maximum value during year date acquired disposed interest dividends royalties amount spaces below complete
you your spouse have also including social security identification taxpayer
personal pin designee designees self select preparer preparers ptin paid firm firms phone ph pn tel mobile
cell occupation county age ages pan karvy routing checking savings refund direct deposit side use only
""".split())

# Leftover tokens shaped like an ID a rule may be missing, anywhere on the page. Shown masked with context.
SHAPES = [
    ("single-digit run (comb boxes?)", re.compile(r"(?<![\d.,])\d(?:[ \t]{1,3}\d){5,}(?![\d.,]?\d)")),
    ("P + 8 digits (PTIN?)", re.compile(r"(?<![A-Za-z0-9])P\d{8}(?![A-Za-z0-9])")),
    ("bare 10 digits", re.compile(r"(?<![\d.,$-])\d{10}(?!\d)(?![.,]\d)")),
    ("PAN-like (letters + digits/mask)", re.compile(r"(?<![A-Za-z0-9])[A-Z]{3,5}[\dXx*]{2,4}[A-Z\dXx*]?(?![a-z0-9])")),
    ("5 digits alone", re.compile(r"(?<![\d.,$-])\d{5}(?![\d.,-]?\d)")),
]


def mask_word(w):
    core = re.sub(r"[^A-Za-z0-9]", "", w).lower()
    if core in VOCAB:
        return w
    return re.sub(r"\d", "#", re.sub(r"[A-Za-z]", "*", w))


def mask(text):
    lines = text.split("\n")
    return " ⏎ ".join(" ".join(mask_word(w) for w in ln.split()) for ln in lines)


def label_rx(label):
    body = r"\s*".join(re.escape(ch) for ch in label if not ch.isspace())
    if len(label) <= 5:  # "PIN", "PN", "Age": whole words only, not "opinion", "open", "page"
        body = rf"(?<![A-Za-z]){body}(?![a-z])"
    return re.compile(body, re.IGNORECASE)


# Labels whose value may sit anywhere in its box rather than after the label in text order.
NEAR_LABELS = ["occupation", "county"]


def probe_near(page, n, p, out):
    """Masked words inside the area right of / below each NEAR_LABELS word, and masked form-field values."""
    words = page.get_text("words")
    for x0, y0, x1, y1, w, *_ in words:
        lab = re.sub(r"[^a-z]", "", w.lower())
        if lab not in NEAR_LABELS:
            continue
        box = fitz.Rect(x0 - 5, y0 - 2, x1 + 260, y1 + 30)
        near = sorted((round(b - y0), round(a - x0), mask_word(t)) for a, b, c, d, t, *_ in words
                      if fitz.Rect(a, b, c, d).intersects(box) and (a, b) != (x0, y0))
        out(f"file#{n} p{p} NEAR {lab!r} at x{round(x0)} y{round(y0)}: "
            + "  ".join(f"(dy{dy},dx{dx}){t}" for dy, dx, t in near))
    for wdg in page.widgets() or []:
        if wdg.field_value not in (None, "", "Off", False):
            out(f"file#{n} p{p} WIDGET {mask(wdg.field_name or '')} type={wdg.field_type_string} "
                f"value={mask(str(wdg.field_value))}")


def probe(pdf, n, after, out=print):
    rxs = [(lab, label_rx(lab)) for lab in LABELS]
    with fitz.open(pdf) as doc:
        for p, page in enumerate(doc, 1):
            for mode, text in (("stream", page.get_text()), ("visual", page.get_text(sort=True))):
                if not text.strip():
                    out(f"file#{n} p{p}: no text layer (scanned?) - skipped")
                    break
                taken = []  # a short label inside or just after a longer one ("City" in "(street, city, ...)") is skipped
                for lab, rx in rxs:
                    for m in rx.finditer(text):
                        if any(s <= m.start() < e for s, e in taken):
                            continue
                        taken.append((m.start(), m.end() + 40))
                        out(f"file#{n} p{p} [{mode}] {lab!r} -> {mask(text[m.end():m.end() + after])}")
                if mode == "stream":
                    probe_near(page, n, p, out)
                    for name, rx in SHAPES:
                        for m in rx.finditer(text):
                            before = mask(text[max(0, m.start() - 60):m.start()])
                            out(f"file#{n} p{p} SHAPE {name}: {before} [[{mask(m.group())}]] "
                                f"{mask(text[m.end():m.end() + 40])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="A PDF or a folder of PDFs (searched recursively); a quoted Windows path works")
    ap.add_argument("--after", type=int, default=160, help="Characters shown after each label (default 160)")
    ap.add_argument("--out", help="Output file (default: diag_output/probe_<date-time>.txt next to this script)")
    args = ap.parse_args()
    if re.match(r"^[A-Za-z]:[^\\/]", args.path):
        sys.exit("The path lost its backslashes - put it in quotes: \"C:\\Users\\...\"")
    root = Path(wsl_path(args.path))
    pdfs = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        sys.exit(f"No PDFs at {root}")
    out_file = Path(args.out) if args.out else Path(__file__).parent / "diag_output" / f"probe_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as fh:
        def out(line):
            print(line)
            fh.write(line + "\n")
        for n, pdf in enumerate(pdfs, 1):
            probe(pdf, n, args.after, out)
    print(f"\nOutput written to {out_file}")


if __name__ == "__main__":
    main()
