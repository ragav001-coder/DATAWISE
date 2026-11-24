"""data_validation.py - Module 5 (Data Validation Engine): choose rules, run them, inspect every problem."""

import streamlit as st

from components import charts, state
from components.metric_cards import metric_row, no_data_message, page_header, pill, section
from components.tables import show_table
from core.file_handler import dataframe_to_csv_bytes
from core.report_generator import validation_report_excel_bytes
from core.validation_engine import RULE_CATALOG, describe_rule, make_rule, suggest_rules, validate


def _rule_form(df) -> None:
    section("1. Choose a rule")
    labels = {key: spec["label"] for key, spec in RULE_CATALOG.items()}
    key = st.selectbox("Rule type", list(labels), format_func=lambda k: labels[k], key="val_rule_type")
    spec = RULE_CATALOG[key]
    st.caption(spec["description"])

    if key == "required_columns":
        options = list(df.columns)
        columns = st.multiselect("Columns that must exist", options, key="val_cols_required",
                                 help="Pick columns from the list, or type a name that should exist.", accept_new_options=True)
    elif key == "duplicates":
        columns = st.multiselect("Columns to compare (leave empty for whole rows)", list(df.columns), key="val_cols_dup")
    else:
        columns = st.multiselect("Columns to check", list(df.columns), key=f"val_cols_{key}")

    params = {}
    cols = st.columns(max(1, min(3, len(spec["params"])))) if spec["params"] else []
    for index, p in enumerate(spec["params"]):
        holder = cols[index % len(cols)]
        wkey = f"val_param_{key}_{p['name']}"
        if p["type"] == "int":
            params[p["name"]] = int(holder.number_input(p["label"], value=int(p["default"]), step=1, key=wkey))
        elif p["type"] == "float":
            text = holder.text_input(p["label"], value="" if p["default"] is None else str(p["default"]), key=wkey)
            try:
                params[p["name"]] = float(text) if text.strip() else None
            except ValueError:
                params[p["name"]] = None
                holder.error("Enter a number.")
        elif p["type"] == "bool":
            default = state.settings()["dayfirst"] if p["name"] == "dayfirst" else bool(p["default"])
            params[p["name"]] = holder.checkbox(p["label"], value=default, key=wkey)
        else:
            params[p["name"]] = holder.text_input(p["label"], value=str(p["default"] or ""), key=wkey)

    if st.button("Add rule", key="val_add", icon=":material/add:"):
        error = None
        if key not in ("duplicates",) and not columns:
            error = "Select at least one column."
        elif key == "allowed_values" and not params.get("values", "").strip():
            error = "Enter the allowed values."
        elif key == "regex" and not params.get("pattern", "").strip():
            error = "Enter a pattern."
        elif key == "range" and params.get("min") is None and params.get("max") is None:
            error = "Enter a minimum, a maximum, or both."
        if error:
            st.error(error)
        else:
            st.session_state["validation_rules"].append(make_rule(key, columns, **params))
            st.rerun()


def render() -> None:
    page_header("Data Validation", "Check the current data against rules you choose. Validation only reports problems; it never changes your data.")
    if not state.has_data():
        no_data_message()
        return

    df = state.working()
    rules = st.session_state["validation_rules"]

    left, right = st.columns([3, 2], gap="large")
    with left:
        _rule_form(df)
    with right:
        section("2. Your rules")
        if st.button("Suggest rules for my data", key="val_suggest", icon=":material/lightbulb:",
                     help="Rule-based suggestions from column names and contents. You can remove any of them."):
            cfg = state.settings()
            for rule in suggest_rules(df, cfg["phone_min_digits"], cfg["phone_max_digits"]):
                if rule not in rules:
                    rules.append(rule)
            st.rerun()
        if not rules:
            st.info("No rules yet. Add a rule on the left or press **Suggest rules**.")
        for index, rule in enumerate(rules):
            r1, r2 = st.columns([6, 1])
            r1.markdown(f"**{index + 1}.** {describe_rule(rule)}")
            if r2.button("X", key=f"val_rm_{index}", help="Remove this rule"):
                rules.pop(index)
                st.rerun()
        if rules and st.button("Remove all rules", key="val_clear"):
            st.session_state["validation_rules"] = []
            st.rerun()

    st.markdown("---")
    if st.button("Run validation", type="primary", disabled=not rules, key="val_run", icon=":material/play_arrow:"):
        with st.spinner("Validating..."):
            state.store_validation(validate(df, rules), rules)
        st.rerun()

    result = st.session_state.get("validation_result")
    if result is None:
        st.info("Add at least one rule, then press **Run validation**.")
    else:
        meta = st.session_state["validation_meta"]
        if not state.validation_is_current():
            st.warning("The data has changed since this validation ran. Press **Run validation** again to refresh the results.")
        st.caption(f"Result from {meta['time']} using {len(meta['rules'])} rule(s).")
        pct = "n/a" if result.validity_pct is None else f"{result.validity_pct}%"
        metric_row([("Records checked", f"{result.total_rows:,}", "", ""), ("Valid records", f"{result.valid_rows:,}", "pass every rule", "good"),
                    ("Invalid records", f"{result.invalid_rows:,}", "fail at least one rule", "bad" if result.invalid_rows else "good"),
                    ("Validation %", pct, "records passing all rules", "accent")])
        for note in result.notes:
            st.warning(note)
        for issue in result.schema_issues:
            st.error(issue)

        c1, c2 = st.columns([3, 2])
        with c1:
            section("Result by rule and column")
            show_table(result.summary.rename(columns={"passed_pct": "pass %"}), height=min(340, 60 + 36 * len(result.summary)), key="val_summary")
        with c2:
            fig = charts.valid_vs_invalid(result.valid_rows, result.invalid_rows)
            if fig is not None:
                st.plotly_chart(fig, width="stretch", key="val_chart")

        section("Row-level issues")
        if result.issues.empty:
            st.success("No issues were found. Every checked value passed.")
        else:
            f1, f2 = st.columns(2)
            rule_filter = f1.multiselect("Filter by rule", sorted(result.issues["rule"].unique()), key="val_f_rule")
            col_filter = f2.multiselect("Filter by column", sorted(result.issues["column"].unique()), key="val_f_col")
            shown = result.issues
            if rule_filter:
                shown = shown[shown["rule"].isin(rule_filter)]
            if col_filter:
                shown = shown[shown["column"].isin(col_filter)]
            show_table(shown.rename(columns={"row": "row number", "error": "problem"}), height=380, key="val_issues")
            st.caption(f"{len(shown):,} issue(s) shown. Row numbers start at 1 and keep their original number even after rows were deleted.")
            d1, d2 = st.columns(2)
            d1.download_button("Download issues (CSV)", dataframe_to_csv_bytes(result.issues), "datawise_validation_issues.csv", "text/csv", key="val_dl_csv", width="stretch")
            d2.download_button("Download validation report (Excel)", validation_report_excel_bytes(result, meta["rules"], st.session_state["file_name"]),
                               "datawise_validation_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="val_dl_xlsx", width="stretch")

    with st.expander("Limitations of validation (please read)"):
        st.markdown(
            "- **Phone numbers** are written differently in every country. The phone rule checks allowed characters and the number of digits "
            "(default 7-15). It cannot know whether a number really exists. Set your own digit range or use a custom pattern for a specific country.\n"
            "- **Dates** such as 05/06/2024 can mean 5 June or 6 May. Choose 'day comes before month' to match your data, or give an exact format.\n"
            "- **Email** validation checks the format only. It does not check that the mailbox exists.\n"
            "- Empty cells are ignored by format rules; use *Required value* to demand a value.\n"
            "- A custom pattern is a regular expression matched against the whole value.")


render()
