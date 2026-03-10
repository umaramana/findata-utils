"""
Rasrich Tools — Internal utility suite for Rasrich Tax Preparers.
Entry point: streamlit run rasrich_tools.py
"""
import streamlit as st
from _ui_helpers import render_sidebar_header

st.set_page_config(page_title="Rasrich Tools", page_icon="🧮", layout="wide")

render_sidebar_header()

pages = [
    st.Page("stock_processor_page.py", title="Stock Processor", icon="📊"),
    st.Page("excel_utilities_page.py", title="Excel Utilities", icon="📁"),
]

pg = st.navigation(pages)
pg.run()
