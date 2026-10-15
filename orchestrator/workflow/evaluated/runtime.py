"""Minimal evaluated execution on a durably published run authority."""

from __future__ import annotations

from dataclasses import replace
import logging
import sys
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from orchestrator.workflow.evaluated.attempts import allocate_attempt, attempt_paths
from orchestrator.workflow.evaluated.commands import CommandPerformerError, command_result  # noqa: F401 (re-export)
from orchestrator.workflow.evaluated.confined_dispatch import EFFECT_UNSUPPORTED, ConfinedDispatchRefusal, require_confinable
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
from orchestrator.workflow.evaluated.provider_io import ProviderIOContext
from .providers import provider_result
from . import effect_execution
from .effect_execution import PreparedAttempt, ExternalOutcome, perform_external
from .run_ref import (
    project_evaluated_run_ref,
    settle_evaluated_run_ref, validate_evaluated_run_ref, reconcile_evaluated_run_ref,
    validate_evaluated_run_ref_start,
)
from .authority import RunAuthority, _require_retained_root, workspace_result_locator
from .machine import evaluate_closed_program, site_classes
from .replay import discover_prefix
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
    stream_output: bool = False,
    confined: Any = None,
) -> tuple[int, Any]:
    """Evaluate the checked table and persist its terminal outcome under its writer lock.

    `confined` is a confined run-ref child's session (`run_ref.confined_session`): its
    command attempts dispatch only through the session's holder (no host route).
    """
    if not isinstance(authority, RunAuthority):
        raise TypeError("authority must be a checked RunAuthority")
    if authority.confined and confined is None and site_classes(authority.program):
        return _resume_refusal(ConfinedDispatchRefusal(EFFECT_UNSUPPORTED, "confined child has no session"))
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

        def handle(node, operands, identity, owner, reader, *, launch_workspace=None):
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
                stream_output=stream_output,
                launch_workspace=launch_workspace,
                confined=confined,
            )

        handler = _execution_handler(handle, authority, inputs, run_id, workspace, provider_io,
            checked_site_classes, run_files, workspace_files, stream_output, confined)
        try:
            value = evaluate_closed_program(
                authority.program,
                inputs,
                effect_handler=handler,
                provider_io=provider_io,
                run_id=run_id,
                print_sink=sys.stdout,
            ).json_value()
            if confined is not None:
                confined.finish()
        except Exception as exc:
            code = getattr(exc, "code", "evaluated_execution_failed")
            message = str(exc) or code
            logger.error("[%s] %s", code, message)
            if _can_append_failure_terminal(exc):
                if confined is not None:
                    confined.record_failure(authority, exc)
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


def _execution_handler(handle, authority, inputs, run_id, workspace, provider_io,
                       site_classes, run_files, workspace_files, stream_output, confined=None):
    from .parallel import ParallelCoordinator, has_parallel
    if not has_parallel(authority.program):
        return handle
    frontiers = _prepare_parallel_recovery(authority, inputs, run_id, workspace, provider_io, site_classes, confined=confined)
    return ParallelCoordinator(handle, authority, dict(workspace=workspace, run_files=run_files,
        workspace_files=workspace_files, site_classes=site_classes, stream_output=stream_output,
        confined=confined), frontiers=frontiers)


def _can_append_failure_terminal(exc):
    return not isinstance(exc, ViewPublicationError) and not getattr(exc, "preflight", False)


def execute_pure_resume(
    authority: RunAuthority,
    inputs: Mapping[str, Any],
    *,
    run_id: str,
    workspace: Path,
    provider_io: ProviderIOContext | None = None,
    stream_output: bool = False,
    confined: Any = None,
) -> tuple[int, Any]:
    """Replay committed effects before allowing resume to repair or continue."""
    if not isinstance(authority, RunAuthority):
        raise TypeError("authority must be a checked RunAuthority")
    if authority.confined and confined is None and site_classes(authority.program):
        return _resume_refusal(ConfinedDispatchRefusal(EFFECT_UNSUPPORTED, "confined child has no session"))
    workspace = Path(workspace).resolve(strict=True)
    checked_site_classes = site_classes(authority.program)
    try:
        snapshot, commits, consumed, value, reached_boundary = _replay_resume_prefix(
            authority, inputs, run_id=run_id, workspace=workspace, provider_io=provider_io,
            site_classes=checked_site_classes, confined=confined,
        )
    except Exception as exc:
        if confined is not None:
            confined.resume_error = exc
        return _resume_refusal(exc)
    if consumed != len(commits):
        return _resume_refusal(MemoError("memo_inconsistent", "active commits remain after replay"))
    terminal_result = _replayed_halt_result(snapshot, value, reached_boundary)
    if terminal_result is not None:
        if terminal_result[0] == 0:
            from .run_ref import retry_evaluated_cleanup
            try:
                pending = retry_evaluated_cleanup(authority, snapshot, workspace)
                for row in pending:
                    logger.error('[run_ref_cleanup_pending] %s attempt=%s: %s', row['identity'], row['attempt'], row['error'])
                if pending:
                    return 2, terminal_result[1]
            except Exception as exc:
                return _resume_refusal(exc)
        return terminal_result
    if snapshot.tail:
        try:
            repair_torn_tail(authority.memo_path, snapshot, run_files=authority.run_files)
        except Exception as exc:
            return _resume_refusal(exc)
    result = execute_pure_run(
        authority, inputs, run_id=run_id, workspace=workspace, provider_io=provider_io,
        stream_output=stream_output, confined=confined,
    )
    if result[0] == 0:
        from .run_ref import retry_evaluated_cleanup
        try:
            completed = read_memo(authority.memo_path, checked_site_classes, run_files=authority.run_files)
            pending = retry_evaluated_cleanup(authority, completed, workspace)
            for row in pending:
                logger.error('[run_ref_cleanup_pending] %s attempt=%s: %s', row['identity'], row['attempt'], row['error'])
            if pending:
                return 2, result[1]
        except Exception as exc:
            return _resume_refusal(exc)
    return result


def _replay_resume_prefix(authority, inputs, *, run_id, workspace, provider_io, site_classes, confined=None):
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    prefix = discover_prefix(authority, snapshot, inputs=inputs, run_id=run_id, provider_io=provider_io)
    _validate_discovered_prefix(authority, prefix, snapshot, workspace, defer_parallel_fault=True, confined=confined)
    from .parallel import has_parallel
    if has_parallel(authority.program):
        from .run_ref import inventory_parallel_run_ref_recovery
        obligations = [reached for reached in prefix.commits if reached.node["class"] == "run_ref"
            and (reached.identity, reached.commit.data["attempt"]) not in snapshot.settlements]
        inventory_parallel_run_ref_recovery(authority, obligations, workspace)
    return snapshot, commits, len(prefix.commits), prefix.value, not prefix.halted


def _prepare_parallel_recovery(authority, inputs, run_id, workspace, provider_io, site_classes, confined=None):
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if not snapshot.entries:
        return frozenset()
    prefix = discover_prefix(authority, snapshot, inputs=inputs, run_id=run_id, provider_io=provider_io)
    _validate_discovered_prefix(authority, prefix, snapshot, workspace, defer_parallel_fault=True, confined=confined)
    run_ref_obligations = []
    for reached in prefix.commits:
        if reached.node['class'] == 'run_ref' and (reached.identity, reached.commit.data['attempt']) not in snapshot.settlements:
            run_ref_obligations.append(reached)
    from .run_ref import inventory_parallel_run_ref_recovery, resolve_run_ref_input
    inventory_parallel_run_ref_recovery(authority, run_ref_obligations, workspace)
    for reached in run_ref_obligations:
        resolved, _parts = resolve_run_ref_input(reached.node, reached.operands)
        reconcile_evaluated_run_ref(authority, resolved, reached.identity, workspace, reached.commit, site_classes)
    return frozenset(reached.identity for reached in prefix.frontiers)


def _validate_discovered_prefix(authority, prefix, snapshot, workspace, *, defer_parallel_fault=False, confined=None, proof_only=False):
    for reached in sorted(prefix.commits, key=lambda reached: reached.commit.offset):
        effect_inputs._replay_committed_effect(authority, reached.node, reached.operands,
            reached.identity, reached.reader, reached.commit, workspace, snapshot, reached.owner,
            launch_workspace=reached.launch_workspace, confined=confined)
    if proof_only:
        return
    frontiers = frozenset(reached.identity for reached in prefix.frontiers)
    for reached in prefix.frontiers:
        effect_inputs._check_resume_boundary(authority, snapshot, reached.node, reached.operands,
            reached.identity, reached.reader, workspace, reached.owner, reached_frontiers=frontiers,
            launch_workspace=reached.launch_workspace, confined=confined)
    if prefix.fault is not None and not (defer_parallel_fault and prefix.fault_in_parallel):
        raise prefix.fault


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


def _execute_effect(authority, node, operands, identity, **kwargs):
    attempt = prepare_effect(authority, node, operands, identity, **kwargs)
    if isinstance(attempt, EvaluatedValue):
        return attempt
    return _start_and_perform_effect(attempt)


def prepare_effect(
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
    stream_output: bool = False,
    launch_workspace: EvaluatedValue | None = None,
    parallel_frontiers: frozenset[str] = frozenset(),
    parallel_unsettled: bool = False,
    confined: Any = None,
) -> PreparedAttempt | EvaluatedValue:
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commit = snapshot.active_commits.get(identity)
    if commit is None:
        effect_inputs._ensure_effect_can_start(snapshot, identity,
            reached_frontiers=parallel_frontiers, allow_unsettled=parallel_unsettled)
        if confined is not None:  # Q1: before `started`, so a refusal leaves no attempt record
            require_confinable(node, authority.header["interpreters"])
    baseline = None if commit is not None else effect_inputs._retry_baseline(
        snapshot, identity, snapshot.latest_starts.get(identity))
    launch_cwd = effect_inputs.resolve_launch_cwd(workspace, launch_workspace,
        identity=identity, previous=commit or baseline, recorded=confined is not None and commit is not None)
    ordinal, attempt_directory, result_path = (
        attempt_paths(snapshot, identity) if commit is None
        else (None, None, commit.data["result_path"]))
    resolved, parts, implementation_files = effect_inputs._resolve_effect_input(
        authority, node, operands, identity, workspace, reader,
        commit, baseline, attempt_directory, result_path, owner=owner, workspace_files=workspace_files, launch_cwd=launch_cwd,
        confined=confined,
    )
    if confined is not None and commit is None:  # D5 attempt snapshot of named clone files (P1, Q3, Q5)
        parts = {**parts, **confined.clone_input_parts(node, launch_cwd, operands)}
    input_digest = canonical_sha256(parts)
    dependencies = effect_inputs.effect_dependencies(operands, launch_workspace)
    if commit is not None:
        return _reuse_reached_commit(authority, node, identity, parts, input_digest,
            dependencies, resolved, workspace, commit, snapshot, site_classes)
    if baseline is not None and node.get("repeat") == "never":
        raise effect_inputs._PreflightRefusal("lexical_restore_pending_effect_unsafe",
            f"{identity}: effect declares that it must not be repeated")
    assert ordinal is not None and attempt_directory is not None
    if baseline is not None:
        logger.warning("[effect_rerun] %s attempts=%s", identity, list(range(1, ordinal)))
    if node['class'] == 'run_ref':
        validate_evaluated_run_ref_start(authority, resolved, identity, ordinal, workspace)
    leaf_context = None if confined is None else confined.leaf_context()  # after the snapshot copy (R3)
    started = dict(record='started', identity=identity, attempt=ordinal,
        input_digest=input_digest, input_parts=parts, implementation_files=implementation_files,
        result_path=result_path, time=time.time())
    if confined is not None:
        from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
        confined.check_evidence(extra_bytes=len(canonical_json_bytes(started)) + 1)
    _require_retained_root(run_files)
    attempt_files = allocate_attempt(run_files, authority.memo_path, started, checked_authority=authority,
        before_failure=None if confined is None else lambda exc: confined.record_failure(authority, exc))
    return PreparedAttempt(authority, node, identity, ordinal, result_path, input_digest,
        parts, implementation_files, tuple(dependencies), resolved, workspace, workspace_files,
        site_classes, provider_executor, attempt_files, launch_cwd, stream_output, leaf_context)


def _reuse_reached_commit(authority, node, identity, parts, input_digest, dependencies,
    resolved, workspace, commit, snapshot, site_classes):
    result = effect_inputs._reuse_effect_commit(authority, commit, node, identity, parts, input_digest, dependencies)
    if node["class"] == "run_ref":
        settled = (identity, commit.data["attempt"]) in snapshot.settlements
        validate_evaluated_run_ref(authority, resolved, identity, workspace, commit, settled=settled)
        if not settled:
            reconcile_evaluated_run_ref(authority, resolved, identity, workspace, commit, site_classes)
    return result


def _start_and_perform_effect(attempt):
    try:
        _require_retained_root(attempt.authority.run_files)
        outcome = perform_external(attempt)
    except Exception as exc:
        return finish_effect(attempt, error=exc)
    except BaseException:
        attempt.attempt_files.close()
        raise
    return finish_effect(attempt, outcome)


def finish_effect(attempt: PreparedAttempt, outcome: ExternalOutcome | None = None,
                  *, error: Exception | None = None, fatal_publication: bool = False) -> EvaluatedValue:
    """Validate, rehash, publish and settle on the run's coordinator."""
    authority, node = attempt.authority, attempt.node
    try:
        if error is not None:
            raise error
        result, digest, proof, prepared = _validate_attempt_outcome(attempt, outcome)
        implementation = (effect_inputs.rehash_command_implementation(node, attempt.workspace,
            attempt.implementation_files, attempt.launch_cwd, authority=authority, confined=attempt.confined)
            if node['class'] == 'command' else {})
        _require_retained_root(authority.run_files)
        committed = dict(record='committed', identity=attempt.identity, attempt=attempt.ordinal,
            input_digest=attempt.input_digest, input_parts=attempt.parts, value=result.json_value(),
            result_path=attempt.result_path, result_digest=digest, implementation_files=implementation,
            depends_on=list(attempt.dependencies), effect_class=node['class'], time=time.time())
        if proof is not None:
            committed['proof'] = proof
        if attempt.confined is not None:
            from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
            attempt.confined.runner.check_evidence(extra_bytes=len(canonical_json_bytes(committed)) + 1)
        _append_effect_commit(authority, committed, fatal_publication)
        if prepared is not None:
            settle_evaluated_run_ref(authority, attempt.resolved, attempt.identity, attempt.ordinal,
                attempt.workspace, attempt.site_classes, prepared, committed)
        return EvaluatedValue(result.value, result.descriptor,
            dependencies=(*attempt.dependencies, attempt.identity),
            committed_result_path=workspace_result_locator(authority.header, attempt.result_path))
    except ViewPublicationError:
        raise
    except Exception as exc:
        if getattr(exc, "publication_failure", False) or (fatal_publication
                and getattr(exc, "code", "") == "reserved_run_root_changed"):
            raise
        if attempt.confined is not None:
            attempt.confined.runner.record_failure(authority, exc)
        publication_error = _fail_started_effect(
            authority, attempt.identity, attempt.ordinal, attempt.site_classes, exc)
        _raise_if_publication_fatal(publication_error, fatal_publication)
        raise
    finally:
        attempt.attempt_files.close()


def _append_effect_commit(authority, committed, fatal_publication):
    try:
        append_record(authority.memo_path, committed, run_files=authority.run_files, checked_authority=authority)
    except Exception as exc:
        _raise_if_publication_fatal(exc, fatal_publication)
        raise


def _raise_if_publication_fatal(error, fatal_publication):
    if fatal_publication and error is not None:
        from .parallel import ParallelPublicationError
        raise ParallelPublicationError(error) from error


def _validate_attempt_outcome(attempt, outcome):
    if attempt.node['class'] == 'run_ref':
        return project_evaluated_run_ref(attempt.node, outcome.run_ref, attempt.attempt_files)
    if attempt.node['class'] == 'command':
        result, digest = command_result(attempt.node, attempt_files=attempt.attempt_files,
            workspace_files=attempt.workspace_files, result_path=outcome.result_path)
    else:
        result, digest = provider_result(attempt.node, attempt.resolved, attempt.attempt_files,
            attempt.workspace_files, outcome.result_path)
    return result, digest, None, None


def _fail_started_effect(authority, identity, ordinal, site_classes, exc) -> Exception | None:
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
    except (MemoError, OSError, ValueError) as publication_error:
        return publication_error
    return None
