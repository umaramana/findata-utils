"""
Stock Transaction Processor - Drake Import Format Generator
Main Streamlit application for processing broker transaction files.

Supports: Fidelity, Charles Schwab, Robinhood
Output: Drake tax software import format (15 columns)
"""

import streamlit as st
import pandas as pd
import io

from brokers import fidelity, schwab, robinhood, merrill, morgan_stanley, betterment, apex_clearing, jpmorgan
import drake_mapper
import utils
import pdf_qc


# Page configuration
st.set_page_config(
    page_title="Stock Transaction Processor",
    page_icon="📊",
    layout="wide"
)

_BROKER_KEY_MAP = {
    "Fidelity": "fidelity",
    "Charles Schwab": "charles_schwab",
    "Robinhood": "robinhood",
    "Merrill Lynch": "merrill",
    "Morgan Stanley": "morgan_stanley",
    "Betterment": "csv_betterment",  # csv_ prefix = skip QC
    "Apex Clearing": "apex_clearing",
    "JP Morgan": "jpmorgan",
}


def _render_broker_selector():
    st.subheader("Step 1: Select Broker")
    broker = st.radio(
        "Choose the broker for your transaction file:",
        ["Fidelity", "Charles Schwab", "Robinhood", "Merrill Lynch", "Morgan Stanley", "Betterment", "Apex Clearing", "JP Morgan"],
        horizontal=True
    )
    st.markdown("---")
    return broker, _BROKER_KEY_MAP[broker]


def _render_file_uploader(broker_key):
    st.subheader("Step 2: Upload Transaction File")
    st.markdown("""
    **Prerequisites:**
    - For Excel brokers: Convert your 1099-B PDF to Excel using PDF24 or similar tool
    - For Fidelity: Keep only the "Stock Trans" sheets
    - For Betterment: Export CSV directly from the platform
    """)
    return st.file_uploader(
        "Upload your transaction file",
        type=["xlsx", "xls", "csv"],
        key=f"uploader_{broker_key}",
        help="Upload the Excel or CSV file from your broker"
    )


def _run_qc_check(uploaded_file, broker_key, qc_key):
    """Run QC and cache results in session state."""
    if broker_key.startswith('csv_'):
        st.info("CSV file detected — column alignment check not required.")
        st.session_state['_qc_key'] = qc_key
        st.session_state['_qc_result'] = {}
        st.session_state.pop('corrected_excel', None)
    elif st.session_state.get('_qc_key') != qc_key:
        try:
            uploaded_file.seek(0)
            qc_result = pdf_qc.detect_and_correct(uploaded_file, broker_key)
            st.session_state['_qc_key'] = qc_key
            st.session_state['_qc_result'] = qc_result
            if qc_result['corrected_excel'] is not None:
                st.session_state['corrected_excel'] = qc_result['corrected_excel']
            else:
                st.session_state.pop('corrected_excel', None)
        except Exception as e:
            st.session_state['_qc_key'] = qc_key
            st.session_state['_qc_result'] = {'error': str(e)}
            st.session_state.pop('corrected_excel', None)


def _render_qc_results(qc_result):
    if 'error' in qc_result:
        st.error(f"Column alignment check failed: {qc_result['error']}")
    elif qc_result:
        if qc_result['total_fixes'] == 0:
            st.success(
                f"Column alignment verified — "
                f"{qc_result['sheets_checked']} sheet(s), no corrections needed."
            )
        else:
            st.info(
                f"Auto-corrected {qc_result['total_fixes']} row(s) across "
                f"{qc_result['sheets_checked']} sheet(s)."
            )

        if qc_result.get('review_rows'):
            st.warning(
                f"**{len(qc_result['review_rows'])} row(s) have optional column values "
                f"— verify these manually:**"
            )
            for row_desc in qc_result['review_rows']:
                st.text(f"  {row_desc}")

        with st.expander("Column Correction Details"):
            for log_line in qc_result['log']:
                st.text(log_line)


def main():
    st.title("Stock Transaction Processor")
    st.markdown("Convert broker 1099-B statements to Drake tax software import format")
    st.markdown("---")

    broker, broker_key = _render_broker_selector()
    uploaded_file = _render_file_uploader(broker_key)

    if uploaded_file is not None:
        st.markdown(f"**Uploaded:** {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")

        qc_key = f"{uploaded_file.name}_{uploaded_file.size}_{broker}"
        _run_qc_check(uploaded_file, broker_key, qc_key)
        qc_result = st.session_state.get('_qc_result', {})
        _render_qc_results(qc_result)

        st.markdown("---")

        file_to_process = st.session_state.get('corrected_excel', None) or uploaded_file
        if st.button("Process Transactions", type="primary"):
            if hasattr(file_to_process, 'seek'):
                file_to_process.seek(0)
            process_file(file_to_process, broker, broker_key)


def _route_to_broker(uploaded_file, broker):
    if broker == "Fidelity":
        return fidelity.process(uploaded_file)
    elif broker == "Charles Schwab":
        return schwab.process(uploaded_file)
    elif broker == "Robinhood":
        return robinhood.process(uploaded_file)
    elif broker == "Merrill Lynch":
        return merrill.process(uploaded_file)
    elif broker == "Morgan Stanley":
        return morgan_stanley.process(uploaded_file)
    elif broker == "Apex Clearing":
        return apex_clearing.process(uploaded_file)
    elif broker == "JP Morgan":
        return jpmorgan.process(uploaded_file)
    else:  # Betterment
        return betterment.process(uploaded_file)


def _normalize_fed_tax(processed_df):
    for col in list(processed_df.columns):
        col_lower = col.lower()
        if col != 'Fed Tax Withheld' and 'federal' in col_lower and 'tax' in col_lower:
            processed_df = processed_df.rename(columns={col: 'Fed Tax Withheld'})
            break
    return processed_df


def _render_raw_data(processed_df):
    with st.expander("View Raw Processed Data", expanded=False):
        st.dataframe(utils.clean_dataframe_for_display(processed_df), use_container_width=True)
        st.caption(f"Found {len(processed_df)} rows from broker processing")


def _render_sheet_diagnostics(uploaded_file, broker_key, processed_df):
    with st.expander("Sheet Processing Diagnostics", expanded=True):
        uploaded_file.seek(0)
        if broker_key.startswith('csv_'):
            raw = pd.read_csv(uploaded_file, header=None, dtype=str)
            st.write(f"**Format:** CSV — {len(raw)} raw rows → {len(processed_df)} processed rows")
            st.dataframe(raw.head(10))
        else:
            diag_excel = pd.ExcelFile(uploaded_file)
            st.write(f"**Sheets in file:** {diag_excel.sheet_names}")
            for sn in diag_excel.sheet_names:
                raw = diag_excel.parse(sn, header=None)
                if 'Source Sheet' in processed_df.columns:
                    sheet_count = len(processed_df[processed_df['Source Sheet'] == sn])
                else:
                    sheet_count = 'N/A'
                st.write(f"**{sn}** — {len(raw)} raw rows → {sheet_count} processed rows")
                st.dataframe(raw.head(10))


def _render_summary_metrics(summary):
    has_fed_tax = summary.get('fed_tax_total', 0.0) > 0

    if has_fed_tax:
        col1, col2, col3, col4, col5 = st.columns(5)
        col5.metric("Fed Tax Withheld", f"${summary['fed_tax_total']:,.2f}",
                    help="Enter this total manually in Drake. Rows with Fed Tax are highlighted below.")
    else:
        col1, col2, col3, col4 = st.columns(4)

    col1.metric("Transactions", summary['total_transactions'])
    col2.metric("Unique Securities", summary['unique_securities'])
    col3.metric("Total Proceeds", f"${summary['total_proceeds']:,.2f}")
    col4.metric("Wash Sales", summary['wash_sale_count'])


def _render_drake_preview(drake_df):
    st.subheader("Drake Import Format Preview")
    st.markdown("*Showing populated columns. Full output includes all 15 Drake columns.*")

    preview_cols = ['Desc', 'Date Acquired', 'Date Sold', 'Type', 'Proceeds', 'Cost', 'Accrued Discount', 'Wash Sale Loss']
    if 'Fed Tax Withheld' in drake_df.columns:
        preview_cols = preview_cols + ['Fed Tax Withheld']

    preview_df = drake_df[[c for c in preview_cols if c in drake_df.columns]].copy()
    display_df = utils.clean_dataframe_for_display(preview_df)

    if 'Fed Tax Withheld' in display_df.columns:
        def _highlight_fed_tax(row):
            val = row.get('Fed Tax Withheld', '')
            try:
                if val and float(val) != 0:
                    return ['background-color: #fff3cd'] * len(row)
            except (ValueError, TypeError):
                pass
            return [''] * len(row)

        st.dataframe(
            display_df.style.apply(_highlight_fed_tax, axis=1),
            use_container_width=True,
            height=400
        )
    else:
        st.dataframe(display_df, use_container_width=True, height=400)


def _render_download_section(drake_df, broker):
    st.subheader("Step 4: Download Drake Import File")

    broker_slug = broker.lower().replace(' ', '_')
    filename = f"{broker_slug}_drake_import.xlsx"

    excel_file = utils.generate_excel_download(drake_df, filename)

    col1, col2 = st.columns([1, 3])
    with col1:
        st.download_button(
            label="Download Drake Import File",
            data=excel_file,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

    with col2:
        st.info(f"""
        **File:** {filename}
        - Contains all 15 Drake columns
        - Populated: Desc, Date Acquired, Date Sold, Proceeds, Cost, Accrued Discount, Wash Sale Loss, Type (where available)
        - Ready for Drake import
        """)

    with st.expander("View Full Drake Output (All 15 Columns)", expanded=False):
        st.dataframe(utils.clean_dataframe_for_display(drake_df), use_container_width=True)


def _process_and_render(uploaded_file, broker, broker_key):
    processed_df = _route_to_broker(uploaded_file, broker)
    processed_df = _normalize_fed_tax(processed_df)

    if processed_df.empty:
        st.error("No transaction data found in the file.")
        st.info("""
        **Troubleshooting tips:**
        - Ensure the file contains transaction data
        - Check that the PDF was converted correctly
        - Verify you selected the correct broker
        """)
        return

    _render_raw_data(processed_df)
    _render_sheet_diagnostics(uploaded_file, broker_key, processed_df)

    drake_df = drake_mapper.map_to_drake_format(processed_df, broker_key)
    is_valid, errors = drake_mapper.validate_drake_output(drake_df)

    if not is_valid:
        st.warning("Validation warnings:")
        for error in errors:
            st.warning(f"- {error}")

    summary = drake_mapper.get_processing_summary(drake_df, broker_key)
    _render_summary_metrics(summary)
    st.success(f"Successfully processed {len(drake_df)} transactions from {broker}")
    st.markdown("---")
    _render_drake_preview(drake_df)
    st.markdown("---")
    _render_download_section(drake_df, broker)


def _render_processing_error(e):
    st.error(f"Error processing file: {str(e)}")
    st.markdown("""
    **Common issues:**
    - File may not be in the expected format
    - PDF conversion may have introduced formatting issues
    - Try re-converting the PDF with PDF24

    If the problem persists, please check the file structure matches the expected broker format.
    """)

    with st.expander("Error Details"):
        import traceback
        st.code(traceback.format_exc())


def process_file(uploaded_file, broker, broker_key):
    """Process the uploaded file based on broker selection."""
    st.subheader("Step 3: Processing Results")

    try:
        with st.spinner(f"Processing {broker} file..."):
            _process_and_render(uploaded_file, broker, broker_key)
    except Exception as e:
        _render_processing_error(e)


# Footer
def show_footer():
    st.markdown("---")
    st.markdown("""
    ### Instructions

    **Pre-processing steps:**
    1. Download your 1099-B PDF or CSV from your broker
    2. For PDF brokers: Convert to Excel using [PDF24](https://tools.pdf24.org/en/pdf-to-excel) or similar
    3. For Fidelity: Remove non-"Stock Trans" sheets
    4. For Betterment: Export CSV directly — no conversion needed

    **Using this tool:**
    1. Select your broker
    2. Upload the Excel or CSV file
    3. Review the processed transactions
    4. Download the Drake import file

    **Output format:**
    - 15-column Drake import format
    - Populated: Desc, Date Acquired, Date Sold, Proceeds, Cost, Accrued Discount, Wash Sale Loss, Type (S/L where available)
    - Empty: TSJ, F, State, City, Form 8949 Check Box, Ordinary, AMT Cost Basis
    """)

    st.caption("Stock Transaction Processor v1.0 | Tax Season 2025")


if __name__ == "__main__":
    main()
    show_footer()
