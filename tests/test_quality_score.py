"""Tests for the data quality score, profiler, Smart Clean engine and reports."""

import json

import numpy as np
import pandas as pd
import pytest

from core.data_utils import blank_mask, parse_dates_flexible, parse_numeric_series
from core.file_handler import read_uploaded_file
from core.profiler import overall_profile, profile_dataframe
from core.quality_score import compute_quality_score, consistency_issues, grade_for
from core.recommendation_engine import analyze_dataset, apply_recommendations
from core.report_generator import (
    build_comparison,
    build_html_report,
    history_to_csv_bytes,
    history_to_dataframe,
    history_to_json_bytes,
    quality_report_excel_bytes,
    validation_report_excel_bytes,
)
from core.validation_engine import make_rule, validate


@pytest.fixture
def perfect():
    return pd.DataFrame({"id": [1, 2, 3, 4], "name": ["Ann", "Bob", "Cy", "Di"], "score": [1.5, 2.5, 3.5, 4.5]})


@pytest.fixture
def messy():
    return pd.DataFrame({
        "Name": [" Ann ", "ann", "BOB", "BOB", None, "  "],
        "Email": ["ann@example.com", "bad@", "bob@example.com", "bob@example.com", "", "c@example.com"],
        "Qty": [1, 2, 2, 2, -1, 3],
        "Date": ["2024-01-05", "05/01/2024", "2024-01-07", "2024-01-07", "2024-01-08", "2024-01-09"],
    })


# ------------------------------------------------------------------ score
def test_perfect_dataset_scores_100(perfect):
    score = compute_quality_score(perfect)
    assert score["overall"] == 100.0 and score["grade"] == "Excellent"
    assert score["categories"]["completeness"]["score"] == 100.0
    assert score["categories"]["uniqueness"]["score"] == 100.0
    assert score["categories"]["validity"]["score"] is None      # nothing to validate
    assert score["categories"]["consistency"]["score"] == 100.0


def test_completeness_and_uniqueness_formulas():
    df = pd.DataFrame({"a": [1, 1, None, 4], "b": ["x", "x", "y", ""]})
    score = compute_quality_score(df)
    assert score["categories"]["completeness"]["score"] == pytest.approx(75.0)  # 2 of 8 cells blank
    assert score["categories"]["uniqueness"]["score"] == pytest.approx(75.0)    # 1 duplicate of 4 rows


def test_score_is_weighted_average_of_categories(messy):
    score = compute_quality_score(messy)
    cats = {k: v["score"] for k, v in score["categories"].items() if v["score"] is not None}
    weights = {"completeness": .3, "validity": .3, "uniqueness": .2, "consistency": .2}
    expected = sum(cats[k] * weights[k] for k in cats) / sum(weights[k] for k in cats)
    assert score["overall"] == pytest.approx(expected, abs=0.1)
    assert 0 <= score["overall"] <= 100
    assert abs(sum(c["effective_weight"] for c in score["categories"].values()) - 1.0) < 0.01


def test_messy_scores_lower_than_clean(perfect, messy):
    assert compute_quality_score(messy)["overall"] < compute_quality_score(perfect)["overall"]


def test_validity_uses_user_rules_when_given(messy):
    auto = compute_quality_score(messy)
    mine = compute_quality_score(messy, rules=[make_rule("email", "Email")])
    assert mine["validity_rules_source"] == "user"
    assert mine["categories"]["validity"]["details"]["checks"] == 5  # the blank email is not checked
    assert mine["categories"]["validity"]["score"] == pytest.approx(80.0)  # only 'bad@' fails
    assert auto["validity_rules_source"] == "auto"
    none = compute_quality_score(messy, rules=[])
    assert none["categories"]["validity"]["score"] is None


def test_consistency_detects_spaces_case_numbers_and_mixed_dates(messy):
    issues, bad, examined = consistency_issues(messy)
    kinds = {i["issue"] for i in issues}
    assert "Extra or repeated spaces" in kinds
    assert "Same value written in different case/spacing" in kinds
    assert "Dates written in more than one format" in kinds
    assert 0 < bad < examined


def test_numeric_text_mix_is_inconsistent():
    df = pd.DataFrame({"v": ["1", "2", "3", "4", "five"]})
    issues, bad, _ = consistency_issues(df)
    assert any("Non-numeric" in i["issue"] for i in issues) and bad == 1


def test_empty_dataset_scores_none():
    for df in (pd.DataFrame(), pd.DataFrame({"a": []}), pd.DataFrame(index=[0, 1])):
        score = compute_quality_score(df)
        assert score["overall"] is None and score["grade"] == "No data" and score["notes"]


def test_all_missing_column_does_not_crash():
    score = compute_quality_score(pd.DataFrame({"a": [None, None], "b": ["", " "]}))
    assert score["categories"]["completeness"]["score"] == 0.0


def test_grade_boundaries():
    assert [grade_for(x) for x in (95, 90, 89.9, 75, 74.9, 50, 49.9, None)] == [
        "Excellent", "Excellent", "Good", "Good", "Fair", "Fair", "Poor", "No data"]


def test_suggestions_and_issues_reference_real_problems(messy):
    score = compute_quality_score(messy)
    text = " ".join(score["suggestions"]).lower()
    assert "duplicate" in text and "missing" in text
    assert score["issues"] and {i["severity"] for i in score["issues"]} <= {"high", "medium", "low"}


# --------------------------------------------------------------- profiler
def test_profile_columns(messy):
    table = profile_dataframe(messy).set_index("column")
    assert table.loc["Name", "missing"] == 2 and table.loc["Name", "empty_strings"] == 1
    assert table.loc["Qty", "min"] == -1 and table.loc["Qty", "max"] == 3
    assert table.loc["Qty", "median"] == 2
    assert table.loc["Email", "unique_values"] == 4
    assert "bob@example.com (2)" in table.loc["Email", "common_values"]
    assert table.loc["Email", "data_type"] == "text"


def test_profile_flags_outliers():
    df = pd.DataFrame({"x": [10, 11, 12, 11, 10, 12, 11, 10, 11, 500]})
    assert profile_dataframe(df).loc[0, "outliers_iqr"] == 1


def test_overall_profile_and_empty():
    profile = overall_profile(pd.DataFrame({"a": [1, 1], "b": [None, None]}))
    assert profile["rows"] == 2 and profile["missing_cells"] == 2 and profile["duplicate_rows"] == 1
    empty = overall_profile(pd.DataFrame())
    assert empty["rows"] == 0 and empty["missing_pct"] == 0.0
    assert profile_dataframe(pd.DataFrame()).empty


# -------------------------------------------------------------- helpers
def test_blank_mask_and_parsers():
    s = pd.Series(["a", " ", "", None, "b"])
    assert blank_mask(s).tolist() == [False, True, True, True, False]
    nums = parse_numeric_series(pd.Series(["1", "2.5", "abc", None, "1,000", "inf"]))
    assert nums.tolist()[:2] == [1.0, 2.5] and nums.isna().tolist() == [False, False, True, True, True, True]
    dates = parse_dates_flexible(pd.Series(["2024-03-05", "05/03/2024", "bad", None]), dayfirst=True)
    assert dates.dt.strftime("%Y-%m-%d").tolist()[:2] == ["2024-03-05", "2024-03-05"] and dates.isna().tolist()[2:] == [True, True]


# --------------------------------------------------------- Smart Clean engine
def test_smart_clean_recommends_and_applies_safe_steps(messy):
    recs = analyze_dataset(messy)
    ids = [r["id"] for r in recs if r["kind"] == "action"]
    assert "trim" in ids and "dups" in ids and "colnames" in ids
    before = messy.copy()
    cleaned, infos = apply_recommendations(messy, [r for r in recs if r["default_selected"]])
    assert messy.equals(before)                        # original untouched
    assert list(cleaned.columns) == ["name", "email", "qty", "date"]
    assert cleaned["name"].map(lambda v: v is np.nan or pd.isna(v) or v == v.strip()).all()
    assert len(cleaned) < len(messy) or "dups" not in ids
    assert all(i["status"] in ("applied", "nothing_to_do") for i in infos)


def test_smart_clean_never_applies_advisories(messy):
    recs = analyze_dataset(messy)
    advisories = [r for r in recs if r["kind"] == "advisory"]
    assert advisories and all(not r["default_selected"] for r in advisories)
    out, infos = apply_recommendations(messy, advisories)
    assert infos == [] and out.equals(messy)


def test_smart_clean_converts_text_numbers_but_keeps_ids_and_phones():
    df = pd.DataFrame({"price": ["10", "20", "30"], "phone": ["09876", "01234", "05555"], "zip_code": ["600001", "600002", "600003"]})
    cleaned, _ = apply_recommendations(df, analyze_dataset(df))
    assert pd.api.types.is_integer_dtype(cleaned["price"])
    assert cleaned["phone"].tolist() == df["phone"].tolist() and cleaned["zip_code"].tolist() == df["zip_code"].tolist()


def test_smart_clean_ambiguous_dates_need_review():
    df = pd.DataFrame({"d": ["01/02/2024", "03/04/2024"]})
    rec = [r for r in analyze_dataset(df) if r["id"] == "date_d"][0]
    assert rec["needs_review"] and not rec["default_selected"]
    day_first = pd.DataFrame({"d": ["15/02/2024", "03/04/2024"]})
    rec = [r for r in analyze_dataset(day_first) if r["id"] == "date_d"][0]
    assert rec["params"]["dayfirst"] is True and rec["default_selected"]


def test_smart_clean_conflicting_date_order_is_only_advice():
    df = pd.DataFrame({"d": ["15/02/2024", "02/15/2024"]})
    recs = analyze_dataset(df)
    assert not any(r["kind"] == "action" and r["operation"] == "convert_date" for r in recs)
    assert any(r["kind"] == "advisory" and r["id"] == "date_d" for r in recs)


def test_smart_clean_on_clean_data_has_nothing_to_apply(perfect):
    assert [r for r in analyze_dataset(perfect) if r["kind"] == "action"] == []
    assert analyze_dataset(pd.DataFrame()) == []


def test_sample_datasets_load_clean_up_and_improve():
    for name in ("customers", "sales", "employees"):
        with open(f"sample_data/{name}_messy.csv", "rb") as fh:
            df = read_uploaded_file(fh.read(), f"{name}_messy.csv")
        before = compute_quality_score(df)
        cleaned, _ = apply_recommendations(df, [r for r in analyze_dataset(df) if r["default_selected"]])
        after = compute_quality_score(cleaned)
        assert after["overall"] > before["overall"], name
        assert len(cleaned) < len(df), name       # sample files contain duplicates


# --------------------------------------------------------------- reports
def test_comparison_table_and_html_report(messy):
    cleaned, infos = apply_recommendations(messy, [r for r in analyze_dataset(messy) if r["default_selected"]])
    s1, s2 = compute_quality_score(messy), compute_quality_score(cleaned)
    table = build_comparison(messy, cleaned, s1, s2)
    assert table.loc[table["metric"] == "Rows", "before"].iloc[0] == 6
    history = [{"step": 1, "timestamp": "2026-01-01 10:00:00", "operation": "Test op", "columns": ["a"], "params": {"k": 1},
                "rows_before": 6, "rows_after": 5, "rows_affected": 1, "cells_changed": 0, "status": "applied", "notes": []}]
    result = validate(cleaned, [make_rule("email", "email")])
    html = build_html_report("people.csv", messy, cleaned, s1, s2, history, result, [make_rule("email", "email")], analyze_dataset(messy), 123, b"\x89PNGfake")
    for expected in ("DATAWISE", "people.csv", "Final status", "Before and after", "Test op", "data:image/png;base64", "DefineInfoTech"):
        assert expected in html


def test_html_report_escapes_malicious_cell_values():
    evil = pd.DataFrame({"<script>alert(1)</script>": ["<img src=x onerror=alert(1)>"]})
    s = compute_quality_score(evil)
    html = build_html_report("<b>evil</b>.csv", evil, evil, s, s, [])
    assert "<script>alert(1)</script>" not in html and "<b>evil</b>" not in html
    assert "&lt;script&gt;" in html


def test_report_without_logo_still_works(perfect):
    s = compute_quality_score(perfect)
    assert "DefineInfoTech" in build_html_report("x.csv", perfect, perfect, s, s, [])


def test_history_exports(tmp_path):
    history = [{"step": 1, "timestamp": "t", "operation": "Op", "columns": ["a", "b"], "params": {"x": 1}, "status": "applied", "notes": ["n"]}]
    frame = history_to_dataframe(history)
    assert frame.loc[0, "columns"] == "a, b"
    assert b"Op" in history_to_csv_bytes(history)
    assert json.loads(history_to_json_bytes(history))[0]["operation"] == "Op"
    assert history_to_dataframe([]).empty


def test_excel_reports_open_and_have_expected_sheets(messy):
    import io
    s = compute_quality_score(messy)
    rules = [make_rule("email", "Email")]
    result = validate(messy, rules)
    book = pd.ExcelFile(io.BytesIO(validation_report_excel_bytes(result, rules, "x.csv")))
    assert {"Overview", "Rules", "Rule summary", "Row-level issues"} <= set(book.sheet_names)
    issues = book.parse("Row-level issues")
    assert len(issues) == result.cells_failed
    report = pd.ExcelFile(io.BytesIO(quality_report_excel_bytes("x.csv", s, s, build_comparison(messy, messy, s, s), profile_dataframe(messy), [])))
    assert {"Before vs after", "Column profile", "Score - original"} <= set(report.sheet_names)
