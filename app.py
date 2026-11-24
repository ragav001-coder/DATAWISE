"""
app.py - the DATAWISE entry point. Run it with:   streamlit run app.py

What it does on every run (Streamlit re-runs this file after each click):
  1. sets the page title/icon  2. applies the design (CSS)  3. prepares the
  session state  4. draws the sidebar (logo, branding, navigation)
  5. runs the page the user selected.

The page files live in the pages/ folder; each one has a render() function.
"""

import streamlit as st

from components import state
from components.sidebar import render_sidebar
from components.styling import apply_global_css
from core.data_utils import APP_NAME, APP_TITLE

st.set_page_config(
    page_title=f"{APP_NAME} | {APP_TITLE}",
    page_icon=":material/insights:",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_global_css()
state.init_state()

PAGES = [
    st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", url_path="dashboard", default=True),
    st.Page("pages/data_upload.py", title="Data Upload", icon=":material/upload_file:", url_path="upload"),
    st.Page("pages/data_profiling.py", title="Data Profiling", icon=":material/query_stats:", url_path="profiling"),
    st.Page("pages/data_cleaning.py", title="Data Cleaning", icon=":material/cleaning_services:", url_path="cleaning"),
    st.Page("pages/data_validation.py", title="Data Validation", icon=":material/rule:", url_path="validation"),
    st.Page("pages/quality_analysis.py", title="Quality Analysis", icon=":material/speed:", url_path="quality"),
    st.Page("pages/reports.py", title="Reports and Downloads", icon=":material/download:", url_path="reports"),
    st.Page("pages/settings.py", title="Settings", icon=":material/settings:", url_path="settings"),
]

# position="hidden": we draw our own navigation inside the sidebar (below the logo and branding).
navigation = st.navigation(PAGES, position="hidden")
render_sidebar(PAGES)
navigation.run()
