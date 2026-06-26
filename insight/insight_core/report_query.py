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
