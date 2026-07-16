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
_ENTITY_TYPES = ['Sole Prop / SMLLC', 'S-Corp', 'Partnership / MMLLC']
_MODEL = 'claude-haiku-4-5'
_BATCH_SIZE = 30

# Column names for the vendor review table
_COL_CATEGORY    = 'Category'
_COL_SUBCATEGORY = 'Subcategory'

# Auto-personal patterns → specific sub-type labels
_AUTO_PERSONAL_PATTERNS = [
    (re.compile(r'^ATM\b', re.I),                                                    'Personal - ATM'),
    (re.compile(r'\bBANK FEE\b|\bSERVICE CHARGE\b|\bMONTHLY (MAINTENANCE|SERVICE)\b', re.I), 'Personal - Bank Charges'),
    (re.compile(r'\bOVERDRAFT\b|\bNSF\b|\bINSUFFICIENT FUNDS\b', re.I),             'Personal - Bank Charges'),
    (re.compile(r'^CONTRA\b', re.I),                                                  'Personal - Contra'),
    (re.compile(r'\bRETURNED ITEM\b|\bREVERSAL\b', re.I),                            'Personal - Reversal'),
]
_PERSONAL_AUTO_TAGS = sorted({label for _, label in _AUTO_PERSONAL_PATTERNS})
_ALWAYS_TAGS = ['Personal - Not Deductible'] + _PERSONAL_AUTO_TAGS + ['Review with Client']

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


def _get_auto_personal_tag(vendor):
    """Return specific personal sub-type label if vendor matches, else ''."""
    for pat, label in _AUTO_PERSONAL_PATTERNS:
        if pat.search(str(vendor)):
            return label
    return ''


# ── Tag lists ────────────────────────────────────────────────────────────────────

def _load_generic_tags():
    """Full 52-tag list from rasrich_tag_lists.csv — always available."""
    df = pd.read_csv(_TAG_LIST_PATH)
    tags = df['tag'].dropna().tolist()
    for t in _ALWAYS_TAGS:
        if t not in tags:
            tags.append(t)
    return tags


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

def _filter_expense_rows(df, amount_col):
    """Rows treated as expenses for the vendor table. Debit-only columns (e.g.
    Subtracted — all positive): no negative values exist, so treat all non-null
    rows as expenses instead of returning an empty table."""
    if not amount_col:
        return df.copy()
    expense_df = df[df[amount_col].apply(_is_expense)].copy()
    if expense_df.empty and amount_col != '_signed_amount':
        parsed = df[amount_col].apply(_parse_amount)
        if parsed.dropna().gt(0).all():
            expense_df = df[parsed.fillna(0) > 0].copy()
    return expense_df


def _resolve_vendor_category(v, lookup_map, pretag_results):
    if v in lookup_map:
        return lookup_map[v]
    auto = _get_auto_personal_tag(v)
    if auto:
        return auto
    return pretag_results[v]['tag'] if pretag_results and v in pretag_results else ''


def _resolve_vendor_subcategory(v, subcat_map, pretag_results):
    if v in subcat_map:
        return subcat_map[v]
    return pretag_results[v].get('subcategory', '') if pretag_results and v in pretag_results else ''


def _resolve_vendor_source(v, lookup_map, pretag_results):
    if v in lookup_map:
        return '📋 Lookup'
    if _get_auto_personal_tag(v):
        return '⚡ Auto'
    return pretag_results[v]['source'] if v in pretag_results else ''


def _build_vendor_table(df, desc_col, amount_col, lookup_df, pretag_results=None):
    """Group by extracted Vendor. Returns unique-vendor DataFrame with pre-filled tags.
    If pretag_results provided, adds Source column (⚡ Auto / 📋 Lookup / 🤖 Claude / blank)."""
    expense_df = _filter_expense_rows(df, amount_col)
    if expense_df.empty:
        return pd.DataFrame(columns=['Vendor', 'Count', 'Total Amount', _COL_CATEGORY, _COL_SUBCATEGORY])

    agg = {'Count': ('Vendor', 'count')}
    if amount_col:
        agg['Total Amount'] = (amount_col, lambda x: round(x.apply(_parse_amount).dropna().sum(), 2))
    grp = expense_df.groupby('Vendor', sort=False).agg(**agg).reset_index()

    lookup_map = dict(zip(lookup_df['vendor_name'], lookup_df['tag'])) if not lookup_df.empty else {}
    subcat_map = dict(zip(lookup_df['vendor_name'], lookup_df.get('subcategory', pd.Series()))) \
        if not lookup_df.empty else {}

    grp[_COL_CATEGORY] = grp['Vendor'].apply(
        lambda v: _resolve_vendor_category(v, lookup_map, pretag_results))
    grp[_COL_SUBCATEGORY] = grp['Vendor'].apply(
        lambda v: _resolve_vendor_subcategory(v, subcat_map, pretag_results))

    if pretag_results is not None:
        grp['Source'] = grp['Vendor'].apply(
            lambda v: _resolve_vendor_source(v, lookup_map, pretag_results))
    return grp


def _merge_edits(full_tbl, edited_view):
    """Write edits from the pending-only view back into the full vendor table."""
    edit_map = {r['Vendor']: {_COL_CATEGORY:    str(r.get(_COL_CATEGORY, '')).strip(),
                               _COL_SUBCATEGORY: str(r.get(_COL_SUBCATEGORY, '')).strip()}
                for _, r in edited_view.iterrows()}
    full = full_tbl.copy()
    for idx, row in full.iterrows():
        if row['Vendor'] in edit_map:
            full.at[idx, _COL_CATEGORY]    = edit_map[row['Vendor']][_COL_CATEGORY]
            full.at[idx, _COL_SUBCATEGORY] = edit_map[row['Vendor']][_COL_SUBCATEGORY]
    return full


def _pending_vendors(tbl):
    """Rows where Category is blank → still need tagging. Subcategory is optional
    and doesn't gate whether a vendor needs preparer/Claude attention."""
    return tbl[tbl[_COL_CATEGORY].fillna('') == '']


# ── Claude API ───────────────────────────────────────────────────────────────────

def _subcategory_vocab_for_prompt(client_id, lookup_tab_subcategories):
    """Combined, deduped subcategory vocabulary (lookup CSV history + this file's
    Lookup tab), no blank entry. Hints Claude toward reusing an existing label
    instead of inventing a new variant of the same concept."""
    lookup_df = _load_lookup(client_id)
    client_subcats = lookup_df['subcategory'].dropna().unique().tolist() if not lookup_df.empty else []
    return [t for t in _get_subcategory_options(client_subcats, lookup_tab_subcategories) if t]


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
        '\n\nThis client has used these subcategory labels before. Reuse one when it '
        'fits, instead of inventing a new variant of the same concept (e.g. do not '
        'return "Medical Insurance" if "Health Insurance" is already in this list):\n'
        + '\n'.join(f'- {t}' for t in subcategory_vocab)
    )


def _build_system_prompt(entity_type, primary, secondary, specific_tags, generic_tags,
                          subcategory_vocab=None):
    """Build Claude system prompt. Specific tags listed first (preferred), then
    remaining generic tags — Claude sees the full combined list."""
    combined = list(specific_tags)
    for t in generic_tags:
        if t not in combined:
            combined.append(t)
    tag_list = '\n'.join(f'- {t}' for t in combined)

    persona = f'Entity type: {entity_type}. Primary activity: {primary}.'
    if secondary:
        persona += f' Secondary activity: {secondary}.'

    specific_note = _specific_tag_note(specific_tags)
    subcat_note = _subcategory_vocab_note(subcategory_vocab)

    return (
        f'You are a tax classification assistant. Client persona: {persona}\n\n'
        f'Classify each vendor to exactly one tag from this list:\n{tag_list}'
        f'{specific_note}{subcat_note}\n\n'
        'Rules:\n'
        '- Return a JSON array only — no prose, no markdown fences.\n'
        '- Each item: {"id": <int>, "tag": "<tag>", "subcategory": "<specific working label>", "confidence": <0.0-1.0>, "reason": "<brief>"}\n'
        '- "tag" = generic tax category from the list above (maps to IRS form line).\n'
        '- "subcategory" = specific preparer working label describing the actual expense type '
        '(e.g., tag="Insurance - General" → subcategory="Health Insurance", '
        'tag="Supplies" → subcategory="Office Supplies"). Be specific and consistent.\n'
        '- Select only from the tag list above for "tag". If unsure, return low confidence.\n'
        '- Use "Personal - Not Deductible" for clearly personal vendors.\n'
        '- Use "Review with Client" only if truly unclassifiable.'
    )


def _parse_api_response(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.split('\n')[1:-1])
    return json.loads(text)


def _tag_batch(batch, api_key, system_prompt):
    payload = json.dumps([{'id': i, 'vendor': r['vendor']} for i, r in enumerate(batch)])
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=_MODEL, max_tokens=2048, system=system_prompt,
        messages=[{'role': 'user', 'content': f'Classify these vendors:\n{payload}'}],
    )
    return _parse_api_response(msg.content[0].text)


def _run_claude_on_vendors(vendor_names, api_key, system_prompt, prog):
    """Call Claude on a list of vendor name strings. Returns vendor→result map."""
    uniq = [{'vendor': v} for v in vendor_names]
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


def _step2_run_pretag(df, specific_tags, cfg):
    """Extract vendors, run pre-tag pass with progress bar, store in session state."""
    vendor_names = df['Vendor'].dropna().unique().tolist()
    lookup_df    = _load_lookup(cfg['client_id'])
    subcat_vocab = _subcategory_vocab_for_prompt(cfg['client_id'], cfg.get('lookup_subcategories', []))
    sys_prompt   = _build_system_prompt(cfg['entity_type'], cfg['primary'], cfg['secondary'],
                                        specific_tags, cfg['generic_tags'], subcat_vocab)
    lookup_map   = dict(zip(lookup_df['vendor_name'], lookup_df['tag'])) \
        if not lookup_df.empty else {}
    n_unknown = sum(1 for v in vendor_names if v not in lookup_map)
    prog = st.progress(0.0, text=f'Pre-tagging {n_unknown} vendors with Claude...')
    st.session_state['tagger_pretag_results'] = _run_pretag_pass(
        vendor_names, lookup_df, cfg['api_key'], sys_prompt, prog)
    prog.empty()


def _run_pretag_pass(vendor_names, lookup_df, api_key, sys_prompt, prog):
    """Pre-tag vendors: lookup CSV fills knowns first, Claude handles the rest.
    Returns {vendor_name: {tag, subcategory, confidence, reason, source}}."""
    lookup_map = dict(zip(lookup_df['vendor_name'], lookup_df['tag'])) if not lookup_df.empty else {}
    sub_map = dict(zip(lookup_df['vendor_name'], lookup_df.get('subcategory', pd.Series()))) \
        if not lookup_df.empty else {}
    results = {}
    known   = [v for v in vendor_names if v in lookup_map]
    unknown = [v for v in vendor_names if v not in lookup_map]
    for v in known:
        results[v] = {'tag': lookup_map[v], 'subcategory': sub_map.get(v, ''),
                      'confidence': 1.0, 'reason': 'Lookup history', 'source': '📋 Lookup'}
    if unknown and api_key:
        claude = _run_claude_on_vendors(unknown, api_key, sys_prompt, prog)
        for v, r in claude.items():
            r['source'] = '🤖 Claude'
            results[v] = r
    else:
        prog.progress(1.0)
    return results


# ── Apply all tags to transaction rows ──────────────────────────────────────────

def _build_prep_map(vendor_tbl, lookup_df):
    """Vendor → {tag, subcategory, source} for every vendor with a Category set.
    source = 'lookup' if the value is an untouched carryover from lookup CSV history
    (exact match on both Category and Subcategory), else 'preparer' — a genuine
    decision made this session, whether starting from blank or overriding a lookup
    suggestion."""
    lookup_map = dict(zip(lookup_df['vendor_name'], lookup_df['tag'])) if not lookup_df.empty else {}
    subcat_map = dict(zip(lookup_df['vendor_name'], lookup_df.get('subcategory', pd.Series()))) \
        if not lookup_df.empty else {}
    prep_map = {}
    for _, r in vendor_tbl.iterrows():
        category = str(r.get(_COL_CATEGORY, '')).strip()
        if not category:
            continue
        vendor = r['Vendor']
        subcategory = str(r.get(_COL_SUBCATEGORY, '')).strip()
        is_untouched = lookup_map.get(vendor) == category and subcat_map.get(vendor, '') == subcategory
        prep_map[vendor] = {'tag': category, 'subcategory': subcategory,
                            'source': 'lookup' if is_untouched else 'preparer'}
    return prep_map


def _apply_all_tags(df, desc_col, amount_col, vendor_tbl, claude_results, threshold, lookup_df):
    """Map vendor→tag back to every transaction row.
    Category and Subcategory are independent fields — neither is derived from the other.
    Priority: preparer-entered/lookup-carried Category/Subcategory → Claude result."""
    prep_map = _build_prep_map(vendor_tbl, lookup_df)

    df = df.copy()

    def _tag_row(row):
        if amount_col and not _is_expense(row.get(amount_col, 0)):
            return pd.Series(['', '', None, '', 'income'])
        v = str(row.get('Vendor', _extract_vendor(str(row[desc_col]))))
        prep = prep_map.get(v)
        if prep:
            return pd.Series([prep['tag'], prep['subcategory'], 1.0, '', prep['source']])
        r = claude_results.get(v, {})
        tag = r.get('tag', 'Review with Client')
        subcat = r.get('subcategory', '')
        conf = float(r.get('confidence', 0.0))
        return pd.Series([tag, subcat, conf, r.get('reason', ''), 'claude' if conf >= threshold else 'flagged'])

    df[['Tag', 'Subcategory', 'Confidence', 'Reason', 'Tag_Source']] = df.apply(_tag_row, axis=1)
    return df


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


def _apply_preparer_tags(df, edited):
    tag_map = dict(zip(edited['Vendor'], edited['Preparer_Tag']))
    subcat_map = dict(zip(edited['Vendor'], edited.get('Preparer_Subcategory', pd.Series(dtype=str))))
    df = df.copy()
    mask = df['Tag_Source'] == 'flagged'
    df.loc[mask, 'Tag'] = df.loc[mask, 'Vendor'].map(tag_map).fillna('Review with Client')
    df.loc[mask, 'Subcategory'] = df.loc[mask, 'Vendor'].map(subcat_map).fillna('')
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
    expense_df = df[df['Tag_Source'] != 'income'].copy()
    tagged = expense_df[expense_df['Tag'].fillna('') != ''].copy()
    if tagged.empty:
        return pd.DataFrame()

    tagged['_amount'] = tagged[amount_col].apply(_parse_amount) if amount_col else 0
    months = []
    if date_col and date_col in tagged.columns:
        tagged['_month'] = tagged[date_col].apply(_parse_month)
        months = [m for m in _MONTH_ORDER if m in tagged['_month'].values]

    rows = _summary_tag_rows(tagged, amount_col, months)

    # Income row
    if amount_col:
        income_df = df[df['Tag_Source'] == 'income'].copy()
        if not income_df.empty:
            income_df['_amount'] = income_df[amount_col].apply(_parse_amount)
            row = {'Tag': 'Income / Not Tagged', 'Subcategory': '', 'Count': len(income_df)}
            if months and date_col in income_df.columns:
                income_df['_month'] = income_df[date_col].apply(_parse_month)
                row.update(_monthly_row(income_df, months, amount_col))
            else:
                row['Total'] = round(income_df['_amount'].sum(), 2)
            rows.append(row)

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
    buf = io.BytesIO()
    out = df.copy().rename(columns={'Tag_Source': 'Tag Source'})
    personal_df = out[out['Tag'].fillna('').str.startswith('Personal -')]
    rwc_df = out[out['Tag Source'] == 'rwc']
    summary_df = _build_summary(df, amount_col, date_col)
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        out.to_excel(writer, sheet_name='Tagged', index=False)
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
            _step2_run_pretag(df, category_tags, cfg)
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
    category_opts = _get_category_options(cfg['generic_tags'], cfg['specific_tags'])
    client_subcats = lookup_df['subcategory'].dropna().unique().tolist() if not lookup_df.empty else []
    subcategory_opts = _get_subcategory_options(client_subcats, cfg.get('lookup_subcategories', []))

    if 'tagger_vendor_tbl' not in st.session_state:
        pretag = st.session_state.get('tagger_pretag_results') if mode == 'pretag' else None
        st.session_state['tagger_vendor_tbl'] = _build_vendor_table(
            df, desc_col, amount_col, lookup_df, pretag)

    full_tbl = st.session_state['tagger_vendor_tbl']

    if mode == 'pretag':
        _render_step3_pretag_view(full_tbl, category_opts, subcategory_opts)
        return

    st.caption('Unique vendors, expenses only. Tag what you know — leave blank to send to Claude.')
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
    display_cols = [c for c in ['Vendor', 'Count', 'Total Amount'] if c in tbl.columns]
    if show_source and 'Source' in tbl.columns:
        display_cols.append('Source')
    display_cols += [_COL_CATEGORY, _COL_SUBCATEGORY]
    col_cfg = {
        _COL_CATEGORY: st.column_config.SelectboxColumn(
            _COL_CATEGORY, options=category_opts, required=False,
            help='IRS/generic tax category — required to resolve this vendor. One click for high-volume vendors.'),
        _COL_SUBCATEGORY: st.column_config.SelectboxColumn(
            _COL_SUBCATEGORY, options=subcategory_opts, required=False,
            help='Optional finer working label under the Category. Independent of Category — leave blank if not needed.'),
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
                st.session_state['tagger_vendor_tbl'] = _merge_edits(full_tbl, edited)
                st.rerun()
        with col_b:
            if st.button('Next → Claude Tags the Rest', type='primary'):
                st.session_state['tagger_vendor_tbl'] = _merge_edits(full_tbl, edited)
                st.session_state['tagger_step'] = 4
                st.rerun()
    return edited


def _render_step3_pretag_view(full_tbl, category_opts, subcategory_opts):
    """Step 3 pre-tag mode: collapsed expander for pre-tagged, main editor for pending."""
    pending   = _pending_vendors(full_tbl)
    src       = full_tbl['Source'].fillna('') if 'Source' in full_tbl.columns \
                else pd.Series('', index=full_tbl.index)
    pretagged = full_tbl[src != '']
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
            updated = _merge_edits(_merge_edits(full_tbl, edited_pre), edited_pend)
            st.session_state['tagger_vendor_tbl'] = updated
            st.rerun()
    with col_b:
        if st.button('Next → Claude Tags the Rest', type='primary', key='pretag_next'):
            updated = _merge_edits(_merge_edits(full_tbl, edited_pre), edited_pend)
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
    vendor_tbl = st.session_state['tagger_vendor_tbl']

    pending = _pending_vendors(vendor_tbl)
    vendor_names = pending['Vendor'].tolist()

    if 'Tag' not in df.columns:
        n_batches = max(1, (len(vendor_names) + _BATCH_SIZE - 1) // _BATCH_SIZE)
        st.info(f'Sending {len(vendor_names)} vendor(s) to Claude Haiku (~{n_batches} API call(s))')
        if st.button('Run Claude →', type='primary'):
            if not cfg.get('api_key', '').strip():
                st.error('API Key required — go back to Step 1 and enter it.')
                return
            subcat_vocab = _subcategory_vocab_for_prompt(cfg['client_id'], cfg.get('lookup_subcategories', []))
            sys_prompt = _build_system_prompt(
                cfg['entity_type'], cfg['primary'], cfg['secondary'],
                cfg['specific_tags'], cfg['generic_tags'], subcat_vocab)
            prog = st.progress(0.0, text='Calling Claude Haiku...')
            try:
                claude_results = _run_claude_on_vendors(vendor_names, cfg['api_key'], sys_prompt, prog)
                prog.empty()
                lookup_df = _load_lookup(cfg['client_id'])
                st.session_state['tagger_df'] = _apply_all_tags(
                    df, desc_col, amount_col, vendor_tbl, claude_results, cfg['threshold'], lookup_df)
                st.rerun()
            except Exception as e:
                st.error(f'Tagging failed: {e}')
        return
    _render_step4_review(df, cfg['generic_tags'] + [t for t in cfg['specific_tags']
                                                     if t not in cfg['generic_tags']])


def _render_step4_review(df, tags):
    lookup = (df['Tag_Source'] == 'lookup').sum()
    auto = (df['Tag_Source'] == 'claude').sum()
    prep = (df['Tag_Source'] == 'preparer').sum()
    flagged = (df['Tag_Source'] == 'flagged').sum()
    income = (df['Tag_Source'] == 'income').sum()
    st.success(f'From lookup history: {lookup} · Preparer: {prep} · Claude auto: {auto} · '
               f'Needs review: {flagged} · Income skipped: {income}')
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
                'Your Subcategory', help='Specific working label (e.g., "Health Insurance", "Office Supplies")'),
        },
        disabled=[c for c in display_cols if c not in editable_cols],
        use_container_width=True, hide_index=True,
    )
    if st.button('Apply Tags & Continue', type='primary'):
        st.session_state['tagger_df'] = _apply_preparer_tags(df, edited)
        st.session_state['tagger_step'] = 5
        st.rerun()


def _vendor_hit_rate_line(df):
    """P3-lite (Card 1.3): one-line vendor-level memory hit-rate summary for Step 5.
    Counts unique vendors (not rows) so a heavily-repeated vendor doesn't skew the rate."""
    tagged = df[df['Tag_Source'] != 'income']
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
    rwc = (df['Tag_Source'] == 'rwc').sum()
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
