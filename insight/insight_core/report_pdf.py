"""
F05-S05 — Full PDF report generator (HTML/CSS → Puppeteer).
generate_full_report(...) → {"path": str, "version": int, "pages": int} | {"error": str}

Pipeline:
  1. F05-S02 query engine → structured data payload
  2. chart_renderer.render_bar_svg()  → SVG strings  (bar chart family)
     table_heatmap.render_table_html() → HTML strings (physio/balance heatmaps)
  3. layout_engine.layout_report()   → bucket partition + CSS grid params
  4. Jinja2 render report_template.html → full HTML document
  5. Node render_report.js (Puppeteer) → single-flow PDF at content height
"""

import os
import base64
import logging
import subprocess
import tempfile

from jinja2 import Environment, FileSystemLoader

from report_query    import build_report_payload
from chart_renderer  import render_bar_svg
from table_heatmap   import render_table_html
from layout_engine   import layout_report
from gender_image    import get_metric_visuals

log = logging.getLogger(__name__)

_HERE          = os.path.dirname(__file__)
_ASSETS_DIR    = os.path.join(_HERE, "assets")
_TEMPLATES_DIR = os.path.join(_HERE, "templates")
_FONTS_DIR     = os.path.join(_HERE, "fonts")
_RENDER_JS     = os.path.join(_HERE, "render_report.js")


def _file_uri(path):
    """Convert an absolute OS path to a file:// URI usable in HTML/CSS."""
    return "file:///" + path.replace("\\", "/")


def _font_uri(rel):
    """Return a file:// URI for a bundled font (relative to _FONTS_DIR)."""
    p = os.path.join(_FONTS_DIR, *rel.split("/"))
    return _file_uri(p) if os.path.exists(p) else None


def _local_asset_library():
    """Hardcoded asset→base64-data-URI mappings derived from assets/ for the pilot.
    base64 avoids Chromium's cross-origin file:// blocking in Puppeteer."""
    def _b64(rel):
        p = os.path.join(_ASSETS_DIR, *rel.replace("/", os.sep).split(os.sep))
        if not os.path.exists(p):
            return None
        ext  = os.path.splitext(p)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
        with open(p, "rb") as f:
            return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"

    entries = [
        # Ungendered images (role=image) — filenames verified against assets/common/
        ("weight_kg",         "ANY", "image", "common/bodyweight.png"),
        ("bmi",               "ANY", "image", "common/bmi_common100X200px.png"),
        ("waist_hip_ratio",   "ANY", "image", "common/waisttohipratio.png"),
        ("bp_systol",         "ANY", "image", "common/bp_common100X200px.png"),
        ("pulse",             "ANY", "image", "common/pulse_common100X200px.png"),
        # Gendered icons — male (role=icon)
        ("weight_kg",         "M",   "icon",  "male/weight_male.png"),
        ("waist_hip_ratio",   "M",   "icon",  "male/waisttohip_male.png"),
        ("pushups",           "M",   "icon",  "male/pushups.png"),
        ("squats",            "M",   "icon",  "male/squats.png"),
        ("situps",            "M",   "icon",  "male/crunches.png"),
        ("plank",             "M",   "icon",  "male/plank.png"),
        ("cooper_12min",      "M",   "icon",  "male/running.png"),
        # Gendered icons — female (role=icon)
        ("weight_kg",         "F",   "icon",  "female/women-weight.jpg"),
        ("waist_hip_ratio",   "F",   "icon",  "female/women-waisttohip.jpg"),
        ("pushups",           "F",   "icon",  "female/women-pushups.jpg"),
        ("squats",            "F",   "icon",  "female/women-situps.jpg"),
        ("situps",            "F",   "icon",  "female/women-situps.jpg"),
        ("plank",             "F",   "icon",  "female/women-plank.jpg"),
        ("cooper_12min",      "F",   "icon",  "female/women-running.jpg"),
    ]
    return [
        {"asset_group_key": key, "gender": g, "role": role, "image_ref": uri}
        for (key, g, role, rel) in entries
        if (uri := _b64(rel)) is not None
    ]

# ── Metric metadata ───────────────────────────────────────────────────────────
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

_MEASUREMENT_ORDER = [
    "neck_cm", "chest_cm", "waist", "abdomen_cm", "hips",
    "thigh_cm", "calf_cm", "shoulder_cm", "forearm_cm", "wrist_cm",
]

_HMS_COMPONENTS = {"physio_2", "balance_open", "balance_closed"}

_COMPONENT_TITLES = {
    "physio_1":       "Physiological Assessment 1",
    "physio_2":       "Physiological Assessment 2",
    "physio_3":       "Physiological Assessment 3",
    "balance_open":   "Balance — Eyes Open",
    "balance_closed": "Balance — Eyes Closed",
    "strength":       "Strength",
}

_COMPONENT_UNIT_NOTE = {
    "physio_1":       "COUNT PER MIN",
    "physio_2":       "IN HH:MM:SS",
    "balance_open":   "IN HH:MM:SS",
    "balance_closed": "IN HH:MM:SS",
}

_BUCKET_3_IDS = ["physio_1", "physio_2", "physio_3", "balance_open", "balance_closed"]


# ── Public API ────────────────────────────────────────────────────────────────

def generate_full_report(client_id, date_from, date_to, component_ids, grid_density,
                         all_readings, client_profile=None,
                         asset_library=None, metric_asset_groups=None,
                         output_dir=None):
    """Orchestrate data → SVG/HTML → Jinja2 → Puppeteer → PDF."""
    output_dir = output_dir or os.path.join(_HERE, "reports")

    payload = build_report_payload(client_id, date_from, date_to, component_ids,
                                   all_readings, client_profile)
    if "error" in payload:
        return payload

    raw_gender = (client_profile or {}).get("gender", "")
    gender     = "F" if str(raw_gender).lower().startswith("f") else "M"

    eff_lib    = asset_library     if asset_library     is not None else _local_asset_library()
    eff_groups = metric_asset_groups if metric_asset_groups is not None else []

    components = payload.get("components", {})
    sections   = _render_sections(components, gender, eff_lib, eff_groups)
    layout     = layout_report(sections, grid_density)

    if layout.get("error") == "empty_report":
        return {"error": "No data available for the selected components"}

    name       = client_id.replace("_", " ").title()
    date_label = _fmt_month_year(date_to)
    html       = _render_template(name, date_label, layout)

    os.makedirs(output_dir, exist_ok=True)
    path, version = _versioned_path(output_dir, client_id, date_to)

    err = _puppeteer_pdf(html, path)
    if err:
        return {"error": err}

    return {"path": path, "version": version, "pages": 1}


# ── Section rendering ─────────────────────────────────────────────────────────

def _render_sections(components, gender="M", asset_library=None, metric_asset_groups=None):
    """Convert components dict to a flat list of rendered section dicts."""
    asset_library       = asset_library or []
    metric_asset_groups = metric_asset_groups or []
    sections = []

    # Bucket 1 — body_measurements grouped bar
    bm = components.get("body_measurements", {})
    bm_series = _measurement_series(bm)
    if bm_series:
        try:
            svg = render_bar_svg(
                {"metrics": bm_series}, "grouped_multi",
                {"show_unit_note": True, "show_legend": True,
                 "stagger_xlabels": True, "bar_width_scale": 0.75},
            )
            sections.append({"component_id": "body_measurements",
                              "title": "Body Measurements", "chart_svg": svg})
        except Exception as exc:
            log.warning("body_measurements render failed: %s", exc)

    # Bucket 2 — body_vitals individual charts
    bv = components.get("body_vitals", {})
    sections.extend(_render_vitals(bv, bm, gender))

    # Strength component
    st = components.get("strength", {})
    if st:
        st_series = _physio_series(st)
        if st_series:
            try:
                svg = render_bar_svg(
                    {"metrics": st_series}, "grouped_multi",
                    {"show_legend": True, "show_unit_note": True},
                )
                sections.append({"component_id": "strength",
                                  "title": "Strength", "chart_svg": svg})
            except Exception as exc:
                log.warning("strength render failed: %s", exc)

    # Bucket 3 — physio / balance heatmaps
    for cid in _BUCKET_3_IDS:
        comp = components.get(cid)
        if not comp:
            continue
        series = _physio_series(comp)
        if not series:
            continue
        try:
            vfmt = "hms" if cid in _HMS_COMPONENTS else "g"
            html = render_table_html({"metrics": series},
                                     {"value_format": vfmt})
            sections.append({
                "component_id": cid,
                "title":        _COMPONENT_TITLES.get(cid, cid),
                "unit_note":    _COMPONENT_UNIT_NOTE.get(cid, ""),
                "chart_html":   html,
            })
        except Exception as exc:
            log.warning("%s heatmap render failed: %s", cid, exc)

    # Attach image_ref / icon_ref to every section from asset library.
    for s in sections:
        lookup_key = s.get("metric_id") or s.get("component_id") or ""
        try:
            v = get_metric_visuals(lookup_key, gender, asset_library, metric_asset_groups)
            s["image_ref"] = v.get("image_ref")
            s["icon_ref"]  = v.get("icon_ref")
        except Exception:
            s["image_ref"] = None
            s["icon_ref"]  = None

    return sections


def _render_vitals(bv, bm, gender="M"):
    out = []

    def _bar(component_id, metric_id, title, data, mode, **extra):
        try:
            svg = render_bar_svg(
                data, mode,
                {"metric_id": metric_id,
                 "show_unit_note": True, "show_date_labels": True,
                 "compact_dates": True, **extra},
            )
            out.append({"component_id": component_id, "metric_id": metric_id,
                         "title": title, "chart_svg": svg})
        except Exception as exc:
            log.warning("Vital %s render failed: %s", metric_id, exc)

    r = _metric_readings(bv, "weight_kg")
    if r:
        _bar("body_vitals", "weight_kg", "Body Weight",
             {"label": "Body Weight", "unit": "kg", "readings": r},
             "horizontal_single", bar_thickness=0.65)

    r = _derived_readings(bv, "bmi")
    if r:
        _bar("body_vitals", "bmi", "BMI",
             {"label": "BMI", "unit": "kg/m²", "readings": r},
             "horizontal_single", bar_thickness=0.65)

    r = _derived_readings(bm, "waist_hip_ratio")
    if r:
        _bar("body_measurements", "waist_hip_ratio", "Waist to Hip Ratio",
             {"label": "Waist to Hip Ratio", "unit": "ratio", "readings": r},
             "horizontal_single", bar_thickness=0.65)

    sys_r = _metric_readings(bv, "bp_systol")
    dia_r = _metric_readings(bv, "bp_diastol")
    if sys_r and dia_r:
        try:
            svg = render_bar_svg(
                {"series": [{"label": "Systolic",  "unit": "mmHg", "readings": sys_r},
                             {"label": "Diastolic", "unit": "mmHg", "readings": dia_r}]},
                "stacked_pair",
                {"metric_id": "bp_systol", "show_legend": True},
            )
            out.append({"component_id": "body_vitals", "metric_id": "bp_systol",
                         "title": "Blood Pressure", "chart_svg": svg})
        except Exception as exc:
            log.warning("Blood Pressure render failed: %s", exc)

    r = _metric_readings(bv, "pulse")
    if r:
        _bar("body_vitals", "pulse", "Pulse",
             {"label": "Pulse", "unit": "bpm", "readings": r},
             "circular_gauge")

    fat_r = _metric_readings(bv, "fat_pct")
    mus_r = _metric_readings(bv, "muscle_pct")
    if fat_r and mus_r:
        try:
            svg = render_bar_svg(
                {"series": [{"label": "Body Fat",    "unit": "%", "readings": fat_r},
                             {"label": "Muscle Mass", "unit": "%", "readings": mus_r}]},
                "stacked_pair",
                {"show_legend": True},
            )
            out.append({"component_id": "body_vitals", "metric_id": "fat_pct",
                         "title": "Body Composition", "chart_svg": svg})
        except Exception as exc:
            log.warning("Body Composition render failed: %s", exc)

    return out


# ── Template rendering ────────────────────────────────────────────────────────

def _render_template(name, date_label, layout):
    env  = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)
    tmpl = env.get_template("report_template.html")
    return tmpl.render(
        name=name,
        date_label=date_label,
        bucket1=layout.get("bucket1", []),
        bucket2_groups=layout.get("bucket2_groups", []),
        bucket3=layout.get("bucket3", []),
        cols_per_row=layout.get("cols_per_row", 1),
        left_logo_b64=_asset_b64("insight_leftlogo.png"),
        right_logo_b64=_asset_b64("insight_rightlogo.png"),
        font_bubblegum=_font_uri("Bubblegum_Sans/BubblegumSans-Regular.ttf"),
        font_roboto=_font_uri("Roboto/static/Roboto-Regular.ttf"),
        font_roboto_bold=_font_uri("Roboto/static/Roboto-Bold.ttf"),
        font_roboto_condensed=_font_uri("Roboto_Condensed/static/RobotoCondensed-Regular.ttf"),
        font_poppins=_font_uri("Poppins/Poppins-Regular.ttf"),
        font_poppins_bold=_font_uri("Poppins/Poppins-Bold.ttf"),
    )


def _asset_b64(filename):
    p = os.path.join(_ASSETS_DIR, filename)
    if not os.path.exists(p):
        return None
    ext  = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
    with open(p, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


# ── Puppeteer PDF call ────────────────────────────────────────────────────────

def _puppeteer_pdf(html_str, pdf_path):
    """Write HTML to a temp file, call Node Puppeteer script, return error str or None."""
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(html_str)
        html_path = f.name
    try:
        result = subprocess.run(
            ["node", _RENDER_JS, html_path, pdf_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.error("Puppeteer failed: %s", result.stderr)
            return f"Puppeteer error: {result.stderr[:300]}"
        return None
    except FileNotFoundError:
        return "Node.js not found — install Node.js to generate PDFs"
    except subprocess.TimeoutExpired:
        return "Puppeteer timed out (60 s)"
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass


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


# ── PDF versioning ────────────────────────────────────────────────────────────

def _versioned_path(output_dir, client_id, date_to):
    base    = f"{client_id}_{date_to}_full_report"
    version = 1
    while True:
        candidate = os.path.join(output_dir, f"{base}_v{version}.pdf")
        if not os.path.exists(candidate):
            return candidate, version
        version += 1


# ── Helpers ───────────────────────────────────────────────────────────────────

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
