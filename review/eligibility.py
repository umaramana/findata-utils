"""§5 eligibility gate (document-level) - SPEC.md §5.2.

Detects source documents whose income the comparison logic was never built
to read - consolidated brokerage statements (INT+DIV+B in one PDF), Schedule
K-1s, 1099-OID - and excludes them before extraction. SPEC.md §5.2's own
reasoning: "the comparison shows a shortfall that is not an error" for these,
so the right move is to skip and say why, never to flag. Running Path A on an
excluded document also wastes real time/cost on it for nothing - consolidated
statements sampled 21 Sep run 6-21 pages vs 1-2 for standalone forms.

Detection is by document content (pdfplumber text layer), not filename -
these documents are not reliably named in practice (see the Morgan Stanley
"MS_2025_1099-CONS_..." examples, which do name themselves, but nothing
guarantees that in general).

Not covered here - SPEC.md §5.2's other rows are properties of the RETURN,
not of a source document (Schedule E/F, Schedule C home office, 1099-S,
seller-financed mortgage interest with no 1099 at all): they need more
Drake-return parsing than drake.py currently does. See PARKING_LOT.md.
"""
import re
from pathlib import Path

import pdfplumber

# Checked in order against the whole document's extracted text (lowercased).
# First match wins - order only affects which reason string is reported when
# a document (as consolidated statements typically do) matches more than one.
_INELIGIBLE_PATTERNS = [
    ("consolidated 1099 (1099-B / broker proceeds present)",
     re.compile(r"1099-?b\b|proceeds from broker|barter exchange")),
    ("consolidated statement (multiple 1099 sections in one document)",
     re.compile(r"consolidated\s+(form\s+)?1099|consolidated\s+tax\s+statement")),
    ("Schedule K-1",
     re.compile(r"schedule\s*k-?1\b|partner'?s?\s+share\s+of\s+(income|profit)")),
    ("1099-OID (original issue discount)",
     re.compile(r"1099-?oid\b|original issue discount")),
]


def classify(path: Path) -> str | None:
    """Reason string if the document is out of scope per SPEC.md §5.2's
    document-type rows, else None (eligible, or undeterminable here).

    A document with no text layer returns None rather than excluding it -
    image-only pages already get their own REVIEW/FAIL handling in the
    redaction gate; this function only acts on documents it can actually
    read, same principle as drake.py's blank-vs-not-found distinction: a
    miss is never treated as a positive result."""
    try:
        with pdfplumber.open(path) as pdf:
            text = " ".join(page.extract_text() or "" for page in pdf.pages).lower()
    except Exception:
        return None  # let the existing unreadable-file handling deal with it
    if not text.strip():
        return None
    for reason, pattern in _INELIGIBLE_PATTERNS:
        if pattern.search(text):
            return reason
    return None
