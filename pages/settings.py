"""settings.py - Module 14 (Settings). Every setting here changes real behaviour in the app."""

import sys

import pandas as pd
import streamlit as st

from components import state
from components.metric_cards import page_header, section
from core.data_utils import APP_NAME, APP_TAGLINE, APP_TITLE, APP_VERSION, COMPANY_NAME, DEVELOPER
from core.file_handler import MAX_FILE_MB


def render() -> None:
    page_header("Settings", "Preferences apply to this browser session only.")
    cfg = state.settings()

    section("Display")
    cfg["preview_rows"] = int(st.select_slider("Rows shown in data previews", options=[5, 10, 20, 50, 100], value=cfg["preview_rows"], key="set_preview"))

    section("Cleaning")
    cfg["treat_blank_as_missing"] = st.toggle("Treat empty or space-only text as missing", value=cfg["treat_blank_as_missing"], key="set_blank",
                                              help="Used by the missing-value tools and recommendations. The quality score always counts blank text as missing.")
    c1, c2 = st.columns(2)
    cfg["iqr_multiplier"] = float(c1.slider("Default IQR multiplier (outliers)", 1.0, 3.0, float(cfg["iqr_multiplier"]), 0.1, key="set_iqr"))
    cfg["zscore_threshold"] = float(c2.slider("Default Z-score threshold (outliers)", 2.0, 4.0, float(cfg["zscore_threshold"]), 0.1, key="set_z"))
    cfg["dayfirst"] = st.toggle("Read ambiguous dates day-first (05/06/2024 = 5 June)", value=cfg["dayfirst"], key="set_dayfirst",
                                help="Default for date conversion and date validation. You can still change it for each operation.")

    section("Validation")
    p1, p2 = st.columns(2)
    low = int(p1.number_input("Phone number: minimum digits", 3, 20, int(cfg["phone_min_digits"]), key="set_phone_min"))
    high = int(p2.number_input("Phone number: maximum digits", 3, 20, int(cfg["phone_max_digits"]), key="set_phone_max"))
    if low > high:
        st.error("Minimum digits cannot be greater than maximum digits. The previous values are kept.")
    else:
        cfg["phone_min_digits"], cfg["phone_max_digits"] = low, high
    st.caption("Used by automatically suggested phone rules and by the quality score.")

    section("Reset")
    r1, r2 = st.columns(2)
    if r1.button("Reset project (remove dataset, history and rules)", key="set_reset_project", icon=":material/restart_alt:", width="stretch"):
        state.clear_dataset()
        st.session_state["flash"] = "The project was reset. Your settings were kept."
        st.rerun()
    if r2.button("Reset everything (including these settings)", key="set_reset_all", icon=":material/delete_forever:", width="stretch"):
        state.reset_everything()
        st.session_state["flash"] = "Everything was reset to the defaults."
        st.rerun()
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    section("Session and privacy")
    st.markdown(
        "- Your data, cleaning history, rules and settings live **only in this browser session** (Streamlit session state).\n"
        "- Nothing is written to disk or a database by DATAWISE. Refreshing the page, closing the tab or a session timeout clears everything.\n"
        "- On Streamlit Community Cloud the app can go to sleep after inactivity and has limited memory, so very large files may fail. "
        f"This app accepts files up to {MAX_FILE_MB} MB.\n"
        "- Do not upload confidential or highly sensitive personal information to a public deployment."
    )

    section("About")
    info = pd.DataFrame({
        "item": ["Application", "Full title", "Tagline", "Version", "Developer", "Internship partner", "Python", "pandas", "Streamlit"],
        "value": [APP_NAME, APP_TITLE, APP_TAGLINE, APP_VERSION, DEVELOPER, COMPANY_NAME, sys.version.split()[0], pd.__version__, st.__version__],
    })
    st.dataframe(info, width="stretch", hide_index=True)


render()
