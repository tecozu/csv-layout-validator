# csv-layout-validator

[![CI](https://github.com/tecozu/csv-layout-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/tecozu/csv-layout-validator/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Declarative validation for the CSV files your partners send you, before they reach your pipeline.**

In financial operations, data still arrives as delimited files from lenders,
banks and administrators. A bad file found mid-pipeline costs hours. This tool
checks each file against a YAML *layout contract* and lists **every** problem,
with the file line where it occurs. You can send that list straight back to whoever
produced the file, or use it to block the load in CI.

```text
$ layout-validator examples/data -l examples/layouts/loan_portfolio.yaml
PASS  examples/data/loan_portfolio_ok.csv  [layout: loan_portfolio]  60 rows
FAIL  examples/data/loan_portfolio_with_errors.csv  [layout: loan_portfolio]  61 rows  (12 invalid rows, 10 violations)
  - [pattern] contract_id: does not match CT-\d{6}
      lines: 11
  - [tax_id] borrower_doc: invalid CPF/CNPJ check digits
      lines: 3
  - [type] face_value: not a decimal (decimal sep ',')
      lines: 5
  - [unique] contract_id,installment_number: duplicate value for (contract_id, installment_number)
      lines: 2, 62
  - [compare] purchase_price: expected purchase_price <= face_value
      lines: 13
  - [consistent] borrower_doc: more than one 'borrower_doc' for the same (contract_id)
      lines: 2, 3, 4, 5, 6, 7, 62
  - [required_if] renegotiation_date: required when status in ['RENEGOTIATED']
      lines: 17
  ...
```

## Why

- **Rules live in YAML, not in code.** Onboarding a new partner or file format is a
  config change that anyone can review in a PR.
- **Collects every error instead of stopping at the first**, with line numbers that match
  what the sender sees in their editor.
- **Handles real-world files**: decimal comma, thousands separators, `dd/mm/yyyy`
  dates, messy headers (`"Contract ID"` / `contractId` → `contract_id`), and Brazilian
  taxpayer IDs (CPF/CNPJ) whose leading zeros were stripped by a spreadsheet.
- **The layout is validated too.** A typo such as `requird: true`, or a check that
  references a column that doesn't exist, fails loudly instead of being silently ignored.

## Install & run

```bash
pip install git+https://github.com/tecozu/csv-layout-validator
layout-validator FILE_OR_FOLDER [...] --layout layout.yaml [--format text|json|markdown] [--warn-only]
```

Exit codes: `0` all valid · `1` violations found · `2` layout/usage error. That makes it
easy to use as a gate in any orchestrator or CI job.

```python
from layout_validator import load_layout, validate_file

report = validate_file("partner_file.csv", load_layout("layouts/loan_portfolio.yaml"))
if not report.ok:
    quarantine(report.to_dict())
```

## Layout reference

```yaml
name: loan_portfolio
file:
  delimiter: ";"            # default ","
  decimal: ","              # default "."
  thousands: "."            # optional
  encoding: utf-8
  header_case: snake        # as_is | lower | snake
  allow_extra_columns: true

columns:
  contract_id:  { required: true, pattern: "CT-\\d{6}" }
  installment:  { type: integer, min: 1 }
  face_value:   { type: decimal, required: true, min: 0.01 }
  due_date:     { type: date, format: "%d/%m/%Y" }
  borrower_doc: { type: tax_id, tax_id_kind: any }   # cpf | cnpj | any
  product:      { enum: [PAYROLL, PERSONAL] }
  name:         { max_length: 120 }

checks:
  - unique: [contract_id, installment]                       # composite key
  - compare: { left: purchase_price, op: "<=", right: face_value }
  - consistent: { key: [contract_id], value: borrower_doc }  # functional dependency
  - required_if: { column: renegotiation_date, when: { column: status, equals: RENEGOTIATED } }
```

| Column rule | Meaning |
|---|---|
| `required` | value must not be blank |
| `type` | `string` · `integer` · `decimal` · `date` (with `format`) · `tax_id` |
| `min` / `max` | numeric bounds |
| `enum` · `pattern` · `max_length` | allowed values · full-match regex · length |

| Table check | Meaning |
|---|---|
| `unique` | no duplicate combination of the listed columns |
| `compare` | row-wise comparison between two typed columns (`<`, `<=`, `>`, `>=`, `==`, `!=`) |
| `consistent` | every `key` maps to exactly one `value` (e.g. one borrower per contract) |
| `required_if` | a column is required when another one `equals` a value or is `in` a list |

## Use it as a CI gate for data files

```yaml
- run: pip install git+https://github.com/tecozu/csv-layout-validator
- run: layout-validator incoming/ -l layouts/loan_portfolio.yaml -f markdown >> "$GITHUB_STEP_SUMMARY"
```

The Markdown format renders as a table in the job summary or in a PR comment.

## Development

```bash
pip install -e ".[dev]"
python examples/make_samples.py   # regenerate the synthetic example files
pytest && ruff check .
```

The example files are synthetic (Faker, fixed seed). The "with errors" file contains
exactly one injected error per rule, and the test suite asserts that each one is
reported on the right line.

## License

MIT
