"""
charts.py - Plotly charts. Every function takes REAL data and returns a figure,
or None when there is not enough data (so the page can say so instead of
drawing a misleading chart).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from components.styling import AMBER, BLUE, GREEN, INK, PALETTE, PURPLE, RED, SLATE
from core.data_utils import is_numeric_column
from core.profiler import dtype_distribution

_LAYOUT = dict(
    template="plotly_white",
    font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color=INK),
    margin=dict(l=10, r=10, t=44, b=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
)


def _style(fig: go.Figure, title: str, height: int = 320) -> go.Figure:
    fig.update_layout(title=dict(text=title, x=0.0, font=dict(size=15)), height=height, **_LAYOUT)
    return fig


def _donut(labels, values, colors, title, center_text: str = "") -> go.Figure:
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.62, marker=dict(colors=colors, line=dict(color="#fff", width=2)),
                           textinfo="percent", sort=False, hovertemplate="%{label}: %{value:,} (%{percent})<extra></extra>"))
    if center_text:
        fig.add_annotation(text=center_text, x=0.5, y=0.5, showarrow=False, font=dict(size=20, color=INK))
    return _style(fig, title)


def missing_by_column(df: pd.DataFrame, summary: pd.DataFrame, key_title: str = "Missing values by column") -> go.Figure | None:
    """summary comes from cleaning_engine.missing_summary()."""
    if summary is None or summary.empty:
        return None
    data = summary.sort_values("missing", ascending=True).tail(20)
    fig = go.Figure(go.Bar(x=data["missing"], y=data["column"], orientation="h", marker_color=AMBER,
                           customdata=data["missing_pct"], hovertemplate="%{y}: %{x:,} missing (%{customdata}%)<extra></extra>"))
    fig.update_xaxes(title="Missing or blank cells")
    return _style(fig, key_title, height=max(260, 40 + 28 * len(data)))


def dtype_chart(df: pd.DataFrame) -> go.Figure | None:
    table = dtype_distribution(df)
    if table.empty:
        return None
    return _donut(table["type"], table["columns"], PALETTE[: len(table)], "Column data types", f"{int(table['columns'].sum())}<br><span style='font-size:12px;color:#64748b'>columns</span>")


def valid_vs_invalid(valid: int, invalid: int) -> go.Figure | None:
    if valid + invalid == 0:
        return None
    return _donut(["Valid records", "Invalid records"], [valid, invalid], [GREEN, RED], "Valid vs invalid records",
                  f"{100 * valid / (valid + invalid):.0f}%<br><span style='font-size:12px;color:#64748b'>valid</span>")


def duplicate_vs_unique(duplicates: int, rows: int) -> go.Figure | None:
    if rows == 0:
        return None
    return _donut(["Unique rows", "Duplicate rows"], [rows - duplicates, duplicates], [BLUE, AMBER], "Duplicate vs unique rows",
                  f"{duplicates:,}<br><span style='font-size:12px;color:#64748b'>duplicates</span>")


def score_breakdown(score: dict) -> go.Figure | None:
    cats = [(c["label"], c["score"]) for c in score.get("categories", {}).values() if c["score"] is not None]
    if not cats:
        return None
    labels = [c[0] for c in cats]
    values = [c[1] for c in cats]
    colors = [GREEN if v >= 90 else (BLUE if v >= 75 else (AMBER if v >= 50 else RED)) for v in values]
    fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=colors, text=[f"{v:.1f}" for v in values],
                           textposition="outside", hovertemplate="%{y}: %{x:.1f}<extra></extra>"))
    fig.update_xaxes(range=[0, 108], title="Score (0-100)")
    fig.update_yaxes(autorange="reversed")
    return _style(fig, "Quality score by category", height=max(240, 60 + 55 * len(cats)))


def score_gauge(value: float | None, title: str = "Data quality score") -> go.Figure | None:
    if value is None:
        return None
    bar = GREEN if value >= 90 else (BLUE if value >= 75 else (AMBER if value >= 50 else RED))
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number=dict(font=dict(size=44, color=INK)),
        gauge=dict(axis=dict(range=[0, 100], tickwidth=1), bar=dict(color=bar, thickness=0.3), bgcolor="#f1f5f9", borderwidth=0,
                   steps=[dict(range=[0, 50], color="#fee2e2"), dict(range=[50, 75], color="#fef3c7"),
                          dict(range=[75, 90], color="#dbeafe"), dict(range=[90, 100], color="#dcfce7")]),
    ))
    fig.update_layout(title=dict(text=title, x=0.0, font=dict(size=15)), height=260, **{k: v for k, v in _LAYOUT.items() if k != "legend"})
    return fig


def before_after(comparison: pd.DataFrame) -> tuple[go.Figure | None, go.Figure | None]:
    """Two figures: counts (rows, missing, duplicates) and scores."""
    table = comparison.set_index("metric")

    def grouped(names, title, axis_title, height):
        rows = [n for n in names if n in table.index and pd.notna(table.loc[n, "before"]) and pd.notna(table.loc[n, "after"])]
        if not rows:
            return None
        fig = go.Figure()
        fig.add_bar(name="Before", x=rows, y=[float(table.loc[n, "before"]) for n in rows], marker_color=SLATE)
        fig.add_bar(name="After", x=rows, y=[float(table.loc[n, "after"]) for n in rows], marker_color=PURPLE)
        fig.update_layout(barmode="group")
        fig.update_yaxes(title=axis_title)
        return _style(fig, title, height)

    counts = grouped(["Rows", "Missing or blank cells", "Duplicate rows"], "Before vs after: data size and problems", "Count", 320)
    scores = grouped(["Quality score (0-100)", "Completeness", "Validity", "Uniqueness", "Consistency"], "Before vs after: quality scores", "Score", 320)
    return counts, scores


def numeric_distribution(df: pd.DataFrame, column: str, lower=None, upper=None) -> go.Figure | None:
    if column not in df.columns or not is_numeric_column(df[column]):
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(values) < 2:
        return None
    fig = go.Figure(go.Box(x=values, name=column, boxpoints="outliers", marker_color=BLUE, line_color=PURPLE,
                           hovertemplate="%{x}<extra></extra>"))
    for bound, label in ((lower, "lower bound"), (upper, "upper bound")):
        if bound is not None:
            fig.add_vline(x=bound, line_dash="dash", line_color=RED, annotation_text=label, annotation_position="top")
    fig.update_yaxes(showticklabels=False)
    return _style(fig, f"Distribution of {column}", height=260)


def histogram(df: pd.DataFrame, column: str) -> go.Figure | None:
    if column not in df.columns or not is_numeric_column(df[column]):
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(values) < 2:
        return None
    fig = go.Figure(go.Histogram(x=values, marker_color=BLUE, nbinsx=30))
    fig.update_xaxes(title=column)
    fig.update_yaxes(title="Count")
    return _style(fig, f"Histogram of {column}", height=300)


def top_values(df: pd.DataFrame, column: str, top: int = 10) -> go.Figure | None:
    if column not in df.columns:
        return None
    series = df[column].dropna()
    series = series[series.astype(str).str.strip() != ""]
    if series.empty:
        return None
    counts = series.astype(str).value_counts().head(top).sort_values()
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h", marker_color=PURPLE))
    fig.update_xaxes(title="Count")
    return _style(fig, f"Most common values in {column}", height=max(240, 60 + 28 * len(counts)))
