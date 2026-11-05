import json
from pathlib import Path

import pytest
from faker import Faker

from layout_validator.cli import main
from layout_validator.tax_id import is_valid_tax_id

EXAMPLES = Path(__file__).parents[1] / "examples"
fake = Faker("pt_BR")
fake.seed_instance(1)


@pytest.mark.parametrize("doc", [fake.cpf() for _ in range(10)] + [fake.cnpj() for _ in range(10)])
def test_valid_tax_ids(doc):
    assert is_valid_tax_id(doc)


def test_leading_zeros_lost_by_spreadsheets_are_restored():
    assert is_valid_tax_id("191", "cpf")  # 000.000.001-91 read back as the number 191
    assert is_valid_tax_id("191")


@pytest.mark.parametrize("doc", ["", "abc", "111.111.111-11", "123.456.789-00"])
def test_invalid_tax_ids(doc):
    assert not is_valid_tax_id(doc)


def test_cli_exit_codes(capsys):
    layout = str(EXAMPLES / "layouts" / "loan_portfolio.yaml")
    assert main([str(EXAMPLES / "data" / "loan_portfolio_ok.csv"), "-l", layout]) == 0
    assert main([str(EXAMPLES / "data" / "loan_portfolio_with_errors.csv"), "-l", layout]) == 1
    assert main([str(EXAMPLES / "data"), "-l", layout, "--warn-only"]) == 0
    assert main([str(EXAMPLES / "data"), "-l", "missing.yaml"]) == 2


def test_cli_json_output(capsys):
    layout = str(EXAMPLES / "layouts" / "loan_portfolio.yaml")
    main([str(EXAMPLES / "data" / "loan_portfolio_with_errors.csv"), "-l", layout, "-f", "json"])
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["invalid_rows"] >= 10
