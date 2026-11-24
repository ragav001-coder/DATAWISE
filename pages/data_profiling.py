"""data_profiling.py - Module 3 (Data Profiling): the health check of every column."""

import streamlit as st

from components import charts, state
from components.metric_cards import metric_row, no_data_message, page_header, section
from components.tables import show_table
from core.cleaning_engine import detect_outliers_iqr, missing_summary
from core.data_utils import is_numeric_column
from core.file_handler import dataframe_to_csv_bytes
from core.profiler import overall_profile, profile_dataframe

LABELS = {
    "column": "Column", "data_type": "Type", "total_records": "Records", "non_null": "Non-null", "missing": "Missing",
    "missing_pct": "Missing %", "empty_strings": "Empty text", "unique_values": "Unique", "duplicate_values": "Repeated values",
    "min": "Min", "max": "Max", "mean": "Mean", "median": "Median", "outliers_iqr": "Outliers (IQR)", "common_values": "Most common values",
}


def render() -> None:
    page_header("Data Profiling", "A detailed health check of every column in the current data.")
    if not state.has_data():
        no_data_message()
        return

    df = state.working()
    if state.is_modified():
        st.caption("Profiling the **current (cleaned)** data.")
    overall = overall_profile(df)
    metric_row([("Rows", f"{overall['rows']:,}", "", ""), ("Columns", f"{overall['columns']:,}", "", ""),
                ("Missing cells", f"{overall['missing_cells']:,}", f"{overall['missing_pct']}%", "warn" if overall["missing_cells"] else "good"),
                ("Duplicate rows", f"{overall['duplicate_rows']:,}", "", "warn" if overall["duplicate_rows"] else "good"),
                ("Memory", f"{overall['memory_kb']:,} KB", "", "")])

    section("Column profile")
    profile = profile_dataframe(df)
    show_table(profile.rename(columns=LABELS), height=min(560, 60 + 36 * len(profile)), key="profile_table")
    st.caption("Missing = empty cells plus empty/space-only text. 'Repeated values' = records whose value already appears elsewhere. "
               "Outliers use the IQR rule (see the Data Cleaning page).")
    st.download_button("Download profile (CSV)", dataframe_to_csv_bytes(profile), "datawise_column_profile.csv", "text/csv", key="dl_profile")

    c1, c2 = st.columns(2)
    with c1:
        fig = charts.missing_by_column(df, missing_summary(df, state.settings()["treat_blank_as_missing"]))
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="prof_missing")
        else:
            st.success("No missing values in any column.")
    with c2:
        fig = charts.dtype_chart(df)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="prof_dtypes")

    section("Look at one column")
    column = st.selectbox("Column", list(df.columns), key="profile_column")
    if column is not None:
        row = profile[profile["column"] == column].iloc[0]
        metric_row([("Type", row["data_type"], "", ""), ("Missing", f"{int(row['missing']):,}", f"{row['missing_pct']}%", ""),
                    ("Unique values", f"{int(row['unique_values']):,}", "", ""), ("Repeated values", f"{int(row['duplicate_values']):,}", "", "")])
        if is_numeric_column(df[column]):
            mask, low, high = detect_outliers_iqr(df[column], state.settings()["iqr_multiplier"])
            left, right = st.columns(2)
            with left:
                fig = charts.histogram(df, column)
                st.plotly_chart(fig, width="stretch", key="prof_hist") if fig is not None else st.info("Not enough numeric values for a histogram.")
            with right:
                fig = charts.numeric_distribution(df, column, low, high)
                st.plotly_chart(fig, width="stretch", key="prof_box") if fig is not None else st.info("Not enough numeric values for a box plot.")
            st.caption(f"{int(mask.sum())} potential outlier(s) by the IQR rule (multiplier {state.settings()['iqr_multiplier']}).")
        else:
            fig = charts.top_values(df, column)
            st.plotly_chart(fig, width="stretch", key="prof_top") if fig is not None else st.info("This column has no values to chart.")


render()
