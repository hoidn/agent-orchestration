"""Readonly reconstruction of evaluated run views from checked authority."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from orchestrator._common.safe_tree import SafeTreeRejectionError

from orchestrator.run_lock import ReservedRunRootError, run_writer_active
from orchestrator.workflow.evaluated.authority import (
    HEADER_FILENAME, MEMO_FILENAME, PROGRAM_FILENAME, PROFILE, SCHEMA_VERSION, RunAuthorityError,
    load_run_authority_from_bytes, _require_retained_root, workspace_result_locator,
)
from orchestrator.workflow.evaluated.machine import evaluate_closed_program, site_classes
from orchestrator.workflow.evaluated.memo import MemoError, _DYNAMIC_INDEX, reduce_memo
from orchestrator.workflow.evaluated.values import EvaluatedValueError, coerce_evaluated_value
from orchestrator.workflow.pure_expr import PureExprEvaluationError
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles


def has_evaluated_authority(run_root: Path, *, run_files: WorkspaceFiles | None = None) -> bool:
    """Select checked loading from authority or a view hint, never trust the view."""
    names = (HEADER_FILENAME, PROGRAM_FILENAME, MEMO_FILENAME)
    if run_files is not None:
        return any(_authority_sibling_present(run_files, name) for name in names) or _evaluated_view_hint(run_files)
    if any(os.path.lexists(Path(run_root) / name) for name in names):
        return True
    try:
        files = WorkspaceFiles(run_root)
    except (OSError, ValueError, SafeTreeRejectionError):
        return False
    try:
        return _evaluated_view_hint(files)
    finally:
        files.close()


def _authority_sibling_present(files, name):
    try:
        os.stat(name, dir_fd=files.root_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _evaluated_view_hint(files):
    try:
        state = json.loads(files.read("state.json"))
    except (OSError, ValueError, RecursionError):
        return False
    return isinstance(state, dict) and (
        state.get("schema_version") == SCHEMA_VERSION or state.get("result_persistence_profile") == PROFILE)


class _MissingCommit(Exception):
    def __init__(self, identity: str):
        self.identity = identity


def _replay(authority, snapshot):
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    consumed = 0

    def handle(node, operands, identity, _owner, _reader):
        nonlocal consumed
        commit = snapshot.active_commits.get(identity)
        if commit is None:
            if consumed != len(commits):
                raise MemoError("memo_inconsistent", "an active commit is unreachable")
            raise _MissingCommit(identity)
        if consumed >= len(commits) or commits[consumed].offset != commit.offset:
            raise MemoError("memo_inconsistent", "active commits are not reachable in journal order")
        consumed += 1
        return _committed_value(authority, node, commit, identity)

    try:
        value = evaluate_closed_program(
            authority.program, authority.header["bound_inputs"],
            effect_handler=handle, run_id=authority.header["run_id"],
        ).json_value()
    except _MissingCommit as boundary:
        return None, boundary.identity, False
    except EvaluatedValueError as exc:
        if consumed != len(commits) or snapshot.pending_starts:
            raise MemoError("memo_inconsistent", str(exc)) from exc
        return None, None, False
    if consumed != len(commits) or snapshot.pending_starts:
        raise MemoError("memo_inconsistent", "evaluated halt leaves unreachable effect evidence")
    return value, None, True


def _committed_value(authority, node, commit, identity):
    try:
        return coerce_evaluated_value(
            commit.data["value"], node["result"],
            dependencies=(*commit.data["depends_on"], identity),
            committed_result_path=workspace_result_locator(authority.header, commit.data["result_path"]),
            context=f"committed {node['class']} result",
        )
    except PureExprEvaluationError as exc:
        raise MemoError("memo_inconsistent", str(exc)) from exc


def _checked_terminal(snapshot, value, halted):
    terminal = snapshot.terminal
    if terminal is not None and terminal.data["outcome"] == "completed":
        if not halted or canonical_sha256(value) != canonical_sha256(terminal.data["value"]):
            raise MemoError("memo_inconsistent", "completed terminal differs from evaluated halt")
    return terminal


def _timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _status(snapshot, halted, writer_active):
    if snapshot.terminal is not None:
        return snapshot.terminal.data["outcome"]
    if not writer_active:
        return "interrupted"
    return "settling" if halted else "running"


class ViewPublicationError(OSError):
    """The memo is already durable; stop without publishing another failure."""

    code = "view_write_failed"


def publish_evaluated_view(authority, entry):
    """Publish exactly the synchronized prefix using the writer's borrowed owner."""
    try:
        files = authority.run_files
        snapshot = reduce_memo(files.read(MEMO_FILENAME)[:entry.end], site_classes(authority.program))
        if snapshot.complete_bytes != entry.end or snapshot.entries[-1] != entry:
            raise MemoError("memo_inconsistent", "published prefix differs from synchronized append")
        value, next_effect, halted = _replay(authority, snapshot)
        terminal = _checked_terminal(snapshot, value, halted)
        view = _view(authority, snapshot, terminal, next_effect, halted, True)
        _require_retained_root(files)
        files.write_atomic("state.json", json.dumps(view, ensure_ascii=False, allow_nan=False).encode() + b"\n")
    except (OSError, OverflowError, TypeError, ValueError, ReservedRunRootError) as exc:
        raise ViewPublicationError(f"derived view publication failed at memo byte {entry.end}: {exc}") from exc


def load_evaluated_view(run_root: Path, *, run_files: WorkspaceFiles | None = None) -> dict[str, Any]:
    """Capture one prefix and reconstruct it without source IO or mutation."""
    root = Path(os.path.abspath(os.fspath(run_root)))
    files = run_files if run_files is not None else WorkspaceFiles(root)
    try:
        authority = load_run_authority_from_bytes(
            root, header_bytes=files.read(HEADER_FILENAME), program_bytes=files.read(PROGRAM_FILENAME),
        )
        snapshot = reduce_memo(files.read(MEMO_FILENAME), site_classes(authority.program))
        value, next_effect, halted = _replay(authority, snapshot)
        terminal = _checked_terminal(snapshot, value, halted)
        active = run_writer_active(root, root_fd=files.root_fd)
        return _view(authority, snapshot, terminal, next_effect, halted, active)
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        if isinstance(exc, (MemoError, RunAuthorityError)):
            raise
        raise MemoError("memo_inconsistent", str(exc)) from exc
    finally:
        if run_files is None:
            files.close()


def _view(authority, snapshot, terminal, next_effect, halted, active):
    header = authority.header
    view = {key: header[key] for key in (
        "schema_version", "result_persistence_profile", "run_id", "workflow_file",
        "workflow_checksum", "started_at", "bound_inputs",
    )}
    times = [entry.data["time"] for entry in snapshot.entries if "time" in entry.data]
    view.update(updated_at=_timestamp(times[-1]) if times else header["started_at"],
                status=_status(snapshot, halted, active), memo_offset=snapshot.complete_bytes,
                steps=_effect_rows(snapshot, site_classes(authority.program)), next_effect=next_effect)
    in_flight = [*snapshot.pending_starts.values(), *snapshot.unsettled_coordinators.values()]
    view["current_step"] = None
    if in_flight:
        row = max(in_flight, key=lambda entry: entry.offset).data
        view["current_step"] = {"name": row["identity"], "identity": row["identity"],
                                "attempt": row["attempt"], "result_path": row["result_path"]}
        view["next_effect"] = None
    view["error"] = None
    view["workflow_outputs"] = None
    if terminal is not None:
        if terminal.data["outcome"] == "completed":
            view["workflow_outputs"] = terminal.data["value"]
        else:
            view["error"] = {"type": terminal.data["code"], "code": terminal.data["code"],
                             "message": terminal.data["message"]}
    return view


def _effect_rows(snapshot, classes):
    rows = {}
    for identity, start in snapshot.latest_starts.items():
        row = start.data
        kind = classes.get(identity) or classes[_DYNAMIC_INDEX.sub("[*]", identity)]
        rows[identity] = {"name": identity, "identity": identity, "status": "running", "effect_class": kind,
                          "attempt": row["attempt"], "result_path": row["result_path"],
                          "started_at": _timestamp(row["time"])}
    for entry in snapshot.entries:
        row = entry.data
        identity = row.get("identity")
        if identity not in rows or row.get("attempt") != rows[identity]["attempt"]:
            continue
        _update_effect_row(rows[identity], row, snapshot)
    return rows


def _update_effect_row(target, row, snapshot):
    kind = row["record"]
    if kind == "committed":
        active = snapshot.active_commits.get(row["identity"])
        target.update(status="completed" if active is not None else "invalidated",
                      effect_class=row["effect_class"], value=row["value"], output=row["value"],
                      completed_at=_timestamp(row["time"]), result_digest=row["result_digest"])
        target["duration_ms"] = int((row["time"] - snapshot.latest_starts[row["identity"]].data["time"]) * 1000)
        if (row["identity"], row["attempt"]) in snapshot.unsettled_coordinators:
            target["status"] = "settling"
    elif kind == "failed":
        target.update(status="failed", error={"type": row["code"], "code": row["code"],
                                               "exit_info": row["exit_info"]})


def report_snapshot(view: dict[str, Any], run_root: Path) -> dict[str, Any]:
    """Adapt real effect rows to the existing public report envelope."""
    run = {key: value for key, value in view.items() if key != "steps"}
    run["run_root"] = str(run_root)
    steps = [{**row, "kind": row.get("effect_class", "unknown"),
              "output": {"output_preview": repr(row.get("output")),
                         "duration_ms": row.get("duration_ms")}}
             for row in view["steps"].values()]
    progress = {status: sum(row["status"] == status for row in steps)
                for status in ("completed", "running", "failed", "pending", "skipped", "settling", "invalidated")}
    progress["total"] = len(steps)
    return {"run": run, "progress": progress, "steps": steps}
