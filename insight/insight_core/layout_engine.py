"""
F05-S04 — Page Layout Engine.
layout_report(rendered_sections, grid_density, options) -> list of page dicts.

Places rendered chart/table images onto report pages. Pure layout logic — no rendering.
Consumed by PDF builder (F05-S05).

Bucket model (fixed order, fixed rules):
  1 — body_measurements      : always full-width, alone in page-row
  2 — body_vitals, strength  : grid_density applies here only
  3 — physio_1/2/3, balance  : always full-width; HARD page break before first item

Canva content area: 1024×768px canvas, safe rectangle x:30→994 y:20→748 → 728px usable height.
Measured at 150 DPI: body_measurements≈588px, vitals≈359–509px, heatmap≈116+58×n_dates px.

Input
-----
rendered_sections : list of dicts, each containing at minimum:
    component_id       str   determines bucket assignment
    rendered_height_px int   height of this chart's PNG at render DPI
    rendered_width_px  int   width of this chart's PNG at render DPI
    (all other fields passed through unchanged to the output rows)

grid_density : "1x1" | "1x2" | "2x1" | "2x2"   applies to Bucket 2 only

Output
------
list of page dicts:
[
    {
        "page_num": int,
        "rows": [
            {
                "cols": int,           # 1 = full-width, 2 = half-width each
                "row_height_px": int,  # max(rendered_height_px) across sections in row
                "sections": [...]      # 1 or 2 section dicts, passed through from input
            },
            ...
        ]
    },
    ...
]
When no sections are provided across all buckets:
    [{"page_num": 1, "error": "empty_report", "rows": []}]
"""

BUCKET_1_IDS = {"body_measurements"}
BUCKET_2_IDS = {"body_vitals", "strength"}
BUCKET_3_IDS = {"physio_1", "physio_2", "physio_3", "balance_open", "balance_closed"}

# Derived metrics have no component_id of their own — always Bucket 2 regardless
# of whatever component_id the section dict carries (or even if it's absent).
BUCKET_2_DERIVED_METRIC_IDS = {"bmi", "waist_hip_ratio"}

USABLE_HEIGHT_PX = 633   # Chart area: y:115 (below 100px logo) → 748 = 633px usable

_VALID_DENSITIES = {"1x1", "1x2", "2x1", "2x2"}
_ITEMS_PER_GROUP = {"1x1": 1, "1x2": 2, "2x1": 2, "2x2": 4}
_ITEMS_PER_ROW   = {"1x1": 1, "1x2": 2, "2x1": 1, "2x2": 2}


# ── Public API ────────────────────────────────────────────────────────────────

def layout_report(rendered_sections, grid_density, options=None):
    """Partition sections into buckets and lay them out across pages."""
    if grid_density not in _VALID_DENSITIES:
        raise ValueError(f"Unknown grid_density: {grid_density!r}. Must be one of {_VALID_DENSITIES}")

    if not rendered_sections:
        return [{"page_num": 1, "error": "empty_report", "rows": []}]

    b1, b2, b3 = _partition(rendered_sections)

    if not any([b1, b2, b3]):
        return [{"page_num": 1, "error": "empty_report", "rows": []}]

    pages = []
    _layout_bucket(b1, "1x1",       pages, force_new_page=False)
    _layout_bucket(b2, grid_density, pages, force_new_page=False)
    _layout_bucket(b3, "1x1",       pages, force_new_page=True)
    return [{"page_num": p["page_num"], "rows": p["rows"]} for p in pages]


# ── Internal helpers (exposed for unit testing) ───────────────────────────────

def _partition(sections):
    """Sort sections into (bucket1, bucket2, bucket3), preserving selection order within each."""
    b1, b2, b3 = [], [], []
    for s in sections:
        cid = s.get("component_id", "")
        mid = s.get("metric_id", "")
        # Derived metrics override: bmi and waist_hip_ratio always land in Bucket 2
        # regardless of what component_id the section carries.
        if mid in BUCKET_2_DERIVED_METRIC_IDS:
            b2.append(s)
        elif cid in BUCKET_1_IDS:
            b1.append(s)
        elif cid in BUCKET_2_IDS:
            b2.append(s)
        elif cid in BUCKET_3_IDS:
            b3.append(s)
        # Unrecognised: silently skipped
    return b1, b2, b3


def _chunk(sections, n):
    """Split a list into consecutive groups of up to n items."""
    return [sections[i:i+n] for i in range(0, len(sections), n)]


def _group_to_rows(group, grid_density):
    """Convert a section group into row descriptors per the grid density."""
    items_per_row = _ITEMS_PER_ROW[grid_density]
    rows = []
    for i in range(0, len(group), items_per_row):
        row_secs = group[i:i+items_per_row]
        rows.append({
            "cols": items_per_row,
            "row_height_px": max(s["rendered_height_px"] for s in row_secs),
            "sections": row_secs,
        })
    return rows


def _layout_bucket(sections, grid_density, pages, force_new_page):
    """Append section groups from one bucket onto pages with height-based pagination."""
    if not sections:
        return

    if force_new_page or not pages:
        pages.append({"page_num": len(pages) + 1, "rows": [], "height_used_px": 0})

    n      = _ITEMS_PER_GROUP[grid_density]
    groups = _chunk(sections, n)

    for group in groups:
        rows         = _group_to_rows(group, grid_density)
        group_height = sum(r["row_height_px"] for r in rows)
        current      = pages[-1]

        # Start a new page only when current page already has content and the
        # next group would overflow — never when the current page is empty
        # (avoids an infinite loop if a single group exceeds USABLE_HEIGHT_PX).
        if current["height_used_px"] > 0 and \
                current["height_used_px"] + group_height > USABLE_HEIGHT_PX:
            pages.append({"page_num": len(pages) + 1, "rows": [], "height_used_px": 0})
            current = pages[-1]

        current["rows"].extend(rows)
        current["height_used_px"] += group_height
