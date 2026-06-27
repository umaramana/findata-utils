"""
F04-S05 — Table Heatmap renderer (Python/matplotlib, server-side).
render_table_heatmap(data, options) -> PNG bytes.
Consumed by layout engine (F05-S04) and PDF builder (F05-S05).

Layout: dates as rows, metrics as columns (matches Looker layout).
Colour:  full-cell fill, global min→lightest pink, global max→darkest magenta.

Data shape
----------
{
  "metrics": [
    {"label": str, "unit": str, "readings": [{"date": "YYYY-MM-DD", "value": float}, ...]},
    ...
  ]
}

Options (all optional)
----------------------
title       str    chart title
unit_note   str    small note top-right (e.g. "COUNT PER MIN")
width_in    float  figure width in inches (default auto)
height_in   float  figure height in inches (default auto)
dpi         int    output resolution (default 150)
"""

import io
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
import matplotlib.font_manager as fm

# ── Fonts (same bundle as chart_renderer) ─────────────────────────────────────
_FONTS_DIR  = os.path.join(os.path.dirname(__file__), "fonts")
_F_BUBBLE   = os.path.join(_FONTS_DIR, "Bubblegum_Sans", "BubblegumSans-Regular.ttf")
_F_ROBOTO   = os.path.join(_FONTS_DIR, "Roboto", "static", "Roboto-Regular.ttf")
_F_ROBOTO_C = os.path.join(_FONTS_DIR, "Roboto_Condensed", "static", "RobotoCondensed-Regular.ttf")

def _fp_text(size): return fm.FontProperties(fname=_F_BUBBLE,   size=size)
def _fp_num(size):  return fm.FontProperties(fname=_F_ROBOTO,   size=size)
def _fp_axis(size): return fm.FontProperties(fname=_F_ROBOTO_C, size=size)

# ── Colour palette ────────────────────────────────────────────────────────────
_MAGENTA    = "#880e4f"   # titles
_HEADER_BG  = "#f0f0f0"   # header row + date-label column
_NO_DATA_BG = "#f5f7f8"   # no-data cells
_BORDER     = "#E5E7EB"   # cell borders
_TEXT       = "#1a1a1a"   # dark text
_MUTED      = "#6b7280"   # no-data italic text

# 8-stop brand gradient: light pink (min) → darkest magenta (max).
# #f538a0 (vivid, lum 124.4) placed BEFORE #ce5a92 (muted, lum 131.0).
# This prevents the R-channel spike (206→245) that the old ce5a92→f538a0
# order created; instead the gradient peaks in vividness at f538a0 then
# deepens smoothly through the muted/dark family.
_HEATMAP_STOPS = [
    "#f8bbd0",  # lum 207.6 — lightest baby pink
    "#f06292",  # lum 145.9 — warm pink
    "#f538a0",  # lum 124.4 — vivid bright pink (bright peak)
    "#ce5a92",  # lum 131.0 — medium magenta (less vivid, deepens from here)
    "#ab4e5f",  # lum 107.7 — muted rose
    "#bf1d6f",  # lum  86.8 — deep magenta
    "#ad1457",  # lum  73.3 — dark magenta
    "#880e4f",  # lum  57.9 — darkest wine
]
_HEATMAP_CMAP = LinearSegmentedColormap.from_list("insight_heatmap", _HEATMAP_STOPS)

# ── Layout constants (inches) ─────────────────────────────────────────────────
_LABEL_W = 1.6    # date-label column
_HDR_H   = 0.65   # header row (taller for potentially 2-line metric names)
_ROW_H   = 0.50   # data row
_TITLE_H = 0.40   # title band


# ── Public API ────────────────────────────────────────────────────────────────

def render_table_heatmap(data, options=None):
    """Render a full-cell-fill heatmap table and return PNG bytes."""
    options = options or {}

    if not data or not data.get("metrics"):
        return _no_data_png(options)

    populated = [m for m in data["metrics"] if m.get("readings")]
    if not populated:
        return _no_data_png(options)

    all_dates    = sorted({r["date"] for m in populated for r in m["readings"]})
    n_metrics    = len(populated)
    n_dates      = len(all_dates)
    title        = options.get("title", "")
    unit_note    = options.get("unit_note", "")
    value_format = options.get("value_format", "g")   # "g" | "hms"
    dpi          = options.get("dpi", 150)

    # Auto-size metric columns: narrower when many metrics
    metric_w  = min(1.4, max(0.9, 7.0 / max(n_metrics, 1)))

    title_h   = _TITLE_H if title else 0
    total_w   = _LABEL_W + metric_w * n_metrics
    total_h   = title_h + _HDR_H + _ROW_H * n_dates + 0.1

    w = options.get("width_in",  total_w)
    h = options.get("height_in", total_h)

    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)

    y_table_top = h - title_h

    if title:
        ax.text(w / 2, h - title_h / 2, title,
                ha="center", va="center",
                fontproperties=_fp_text(11), color=_MAGENTA)

    if unit_note:
        note_y = (h - title_h / 2) if title else (h - 0.15)
        ax.text(w - 0.05, note_y, unit_note,
                ha="right", va="center",
                fontproperties=_fp_text(7), color=_MUTED)

    # ── Header row: blank date-label cell + metric name cells ──────────────────
    _cell(ax, 0, y_table_top - _HDR_H, _LABEL_W, _HDR_H, bg=_HEADER_BG)

    for col_i, m in enumerate(populated):
        cx = _LABEL_W + metric_w * col_i
        _cell(ax, cx, y_table_top - _HDR_H, metric_w, _HDR_H, bg=_HEADER_BG)
        ax.text(cx + metric_w / 2, y_table_top - _HDR_H / 2,
                m.get("label", ""),
                ha="center", va="center",
                fontproperties=_fp_text(8), color=_TEXT,
                fontweight="bold")

    # ── Cell data: 1 date → row normalization; 2+ dates → per-column ─────────
    cells = _prepare_cells(populated, all_dates)

    # Reshape flat list into metric_cells[metric_i][date] for O(1) lookup
    metric_cells = []
    cells_iter = iter(cells)
    for _ in populated:
        date_map = {d: next(cells_iter) for d in all_dates}
        metric_cells.append(date_map)

    # ── Data rows: one row per date ────────────────────────────────────────────
    for row_i, d in enumerate(all_dates):
        y_bot = y_table_top - _HDR_H - _ROW_H * (row_i + 1)
        y_mid = y_bot + _ROW_H / 2

        # Date label cell
        _cell(ax, 0, y_bot, _LABEL_W, _ROW_H, bg=_HEADER_BG)
        ax.text(_LABEL_W * 0.06, y_mid, _fmt_date_label(d),
                ha="left", va="center",
                fontproperties=_fp_axis(8.5), color=_TEXT)

        # Value cells (one per metric column)
        for col_i in range(n_metrics):
            cx = _LABEL_W + metric_w * col_i
            c  = metric_cells[col_i][d]

            if c["type"] == "no_data":
                _cell(ax, cx, y_bot, metric_w, _ROW_H, bg=_NO_DATA_BG)
                ax.text(cx + metric_w / 2, y_mid, "No data",
                        ha="center", va="center",
                        fontproperties=_fp_axis(7), color=_MUTED,
                        style="italic")
            else:
                bg_rgb = _value_color(c["fill_prop"])
                _cell(ax, cx, y_bot, metric_w, _ROW_H, bg=bg_rgb)
                ax.text(cx + metric_w / 2, y_mid,
                        _fmt_value(c["value"], value_format),
                        ha="center", va="center",
                        fontproperties=_fp_num(9),
                        color=_text_color_for_bg(bg_rgb))

    return _to_png(fig, dpi)


# ── Data preparation (exposed for testing) ────────────────────────────────────

def _prepare_cells(populated, all_dates):
    """
    Return a flat list of cell descriptors, metric-major / date-minor order.

    Normalization strategy:
      1 date  → across the row  (compare all metrics at this single assessment)
      2+ dates → per column     (compare each metric to itself across time)

    fill_prop = 0.0 (lightest) → 1.0 (darkest); None for no_data cells only.
    fill_prop = 1.0 when a metric has no range (single value or all equal).

    Each dict:
      col_i     int           date index in all_dates
      date      str           YYYY-MM-DD
      type      "value"|"no_data"
      value     float|None
      fill_prop float|None
    """
    if len(all_dates) == 1:
        # Single date: normalize across the row — compare all metric values together
        all_values = [float(r["value"]) for m in populated for r in m.get("readings", [])]
        g_min   = min(all_values) if all_values else None
        g_max   = max(all_values) if all_values else None
        g_range = (g_max - g_min) if (g_min is not None and g_max > g_min) else None

        cells = []
        for m in populated:
            by_date = {r["date"]: float(r["value"]) for r in m.get("readings", [])}
            for col_i, d in enumerate(all_dates):
                if d not in by_date:
                    cells.append({"col_i": col_i, "date": d,
                                   "type": "no_data", "value": None, "fill_prop": None})
                else:
                    val       = by_date[d]
                    fill_prop = (val - g_min) / g_range if g_range is not None else 1.0
                    cells.append({"col_i": col_i, "date": d,
                                   "type": "value", "value": val, "fill_prop": fill_prop})
        return cells

    # Multiple dates: normalize per column — each metric's own range across time
    cells = []
    for m in populated:
        m_min, m_max = _row_range(m)
        m_range = (m_max - m_min) if (m_min is not None and m_max > m_min) else None

        by_date = {r["date"]: float(r["value"]) for r in m.get("readings", [])}
        for col_i, d in enumerate(all_dates):
            if d not in by_date:
                cells.append({"col_i": col_i, "date": d,
                               "type": "no_data", "value": None, "fill_prop": None})
            else:
                val       = by_date[d]
                fill_prop = (val - m_min) / m_range if m_range is not None else 1.0
                cells.append({"col_i": col_i, "date": d,
                               "type": "value", "value": val, "fill_prop": fill_prop})
    return cells


def _row_range(m):
    """Return (min, max) of readings values, or (None, None) if ≤ 1 reading."""
    vals = [float(r["value"]) for r in m.get("readings", [])]
    if len(vals) <= 1:
        return None, None
    return min(vals), max(vals)


# ── Colour helpers ────────────────────────────────────────────────────────────

def _value_color(fill_prop):
    """Map fill_prop 0→1 through the 8-stop brand gradient. Returns RGB tuple."""
    p = max(0.0, min(1.0, fill_prop if fill_prop is not None else 1.0))
    return _HEATMAP_CMAP(p)[:3]


def _fmt_value(val, fmt):
    """Format a cell value. fmt='g' (default) or 'hms' (seconds → HH:MM:SS)."""
    if fmt == "hms":
        secs = int(round(val))
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{val:g}"


def _text_color_for_bg(rgb):
    """White text on dark backgrounds, near-black on light."""
    r, g, b = rgb
    return "white" if (0.299 * r + 0.587 * g + 0.114 * b) < 0.55 else _TEXT


def _fmt_date_label(d):
    """'YYYY-MM-DD' → 'Mon YYYY'. Non-matching values pass through."""
    if not d:
        return d
    try:
        from datetime import datetime
        return datetime.strptime(str(d), "%Y-%m-%d").strftime("%b %Y")
    except ValueError:
        return d


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _cell(ax, x, y_bot, width, height, bg):
    ax.add_patch(Rectangle(
        (x, y_bot), width, height,
        facecolor=bg, edgecolor="none", linewidth=0, zorder=1,
    ))


def _to_png(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _no_data_png(options):
    w   = options.get("width_in",  5)
    h   = options.get("height_in", 3)
    dpi = options.get("dpi", 150)
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor(_NO_DATA_BG)
    ax.text(0.5, 0.5, "No data", ha="center", va="center",
            fontproperties=_fp_text(13), color=_MUTED, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    if options.get("title"):
        ax.set_title(options["title"], fontproperties=_fp_text(11),
                     color=_MAGENTA, pad=10)
    return _to_png(fig, dpi)
