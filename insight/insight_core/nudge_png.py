"""
Nudge PNG generator — design handoff 2c ("WhatsApp Card").

Pipeline:
  1. report_query.build_nudge_payload() -> flat data payload
  2. Jinja2 render nudge_template.html   -> full HTML document
  3. Node render_report.js (Puppeteer, --mode=png) -> single PNG screenshot

Deliberately separate from report_pdf.py's pipeline: the nudge has a fixed,
static layout (no chart_renderer/layout_engine bucket logic needed) and a
different render target (PNG screenshot of one card, not a multi-page PDF).
"""

import os
import base64
import logging
import subprocess
import tempfile

from jinja2 import Environment, FileSystemLoader

from report_query import build_nudge_payload

log = logging.getLogger(__name__)

_HERE          = os.path.dirname(__file__)
_ASSETS_DIR    = os.path.join(_HERE, "assets")
_TEMPLATES_DIR = os.path.join(_HERE, "templates")
_RENDER_JS     = os.path.join(_HERE, "render_report.js")


def generate_nudge_png(client_id, date_to, all_readings, component_id="body_vitals", output_dir=None):
    """Orchestrate data -> HTML -> Puppeteer -> PNG.

    component_id: any of the 7 Report Config components (F06-S02) — the
    single component the Nudge card renders. Defaults to body_vitals.

    Returns {"path": str, "version": int} | {"error": str}.
    """
    output_dir = output_dir or os.path.join(_HERE, "reports")

    payload = build_nudge_payload(client_id, date_to, all_readings, component_id=component_id)
    if "error" in payload:
        return payload

    name = client_id.replace("_", " ").title()
    html = _render_template(name, payload)

    os.makedirs(output_dir, exist_ok=True)
    path, version = _versioned_path(output_dir, client_id, date_to, component_id)

    err = _puppeteer_png(html, path)
    if err:
        return {"error": err}

    return {"path": path, "version": version}


def _render_template(name, payload):
    env  = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)
    tmpl = env.get_template("nudge_template.html")
    return tmpl.render(
        client_name=name,
        headline_caption=payload["headlineCaption"],
        headline_value=payload["headlineValue"],
        stat_boxes=payload["statBoxes"],
        measurement_bars=payload["measurementBars"],
        logo_b64=_asset_b64("insight_leftlogo.png"),
    )


def _asset_b64(filename):
    p = os.path.join(_ASSETS_DIR, filename)
    if not os.path.exists(p):
        return None
    ext  = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
    with open(p, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def _versioned_path(output_dir, client_id, date_to, component_id):
    base    = f"{client_id}_{date_to}_nudge_{component_id}"
    version = 1
    while True:
        candidate = os.path.join(output_dir, f"{base}_v{version}.png")
        if not os.path.exists(candidate):
            return candidate, version
        version += 1


def _puppeteer_png(html_str, png_path):
    """Write HTML to a temp file, call Node Puppeteer script in PNG mode, return error str or None."""
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(html_str)
        html_path = f.name
    try:
        result = subprocess.run(
            ["node", _RENDER_JS, html_path, png_path, "--mode=png"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.error("Puppeteer failed: %s", result.stderr)
            return f"Puppeteer error: {result.stderr[:300]}"
        return None
    except FileNotFoundError:
        return "Node.js not found — install Node.js to generate the nudge PNG"
    except subprocess.TimeoutExpired:
        return "Puppeteer timed out (60 s)"
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass
