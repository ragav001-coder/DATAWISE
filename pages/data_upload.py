"""
data_upload.py - Module 2 (Data Upload) and Module 11 (Sample Dataset Library).

The uploaded file is read from memory (never saved to disk, never executed)
and stored in st.session_state. Nothing is replaced until you press
"Load this dataset", so a stray upload cannot overwrite your work.
"""

import hashlib

import streamlit as st

from components import state
from components.metric_cards import metric_row, page_header, section
from components.styling import PROJECT_ROOT
from components.tables import dtype_table, preview_table
from core.data_utils import format_bytes
from core.file_handler import MAX_FILE_MB, FileReadError, read_uploaded_file

SAMPLES = {
    "customers_messy.csv": ("Customers", "Names with extra spaces, wrong capitals, invalid emails and phones, mixed date formats, missing values and duplicate rows."),
    "sales_messy.csv": ("Sales orders", "Prices written as 'Rs 1,200' or '$45', inconsistent categories, impossible dates, negative quantities and duplicates."),
    "employees_messy.csv": ("Employees", "Salaries as text, department spelling variations, invalid emails and phones, bad dates and duplicates."),
}


def _load_sample(file_name: str) -> None:
    path = PROJECT_ROOT / "sample_data" / file_name
    try:
        data = path.read_bytes()
        df = read_uploaded_file(data, file_name)
    except (OSError, FileReadError) as exc:
        st.error(f"The sample file could not be loaded: {exc}")
        return
    state.set_dataset(df, file_name, len(data), "sample")
    st.session_state["flash"] = f"Sample dataset '{file_name}' loaded."
    st.rerun()


def render() -> None:
    page_header("Data Upload", "Upload a CSV, Excel (.xlsx) or JSON file, or start with a sample dataset.")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    st.warning("**Privacy:** this app may be running on a public server. Do not upload confidential or highly sensitive personal data. "
               "Files are processed in memory for your session only and are not stored by DATAWISE.")

    # ------------------------------------------------------------------ upload
    uploaded = st.file_uploader(
        "Choose a file", type=["csv", "xlsx", "json"], accept_multiple_files=False,
        help=f"Supported: CSV, XLSX, JSON. Maximum size {MAX_FILE_MB} MB.",
    )

    if uploaded is not None:
        data = uploaded.getvalue()
        signature = (uploaded.name, len(data), hashlib.md5(data).hexdigest())  # only to detect "same file again"
        cache = st.session_state["upload_cache"]
        if cache.get("signature") != signature:
            try:
                with st.spinner("Reading file..."):
                    df = read_uploaded_file(data, uploaded.name)
                cache.clear()
                cache.update({"signature": signature, "df": df, "name": uploaded.name, "size": len(data), "error": None})
            except FileReadError as exc:
                cache.clear()
                cache.update({"signature": signature, "df": None, "name": uploaded.name, "size": len(data), "error": str(exc)})
            except Exception:  # noqa: BLE001 - never show internal errors to the user
                cache.clear()
                cache.update({"signature": signature, "df": None, "name": uploaded.name, "size": len(data),
                              "error": "An unexpected problem occurred while reading this file. Please check that it is a valid CSV, XLSX or JSON file."})

        if cache.get("error"):
            st.error(f"**{uploaded.name}** could not be loaded. {cache['error']}")
        else:
            df = cache["df"]
            section("File ready to load")
            metric_row([("File name", cache["name"], "", ""), ("File size", format_bytes(cache["size"]), "", ""),
                        ("Rows", f"{df.shape[0]:,}", "", ""), ("Columns", f"{df.shape[1]:,}", "", "")])
            if state.has_data():
                st.info("Loading this file will **replace** the current dataset and clear its cleaning history.")
            if st.button("Load this dataset", type="primary", icon=":material/check_circle:", key="load_uploaded"):
                state.set_dataset(df, cache["name"], cache["size"], "upload")
                st.session_state["upload_cache"] = {}
                st.session_state["flash"] = f"'{cache['name']}' loaded: {df.shape[0]:,} rows and {df.shape[1]:,} columns."
                st.rerun()
            tab_a, tab_b = st.tabs(["Preview", "Data types"])
            with tab_a:
                preview_table(df, state.settings()["preview_rows"], key="upload_preview")
            with tab_b:
                st.dataframe(dtype_table(df), width="stretch", hide_index=True)

    # ----------------------------------------------------------- current data
    if state.has_data():
        df = state.original()
        section("Loaded dataset")
        source = "Sample data (fictional)" if st.session_state["source"] == "sample" else "Your upload"
        metric_row([("File name", st.session_state["file_name"], source, ""),
                    ("File size", format_bytes(st.session_state["file_size"] or 0), "", ""),
                    ("Rows", f"{df.shape[0]:,}", "original upload", ""), ("Columns", f"{df.shape[1]:,}", "original upload", "")])
        tab_a, tab_b = st.tabs(["Preview of uploaded data", "Data types"])
        with tab_a:
            preview_table(df, state.settings()["preview_rows"], key="loaded_preview")
        with tab_b:
            st.dataframe(dtype_table(df), width="stretch", hide_index=True)
        if state.is_modified():
            st.caption("The preview shows the ORIGINAL upload. Cleaned data is on the Data Cleaning page.")
        left, right, _ = st.columns([1, 1, 3])
        left.page_link("pages/data_profiling.py", label="Profile this data", icon=":material/query_stats:")
        right.page_link("pages/data_cleaning.py", label="Clean this data", icon=":material/cleaning_services:")
        if st.button("Remove dataset and start over", icon=":material/delete:", key="remove_dataset"):
            state.clear_dataset()
            st.rerun()

    # ----------------------------------------------------------------- samples
    section("Sample dataset library")
    st.caption("Intentionally messy, **fictional** data for testing. It does not describe any real person or company.")
    columns = st.columns(len(SAMPLES))
    for column, (file_name, (title, text)) in zip(columns, SAMPLES.items()):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}** <span class='dw-demo-tag'>SAMPLE</span>", unsafe_allow_html=True)
                st.caption(text)
                if st.button(f"Load {title.lower()} sample", key=f"sample_{file_name}", width="stretch"):
                    _load_sample(file_name)


render()
