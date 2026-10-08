"""
Page text from a statement file: text layer when the PDF has one, OCR otherwise.

    pages = file_pages(path)  ->  (list of page texts, 'text' | 'ocr')

Images (.jpg/.png/.tif) are always OCR'd. A PDF is read as text when every page
has at least MIN_TEXT_CHARS of text; if any page is below that (an image PDF),
the whole file is OCR'd so pages are not mixed between two extractors.
PyMuPDF renders the PDF pages; Tesseract does the OCR (psm 6, as the other extractors).
"""
import io
import os
import shutil
from pathlib import Path

MIN_TEXT_CHARS = 40
OCR_DPI = 200
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
_WIN_TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def configure_tesseract(pytesseract):
    """Point pytesseract at Tesseract without breaking on a machine that lacks the Windows path.
    Order: TESSERACT_CMD env var, then the Windows default if it exists, else PATH."""
    cmd = os.environ.get('TESSERACT_CMD')
    if not cmd and os.path.exists(_WIN_TESSERACT):
        cmd = _WIN_TESSERACT
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


def _ocr(img):
    import pytesseract
    configure_tesseract(pytesseract)
    return pytesseract.image_to_string(img, config='--psm 6')


def file_pages(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        from PIL import Image
        return [_ocr(Image.open(path))], 'ocr'
    if ext != '.pdf':
        raise ValueError(f'unsupported file type: {path.name}')

    import pymupdf
    with pymupdf.open(path) as doc:
        texts = [p.get_text() for p in doc]
        if texts and all(len(t.strip()) >= MIN_TEXT_CHARS for t in texts):
            return texts, 'text'
        from PIL import Image
        zoom = OCR_DPI / 72
        out = []
        for p in doc:
            pix = p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            out.append(_ocr(Image.open(io.BytesIO(pix.tobytes('png')))))
        return out, 'ocr'
