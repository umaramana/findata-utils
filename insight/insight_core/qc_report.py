"""
Report QC script — compares a newly generated report PDF against a known-good
baseline sample, and prints a short structured list of issues.

Usage:
    python qc_report.py <new_report.pdf> <baseline_sample.pdf> [--out qc_out]

What it checks:
  1. Page count match
  2. Pixel diff per page (visual regression) -> diff images saved to --out
  3. Text-based structural checks (cover page present, closing page present,
     unit-label presence per chart, icon/image presence heuristics)

This is a starting point, not a finished product — thresholds and the
structural checklist should be tuned against more of your 7 real samples
as you run it more.
"""

import sys
import argparse
import os
import re
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image, ImageChops
import pdfplumber


def pixel_diff(new_pdf, baseline_pdf, out_dir, dpi=150, threshold_pct=2.0, baseline_page_range=None):
    issues = []
    new_pages = convert_from_path(new_pdf, dpi=dpi)
    base_pages_full = convert_from_path(baseline_pdf, dpi=dpi)

    if baseline_page_range:
        start, end = baseline_page_range
        base_pages_selected = base_pages_full[start - 1:end]
    else:
        base_pages_selected = base_pages_full

    # New report is a single continuous content page. If the baseline's
    # content spans multiple separate pages, stitch them into one tall
    # image so the comparison is apples-to-apples.
    if len(base_pages_selected) > 1:
        widths = [p.width for p in base_pages_selected]
        total_height = sum(p.height for p in base_pages_selected)
        stitched = Image.new("RGB", (max(widths), total_height), "white")
        y_offset = 0
        for p in base_pages_selected:
            stitched.paste(p.convert("RGB"), (0, y_offset))
            y_offset += p.height
        base_pages = [stitched]
    else:
        base_pages = base_pages_selected

    n_compare = min(len(new_pages), len(base_pages))
    os.makedirs(out_dir, exist_ok=True)

    for i in range(n_compare):
        n_img = new_pages[i].convert("RGB")
        b_img = base_pages[i].convert("RGB")

        if n_img.size != b_img.size:
            dw, dh = n_img.width - b_img.width, n_img.height - b_img.height
            pct_h = (dh / b_img.height) * 100 if b_img.height else 0
            issues.append(
                f"page {i+1}: HEIGHT/WIDTH MISMATCH — new={n_img.size} baseline={b_img.size} "
                f"({'+' if dh >= 0 else ''}{dh}px / {pct_h:+.1f}% height) — new content legitimately "
                f"changed height (or something regressed layout height); the pixel-diff % below only "
                f"covers the shared top-left region and CANNOT see anything past the shorter page's edge"
            )

        # Compare only the overlapping top-left region — resizing/stretching
        # one image to match the other's dimensions distorts content and
        # produces a misleading cascading-misalignment diff (verified
        # 2026-07-01: a 33px height difference made the whole page look
        # "doubled" in the diff even though individual regions were correct).
        cw, ch = min(n_img.width, b_img.width), min(n_img.height, b_img.height)
        n_crop = n_img.crop((0, 0, cw, ch))
        b_crop = b_img.crop((0, 0, cw, ch))

        diff = ImageChops.difference(n_crop, b_crop)
        bbox = diff.getbbox()
        if bbox is None:
            continue

        hist = diff.histogram()
        # histogram is 256 bins per channel (R,G,B) = 768 values total
        nonzero_weighted = sum(v * (idx % 256) for idx, v in enumerate(hist))
        total_pixels = cw * ch * 3 * 255
        pct = (nonzero_weighted / total_pixels) * 100 if total_pixels else 0

        if pct >= threshold_pct:
            diff_path = os.path.join(out_dir, f"diff_page{i+1}.png")
            diff.save(diff_path)
            issues.append(
                f"page {i+1}: {pct:.2f}% pixel difference in shared region (threshold {threshold_pct}%), "
                f"diff region bbox={bbox}, saved -> {diff_path}"
            )

    return issues


def structural_checks(new_pdf):
    issues = []
    with pdfplumber.open(new_pdf) as pdf:
        n_pages = len(pdf.pages)
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

        # Cover and closing pages are being removed from the pipeline by
        # design (content-only report now) — no checks for those here.

        # 1. Text-coverage check — find the lowest y-position with extractable
        # text vs the page's full height. A large gap means that section is
        # image-only, not live text — loses selectability/searchability.
        for i, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not words:
                issues.append(f"page {i+1}: zero extractable text found — entire page may be image-only")
                continue
            max_text_y = max(w["top"] for w in words)
            coverage_pct = (max_text_y / page.height) * 100
            if coverage_pct < 85:
                issues.append(
                    f"page {i+1}: extractable text stops at {coverage_pct:.0f}% of page height "
                    f"(text found up to y={max_text_y:.0f} of {page.height:.0f}) — "
                    "the remaining section is likely rendered as a flattened image, not live text"
                )

        # Unit badge check: bucket-2 metrics (body_vitals) use SVG axis labels, not HTML badges.
        # Bucket-3 heatmaps use HTML .unit-badge spans (e.g. "COUNT PER MIN", "HH:MM:SS")
        # which ARE extractable. Only flag if a bucket-3 header keyword is present but no badge.
        # Deferred — no reliable pattern to distinguish badges from column headers here.

        # 4. Icon/image presence — count embedded images per content page,
        # flag pages with charts but zero supporting icon images.
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            has_chart_keywords = any(
                kw in page_text for kw in ["BMI", "Body Weight", "Pulse", "Blood Pressure"]
            )
            if has_chart_keywords and len(page.images) == 0:
                issues.append(
                    f"page {i+1}: contains metric charts but zero embedded images "
                    "(expected per-metric icon/hero image)"
                )

    return issues, n_pages


def layout_checks(new_pdf):
    """
    Checks the bucket model directly: body_measurements alone full-width,
    bucket-2 metrics arranged in a grid (paired by row), bucket-3 heatmaps
    stacked full-width. Works by reading the x/y position of each chart's
    title text — no access to the underlying HTML/CSS, so this is a
    positional heuristic, not a DOM check. Flag if it gives false positives
    and we'll tighten the keyword list or tolerance.
    """
    issues = []
    BUCKET1_TITLES = ["Body Measurements"]
    BUCKET2_TITLES = ["Body Weight", "BMI", "Waist to Hip Ratio", "Blood Pressure", "Pulse", "Body Composition"]
    BUCKET3_TITLES = ["Physiological Assessment", "Balance"]

    with pdfplumber.open(new_pdf) as pdf:
        # Build an ordered list of (word, x0, top, page_num) per page, then
        # find each full title as a sequence of consecutive, spatially-close words.
        def find_title_pos(title, page_words):
            title_tokens = title.split()
            for i in range(len(page_words) - len(title_tokens) + 1):
                window = page_words[i:i + len(title_tokens)]
                if all(w["text"] == tok for w, tok in zip(window, title_tokens)):
                    # confirm they're on the same line and close together
                    tops = [w["top"] for w in window]
                    if max(tops) - min(tops) < 5:
                        return (window[0]["x0"], window[0]["top"], window[0].get("_page_num"))
            return None

        all_b1, all_b2, all_b3 = [], {}, []
        for page in pdf.pages:
            words = page.extract_words()
            for w in words:
                w["_page_num"] = page.page_number

            for t in BUCKET1_TITLES:
                pos = find_title_pos(t, words)
                if pos:
                    all_b1.append(pos)
            for t in BUCKET2_TITLES:
                pos = find_title_pos(t, words)
                if pos and t not in all_b2:
                    all_b2[t] = pos
            for t in BUCKET3_TITLES:
                pos = find_title_pos(t, words)
                if pos:
                    all_b3.append(pos)

        b1_pos, b2_pos, b3_pos = all_b1, all_b2, all_b3

        if not b1_pos:
            issues.append("could not locate 'Body Measurements' title — bucket 1 may be missing or mislabeled")

        if len(b2_pos) < 2:
            issues.append(f"only found {len(b2_pos)} of {len(BUCKET2_TITLES)} expected bucket-2 chart titles")
        else:
            # Group bucket-2 titles into rows by similar y (top), tolerance 20pt
            sorted_b2 = sorted(b2_pos.items(), key=lambda kv: kv[1][1])
            rows = []
            for title, (x0, top, page_num) in sorted_b2:
                placed = False
                for row in rows:
                    if abs(row[0][1][1] - top) < 20 and row[0][1][2] == page_num:
                        row.append((title, (x0, top, page_num)))
                        placed = True
                        break
                if not placed:
                    rows.append([(title, (x0, top, page_num))])

            for row in rows:
                if len(row) > 1:
                    xs = sorted(item[1][0] for item in row)
                    if any(xs[i+1] - xs[i] < 30 for i in range(len(xs) - 1)):
                        names = ", ".join(item[0] for item in row)
                        issues.append(f"bucket-2 items appear too close horizontally / possibly overlapping: {names}")

            # bucket 1 should sit above all bucket-2 rows
            if b1_pos and rows:
                b1_top = b1_pos[0][1]
                min_b2_top = min(item[1][1] for row in rows for item in row)
                if b1_top >= min_b2_top:
                    issues.append("'Body Measurements' does not appear above bucket-2 charts — bucket order may be wrong")

        if not b3_pos:
            issues.append("could not locate any Physiological/Balance (bucket-3) titles — heatmaps may be missing")
        else:
            # bucket 3 should sit below bucket 2
            if b2_pos:
                max_b2_top = max(p[1] for p in b2_pos.values())
                min_b3_top = min(p[1] for p in b3_pos)
                if min_b3_top <= max_b2_top:
                    issues.append("a bucket-3 (heatmap) title appears above or level with bucket-2 charts — order may be wrong")

            # bucket 3 items should be full-width — title position alone can't confirm
            # a heatmap spans the full content width, so this is a visual / eyeball check.

    return issues


EXPECTED_ORIENTATION = {
    "Body Weight": "wide",        # horizontal_single
    "Waist to Hip Ratio": "wide",  # horizontal_single
    "BMI": "wide",                 # horizontal_single
    "Body Measurements": "wide",   # grouped_multi
    # Pulse intentionally excluded — it's a circular gauge/donut, not a bar.
    # Confirmed against the real Reshma sample 2026-06-30. See CIRCULAR_METRICS below.
    # Blood Pressure intentionally excluded from the wide/tall test — its bbox
    # aspect ratio is a function of date count N (more dates = wider bbox for
    # the same "2 segments per bar" shape), so a fixed wide/tall expectation
    # can never be right for all N. Checked instead via STACKED_PAIR_METRICS
    # below with an N-general rule: segment_count == 2 * date_count. (F04-S07,
    # replaces a prior version of this file that hardcoded "2 dates" in a
    # comment and skipped Blood Pressure with no real check at all.)
}

CIRCULAR_METRICS = ["Pulse"]  # checked for roughly-square aspect (a circle's bbox), not wide/tall

STACKED_PAIR_METRICS = ["Blood Pressure"]  # checked via bar-segment count, not orientation
_DATE_LABEL_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")

WIDE_RATIO_THRESHOLD = 1.4  # width/height above this = "wide", below 1/1.4 = "tall"
EDGE_MARGIN_PT = 15         # how close to the page edge counts as "edge-to-edge"

# Metrics with no expected side image by design (no file exists; omit icon check)
NO_ICON_EXPECTED = {"Body Measurements"}


def get_row_groups(title_positions):
    """Group titles into rows by similar y-position, then sort each row left-to-right."""
    items = sorted(title_positions.items(), key=lambda kv: kv[1][1])
    rows = []
    for title, pos in items:
        placed = False
        for row in rows:
            if abs(row[0][1][1] - pos[1]) < 20 and row[0][1][2] == pos[2]:
                row.append((title, pos))
                placed = True
                break
        if not placed:
            rows.append([(title, pos)])
    for row in rows:
        row.sort(key=lambda item: item[1][0])
    return rows


def column_bounds_for_row(row, page_width):
    """Each item's column = from its own x0 to the next column's x0 (or page edge).
    Using next column's x0 (not midpoint) because chart content (bars, axes) extends
    beyond the midpoint — bars for the current metric can reach close to the next title."""
    bounds = {}
    for i, (title, pos) in enumerate(row):
        left = pos[0]
        right = row[i + 1][1][0] if i + 1 < len(row) else page_width
        bounds[title] = (left, right)
    return bounds


def find_nearby_images(title_pos, page_images, max_vertical_gap=140, col_bounds=None):
    """Images vertically below the title within max_vertical_gap. Without
    col_bounds this also matches unrelated content anywhere on the page at
    the same height (e.g. the footer's decorative dot-grid images landed
    inside this window for a short, single-metric report and were
    miscounted as "the icon" — F04-S09, 2026-07-04) — always pass col_bounds
    when the caller already has a column to check against."""
    x0, top, _ = title_pos
    matches = [img for img in page_images if img["top"] >= top and (img["top"] - top) < max_vertical_gap]
    if col_bounds is not None:
        left, right = col_bounds
        matches = [img for img in matches if left <= img["x0"] and img["x1"] <= right]
    return matches


def chart_render_checks(new_pdf):
    issues = []
    titles_to_check = list(EXPECTED_ORIENTATION.keys()) + CIRCULAR_METRICS + STACKED_PAIR_METRICS

    with pdfplumber.open(new_pdf) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            page_images = page.images
            page_width = page.width
            page_rects = page.rects
            page_lines = page.lines
            page_curves = page.curves

            title_positions = {}
            for title in titles_to_check:
                tokens = title.split()
                for i in range(len(words) - len(tokens) + 1):
                    window = words[i:i + len(tokens)]
                    if all(wd["text"] == tok for wd, tok in zip(window, tokens)):
                        tops = [wd["top"] for wd in window]
                        if max(tops) - min(tops) < 5:
                            title_positions[title] = (window[0]["x0"], window[0]["top"], page.page_number)
                            break

            if not title_positions:
                continue

            for row in get_row_groups(title_positions):
                col_bounds = column_bounds_for_row(row, page_width)
                for title, pos in row:
                    left, right = col_bounds[title]
                    top = pos[1]

                    if title in CIRCULAR_METRICS:
                        # Expect a donut/ring drawn with curves, roughly square bbox —
                        # not the bar wide/tall test. Filter out tiny curves (font glyph
                        # outlines are < 15pt wide) — only keep arc-sized curves.
                        curves = [
                            c for c in page_curves
                            if left <= c["x0"] and c["x1"] <= right
                            and c["top"] >= top and (c["top"] - top) < 140
                            and (c["x1"] - c["x0"]) > 15  # exclude font glyph outlines
                        ]
                        if not curves:
                            issues.append(
                                f"'{title}': expected a circular gauge/donut (drawn with curves) — "
                                f"found no arc-sized curve shapes in its column, may be rendering as a bar instead"
                            )
                        else:
                            w_ = max(c["x1"] for c in curves) - min(c["x0"] for c in curves)
                            h_ = max(c["bottom"] for c in curves) - min(c["top"] for c in curves)
                            ratio = w_ / h_ if h_ else 0
                            if not (0.6 <= ratio <= 1.8):
                                issues.append(
                                    f"'{title}': has curve shapes but bbox isn't roughly circular "
                                    f"(w={w_:.0f}, h={h_:.0f}, ratio={ratio:.2f}) — check it's actually a donut, not a stretched shape"
                                )
                        nearby_imgs = find_nearby_images(pos, page_images, col_bounds=(left, right))
                        if not nearby_imgs:
                            issues.append(f"'{title}': no icon image found near its title (icons are inset raster images per spec)")
                        continue

                    if title in STACKED_PAIR_METRICS:
                        # N-general rule (F04-S07): a stacked_pair chart draws exactly
                        # 2 bar segments per date, for any date count — count segment
                        # rects and date-month tick labels independently within this
                        # column and assert they're in a fixed 2:1 ratio. Replaces the
                        # old wide/tall aspect check, which only ever worked for the
                        # one N it was eyeballed against.
                        col_words = [
                            w for w in words
                            if left <= w["x0"] and w["x1"] <= right
                            and w["top"] >= top and (w["top"] - top) < 140
                        ]
                        date_count = sum(1 for w in col_words if _DATE_LABEL_RE.match(w["text"]))

                        seg_rects = [
                            s for s in page_rects
                            if left <= s["x0"] and s["x1"] <= right
                            and s["top"] >= top and (s["top"] - top) < 140
                            and (s["x1"] - s["x0"]) > 2 and (s["bottom"] - s["top"]) > 2
                        ]
                        seg_count = len(seg_rects)

                        if date_count == 0:
                            issues.append(f"'{title}': could not detect any date labels in its column — check manually")
                        elif seg_count != 2 * date_count:
                            issues.append(
                                f"'{title}': expected {2 * date_count} bar segments (2 per date × "
                                f"{date_count} dates), found {seg_count} — check stacked_pair is "
                                "rendering both series for every date"
                            )
                        continue

                    shapes = [
                        s for s in (list(page_rects) + list(page_lines))
                        if left <= s["x0"] and s["x1"] <= right
                        and s["top"] >= top and (s["top"] - top) < 140
                    ]

                    if not shapes:
                        issues.append(f"'{title}': could not isolate a chart shape in its column — check manually")
                        continue

                    w_ = max(s["x1"] for s in shapes) - min(s["x0"] for s in shapes)
                    h_ = max(s["bottom"] for s in shapes) - min(s["top"] for s in shapes)
                    ratio = w_ / h_ if h_ else 0
                    actual = "wide" if ratio >= WIDE_RATIO_THRESHOLD else ("tall" if ratio <= 1 / WIDE_RATIO_THRESHOLD else "square")
                    expected = EXPECTED_ORIENTATION[title]

                    if actual != expected:
                        issues.append(
                            f"'{title}': expected a {expected} bar (bar runs "
                            f"{'sideways, short and wide' if expected=='wide' else 'upward, tall and narrow'}), "
                            f"but found {actual} (w={w_:.0f}, h={h_:.0f}, ratio={ratio:.2f})"
                        )

                    # Width-constraint: only meaningful for items alone in their row (e.g. Body Measurements)
                    if len(row) == 1 and left < EDGE_MARGIN_PT and (page_width - right) < EDGE_MARGIN_PT:
                        issues.append(
                            f"'{title}': chart spans edge-to-edge (x0={left:.0f}, x1={right:.0f} "
                            f"of page width {page_width:.0f}) — content should sit inside a constrained, margined column"
                        )

                    if title not in NO_ICON_EXPECTED:
                        nearby_imgs = find_nearby_images(pos, page_images, col_bounds=(left, right))
                        if not nearby_imgs:
                            issues.append(f"'{title}': no icon image found near its title (icons are inset raster images per spec)")

    return issues


# ---------------------------------------------------------------------------
# New checks added 2026-06-30, round 2 — picked because they generalize
# across different clients/data shapes (font, duplicate text, position),
# not because they're easy. Pixel-gap/proportion feedback from this round
# was deliberately left out — see chat notes, that's eyeball-and-tune work,
# not durable QC.
# ---------------------------------------------------------------------------

# Font/size consistency is intentionally NOT automated here. Built and then
# removed a font-name/size detection system (CSS-variable parser, fuzzy
# matching, pt-conversion) — it was more machinery than the problem
# warranted. The actual fix is centralizing font/size rules once in the
# stylesheet (h1/h2/.chart-title { font-family: ... }) so every chart
# inherits instead of declaring its own — see design_tokens.css for the
# values. Eyeball font consistency visually; once centralized it's a
# 30-second check, not something worth scripting.


def duplicate_title_checks(new_pdf):
    """Flags a chart title appearing twice in close proximity (e.g. top-left
    label + a repeated top-right label) — the bug found on Body Measurements
    and other Body Vitals charts in round 2 feedback. Generalizes to any
    metric, not hardcoded to specific ones."""
    issues = []
    title_keywords = [
        "Body Measurements", "Body Weight", "Waist to Hip Ratio", "BMI",
        "Blood Pressure", "Pulse", "Body Composition",
    ]

    with pdfplumber.open(new_pdf) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for title in title_keywords:
                tokens = title.split()
                matches = []
                for i in range(len(words) - len(tokens) + 1):
                    window = words[i:i + len(tokens)]
                    if all(w["text"] == tok for w, tok in zip(window, tokens)):
                        tops = [w["top"] for w in window]
                        if max(tops) - min(tops) < 5:
                            matches.append((window[0]["x0"], window[0]["top"]))
                if len(matches) > 1:
                    # group matches that are vertically close (same chart's title area, not two
                    # separate unrelated charts coincidentally sharing a name)
                    matches.sort(key=lambda m: m[1])
                    clustered = []
                    cluster = [matches[0]]
                    for m in matches[1:]:
                        if m[1] - cluster[-1][1] < 60:
                            cluster.append(m)
                        else:
                            clustered.append(cluster)
                            cluster = [m]
                    clustered.append(cluster)
                    for cluster in clustered:
                        if len(cluster) > 1:
                            xs = [c[0] for c in cluster]
                            issues.append(
                                f"'{title}': title text appears {len(cluster)} times in the same chart area "
                                f"(x-positions {[round(x) for x in xs]}) — likely a duplicate label, keep only the left-aligned one"
                            )
    return issues


def unit_of_measure_position_checks(new_pdf):
    """Confirms 'Units of measure' / 'Measurement units' text sits in the
    right portion of its chart's column, per the locked right-corner placement rule."""
    issues = []
    unit_phrases = ["Units of measure", "Measurement units", "Unit of measure"]

    with pdfplumber.open(new_pdf) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            page_width = page.width
            for phrase in unit_phrases:
                tokens = phrase.split()
                for i in range(len(words) - len(tokens) + 1):
                    window = words[i:i + len(tokens)]
                    if all(w["text"] == tok for w, tok in zip(window, tokens)):
                        x0 = window[0]["x0"]
                        # crude global check: should be in the right half of the page at minimum.
                        # NOTE: this doesn't know per-chart column boundaries by itself — if charts
                        # are gridded, "right half of page" is too coarse. Pair with layout_checks'
                        # row/column logic if a tighter per-column check is needed later.
                        if x0 < page_width * 0.5:
                            issues.append(
                                f"'{phrase}' found at x0={x0:.0f} on a page {page_width:.0f}pt wide — "
                                "expected in the right corner of its chart, found in the left half"
                            )
                        break
    return issues


def thank_you_page_absence_check(new_pdf):
    """Confirms the Thank You / closing page has actually been removed,
    per round-2 feedback. Inverse of the old closing-page-presence check."""
    issues = []
    with pdfplumber.open(new_pdf) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        if "Thank You" in full_text or "Thank you" in full_text:
            issues.append("'Thank You' text still found in the document — closing page should be fully removed, not just shortened")
    return issues


# ---------------------------------------------------------------------------
# Round-4 feedback checks (Tier A/B/C, 2026-07-01)
# ---------------------------------------------------------------------------

def header_logo_size_check(new_pdf, tolerance_pt=6):
    """Feedback: right header logo must match the left logo's height."""
    issues = []
    with pdfplumber.open(new_pdf) as pdf:
        page = pdf.pages[0]
        header_imgs = [im for im in page.images if im["top"] < 200]
        if len(header_imgs) < 2:
            issues.append(f"header: expected 2 logos near the top, found {len(header_imgs)}")
            return issues
        left  = min(header_imgs, key=lambda im: im["x0"])
        right = max(header_imgs, key=lambda im: im["x0"])
        h_left  = left["bottom"] - left["top"]
        h_right = right["bottom"] - right["top"]
        if abs(h_left - h_right) > tolerance_pt:
            issues.append(
                f"header logos: left height={h_left:.0f}pt, right height={h_right:.0f}pt "
                f"— should match within {tolerance_pt}pt"
            )
    return issues


def side_strip_two_tone_check(new_pdf, dpi=150):
    """Feedback: left strip must be black behind the header, magenta below it."""
    issues = []
    pages = convert_from_path(new_pdf, dpi=dpi)
    img = pages[0].convert("RGB")
    x = 3  # a few px into the 10pt-wide strip
    y_header = int(0.02 * img.height)   # near the very top (inside the header band)
    y_body   = int(0.30 * img.height)   # well below the header, in the magenta zone
    top_px  = img.getpixel((x, y_header))
    body_px = img.getpixel((x, y_body))
    dist = sum((a - b) ** 2 for a, b in zip(top_px, body_px)) ** 0.5
    if dist < 40:
        issues.append(
            f"side strip: top color {top_px} and body color {body_px} look too similar "
            f"(dist={dist:.0f}) — expected a black/magenta two-tone split, not one solid color"
        )
    return issues


HORIZONTAL_BAR_TITLES = ["Body Weight", "Waist to Hip Ratio"]


def horizontal_bar_yaxis_check(new_pdf):
    """Feedback: BW/WHR (horizontal bars) must show a left axis line."""
    issues = []
    with pdfplumber.open(new_pdf) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            page_lines = page.lines
            page_rects = page.rects
            title_positions = {}
            for title in HORIZONTAL_BAR_TITLES:
                tokens = title.split()
                for i in range(len(words) - len(tokens) + 1):
                    window = words[i:i + len(tokens)]
                    if all(w["text"] == tok for w, tok in zip(window, tokens)):
                        tops = [w["top"] for w in window]
                        if max(tops) - min(tops) < 5:
                            title_positions[title] = (window[0]["x0"], window[0]["top"])
                            break
            for title, (x0, top) in title_positions.items():
                # A left axis line/rect should sit near the title's left edge,
                # spanning down through the chart area below the title.
                nearby = [
                    s for s in (list(page_lines) + list(page_rects))
                    if abs(s["x0"] - x0) < 20 and s["top"] >= top and (s["top"] - top) < 250
                    and (s["bottom"] - s["top"]) > 40
                ]
                if not nearby:
                    issues.append(f"'{title}': no left axis line found near x={x0:.0f} — Y-axis may be missing")
    return issues


# Component title -> its expected unit-note badge text (report_pdf.py's
# _COMPONENT_UNIT_NOTE). If the badge is present in the DOM but gets clipped
# (e.g. by a parent with overflow-x:auto silently forcing overflow-y:auto —
# the exact bug hit 2026-07-01 when the badge was merged into the table's
# scroll wrapper), Chromium's print-to-PDF omits the clipped text entirely,
# so this is a reliable presence check, not just a position heuristic.
_HEATMAP_BADGE_BY_TITLE = {
    "Physiological Assessment 1": "COUNT PER MIN",
    "Physiological Assessment 2": "IN HH:MM:SS",
    "Balance": "IN HH:MM:SS",
}


def heatmap_unit_badge_presence_check(new_pdf):
    issues = []
    with pdfplumber.open(new_pdf) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        for title_kw, badge_text in _HEATMAP_BADGE_BY_TITLE.items():
            if title_kw in full_text and badge_text not in full_text:
                issues.append(
                    f"'{title_kw}': expected unit badge '{badge_text}' not found in extracted text — "
                    f"it may be present in the DOM but clipped (check for overflow-x set without an "
                    f"explicit overflow-y:visible on an ancestor of the badge)"
                )
    return issues


# ---------------------------------------------------------------------------
# F04-S07/F04-S09 regression checks (2026-07-04) — date-count (N) bugs that
# shipped once and had to be caught by manually rendering to PNG and looking,
# not by this script. Both are now checked directly so they can't resurface
# silently:
#   1. Bar thickness varying with N (horizontal_single: Body Weight/BMI/WHR
#      rendered at visibly different thickness depending on how many dates
#      each metric had — a chrome-band layout change silently broke the
#      inches-per-y-unit rate this was calibrated to keep constant).
#   2. Icon overlapping the unit note at low N (icon's fixed real-world size
#      became a bigger fraction of a short chart, reaching into the "In: kg"
#      text above it).
# ---------------------------------------------------------------------------

_HORIZONTAL_SINGLE_TITLES = ["Body Weight", "BMI", "Waist to Hip Ratio"]


def _find_title_positions(page, titles):
    words = page.extract_words()
    positions = {}
    for title in titles:
        tokens = title.split()
        for i in range(len(words) - len(tokens) + 1):
            window = words[i:i + len(tokens)]
            if all(w["text"] == tok for w, tok in zip(window, tokens)):
                tops = [w["top"] for w in window]
                if max(tops) - min(tops) < 5:
                    positions[title] = (window[0]["x0"], window[0]["top"])
                    break
    return positions


def bar_thickness_consistency_check(new_pdf, tolerance_pct=10):
    """All horizontal_single charts (Body Weight, BMI, Waist to Hip Ratio)
    must render bars at the same thickness regardless of each metric's own
    date count (F04-S07's invariant) — real bars are identified as filled,
    unstroked rects (fill=True, stroke=False), which excludes axis-box
    outlines and gridlines."""
    issues = []
    with pdfplumber.open(new_pdf) as pdf:
        for page in pdf.pages:
            title_positions = _find_title_positions(page, _HORIZONTAL_SINGLE_TITLES)
            if len(title_positions) < 2:
                continue

            row = [(t, (x0, top, page.page_number)) for t, (x0, top) in title_positions.items()]
            row.sort(key=lambda item: item[1][0])
            bounds = column_bounds_for_row(row, page.width)

            thicknesses = {}
            for title, (x0, top) in title_positions.items():
                left, right = bounds[title]
                bars = [
                    r for r in page.rects
                    if left <= r["x0"] and r["x1"] <= right
                    and r["top"] >= top and (r["top"] - top) < 250
                    and r["width"] > 50 and r.get("fill") and not r.get("stroke")
                ]
                if bars:
                    thicknesses[title] = bars[0]["height"]

            if len(thicknesses) < 2:
                continue
            avg = sum(thicknesses.values()) / len(thicknesses)
            for title, h in thicknesses.items():
                if abs(h - avg) / avg > tolerance_pct / 100:
                    issues.append(
                        f"'{title}': bar thickness {h:.1f}pt differs from the other horizontal "
                        f"charts' average {avg:.1f}pt by more than {tolerance_pct}% — possible "
                        f"date-count (N) inconsistency regression (F04-S07/F04-S09)"
                    )
    return issues


# icon_unit_note_overlap_check was attempted here via text search for the
# "In:" token, then dropped (2026-07-04): value labels and unit-note text
# drawn with ax.text() don't reliably extract as searchable words in the
# Puppeteer-printed PDF — tick labels and titles do, but "82", "80.5",
# "In: kg" etc. consistently do not (confirmed on both a real client report
# and the smoke_output fixture; likely Chromium's print pipeline converting
# some SVG <text> to outlined <path> on export, not something this session
# investigated further). A check built on text search for "In:" would never
# fire — worse than no check, since it reports false confidence. The real
# guard against icon/unit-note overlap is now structural instead: unit-note
# is drawn in fig.text()'s reserved chrome band ABOVE the axes, and the icon
# is anchored inside the axes near the bottom — see
# TestIconInset.test_icon_anchored_in_axes_fraction_for_n1_and_n2 in
# tests/test_chart_renderer.py for the geometric regression test. Revisit a
# PDF-level check here only after the text-extraction gap itself is
# understood — flagged as a new backlog item, not solved in this session.


def main():
    parser = argparse.ArgumentParser(description="QC a generated report PDF against a baseline sample")
    parser.add_argument("new_pdf", help="Path to the newly generated report PDF")
    parser.add_argument("baseline_pdf", help="Path to the known-good baseline sample PDF")
    parser.add_argument("--out", default="qc_out", help="Directory to save diff images")
    parser.add_argument("--threshold", type=float, default=2.0, help="Pixel-diff %% threshold to flag a page")
    parser.add_argument(
        "--baseline-pages",
        default=None,
        help="1-indexed inclusive page range of the baseline to use as content-only comparison, "
             "e.g. '2,3' to skip a cover (page 1) and closing page (page 4). "
             "Omit to use the whole baseline.",
    )
    args = parser.parse_args()

    baseline_range = None
    if args.baseline_pages:
        start, end = (int(x) for x in args.baseline_pages.split(","))
        baseline_range = (start, end)

    print(f"QC report: {args.new_pdf}")
    print(f"Baseline:  {args.baseline_pdf}")
    if baseline_range:
        print(f"Baseline page range (content-only): {baseline_range[0]}-{baseline_range[1]}")
    print()

    struct_issues, n_pages = structural_checks(args.new_pdf)
    layout_issues = layout_checks(args.new_pdf)
    render_issues = chart_render_checks(args.new_pdf)
    dup_title_issues = duplicate_title_checks(args.new_pdf)
    unit_pos_issues = unit_of_measure_position_checks(args.new_pdf)
    thank_you_issues = thank_you_page_absence_check(args.new_pdf)
    logo_size_issues = header_logo_size_check(args.new_pdf)
    strip_issues = side_strip_two_tone_check(args.new_pdf)
    yaxis_issues = horizontal_bar_yaxis_check(args.new_pdf)
    heatmap_badge_issues = heatmap_unit_badge_presence_check(args.new_pdf)
    bar_thickness_issues = bar_thickness_consistency_check(args.new_pdf)
    visual_issues = pixel_diff(
        args.new_pdf, args.baseline_pdf, args.out,
        threshold_pct=args.threshold, baseline_page_range=baseline_range,
    )

    print(f"STRUCTURAL ({len(struct_issues)} issue(s)):")
    if struct_issues:
        for issue in struct_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nDUPLICATE TITLES ({len(dup_title_issues)} issue(s)):")
    if dup_title_issues:
        for issue in dup_title_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nUNIT-OF-MEASURE POSITION ({len(unit_pos_issues)} issue(s)):")
    if unit_pos_issues:
        for issue in unit_pos_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nTHANK-YOU PAGE ({len(thank_you_issues)} issue(s)):")
    if thank_you_issues:
        for issue in thank_you_issues:
            print(f"  - {issue}")
    else:
        print("  ok (no closing page found)")

    print(f"\nLAYOUT / BUCKET MODEL ({len(layout_issues)} issue(s)):")
    if layout_issues:
        for issue in layout_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nCHART RENDER (orientation / icons / width) ({len(render_issues)} issue(s)):")
    if render_issues:
        for issue in render_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nHEADER LOGO SIZE ({len(logo_size_issues)} issue(s)):")
    if logo_size_issues:
        for issue in logo_size_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nSIDE STRIP TWO-TONE ({len(strip_issues)} issue(s)):")
    if strip_issues:
        for issue in strip_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nHORIZONTAL BAR Y-AXIS ({len(yaxis_issues)} issue(s)):")
    if yaxis_issues:
        for issue in yaxis_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nHEATMAP UNIT BADGE ({len(heatmap_badge_issues)} issue(s)):")
    if heatmap_badge_issues:
        for issue in heatmap_badge_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nBAR THICKNESS CONSISTENCY (F04-S07/F04-S09) ({len(bar_thickness_issues)} issue(s)):")
    if bar_thickness_issues:
        for issue in bar_thickness_issues:
            print(f"  - {issue}")
    else:
        print("  ok")

    print(f"\nVISUAL ({len(visual_issues)} issue(s), {n_pages} page(s) checked):")
    if visual_issues:
        for issue in visual_issues:
            print(f"  - {issue}")
    else:
        print("  ok")


if __name__ == "__main__":
    main()
