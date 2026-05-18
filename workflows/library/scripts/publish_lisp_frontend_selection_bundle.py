#!/usr/bin/env python3
"""Publish the authoritative selector bundle path as structured state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path.cwd()
ALLOWED_STATUSES = {"SELECT_BACKLOG_ITEM", "DRAFT_DESIGN_GAP", "DONE", "BLOCKED"}


def _safe_relpath(value: str, *, under: str, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    if must_exist and not (REPO_ROOT / path).is_file():
        raise SystemExit(f"Required file does not exist: {value}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    selection_rel = _safe_relpath(args.selection_path, under="state", must_exist=True)
    selection = json.loads((REPO_ROOT / selection_rel).read_text(encoding="utf-8"))
    status = selection.get("selection_status")
    if status not in ALLOWED_STATUSES:
        raise SystemExit(f"Invalid selection_status: {status}")

    output_rel = _safe_relpath(args.output, under="state")
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"selection_bundle_path": selection_rel.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
