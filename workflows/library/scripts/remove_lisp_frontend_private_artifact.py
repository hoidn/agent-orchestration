#!/usr/bin/env python3
"""Remove a generated private workflow artifact before provider selection."""

from __future__ import annotations

import argparse
from pathlib import Path


REPO_ROOT = Path.cwd()


def _safe_relpath(value: str, *, under: str) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--under", default="state")
    args = parser.parse_args()

    path = REPO_ROOT / _safe_relpath(args.path, under=args.under)
    path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
