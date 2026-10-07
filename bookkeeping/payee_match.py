"""
Payee matching for Check Extractor (Phase 2, spec: check_ocr_spec.md).

Handwritten payees misread differently on every check ("KLMB", "KAL MB" are
both KLMN). Each OCR payee is matched against the client's known vendors:
  1. exact alias hit on the normalized OCR text  -> that vendor (kind "alias")
  2. fuzzy match vs tagger vendor_name + alias vendors -> best one if its score
     clears MIN_SCORE and beats the runner-up by MIN_MARGIN (kind "fuzzy")
  3. otherwise no match: the OCR text is kept and the row is flagged

Only COGS vendors are matched (tag "COGS" or "Cost of Goods Sold", any case).

Files (stock_processor/lookups/, gitignored):
  {client_id}_lookup.csv         tagger lookup: vendor_name + tag columns. READ ONLY.
  {client_id}_lookup.xlsx        manual lookup: one tab per year; tabs without both a
                                 Vendor and a Category column are skipped. READ ONLY.
  {client_id}_check_aliases.csv  ocr_text_norm, vendor_name, date_saved. Read + write.
"""
import csv
import os
import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

LOOKUPS_DIR = Path(__file__).resolve().parent.parent / "stock_processor" / "lookups"
ALIAS_COLS = ["ocr_text_norm", "vendor_name", "date_saved"]
COGS_TAGS = {"COGS", "COST OF GOODS SOLD"}

# Chosen 6 Oct 2026 from 400 synthetic misreads + 48 non-vendor payees: 0 wrong vendor
# matches, 0/48 non-vendors matched, ~10% of misreads flagged (test_payee_match.py --report)
MIN_SCORE = 0.60
MIN_MARGIN = 0.10  # over the runner-up; this is what flags "ACME" when two vendors start ACME
MIN_WINDOW = 3     # letters; shorter token windows ("CO", "NC") are not matched alone


def norm(text):
    """Uppercase, letters and single spaces only."""
    return " ".join(re.sub(r"[^A-Z]+", " ", str(text or "").upper()).split())


def _windows(tokens):
    """Letters of every contiguous run of tokens (with >= MIN_WINDOW letters)."""
    out = set()
    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens) + 1):
            w = "".join(tokens[i:j])
            if len(w) >= MIN_WINDOW:
                out.add(w)
    return out


def score(ocr_norm, vendor_norm):
    """Best ratio of the OCR letters vs the whole vendor name or any run of its tokens.

    Token runs handle bank-style names with extra tokens ("ACME SUPPLY CO NC"
    vs handwritten "ACME"). OCR text is always compared whole: OCR splits words
    at random ("KAL MB"), and scoring a fragment ("KAL") alone lifts look-alike
    vendors (KLAX) and erases the margin.
    """
    a, b = ocr_norm.replace(" ", ""), vendor_norm.replace(" ", "")
    if not a or not b:
        return 0.0
    best = SequenceMatcher(None, a, b).ratio()
    for w in _windows(vendor_norm.split()):
        best = max(best, SequenceMatcher(None, a, w).ratio())
    return best


@dataclass
class Match:
    vendor: str         # matched vendor_name, "" if none
    kind: str           # "alias" | "fuzzy" | "none"
    score: float = 0.0
    runner_up: float = 0.0


class PayeeMatcher:
    def __init__(self, vendors, aliases=None):
        """vendors: vendor_name strings; aliases: {ocr_text_norm: vendor_name}."""
        self.aliases = dict(aliases or {})
        self.vendors = {}  # norm -> exact name (first seen wins)
        for v in list(vendors) + list(self.aliases.values()):
            n = norm(v)
            if n and n not in self.vendors:
                self.vendors[n] = str(v)

    def ranked(self, ocr_text):
        n = norm(ocr_text)
        return sorted(((score(n, vn), name) for vn, name in self.vendors.items()), reverse=True)

    def match(self, ocr_text):
        n = norm(ocr_text)
        if not n:
            return Match("", "none")
        if n in self.aliases:
            return Match(self.aliases[n], "alias", 1.0)
        ranked = self.ranked(ocr_text)
        if not ranked:
            return Match("", "none")
        best, name = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        if best >= MIN_SCORE and best - second >= MIN_MARGIN:
            return Match(name, "fuzzy", best, second)
        return Match("", "none", best, second)


# ── Files ──────────────────────────────────────────────────────────────────────

def lookup_path(client_id, lookups_dir=LOOKUPS_DIR):
    return Path(lookups_dir) / f"{client_id}_lookup.csv"


def manual_lookup_path(client_id, lookups_dir=LOOKUPS_DIR):
    return Path(lookups_dir) / f"{client_id}_lookup.xlsx"


def aliases_path(client_id, lookups_dir=LOOKUPS_DIR):
    return Path(lookups_dir) / f"{client_id}_check_aliases.csv"


def list_clients(lookups_dir=LOOKUPS_DIR):
    """client_ids that have a tagger (.csv) or manual (.xlsx) lookup file."""
    d = Path(lookups_dir)
    if not d.is_dir():
        return []
    ids = {p.name.rsplit("_lookup.", 1)[0] for p in [*d.glob("*_lookup.csv"), *d.glob("*_lookup.xlsx")]
           if not p.name.startswith("~$")}  # ~$ = Excel's lock file while the workbook is open
    return sorted(ids)


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def is_cogs(tag):
    return " ".join(str(tag or "").upper().split()) in COGS_TAGS


def _manual_vendors(path):
    """COGS vendors from every tab with a Vendor and a Category column (header = first row)."""
    if not path.exists():
        return []
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    out = []
    try:
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = [str(h or "").strip().lower() for h in next(rows, ())]
            vcol = next((i for i, h in enumerate(header) if "vendor" in h), None)
            ccol = next((i for i, h in enumerate(header) if "category" in h), None)
            if vcol is None or ccol is None:
                continue
            for r in rows:
                v = r[vcol] if vcol < len(r) else None
                c = r[ccol] if ccol < len(r) else None
                if v is not None and str(v).strip() and is_cogs(c):
                    out.append(str(v).strip())
    finally:
        wb.close()
    return out


def load_vendors(client_id, lookups_dir=LOOKUPS_DIR):
    """COGS vendor names from the tagger CSV and the manual workbook (both opened read-only)."""
    tagger = [r["vendor_name"] for r in _read_rows(lookup_path(client_id, lookups_dir))
              if (r.get("vendor_name") or "").strip() and is_cogs(r.get("tag"))]
    return tagger + _manual_vendors(manual_lookup_path(client_id, lookups_dir))


def load_aliases(client_id, lookups_dir=LOOKUPS_DIR):
    return {r["ocr_text_norm"]: r["vendor_name"] for r in _read_rows(aliases_path(client_id, lookups_dir))
            if r.get("ocr_text_norm") and r.get("vendor_name")}


def load_matcher(client_id, lookups_dir=LOOKUPS_DIR):
    return PayeeMatcher(load_vendors(client_id, lookups_dir), load_aliases(client_id, lookups_dir))


def save_aliases(client_id, corrections, lookups_dir=LOOKUPS_DIR):
    """Add/replace aliases. corrections: [(ocr_text, vendor_name)]. Returns count saved.

    Keyed on normalized OCR text (last one wins). Writes the aliases file only.
    """
    rows = {r["ocr_text_norm"]: r for r in _read_rows(aliases_path(client_id, lookups_dir))}
    saved = 0
    for ocr_text, vendor in corrections:
        n, vendor = norm(ocr_text), str(vendor or "").strip()
        if n and vendor:
            rows[n] = {"ocr_text_norm": n, "vendor_name": vendor, "date_saved": date.today().isoformat()}
            saved += 1
    if saved:
        path = aliases_path(client_id, lookups_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ALIAS_COLS)
            w.writeheader()
            w.writerows(rows.values())
        os.replace(tmp, path)
    return saved
