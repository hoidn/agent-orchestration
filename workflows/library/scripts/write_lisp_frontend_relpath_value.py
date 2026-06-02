#!/usr/bin/env python3
"""Write a validated repo-relative path value to a pointer file."""

from __future__ import annotations

import argparse
from pathlib import Path


def _safe_relpath(value: str, *, under: str) -> Path:
    path = Path(value.strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    under_path = Path(under)
    if path.parts[: len(under_path.parts)] != under_path.parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value", required=True)
    parser.add_argument("--under", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    value = _safe_relpath(args.value, under=args.under)
    output = _safe_relpath(args.output, under="state")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(value.as_posix() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
