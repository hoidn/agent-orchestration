#!/usr/bin/env python3
"""Build a Lisp frontend backlog manifest and expose its path in the bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_neurips_backlog_manifest import _build_manifest_entries


REPO_ROOT = Path.cwd()


def _safe_relpath(value: str, *, under: str | None = None) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backlog-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    backlog_rel = _safe_relpath(args.backlog_root, under="docs/backlog")
    backlog_root = (REPO_ROOT / backlog_rel).resolve()
    if not backlog_root.is_dir():
        raise SystemExit(f"Backlog root does not exist: {backlog_rel}")
    try:
        normalized_backlog_rel = backlog_root.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise SystemExit(f"Backlog root must live under repo root: {backlog_root}") from exc

    output_rel = _safe_relpath(args.output, under="state")
    entries, invalid_entries = _build_manifest_entries(sorted(backlog_root.glob("*.md")))
    payload = {
        "manifest_version": 2,
        "manifest_path": output_rel.as_posix(),
        "backlog_root": normalized_backlog_rel.as_posix(),
        "active_count": len(entries),
        "total_active_count": len(entries) + len(invalid_entries),
        "invalid_count": len(invalid_entries),
        "items": entries,
        "invalid_items": invalid_entries,
    }
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
