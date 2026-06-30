"""
Smoke test — generates sample PNGs for every renderer and saves to smoke_output/.
Run after each card session to visually verify output before calling it done.

Usage: python smoke_test.py
Output: smoke_output/*.png  (opens the folder automatically on Windows)
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
from chart_renderer import render_bar
from table_heatmap import render_table_heatmap

OUT = os.path.join(os.path.dirname(__file__), "smoke_output")
os.makedirs(OUT, exist_ok=True)


def save(name, data):
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(data)
    print(f"  saved: {name}")


# ── chart_renderer ────────────────────────────────────────────────────────────

print("\n[chart_renderer]")

save("bar_horizontal_single.png", render_bar(
    {"label": "Body Weight", "unit": "kg",
     "readings": [
         {"date": "2026-01-15", "value": 85.0},
         {"date": "2026-02-15", "value": 83.5},
         {"date": "2026-03-15", "value": 82.0},
         {"date": "2026-04-15", "value": 80.8},
     ]},
    "horizontal_single",
    {"title": "Body Weight"},
))

save("bar_vertical_single.png", render_bar(
    {"label": "BMI", "unit": "",
     "readings": [
         {"date": "2026-01-15", "value": 27.3},
         {"date": "2026-02-15", "value": 26.8},
         {"date": "2026-03-15", "value": 26.2},
     ]},
    "vertical_single",
    {"title": "BMI"},
))

save("bar_vertical_truncate_y.png", render_bar(
    {"label": "BMR", "unit": "kcal",
     "readings": [
         {"date": "2026-01-15", "value": 1740},
         {"date": "2026-02-15", "value": 1728},
         {"date": "2026-03-15", "value": 1715},
     ]},
    "vertical_single",
    {"title": "BMR", "truncate_y": True},
))

save("bar_stacked_pair.png", render_bar(
    {"series": [
        {"label": "Fat %",    "unit": "%",
         "readings": [{"date": "2026-01-15", "value": 28}, {"date": "2026-03-15", "value": 26}]},
        {"label": "Muscle %", "unit": "%",
         "readings": [{"date": "2026-01-15", "value": 42}, {"date": "2026-03-15", "value": 44}]},
    ]},
    "stacked_pair",
    {"title": "Body Composition"},
))

# Body measurements — 8 metrics, realistic labels and values from samples

_BODY_METRICS_1DATE = {   # Reshma-style: single assessment
    "metrics": [
        {"label": "a Neck",      "unit": "in", "readings": [{"date": "2023-06-01", "value": 12}]},
        {"label": "b Waist",     "unit": "in", "readings": [{"date": "2023-06-01", "value": 30}]},
        {"label": "c Abdomen",   "unit": "in", "readings": [{"date": "2023-06-01", "value": 31}]},
        {"label": "d Hips",      "unit": "in", "readings": [{"date": "2023-06-01", "value": 38}]},
        {"label": "e Thighs",    "unit": "in", "readings": [{"date": "2023-06-01", "value": 18.9}]},
        {"label": "f Calves",    "unit": "in", "readings": [{"date": "2023-06-01", "value": 17.5}]},
        {"label": "g Arms",      "unit": "in", "readings": [{"date": "2023-06-01", "value": 8.7}]},
        {"label": "h Fore Arms", "unit": "in", "readings": [{"date": "2023-06-01", "value": 9}]},
    ]
}

_BODY_METRICS_2DATES = {  # Dr Uma-style: 2 assessments
    "metrics": [
        {"label": "a Neck",      "unit": "in", "readings": [{"date": "2025-06-01", "value": 14}, {"date": "2026-02-01", "value": 15}]},
        {"label": "b Waist",     "unit": "in", "readings": [{"date": "2025-06-01", "value": 35}, {"date": "2026-02-01", "value": 35}]},
        {"label": "c2 Abdomen",  "unit": "in", "readings": [{"date": "2025-06-01", "value": 37}, {"date": "2026-02-01", "value": 37}]},
        {"label": "d Hips",      "unit": "in", "readings": [{"date": "2025-06-01", "value": 42}, {"date": "2026-02-01", "value": 41}]},
        {"label": "e Thighs",    "unit": "in", "readings": [{"date": "2025-06-01", "value": 21}, {"date": "2026-02-01", "value": 21}]},
        {"label": "f Calves",    "unit": "in", "readings": [{"date": "2025-06-01", "value": 16}, {"date": "2026-02-01", "value": 16}]},
        {"label": "g Arms",      "unit": "in", "readings": [{"date": "2025-06-01", "value": 11}, {"date": "2026-02-01", "value": 10}]},
        {"label": "h Fore Arms", "unit": "in", "readings": [{"date": "2025-06-01", "value": 10}, {"date": "2026-02-01", "value": 10}]},
    ]
}

_BODY_METRICS_5DATES = {  # Dr Praveena-style: 5 assessments across years
    "metrics": [
        {"label": "a Neck",      "unit": "in", "readings": [{"date": "2019-01-01", "value": 12}, {"date": "2020-01-01", "value": 12}, {"date": "2021-01-01", "value": 12}, {"date": "2024-01-01", "value": 12}, {"date": "2026-01-01", "value": 12}]},
        {"label": "b Waist",     "unit": "in", "readings": [{"date": "2019-01-01", "value": 27}, {"date": "2020-01-01", "value": 26}, {"date": "2021-01-01", "value": 27}, {"date": "2024-01-01", "value": 27}, {"date": "2026-01-01", "value": 31}]},
        {"label": "c2 Abdomen",  "unit": "in", "readings": [{"date": "2019-01-01", "value": 31}, {"date": "2020-01-01", "value": 31}, {"date": "2021-01-01", "value": 31}, {"date": "2024-01-01", "value": 32}, {"date": "2026-01-01", "value": 34}]},
        {"label": "d Hips",      "unit": "in", "readings": [{"date": "2019-01-01", "value": 37}, {"date": "2020-01-01", "value": 38}, {"date": "2021-01-01", "value": 38}, {"date": "2024-01-01", "value": 38}, {"date": "2026-01-01", "value": 39}]},
        {"label": "e Thighs",    "unit": "in", "readings": [{"date": "2019-01-01", "value": 17}, {"date": "2020-01-01", "value": 18}, {"date": "2021-01-01", "value": 20}, {"date": "2024-01-01", "value": 19}, {"date": "2026-01-01", "value": 21}]},
        {"label": "f Calves",    "unit": "in", "readings": [{"date": "2019-01-01", "value": 12}, {"date": "2020-01-01", "value": 12}, {"date": "2021-01-01", "value": 12}, {"date": "2024-01-01", "value": 12}, {"date": "2026-01-01", "value": 13}]},
        {"label": "g Arms",      "unit": "in", "readings": [{"date": "2019-01-01", "value": 9},  {"date": "2020-01-01", "value": 10}, {"date": "2021-01-01", "value": 10}, {"date": "2024-01-01", "value": 9},  {"date": "2026-01-01", "value": 10}]},
        {"label": "h Fore Arms", "unit": "in", "readings": [{"date": "2019-01-01", "value": 8},  {"date": "2020-01-01", "value": 8},  {"date": "2021-01-01", "value": 8},  {"date": "2024-01-01", "value": 8},  {"date": "2026-01-01", "value": 8}]},
    ]
}

_OPTS = {"title": "Body Measurements",
         "unit_note": "Measurement units: Inches"}

save("grouped_1date_reshma.png",  render_bar(_BODY_METRICS_1DATE,  "grouped_multi", _OPTS))
save("grouped_2dates_uma.png",    render_bar(_BODY_METRICS_2DATES, "grouped_multi", _OPTS))
save("grouped_5dates_praveena.png", render_bar(_BODY_METRICS_5DATES, "grouped_multi", _OPTS))

save("bar_scorecard.png", render_bar(
    {"metrics": [
        {"label": "Push-ups", "unit": "reps",
         "readings": [{"date": "2026-04-15", "value": 32}]},
    ]},
    "grouped_multi",
    {"title": "Push-ups"},
))

save("bar_no_data.png", render_bar(
    {"label": "Pulse", "unit": "bpm", "readings": []},
    "horizontal_single",
    {"title": "Pulse"},
))

# ── table_heatmap — Reshma report page 3 patterns ─────────────────────────────
# Page 3 shows 4 distinct heatmap types; each smoke PNG exercises one type.

print("\n[table_heatmap]")

# ── Physio 1: Count per Min — integers, one date (Reshma single-assessment) ──
save("heatmap_physio1_single.png", render_table_heatmap(
    {"metrics": [
        {"label": "1. Modified Pushups", "unit": "reps",
         "readings": [{"date": "2023-06-01", "value": 9}]},
        {"label": "2. Squats",           "unit": "reps",
         "readings": [{"date": "2023-06-01", "value": 27}]},
        {"label": "3. Crunches",         "unit": "reps",
         "readings": [{"date": "2023-06-01", "value": 25}]},
    ]},
    {"title": "Physiological Assessment 1", "unit_note": "COUNT PER MIN"},
))

# ── Physio 1: Count per Min — multi-date shows gradient over time ─────────────
save("heatmap_physio1_multi.png", render_table_heatmap(
    {"metrics": [
        {"label": "1. Modified Pushups", "unit": "reps",
         "readings": [{"date": "2021-06-01", "value": 16},
                      {"date": "2022-06-01", "value": 21},
                      {"date": "2023-06-01", "value": 16}]},
        {"label": "2. Squats",           "unit": "reps",
         "readings": [{"date": "2021-06-01", "value": 23},
                      {"date": "2022-06-01", "value": 19},
                      {"date": "2023-06-01", "value": 24}]},
        {"label": "3. Crunches",         "unit": "reps",
         "readings": [{"date": "2021-06-01", "value": 15},
                      {"date": "2022-06-01", "value": 22},
                      {"date": "2023-06-01", "value": 18}]},
    ]},
    {"title": "Physiological Assessment 1 — multi-date", "unit_note": "COUNT PER MIN"},
))

# ── Physio 2: HH:MM:SS — timed holds, one date ────────────────────────────────
save("heatmap_physio2_hms.png", render_table_heatmap(
    {"metrics": [
        {"label": "4. Plank",                  "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 11}]},
        {"label": "5. Modified Right\nSide Plank", "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 33}]},
        {"label": "6. Modified Left\nSide Plank",  "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 26}]},
        {"label": "7. 40* hold",               "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 28}]},
        {"label": "8. Sorenso hold",           "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 14}]},
    ]},
    {"title": "Physiological Assessment 2",
     "unit_note": "IN HH:MM:SS",
     "value_format": "hms"},
))

# ── Partial missing cell — verifies "-" renders (not "No data") ───────────────
save("heatmap_partial_missing.png", render_table_heatmap(
    {"metrics": [
        {"label": "Push-ups",   "unit": "reps",
         "readings": [{"date": "2023-06-01", "value": 20},
                      {"date": "2023-09-01", "value": 24},
                      {"date": "2024-01-01", "value": 27}]},
        {"label": "Sit-ups",    "unit": "reps",
         "readings": [{"date": "2023-06-01", "value": 18},
                      # 2023-09-01 missing → should render "-"
                      {"date": "2024-01-01", "value": 22}]},
        {"label": "Burpees",    "unit": "reps",
         "readings": [{"date": "2023-06-01", "value": 10},
                      {"date": "2023-09-01", "value": 13},
                      {"date": "2024-01-01", "value": 15}]},
    ]},
    {"title": "Partial Missing Cell Test"},
))

# ── Physio 3: separate charts per metric (different units — no shared table) ──
# 12 min Cooper Test rendered alone
save("heatmap_physio3_cooper.png", render_table_heatmap(
    {"metrics": [
        {"label": "12 min Cooper Test", "unit": "km",
         "readings": [{"date": "2023-06-01", "value": 1.28}]},
    ]},
    {"title": "Physiological Assessment 3", "unit_note": "In KMs"},
))

# Flexibility rendered alone (different unit → separate render_table_heatmap call)
save("heatmap_physio3_flex.png", render_table_heatmap(
    {"metrics": [
        {"label": "Flexibility", "unit": "cm",
         "readings": [{"date": "2023-06-01", "value": 28}]},
    ]},
    {"title": "Physiological Assessment 3", "unit_note": "In cms"},
))

# ── Balance Test: HH:MM:SS — wide multi-column, Eyes Open row ────────────────
save("heatmap_balance_hms.png", render_table_heatmap(
    {"metrics": [
        {"label": "Normal",        "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 20}]},
        {"label": "Tandem\nLeft Front", "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 20}]},
        {"label": "Tandem\nRight Front", "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 20}]},
        {"label": "Right Up",     "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 20}]},
        {"label": "Left Up",      "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 7}]},
        {"label": "Stork\nBalance L", "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 20}]},
        {"label": "Stork\nBalance R", "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 20}]},
        {"label": "On Toes L",    "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 2}]},
        {"label": "On Toes R",    "unit": "s",
         "readings": [{"date": "2023-06-01", "value": 6}]},
    ]},
    {"title": "Balance Test — Eyes Open",
     "unit_note": "IN HH:MM:SS",
     "value_format": "hms"},
))

# ── No-data fallback ──────────────────────────────────────────────────────────
save("heatmap_no_data.png", render_table_heatmap(
    {"metrics": []},
    {"title": "No-data fallback"},
))

print(f"\nAll PNGs saved to: {OUT}")
subprocess.Popen(f'explorer "{OUT}"')
