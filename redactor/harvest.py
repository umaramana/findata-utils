"""Harvest: read the client's identifying values from their Drake return, so the other files in the folder can be
redacted without anyone typing them (PARKING_LOT "DECIDED (25 Sep)", double blind).

    python harvest.py "<return.pdf>" [--out FILE]   # masked report: each field found/missing and its SHAPE

Values stay in memory: harvest() hands them to the caller (the batch driver) as redaction entries. Nothing here
prints or writes a value. The CLI prints shapes only (every letter becomes *, every digit #) to the console and to
diag_output/harvest_<date-time>.txt.

How a value is found: by its position on the page, not by text order. Drake writes the typed values as a layer
separate from the printed form, so in the text stream a value is nowhere near its label. Each field is a printed
IRS label ("Your first name and middle initial"). Its value is the words inside the label's box, either below the
label (header boxes) or to its right (refund comb boxes, "Phone no."). The box's right edge is the next known label
on the same row, and its bottom edge is the next known label below it. No coordinates are hard-coded, so a shifted
or rescaled layout reads the same.

Step 1 covers the Form 1040 header (names, SSNs, home address), occupations, phone and the refund account.
Dependents, the state return and other forms come later (PARKING_LOT build order).
"""
import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    where: str = "below"   # "below": value under the label in its box; "right": value after it on the same row
    row: str = ""          # another label that must be on the same row (tells the two "Last name" labels apart)


_TP_ROW, _SP_ROW, _CITY_ROW = ("Your first name and middle initial", "If joint return, spouse's first name and middle initial",
                               "City, town, or post office")
FIELDS = [
    Field("tp_first", _TP_ROW),
    Field("tp_last", "Last name", row=_TP_ROW),
    Field("tp_ssn", "Your social security number"),
    Field("sp_first", _SP_ROW),
    Field("sp_last", "Last name", row=_SP_ROW),
    Field("sp_ssn", "Spouse's social security number"),
    Field("street", "Home address (number and street)"),
    Field("apt", "Apt. no."),
    Field("city", _CITY_ROW),
    Field("state", "State", row=_CITY_ROW),
    Field("zip", "ZIP code", row=_CITY_ROW),
    Field("country", "Foreign country name"),
    Field("province", "Foreign province/state/county"),
    Field("postal", "Foreign postal code"),
    Field("tp_occupation", "Your occupation"),
    Field("sp_occupation", "Spouse's occupation"),
    Field("phone", "Phone no.", "right"),
    Field("routing", "Routing number", "right"),
    Field("account", "Account number", "right"),
]
# Printed wording that only marks where a neighbouring box starts. Never read as a value.
BOUNDARIES = ["Type", "Checking", "Email address", "Date", "Your signature", "Spouse's signature",
              "If the IRS sent you", "If the IRS sent your spouse", "Presidential Election Campaign"]

# Occupations that say nothing about who the person is: not worth blacking out every "retired" in the folder.
GENERIC_OCCUPATIONS = {"retired", "none", "student", "homemaker", "unemployed", "disabled", "self employed",
                       "self-employed", "n/a", "na"}

_WORDLIKE = {
    "name": re.compile(r"[A-Za-z][A-Za-z .'\-]{0,39}"),
    "ssn": re.compile(r"\d{3}-?\d{2}-?\d{4}"),
    "text": re.compile(r"(?=.*[A-Za-z0-9]).{1,60}"),
    "short": re.compile(r"[A-Za-z0-9\- ]{1,10}"),
    "state": re.compile(r"[A-Za-z]{2}"),
    "zip": re.compile(r"\d{5}(?:-?\d{4})?"),
}
_SHAPE = {"tp_first": "name", "tp_last": "name", "sp_first": "name", "sp_last": "name", "tp_ssn": "ssn",
          "sp_ssn": "ssn", "street": "text", "apt": "short", "city": "name", "state": "state", "zip": "zip",
          "country": "name", "province": "name", "postal": "short", "tp_occupation": "text",
          "sp_occupation": "text"}
_DIGITS = {"phone": (10, 11), "routing": (9, 9), "account": (4, 17)}  # "right" fields: digit count allowed


@dataclass
class Harvest:
    values: dict = field(default_factory=dict)   # field key -> list of distinct values, in page order
    pages: int = 0                               # pages that held at least one known label

    def first(self, key):
        return (self.values.get(key) or [""])[0]

    def entries(self):
        """Redaction entries for redact.build_patterns(names=...): full names, SSNs, the address (whole and as
        "street; city; ST ZIP" so its pieces are matched alone too), occupations, phone, bank numbers."""
        out = []
        for who in ("tp", "sp"):
            firsts, lasts = self.values.get(f"{who}_first", []), self.values.get(f"{who}_last", [])
            if who == "sp" and firsts and not lasts:
                lasts = self.values.get("tp_last", [])   # spouse shares the surname and Drake left it blank
            out += [f"{f} {l}" for f in firsts for l in lasts]
            out += self.values.get(f"{who}_ssn", [])
            out += [o for o in self.values.get(f"{who}_occupation", []) if o.lower() not in GENERIC_OCCUPATIONS]
        street, city = self.first("street"), self.first("city")
        if street:
            out.append(street)
            region = " ".join(v for v in (self.first("state"), self.first("zip")) if v)
            if city:
                out.append("; ".join(v for v in (street, city, region) if v))
        # Foreign parts only for an address that has a city (harvest() already drops them next to a US ZIP):
        # below those boxes sits the next section's heading ("Filing Status"), which an empty box hands over.
        if city:
            for key in ("province", "postal", "country"):
                out += [v for v in self.values.get(key, []) if len(v) >= 4]
        for key in ("phone", "routing", "account"):
            out += self.values.get(key, [])
        return list(dict.fromkeys(e for e in out if e.strip()))


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _rows(words, tol=2.5):
    """Words grouped into visual rows by vertical centre, each row left to right."""
    rows, cur, prev = [], [], None
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        mid = (w[1] + w[3]) / 2
        if cur and abs(mid - prev) > tol:
            rows.append(sorted(cur, key=lambda w: w[0]))
            cur = []
        cur.append(w)
        prev = mid
    if cur:
        rows.append(sorted(cur, key=lambda w: w[0]))
    return rows


def _find_labels(rows, labels):
    """{label: [(Rect, row index, word ids)]} - a label is consecutive words of one row whose letters and digits,
    joined, spell it (so "province/state/county" matches whether the PDF splits it at the slashes or not)."""
    found = {lab: [] for lab in labels}
    for r, row in enumerate(rows):
        norms = [_norm(w[4]) for w in row]
        for lab in labels:
            target = _norm(lab)
            for i in range(len(row)):
                if not norms[i] or not target.startswith(norms[i]):
                    continue
                acc, j = "", i
                while j < len(row) and len(acc) < len(target):
                    acc += norms[j]
                    j += 1
                if acc == target:
                    rect = fitz.Rect(row[i][:4])
                    for w in row[i + 1:j]:
                        rect |= fitz.Rect(w[:4])
                    found[lab].append((rect, r, {id(w) for w in row[i:j]}))
    return found


def _page_labels(page):
    words = [tuple(w) for w in page.get_text("words")]
    labels = list(dict.fromkeys([f.label for f in FIELDS] + [f.row for f in FIELDS if f.row] + BOUNDARIES))
    found = _find_labels(_rows(words), labels)
    return words, found, [(lab, rect, r, ids) for lab, hits in found.items() for rect, r, ids in hits]


def _read_page(page, harvest):
    words, found, occ = _page_labels(page)
    if not occ:
        return
    harvest.pages += 1
    label_words = set().union(*(ids for *_, ids in occ))
    same_row = lambda a, b: abs((a.y0 + a.y1) / 2 - (b.y0 + b.y1) / 2) <= 3
    for f in FIELDS:
        for rect, r, ids in found[f.label]:
            if f.row and not any(same_row(rect, o) for o, *_ in found[f.row]):
                continue
            right = min((o.x0 for _, o, _, _ in occ if same_row(rect, o) and o.x0 > rect.x1 - 1),
                        default=page.rect.width)
            if f.where == "below":
                # the leftmost box on a row starts at the page edge (a value may sit left of its label)
                left = rect.x0 - 4 if any(same_row(rect, o) and o.x1 <= rect.x0 for _, o, _, _ in occ) else 0
                # the box ends at the next row holding any known label, in any column: an empty box must not
                # hand over the next row's value (the email under an empty spouse's-occupation box)
                below = [o.y0 for _, o, _, _ in occ if o.y0 > rect.y1 + 1]
                bottom = min(below + [rect.y1 + 5 * rect.height])
                inside = [w for w in words if id(w) not in label_words and left <= (w[0] + w[2]) / 2 < right
                          and rect.y1 < (w[1] + w[3]) / 2 < bottom]
                # a value line starts under its label; a line starting far to the right is wording beside the box
                # (a short label such as "State" may have its value start just past the label's end)
                starts = {id(r[0]) for r in _rows(inside) if r[0][0] <= rect.x1 + 3 * rect.height}
                inside = [w for r in _rows(inside) if id(r[0]) in starts for w in r]
            else:
                inside = [w for w in words if id(w) not in label_words and rect.x1 <= (w[0] + w[2]) / 2 < right
                          and abs((w[1] + w[3]) / 2 - (rect.y0 + rect.y1) / 2) <= max(rect.height, 6)]
            value = _clean(f.key, [w[4] for w in _first_run(inside)])
            if value and value not in harvest.values.setdefault(f.key, []):
                harvest.values[f.key].append(value)


def _first_run(words):
    """The value's words: the first line in the box (every value here is one line, so a lower line is the next
    box's content), cut at the first gap wider than 2.5 character heights (wording that carries on to the
    right on the same line, e.g. the Presidential Election Campaign text beside the ZIP code)."""
    rows = _rows(words)
    if not rows:
        return []
    run = [rows[0][0]]
    for w in rows[0][1:]:
        if w[0] - run[-1][2] > 2.5 * (w[3] - w[1]):
            break
        run.append(w)
    return run


def _clean(key, tokens):
    """The field's value from the words in its box, or None when they do not look like that field."""
    if key in _DIGITS:
        digits = ""
        for t in tokens:
            if re.search(r"[A-Za-z]{2}", t):
                break               # printed wording, not the typed number ("Account number or other designation")
            # a lone letter is a comb-box glyph (Drake draws the empty boxes with a font character): skip it
            digits += re.sub(r"\D", "", t)
        lo, hi = _DIGITS[key]
        return digits if lo <= len(digits) <= hi else None
    value = re.sub(r"\s+", " ", " ".join(tokens)).strip(" ,.")
    return value if value and _WORDLIKE[_SHAPE[key]].fullmatch(value) else None


def harvest(pdf_path):
    """A Harvest of the return at pdf_path. Every page is read, so a second copy of the 1040 or the e-file
    authorization adds any value the first page missed."""
    h = Harvest()
    with fitz.open(pdf_path) as doc:
        for page in doc:
            _read_page(page, h)
    if h.values.get("zip"):   # a US address has no foreign part; an empty foreign box reads the heading below it
        for key in ("country", "province", "postal"):
            h.values.pop(key, None)
    return h


def shape(value):
    return re.sub(r"\d", "#", re.sub(r"[A-Za-z]", "*", value))


def main():
    from diag_redact import wsl_path
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf", help="The Drake return (a quoted Windows path works)")
    ap.add_argument("--out", help="Output file (default: diag_output/harvest_<date-time>.txt next to this script)")
    ap.add_argument("--near", nargs="*", default=["sp_occupation"],
                    help="Also show the NEAR view for these fields (MISSING fields always get it)")
    args = ap.parse_args()
    if re.match(r"^[A-Za-z]:[^\\/]", args.pdf):
        sys.exit("The path lost its backslashes - put it in quotes: \"C:\\Users\\...\"")
    pdf = Path(wsl_path(args.pdf))
    if not pdf.is_file():
        sys.exit("No such file")
    h = harvest(pdf)
    lines = [f"pages with a known label: {h.pages}"]
    for f in dict.fromkeys(f.key for f in FIELDS):
        vals = h.values.get(f, [])
        lines.append(f"{f:14} {'MISSING' if not vals else ' | '.join(shape(v) for v in vals)}")
    lines.append(f"redaction entries: {len(h.entries())}")
    near = [f for f in FIELDS if f.key in args.near or not h.values.get(f.key)]
    if near:
        lines += ["", "NEAR view (masked): words around each label of the fields above, as (dy,dx,height)word.",
                  "dy/dx: offset of the word's top-left from the label's top-left; [label] = a known label."]
        with fitz.open(pdf) as doc:
            for p, page in enumerate(doc, 1):
                words, found, occ = _page_labels(page)
                label_of = {i: lab for lab, _, _, ids in occ for i in ids}
                for f in near:
                    for rect, *_ in found[f.label]:
                        area = fitz.Rect(rect.x0 - 60, rect.y0 - 12, rect.x1 + 320, rect.y1 + 40)
                        seen, parts = set(), []
                        for w in sorted(words, key=lambda w: (round(w[1]), w[0])):
                            if not fitz.Rect(w[:4]).intersects(area):
                                continue
                            lab = label_of.get(id(w))
                            if lab in seen:
                                continue
                            if lab:
                                seen.add(lab)
                            txt = f"[{lab}]" if lab else shape(w[4])
                            parts.append(f"({round(w[1] - rect.y0)},{round(w[0] - rect.x0)},{round(w[3] - w[1])}){txt}")
                        lines.append(f"p{p} {f.key} label h{round(rect.height)}: " + " ".join(parts))
    out_file = Path(args.out) if args.out else Path(__file__).parent / "diag_output" / f"harvest_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines) + f"\n\nOutput written to {out_file}")


if __name__ == "__main__":
    main()
