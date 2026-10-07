"""Minimal evaluated execution on a durably published run authority."""

from __future__ import annotations

from dataclasses import replace
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
    perform_command,
    workspace_relative_path,
)
from orchestrator.workflow.evaluated.memo import (
    MemoError,
    append_record,
    read_memo,
    repair_torn_tail,
)
from orchestrator.workflow.evaluated.values import EvaluatedValue
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.workflow_lisp.closed.frontend import ProviderIOContext
from .providers import perform_provider
from .run_ref import (
    prepare_evaluated_run_ref,
    settle_evaluated_run_ref, validate_evaluated_run_ref, reconcile_evaluated_run_ref,
    validate_evaluated_run_ref_start,
)
from .authority import RunAuthority, _require_retained_root, workspace_result_locator
from .machine import evaluate_closed_program, site_classes
from .views import ViewPublicationError
from . import effect_inputs


logger = logging.getLogger(__name__)


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
    run_files = authority.run_files or WorkspaceFiles(authority.run_root)
    owns_run_files = authority.run_files is None
    authority = replace(authority, run_files=run_files)
    workspace_files = WorkspaceFiles(workspace)
    try:
        _require_retained_root(run_files)
        before = read_memo(authority.memo_path, checked_site_classes, run_files=authority.run_files)
        if before.terminal is not None and before.terminal.data["outcome"] == "completed":
            return 0, before.terminal.data["value"]

        provider_executor = None

        def handle(node, operands, identity, owner, reader):
            nonlocal provider_executor
            if node.get("class") not in {"command", "provider", "run_ref"}:
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
                owner=owner,
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
            if _can_append_failure_terminal(exc):
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
        if owns_run_files:
            run_files.close()


class _ResumeBoundary(Exception):
    pass


def _can_append_failure_terminal(exc):
    return not isinstance(exc, ViewPublicationError) and not getattr(exc, "preflight", False)


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
            repair_torn_tail(authority.memo_path, snapshot, run_files=authority.run_files)
        except Exception as exc:
            return _resume_refusal(exc)
    return execute_pure_run(
        authority, inputs, run_id=run_id, workspace=workspace, provider_io=provider_io
    )


def _replay_resume_prefix(authority, inputs, *, run_id, workspace, provider_io, site_classes):
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    consumed = 0

    def handle(node, operands, identity, owner, reader):
        nonlocal consumed
        commit = snapshot.active_commits.get(identity)
        if commit is not None:
            if consumed >= len(commits) or commits[consumed].offset != commit.offset:
                raise MemoError("memo_inconsistent", "active commits are not reachable in journal order")
            result = effect_inputs._replay_committed_effect(
                authority, node, operands, identity, reader, commit, workspace, snapshot, owner
            )
            consumed += 1
            return result
        if consumed != len(commits):
            raise MemoError("memo_inconsistent", "an active commit is unreachable from the evaluated program")
        effect_inputs._check_resume_boundary(authority, snapshot, node, operands, identity, reader, workspace, owner)
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
    if snapshot.pending_starts:
        return _resume_refusal(
            MemoError("memo_inconsistent", "evaluated halt leaves active effect evidence unsettled")
        )
    terminal = snapshot.terminal
    if terminal is None or terminal.data["outcome"] != "completed":
        return None
    if canonical_sha256(value) != canonical_sha256(terminal.data["value"]):
        return _resume_refusal(MemoError("memo_inconsistent", "completed terminal differs from evaluated halt"))
    return 0, terminal.data["value"]


def _persist_completed_terminal(
    authority: RunAuthority,
    site_classes: Mapping[str, str],
    value: Any,
) -> tuple[int, Any]:
    after = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if after.pending_starts or after.unsettled_coordinators:
        message = "evaluation returned with an unsettled effect"
        logger.error("[memo_inconsistent] %s", message)
        return 1, None
    if after.terminal is not None:
        # A prior failed terminal can only be reopened by a new durable start.
        return 1, None
    _require_retained_root(authority.run_files)
    append_record(
        authority.memo_path,
        {"record": "terminal", "outcome": "completed", "value": value},
        run_files=authority.run_files,
        checked_authority=authority,
    )
    _require_retained_root(authority.run_files)
    return 0, value


def _append_failed_terminal_if_clear(
    authority: RunAuthority,
    site_classes: Mapping[str, str],
    *,
    code: str,
    message: str,
) -> None:
    try:
        snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    except (MemoError, OSError, ValueError):
        return
    if snapshot.pending_starts or snapshot.unsettled_coordinators or snapshot.terminal is not None:
        return
    append_record(
        authority.memo_path,
        {"record": "terminal", "outcome": "failed", "code": code, "message": message},
        run_files=authority.run_files,
        checked_authority=authority,
    )


def _execute_effect(
    authority: RunAuthority,
    node: Mapping[str, Any],
    operands: Sequence[EvaluatedValue],
    identity: str,
    *,
    owner: str,
    workspace: Path,
    run_files: WorkspaceFiles,
    workspace_files: WorkspaceFiles,
    site_classes: Mapping[str, str],
    reader,
    provider_executor: ProviderExecutor | None,
) -> EvaluatedValue:
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commit = snapshot.active_commits.get(identity)
    if commit is None:
        effect_inputs._ensure_effect_can_start(snapshot, identity)
    baseline = None if commit is not None else effect_inputs._retry_baseline(
        snapshot, identity, snapshot.latest_starts.get(identity))
    ordinal, attempt_directory, result_path = (
        attempt_paths(snapshot, identity) if commit is None
        else (None, None, commit.data["result_path"]))
    resolved, parts, implementation_files = effect_inputs._resolve_effect_input(
        authority, node, operands, identity, workspace, reader,
        commit, baseline, attempt_directory, result_path, owner=owner, workspace_files=workspace_files,
    )
    input_digest = canonical_sha256(parts)
    dependencies = sorted({dependency for value in operands for dependency in value.dependencies})
    if commit is not None:
        return _reuse_reached_commit(authority, node, identity, parts, input_digest,
            dependencies, resolved, workspace, commit, snapshot, site_classes)
    if baseline is not None and node.get("repeat") == "never":
        raise effect_inputs._PreflightRefusal("lexical_restore_pending_effect_unsafe",
            f"{identity}: effect declares that it must not be repeated")
    assert ordinal is not None and attempt_directory is not None
    if baseline is not None:
        logger.warning("[effect_rerun] %s attempts=%s", identity, list(range(1, ordinal)))
    return _start_and_perform_effect(authority, node, identity, ordinal, result_path,
        input_digest, parts, implementation_files, dependencies, resolved, workspace,
        run_files, workspace_files, site_classes, provider_executor)


def _reuse_reached_commit(authority, node, identity, parts, input_digest, dependencies,
    resolved, workspace, commit, snapshot, site_classes):
    result = effect_inputs._reuse_effect_commit(authority, commit, node, identity, parts, input_digest, dependencies)
    if node["class"] == "run_ref":
        settled = (identity, commit.data["attempt"]) in snapshot.settlements
        validate_evaluated_run_ref(authority, resolved, identity, workspace, commit, settled=settled)
        if not settled:
            reconcile_evaluated_run_ref(authority, resolved, identity, workspace, commit, site_classes)
    return result


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
    if node["class"] == "run_ref":
        validate_evaluated_run_ref_start(authority, resolved_request, identity, ordinal, workspace)
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
    _require_retained_root(run_files)
    attempt_files = allocate_attempt(run_files, authority.memo_path, started, checked_authority=authority)
    try:
        _require_retained_root(run_files)
        proof = None
        prepared = None
        if node["class"] == "command":
            result, result_digest = _dispatch_command(
                authority, node, resolved_request, attempt_files, workspace_files)
            after_files = _rehash_command_implementation(node, workspace, implementation_files)
        elif node["class"] == "run_ref":
            result, result_digest, proof, prepared = prepare_evaluated_run_ref(
                authority, node, resolved_request, identity, ordinal, workspace, attempt_files)
            after_files = {}
        else:
            result, result_digest = perform_provider(node, resolved_request, identity,
                executor=provider_executor, attempt_files=attempt_files,
                workspace_files=workspace_files, result_path=workspace_relative_path(
                    workspace, authority.run_root / result_path))
            after_files = {}
        value = result.json_value()
        _require_retained_root(run_files)
        committed_record = {
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
                **({"proof": proof} if proof is not None else {}),
            }
        append_record(authority.memo_path, committed_record, run_files=run_files, checked_authority=authority)
        if prepared is not None:
            settle_evaluated_run_ref(authority, resolved_request, identity, ordinal,
                workspace, site_classes, prepared, committed_record)
        return EvaluatedValue(
            result.value,
            result.descriptor,
            dependencies=(*dependencies, identity),
            committed_result_path=workspace_result_locator(authority.header, result_path),
        )
    except ViewPublicationError:
        raise
    except Exception as exc:
        _fail_started_effect(authority, identity, ordinal, site_classes, exc)
        raise
    finally:
        attempt_files.close()


def _dispatch_command(authority, node, resolved_request, attempt_files, workspace_files):
    resolved_argv, document = resolved_request
    launch_argv = list(resolved_argv)
    if document is not None:
        launch_argv.append(workspace_relative_path(workspace_files.workspace,
            attempt_files.workspace / "inputs.json"))
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
        input_document=document,
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
            f"command closure changed during its attempt: {effect_inputs._changed_evidence(implementation_files, after_files)}",
        )
    return after_files


def _fail_started_effect(authority, identity, ordinal, site_classes, exc) -> None:
    try:
        after = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
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
            append_record(authority.memo_path, failure, run_files=authority.run_files, checked_authority=authority)
    except ViewPublicationError:
        raise
    except (MemoError, OSError, ValueError):
        pass
