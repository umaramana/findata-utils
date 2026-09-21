"""Capability A - Drake return parser (ARCHITECTURE.md §3).

Reads a print-to-PDF Drake return (text layer, pdfplumber only - no model, no
OCR, no redaction needed) and returns the Form 1040 face lines as a
DrakeReturn. compare.py (check 4, source documents vs. the return) reads the
Drake side through this module.

    python drake.py return.pdf              # masked: line state/method/page only
    python drake.py return.pdf --values     # include amounts

Parsing strategy, per 1040 line id (e.g. "2b"):

  1. Marker: the printed 1040 repeats each line id next to its amount box
     ("... Taxable interest . . . . 2b  1,500"). Take the number to the right
     of a bare `2b` token. This is what makes rows that hold two boxes
     ("2a ... 600  b Taxable interest ... 2b 1,500") come out right - a
     "last amount on the line" rule would give 2a the 2b value.
  2. Label-line fallback: a line that starts with the id and matches the
     line's label, holding exactly one number. More than one number is
     reported "ambiguous", never guessed.

A line whose marker is present with no amount is "blank" - the IRS form's own
convention for zero/none, so value() returns 0.0. A line that was never
located is "not_found" and value() returns None; nothing is ever defaulted to
zero on a miss.

Validated on one real TY2025 Drake print (all 47 lines read, 13/13 identities). The
TY2024 line map has never met a real return. Each year has its own line map and
identity list; a year without one is read with the latest map and warned about.
verify_arithmetic() re-derives the return's own totals from the parsed
lines and is the guard against a layout drift or misread going unnoticed.
A FAIL means the parser did not match this return's layout - do not trust the
Drake side of a comparison run on it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

# (line id, report label, label regex for the fallback path)
_LINE_TABLE_2024 = [
    ("1a", "Total amount from Form(s) W-2, box 1", r"total amount from form|wages"),
    ("1z", "Add lines 1a through 1h", r"add lines 1a|wages"),
    ("2a", "Tax-exempt interest", r"tax-?exempt interest"),
    ("2b", "Taxable interest", r"taxable interest"),
    ("3a", "Qualified dividends", r"qualified dividends"),
    ("3b", "Ordinary dividends", r"ordinary dividends"),
    ("4a", "IRA distributions", r"ira distributions"),
    ("4b", "IRA distributions, taxable amount", r"taxable amount"),
    ("5a", "Pensions and annuities", r"pensions and annuities"),
    ("5b", "Pensions and annuities, taxable amount", r"taxable amount"),
    ("6a", "Social security benefits", r"social security benefits"),
    ("6b", "Social security benefits, taxable amount", r"taxable amount"),
    ("7", "Capital gain or (loss)", r"capital gain or \(loss\)"),
    ("8", "Additional income from Schedule 1, line 10", r"additional income"),
    ("9", "Total income", r"total income|add lines 1z"),
    ("10", "Adjustments to income", r"adjustments to income"),
    ("11", "Adjusted gross income", r"adjusted gross income"),
    ("12", "Standard deduction or itemized deductions", r"standard deduction or itemized"),
    ("13", "Qualified business income deduction", r"qualified business income"),
    ("14", "Add lines 12 and 13", r"add lines 12 and 13"),
    ("15", "Taxable income", r"taxable income"),
    ("16", "Tax", r"\btax\b"),
    ("17", "Amount from Schedule 2, line 3", r"schedule 2, line 3"),
    ("18", "Add lines 16 and 17", r"add lines 16 and 17"),
    ("19", "Child tax credit / credit for other dependents", r"child tax credit"),
    ("20", "Amount from Schedule 3, line 8", r"schedule 3, line 8"),
    ("21", "Add lines 19 and 20", r"add lines 19 and 20"),
    ("22", "Subtract line 21 from line 18", r"subtract line 21"),
    ("23", "Other taxes", r"other taxes"),
    ("24", "Total tax", r"total tax"),
    ("25a", "Federal withholding, Form(s) W-2", r"w-2"),
    ("25b", "Federal withholding, Form(s) 1099", r"1099"),
    ("25c", "Federal withholding, other forms", r"other forms"),
    ("25d", "Add lines 25a through 25c", r"add lines 25a"),
    ("26", "Estimated tax payments", r"estimated tax payments"),
    ("27", "Earned income credit (EIC)", r"earned income credit"),
    ("28", "Additional child tax credit", r"additional child tax credit"),
    ("29", "American opportunity credit", r"american opportunity credit"),
    ("31", "Amount from Schedule 3, line 15", r"schedule 3, line 15"),
    ("32", "Total other payments and refundable credits", r"add lines 27|other payments"),
    ("33", "Total payments", r"total payments|add lines 25d"),
    ("34", "Overpaid", r"overpaid|subtract line 24 from line 33"),
    ("35a", "Refunded to you", r"refunded to you"),
    ("37", "Amount you owe", r"amount you owe|subtract line 33 from line 24"),
]


def _derive(table, replacements):
    out = []
    for row in table:
        out.extend(replacements.get(row[0], [row]))
    return out


# TY2025 renumbered part of the 1040 (ids read off a real Drake TY2025 print, labels
# keyword-checked against it): 7 -> 7a, 11 -> 11a (page 1) + 11b (page 2 carry),
# 12 -> 12e, 13 -> 13a + 13b, 14 = 12e+13a+13b, 27 -> 27a, new line 30 in 32's sum, and
# line 38 (estimated tax penalty), which this Drake print adds into line 37.
_LINE_TABLE_2025 = _derive(_LINE_TABLE_2024, {
    "7": [("7a", "Capital gain or (loss)", r"capital gain or \(loss\)")],
    "11": [("11a", "Adjusted gross income", r"adjusted gross income"),
           ("11b", "Amount from line 11a", r"amount from line 11a")],
    "12": [("12e", "Standard deduction or itemized deductions", r"standard deduction or itemized")],
    "13": [("13a", "Qualified business income deduction", r"qualified business income"),
           ("13b", "Additional deductions from Schedule 1-A", r"schedule 1-a")],
    "14": [("14", "Add lines 12e, 13a, and 13b", r"add lines 12e")],
    "27": [("27a", "Earned income credit (EIC)", r"earned income credit")],
    "29": [("29", "American opportunity credit", r"american opportunity credit"),
           ("30", "Refundable credit (line 30)", r"refundable")],
    "32": [("32", "Total other payments and refundable credits", r"add lines 27a|other payments")],
    "37": [("37", "Amount you owe", r"amount you owe|subtract line 33 from line 24"),
           ("38", "Estimated tax penalty", r"estimated tax penalty")],
})

# Which layout to read the return with; a year with no map of its own uses the latest one.
LINE_MAP_YEARS = {2024: _LINE_TABLE_2024, 2025: _LINE_TABLE_2025}

_NUM_RE = re.compile(r"^\(?-?\$?\d[\d,]*(?:\.\d{1,2})?\)?$")
_LEADER_RE = re.compile(r"^[.…·_•-]+$")
# A bare id token right after one of these is a cross-reference inside a label
# ("... Schedule 1, line 10"), not the line's own amount-box marker.
_XREF_WORDS = {"line", "lines", "and", "through", "thru", "form", "forms",
               "schedule", "box", "to", "or", "from", "of", "see", "on", "in"}
_FORM_1040_RE = re.compile(r"^\s*Form\s+1040(?:-SR)?(?![-\w,])", re.I)
_YEAR_RE = re.compile(r"Form\s+1040(?:-SR)?\s*\(\s*(20\d\d)\s*\)", re.I)
_VERTICAL_FORM = {"FORM", "MROF"}   # rotated text can be read top-to-bottom or bottom-to-top


class DrakeParseError(Exception):
    """The return could not be read at all (corrupt, or no text layer)."""


@dataclass
class LineValue:
    id: str
    label: str
    state: str                    # "value" | "blank" | "not_found" | "ambiguous"
    value: float | None = None
    page: int | None = None       # 1-based
    method: str | None = None     # "marker" | "label-line"
    note: str = ""


@dataclass
class DrakeReturn:
    path: str
    tax_year: int | None
    page_count: int
    form_pages: list
    lines: dict
    warnings: list = field(default_factory=list)
    map_year: int = 2024          # which year's line map was used to read it

    def value(self, line_id: str) -> float | None:
        """Amount, 0.0 for a blank line, None if the line wasn't read."""
        lv = self.lines.get(line_id)
        if lv is None or lv.state in ("not_found", "ambiguous"):
            return None
        return 0.0 if lv.state == "blank" else lv.value

    def count(self, state: str) -> int:
        return sum(1 for lv in self.lines.values() if lv.state == state)


def _is_num(tok: str) -> bool:
    return bool(_NUM_RE.match(tok))


def _parse_num(tok: str) -> float:
    neg = "(" in tok or "-" in tok
    n = float(tok.strip("()").replace("$", "").replace(",", "").lstrip("-"))
    return -n if neg else n


def _is_leader(tok: str) -> bool:
    return bool(_LEADER_RE.match(tok))


def _is_skippable(tok: str) -> bool:
    return _is_leader(tok) or tok == "$"


def _group_lines(words: list, y_tol: float = 3.0) -> list:
    """Cluster pdfplumber words into visual rows: list of token lists, left to right.

    Rows are built on each word's vertical centre, chained to the previous word in
    the row. Comparing `top` to the row's first word split rows whose words differ in
    font size or baseline by a point or two, leaving an amount in the row below its
    own line-id marker.
    """
    def mid(w):
        return (w["top"] + w["bottom"]) / 2

    rows, cur, prev = [], [], 0.0
    for w in sorted(words, key=lambda w: (mid(w), w["x0"])):
        if cur and abs(mid(w) - prev) > y_tol:
            rows.append([x["text"] for x in sorted(cur, key=lambda x: x["x0"])])
            cur = []
        cur.append(w)
        prev = mid(w)
    if cur:
        rows.append([x["text"] for x in sorted(cur, key=lambda x: x["x0"])])
    return rows


def _has_vertical_form_heading(words: list, page_height: float) -> bool:
    """Drake prints page 1's heading with "FORM" rotated 90 degrees, so no row ever
    starts with "Form 1040". Recognise it as a rotated FORM near the top of the page
    plus an exact "1040" token (1040-ES / -V / (Form 1040) do not produce one)."""
    top = [w for w in words
           if not w.get("upright", True) and w["text"].upper() in _VERTICAL_FORM
           and w["top"] < page_height * 0.2]
    return bool(top) and any(w["text"].upper() in ("1040", "1040-SR") for w in words)


def _marker_hits(toks: list, line_id: str) -> list:
    """[("value", float) | ("blank", None)] for each amount-box marker of line_id in one row."""
    hits = []
    for i, tok in enumerate(toks):
        # i == 0 is the row's own label prefix ("26 2024 estimated tax payments..."),
        # never an amount-box marker - the year would otherwise read as an amount.
        if tok != line_id or i == 0:
            continue
        prev = toks[i - 1]
        p = prev.lower().rstrip(".:;)")
        if p in _XREF_WORDS or prev.endswith(","):
            continue
        nxt = next((t for t in toks[i + 1:] if not _is_skippable(t)), None)
        if nxt is not None and _is_num(nxt):
            hits.append(("value", _parse_num(nxt)))
        else:
            # Marker with no amount after it: the box is empty. Drake prints no dot
            # leaders, so the marker is often the row's last token, or is followed by
            # the other column's label. A stray number-less marker never beats a real
            # amount for the same line (values win in parse_drake).
            hits.append(("blank", None))
    return hits


def _label_line_amounts(rows: list, line_id: str, rx) -> list:
    """Numbers on rows that start with line_id and match its label (fallback path)."""
    start = re.compile(rf"^\s*{re.escape(line_id)}\b")
    out = []
    for toks in rows:
        text = " ".join(toks)
        if start.match(text) and rx.search(text):
            out.extend(_parse_num(t) for t in toks[1:] if _is_num(t))
    return out


def parse_drake(path, tax_year: int | None = None) -> DrakeReturn:
    path = Path(path)
    try:
        with pdfplumber.open(path) as pdf:
            page_words = [page.extract_words(extra_attrs=["upright"]) for page in pdf.pages]
            page_heights = [page.height for page in pdf.pages]
        page_rows = [_group_lines(w) for w in page_words]
    except Exception as e:
        raise DrakeParseError(f"cannot open {path.name}: {type(e).__name__}: {e}") from e
    if not any(page_rows):
        raise DrakeParseError(f"{path.name}: no text layer on any page (Drake export should be print-to-PDF, not a scan)")

    warnings = []
    form_pages = [
        n for n, rows in enumerate(page_rows, start=1)
        if any(_FORM_1040_RE.match(" ".join(r)) for r in rows)
        or _has_vertical_form_heading(page_words[n - 1], page_heights[n - 1])
    ]
    if form_pages:
        scan = form_pages
    else:
        scan = list(range(1, len(page_rows) + 1))
        warnings.append("no 'Form 1040' page heading found - scanned every page; values are less trustworthy")

    if tax_year is None:
        for n in scan:
            years = [m.group(1) for m in (_YEAR_RE.search(" ".join(r)) for r in page_rows[n - 1]) if m]
            if years:
                tax_year = int(years[0])
                break
    map_year = tax_year if tax_year in LINE_MAP_YEARS else max(LINE_MAP_YEARS)
    if tax_year not in LINE_MAP_YEARS:
        warnings.append(
            f"tax year {tax_year or 'unknown'}: no line map for that year, using the TY{map_year} Form 1040 "
            "layout - confirm line numbers before trusting results"
        )

    lines = {}
    for line_id, label, label_rx in LINE_MAP_YEARS[map_year]:
        label_rx = re.compile(label_rx, re.I)
        values, blanks = [], []
        for n in scan:
            for toks in page_rows[n - 1]:
                for kind, val in _marker_hits(toks, line_id):
                    (values if kind == "value" else blanks).append((n, val))
        distinct = {round(v, 2) for _, v in values}
        if len(distinct) == 1:
            lines[line_id] = LineValue(line_id, label, "value", values[0][1], values[0][0], "marker")
            continue
        if len(distinct) > 1:
            lines[line_id] = LineValue(line_id, label, "ambiguous", None, values[0][0], "marker",
                                       f"{len(distinct)} different amounts next to marker {line_id}")
            continue
        if blanks:
            lines[line_id] = LineValue(line_id, label, "blank", None, blanks[0][0], "marker")
            continue
        amounts = []
        for n in scan:
            amounts.extend((n, a) for a in _label_line_amounts(page_rows[n - 1], line_id, label_rx))
        distinct = {round(a, 2) for _, a in amounts}
        if len(distinct) == 1:
            lines[line_id] = LineValue(line_id, label, "value", amounts[0][1], amounts[0][0], "label-line")
        elif len(distinct) > 1:
            lines[line_id] = LineValue(line_id, label, "ambiguous", None, amounts[0][0], "label-line",
                                       f"{len(distinct)} amounts on the label row")
        else:
            lines[line_id] = LineValue(line_id, label, "not_found")

    return DrakeReturn(str(path), tax_year, len(page_rows), form_pages, lines, warnings, map_year)


# --- arithmetic self-check ---------------------------------------------------

# name, lhs terms, rhs terms, rhs floored at 0. Terms are (sign, line id).
_IDENTITIES_2024 = [
    ("9 = 1z+2b+3b+4b+5b+6b+7+8", [(1, "9")], [(1, i) for i in ("1z", "2b", "3b", "4b", "5b", "6b", "7", "8")], False),
    ("11 = 9 - 10", [(1, "11")], [(1, "9"), (-1, "10")], False),
    ("14 = 12 + 13", [(1, "14")], [(1, "12"), (1, "13")], False),
    ("15 = 11 - 14 (min 0)", [(1, "15")], [(1, "11"), (-1, "14")], True),
    ("18 = 16 + 17", [(1, "18")], [(1, "16"), (1, "17")], False),
    ("21 = 19 + 20", [(1, "21")], [(1, "19"), (1, "20")], False),
    ("22 = 18 - 21 (min 0)", [(1, "22")], [(1, "18"), (-1, "21")], True),
    ("24 = 22 + 23", [(1, "24")], [(1, "22"), (1, "23")], False),
    ("25d = 25a+25b+25c", [(1, "25d")], [(1, "25a"), (1, "25b"), (1, "25c")], False),
    ("32 = 27+28+29+31", [(1, "32")], [(1, i) for i in ("27", "28", "29", "31")], False),
    ("33 = 25d + 26 + 32", [(1, "33")], [(1, "25d"), (1, "26"), (1, "32")], False),
    ("34 - 37 = 33 - 24", [(1, "34"), (-1, "37")], [(1, "33"), (-1, "24")], False),
]
_IDENTITIES_2025 = [
    ("9 = 1z+2b+3b+4b+5b+6b+7a+8", [(1, "9")], [(1, i) for i in ("1z", "2b", "3b", "4b", "5b", "6b", "7a", "8")], False),
    ("11a = 9 - 10", [(1, "11a")], [(1, "9"), (-1, "10")], False),
    ("11b = 11a", [(1, "11b")], [(1, "11a")], False),
    ("14 = 12e+13a+13b", [(1, "14")], [(1, "12e"), (1, "13a"), (1, "13b")], False),
    ("15 = 11b - 14 (min 0)", [(1, "15")], [(1, "11b"), (-1, "14")], True),
] + [i for i in _IDENTITIES_2024 if i[0].split(" ")[0] in ("18", "21", "22", "24", "25d")] + [
    ("32 = 27a+28+29+30+31", [(1, "32")], [(1, i) for i in ("27a", "28", "29", "30", "31")], False),
    ("33 = 25d + 26 + 32", [(1, "33")], [(1, "25d"), (1, "26"), (1, "32")], False),
    # line 37 includes the line 38 penalty (seen on a real TY2025 Drake print with a penalty; the
    # refund-side treatment of a penalty is not confirmed - a FAIL there is a real flag, not noise)
    ("34 - 37 = 33 - 24 - 38", [(1, "34"), (-1, "37")], [(1, "33"), (-1, "24"), (-1, "38")], False),
]
IDENTITIES_BY_MAP_YEAR = {2024: _IDENTITIES_2024, 2025: _IDENTITIES_2025}
MIN_LINES_WITH_VALUES = 6
MIN_IDENTITIES_EVALUATED = 4


@dataclass
class IdentityResult:
    name: str
    status: str            # "ok" | "fail" | "skipped"
    lhs: float | None = None
    rhs: float | None = None


@dataclass
class IntegrityResult:
    status: str            # "PASS" | "FAIL" | "INSUFFICIENT"
    identities: list
    lines_with_values: int
    reason: str = ""


def verify_arithmetic(ret: DrakeReturn) -> IntegrityResult:
    """Re-derive the return's own totals from the parsed lines.

    A parse that reads the wrong number for any line usually breaks at least one
    of these, so PASS is evidence the line map matched this return's layout.
    Tolerance is 1 dollar per term - Drake prints whole dollars, each rounded
    independently.
    """
    results = []
    for name, lhs_terms, rhs_terms, floor in IDENTITIES_BY_MAP_YEAR[ret.map_year]:
        vals = {i: ret.value(i) for _, i in lhs_terms + rhs_terms}
        if any(v is None for v in vals.values()):
            results.append(IdentityResult(name, "skipped"))
            continue
        lhs = sum(s * vals[i] for s, i in lhs_terms)
        rhs = sum(s * vals[i] for s, i in rhs_terms)
        if floor:
            rhs = max(0.0, rhs)
        tol = float(len(lhs_terms) + len(rhs_terms))
        results.append(IdentityResult(name, "ok" if abs(lhs - rhs) <= tol else "fail", lhs, rhs))

    with_values = sum(1 for lv in ret.lines.values() if lv.state == "value")
    evaluated = [r for r in results if r.status != "skipped"]
    failed = [r for r in evaluated if r.status == "fail"]
    if failed:
        return IntegrityResult("FAIL", results, with_values,
                               "; ".join(f"{r.name} (got {r.lhs:,.0f} vs {r.rhs:,.0f})" for r in failed))
    if with_values < MIN_LINES_WITH_VALUES or len(evaluated) < MIN_IDENTITIES_EVALUATED:
        return IntegrityResult(
            "INSUFFICIENT", results, with_values,
            f"only {with_values} line(s) read with an amount and {len(evaluated)} arithmetic identities "
            f"evaluable (need {MIN_LINES_WITH_VALUES} and {MIN_IDENTITIES_EVALUATED}) - "
            "not enough to confirm the parser matched this return's layout",
        )
    return IntegrityResult("PASS", results, with_values)


# --- CLI ---------------------------------------------------------------------

def _main():
    import argparse

    ap = argparse.ArgumentParser(description="Parse a Drake return PDF's Form 1040 face lines.")
    ap.add_argument("drake_pdf")
    ap.add_argument("--year", type=int, default=None, help="Tax year (default: read from the form)")
    ap.add_argument("--values", action="store_true",
                    help="Print amounts too. Default output is masked - line state, method and page only.")
    args = ap.parse_args()

    try:
        ret = parse_drake(args.drake_pdf, args.year)
    except DrakeParseError as e:
        # the message can carry the file's name/path - this output is meant to be pasteable
        msg = str(e).replace(str(args.drake_pdf), "<return>").replace(Path(args.drake_pdf).name, "<return>")
        raise SystemExit(f"ERROR: {msg}")

    # No filename and, by default, no amounts: this output is meant to be safe to paste into a chat.
    print(f"TY{ret.tax_year or '?'}  {ret.page_count} page(s), 1040 page(s): {ret.form_pages or 'none detected'}")
    for w in ret.warnings:
        print(f"  WARNING: {w}")
    print(f"\n{'line':<5} {'state':<10} {'method':<11} {'page':<5}" + ("value" if args.values else ""))
    for lv in ret.lines.values():
        row = f"{lv.id:<5} {lv.state:<10} {lv.method or '-':<11} {lv.page or '-':<5}"
        if args.values and lv.value is not None:
            row += f"{lv.value:,.2f}"
        if lv.note:
            row += f"  ({lv.note})"
        print(row)
    print("\n" + ", ".join(f"{ret.count(s)} {s}" for s in ("value", "blank", "ambiguous", "not_found")))

    integ = verify_arithmetic(ret)
    reason = integ.reason
    if integ.status == "FAIL" and not args.values:  # the FAIL reason quotes amounts
        reason = "failed: " + "; ".join(r.name for r in integ.identities if r.status == "fail")
    print(f"\nArithmetic self-check: {integ.status}" + (f" - {reason}" if reason else ""))
    for r in integ.identities:
        print(f"  {r.status:<8} {r.name}")


if __name__ == "__main__":
    _main()
