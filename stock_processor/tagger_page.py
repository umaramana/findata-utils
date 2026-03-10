"""
Transaction Tagger — Sprint 1
Preparer reviews all vendors first; Claude tags only the remainder.
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
_ALWAYS_TAGS = ['Personal - Not Deductible', 'Review with Client']
_MODEL = 'claude-haiku-4-5'
_BATCH_SIZE = 30

# Full-replacement patterns — matched description → clean generic label (no PII)
_TRANSFER_PATTERNS = [
    (re.compile(r'ORIG CO NAME:\s*(.*?)(?:\s+CO ENTRY|\s+ID:|$)', re.I),
     lambda m: m.group(1).strip()[:50]),
    (re.compile(r'^ZELLE\b', re.I),            lambda _: 'Zelle Payment'),
    (re.compile(r'^ONLINE TRANSFER\b', re.I),  lambda _: 'Online Transfer'),
    (re.compile(r'^ATM DEPOSIT\b', re.I),      lambda _: 'ATM Deposit'),
    (re.compile(r'^CHECK\s+#?\d+', re.I),      lambda _: 'Check'),
    (re.compile(r'^WIRE TRANSFER\b', re.I),    lambda _: 'Wire Transfer'),
    (re.compile(r'^SERVICE CHARGE\b', re.I),   lambda _: 'Bank Service Charge'),
    (re.compile(r'^BANK FEE\b', re.I),         lambda _: 'Bank Fee'),
]

# Trailing noise patterns — strip from merchant descriptions
_CLEANUP_PATTERNS = [
    re.compile(r'\s+#\s*\d{2,}$'),                                               # store #1234
    re.compile(r'\s+NO\.?\s*\d{3,}$', re.I),                                     # No. 123
    re.compile(r'\s+\d{5,}$'),                                                    # long trailing number
    re.compile(r'\s+\d+\s+\w+\s+(ST|AVE|RD|BLVD|DR|LN|WAY|PKWY)\b.*$', re.I),  # address
    re.compile(r'\s+[A-Z]{2}\s+\d{5}(-\d{4})?$'),                               # state + zip
]


# ── Vendor extraction ───────────────────────────────────────────────────────────

def _extract_vendor(desc):
    """Extract clean vendor name from raw bank/CC description. No PII sent to Claude."""
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


# ── Tag list ───────────────────────────────────────────────────────────────────

def _load_tag_list(entity_type, xl=None):
    """Return tag names for entity_type. Uses Lookup tab if present, else generic CSV."""
    if xl is not None:
        try:
            if 'Lookup' in xl.sheet_names:
                df = xl.parse('Lookup')
                tags = df[df['entity_type'] == entity_type]['tag'].dropna().tolist()
                for t in _ALWAYS_TAGS:
                    if t not in tags:
                        tags.append(t)
                if tags:
                    return tags
        except Exception:
            pass
    df = pd.read_csv(_TAG_LIST_PATH)
    return df[df['entity_type'] == entity_type]['tag'].dropna().tolist()


# ── Lookup table ───────────────────────────────────────────────────────────────

def _lookup_path(client_id):
    return os.path.join(_LOOKUPS_DIR, f'{client_id}_lookup.csv')


def _load_lookup(client_id):
    path = _lookup_path(client_id)
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame(columns=['vendor_name', 'tag', 'source', 'date_tagged'])


def _save_lookup(client_id, entries):
    """Append new entries to lookup CSV, deduplicating by vendor_name (keep last)."""
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


# ── Claude API ─────────────────────────────────────────────────────────────────

def _build_system_prompt(entity_type, primary, secondary, tags):
    tag_list = '\n'.join(f'- {t}' for t in tags)
    persona = f'Entity type: {entity_type}. Primary activity: {primary}.'
    if secondary:
        persona += f' Secondary activity: {secondary}.'
    return (
        f'You are a tax classification assistant. Client persona: {persona}\n\n'
        f'Classify each vendor to exactly one tag from this list:\n{tag_list}\n\n'
        'Rules:\n'
        '- Return a JSON array only — no prose, no markdown fences.\n'
        '- Each item: {"id": <int>, "tag": "<tag>", "confidence": <0.0-1.0>, "reason": "<brief>"}\n'
        '- Select only from the tag list. If unsure, return low confidence.\n'
        '- Use "Personal - Not Deductible" for clearly personal vendors.\n'
        '- Use "Review with Client" only if truly unclassifiable.'
    )


def _parse_api_response(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.split('\n')[1:-1])
    return json.loads(text)


def _tag_batch(batch, api_key, system_prompt):
    payload = json.dumps([
        {'id': i, 'vendor': r['description'], 'amount': r['amount']}
        for i, r in enumerate(batch)
    ])
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=_MODEL, max_tokens=2048, system=system_prompt,
        messages=[{'role': 'user', 'content': f'Classify these vendors:\n{payload}'}],
    )
    return _parse_api_response(msg.content[0].text)


# ── Vendor review table ────────────────────────────────────────────────────────

def _build_vendor_review_table(df, amount_col):
    """Unique vendor list for preparer review. Blank Tag = send to Claude."""
    agg = {'Count': ('Vendor', 'count')}
    if amount_col:
        agg['Sample Amount'] = (amount_col, 'first')
    grp = df.groupby('Vendor', sort=False).agg(**agg).reset_index()
    grp['Tag'] = ''
    return grp


# ── Claude-on-remainder ────────────────────────────────────────────────────────

def _run_pass1c_on_remainder(blank_vendors, df, amount_col, system_prompt, api_key, prog):
    """Call Claude only for vendors left blank by preparer. Returns vendor→result map."""
    seen, uniq = set(), []
    for v in blank_vendors:
        if v in seen:
            continue
        seen.add(v)
        amt_rows = df[df['Vendor'] == v]
        amt = None
        if amount_col and not amt_rows.empty:
            raw = pd.to_numeric(amt_rows[amount_col].iloc[0], errors='coerce')
            amt = float(raw) if pd.notna(raw) else None
        uniq.append({'description': v, 'amount': amt})
    results_map = {}
    batches = [uniq[i:i + _BATCH_SIZE] for i in range(0, len(uniq), _BATCH_SIZE)]
    for b_idx, batch in enumerate(batches):
        try:
            items = _tag_batch(batch, api_key, system_prompt)
            for item in items:
                results_map[batch[item['id']]['description']] = item
        except Exception as e:
            for entry in batch:
                results_map[entry['description']] = {
                    'tag': 'Review with Client', 'confidence': 0.0, 'reason': f'API error: {e}'}
        prog.progress((b_idx + 1) / max(1, len(batches)))
    return results_map


def _apply_all_tags(df, vendor_review, claude_results, threshold):
    """Apply preparer tags (non-blank) and Claude results (blank vendors) to all rows."""
    prep_map = {r['Vendor']: r['Tag'] for _, r in vendor_review.iterrows()
                if str(r.get('Tag', '')).strip()}
    df = df.copy()

    def _tag_row(row):
        v = row['Vendor']
        if v in prep_map:
            return pd.Series([prep_map[v], 1.0, '', 'preparer'])
        r = claude_results.get(v, {})
        tag = r.get('tag', 'Review with Client')
        conf = float(r.get('confidence', 0.0))
        return pd.Series([tag, conf, r.get('reason', ''), 'auto' if conf >= threshold else 'flagged'])

    df[['Tag', 'Confidence', 'Reason', 'Tag_Source']] = df.apply(_tag_row, axis=1)
    return df


# ── Preparer review helpers ────────────────────────────────────────────────────

def _flagged_summary(df, desc_col, amount_col):
    flagged = df[df['Tag_Source'] == 'flagged']
    agg = {
        'Suggested_Tag': ('Tag', 'first'),
        'Confidence': ('Confidence', 'mean'),
        'Reason': ('Reason', 'first'),
    }
    if amount_col:
        agg['Amount'] = (amount_col, 'first')
    uniq = flagged.groupby(desc_col, sort=False).agg(**agg).reset_index()
    uniq = uniq.rename(columns={desc_col: 'Description'})
    uniq['Preparer_Tag'] = uniq['Suggested_Tag']
    return uniq


def _apply_preparer_tags(df, desc_col, edited):
    tag_map = dict(zip(edited['Description'], edited['Preparer_Tag']))
    df = df.copy()
    mask = df['Tag_Source'] == 'flagged'
    df.loc[mask, 'Tag'] = df.loc[mask, desc_col].map(tag_map).fillna('Review with Client')
    df.loc[mask, 'Tag_Source'] = df.loc[mask].apply(
        lambda r: 'rwc' if r['Tag'] == 'Review with Client' else 'preparer', axis=1)
    df.loc[mask, ['Confidence', 'Reason']] = None
    return df


# ── Step renderers ─────────────────────────────────────────────────────────────

def _render_step1():
    st.subheader("Step 1 — Setup")
    cfg = st.session_state.get('tagger_config', {})
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        api_key = st.text_input("Anthropic API Key", value=cfg.get('api_key', ''), type='password')
    client_id = st.text_input("Client ID (used as lookup filename)", value=cfg.get('client_id', ''))
    et_idx = _ENTITY_TYPES.index(cfg.get('entity_type', _ENTITY_TYPES[0]))
    entity_type = st.selectbox("Entity Type", _ENTITY_TYPES, index=et_idx)
    primary = st.text_input("Primary Business Activity (e.g. Plumbing contractor)", value=cfg.get('primary', ''))
    secondary = st.text_input("Secondary Activity (optional)", value=cfg.get('secondary', ''))
    threshold = st.slider("Confidence Threshold (%)", 0, 100, cfg.get('threshold_pct', 75))
    all_tags = _load_tag_list(entity_type)
    selected_tags = st.multiselect("Tag list for this client (deselect irrelevant ones):",
                                   options=all_tags, default=cfg.get('selected_tags', all_tags))
    for t in _ALWAYS_TAGS:
        if t not in selected_tags:
            selected_tags.append(t)
    if st.button("Next →", type='primary'):
        if not all([client_id.strip(), primary.strip(), api_key.strip()]):
            st.error("Client ID, Primary Activity and API Key are required.")
            return
        st.session_state['tagger_config'] = {
            'api_key': api_key, 'client_id': client_id.strip(), 'entity_type': entity_type,
            'primary': primary, 'secondary': secondary,
            'threshold': threshold / 100, 'threshold_pct': threshold,
            'selected_tags': selected_tags,
        }
        st.session_state['tagger_step'] = 2
        st.rerun()


def _render_step2():
    st.subheader("Step 2 — Upload Transactions")
    uploaded = st.file_uploader("Upload Excel or CSV", type=['xlsx', 'xls', 'csv'], key='tagger_upload')
    if uploaded is None:
        return
    try:
        if uploaded.name.lower().endswith('.csv'):
            df = pd.read_csv(uploaded)
            xl = None
        else:
            xl = pd.ExcelFile(uploaded)
            n_sheets = len(xl.sheet_names)
            sheet = st.selectbox("Select sheet", xl.sheet_names) if n_sheets > 1 else xl.sheet_names[0]
            df = xl.parse(sheet)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return
    cols = df.columns.tolist()
    desc_default = next((i for i, c in enumerate(cols) if 'desc' in str(c).lower()), 0)
    desc_col = st.selectbox("Description column", cols, index=desc_default)
    amount_col = st.selectbox("Amount column (optional)", ['(none)'] + cols)
    amount_col = None if amount_col == '(none)' else amount_col
    st.dataframe(df[[desc_col] + ([amount_col] if amount_col else [])].head(5))
    if xl is not None and 'Lookup' in xl.sheet_names:
        tags = _load_tag_list(st.session_state['tagger_config']['entity_type'], xl)
        st.session_state['tagger_config']['selected_tags'] = tags
        st.info(f"Lookup tab found — tag list updated to {len(tags)} client-specific tags.")
    if st.button("Next →", type='primary'):
        df = df.copy()
        df['Vendor'] = df[desc_col].apply(_extract_vendor)
        st.session_state['tagger_df'] = df
        st.session_state['tagger_desc_col'] = desc_col
        st.session_state['tagger_amount_col'] = amount_col
        st.session_state['tagger_step'] = 3
        st.rerun()


def _render_step3():
    st.subheader("Step 3 — Preparer Review")
    st.caption("Tag the vendors you recognise. Leave blank → Claude will tag it.")
    df = st.session_state['tagger_df']
    amount_col = st.session_state['tagger_amount_col']
    tags = st.session_state['tagger_config']['selected_tags']
    if 'tagger_vendor_review' not in st.session_state:
        st.session_state['tagger_vendor_review'] = _build_vendor_review_table(df, amount_col)
    tbl = st.session_state['tagger_vendor_review']
    display_cols = [c for c in ['Vendor', 'Count', 'Sample Amount', 'Tag'] if c in tbl.columns]
    edited = st.data_editor(
        tbl[display_cols],
        column_config={'Tag': st.column_config.SelectboxColumn(
            "Your Tag (blank → Claude)", options=[''] + tags, required=False)},
        disabled=[c for c in display_cols if c != 'Tag'],
        use_container_width=True, hide_index=True,
        key='vendor_review_editor',
    )
    tagged_count = (edited['Tag'].fillna('') != '').sum()
    claude_count = len(edited) - tagged_count
    st.info(f"You tagged **{tagged_count}** vendor(s) · Sending **{claude_count}** to Claude")
    if st.button("Run Claude →", type='primary'):
        st.session_state['tagger_vendor_review'] = edited.copy()
        st.session_state['tagger_step'] = 4
        st.rerun()


def _render_step4():
    st.subheader("Step 4 — Claude Tags the Rest")
    cfg = st.session_state['tagger_config']
    df = st.session_state['tagger_df']
    amount_col = st.session_state['tagger_amount_col']
    vendor_review = st.session_state['tagger_vendor_review']
    tags = cfg['selected_tags']
    blank_vendors = vendor_review[vendor_review['Tag'].fillna('') == '']['Vendor'].tolist()
    if 'Tag' not in df.columns:
        n = len(blank_vendors)
        n_batches = max(1, (n + _BATCH_SIZE - 1) // _BATCH_SIZE)
        st.info(f"Sending {n} unique vendor(s) to Claude Haiku (~{n_batches} API call(s))")
        if st.button("Run Claude →", type='primary'):
            sys_prompt = _build_system_prompt(
                cfg['entity_type'], cfg['primary'], cfg['secondary'], cfg['selected_tags'])
            prog = st.progress(0.0, text="Calling Claude Haiku...")
            try:
                claude_results = _run_pass1c_on_remainder(
                    blank_vendors, df, amount_col, sys_prompt, cfg['api_key'], prog)
                prog.empty()
                st.session_state['tagger_df'] = _apply_all_tags(
                    df, vendor_review, claude_results, cfg['threshold'])
                st.rerun()
            except Exception as e:
                st.error(f"Tagging failed: {e}")
        return
    _render_step4_review(df, tags)


def _render_step4_review(df, tags):
    """Show Claude results summary and secondary review of low-confidence items."""
    auto = (df['Tag_Source'] == 'auto').sum()
    prep = (df['Tag_Source'] == 'preparer').sum()
    flagged = (df['Tag_Source'] == 'flagged').sum()
    st.success(f"Preparer tagged: {prep} · Claude auto-tagged: {auto} · Needs review: {flagged}")
    if flagged == 0:
        if st.button("Next → Output", type='primary'):
            st.session_state['tagger_step'] = 5
            st.rerun()
        return
    amount_col = st.session_state['tagger_amount_col']
    uniq = _flagged_summary(df, 'Vendor', amount_col)
    st.info(f"{len(uniq)} vendor(s) below confidence threshold — assign tags below.")
    display_cols = ['Description', 'Confidence', 'Suggested_Tag', 'Reason', 'Preparer_Tag']
    if amount_col and 'Amount' in uniq.columns:
        display_cols = ['Description', 'Amount', 'Confidence', 'Suggested_Tag', 'Reason', 'Preparer_Tag']
    edited = st.data_editor(
        uniq[display_cols],
        column_config={'Preparer_Tag': st.column_config.SelectboxColumn(
            "Your Tag", options=tags, required=True)},
        disabled=[c for c in display_cols if c != 'Preparer_Tag'],
        use_container_width=True, hide_index=True,
    )
    if st.button("Apply Tags & Continue", type='primary'):
        st.session_state['tagger_df'] = _apply_preparer_tags(df, 'Vendor', edited)
        st.session_state['tagger_step'] = 5
        st.rerun()


def _render_step5_downloads(df, desc_col, cfg):
    """Render download buttons for tagged file and RWC list."""
    out = df.copy().rename(columns={'Tag_Source': 'Tag Source'})
    buf = io.BytesIO()
    out.to_excel(buf, index=False)
    buf.seek(0)
    st.download_button("Download Tagged File", data=buf,
                       file_name=f"{cfg['client_id']}_tagged.xlsx",
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       type='primary')
    rwc_cols = (['Vendor', desc_col, 'Reason']
                if 'Vendor' in df.columns else [desc_col, 'Reason'])
    rwc_df = df[df['Tag_Source'] == 'rwc'][rwc_cols]
    if rwc_df.empty:
        return
    rwc_buf = io.BytesIO()
    rwc_df.to_excel(rwc_buf, index=False)
    rwc_buf.seek(0)
    st.download_button("Download Review-with-Client List", data=rwc_buf,
                       file_name=f"{cfg['client_id']}_rwc.xlsx",
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _render_step5():
    st.subheader("Step 5 — Output")
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    cfg = st.session_state['tagger_config']
    auto = (df['Tag_Source'] == 'auto').sum()
    preparer = (df['Tag_Source'] == 'preparer').sum()
    rwc = (df['Tag_Source'] == 'rwc').sum()
    col1, col2, col3 = st.columns(3)
    col1.metric("Auto-tagged (Claude)", int(auto))
    col2.metric("Preparer-tagged", int(preparer))
    col3.metric("Review with Client", int(rwc))
    _render_step5_downloads(df, desc_col, cfg)
    entries = _collect_lookup_entries(df, desc_col)
    _save_lookup(cfg['client_id'], entries)
    st.info(f"Lookup saved: {len(entries)} entries → {cfg['client_id']}_lookup.csv")
    if st.button("Start New Run", type='secondary'):
        for k in ['tagger_step', 'tagger_config', 'tagger_df',
                  'tagger_desc_col', 'tagger_amount_col', 'tagger_vendor_review']:
            st.session_state.pop(k, None)
        st.rerun()


# ── Entry point ────────────────────────────────────────────────────────────────

def render():
    st.title("Transaction Tagger")
    st.markdown("---")
    if 'tagger_step' not in st.session_state:
        st.session_state['tagger_step'] = 1
    step = st.session_state['tagger_step']
    step_names = ['Setup', 'Upload', 'Preparer Tag', 'Claude Tag', 'Output']
    cols = st.columns(5)
    for i, (col, name) in enumerate(zip(cols, step_names), 1):
        col.markdown(f"**{i}. {name}**" if i == step else f"{i}. {name}")
    st.markdown("---")
    {1: _render_step1, 2: _render_step2, 3: _render_step3,
     4: _render_step4, 5: _render_step5}[step]()


render()
