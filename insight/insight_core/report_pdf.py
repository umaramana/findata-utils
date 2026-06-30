"""
F05-S05 — Full PDF report generator (infographic composer).
generate_full_report(...) → {"path": str, "version": int, "pages": int} | {"error": str}

Layout (single tall infographic content page between cover + closing):
  ┌──────────────────────┬─────────────────────────────┐
  │  Header (logo, title, name pill)                    │
  ├──────────────────────┬─────────────────────────────┤
  │  Body Measurements   │  Body Weight  (VITAL_H)     │  ← top band
  │  chart + 2 photos    ├─────────────────────────────┤
  │  (BM_H = VITAL_H×2) │  Waist-to-Hip (VITAL_H)     │
  ├──────────┬───────────┴──────────────────────────────┤
  │   BMI    │    Blood Pressure    │      Pulse         │  ← mid band
  ├──────────┴──────────────────────┴───────────────────┤
  │  Physiological heatmaps × N  (full width, stacked)  │
  │  Balance heatmap                                     │
  └─────────────────────────────────────────────────────┘

Charts render as VECTOR onto positioned axes (crisp, no PNG resize).
Icons (BW, WHR) are overlaid as inset axes inside the chart cell —
icon height < chart height rule always satisfied.
Images (BMI, BP, Pulse) occupy a reserved placeholder box to the right of
each mid-band chart. BM photos stack in a reserved column inside the BM cell.
"""

import os
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages

from report_query   import build_report_payload
from chart_renderer import draw_bar_into
from table_heatmap  import _draw_heatmap, heatmap_natural_size
from gender_image   import get_metric_visuals

log = logging.getLogger(__name__)

# ── Page / branding ──────────────────────────────────────────────────────────
PAGE_W, PAGE_H = 1024, 768       # cover + closing
CONTENT_W = 1024                 # infographic width; height computed per report
DPI = 200

_MAGENTA  = "#880e4f"
_MAROON   = "#6d1a47"
_MUTED    = "#6b7280"
_PILL_BG  = "#f0f0f0"
_PH_BG    = "#f4eef1"            # asset placeholder fill
_PH_EDGE  = "#e3d4dc"

_STRIP_W  = 12                   # left brand strip width (px)

# ── Fonts ─────────────────────────────────────────────────────────────────────
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_F_BUBBLE  = os.path.join(_FONTS_DIR, "Bubblegum_Sans", "BubblegumSans-Regular.ttf")
_F_ROBOTO  = os.path.join(_FONTS_DIR, "Roboto", "static", "Roboto-Regular.ttf")

def _fp_title(size): return fm.FontProperties(fname=_F_BUBBLE, size=size)
def _fp_num(size):   return fm.FontProperties(fname=_F_ROBOTO,  size=size)

# ── Assets ────────────────────────────────────────────────────────────────────
_ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "assets")
_BG_PNG       = os.path.join(_ASSETS_DIR, "Insight BG.png")
_LOGO_COVER   = os.path.join(_ASSETS_DIR, "Insight (400 × 400 px) logo.png")
_LOGO_CONTENT = os.path.join(_ASSETS_DIR, "Insight (200 X 100 Px) logo.png")
_CLOSING_PNG  = os.path.join(_ASSETS_DIR, "Insight Thank you Page.png")

# Local-file fallbacks — used when asset_library sheet has no row
_DEFAULT_ICONS = {
    "weight_kg":       {"M": "male/weight_male.png",     "F": "female/women-weight.jpg"},
    "waist_hip_ratio": {"M": "male/waisttohip_male.png", "F": "female/women-waisttohip.jpg"},
}
_DEFAULT_IMAGES = {
    "bmi":               "common/bmi.jpg",
    "bp_systol":         "common/bp_fullimage.jpg",
    "pulse":             "common/pulse_common100X200px.png",
    "body_measurements": "common/bodyweight_common_100X200px.png",
}

# ── Metric metadata ───────────────────────────────────────────────────────────
_HMS_COMPONENTS = {"physio_2", "balance_open", "balance_closed"}

_COMPONENT_TITLES = {
    "physio_1": "Physiological Assessment 1",
    "physio_2": "Physiological Assessment 2",
    "physio_3": "Physiological Assessment 3",
    "balance_open":   "Balance — Eyes Open",
    "balance_closed": "Balance — Eyes Closed",
    "strength": "Strength",
}
_COMPONENT_UNIT_NOTE = {
    "physio_1": "COUNT PER MIN",
    "physio_2": "IN HH:MM:SS",
    "balance_open":   "IN HH:MM:SS",
    "balance_closed": "IN HH:MM:SS",
}

_METRIC_META = {
    "weight_kg":       ("Body Weight",        "kg"),
    "height_cm":       ("Height",             "cm"),
    "fat_pct":         ("Body Fat",           "%"),
    "muscle_pct":      ("Muscle Mass",        "%"),
    "bp_systol":       ("Systolic",           "mmHg"),
    "bp_diastol":      ("Diastolic",          "mmHg"),
    "pulse":           ("Pulse",              "bpm"),
    "bmi":             ("BMI",                "kg/m²"),
    "bmr":             ("BMR",                "kcal"),
    "waist_hip_ratio": ("Waist to Hip Ratio", "ratio"),
    "waist":           ("Waist",              "cm"),
    "hips":            ("Hips",               "cm"),
    "neck_cm":         ("Neck",               "cm"),
    "shoulder_cm":     ("Shoulder",           "cm"),
    "chest_cm":        ("Chest",              "cm"),
    "abdomen_cm":      ("Abdomen",            "cm"),
    "thigh_cm":        ("Thigh",              "cm"),
    "calf_cm":         ("Calf",               "cm"),
    "forearm_cm":      ("Forearm",            "cm"),
    "wrist_cm":        ("Wrist",              "cm"),
}
_MEASUREMENT_ORDER = ["neck_cm", "chest_cm", "waist", "abdomen_cm", "hips",
                      "thigh_cm", "calf_cm", "shoulder_cm", "forearm_cm", "wrist_cm"]

# ── Content-page geometry (px, top-left origin) ───────────────────────────────
_MARGIN_L  = 45
_MARGIN_R  = 45
_HEADER_H  = 100       # branded header band height

USABLE_W   = CONTENT_W - _MARGIN_L - _MARGIN_R   # 934 px

# Top band: Body Measurements (left) | Body Weight + WHR (right)
VITAL_H    = 140       # height per vital cell (BW, WHR) — all the same
BM_H       = VITAL_H * 2    # Body Measurements spans both rows = 280 px

PHOTO_W    = 105       # photo/image strip on the right side of BM cell
COL1_W     = 440       # BM cell total width (chart + photo strip)
COL_GAP    = 20
COL2_X     = _MARGIN_L + COL1_W + COL_GAP   # 505
COL2_W     = CONTENT_W - COL2_X - _MARGIN_R  # 474

# Mid band: BMI | BP | Pulse (3 equal columns)
MID_H      = 155       # mid-band cell height
THIRD_W    = USABLE_W // 3     # 311 px per column

# Heatmap sizing
_HEATMAP_GAP     = 24
_HEATMAP_TITLE_H = 22
_HEATMAP_SCALE   = 105   # px per inch for heatmap layout

_BUCKET_3 = ["physio_1", "physio_2", "physio_3", "balance_open", "balance_closed"]

# ── Public API ────────────────────────────────────────────────────────────────

def generate_full_report(client_id, date_from, date_to, component_ids, grid_density,
                         all_readings, client_profile=None,
                         asset_library=None, metric_asset_groups=None,
                         output_dir=None):
    """Orchestrate the pipeline and write a versioned infographic PDF."""
    asset_library       = asset_library       or []
    metric_asset_groups = metric_asset_groups or []
    output_dir          = output_dir or os.path.join(os.path.dirname(__file__), "reports")

    payload = build_report_payload(client_id, date_from, date_to, component_ids,
                                   all_readings, client_profile)
    if "error" in payload:
        return payload

    components = payload.get("components", {})
    gender_key = "M" if str((client_profile or {}).get("gender", "")).lower().startswith("m") else "F"
    visuals    = _VisualResolver(gender_key, asset_library, metric_asset_groups)

    name       = client_id.replace("_", " ").title()
    date_label = _fmt_month_year(date_to)

    figs = [_cover_page(name, date_label)]
    figs.append(_content_page(components, visuals, name, date_label))
    figs.append(_closing_page())

    os.makedirs(output_dir, exist_ok=True)
    path, version = _versioned_path(output_dir, client_id, date_to)
    _save_pdf(figs, path)
    return {"path": path, "version": version, "pages": 3}


# ── Content page (tall infographic) ──────────────────────────────────────────

def _content_page(components, visuals, name, date_label):
    bm  = components.get("body_measurements", {})
    bv  = components.get("body_vitals", {})

    col2_items = _resolve_vitals_col2(bm, bv)   # [BW, WHR]
    mid_items  = _resolve_vitals_mid(bm, bv)    # [BMI, BP, Pulse]
    heatmaps   = _sized_heatmaps(components)

    has_top = bool(_measurement_series(bm) or col2_items)
    has_mid = bool(mid_items)

    # ── Compute total page height ─────────────────────────────────────────
    cursor = _HEADER_H + 10
    if has_top:
        cursor += BM_H + 14
    if has_mid:
        cursor += MID_H + 14
    for _cid, _w, _h in heatmaps:
        cursor += _HEATMAP_TITLE_H + _h + _HEATMAP_GAP
    total_h = max(PAGE_H, cursor + 30)

    cv = _Canvas(CONTENT_W, total_h, branded=True)
    _content_header(cv, name, date_label)

    y = _HEADER_H + 10

    # Top band: BM left, BW + WHR right
    if has_top:
        _draw_measurements_column(cv, bm, visuals, y)
        _draw_col2_vitals(cv, col2_items, visuals, y)
        y += BM_H + 14

    # Mid band: BMI | BP | Pulse
    if has_mid:
        _draw_mid_vitals(cv, mid_items, visuals, y)
        y += MID_H + 14

    # Heatmaps stacked full width
    for cid, disp_w, disp_h in heatmaps:
        cv.title(_MARGIN_L, y, _COMPONENT_TITLES.get(cid, cid), size=12)
        badge = _COMPONENT_UNIT_NOTE.get(cid, "")
        if badge:
            cv.badge(_MARGIN_L + USABLE_W, y, badge)   # right edge of content — no title overlap
        ax = cv.axes(_MARGIN_L, y + _HEATMAP_TITLE_H, disp_w, disp_h)
        _draw_heatmap(ax, {"metrics": _physio_series(components.get(cid, {}))},
                      {"title": "", "font_scale": 0.85,
                       "value_format": "hms" if cid in _HMS_COMPONENTS else "g"})
        y += _HEATMAP_TITLE_H + disp_h + _HEATMAP_GAP

    return cv.fig


# ── Top band: Body Measurements (left) + BW/WHR (right) ───────────────────────

def _draw_measurements_column(cv, bm, visuals, band_top):
    """
    Body Measurements grouped bar chart in the left column.
    Photos stack in a reserved strip at the right edge of the BM cell.
    Title drawn inside chart top-right (title_align='right').
    """
    meas = _measurement_series(bm)
    if not meas:
        return

    chart_w = COL1_W - PHOTO_W - 8   # chart takes all but the photo strip
    ax = cv.axes(_MARGIN_L, band_top, chart_w, BM_H)
    draw_bar_into(ax, {"metrics": meas}, "grouped_multi",
                  {"title": "Body Measurements", "title_align": "right",
                   "dpi": DPI, "font_scale": 0.68,
                   "show_unit_note": True, "show_legend": True,
                   "stagger_xlabels": True,
                   "width_in": chart_w / DPI, "height_in": BM_H / DPI})

    # 2 photos stacked on the right strip of the BM cell
    photo_h = BM_H // 2
    photo_x = _MARGIN_L + chart_w + 8
    bm_img  = visuals.image("body_measurements")
    cv.asset(photo_x, band_top,           PHOTO_W, photo_h, bm_img)
    cv.asset(photo_x, band_top + photo_h, PHOTO_W, photo_h, None)


def _draw_col2_vitals(cv, col2_items, visuals, band_top):
    """
    BW + WHR stacked in the right column.
    Each is horizontal_single; icon drawn as inset inside the chart cell.
    Icon sits in the rightmost 13% of the axes — bar xlim leaves room.
    """
    _DATE_PAD = 40   # px reserved to the left of axes for "Jun\n2026" y-tick label
    for i, item in enumerate(col2_items):
        y  = band_top + i * VITAL_H
        ax = cv.axes(COL2_X + _DATE_PAD, y, COL2_W - _DATE_PAD, VITAL_H)

        opts = {
            "title":            item["title"],
            "metric_id":        item.get("metric_id", ""),
            "dpi":              DPI,
            "font_scale":       0.68,
            "show_unit_note":   True,
            "show_date_labels": True,
            "compact_dates":    True,   # "Jun 2026" → "Jun\n2026" saves y-axis width
            "width_in":         (COL2_W - _DATE_PAD) / DPI,
        }
        draw_bar_into(ax, item["data"], item["mode"], opts)

        # Icon inset: right 13% of the chart axes, vertically centered
        icon_path = visuals.resolve_marker(item["asset"])
        if icon_path and os.path.exists(icon_path):
            try:
                img = mpimg.imread(icon_path)
                icon_ax = ax.inset_axes([0.85, 0.06, 0.12, 0.88])
                icon_ax.imshow(img, aspect="equal")
                icon_ax.axis("off")
            except Exception as exc:
                log.warning("Icon load failed (%s): %s", icon_path, exc)


# ── Mid band: BMI | BP | Pulse (3 equal columns) ──────────────────────────────

_MID_DATE_PAD = 32   # px reserved left of mid-band horizontal chart axes for y-tick date

def _draw_mid_vitals(cv, mid_items, visuals, band_top):
    """
    Three equal columns across the full content width.
    Each cell: chart (left ~72%) + image placeholder (right ~28%).
    Horizontal mode: date pad added to the left so "Jun\n2026" y-label doesn't clip.
    """
    for i, item in enumerate(mid_items):
        x       = _MARGIN_L + i * THIRD_W
        chart_w = int(THIRD_W * 0.72)
        asset_w = THIRD_W - chart_w - 8

        is_horiz = item["mode"] == "horizontal_single"
        dp       = _MID_DATE_PAD if is_horiz else 0
        ax = cv.axes(x + dp, band_top, chart_w - dp, MID_H)

        opts = {
            "title":            item["title"],
            "metric_id":        item.get("metric_id", ""),
            "dpi":              DPI,
            "font_scale":       0.75,
            "show_unit_note":   False,
            "show_date_labels": True,
            "compact_dates":    True,
            "width_in":         (chart_w - dp) / DPI,
        }
        if item["mode"] == "stacked_pair":
            opts["show_legend"]   = False
            opts["bar_thickness"] = 0.42
            draw_bar_into(ax, item["data"], "stacked_pair", opts)
        else:
            draw_bar_into(ax, item["data"], item["mode"], opts)

        # Image placeholder to the right (outside chart)
        asset_path = visuals.resolve_marker(item["asset"])
        cv.asset(x + chart_w + 8, band_top, asset_w, MID_H, asset_path)


# ── Cover / closing ───────────────────────────────────────────────────────────

def _cover_page(name, date_label):
    cv = _Canvas(PAGE_W, PAGE_H, branded=False, bg=True)
    cv.image(_LOGO_COVER, (PAGE_W - 330) // 2, 110, target=(330, 330))
    cv.fig.text(0.5, 0.50, "Fitness Dashboard for", ha="center", va="center",
                fontproperties=_fp_title(30), color=_MAGENTA)
    cv.fig.text(0.5, 0.40, name, ha="center", va="center",
                fontproperties=_fp_title(26), color=_MAGENTA)
    cv.fig.text(0.5, 0.31, f"Fitness Assessment for {date_label}", ha="center",
                va="center", fontproperties=_fp_title(14), color=_MAGENTA)
    return cv.fig


def _closing_page():
    if os.path.exists(_CLOSING_PNG):
        cv = _Canvas(PAGE_W, PAGE_H, branded=False)
        cv.image(_CLOSING_PNG, 0, 0, target=(PAGE_W, PAGE_H))
        return cv.fig
    cv = _Canvas(PAGE_W, PAGE_H, branded=False, bg=True)
    cv.fig.text(0.5, 0.5, "Thank You", ha="center", va="center",
                fontproperties=_fp_title(28), color=_MAGENTA)
    return cv.fig


def _content_header(cv, name, date_label):
    cv.image(_LOGO_CONTENT, _MARGIN_L - 8, 16, target=(170, 85))
    cv.fig.text(0.49, (cv.h - 50) / cv.h, "Anthropometric Assessment",
                ha="center", va="center", fontproperties=_fp_title(18), color=_MAGENTA)
    cv.fig.text(0.875, (cv.h - 40) / cv.h, f"{name}   {date_label}",
                ha="center", va="center", fontproperties=_fp_title(11), color=_MAGENTA,
                bbox=dict(boxstyle="round,pad=0.45", facecolor=_PILL_BG, edgecolor="none"))


# ── Heatmap sizing ────────────────────────────────────────────────────────────

def _sized_heatmaps(components):
    """Return [(cid, disp_w_px, disp_h_px)] for all populated Bucket-3 components."""
    avail_w = CONTENT_W - _MARGIN_L - _MARGIN_R
    out = []
    for cid in _BUCKET_3:
        comp = components.get(cid)
        if not comp:
            continue
        series = _physio_series(comp)
        if not series:
            continue
        nat_w, nat_h = heatmap_natural_size({"metrics": series}, {"title": ""})
        scale = min(_HEATMAP_SCALE, avail_w / nat_w) if nat_w else _HEATMAP_SCALE
        out.append((cid, nat_w * scale, nat_h * scale))
    return out


# ── Vitals planning ───────────────────────────────────────────────────────────

def _resolve_vitals_col2(bm, bv):
    """BW + WHR — right column, two rows."""
    return [item for item in (_vital_item(k, bm, bv) for k in ["weight_kg", "waist_hip_ratio"])
            if item]


def _resolve_vitals_mid(bm, bv):
    """BMI + BP + Pulse — 3-column mid band."""
    return [item for item in (_vital_item(k, bm, bv) for k in ["bmi", "bp", "pulse"])
            if item]


def _vital_item(key, bm, bv):
    if key == "weight_kg":
        r = _metric_readings(bv, "weight_kg")
        if r:
            return {"title": "Body Weight", "mode": "horizontal_single",
                    "metric_id": "weight_kg",
                    "data": {"label": "Body Weight", "unit": "kg", "readings": r},
                    "asset": self_icon("weight_kg")}
    elif key == "waist_hip_ratio":
        r = _derived_readings(bm, "waist_hip_ratio")
        if r:
            return {"title": "Waist to Hip Ratio", "mode": "horizontal_single",
                    "metric_id": "waist_hip_ratio",
                    "data": {"label": "Waist to Hip Ratio", "unit": "", "readings": r},
                    "asset": self_icon("waist_hip_ratio")}
    elif key == "bmi":
        r = _derived_readings(bv, "bmi")
        if r:
            return {"title": "BMI", "mode": "horizontal_single",
                    "metric_id": "bmi",
                    "data": {"label": "BMI", "unit": "kg/m²", "readings": r},
                    "asset": self_image("bmi")}
    elif key == "bp":
        sys_r = _metric_readings(bv, "bp_systol")
        dia_r = _metric_readings(bv, "bp_diastol")
        if sys_r and dia_r:
            return {"title": "Blood Pressure", "mode": "stacked_pair",
                    "metric_id": "bp_systol",
                    "data": {"series": [
                        {"label": "Systolic",  "unit": "mmHg", "readings": sys_r},
                        {"label": "Diastolic", "unit": "mmHg", "readings": dia_r}]},
                    "asset": self_image("bp_systol")}
    elif key == "pulse":
        r = _metric_readings(bv, "pulse")
        if r:
            return {"title": "Pulse", "mode": "horizontal_single",
                    "metric_id": "pulse",
                    "data": {"label": "Pulse", "unit": "bpm", "readings": r},
                    "asset": self_image("pulse")}
    return None


def self_icon(metric_id):  return ("icon",  metric_id)
def self_image(metric_id): return ("image", metric_id)


# ── Data extraction ───────────────────────────────────────────────────────────

def _metric_readings(component, metric_id):
    return (component.get("metrics", {}).get(metric_id) or {}).get("readings", [])

def _derived_readings(component, key):
    return component.get("derived", {}).get(key, [])

def _measurement_series(bm):
    metrics = bm.get("metrics", {})
    series  = []
    for mid in _MEASUREMENT_ORDER:
        readings = (metrics.get(mid) or {}).get("readings", [])
        if readings:
            label, unit = _label_unit(mid)
            series.append({"label": label, "unit": unit, "readings": readings})
    return series

def _physio_series(component):
    metrics = component.get("metrics", {})
    series  = []
    for mid, mdata in metrics.items():
        readings = mdata.get("readings", [])
        if readings:
            label, unit = _label_unit(mid)
            series.append({"label": label, "unit": unit, "readings": readings})
    return series


# ── Visual resolution ─────────────────────────────────────────────────────────

class _VisualResolver:
    def __init__(self, gender_key, asset_library, metric_asset_groups):
        self.gender = gender_key
        self.lib    = asset_library
        self.groups = metric_asset_groups

    def image(self, metric_id):
        return self._resolve("image", metric_id)

    def icon(self, metric_id):
        return self._resolve("icon", metric_id)

    def resolve_marker(self, marker):
        if not marker:
            return None
        role, metric_id = marker
        return self._resolve(role, metric_id)

    def _resolve(self, role, metric_id):
        v   = get_metric_visuals(metric_id, self.gender, self.lib, self.groups)
        ref = v.get("icon_ref") if role == "icon" else v.get("image_ref")
        path = _resolve_path(ref)
        if path:
            return path
        return _default_asset(role, metric_id, self.gender)


def _default_asset(role, metric_id, gender):
    if role == "icon":
        choice = _DEFAULT_ICONS.get(metric_id, {}).get(gender)
        return _resolve_path(choice)
    return _resolve_path(_DEFAULT_IMAGES.get(metric_id))

def _resolve_path(ref):
    if not ref:
        return None
    candidate = ref if os.path.isabs(ref) else os.path.join(_ASSETS_DIR, ref)
    return candidate if os.path.exists(candidate) else None


# ── Canvas (px coordinates from top-left, variable page height) ───────────────

class _Canvas:
    def __init__(self, w_px, h_px, branded=False, bg=False):
        self.w = w_px
        self.h = h_px
        self.fig = plt.figure(figsize=(w_px / DPI, h_px / DPI), dpi=DPI)
        self.fig.patch.set_facecolor("white")
        if bg and os.path.exists(_BG_PNG):
            self.image(_BG_PNG, 0, 0, target=(w_px, h_px))
        if branded:
            self.fig.add_artist(mpatches.Rectangle(
                (0, 0), _STRIP_W / self.w, 1.0, transform=self.fig.transFigure,
                facecolor=_MAROON, edgecolor="none", zorder=0))

    def axes(self, x, y, w, h):
        left   = x / self.w
        bottom = (self.h - (y + h)) / self.h
        return self.fig.add_axes([left, bottom, w / self.w, h / self.h])

    def title(self, x, y, text, size=12):
        self.fig.text(x / self.w, (self.h - y) / self.h, text,
                      ha="left", va="top",
                      fontproperties=_fp_title(size), color=_MAGENTA)

    def badge(self, x_right, y, text):
        self.fig.text(x_right / self.w, (self.h - y - 2) / self.h, text,
                      ha="right", va="top", fontproperties=_fp_num(7.5), color=_MUTED,
                      bbox=dict(boxstyle="round,pad=0.3", facecolor=_PILL_BG, edgecolor="none"))

    def asset(self, x, y, w, h, path):
        """Reserved asset box: placeholder always drawn, image overlaid when path available."""
        self.fig.add_artist(mpatches.FancyBboxPatch(
            (x / self.w, (self.h - (y + h)) / self.h),
            w / self.w, h / self.h,
            boxstyle="round,pad=0,rounding_size=0.004",
            transform=self.fig.transFigure,
            facecolor="none", edgecolor=_PH_EDGE, linestyle="dashed",
            linewidth=0.5, zorder=1))
        if path and os.path.exists(path):
            self._fit_image(path, x, y, w, h)

    def _fit_image(self, path, x, y, w, h):
        try:
            img = mpimg.imread(path)
        except Exception as exc:
            log.warning("Could not read asset %s: %s", path, exc)
            return
        ih, iw = img.shape[0], img.shape[1]
        scale  = min(w / iw, h / ih)
        tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
        xo     = x + (w - tw) // 2
        yo_top = y + (h - th) // 2
        self.image(path, xo, yo_top, target=(tw, th))

    def image(self, path, x_px, y_top_px, target=None):
        try:
            img = mpimg.imread(path)
        except Exception as exc:
            log.warning("Could not read image %s: %s", path, exc)
            return
        if target:
            img = _resize_array(img, target[0], target[1])
        ih = img.shape[0]
        yo = self.h - y_top_px - ih
        self.fig.figimage(img, xo=x_px, yo=yo, zorder=2)


# ── Image utility ─────────────────────────────────────────────────────────────

def _resize_array(img, w, h):
    from PIL import Image
    import numpy as np
    arr = (img * 255).astype("uint8") if img.dtype.kind == "f" else img
    pil = Image.fromarray(arr)
    pil = pil.resize((max(1, w), max(1, h)), Image.LANCZOS)
    out = np.asarray(pil)
    return out.astype("float32") / 255.0 if img.dtype.kind == "f" else out


# ── PDF save + versioning ──────────────────────────────────────────────────────

def _save_pdf(figs, path):
    with PdfPages(path) as pdf:
        for fig in figs:
            pdf.savefig(fig, dpi=DPI)
            plt.close(fig)


def _versioned_path(output_dir, client_id, date_to):
    base    = f"{client_id}_{date_to}_full_report"
    version = 1
    while True:
        candidate = os.path.join(output_dir, f"{base}_v{version}.pdf")
        if not os.path.exists(candidate):
            return candidate, version
        version += 1


# ── Small helpers ──────────────────────────────────────────────────────────────

def _label_unit(metric_id):
    if metric_id in _METRIC_META:
        return _METRIC_META[metric_id]
    return metric_id.replace("_", " ").title(), ""

def _fmt_month_year(date_str):
    try:
        from datetime import datetime
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y")
    except (ValueError, TypeError):
        return date_str
