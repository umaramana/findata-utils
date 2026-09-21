"""Turn photos/scans of tax documents (JPEG/PNG) into one-page PDFs the redactor can read.

    python img_to_pdf.py --src <folder of images> --out <folder for the PDFs>

redact.py only accepts PDFs. A converted image is an image-only page, so it goes through
`redact.py --prompt --ocr` like any other scan. The camera's EXIF rotation is applied (a phone photo taken
sideways comes out upright) and the EXIF block itself is dropped. Each PDF keeps its image's stem as its
name, so the redactor can scrub a client name out of it the way it does for any file - nothing is printed
about a file except its position and pixel size. The originals are never modified.
"""
import argparse
import io
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageOps

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
PAGE_DPI = 300  # nominal: the page is sized so the redactor's 300 DPI OCR render is 1:1 with the pixels


def image_to_pdf(src: Path, dst: Path) -> tuple:
    """Write src as a one-page PDF at dst. Returns (width_px, height_px, exif_rotated)."""
    with Image.open(src) as im:
        upright = ImageOps.exif_transpose(im)
        rotated = upright is not im and im.getexif().get(274, 1) != 1
        upright = upright.convert("RGB")
    buf = io.BytesIO()
    upright.save(buf, "JPEG", quality=92)  # drops EXIF (no exif= passed)
    w, h = upright.size
    doc = fitz.open()
    page = doc.new_page(width=w * 72 / PAGE_DPI, height=h * 72 / PAGE_DPI)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(dst, garbage=4, deflate=True)
    doc.close()
    return w, h, rotated


def main():
    ap = argparse.ArgumentParser(description="Convert JPEG/PNG document images to one-page PDFs.")
    ap.add_argument("--src", required=True, help="Folder holding the images (searched recursively)")
    ap.add_argument("--out", required=True, help="Folder for the PDFs (must differ from --src)")
    args = ap.parse_args()
    src, out = Path(args.src).resolve(), Path(args.out).resolve()
    if not src.is_dir():
        sys.exit("--src is not a folder")
    if src == out:
        sys.exit("--out must differ from --src")
    images = sorted(p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        sys.exit("No .jpg/.jpeg/.png files found under --src")
    out.mkdir(parents=True, exist_ok=True)
    used = set()
    for n, img in enumerate(images, 1):
        name, k = img.stem + ".pdf", 2
        while name.lower() in used:
            name, k = f"{img.stem}_{k}.pdf", k + 1
        used.add(name.lower())
        try:
            w, h, rotated = image_to_pdf(img, out / name)
            print(f"  #{n}: {w}x{h} px, exif rotation applied={rotated}")
        except Exception as e:  # keep going, name nothing
            print(f"  #{n}: FAILED ({type(e).__name__})")
    print(f"{len(images)} image(s) -> PDFs in --out. Next: redact.py --src <that folder> --prompt --ocr")


if __name__ == "__main__":
    main()
