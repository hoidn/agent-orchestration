"""Minimal evaluated execution on a durably published run authority."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from orchestrator.workflow.evaluated.attempts import allocate_attempt, attempt_paths
from orchestrator.workflow.evaluated.closure import (
    ClosureEvidenceError,
    resolve_command_evidence,
)
from orchestrator.workflow.evaluated.commands import (
    CommandPerformerError,
    CommandTemplateError,
    inline_command_document,
    perform_command,
    render_command_argv,
    workspace_relative_path,
)
from orchestrator.workflow.evaluated.memo import (
    MemoError,
    JournalEntry,
    MemoSnapshot,
    append_record,
    read_memo,
    repair_torn_tail,
)
from orchestrator.workflow.evaluated.values import EvaluatedValue, coerce_evaluated_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.workflow_lisp.closed.frontend import ProviderIOContext
from .providers import perform_provider, resolve_provider_input
from .authority import RunAuthority
from .machine import evaluate_closed_program, site_classes


logger = logging.getLogger(__name__)


class _PreflightRefusal(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.preflight = True
        super().__init__(message)


class _EffectInputDiverged(_PreflightRefusal):
    def __init__(self, identity: str, detail: str) -> None:
        super().__init__(
            "effect_input_diverged",
            f"{identity}: effect input diverged ({detail})",
        )


def execute_pure_run(
    authority: RunAuthority,
    inputs: Mapping[str, Any],
    *,
    run_id: str,
    workspace: Path,
    provider_io: ProviderIOContext | None = None,
) -> tuple[int, Any]:
    """Evaluate the checked table and persist its terminal outcome under its writer lock."""
    if not isinstance(authority, RunAuthority):
        raise TypeError("authority must be a checked RunAuthority")
    workspace = Path(workspace).resolve(strict=True)
    checked_site_classes = site_classes(authority.program)
    run_files = WorkspaceFiles(authority.run_root)
    workspace_files = WorkspaceFiles(workspace)
    try:
        before = read_memo(authority.memo_path, checked_site_classes)
        if before.terminal is not None and before.terminal.data["outcome"] == "completed":
            return 0, before.terminal.data["value"]

        provider_executor = None

        def handle(node, operands, identity, _owner, reader):
            nonlocal provider_executor
            if node.get("class") not in {"command", "provider"}:
                raise RuntimeError("unsupported evaluated effect class")
            if node["class"] == "provider" and provider_executor is None:
                provider_executor = ProviderExecutor(
                    workspace, ProviderRegistry(), provider_observation_enabled=False
                )
            return _execute_effect(
                authority,
                node,
                operands,
                identity,
                workspace=workspace,
                run_files=run_files,
                workspace_files=workspace_files,
                site_classes=checked_site_classes,
                reader=reader,
                provider_executor=provider_executor,
            )

        try:
            value = evaluate_closed_program(
                authority.program,
                inputs,
                effect_handler=handle,
                provider_io=provider_io,
                run_id=run_id,
            ).json_value()
        except Exception as exc:
            code = getattr(exc, "code", "evaluated_execution_failed")
            message = str(exc) or code
            logger.error("[%s] %s", code, message)
            if not getattr(exc, "preflight", False):
                _append_failed_terminal_if_clear(
                    authority, checked_site_classes, code=code, message=message
                )
            return 1, None

        return _persist_completed_terminal(authority, checked_site_classes, value)
    except Exception as exc:
        code = getattr(exc, "code", "evaluated_execution_failed")
        message = str(exc) or code
        logger.error("[%s] %s", code, message)
        return 1, None
    finally:
        workspace_files.close()
        run_files.close()


class _ResumeBoundary(Exception):
    pass


def execute_pure_resume(
    authority: RunAuthority,
    inputs: Mapping[str, Any],
    *,
    run_id: str,
    workspace: Path,
    provider_io: ProviderIOContext | None = None,
) -> tuple[int, Any]:
    """Replay committed effects before allowing resume to repair or continue."""
    if not isinstance(authority, RunAuthority):
        raise TypeError("authority must be a checked RunAuthority")
    workspace = Path(workspace).resolve(strict=True)
    checked_site_classes = site_classes(authority.program)
    try:
        snapshot, commits, consumed, value, reached_boundary = _replay_resume_prefix(
            authority, inputs, run_id=run_id, workspace=workspace, provider_io=provider_io,
            site_classes=checked_site_classes,
        )
    except Exception as exc:
        return _resume_refusal(exc)
    if consumed != len(commits):
        return _resume_refusal(MemoError("memo_inconsistent", "active commits remain after replay"))
    terminal_result = _replayed_halt_result(snapshot, value, reached_boundary)
    if terminal_result is not None:
        return terminal_result
    if snapshot.tail:
        try:
            repair_torn_tail(authority.memo_path, snapshot)
        except Exception as exc:
            return _resume_refusal(exc)
    return execute_pure_run(
        authority, inputs, run_id=run_id, workspace=workspace, provider_io=provider_io
    )


def _replay_resume_prefix(authority, inputs, *, run_id, workspace, provider_io, site_classes):
    snapshot = read_memo(authority.memo_path, site_classes)
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    consumed = 0

    def handle(node, operands, identity, _owner, reader):
        nonlocal consumed
        commit = snapshot.active_commits.get(identity)
        if commit is not None:
            if consumed >= len(commits) or commits[consumed].offset != commit.offset:
                raise MemoError("memo_inconsistent", "active commits are not reachable in journal order")
            result = _replay_committed_effect(
                authority, node, operands, identity, reader, commit, workspace
            )
            consumed += 1
            return result
        if consumed != len(commits):
            raise MemoError("memo_inconsistent", "an active commit is unreachable from the evaluated program")
        _check_resume_boundary(authority, snapshot, node, operands, identity, reader, workspace)
        raise _ResumeBoundary

    try:
        value = evaluate_closed_program(
            authority.program,
            inputs,
            effect_handler=handle,
            provider_io=provider_io,
            run_id=run_id,
        ).json_value()
    except _ResumeBoundary:
        return snapshot, commits, consumed, None, True
    return snapshot, commits, consumed, value, False


def _resume_refusal(exc: Exception) -> tuple[int, None]:
    code = getattr(exc, "code", "resume_preflight_failed")
    logger.error("[%s] %s", code, str(exc) or code)
    return 2, None


def _replayed_halt_result(snapshot, value, reached_boundary):
    if reached_boundary:
        return None
    if snapshot.pending_starts or snapshot.unsettled_coordinators:
        return _resume_refusal(
            MemoError("memo_inconsistent", "evaluated halt leaves active effect evidence unsettled")
        )
    terminal = snapshot.terminal
    if terminal is None or terminal.data["outcome"] != "completed":
        return None
    if canonical_sha256(value) != canonical_sha256(terminal.data["value"]):
        return _resume_refusal(MemoError("memo_inconsistent", "completed terminal differs from evaluated halt"))
    return 0, terminal.data["value"]


def _replay_committed_effect(authority, node, operands, identity, reader, commit, workspace):
    _resolved, parts, _implementation_files = _resolve_effect_input(
        authority, node, operands, identity, workspace, reader,
        commit, None, None, commit.data["result_path"],
        check_command_destinations=False,
    )
    dependencies = sorted({dependency for value in operands for dependency in value.dependencies})
    return _reuse_effect_commit(
        commit, node, identity, parts, canonical_sha256(parts), dependencies
    )


def _check_resume_boundary(authority, snapshot, node, operands, identity, reader, workspace) -> None:
    _ensure_effect_can_start(snapshot, identity)
    baseline = _retry_baseline(snapshot, identity, snapshot.latest_starts.get(identity))
    if node["class"] == "command" and baseline is not None:
        _ordinal, attempt_directory, result_path = attempt_paths(snapshot, identity)
        _resolve_effect_input(
            authority, node, operands, identity, workspace, reader,
            None, baseline, attempt_directory, result_path,
            check_command_destinations=False,
        )
    elif node["class"] == "provider" and identity in snapshot.pending_starts:
        _ordinal, attempt_directory, result_path = attempt_paths(snapshot, identity)
        _resolve_effect_input(
            authority, node, operands, identity, workspace, reader,
            None, baseline, attempt_directory, result_path,
        )
    if baseline is not None and node.get("repeat") == "never":
        raise _PreflightRefusal(
            "lexical_restore_pending_effect_unsafe",
            f"{identity}: effect declares that it must not be repeated",
        )


def _persist_completed_terminal(
    authority: RunAuthority,
    site_classes: Mapping[str, str],
    value: Any,
) -> tuple[int, Any]:
    after = read_memo(authority.memo_path, site_classes)
    if after.pending_starts or after.unsettled_coordinators:
        message = "evaluation returned with an unsettled effect"
        logger.error("[memo_inconsistent] %s", message)
        return 1, None
    if after.terminal is not None:
        # A prior failed terminal can only be reopened by a new durable start.
        return 1, None
    append_record(
        authority.memo_path,
        {"record": "terminal", "outcome": "completed", "value": value},
    )
    return 0, value


def _append_failed_terminal_if_clear(
    authority: RunAuthority,
    site_classes: Mapping[str, str],
    *,
    code: str,
    message: str,
) -> None:
    try:
        snapshot = read_memo(authority.memo_path, site_classes)
    except (MemoError, OSError, ValueError):
        return
    if snapshot.pending_starts or snapshot.unsettled_coordinators or snapshot.terminal is not None:
        return
    append_record(
        authority.memo_path,
        {"record": "terminal", "outcome": "failed", "code": code, "message": message},
    )


def _execute_effect(
    authority: RunAuthority,
    node: Mapping[str, Any],
    operands: Sequence[EvaluatedValue],
    identity: str,
    *,
    workspace: Path,
    run_files: WorkspaceFiles,
    workspace_files: WorkspaceFiles,
    site_classes: Mapping[str, str],
    reader,
    provider_executor: ProviderExecutor | None,
) -> EvaluatedValue:
    snapshot = read_memo(authority.memo_path, site_classes)
    commit = snapshot.active_commits.get(identity)
    if commit is None:
        _ensure_effect_can_start(snapshot, identity)
    baseline = None if commit is not None else _retry_baseline(
        snapshot, identity, snapshot.latest_starts.get(identity))
    ordinal, attempt_directory, result_path = (
        attempt_paths(snapshot, identity) if commit is None
        else (None, None, commit.data["result_path"]))
    resolved, parts, implementation_files = _resolve_effect_input(
        authority, node, operands, identity, workspace, reader,
        commit, baseline, attempt_directory, result_path,
    )
    input_digest = canonical_sha256(parts)
    dependencies = sorted({dependency for value in operands for dependency in value.dependencies})
    if commit is not None:
        return _reuse_effect_commit(commit, node, identity, parts, input_digest, dependencies)
    if baseline is not None and node.get("repeat") == "never":
        raise _PreflightRefusal("lexical_restore_pending_effect_unsafe",
            f"{identity}: effect declares that it must not be repeated")
    assert ordinal is not None and attempt_directory is not None
    if baseline is not None:
        logger.warning("[effect_rerun] %s attempts=%s", identity, list(range(1, ordinal)))
    return _start_and_perform_effect(authority, node, identity, ordinal, result_path,
        input_digest, parts, implementation_files, dependencies, resolved, workspace,
        run_files, workspace_files, site_classes, provider_executor)


def _resolve_effect_input(
    authority, node, operands, identity, workspace, reader,
    commit, baseline, attempt_directory, result_path, *, check_command_destinations=True,
):
    """Resolve only the reached effect; command closure checks stay local."""
    if node["class"] == "command":
        previous = commit if commit is not None else baseline
        resolved, document_bytes = _render_resolved_argv(node, operands, commit, identity)
        destinations = (
            _command_destinations(authority, attempt_directory, result_path)
            if commit is None and check_command_destinations
            else ()
        )
        implementation_files = _resolve_command_implementation(node, workspace, identity,
            None if previous is None else previous.data["implementation_files"], destinations)
        _check_retry_implementation(identity, baseline, implementation_files)
        parts = _command_input_parts(node, resolved, implementation_files, document_bytes)
    else:
        try:
            resolved = resolve_provider_input(node, operands, workspace=workspace, reader=reader,
                result_path=workspace_relative_path(workspace, authority.run_root / result_path))
        except Exception as exc:
            if commit is not None:
                raise _EffectInputDiverged(identity, f"provider inputs could not be resolved: {exc}") from exc
            raise
        parts = dict(resolved.input_parts)
        implementation_files = {}
    return resolved, parts, implementation_files


def _ensure_effect_can_start(snapshot: MemoSnapshot, identity: str) -> None:
    pending_elsewhere = sorted(set(snapshot.pending_starts) - {identity})
    if pending_elsewhere or snapshot.unsettled_coordinators:
        raise _PreflightRefusal(
            "memo_inconsistent",
            f"cannot start {identity}: other effect evidence is unsettled",
        )
    terminal = snapshot.terminal
    if terminal is not None and terminal.data["outcome"] == "completed":
        raise _PreflightRefusal(
            "memo_inconsistent",
            f"cannot start {identity}: run already has a completed terminal",
        )


def _render_resolved_argv(node, operands, commit, identity):
    try:
        tail = render_command_argv(node, operands)
    except CommandTemplateError as exc:
        if commit is not None:
            raise _EffectInputDiverged(identity, f"template resolution failed: {exc}") from exc
        raise
    document = inline_command_document(node, operands)
    argv = [*node["command"], *tail]
    if document is not None:
        argv.append(document.decode("utf-8"))
    return argv, document


def _resolve_command_implementation(node, workspace, identity, previous, destinations):
    try:
        return resolve_command_evidence(
            node["command"],
            node["closure"],
            workspace_root=workspace,
            prior=previous,
            destinations=destinations,
        )
    except ClosureEvidenceError as exc:
        if previous is not None and not _is_destination_overlap(exc):
            raise _EffectInputDiverged(
                identity, f"implementation evidence could not be re-resolved: {exc}"
            ) from exc
        raise


def _check_retry_implementation(identity, baseline, implementation_files) -> None:
    if baseline is None or implementation_files == baseline.data["implementation_files"]:
        return
    changed = _changed_evidence(baseline.data["implementation_files"], implementation_files)
    raise _EffectInputDiverged(identity, f"retry implementation files changed: {changed}")


def _reuse_effect_commit(commit, node, identity, parts, input_digest, dependencies):
    row = commit.data
    changed_parts = sorted(
        name for name in set(parts) | set(row["input_parts"])
        if parts.get(name) != row["input_parts"].get(name)
    )
    dependency_changed = dependencies != row["depends_on"]
    if input_digest != row["input_digest"] or changed_parts or dependency_changed:
        raise _EffectInputDiverged(
            identity,
            f"input parts changed: {changed_parts}; dependency identities changed: {dependency_changed}; previous {row['input_digest']}, current {input_digest}",
        )
    return coerce_evaluated_value(
        row["value"],
        node["result"],
        dependencies=(*dependencies, identity),
        committed_result_path=row["result_path"],
        context=f"committed {node['class']} result",
    )


def _start_and_perform_effect(
    authority,
    node,
    identity,
    ordinal,
    result_path,
    input_digest,
    parts,
    implementation_files,
    dependencies,
    resolved_request,
    workspace,
    run_files,
    workspace_files,
    site_classes,
    provider_executor,
):
    started = {
        "record": "started",
        "identity": identity,
        "attempt": ordinal,
        "input_digest": input_digest,
        "input_parts": parts,
        "implementation_files": implementation_files,
        "result_path": result_path,
        "time": time.time(),
    }
    attempt_files = allocate_attempt(run_files, authority.memo_path, started)
    try:
        if node["class"] == "command":
            result, result_digest = _dispatch_command(
                authority, node, resolved_request, attempt_files, workspace_files)
            after_files = _rehash_command_implementation(node, workspace, implementation_files)
        else:
            result, result_digest = perform_provider(node, resolved_request, identity,
                executor=provider_executor, attempt_files=attempt_files,
                workspace_files=workspace_files, result_path=workspace_relative_path(
                    workspace, authority.run_root / result_path))
            after_files = {}
        value = result.json_value()
        append_record(
            authority.memo_path,
            {
                "record": "committed",
                "identity": identity,
                "attempt": ordinal,
                "input_digest": input_digest,
                "input_parts": parts,
                "value": value,
                "result_path": result_path,
                "result_digest": result_digest,
                "implementation_files": after_files,
                "depends_on": dependencies,
                "effect_class": node["class"],
                "time": time.time(),
            },
        )
        return EvaluatedValue(
            result.value,
            result.descriptor,
            dependencies=(*dependencies, identity),
            committed_result_path=result_path,
        )
    except Exception as exc:
        _fail_started_effect(authority, identity, ordinal, site_classes, exc)
        raise
    finally:
        attempt_files.close()


def _dispatch_command(authority, node, resolved_argv, attempt_files, workspace_files):
    launch_argv = list(resolved_argv)
    interpreter = node["command"][0]
    if "/" not in interpreter:
        pin = authority.header["interpreters"].get(interpreter)
        if not isinstance(pin, Mapping) or not isinstance(pin.get("path"), str):
            raise CommandPerformerError(
                "command_interpreter_missing",
                f"run authority has no interpreter pin for {interpreter!r}",
            )
        launch_argv[0] = pin["path"]
    return perform_command(
        node,
        launch_argv,
        attempt_files=attempt_files,
        workspace_files=workspace_files,
    )


def _rehash_command_implementation(node, workspace, implementation_files):
    try:
        after_files = resolve_command_evidence(
            node["command"],
            node["closure"],
            workspace_root=workspace,
            prior=implementation_files,
        )
    except ClosureEvidenceError as exc:
        raise CommandPerformerError(
            "command_closure_written",
            f"command closure changed during its attempt: {exc}",
        ) from exc
    if after_files != implementation_files:
        raise CommandPerformerError(
            "command_closure_written",
            f"command closure changed during its attempt: {_changed_evidence(implementation_files, after_files)}",
        )
    return after_files


def _fail_started_effect(authority, identity, ordinal, site_classes, exc) -> None:
    try:
        after = read_memo(authority.memo_path, site_classes)
        pending = after.pending_starts.get(identity)
        if pending is not None and pending.data["attempt"] == ordinal:
            failure = {
                "record": "failed",
                "identity": identity,
                "attempt": ordinal,
                "code": getattr(exc, "code", "evaluated_execution_failed"),
                "exit_info": getattr(exc, "exit_info", None) or {},
            }
            violations = getattr(exc, "violations", None)
            if violations is not None:
                failure["violations"] = violations
            append_record(authority.memo_path, failure)
    except (MemoError, OSError, ValueError):
        pass


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


def _command_destinations(
    authority: RunAuthority,
    attempt_directory: str,
    result_path: str,
) -> tuple[Path, ...]:
    run_root = authority.run_root
    attempt_root = run_root / attempt_directory
    paths = [
        attempt_root,
        run_root / result_path,
        attempt_root / "stdout.txt",
        attempt_root / "stderr.txt",
        authority.memo_path,
    ]
    return tuple(paths)


def _command_input_parts(
    node: Mapping[str, Any],
    resolved_argv: Sequence[str],
    implementation_files: Mapping[str, Any],
    document_bytes: bytes | None,
) -> dict[str, str]:
    parts = {
        "argv": canonical_sha256(list(resolved_argv)),
        "contract": canonical_sha256(node["contract"]),
        "closure": canonical_sha256(node["closure"]),
        "implementation_files": canonical_sha256(dict(implementation_files)),
    }
    if document_bytes is not None:
        parts["document"] = "sha256:" + hashlib.sha256(document_bytes).hexdigest()
    return parts


def _changed_evidence(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return sorted(
        key for key in set(before) | set(after) if before.get(key) != after.get(key)
    )


def _is_destination_overlap(exc: ClosureEvidenceError) -> bool:
    return "runtime destination overlaps command closure" in exc.reason
