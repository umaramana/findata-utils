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
            issues.append(
                f"page {i+1}: size mismatch new={n_img.size} baseline={b_img.size} "
                f"(resized baseline to compare, take this diff with a grain of salt)"
            )
            b_img = b_img.resize(n_img.size)

        diff = ImageChops.difference(n_img, b_img)
        bbox = diff.getbbox()
        if bbox is None:
            continue

        hist = diff.histogram()
        # histogram is 256 bins per channel (R,G,B) = 768 values total
        nonzero_weighted = sum(v * (idx % 256) for idx, v in enumerate(hist))
        total_pixels = n_img.size[0] * n_img.size[1] * 3 * 255
        pct = (nonzero_weighted / total_pixels) * 100 if total_pixels else 0

        if pct >= threshold_pct:
            diff_path = os.path.join(out_dir, f"diff_page{i+1}.png")
            diff.save(diff_path)
            issues.append(
                f"page {i+1}: {pct:.2f}% pixel difference (threshold {threshold_pct}%), "
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

        # 3. Unit label presence — flag if "Units" or "measure" appears only
        # once across the whole doc (likely only on one chart, not all)
        unit_mentions = full_text.count("Units") + full_text.count("unit")
        if unit_mentions <= 1:
            issues.append(
                f"only {unit_mentions} unit-label mention(s) found across the document — "
                "expected one per chart (body weight, BMI, BP, pulse, etc.)"
            )

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

            # bucket 3 items should be full-width (similar, large x0 spread isn't directly
            # checkable from a title alone — flag for manual confirmation instead of guessing)
            issues.append(
                "note: bucket-3 full-width check is a manual confirm for now — "
                "title position alone can't confirm a heatmap spans the full content width"
            )

    return issues


EXPECTED_ORIENTATION = {
    "Body Weight": "wide",        # horizontal_single
    "Waist to Hip Ratio": "wide",  # horizontal_single
    "BMI": "wide",                 # horizontal_single
    "Blood Pressure": "tall",      # stacked_pair
    "Body Measurements": "wide",   # grouped_multi
    # Pulse intentionally excluded — it's a circular gauge/donut, not a bar.
    # Confirmed against the real Reshma sample 2026-06-30. See CIRCULAR_METRICS below.
}

CIRCULAR_METRICS = ["Pulse"]  # checked for roughly-square aspect (a circle's bbox), not wide/tall

WIDE_RATIO_THRESHOLD = 1.6  # width/height above this = "wide", below 1/1.6 = "tall"
EDGE_MARGIN_PT = 15         # how close to the page edge counts as "edge-to-edge"


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
    """Each item's column = from its own x0 to the midpoint with the next item's x0
    in the same row (or the page edge for the last item). Derived from actual
    title positions — no margin-guessing or hardcoded column-count lookup needed."""
    bounds = {}
    for i, (title, pos) in enumerate(row):
        left = pos[0]
        right = (pos[0] + row[i + 1][1][0]) / 2 if i + 1 < len(row) else page_width
        bounds[title] = (left, right)
    return bounds


def find_nearby_images(title_pos, page_images, max_vertical_gap=200):
    x0, top, _ = title_pos
    return [img for img in page_images if img["top"] >= top and (img["top"] - top) < max_vertical_gap]


def chart_render_checks(new_pdf):
    issues = []
    titles_to_check = list(EXPECTED_ORIENTATION.keys()) + CIRCULAR_METRICS

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
                        # not the bar wide/tall test.
                        curves = [
                            c for c in page_curves
                            if left <= c["x0"] and c["x1"] <= right
                            and c["top"] >= top and (c["top"] - top) < 200
                        ]
                        if not curves:
                            issues.append(
                                f"'{title}': expected a circular gauge/donut (drawn with curves) — "
                                f"found no curve shapes in its column, may be rendering as a bar instead"
                            )
                        else:
                            w_ = max(c["x1"] for c in curves) - min(c["x0"] for c in curves)
                            h_ = max(c["bottom"] for c in curves) - min(c["top"] for c in curves)
                            ratio = w_ / h_ if h_ else 0
                            if not (0.7 <= ratio <= 1.4):
                                issues.append(
                                    f"'{title}': has curve shapes but bbox isn't roughly circular "
                                    f"(w={w_:.0f}, h={h_:.0f}, ratio={ratio:.2f}) — check it's actually a donut, not a stretched shape"
                                )
                        nearby_imgs = find_nearby_images(pos, page_images)
                        if not nearby_imgs:
                            issues.append(f"'{title}': no icon image found near its title (icons are inset raster images per spec)")
                        continue

                    shapes = [
                        s for s in (list(page_rects) + list(page_lines))
                        if left <= s["x0"] and s["x1"] <= right
                        and s["top"] >= top and (s["top"] - top) < 200
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

                    nearby_imgs = find_nearby_images(pos, page_images)
                    if not nearby_imgs:
                        issues.append(f"'{title}': no icon image found near its title (icons are inset raster images per spec)")

    return issues


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

    print(f"\nVISUAL ({len(visual_issues)} issue(s), {n_pages} page(s) checked):")
    if visual_issues:
        for issue in visual_issues:
            print(f"  - {issue}")
    else:
        print("  ok")


if __name__ == "__main__":
    main()
