"""
data_cleaning.py - Modules 4, 6, 7 and 10 on one page, as tabs:

  Smart Clean | Missing values | Duplicates | Text | Column names | Data types |
  Outliers | Standardization | Custom rules | History and compare

Every button calls core/cleaning_engine.py (through state.apply_operation) on
a COPY of the data. The original upload is never changed, you can Undo the
last step, and "Reset to original" brings everything back.
"""

import pandas as pd
import streamlit as st

from components import charts, state
from components.metric_cards import metric_row, no_data_message, page_header, pill, report_operation, section
from components.tables import preview_table, show_table
from core import cleaning_engine as ce
from core.data_utils import is_numeric_column, is_text_series
from core.recommendation_engine import analyze_dataset, apply_recommendation
from core.report_generator import build_comparison, history_to_dataframe

DATE_FORMATS = {"2024-03-15  (ISO, recommended)": "%Y-%m-%d", "15/03/2024": "%d/%m/%Y", "03/15/2024": "%m/%d/%Y", "15-Mar-2024": "%d-%b-%Y"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def run(func, *args, **kwargs) -> None:
    """Apply one operation, remember the outcome and refresh the page."""
    info = state.apply_operation(func, *args, **kwargs)
    st.session_state["last_infos"] = [info]
    st.rerun()


def apply_button(label: str, key: str, disabled: bool = False) -> bool:
    return st.button(label, type="primary", key=key, disabled=disabled, icon=":material/play_arrow:")


def pick_columns(label: str, options: list, key: str, default=None, help_text: str | None = None) -> list:
    return st.multiselect(label, options, default=default if default is not None else [], key=key, help=help_text)


# --------------------------------------------------------------------------
# tabs
# --------------------------------------------------------------------------
def tab_smart(df: pd.DataFrame) -> None:
    st.markdown("**Smart Clean** is *rule-based intelligent automation*: it uses fixed rules, Pandas and statistics to find safe, common problems. "
                "It is **not** generative AI and uses no external service. You review every step before anything changes.")
    key = (st.session_state["load_id"], st.session_state["data_version"])
    if st.button("Analyze dataset", type="primary", key="smart_analyze", icon=":material/search:"):
        with st.spinner("Analyzing..."):
            st.session_state["recs"] = analyze_dataset(df, state.settings())
            st.session_state["recs_key"] = key
        st.rerun()

    recs = st.session_state.get("recs")
    if recs is None or st.session_state.get("recs_key") != key:
        st.info("Press **Analyze dataset** to see recommended cleaning steps for the current data.")
        return

    actions = [r for r in recs if r["kind"] == "action"]
    advice = [r for r in recs if r["kind"] == "advisory"]
    if not actions and not advice:
        st.success("Nothing to recommend. The data already looks tidy.")
        return

    section("Recommended steps (safe to automate)")
    if not actions:
        st.success("No automatic steps are needed.")
    selected = []
    for rec in actions:
        with st.container(border=True):
            left, right = st.columns([5, 2])
            with left:
                checked = st.checkbox(rec["title"], value=rec["default_selected"], key=f"rec_{rec['id']}")
                st.caption(rec["description"])
            with right:
                impact = []
                if rec["rows"]:
                    impact.append(f"{rec['rows']:,} row(s)")
                if rec["cells"]:
                    impact.append(f"{rec['cells']:,} cell(s)")
                st.markdown((pill("Review first", "warn") + " " if rec["needs_review"] else "") + pill(", ".join(impact) or "structure", "neutral"), unsafe_allow_html=True)
            if checked:
                selected.append(rec)

    if actions:
        st.markdown(f"**Summary:** {len(selected)} of {len(actions)} step(s) selected.")
        if st.button("Apply selected steps", type="primary", disabled=not selected, key="smart_apply", icon=":material/auto_fix_high:"):
            infos = []
            for index, rec in enumerate(selected):
                infos.append(state.apply_operation(apply_recommendation, rec, push_undo=(index == 0)))
            st.session_state["last_infos"] = infos
            st.rerun()

    if advice:
        section("Needs your decision (never applied automatically)")
        for rec in advice:
            icon = {"high": ":material/error:", "medium": ":material/warning:"}.get(rec.get("severity"), ":material/info:")
            st.markdown(f"{icon} **{rec['title']}**  \n{rec['description']}")


def tab_missing(df: pd.DataFrame) -> None:
    treat_blank = state.settings()["treat_blank_as_missing"]
    summary = ce.missing_summary(df, treat_blank)
    if summary.empty:
        st.success("No missing values were found in the current data.")
        return
    left, right = st.columns([1, 1])
    with left:
        show_table(summary, height=min(360, 60 + 36 * len(summary)), key="missing_summary")
    with right:
        fig = charts.missing_by_column(df, summary)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key="clean_missing_chart")

    mode = st.radio("What do you want to do?", ["Fill missing values", "Remove rows with missing values"], horizontal=True, key="missing_mode")
    columns = pick_columns("Columns to handle", list(summary["column"]), "missing_cols", default=list(summary["column"]))
    kinds = {c: ("number" if is_numeric_column(df[c]) else "text") for c in columns}
    if columns:
        st.caption("Column types: " + ", ".join(f"{c} ({k})" for c, k in kinds.items()))

    if mode == "Fill missing values":
        method = st.selectbox("Method", ["median", "mean", "zero", "mode", "custom"], key="missing_method",
                              help="mean / median / zero work on number columns only. 'mode' (most frequent value) and 'custom' work on any column.")
        custom = None
        if method == "custom":
            custom = st.text_input("Custom value", key="missing_custom")
        text_cols = [c for c, k in kinds.items() if k == "text"]
        if method in ("mean", "median", "zero") and text_cols:
            st.warning("These text columns will be skipped for this method: " + ", ".join(text_cols) + ". Run 'mode' or 'custom' for them.")
        if apply_button("Fill missing values", "missing_apply", disabled=not columns):
            run(ce.fill_missing, columns, method, custom_value=custom, treat_blank_as_missing=treat_blank)
    else:
        how = st.radio("Remove a row if", ["ANY selected column is missing", "ALL selected columns are missing"], key="missing_how")
        st.caption(f"Rows currently containing a missing value in the selected columns will be deleted.")
        if apply_button("Remove rows", "missing_drop", disabled=not columns):
            run(ce.drop_missing_rows, columns, "any" if how.startswith("ANY") else "all", treat_blank_as_missing=treat_blank)


def tab_duplicates(df: pd.DataFrame) -> None:
    subset = pick_columns("Columns that identify a duplicate (leave empty to compare whole rows)", list(df.columns), "dup_cols")
    count = ce.count_duplicates(df, subset or None)
    metric_row([("Duplicate rows", f"{count:,}", "extra copies that would be removed", "warn" if count else "good"),
                ("Rows now", f"{len(df):,}", "", "")])
    if count == 0:
        st.success("No duplicate rows with these settings.")
        return
    keep = st.radio("Which copy to keep?", ["first", "last"], horizontal=True, key="dup_keep")
    with st.expander("Show the rows involved in duplicates"):
        show_table(ce.get_duplicate_rows(df, subset or None).head(500), hide_index=False, height=320, key="dup_rows")
    if apply_button(f"Remove {count:,} duplicate row(s)", "dup_apply"):
        run(ce.remove_duplicates, subset or None, keep)


def tab_text(df: pd.DataFrame) -> None:
    text_cols = [c for c in df.columns if is_text_series(df[c])]
    if not text_cols:
        st.info("The current data has no text columns.")
        return
    section("Clean text")
    columns = pick_columns("Text columns", text_cols, "text_cols")
    operation = st.selectbox("Operation", ["Trim leading/trailing spaces", "Remove repeated spaces", "Convert to lowercase", "Convert to UPPERCASE",
                                           "Convert to Title Case", "Replace text", "Remove unwanted characters", "Replace blank text"], key="text_op")
    old = new = chars = ""
    whole, case = True, True
    if operation == "Replace text":
        c1, c2 = st.columns(2)
        old, new = c1.text_input("Find", key="text_find"), c2.text_input("Replace with", key="text_replace")
        whole = st.checkbox("Match the whole cell only", value=True, key="text_whole")
        case = st.checkbox("Case sensitive", value=True, key="text_case")
    elif operation == "Remove unwanted characters":
        chars = st.text_input("Characters to remove (for example  #$%@!)", key="text_chars")
    elif operation == "Replace blank text":
        new = st.text_input("Replace blanks with (leave empty to mark as missing)", key="text_blank_value")

    if apply_button("Apply to selected columns", "text_apply", disabled=not columns):
        if operation.startswith("Trim"):
            run(ce.trim_spaces, columns)
        elif operation.startswith("Remove repeated"):
            run(ce.collapse_spaces, columns)
        elif operation.endswith("lowercase"):
            run(ce.change_case, columns, "lower")
        elif operation.endswith("UPPERCASE"):
            run(ce.change_case, columns, "upper")
        elif operation.endswith("Title Case"):
            run(ce.change_case, columns, "title")
        elif operation == "Replace text":
            if not old:
                st.error("Enter the text to find.")
            else:
                run(ce.replace_values, columns, old, new, whole_cell=whole, case_sensitive=case)
        elif operation == "Remove unwanted characters":
            if not chars:
                st.error("Enter at least one character to remove.")
            else:
                run(ce.remove_characters, columns, chars)
        else:
            run(ce.replace_blank_text, columns, new or None)

    section("Standardize categories")
    st.caption("Make the same value look the same everywhere (for example Male, male, MALE, M).")
    column = st.selectbox("Column", text_cols, key="cat_col")
    suggestion = ce.suggest_category_groups(df[column])
    base = pd.DataFrame({"found": list(suggestion.keys()), "standardize to": list(suggestion.values())})
    if base.empty:
        st.caption("No spelling variations (case/spacing) were detected in this column. You can still add your own mapping below.")
        base = pd.DataFrame({"found": [""], "standardize to": [""]})
        editor_disabled = []
    else:
        st.caption("Suggested from upper/lower-case and spacing differences. Edit the right-hand column if you prefer another spelling.")
        editor_disabled = ["found"]
    values = df[column].dropna().astype(str).value_counts().head(25)
    with st.expander("Most common values in this column"):
        st.dataframe(values.rename("count").reset_index().rename(columns={column: "value", "index": "value"}), width="stretch", hide_index=True)
    edited = st.data_editor(base, disabled=editor_disabled, hide_index=True, num_rows="dynamic" if not editor_disabled else "fixed",
                            width="stretch", key=f"cat_editor_{column}_{len(suggestion)}")
    mapping = {str(r["found"]): str(r["standardize to"]) for _, r in edited.iterrows()
               if str(r["found"]).strip() != "" and str(r["standardize to"]).strip() != "" and str(r["found"]) != str(r["standardize to"])}
    if apply_button(f"Apply {len(mapping)} replacement(s)", "cat_apply", disabled=not mapping):
        run(ce.standardize_categories, column, mapping)


def tab_names(df: pd.DataFrame) -> None:
    c1, c2, c3 = st.columns(3)
    lower = c1.checkbox("Convert to lowercase", True, key="cn_lower")
    under = c2.checkbox("Replace spaces with underscores", True, key="cn_under")
    special = c3.checkbox("Remove special characters", True, key="cn_special")
    pairs = ce.preview_column_names(df.columns, lower, under, special)
    table = pd.DataFrame(pairs, columns=["current name", "new name"])
    table["changes"] = table["current name"] != table["new name"]
    show_table(table, height=min(420, 60 + 36 * len(table)), key="cn_preview")
    st.caption("If cleaning makes two names identical, a number is added (name, name_2, ...), so no column is lost.")
    changed = int(table["changes"].sum())
    if apply_button(f"Rename {changed} column(s)", "cn_apply", disabled=changed == 0):
        run(ce.clean_column_names, lower, under, special)


def tab_types(df: pd.DataFrame) -> None:
    column = st.selectbox("Column", list(df.columns), key="dt_col")
    st.caption(f"Current type: **{df[column].dtype}**. Example values: " + ", ".join(f"`{v}`" for v in df[column].dropna().astype(str).head(3)))
    target = st.selectbox("Convert to", list(ce.TARGET_TYPES), key="dt_target")
    c1, c2 = st.columns(2)
    on_error = c1.radio("If some values cannot be converted", ["Stop and show me the problem values", "Set those values to missing"], key="dt_error")
    clean_symbols = dayfirst = False
    fmt = ""
    if target in ("integer", "float"):
        clean_symbols = c2.checkbox("Ignore currency signs, commas and spaces (Rs, $, 1,200)", key="dt_symbols")
    if target in ("date", "datetime"):
        dayfirst = c2.checkbox("Day comes before month (05/06/2024 = 5 June)", value=state.settings()["dayfirst"], key="dt_dayfirst")
        fmt = c2.text_input("Exact format (optional, e.g. %d/%m/%Y)", key="dt_format")
    if apply_button("Convert column", "dt_apply"):
        run(ce.convert_column_type, column, target, on_error="abort" if on_error.startswith("Stop") else "set_missing",
            dayfirst=dayfirst, date_format=fmt.strip() or None, clean_symbols=clean_symbols)


def tab_outliers(df: pd.DataFrame) -> None:
    numeric = [c for c in df.columns if is_numeric_column(df[c])]
    if not numeric:
        st.info("The current data has no numeric columns.")
        return
    cfg = state.settings()
    method_label = st.radio("Detection method", ["IQR (recommended)", "Z-score"], horizontal=True, key="out_method")
    method = "iqr" if method_label.startswith("IQR") else "zscore"
    if method == "iqr":
        parameter = st.slider("IQR multiplier", 1.0, 3.0, float(cfg["iqr_multiplier"]), 0.1, key="out_iqr",
                              help="Values below Q1 - k x IQR or above Q3 + k x IQR are outliers. 1.5 is the usual choice.")
    else:
        parameter = st.slider("Z-score threshold", 2.0, 4.0, float(cfg["zscore_threshold"]), 0.1, key="out_z",
                              help="Values more than this many standard deviations from the mean are outliers. Works best with 30+ values.")
    report = ce.outlier_report(df, numeric, method, parameter)
    show_table(report, height=min(300, 60 + 36 * len(report)), key="out_report")
    column = st.selectbox("Review a column", numeric, key="out_col")
    mask, low, high = (ce.detect_outliers_zscore(df[column], parameter) if method == "zscore" else ce.detect_outliers_iqr(df[column], parameter))
    if low is None:
        st.info("Not enough data (or no variation) to detect outliers in this column.")
        return
    fig = charts.numeric_distribution(df, column, low, high)
    if fig is not None:
        st.plotly_chart(fig, width="stretch", key="out_chart")
    st.markdown(f"Acceptable range: **{low:,.2f}** to **{high:,.2f}**  -  **{int(mask.sum())}** outlier(s) found.")
    if mask.any():
        st.markdown("**Review these rows before changing anything:**")
        show_table(df[mask].head(200), hide_index=False, height=min(320, 60 + 36 * int(min(mask.sum(), 8))), key="out_rows")
        action = st.radio("Action", ["Cap (limit to the range above)", "Remove the rows"], key="out_action")
        reviewed = st.checkbox("I have reviewed these outliers and want to apply this action.", key="out_confirm")
        if apply_button("Apply", "out_apply", disabled=not reviewed):
            run(ce.handle_outliers, column, method, parameter, "cap" if action.startswith("Cap") else "remove")
    else:
        st.success("No outliers in this column with these settings.")


def tab_standardize(df: pd.DataFrame) -> None:
    section("Dates")
    st.caption("Rewrite a date column so every date has the same format.")
    column = st.selectbox("Date column", list(df.columns), key="sd_date_col")
    c1, c2, c3 = st.columns(3)
    out_label = c1.selectbox("Output format", list(DATE_FORMATS), key="sd_date_fmt")
    dayfirst = c2.checkbox("Day before month in the input", value=state.settings()["dayfirst"], key="sd_dayfirst")
    stop = c3.radio("Unreadable dates", ["Stop", "Set to missing"], key="sd_date_error", horizontal=True)
    if apply_button("Standardize dates", "sd_date_apply"):
        run(ce.standardize_dates, column, DATE_FORMATS[out_label], dayfirst=dayfirst, on_error="abort" if stop == "Stop" else "set_missing")

    section("Numbers stored as text")
    st.caption("Read values like 'Rs 1,200' or '$45' as real numbers.")
    text_cols = [c for c in df.columns if is_text_series(df[c])]
    if text_cols:
        n1, n2, n3 = st.columns(3)
        ncol = n1.selectbox("Column", text_cols, key="sd_num_col")
        decimals = n2.number_input("Round to decimals (-1 = do not round)", -1, 8, -1, key="sd_num_dec")
        stop_n = n3.radio("Unreadable values", ["Stop", "Set to missing"], key="sd_num_error", horizontal=True)
        if apply_button("Standardize numbers", "sd_num_apply"):
            run(ce.standardize_numeric, ncol, None if decimals < 0 else int(decimals), True, "abort" if stop_n == "Stop" else "set_missing")
    else:
        st.caption("No text columns.")

    section("Scale numeric columns")
    st.caption("Adds NEW columns with scaled values; your original columns stay unchanged.")
    numeric = [c for c in df.columns if is_numeric_column(df[c])]
    if numeric:
        cols = pick_columns("Numeric columns", numeric, "sd_scale_cols")
        method = st.radio("Method", ["minmax (0 to 1)", "zscore (mean 0, std 1)"], horizontal=True, key="sd_scale_method")
        if apply_button("Add scaled columns", "sd_scale_apply", disabled=not cols):
            run(ce.normalize_numeric, cols, "minmax" if method.startswith("minmax") else "zscore")
    else:
        st.caption("No numeric columns.")
    st.caption("Text case and category spelling are standardized in the **Text** tab.")


def tab_rules(df: pd.DataFrame) -> None:
    st.caption("Build your own cleaning rules, add them to the list, then apply them all in order.")
    queue = st.session_state.setdefault("rule_queue", [])
    labels = {key: spec["label"] for key, spec in ce.RULE_OPERATIONS.items()}
    c1, c2 = st.columns(2)
    column = c1.selectbox("Column", list(df.columns), key="rule_col")
    operation = c2.selectbox("Operation", list(labels), format_func=lambda k: labels[k], key="rule_op")
    spec = ce.RULE_OPERATIONS[operation]
    value = value2 = None
    v1, v2 = st.columns(2)
    if spec.get("choices"):
        value = v1.selectbox(spec["value_label"], spec["choices"], key=f"rule_val_{operation}")
    elif spec["value_label"]:
        value = v1.text_input(spec["value_label"], key=f"rule_val_{operation}")
    if spec["value2_label"]:
        value2 = v2.text_input(spec["value2_label"], key=f"rule_val2_{operation}")
    if st.button("Add rule to the list", key="rule_add", icon=":material/add:"):
        if spec["needs_value"] and not (value or "").strip():
            st.error(f"'{spec['value_label']}' is required for this operation.")
        elif spec["needs_value2"] and value2 is None:
            st.error(f"'{spec['value2_label']}' is required for this operation.")
        else:
            queue.append({"column": column, "operation": operation, "value": value, "value2": value2})
            st.rerun()

    if queue:
        section("Rules to apply")
        for index, rule in enumerate(queue):
            r1, r2 = st.columns([8, 1])
            extras = ", ".join(str(x) for x in (rule["value"], rule["value2"]) if x not in (None, ""))
            r1.markdown(f"**{index + 1}.** {labels[rule['operation']]} on **{rule['column']}**" + (f"  -  `{extras}`" if extras else ""))
            if r2.button("Remove", key=f"rule_rm_{index}"):
                queue.pop(index)
                st.rerun()
        a, b = st.columns([1, 1])
        if a.button("Apply all rules", type="primary", key="rule_apply", icon=":material/play_arrow:"):
            infos = [state.apply_operation(ce.apply_rule, dict(rule), push_undo=(i == 0)) for i, rule in enumerate(queue)]
            st.session_state["rule_queue"] = []
            st.session_state["last_infos"] = infos
            st.rerun()
        if b.button("Clear the list", key="rule_clear"):
            st.session_state["rule_queue"] = []
            st.rerun()
    else:
        st.info("No rules in the list yet.")


def tab_history(df: pd.DataFrame) -> None:
    history = st.session_state["history"]
    st.caption("History is kept **for this browser session only**. It disappears when you refresh, close the tab or the session times out. "
               "Download it from the Reports page if you need a permanent record.")
    if history:
        show_table(history_to_dataframe(history), height=min(420, 60 + 36 * len(history)), key="hist_table")
    else:
        st.info("No cleaning steps have been recorded yet.")

    section("Original vs current data")
    original_score, current_score = state.get_scores()
    comparison = build_comparison(state.original(), df, original_score, current_score)
    show_table(comparison, height=40 + 36 * len(comparison), key="hist_compare")
    c1, c2 = charts.before_after(comparison)
    left, right = st.columns(2)
    if c1 is not None:
        left.plotly_chart(c1, width="stretch", key="hist_chart_counts")
    if c2 is not None:
        right.plotly_chart(c2, width="stretch", key="hist_chart_scores")
    t1, t2 = st.tabs(["Original (as uploaded)", "Current (cleaned)"])
    with t1:
        preview_table(state.original(), state.settings()["preview_rows"], key="hist_prev_orig")
    with t2:
        preview_table(df, state.settings()["preview_rows"], key="hist_prev_cur")


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------
def render() -> None:
    page_header("Data Cleaning", "Fix problems step by step. Your original upload is never changed.")
    if not state.has_data():
        no_data_message()
        return

    for info in st.session_state.pop("last_infos", []) or []:
        report_operation(info)

    df = state.working()
    top = st.columns([1, 1, 1, 3])
    top[0].metric("Rows", f"{len(df):,}")
    top[1].metric("Columns", f"{df.shape[1]:,}")
    if top[2].button("Undo last step", disabled=not state.can_undo(), key="undo_btn", icon=":material/undo:"):
        state.undo_last()
        st.session_state["last_infos"] = [{"operation": "Undo last step", "status": "applied", "rows_before": len(df), "rows_after": len(state.working())}]
        st.rerun()
    if top[3].button("Reset to original data", disabled=not state.is_modified(), key="reset_btn", icon=":material/restart_alt:"):
        state.reset_to_original()
        st.session_state["last_infos"] = [{"operation": "Reset to original data", "status": "applied", "rows_before": len(df), "rows_after": len(state.working())}]
        st.rerun()

    tabs = st.tabs(["Smart Clean", "Missing values", "Duplicates", "Text", "Column names", "Data types",
                    "Outliers", "Standardization", "Custom rules", "History and compare"])
    handlers = [tab_smart, tab_missing, tab_duplicates, tab_text, tab_names, tab_types, tab_outliers, tab_standardize, tab_rules, tab_history]
    for tab, handler in zip(tabs, handlers):
        with tab:
            handler(df)


render()
