"""Render a Report as text (terminal), JSON (machines) or Markdown (PR comments)."""

from __future__ import annotations

import json

from layout_validator.validator import Report


def _rows(rows: list[int], limit: int) -> str:
    shown = ", ".join(map(str, rows[:limit]))
    return shown + (f", ... (+{len(rows) - limit})" if len(rows) > limit else "")


def to_text(r: Report, max_rows: int = 10) -> str:
    head = f"{r.file}  [layout: {r.layout}]  {r.row_count} rows"
    if r.ok:
        return f"PASS  {head}"
    lines = [f"FAIL  {head}  ({r.invalid_rows} invalid rows, {len(r.violations)} violations)"]
    for v in r.violations:
        where = f"{v.column}: " if v.column else ""
        lines.append(f"  - [{v.rule}] {where}{v.message}")
        if v.rows:
            lines.append(f"      lines: {_rows(v.rows, max_rows)}")
    return "\n".join(lines)


def to_markdown(r: Report, max_rows: int = 10) -> str:
    icon = "✅" if r.ok else "❌"
    summary = f"{r.row_count} rows · {r.invalid_rows} invalid rows · {len(r.violations)} violations"
    out = [f"### {icon} `{r.file}` — layout `{r.layout}`", "", summary]
    if not r.ok:
        out += ["", "| Rule | Column | Problem | Count | Lines |", "|---|---|---|---:|---|"]
        for v in r.violations:
            lines = _rows(v.rows, max_rows)
            out.append(f"| `{v.rule}` | `{v.column or ''}` | {v.message} | {v.count} | {lines} |")
    return "\n".join(out)


def to_json(r: Report) -> str:
    return json.dumps(r.to_dict(), ensure_ascii=False, indent=2)


RENDERERS = {"text": to_text, "markdown": to_markdown, "json": lambda r, **_: to_json(r)}
