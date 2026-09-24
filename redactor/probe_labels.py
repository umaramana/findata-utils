"""Show the SHAPE of the text after address labels, never the text itself - safe to paste into a chat.

    python probe_labels.py <pdf or folder> [--after 160]

For every page with a text layer, finds form labels such as "Physical address of each property" and prints
what follows each one with every word masked unless it is common form wording: every letter becomes *, every
digit # ("## ** ****, ****"). Files are shown as file#1, file#2 (a filename can carry the
client's name); the page number is shown. Nothing is written to disk.

Purpose: decide how far past a label an address-label redaction rule has to reach, without anyone reading a
client's address. Text layer only - a scanned page is reported as such and skipped.
"""
import argparse
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

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
""".split())


def mask_word(w):
    core = re.sub(r"[^A-Za-z0-9]", "", w).lower()
    if core in VOCAB:
        return w
    return re.sub(r"\d", "#", re.sub(r"[A-Za-z]", "*", w))


def mask(text):
    lines = text.split("\n")
    return " ⏎ ".join(" ".join(mask_word(w) for w in ln.split()) for ln in lines)


def label_rx(label):
    return re.compile(r"\s*".join(re.escape(ch) for ch in label if not ch.isspace()), re.IGNORECASE)


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="A PDF or a folder of PDFs (searched recursively)")
    ap.add_argument("--after", type=int, default=160, help="Characters shown after each label (default 160)")
    args = ap.parse_args()
    root = Path(args.path)
    pdfs = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        sys.exit(f"No PDFs at {root}")
    for n, pdf in enumerate(pdfs, 1):
        probe(pdf, n, args.after)


if __name__ == "__main__":
    main()
