"""reports.py - Module 12 (Download Center) and Module 13 (Reports)."""

import streamlit as st
import streamlit.components.v1 as components

from components import state
from components.metric_cards import no_data_message, page_header, section
from components.styling import logo_bytes
from core.file_handler import dataframe_to_csv_bytes, dataframe_to_excel_bytes
from core.profiler import profile_dataframe
from core.recommendation_engine import analyze_dataset
from core.report_generator import (
    build_comparison,
    build_html_report,
    history_to_csv_bytes,
    history_to_json_bytes,
    quality_report_excel_bytes,
    validation_report_excel_bytes,
)
from core.validation_engine import suggest_rules, validate

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _validation_for_reports(df):
    """Use the latest validation if it matches the current data, otherwise validate with suggested rules."""
    result = st.session_state.get("validation_result")
    meta = st.session_state.get("validation_meta")
    if result is not None and state.validation_is_current():
        return result, meta["rules"], "Using your latest validation run."
    cfg = state.settings()
    rules = st.session_state["validation_rules"] or suggest_rules(df, cfg["phone_min_digits"], cfg["phone_max_digits"])
    note = ("No up-to-date validation run was found, so the " + ("rules you selected" if st.session_state["validation_rules"] else "automatically suggested rules")
            + " were applied to the current data just now.")
    return validate(df, rules), rules, note


def render() -> None:
    page_header("Reports and Downloads", "Download the cleaned data, validation results, quality reports and the cleaning log.")
    if not state.has_data():
        no_data_message()
        return

    df = state.working()
    name = st.session_state["file_name"]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    original_score, score = state.get_scores()
    comparison = build_comparison(state.original(), df, original_score, score)
    history = st.session_state["history"]
    validation, rules, note = _validation_for_reports(df)

    if not state.is_modified():
        st.info("No cleaning has been applied yet, so the downloads contain the data as uploaded.")

    section("Download center")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Cleaned data (CSV)", dataframe_to_csv_bytes(df), f"{stem}_cleaned.csv", "text/csv", key="dl_csv", width="stretch", icon=":material/table:")
    c2.download_button("Cleaned data (Excel)", dataframe_to_excel_bytes(df), f"{stem}_cleaned.xlsx", XLSX, key="dl_xlsx", width="stretch", icon=":material/table_view:")
    c3.download_button("Quality report (Excel)", quality_report_excel_bytes(name, original_score, score, comparison, profile_dataframe(df), history),
                       f"{stem}_quality_report.xlsx", XLSX, key="dl_quality", width="stretch", icon=":material/speed:")
    c4, c5, c6 = st.columns(3)
    c4.download_button("Validation report (Excel)", validation_report_excel_bytes(validation, rules, name), f"{stem}_validation_report.xlsx", XLSX,
                       key="dl_validation", width="stretch", icon=":material/rule:")
    c5.download_button("Cleaning history (CSV)", history_to_csv_bytes(history), f"{stem}_cleaning_history.csv", "text/csv", key="dl_hist_csv", width="stretch", icon=":material/history:")
    c6.download_button("Cleaning history (JSON)", history_to_json_bytes(history), f"{stem}_cleaning_history.json", "application/json", key="dl_hist_json", width="stretch", icon=":material/data_object:")
    st.caption(note + " Cleaning history covers this session only.")

    section("Data quality report")
    recs = analyze_dataset(df, state.settings())
    html_report = build_html_report(
        name, state.original(), df, original_score, score, history, validation, rules, recs,
        file_size=st.session_state["file_size"], logo_bytes=logo_bytes(),
    )
    d1, d2 = st.columns([1, 2])
    d1.download_button("Download report (HTML)", html_report.encode("utf-8"), f"{stem}_data_quality_report.html", "text/html", type="primary",
                       key="dl_html", width="stretch", icon=":material/description:")
    d2.caption("Open the HTML file in any browser. To get a PDF, press Ctrl+P and choose 'Save as PDF'.")
    with st.expander("Preview the report", expanded=False):
        components.html(html_report, height=760, scrolling=True)


render()
