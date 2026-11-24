"""Tests for the cleaning engine (missing values, duplicates, text, names, types, outliers, rules)."""

import numpy as np
import pandas as pd
import pytest

from core import cleaning_engine as ce
from core.data_utils import blank_mask, count_blank_cells


@pytest.fixture
def people():
    return pd.DataFrame({
        "Name": ["  Anu  Raj ", "bala", "BALA", None, "Chitra"],
        "City": ["Madurai", "", "Chennai", "chennai", "Madurai"],
        "Age": [25, np.nan, 40, 31, np.nan],
        "Salary": [1000.0, 2000.0, np.nan, 4000.0, 5000.0],
    })


# --------------------------------------------------------- missing values
def test_missing_detection_counts_none_nan_and_blank_text(people):
    summary = ce.missing_summary(people).set_index("column")["missing"].to_dict()
    assert summary == {"Name": 1, "City": 1, "Age": 2, "Salary": 1}
    assert count_blank_cells(people) == 5


def test_blank_not_counted_when_setting_off(people):
    summary = ce.missing_summary(people, treat_blank_as_missing=False).set_index("column")["missing"].to_dict()
    assert "City" not in summary


def test_drop_missing_rows_any_and_selected_columns(people):
    out, info = ce.drop_missing_rows(people, ["Age"])
    assert len(out) == 3 and info["rows_affected"] == 2
    out_all, _ = ce.drop_missing_rows(people)
    assert len(out_all) == 1
    assert len(people) == 5  # the input is never changed


def test_fill_mean_median_zero_on_numeric(people):
    mean, _ = ce.fill_missing(people, ["Salary"], "mean")
    assert mean.loc[2, "Salary"] == pytest.approx(3000.0)
    med, _ = ce.fill_missing(people, ["Age"], "median")
    assert med.loc[1, "Age"] == 31
    zero, info = ce.fill_missing(people, ["Age"], "zero")
    assert zero["Age"].isna().sum() == 0 and info["cells_changed"] == 2


def test_fill_numeric_method_skips_text_column(people):
    out, info = ce.fill_missing(people, ["City", "Age"], "median")
    assert any(item["column"] == "City" for item in info["skipped"])
    assert out["City"].tolist() == people["City"].tolist()  # untouched
    assert out["Age"].isna().sum() == 0


def test_fill_mode_and_custom(people):
    out, _ = ce.fill_missing(people, ["City"], "mode")
    assert out.loc[1, "City"] == "Madurai"
    out2, _ = ce.fill_missing(people, ["Name"], "custom", custom_value="Unknown")
    assert out2.loc[3, "Name"] == "Unknown"


def test_fill_custom_non_number_on_numeric_is_skipped(people):
    out, info = ce.fill_missing(people, ["Age"], "custom", custom_value="abc")
    assert info["skipped"] and out["Age"].isna().sum() == 2


def test_fill_missing_unknown_column_is_reported(people):
    _, info = ce.fill_missing(people, ["Nope"], "zero")
    assert info["skipped"][0]["reason"] == "Column not found"


# -------------------------------------------------------------- duplicates
def test_duplicate_detection_and_removal():
    df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "z", "w"]})
    assert ce.count_duplicates(df) == 1
    assert ce.count_duplicates(df, ["a"]) == 2
    assert len(ce.get_duplicate_rows(df)) == 2
    out, info = ce.remove_duplicates(df)
    assert len(out) == 4 and info["rows_affected"] == 1
    out2, _ = ce.remove_duplicates(df, subset=["a"], keep="last")
    assert out2["b"].tolist() == ["x", "z", "w"]


def test_remove_duplicates_nothing_to_do():
    df = pd.DataFrame({"a": [1, 2]})
    _, info = ce.remove_duplicates(df)
    assert info["status"] == "nothing_to_do"


# ---------------------------------------------------------------- text
def test_trim_and_collapse_spaces(people):
    out, info = ce.trim_spaces(people, ["Name"])
    assert out.loc[0, "Name"] == "Anu  Raj"
    out, _ = ce.collapse_spaces(out, ["Name"])
    assert out.loc[0, "Name"] == "Anu Raj"
    assert pd.isna(out.loc[3, "Name"])  # missing stays missing


def test_change_case_modes(people):
    assert ce.change_case(people, ["Name"], "lower")[0].loc[1, "Name"] == "bala"
    assert ce.change_case(people, ["Name"], "upper")[0].loc[1, "Name"] == "BALA"
    assert ce.change_case(people, ["Name"], "title")[0].loc[4, "Name"] == "Chitra"
    with pytest.raises(ValueError):
        ce.change_case(people, ["Name"], "weird")


def test_text_operations_never_touch_numbers(people):
    out, info = ce.change_case(people, ["Age"], "upper")
    assert info["skipped"][0]["reason"] == "Not a text column"
    assert out["Age"].equals(people["Age"])


def test_mixed_type_object_column_keeps_numbers():
    df = pd.DataFrame({"v": pd.Series([" a ", 5, 2.5, None], dtype=object)})
    out, _ = ce.trim_spaces(df, ["v"])
    assert out["v"].tolist()[0] == "a" and out["v"].tolist()[1] == 5


def test_replace_values_whole_cell_and_partial(people):
    out, info = ce.replace_values(people, ["City"], "Madurai", "Madura")
    assert out["City"].tolist().count("Madura") == 2 and info["cells_changed"] == 2
    out2, _ = ce.replace_values(people, ["City"], "chen", "CHEN", whole_cell=False, case_sensitive=False)
    assert "CHENnai" in out2["City"].tolist()
    with pytest.raises(ValueError):
        ce.replace_values(people, ["City"], "", "x")


def test_remove_characters():
    df = pd.DataFrame({"p": ["(044) 123-45", "98#76$"]})
    out, _ = ce.remove_characters(df, ["p"], "()-#$ ")
    assert out["p"].tolist() == ["04412345", "9876"]


def test_replace_blank_text_to_missing(people):
    out, info = ce.replace_blank_text(people, ["City"])
    assert pd.isna(out.loc[1, "City"]) and info["cells_changed"] == 1


def test_standardize_categories_with_suggestions(people):
    mapping = ce.suggest_category_groups(people["City"])
    assert mapping == {"chennai": "Chennai"} or mapping == {"Chennai": "chennai"}
    out, info = ce.standardize_categories(people, "City", {"chennai": "Chennai"})
    assert out["City"].tolist().count("Chennai") == 2 and info["cells_changed"] == 1


# ------------------------------------------------------------ column names
def test_clean_column_names_and_duplicates():
    df = pd.DataFrame([[1, 2, 3, 4]], columns=[" First Name ", "E-mail (work)", "email  work", "ID#"])
    out, info = ce.clean_column_names(df)
    assert list(out.columns) == ["first_name", "email_work", "email_work_2", "id"]
    assert info["columns_renamed"] == 4


def test_clean_column_names_nothing_to_do():
    _, info = ce.clean_column_names(pd.DataFrame({"a": [1]}))
    assert info["status"] == "nothing_to_do"


# ------------------------------------------------------------- type conversion
def test_convert_to_integer_float_string():
    df = pd.DataFrame({"n": ["1", " 2 ", None], "f": ["1.5", "2", "3.25"]})
    out, info = ce.convert_column_type(df, "n", "integer")
    assert info["status"] == "applied" and out["n"].tolist()[:2] == [1, 2] and pd.isna(out["n"].iloc[2])
    out, _ = ce.convert_column_type(df, "f", "float")
    assert out["f"].tolist() == [1.5, 2.0, 3.25]
    out, _ = ce.convert_column_type(pd.DataFrame({"x": [1, 2]}), "x", "string")
    assert out["x"].tolist() == ["1", "2"]


def test_conversion_errors_block_by_default_and_are_listed():
    df = pd.DataFrame({"n": ["1", "two", "3", "4x"]})
    out, info = ce.convert_column_type(df, "n", "integer")
    assert info["status"] == "blocked" and info["error_count"] == 2
    assert {e["value"] for e in info["errors"]} == {"two", "4x"}
    assert out["n"].tolist() == df["n"].tolist()  # nothing was corrupted


def test_conversion_set_missing_option():
    df = pd.DataFrame({"n": ["1", "two"]})
    out, info = ce.convert_column_type(df, "n", "float", on_error="set_missing")
    assert info["status"] == "applied" and pd.isna(out["n"].iloc[1]) and info["error_count"] == 1


def test_integer_conversion_rejects_decimals():
    _, info = ce.convert_column_type(pd.DataFrame({"n": ["1", "2.5"]}), "n", "integer")
    assert info["status"] == "blocked"


def test_currency_symbols_need_clean_symbols_flag():
    df = pd.DataFrame({"p": ["Rs 1,200", "$45", "300"]})
    _, blocked = ce.convert_column_type(df, "p", "float")
    assert blocked["status"] == "blocked"
    out, info = ce.convert_column_type(df, "p", "float", clean_symbols=True)
    assert out["p"].tolist() == [1200.0, 45.0, 300.0]


def test_convert_to_date_and_datetime_and_ambiguity():
    df = pd.DataFrame({"d": ["2024-03-15", "15/03/2024", "Mar 5, 2024"]})
    out, info = ce.convert_column_type(df, "d", "date", dayfirst=True)
    assert info["status"] == "applied"
    assert out["d"].dt.strftime("%Y-%m-%d").tolist() == ["2024-03-15", "2024-03-15", "2024-03-05"]
    amb = pd.DataFrame({"d": ["05/06/2024"]})
    assert ce.convert_column_type(amb, "d", "date", dayfirst=True)[0]["d"].iloc[0].month == 6
    assert ce.convert_column_type(amb, "d", "date", dayfirst=False)[0]["d"].iloc[0].month == 5
    out, _ = ce.convert_column_type(pd.DataFrame({"d": ["2024-03-15 10:30:00"]}), "d", "datetime")
    assert out["d"].iloc[0].hour == 10


def test_invalid_calendar_date_blocks_conversion():
    _, info = ce.convert_column_type(pd.DataFrame({"d": ["2024-02-30", "2024-01-01"]}), "d", "date")
    assert info["status"] == "blocked" and info["error_count"] == 1


def test_convert_to_boolean():
    df = pd.DataFrame({"b": ["Yes", "no", "TRUE", None]})
    out, info = ce.convert_column_type(df, "b", "boolean")
    assert out["b"].tolist()[:3] == [True, False, True] and pd.isna(out["b"].iloc[3])
    _, bad = ce.convert_column_type(pd.DataFrame({"b": ["maybe"]}), "b", "boolean")
    assert bad["status"] == "blocked"


# ------------------------------------------------------------------ outliers
@pytest.fixture
def numbers():
    return pd.Series([10, 11, 12, 11, 10, 12, 11, 10, 11, 500], name="x")


def test_iqr_outlier_detection(numbers):
    mask, low, high = ce.detect_outliers_iqr(numbers)
    assert mask.tolist() == [False] * 9 + [True]
    assert low < 10 and high < 500


def test_zscore_outlier_detection():
    values = pd.Series([10] * 30 + [11] * 30 + [200])
    mask, _, _ = ce.detect_outliers_zscore(values, 3.0)
    assert mask.sum() == 1 and mask.iloc[-1]


def test_zscore_with_constant_values_finds_nothing():
    mask, low, _ = ce.detect_outliers_zscore(pd.Series([5] * 10))
    assert not mask.any() and low is None


def test_outlier_report_and_handling(numbers):
    df = pd.DataFrame({"x": numbers, "t": list("abcdefghij")})
    report = ce.outlier_report(df)
    assert report.loc[0, "outliers"] == 1 and list(report["column"]) == ["x"]
    removed, info = ce.handle_outliers(df, "x", action="remove")
    assert len(removed) == 9 and info["rows_affected"] == 1
    capped, info = ce.handle_outliers(df, "x", action="cap")
    assert len(capped) == 10 and capped["x"].max() < 500 and info["cells_changed"] == 1
    assert df["x"].max() == 500  # original untouched


def test_outliers_on_text_column_are_blocked():
    _, info = ce.handle_outliers(pd.DataFrame({"t": ["a", "b"]}), "t")
    assert info["status"] == "blocked"


# ------------------------------------------------------------- standardisation
def test_standardize_dates_to_iso():
    df = pd.DataFrame({"d": ["15/03/2024", "2024-03-16", None]})
    out, info = ce.standardize_dates(df, "d", dayfirst=True)
    assert out["d"].tolist()[:2] == ["2024-03-15", "2024-03-16"] and pd.isna(out["d"].iloc[2])
    _, blocked = ce.standardize_dates(pd.DataFrame({"d": ["nonsense"]}), "d")
    assert blocked["status"] == "blocked"


def test_standardize_numeric_with_rounding():
    out, info = ce.standardize_numeric(pd.DataFrame({"p": ["Rs 1,200.456", "10"]}), "p", decimals=1)
    assert out["p"].tolist() == [1200.5, 10.0]


def test_normalize_numeric_adds_new_columns():
    df = pd.DataFrame({"a": [0.0, 5.0, 10.0], "b": [1, 1, 1]})
    out, info = ce.normalize_numeric(df, ["a", "b"], "minmax")
    assert out["a_minmax"].tolist() == [0.0, 0.5, 1.0] and "a" in out.columns
    assert any(s["column"] == "b" for s in info["skipped"])  # constant column
    z, _ = ce.normalize_numeric(df, ["a"], "zscore")
    assert abs(z["a_zscore"].mean()) < 1e-9


# ----------------------------------------------------------------- custom rules
def test_custom_rules_are_applied(people):
    rules = [
        {"column": "Name", "operation": "trim"},
        {"column": "City", "operation": "upper"},
        {"column": "City", "operation": "replace_value", "value": "MADURAI", "value2": "MDU"},
        {"column": "Age", "operation": "fill_missing", "value": "mean"},
        {"column": "Salary", "operation": "clip_range", "value": "1500", "value2": "4500"},
    ]
    out, infos = ce.apply_rules(people, rules)
    assert out.loc[0, "Name"] == "Anu  Raj"
    assert out["City"].tolist().count("MDU") == 2
    assert out["Age"].isna().sum() == 0
    assert out["Salary"].min() == 1500 and out["Salary"].max() == 4500
    assert all("Custom rule" in i["operation"] for i in infos)


def test_allowed_values_rule():
    df = pd.DataFrame({"status": ["Active", "inactive", "Pending", None]})
    out, info = ce.apply_rule(df, {"column": "status", "operation": "set_allowed_values", "value": "Active, Inactive", "value2": "Unknown"})
    assert out["status"].tolist()[:3] == ["Active", "Unknown", "Unknown"]


def test_round_and_bad_clip_inputs():
    df = pd.DataFrame({"x": [1.234, 2.678]})
    out, _ = ce.apply_rule(df, {"column": "x", "operation": "round_numbers", "value": "1"})
    assert out["x"].tolist() == [1.2, 2.7]
    _, info = ce.apply_rule(df, {"column": "x", "operation": "clip_range", "value": "abc", "value2": ""})
    assert info["status"] == "blocked"


def test_unknown_rule_operation_raises():
    with pytest.raises(ValueError):
        ce.apply_rule(pd.DataFrame({"a": [1]}), {"column": "a", "operation": "explode"})
