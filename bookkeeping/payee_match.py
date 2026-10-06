"""
Payee matching for Check Extractor (Phase 2, spec: check_ocr_spec.md).

Handwritten payees misread differently on every check ("KLMB", "KAL MB" are
both KLMN). Each OCR payee is matched against the client's known vendors:
  1. exact alias hit on the normalized OCR text  -> that vendor (kind "alias")
  2. fuzzy match vs tagger vendor_name + alias vendors -> best one if its score
     clears MIN_SCORE and beats the runner-up by MIN_MARGIN (kind "fuzzy")
  3. otherwise no match: the OCR text is kept and the row is flagged

Files (stock_processor/lookups/, gitignored):
  {client_id}_lookup.csv         tagger lookup, vendor_name column. READ ONLY.
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


def aliases_path(client_id, lookups_dir=LOOKUPS_DIR):
    return Path(lookups_dir) / f"{client_id}_check_aliases.csv"


def list_clients(lookups_dir=LOOKUPS_DIR):
    """client_ids that have a tagger lookup file."""
    d = Path(lookups_dir)
    return sorted(p.name[: -len("_lookup.csv")] for p in d.glob("*_lookup.csv")) if d.is_dir() else []


def _read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_vendors(client_id, lookups_dir=LOOKUPS_DIR):
    """vendor_name values from the tagger lookup (opened read-only)."""
    return [r["vendor_name"] for r in _read_rows(lookup_path(client_id, lookups_dir))
            if (r.get("vendor_name") or "").strip()]


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
