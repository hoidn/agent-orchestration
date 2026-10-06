"""Public adapter for append-only invalidation of evaluated effect commits."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any
from orchestrator.run_lock import ReservedRunRootError

from orchestrator.cli.commands.resume import _has_authority_header
from orchestrator.cli.commands.run import _state_root_symlink_error
from orchestrator.workflow.evaluated.authority import (
    PROFILE,
    SCHEMA_VERSION,
    RunAuthorityError,
    _read_header_json,
    load_run_authority,
    _require_retained_root,
)
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import MemoError, invalidate_suffix, memo_writer_lock
from orchestrator.workflow.evaluated.views import has_evaluated_authority
from orchestrator.workflow.pure_result_replay import DERIVED_PURE_REPLAY_PROFILE


def invalidate_run(run_id: str, identity: str, state_dir: str | None = None) -> dict[str, Any]:
    """Validate stored evaluated authority and append one invalidation row under its lock."""
    workspace = Path.cwd()
    if state_dir is None:
        root_error = _state_root_symlink_error(workspace)
        if root_error is not None:
            raise MemoError("memo_inconsistent", root_error)
    if state_dir:
        try:
            runs_root = Path(state_dir).expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise MemoError("memo_inconsistent", f"state directory cannot be resolved: {exc}") from exc
    else:
        runs_root = workspace / ".orchestrate" / "runs"
    run_root = runs_root / run_id
    if not run_root.exists():
        raise MemoError("memo_inconsistent", f"run directory not found: {run_root}")
    _refuse_without_authority(run_root)

    with memo_writer_lock(run_root) as fd:
        run_files = WorkspaceFiles(run_root, root_fd=fd)
        try:
            return _invalidate_retained(run_root, identity, run_files)
        finally:
            run_files.close()


def _refuse_without_authority(run_root: Path) -> None:
    """Refuse a run lacking evaluated authority before the lock can create run.lock."""
    if os.path.realpath(run_root) != os.path.abspath(run_root):
        raise MemoError("memo_inconsistent", f"run root passes through a symbolic link: {run_root}")
    if _has_authority_header(run_root, None):
        return
    if (run_root / "state.json").exists() and not has_evaluated_authority(run_root):
        raise MemoError("invalidate_profile_unsupported", "flat-route run profile cannot be invalidated")
    raise RunAuthorityError("evaluated run authority header is missing")


def _invalidate_retained(run_root, identity, run_files):
    _require_retained_root(run_files)
    header = _read_header_json(run_root / "run.json", run_files)
    if not isinstance(header, dict):
        raise RunAuthorityError("run header is not an object")
    profile = header.get("result_persistence_profile")
    schema = header.get("schema_version")
    if schema == "2.1" and profile in (None, DERIVED_PURE_REPLAY_PROFILE):
        raise MemoError("invalidate_profile_unsupported", "historical run profile cannot be invalidated")
    if profile != PROFILE or schema != SCHEMA_VERSION:
        raise RunAuthorityError("unsupported evaluated run authority profile or schema")
    authority = load_run_authority(run_root, header=header, run_files=run_files)
    _require_retained_root(run_files)
    return invalidate_suffix(
        authority.memo_path,
        identity,
        site_classes(authority.program),
        run_files=run_files,
        checked_authority=authority,
    )


def invalidate_command(
    run_id: str,
    identity: str,
    *,
    state_dir: str | None = None,
) -> int:
    """Run public invalidation and print its one-row JSON result or refusal diagnostic."""
    try:
        record = invalidate_run(run_id, identity, state_dir=state_dir)
    except (OSError, UnicodeError, ValueError, ReservedRunRootError) as exc:
        code = getattr(exc, "code", "memo_inconsistent")
        detail = getattr(exc, "detail", str(exc))
        print(f"[{code}] {detail}", file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=True, sort_keys=True))
    return 0
