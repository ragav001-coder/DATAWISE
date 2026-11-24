"""metric_cards.py - small reusable UI pieces: metric cards, headers, messages."""

from __future__ import annotations

import html

import streamlit as st

from components.styling import logo_html


def _e(value) -> str:
    return html.escape(str(value))


def metric_card(label: str, value, help_text: str = "", tone: str = "") -> str:
    """HTML of one card. tone: '', 'good', 'warn', 'bad' or 'accent'."""
    extra = f'<div class="dw-card-help">{_e(help_text)}</div>' if help_text else ""
    return (f'<div class="dw-card {tone}"><div class="dw-card-label">{_e(label)}</div>'
            f'<div class="dw-card-value">{_e(value)}</div>{extra}</div>')


def metric_row(items: list[tuple]) -> None:
    """items: [(label, value, help_text, tone), ...] shown side by side."""
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        label, value, help_text, tone = (list(item) + ["", ""])[:4]
        column.markdown(metric_card(label, value, help_text, tone), unsafe_allow_html=True)


def pill(text: str, tone: str = "neutral") -> str:
    return f'<span class="dw-pill {tone}">{_e(text)}</span>'


def page_header(title: str, subtitle: str = "", show_logo: bool = False) -> None:
    """Page title. show_logo=True adds the DIT logo on the right (dashboard only)."""
    logo = f'<div style="flex:0 0 auto">{logo_html(190)}</div>' if show_logo else ""
    st.markdown(
        f'<div class="dw-header"><div><h1 class="dw-title">{_e(title)}</h1>'
        f'<p class="dw-subtitle">{_e(subtitle)}</p></div>{logo}</div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    st.markdown(f'<div class="dw-section">{_e(title)}</div>', unsafe_allow_html=True)


def tone_for_score(score) -> str:
    if score is None:
        return ""
    return "good" if score >= 90 else ("accent" if score >= 75 else ("warn" if score >= 50 else "bad"))


def no_data_message() -> None:
    """Shown by every page that needs a dataset."""
    st.info("No dataset is loaded yet. Open **Data Upload** in the sidebar to upload a file or load a sample dataset.")
    st.page_link("pages/data_upload.py", label="Go to Data Upload", icon=":material/upload_file:")


def report_operation(info: dict) -> None:
    """Show the outcome of a cleaning operation as a success / warning / error message."""
    name = info.get("operation", "Operation")
    for item in info.get("skipped", []):
        st.warning(f"Skipped **{item['column']}**: {item['reason']}.")
    status = info.get("status")
    if status == "applied":
        parts = []
        if info.get("rows_before") != info.get("rows_after"):
            parts.append(f"rows {info['rows_before']:,} -> {info['rows_after']:,}")
        if info.get("cells_changed"):
            parts.append(f"{info['cells_changed']:,} cell(s) changed")
        if info.get("columns_renamed"):
            parts.append(f"{info['columns_renamed']} column(s) renamed")
        st.success(f"{name}: applied" + (f" ({', '.join(parts)})." if parts else "."))
    elif status == "blocked":
        st.error(f"{name}: not applied. " + " ".join(info.get("notes", [])))
        errors = info.get("errors") or []
        if errors:
            import pandas as pd
            st.caption(f"Values that caused the problem ({info.get('error_count', len(errors))} in total, first {len(errors)} shown):")
            st.dataframe(pd.DataFrame(errors), width="stretch", hide_index=True, height=min(240, 40 + 35 * len(errors)))
    else:
        st.info(f"{name}: nothing to change with these settings." + (" " + " ".join(info.get("notes", [])) if info.get("notes") else ""))
    for note in info.get("notes", []):
        if status == "applied":
            st.caption(note)
