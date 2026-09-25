"""RASRICH PDF Redactor — local SSN + name redaction for a folder of PDFs.

Usage:
    python redact.py --input ./docs --output ./redacted --names "John Smith, Jane Doe"
    python redact.py --input ./docs --output ./redacted --names "John Smith" --ssns "123-45-6789"

Detection uses pdfplumber (text + positions) plus PyMuPDF's own text reader
as a second detector — PyMuPDF reads sideways text (landscape schedules on
portrait pages) that pdfplumber scrambles. Redaction uses PyMuPDF, which
removes the underlying text (not just a black box drawn over it). Originals
are never modified. Fully local — no network calls.

Reconciliation: after redacting, every output file is re-read and checked for
any remaining SSN / name text. Files with no text layer (scans) are flagged
because they cannot be redacted without OCR. Exit code is 1 if any file fails.
"""
import argparse
import datetime
import io
import re
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber

try:
    from . import redact_ocr  # imported as redactor.redact
except ImportError:
    import redact_ocr  # run as a script from this folder

# Tolerates a line break after either hyphen ("123-45-\n6789").
SSN_RE = re.compile(r"(?<!\d)\d{3}-\s*\d{2}-\s*\d{4}(?!\d)")

# Employer/payer EIN, ##-####### grouping (distinct from SSN's 3-2-4), same
# line-break tolerance. Structural, catches unknown EINs same as SSN_RE does
# for unknown SSNs - no name/EIN list needs to be passed in.
EIN_RE = re.compile(r"(?<!\d)\d{2}-\s*\d{7}(?!\d)")

# Any standalone run of exactly 9 digits: an SSN or EIN printed with no dashes (some W-2s print the employer
# EIN as 123456789). Not part of a longer number, and not a whole-dollar figure with a decimal ("123456789.50")
# or thousands group. Also redacts 9-digit account numbers and CUSIPs, which no check needs.
NINE_RE = re.compile(r"(?<![\d.,$-])\d{9}(?!\d)(?![.,]\d)")

# US phone numbers, only when laid out as one: 555-123-4567, (555) 123-4567, (555)123-4567, +1 555-123-4567,
# 1-555-123-4567. A bare 10-digit run (5551234567) or dots/spaces only (555.123.4567) is left alone - account
# numbers and other IDs look the same. A phone number the user enters is matched in any format (see build_patterns).
PHONE_RE = re.compile(r"(?<![\d-])(?:\+?1[\s-])?(?:\(\d{3}\)\s?|\d{3}-)\d{3}-\d{4}(?![\d-])")

# Every email address, whoever it belongs to.
EMAIL_RE = re.compile(r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")

# Indian PAN (also Karvy/CAMS investor IDs): 5 letters, 4 digits, 1 letter; the 4th letter is the holder type
# (P person, C company, H HUF, F firm, A AOP, T trust, B BOI, L local authority, J juridical, G government).
PAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z](?![A-Za-z0-9])")

# Aadhaar as printed: #### #### #### (or dashes), first digit 2-9. Spaces only, not line breaks, and not three
# years in a row ("2024 2023 2022" column headers). An unspaced one is caught by LONGNUM.
AADHAAR_RE = re.compile(r"(?<![\d-])(?!(?:(?:19|20)\d\d[ -]){2}(?:19|20)\d\d)[2-9]\d{3}([ -])\d{4}\1\d{4}(?![\d-])")

# California employer account number (W-2 box 15 "Employer's state ID number"): ###-####-#.
CA_EMPLOYER_ID_RE = re.compile(r"(?<![\d-])\d{3}-\d{4}-\d(?![\d-])")

# A bare run of 11-18 digits: a bank/brokerage account (ICICI is 12+), an unspaced Aadhaar, a card number.
# Dollar amounts carry commas or decimals, so they don't qualify. 10 digits is left alone (see PHONE_RE); 9 is
# ID9. The last 4 digits stay visible (group "v" is the rest) so a 1099 can still be matched to its account.
LONGNUM_RE = re.compile(r"(?<![\d.,$-])(?P<v>\d{7,14})\d{4}(?!\d)(?![.,]\d)")

# A number printed right after an account label. Same gap rule as DOB_LABEL_RE (punctuation, whitespace, a short
# bracketed hint like "(see instructions)"), so it cannot reach past a blacked-out value to the next number. A
# value may mix digits with mask characters and single spaces/dashes ("XXXX-1234", "1234 5678 9012"). 8+
# characters: all but the last 4 digits are blacked out; 5-7: all of it. A 4-character value is left alone: it is
# what a redacted long one leaves behind, and 4 digits identify nothing.
_ACCT_LABEL = (r"(?<![a-z])(?:account\s*(?:number|num\b|no\b\.?|#)|acct\b\.?\s*(?:number|no\b\.?|#)?"
               r"|a/c\s*(?:number|no\b\.?|#)?|folio\s*(?:number|no\b\.?|#)?)"
               r"[\s:#.\-]*(?:\([^)\d]{0,20}\)[\s:#.\-]*)?")
_ACCT_CH = r"[\dXx*•]"
ACCT_LONG_RE = re.compile(_ACCT_LABEL + rf"(?P<v>{_ACCT_CH}(?:[ -]?{_ACCT_CH}){{3,15}})(?:[ -]?\d){{4}}"
                          rf"(?![ -]?{_ACCT_CH})(?!\w)", re.IGNORECASE)
ACCT_SHORT_RE = re.compile(_ACCT_LABEL + rf"(?P<v>{_ACCT_CH}(?:[ -]?{_ACCT_CH}){{4,6}})(?![ -]?{_ACCT_CH})(?!\w)",
                           re.IGNORECASE)

# 9 digits right after an EIN label, in any spacing ("EIN 12 3456789"); ##-####### and 123456789 are EIN/ID9.
EIN_LABEL_RE = re.compile(r"(?<![a-z])(?:f?ein\b|employer(?:'s)?\s+(?:identification\s+number|id\b(?:\s*(?:number|no\b\.?))?))"
                          r"[\s:#.\-]*(?:\([^)\d]{0,20}\)[\s:#.\-]*)?(?P<v>\d(?:[ -]?\d){8})(?!\d)", re.IGNORECASE)

# US street address lines, redacted whoever they belong to (client, payer, bank, employer):
#   street:  "1234 N Main St Apt 5", "55 WEST 5TH AVENUE" - a house number, 1-4 capitalised words on the same
#            line, then a street suffix written Title-case or UPPER (so sentence-case form text doesn't match)
#   PO box:  "PO Box 123", "P.O. BOX 123"
#   city:    "San Diego, CA 92121", "SAN DIEGO CA 92121-1234" - capitalised words, state code, ZIP; one line
#            break allowed between each. The first word has 2+ letters: a lone capital is a checkbox "X" or an
#            initial, and after redaction it can land next to a state code + 5 digits that were never an address
# An address outside the US, or a US one in another layout, is caught only if the user enters it.
_SUFFIXES = ("Street", "St", "Avenue", "Ave", "Av", "Road", "Rd", "Boulevard", "Blvd", "Drive", "Dr", "Lane", "Ln",
             "Court", "Ct", "Circle", "Cir", "Way", "Place", "Pl", "Terrace", "Ter", "Parkway", "Pkwy", "Highway",
             "Hwy", "Trail", "Trl", "Square", "Sq", "Plaza", "Plz", "Loop", "Pike", "Cove", "Cv", "Crossing", "Xing",
             "Run", "Walk", "Row", "Path", "Glen", "Heights", "Hts", "Ridge", "Commons", "Crescent", "Cres", "Close",
             "Grove", "Gardens", "Manor", "Mews", "Hollow", "Pass", "Point", "Pt", "Park", "View", "Vista", "Alley",
             "Bend", "Creek", "Hill", "Knoll", "Landing", "Meadows", "Meadow", "Oval", "Summit", "Turnpike", "Tpke",
             "Estates", "Harbor", "Station", "Village", "Junction", "Expressway", "Expy", "Freeway", "Fwy")
_SUFFIX = "|".join(s for x in _SUFFIXES for s in (x, x.upper()))
_STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
           "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI").split()
_UNIT = r"(?:[ \t]*,?[ \t]*(?:Apt|APT|Unit|UNIT|Suite|SUITE|Ste|STE|#)\.?[ \t]*#?[ \t]*[A-Za-z0-9-]+)?"
STREET_RE = re.compile(rf"(?<![\w-])\d{{1,6}}[A-Za-z]?(?:[ \t]+[A-Z0-9][\w.'-]*){{1,4}}?[ \t]+(?:{_SUFFIX})\b\.?"
                       rf"(?:[ \t]+(?:[NS][EW]|[NSEW])\b\.?)?{_UNIT}")
PO_BOX_RE = re.compile(r"(?<![A-Za-z])P\.?[ \t]*O\.?[ \t]*(?:Box|BOX)[ \t]+\d+", re.IGNORECASE)
_GAP = r"(?:,?[ \t]*\n[ \t]*|,?[ \t]+)"  # same line, or one line break (1040 header: city, state, ZIP on 3 lines)
CITY_STATE_ZIP_RE = re.compile(rf"(?<![\w-])[A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]*){{0,3}}{_GAP}"
                               rf"(?:{'|'.join(_STATES)}){_GAP}\d{{5}}(?:-\d{{4}})?(?![\d.,]?\d)")

# India addresses. Anchors: an Indian state or "India" next to a 6-digit PIN code (also printed "411 001"), a state
# followed by "India", or a capitalised place name + comma/dash + PIN ("Kothrud - 411038", "Nasik, 422002"). A
# state, "India" or a 6-digit number alone is NOT enough, nor an ID word + PIN ("Invoice - 123456", "Folio No -
# 556677"). Everything before the anchor on the same line goes too, however long (flat, street, area, city) -
# except that it starts after a dollar amount ("$", "12,345", "99.50") or a colon, so an amount column or a
# "Property:" label printed on the same line survives. "PIN"/"Pincode"/"Postal code" + 6 digits too (also the IRS 6-digit Identity Protection PIN).
_IN_STATES = ("Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
              "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
              "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Orissa", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
              "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "New Delhi", "Delhi",
              "Jammu and Kashmir", "Ladakh", "Puducherry", "Pondicherry", "Chandigarh")
_IN_STATE = "|".join(r"[ \t]+".join(w.split()) for w in _IN_STATES)
_PIN = r"[1-9]\d{2}[ \t]?\d{3}(?!\d)"
_IN_SEP = r"[ \t,.\-]*"
_ID_WORDS = r"(?:No|Ref|Invoice|Inv|Folio|Order|Account|Acct|Receipt|Bill|Policy|Id|Code|Page|Total|Box|Line|Form|Pin)"
_AMOUNT = r"(?:\$|\d{1,3}(?:,\d{3})+|\d\.\d\d\b)"
IN_ADDRESS_RE = re.compile(rf"(?<!\S)(?:(?!{_AMOUNT})[^\n:])*?"
                           rf"(?:(?:{_IN_STATE}){_IN_SEP}(?:India{_IN_SEP})?{_PIN}(?:{_IN_SEP}India\b)?"
                           rf"|(?:{_IN_STATE}){_IN_SEP}India\b(?:{_IN_SEP}{_PIN})?"
                           rf"|{_PIN}{_IN_SEP}India\b|India{_IN_SEP}{_PIN}"
                           rf"|(?!{_ID_WORDS}\b)(?-i:[A-Z][A-Za-z.]+)[ \t]*[,\-–][ \t]*{_PIN})", re.IGNORECASE)
PIN_LABEL_RE = re.compile(rf"(?<![a-z])(?:pin[ \t]*code|pincode|pin\b|postal[ \t]+code)[\s:.#\-]*(?P<v>{_PIN})", re.IGNORECASE)

# The line after an address label, when it reads like an address. Many forms print the value on the line below
# its label (Form 8938 "...room or suite no." / "...ZIP or foreign postal code", "Employee's address and ZIP
# code", "Street address"); a street with no house number ("Shivaji Chowk, Kasturba Rd") has no shape a rule
# could spot on its own. Label line: any line containing "address", "suite no.", "postal code" or "ZIP code".
# Next line reads like an address when it has a comma, or a number followed by more words, and it is not the
# form's own wording: it does not start with Form/Part/Schedule/Page/Line/See/If/For/Check/Type/Enter, has
# fewer than 3 lower-case words of 3+ letters (form text is sentence case), and holds no dollar amount. An
# empty field is followed by form text, a bare line number, or the next field's number and label ("12  State",
# "14  ZIP/Postal Code", or a row of them: 1-2 digits, then words with no comma or digit), so nothing goes. A street written
# that way ("12 Shivaji Chowk") is then caught only by STREET_RE (needs a suffix) or if the user enters it.
_ADDR_LABEL_LINE = r"(?i:address|suite\s+no\.|postal\s+code|zip\s+code)[^\n]*\n[ \t]*"
ADDRESS_NEXT_LINE_RE = re.compile(
    _ADDR_LABEL_LINE
    + r"(?P<v>(?!(?i:Form|Part|Schedule|Page|Line|See|If|For|Check|Type|Enter)\b)"
    + r"(?!(?:\d{1,2}[A-Za-z]?[ \t]+[^\d,\n]+)+(?:\n|$))"
    + r"(?=[^\n]*?(?:\d[^\n]*?[ \t]\S|,))"
    + r"(?![^\n]*?(?:\b[a-z]{3,}\b[^\n]*?){3})"
    + rf"(?![^\n]*?{_AMOUNT})"
    + r"[^\n]*\S)")

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")
_ANY_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?"
_ORD = r"(?:st|nd|rd|th)?"
_ANY_DATE = (r"(?:\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*(?:\d{4}|\d{2})"   # 01/15/1980, 1-15-80, 15.01.1980
             r"|\d{4}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*\d{1,2}"                # 1980-01-15
             rf"|{_ANY_MONTH}\s*\d{{1,2}}{_ORD},?\s*'?\d{{2,4}}"          # Jan 15, 1980
             rf"|\d{{1,2}}{_ORD}[\s-]*{_ANY_MONTH},?[\s-]*'?\d{{2,4}})")  # 15-Jan-1980
# A date printed right after a date-of-birth label: only punctuation, whitespace (incl. a line break) and a
# bracketed format hint like "(MM/DD/YYYY)" may sit between. Anything wider would reach past a blacked-out DOB to
# the next date on the line ("DOB: <gone>  Sold 07/22/2024"). Only the date (group "v") is blacked out. "Born"
# is deliberately not a label: the 1040 prints "born before January 2, 1961". A birth date that is not right
# after one of these labels is caught only if the user enters it.
DOB_LABEL_RE = re.compile(r"(?<![a-z])(?:date\s+of\s+birth|birth\s*date|d\.?\s?o\.?\s?b\b\.?)"
                          r"[\s:#.\-]*(?:\([^)\d]{0,20}\)[\s:#.\-]*)?"
                          rf"(?P<v>(?<!\d){_ANY_DATE}(?!\d))", re.IGNORECASE)

# Third-party designee PIN / Self-select PIN: 5 digits right after a "PIN" label, same or next line (1040 p2:
# "Personal identification number (PIN)" with the value below). 6 digits after PIN is PIN_LABEL_RE.
PIN5_RE = re.compile(r"(?<![A-Za-z])PIN\)?[\s:.#\-]*(?P<v>\d{5})(?![\d.,-]?\d)")

# Preparer tax identification number: P + 8 digits as its own word. Printed wherever a paid preparer signs.
PTIN_RE = re.compile(r"(?<![A-Za-z0-9])P\d{8}(?![A-Za-z0-9])")

# 10 bare digits right after a phone label (NC D-400 "PN 5551234567"); a punctuated US phone is PHONE_RE. 10
# digits without a label stay (an order or invoice number).
PHONE_LABEL_RE = re.compile(r"(?<![A-Za-z])(?:phone|telephone|ph|pn|tel|mobile|cell)\b\.?(?:\s*(?:no\b\.?|number|#))?"
                            r"[\s:#.\-]*(?:\([^)\d]{0,30}\)[\s:#.\-]*)?(?P<v>\d{10})(?!\d)", re.IGNORECASE)

# A PAN with some of its 4 digits masked ("ABCPE123XF", 2+ real digits), and whatever is joined to a PAN by "&"
# (a second holder's PAN, possibly cut short: "ABCPE1234F & XYZH"). A PAN cut short (no final letter, fewer
# digits) only right after a "PAN" label: 5 letters + digits alone is also a form or product code.
_PAN_CORE = r"[A-Z]{3}[ABCFGHJLPT][A-Z](?=(?:[Xx*]*\d){2})[\dXx*]{4}[A-Z]"
PAN_LOOSE_RE = re.compile(rf"(?<![A-Za-z0-9]){_PAN_CORE}(?:[ \t]*&[ \t]*[A-Z0-9Xx*]{{3,10}})?(?![A-Za-z0-9])")
PAN_LABEL_RE = re.compile(r"(?<![A-Za-z])PAN\b[\s:#.\-]*(?:no\b\.?|number)?[\s:#.\-]*"
                          r"(?P<v>[A-Z]{3,5}[\dXx*]{2,4}[A-Z]?)(?![A-Za-z0-9])", re.IGNORECASE)

# Ages after an "Age" / "Ages" label and a colon, optionally dated ("Age on 12/31/2024: 45 43"). The colon keeps
# form wording ("if age 65 or older") out.
AGE_RE = re.compile(r"(?<![A-Za-z])Ages?(?:\s+(?:on|as\s+of|at)\s+\d{1,2}/\d{1,2}/\d{2,4})?[ \t]*:[ \t]*"
                    r"(?P<v>\d{1,3}(?:[ \t,&]+\d{1,3}){0,3})(?![\d.,/])", re.IGNORECASE)

# An account number in a table: a header line holding "Account number" and more column titles, the value in the
# row below (CA 540 refund: "Type  Routing number  Account number  Direct deposit amount", then "Checking
# <routing> 12345678 1,234.00"). The first bare run of 5-17 digits within the next 3 lines, not part of an amount
# or a dashed number; 8+ digits keep their last 4 like ACCT_LONG_RE.
_ACCT_END = r"(?![\d.,-]?\d)(?!-)"
ACCT_TABLE_RE = re.compile(r"(?i:account\s+number)[^\n]*\n(?:[^\n]*\n){0,2}?[^\n\d]*?(?<![\d.,$-])"
                           rf"(?P<v>\d{{4,13}}(?=\d{{4}}{_ACCT_END})|\d{{5,7}}{_ACCT_END})")

# Redacted in every document, whatever the user enters. Labels never contain a value.
ALWAYS_PATTERNS = (("SSN", SSN_RE), ("EIN", EIN_RE), ("ID9", NINE_RE), ("PHONE", PHONE_RE), ("EMAIL", EMAIL_RE),
                   ("DOB", DOB_LABEL_RE), ("PAN", PAN_RE), ("AADHAAR", AADHAAR_RE), ("CA-EMPLOYER-ID", CA_EMPLOYER_ID_RE),
                   ("LONGNUM", LONGNUM_RE), ("ACCT", ACCT_LONG_RE), ("ACCT", ACCT_SHORT_RE), ("EIN", EIN_LABEL_RE),
                   ("ADDRESS", STREET_RE), ("ADDRESS", PO_BOX_RE), ("ADDRESS", CITY_STATE_ZIP_RE),
                   ("ADDRESS", IN_ADDRESS_RE), ("ADDRESS", PIN_LABEL_RE),
                   ("ADDRESS", ADDRESS_NEXT_LINE_RE), ("PIN", PIN5_RE), ("PTIN", PTIN_RE),
                   ("PHONE", PHONE_LABEL_RE), ("PAN", PAN_LOOSE_RE), ("PAN", PAN_LABEL_RE), ("AGE", AGE_RE),
                   ("ACCT", ACCT_TABLE_RE))

MASK = r"[Xx*#•]"


def parse_date(text):
    """(year, month, day) if text is a whole date in a common written form, else None.

    Numeric dates are read US-style (month first) unless the first number cannot be a month. The
    redaction pattern covers the day-first reading as well (dob_pattern), so the order only matters
    for invalid dates. Two-digit years are 19xx unless that would be in the future."""
    t = " ".join(text.split())
    parts = None
    if m := re.fullmatch(r"(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4}|\d{2})", t):
        mo, d, y = map(int, m.groups())
        parts = (y, d, mo) if mo > 12 else (y, mo, d)
    elif m := re.fullmatch(r"(\d{4})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})", t):
        parts = tuple(map(int, m.groups()))
    elif m := re.fullmatch(rf"({_ANY_MONTH})\s*(\d{{1,2}}){_ORD},?\s*'?(\d{{4}}|\d{{2}})", t, re.I):
        parts = (int(m[3]), m[1], int(m[2]))
    elif m := re.fullmatch(rf"(\d{{1,2}}){_ORD}[\s-]*({_ANY_MONTH}),?[\s-]*'?(\d{{4}}|\d{{2}})", t, re.I):
        parts = (int(m[3]), m[2], int(m[1]))
    if parts is None:
        return None
    y, mo, d = parts
    if isinstance(mo, str):
        mo = next((i for i, name in enumerate(_MONTHS, 1) if name.startswith(mo.lower().rstrip(".")[:3])), 0)
    if y < 100:
        y += 1900 if y > datetime.date.today().year % 100 else 2000
    try:
        datetime.date(y, mo, d)
    except ValueError:
        return None
    return y, mo, d


def dob_pattern(y, m, d):
    """One regex for a known birth date in every common written form: 01/15/1980, 1/15/80, 01-15-1980,
    1.15.80, 1980-01-15, Jan 15, 1980, January 15th 1980, 15-Jan-1980, and the day-first 15/01/1980."""
    M, D, Y = rf"0?{m}", rf"0?{d}", rf"(?:{y}|'?{y % 100:02d})"
    S = r"\s*[/.-]\s*"
    full = _MONTHS[m - 1]
    mon = rf"(?:{full}|{full[:3]}{'t?' if m == 9 else ''}\.?)"
    forms = [f"{M}{S}{D}{S}{Y}", f"{D}{S}{M}{S}{Y}", f"{y}{S}{M}{S}{D}",
             rf"{mon}\s*{D}{_ORD},?\s*{Y}", rf"{D}{_ORD}[\s-]*{mon},?[\s-]*{Y}"]
    return re.compile(r"(?<![\d/.-])(?:" + "|".join(forms) + r")(?!\d)", re.IGNORECASE)


def phone_digits(text):
    """The 10 digits of a US phone number written in any format, else None."""
    if not re.fullmatch(r"[\d\s().+-]+", text):
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def classify_entry(text):
    """What a user-entered line is: ("ssn", digits) / ("phone", digits) / ("dob", (y, m, d)) /
    ("email", text) / ("number", digits) / ("name", text). "number" is any other run of 4+ digits (an account
    number) with optional spaces/dashes. "name" covers addresses and anything else matched literally."""
    t = text.strip()
    if EMAIL_RE.fullmatch(t):
        return "email", t
    if re.fullmatch(r"\d{3}[\s-]?\d{2}[\s-]?\d{4}", t):
        return "ssn", re.sub(r"\D", "", t)
    if digits := phone_digits(t):
        return "phone", digits
    if ymd := parse_date(t):
        return "dob", ymd
    if re.fullmatch(r"[\d\s-]+", t) and len(digits := re.sub(r"\D", "", t)) >= 4:
        return "number", digits
    return "name", t


def _clean_tokens(text):
    return [t for t in (re.sub(r"[.,]", "", w) for w in text.split()) if t]


def _word_rx(word):
    return r"(?:-\s+)?".join(map(re.escape, word))  # a word may be hyphenated across a line break


def _atom_rx(atom):
    kind, val = atom
    if kind == "w":  # a whole name part (a tuple of words: a multi-word surname is one atom)
        return r"\s+".join(_word_rx(w) for w in val)
    if kind == "i":  # an initial, period optional
        return re.escape(val) + r"\.?"
    return r"(?:[A-Za-z]\.?(?:\s+|(?<=\.)))?"  # "o": optional single-letter middle initial, with its own separator


def _form_rx(atoms, reversed_order=False):
    parts = []
    for n, atom in enumerate(atoms):
        if n and atoms[n - 1][0] != "o":
            if reversed_order and n == 1:
                parts.append(r"(?:\s*,\s*|\s+)")          # "Smith, John" / "Smith John"
            elif atoms[n - 1][0] == "i":
                parts.append(r"(?:\s+|(?<=\.))")           # "J. Smith" / "J.Smith"
            else:
                parts.append(r"\s+")
        parts.append(_atom_rx(atom))
    return re.compile(r"(?<!\w)" + "".join(parts) + r"(?!\w)", re.IGNORECASE)


def name_variant_patterns(name):
    """Other written forms of the SAME person's name, as regexes.

    "Robert Alan Smith" also matches: Robert Smith / Robert A Smith / Robert A. Smith / R. Smith /
    R A Smith / Smith, Robert / Smith Robert Alan / Smith, R. - any case. If the entry has no middle
    name, "Robert J. Smith" (one middle initial) matches too.

    Deliberately NOT included: a first or last name on its own. Those also match other people
    ("Mary Smith"), and the redactor keeps look-alikes. Entries containing a digit (addresses) or
    a single word are left literal.
    """
    if re.search(r"\d", name):
        return []
    if "," in name:  # "Smith, Robert A"
        left, _, right = name.partition(",")
        last, given = tuple(_clean_tokens(left)), _clean_tokens(right)
    else:
        toks = _clean_tokens(name)
        last, given = (toks[-1],) if toks else (), toks[:-1]
    if not last or not given:
        return []
    first, mids = given[0], given[1:]
    F, L = ("w", (first,)), ("w", last)
    ini = lambda w: ("i", w[0])
    middles, initials = [("w", (m,)) for m in mids], [ini(m) for m in mids]
    forward = [[F, L], [ini(first), L]]
    backward = [[L, F], [L, ini(first)]]
    if mids:
        forward += [[F, *initials, L], [ini(first), *initials, L]]
        backward += [[L, F, *middles], [L, F, *initials], [L, ini(first), *initials]]
    else:
        forward.append([F, ("o", ""), L])
    return [_form_rx(a) for a in forward] + [_form_rx(a, reversed_order=True) for a in backward]


_ENTRY_SEP = r"[\s,.;:/#()&'\-]"


def loose_entry_rx(entry):
    """The entry with its punctuation ignored: "Flat 4B, Sai Apts., M.G. Road, Pune - 411001" also matches
    "Flat 4B Sai Apts MG Road Pune 411 001" and "Flat 4B,Sai Apts, M G Road,Pune,411001". Words keep their
    order; commas, periods, dashes, slashes, # and brackets between them may be missing, extra or different.
    Two words need at least one separator; next to a number or between two initials none is needed
    ("4B", "No.12", "M.G." = "MG"). A number may
    carry one space ("411 001"). None for a one-word entry (a single word would match too much)."""
    tokens = re.findall(r"[A-Za-z0-9]+", entry)
    if len(tokens) < 2:
        return None
    rx = []
    for n, tok in enumerate(tokens):
        if n:
            glued = any(c.isdigit() for c in tokens[n - 1] + tok) or len(tokens[n - 1]) == len(tok) == 1
            rx.append(_ENTRY_SEP + ("*" if glued else "+"))
        rx.append(r"\s?".join(tok) if tok.isdigit() else _word_rx(tok))
    return re.compile(r"(?<![A-Za-z0-9])" + "".join(rx) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def name_controls(name):
    """IRS name controls a person's name may print as: the first 4 letters of the name from each word on, in
    capitals ("John Smith" -> JOHN, SMIT; "Maria De La Cruz" -> also DELA, LACR). Which word is the surname
    is not known, so every start is taken. Fewer than 4 letters from a word on is skipped: a 2-3 letter
    fragment matches too much (user decision 24 Sep). Entries with a digit (addresses) or one word: none."""
    if re.search(r"\d", name):
        return []
    words = [re.sub(r"[^A-Za-z]", "", w) for w in name.split()]
    words = [w for w in words if w]
    if len(words) < 2:
        return []
    return list(dict.fromkeys(("".join(words[i:])[:4]).upper() for i in range(len(words))
                              if len("".join(words[i:])) >= 4))


_US_STATE_RX = rf"\b(?:{'|'.join(_STATES)})\b"
_POSTAL_RX = r"(?<![\dA-Za-z])(?:\d{5}(?:-\d{4})?|[1-9]\d{2} ?\d{3})(?![\dA-Za-z])"


def address_parts(entry):
    """(house number, postal codes, city) of an entered address, any of them None/empty when not found.

    Parts are split at commas, semicolons and " - ". Postal code: a 5-digit ZIP (optional -4) or a 6-digit
    India PIN ("411 001" too). City: the last part after the first that is left with 1-3 words and no digit
    once its postal code, US state code, Indian state and "India" are removed ("Cary, NC 27513",
    "Kothrud - 411038"); with no separators, the word before a state code + ZIP. House number: the first
    token of the first part that holds a digit ("4471", "12B", "4B" in "Flat 4B")."""
    parts = [p.strip() for p in re.split(r"[,;]|\s[-–]\s", entry) if p.strip()]
    # not in the first part, which starts with the house number ("12345 Oak St"); with no separators, not at the start
    tail = " ".join(parts[1:]) if len(parts) > 1 else re.sub(r"^\s*\S+", "", entry)
    postal = [re.sub(r"\D", "", z)[:5] if "-" in z or len(re.sub(r"\D", "", z)) == 5 else re.sub(r"\D", "", z)
              for z in re.findall(_POSTAL_RX, tail)]
    city = None
    for part in reversed(parts[1:]):
        rest = re.sub(_POSTAL_RX, " ", part)
        rest = re.sub(_US_STATE_RX, " ", rest)
        rest = re.sub(rf"(?i)\b(?:{_IN_STATE}|India)\b", " ", rest).strip(" .-")
        if rest and not re.search(r"\d", rest) and len(rest.split()) <= 3:
            city = rest
            break
    if city is None and len(parts) == 1:
        m = re.search(rf"([A-Za-z][A-Za-z.'-]+)[ \t]+{_US_STATE_RX}[ \t]+\d{{5}}", entry)
        city = m[1] if m else None
    house = next((t for t in parts[0].split() if re.search(r"\d", t) and re.fullmatch(r"\d{1,6}[A-Za-z]?", t)),
                 None) if parts else None
    return house, postal, city


def address_part_patterns(entry):
    """Pieces of an entered address matched on their own, for layouts that repeat them without the rest (a
    state form's machine-readable scan line: "SMIT 4471 27540 HOLLY SPRINGS"). The postal code and the city go
    wherever they appear (city as whole words, any case). The house number goes only on a line that also
    holds that postal code or city: alone it is just a number ("Line 12"). Nothing for an entry with no
    digit (a name)."""
    if not re.search(r"\d", entry):
        return []
    house, postal, city = address_parts(entry)
    pats, anchors = [], []
    for z in postal:
        rx = (rf"{z}(?:-?\d{{4}})?" if len(z) == 5 else rf"{z[:3]} ?{z[3:]}")
        anchors.append(rx)
        pats.append(re.compile(rf"(?<![\d.,$-]){rx}(?!\d)(?![.,]\d)"))
    if city and len(re.sub(r"[^A-Za-z]", "", city)) >= 3:
        rx = r"\s+".join(_word_rx(w) for w in city.split())
        anchors.append(rx)
        pats.append(re.compile(rf"(?<![A-Za-z]){rx}(?![A-Za-z])", re.IGNORECASE))
    if house and anchors:
        anchor = rf"(?<![A-Za-z\d])(?i:{'|'.join(anchors)})(?![A-Za-z\d])"
        h = rf"(?<![\w.,$-])(?P<v>{re.escape(house)})(?![\w]|[.,]\d)"
        pats.append(re.compile(rf"{h}(?=[^\n]{{0,80}}?{anchor})"))
        pats.append(re.compile(rf"{anchor}[^\n]{{0,80}}?{h}"))
    return pats


def build_patterns(names, ssns=()):
    """SSN, EIN and 9-digit patterns + known-SSN patterns + one case-insensitive pattern per name.

    Known SSNs match in any separator style (123-45-6789, 123 45 6789,
    123456789) and as masked last-4 (XXX-XX-6789, ***-**-6789). Labels never
    contain the SSN itself, so console output stays safe to share.

    Name tokens may be separated by any whitespace (incl. line breaks), and a
    token may be hyphenated across a line break ("Smi-\\nth"). Each name also gets
    the other ways the same person's name is written - reordered, initials, a
    middle initial (see name_variant_patterns).

    An entered account number (4+ digits, classify_entry "number") is matched with any spaces/dashes (NUM#n);
    8+ digits keep their last 4 visible, like LONGNUM and the account-label rule.

    Every phone number in US layout (PHONE), every email address (EMAIL) and any date next to a
    date-of-birth label (DOB) are always redacted. An entry in `names` that is a date, a phone number
    or an SSN (classify_entry) is not treated as a name: a date becomes a known birth date matched in
    every written form (DOB#n), a phone number is matched in any format incl. bare digits (PHONE#n),
    an SSN joins `ssns`, and an email adds nothing (EMAIL covers it). Their labels never contain the value.
    """
    patterns = list(ALWAYS_PATTERNS)
    ssns, plain_names, n_dob, n_phone, n_num = list(ssns), [], 0, 0, 0
    for entry in names:
        kind, val = classify_entry(entry)
        if kind == "ssn":
            ssns.append(val)
        elif kind == "dob":
            n_dob += 1
            patterns.append((f"DOB#{n_dob}", dob_pattern(*val)))
        elif kind == "phone":
            n_phone += 1
            a, b, c = val[:3], val[3:6], val[6:]
            patterns.append((f"PHONE#{n_phone}",
                             re.compile(rf"(?<!\d)(?:\+?1[\s.-]*)?\(?{a}\)?[\s.-]*{b}[\s.-]*{c}(?!\d)")))
        elif kind == "number":
            n_num += 1
            head, tail = (val[:-4], val[-4:]) if len(val) >= 8 else (val, "")
            sep = r"[\s-]*"
            rx = rf"(?<!\d)(?P<v>{sep.join(head)})"
            if tail:
                rx += sep + sep.join(tail)
            patterns.append((f"NUM#{n_num}", re.compile(rx + r"(?!\d)")))
        elif kind == "name":
            plain_names.append(entry)
    names = plain_names
    for n, ssn in enumerate(ssns, 1):
        a, b, c = ssn[:3], ssn[3:5], ssn[5:]
        patterns.append((f"SSN#{n}", re.compile(rf"(?<!\d){a}[\s-]*{b}[\s-]*{c}(?!\d)")))
        patterns.append((f"SSN#{n} last-4",
                         re.compile(rf"{MASK}{{3}}[\s-]*{MASK}{{2}}[\s-]*{c}(?!\d)")))
    for name in names:
        tokens = name.split()
        if tokens:
            token_rx = [r"(?:-\s+)?".join(map(re.escape, t)) for t in tokens]
            rx = re.compile(r"\b" + r"\s+".join(token_rx) + r"\b", re.IGNORECASE)
            patterns.append((name, rx))
            if loose := loose_entry_rx(name):
                patterns.append((name, loose))
            # Same label for every form of one person, so counts/leftovers stay one line per name
            # and the label-anonymizing callers keep working.
            patterns.extend((name, vrx) for vrx in name_variant_patterns(name))
            patterns.extend((name, re.compile(rf"(?<![A-Za-z]){nc}(?![A-Za-z])")) for nc in name_controls(name))
            patterns.extend((name, prx) for prx in address_part_patterns(name))
    return patterns


# Output filenames are scrubbed with looser matching than page text: in a filename
# a name is usually joined by _ - . + or nothing ("W2_John_Smith", "JohnSmith"), and
# \b does not fire next to "_".
_FILENAME_SEP = r"[\s_.+\-]*"


def scrub_text(text, names):
    """text with any SSN/EIN/phone/email-shaped string and any supplied name replaced by REDACTED."""
    out = EMAIL_RE.sub("REDACTED", text)
    for rx in (PHONE_RE, PAN_RE, AADHAAR_RE, CA_EMPLOYER_ID_RE, STREET_RE, PO_BOX_RE, CITY_STATE_ZIP_RE,
               IN_ADDRESS_RE):
        out = rx.sub("REDACTED", out)
    out = re.sub(r"(?<!\d)\d{10,}(?!\d)", "REDACTED", out)  # any long number in a filename (account, Aadhaar)
    out = SSN_RE.sub("REDACTED", out)
    out = EIN_RE.sub("REDACTED", out)
    out = NINE_RE.sub("REDACTED", out)
    for name in names:
        tokens = name.split()
        if tokens:
            rx = re.compile(r"(?<![A-Za-z0-9])" + _FILENAME_SEP.join(map(re.escape, tokens))
                            + r"(?![A-Za-z0-9])", re.IGNORECASE)
            out = rx.sub("REDACTED", out)
        if re.search(r"\d", name) or "@" in name:
            continue  # an address/date/phone/email: its parts ("Street") are not identifying on their own
        # A filename is cosmetic, so it can be stricter than page text: every part of the name on its
        # own, and - for long names - a truncated form ("Ramachandran" -> "Rama"), which is how a
        # client's name usually turns up in a filename.
        for word in _clean_tokens(name):
            if len(word) >= 6:
                out = re.sub(r"(?<![A-Za-z0-9])" + re.escape(word[:4]) + r"[A-Za-z]*", "REDACTED", out, flags=re.I)
            elif len(word) >= 3:
                out = re.sub(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", "REDACTED", out, flags=re.I)
    return out


def safe_filename(filename, names):
    """Filename for the redacted copy: the original with names/SSNs/EINs scrubbed out (extension kept)."""
    p = Path(filename)
    return scrub_text(p.stem, names) + p.suffix


def unique_name(name, used):
    """Scrubbing can make two names collide ("W2 - REDACTED.pdf" twice); number the later one."""
    p = Path(name)
    candidate, n = name, 2
    while candidate.lower() in used:
        candidate = str(p.with_name(f"{p.stem}_{n}{p.suffix}"))
        n += 1
    used.add(candidate.lower())
    return candidate


def _char_streams(page):
    """Yield (text, char_boxes): words joined by a space, or by a newline where the next word starts a new line
    (its top moves by more than half the previous word's height). Patterns that must stay on one line (address
    rules use [ \t]) rely on that; everything else matches across lines with \s.

    Two orderings: visual (top-to-bottom) and PDF content-stream order, which
    follows columns in multi-column layouts. char_boxes[i] is the pdfplumber
    char dict behind text[i] (None for inserted separators).
    """
    for flow in (False, True):
        text, boxes, prev = [], [], None
        for w in page.extract_words(use_text_flow=flow, return_chars=True):
            if text:
                text.append("\n" if abs(w["top"] - prev["top"]) > (prev["bottom"] - prev["top"]) / 2 else " ")
                boxes.append(None)
            prev = w
            for c in w["chars"]:
                text.append(c["text"])
                boxes.extend([c] * len(c["text"]))  # ligatures ("fi") span >1 index
        yield "".join(text), boxes


def _fitz_streams(page, dx=0.0, dy=0.0):
    """Yield (text, char_boxes) from PyMuPDF, lines joined by newlines.

    PyMuPDF builds lines along the text's own direction, so sideways text
    reads correctly. Boxes are shifted by (dx, dy) into pdfplumber's
    mediabox-relative coords and tagged with their line number.
    """
    for sort in (False, True):
        text, boxes, line_no = [], [], 0
        for block in page.get_text("rawdict", sort=sort)["blocks"]:
            for line in block.get("lines", []):
                line_no += 1
                for span in line["spans"]:
                    for ch in span["chars"]:
                        x0, y0, x1, y1 = ch["bbox"]
                        text.append(ch["c"])
                        boxes.append({"x0": x0 + dx, "top": y0 + dy, "x1": x1 + dx,
                                      "bottom": y1 + dy, "line": line_no})
                text.append("\n")
                boxes.append(None)
        yield "".join(text), boxes


def _match_rects(chars):
    """One rectangle per line the match touches (a split name gets two boxes).

    PyMuPDF chars carry their line number; pdfplumber chars are grouped by
    vertical position.
    """
    rects, prev = [], None
    for c in chars:
        if prev is None:
            same_line = False
        elif "line" in c:
            same_line = c["line"] == prev["line"]
        else:
            same_line = abs(c["top"] - prev["top"]) < (c["bottom"] - c["top"]) / 2
        if same_line:
            r = rects[-1]
            rects[-1] = (min(r[0], c["x0"]), min(r[1], c["top"]), max(r[2], c["x1"]), max(r[3], c["bottom"]))
        else:
            rects.append((c["x0"], c["top"], c["x1"], c["bottom"]))
        prev = c
    return rects


def match_span(m):
    """The part of a match to black out: group "v" when the pattern has one (a label that only locates
    the value, e.g. "Date of birth:" before a date), else the whole match."""
    return m.span("v") if "v" in m.re.groupindex else m.span()


def _ocr_streams(upright, index):
    """OCR text streams for page `index` of the rotation-reset in-memory copy, or None if unreadable."""
    with fitz.open("pdf", upright.getvalue()) as doc:
        page = doc[index]
        words = redact_ocr.read_words(page)
        if not redact_ocr.readable(words)[0]:
            return None
        return redact_ocr.streams(words, page.cropbox.x0 - page.mediabox.x0, page.cropbox.y0 - page.mediabox.y0)


_PAD = 1  # points added around every redaction box, so a glyph's edge is never left behind


def find_hits(pdf_path, patterns, ocr=False, ocr_pages=None):
    """Return ({page_index: [bbox, ...]}, {label: count}, pages_without_text).

    ocr=True: a page with no text layer is read with OCR (redact_ocr) instead of being reported.
    Its 1-based number is appended to ocr_pages (if given); a page OCR cannot read well stays in
    pages_without_text.

    Detection runs on an in-memory copy with every page's rotation reset to 0:
    on rotated pages pdfplumber sees sideways chars and scrambles line/word
    order, which breaks names split across lines. Boxes come back in
    unrotated coordinates, which is what PyMuPDF's redact annots expect.
    """
    boxes, counts, no_text = {}, {}, []
    with fitz.open(pdf_path) as src:
        for page in src:
            page.set_rotation(0)
        upright = io.BytesIO(src.tobytes())
        fitz_streams = [list(_fitz_streams(p, p.cropbox.x0 - p.mediabox.x0, p.cropbox.y0 - p.mediabox.y0))
                        for p in src]
    with pdfplumber.open(upright) as pdf:
        for i, page in enumerate(pdf.pages):
            streams = list(_char_streams(page)) + fitz_streams[i]
            if not any(text.strip() for text, _ in streams):
                streams = _ocr_streams(upright, i) if ocr else None
                if streams is None:
                    no_text.append(i + 1)
                    continue
                if ocr_pages is not None:
                    ocr_pages.append(i + 1)
            found = []  # (label, rects) already counted
            for text, char_boxes in streams:
                for label, rx in patterns:
                    for m in rx.finditer(text):
                        s, e = match_span(m)
                        rects = [fitz.Rect(r) for r in _match_rects([c for c in char_boxes[s:e] if c])]
                        if not rects:
                            continue
                        if (s, e) != m.span():
                            # Part of the match stays visible (a label, an account's last 4). redact_file pads
                            # every box by 1pt, which would also wipe the touching visible character; cancel it.
                            rects = [r + (_PAD, _PAD, -_PAD, -_PAD) for r in rects]
                        # Always redact every box (overlap is harmless); count a match only
                        # once even when several orderings/detectors find it.
                        boxes.setdefault(i, []).extend(tuple(r) for r in rects)
                        if not any(lbl == label and all(any(r.intersects(q) for q in prev) for r in rects)
                                   for lbl, prev in found):
                            found.append((label, rects))
                            counts[label] = counts.get(label, 0) + 1
    return boxes, counts, no_text


def redact_file(src, dst, patterns, ocr=False, ocr_pages=None):
    if ocr:
        redact_ocr.require()
    boxes, counts, no_text = find_hits(src, patterns, ocr=ocr, ocr_pages=ocr_pages)
    doc = fitz.open(src)
    try:
        strip_annotations(doc)
        for i, rects in boxes.items():
            page = doc[i]
            # pdfplumber coords are relative to the mediabox; PyMuPDF's to the cropbox.
            dx, dy = page.mediabox.x0 - page.cropbox.x0, page.mediabox.y0 - page.cropbox.y0
            for x0, top, x1, bottom in rects:
                r = fitz.Rect(x0 + dx, top + dy, x1 + dx, bottom + dy)
                page.add_redact_annot(r + (-_PAD, -_PAD, _PAD, _PAD), fill=(0, 0, 0))
            page.apply_redactions()
        doc.set_metadata({})  # names often sit in Author/Title
        doc.del_xml_metadata()  # the XMP packet is separate from the Info dict and can hold the same names
        doc.save(dst, garbage=4, deflate=True)
    finally:
        doc.close()
    return counts, no_text


def redact_and_verify(src, dst, patterns, ocr=False, ocr_pages=None, extra_passes=2, confirm_passes=1):
    """redact_file + verify, re-passing when an OCR re-read of the output still finds something, then
    re-confirming with `confirm_passes` further independent OCR re-reads once clean.

    OCR is not repeatable: a photo can be read one way when detecting and another way when verifying, so a
    string the first read missed shows up as "pN-ocr:..." after redaction. Then the output itself is redacted
    again from what OCR sees in it (at most `extra_passes` times). Leftovers on a text layer, in metadata or in
    an annotation are never retried - those are not OCR variance.

    A single clean verify() is not proof by itself: if a page's first detection pass and that same run's
    verify pass both happen to misread the same spot (independent OCR variance going the wrong way twice
    in a row), the file reports clean with real, unredacted text still on the page - reproduced 22 Sep 2026
    on a real phone-photo W-2 (see PARKING_LOT.md). Once verify() first comes back empty on a page that used
    OCR, `confirm_passes` more independent re-reads (no further redaction unless one of them finds something)
    must also come back empty before this returns. Any of them finding something feeds back into the retry
    above (still bounded by extra_passes) and resets the confirmation count.
    Returns (counts, pages_without_text, leftovers, passes)."""
    dst = Path(dst)
    ocr_pages = [] if ocr_pages is None else ocr_pages
    counts, no_text = redact_file(src, dst, patterns, ocr=ocr, ocr_pages=ocr_pages)
    leftovers = verify(dst, patterns, ocr_pages)
    passes, redact_passes, clean_streak = 1, 0, 0
    while True:
        if leftovers:
            if not (ocr and all("-ocr:" in item for item in leftovers)) or redact_passes >= extra_passes:
                break
            again = dst.with_name(dst.name + ".pass.tmp")
            try:
                more, _ = redact_file(dst, again, patterns, ocr=True, ocr_pages=[])
                again.replace(dst)
            finally:
                again.unlink(missing_ok=True)
            for label, n in more.items():
                counts[label] = counts.get(label, 0) + n
            redact_passes += 1
            clean_streak = 0
        elif ocr and ocr_pages and clean_streak < confirm_passes:
            clean_streak += 1
        else:
            break
        leftovers = verify(dst, patterns, ocr_pages)
        passes += 1
    return counts, no_text, leftovers, passes


_ANNOT_TEXT_KEYS = ("Contents", "T", "Subj", "RC", "V", "DV", "TU")


def _annotation_xrefs(doc, page):
    """xrefs of the page's annotations, read from its /Annots array itself.

    Not page.annot_xrefs(): that silently skips annotation types MuPDF does not know
    (e.g. a vendor's /FOSINDEX) - exactly the ones that would go unchecked.
    """
    kind, val = doc.xref_get_key(page.xref, "Annots")
    if kind == "null":
        return []
    if kind == "xref":  # the array is an indirect object
        val = doc.xref_object(int(val.split()[0]), compressed=False)
    return [int(m) for m in re.findall(r"(\d+)\s+0\s+R", val)]


def strip_annotations(doc):
    """Remove every annotation except form-field widgets from every page.

    Annotations are not page text, so the redactor cannot see what they hold - and they can hold a
    lot: comments, and vendor markers such as /FOSINDEX, which in practice carried a client name and
    an SSN. They have no value for extraction. Widgets (fillable form fields) are document content,
    so they stay; verify() still scans them and fails the file if one holds a pattern.
    Call before adding redaction annotations. The dropped objects are unreferenced afterwards and
    disappear on save(garbage=4).
    """
    for page in doc:
        xrefs = _annotation_xrefs(doc, page)
        if not xrefs:
            continue
        keep = [x for x in xrefs if doc.xref_get_key(x, "Subtype")[1] == "/Widget"]
        doc.xref_set_key(page.xref, "Annots", "[" + " ".join(f"{x} 0 R" for x in keep) + "]" if keep else "null")


def _annotation_text(doc, page):
    """Text held in the page's annotation dictionaries (form fields that survive strip_annotations,
    or anything in a file that has not been through redact_file)."""
    parts = []
    for xref in _annotation_xrefs(doc, page):
        parts.append(doc.xref_object(xref, compressed=False))
        for key in _ANNOT_TEXT_KEYS:  # decoded (a hex UTF-16 string does not match the raw dict text)
            k_kind, k_val = doc.xref_get_key(xref, key)
            if k_kind == "string":
                parts.append(k_val)
    return " ".join(parts)


def verify(dst, patterns, ocr_pages=()):
    """Reconciliation: re-read the output and list any sensitive text still present.

    ocr_pages: 1-based pages that were redacted from OCR; they have no text layer, so they are re-read
    with OCR too (leftover label "pN-ocr:...")."""
    leftovers = []
    with fitz.open(dst) as doc:
        # "format"/"encryption" describe the file itself, not user-entered metadata
        meta = " ".join(v for k, v in doc.metadata.items() if v and k not in ("format", "encryption"))
        meta += " " + (doc.get_xml_metadata() or "")
        for label, rx in patterns:
            if rx.search(meta):
                leftovers.append(f"meta:{label}")
        for i, page in enumerate(doc):
            annot = _annotation_text(doc, page)
            for label, rx in patterns:
                if rx.search(annot):
                    leftovers.append(f"p{i + 1}-annot:{label}")  # "pN-annot" keeps the label parseable as "page:label"
            texts = (page.get_text(), page.get_text(sort=True))  # stream + visual order
            for label, rx in patterns:
                if any(rx.search(t) for t in texts):
                    leftovers.append(f"p{i + 1}:{label}")
            if i + 1 in ocr_pages:
                ocr_texts = [t for t, _ in redact_ocr.streams(redact_ocr.read_words(page))]
                for label, rx in patterns:
                    if any(rx.search(t) for t in ocr_texts):
                        leftovers.append(f"p{i + 1}-ocr:{label}")
    return leftovers


def main():
    ap = argparse.ArgumentParser(description="Redact SSNs and names from a folder of PDFs.")
    ap.add_argument("--input", required=True, help="Folder of source PDFs")
    ap.add_argument("--output", required=True, help="Folder for redacted copies")
    ap.add_argument("--names", default="",
                    help="Comma-separated names/addresses; an entry that is a date (DOB, numeric form - a comma "
                         "splits \"Jan 15, 1980\") or a phone number is matched in every written form")
    ap.add_argument("--ssns", default="",
                    help='Comma-separated known SSNs (any format) — also redacts masked last-4, e.g. XXX-XX-6789')
    ap.add_argument("--ocr", action="store_true",
                    help="OCR pages with no text layer (needs `tesseract`) and redact what it finds there. "
                         "Weaker than a text-layer check: OCR can miss text.")
    args = ap.parse_args()
    if args.ocr:
        redact_ocr.require()

    ssns = []
    for raw in filter(None, (s.strip() for s in args.ssns.split(","))):
        digits = re.sub(r"\D", "", raw)
        if len(digits) != 9:
            sys.exit(f"--ssns: entry #{len(ssns) + 1} is not 9 digits")
        ssns.append(digits)

    src_dir, out_dir = Path(args.input).resolve(), Path(args.output).resolve()
    if not src_dir.is_dir():
        sys.exit(f"Input folder not found: {src_dir}")
    if out_dir == src_dir:
        sys.exit("Output folder must differ from input folder (originals are never overwritten).")
    out_dir.mkdir(parents=True, exist_ok=True)

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    patterns = build_patterns(names, ssns)
    pdfs = sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        sys.exit(f"No PDFs in {src_dir}")

    kinds = Counter(classify_entry(n)[0] for n in names)  # counts only: entries are never printed
    print(f"Redacting {len(pdfs)} PDF(s); always: SSN, EIN, 9-digit, phone, email, labelled DOB, PAN, Aadhaar, "
          f"CA employer ID, account numbers (last 4 kept), US + India addresses; entered: "
          f"{len(ssns) + kinds['ssn']} SSN(s), {kinds['name']} name/address(es), {kinds['dob']} DOB(s), "
          f"{kinds['phone']} phone(s), {kinds['number']} account number(s)")
    failures, needs_review, used = [], [], set()
    for src in pdfs:
        shown = unique_name(safe_filename(src.name, names), used)  # original name may contain the client's
        dst = out_dir / shown
        try:
            ocr_pages = []
            counts, no_text, leftovers, passes = redact_and_verify(src, dst, patterns, ocr=args.ocr, ocr_pages=ocr_pages)
        except Exception as e:  # keep going on a bad file, but report it
            failures.append(shown)
            print(f"  ERROR  {shown}: {e}")
            continue
        summary = ", ".join(f"{k}={v}" for k, v in counts.items()) or "no matches"
        status = "OK"
        if leftovers:
            status = "FAIL"
            failures.append(shown)
            summary += f" | STILL PRESENT: {', '.join(leftovers)}"
        if ocr_pages:
            summary += f" | OCR read page(s) {ocr_pages}" + (f", {passes} passes" if passes > 1 else "")
        if no_text:
            status = "REVIEW" if status == "OK" else status
            needs_review.append(shown)
            summary += f" | no text layer on page(s) {no_text} — scanned? NOT redacted"
        print(f"  {status:<6} {shown}: {summary}")

    print("\nReconciliation")
    print(f"  Files in:        {len(pdfs)}")
    print(f"  Verified clean:  {len(pdfs) - len(failures) - len(needs_review)}")
    print(f"  Needs review:    {len(needs_review)}  (image-only pages; OCR/manual check required)")
    print(f"  Failed:          {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
