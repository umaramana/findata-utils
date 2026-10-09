"""
Transaction Tagger — Sprint 1
Preparer reviews unique extracted vendors; Claude tags only the remainder.
Entry point: called via rasrich_tools.py page navigation.
"""
import io
import json
import os
import re
from datetime import date

import anthropic
import pandas as pd
import streamlit as st

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_TAG_LIST_PATH = os.path.join(_SCRIPT_DIR, '..', 'docs', 'rasrich_tag_lists.csv')
_LOOKUPS_DIR = os.path.join(_SCRIPT_DIR, 'lookups')
_WAVE_MAPPING_PATH = os.path.join(_SCRIPT_DIR, '..', 'docs', 'wave_mapping.csv')
_AUTO_RULES_PATH = os.path.join(_SCRIPT_DIR, '..', 'docs', 'auto_rules.csv')
_ENTITY_TYPES = ['Sole Prop / SMLLC', 'S-Corp', 'Partnership / MMLLC']
_MODEL = 'claude-haiku-4-5'
_BATCH_SIZE = 30

# Column names for the vendor review table
_COL_CATEGORY    = 'Category'
_COL_SUBCATEGORY = 'Subcategory'   # holds the Wave category; shown as "Wave Category"
_COL_DIRECTION   = 'Direction'     # 'debit' (money out) / 'credit' (money in)

# Purchase prefix pattern — transaction type only, date handled separately.
# Goal: strip only the payment method prefix so the vendor + location reach Claude intact.
# Handles: "Card Purchase", "Mobile Purchase", "Debit Purchase", "Debit Card Purchase",
#          "PIN Purchase", "Recurring Card Purchase", "Card Purchase With Pin", "Card Purchase Return"
_PURCHASE_PREFIX_RE = re.compile(
    r'^(?:Recurring\s+)?(?:Debit\s+)?(?:Card|Mobile|Debit|Online|PIN)\s+Purchase(?:\s+(?:With\s+Pin|Return))?',
    re.I
)


def _clean_card_purchase(raw):
    """Extract merchant+location from purchase description.
    Two formats detected by what follows the purchase prefix:
    - Capital One: '- MERCHANT CITY, STATE' (dash-space separator, no card ref)
    - Citibank:    'abbrev MM/DD HH:MM #card | MERCHANT | Category' (card ref separator)"""
    s = _PURCHASE_PREFIX_RE.sub('', raw).strip()
    if re.match(r'^-\s', s):
        # Capital One format — everything after "- " is merchant+location
        s = s[2:].strip()
        if ' | ' in s:
            s = s.split(' | ')[0].strip()
        s = re.sub(r',\s*', ' ', s).strip()   # normalize commas to spaces
    else:
        # Citibank format — #card ref marks end of metadata, merchant follows
        stripped = re.sub(r'^.*?#\d{3,5}\s*', '', s)
        s = stripped.strip() if stripped != s else re.sub(r'^.*?\b\d{2}/\d{2}\s+', '', s).strip()
        s = re.sub(r'^\|\s*', '', s).strip()
        if ' | ' in s:
            s = s.split(' | ')[0].strip()
    # Normalize OCR space-substitutes (= and _ used as space in Citibank OCR)
    s = re.sub(r'\s*[=_]\s*', ' ', s).strip()
    # Strip leading em-dash OCR artifact (e.g. "—NYUS05154")
    s = re.sub(r'^[—–]\s*', '', s).strip()
    # Strip noise suffixes (phone, card number, bank ref, store number)
    s = re.sub(r'^Nst\s+', '', s, flags=re.I)
    s = re.sub(r'\s+Car(?:d\s+\d+)?\s*$', '', s, flags=re.I)
    s = re.sub(r'\s+\d{3}[-.\s]\d{3}[-.\s]\d+(?:[-.\s]\d+)?\s*$', '', s)
    s = re.sub(r'(?:\s+\d+){2,}\s*$', '', s)
    s = re.sub(r'\s+MV/\d+\s*$', '', s)
    s = re.sub(r'\s+#\s*\d+\s*$', '', s)
    # Strip concatenated state+country+zip/ref OCR artifact (e.g. NYUS05154, NYUSO7117)
    # Pattern: 2-char state + literal "US" + zip/ref — avoids eating real words like "PARK"
    s = re.sub(r'[A-Z]{2}US[A-Z0-9]{3,}$', '', s).rstrip('—– ')
    return s.strip()[:80]


# Full-replacement patterns → clean vendor label (no PII sent to Claude)
# Order matters: more specific patterns first.
_TRANSFER_PATTERNS = [
    # "ACH: American Express" (pre-cleaned by bank extractor) → "American Express"
    (re.compile(r'^ACH:\s+(.+)$', re.I),
     lambda m: m.group(1).strip().split(' | ')[0][:50]),
    # ACH Electronic Debit/Credit — strip bank prefix, keep vendor + details
    (re.compile(r'^ACH\s+Electronic\s+(?:Debit|Credit)\s+(.+)$', re.I),
     lambda m: m.group(1).strip()),
    # Capital One: Withdrawal/Deposit from/to — strip prefix, mask account number, split multi-txn
    (re.compile(r'^(?:Withdrawal|Deposit)\s+(?:from|to)\s+(.+)$', re.I),
     lambda m: re.sub(r'\s+X{3,}\d+$', '', m.group(1).split(' | ')[0].strip())),
    # Capital One: garbled/OCR purchase prefix — extract merchant after "Purchase - "
    # Catches "Bepit Card Purchase - MERCHANT", "pent Card Purchase - MERCHANT" etc.
    (re.compile(r'\bPurchase\s*-\s*(.+)', re.I),
     lambda m: re.sub(r',\s*', ' ', m.group(1).split(' | ')[0].strip()).strip()),
    # Raw Orig CO Name (not yet cleaned by bank extractor)
    (re.compile(r'ORIG CO NAME:\s*(.*?)(?:\s+ORIG\s+ID:|\s+CO ENTRY|\s+ID:|$)', re.I),
     lambda m: re.sub(r'\s+ORIG$', '', m.group(1)).strip()[:50]),
    # Zelle: extract recipient, strip trailing alphanumeric reference codes
    (re.compile(r'^ZELLE\b(?:\s+(?:PAYMENT|CREDIT|DEBIT))?\s+(?:(?:TO|FROM)\s+)?(.+)', re.I),
     lambda m: 'Zelle: ' + re.sub(r'\s+[A-Za-z0-9]{8,}$', '', m.group(1).strip())[:50]),
    # Amazon: any XXXX* subtype (MARK*, RETA*, MKTPL* etc.) — strip subtype+hash, keep location
    (re.compile(r'^AMAZON\s+\S*\*\s*[A-Z0-9]{4,}\s+(.*)', re.I),
     lambda m: ('Amazon ' + m.group(1).strip()).strip()),
    # Amazon fallback (AMAZON.COM, AMAZON PRIME, etc.)
    (re.compile(r'^AMAZON\s*\*?\s*(.+)', re.I),
     lambda m: ('Amazon ' + m.group(1).strip()).strip()),
    (re.compile(r'^Cash\s+Withdrawal\b', re.I), lambda _: 'ATM Withdrawal'),
    (re.compile(r'^ONLINE TRANSFER\b', re.I),   lambda _: 'Online Transfer'),
    (re.compile(r'^ATM\b', re.I),               lambda _: 'ATM Withdrawal'),
    (re.compile(r'^CHECK\s+#?\d+', re.I),       lambda _: 'Check'),
    (re.compile(r'^WIRE TRANSFER\b', re.I),     lambda _: 'Wire Transfer'),
    (re.compile(r'^SERVICE CHARGE\b', re.I),    lambda _: 'Bank Service Charge'),
    (re.compile(r'^BANK FEE\b', re.I),          lambda _: 'Bank Fee'),
]


# Trailing noise to strip from merchant descriptions.
# Objective: strip only PII and bank metadata — keep vendor name, location, address intact
# because all of that is context for the preparer and Claude API.
# What is noise: transaction dates, phone numbers, bank ref codes, store numbers.
# What is NOT noise: city, state, zip, street address — location stays.
_CLEANUP_PATTERNS = [
    re.compile(r'\s+\d{6,}\s+\d{2}/\d{2}\s*$'),                       # ref + date e.g. "795813  12/08"
    re.compile(r'\s+\d{2}/\d{2}\s*$'),                                 # trailing date e.g. "11/21"
    re.compile(r'\s+\d{5,}\s*$'),                                      # trailing bank ref codes (5+ digits)
    re.compile(r'\s+\d{3}[-.\s]\d{3}[-.\s]\d+(?:[-.\s]\d+)?\s*$'),   # phone e.g. 800-956-6310
    re.compile(r'\s+\d{3}-\d{7}\s*$'),                                 # phone e.g. 800-6427676
    re.compile(r'\s+#\s*\d{2,}$'),                                     # store number e.g. "#054"
    re.compile(r'\s+NO\.?\s*\d{3,}$', re.I),                          # ref e.g. "NO. 4521"
    re.compile(r'\s+MV/\d+\s*$'),                                      # bank ref e.g. "MV/3563534"
    re.compile(r',?\s+US\s*$'),                                        # trailing country code e.g. "NY US"
    re.compile(r',\s*$'),                                              # trailing comma e.g. "FLORAL,"
]

# Leading merchant prefixes to strip (Square, Toast, FSI, Zip, etc.)
# Z[A-Za-z]?IP covers OCR variants: ZIP*, ZzIP*, ZiIP* etc.
_MERCHANT_PREFIX_RE = re.compile(
    r'^(?:SQ\s*\*|SQSP\*\s*|TST\*|FSI\*|MSFT\s*\*\s*\S+\s+|Z[A-Za-z]?IP\*\s*)', re.I
)

# Leading bank transaction codes — short opaque tokens that precede the actual merchant name.
# Pattern: 2-char uppercase OR 2-3 digits, followed by a mixed-case ref word (initial cap +
# 1-3 lowercase), plus optional card-last-4 reference (#NNNN).
# Examples stripped: "OT Crpj ", "11 Sjq #5989 "
# Safe because real vendor names in bank statements are all-caps or contain * / . separators —
# the mixed-case ref word (e.g. "Crpj", "Sjq") is the distinguishing signal.
_BANK_PREFIX_RE = re.compile(
    r'^(?:[A-Z]{2}|\d{2,3})\s+[A-Z][a-z]{1,3}\s+(?:#\d{3,5}\s+)?(?=\S)',
)


# ── Amount helpers ───────────────────────────────────────────────────────────────

def _parse_amount(val):
    """Parse amount including bracketed negatives like (100.00). Returns float or None."""
    s = str(val).strip().replace(',', '').replace('$', '').replace(' ', '')
    if s.startswith('(') and s.endswith(')'):
        try:
            return -abs(float(s[1:-1]))
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_expense(val):
    amt = _parse_amount(val)
    return amt is not None and amt < 0


def _row_directions(df, amount_col):
    """Per-row 'debit' / 'credit' / '' (no parseable amount). No amount column = all
    debits. A single column with no negatives (e.g. Subtracted) is debit-only, so its
    positive values are debits, not credits."""
    if not amount_col:
        return pd.Series('debit', index=df.index)
    parsed = df[amount_col].apply(_parse_amount)
    debit_only = amount_col != '_signed_amount' and not parsed.dropna().lt(0).any()
    return parsed.apply(lambda a: '' if a is None or pd.isna(a)
                        else 'debit' if debit_only or a < 0 else 'credit')


# ── Vendor extraction (regex, no PII to Claude) ──────────────────────────────────

def _extract_vendor(desc):
    """Strip transaction metadata → keep vendor name + location for Claude context."""
    desc = str(desc).strip()
    if _PURCHASE_PREFIX_RE.match(desc):
        # Extract merchant section, then run through transfer patterns (Amazon etc.)
        result = _clean_card_purchase(desc)
        matched = next((handler(m) for pat, handler in _TRANSFER_PATTERNS
                        if (m := pat.search(result))), None)
        if matched is None:
            result = _MERCHANT_PREFIX_RE.sub('', result).strip()
            for pat in _CLEANUP_PATTERNS:
                result = pat.sub('', result).strip()
        else:
            result = matched
    else:
        matched = next((handler(m) for pat, handler in _TRANSFER_PATTERNS
                        if (m := pat.search(desc))), None)
        if matched is not None:
            result = matched
        else:
            result = _MERCHANT_PREFIX_RE.sub('', desc).strip()
            result = _BANK_PREFIX_RE.sub('', result).strip()
            if result != desc:
                matched = next((handler(m) for pat, handler in _TRANSFER_PATTERNS
                                if (m := pat.search(result))), None)
                if matched is not None:
                    result = matched
            if matched is None:
                for pat in _CLEANUP_PATTERNS:
                    result = pat.sub('', result).strip()
                for delim in ('  ', ' - ', ' | ', ' / '):
                    if delim in result:
                        result = result.split(delim)[0].strip()
                        break
    # Final pass: strip trailing refs on every path
    result = re.sub(r'\s+\d{5,}\s*$', '', result).strip()        # ref with space e.g. "WA 25113"
    result = re.sub(r'(?<=[A-Z])\d{5,}$', '', result).strip()    # concatenated e.g. "WA25113"
    result = re.sub(r'(?:\s+\d+){3,}\s*$', '', result).strip()   # policy/acct numbers e.g. "48 417 697"
    result = re.sub(r'\s+\d{2}/\d{2}\s*$', '', result).strip()   # trailing date
    return result[:80] if result else desc[:80]


def _load_auto_rules():
    """auto_rules.csv: pattern, direction (any/debit/credit), wave_category, tag.
    A rule gives either a Wave category (tag then comes from the Wave mapping) or a tag."""
    df = pd.read_csv(_AUTO_RULES_PATH, dtype=str).fillna('')
    return [(re.compile(r['pattern'], re.I), r['direction'] or 'any',
             r['wave_category'].strip(), r['tag'].strip()) for _, r in df.iterrows()]


_AUTO_RULES = _load_auto_rules()


def _get_auto_rule(vendor, direction='debit'):
    """First matching auto rule → {'tag', 'subcategory'}, or None."""
    for pat, rule_dir, wave_cat, tag in _AUTO_RULES:
        if rule_dir in ('any', direction) and pat.search(str(vendor)):
            return {'tag': tag, 'subcategory': wave_cat}
    return None


# ── Wave mapping ─────────────────────────────────────────────────────────────────

def _wave_mapping_path(client_id):
    return os.path.join(_LOOKUPS_DIR, f'{client_id}_wave_mapping.csv')


def _load_wave_mapping(client_id=None):
    """{(wave_category, direction): tag} from the shared wave_mapping.csv, then the
    client's lookups/{client_id}_wave_mapping.csv (e.g. its own bank accounts), whose
    rows override shared ones."""
    paths = [_WAVE_MAPPING_PATH] + ([_wave_mapping_path(client_id)] if client_id else [])
    mapping = {}
    for path in paths:
        if os.path.exists(path):
            for _, r in pd.read_csv(path, dtype=str).fillna('').iterrows():
                if r['wave_category'].strip() and r['tag'].strip():
                    mapping[(r['wave_category'].strip(), r['direction'].strip() or 'any')] = r['tag'].strip()
    return mapping


def _wave_categories(wave_map):
    return list(dict.fromkeys(cat for cat, _ in wave_map))


def _wave_tag(wave_cat, direction, wave_map):
    """Tax tag for a Wave category in this direction; '' if the category isn't mapped."""
    if not wave_map or not wave_cat:
        return ''
    return wave_map.get((wave_cat, direction)) or wave_map.get((wave_cat, 'any'), '')


def _is_new_wave(wave_cat, wave_map):
    """A non-blank Wave category that isn't in the mapping yet (e.g. proposed by Claude)."""
    wave_cat = str(wave_cat or '').strip()
    return bool(wave_cat) and wave_map is not None and wave_cat not in _wave_categories(wave_map)


def _add_client_wave_categories(client_id, rows):
    """Append (wave_category, tag) pairs to lookups/{client_id}_wave_mapping.csv as
    direction 'any', skipping names already mapped (case-insensitive). Returns names added."""
    known = {c.lower() for c in _wave_categories(_load_wave_mapping(client_id))}
    new = []
    for name, tag in rows:
        name, tag = str(name).strip(), str(tag).strip()
        if name and tag and name.lower() not in known:
            new.append({'wave_category': name, 'direction': 'any', 'tag': tag})
            known.add(name.lower())
    if new:
        path = _wave_mapping_path(client_id)
        os.makedirs(_LOOKUPS_DIR, exist_ok=True)
        pd.DataFrame(new).to_csv(path, mode='a', index=False, header=not os.path.exists(path))
    return [r['wave_category'] for r in new]


def _new_wave_rows_from_output(df, wave_map):
    """Wave categories used in the tagged output that the mapping doesn't know yet,
    each with its most common tag (Review with Client rows ignored)."""
    used = df[df['Subcategory'].fillna('').astype(str).str.strip().ne('')
              & df['Tag'].fillna('').ne('') & df['Tag'].ne('Review with Client')]
    used = used[used['Subcategory'].apply(lambda w: _is_new_wave(w, wave_map))]
    return [(name, grp['Tag'].mode().iloc[0]) for name, grp in used.groupby('Subcategory')]


# ── Tag lists ────────────────────────────────────────────────────────────────────

def _load_generic_tags():
    """Full tag list from rasrich_tag_lists.csv — always available."""
    df = pd.read_csv(_TAG_LIST_PATH)
    return df['tag'].dropna().tolist()


_LOOKUP_CATEGORY_COL_NAMES = {'tag', 'tags', 'category', 'categories',
                              'expense tag', 'expense category'}
_LOOKUP_SUBCATEGORY_COL_NAMES = {'subcategory', 'sub category', 'sub-category',
                                 'subcategories', 'specific tag'}


def _load_lookup_tab_vocab(xl):
    """Vocabulary from the uploaded file's Lookup tab: valid Category and Subcategory
    values specific to this client, for populating dropdown options. NOT a vendor
    mapping — no vendor/description column is read here; per-vendor assignment comes
    only from the persistent lookup CSV (see _load_lookup).
    Returns (category_tags, subcategory_tags, warning). Empty lists + warning=None
    means no Lookup tab found (not an error — the tab is optional)."""
    if xl is None:
        return [], [], None
    try:
        sheet = next((s for s in xl.sheet_names
                      if 'lookup' in s.strip().lower()), None)
        if sheet is None:
            return [], [], None
        df = xl.parse(sheet)
        cat_col = next((c for c in df.columns
                        if str(c).strip().lower() in _LOOKUP_CATEGORY_COL_NAMES), None)
        if cat_col is None:
            cols = ', '.join(f'"{c}"' for c in df.columns.tolist())
            return [], [], (f'Lookup tab "{sheet}" found but no Category column detected. '
                            f'Columns found: {cols}. Rename one to "Category".')
        subcat_col = next((c for c in df.columns
                           if str(c).strip().lower() in _LOOKUP_SUBCATEGORY_COL_NAMES), None)
        category_tags = df[cat_col].dropna().unique().tolist()
        subcategory_tags = df[subcat_col].dropna().unique().tolist() if subcat_col else []
        return category_tags, subcategory_tags, None
    except Exception as e:
        return [], [], f'Error reading Lookup tab: {e}'


def _get_category_options(generic_tags, lookup_tab_categories):
    """Dropdown options for Category: full IRS/generic list + any extra values
    the client's Lookup tab contributes (usually a subset, but not required to be)."""
    opts = [''] + list(generic_tags)
    for t in lookup_tab_categories:
        if t not in opts:
            opts.append(t)
    return opts


def _get_subcategory_options(client_subcategories, lookup_tab_subcategories):
    """Dropdown options for Subcategory: this client's own history (from the lookup
    CSV) plus any vocabulary the Lookup tab contributes. Dropdown-constrained rather
    than free text to avoid fragmenting the Tag→Subcategory summary grouping with
    typo variants (e.g. 'Health Insurance' vs 'Health Ins')."""
    opts = ['']
    seen = set()
    for t in list(client_subcategories) + list(lookup_tab_subcategories):
        if t and t not in seen:
            opts.append(t)
            seen.add(t)
    return opts


# ── Lookup table ─────────────────────────────────────────────────────────────────

def _lookup_path(client_id):
    return os.path.join(_LOOKUPS_DIR, f'{client_id}_lookup.csv')


def _load_lookup(client_id):
    path = _lookup_path(client_id)
    if os.path.exists(path):
        df = pd.read_csv(path)
        if 'source' in df.columns:
            df.loc[df['source'] == 'auto', 'source'] = 'claude'
        return df
    return pd.DataFrame(columns=['vendor_name', 'tag', 'subcategory', 'source', 'date_tagged'])


_MIN_LOOKUP_NAME = 3   # shorter names would match inside unrelated vendors


def _lookup_matcher(lookup_df):
    """vendor → {'tag', 'subcategory'} or None. Exact vendor_name first; else the longest
    lookup name found inside the vendor as whole words, ignoring case and spacing — so a
    hand-typed 'Orkin' matches 'Recurring Card Transaction Orkin LLC 002 ...'."""
    if lookup_df.empty:
        return lambda v: None
    rows = {}
    for _, r in lookup_df.iterrows():
        rows[str(r['vendor_name'])] = {'tag': r['tag'],
                                       'subcategory': '' if pd.isna(r.get('subcategory')) else r.get('subcategory', '')}
    contained = sorted(((re.compile(r'(?<![a-z0-9])' + re.escape(_norm_name(n)) + r'(?![a-z0-9])'), entry)
                        for n, entry in rows.items() if len(_norm_name(n)) >= _MIN_LOOKUP_NAME),
                       key=lambda pe: -len(pe[0].pattern))

    def match(vendor):
        if vendor in rows:
            return rows[vendor]
        v = _norm_name(vendor)
        return next((entry for pat, entry in contained if pat.search(v)), None)
    return match


def _norm_name(s):
    return re.sub(r'\s+', ' ', str(s)).strip().lower()


def _save_lookup(client_id, entries):
    os.makedirs(_LOOKUPS_DIR, exist_ok=True)
    existing = _load_lookup(client_id)
    combined = pd.concat([existing, pd.DataFrame(entries)], ignore_index=True)
    combined = combined.drop_duplicates(subset='vendor_name', keep='last')
    combined.to_csv(_lookup_path(client_id), index=False)


def _collect_lookup_entries(df, desc_col):
    today = date.today().isoformat()
    entries = []
    for _, row in df.iterrows():
        if row.get('Tag_Source') in ('claude', 'preparer'):
            entries.append({
                'vendor_name': str(row.get('Vendor', row[desc_col])),
                'tag': row['Tag'],
                'subcategory': row.get('Subcategory', ''),
                'source': row['Tag_Source'],
                'date_tagged': today,
            })
    return entries


# ── Vendor review table ──────────────────────────────────────────────────────────

def _resolve_vendor(v, direction, lookup_match, pretag_results):
    """(category, subcategory, source label) in precedence lookup > auto rule > pretag."""
    hit = lookup_match(v)
    if hit:
        return hit['tag'], hit['subcategory'], '📋 Lookup'
    rule = _get_auto_rule(v, direction)
    if rule:
        return rule['tag'], rule['subcategory'], '⚡ Auto'
    if pretag_results and v in pretag_results:
        r = pretag_results[v]
        return r.get('tag', ''), r.get('subcategory', ''), r.get('source', '')
    return '', '', ''


def _fill_tags_from_wave(tbl, wave_map):
    """Category follows the Wave category wherever the Wave mapping knows it,
    using the vendor's net direction. Unmapped Wave categories leave Category as is."""
    if not wave_map or tbl.empty:
        return tbl
    tbl = tbl.copy()
    for idx, r in tbl.iterrows():
        tag = _wave_tag(str(r.get(_COL_SUBCATEGORY, '') or '').strip(),
                        r.get(_COL_DIRECTION, 'debit'), wave_map)
        if tag:
            tbl.at[idx, _COL_CATEGORY] = tag
    return tbl


def _build_vendor_table(df, desc_col, amount_col, lookup_df, pretag_results=None, wave_map=None):
    """Group by extracted Vendor, debits and credits alike. Direction = the vendor's net
    sign. Returns unique-vendor DataFrame with pre-filled tags.
    If pretag_results provided, adds Source column (⚡ Auto / 📋 Lookup / 🤖 Claude / blank)."""
    dirs = _row_directions(df, amount_col)
    rows = df[dirs != ''].copy()
    if rows.empty:
        return pd.DataFrame(columns=['Vendor', 'Count', 'Total Amount', _COL_DIRECTION,
                                     _COL_CATEGORY, _COL_SUBCATEGORY])

    agg = {'Count': ('Vendor', 'count')}
    if amount_col:
        agg['Total Amount'] = (amount_col, lambda x: round(x.apply(_parse_amount).dropna().sum(), 2))
    grp = rows.groupby('Vendor', sort=False).agg(**agg).reset_index()
    # Net money in vs out per vendor (a debit-only column never yields a credit)
    if amount_col:
        rows['_net'] = rows[amount_col].apply(lambda a: abs(_parse_amount(a)))
        rows.loc[dirs[rows.index] == 'debit', '_net'] *= -1
        net = rows.groupby('Vendor')['_net'].sum()
        grp[_COL_DIRECTION] = grp['Vendor'].map(lambda v: 'credit' if net[v] > 0 else 'debit')
    else:
        grp[_COL_DIRECTION] = 'debit'

    lookup_match = _lookup_matcher(lookup_df)
    resolved = grp.apply(lambda r: _resolve_vendor(r['Vendor'], r[_COL_DIRECTION], lookup_match,
                                                   pretag_results), axis=1)
    grp[_COL_CATEGORY] = [c for c, _, _ in resolved]
    grp[_COL_SUBCATEGORY] = [s for _, s, _ in resolved]
    if pretag_results is not None:
        grp['Source'] = [src + (' 🆕' if src.startswith('🤖') and _is_new_wave(sub, wave_map) else '')
                         for (_, sub, src) in resolved]
    return _fill_tags_from_wave(grp, wave_map)


def _merge_edits(full_tbl, edited_view, wave_map=None):
    """Write edits from the pending-only view back into the full vendor table,
    then fill Category from any Wave category the preparer picked."""
    edit_map = {r['Vendor']: {_COL_CATEGORY:    str(r.get(_COL_CATEGORY, '') or '').strip(),
                               _COL_SUBCATEGORY: str(r.get(_COL_SUBCATEGORY, '') or '').strip()}
                for _, r in edited_view.iterrows()}
    full = full_tbl.copy()
    for idx, row in full.iterrows():
        if row['Vendor'] in edit_map:
            full.at[idx, _COL_CATEGORY]    = edit_map[row['Vendor']][_COL_CATEGORY]
            full.at[idx, _COL_SUBCATEGORY] = edit_map[row['Vendor']][_COL_SUBCATEGORY]
    return _fill_tags_from_wave(full, wave_map)


def _pending_vendors(tbl):
    """Rows where Category is blank → still need tagging. Subcategory is optional
    and doesn't gate whether a vendor needs preparer/Claude attention."""
    return tbl[tbl[_COL_CATEGORY].fillna('') == '']


# ── Claude API ───────────────────────────────────────────────────────────────────

def _subcategory_vocab_for_prompt(client_id, lookup_tab_subcategories):
    """Wave categories Claude may pick from (shared + this client's Wave mapping, plus
    this file's Lookup tab), deduped, no blank entry. Not the client's lookup history:
    that holds older free-text labels Claude should stop reusing."""
    wave_cats = _wave_categories(_load_wave_mapping(client_id))
    return [t for t in _get_subcategory_options(wave_cats, lookup_tab_subcategories) if t]


def _rules_path(client_id):
    return os.path.join(_LOOKUPS_DIR, f'{client_id}_rules.txt')


def _load_client_rules(client_id):
    """Card A: free-text, one-rule-per-line client rules file. Absent file = no
    rules (current behavior unchanged). '#'-prefixed lines are comments."""
    path = _rules_path(client_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]


def _client_rules_note(rules):
    """Absent/empty rules => '' so the prompt is byte-identical to prior behavior
    (Card A acceptance #4). The apportionment boundary only needs stating once a
    rule actually exists to apply it to."""
    if not rules:
        return ''
    return (
        '\n\nClient-specific rules (apply these over generic classification):\n'
        + '\n'.join(f'- {r}' for r in rules)
        + '\nThese rules describe classification only. Apply one to pick a tag, but '
        'never compute or carry forward an apportioned dollar amount (e.g. a 15%/80% '
        'split) — if a rule implies a calculation, use "Review with Client" instead.'
    )


def _vendor_stats(df, amount_col, date_col):
    """Per-vendor aggregates for the enriched prompt payload (Card A): amount_total,
    txn_count (recurrence signal), amount_sample, date_span. Vendor string itself
    stays the memory key (unchanged) — this only adds context around it."""
    stats = {}
    dirs = _row_directions(df, amount_col)
    for v, grp in df.groupby('Vendor'):
        stat = {'txn_count': len(grp)}
        if amount_col:
            # Signed by direction so a debit-only (all-positive) column still reads as money out
            amounts = grp[amount_col].apply(_parse_amount).dropna().abs()
            amounts[dirs[amounts.index] == 'debit'] *= -1
            if not amounts.empty:
                stat['amount_total'] = round(amounts.sum(), 2)
                stat['amount_sample'] = (
                    round(amounts.iloc[0], 2) if len(amounts) == 1
                    else f'{round(amounts.min(), 2)} to {round(amounts.max(), 2)}')
        if date_col and date_col in grp.columns:
            months = [m for m in _MONTH_ORDER if m in grp[date_col].apply(_parse_month).values]
            if months:
                stat['date_span'] = months[0] if len(months) == 1 else f'{months[0]}-{months[-1]}'
        stats[v] = stat
    return stats


def _specific_tag_note(specific_tags):
    if not specific_tags:
        return ''
    return (
        '\n\nThis client uses a curated tag list. Prefer these specific tags when they fit:\n'
        + '\n'.join(f'- {t}' for t in specific_tags)
        + '\nFall back to the full list only when no specific tag is appropriate.'
    )


def _subcategory_vocab_note(subcategory_vocab):
    if not subcategory_vocab:
        return ''
    return (
        '\n\nWave categories (the bookkeeping categories this client posts to). For '
        '"subcategory", return one of these exactly when it fits. Only if none fits, propose '
        'a short new category name in the same style (e.g. "Cost of Goods Sold - Beverages") '
        'and reuse that same name for similar vendors:\n'
        + '\n'.join(f'- {t}' for t in subcategory_vocab)
    )


def _persona_clause(entity_type, primary, secondary, include_persona):
    if not include_persona:
        return ''
    persona = f'Entity type: {entity_type}. Primary activity: {primary}.'
    if secondary:
        persona += f' Secondary activity: {secondary}.'
    return f' Client persona: {persona}'


def _build_system_prompt(entity_type, primary, secondary, specific_tags, generic_tags,
                          subcategory_vocab=None, rules=None, include_persona=True):
    """Build Claude system prompt. Specific tags listed first (preferred), then
    remaining generic tags — Claude sees the full combined list.
    rules: Card A client-rules lines (data, not code — see _load_client_rules).
    include_persona: control-arm toggle for Card 4.2's persona-off eval config."""
    combined = list(specific_tags)
    for t in generic_tags:
        if t not in combined:
            combined.append(t)
    tag_list = '\n'.join(f'- {t}' for t in combined)

    persona_clause = _persona_clause(entity_type, primary, secondary, include_persona)
    specific_note = _specific_tag_note(specific_tags)
    subcat_note = _subcategory_vocab_note(subcategory_vocab)
    rules_note = _client_rules_note(rules)

    return (
        f'You are a tax classification assistant.{persona_clause}\n\n'
        f'Classify each vendor to exactly one tag from this list:\n{tag_list}'
        f'{specific_note}{subcat_note}{rules_note}\n\n'
        'Rules:\n'
        '- Return a JSON array only — no prose, no markdown fences.\n'
        '- Each item: {"id": <int>, "tag": "<tag>", "subcategory": "<specific working label>", "confidence": <0.0-1.0>, "reason": "<brief>"}\n'
        '- "tag" = generic tax category from the list above (maps to IRS form line).\n'
        '- "subcategory" = the Wave category (see list, if given), a proposed new one, or "".\n'
        '- amount_total < 0 is money out; > 0 is money in (sales, refunds, transfers in). '
        'Use the income tags only for money in.\n'
        '- Select only from the tag list above for "tag". If unsure, return low confidence.\n'
        '- Use "Personal - Not Deductible" for clearly personal vendors.\n'
        '- Use "Review with Client" only if truly unclassifiable.\n'
        '- "reason" must be under 12 words, every item, no exceptions. If a client rule applied, '
        'name it in 3-4 words (e.g. "client rule: credit-card->COGS") — never quote the rule text back.'
    )


def _parse_api_response(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.split('\n')[1:-1])
    return json.loads(text)


_PAYLOAD_STAT_KEYS = ('amount_total', 'txn_count', 'amount_sample', 'date_span')


def _tag_batch(batch, api_key, system_prompt):
    payload_items = []
    for i, r in enumerate(batch):
        item = {'id': i, 'vendor': r['vendor']}
        item.update({k: r[k] for k in _PAYLOAD_STAT_KEYS if k in r})
        payload_items.append(item)
    payload = json.dumps(payload_items)
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=_MODEL, max_tokens=4096, system=system_prompt,
        messages=[{'role': 'user', 'content': f'Classify these vendors:\n{payload}'}],
    )
    return _parse_api_response(msg.content[0].text)


def _run_claude_on_vendors(vendor_names, api_key, system_prompt, prog, vendor_stats=None):
    """Call Claude on a list of vendor name strings. Returns vendor→result map.
    vendor_stats: optional {vendor: {amount_total, txn_count, amount_sample, date_span}}
    (Card A). None = bare vendor-name-only payload, unchanged prior behavior."""
    vendor_stats = vendor_stats or {}
    uniq = [{'vendor': v, **vendor_stats.get(v, {})} for v in vendor_names]
    results_map = {}
    batches = [uniq[i:i + _BATCH_SIZE] for i in range(0, len(uniq), _BATCH_SIZE)]
    for b_idx, batch in enumerate(batches):
        try:
            items = _tag_batch(batch, api_key, system_prompt)
            for item in items:
                results_map[batch[item['id']]['vendor']] = item
        except Exception as e:
            for entry in batch:
                results_map[entry['vendor']] = {
                    'tag': 'Review with Client', 'confidence': 0.0, 'reason': f'API error: {e}'}
        prog.progress((b_idx + 1) / max(1, len(batches)))
    return results_map


def _step2_run_pretag(df, specific_tags, cfg, amount_col=None, date_col=None):
    """Extract vendors, run pre-tag pass with progress bar, store in session state."""
    vendor_names = df['Vendor'].dropna().unique().tolist()
    lookup_df    = _load_lookup(cfg['client_id'])
    subcat_vocab = _subcategory_vocab_for_prompt(cfg['client_id'], cfg.get('lookup_subcategories', []))
    rules        = _load_client_rules(cfg['client_id'])
    sys_prompt   = _build_system_prompt(cfg['entity_type'], cfg['primary'], cfg['secondary'],
                                        specific_tags, cfg['generic_tags'], subcat_vocab, rules)
    vendor_stats = _vendor_stats(df, amount_col, date_col)
    lookup_match = _lookup_matcher(lookup_df)
    n_unknown = sum(1 for v in vendor_names if not lookup_match(v))
    prog = st.progress(0.0, text=f'Pre-tagging {n_unknown} vendors with Claude...')
    st.session_state['tagger_pretag_results'] = _run_pretag_pass(
        vendor_names, lookup_df, cfg['api_key'], sys_prompt, prog, vendor_stats)
    prog.empty()


def _run_pretag_pass(vendor_names, lookup_df, api_key, sys_prompt, prog, vendor_stats=None):
    """Pre-tag vendors: lookup CSV fills knowns first, Claude handles the rest.
    Returns {vendor_name: {tag, subcategory, confidence, reason, source}}."""
    lookup_match = _lookup_matcher(lookup_df)
    results = {}
    hits    = {v: lookup_match(v) for v in vendor_names}
    unknown = [v for v in vendor_names if not hits[v]]
    for v in (v for v in vendor_names if hits[v]):
        results[v] = {'tag': hits[v]['tag'], 'subcategory': hits[v]['subcategory'],
                      'confidence': 1.0, 'reason': 'Lookup history', 'source': '📋 Lookup'}
    if unknown and api_key:
        claude = _run_claude_on_vendors(unknown, api_key, sys_prompt, prog, vendor_stats)
        for v, r in claude.items():
            r['source'] = '🤖 Claude'
            results[v] = r
    else:
        prog.progress(1.0)
    return results


# ── Apply all tags to transaction rows ──────────────────────────────────────────

def _build_prep_map(vendor_tbl, lookup_df, pretag_results=None):
    """Vendor → {tag, subcategory, confidence, source} for every vendor with a Category set.
    Card 1.4a fix: a vendor's source reflects who actually decided its value, checked in
    the same precedence _resolve_vendor_category uses to pre-fill it (lookup > rule > pretag):
    - 'lookup' if untouched carryover from lookup CSV history (exact match)
    - 'rule'   if untouched carryover from the deterministic personal-tag engine
    - 'claude' if untouched carryover from this run's Claude/pretag suggestion (exact match) —
      confidence is Claude's own, not hardcoded, so low-confidence unedited rows stay visible
    - 'preparer' otherwise — a genuine decision made this session, whether starting from
      blank or overriding a suggestion (confidence 1.0: a real decision is certain)."""
    lookup_match = _lookup_matcher(lookup_df)
    pretag_results = pretag_results or {}
    prep_map = {}
    for _, r in vendor_tbl.iterrows():
        category = str(r.get(_COL_CATEGORY, '')).strip()
        if not category:
            continue
        vendor = r['Vendor']
        subcategory = str(r.get(_COL_SUBCATEGORY, '') or '').strip()
        suggestion = pretag_results.get(vendor, {})
        rule = _get_auto_rule(vendor, r.get(_COL_DIRECTION, 'debit')) or {}
        hit = lookup_match(vendor) or {}
        if hit and hit['tag'] == category and hit['subcategory'] == subcategory:
            source, confidence = 'lookup', 1.0
        elif rule and rule['subcategory'] == subcategory and (rule['tag'] in ('', category)):
            source, confidence = 'rule', 1.0
        elif suggestion.get('tag') == category and suggestion.get('subcategory', '') == subcategory:
            source, confidence = 'claude', float(suggestion.get('confidence', 1.0))
        else:
            source, confidence = 'preparer', 1.0
        prep_map[vendor] = {'tag': category, 'subcategory': subcategory,
                            'source': source, 'confidence': confidence}
    return prep_map


def _apply_all_tags(df, desc_col, amount_col, vendor_tbl, claude_results, threshold, lookup_df,
                     pretag_results=None, wave_map=None):
    """Map vendor→tag back to every transaction row, debits and credits alike.
    Where the Wave category (Subcategory) is in the Wave mapping, the row's tag comes
    from it, using the row's own direction (e.g. Bank Interest in vs out).
    Priority: preparer-entered/lookup-carried Category/Subcategory → Claude result."""
    prep_map = _build_prep_map(vendor_tbl, lookup_df, pretag_results)

    df = df.copy()
    df['_dir'] = _row_directions(df, amount_col)

    def _tag_row(row):
        if not row['_dir']:
            return pd.Series(['', '', None, '', 'skipped'])
        v = str(row.get('Vendor', _extract_vendor(str(row[desc_col]))))
        prep = prep_map.get(v)
        if prep:
            tag, subcat, conf, reason, source = (prep['tag'], prep['subcategory'],
                                                 prep['confidence'], '', prep['source'])
        else:
            r = claude_results.get(v, {})
            tag, subcat = r.get('tag', 'Review with Client'), r.get('subcategory', '')
            conf = float(r.get('confidence', 0.0))
            reason, source = r.get('reason', ''), 'claude' if conf >= threshold else 'flagged'
            if _is_new_wave(subcat, wave_map):
                source = 'flagged'   # a proposed new Wave category always gets preparer review
        tag = _wave_tag(subcat, row['_dir'], wave_map) or tag
        return pd.Series([tag, subcat, conf, reason, source])

    df[['Tag', 'Subcategory', 'Confidence', 'Reason', 'Tag_Source']] = df.apply(_tag_row, axis=1)
    return df.drop(columns='_dir')


# ── Preparer review helpers ──────────────────────────────────────────────────────

def _flagged_summary(df, amount_col):
    flagged = df[df['Tag_Source'] == 'flagged']
    agg = {'Suggested_Tag': ('Tag', 'first'), 'Suggested_Subcategory': ('Subcategory', 'first'),
           'Confidence': ('Confidence', 'mean'), 'Reason': ('Reason', 'first')}
    if amount_col:
        agg['Amount'] = (amount_col, 'first')
    uniq = flagged.groupby('Vendor', sort=False).agg(**agg).reset_index()
    uniq['Preparer_Tag'] = uniq['Suggested_Tag']
    uniq['Preparer_Subcategory'] = uniq['Suggested_Subcategory']
    return uniq


def _apply_preparer_tags(df, edited, amount_col=None, wave_map=None):
    tag_map = dict(zip(edited['Vendor'], edited['Preparer_Tag']))
    subcat_map = dict(zip(edited['Vendor'], edited.get('Preparer_Subcategory', pd.Series(dtype=str))))
    df = df.copy()
    mask = df['Tag_Source'] == 'flagged'
    df.loc[mask, 'Tag'] = df.loc[mask, 'Vendor'].map(tag_map).fillna('Review with Client')
    df.loc[mask, 'Subcategory'] = df.loc[mask, 'Vendor'].map(subcat_map).fillna('')
    if wave_map:
        dirs = _row_directions(df, amount_col)
        df.loc[mask, 'Tag'] = [_wave_tag(s, d, wave_map) or t for s, d, t in
                               zip(df.loc[mask, 'Subcategory'], dirs[mask], df.loc[mask, 'Tag'])]
    df.loc[mask, 'Tag_Source'] = df.loc[mask].apply(
        lambda r: 'rwc' if r['Tag'] == 'Review with Client' else 'preparer', axis=1)
    df.loc[mask, ['Confidence', 'Reason']] = None
    return df


# ── Output Excel ─────────────────────────────────────────────────────────────────

def _parse_month(date_val):
    """Extract month label (e.g., 'Jan', 'Feb') from a date value. Returns '' on failure."""
    if pd.isna(date_val):
        return ''
    s = str(date_val).strip()
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y', '%Y-%m-%d', '%m/%d'):
        try:
            from datetime import datetime
            dt = datetime.strptime(s.split()[0], fmt)
            return dt.strftime('%b')
        except ValueError:
            continue
    # Try pandas as fallback
    try:
        dt = pd.to_datetime(date_val)
        return dt.strftime('%b')
    except Exception:
        return ''


_MONTH_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _monthly_row(grp, months, amount_col):
    """Build month columns + Total for a group of rows."""
    row = {}
    for m in months:
        month_amt = grp[grp['_month'] == m]['_amount'].sum()
        row[m] = round(month_amt, 2) if month_amt != 0 else None
    row['Total'] = round(grp['_amount'].sum(), 2) if amount_col else None
    return row


def _summary_tag_rows(tagged, amount_col, months):
    """Build detail + subtotal rows grouped by Tag → Subcategory."""
    rows = []
    for tag, tag_grp in tagged.groupby('Tag', sort=True):
        subcats = list(tag_grp.groupby(tag_grp['Subcategory'].fillna(''), sort=True))
        for subcat, sub_grp in subcats:
            row = {'Tag': tag, 'Subcategory': subcat or '(unspecified)', 'Count': len(sub_grp)}
            if months:
                row.update(_monthly_row(sub_grp, months, amount_col))
            else:
                row['Total'] = round(sub_grp['_amount'].sum(), 2) if amount_col else None
            rows.append(row)
        if len(subcats) > 1:
            row = {'Tag': f'{tag} — SUBTOTAL', 'Subcategory': '', 'Count': len(tag_grp)}
            if months:
                row.update(_monthly_row(tag_grp, months, amount_col))
            else:
                row['Total'] = round(tag_grp['_amount'].sum(), 2) if amount_col else None
            rows.append(row)
    return rows


def _build_summary(df, amount_col, date_col=None):
    """Build pivot summary: rows = Tag/Subcategory with subtotals, cols = months (if date_col)."""
    tagged = df[(df['Tag_Source'] != 'skipped') & (df['Tag'].fillna('') != '')].copy()
    if tagged.empty:
        return pd.DataFrame()

    tagged['_amount'] = tagged[amount_col].apply(_parse_amount) if amount_col else 0
    months = []
    if date_col and date_col in tagged.columns:
        tagged['_month'] = tagged[date_col].apply(_parse_month)
        months = [m for m in _MONTH_ORDER if m in tagged['_month'].values]

    rows = _summary_tag_rows(tagged, amount_col, months)

    # Rows with no readable amount are not tagged; show their count only
    skipped = int((df['Tag_Source'] == 'skipped').sum())
    if skipped:
        rows.append({'Tag': 'Not Tagged (no amount)', 'Subcategory': '', 'Count': skipped})

    summary = pd.DataFrame(rows)
    if not summary.empty and amount_col:
        non_sub = summary[~summary['Tag'].str.endswith('— SUBTOTAL')]
        total_row = {'Tag': 'GRAND TOTAL', 'Subcategory': '', 'Count': int(non_sub['Count'].sum()),
                     'Total': round(non_sub['Total'].dropna().sum(), 2)}
        if months:
            for m in months:
                col_vals = non_sub[m] if m in non_sub.columns else pd.Series()
                total_row[m] = round(col_vals.dropna().sum(), 2) if not col_vals.empty else None
        summary = pd.concat([summary, pd.DataFrame([total_row])], ignore_index=True)
    return summary


def _write_output_excel(df, desc_col, amount_col, date_col, cfg):
    """Card 1.4b fix: RWC routing is keyed on Tag == 'Review with Client', not just
    Tag_Source == 'rwc' — Pre-tag mode assigns the RWC tag via Claude/preparer Category
    selection, which never touches the flagged-vendor-correction path that sets 'rwc'.
    RWC rows are excluded from the Tagged sheet, matching Personal's existing split."""
    buf = io.BytesIO()
    out = df.copy().rename(columns={'Tag_Source': 'Tag Source'})
    is_rwc = (out['Tag'] == 'Review with Client') | (out['Tag Source'] == 'rwc')
    personal_df = out[out['Tag'].fillna('').str.startswith('Personal -')]
    rwc_df = out[is_rwc]
    tagged_df = out[~is_rwc]
    summary_df = _build_summary(df, amount_col, date_col)
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        tagged_df.to_excel(writer, sheet_name='Tagged', index=False)
        personal_df.to_excel(writer, sheet_name='Personal', index=False)
        rwc_df.to_excel(writer, sheet_name='Review with Client', index=False)
        if not summary_df.empty:
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
    buf.seek(0)
    return buf


# ── Navigation helpers ────────────────────────────────────────────────────────────

def _back_button(to_step):
    if st.button('← Back', type='secondary', key=f'back_{to_step}'):
        st.session_state['tagger_step'] = to_step
        st.rerun()


def _session_wave_map():
    return _load_wave_mapping(st.session_state['tagger_config']['client_id'])


def _wave_subcategory_options(wave_map, lookup_df, cfg):
    """Wave Category dropdown: Wave categories first, then this client's history and
    the file's Lookup tab (older labels stay selectable so existing rows still show)."""
    history = lookup_df['subcategory'].dropna().unique().tolist() if not lookup_df.empty else []
    return _get_subcategory_options(_wave_categories(wave_map) + history,
                                    cfg.get('lookup_subcategories', []))


# ── Step renderers ────────────────────────────────────────────────────────────────

def _render_step1():
    st.subheader('Step 1 — Setup')
    cfg = st.session_state.get('tagger_config', {})
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        api_key = st.text_input('Anthropic API Key (needed in Step 4 only)',
                                value=cfg.get('api_key', ''), type='password')
    client_id = st.text_input('Client ID (used as lookup filename)', value=cfg.get('client_id', ''))
    et_idx = _ENTITY_TYPES.index(cfg.get('entity_type', _ENTITY_TYPES[0]))
    entity_type = st.selectbox('Entity Type', _ENTITY_TYPES, index=et_idx)
    primary = st.text_input('Primary Business Activity', value=cfg.get('primary', ''))
    secondary = st.text_input('Secondary Activity (optional)', value=cfg.get('secondary', ''))
    threshold = st.slider('Confidence Threshold (%)', 0, 100, cfg.get('threshold_pct', 75))
    mode_opts = ['Review-first (preparer tags, Claude fills gaps)',
                 'Pre-tag (Claude tags all vendors first, preparer reviews)']
    mode_default = 1 if cfg.get('tagging_mode') == 'pretag' else 0
    tagging_mode_label = st.radio('Tagging Mode', mode_opts, index=mode_default)
    tagging_mode = 'pretag' if 'Pre-tag' in tagging_mode_label else 'review_first'
    generic_tags = _load_generic_tags()
    st.caption(f'Category list: {len(generic_tags)} tags from rasrich_tag_lists.csv — '
               'always sent to Claude. The file\'s Lookup tab (Step 2) can add extra Category '
               'and Subcategory vocabulary specific to this client.')

    if st.button('Next →', type='primary'):
        if not all([client_id.strip(), primary.strip()]):
            st.error('Client ID and Primary Activity are required.')
            return
        # Mode changed — discard stale pretag table so Step 3 rebuilds fresh.
        if tagging_mode != cfg.get('tagging_mode'):
            for k in ('tagger_vendor_tbl', 'tagger_pretag_results'):
                st.session_state.pop(k, None)
        st.session_state['tagger_config'] = _build_tagger_config(
            api_key, client_id, entity_type, primary, secondary,
            threshold, generic_tags, tagging_mode, cfg)
        st.session_state['tagger_step'] = 2
        st.rerun()


def _build_tagger_config(api_key, client_id, entity_type, primary, secondary,
                          threshold, generic_tags, tagging_mode, prior_cfg):
    return {
        'api_key': api_key, 'client_id': client_id.strip(), 'entity_type': entity_type,
        'primary': primary, 'secondary': secondary,
        'threshold': threshold / 100, 'threshold_pct': threshold,
        'generic_tags': generic_tags,
        'specific_tags': prior_cfg.get('specific_tags', []),
        'lookup_subcategories': prior_cfg.get('lookup_subcategories', []),
        'tagging_mode': tagging_mode,
    }


def _load_upload_file(uploaded):
    """Parse uploaded file. Returns (df, xl) tuple or (None, None) on error."""
    try:
        if uploaded.name.lower().endswith('.csv'):
            return pd.read_csv(uploaded), None
        xl = pd.ExcelFile(uploaded)
        n_sheets = len(xl.sheet_names)
        sheet = st.selectbox('Select sheet', xl.sheet_names) if n_sheets > 1 else xl.sheet_names[0]
        return xl.parse(sheet), xl
    except Exception as e:
        st.error(f'Could not read file: {e}')
        return None, None


def _build_signed_amount(df, debit_col, credit_col):
    """Combine separate Debit/Credit columns into a single signed '_signed_amount' column.
    Debit values (positive expenses) become negative; credit values stay positive.
    Blank/NaN cells are treated as 0 — uses pd.to_numeric to safely handle nan from _parse_amount."""
    df = df.copy()
    debits  = pd.to_numeric(df[debit_col].apply(_parse_amount), errors='coerce').fillna(0.0)
    credits = pd.to_numeric(df[credit_col].apply(_parse_amount), errors='coerce').fillna(0.0) if credit_col else pd.Series(0.0, index=df.index)
    df['_signed_amount'] = credits - debits
    return df


def _select_amount_cols(cols):
    """Render amount format radio and pickers. Returns (amount_col, debit_col, credit_col).
    debit_col is non-None only in two-column mode."""
    mode = st.radio(
        'Amount format',
        ['Single column (signed, e.g. Chase: -250.00)', 'Two columns (Debit / Credit, both positive)'],
        index=0,
        help='Use "Single column" when expenses are negative numbers. '
             'Use "Two columns" when your file has separate Debit and Credit columns.',
    )
    if mode.startswith('Single'):
        amt = st.selectbox('Amount column', ['(none)'] + cols)
        return (None if amt == '(none)' else amt), None, None
    debit_kw  = ('debit', 'subtracted', 'withdrawal')
    credit_kw = ('credit', 'added', 'deposit')
    debit_default  = next((i for i, c in enumerate(cols) if any(k in str(c).lower() for k in debit_kw)), 0)
    credit_default = next((i for i, c in enumerate(cols) if any(k in str(c).lower() for k in credit_kw)), 0)
    debit_col  = st.selectbox('Debit column (expenses — positive values)', cols, index=debit_default)
    credit_col = st.selectbox('Credit column (income — positive values, optional)', ['(none)'] + cols,
                              index=credit_default + 1)
    return '_signed_amount', debit_col, (None if credit_col == '(none)' else credit_col)


def _select_columns(df):
    """Render column selectors for description, amount format, and date.
    Returns (desc_col, amount_col, date_col, debit_col, credit_col)."""
    cols = df.columns.tolist()
    desc_default = next((i for i, c in enumerate(cols) if 'desc' in str(c).lower()), 0)
    desc_col = st.selectbox('Description column', cols, index=desc_default)
    amount_col, debit_col, credit_col = _select_amount_cols(cols)
    date_default = next((i for i, c in enumerate(cols) if 'date' in str(c).lower()), 0)
    date_col = st.selectbox('Date column (for monthly summary pivot)', ['(none)'] + cols,
                            index=date_default + 1 if date_default is not None else 0)
    date_col = None if date_col == '(none)' else date_col
    preview_cols = [desc_col]
    if debit_col:
        preview_cols += [debit_col] + ([credit_col] if credit_col else [])
    elif amount_col:
        preview_cols.append(amount_col)
    if date_col:
        preview_cols.append(date_col)
    st.dataframe(df[preview_cols].head(5))
    return desc_col, amount_col, date_col, debit_col, credit_col


def _show_lookup_tab_status(category_tags, subcategory_tags, lookup_warn):
    if category_tags:
        msg = f'Lookup tab found — {len(category_tags)} Category value(s)'
        if subcategory_tags:
            msg += f' + {len(subcategory_tags)} Subcategory value(s)'
        st.success(msg + ' loaded as extra dropdown options.')
    elif lookup_warn:
        st.warning(lookup_warn)
    else:
        st.info('No Lookup tab found — Category dropdown will show the full 52-tag list only; '
                'Subcategory dropdown will show this client\'s prior history only.')


def _render_step2():
    st.subheader('Step 2 — Upload Transactions')
    _back_button(1)
    uploaded = st.file_uploader('Upload Excel or CSV', type=['xlsx', 'xls', 'csv'], key='tagger_upload')
    if uploaded is None:
        return
    df, xl = _load_upload_file(uploaded)
    if df is None:
        return

    desc_col, amount_col, date_col, debit_col, credit_col = _select_columns(df)

    category_tags, subcategory_tags, lookup_warn = _load_lookup_tab_vocab(xl)
    _show_lookup_tab_status(category_tags, subcategory_tags, lookup_warn)

    if st.button('Next →', type='primary'):
        df = df.copy()
        if debit_col:
            df = _build_signed_amount(df, debit_col, credit_col)
        df['Vendor'] = df[desc_col].apply(_extract_vendor)
        st.session_state['tagger_df'] = df
        st.session_state['tagger_desc_col'] = desc_col
        st.session_state['tagger_amount_col'] = amount_col
        st.session_state['tagger_date_col'] = date_col
        st.session_state['tagger_config']['specific_tags'] = category_tags
        st.session_state['tagger_config']['lookup_subcategories'] = subcategory_tags
        st.session_state.pop('tagger_vendor_tbl', None)
        cfg = st.session_state['tagger_config']
        if cfg.get('tagging_mode') == 'pretag':
            _step2_run_pretag(df, category_tags, cfg, amount_col, date_col)
        st.session_state['tagger_step'] = 3
        st.rerun()


def _render_step3():
    st.subheader('Step 3 — Preparer Review')
    _back_button(2)
    df          = st.session_state['tagger_df']
    desc_col    = st.session_state['tagger_desc_col']
    amount_col  = st.session_state['tagger_amount_col']
    cfg         = st.session_state['tagger_config']
    mode        = cfg.get('tagging_mode', 'review_first')

    lookup_df = _load_lookup(cfg['client_id'])
    wave_map = _load_wave_mapping(cfg['client_id'])
    category_opts = _get_category_options(cfg['generic_tags'], cfg['specific_tags'])
    subcategory_opts = _wave_subcategory_options(wave_map, lookup_df, cfg)

    if 'tagger_vendor_tbl' not in st.session_state:
        pretag = st.session_state.get('tagger_pretag_results') if mode == 'pretag' else None
        st.session_state['tagger_vendor_tbl'] = _build_vendor_table(
            df, desc_col, amount_col, lookup_df, pretag, wave_map)

    full_tbl = st.session_state['tagger_vendor_tbl']
    subcategory_opts += [w for w in full_tbl[_COL_SUBCATEGORY].dropna().unique()
                         if w and w not in subcategory_opts]   # Claude's 🆕 proposals
    _render_add_wave_category(cfg['client_id'], category_opts)

    if mode == 'pretag':
        _render_step3_pretag_view(full_tbl, category_opts, subcategory_opts)
        return

    st.caption('Unique vendors, money in and out. Pick the Wave Category — the tax Category '
               'fills in on Apply. Leave blank to send to Claude.')
    pending = _pending_vendors(full_tbl)
    tagged_count = len(full_tbl) - len(pending)
    st.info(f'Tagged: **{tagged_count} / {len(full_tbl)}** vendors · '
            f'**{len(pending)}** remaining → Claude will tag these')
    if pending.empty:
        if st.button('Next → Claude Tags the Rest', type='primary'):
            st.session_state['tagger_step'] = 4
            st.rerun()
        return
    _render_step3_editor(pending, category_opts, subcategory_opts, full_tbl)


def _render_step3_editor(tbl, category_opts, subcategory_opts, full_tbl,
                          show_source=False, editor_key='vendor_review_editor',
                          show_buttons=True):
    """Render vendor data_editor. Returns edited DataFrame.
    show_source: include read-only Source column (pre-tag mode).
    show_buttons: render Apply/Next buttons (review-first mode only)."""
    display_cols = [c for c in ['Vendor', 'Count', 'Total Amount', _COL_DIRECTION] if c in tbl.columns]
    if show_source and 'Source' in tbl.columns:
        display_cols.append('Source')
    display_cols += [_COL_CATEGORY, _COL_SUBCATEGORY]
    col_cfg = {
        _COL_CATEGORY: st.column_config.SelectboxColumn(
            _COL_CATEGORY, options=category_opts, required=False,
            help='Tax category. Fills in from the Wave Category on Apply; pick it directly '
                 'only when no Wave Category fits.'),
        _COL_SUBCATEGORY: st.column_config.SelectboxColumn(
            'Wave Category', options=subcategory_opts, required=False,
            help='Wave bookkeeping category. Sets the tax Category via wave_mapping.csv.'),
    }
    disabled = [c for c in display_cols if c not in (_COL_CATEGORY, _COL_SUBCATEGORY)]
    edited = st.data_editor(
        tbl[display_cols].reset_index(drop=True),
        column_config=col_cfg, disabled=disabled,
        use_container_width=True, hide_index=True, key=editor_key,
    )
    if show_buttons:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button('Apply & Refresh List', type='secondary'):
                st.session_state['tagger_vendor_tbl'] = _merge_edits(full_tbl, edited, _session_wave_map())
                st.rerun()
        with col_b:
            if st.button('Next → Claude Tags the Rest', type='primary'):
                st.session_state['tagger_vendor_tbl'] = _merge_edits(full_tbl, edited, _session_wave_map())
                st.session_state['tagger_step'] = 4
                st.rerun()
    return edited


def _render_add_wave_category(client_id, category_opts):
    """Option B: preparer adds a client-specific Wave category (name + tax tag)."""
    with st.expander('➕ Add a Wave category for this client'):
        c1, c2, c3 = st.columns([3, 3, 1])
        name = c1.text_input('Wave category name', key='new_wave_name')
        tag = c2.selectbox('Tax tag', category_opts, key='new_wave_tag')
        if c3.button('Add', key='new_wave_add'):
            added = _add_client_wave_categories(client_id, [(name, tag)])
            if added:
                st.session_state['tagger_vendor_tbl'] = _fill_tags_from_wave(
                    st.session_state['tagger_vendor_tbl'], _load_wave_mapping(client_id))
                st.rerun()
            st.warning('Enter a new name and a tax tag (name may already exist).')


def _render_step3_pretag_view(full_tbl, category_opts, subcategory_opts):
    """Step 3 pre-tag mode: collapsed expander for pre-tagged, main editor for pending.
    Vendors where Claude proposed a new Wave category (🆕) count as pending."""
    src       = full_tbl['Source'].fillna('') if 'Source' in full_tbl.columns \
                else pd.Series('', index=full_tbl.index)
    is_new    = src.str.contains('🆕')
    pending   = full_tbl[(full_tbl[_COL_CATEGORY].fillna('') == '') | is_new]
    pretagged = full_tbl[(src != '') & ~is_new]
    n_pre, n_pend = len(pretagged), len(pending)
    st.caption(f'🤖 Pre-tagged: **{n_pre}** · Needs your attention: **{n_pend}** · '
               f'Total: **{len(full_tbl)}** unique vendors')
    with st.expander(f'🤖 Pre-tagged vendors ({n_pre}) — expand to review & correct',
                     expanded=False):
        if pretagged.empty:
            st.caption('None pre-tagged.')
            edited_pre = pretagged
        else:
            edited_pre = _render_step3_editor(
                pretagged, category_opts, subcategory_opts, full_tbl,
                show_source=True, editor_key='pretag_ed', show_buttons=False)
    if pending.empty:
        st.success('All vendors pre-tagged. Review the section above if needed.')
        edited_pend = pending
    else:
        st.markdown(f'**Needs your attention ({n_pend})**')
        edited_pend = _render_step3_editor(
            pending, category_opts, subcategory_opts, full_tbl,
            editor_key='pending_ed', show_buttons=False)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button('Apply & Refresh', type='secondary', key='pretag_apply'):
            wave_map = _session_wave_map()
            updated = _merge_edits(_merge_edits(full_tbl, edited_pre, wave_map), edited_pend, wave_map)
            st.session_state['tagger_vendor_tbl'] = updated
            st.rerun()
    with col_b:
        if st.button('Next → Claude Tags the Rest', type='primary', key='pretag_next'):
            wave_map = _session_wave_map()
            updated = _merge_edits(_merge_edits(full_tbl, edited_pre, wave_map), edited_pend, wave_map)
            st.session_state['tagger_vendor_tbl'] = updated
            st.session_state['tagger_step'] = 4
            st.rerun()


def _render_step4():
    st.subheader('Step 4 — Claude Tags the Rest')
    _back_button(3)
    cfg = st.session_state['tagger_config']
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    amount_col = st.session_state['tagger_amount_col']
    date_col = st.session_state.get('tagger_date_col')
    vendor_tbl = st.session_state['tagger_vendor_tbl']

    pending = _pending_vendors(vendor_tbl)
    vendor_names = pending['Vendor'].tolist()

    if 'Tag' not in df.columns:
        n_batches = max(1, (len(vendor_names) + _BATCH_SIZE - 1) // _BATCH_SIZE)
        st.info(f'Sending {len(vendor_names)} vendor(s) to Claude Haiku (~{n_batches} API call(s))')
        if st.button('Run Claude →', type='primary'):
            _run_step4_claude_call(cfg, df, desc_col, amount_col, date_col, vendor_tbl, vendor_names)
        return
    wave_map = _load_wave_mapping(cfg['client_id'])
    _render_step4_review(df, cfg['generic_tags'] + [t for t in cfg['specific_tags']
                                                     if t not in cfg['generic_tags']], wave_map)


def _run_step4_claude_call(cfg, df, desc_col, amount_col, date_col, vendor_tbl, vendor_names):
    if not cfg.get('api_key', '').strip():
        st.error('API Key required — go back to Step 1 and enter it.')
        return
    subcat_vocab = _subcategory_vocab_for_prompt(cfg['client_id'], cfg.get('lookup_subcategories', []))
    rules = _load_client_rules(cfg['client_id'])
    sys_prompt = _build_system_prompt(
        cfg['entity_type'], cfg['primary'], cfg['secondary'],
        cfg['specific_tags'], cfg['generic_tags'], subcat_vocab, rules)
    vendor_stats = _vendor_stats(df, amount_col, date_col)
    prog = st.progress(0.0, text='Calling Claude Haiku...')
    try:
        claude_results = _run_claude_on_vendors(
            vendor_names, cfg['api_key'], sys_prompt, prog, vendor_stats)
        prog.empty()
        lookup_df = _load_lookup(cfg['client_id'])
        pretag_results = st.session_state.get('tagger_pretag_results')
        st.session_state['tagger_df'] = _apply_all_tags(
            df, desc_col, amount_col, vendor_tbl, claude_results, cfg['threshold'], lookup_df,
            pretag_results, _load_wave_mapping(cfg['client_id']))
        st.rerun()
    except Exception as e:
        st.error(f'Tagging failed: {e}')


def _render_step4_review(df, tags, wave_map=None):
    lookup = (df['Tag_Source'] == 'lookup').sum()
    auto = (df['Tag_Source'] == 'claude').sum()
    prep = (df['Tag_Source'] == 'preparer').sum()
    flagged = (df['Tag_Source'] == 'flagged').sum()
    skipped = (df['Tag_Source'] == 'skipped').sum()
    st.success(f'From lookup history: {lookup} · Preparer: {prep} · Claude auto: {auto} · '
               f'Needs review: {flagged} · No amount (skipped): {skipped}')
    if flagged == 0:
        if st.button('Next → Output', type='primary'):
            st.session_state['tagger_step'] = 5
            st.rerun()
        return
    amount_col = st.session_state['tagger_amount_col']
    uniq = _flagged_summary(df, amount_col)
    st.info(f'{len(uniq)} vendor(s) below confidence threshold — assign tags below.')
    display_cols = ['Vendor', 'Confidence', 'Suggested_Tag', 'Suggested_Subcategory', 'Reason', 'Preparer_Tag', 'Preparer_Subcategory']
    if amount_col and 'Amount' in uniq.columns:
        display_cols = ['Vendor', 'Amount', 'Confidence', 'Suggested_Tag', 'Suggested_Subcategory', 'Reason', 'Preparer_Tag', 'Preparer_Subcategory']
    editable_cols = ('Preparer_Tag', 'Preparer_Subcategory')
    edited = st.data_editor(
        uniq[display_cols],
        column_config={
            'Preparer_Tag': st.column_config.SelectboxColumn(
                'Your Tag', options=tags, required=True),
            'Preparer_Subcategory': st.column_config.TextColumn(
                'Your Wave Category',
                help='Keep, rename or clear. A name not in the Wave mapping is added to this '
                     'client\'s mapping at Step 5, with Your Tag.'),
        },
        disabled=[c for c in display_cols if c not in editable_cols],
        use_container_width=True, hide_index=True,
    )
    if st.button('Apply Tags & Continue', type='primary'):
        st.session_state['tagger_df'] = _apply_preparer_tags(df, edited, amount_col, wave_map)
        st.session_state['tagger_step'] = 5
        st.rerun()


def _vendor_hit_rate_line(df):
    """P3-lite (Card 1.3): one-line vendor-level memory hit-rate summary for Step 5.
    Counts unique vendors (not rows) so a heavily-repeated vendor doesn't skew the rate."""
    tagged = df[df['Tag_Source'] != 'skipped']
    sources = tagged.drop_duplicates('Vendor')['Tag_Source']
    total = len(sources)
    if total == 0:
        return 'Memory: 0/0 vendors (0%) · Claude: 0 · Preparer: 0'
    mem_hits = int((sources == 'lookup').sum())
    claude_ct = int((sources == 'claude').sum())
    prep_ct = int(sources.isin(['preparer', 'rwc']).sum())
    hit_rate = round(100 * mem_hits / total)
    return f'Memory: {mem_hits}/{total} vendors ({hit_rate}%) · Claude: {claude_ct} · Preparer: {prep_ct}'


def _render_step5():
    st.subheader('Step 5 — Output')
    _back_button(4)
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    amount_col = st.session_state['tagger_amount_col']
    date_col = st.session_state.get('tagger_date_col')
    cfg = st.session_state['tagger_config']
    lookup = (df['Tag_Source'] == 'lookup').sum()
    auto = (df['Tag_Source'] == 'claude').sum()
    preparer = (df['Tag_Source'] == 'preparer').sum()
    rwc = ((df['Tag'] == 'Review with Client') | (df['Tag_Source'] == 'rwc')).sum()
    personal = df['Tag'].fillna('').str.startswith('Personal -').sum()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric('From lookup history', int(lookup))
    col2.metric('Claude auto-tagged', int(auto))
    col3.metric('Preparer-tagged', int(preparer))
    col4.metric('Personal', int(personal))
    col5.metric('Review with Client', int(rwc))
    st.caption(_vendor_hit_rate_line(df))
    summary_df = _build_summary(df, amount_col, date_col)
    if not summary_df.empty:
        st.subheader('Summary — Monthly Pivot')
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    buf = _write_output_excel(df, desc_col, amount_col, date_col, cfg)
    st.download_button('Download Tagged File', data=buf,
                       file_name=f"{cfg['client_id']}_tagged.xlsx",
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       type='primary')
    entries = _collect_lookup_entries(df, desc_col)
    _save_lookup(cfg['client_id'], entries)
    st.info(f"Lookup saved: {len(entries)} entries → {cfg['client_id']}_lookup.csv")
    added = _add_client_wave_categories(
        cfg['client_id'], _new_wave_rows_from_output(df, _load_wave_mapping(cfg['client_id'])))
    if added:
        st.info(f"New Wave categories added to {cfg['client_id']}_wave_mapping.csv: {', '.join(added)}")
    if st.button('Start New Run', type='secondary'):
        for k in ['tagger_step', 'tagger_config', 'tagger_df',
                  'tagger_desc_col', 'tagger_amount_col', 'tagger_date_col', 'tagger_vendor_tbl']:
            st.session_state.pop(k, None)
        st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────────────

def render():
    st.title('Transaction Tagger')
    st.markdown('---')
    if 'tagger_step' not in st.session_state:
        st.session_state['tagger_step'] = 1
    step = st.session_state['tagger_step']
    step_names = ['Setup', 'Upload', 'Preparer Tag', 'Claude Tag', 'Output']
    cols = st.columns(5)
    for i, (col, name) in enumerate(zip(cols, step_names), 1):
        col.markdown(f'**{i}. {name}**' if i == step else f'{i}. {name}')
    st.markdown('---')
    {1: _render_step1, 2: _render_step2, 3: _render_step3,
     4: _render_step4, 5: _render_step5}[step]()


render()
