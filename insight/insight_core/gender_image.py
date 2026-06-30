"""
F05-S06 — Metric-level image and icon resolution.

get_metric_visuals(metric_id, gender, asset_library, metric_asset_groups)
  → {image_ref: str|None, icon_ref: str|None}

Resolution rules
----------------
1. resolve_asset_group_key(metric_id): look up metric_id in metric_asset_groups;
   if a row exists use its asset_group_key, otherwise default to metric_id itself.
   This makes Balance pose-sharing (and any future component-level sharing) pure data,
   not a code branch.

2. Image lookup: exact asset_group_key match, role='image' → image_ref or None.
   Images are never gendered — same ref regardless of client gender.

3. Icon lookup: exact key+gender → key+ANY → None.
   Icons are gendered (M/F); ANY is a fallback for assets that work for both.

Data formats
------------
asset_library       : list of {asset_group_key, gender, role, image_ref}
                      role = 'image' | 'icon'
                      gender = 'M' | 'F' | 'ANY' (icons); blank/ANY (images)
metric_asset_groups : list of {metric_id, asset_group_key}
                      sparse — only needs rows where metric_id != asset_group_key

Sheet loaders
-------------
load_asset_library(spreadsheet)       → list of dicts (tab: asset_library)
load_metric_asset_groups(spreadsheet) → list of dicts (tab: metric_asset_groups)
"""

import logging

log = logging.getLogger(__name__)

_IMAGE_TAB  = "asset_library"
_GROUPS_TAB = "metric_asset_groups"


# ── Public API ────────────────────────────────────────────────────────────────

def get_metric_visuals(metric_id, gender, asset_library, metric_asset_groups):
    """
    Resolve the image_ref and icon_ref for a metric at render time.

    Returns dict with keys 'image_ref' and 'icon_ref', either of which may be None
    when no asset is registered. Callers must render gracefully with whatever is present.
    """
    key       = resolve_asset_group_key(metric_id, metric_asset_groups)
    image_ref = _find_image(key, asset_library)
    icon_ref  = _find_icon(key, gender, asset_library)
    return {"image_ref": image_ref, "icon_ref": icon_ref}


def resolve_asset_group_key(metric_id, metric_asset_groups):
    """
    Return the override asset_group_key for metric_id if one exists,
    otherwise return metric_id itself (the default per-metric key).
    """
    for row in metric_asset_groups:
        if row.get("metric_id") == metric_id:
            return row.get("asset_group_key") or metric_id
    return metric_id


# ── Sheet loaders (integration — require authenticated spreadsheet object) ─────

def load_asset_library(spreadsheet):
    """Load asset_library tab from the live sheet as a list of row dicts."""
    return _load_tab(spreadsheet, _IMAGE_TAB,
                     ["asset_group_key", "gender", "role", "image_ref"])


def load_metric_asset_groups(spreadsheet):
    """Load metric_asset_groups tab from the live sheet as a list of row dicts."""
    return _load_tab(spreadsheet, _GROUPS_TAB,
                     ["metric_id", "asset_group_key"])


# ── Private helpers ───────────────────────────────────────────────────────────

def _find_image(key, asset_library):
    """Ungendered image: exact asset_group_key + role='image' match."""
    for row in asset_library:
        if row.get("asset_group_key") == key and row.get("role") == "image":
            ref = row.get("image_ref", "")
            return ref if ref else None
    return None


def _find_icon(key, gender, asset_library):
    """Gendered icon: exact key+gender first, then key+ANY fallback."""
    any_fallback = None
    for row in asset_library:
        if row.get("asset_group_key") != key or row.get("role") != "icon":
            continue
        ref = row.get("image_ref", "") or None
        row_gender = row.get("gender", "")
        if row_gender == gender:
            return ref
        if row_gender in ("ANY", "") and any_fallback is None:
            any_fallback = ref
    return any_fallback


def _load_tab(spreadsheet, tab_name, columns):
    """Read a named tab and return rows as list of dicts keyed by columns."""
    try:
        ws   = spreadsheet.worksheet(tab_name)
        rows = ws.get_all_values()
    except Exception as exc:
        log.warning("Could not load tab %r: %s", tab_name, exc)
        return []

    if len(rows) < 2:
        return []

    header = [c.strip().lower() for c in rows[0]]
    col_idx = {col: header.index(col) for col in columns if col in header}

    result = []
    for row in rows[1:]:
        if not any(row):
            continue
        result.append({col: (row[idx] if idx < len(row) else "")
                       for col, idx in col_idx.items()})
    return result
