"""quality_analysis.py - Module 8 (Data Quality Score) and Module 9 (visual analytics, part 2)."""

import streamlit as st

from components import charts, state
from components.metric_cards import metric_row, no_data_message, page_header, pill, section, tone_for_score
from core.cleaning_engine import missing_summary
from core.profiler import overall_profile
from core.quality_score import SCORE_METHOD_TEXT
from core.report_generator import build_comparison

SEVERITY_TONE = {"high": "bad", "medium": "warn", "low": "neutral"}


def render() -> None:
    page_header("Quality Analysis", "A transparent 0-100 score built from four measurable categories.")
    if not state.has_data():
        no_data_message()
        return

    df = state.working()
    original_score, score = state.get_scores()
    profile = overall_profile(df)

    if score["overall"] is None:
        st.warning(" ".join(score["notes"]) or "No score can be calculated for this data.")
        return

    source = score["validity_rules_source"]
    source_text = {"user": "your validation rules", "auto": "automatically suggested rules", "none": "no rules (not scored)"}[source]
    left, right = st.columns([2, 3], gap="large")
    with left:
        fig = charts.score_gauge(score["overall"])
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="qa_gauge")
        st.markdown(f"Grade: {pill(score['grade'], 'good' if score['overall'] >= 75 else 'warn')}", unsafe_allow_html=True)
        st.caption(f"Validity is measured with {source_text}.")
        if state.is_modified() and original_score["overall"] is not None:
            st.markdown(f"Original score **{original_score['overall']}** -> now **{score['overall']}** ({score['overall'] - original_score['overall']:+.1f})")
    with right:
        cols = st.columns(2)
        for index, cat in enumerate(score["categories"].values()):
            with cols[index % 2]:
                with st.container(border=True):
                    value = "n/a" if cat["score"] is None else f"{cat['score']}"
                    weight = f"weight {int(cat['effective_weight'] * 100)}%" if cat["applicable"] else "not scored"
                    st.markdown(f"<div class='dw-card-label'>{cat['label']} <span class='dw-muted'>({weight})</span></div>"
                                f"<div class='dw-card-value'>{value}</div>", unsafe_allow_html=True)
                    st.caption(cat["explanation"])

    section("Issues affecting the score")
    if score["issues"]:
        for issue in score["issues"]:
            st.markdown(f"{pill(issue['severity'].upper(), SEVERITY_TONE[issue['severity']])} &nbsp; **{issue['category']}** - {issue['description']}", unsafe_allow_html=True)
    else:
        st.success("No quality issues were detected.")

    section("How to improve the score")
    for tip in score["suggestions"]:
        st.markdown(f"- {tip}")
    st.page_link("pages/data_cleaning.py", label="Open Data Cleaning", icon=":material/cleaning_services:")

    section("Charts")
    c1, c2 = st.columns(2)
    with c1:
        fig = charts.score_breakdown(score)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="qa_breakdown")
    with c2:
        fig = charts.missing_by_column(df, missing_summary(df, state.settings()["treat_blank_as_missing"]))
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="qa_missing")
        else:
            st.success("No missing values, so there is no missing-value chart.")
    c3, c4 = st.columns(2)
    with c3:
        fig = charts.duplicate_vs_unique(profile["duplicate_rows"], profile["rows"])
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="qa_dups")
    with c4:
        result = st.session_state.get("validation_result")
        if result is not None and state.validation_is_current() and result.total_rows:
            fig = charts.valid_vs_invalid(result.valid_rows, result.invalid_rows)
            st.plotly_chart(fig, width="stretch", key="qa_valid")
        else:
            st.info("Run validation on the **Data Validation** page to see valid vs invalid records for the current data.")

    if state.is_modified():
        section("Before and after cleaning")
        comparison = build_comparison(state.original(), df, original_score, score)
        c5, c6 = charts.before_after(comparison)
        a, b = st.columns(2)
        if c5 is not None:
            a.plotly_chart(c5, width="stretch", key="qa_ba_counts")
        if c6 is not None:
            b.plotly_chart(c6, width="stretch", key="qa_ba_scores")

    with st.expander("How the score is calculated"):
        st.code(SCORE_METHOD_TEXT, language="text")


render()
