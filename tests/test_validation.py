"""Tests for the validation engine (email, phone, numeric, date, range, length, allowed values, ...)."""

import pandas as pd
import pytest

from core.data_utils import EMAIL_REGEX
from core.validation_engine import make_rule, suggest_rules, validate


@pytest.fixture
def contacts():
    return pd.DataFrame({
        "email": ["ann@example.com", "bad@", "no-at.com", "", None, " spaced@example.com ", "a..b@example.com"],
        "phone": ["+91 98765 43210", "12345", "abc-defg-hij", "(044) 2345-6789", "98765432101234567", None, "9876543210"],
        "age": ["25", "abc", "-5", "300", "40", "", "18"],
        "joined": ["2024-03-15", "15/03/2024", "31/04/2024", "hello", "", None, "2024-13-01"],
        "code": ["ABC-1234", "abc-1234", "ABC1234", "XYZ-9999", "", "ABC-12345", "QRS-0000"],
        "status": ["Active", "active", "Pending", "Unknown", "", None, "INACTIVE"],
    })


def failed_rows(result, column):
    return sorted(result.issues.loc[result.issues["column"] == column, "row"].tolist())


# ------------------------------------------------------------------- email
@pytest.mark.parametrize("value,ok", [
    ("a@b.co", True), ("first.last+tag@sub.example.org", True), ("x@example.com", True),
    ("bad@", False), ("@example.com", False), ("a b@example.com", False), ("a@b", False),
    ("a@@b.com", False), ("a@b.c", False), ("a@-b.com", False),
])
def test_email_regex_examples(value, ok):
    assert bool(EMAIL_REGEX.match(value)) is ok


def test_email_rule_flags_only_non_empty_invalid_values(contacts):
    result = validate(contacts, [make_rule("email", "email")])
    # rows are 1-based: bad@ (2), no-at.com (3), a..b@ (7). Blank/None are ignored; padded spaces are trimmed.
    assert failed_rows(result, "email") == [2, 3, 7]
    assert result.cells_checked == 5


# ------------------------------------------------------------------- phone
def test_phone_rule_default_and_custom_digit_range(contacts):
    result = validate(contacts, [make_rule("phone", "phone")])
    assert failed_rows(result, "phone") == [2, 3, 5]  # too short, letters, 17 digits
    strict = validate(contacts, [make_rule("phone", "phone", min_digits=10, max_digits=10)])
    assert 1 in failed_rows(strict, "phone")  # +91 98765 43210 has 12 digits


def test_phone_numbers_stored_as_floats_are_read_correctly():
    df = pd.DataFrame({"p": [9876543210.0, 12345.0]})
    result = validate(df, [make_rule("phone", "p")])
    assert failed_rows(result, "p") == [2]


# ----------------------------------------------------------------- numeric
def test_numeric_rule(contacts):
    result = validate(contacts, [make_rule("numeric", "age")])
    assert failed_rows(result, "age") == [2]
    assert result.summary.loc[0, "checked"] == 6  # the blank cell is not checked


def test_range_rule_min_max_and_non_numbers(contacts):
    result = validate(contacts, [make_rule("range", "age", min=0, max=120)])
    assert failed_rows(result, "age") == [2, 3, 4]
    messages = result.issues.set_index("row")["error"].to_dict()
    assert "Not a number" in messages[2] and "minimum" in messages[3] and "maximum" in messages[4]


def test_range_rule_with_only_one_bound():
    df = pd.DataFrame({"q": [1, -1, 5]})
    assert failed_rows(validate(df, [make_rule("range", "q", min=0)]), "q") == [2]


# -------------------------------------------------------------------- date
def test_date_rule_rejects_impossible_and_non_dates(contacts):
    result = validate(contacts, [make_rule("date", "joined", dayfirst=True)])
    assert failed_rows(result, "joined") == [3, 4, 7]  # 31/04, "hello", month 13


def test_date_rule_with_explicit_format():
    df = pd.DataFrame({"d": ["15/03/2024", "2024-03-15"]})
    result = validate(df, [make_rule("date", "d", date_format="%d/%m/%Y")])
    assert failed_rows(result, "d") == [2]


def test_plain_numbers_are_not_dates():
    df = pd.DataFrame({"d": ["5", "20240315"]})
    assert failed_rows(validate(df, [make_rule("date", "d")]), "d") == [1, 2]


def test_real_datetime_column_is_always_valid():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", "2024-02-01"])})
    assert validate(df, [make_rule("date", "d")]).invalid_rows == 0


# ------------------------------------------------ missing, length, allowed, regex
def test_not_missing_rule(contacts):
    result = validate(contacts, [make_rule("not_missing", "email")])
    assert failed_rows(result, "email") == [4, 5]


def test_text_length_rule():
    df = pd.DataFrame({"n": ["ab", "abcdef", "  a  ", ""]})
    result = validate(df, [make_rule("text_length", "n", min_length=2, max_length=5)])
    assert failed_rows(result, "n") == [2, 3]


def test_allowed_values_rule_case_options(contacts):
    result = validate(contacts, [make_rule("allowed_values", "status", values="Active, Pending, Inactive")])
    assert failed_rows(result, "status") == [4]  # 'Unknown' only (case-insensitive by default)
    strict = validate(contacts, [make_rule("allowed_values", "status", values="Active, Pending, Inactive", case_sensitive=True)])
    assert failed_rows(strict, "status") == [2, 4, 7]


def test_regex_rule_and_invalid_pattern(contacts):
    result = validate(contacts, [make_rule("regex", "code", pattern=r"[A-Z]{3}-\d{4}")])
    assert failed_rows(result, "code") == [2, 3, 6]
    bad = validate(contacts, [make_rule("regex", "code", pattern="(")])
    assert bad.cells_checked == 0 and any("could not run" in n for n in bad.notes)


def test_duplicate_rule_whole_row_and_subset():
    df = pd.DataFrame({"id": [1, 1, 2], "v": ["a", "a", "a"]})
    assert validate(df, [make_rule("duplicates", [])]).invalid_rows == 1
    assert validate(df, [make_rule("duplicates", ["v"])]).invalid_rows == 2


def test_required_columns_rule():
    df = pd.DataFrame({"a": [1]})
    result = validate(df, [make_rule("required_columns", ["a", "b"])])
    assert result.schema_issues == ["Required column 'b' is missing from the dataset."]
    assert result.summary.loc[0, "failed"] == 1


# --------------------------------------------------------------- result object
def test_result_counts_and_percentages(contacts):
    rules = [make_rule("email", "email"), make_rule("range", "age", min=0, max=120)]
    result = validate(contacts, rules)
    assert result.total_rows == 7
    assert result.invalid_rows == len(set(result.issues["row"]))
    assert result.valid_rows + result.invalid_rows == 7
    assert result.validity_pct == pytest.approx(100 * result.valid_rows / 7, abs=0.01)
    assert list(result.issues.columns) == ["row", "column", "rule", "value", "error"]


def test_validation_does_not_modify_data(contacts):
    before = contacts.copy()
    validate(contacts, [make_rule("email", "email")])
    assert contacts.equals(before)


def test_empty_inputs_are_handled():
    assert validate(pd.DataFrame(), [make_rule("email", "x")]).notes
    assert validate(pd.DataFrame({"a": [1]}), []).notes
    unknown = validate(pd.DataFrame({"a": [1]}), [make_rule("email", "missing_col")])
    assert unknown.cells_checked == 0 and unknown.notes


def test_row_numbers_survive_row_deletion():
    df = pd.DataFrame({"e": ["ok@example.com", "bad", "bad2"]}).drop(index=0)
    assert failed_rows(validate(df, [make_rule("email", "e")]), "e") == [2, 3]


# --------------------------------------------------------------- suggestions
def test_suggest_rules_from_names_and_content(contacts):
    rules = {(r["rule"], tuple(r["columns"])) for r in suggest_rules(contacts)}
    assert ("email", ("email",)) in rules
    assert ("phone", ("phone",)) in rules
    assert ("numeric", ("age",)) in rules or ("range", ("age",)) in rules
    assert ("date", ("joined",)) in rules
