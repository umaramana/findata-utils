"""Step 2 - compare extracted source-document totals against the Drake return.

The Drake side is read by drake.py (capability A): line-id markers first, a
label-line fallback second, so rows holding two boxes (2a/2b, 3a/3b) come out
right. A line that drake.py cannot read reports "NO DRAKE LINE" here; a line
printed blank on the return compares as 0.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import drake

CATEGORY_LABELS = {
    "wages": "Line 1 - Wages",
    "federal_withholding_w2": "Line 25a - Federal withholding, W-2 (W-2 Box 2)",
    "tax_exempt_interest": "Line 2a - Tax-exempt interest (1099-INT Box 8 + 1099-DIV Box 12)",
    "taxable_interest": "Line 2b - Taxable interest (1099-INT Box 1 + Box 3)",
    "ordinary_dividends": "Line 3b - Ordinary dividends",
}

# 1098 (mortgage interest / Schedule A) is out of v1 scope per the real
# SPEC.md §1/§10 - dropped from extract.py's _FORM_FIELDS too, so no
# extraction ever produces a mortgage_interest field to compare here.
#
# federal_withholding_w2 compares to line 25a (user decision, 21 Sep 2026; SPEC.md §6 had left it [FILL]).
# The sum still comes from W-2 box 2 only (via _CATEGORY_ALIASES below). A 1099 with federal withholding
# belongs on 25b, so it is not summed here.
#
# category -> Form 1040 line ids, first one drake.py can read wins. Wages is
# line 1a (total of W-2 box 1); 1z is only the fallback for a return whose
# layout lacks a 1a row.
_DRAKE_LINES_FOR_CATEGORY = {
    "wages": ["1a", "1z"],
    "federal_withholding_w2": ["25a"],  # user decision 21 Sep: W-2 box 2 sum compares to line 25a
    "tax_exempt_interest": ["2a"],
    "taxable_interest": ["2b"],
    "ordinary_dividends": ["3b"],
}

# Deterministic field_name -> category mapping (extract.py asks the model to
# use these exact box names). Falls back to a loose substring match for
# anything a vision model phrases differently. box_1b_qualified_dividends
# and "other_boxes" are deliberately NOT aliased to any category here - the
# real spec leaves 1b's comparison as [FILL] (extracted, not yet summed) and
# other_boxes is extract-for-completeness only (SPEC §4.2/§4.3), never
# summed into a line.
_CATEGORY_ALIASES = {
    "wages": ["box_1_wages", "wages"],
    "federal_withholding_w2": ["box_2_federal_withheld"],
    "taxable_interest": [
        "box_1_interest_income", "box_3_us_savings_bonds_treasury_interest", "taxable_interest",
    ],
    "tax_exempt_interest": [
        "box_8_tax_exempt_interest", "box_12_exempt_interest_dividends", "tax_exempt_interest",
    ],
    "ordinary_dividends": ["box_1a_ordinary_dividends", "ordinary_dividends"],
}

TOLERANCE = 1.00


def extract_drake_lines(drake_path: Path) -> dict:
    """{category: amount|None} read from the Drake return by drake.py."""
    ret = drake.parse_drake(drake_path)
    result = {}
    for category, line_ids in _DRAKE_LINES_FOR_CATEGORY.items():
        result[category] = next((v for v in (ret.value(i) for i in line_ids) if v is not None), None)
    return result


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def categorize_field(field_name: str) -> str | None:
    norm = _normalize(field_name)
    for category, aliases in _CATEGORY_ALIASES.items():
        for alias in aliases:
            alias_norm = _normalize(alias)
            if alias_norm in norm or norm in alias_norm:
                return category
    return None


def sum_by_category(extractions: list) -> tuple[dict, dict]:
    """(sums, contributions) - contributions[category] = [(source_file, field_name, value), ...]"""
    sums, contributions = {}, {}
    for ex in extractions:
        for field_name, value in ex.fields.items():
            category = categorize_field(field_name)
            if category is None or not isinstance(value, (int, float)):
                continue
            sums[category] = sums.get(category, 0.0) + value
            contributions.setdefault(category, []).append((ex.source_file, field_name, value))
    return sums, contributions


@dataclass
class ComparisonRow:
    category: str
    label: str
    source_total: float
    drake_line: float | None
    diff: float | None
    status: str  # "MATCH" | "FLAG" | "NO DRAKE LINE"
    contributions: list = field(default_factory=list)


def compare(extractions: list, drake_path: Path) -> list[ComparisonRow]:
    drake_lines = extract_drake_lines(drake_path)
    sums, contributions = sum_by_category(extractions)
    rows = []
    for category, label in CATEGORY_LABELS.items():
        total = round(sums.get(category, 0.0), 2)
        drake_val = drake_lines.get(category)
        contribs = contributions.get(category, [])
        if drake_val is None:
            rows.append(ComparisonRow(category, label, total, None, None, "NO DRAKE LINE", contribs))
            continue
        diff = round(total - drake_val, 2)
        status = "MATCH" if abs(diff) <= TOLERANCE else "FLAG"
        rows.append(ComparisonRow(category, label, total, drake_val, diff, status, contribs))
    return rows
