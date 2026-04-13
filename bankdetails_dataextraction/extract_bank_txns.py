"""
Citibank Statement OCR Extractor
Extracts checking transactions from scanned statement images using Tesseract OCR.
Outputs CSV with: Date, Description, Amount Subtracted, Amount Added, Balance

Usage:
    python extract_bank_txns.py "path/to/images/folder"
    python extract_bank_txns.py "path/to/images/folder" --output result.csv
"""

import sys
import re
import csv
import pytesseract
from PIL import Image, ImageOps
from pathlib import Path

# If Tesseract is not on PATH, uncomment and set the path below:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# Month names for banner OCR extraction
MONTHS = [
    'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
    'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'
]


def natural_sort_key(filename):
    """Sort filenames naturally so page-2 comes before page-10."""
    parts = re.split(r'(\d+)', str(filename))
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _clean_ocr_text(text):
    """Strip leading pipe/bar artifacts from page border OCR."""
    cleaned_lines = []
    for line in text.split('\n'):
        line = re.sub(r'^[|iI]\s+', '', line)
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)


def _count_txn_lines(text):
    """Count how many MM/DD lines with amounts exist in OCR text."""
    txn_re = re.compile(r'^(\d{2}/\d{2})\s+(.+)$', re.MULTILINE)
    amt_re = re.compile(r'\d{1,3}(?:,\d{3})*\.\d{2}')
    count = 0
    for m in txn_re.finditer(text):
        if amt_re.search(m.group(2)):
            count += 1
    return count


def ocr_image(image_path):
    """Run Tesseract OCR on a single image, return raw text.
    Tries PSM 6 (uniform block — better for tables) and PSM 3 (default),
    picks whichever finds more transaction lines with amounts.
    """
    img = Image.open(image_path)
    text_psm6 = _clean_ocr_text(pytesseract.image_to_string(img, config='--psm 6'))
    text_psm3 = _clean_ocr_text(pytesseract.image_to_string(img, config='--psm 3'))

    count6 = _count_txn_lines(text_psm6)
    count3 = _count_txn_lines(text_psm3)

    if count6 >= count3:
        return text_psm6
    else:
        return text_psm3


def ocr_banner(image_path):
    """
    Try to read the dark banner "BASIC BANKING PACKAGE AS OF [MONTH] ..."
    by cropping the banner region and thresholding to extract white text.
    Returns month name if found, else None.
    """
    try:
        img = Image.open(image_path)
        w, h = img.size
        # Banner is roughly at 27-34% from top, left 75% of page
        banner = img.crop((100, int(h * 0.27), int(w * 0.75), int(h * 0.34)))
        banner = banner.convert('L')
        banner = banner.point(lambda x: 255 if x > 128 else 0)
        text = pytesseract.image_to_string(banner, config='--psm 7').strip().upper()
        if 'AS' in text and 'OF' in text:
            for month in MONTHS:
                # Match even partial OCR (e.g., AUGUS for AUGUST, JULV for JULY)
                if month[:4] in text or month[:3] in text:
                    return month.capitalize()
    except Exception:
        pass
    return None


# Boilerplate markers — when we hit any of these, stop appending to description
BOILERPLATE_MARKERS = [
    'Total Subtracted', 'All transaction', 'CHECKING ACTIVITY',
    'IF YOU HAVE', 'CUSTOMER SERVICE', 'Please read', 'FDIC',
    'IN CASE OF', 'CHECKING AND SAVINGS', 'The products reported',
    'In Case of Errors', 'You are entitled', 'Give us the following',
    'The following special', 'Citibank is an Equal', 'Date Description',
    'Amount Subtracted', 'Amount Added', '© 20', 'Citigroup',
    'BASIC BANKING', 'Relationship Summary', 'Regular Checking Fees',
    'Monthly Service Fee*', 'Fee for non-Citibank', 'Beginning Balance',
    'Ending Balance', 'TTY:', 'Impaired Customers', 'Speech and Hearing',
    'packages.', 'limitations of', 'time it takes us',
    'SUGGESTIONS AND', 'EOLR', 'PAGE 00',
]

# Keywords indicating a debit (subtracted)
# Order matters — more specific patterns first to avoid false matches
DEBIT_KEYWORDS = [
    'Wire Transfer Fee', 'Incoming Wire Fee',
    'Debit Card Purchase', 'ACH Electronic Debit', 'Check #', 'Check#',
    'Recurring Card Purchase', 'Bill Payment', 'Online Payment',
    'Zelle Payment', 'Zelle Debit', 'Wire Transfer Debit', 'ATM Withdrawal',
    'Cash Withdrawal', 'Debit Pay',
    'Citibank Online Pmt', 'Transfer To', 'Transter to',
    'Outgoing Domestic', 'Domestic Funds Transfer',
    'Service Fee', 'Mobile Purchase',
    'Purchase',  # catches OCR-garbled "Debit Card Purchase"
]

# Keywords indicating a credit (added)
# Checked FIRST — more specific patterns override generic debit matches
CREDIT_KEYWORDS = [
    'Incoming Wire Transfer', 'Incoming Wire',
    'Insufficient Funds',  # returned funds — money back to account
    'ACH Electronic Credit', 'Deposit', 'Transfer From',
    'Direct Dep', 'DIRECT DEP', 'Wire Transfer Credit',
    'Zelle Credit', 'Other Credit', 'Refund', 'Interest Payment',
]


# Fuzzy OCR patterns for total-row detection (tolerates digit/letter substitutions)
_TOTAL_ROW_FUZZY_RE = [
    re.compile(r'tot[a4i]l\s+sub', re.IGNORECASE),
    re.compile(r'tot[a4i]l\s+[a4]dd', re.IGNORECASE),
]


def classify_debit_credit(description):
    """Determine if a transaction is a debit or credit from description keywords.
    Credits checked first — they contain more specific patterns that override
    generic debit matches (e.g., 'Returned Insufficient Funds - Check #').
    """
    desc_upper = description.upper()
    for kw in CREDIT_KEYWORDS:
        if kw.upper() in desc_upper:
            return 'credit'
    for kw in DEBIT_KEYWORDS:
        if kw.upper() in desc_upper:
            return 'debit'
    return 'unknown'


def is_boilerplate(line):
    """Check if a line is boilerplate text that should stop description appending."""
    for marker in BOILERPLATE_MARKERS:
        if marker.lower() in line.lower():
            return True
    # BTP-1: fuzzy match for OCR-garbled total-row labels (e.g. "Totai Subtracted")
    for pat in _TOTAL_ROW_FUZZY_RE:
        if pat.search(line):
            return True
    return False


def parse_page_totals(text):
    """
    Extract the 'Total Subtracted/Added' line from OCR text.
    Returns (total_subtracted, total_added) as floats, or (None, None) if not found.
    """
    amount_re = re.compile(r'[\d,]+\.\d{2}')
    for line in text.split('\n'):
        if 'total subtracted' in line.lower() or 'total subtracted/added' in line.lower():
            amounts = amount_re.findall(line)
            if len(amounts) >= 2:
                return float(amounts[0].replace(',', '')), float(amounts[1].replace(',', ''))
            elif len(amounts) == 1:
                # Only subtracted, no added (or vice versa)
                return float(amounts[0].replace(',', '')), 0.0
    return None, None


def _to_float(val):
    """Convert a string amount ('1,234.56') to float, or None if empty/invalid."""
    if not val:
        return None
    try:
        return float(str(val).replace(',', ''))
    except (ValueError, AttributeError):
        return None


def _try_exclude_total_row(txns, expected_sub, expected_add):
    """
    BTP-1 math check: if the sum of parsed transactions exceeds the page total
    by exactly one transaction's amount, that row is the page total row — remove it.
    Returns (filtered_txns, excluded_description or None).
    """
    if expected_sub is None or not txns:
        return txns, None

    parsed_sub = sum(_to_float(t['subtracted']) or 0 for t in txns)
    parsed_add = sum(_to_float(t['added']) or 0 for t in txns)
    excess_sub = round(parsed_sub - expected_sub, 2)
    excess_add = round(parsed_add - expected_add, 2)

    # Only proceed if we over-counted (positive excess)
    if excess_sub <= 0.02 and excess_add <= 0.02:
        return txns, None

    # Find the single row whose sub+add accounts for the entire excess
    for t in txns:
        t_sub = _to_float(t['subtracted']) or 0
        t_add = _to_float(t['added']) or 0
        if abs(t_sub - excess_sub) < 0.02 and abs(t_add - excess_add) < 0.02:
            return [x for x in txns if x is not t], t.get('description', '(no desc)')

    return txns, None


def _reconcile_and_correct(all_txns):
    """
    Walk all transactions in output order.
    For each row with a non-empty balance, verify:
        prev_balance + added - subtracted ≈ current_balance
    Flags mismatches as VERIFY — never modifies OCR'd amounts.
    Returns count of flagged rows.
    """
    flags = 0
    prev_balance = None
    prev_period = None

    for t in all_txns:
        if t.get('description', '').startswith('***'):
            continue  # skip sentinel rows

        # Reset walk at each new statement period — prevents cross-month corruption
        period = t.get('statement_period')
        if period != prev_period:
            prev_balance = None
            prev_period = period

        sub = _to_float(t['subtracted'])
        add = _to_float(t['added'])
        bal = _to_float(t['balance'])

        if bal is None:
            continue
        if prev_balance is None:
            prev_balance = bal
            continue

        expected = round(prev_balance + (add or 0) - (sub or 0), 2)
        if abs(expected - bal) <= 0.02:
            prev_balance = bal
            continue  # reconciles — no action needed

        note = t.get('flag', '')
        note += f' | VERIFY: balance does not reconcile (expected {expected:.2f}, got {bal:.2f})'
        t['flag'] = note.lstrip(' |').strip()
        prev_balance = bal
        flags += 1

    return flags


def _build_txn(description, amounts):
    """Build a transaction dict from description and list of amount strings."""
    txn_type = classify_debit_credit(description)
    amt_subtracted = ''
    amt_added = ''
    balance = ''

    if len(amounts) >= 2:
        balance = amounts[-1]
        if len(amounts) == 3:
            amt_subtracted = amounts[0]
            amt_added = amounts[1]
        elif len(amounts) == 2:
            pre_balance_amt = amounts[0]
            if txn_type == 'debit':
                amt_subtracted = pre_balance_amt
            elif txn_type == 'credit':
                amt_added = pre_balance_amt
            else:
                amt_subtracted = pre_balance_amt
                description = '[CHECK TYPE] ' + description
    elif len(amounts) == 1:
        if txn_type == 'credit':
            amt_added = amounts[0]
        elif txn_type == 'debit':
            amt_subtracted = amounts[0]
        else:
            balance = amounts[0]

    return {
        'date': '',
        'description': description,
        'subtracted': amt_subtracted,
        'added': amt_added,
        'balance': balance,
    }


def parse_transactions(text):
    """
    Parse transaction lines from OCR text.

    Transaction pattern:
      MM/DD  Description text  [Amount Subtracted]  [Amount Added]  Balance

    Amounts are like: 1,234.56 or 234.56
    A transaction line starts with MM/DD and has at least one dollar amount.
    Continuation lines (no date prefix) get ONE append to description, then stop.
    """
    transactions = []

    # Match lines starting with MM/DD or MM/DD/YY (Citi Priority format)
    txn_pattern = re.compile(r'^(\d{2}/\d{2}(?:/\d{2})?)\s+(.+)$')

    # Match dollar amounts (with optional commas), must be preceded by whitespace
    # or start of string to avoid matching inside account numbers
    amount_pattern = re.compile(r'(?:^|(?<=\s))(\d{1,3}(?:,\d{3})*\.\d{2})(?:\s|$)')

    lines = text.split('\n')
    current_txn = None
    pending_no_amounts = None  # MM/DD line with description but no amounts yet
    hit_boilerplate = False
    continuation_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for boilerplate — stop appending to current txn
        if is_boilerplate(line):
            hit_boilerplate = True
            if pending_no_amounts:
                # Had a date line with no amounts and hit boilerplate — drop it
                pending_no_amounts = None
            if current_txn:
                transactions.append(current_txn)
                current_txn = None
            continue

        match = txn_pattern.match(line)
        if match:
            # Save previous transaction
            if current_txn:
                transactions.append(current_txn)
                current_txn = None
            # Drop any unresolved pending (no amounts ever found)
            if pending_no_amounts:
                pending_no_amounts = None

            hit_boilerplate = False
            continuation_count = 0

            date = match.group(1)
            rest = match.group(2)

            # Skip balance marker rows (Citi Priority format)
            if re.match(r'(Opening|Closing)\s+Balance', rest.strip(), re.IGNORECASE):
                continue

            # Find all dollar amounts in the line
            amounts = [m.group(1) for m in amount_pattern.finditer(rest)]

            if not amounts:
                # Date line but amounts may be on next line (OCR split columns)
                description = rest.strip()
                pending_no_amounts = {'date': date, 'description': description}
                continue

            # Description is everything before the first dollar amount
            first_amt_match = amount_pattern.search(rest)
            description = rest[:first_amt_match.start()].strip()

            current_txn = _build_txn(description, amounts)
            current_txn['date'] = date

        elif pending_no_amounts:
            # Previous line had MM/DD + description but no amounts
            # This line might contain the amounts (OCR column split)
            amounts = [m.group(1) for m in amount_pattern.finditer(line)]
            if amounts:
                # Found amounts — build the transaction
                current_txn = _build_txn(pending_no_amounts['description'], amounts)
                current_txn['date'] = pending_no_amounts['date']
                pending_no_amounts = None
                continuation_count = 0
            else:
                # Still no amounts — append as description continuation
                pending_no_amounts['description'] += ' | ' + line
                # Look ahead max 1 more line
                continuation_count += 1
                if continuation_count >= 2:
                    # Give up — record without amounts
                    current_txn = _build_txn(pending_no_amounts['description'], [])
                    current_txn['date'] = pending_no_amounts['date']
                    pending_no_amounts = None

        elif current_txn and not hit_boilerplate and continuation_count < 2:
            # Allow max 2 continuation lines for description (vendor name, address)
            if not is_boilerplate(line) and len(line) < 100:
                current_txn['description'] += ' | ' + line
                continuation_count += 1

    # Don't forget the last transaction
    if pending_no_amounts:
        current_txn = _build_txn(pending_no_amounts['description'], [])
        current_txn['date'] = pending_no_amounts['date']
    if current_txn:
        transactions.append(current_txn)

    return transactions


def extract_statement_period(text):
    """Try to extract statement period/date from page text."""
    # "BASIC BANKING PACKAGE AS OF MONTH DD, YYYY"
    m = re.search(r'AS OF\s+(\w+ \d+,?\s*\d{4})', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Citi Priority format: "April 1 - April 30, 2025"
    m = re.search(
        r'((?:January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d+\s+-\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d+,\s*\d{4})',
        text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: look for "Statement Period: MM/DD/YYYY - MM/DD/YYYY" or similar
    m = re.search(r'Statement Period[:\s]+(\S+ .+?\d{4})', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def extract_year_from_text(text):
    """Try to find a year (20xx) anywhere in the page text for date context."""
    # Look for © 20XX or similar year markers
    m = re.search(r'©\s*(20\d{2})', text)
    if m:
        return int(m.group(1))
    # Look for any 4-digit year in common patterns
    m = re.search(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,?\s*(20\d{2})', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_bank_txns.py <images_folder> [--output file.csv]")
        sys.exit(1)

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Error: {folder} is not a directory")
        sys.exit(1)

    # Output file
    output_file = folder.parent / f"{folder.name}_transactions.csv"
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_file = Path(sys.argv[idx + 1])

    # Gather image files
    image_files = sorted(
        [f for f in folder.iterdir() if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.tif', '.tiff')],
        key=natural_sort_key
    )

    print(f"Found {len(image_files)} images in {folder}")

    all_transactions = []
    page_warnings = []
    current_period = "Unknown"
    current_year = None

    for i, img_path in enumerate(image_files):
        print(f"  OCR page {i+1}/{len(image_files)}: {img_path.name}...", end=' ', flush=True)
        text = ocr_image(img_path)

        # Try to detect year from any page
        if not current_year:
            yr = extract_year_from_text(text)
            if yr:
                current_year = yr

        # Check for statement period — first try normal text
        period = extract_statement_period(text)
        if not period:
            # Fallback: try reading the dark banner via image crop + threshold
            month = ocr_banner(img_path)
            if month:
                year_str = str(current_year) if current_year else ''
                period = f"{month} {year_str}".strip()
        if period:
            current_period = period
            print(f"[{current_period}]", end=' ')

        txns = parse_transactions(text)

        # If still no period and we have transactions, infer from the last txn date
        if current_period == 'Unknown' and txns and current_year:
            last_date = txns[-1]['date']  # MM/DD
            month_num = int(last_date.split('/')[0])
            month_names = ['', 'January', 'February', 'March', 'April', 'May',
                           'June', 'July', 'August', 'September', 'October',
                           'November', 'December']
            if 1 <= month_num <= 12:
                current_period = f"{month_names[month_num]} {current_year} (inferred)"
                print(f"[{current_period}]", end=' ')

        # Validate against "Total Subtracted/Added" line
        sentinel_rows = []
        if txns:
            expected_sub, expected_add = parse_page_totals(text)

            # BTP-1 math check: remove any row that accounts for the entire excess
            txns, excluded_desc = _try_exclude_total_row(txns, expected_sub, expected_add)
            if excluded_desc:
                print(f'  [BTP-1] Excluded total row: "{excluded_desc[:70]}"')

            parsed_sub = sum(_to_float(t['subtracted']) or 0 for t in txns)
            parsed_add = sum(_to_float(t['added']) or 0 for t in txns)

            if expected_sub is not None:
                sub_gap = round(expected_sub - parsed_sub, 2)
                add_gap = round(expected_add - parsed_add, 2)
                if abs(sub_gap) > 0.02 or abs(add_gap) > 0.02:
                    page_warnings.append({
                        'page': img_path.name,
                        'expected_sub': expected_sub,
                        'parsed_sub': parsed_sub,
                        'expected_add': expected_add,
                        'parsed_add': parsed_add,
                    })
                    # BTP-2: sentinel row carries the error; valid rows get no flag
                    sentinel_rows.append({
                        'statement_period': current_period,
                        'date': '',
                        'description': '*** MISSING ROWS - check page manually ***',
                        'subtracted': '{:.2f}'.format(sub_gap) if sub_gap > 0.02 else '',
                        'added': '{:.2f}'.format(add_gap) if add_gap > 0.02 else '',
                        'balance': '',
                        'flag': 'VERIFY - missing rows (sub gap: {:.2f}, add gap: {:.2f})'.format(sub_gap, add_gap),
                        'source_page': img_path.name,
                    })

        for t in txns:
            t['statement_period'] = current_period
            t['source_page'] = img_path.name
            t.setdefault('flag', '')  # BTP-2: valid rows get no error flag
        if sentinel_rows:
            txns.extend(sentinel_rows)

        all_transactions.extend(txns)
        print(f"{len(txns)} txns")

    # BTP-3/4/5/7: balance reconciliation and auto-correction pass (runs after all pages)
    corrections = _reconcile_and_correct(all_transactions)
    if corrections:
        print(f'  Balance reconciliation: flagged {corrections} transaction(s) for review.')

    if current_year:
        print(f"  Detected year from document: {current_year}")

    # Write CSV
    print(f"\nTotal transactions extracted: {len(all_transactions)}")

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'statement_period', 'date', 'description',
            'subtracted', 'added', 'balance', 'flag', 'source_page'
        ])
        writer.writeheader()
        writer.writerows(all_transactions)

    print(f"Written to: {output_file}")

    # Quick summary
    print("\n--- Summary by Statement Period ---")
    periods = {}
    for t in all_transactions:
        p = t['statement_period']
        if p not in periods:
            periods[p] = {'count': 0, 'sub': 0.0, 'add': 0.0}
        periods[p]['count'] += 1
        if t['subtracted']:
            periods[p]['sub'] += float(t['subtracted'].replace(',', ''))
        if t['added']:
            periods[p]['add'] += float(t['added'].replace(',', ''))
    for p, data in periods.items():
        print(f"  {p}: {data['count']} txns | Subtracted: ${data['sub']:,.2f} | Added: ${data['add']:,.2f}")

    # Print page warnings
    if page_warnings:
        print(f"\n*** MISSING ROWS DETECTED on {len(page_warnings)} page(s) ***")
        for w in page_warnings:
            sub_gap = w['expected_sub'] - w['parsed_sub']
            add_gap = w['expected_add'] - w['parsed_add']
            print(f"  {w['page']}:")
            print(f"    Subtracted: expected ${w['expected_sub']:,.2f}, got ${w['parsed_sub']:,.2f} (gap: ${sub_gap:,.2f})")
            print(f"    Added:      expected ${w['expected_add']:,.2f}, got ${w['parsed_add']:,.2f} (gap: ${add_gap:,.2f})")
        print("  >> Check these pages manually for overlapping/garbled text")
    else:
        print("\nAll page totals match — no missing rows detected.")


if __name__ == '__main__':
    main()
