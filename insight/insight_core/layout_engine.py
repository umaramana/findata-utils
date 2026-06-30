"""
F05-S04 — Section Layout Engine (single-flow, no pagination).
layout_report(rendered_sections, grid_density) -> layout dict.

Partitions sections into three ordered content buckets and chunks Bucket 2
by grid_density. No page-break logic — the report is one continuous HTML flow.

Bucket model (fixed order, fixed rules):
  1 — body_measurements      : always full-width, alone
  2 — body_vitals, strength  : grid_density applies here only
  3 — physio_1/2/3, balance  : always full-width, never gridded

Grid densities
--------------
  1x1 → 1 item/group, 1 col   |  1x2 → 2 items/group, 2 cols
  2x1 → 2 items/group, 1 col  |  2x2 → 4 items/group, 2 cols
  3x2 → 6 items/group, 3 cols  (covers Bucket 2's real 6-item set)

Output
------
{
    "bucket1":       [section, ...],
    "bucket2_groups": [[section, ...], ...],   # chunked by density
    "bucket3":       [section, ...],
    "cols_per_row":  int,                      # 1, 2, or 3 for CSS grid
}
or {"error": "empty_report", "bucket1": [], "bucket2_groups": [], "bucket3": []}
"""

BUCKET_1_IDS = {"body_measurements"}
BUCKET_2_IDS = {"body_vitals", "strength"}
BUCKET_3_IDS = {"physio_1", "physio_2", "physio_3", "balance_open", "balance_closed"}

# Derived metrics always land in Bucket 2 regardless of component_id.
BUCKET_2_DERIVED_METRIC_IDS = {"bmi", "waist_hip_ratio"}

_VALID_DENSITIES  = {"1x1", "1x2", "2x1", "2x2", "3x2"}
_ITEMS_PER_GROUP  = {"1x1": 1, "1x2": 2, "2x1": 2, "2x2": 4, "3x2": 6}
_ITEMS_PER_ROW    = {"1x1": 1, "1x2": 2, "2x1": 1, "2x2": 2, "3x2": 3}


# ── Public API ────────────────────────────────────────────────────────────────

def layout_report(rendered_sections, grid_density, options=None):
    """Partition sections into buckets and return a CSS-ready layout dict."""
    if grid_density not in _VALID_DENSITIES:
        raise ValueError(
            f"Unknown grid_density: {grid_density!r}. Must be one of {_VALID_DENSITIES}"
        )

    if not rendered_sections:
        return {"error": "empty_report", "bucket1": [], "bucket2_groups": [], "bucket3": []}

    b1, b2, b3 = _partition(rendered_sections)

    if not any([b1, b2, b3]):
        return {"error": "empty_report", "bucket1": [], "bucket2_groups": [], "bucket3": []}

    return {
        "bucket1":       b1,
        "bucket2_groups": _chunk(b2, _ITEMS_PER_GROUP[grid_density]),
        "bucket3":       b3,
        "cols_per_row":  _ITEMS_PER_ROW[grid_density],
    }


# ── Internal helpers (exposed for unit testing) ───────────────────────────────

def _partition(sections):
    """Sort sections into (bucket1, bucket2, bucket3), preserving selection order."""
    b1, b2, b3 = [], [], []
    for s in sections:
        cid = s.get("component_id", "")
        mid = s.get("metric_id", "")
        if mid in BUCKET_2_DERIVED_METRIC_IDS:
            b2.append(s)
        elif cid in BUCKET_1_IDS:
            b1.append(s)
        elif cid in BUCKET_2_IDS:
            b2.append(s)
        elif cid in BUCKET_3_IDS:
            b3.append(s)
    return b1, b2, b3


def _chunk(sections, n):
    """Split a list into consecutive groups of up to n items."""
    return [sections[i:i+n] for i in range(0, len(sections), n)]
