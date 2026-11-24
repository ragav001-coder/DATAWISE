"""
sidebar.py - the dark sidebar: DIT logo (top), DATAWISE branding, navigation,
current dataset card and the privacy note.

The logo is placed ABOVE the DATAWISE branding, as required.
"""

from __future__ import annotations

import html

import streamlit as st

from components import state
from components.styling import render_logo
from core.data_utils import APP_NAME, APP_TAGLINE, APP_TITLE, APP_VERSION, format_bytes


def render_sidebar(pages: list) -> None:
    with st.sidebar:
        # 1. DIT logo (official file, fitted to the sidebar width, aspect ratio kept)
        render_logo()

        # 2. DATAWISE branding
        st.markdown(
            f'<div class="dw-brand"><div class="dw-brand-badge">D</div><div>'
            f'<div class="dw-brand-name">{html.escape(APP_NAME)}</div>'
            f'<div class="dw-brand-sub">{html.escape(APP_TITLE)}</div></div></div>',
            unsafe_allow_html=True,
        )

        # 3. navigation
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        for page in pages:
            st.page_link(page)

        # 4. current dataset
        if state.has_data():
            df = state.working()
            steps = len([h for h in st.session_state["history"] if h.get("status") == "applied"])
            status = f"Modified - {steps} step(s)" if state.is_modified() else "Original (not cleaned)"
            name = html.escape(str(st.session_state["file_name"]))
            sample = " <span class='dw-demo-tag'>SAMPLE</span>" if st.session_state.get("source") == "sample" else ""
            st.markdown(
                f'<div class="dw-side-card"><div class="dw-side-label">Current dataset</div><b>{name}</b>{sample}'
                f'<div>{df.shape[0]:,} rows x {df.shape[1]:,} columns</div>'
                f'<div style="color:#94a3b8">{html.escape(status)}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="dw-side-card"><div class="dw-side-label">Current dataset</div>None loaded</div>', unsafe_allow_html=True)

        st.markdown(
            f'<div class="dw-side-note"><b>{html.escape(APP_TAGLINE)}</b><br>'
            "Do not upload confidential or highly sensitive personal data to a public deployment. "
            f"Your work lives only in this browser session. v{html.escape(APP_VERSION)}</div>",
            unsafe_allow_html=True,
        )
