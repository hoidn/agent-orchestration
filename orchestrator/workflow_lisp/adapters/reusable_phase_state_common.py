"""Shared helpers for the certified command adapters (now only `validate_review_findings_v1`)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from ..._common.io_atomic import atomic_write_text


def logical_workspace_root() -> Path:
    """Return the validated logical root, defaulting to the resolved cwd."""
    raw_root = os.environ.get("ORCHESTRATOR_WORKSPACE_ROOT", "")
    if not raw_root:
        return Path.cwd().resolve()
    root = Path(raw_root)
    if not root.is_absolute():
        raise ValueError("logical_workspace_root_invalid")
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("logical_workspace_root_invalid") from error
    if not root.is_dir():
        raise ValueError("logical_workspace_root_invalid")
    return root


def emit_structured_result(payload: Mapping[str, object]) -> int:
    """Emit structured adapter output to the runtime-owned bundle path when set."""

    logical_workspace_root()
    logical_root_active = bool(
        os.environ.get("ORCHESTRATOR_WORKSPACE_ROOT", "")
    )
    bundle_path_raw = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "")
    if not logical_root_active:
        bundle_path_raw = bundle_path_raw.strip()
    if logical_root_active:
        bundle_path = Path(bundle_path_raw)
        if (
            not bundle_path_raw
            or not bundle_path.is_absolute()
            or "\0" in bundle_path_raw
            or os.path.normpath(bundle_path_raw) != bundle_path_raw
        ):
            raise ValueError("resume_state_path_unsafe")
    elif bundle_path_raw:
        bundle_relpath = workspace_relpath(bundle_path_raw)
        bundle_path = Path(bundle_relpath)
    else:
        bundle_path = None
    if bundle_path is not None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(bundle_path, json.dumps(payload, sort_keys=True))
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


def workspace_relpath(path_value: object) -> str:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("resume_state_contract_invalid")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("resume_state_path_unsafe")
    return path_value
