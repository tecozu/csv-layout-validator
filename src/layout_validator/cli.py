"""`layout-validator FILE [FILE ...] --layout LAYOUT.yaml`

Exit codes: 0 = all files valid, 1 = violations found, 2 = usage/layout error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from layout_validator.layout import LayoutError, load_layout
from layout_validator.report import RENDERERS
from layout_validator.validator import validate_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="layout-validator", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    p.add_argument("files", nargs="+", type=Path, help="files (or folders) to validate")
    p.add_argument("-l", "--layout", required=True, type=Path, help="layout YAML")
    p.add_argument("-f", "--format", choices=sorted(RENDERERS), default="text")
    p.add_argument("--max-rows", type=int, default=10, help="line numbers shown per violation")
    p.add_argument("--warn-only", action="store_true", help="always exit 0 (report only)")
    args = p.parse_args(argv)

    try:
        layout = load_layout(args.layout)
    except (LayoutError, OSError) as exc:
        print(f"layout error: {exc}", file=sys.stderr)
        return 2

    files = [
        f for path in args.files for f in (sorted(path.glob("*.csv")) if path.is_dir() else [path])
    ]
    if not files:
        print("no files to validate", file=sys.stderr)
        return 2

    all_ok = True
    for f in files:
        report = validate_file(f, layout)
        all_ok &= report.ok
        print(RENDERERS[args.format](report, max_rows=args.max_rows))
    return 0 if all_ok or args.warn_only else 1


if __name__ == "__main__":
    sys.exit(main())
