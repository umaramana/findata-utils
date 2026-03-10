"""
Shared UI helpers for Rasrich Tools pages.
"""
import streamlit as st


def render_sidebar_header():
    """Inject a styled Rasrich Tools header above the st.navigation nav links via CSS."""
    st.markdown("""
    <style>
    [data-testid="stSidebarNavItems"]::before {
        content: "🧮 Rasrich Tools";
        display: block;
        font-size: 1.15rem;
        font-weight: 700;
        color: #1f4e79;
        padding: 1.2rem 0.8rem 0.8rem;
        border-bottom: 2px solid #d0e4f7;
        margin-bottom: 0.4rem;
        letter-spacing: 0.3px;
    }
    </style>
    """, unsafe_allow_html=True)
