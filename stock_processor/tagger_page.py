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
_COL_QUICK   = 'Quick Tag (Specific)'
_COL_GENERIC = 'Tax Categories (Generic)'

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

# Full-replacement patterns → clean vendor label (no PII sent to Claude)
# Order matters: more specific patterns first.
_TRANSFER_PATTERNS = [
    # "ACH: American Express" (pre-cleaned by bank extractor) → "American Express"
    (re.compile(r'^ACH:\s+(.+)$', re.I),
     lambda m: m.group(1).strip().split(' | ')[0][:50]),
    # Raw Orig CO Name (not yet cleaned by bank extractor)
    (re.compile(r'ORIG CO NAME:\s*(.*?)(?:\s+CO ENTRY|\s+ID:|$)', re.I),
     lambda m: m.group(1).strip()[:50]),
    # Zelle: extract recipient, strip trailing reference number
    # "Zelle Payment To Garbage Home Depto 24055301173" → "Zelle: Garbage Home Depto"
    (re.compile(r'^ZELLE\b(?:\s+PAYMENT)?\s+(?:TO\s+)?(.+)', re.I),
     lambda m: 'Zelle: ' + re.sub(r'\s+\d{6,}$', '', m.group(1).strip())[:50]),
    (re.compile(r'^ONLINE TRANSFER\b', re.I),  lambda _: 'Online Transfer'),
    (re.compile(r'^ATM\b', re.I),              lambda _: 'ATM Withdrawal'),
    (re.compile(r'^CHECK\s+#?\d+', re.I),      lambda _: 'Check'),
    (re.compile(r'^WIRE TRANSFER\b', re.I),    lambda _: 'Wire Transfer'),
    (re.compile(r'^SERVICE CHARGE\b', re.I),   lambda _: 'Bank Service Charge'),
    (re.compile(r'^BANK FEE\b', re.I),         lambda _: 'Bank Fee'),
]

# Trailing noise to strip from merchant descriptions
_CLEANUP_PATTERNS = [
    re.compile(r'\s+#\s*\d{2,}$'),
    re.compile(r'\s+NO\.?\s*\d{3,}$', re.I),
    re.compile(r'\s+\d{5,}$'),
    re.compile(r'\s+\d+\s+\w+\s+(ST|AVE|RD|BLVD|DR|LN|WAY|PKWY)\b.*$', re.I),
    re.compile(r'\s+[A-Z]{2}\s+\d{5}(-\d{4})?$'),
]


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
    """Strip PII from description → clean vendor label."""
    desc = str(desc).strip()
    for pat, handler in _TRANSFER_PATTERNS:
        m = pat.search(desc)
        if m:
            return handler(m)
    result = desc
    for pat in _CLEANUP_PATTERNS:
        result = pat.sub('', result).strip()
    for delim in ('  ', ' - ', ' | ', ' / '):
        if delim in result:
            result = result.split(delim)[0].strip()
            break
    return result[:60] if result else desc[:60]


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


def _load_specific_tags(xl):
    """Tags from the uploaded file's Lookup tab — client-specific curated list.
    Returns [] if no Lookup tab present. Sheet name and column name are case-insensitive."""
    if xl is None:
        return []
    try:
        sheet = next((s for s in xl.sheet_names if s.strip().lower() == 'lookup'), None)
        if sheet is None:
            return []
        df = xl.parse(sheet)
        col = next((c for c in df.columns if str(c).strip().lower() == 'tag'), None)
        if col is None:
            return []
        return df[col].dropna().tolist()
    except Exception:
        return []


def _get_quick_tags(specific_tags):
    """Dropdown options for Quick Tag (Specific): specific business tags first,
    then personal tags, then Review with Client."""
    opts = [''] + list(specific_tags)
    for t in ['Personal - Not Deductible'] + _PERSONAL_AUTO_TAGS + ['Review with Client']:
        if t not in opts:
            opts.append(t)
    return opts


# ── Lookup table ─────────────────────────────────────────────────────────────────

def _lookup_path(client_id):
    return os.path.join(_LOOKUPS_DIR, f'{client_id}_lookup.csv')


def _load_lookup(client_id):
    path = _lookup_path(client_id)
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame(columns=['vendor_name', 'tag', 'source', 'date_tagged'])


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
        if row.get('Tag_Source') in ('auto', 'preparer'):
            entries.append({
                'vendor_name': str(row.get('Vendor', row[desc_col])),
                'tag': row['Tag'],
                'source': row['Tag_Source'],
                'date_tagged': today,
            })
    return entries


# ── Vendor review table ──────────────────────────────────────────────────────────

def _build_vendor_table(df, desc_col, amount_col, lookup_df):
    """Group by extracted Vendor. Returns unique-vendor DataFrame with pre-filled tags."""
    expense_df = df[df[amount_col].apply(_is_expense)].copy() if amount_col else df.copy()
    if expense_df.empty:
        return pd.DataFrame(columns=['Vendor', 'Count', 'Total Amount', _COL_QUICK, _COL_GENERIC])

    agg = {'Count': ('Vendor', 'count')}
    if amount_col:
        agg['Total Amount'] = (amount_col, lambda x: round(x.apply(_parse_amount).dropna().sum(), 2))
    grp = expense_df.groupby('Vendor', sort=False).agg(**agg).reset_index()

    lookup_map = dict(zip(lookup_df['vendor_name'], lookup_df['tag'])) if not lookup_df.empty else {}
    grp[_COL_QUICK]   = grp['Vendor'].apply(_get_auto_personal_tag)
    grp[_COL_GENERIC] = grp['Vendor'].apply(lambda v: lookup_map.get(v, ''))
    return grp


def _merge_edits(full_tbl, edited_view):
    """Write edits from the pending-only view back into the full vendor table."""
    edit_map = {r['Vendor']: {_COL_QUICK:   str(r.get(_COL_QUICK, '')).strip(),
                               _COL_GENERIC: str(r.get(_COL_GENERIC, '')).strip()}
                for _, r in edited_view.iterrows()}
    full = full_tbl.copy()
    for idx, row in full.iterrows():
        if row['Vendor'] in edit_map:
            full.at[idx, _COL_QUICK]   = edit_map[row['Vendor']][_COL_QUICK]
            full.at[idx, _COL_GENERIC] = edit_map[row['Vendor']][_COL_GENERIC]
    return full


def _pending_vendors(tbl):
    """Rows where both columns are blank → still need tagging."""
    return tbl[
        (tbl[_COL_QUICK].fillna('') == '') &
        (tbl[_COL_GENERIC].fillna('') == '')
    ]


# ── Claude API ───────────────────────────────────────────────────────────────────

def _build_system_prompt(entity_type, primary, secondary, specific_tags, generic_tags):
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

    specific_note = ''
    if specific_tags:
        specific_note = (
            f'\n\nThis client uses a curated tag list. Prefer these specific tags when they fit:\n'
            + '\n'.join(f'- {t}' for t in specific_tags)
            + '\nFall back to the full list only when no specific tag is appropriate.'
        )

    return (
        f'You are a tax classification assistant. Client persona: {persona}\n\n'
        f'Classify each vendor to exactly one tag from this list:\n{tag_list}'
        f'{specific_note}\n\n'
        'Rules:\n'
        '- Return a JSON array only — no prose, no markdown fences.\n'
        '- Each item: {"id": <int>, "tag": "<tag>", "confidence": <0.0-1.0>, "reason": "<brief>"}\n'
        '- Select only from the tag list above. If unsure, return low confidence.\n'
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


# ── Apply all tags to transaction rows ──────────────────────────────────────────

def _apply_all_tags(df, desc_col, amount_col, vendor_tbl, claude_results, threshold):
    """Map vendor→tag back to every transaction row.
    Priority: Quick Tag (Specific) → Tax Categories (Generic) → Claude result."""
    prep_map = {}
    for _, r in vendor_tbl.iterrows():
        quick   = str(r.get(_COL_QUICK, '')).strip()
        generic = str(r.get(_COL_GENERIC, '')).strip()
        tag = quick or generic   # specific wins over generic
        if tag:
            prep_map[r['Vendor']] = tag

    df = df.copy()

    def _tag_row(row):
        if amount_col and not _is_expense(row.get(amount_col, 0)):
            return pd.Series(['', None, '', 'income'])
        v = str(row.get('Vendor', _extract_vendor(str(row[desc_col]))))
        prep_tag = prep_map.get(v, '')
        if prep_tag:
            return pd.Series([prep_tag, 1.0, '', 'preparer'])
        r = claude_results.get(v, {})
        tag = r.get('tag', 'Review with Client')
        conf = float(r.get('confidence', 0.0))
        return pd.Series([tag, conf, r.get('reason', ''), 'auto' if conf >= threshold else 'flagged'])

    df[['Tag', 'Confidence', 'Reason', 'Tag_Source']] = df.apply(_tag_row, axis=1)
    return df


# ── Preparer review helpers ──────────────────────────────────────────────────────

def _flagged_summary(df, amount_col):
    flagged = df[df['Tag_Source'] == 'flagged']
    agg = {'Suggested_Tag': ('Tag', 'first'), 'Confidence': ('Confidence', 'mean'),
           'Reason': ('Reason', 'first')}
    if amount_col:
        agg['Amount'] = (amount_col, 'first')
    uniq = flagged.groupby('Vendor', sort=False).agg(**agg).reset_index()
    uniq['Preparer_Tag'] = uniq['Suggested_Tag']
    return uniq


def _apply_preparer_tags(df, edited):
    tag_map = dict(zip(edited['Vendor'], edited['Preparer_Tag']))
    df = df.copy()
    mask = df['Tag_Source'] == 'flagged'
    df.loc[mask, 'Tag'] = df.loc[mask, 'Vendor'].map(tag_map).fillna('Review with Client')
    df.loc[mask, 'Tag_Source'] = df.loc[mask].apply(
        lambda r: 'rwc' if r['Tag'] == 'Review with Client' else 'preparer', axis=1)
    df.loc[mask, ['Confidence', 'Reason']] = None
    return df


# ── Output Excel ─────────────────────────────────────────────────────────────────

def _build_summary(df, amount_col):
    rows = []
    expense_df = df[df['Tag_Source'] != 'income']
    for tag, grp in expense_df[expense_df['Tag'].fillna('') != ''].groupby('Tag'):
        amt = round(grp[amount_col].apply(_parse_amount).dropna().sum(), 2) if amount_col else None
        rows.append({'Tag': tag, 'Count': len(grp), 'Total Amount': amt})
    if amount_col:
        income_df = df[df['Tag_Source'] == 'income']
        if not income_df.empty:
            amt = round(income_df[amount_col].apply(_parse_amount).dropna().sum(), 2)
            rows.append({'Tag': 'Income / Not Tagged', 'Count': len(income_df), 'Total Amount': amt})
    summary = pd.DataFrame(rows)
    if not summary.empty and amount_col:
        total = round(summary['Total Amount'].sum(), 2)
        total_row = pd.DataFrame([{'Tag': 'GRAND TOTAL', 'Count': summary['Count'].sum(), 'Total Amount': total}])
        summary = pd.concat([summary, total_row], ignore_index=True)
    return summary


def _write_output_excel(df, desc_col, amount_col, cfg):
    buf = io.BytesIO()
    out = df.copy().rename(columns={'Tag_Source': 'Tag Source'})
    personal_df = df[df['Tag'].fillna('').str.startswith('Personal -')]
    rwc_df = df[df['Tag_Source'] == 'rwc']
    summary_df = _build_summary(df, amount_col)
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

    generic_tags = _load_generic_tags()
    st.caption(f'Generic tag list: {len(generic_tags)} tags from rasrich_tag_lists.csv — '
               'always sent to Claude. Specific tags load from the file\'s Lookup tab in Step 2.')

    if st.button('Next →', type='primary'):
        if not all([client_id.strip(), primary.strip()]):
            st.error('Client ID and Primary Activity are required.')
            return
        st.session_state['tagger_config'] = {
            'api_key': api_key, 'client_id': client_id.strip(), 'entity_type': entity_type,
            'primary': primary, 'secondary': secondary,
            'threshold': threshold / 100, 'threshold_pct': threshold,
            'generic_tags': generic_tags,
            'specific_tags': cfg.get('specific_tags', []),  # may be filled in Step 2
        }
        st.session_state['tagger_step'] = 2
        st.rerun()


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


def _render_step2():
    st.subheader('Step 2 — Upload Transactions')
    _back_button(1)
    uploaded = st.file_uploader('Upload Excel or CSV', type=['xlsx', 'xls', 'csv'], key='tagger_upload')
    if uploaded is None:
        return
    df, xl = _load_upload_file(uploaded)
    if df is None:
        return

    cols = df.columns.tolist()
    desc_default = next((i for i, c in enumerate(cols) if 'desc' in str(c).lower()), 0)
    desc_col = st.selectbox('Description column', cols, index=desc_default)
    amount_col = st.selectbox('Amount column (required for expense filtering)', ['(none)'] + cols)
    amount_col = None if amount_col == '(none)' else amount_col
    st.dataframe(df[[desc_col] + ([amount_col] if amount_col else [])].head(5))

    # Load specific tags from Lookup tab if present
    specific_tags = _load_specific_tags(xl)
    if specific_tags:
        st.success(f'Lookup tab found — {len(specific_tags)} specific tags loaded for Quick Tag column.')
    else:
        st.info('No Lookup tab found — Quick Tag (Specific) will show personal tags only. '
                'Tax Categories (Generic) will show the full 52-tag list.')

    if st.button('Next →', type='primary'):
        df = df.copy()
        df['Vendor'] = df[desc_col].apply(_extract_vendor)
        st.session_state['tagger_df'] = df
        st.session_state['tagger_desc_col'] = desc_col
        st.session_state['tagger_amount_col'] = amount_col
        st.session_state['tagger_config']['specific_tags'] = specific_tags
        st.session_state.pop('tagger_vendor_tbl', None)
        st.session_state['tagger_step'] = 3
        st.rerun()


def _render_step3():
    st.subheader('Step 3 — Preparer Review')
    st.caption('Unique vendors, expenses only. Tag what you know — leave blank to send to Claude.')
    _back_button(2)
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    amount_col = st.session_state['tagger_amount_col']
    cfg = st.session_state['tagger_config']
    generic_tags = cfg['generic_tags']
    specific_tags = cfg['specific_tags']
    quick_tags = _get_quick_tags(specific_tags)

    if 'tagger_vendor_tbl' not in st.session_state:
        lookup_df = _load_lookup(cfg['client_id'])
        st.session_state['tagger_vendor_tbl'] = _build_vendor_table(df, desc_col, amount_col, lookup_df)

    full_tbl = st.session_state['tagger_vendor_tbl']
    pending = _pending_vendors(full_tbl)
    tagged_count = len(full_tbl) - len(pending)
    total_count = len(full_tbl)

    st.info(f'Tagged: **{tagged_count} / {total_count}** vendors · '
            f'**{len(pending)}** remaining → Claude will tag these')

    if pending.empty:
        if st.button('Next → Claude Tags the Rest', type='primary'):
            st.session_state['tagger_step'] = 4
            st.rerun()
        return

    _render_step3_editor(pending, quick_tags, generic_tags, full_tbl)


def _render_step3_editor(pending, quick_tags, generic_tags, full_tbl):
    """Render vendor data_editor and navigation buttons for Step 3."""
    display_cols = [c for c in ['Vendor', 'Count', 'Total Amount'] if c in pending.columns]
    display_cols += [_COL_QUICK, _COL_GENERIC]
    edited = st.data_editor(
        pending[display_cols].reset_index(drop=True),
        column_config={
            _COL_QUICK: st.column_config.SelectboxColumn(
                _COL_QUICK, options=quick_tags, required=False,
                help='Specific client tags + personal categories'),
            _COL_GENERIC: st.column_config.SelectboxColumn(
                _COL_GENERIC, options=[''] + generic_tags, required=False,
                help='Full IRS/generic tax category list'),
        },
        disabled=[c for c in display_cols if c not in (_COL_QUICK, _COL_GENERIC)],
        use_container_width=True, hide_index=True,
        key='vendor_review_editor',
    )
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
            sys_prompt = _build_system_prompt(
                cfg['entity_type'], cfg['primary'], cfg['secondary'],
                cfg['specific_tags'], cfg['generic_tags'])
            prog = st.progress(0.0, text='Calling Claude Haiku...')
            try:
                claude_results = _run_claude_on_vendors(vendor_names, cfg['api_key'], sys_prompt, prog)
                prog.empty()
                st.session_state['tagger_df'] = _apply_all_tags(
                    df, desc_col, amount_col, vendor_tbl, claude_results, cfg['threshold'])
                st.rerun()
            except Exception as e:
                st.error(f'Tagging failed: {e}')
        return
    _render_step4_review(df, cfg['generic_tags'] + [t for t in cfg['specific_tags']
                                                     if t not in cfg['generic_tags']])


def _render_step4_review(df, tags):
    auto = (df['Tag_Source'] == 'auto').sum()
    prep = (df['Tag_Source'] == 'preparer').sum()
    flagged = (df['Tag_Source'] == 'flagged').sum()
    income = (df['Tag_Source'] == 'income').sum()
    st.success(f'Preparer: {prep} · Claude auto: {auto} · Needs review: {flagged} · Income skipped: {income}')
    if flagged == 0:
        if st.button('Next → Output', type='primary'):
            st.session_state['tagger_step'] = 5
            st.rerun()
        return
    amount_col = st.session_state['tagger_amount_col']
    uniq = _flagged_summary(df, amount_col)
    st.info(f'{len(uniq)} vendor(s) below confidence threshold — assign tags below.')
    display_cols = ['Vendor', 'Confidence', 'Suggested_Tag', 'Reason', 'Preparer_Tag']
    if amount_col and 'Amount' in uniq.columns:
        display_cols = ['Vendor', 'Amount', 'Confidence', 'Suggested_Tag', 'Reason', 'Preparer_Tag']
    edited = st.data_editor(
        uniq[display_cols],
        column_config={'Preparer_Tag': st.column_config.SelectboxColumn(
            'Your Tag', options=tags, required=True)},
        disabled=[c for c in display_cols if c != 'Preparer_Tag'],
        use_container_width=True, hide_index=True,
    )
    if st.button('Apply Tags & Continue', type='primary'):
        st.session_state['tagger_df'] = _apply_preparer_tags(df, edited)
        st.session_state['tagger_step'] = 5
        st.rerun()


def _render_step5():
    st.subheader('Step 5 — Output')
    _back_button(4)
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    amount_col = st.session_state['tagger_amount_col']
    cfg = st.session_state['tagger_config']
    auto = (df['Tag_Source'] == 'auto').sum()
    preparer = (df['Tag_Source'] == 'preparer').sum()
    rwc = (df['Tag_Source'] == 'rwc').sum()
    personal = df['Tag'].fillna('').str.startswith('Personal -').sum()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Claude auto-tagged', int(auto))
    col2.metric('Preparer-tagged', int(preparer))
    col3.metric('Personal', int(personal))
    col4.metric('Review with Client', int(rwc))
    summary_df = _build_summary(df, amount_col)
    if not summary_df.empty:
        st.subheader('Summary')
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    buf = _write_output_excel(df, desc_col, amount_col, cfg)
    st.download_button('Download Tagged File', data=buf,
                       file_name=f"{cfg['client_id']}_tagged.xlsx",
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       type='primary')
    entries = _collect_lookup_entries(df, desc_col)
    _save_lookup(cfg['client_id'], entries)
    st.info(f"Lookup saved: {len(entries)} entries → {cfg['client_id']}_lookup.csv")
    if st.button('Start New Run', type='secondary'):
        for k in ['tagger_step', 'tagger_config', 'tagger_df',
                  'tagger_desc_col', 'tagger_amount_col', 'tagger_vendor_tbl']:
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
