"""Durable allocation of one evaluated effect attempt."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.workflow.evaluated.memo import (
    MemoError,
    MemoSnapshot,
    append_record,
)
from orchestrator.workflow.workspace_files import WorkspaceFiles


def attempt_paths(snapshot: MemoSnapshot, identity: str) -> tuple[int, str, str]:
    """Return the next ordinal and its fixed directory/result paths."""
    latest = snapshot.latest_starts.get(identity)
    ordinal = 1 if latest is None else latest.data["attempt"] + 1
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    directory = f"effects/{digest}/attempt-{ordinal}"
    return ordinal, directory, f"{directory}/result.json"


def allocate_attempt(
    run_files: WorkspaceFiles,
    memo_path: Path,
    started_record: Mapping[str, Any],
    *,
    checked_authority=None,
) -> WorkspaceFiles:
    """Synchronize ``started`` before creating and pinning its attempt directory."""
    attempt_dir = Path(started_record["result_path"]).parent
    append_record(memo_path, started_record, run_files=run_files, checked_authority=checked_authority)
    try:
        return run_files.mkdir_exclusive(attempt_dir)
    except OSError as exc:
        code = (
            "effect_attempt_path_exists"
            if isinstance(exc, FileExistsError)
            else "effect_attempt_allocation_failed"
        )
        append_record(
            memo_path,
            {
                "record": "failed",
                "identity": started_record["identity"],
                "attempt": started_record["attempt"],
                "code": code,
                "exit_info": {"errno": exc.errno},
            },
            run_files=run_files,
            checked_authority=checked_authority,
        )
        raise MemoError(code, str(exc)) from exc
