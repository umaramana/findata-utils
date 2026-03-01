"""
Chase Freedom Unlimited - Mobile App Screenshot Extractor
Extracts credit card transactions from mobile app screenshot images (PNG/JPG).

Handles two layout formats:
  - List view (char*.png): date header row appears BEFORE each transaction group
  - Detail view (donations.png): date appears AFTER each transaction, followed by "Payment"

Output CSV columns: date, description, amount (plain number, no $ sign), source_page

Usage:
    python extract_freedom_txns.py "path/to/images/folder"
    python extract_freedom_txns.py "path/to/images/folder" --output result.csv
"""

import sys
import re
import csv
import pytesseract
from PIL import Image
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Handles: $18.50  -$102  -$1,501  -$299.70
AMOUNT_RE = re.compile(r'-?\$[\d,]+(?:\.\d{2})?')

# UI chrome patterns — skip these lines entirely
CHROME_RE = re.compile(
    r'freedom\s+unlimit|\(\.\.\.\d{4}\)|transactions\s*$',
    re.IGNORECASE
)


def natural_sort_key(filename):
    parts = re.split(r'(\d+)', str(filename))
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def ocr_image(image_path):
    img = Image.open(image_path)
    # Upscale 3x before OCR — screenshots are low DPI (~96), Tesseract needs ~300+
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    return pytesseract.image_to_string(img, config='--psm 6')


def _is_date_line(line):
    """
    Detect a date header or inline date line.
    Must contain a 4-digit year (20xx), no dollar amount, short, has letters.
    Handles: "Jul 10, 2025" / "Nov 2025" / "3 Dec 30, 2025" (with icon artifact prefix)
    """
    if AMOUNT_RE.search(line):
        return False
    if not re.search(r'20\d{2}', line):
        return False
    if len(line) > 25:
        return False
    if not re.search(r'[a-zA-Z]', line):
        return False
    return True


def _clean_date(raw):
    """Normalize OCR date text for storage.
    - Strip leading non-alpha chars (digit/symbol artifacts from icon)
    - Strip trailing commas/spaces
    - Insert space after day comma if missing: '24,2025' -> '24, 2025'
    - Capitalize first letter
    """
    s = re.sub(r'^[^a-zA-Z]+', '', raw).strip()         # strip leading non-alpha
    s = re.sub(r'[,\s]+$', '', s).strip()                # strip trailing commas/spaces
    s = re.sub(r'(\d),(\d)', r'\1, \2', s)               # add space: 24,2025 -> 24, 2025
    if s:
        s = s[0].upper() + s[1:]
    return s or raw.strip()


def _clean_description(text):
    """Strip leading non-alphanumeric icon artifacts (©, symbols, etc.)."""
    return re.sub(r'^[^a-zA-Z0-9]+', '', text).strip()


def _normalize_amount(raw):
    """Convert OCR amount string to plain positive number string.
    '$18.50' -> '18.50'  |  '-$1,501' -> '1501'  |  '-$299.70' -> '299.70'
    """
    return raw.replace('-', '').replace('$', '').replace(',', '').strip()


def _is_payment_line(line):
    return line.strip().lower() == 'payment'


def parse_transactions(text, source_page, last_known_date=None):
    """
    Parse transactions from OCR text of one image.

    Handles two formats automatically:
      List view:   [date header] → [merchant + amount]
      Detail view: [merchant + amount] → [inline date] → [Payment]

    Returns:
        transactions    - list of dicts {date, description, amount, source_page}
        last_known_date - last date seen (carry into next image)
    """
    transactions = []
    current_date = last_known_date

    # Pre-process: strip trailing ">" arrow artifacts, drop blank lines
    lines = []
    for ln in text.split('\n'):
        ln = re.sub(r'\s*>+\s*$', '', ln.strip()).strip()
        if ln:
            lines.append(ln)

    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip UI chrome and "Payment" labels
        if CHROME_RE.search(line) or _is_payment_line(line):
            i += 1
            continue

        # Date section header — comes before transactions (list view)
        # Only treat as section header if not immediately following an amount line
        # (inline dates are consumed in the transaction block below)
        if _is_date_line(line):
            current_date = _clean_date(line)
            i += 1
            continue

        # Transaction line: contains a dollar amount
        amt_match = AMOUNT_RE.search(line)
        if amt_match:
            amount = amt_match.group(0)
            description = _clean_description(line[:amt_match.start()])
            txn_date = current_date
            advance_to = i + 1

            # Look at next non-chrome line (don't skip Payment here — it's our signal)
            j = i + 1
            while j < len(lines) and CHROME_RE.search(lines[j]):
                j += 1

            if j < len(lines):
                nxt = lines[j]

                if _is_date_line(nxt):
                    # Could be inline date (detail view) or section header (list view).
                    # Disambiguate: if the line after the date is "Payment" → inline date.
                    k = j + 1
                    while k < len(lines) and CHROME_RE.search(lines[k]):
                        k += 1

                    if k < len(lines) and _is_payment_line(lines[k]):
                        # Detail view: inline date belongs to THIS transaction
                        txn_date = _clean_date(nxt)
                        current_date = txn_date  # carry as fallback for next txn
                        advance_to = j + 1       # skip past the inline date
                    # else: list view section header — leave it for the next iteration

                elif (not _is_payment_line(nxt)
                        and not AMOUNT_RE.search(nxt)
                        and len(nxt) <= 30
                        and re.search(r'[a-zA-Z]', nxt)):
                    # Continuation line: split merchant name (e.g. "NORTH AMER")
                    continuation = _clean_description(nxt)
                    if continuation:
                        description = (description + ' ' + continuation).strip()
                    advance_to = j + 1

            if description:
                transactions.append({
                    'date': txn_date if txn_date else 'date unknown',
                    'description': description,
                    'amount': _normalize_amount(amount),
                    'source_page': source_page,
                })

            i = advance_to
            continue

        i += 1

    return transactions, current_date


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_freedom_txns.py <images_folder> [--output file.csv]")
        sys.exit(1)

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory")
        sys.exit(1)

    output_file = folder.parent / f"{folder.name}_transactions.csv"
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_file = Path(sys.argv[idx + 1])

    image_files = sorted(
        [f for f in folder.iterdir() if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.tif', '.tiff')],
        key=natural_sort_key
    )

    print(f"Found {len(image_files)} images in {folder}")

    all_transactions = []
    last_known_date = None

    for i, img_path in enumerate(image_files):
        print(f"  OCR {i+1}/{len(image_files)}: {img_path.name}...", end=' ', flush=True)
        text = ocr_image(img_path)
        txns, last_known_date = parse_transactions(text, img_path.name, last_known_date)
        all_transactions.extend(txns)
        print(f"{len(txns)} txns")

    print(f"\nTotal transactions: {len(all_transactions)}")

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'description', 'amount', 'source_page'])
        writer.writeheader()
        writer.writerows(all_transactions)

    print(f"Written to: {output_file}")

    # Summary
    print("\n--- Summary ---")
    total_amt = 0.0
    for t in all_transactions:
        try:
            total_amt += float(t['amount'])
        except ValueError:
            pass
    print(f"  {len(all_transactions)} transactions | Total: {total_amt:,.2f}")

    unknown = sum(1 for t in all_transactions if t['date'] == 'date unknown')
    if unknown:
        print(f"  WARNING: {unknown} row(s) had no date — labeled 'date unknown'. Check manually.")


if __name__ == '__main__':
    main()
