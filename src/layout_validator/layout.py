"""Layout specification: what a valid file looks like, declared in YAML.

Example::

    name: receivables
    file: { delimiter: ";", decimal: ",", header_case: snake }
    columns:
      contract_id:  { required: true }
      face_value:   { type: decimal, required: true, min: 0.01 }
      due_date:     { type: date, format: "%d/%m/%Y" }
      debtor_doc:   { type: tax_id }
    checks:
      - unique: [contract_id, installment]
      - compare: { left: purchase_price, op: "<=", right: face_value }
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

COLUMN_TYPES = {"string", "integer", "decimal", "date", "tax_id"}
CHECK_TYPES = {"unique", "compare", "consistent", "required_if"}
COMPARE_OPS = {"<", "<=", ">", ">=", "==", "!="}
HEADER_CASES = {"as_is", "lower", "snake"}


class LayoutError(ValueError):
    """The layout file itself is invalid."""


@dataclass(frozen=True)
class FileOptions:
    delimiter: str = ","
    decimal: str = "."
    thousands: str | None = None
    encoding: str = "utf-8"
    header_case: str = "as_is"
    allow_extra_columns: bool = True


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    type: str = "string"
    required: bool = False
    format: str = "%Y-%m-%d"  # dates
    tax_id_kind: str = "any"  # cpf | cnpj | any
    min: float | None = None
    max: float | None = None
    enum: list[str] | None = None
    pattern: str | None = None
    max_length: int | None = None
    description: str | None = None


@dataclass(frozen=True)
class Layout:
    name: str
    file: FileOptions
    columns: dict[str, ColumnSpec]
    checks: list[dict[str, Any]] = field(default_factory=list)
    description: str | None = None


def _known(cls) -> set[str]:
    return {f.name for f in fields(cls)}


def _reject_unknown(where: str, given: dict, allowed: set[str]) -> None:
    unknown = set(given) - allowed
    if unknown:
        raise LayoutError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(allowed)}")


def parse_layout(raw: dict[str, Any]) -> Layout:
    """Build a Layout from a dict, failing loudly on typos instead of ignoring them."""
    _reject_unknown("layout", raw, {"name", "description", "file", "columns", "checks"})
    if "name" not in raw or "columns" not in raw:
        raise LayoutError("layout needs at least 'name' and 'columns'")

    file_raw = raw.get("file") or {}
    _reject_unknown("file", file_raw, _known(FileOptions))
    file = FileOptions(**file_raw)
    if file.header_case not in HEADER_CASES:
        raise LayoutError(f"file.header_case must be one of {sorted(HEADER_CASES)}")

    columns: dict[str, ColumnSpec] = {}
    for name, spec in (raw["columns"] or {}).items():
        spec = spec or {}
        _reject_unknown(f"column '{name}'", spec, _known(ColumnSpec) - {"name"})
        col = ColumnSpec(name=name, **spec)
        if col.type not in COLUMN_TYPES:
            raise LayoutError(f"column '{name}': type must be one of {sorted(COLUMN_TYPES)}")
        if col.tax_id_kind not in {"cpf", "cnpj", "any"}:
            raise LayoutError(f"column '{name}': tax_id_kind must be cpf, cnpj or any")
        columns[name] = col

    checks = raw.get("checks") or []
    for i, check in enumerate(checks):
        if not isinstance(check, dict) or len(check) != 1:
            raise LayoutError(f"checks[{i}] must be a single-key mapping, e.g. '- unique: [a, b]'")
        kind = next(iter(check))
        if kind not in CHECK_TYPES:
            raise LayoutError(
                f"checks[{i}]: unknown check '{kind}'; allowed: {sorted(CHECK_TYPES)}"
            )
        if kind == "compare" and check[kind].get("op") not in COMPARE_OPS:
            raise LayoutError(f"checks[{i}]: compare.op must be one of {sorted(COMPARE_OPS)}")
        referenced = _referenced_columns(kind, check[kind])
        missing = [c for c in referenced if c not in columns]
        if missing:
            raise LayoutError(f"checks[{i}] ({kind}) references undeclared column(s) {missing}")

    return Layout(raw["name"], file, columns, checks, raw.get("description"))


def _referenced_columns(kind: str, args: Any) -> list[str]:
    if kind == "unique":
        return list(args)
    if kind == "compare":
        return [args["left"], args["right"]]
    if kind == "consistent":
        return [*args["key"], args["value"]]
    if kind == "required_if":
        return [args["column"], args["when"]["column"]]
    return []


def load_layout(path: str | Path) -> Layout:
    with open(path, encoding="utf-8") as f:
        return parse_layout(yaml.safe_load(f))
