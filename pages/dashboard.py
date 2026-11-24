"""
dashboard.py - Module 1 (Dashboard) and Module 9 (visual analytics, part 1).

Without data: a welcome / empty-state screen (no fake numbers).
With data:    real metrics, overview, quality summary and charts.
"""

import streamlit as st

from components import charts, state
from components.metric_cards import metric_row, page_header, pill, section, tone_for_score
from components.styling import render_logo
from components.tables import preview_table
from core.cleaning_engine import missing_summary
from core.data_utils import APP_NAME, APP_TAGLINE, APP_TITLE
from core.profiler import overall_profile


def _welcome() -> None:
    # Welcome screen: the DIT logo is shown once here.
    render_logo(230)
    st.markdown(
        f'<div class="dw-hero"><h1>{APP_NAME}</h1><p><b>{APP_TITLE}</b><br>{APP_TAGLINE}. '
        "Upload a dataset, find its quality problems, clean it with full control, validate it and download the result and a report.</p></div>",
        unsafe_allow_html=True,
    )
    st.info("No dataset is loaded yet, so there are no metrics to show. Upload a file or try a sample dataset to begin.")
    left, right, _ = st.columns([1, 1, 2])
    left.page_link("pages/data_upload.py", label="Upload a dataset", icon=":material/upload_file:")
    right.page_link("pages/data_upload.py", label="Try a sample dataset", icon=":material/dataset:")

    section("How DATAWISE works")
    steps = ["Upload a CSV, Excel or JSON file (or load a sample).", "DATAWISE profiles the data and detects problems automatically.",
             "Review the Smart Clean recommendations, or clean step by step.", "Validate the cleaned data with your own rules.",
             "Compare before and after, then download the cleaned data and a report."]
    for number, text in enumerate(steps, start=1):
        st.markdown(f'<div class="dw-step"><div class="dw-step-n">{number}</div><div class="dw-step-t">{text}</div></div>', unsafe_allow_html=True)


def render() -> None:
    if not state.has_data():
        _welcome()
        return

    page_header("Dashboard", "A live summary of the dataset you are working on.", show_logo=True)
    df = state.working()
    original_score, score = state.get_scores()
    profile = overall_profile(df)

    validity = score["categories"].get("validity", {})
    invalid_text = f"{validity['details'].get('failed', 0):,}" if validity.get("score") is not None else "n/a"
    invalid_help = "failed checks (automatic or your rules)" if validity.get("score") is not None else "no rule applies yet"

    metric_row([("Total rows", f"{profile['rows']:,}", "", ""), ("Total columns", f"{profile['columns']:,}", "", ""),
                ("Missing values", f"{profile['missing_cells']:,}", f"{profile['missing_pct']}% of all cells", "warn" if profile["missing_cells"] else "good")])
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    metric_row([("Duplicate rows", f"{profile['duplicate_rows']:,}", "", "warn" if profile["duplicate_rows"] else "good"),
                ("Invalid values", invalid_text, invalid_help, "bad" if invalid_text not in ("0", "n/a") else ""),
                ("Quality score", "n/a" if score["overall"] is None else f"{score['overall']}", score["grade"], tone_for_score(score["overall"]))])

    # status and latest activity
    history = [h for h in st.session_state["history"]]
    status = "Cleaned" if state.is_modified() else "Uploaded - not cleaned yet"
    tone = "good" if state.is_modified() else "info"
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    left, right = st.columns([1, 1])
    with left:
        with st.container(border=True):
            section("Dataset status")
            source = "sample data" if st.session_state["source"] == "sample" else "your upload"
            st.markdown(f"{pill(status, tone)} &nbsp; <span class='dw-muted'>{st.session_state['file_name']} ({source})</span>", unsafe_allow_html=True)
            if original_score["overall"] is not None and state.is_modified():
                change = score["overall"] - original_score["overall"]
                st.markdown(f"Quality score: **{original_score['overall']} -> {score['overall']}** ({change:+.1f})")
    with right:
        with st.container(border=True):
            section("Latest cleaning activity")
            if history:
                last = history[-1]
                st.markdown(f"**{last['operation']}**  \n<span class='dw-muted'>{last['timestamp']} - {last.get('status')}"
                            f" - rows {last.get('rows_before')} -> {last.get('rows_after')}</span>", unsafe_allow_html=True)
                st.caption(f"{len(history)} step(s) in this session.")
            else:
                st.markdown("<span class='dw-muted'>No cleaning has been done yet in this session.</span>", unsafe_allow_html=True)

    section("Quick actions")
    a, b, c, d = st.columns(4)
    a.page_link("pages/data_cleaning.py", label="Run Smart Clean", icon=":material/auto_fix_high:")
    b.page_link("pages/data_validation.py", label="Validate data", icon=":material/rule:")
    c.page_link("pages/quality_analysis.py", label="Quality analysis", icon=":material/speed:")
    d.page_link("pages/reports.py", label="Reports and downloads", icon=":material/download:")

    section("Data quality summary")
    cols = st.columns(len(score["categories"]))
    for column, cat in zip(cols, score["categories"].values()):
        with column:
            with st.container(border=True):
                value = "n/a" if cat["score"] is None else f"{cat['score']}"
                st.markdown(f"<div class='dw-card-label'>{cat['label']}</div><div class='dw-card-value'>{value}</div>", unsafe_allow_html=True)
                width = 0 if cat["score"] is None else cat["score"]
                st.markdown(f"<div class='dw-bar'><span style='width:{width}%'></span></div>", unsafe_allow_html=True)
                st.caption(cat["explanation"])

    section("Dataset overview")
    preview_table(df, state.settings()["preview_rows"], key="dash_preview")

    section("Charts")
    summary = missing_summary(df, state.settings()["treat_blank_as_missing"])
    c1, c2 = st.columns(2)
    with c1:
        fig = charts.missing_by_column(df, summary)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="dash_missing")
        else:
            st.success("No missing values were found, so there is no missing-value chart.")
    with c2:
        fig = charts.score_breakdown(score)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="dash_breakdown")
        else:
            st.info("Not enough data for a score breakdown.")
    c3, c4 = st.columns(2)
    with c3:
        fig = charts.dtype_chart(df)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="dash_dtypes")
    with c4:
        fig = charts.duplicate_vs_unique(profile["duplicate_rows"], profile["rows"])
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="dash_dups")


render()
