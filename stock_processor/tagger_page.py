"""
Transaction Tagger — Sprint 1
Multi-pass tagging of bank/CC transactions to expense heads using Claude Haiku.
Entry point: called via rasrich_tools.py page navigation.
"""
import io
import json
import os
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
                'vendor_name': str(row[desc_col]),
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
        f'Classify each transaction to exactly one tag from this list:\n{tag_list}\n\n'
        'Rules:\n'
        '- Return a JSON array only — no prose, no markdown fences.\n'
        '- Each item: {"id": <int>, "tag": "<tag>", "confidence": <0.0-1.0>, "reason": "<brief>"}\n'
        '- Select only from the tag list. If unsure, return low confidence rather than guessing.\n'
        '- Use "Personal - Not Deductible" for clearly personal transactions.\n'
        '- Use "Review with Client" only if truly unclassifiable even at low confidence.'
    )


def _parse_api_response(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.split('\n')[1:-1])
    return json.loads(text)


def _tag_batch(batch, api_key, system_prompt):
    payload = json.dumps([
        {'id': i, 'description': r['description'], 'amount': r['amount']}
        for i, r in enumerate(batch)
    ])
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{'role': 'user', 'content': f'Classify these transactions:\n{payload}'}],
    )
    return _parse_api_response(msg.content[0].text)


def _dedup_for_api(df, desc_col, amount_col):
    result = []
    for desc, grp in df.groupby(desc_col, sort=False):
        if amount_col:
            amt = pd.to_numeric(grp[amount_col], errors='coerce').mean()
            amt = round(float(amt), 2) if pd.notna(amt) else None
        else:
            amt = None
        result.append({'description': str(desc), 'amount': amt})
    return result


def _run_pass1c(df, desc_col, amount_col, system_prompt, threshold, api_key, prog):
    uniq = _dedup_for_api(df, desc_col, amount_col)
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
        prog.progress((b_idx + 1) / len(batches))

    def _apply(row):
        r = results_map.get(str(row[desc_col]), {})
        tag = r.get('tag', 'Review with Client')
        conf = float(r.get('confidence', 0.0))
        source = 'auto' if conf >= threshold else 'flagged'
        return pd.Series([tag, conf, r.get('reason', ''), source])

    df = df.copy()
    df[['Tag', 'Confidence', 'Reason', 'Tag_Source']] = df.apply(_apply, axis=1)
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
            sheet = st.selectbox("Select sheet", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
            df = xl.parse(sheet)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return
    cols = df.columns.tolist()
    desc_default = next((i for i, c in enumerate(cols) if 'desc' in str(c).lower()), 0)
    desc_col = st.selectbox("Description column", cols, index=desc_default)
    amount_col = st.selectbox("Amount column (optional — adds context for tagging)", ['(none)'] + cols)
    amount_col = None if amount_col == '(none)' else amount_col
    st.dataframe(df[[desc_col] + ([amount_col] if amount_col else [])].head(5))
    if xl is not None and 'Lookup' in xl.sheet_names:
        tags = _load_tag_list(st.session_state['tagger_config']['entity_type'], xl)
        st.session_state['tagger_config']['selected_tags'] = tags
        st.info(f"Lookup tab found — tag list updated to {len(tags)} client-specific tags.")
    if st.button("Next →", type='primary'):
        st.session_state['tagger_df'] = df
        st.session_state['tagger_desc_col'] = desc_col
        st.session_state['tagger_amount_col'] = amount_col
        st.session_state['tagger_step'] = 3
        st.rerun()


def _render_step3():
    st.subheader("Step 3 — Auto-Tag (Pass 1c)")
    cfg = st.session_state['tagger_config']
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    amount_col = st.session_state['tagger_amount_col']
    if 'Tag' not in df.columns:
        n_uniq = df[desc_col].nunique()
        n_batches = max(1, (n_uniq + _BATCH_SIZE - 1) // _BATCH_SIZE)
        st.info(f"{len(df)} rows · {n_uniq} unique descriptions · ~{n_batches} API call(s) to Haiku")
        if st.button("Run Auto-Tag", type='primary'):
            sys_prompt = _build_system_prompt(
                cfg['entity_type'], cfg['primary'], cfg['secondary'], cfg['selected_tags'])
            prog = st.progress(0.0, text="Calling Claude Haiku...")
            try:
                tagged = _run_pass1c(df.copy(), desc_col, amount_col,
                                     sys_prompt, cfg['threshold'], cfg['api_key'], prog)
            except Exception as e:
                st.error(f"Tagging failed: {e}")
                return
            prog.empty()
            st.session_state['tagger_df'] = tagged
            st.rerun()
        return
    auto = (df['Tag_Source'] == 'auto').sum()
    flagged = (df['Tag_Source'] == 'flagged').sum()
    st.success(f"Auto-tagged: {auto} rows · Flagged for review: {flagged} rows")
    if st.button("Next → Preparer Review", type='primary'):
        st.session_state['tagger_step'] = 4
        st.rerun()


def _render_step4():
    st.subheader("Step 4 — Preparer Review")
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    amount_col = st.session_state['tagger_amount_col']
    tags = st.session_state['tagger_config']['selected_tags']
    if df[df['Tag_Source'] == 'flagged'].empty:
        st.success("No rows to review — all auto-tagged above threshold.")
        if st.button("Next → Output", type='primary'):
            st.session_state['tagger_step'] = 5
            st.rerun()
        return
    uniq = _flagged_summary(df, desc_col, amount_col)
    n = len(uniq)
    st.info(f"{n} unique description{'s' if n != 1 else ''} to review. Assign the correct tag to each.")
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
        st.session_state['tagger_df'] = _apply_preparer_tags(df, desc_col, edited)
        st.session_state['tagger_step'] = 5
        st.rerun()


def _render_step5():
    st.subheader("Step 5 — Output")
    df = st.session_state['tagger_df']
    desc_col = st.session_state['tagger_desc_col']
    cfg = st.session_state['tagger_config']
    auto = (df['Tag_Source'] == 'auto').sum()
    preparer = (df['Tag_Source'] == 'preparer').sum()
    rwc = (df['Tag_Source'] == 'rwc').sum()
    col1, col2, col3 = st.columns(3)
    col1.metric("Auto-tagged", int(auto))
    col2.metric("Preparer-tagged", int(preparer))
    col3.metric("Review with Client", int(rwc))
    out = df.copy().rename(columns={'Tag_Source': 'Tag Source'})
    output = io.BytesIO()
    out.to_excel(output, index=False)
    output.seek(0)
    st.download_button("Download Tagged File", data=output,
                       file_name=f"{cfg['client_id']}_tagged.xlsx",
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       type='primary')
    rwc_df = df[df['Tag_Source'] == 'rwc'][[desc_col, 'Reason']]
    if not rwc_df.empty:
        rwc_out = io.BytesIO()
        rwc_df.to_excel(rwc_out, index=False)
        rwc_out.seek(0)
        st.download_button("Download Review-with-Client List", data=rwc_out,
                           file_name=f"{cfg['client_id']}_rwc.xlsx",
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    entries = _collect_lookup_entries(df, desc_col)
    _save_lookup(cfg['client_id'], entries)
    st.info(f"Lookup saved: {len(entries)} entries → {cfg['client_id']}_lookup.csv")
    if st.button("Start New Run", type='secondary'):
        for k in ['tagger_step', 'tagger_config', 'tagger_df', 'tagger_desc_col', 'tagger_amount_col']:
            st.session_state.pop(k, None)
        st.rerun()


# ── Entry point ────────────────────────────────────────────────────────────────

def render():
    st.title("Transaction Tagger")
    st.markdown("---")
    if 'tagger_step' not in st.session_state:
        st.session_state['tagger_step'] = 1
    step = st.session_state['tagger_step']
    step_names = ['Setup', 'Upload', 'Auto-Tag', 'Review', 'Output']
    cols = st.columns(5)
    for i, (col, name) in enumerate(zip(cols, step_names), 1):
        col.markdown(f"**{i}. {name}**" if i == step else f"{i}. {name}")
    st.markdown("---")
    {1: _render_step1, 2: _render_step2, 3: _render_step3,
     4: _render_step4, 5: _render_step5}[step]()


render()
