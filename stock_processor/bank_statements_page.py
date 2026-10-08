"""
Bank Statements — extract transactions from statement PDFs/images, fill check payees
from a Check Extractor register, review totals, download Summary -> Master -> months.
"""
import os
import tempfile

import pandas as pd
import streamlit as st

import bank_statements as B
from pdf_text import file_pages
from check_register import load_register


def _save_temp(uploaded):
    suffix = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded.getvalue())
        return f.name


def _totals_table(totals):
    for name, (printed, extracted, ok) in totals.items():
        if ok is None:
            st.markdown(f"⚪ **{name}**: extracted {extracted:,.2f} (no printed total)")
        elif ok:
            st.markdown(f":green[✅ **{name}**: {printed:,.2f} = {extracted:,.2f}]")
        else:
            st.markdown(f":red[❌ **{name}**: printed {printed:,.2f}, extracted {extracted:,.2f}, "
                        f"gap {extracted - printed:+,.2f}]")


st.title("Bank Statements")
st.markdown("---")

fmt = st.selectbox("Statement format", list(B.FORMATS))
files = st.file_uploader("Upload statements (PDF or image)", type=["pdf", "png", "jpg", "jpeg"],
                         accept_multiple_files=True, key="bank_stmts")
reg_file = st.file_uploader("Check register (optional, Check Extractor Excel)", type=["xlsx"], key="bank_reg")

if files and st.button("Extract", type="primary"):
    register = None
    if reg_file is not None:
        try:
            register = load_register(reg_file)
        except Exception as e:
            st.error(f"Register: {e}")
            st.stop()
    results = []
    for up in files:
        path = _save_temp(up)
        try:
            with st.spinner(f"Reading {up.name}..."):
                pages, how = file_pages(path)
            parsed = B.parse_file(fmt, pages)
            B.apply_register(parsed['transactions'], register)
            results.append({'name': up.name, 'how': how, **parsed})
        except Exception as e:
            st.error(f"{up.name}: {e}")
        finally:
            os.unlink(path)
    st.session_state['bank_results'] = results

results = st.session_state.get('bank_results')
if results:
    for r in results:
        with st.expander(f"{r['name']} — {len(r['transactions'])} rows (read as {r['how']})", expanded=True):
            _totals_table(r['totals'])
            if r['unparsed']:
                st.warning(f"{len(r['unparsed'])} line(s) had no amount and were not added:")
                st.code("\n".join(r['unparsed']))
            st.dataframe(pd.DataFrame(
                [{'date': t['date'], 'description': t['description'], 'amount': t['amount'],
                  'section': t['section'], 'status': t['status'], 'filename': r['name']} for t in r['transactions']]),
                use_container_width=True, hide_index=True)
    if not any(r['transactions'] for r in results):
        st.error("No rows were extracted from any file, so there is nothing to download. "
                 "Check the statement format selected above.")
        st.stop()
    st.download_button(
        "Download Excel", data=B.build_workbook(results), file_name="bank_statements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
