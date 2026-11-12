"""Durable allocation of one evaluated effect attempt."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.workflow.evaluated.attempt_processes import attempt_process_alive
from orchestrator.workflow.evaluated.closure import resolve_command_evidence
from orchestrator.workflow.evaluated.memo import (
    _DYNAMIC_INDEX,
    JournalEntry,
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
    before_failure=None,
    after_started=None,
) -> WorkspaceFiles:
    """Synchronize ``started`` (then call ``after_started``) before creating and pinning its attempt directory."""
    attempt_dir = Path(started_record["result_path"]).parent
    append_record(memo_path, started_record, run_files=run_files, checked_authority=checked_authority)
    if after_started is not None:
        after_started()
    try:
        return run_files.mkdir_exclusive(attempt_dir)
    except OSError as exc:
        code = (
            "effect_attempt_path_exists"
            if isinstance(exc, FileExistsError)
            else "effect_attempt_allocation_failed"
        )
        failure = MemoError(code, str(exc))
        failure.exit_info = {"errno": exc.errno}
        if before_failure is not None:
            before_failure(failure)
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


def closure_after_failure(attempt) -> str | None:
    """`unchanged` when no process of a failed host command is alive and its declared files still equal its
    `started` evidence, else `changed`.

    The liveness check comes first: once no process of the attempt is alive, none can write afterwards, so the
    rehash that follows (as the precommit check does, C4) is final. A rehash that cannot complete counts as
    `changed`, so its retry still needs the author's acceptance. None for every other effect and inside a
    confined child.
    """
    node = attempt.node
    if node["class"] != "command" or attempt.confined is not None:
        return None
    if attempt_process_alive(attempt.authority.run_root.name, attempt.result_path):
        return "changed"
    try:
        after = resolve_command_evidence(node["command"], node["closure"], workspace_root=attempt.workspace,
                                         prior=attempt.implementation_files, launch_cwd=attempt.launch_cwd)
    except Exception:  # noqa: BLE001 - any failure to prove the files unchanged is `changed`, never a lost `failed` row
        return "changed"
    return "unchanged" if after == attempt.implementation_files else "changed"


def proven_unchanged(snapshot: MemoSnapshot, start: JournalEntry) -> bool:
    """The start's attempt failed with `closure: unchanged`, outside a parallel map (§8.1)."""
    row = start.data
    # ponytail: every parallel-map item is unproven (Phase 3a decision 7), since a sibling may write the script
    # after the failure; relax to "no sibling record follows the failure" once a probe shows it is safe.
    if "par-map:" in row["identity"]:
        return False
    return any(entry.data["record"] == "failed" and entry.data.get("identity") == row["identity"]
               and entry.data.get("attempt") == row["attempt"] and entry.data.get("closure") == "unchanged"
               for entry in reversed(snapshot.entries))


def retry_change_admitted(snapshot: MemoSnapshot | None, baseline: JournalEntry, accept_changes: bool) -> bool:
    """§8.1: changed retry evidence is accepted after a proven-clean failure, or by `resume --accept-changes`."""
    return accept_changes or (snapshot is not None and proven_unchanged(snapshot, baseline))


def unproven_command_retries(snapshot: MemoSnapshot, site_classes: Mapping[str, str]) -> list[str]:
    """Uncommitted host commands with a retry baseline that no clean failure covers: what the flag accepts."""
    def is_command(identity):
        return (site_classes.get(identity) or site_classes.get(_DYNAMIC_INDEX.sub("[*]", identity))) == "command"
    return [identity for identity, start in snapshot.latest_starts.items()
            if identity not in snapshot.active_commits and is_command(identity)
            and _retry_baseline(snapshot, identity, start) is not None and not proven_unchanged(snapshot, start)]


def changed_files_note(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    """` changed_files=<names>` for the `[effect_rerun]` line of a retry whose declared files changed."""
    names = sorted({json.loads(key)[1] for key in set(before) | set(after) if before.get(key) != after.get(key)})
    return f" changed_files={','.join(names)}" if names else ""


def _retry_baseline(
    snapshot: MemoSnapshot,
    identity: str,
    latest_start: JournalEntry | None,
) -> JournalEntry | None:
    if latest_start is None:
        return None
    row = latest_start.data
    commit = next(
        (
            entry
            for entry in reversed(snapshot.entries)
            if entry.data.get("record") == "committed"
            and entry.data.get("identity") == identity
            and entry.data.get("attempt") == row["attempt"]
        ),
        None,
    )
    if commit is not None and any(
        entry.offset > commit.offset
        and entry.data.get("record") == "invalidated"
        and entry.data.get("from_commit", commit.offset + 1) <= commit.offset
        for entry in snapshot.entries
    ):
        return None
    return latest_start
