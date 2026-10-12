"""
Excel Utilities — Collate multiple Excel tabs into a single master sheet
with type-aware formatting and an inline reconciliation summary.
"""

import pandas as pd
import streamlit as st

from excel_collator import _collate_sheets, _generate_output, _preview_cols


# ── Column type UI ────────────────────────────────────────────────────────────

def _render_type_selector(auto_types):
    number_cols = [col for col, t in auto_types.items() if t == 'number']
    if not number_cols:
        return {col: ('currency' if t == 'number' else t) for col, t in auto_types.items()}
    with st.expander("Column types — auto-detected, adjust if needed", expanded=True):
        integer_cols = st.multiselect(
            "Mark as Integer (whole numbers — e.g. check numbers):",
            options=number_cols,
            help="Unselected numeric columns are treated as Currency and included in reconciliation totals."
        )
    return {col: ('integer' if col in integer_cols else ('currency' if t == 'number' else t))
            for col, t in auto_types.items()}



# ── Page render ───────────────────────────────────────────────────────────────

def _render_tab_collator():
    st.subheader("Collate Excel Tabs → Master")
    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"], key="collator_upload")
    if uploaded_file is None:
        return

    sheet_names = pd.ExcelFile(uploaded_file).sheet_names
    selected = st.multiselect("Select tabs to include:", options=sheet_names, default=sheet_names)
    if not selected:
        st.warning("Select at least one tab.")
        return

    uploaded_file.seek(0)
    _, auto_types = _preview_cols(uploaded_file, selected[0])
    col_types = _render_type_selector(auto_types)

    if st.button("Collate", type="primary"):
        try:
            uploaded_file.seek(0)
            with st.spinner(f"Collating {len(selected)} tab(s)..."):
                master_df = _collate_sheets(uploaded_file, selected)
            if master_df.empty:
                st.error("No data found in selected tabs.")
                return
            uploaded_file.seek(0)
            with st.spinner("Generating output file..."):
                output = _generate_output(uploaded_file, master_df, col_types)
            st.success(f"{len(master_df)} rows from {len(selected)} tab(s) — Master tab added with reconciliation.")
            st.download_button(
                label="Download",
                data=output,
                file_name=uploaded_file.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        except Exception as e:
            st.error(f"Error: {str(e)}")


st.title("Excel Utilities")
st.markdown("---")
_render_tab_collator()
