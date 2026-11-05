"""Brazilian taxpayer IDs: CPF (individuals, 11 digits) and CNPJ (companies, 14 digits)."""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D")
_CNPJ_W1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CNPJ_W2 = [6, *_CNPJ_W1]


def _check_digit(digits: list[int], weights: list[int]) -> int:
    remainder = sum(d * w for d, w in zip(digits, weights, strict=True)) % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cpf(value: str) -> bool:
    d = [int(c) for c in _NON_DIGITS.sub("", value or "")]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    return d[9] == _check_digit(d[:9], list(range(10, 1, -1))) and d[10] == _check_digit(
        d[:10], list(range(11, 1, -1))
    )


def is_valid_cnpj(value: str) -> bool:
    d = [int(c) for c in _NON_DIGITS.sub("", value or "")]
    if len(d) != 14 or len(set(d)) == 1:
        return False
    return d[12] == _check_digit(d[:12], _CNPJ_W1) and d[13] == _check_digit(d[:13], _CNPJ_W2)


def is_valid_tax_id(value: str, kind: str = "any") -> bool:
    """Validate a CPF, a CNPJ, or either (`kind` = "cpf" | "cnpj" | "any").

    Numeric exports often drop leading zeros, so a short value is left-padded
    before validation.
    """
    digits = _NON_DIGITS.sub("", value or "")
    if not digits:
        return False
    if kind == "cpf":
        return is_valid_cpf(digits.zfill(11))
    if kind == "cnpj":
        return is_valid_cnpj(digits.zfill(14))
    return (len(digits) <= 11 and is_valid_cpf(digits.zfill(11))) or is_valid_cnpj(digits.zfill(14))
