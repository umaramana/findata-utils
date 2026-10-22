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
import re
import subprocess
import tempfile

from jinja2 import Environment, FileSystemLoader

from report_query import build_nudge_payload, build_walkin_nudge_payload

log = logging.getLogger(__name__)

_HERE          = os.path.dirname(__file__)
_ASSETS_DIR    = os.path.join(_HERE, "assets")
_TEMPLATES_DIR = os.path.join(_HERE, "templates")
_RENDER_JS     = os.path.join(_HERE, "render_report.js")


def generate_nudge_png(client_id, date_to, all_readings, component_id="body_vitals",
                       output_dir=None, client_name=None, gym_name=None, gym_logo=None):
    """Orchestrate data -> HTML -> Puppeteer -> PNG.

    component_id: any of the 7 Report Config components (F06-S02) — the
    single component the Nudge card renders. Defaults to body_vitals.

    client_name: client_info.full_name when the caller has read it. Falls back
    to the client_id-derived guess ("dr_pavan" -> "Dr Pavan"), which is fine on
    the small generic card but reads poorly on the grip card's 25px name slot.

    gym_name / gym_logo: the client's gym, resolved by Apps Script (the logo
    arrives already base64'd as a data URI — the Cloud Run service account
    cannot read the trainer's Drive). Grip card only; both optional, and the
    card falls back to its house text for whichever one is missing.

    Returns {"path": str, "version": int} | {"error": str}.
    """
    output_dir = output_dir or os.path.join(_HERE, "reports")

    payload = build_nudge_payload(client_id, date_to, all_readings, component_id=component_id)
    if "error" in payload:
        return payload

    name = client_name or client_id.replace("_", " ").title()
    filename_base = f"{client_id}_{date_to}_nudge_{component_id}"
    return _render_and_save(name, payload, output_dir, filename_base,
                            gym_name=gym_name, gym_logo=gym_logo)


def generate_walkin_nudge_png(name, date, values, output_dir=None,
                              gym_name=None, gym_logo=None):
    """Walk-In tab (F06-S04 Part B) — untracked gym-challenge entry.

    Renders directly from the submitted form values, not from Sheets history:
    no client_id, no by-metric/date lookup (see build_walkin_nudge_payload).
    Same renderer/template as the tracked-client grip_strength path — only
    the payload source differs.

    values: {metric_id: numeric-or-blank-string} — grip_right_trial_1..3,
    grip_left_trial_1..3, grip_right_grade, grip_left_grade.

    gym_name / gym_logo: the gym picked on the form, same contract as
    generate_nudge_png's.

    Returns {"path": str, "version": int} | {"error": str}.
    """
    output_dir = output_dir or os.path.join(_HERE, "reports")

    payload = build_walkin_nudge_payload(name, date, values)
    if "error" in payload:
        return payload

    safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "walkin"
    filename_base = f"walkin_{safe_name}_{date}_grip_strength"
    return _render_and_save(name, payload, output_dir, filename_base,
                            gym_name=gym_name, gym_logo=gym_logo)


def _render_and_save(name, payload, output_dir, filename_base, gym_name=None, gym_logo=None):
    html = _render_template(name, payload, gym_name=gym_name, gym_logo=gym_logo)

    os.makedirs(output_dir, exist_ok=True)
    path, version = _versioned_path(output_dir, filename_base)

    err = _puppeteer_png(html, path)
    if err:
        return {"error": err}

    return {"path": path, "version": version}


_FONT_BOLD    = os.path.join(_HERE, "fonts", "Roboto", "static", "Roboto-Bold.ttf")
_FONT_REGULAR = os.path.join(_HERE, "fonts", "Roboto", "static", "Roboto-Regular.ttf")

_BLUR_RADIUS = 28
_PANEL_W, _PANEL_H = 620, 760
_QR_MIN_PX = 360
_QR_BORDER_MODULES = 4


def upi_config():
    """F06-S08 — the 3 paywall env vars, or None if any is missing/invalid.

    A config gap must never block the normal report, so callers treat None as
    "no locked image" rather than an error.
    """
    vpa   = (os.environ.get("UPI_VPA") or "").strip()
    payee = (os.environ.get("UPI_PAYEE_NAME") or "").strip()
    price = (os.environ.get("UNLOCK_PRICE_INR") or "").strip()
    try:
        ok_price = float(price) > 0
    except ValueError:
        ok_price = False
    if not (vpa and payee and ok_price):
        return None
    return {"vpa": vpa, "payee": payee, "price": price}


def build_upi_string(cfg, client_name):
    from urllib.parse import quote
    q = lambda s: quote(s, safe="")  # noqa: E731 — spaces must be %20, not +
    return (
        f"upi://pay?pa={q(cfg['vpa'])}&pn={q(cfg['payee'])}&am={q(cfg['price'])}"
        f"&cu=INR&tn={q('Grip report ' + client_name)}"
    )


def make_locked_png(full_path, client_name, cfg):
    """F06-S08 — blur the whole full PNG and paste a sharp UPI-QR panel on top.

    Post-process only: the full render and its template are untouched.
    Returns the path of the saved "<base>_locked.png".
    """
    import io
    import segno
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.open(full_path).convert("RGB").filter(ImageFilter.GaussianBlur(_BLUR_RADIUS))
    W, H = img.size

    # QR: integer module scale, so every module stays crisp after WhatsApp
    # recompression; border is the quiet zone.
    qr = segno.make(build_upi_string(cfg, client_name), error="m")
    n = qr.symbol_size(border=_QR_BORDER_MODULES)[0]
    scale = -(-_QR_MIN_PX // n)  # ceil
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=_QR_BORDER_MODULES, dark="black", light="white")
    qr_img = Image.open(buf).convert("RGB")

    px, py = (W - _PANEL_W) // 2, (H - _PANEL_H) // 2
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([px, py, px + _PANEL_W, py + _PANEL_H], radius=32, fill="white")

    def centred(text, y, font):
        w = draw.textlength(text, font=font)
        draw.text((px + (_PANEL_W - w) / 2, y), text, font=font, fill="#1a1a1a")

    # Name shrinks to fit the panel width; it is the one variable-length string.
    size = 46
    while size > 22:
        name_font = ImageFont.truetype(_FONT_BOLD, size)
        if draw.textlength(client_name, font=name_font) <= _PANEL_W - 60:
            break
        size -= 2
    centred(client_name, py + 40, name_font)
    centred("your report is ready", py + 40 + size + 14, ImageFont.truetype(_FONT_REGULAR, 34))

    img.paste(qr_img, (px + (_PANEL_W - qr_img.width) // 2, py + 170))

    price = cfg["price"].rstrip("0").rstrip(".") if "." in cfg["price"] else cfg["price"]
    centred(f"Scan to unlock · ₹{price}", py + _PANEL_H - 100, ImageFont.truetype(_FONT_BOLD, 44))

    out = os.path.splitext(full_path)[0] + "_locked.png"
    img.save(out, "PNG")
    return out


def _render_template(name, payload, gym_name=None, gym_logo=None):
    """Pick the card template for this payload and render it.

    grip_strength has its own full-bleed 1024x1536 design (2026-09-23 handover)
    that shares none of the generic card's markup — two fixed hand panels, a
    photographic masthead, bundled webfonts. The other six components keep
    nudge_template.html unchanged.

    gym_name/gym_logo are grip-card-only slots; the generic card has nowhere
    to put them and ignores them.
    """
    if payload.get("componentId") == "grip_strength":
        return _render_grip_template(name, payload, gym_name=gym_name, gym_logo=gym_logo)

    env  = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)
    tmpl = env.get_template("nudge_template.html")
    return tmpl.render(
        client_name=name,
        kicker=payload["displayName"].upper(),
        display_date=_format_date(payload["date"]),
        headline_caption=payload["headlineCaption"],
        headline_value=payload["headlineValue"],
        stat_boxes=payload["statBoxes"],
        measurement_bars=payload["measurementBars"],
        logo_b64=_asset_b64("insight_leftlogo.png"),
    )


def _render_grip_template(name, payload, gym_name=None, gym_logo=None):
    """Hand Grip Strength card - grip_nudge_template.html (1024x1536).

    Both hands are mandatory at data entry, so the template always has two
    numbers to show; _hand() still raises rather than rendering a half-card if
    a payload ever arrives with a hand missing, since a silently blank 100px
    numeral is worse than a caught error.

    The gym is optional at both ends: without a gym name the third meta column
    stays on the test name, and without a logo the footer keeps the house
    MOVE BETTER / FEEL BETTER / LIVE BOLDER block. A gym with a name but no
    logo file gets one without the other, which is why the template branches
    on each separately.
    """
    env  = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)
    tmpl = env.get_template("grip_nudge_template.html")

    right = _hand(payload, "RIGHT HAND")
    left  = _hand(payload, "LEFT HAND")

    return tmpl.render(
        name=name,
        test_date=_format_date(payload["date"]),
        test_name=payload["displayName"],
        right=_kg(right["value"]),
        left=_kg(left["value"]),
        right_label=right.get("grade") or "",
        left_label=left.get("grade") or "",
        font_face_css=_font_face_css(),
        hero_b64=_asset_b64(os.path.join("grip", "man.png")),
        logo_b64=_asset_b64("insight_leftlogo.png"),
        mountain_b64=_asset_b64(os.path.join("grip", "mountain.png")),
        gym_name=gym_name or "",
        gym_logo=_safe_logo(gym_logo),
    )


def _safe_logo(gym_logo):
    """Only ever let a self-contained data: URI into the card's <img>.

    The logo reaches us as a payload string from Apps Script; a remote URL
    here would make the Puppeteer render depend on (and reach out to) an
    outside host at render time. Anything else degrades to the house footer.
    """
    if isinstance(gym_logo, str) and gym_logo.startswith("data:image/"):
        return gym_logo
    if gym_logo:
        log.warning("Ignoring gym logo that is not an inline data: URI")
    return ""


def _hand(payload, label):
    for box in payload.get("statBoxes", []):
        if box.get("label") == label:
            return box
    raise ValueError(f"grip nudge payload has no {label} stat box")


def _kg(value):
    """Template does no rounding - always hand it a 1dp string."""
    return f"{float(value):.1f}"


# Bundled webfonts. The Cloud Run image (report_service/Dockerfile) installs
# only fonts-liberation, and this layout's letter-spacing is load-bearing, so a
# silent fallback to system sans would ship a broken card with no error. Latin
# subsets only; Archivo is a variable font, hence one file across 400-700.
_FONT_FACES = [
    ("Archivo",               "100 900", "archivo-variable.woff2"),
    ("Archivo Black",         "400",     "archivo-black-400.woff2"),
    ("Barlow Semi Condensed", "600",     "barlow-semi-condensed-600.woff2"),
    ("Barlow Semi Condensed", "800",     "barlow-semi-condensed-800.woff2"),
    ("Dancing Script",        "400 700", "dancing-script-600.woff2"),
]


def _font_face_css():
    out = []
    for family, weight, filename in _FONT_FACES:
        path = os.path.join(_ASSETS_DIR, "fonts", filename)
        if not os.path.exists(path):
            log.warning("Missing bundled font %s - card will fall back to system sans", filename)
            continue
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        out.append(
            f"  @font-face {{ font-family: '{family}'; font-style: normal; "
            f"font-weight: {weight}; font-display: block; "
            f"src: url(data:font/woff2;base64,{b64}) format('woff2'); }}"
        )
    return "\n".join(out)


def _format_date(date_iso):
    """YYYY-MM-DD -> 'Aug 21, 2026' for the card display.

    Avoids strftime's %-d/%#d (platform-specific, breaks across Linux Cloud
    Run vs local Windows testing via generate_nudge.py) by formatting the
    day number manually.
    """
    import datetime
    d = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _asset_b64(filename):
    p = os.path.join(_ASSETS_DIR, filename)
    if not os.path.exists(p):
        return None
    ext  = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
    with open(p, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def _versioned_path(output_dir, base):
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
