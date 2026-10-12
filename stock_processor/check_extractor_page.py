"""
Check Extractor — OCR handwritten check images into an editable table,
then export to Excel/CSV. 100% local (Surya OCR on CPU).
Core logic lives in bookkeeping/check_extractor.py.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bookkeeping"))
import check_extractor as ce  # noqa: E402
import payee_match as pm  # noqa: E402

SS = st.session_state


@st.cache_resource(show_spinner="Loading OCR models (first run downloads ~1-2 GB)...")
def _get_engine():
    return ce.SuryaEngine()


def _file_key(files):
    return tuple((f.name, f.size) for f in files)


# ── Step 1: Upload ────────────────────────────────────────────────────────────

def _render_upload():
    st.subheader("Step 1: Upload Checks")
    files = st.file_uploader("Check images or PDF pages", type=ce.SUPPORTED_TYPES,
                             accept_multiple_files=True)
    multi = st.toggle("Multiple checks per page", value=False,
                      help="Detect and split individual checks on each page (scanned sheets).")
    st.selectbox("Client (payee matching)", ["(none)"] + pm.list_clients(), key="ck_client",
                 help="Match payees to this client's tagger vendors and saved check aliases. "
                      "(none) = keep the OCR text as read.")
    if not files:
        return None, multi

    if SS.get("ck_pages_key") != _file_key(files):
        pages = []
        for f in files:
            try:
                pages += [(f.name, n, img) for n, img in ce.load_pages(f.name, f.getvalue())]
            except Exception as e:
                st.error(f"{f.name}: could not read file ({e})")
        SS.ck_pages, SS.ck_pages_key = pages, _file_key(files)

    pages = SS.ck_pages
    st.caption(f"{len(pages)} page(s) from {len(files)} file(s)")
    cols = st.columns(6)
    for i, (name, n, img) in enumerate(pages[:24]):
        cols[i % 6].image(img, caption=f"{name} p{n}", use_container_width=True)
    if len(pages) > 24:
        st.caption(f"... and {len(pages) - 24} more")
    return pages, multi


def _run_extraction(pages, multi):
    try:
        engine = _get_engine()
    except ce.OcrEngineError as e:
        st.error(str(e))
        return

    checks, extracted, raws = [], [], []

    def add(chk, fields, failed):
        checks.append(chk)
        extracted.append((fields, failed))
        raws.append(fields["raw_text"])

    def ocr(img, where):
        try:
            return engine.ocr(img)
        except Exception as e:  # one bad image shouldn't stop the batch
            st.warning(f"{where}: OCR error ({e})")
            return []

    bar = st.progress(0.0, text="Extracting...")
    for p, (name, n, img) in enumerate(pages, start=1):
        boxes = ce.find_check_boxes(img) if multi else []
        if len(boxes) >= 2:  # statement page: one OCR pass for the whole grid
            bar.progress((p - 1) / len(pages), text=f"Page {p} of {len(pages)}: {len(boxes)} checks, reading page...")
            lines = ocr(img, f"{name} p{n}")
            for i, (fields, (x, y, w, h)) in enumerate(ce.extract_page(lines, boxes), start=1):
                view = img.crop((x, y, x + w, min(y + h, img.height)))
                add(ce.CheckImage(name, n, i, view), fields, failed=not lines)
            continue
        crops = [img.crop((x, y, x + w, y + h)) for x, y, w, h in boxes] or [img]
        for i, crop in enumerate(crops, start=1):
            bar.progress((p - 1) / len(pages), text=f"Page {p} of {len(pages)}: check {i} of {len(crops)}")
            lines = ocr(crop, f"{name} p{n} #{i}")
            add(ce.CheckImage(name, n, i, crop), ce.extract_fields(lines, *crop.size), failed=not lines)
    bar.empty()

    SS.ck_checks, SS.ck_raw, SS.ck_fields = checks, raws, extracted
    SS.ck_df_key = SS.ck_pages_key
    SS.ck_run = SS.get("ck_run", 0) + 1  # fresh editor state per extraction
    SS.ck_rows_key = None
    st.success(f"Extracted {len(checks)} check(s).")


def _build_rows():
    """Rows from the stored OCR fields, matched to the picked client. Re-run on client change, no re-OCR."""
    client = SS.get("ck_client", "(none)")
    key = (SS.ck_run, client)
    if SS.get("ck_rows_key") == key:
        return
    matcher = None if client == "(none)" else pm.load_matcher(client)
    rows = []
    for chk, (fields, failed) in zip(SS.ck_checks, SS.ck_fields):
        fields = dict(fields)
        if matcher and not failed:
            ce.apply_payee_match(fields, matcher)
        rows.append(ce.build_row(chk, fields, ocr_failed=failed))
    SS.ck_df = pd.DataFrame(rows)
    SS.ck_rows_key = key
    SS.ck_editor_v = SS.get("ck_editor_v", 0) + 1  # fresh editor state for the new rows


# ── Step 2: Review ────────────────────────────────────────────────────────────

def _render_review():
    st.subheader("Step 2: Review")
    df = SS.ck_df
    edited = st.data_editor(
        df, key=f"ck_editor_{SS.ck_editor_v}", hide_index=True, use_container_width=True,
        disabled=["Source", "Page", "Check #", "Payee (OCR)"],
        column_config={
            "Check No.": st.column_config.TextColumn(),
            "Date": st.column_config.TextColumn(help="Kept as text — handwriting isn't force-parsed."),
            "Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Payee": st.column_config.TextColumn(width="medium"),
            "Payee (OCR)": st.column_config.TextColumn(width="medium", help="Payee as read, before matching."),
            "Purpose": st.column_config.TextColumn(width="medium"),
            "Confidence": st.column_config.SelectboxColumn(options=ce.CONF_LEVELS, required=True),
            "Flag": st.column_config.CheckboxColumn(),
        },
    )

    if "Payee (OCR)" in df.columns:
        _render_save_corrections(df, edited)

    labels = [f"{i + 1}. {r['Source']} p{r['Page']} #{r['Check #']} — {r['Payee'] or '(no payee)'}"
              for i, r in edited.iterrows()]
    pick = st.selectbox("View check", range(len(labels)), format_func=lambda i: labels[i])
    left, right = st.columns([3, 2])
    left.image(SS.ck_checks[pick].image, use_container_width=True)
    with right:
        row = edited.iloc[pick]
        st.markdown(f"**Confidence:** {row['Confidence']}  \n**Flag:** {'Yes' if row['Flag'] else 'No'}")
        with st.expander("Raw OCR text"):
            st.code(SS.ck_raw[pick] or "(no text)", language=None)
    return edited


def _render_save_corrections(df, edited):
    """Payees edited in the table -> the client's check aliases file (never the tagger lookup)."""
    changed = [(o, e) for o, before, e in zip(df["Payee (OCR)"], df["Payee"], edited["Payee"])
               if str(o).strip() and str(e).strip() and e != before]
    if st.button(f"Save payee corrections ({len(changed)})", disabled=not changed,
                 help="Remember these OCR readings for this client, so they match exactly next time."):
        n = pm.save_aliases(SS.ck_client, changed)
        st.success(f"Saved {n} payee alias(es) for {SS.ck_client}.")


def _render_sidebar_counts(df):
    counts = df["Confidence"].value_counts()
    st.sidebar.markdown("**Check Confidence**")
    c1, c2, c3 = st.sidebar.columns(3)
    c1.metric("HIGH", int(counts.get("HIGH", 0)))
    c2.metric("MED", int(counts.get("MEDIUM", 0)))
    c3.metric("LOW", int(counts.get("LOW", 0)))
    st.sidebar.caption(f"{int(df['Flag'].sum())} flagged")


# ── Step 3: Export ────────────────────────────────────────────────────────────

def _render_export(df):
    st.subheader("Step 3: Export")
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("Download Excel", ce.to_excel(df), file_name="checks.xlsx", type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c2.download_button("Download CSV", df[[c for c in ce.EXPORT_COLS if c in df.columns]].to_csv(index=False).encode(),
                       file_name="checks.csv", mime="text/csv")


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("Check Extractor")
st.info("🔒 All processing runs locally. No data sent to any external service. "
        "Saved payee corrections stay on this machine (client aliases file: OCR text and vendor only, "
        "no check images or amounts).")
st.markdown("---")

pages, multi = _render_upload()
if pages and st.button("Extract All", type="primary"):
    _run_extraction(pages, multi)

if pages and SS.get("ck_df_key") == SS.get("ck_pages_key"):
    st.markdown("---")
    _build_rows()
    edited = _render_review()
    _render_sidebar_counts(edited)
    st.markdown("---")
    _render_export(edited)
