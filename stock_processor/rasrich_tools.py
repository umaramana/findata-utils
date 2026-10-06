"""
Rasrich Tools — Internal utility suite for Rasrich Tax Preparers.
Entry point: streamlit run rasrich_tools.py
"""
import streamlit as st
from _ui_helpers import render_sidebar_header

st.set_page_config(page_title="Rasrich Tools", page_icon="🧮", layout="wide")

render_sidebar_header()

pages = {
    "Tax": [
        st.Page("stock_processor_page.py", title="Stock Processor", icon="📊"),
    ],
    "Bookkeeping": [
        st.Page("tagger_page.py", title="Transaction Tagger", icon="🏷️"),
        st.Page("check_extractor_page.py", title="Check Extractor", icon="🧾"),
    ],
    "Utilities": [
        st.Page("excel_utilities_page.py", title="Excel Utilities", icon="📁"),
    ],
}

pg = st.navigation(pages)
pg.run()
