"""
Insight Fitness chart visual style specification — single source of truth
for all visual properties: colors, typography, bar geometry, and axis rules.

chart_renderer.py and table_heatmap.py import INSIGHT_STYLE and set module
constants from it at load time. To change the look globally, edit values here.
Never hard-code visual literals directly in renderer functions.
"""

# ── Magenta-family palette ────────────────────────────────────────────────────
# Ordered for visual relief: alternates dark/light/dark across chart types.
PALETTE = [
    "#880e4f",   # [0] darkest wine       — primary (BW, BM first date)
    "#f8bbd0",   # [1] baby pink/lightest — WHR (high-contrast relief)
    "#ad1457",   # [2] dark magenta       — BMI, BM second date
    "#bf1d6f",   # [3] deep rose          — BP systolic, BM third date
    "#f06292",   # [4] warm pink          — BP diastolic, BM fourth date
    "#ce5a92",   # [5] medium magenta     — Pulse, BM fifth date
    "#f538a0",   # [6] vivid bright pink  — accent / BM sixth date
    "#ab4e5f",   # [7] muted rose         — BM seventh+ date cycle
]

# Explicit per-metric color for single-metric charts (horizontal/vertical_single).
METRIC_COLOR = {
    "weight_kg":       "#880e4f",   # darkest — primary vital
    "waist_hip_ratio": "#f8bbd0",   # lightest — visual relief; dark value text auto-selected
    "bmi":             "#ad1457",   # dark magenta
    "bp_systol":       "#bf1d6f",   # deep rose (top stacked segment)
    "bp_diastol":      "#f06292",   # warm pink (bottom stacked segment)
    "pulse":           "#ce5a92",   # medium magenta
}

# Date-series palette for grouped_multi — used when there are 2+ assessment dates.
# Alternates dark/light for distinct per-date bar groups.
DATE_PALETTE = [
    "#880e4f",   # date 1 — darkest wine
    "#f06292",   # date 2 — warm pink
    "#ad1457",   # date 3 — dark magenta
    "#ce5a92",   # date 4 — medium magenta
    "#bf1d6f",   # date 5 — deep rose
    "#f8bbd0",   # date 6 — baby pink
    "#f538a0",   # date 7 — vivid bright
    "#ab4e5f",   # date 8 — muted rose
]

INSIGHT_STYLE = {
    # ── Colors ───────────────────────────────────────────────────────────────
    "palette":           PALETTE,
    "date_palette":      DATE_PALETTE,
    "metric_color":      METRIC_COLOR,
    "title_color":       "#880e4f",
    "axis_label_color":  "#333333",
    "tick_color":        "#555555",
    "muted_color":       "#6b7280",
    "text_color":        "#1a1a1a",
    "grid_color":        "#EBEBEB",
    "grid_alpha":        0.7,
    "grid_linewidth":    0.5,
    "no_data_bg":        "#f5f7f8",
    "spine_color":       "#CCCCCC",

    # ── Typography (before _FONT_SCALE is applied) ───────────────────────────
    "title_size":        11,     # chart title (Bubblegum Sans, bold treatment)
    "axis_label_size":   7.5,    # x/y axis labels
    "tick_size":         7,      # tick labels (Roboto Condensed)
    "value_size":        9,      # bar value annotations (Roboto Bold)
    "legend_size":       8,      # legend text
    "unit_note_size":    7,      # unit note / annotation text

    # ── Bar geometry ─────────────────────────────────────────────────────────
    "h_bar_height":        0.18,  # horizontal single bar height (fraction of y-slot)
    "v_bar_width":         0.45,  # vertical single bar width (data units)
    "v_bar_width_grouped": 0.55,  # grouped multi (before per-date division)

    # ── Axis / spine rules ───────────────────────────────────────────────────
    "major_tick_len":    3,
    "major_tick_width":  0.8,
    "minor_ticks":       False,
}
