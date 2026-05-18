#!/usr/bin/env python3
"""Build an index of existing Lisp frontend implementation architectures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path.cwd()


def _safe_relpath(value: str, *, under: str | None = None) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def _heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps")
    parser.add_argument("--exclude", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--bundle", required=True)
    args = parser.parse_args()

    root_rel = _safe_relpath(args.root, under="docs/plans")
    output_rel = _safe_relpath(args.output, under="state")
    bundle_rel = _safe_relpath(args.bundle, under="state")
    exclude_rel = _safe_relpath(args.exclude, under="docs/plans") if args.exclude else None

    root = REPO_ROOT / root_rel
    docs: list[Path] = []
    if root.is_dir():
        for path in sorted(root.glob("*/implementation_architecture.md")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if exclude_rel is not None and rel == exclude_rel.as_posix():
                continue
            docs.append(path)

    lines = [
        "# Existing Lisp Frontend Implementation Architectures",
        "",
        "This index is generated before drafting a new implementation architecture.",
        "Use it to keep the new slice coherent with prior implementation slices.",
        "",
    ]
    if not docs:
        lines.extend(["No prior implementation architecture documents were found.", ""])
    else:
        lines.extend(
            [
                "Review these documents before drafting the new slice:",
                "",
            ]
        )
        for path in docs:
            rel = path.relative_to(REPO_ROOT).as_posix()
            lines.append(f"- `{rel}`: {_heading(path)}")
        lines.append("")

    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    payload = {
        "architecture_index_path": output_rel.as_posix(),
        "existing_architecture_count": len(docs),
        "existing_architecture_paths": [path.relative_to(REPO_ROOT).as_posix() for path in docs],
    }
    bundle_path = REPO_ROOT / bundle_rel
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
