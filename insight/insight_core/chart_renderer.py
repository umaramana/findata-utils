"""
F04-S02/S03/S04 — Bar chart family renderer.
render_bar(data, mode, options) -> PNG bytes via matplotlib (server-side).
Consumed by layout engine (F05-S04) and PDF builder (F05-S05).

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
title       str    chart title
truncate_y  bool   non-zero y floor for narrow-range vertical_single (default False)
width_in    float  figure width in inches (default auto-scaled)
height_in   float  figure height in inches (default auto-scaled)
colors      list   hex color strings; auto-generated when omitted
dpi         int    output resolution (default 150)
"""

import io
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# ── Bundled fonts ─────────────────────────────────────────────────────────────
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_F_BUBBLE     = os.path.join(_FONTS_DIR, "Bubblegum_Sans",   "BubblegumSans-Regular.ttf")
_F_ROBOTO     = os.path.join(_FONTS_DIR, "Roboto", "static", "Roboto-Regular.ttf")
_F_ROBOTO_B   = os.path.join(_FONTS_DIR, "Roboto", "static", "Roboto-Bold.ttf")
_F_ROBOTO_C   = os.path.join(_FONTS_DIR, "Roboto_Condensed", "static", "RobotoCondensed-Regular.ttf")


def _fp_text(size):
    """Bubblegum Sans — titles, labels, legend, metric names."""
    return fm.FontProperties(fname=_F_BUBBLE, size=size)


def _fp_num(size, bold=False):
    """Roboto — numeric values annotated on bars and scorecards."""
    return fm.FontProperties(fname=_F_ROBOTO_B if bold else _F_ROBOTO, size=size)


def _fp_axis(size):
    """Roboto Condensed — axis tick labels (dates, numeric ticks)."""
    return fm.FontProperties(fname=_F_ROBOTO_C, size=size)

# Insight brand colours — magenta palette
_MAGENTA     = "#880e4f"   # darkest magenta: primary bars, chart titles, first series
_PINK_LIGHT  = "#f48fb1"   # light pink: second series, stacked-pair top
_PALETTE     = [           # cycling palette for grouped_multi (per-metric single-date)
    "#880e4f",  # darkest magenta  (series 1)
    "#ad1457",  # deep magenta     (series 2)
    "#c2185b",  # medium magenta   (series 3)
    "#f06292",  # light pink       (series 4)
    "#ce93d8",  # lavender         (series 5)
    "#e1bee7",  # pale lavender    (series 6)
    "#880e4f",  # cycle back
    "#ad1457",
]
# Date series palette for grouped_multi — alternates dark/light for contrast
_DATE_PALETTE = [
    "#880e4f",  # date 1 — darkest magenta
    "#f48fb1",  # date 2 — light pink (high contrast with date 1)
    "#ad1457",  # date 3 — deep magenta
    "#f06292",  # date 4 — medium pink
    "#ce93d8",  # date 5 — lavender
    "#4a148c",  # date 6 — deep purple
    "#f8bbd0",  # date 7 — very light pink
    "#880e4f",  # cycle back
]
_GRID        = "#E5E7EB"   # light horizontal gridlines
_GREY_BG     = "#f5f7f8"
_TEXT        = "#1a1a1a"
_MUTED       = "#6b7280"


def _luminance(hex_color):
    r, g, b = (int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


def _label_color(bg_hex):
    """White text on dark backgrounds, dark text on light backgrounds."""
    return "white" if _luminance(bg_hex) < 0.5 else _TEXT


# ── Public API ────────────────────────────────────────────────────────────────

def render_bar(data, mode, options=None):
    """Render a bar chart and return PNG bytes. See module docstring for shapes."""
    options = options or {}

    if not data:
        return _no_data(options)

    if mode in ("horizontal_single", "vertical_single"):
        readings = data.get("readings", [])
        if not readings:
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

    raise ValueError(f"Unknown mode: {mode!r}")


def _is_scorecard(data):
    """True when grouped_multi has exactly 1 metric with exactly 1 reading."""
    populated = [m for m in data.get("metrics", []) if m.get("readings")]
    return len(populated) == 1 and len(populated[0]["readings"]) == 1


# ── Internal helpers ──────────────────────────────────────────────────────────

def _make_fig(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    return fig, ax


def _style(ax, title="", title_align="center"):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_GRID)
    ax.spines["bottom"].set_color(_GRID)
    ax.yaxis.grid(True, color=_GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(labelcolor=_MAGENTA, length=0)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontproperties(_fp_axis(9))
    if title:
        ax.set_title(title, fontproperties=_fp_text(11), color=_MAGENTA,
                     pad=10, loc=title_align)


def _to_png(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _no_data(options):
    w = options.get("width_in", 5)
    h = options.get("height_in", 3)
    fig, ax = _make_fig(w, h)
    ax.set_facecolor(_GREY_BG)
    ax.text(0.5, 0.5, "No data", ha="center", va="center",
            fontproperties=_fp_text(13), color=_MUTED, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    title = options.get("title", "")
    title_align = options.get("title_align", "center")
    if title:
        ax.set_title(title, fontproperties=_fp_text(11), color=_MAGENTA,
                     pad=10, loc=title_align)
    return _to_png(fig, options.get("dpi", 150))


def _single(data, mode, options):
    readings  = data.get("readings", [])
    dates     = [r["date"] for r in readings]
    values    = [float(r["value"]) for r in readings]
    label     = data.get("label", "")
    unit      = data.get("unit", "")
    color     = (options.get("colors") or [_MAGENTA])[0]
    title     = options.get("title", label)
    unit_note = f"Measurement units: {unit}" if unit else ""
    dpi       = options.get("dpi", 150)
    vmax     = max(values) if values else 1

    n = len(readings)
    fmt_dates = [_fmt_date_label(d) for d in dates]
    if mode == "horizontal_single":
        # Height scales so bars don't become paper-thin with many readings
        h = options.get("height_in", max(2.5, n * 0.55))
        w = options.get("width_in", 5.5)
        fig, ax = _make_fig(w, h)
        bars = ax.barh(fmt_dates, values, color=color, height=0.55, zorder=3)
        ax.set_xlim(0, vmax * 1.20)
        ax.xaxis.grid(False)
        ax.yaxis.grid(False)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + vmax * 0.015,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}", va="center", ha="left",
                fontproperties=_fp_num(8.5), color=_TEXT,
            )
    else:  # vertical_single
        w = options.get("width_in", max(4.0, n * 1.0))
        h = options.get("height_in", 3.5)
        fig, ax = _make_fig(w, h)
        bars = ax.bar(fmt_dates, values, color=color, width=0.55, zorder=3)
        if options.get("truncate_y") and len(values) > 1:
            spread = max(values) - min(values)
            margin = max(spread * 0.4, vmax * 0.02)
            ax.set_ylim(min(values) - margin, vmax + margin * 1.5)
        elif options.get("truncate_y") and len(values) == 1:
            ax.set_ylim(values[0] * 0.96, values[0] * 1.06)
        _rot = 30 if n > 3 else 0
        plt.xticks(rotation=_rot, ha="right" if _rot else "center")
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.015,
                f"{val:.1f}", ha="center", va="bottom",
                fontproperties=_fp_num(8.5), color=_TEXT,
            )

    if unit_note:
        ax.text(1.0, 1.02, unit_note, ha="right", va="bottom",
                transform=ax.transAxes,
                fontproperties=_fp_text(7), color=_MUTED)
    _style(ax, title, options.get("title_align", "center"))
    fig.tight_layout()
    return _to_png(fig, dpi)


def _stacked_pair(data, options):
    """
    Two series stacked per date. Both segment values labeled individually.
    Adaptive text color: white on dark segments, dark on light segments.
    Units: same unit → y-axis label; different units → appended to legend labels.
    Legend + unit note above axes (matching grouped_multi layout).
    """
    s1, s2   = data["series"][0], data["series"][1]
    colors   = options.get("colors") or [_MAGENTA, _PINK_LIGHT]
    c1, c2   = colors[0], colors[1]
    dpi      = options.get("dpi", 150)
    title    = options.get("title", "")
    title_align = options.get("title_align", "center")

    s1_unit   = s1.get("unit", "")
    s2_unit   = s2.get("unit", "")
    same_unit = bool(s1_unit) and s1_unit == s2_unit

    # Legend labels: include unit only when the two series have different units
    def _lbl(s, unit):
        base = s.get("label", "")
        return f"{base} ({unit})" if (unit and not same_unit) else base

    all_dates = sorted({r["date"] for s in [s1, s2] for r in s.get("readings", [])})
    n         = len(all_dates)

    def _by_date(s):
        return {r["date"]: float(r["value"]) for r in s.get("readings", [])}

    v1    = _by_date(s1)
    v2    = _by_date(s2)
    vals1 = [v1.get(d, 0.0) for d in all_dates]
    vals2 = [v2.get(d, 0.0) for d in all_dates]

    x     = np.arange(n)
    width = 0.55
    w = options.get("width_in", max(4.0, n * 1.2))
    h = options.get("height_in", 3.5)
    fig, ax = _make_fig(w, h)

    bars1 = ax.bar(x, vals1, width, color=c1,
                   label=_lbl(s1, s1_unit), zorder=3)
    bars2 = ax.bar(x, vals2, width, bottom=vals1, color=c2,
                   label=_lbl(s2, s2_unit), zorder=3)

    lc1 = _label_color(c1)
    lc2 = _label_color(c2)

    for bar, val in zip(bars1, vals1):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    val / 2,
                    f"{val:.1f}", ha="center", va="center",
                    fontproperties=_fp_num(8.5, bold=True), color=lc1, zorder=4)

    for bar, base, val in zip(bars2, vals1, vals2):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    base + val / 2,
                    f"{val:.1f}", ha="center", va="center",
                    fontproperties=_fp_num(8.5, bold=True), color=lc2, zorder=4)

    ax.set_xticks(x)
    _rot = 30 if n > 3 else 0
    ax.set_xticklabels([_fmt_date_label(d) for d in all_dates],
                       rotation=_rot, ha="right" if _rot else "center")

    # Legend above axes (matches grouped_multi positioning)
    ax.legend(prop=_fp_text(8), frameon=False,
              loc="lower left", ncol=2,
              bbox_to_anchor=(0.0, 1.02),
              bbox_transform=ax.transAxes,
              borderaxespad=0)

    # Unit note: explicit option takes precedence; auto-derive when same unit
    unit_note = options.get("unit_note", "")
    if not unit_note and same_unit and s1_unit:
        unit_note = f"Measurement units: {s1_unit}"
    if unit_note:
        ax.text(1.0, 1.02, unit_note,
                ha="right", va="bottom", transform=ax.transAxes,
                fontproperties=_fp_text(7), color=_MUTED)

    _style(ax)   # spine/grid/tick styling only; title handled below
    if title:
        _TA = {"center": (0.5, "center"), "left": (0.02, "left"), "right": (0.98, "right")}
        _x, _ha = _TA.get(title_align, (0.5, "center"))
        fig.suptitle(title, fontproperties=_fp_text(11), color=_MAGENTA, x=_x, ha=_ha)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _to_png(fig, dpi)


def _grouped_multi(data, options):
    """
    Clustered bars matching Looker Studio body measurements layout:
      X axis  = metric labels  (one group per metric)
      Colors  = date series    (one bar per date, per group)
      Legend  = date labels    (top of chart, "Mon YYYY" format)

    Value labels shown on every bar (font scales down with bar count).
    Unit annotation supported via options["unit_note"].
    """
    populated  = [m for m in data.get("metrics", []) if m.get("readings")]
    all_dates  = sorted({r["date"] for m in populated for r in m["readings"]})
    n_metrics  = len(populated)
    n_dates    = len(all_dates)
    colors  = options.get("colors") or [
        _DATE_PALETTE[i % len(_DATE_PALETTE)] for i in range(n_dates)
    ]
    dpi     = options.get("dpi", 150)

    # Bar fills 80% of each 1-unit metric slot; narrower with more dates
    bar_w = min(0.65, 0.80 / n_dates)

    # Width scales with bars but caps at 8" — matches Looker page width
    auto_w = min(8.0, max(5.5, n_metrics * n_dates * 0.20 + 2.0))
    w = options.get("width_in", auto_w)
    h = options.get("height_in", 4.2)
    fig, ax = _make_fig(w, h)

    x       = np.arange(n_metrics)
    offsets = np.linspace(
        -(n_dates - 1) * bar_w / 2,
         (n_dates - 1) * bar_w / 2,
        n_dates,
    )

    # Pass 1: draw all bars, collect positions for labels
    all_bars = []
    for i, d in enumerate(all_dates):
        bar_pos = x + offsets[i]
        vals = [
            {r["date"]: float(r["value"]) for r in m["readings"]}.get(d, 0.0)
            for m in populated
        ]
        ax.bar(bar_pos, vals, bar_w, color=colors[i],
               label=_fmt_date_label(d), zorder=3)
        all_bars.append((bar_pos, vals))

    # Pass 2: add 15% headroom above tallest bar, then draw labels
    ax.set_ylim(0, ax.get_ylim()[1] * 1.15)
    yspan  = ax.get_ylim()[1]                 # bottom is 0, so span == top
    # Approximate each bar's rendered pixel width and step font down to prevent overlap.
    # bar_w is in axes units; n_metrics axes units fill w inches at dpi px/in.
    bar_px = bar_w / n_metrics * w * dpi
    val_fs = 7.5 if bar_px >= 50 else 6.0 if bar_px >= 30 else 5.0
    for bar_pos, vals in all_bars:
        for pos, val in zip(bar_pos, vals):
            if val > 0:
                ax.text(pos, val + yspan * 0.008,
                        f"{val:.1f}", ha="center", va="bottom",
                        fontproperties=_fp_num(val_fs), color=_TEXT, zorder=4)

    # Unit display: if all metrics share one unit → unit_note; if mixed → per-label suffix
    _units  = [m.get("unit", "") for m in populated]
    _unique = {u for u in _units if u}
    _mixed  = len(_unique) > 1

    metric_labels = [
        (f"{m.get('label', f'M{i+1}')} ({m['unit']})" if (_mixed and m.get("unit"))
         else m.get("label", f"M{i+1}"))
        for i, m in enumerate(populated)
    ]
    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.set_ylabel("")
    ax.tick_params(axis="x", length=0)

    # Tick fonts: Roboto Condensed for y-axis numbers; Bubblegum Sans for
    # x-axis metric names (text, not numbers).
    _style(ax)   # no title here — title goes via suptitle below
    for lbl in ax.get_xticklabels():
        lbl.set_fontproperties(_fp_text(8.5))
        lbl.set_color(_MAGENTA)

    # Header layout (top → bottom):
    #   suptitle  ← fig.suptitle(), sits at the very top of the figure
    #   legend row + unit note  ← just above the axes, below the suptitle
    #   chart area

    # Legend row: bottom edge anchored just above the axes top edge
    ax.legend(prop=_fp_text(8), frameon=False,
              loc="lower left",
              ncol=n_dates,
              bbox_to_anchor=(0.0, 1.02),
              bbox_transform=ax.transAxes,
              borderaxespad=0)

    unit_note = options.get("unit_note", "")
    if not unit_note and not _mixed and _unique:
        unit_note = f"Measurement units: {next(iter(_unique))}"
    if unit_note:
        ax.text(1.0, 1.02, unit_note,
                ha="right", va="bottom", transform=ax.transAxes,
                fontproperties=_fp_text(7), color=_MUTED)

    title = options.get("title", "")
    title_align = options.get("title_align", "center")
    if title:
        _TA = {"center": (0.5, "center"), "left": (0.02, "left"), "right": (0.98, "right")}
        _x, _ha = _TA.get(title_align, (0.5, "center"))
        fig.suptitle(title, fontproperties=_fp_text(11), color=_MAGENTA, x=_x, ha=_ha)

    # rect leaves the top band for suptitle + the out-of-axes legend row.
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _to_png(fig, dpi)


def _fmt_date_label(date_str):
    """Format YYYY-MM-DD as 'Mon YYYY' for chart legends (e.g. 'Jun 2025')."""
    try:
        from datetime import datetime
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %Y")
    except (ValueError, TypeError):
        return date_str


def _scorecard(data, options):
    """
    Large-value display for a single-date, single-metric reading.
    Returns PNG bytes like every other mode.
    """
    populated = [m for m in data.get("metrics", []) if m.get("readings")]
    m       = populated[0]
    reading = m["readings"][0]
    value   = reading["value"]
    label   = m.get("label", "")
    unit    = m.get("unit", "")
    date    = reading["date"]
    dpi     = options.get("dpi", 150)

    w = options.get("width_in", 3.5)
    h = options.get("height_in", 2.5)
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor(_GREY_BG)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    # Number and unit rendered separately so each uses its own font standard:
    # number → Roboto Bold (_fp_num), unit → Bubblegum Sans (_fp_text).
    y_num   = 0.63 if unit else 0.58
    y_label = 0.26 if unit else 0.30
    ax.text(0.5, y_num, f"{value:.1f}", ha="center", va="center",
            fontproperties=_fp_num(28, bold=True), color=_MAGENTA, transform=ax.transAxes)
    if unit:
        ax.text(0.5, 0.47, unit, ha="center", va="center",
                fontproperties=_fp_text(11), color=_MUTED, transform=ax.transAxes)
    ax.text(0.5, y_label, label, ha="center", va="center",
            fontproperties=_fp_text(10), color=_MUTED, transform=ax.transAxes)
    ax.text(0.5, 0.09, _fmt_date_label(date), ha="center", va="center",
            fontproperties=_fp_axis(8), color=_MUTED, transform=ax.transAxes)

    if options.get("title"):
        ax.set_title(options["title"], fontproperties=_fp_text(10), color=_MAGENTA, pad=6)

    fig.tight_layout()
    return _to_png(fig, dpi)
