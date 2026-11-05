"""Generate the example files (synthetic, deterministic).

    python examples/make_samples.py

Writes a clean file and a copy with one known error per rule, so the README
output is reproducible and the tests know exactly what must be caught.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

OUT = Path(__file__).parent / "data"
HEADER = [
    "Reference Date", "Contract ID", "Installment Number", "Total Installments", "Lender Doc",
    "Borrower Name", "Borrower Doc", "Product", "Issue Date", "Due Date", "Face Value",
    "Purchase Price", "Annual Rate", "Status", "Renegotiation Date",
]  # fmt: skip

# (line number in the error file, column, bad value) -> one per rule
ERRORS = [
    (3, "Borrower Doc", "123.456.789-00"),  # tax_id
    (5, "Face Value", "1.234,5x"),  # type decimal
    (7, "Due Date", "31/02/2026"),  # type date
    (9, "Product", "CRYPTO"),  # enum
    (11, "Contract ID", "CONTRACT-1"),  # pattern
    (13, "Purchase Price", "999999,00"),  # compare price <= face
    (15, "Borrower Name", ""),  # required
    (17, "Status", "RENEGOTIATED"),  # required_if renegotiation_date
]


def br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def money(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def build_rows(n_contracts: int = 12, seed: int = 7) -> list[dict]:
    rng, fake = random.Random(seed), Faker("pt_BR")
    fake.seed_instance(seed)
    lender = fake.cnpj()
    ref = date(2026, 6, 30)
    rows = []
    for c in range(1, n_contracts + 1):
        total = rng.choice([3, 6, 12])
        issue = ref - timedelta(days=rng.randint(30, 200))
        name, doc = (
            (fake.name(), fake.cpf()) if rng.random() < 0.7 else (fake.company(), fake.cnpj())
        )
        product = rng.choice(["PAYROLL", "PERSONAL", "SME_WORKING_CAPITAL", "TRADE_BILL"])
        rate = rng.uniform(0.2, 0.9)
        face = round(rng.uniform(300, 5000), 2)
        for i in range(1, total + 1):
            due = issue + timedelta(days=30 * i)
            rows.append({
                "Reference Date": br(ref), "Contract ID": f"CT-{c:06d}",
                "Installment Number": str(i), "Total Installments": str(total),
                "Lender Doc": lender, "Borrower Name": name, "Borrower Doc": doc,
                "Product": product, "Issue Date": br(issue), "Due Date": br(due),
                "Face Value": money(face),
                "Purchase Price": money(face / (1 + rate) ** (30 * i / 365)),
                "Annual Rate": f"{rate:.4f}".replace(".", ","),
                "Status": "OVERDUE" if due < ref else "CURRENT", "Renegotiation Date": "",
            })  # fmt: skip
    return rows


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    rows = build_rows()
    write(OUT / "loan_portfolio_ok.csv", rows)

    bad = [dict(r) for r in rows]
    for line, col, value in ERRORS:
        bad[line - 2][col] = value
    bad.append(dict(bad[0]))  # duplicated installment -> unique
    bad[-1]["Borrower Doc"] = rows[-1]["Borrower Doc"]  # ...with another borrower -> consistent
    write(OUT / "loan_portfolio_with_errors.csv", bad)
    print(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
