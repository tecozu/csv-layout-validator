"""Run a Layout against a file and collect every violation (never stop at the first).

Row numbers in the report are *file line numbers* (header = line 1), so they can be
opened directly in an editor or sent back to whoever produced the file.
"""

from __future__ import annotations

import operator
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from layout_validator.layout import ColumnSpec, Layout
from layout_validator.tax_id import is_valid_tax_id

OPS = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt,
    ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
}  # fmt: skip


@dataclass
class Violation:
    rule: str
    column: str | None
    rows: list[int]
    message: str

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass
class Report:
    file: str
    layout: str
    row_count: int
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def invalid_rows(self) -> int:
        return len({r for v in self.violations for r in v.rows})

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "layout": self.layout,
            "row_count": self.row_count,
            "ok": self.ok,
            "invalid_rows": self.invalid_rows,
            "violations": [asdict(v) | {"count": v.count} for v in self.violations],
        }


# --------------------------------------------------------------------------- helpers
def normalize_header(name: str, case: str) -> str:
    if case == "lower":
        return name.strip().lower()
    if case == "snake":
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())
        return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    return name.strip()


def _line_numbers(mask: pd.Series) -> list[int]:
    return [int(i) + 2 for i in mask[mask].index]  # +1 for 0-index, +1 for header line


def _is_blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip() == "")


def parse_column(s: pd.Series, spec: ColumnSpec, layout: Layout) -> pd.Series:
    """Typed view of a column (NaN/NaT where blank or unparseable)."""
    s = s.where(~_is_blank(s)).astype("object").str.strip()
    if spec.type in ("decimal", "integer"):
        if layout.file.thousands:
            s = s.str.replace(layout.file.thousands, "", regex=False)
        if layout.file.decimal != ".":
            s = s.str.replace(layout.file.decimal, ".", regex=False)
        return pd.to_numeric(s, errors="coerce")
    if spec.type == "date":
        return pd.to_datetime(s, format=spec.format, errors="coerce")
    return s


# --------------------------------------------------------------------------- column rules
def _column_violations(raw: pd.Series, spec: ColumnSpec, layout: Layout) -> list[Violation]:
    out: list[Violation] = []
    blank = _is_blank(raw)
    present = ~blank
    text = raw.astype(str).str.strip()
    typed = parse_column(raw, spec, layout)

    def add(rule: str, invalid: pd.Series, message: str) -> None:
        if invalid.any():
            out.append(Violation(rule, spec.name, _line_numbers(invalid), message))

    if spec.required:
        add("required", blank, "value is required")

    if spec.type == "integer":
        add("type", present & ~text.str.fullmatch(r"[+-]?\d+"), "not an integer")
    elif spec.type == "decimal":
        add("type", present & typed.isna(), f"not a decimal (decimal sep '{layout.file.decimal}')")
    elif spec.type == "date":
        add("type", present & typed.isna(), f"not a date in format {spec.format}")
    elif spec.type == "tax_id":
        valid = text.map(lambda v: is_valid_tax_id(v, spec.tax_id_kind))
        kind = "CPF/CNPJ" if spec.tax_id_kind == "any" else spec.tax_id_kind.upper()
        add("tax_id", present & ~valid, f"invalid {kind} check digits")

    if spec.min is not None and spec.type in ("integer", "decimal"):
        add("min", typed.notna() & (typed < spec.min), f"below minimum {spec.min}")
    if spec.max is not None and spec.type in ("integer", "decimal"):
        add("max", typed.notna() & (typed > spec.max), f"above maximum {spec.max}")
    if spec.enum is not None:
        allowed = {str(v) for v in spec.enum}
        add("enum", present & ~text.isin(allowed), f"not one of {sorted(allowed)}")
    if spec.pattern is not None:
        add(
            "pattern", present & ~text.str.fullmatch(spec.pattern), f"does not match {spec.pattern}"
        )
    if spec.max_length is not None:
        add("max_length", present & (text.str.len() > spec.max_length),
            f"longer than {spec.max_length} characters")  # fmt: skip
    return out


# --------------------------------------------------------------------------- table checks
def _check_violations(df: pd.DataFrame, typed: dict[str, pd.Series], layout: Layout):
    for check in layout.checks:
        kind, args = next(iter(check.items()))

        if kind == "unique":
            cols = list(args)
            dup = df.duplicated(subset=cols, keep=False) & ~df[cols].apply(_is_blank).all(axis=1)
            if dup.any():
                yield Violation("unique", ",".join(cols), _line_numbers(dup),
                                f"duplicate value for ({', '.join(cols)})")  # fmt: skip

        elif kind == "compare":
            left, right = typed[args["left"]], typed[args["right"]]
            both = left.notna() & right.notna()
            bad = both & ~OPS[args["op"]](left, right)
            if bad.any():
                rule = f"{args['left']} {args['op']} {args['right']}"
                yield Violation("compare", args["left"], _line_numbers(bad), f"expected {rule}")

        elif kind == "consistent":
            key, value = list(args["key"]), args["value"]
            n_values = df.groupby(key, dropna=False)[value].transform("nunique")
            bad = n_values > 1
            if bad.any():
                msg = f"more than one '{value}' for the same ({', '.join(key)})"
                yield Violation("consistent", value, _line_numbers(bad), msg)

        elif kind == "required_if":
            col, when = args["column"], args["when"]
            trigger = df[when["column"]].astype(str).str.strip()
            values = when["in"] if "in" in when else [when["equals"]]
            active = trigger.isin([str(v) for v in values])
            bad = active & _is_blank(df[col])
            if bad.any():
                yield Violation("required_if", col, _line_numbers(bad),
                                f"required when {when['column']} in {values}")  # fmt: skip


# --------------------------------------------------------------------------- entry points
def validate_frame(df: pd.DataFrame, layout: Layout) -> list[Violation]:
    """Validate a DataFrame of strings (headers already normalized)."""
    violations: list[Violation] = []
    present_cols = set(df.columns)

    missing = [c for c in layout.columns if c not in present_cols]
    for col in missing:
        violations.append(Violation("missing_column", col, [], "column not found in file"))
    if not layout.file.allow_extra_columns:
        for col in sorted(present_cols - set(layout.columns)):
            violations.append(Violation("unexpected_column", col, [], "column not in layout"))

    typed: dict[str, pd.Series] = {}
    for name, spec in layout.columns.items():
        if name in present_cols:
            violations.extend(_column_violations(df[name], spec, layout))
            typed[name] = parse_column(df[name], spec, layout)

    # table-level checks need every referenced column to exist
    if not missing:
        violations.extend(_check_violations(df, typed, layout))
    return violations


def read_file(path: str | Path, layout: Layout) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep=layout.file.delimiter,
        dtype=str,
        keep_default_na=False,
        encoding=layout.file.encoding,
    )
    df.columns = [normalize_header(c, layout.file.header_case) for c in df.columns]
    return df


def validate_file(path: str | Path, layout: Layout) -> Report:
    df = read_file(path, layout)
    return Report(str(path), layout.name, len(df), validate_frame(df, layout))
