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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]

# Insight brand colours — magenta palette
_MAGENTA     = "#880e4f"   # darkest magenta: primary bars, chart titles, first series
_PINK_LIGHT  = "#f06292"   # light pink: second series, stacked-pair top
_PALETTE     = [           # cycling palette for grouped_multi
    "#880e4f",  # darkest magenta  (series 1)
    "#ad1457",  # deep magenta     (series 2)
    "#c2185b",  # medium magenta   (series 3)
    "#f06292",  # light pink       (series 4)
    "#ce93d8",  # lavender         (series 5)
    "#e1bee7",  # pale lavender    (series 6)
    "#880e4f",  # cycle back to start (series 7+)
    "#ad1457",
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


def _style(ax, title="", teal_title=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_GRID)
    ax.spines["bottom"].set_color(_GRID)
    ax.yaxis.grid(True, color=_GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9, colors=_TEXT, length=0)
    if title:
        title_color = _MAGENTA if teal_title else _TEXT
        ax.set_title(title, fontsize=11, fontweight="bold",
                     color=title_color, pad=10)


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
            fontsize=13, color=_MUTED, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    title = options.get("title", "")
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold",
                     color=_MAGENTA, pad=10)
    return _to_png(fig, options.get("dpi", 150))


def _single(data, mode, options):
    readings = data.get("readings", [])
    dates    = [r["date"] for r in readings]
    values   = [float(r["value"]) for r in readings]
    label    = data.get("label", "")
    unit     = data.get("unit", "")
    axis_lbl = f"{label} ({unit})" if unit else label
    color    = (options.get("colors") or [_MAGENTA])[0]
    title    = options.get("title", label)
    dpi      = options.get("dpi", 150)
    vmax     = max(values) if values else 1

    n = len(readings)
    if mode == "horizontal_single":
        # Height scales so bars don't become paper-thin with many readings
        h = options.get("height_in", max(2.5, n * 0.55))
        w = options.get("width_in", 5.5)
        fig, ax = _make_fig(w, h)
        bars = ax.barh(dates, values, color=color, height=0.55, zorder=3)
        ax.set_xlabel(axis_lbl, fontsize=9, color=_TEXT)
        ax.set_xlim(0, vmax * 1.20)
        ax.xaxis.grid(False)
        ax.yaxis.grid(False)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + vmax * 0.015,
                bar.get_y() + bar.get_height() / 2,
                f"{val:g}", va="center", ha="left", fontsize=8.5, color=_TEXT,
            )
    else:  # vertical_single
        w = options.get("width_in", max(4.0, n * 1.0))
        h = options.get("height_in", 3.5)
        fig, ax = _make_fig(w, h)
        bars = ax.bar(dates, values, color=color, width=0.55, zorder=3)
        ax.set_ylabel(axis_lbl, fontsize=9, color=_TEXT)
        if options.get("truncate_y") and len(values) > 1:
            spread = max(values) - min(values)
            margin = max(spread * 0.4, vmax * 0.02)
            ax.set_ylim(min(values) - margin, vmax + margin * 1.5)
        elif options.get("truncate_y") and len(values) == 1:
            ax.set_ylim(values[0] * 0.96, values[0] * 1.06)
        plt.xticks(rotation=30 if n > 3 else 0, ha="right")
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.015,
                f"{val:g}", ha="center", va="bottom", fontsize=8.5, color=_TEXT,
            )

    _style(ax, title)
    fig.tight_layout()
    return _to_png(fig, dpi)


def _stacked_pair(data, options):
    """
    Two series stacked per date. Both segment values labeled individually.
    Adaptive text color: white on dark segments, dark on light segments.
    """
    s1, s2   = data["series"][0], data["series"][1]
    colors   = options.get("colors") or [_MAGENTA, _PINK_LIGHT]
    c1, c2   = colors[0], colors[1]
    dpi      = options.get("dpi", 150)

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
                   label=s1.get("label", "Series 1"), zorder=3)
    bars2 = ax.bar(x, vals2, width, bottom=vals1, color=c2,
                   label=s2.get("label", "Series 2"), zorder=3)

    lc1 = _label_color(c1)
    lc2 = _label_color(c2)

    for bar, val in zip(bars1, vals1):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    val / 2,
                    f"{val:g}", ha="center", va="center",
                    fontsize=8.5, color=lc1, fontweight="bold", zorder=4)

    for bar, base, val in zip(bars2, vals1, vals2):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    base + val / 2,
                    f"{val:g}", ha="center", va="center",
                    fontsize=8.5, color=lc2, fontweight="bold", zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels(all_dates, rotation=30 if n > 3 else 0, ha="right")
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    _style(ax, options.get("title", ""))
    fig.tight_layout()
    return _to_png(fig, dpi)


def _grouped_multi(data, options):
    """
    Clustered bars: one group per date, one bar per metric.
    Value labels shown only when total bars ≤ 14 (avoids label soup at small size).
    Figure width auto-scales by n_metrics × n_dates so bars never cram.
    """
    populated  = [m for m in data.get("metrics", []) if m.get("readings")]
    all_dates  = sorted({r["date"] for m in populated for r in m["readings"]})
    n_dates    = len(all_dates)
    n_metrics  = len(populated)
    total_bars = n_dates * n_metrics
    colors     = options.get("colors") or [_PALETTE[i % len(_PALETTE)] for i in range(n_metrics)]
    dpi        = options.get("dpi", 150)

    w = options.get("width_in", max(5.5, n_metrics * n_dates * 0.55))
    h = options.get("height_in", 3.8)
    fig, ax = _make_fig(w, h)

    x       = np.arange(n_dates)
    width   = min(0.8 / n_metrics, 0.3)
    offsets = np.linspace(
        -(n_metrics - 1) * width / 2,
         (n_metrics - 1) * width / 2,
        n_metrics,
    )

    for i, m in enumerate(populated):
        by_date = {r["date"]: float(r["value"]) for r in m["readings"]}
        vals    = [by_date.get(d, 0.0) for d in all_dates]
        bar_pos = x + offsets[i]
        ax.bar(bar_pos, vals, width, color=colors[i],
               label=m.get("label", f"M{i + 1}"), zorder=3)

        if total_bars <= 14:
            vmax = max(vals) if vals else 1
            yrange = ax.get_ylim()[1] - ax.get_ylim()[0]
            for pos, val in zip(bar_pos, vals):
                if val > 0:
                    ax.text(pos, val + max(vmax * 0.01, yrange * 0.01),
                            f"{val:g}", ha="center", va="bottom",
                            fontsize=7.5, color=_TEXT, zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels(all_dates, rotation=30 if n_dates > 3 else 0, ha="right")
    ax.legend(fontsize=7.5, frameon=False, ncol=min(n_metrics, 5),
              loc="upper right")
    _style(ax, options.get("title", ""))
    fig.tight_layout()
    return _to_png(fig, dpi)


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

    display_val = f"{value:g}" + (f" {unit}" if unit else "")
    ax.text(0.5, 0.58, display_val, ha="center", va="center",
            fontsize=28, fontweight="bold", color=_MAGENTA, transform=ax.transAxes)
    ax.text(0.5, 0.30, label, ha="center", va="center",
            fontsize=10, color=_MUTED, transform=ax.transAxes)
    ax.text(0.5, 0.10, date, ha="center", va="center",
            fontsize=8, color=_MUTED, transform=ax.transAxes)

    if options.get("title"):
        ax.set_title(options["title"], fontsize=10, fontweight="bold",
                     color=_MAGENTA, pad=6)

    fig.tight_layout()
    return _to_png(fig, dpi)
