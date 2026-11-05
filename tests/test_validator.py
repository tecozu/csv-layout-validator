from pathlib import Path

import pandas as pd
import pytest

from layout_validator import load_layout, validate_file, validate_frame
from layout_validator.layout import LayoutError, parse_layout
from layout_validator.validator import normalize_header

EXAMPLES = Path(__file__).parents[1] / "examples"
LAYOUT = load_layout(EXAMPLES / "layouts" / "loan_portfolio.yaml")


def rules(violations):
    return {(v.rule, v.column) for v in violations}


def test_clean_example_passes():
    report = validate_file(EXAMPLES / "data" / "loan_portfolio_ok.csv", LAYOUT)
    assert report.ok, [v.message for v in report.violations]
    assert report.row_count > 50


def test_error_example_catches_every_injected_error():
    report = validate_file(EXAMPLES / "data" / "loan_portfolio_with_errors.csv", LAYOUT)
    found = {(v.rule, v.column): v.rows for v in report.violations}

    assert found[("tax_id", "borrower_doc")] == [3]
    assert found[("type", "face_value")] == [5]
    assert found[("type", "due_date")] == [7]
    assert found[("enum", "product")] == [9]
    assert found[("pattern", "contract_id")] == [11]
    assert 13 in found[("compare", "purchase_price")]
    assert found[("required", "borrower_name")] == [15]
    assert found[("required_if", "renegotiation_date")] == [17]
    assert ("unique", "contract_id,installment_number") in found
    assert ("consistent", "borrower_doc") in found


def frame(**cols):
    return pd.DataFrame({k: [str(x) for x in v] for k, v in cols.items()})


def layout(columns, checks=None, **file):
    return parse_layout({"name": "t", "file": file, "columns": columns, "checks": checks or []})


def test_line_numbers_account_for_header():
    v = validate_frame(frame(a=["1", "", "3"]), layout({"a": {"required": True}}))
    assert v[0].rows == [3]


def test_decimal_with_thousands_and_comma():
    lay = layout({"x": {"type": "decimal", "min": 0}}, decimal=",", thousands=".")
    assert not validate_frame(frame(x=["1.234,56", "0,01"]), lay)
    assert rules(validate_frame(frame(x=["-1,00"]), lay)) == {("min", "x")}


def test_blank_optional_values_are_not_type_errors():
    lay = layout({"d": {"type": "date", "format": "%d/%m/%Y"}, "n": {"type": "integer"}})
    assert not validate_frame(frame(d=["", "01/02/2026"], n=["", "7"]), lay)


def test_missing_column_skips_table_checks():
    lay = layout({"a": {}, "b": {}}, checks=[{"unique": ["a", "b"]}])
    v = validate_frame(frame(a=["1", "1"]), lay)
    assert rules(v) == {("missing_column", "b")}


def test_extra_columns_can_be_forbidden():
    lay = layout({"a": {}}, allow_extra_columns=False)
    assert rules(validate_frame(frame(a=["1"], z=["2"]), lay)) == {("unexpected_column", "z")}


def test_required_if_with_in():
    lay = layout(
        {"status": {}, "reason": {}},
        checks=[
            {"required_if": {"column": "reason", "when": {"column": "status", "in": ["X", "Y"]}}}
        ],
    )
    v = validate_frame(frame(status=["X", "Y", "Z"], reason=["ok", "", ""]), lay)
    assert v[0].rows == [3]


@pytest.mark.parametrize(
    "raw, expected",
    [("Contract ID", "contract_id"), ("contractId", "contract_id"), (" Valor-Pago ", "valor_pago")],
)
def test_snake_case_headers(raw, expected):
    assert normalize_header(raw, "snake") == expected


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "t", "columns": {"a": {"typo": 1}}},
        {"name": "t", "columns": {"a": {"type": "money"}}},
        {"name": "t", "columns": {"a": {}}, "checks": [{"unique": ["b"]}]},
        {
            "name": "t",
            "columns": {"a": {}},
            "checks": [{"compare": {"left": "a", "op": "~", "right": "a"}}],
        },
        {"name": "t", "columns": {"a": {}}, "checks": [{"sometimes": ["a"]}]},
    ],
)
def test_invalid_layouts_fail_loudly(bad):
    with pytest.raises(LayoutError):
        parse_layout(bad)
