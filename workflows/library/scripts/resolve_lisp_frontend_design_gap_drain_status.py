#!/usr/bin/env python3
"""Resolve a design-gap draft branch drain status after architecture validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()


def _safe_relpath(value: str, *, under: str, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    if must_exist and not (REPO_ROOT / path).exists():
        raise SystemExit(f"Required path does not exist: {value}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture-validation-path", required=True)
    parser.add_argument("--work-item-drain-status-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    validation_rel = _safe_relpath(args.architecture_validation_path, under="state", must_exist=True)
    output_rel = _safe_relpath(args.output, under="state")
    validation = _load_json(REPO_ROOT / validation_rel)
    architecture_status = str(validation.get("architecture_validation_status") or "").strip()
    reason = str(validation.get("reason") or "").strip()

    if architecture_status == "VALID":
        status_rel = _safe_relpath(args.work_item_drain_status_path, under="state", must_exist=True)
        drain_status = (REPO_ROOT / status_rel).read_text(encoding="utf-8").strip()
        if drain_status not in {"CONTINUE", "DONE", "BLOCKED"}:
            raise SystemExit(f"Unsupported work-item drain status: {drain_status!r}")
    elif architecture_status in {"INVALID", "BLOCKED"}:
        drain_status = "BLOCKED"
    else:
        raise SystemExit(f"Unsupported architecture_validation_status: {architecture_status!r}")

    _write_json(
        REPO_ROOT / output_rel,
        {
            "drain_status": drain_status,
            "architecture_validation_status": architecture_status,
            "reason": reason,
            "architecture_validation_path": validation_rel.as_posix(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
