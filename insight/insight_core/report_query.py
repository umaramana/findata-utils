"""
F05-S01_S02 — Report query engine (pure functions, no Sheets API).

The GAS Code.gs generateReportPayload() mirrors this logic exactly.
S4.1 (full PDF) calls build_report_payload() after fetching readings
via the Sheets API — the API layer is the caller's responsibility.
"""

from datetime import date as _date


def build_report_payload(client_id, date_from, date_to, component_ids,
                         all_readings, client_profile=None):
    """
    Build a structured report payload from a flat list of reading dicts.

    Parameters
    ----------
    client_id      : str
    date_from      : str  YYYY-MM-DD
    date_to        : str  YYYY-MM-DD
    component_ids  : list[str]  selected components
    all_readings   : list[dict]  every reading row for this client (all history):
                       {client_id, date, component, metric, value}
    client_profile : dict | None
                       {"gender": "male"|"female", "dob": "YYYY-MM-DD"}
                     Required only when body_vitals is selected (for BMR).

    Returns
    -------
    dict  on success:
        {
          client_id, date_from, date_to,
          components: {
            component_id: {
              metrics: {
                metric_id: { readings: [{date, value}], baseline }
              },
              derived: { bmi: [...], bmr: [...], waist_hip_ratio: [...] }
            }
          }
        }
    dict  on empty/invalid: { error: str }
    """
    if not component_ids:
        return {"error": "No components selected."}

    component_set = set(component_ids)
    baseline_dates = {}   # metric_id -> earliest date across all client history
    in_range = {}         # component_id -> metric_id -> [{date, value}]
    for cid in component_ids:
        in_range[cid] = {}

    for row in all_readings:
        if row["client_id"] != client_id:
            continue
        metric = row["metric"]
        d      = row["date"]
        value  = row["value"]

        # Baseline: track MIN date across ALL history for this client+metric
        if metric not in baseline_dates or d < baseline_dates[metric]:
            baseline_dates[metric] = d

        # In-range readings: selected components + inside date window only
        comp = row["component"]
        if comp not in component_set:
            continue
        if d < date_from or d > date_to:
            continue

        in_range.setdefault(comp, {}).setdefault(metric, []).append({"date": d, "value": value})

    components_payload = {}
    for cid in component_ids:
        metrics_payload = {}
        for metric, readings in (in_range.get(cid) or {}).items():
            metrics_payload[metric] = {
                "readings": sorted(readings, key=lambda r: r["date"]),
                "baseline": baseline_dates.get(metric),
            }
        components_payload[cid] = {
            "metrics": metrics_payload,
            "derived": _compute_derived(cid, in_range.get(cid) or {}, client_profile),
        }

    has_readings = any(bool(components_payload[cid]["metrics"]) for cid in component_ids)
    if not has_readings:
        return {"error": "No readings found for the selected client, components, and date range."}

    return {
        "client_id":  client_id,
        "date_from":  date_from,
        "date_to":    date_to,
        "components": components_payload,
    }


def _compute_derived(component_id, metrics_by_id, client_profile=None):
    """
    Compute per-date derived metrics for a component's readings.

    body_vitals       → bmi  (weight_kg + height_cm, same date)
                      → bmr  (weight_kg + height_cm + age + gender, same date)
                             Mifflin-St Jeor: male   = 10w + 6.25h - 5a + 5
                                              female = 10w + 6.25h - 5a - 161
    body_measurements → waist_hip_ratio (waist + hips, same date)
    """
    derived = {}

    if component_id == "body_vitals":
        weight_by_date = {r["date"]: r["value"] for r in metrics_by_id.get("weight_kg", [])}
        height_by_date = {r["date"]: r["value"] for r in metrics_by_id.get("height_cm", [])}

        bmi_readings = []
        bmr_readings = []

        gender_offset = None
        age_at = None
        if client_profile:
            g = (client_profile.get("gender") or "").lower()
            if g in ("male", "female"):
                gender_offset = 5 if g == "male" else -161
            dob_str = client_profile.get("dob")
            if dob_str:
                try:
                    dob = _date.fromisoformat(dob_str)
                    # age_at: callable returning age in years on a given date string
                    def age_at(date_str, _dob=dob):
                        d = _date.fromisoformat(date_str)
                        return (d - _dob).days // 365
                except ValueError:
                    pass

        for d, w in weight_by_date.items():
            h = height_by_date.get(d)
            if not h or h <= 0:
                continue

            h_m = h / 100
            bmi_readings.append({"date": d, "value": round(w / (h_m * h_m), 1)})

            if gender_offset is not None and age_at is not None:
                a = age_at(d)
                bmr = 10 * w + 6.25 * h - 5 * a + gender_offset
                bmr_readings.append({"date": d, "value": round(bmr)})

        if bmi_readings:
            derived["bmi"] = sorted(bmi_readings, key=lambda r: r["date"])
        if bmr_readings:
            derived["bmr"] = sorted(bmr_readings, key=lambda r: r["date"])

    elif component_id == "body_measurements":
        waist_by_date = {r["date"]: r["value"] for r in metrics_by_id.get("waist", [])}
        hips_by_date  = {r["date"]: r["value"] for r in metrics_by_id.get("hips",  [])}
        whr_readings = []
        for d, waist in waist_by_date.items():
            hips = hips_by_date.get(d)
            if hips and hips > 0:
                whr_readings.append({"date": d, "value": round(waist / hips, 3)})
        if whr_readings:
            derived["waist_hip_ratio"] = sorted(whr_readings, key=lambda r: r["date"])

    return derived


# Reference max for body-measurement bar fills, inches — matches the design
# handoff's prototype formula (README: "pct... computed as value/referenceMax*100,
# e.g. waist/45in"). Same convention reused here rather than invented.
_MEASUREMENT_REF_MAX_IN = 45

# F06-S02 — Nudge is single-select across all 7 Report Config components, no
# longer hardcoded to Body Vitals. For each non-body_measurements component,
# "headline" is the metric used for the big delta stat + first stat box;
# "boxes" are up to 2 more metrics shown as latest-value-only stat boxes
# (mirrors body_vitals' existing weight/fat/muscle box layout). Every metric
# here shares one unit (reps, seconds, km/cm) so a single delta format works.
# body_measurements is handled separately below — it keeps its existing
# bar-list rendering instead of stat boxes.
NUDGE_METRIC_CONFIG = {
    # body_vitals boxes is a priority-ordered candidate pool, not a fixed pair —
    # fat_pct/muscle_pct come from Check-In, bp/bpm/height_cm are Full-Assessment-only.
    # The fill loop below takes the first 2 candidates that actually have data for
    # the selected date, so a Check-In-only history still gets 2 boxes and a
    # Full-Assessment one isn't stuck showing blank fat/muscle boxes.
    "body_vitals":     {"headline": "weight_kg",           "boxes": ["fat_pct", "muscle_pct", "bp", "bpm", "height_cm"]},
    "physio_1":        {"headline": "pushups",              "boxes": ["squats", "crunches"]},
    "physio_2":        {"headline": "plank",                "boxes": ["right_side_plank", "left_side_plank"]},
    "physio_3":        {"headline": "cooper_test",          "boxes": ["flexibility", "coordination"]},
    "balance_open":    {"headline": "balance_normal_open",  "boxes": ["balance_tandem_right_open", "balance_tandem_left_open"]},
    "balance_closed":  {"headline": "balance_normal_closed","boxes": ["balance_tandem_right_closed", "balance_tandem_left_closed"]},
    "strength":        {"headline": "bench_press_weight",  "boxes": ["squat_weight", "deadlift_weight"]},
}

# metric_id -> (kicker label for stat box, unit suffix, friendly name for error text)
NUDGE_METRIC_LABELS = {
    "weight_kg":                  ("WEIGHT",       "kg",   "weight"),
    "fat_pct":                    ("BODY FAT",     "%",    "body fat"),
    "muscle_pct":                 ("MUSCLE",       "%",    "muscle"),
    "bp":                         ("BLOOD PRESSURE","mmHg","blood pressure"),
    "bpm":                        ("HEART RATE",   "bpm",  "heart rate"),
    "height_cm":                  ("HEIGHT",       "cm",   "height"),
    "pushups":                    ("PUSHUPS",      "reps", "pushups"),
    "squats":                     ("SQUATS",       "reps", "squats"),
    "crunches":                   ("CRUNCHES",     "reps", "crunches"),
    "plank":                      ("PLANK",        "sec",  "plank"),
    "right_side_plank":           ("R SIDE PLANK", "sec",  "right side plank"),
    "left_side_plank":            ("L SIDE PLANK", "sec",  "left side plank"),
    "cooper_test":                ("COOPER TEST",  "km",   "cooper test"),
    "flexibility":                ("FLEXIBILITY",  "cm",   "flexibility"),
    "coordination":               ("COORDINATION", "cm",   "coordination"),
    "balance_normal_open":        ("NORMAL STANCE","sec",  "balance (normal stance, eyes open)"),
    "balance_tandem_right_open":  ("TANDEM R",     "sec",  "balance (tandem right, eyes open)"),
    "balance_tandem_left_open":   ("TANDEM L",     "sec",  "balance (tandem left, eyes open)"),
    "balance_normal_closed":      ("NORMAL STANCE","sec",  "balance (normal stance, eyes closed)"),
    "balance_tandem_right_closed":("TANDEM R",     "sec",  "balance (tandem right, eyes closed)"),
    "balance_tandem_left_closed": ("TANDEM L",     "sec",  "balance (tandem left, eyes closed)"),
    "bench_press_weight":         ("BENCH PRESS",  "lbs",  "bench press weight"),
    "squat_weight":               ("SQUAT",        "lbs",  "squat weight"),
    "deadlift_weight":            ("DEADLIFT",     "lbs",  "deadlift weight"),
}


def _latest_on_or_before(readings, date_to):
    """readings: [{date, value}] (any order) -> sorted-by-date list with date <= date_to."""
    in_range = [r for r in readings if r["date"] <= date_to]
    return sorted(in_range, key=lambda r: r["date"])


def _headline(latest_value, previous_value, unit):
    """Returns (caption, value) for the Nudge card's big headline stat.

    First check-in has no delta to show — rather than blow up the sentence
    "First check-in" to the same 34px slot a delta number occupies, show the
    actual reading there instead (consistent size/shape every time) and move
    "First check-in" to the small caption above it.
    """
    if previous_value is None:
        return "First check-in", f"{latest_value:g} {unit}"
    delta = round(latest_value - previous_value, 1)
    arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
    return "Since last check-in", f"{arrow} {abs(delta):.1f} {unit}"


def build_nudge_payload(client_id, date_to, all_readings, component_id="body_vitals", client_profile=None):
    """
    Build the flat data shape the Nudge PNG (WhatsApp card) needs, from the
    same raw all_readings history build_report_payload() uses.

    F06-S02: single-select across all 7 Report Config components (not
    hardcoded to Body Vitals) — component_id picks which one drives the card.
    NUDGE_METRIC_CONFIG maps each component to a headline metric (drives the
    big delta stat) + up to 2 secondary metrics (stat boxes). body_measurements
    is the one exception — it keeps its existing bar-list rendering.

    "Since last check-in" delta needs the reading *before* the latest one,
    which may fall outside any selected date range — so this reads from
    all_readings (full client history), not build_report_payload()'s
    in-range-only output.

    Returns
    -------
    dict  on success:
        { componentId, headlineCaption, headlineValue,
          statBoxes: [{label, unit, value}],
          measurementBars: [{label, value, pct}] }   # non-empty only for body_measurements
    dict  on no headline-metric history at/before date_to: { error: str }
    """
    by_metric = {}
    for row in all_readings:
        if row["client_id"] != client_id:
            continue
        by_metric.setdefault(row["metric"], []).append({"date": row["date"], "value": row["value"]})

    def _latest_value(metric_id):
        series = _latest_on_or_before(by_metric.get(metric_id, []), date_to)
        return series[-1]["value"] if series else None

    if component_id == "body_measurements":
        waist = _latest_value("waist")
        if waist is None:
            return {"error": "No waist readings found for this client on or before the selected date."}
        waist_series = _latest_on_or_before(by_metric.get("waist", []), date_to)
        previous = waist_series[-2]["value"] if len(waist_series) >= 2 else None
        headline_caption, headline_value = _headline(waist, previous, "in")

        measurement_bars = []
        for metric_id, label, unit in (("waist", "Waist", '"'), ("hips", "Hips", '"')):
            v = _latest_value(metric_id)
            if v is None:
                continue
            pct = min(100, round(v / _MEASUREMENT_REF_MAX_IN * 100))
            measurement_bars.append({"label": label, "value": f"{v:g}{unit}", "pct": pct})

        return {
            "componentId":     component_id,
            "headlineCaption": headline_caption,
            "headlineValue":   headline_value,
            "statBoxes":       [],
            "measurementBars": measurement_bars,
        }

    cfg = NUDGE_METRIC_CONFIG[component_id]
    headline_id = cfg["headline"]
    headline_label, headline_unit, headline_name = NUDGE_METRIC_LABELS[headline_id]

    headline_series = _latest_on_or_before(by_metric.get(headline_id, []), date_to)
    if not headline_series:
        return {"error": f"No {headline_name} readings found for this client on or before the selected date."}

    latest = headline_series[-1]["value"]
    previous = headline_series[-2]["value"] if len(headline_series) >= 2 else None
    headline_caption, headline_value = _headline(latest, previous, headline_unit)

    stat_boxes = [{"label": headline_label, "unit": headline_unit, "value": latest}]
    for metric_id in cfg["boxes"]:
        if len(stat_boxes) >= 3:
            break
        label, unit, _name = NUDGE_METRIC_LABELS[metric_id]
        if metric_id == "bp":
            sys_v = _latest_value("bp_systol")
            dia_v = _latest_value("bp_diastol")
            if sys_v is None or dia_v is None:
                continue
            stat_boxes.append({"label": label, "unit": unit, "value": f"{sys_v:g}/{dia_v:g}"})
            continue
        v = _latest_value(metric_id)
        if v is None:
            continue
        stat_boxes.append({"label": label, "unit": unit, "value": v})

    return {
        "componentId":     component_id,
        "headlineCaption": headline_caption,
        "headlineValue":   headline_value,
        "statBoxes":       stat_boxes[:3],
        "measurementBars": [],
    }
