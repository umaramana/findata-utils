"""
F04-S02/S03/S04 — Bar chart family renderer.
render_bar(data, mode, options) -> PNG bytes via matplotlib (server-side).
Consumed by layout engine (F05-S04) and PDF builder (F05-S05).

Visual style is driven by chart_style.INSIGHT_STYLE — edit that file to tune
colors, typography, and bar geometry without touching renderer logic.

Modes
-----
horizontal_single  one horizontal bar per date, single metric stands alone
                   (weight_kg, waist_hip_ratio)
vertical_single    one vertical bar per date, single metric stands alone
                   (BMI, bmr, pulse) — supports truncate_y for narrow-range metrics
stacked_pair       two metrics stacked in one bar per date, both segments individually labeled
                   (fat_pct+muscle_pct, bp_systol+bp_diastol)
grouped_multi      multiple metrics as clustered bars, one date-group per date
                   (body_measurements, strength pairs)
                   → scorecard path: 1 metric + 1 date → large-value display, no bars

Data shapes
-----------
horizontal_single / vertical_single:
    {"label": str, "unit": str, "readings": [{"date": "YYYY-MM-DD", "value": float}, ...]}

stacked_pair:
    {"series": [
        {"label": str, "unit": str, "readings": [...]},
        {"label": str, "unit": str, "readings": [...]},
    ]}

grouped_multi:
    {"metrics": [
        {"label": str, "unit": str, "readings": [...]},
        ...
    ]}

Options (all optional)
----------------------
title           str    chart title (drawn inside axes top-left/right)
title_align     str    "left" | "right" | "center" (default "left")
metric_id       str    metric key for per-metric brand color lookup
truncate_y      bool   non-zero y floor for narrow-range vertical_single (default False)
width_in        float  figure width in inches (default auto-scaled)
height_in       float  figure height in inches (default auto-scaled)
colors          list   hex color strings; auto-selected when omitted
dpi             int    output resolution (default 150)
bar_thickness   float  override bar width/height geometry
show_unit_note  bool   show x-label / unit annotation (default True)
show_date_labels bool  show date tick labels (default True)
show_legend     bool   show series legend (default True)
stagger_xlabels bool   alternate x-label heights for grouped_multi (auto when n>4)
xtick_rotation  int    x-tick label rotation for grouped_multi (default 0)
"""

import io
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as mticker
from matplotlib.transforms import blended_transform_factory as _blended_tf
import numpy as np

from chart_style import INSIGHT_STYLE as _S

# ── Bundled fonts ─────────────────────────────────────────────────────────────
_FONTS_DIR  = os.path.join(os.path.dirname(__file__), "fonts")
_F_BUBBLE   = os.path.join(_FONTS_DIR, "Bubblegum_Sans",   "BubblegumSans-Regular.ttf")
_F_ROBOTO   = os.path.join(_FONTS_DIR, "Roboto", "static", "Roboto-Regular.ttf")
_F_ROBOTO_B = os.path.join(_FONTS_DIR, "Roboto", "static", "Roboto-Bold.ttf")
_F_ROBOTO_C = os.path.join(_FONTS_DIR, "Roboto_Condensed", "static", "RobotoCondensed-Regular.ttf")

# ── Output format ─────────────────────────────────────────────────────────────
_OUTPUT_FMT = "png"   # "png" | "svg" — toggled by render_bar_svg()

# ── Container widths ──────────────────────────────────────────────────────────
# Every chart is an inline SVG stretched to its CSS container's pixel width
# (width:100%). Font/bar sizes are fixed absolute values, so the *rendered*
# size depends entirely on (container_px / native_svg_width_in) — that ratio
# must be identical for every chart sharing a container, or identical fonts
# come out visibly different sizes. horizontal_single/vertical_single/
# stacked_pair all land in the same bucket-2 3-column grid cell — one fixed
# width, never data-dependent. grouped_multi (Body Measurements) is the only
# occupant of the full-width bucket-1 row — its own single fixed width.
# Ratio derivation (box-sizing:border-box, .section max-width:920px, padding
# 24px each side -> 872px content width):
#   bucket-2 cell: (872 - 2*16 gap) / 3 cols = 280px; minus .chart-visuals
#   (74px + 8px padding) = 198px chart-cell. Ratio = 198 / 3.0in = 66 px/in.
#   bucket-1 container is CSS-capped at 576px (.bucket1 .chart-cell
#   max-width, preserving the original visual footprint rather than filling
#   the full ~790px row) -> width_in = 576 / 66 px/in = 8.73in, same ratio
#   as bucket-2 so font/bar scale still matches.
_BUCKET2_WIDTH_IN = 3.0
_BUCKET1_WIDTH_IN = 8.73

# grouped_multi (Body Measurements) reserves x-axis space for at least this
# many metric slots, regardless of how many a given client actually has —
# otherwise a client with fewer recorded measurements gets wider bars than
# one with the full set, purely because there's less data (same bug as the
# width_in issue, one level down: matplotlib auto-scales the x-axis to
# whatever data is present, so slot width = width_in / n_metrics). Reserving
# a fixed reference slot count keeps bar width constant across clients;
# only clients with MORE metrics than this compress further, same as before.
_GROUPED_MULTI_REF_SLOTS = 9

# Font sizes come from INSIGHT_STYLE (chart_style.py) which mirrors design_tokens.css.
# No per-chart font_scale multiplier — one size set, applied everywhere.
def _fp_text(size):  return fm.FontProperties(fname=_F_BUBBLE,   size=size)
def _fp_num(size, bold=False):
    return fm.FontProperties(fname=_F_ROBOTO_B if bold else _F_ROBOTO, size=size)
def _fp_axis(size):  return fm.FontProperties(fname=_F_ROBOTO_C, size=size)

# ── Style constants (from INSIGHT_STYLE) ─────────────────────────────────────
_PALETTE      = _S["palette"]
_DATE_PALETTE = _S["date_palette"]
_METRIC_COLOR = _S["metric_color"]
_MAGENTA      = _S["title_color"]
_GRID         = _S["grid_color"]
_GRID_A       = _S["grid_alpha"]
_GRID_LW      = _S["grid_linewidth"]
_MUTED        = _S["muted_color"]
_TEXT         = _S["text_color"]
_TEXT_DARK    = _S["axis_label_color"]
_SPINE_C      = _S["spine_color"]
_TICK_C       = _S["tick_color"]
_NO_DATA_BG   = _S["no_data_bg"]
_GREY_BG      = _NO_DATA_BG

# Typography
_TITLE_SIZE   = _S["title_size"]
_AX_SIZE      = _S["axis_label_size"]
_TICK_SIZE    = _S["tick_size"]
_V_SIZE       = _S["value_size"]
_LEG_SIZE     = _S["legend_size"]
_UNIT_SIZE    = _S["unit_note_size"]

# Bar geometry
_H_BAR_H      = _S["h_bar_height"]
_V_BAR_W      = _S["v_bar_width"]
_V_BAR_W_GRP  = _S["v_bar_width_grouped"]

# Tick geometry
_TICK_LEN     = _S["major_tick_len"]
_TICK_W       = _S["major_tick_width"]

_PINK_LIGHT   = _PALETTE[1]   # legacy alias (stacked_pair second series default)

# stacked_pair color lookup: options["metric_id"] (the first series' metric) -> (color1_key, color2_key)
_STACKED_PAIR_COLOR_KEYS = {
    "bp_systol": ("bp_systol", "bp_diastol"),
    "fat_pct":   ("fat_pct", "muscle_pct"),
}


# ── Color helpers ─────────────────────────────────────────────────────────────

def _luminance(hex_color):
    r, g, b = (int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b

def _label_color(bg_hex):
    """White on dark backgrounds, near-black on light."""
    return "white" if _luminance(bg_hex) < 0.5 else _TEXT

def _fmt_value(value):
    """Natural precision: integer when no meaningful fraction, else 1 dp."""
    if value == round(value, 0):
        return f"{int(round(value))}"
    return f"{value:.1f}"


# ── Public API ────────────────────────────────────────────────────────────────

def render_bar(data, mode, options=None):
    """Render a bar chart and return PNG bytes. See module docstring for shapes."""
    options = options or {}
    return _render_bar_inner(data, mode, options)


def render_bar_svg(data, mode, options=None):
    """Render a bar chart and return an SVG string. Same data shapes as render_bar()."""
    global _OUTPUT_FMT
    options = options or {}
    _OUTPUT_FMT = "svg"
    try:
        return _render_bar_inner(data, mode, options)
    finally:
        _OUTPUT_FMT = "png"


def draw_bar_into(ax, data, mode, options=None):
    """
    Draw a bar chart directly onto an existing matplotlib axes — vector path
    used by the PDF composer (F05-S05).

    Returns the resolved mode actually drawn ("scorecard" when grouped_multi
    collapses to a single value), so the caller knows whether a title was drawn.
    """
    options = options or {}
    return _draw_bar_into_inner(ax, data, mode, options)


# ── Internal dispatch ─────────────────────────────────────────────────────────

def _render_bar_inner(data, mode, options):
    if not data:
        return _no_data(options)
    if mode in ("horizontal_single", "vertical_single"):
        if not data.get("readings"):
            return _no_data(options)
        return _single(data, mode, options)
    if mode == "stacked_pair":
        series = data.get("series", [])
        if len(series) < 2:
            raise ValueError("stacked_pair requires exactly 2 series")
        if all(not s.get("readings") for s in series):
            return _no_data(options)
        return _stacked_pair(data, options)
    if mode == "grouped_multi":
        metrics = data.get("metrics", [])
        if not metrics or not any(m.get("readings") for m in metrics):
            return _no_data(options)
        if _is_scorecard(data):
            return _scorecard(data, options)
        return _grouped_multi(data, options)
    if mode == "circular_gauge":
        if not data.get("readings"):
            return _no_data(options)
        return _circular_gauge(data, options)
    raise ValueError(f"Unknown mode: {mode!r}")


def _draw_bar_into_inner(ax, data, mode, options):
    if not data:
        _draw_no_data(ax, options)
        return "no_data"
    if mode in ("horizontal_single", "vertical_single"):
        if not data.get("readings"):
            _draw_no_data(ax, options)
            return "no_data"
        _draw_single(ax, data, mode, options)
        return mode
    if mode == "stacked_pair":
        series = data.get("series", [])
        if len(series) < 2:
            raise ValueError("stacked_pair requires exactly 2 series")
        if all(not s.get("readings") for s in series):
            _draw_no_data(ax, options)
            return "no_data"
        _draw_stacked_pair(ax, data, options)
        return "stacked_pair"
    if mode == "grouped_multi":
        metrics = data.get("metrics", [])
        if not metrics or not any(m.get("readings") for m in metrics):
            _draw_no_data(ax, options)
            return "no_data"
        if _is_scorecard(data):
            _draw_scorecard(ax, data, options)
            return "scorecard"
        _draw_grouped_multi(ax, data, options)
        return "grouped_multi"
    raise ValueError(f"Unknown mode: {mode!r}")


def _is_scorecard(data):
    populated = [m for m in data.get("metrics", []) if m.get("readings")]
    return len(populated) == 1 and len(populated[0]["readings"]) == 1


# ── Figure helpers ────────────────────────────────────────────────────────────

def _make_fig(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    return fig, ax

def _to_png(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def _to_svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def _to_output(fig, dpi=150):
    return _to_svg(fig) if _OUTPUT_FMT == "svg" else _to_png(fig, dpi)

def _no_data(options):
    w = options.get("width_in", 5)
    h = options.get("height_in", 3)
    fig, ax = _make_fig(w, h)
    _draw_no_data(ax, options)
    return _to_output(fig, options.get("dpi", 150))

def _draw_no_data(ax, options):
    ax.set_facecolor(_GREY_BG)
    ax.text(0.5, 0.5, "No data", ha="center", va="center",
            fontproperties=_fp_text(13), color=_MUTED, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    title = options.get("title", "")
    if title:
        ax.text(0.5, 0.97, title, ha="center", va="top",
                transform=ax.transAxes, clip_on=False,
                fontproperties=_fp_text(_TITLE_SIZE), color=_MAGENTA, zorder=5)


# ── _draw_single  (horizontal_single + vertical_single) ───────────────────────

def _single(data, mode, options):
    readings = data.get("readings", [])
    n = len(readings)
    if mode == "horizontal_single":
        h = options.get("height_in", max(1.5, n * 0.60))
        w = options.get("width_in", _BUCKET2_WIDTH_IN)
    else:
        w = options.get("width_in", _BUCKET2_WIDTH_IN)
        h = options.get("height_in", 3.5)
    fig, ax = _make_fig(w, h)
    _draw_single(ax, data, mode, options)
    fig.tight_layout(pad=0.8)
    return _to_output(fig, options.get("dpi", 150))


def _draw_single(ax, data, mode, options):
    """
    Draw a horizontal or vertical single-metric bar chart onto an existing axes.

    Key visual properties (from INSIGHT_STYLE):
      horizontal  — sleek bar (h=0.28), value inside bar (auto-contrast white/dark),
                    date labels on y-axis only, x-axis label with unit, bottom spine only.
      vertical    — slim bar (w=0.45), value above bar, horizontal grid lines,
                    left+bottom spines.

    Title is drawn INSIDE the axes (top-left corner) so it's always visible
    regardless of cell positioning on the page figure.
    """
    readings  = data.get("readings", [])
    dates     = [r["date"] for r in readings]
    values    = [float(r["value"]) for r in readings]
    label     = data.get("label", "")
    unit      = data.get("unit", "")
    n         = len(readings)
    title     = options.get("title", "")
    metric_id = options.get("metric_id", "")
    color     = (options.get("colors") or [_METRIC_COLOR.get(metric_id, _PALETTE[0])])[0]
    vmax      = max(values) if values else 1.0
    fmt_dates = [_fmt_date_label(d) for d in dates]

    ax.set_facecolor("white")

    if mode == "horizontal_single":
        bar_h    = options.get("bar_thickness", _H_BAR_H)
        y_pos    = list(range(n))
        bars     = ax.barh(y_pos, values, height=bar_h,
                           color=color, zorder=3, linewidth=0)
        xlim_max = vmax * 1.20   # 20% breathing room; images are now in separate column
        ax.set_xlim(0, xlim_max)
        bottom_margin = 0.60   # clear gap so the lowest bar doesn't sit flush against the axis corner
        top_margin = 1.00      # room for title + unit note above the highest bar (bar_thickness can be tall, e.g. 0.65)
        ax.set_ylim(-bottom_margin, n - 1 + top_margin)

        lc = _label_color(color)
        for bar, val in zip(bars, values):
            if bar.get_width() > xlim_max * 0.12:
                # value inside bar, right-aligned
                ax.text(bar.get_width() - xlim_max * 0.015,
                        bar.get_y() + bar.get_height() / 2,
                        _fmt_value(val), va="center", ha="right",
                        fontproperties=_fp_num(_V_SIZE, bold=True),
                        color=lc, zorder=4)
            else:
                # short bar: value just right of bar end
                ax.text(bar.get_width() + xlim_max * 0.02,
                        bar.get_y() + bar.get_height() / 2,
                        _fmt_value(val), va="center", ha="left",
                        fontproperties=_fp_num(_V_SIZE, bold=True),
                        color=_TEXT, zorder=4)

        # Y-axis: date labels only
        # compact_dates=True wraps "Jun 2026" → "Jun\n2026" to save horizontal space
        # in narrow cells (matching the sample report two-line date format).
        if options.get("compact_dates", False):
            fmt_dates = [d.replace(" ", "\n") for d in fmt_dates]
        ax.set_yticks(y_pos)
        if options.get("show_date_labels", True):
            ax.set_yticklabels(fmt_dates)
            for lbl in ax.get_yticklabels():
                lbl.set_fontproperties(_fp_axis(_TICK_SIZE))
        else:
            ax.set_yticklabels([])
        ax.tick_params(axis="y", length=0, labelcolor=_TEXT)

        # X-axis: major ticks, no grid
        ax.xaxis.set_major_locator(mticker.MaxNLocator(5, integer=False))
        ax.tick_params(axis="x", length=_TICK_LEN, width=_TICK_W,
                       color=_TICK_C, labelcolor=_TICK_C)
        for lbl in ax.get_xticklabels():
            lbl.set_fontproperties(_fp_axis(_TICK_SIZE))
        ax.xaxis.grid(False)
        ax.yaxis.grid(False)

        # Unit: always top-right, inside the chart — one universal rule,
        # not dependent on legend presence or column width.
        if options.get("show_unit_note", True) and unit:
            ax.text(0.98, 0.99, f"In: {unit}",
                    ha="right", va="top", transform=ax.transAxes,
                    fontproperties=_fp_text(_UNIT_SIZE), color=_MUTED)

        # Spines: left + bottom (Y-axis line was missing — matches vertical_single)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(_SPINE_C)
        ax.spines["bottom"].set_color(_SPINE_C)

    else:  # vertical_single
        thickness = options.get("bar_thickness", _V_BAR_W)
        x_pos     = list(range(n))
        bars      = ax.bar(x_pos, values, width=thickness,
                           color=color, zorder=3, linewidth=0)

        if options.get("truncate_y") and n > 1:
            spread = max(values) - min(values)
            margin = max(spread * 0.4, vmax * 0.02)
            ax.set_ylim(min(values) - margin, vmax + margin * 2.0)
        elif options.get("truncate_y") and n == 1:
            ax.set_ylim(values[0] * 0.96, values[0] * 1.06)
        else:
            ax.set_ylim(0, vmax * 1.22)

        ax.set_xticks(x_pos)
        if options.get("show_date_labels", True):
            _rot = 30 if n > 3 else 0
            ax.set_xticklabels(fmt_dates, rotation=_rot,
                               ha="right" if _rot else "center")
        else:
            ax.set_xticklabels([])
        ax.tick_params(axis="x", length=0, labelcolor=_TEXT)
        for lbl in ax.get_xticklabels():
            lbl.set_fontproperties(_fp_axis(_TICK_SIZE))

        # Value labels above each bar
        yspan = ax.get_ylim()[1] - ax.get_ylim()[0]
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + yspan * 0.015,
                    _fmt_value(val), ha="center", va="bottom",
                    fontproperties=_fp_num(_V_SIZE, bold=True),
                    color=_TEXT, zorder=4)

        # Horizontal grid lines, left+bottom spines
        ax.yaxis.grid(True, color=_GRID, linewidth=_GRID_LW, alpha=_GRID_A, zorder=0)
        ax.xaxis.grid(False)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=_TICK_LEN, width=_TICK_W,
                       color=_TICK_C, labelcolor=_TICK_C)
        for lbl in ax.get_yticklabels():
            lbl.set_fontproperties(_fp_axis(_TICK_SIZE))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(_SPINE_C)
        ax.spines["bottom"].set_color(_SPINE_C)

    # Title: inside axes, top-left — always visible regardless of cell position
    if title:
        ax.text(0.02, 0.97, title, ha="left", va="top",
                transform=ax.transAxes, clip_on=False,
                fontproperties=_fp_text(_TITLE_SIZE), color=_MAGENTA, zorder=5)


# ── _draw_stacked_pair ────────────────────────────────────────────────────────

def _stacked_pair(data, options):
    s1, s2   = data["series"][0], data["series"][1]
    all_dates = sorted({r["date"] for s in [s1, s2] for r in s.get("readings", [])})
    n = len(all_dates)
    w = options.get("width_in", _BUCKET2_WIDTH_IN)
    h = options.get("height_in", 3.5)
    fig, ax = _make_fig(w, h)
    _draw_stacked_pair(ax, data, options)
    # Legend is above axes: leave room at top
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    return _to_output(fig, options.get("dpi", 150))


def _draw_stacked_pair(ax, data, options):
    """
    Two stacked series, each segment labeled with its value.
    Colors: metric-specific (bp_systol/bp_diastol), overridable via options["colors"].
    Title drawn inside axes top-left.
    Legend above axes (suppressible via show_legend=False).
    """
    s1, s2  = data["series"][0], data["series"][1]
    # Default colors: keyed off metric_id so each stacked-pair chart type gets
    # its own pair, not always bp_systol/bp_diastol.
    key1, key2 = _STACKED_PAIR_COLOR_KEYS.get(options.get("metric_id"), ("bp_systol", "bp_diastol"))
    default_c1 = _METRIC_COLOR.get(key1, _PALETTE[3])
    default_c2 = _METRIC_COLOR.get(key2, _PALETTE[4])
    colors  = options.get("colors") or [default_c1, default_c2]
    c1, c2  = colors[0], colors[1]

    s1_unit  = s1.get("unit", "")
    s2_unit  = s2.get("unit", "")
    same_u   = bool(s1_unit) and s1_unit == s2_unit

    def _lbl(s, unit):
        base = s.get("label", "")
        return f"{base} ({unit})" if (unit and not same_u) else base

    all_dates = sorted({r["date"] for s in [s1, s2] for r in s.get("readings", [])})
    n         = len(all_dates)

    def _by_date(s):
        return {r["date"]: float(r["value"]) for r in s.get("readings", [])}

    v1    = _by_date(s1)
    v2    = _by_date(s2)
    vals1 = [v1.get(d, 0.0) for d in all_dates]
    vals2 = [v2.get(d, 0.0) for d in all_dates]

    x     = np.arange(n)
    width = options.get("bar_thickness", _V_BAR_W)

    bars1 = ax.bar(x, vals1, width, color=c1, label=_lbl(s1, s1_unit), zorder=3, linewidth=0)
    bars2 = ax.bar(x, vals2, width, bottom=vals1, color=c2, label=_lbl(s2, s2_unit), zorder=3, linewidth=0)

    lc1, lc2 = _label_color(c1), _label_color(c2)

    for bar, val in zip(bars1, vals1):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, val / 2,
                    _fmt_value(val), ha="center", va="center",
                    fontproperties=_fp_num(_V_SIZE, bold=True), color=lc1, zorder=4)

    for bar, base, val in zip(bars2, vals1, vals2):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, base + val / 2,
                    _fmt_value(val), ha="center", va="center",
                    fontproperties=_fp_num(_V_SIZE, bold=True), color=lc2, zorder=4)

    ax.set_xticks(x)
    _rot = 30 if n > 3 else 0
    if options.get("show_date_labels", True):
        ax.set_xticklabels([_fmt_date_label(d) for d in all_dates],
                           rotation=_rot, ha="right" if _rot else "center")
    else:
        ax.set_xticklabels([])
    ax.tick_params(axis="x", length=0, labelcolor=_TEXT)
    for lbl in ax.get_xticklabels():
        lbl.set_fontproperties(_fp_axis(_TICK_SIZE))

    ax.yaxis.grid(True, color=_GRID, linewidth=_GRID_LW, alpha=_GRID_A, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=_TICK_LEN, width=_TICK_W, color=_TICK_C, labelcolor=_TICK_C)
    for lbl in ax.get_yticklabels():
        lbl.set_fontproperties(_fp_axis(_TICK_SIZE))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_SPINE_C)
    ax.spines["bottom"].set_color(_SPINE_C)

    # Legend above axes, left-anchored
    if options.get("show_legend", True):
        ax.legend(prop=_fp_text(_LEG_SIZE), frameon=False,
                  loc="lower left", ncol=2,
                  bbox_to_anchor=(0.0, 1.02), bbox_transform=ax.transAxes,
                  borderaxespad=0)

    # Unit note when both series share a unit — placed just inside the axes
    # top-right corner (vertically below the above-axes legend row), not
    # sharing the legend's row: a 2-column legend can span most of this
    # chart's fixed width, leaving no horizontal room for same-row text.
    unit_note = options.get("unit_note", "")
    if not unit_note and same_u and s1_unit:
        unit_note = f"In: {s1_unit}"
    if unit_note and options.get("show_unit_note", True):
        ax.text(0.98, 0.99, unit_note, ha="right", va="top",
                transform=ax.transAxes,
                fontproperties=_fp_text(_UNIT_SIZE), color=_MUTED)

    # Title: inside axes, top-left
    title = options.get("title", "")
    if title:
        ax.text(0.02, 0.97, title, ha="left", va="top",
                transform=ax.transAxes, clip_on=False,
                fontproperties=_fp_text(_TITLE_SIZE), color=_MAGENTA, zorder=5)


# ── _draw_grouped_multi ───────────────────────────────────────────────────────

def _grouped_multi(data, options):
    populated = [m for m in data.get("metrics", []) if m.get("readings")]
    n_metrics = len(populated)
    n_dates   = len({r["date"] for m in populated for r in m["readings"]})
    w = options.get("width_in", _BUCKET1_WIDTH_IN)
    h = options.get("height_in", 4.0)
    fig, ax   = _make_fig(w, h)
    _draw_grouped_multi(ax, data, {**options, "width_in": w})
    # Legend row sits above axes (bbox_to_anchor 1.02); leave 8% headroom.
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    return _to_output(fig, options.get("dpi", 150))


def _draw_grouped_multi(ax, data, options):
    """
    Clustered bars: X = metric labels, colors = date series.

    Visual spec from INSIGHT_STYLE:
      - Bar width = v_bar_width_grouped (per-date narrower)
      - Title: drawn inside axes, top-right (title_align="right") by default for BM
      - Legend: above axes, left-aligned, date labels
      - X-labels: staggered (alternate heights) when n_metrics > 4
      - Values: shown on/above each bar; font scales with bar pixel width
      - Horizontal grid lines; left+bottom spines.
    """
    populated = [m for m in data.get("metrics", []) if m.get("readings")]
    all_dates = sorted({r["date"] for m in populated for r in m["readings"]})
    n_metrics = len(populated)
    n_dates   = len(all_dates)
    colors    = options.get("colors") or [
        _DATE_PALETTE[i % len(_DATE_PALETTE)] for i in range(n_dates)
    ]
    dpi   = options.get("dpi", 150)
    w     = options.get("width_in", _BUCKET1_WIDTH_IN)

    # Bar width: fill ~80% of each 1-unit slot, narrower with more dates
    bar_w = min(_V_BAR_W_GRP, 0.80 / n_dates) * options.get("bar_width_scale", 1.0)

    x       = np.arange(n_metrics)
    offsets = np.linspace(-(n_dates - 1) * bar_w / 2,
                           (n_dates - 1) * bar_w / 2, n_dates)

    # Reserve space for a fixed reference slot count so bar width doesn't
    # depend on how many metrics this particular client has (see
    # _GROUPED_MULTI_REF_SLOTS above).
    ref_slots = max(n_metrics, _GROUPED_MULTI_REF_SLOTS)
    ax.set_xlim(-0.5, ref_slots - 0.5)

    # Draw bars
    for i, d in enumerate(all_dates):
        bar_pos = x + offsets[i]
        vals = [
            {r["date"]: float(r["value"]) for r in m["readings"]}.get(d, 0.0)
            for m in populated
        ]
        ax.bar(bar_pos, vals, bar_w, color=colors[i],
               label=_fmt_date_label(d), zorder=3, linewidth=0)

    # 15% headroom above tallest bar
    ax.set_ylim(0, ax.get_ylim()[1] * 1.15)
    yspan = ax.get_ylim()[1]

    # Value labels: use global value-label size from INSIGHT_STYLE (no per-chart override)
    all_bars_pos = [x + offsets[i] for i in range(n_dates)]
    all_vals     = [
        [{r["date"]: float(r["value"]) for r in m["readings"]}.get(d, 0.0)
         for m in populated]
        for d in all_dates
    ]
    for bar_pos, vals in zip(all_bars_pos, all_vals):
        for pos, val in zip(bar_pos, vals):
            if val > 0:
                ax.text(pos, val + yspan * 0.008, _fmt_value(val),
                        ha="center", va="bottom",
                        fontproperties=_fp_num(_V_SIZE, bold=True), color=_TEXT, zorder=4)

    # X-axis: metric labels — staggered when many metrics
    _units  = [m.get("unit", "") for m in populated]
    _unique = {u for u in _units if u}
    _mixed  = len(_unique) > 1
    metric_labels = [
        (f"{m.get('label', f'M{i+1}')} ({m['unit']})" if (_mixed and m.get("unit"))
         else m.get("label", f"M{i+1}"))
        for i, m in enumerate(populated)
    ]
    ax.set_xticks(x)
    stagger = options.get("stagger_xlabels", n_metrics > 4)
    _xrot   = options.get("xtick_rotation", 0)

    if stagger:
        ax.set_xticklabels([])   # clear, draw manually
        trans = _blended_tf(ax.transData, ax.transAxes)
        for i, (xi, lbl) in enumerate(zip(x, metric_labels)):
            y_frac = -0.03 if i % 2 == 0 else -0.09
            ax.text(xi, y_frac, lbl, ha="center", va="top",
                    transform=trans, clip_on=False,
                    fontproperties=_fp_text(_TICK_SIZE), color=_MAGENTA)
    else:
        ax.set_xticklabels(metric_labels, rotation=_xrot,
                           ha="right" if _xrot else "center")
        for lbl in ax.get_xticklabels():
            lbl.set_fontproperties(_fp_text(_TICK_SIZE))
            lbl.set_color(_MAGENTA)

    ax.tick_params(axis="x", length=0, labelcolor=_MAGENTA)

    # Grid and spines
    ax.yaxis.grid(True, color=_GRID, linewidth=_GRID_LW, alpha=_GRID_A, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=_TICK_LEN, width=_TICK_W, color=_TICK_C, labelcolor=_TICK_C)
    for lbl in ax.get_yticklabels():
        lbl.set_fontproperties(_fp_axis(_TICK_SIZE))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_SPINE_C)
    ax.spines["bottom"].set_color(_SPINE_C)

    # Legend: above axes, left-aligned (date-series swatches)
    if options.get("show_legend", True):
        ax.legend(prop=_fp_text(_LEG_SIZE), frameon=False,
                  loc="lower left", ncol=n_dates,
                  bbox_to_anchor=(0.0, 1.02), bbox_transform=ax.transAxes,
                  borderaxespad=0)

    # Unit note: top-right above axes when all metrics share a unit
    unit_note = options.get("unit_note", "")
    if not unit_note and not _mixed and _unique:
        unit_note = f"In: {next(iter(_unique))}"
    if unit_note and options.get("show_unit_note", True):
        ax.text(1.0, 1.02, unit_note, ha="right", va="bottom",
                transform=ax.transAxes,
                fontproperties=_fp_text(_UNIT_SIZE), color=_MUTED)

    # Title: inside axes — top-right for Body Measurements (title_align="right"),
    # top-left for other grouped charts.
    title = options.get("title", "")
    title_align = options.get("title_align", "right")
    ha_map = {"right": ("right", 0.98), "left": ("left", 0.02), "center": ("center", 0.50)}
    ha, tx = ha_map.get(title_align, ("right", 0.98))
    if title:
        ax.text(tx, 0.97, title, ha=ha, va="top",
                transform=ax.transAxes, clip_on=False,
                fontproperties=_fp_text(_TITLE_SIZE), color=_MAGENTA, zorder=5)


# ── Scorecard ─────────────────────────────────────────────────────────────────

def _scorecard(data, options):
    w = options.get("width_in", 3.5)
    h = options.get("height_in", 2.5)
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    _draw_scorecard(ax, data, options)
    fig.tight_layout()
    return _to_output(fig, options.get("dpi", 150))


def _draw_scorecard(ax, data, options):
    populated = [m for m in data.get("metrics", []) if m.get("readings")]
    m       = populated[0]
    reading = m["readings"][0]
    value   = reading["value"]
    unit    = m.get("unit", "")
    date    = reading["date"]

    ax.set_facecolor(_GREY_BG)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    y_num = 0.63 if unit else 0.58
    ax.text(0.5, y_num, _fmt_value(value), ha="center", va="center",
            fontproperties=_fp_num(28, bold=True), color=_MAGENTA,
            transform=ax.transAxes)
    if unit:
        ax.text(0.5, 0.47, unit, ha="center", va="center",
                fontproperties=_fp_text(11), color=_MUTED, transform=ax.transAxes)
    ax.text(0.5, 0.09, _fmt_date_label(date), ha="center", va="center",
            fontproperties=_fp_axis(8), color=_MUTED, transform=ax.transAxes)

    if options.get("title"):
        ax.text(0.5, 0.97, options["title"], ha="center", va="top",
                transform=ax.transAxes, clip_on=False,
                fontproperties=_fp_text(10), color=_MAGENTA, zorder=5)


# ── Circular gauge / date-series donut (Pulse) ───────────────────────────────

def _circular_gauge(data, options):
    """Donut — one equal-sized wedge per assessment date (n=1 collapses to a
    full solid circle), colored via the shared date palette, each wedge
    labeled with its own value. Matches the per-date pie shown in the
    multi-year reference samples — this is NOT a proportional-fill gauge
    against an invented range (that was the old, unverified design)."""
    readings = sorted(data.get("readings", []), key=lambda r: r["date"])
    unit     = data.get("unit", "")
    title    = options.get("title", "")
    n        = len(readings)

    colors = options.get("colors") or [_DATE_PALETTE[i % len(_DATE_PALETTE)] for i in range(n)]

    # Square figure at the same width as every other bucket-2 chart
    # (_BUCKET2_WIDTH_IN) — was hardcoded to 4.0in, a different native size
    # than the rest of bucket-2, which is exactly what caused its font/legend
    # to scale differently (too small) once stretched into the same column.
    fig, ax = plt.subplots(figsize=(_BUCKET2_WIDTH_IN, _BUCKET2_WIDTH_IN))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_aspect("equal")

    wedges, _ = ax.pie(
        [1] * n,
        colors=colors,
        wedgeprops={"width": 0.35, "edgecolor": "white", "linewidth": 1.5},
        startangle=90,
        counterclock=False,
    )

    ring_mid = 1 - 0.35 / 2
    for wedge, r, c in zip(wedges, readings, colors):
        if n == 1:
            # solid circle — big number centered in the hole, not on the ring band
            x, y, label_color, size = 0, 0, _TEXT, 20
        else:
            ang = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
            x, y = ring_mid * np.cos(ang), ring_mid * np.sin(ang)
            label_color, size = _label_color(c), _V_SIZE
        ax.text(x, y, _fmt_value(float(r["value"])),
                ha="center", va="center",
                fontproperties=_fp_num(size, bold=True),
                color=label_color)

    if title:
        ax.text(0, -1.3, title,
                ha="center", va="top",
                fontproperties=_fp_text(_TITLE_SIZE),
                color=_MAGENTA)

    if unit and options.get("show_unit_note", True):
        ax.text(0.98, 1.15, f"In: {unit}",
                ha="right", va="top",
                fontproperties=_fp_text(_UNIT_SIZE), color=_MUTED)

    if options.get("show_legend", True):
        handles = [plt.Line2D([0], [0], marker="o", linestyle="", color=c, markersize=8)
                   for c in colors]
        labels  = [_fmt_date_label(r["date"]) for r in readings]
        ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.05, 0.5),
                  frameon=False, prop=_fp_text(_LEG_SIZE))

    ax.set_xlim(-1.3, 1.9)
    ax.set_ylim(-1.6, 1.3)
    ax.axis("off")

    return _to_output(fig, options.get("dpi", 150))


# ── Date formatting ───────────────────────────────────────────────────────────

def _fmt_date_label(date_str):
    """Format YYYY-MM-DD as 'Mon YYYY' (e.g. 'Jun 2025')."""
    try:
        from datetime import datetime
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y")
    except (ValueError, TypeError):
        return date_str
