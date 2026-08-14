"""Public compile-and-run surface for one target-2.25 trial entry."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any

from orchestrator.monitor.process import (
    process_start_time_token,
    write_process_metadata,
)
from orchestrator.run_lock import run_writer_lock
from orchestrator.runtime_observability import (
    close_executor_session,
    open_executor_session,
    record_compiled_frontend_provenance,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_public_input_contracts,
)
from orchestrator.workflow.pure_result_replay import DERIVED_PURE_REPLAY_PROFILE
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    FrontendBuildResult,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import TrialExpr
from orchestrator.workflow_lisp.wcc.route import (
    workflow_lisp_context_with_lowering_schema,
)


TRIAL_RUN_RESULT_SCHEMA_VERSION = "workflow_trial_run_result.v1"
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_FAILURE_CODE_LIMIT = 128
_FAILURE_MESSAGE_LIMIT = 1024


class TrialEntryRequestError(ValueError):
    """One public trial request failed before a run was allocated."""

    def __init__(self, code: str, message: str) -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("trial entry error code must be non-empty")
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TrialRunOptions:
    """Closed ordinary compiler/executor options for the public trial SDK."""

    source_roots: tuple[Path, ...] = ()
    provider_externs_file: Path | None = None
    prompt_externs_file: Path | None = None
    imported_workflow_bundles_file: Path | None = None
    command_boundaries_file: Path | None = None
    max_retries: int = 1
    retry_delay_ms: int = 1000

    def __post_init__(self) -> None:
        if not isinstance(self.source_roots, tuple) or any(
            not isinstance(path, Path) for path in self.source_roots
        ):
            raise TypeError("trial source_roots must be a tuple of Paths")
        for name in (
            "provider_externs_file",
            "prompt_externs_file",
            "imported_workflow_bundles_file",
            "command_boundaries_file",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Path):
                raise TypeError(f"trial {name} must be a Path or None")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("trial max_retries must be a nonnegative integer")
        if type(self.retry_delay_ms) is not int or self.retry_delay_ms < 0:
            raise ValueError("trial retry_delay_ms must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class TrialFailureDiagnostic:
    """Bounded public failure projection without internal runtime state."""

    code: str
    message: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.code, str)
            or not self.code
            or len(self.code) > _FAILURE_CODE_LIMIT
        ):
            raise ValueError("trial failure code is invalid")
        if (
            not isinstance(self.message, str)
            or not self.message
            or len(self.message) > _FAILURE_MESSAGE_LIMIT
        ):
            raise ValueError("trial failure message is invalid")

    @property
    def record(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class TrialRunResult:
    """One closed immutable public summary for a terminal trial run."""

    run_id: str
    terminal_status: str
    verdict_digest: str | None
    verdict_path: str | None
    failure_diagnostic: TrialFailureDiagnostic | None
    schema_version: str = TRIAL_RUN_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRIAL_RUN_RESULT_SCHEMA_VERSION:
            raise ValueError("trial run result schema version is unsupported")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("trial run result run_id must be non-empty")
        if self.terminal_status not in {"completed", "failed"}:
            raise ValueError("trial run result status must be terminal")
        if self.terminal_status == "completed":
            if (
                not isinstance(self.verdict_digest, str)
                or _DIGEST_RE.fullmatch(self.verdict_digest) is None
                or not _is_trial_verdict_relpath(self.verdict_path)
                or self.failure_diagnostic is not None
            ):
                raise ValueError("completed trial run result is malformed")
            return
        if (
            self.verdict_digest is not None
            or self.verdict_path is not None
            or type(self.failure_diagnostic) is not TrialFailureDiagnostic
        ):
            raise ValueError("failed trial run result is malformed")

    @classmethod
    def completed(
        cls,
        *,
        run_id: str,
        verdict_digest: str,
        verdict_path: str,
    ) -> "TrialRunResult":
        return cls(
            run_id=run_id,
            terminal_status="completed",
            verdict_digest=verdict_digest,
            verdict_path=verdict_path,
            failure_diagnostic=None,
        )

    @classmethod
    def failed(
        cls,
        *,
        run_id: str,
        code: str,
        message: str,
    ) -> "TrialRunResult":
        return cls(
            run_id=run_id,
            terminal_status="failed",
            verdict_digest=None,
            verdict_path=None,
            failure_diagnostic=TrialFailureDiagnostic(
                code=_bounded_text(code, _FAILURE_CODE_LIMIT, fallback="trial_run_failed"),
                message=_bounded_text(
                    message,
                    _FAILURE_MESSAGE_LIMIT,
                    fallback="trial execution failed",
                ),
            ),
        )

    @property
    def record(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "terminal_status": self.terminal_status,
                "verdict_digest": self.verdict_digest,
                "verdict_path": self.verdict_path,
                "failure_diagnostic": (
                    None
                    if self.failure_diagnostic is None
                    else self.failure_diagnostic.record
                ),
            }
        )

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(dict(self.record))


def _bounded_text(value: object, limit: int, *, fallback: str) -> str:
    text = value if isinstance(value, str) and value else fallback
    return text[:limit]


def _is_trial_verdict_relpath(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and "\\" not in value
        and path.parts[:2] == ("artifacts", "trials")
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _request_path(value: object, *, field: str, optional: bool = False) -> Path | None:
    if value is None and optional:
        return None
    if not isinstance(value, Path):
        suffix = " or None" if optional else ""
        raise TypeError(f"{field} must be a Path{suffix}")
    return value


def _resolve_option_path(value: Path | None, *, workspace: Path) -> Path | None:
    if value is None:
        return None
    return (value if value.is_absolute() else workspace / value).resolve()


def _workflow_path_for_state(workspace: Path, workflow_file: Path) -> str:
    try:
        return workflow_file.relative_to(workspace).as_posix()
    except ValueError:
        return workflow_file.as_posix()


def _compile_trial_entry(
    *,
    workflow_file: Path,
    entry_workflow: str,
    workspace: Path,
    options: TrialRunOptions,
) -> FrontendBuildResult:
    try:
        built = build_frontend_bundle(
            FrontendBuildRequest(
                source_path=workflow_file,
                source_roots=tuple(
                    (path if path.is_absolute() else workspace / path).resolve()
                    for path in options.source_roots
                ),
                entry_workflow=entry_workflow,
                provider_externs_path=_resolve_option_path(
                    options.provider_externs_file,
                    workspace=workspace,
                ),
                prompt_externs_path=_resolve_option_path(
                    options.prompt_externs_file,
                    workspace=workspace,
                ),
                imported_workflow_bundles_path=_resolve_option_path(
                    options.imported_workflow_bundles_file,
                    workspace=workspace,
                ),
                command_boundaries_path=_resolve_option_path(
                    options.command_boundaries_file,
                    workspace=workspace,
                ),
                workspace_root=workspace,
            )
        )
    except LispFrontendCompileError as exc:
        first = exc.diagnostics[0] if exc.diagnostics else None
        detail = (
            str(exc)
            if first is None
            else f"{first.code}: {first.message}"
        )
        raise TrialEntryRequestError(
            "trial_entry_compile_failed",
            _bounded_text(detail, _FAILURE_MESSAGE_LIMIT, fallback="trial compile failed"),
        ) from exc
    # Intentionally version-specific: the public trial entry accepts exactly
    # 2.25 even though the compiler admits 2.26. Widening is a separate change.
    if built.validated_bundle.surface.version != "2.25":
        raise TrialEntryRequestError(
            "trial_entry_target_unsupported",
            "trial entry must target exactly DSL 2.25",
        )
    canonical_name = built.entry_selection.canonical_name
    typed = tuple(
        workflow
        for workflow in built.compile_result.entry_result.typed_workflows
        if workflow.definition.name == canonical_name
    )
    direct_result_digest = (
        typed[0].signature.compiler_direct_result_contract_digest
        if len(typed) == 1
        else None
    )
    if (
        len(typed) != 1
        or not isinstance(typed[0].typed_body.expr, TrialExpr)
        or not isinstance(direct_result_digest, str)
        or _DIGEST_RE.fullmatch(direct_result_digest) is None
    ):
        raise TrialEntryRequestError(
            "trial_entry_result_required",
            "trial entry terminal result must be the compiler-owned trial result",
        )
    trial_nodes = tuple(
        node
        for node in built.validated_bundle.ir.nodes.values()
        if node.kind.value == "trial"
    )
    if len(trial_nodes) != 1:
        raise TrialEntryRequestError(
            "trial_entry_result_required",
            "trial entry must lower to exactly one terminal trial effect",
        )
    step_config = trial_nodes[0].execution_config
    if not isinstance(step_config, TrialStepConfig):
        raise TrialEntryRequestError(
            "trial_entry_result_required",
            "trial entry executable config is not the compiler-owned trial config",
        )
    config = step_config.trial
    if config.result_digest != direct_result_digest:
        raise TrialEntryRequestError(
            "trial_entry_result_required",
            "trial entry compiler result digest disagrees with its terminal effect",
        )
    if any(
        _COMMIT_RE.fullmatch(arm.run_ref.source.commit) is None
        for arm in config.arms
    ):
        raise TrialEntryRequestError(
            "trial_entry_pin_required",
            "every trial arm must use an exact literal commit pin",
        )
    return built


def _failure_from_state(state: Mapping[str, Any]) -> tuple[str, str]:
    error = state.get("error")
    if not isinstance(error, Mapping):
        return "trial_run_failed", "trial execution failed without a diagnostic"
    code = error.get("code") or error.get("type") or "trial_run_failed"
    message = error.get("message") or error.get("error") or "trial execution failed"
    return str(code), str(message)


def _terminal_summary(state: Mapping[str, Any]) -> TrialRunResult:
    run_id = state.get("run_id")
    status = state.get("status")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("trial executor result is missing run_id")
    if status == "failed":
        code, message = _failure_from_state(state)
        return TrialRunResult.failed(run_id=run_id, code=code, message=message)
    if status != "completed":
        raise ValueError("trial executor returned a nonterminal status")
    steps = state.get("steps")
    if not isinstance(steps, Mapping):
        raise ValueError("completed trial run is missing terminal trial state")
    terminal: list[Mapping[str, Any]] = []
    for step in steps.values():
        if not isinstance(step, Mapping) or step.get("status") != "completed":
            continue
        trial = step.get("trial")
        if isinstance(trial, Mapping):
            terminal.append(trial)
    if len(terminal) != 1:
        raise ValueError("completed trial run has missing or ambiguous trial result")
    envelope = terminal[0]
    if set(envelope) != {"outcomes", "verdict", "verdict_artifact"}:
        raise ValueError("completed trial result is not closed")
    verdict = envelope["verdict"]
    verdict_path = envelope["verdict_artifact"]
    if (
        not isinstance(verdict, Mapping)
        or not isinstance(verdict_path, str)
        or not _is_trial_verdict_relpath(verdict_path)
    ):
        raise ValueError("completed trial verdict projection is invalid")
    return TrialRunResult.completed(
        run_id=run_id,
        verdict_digest=canonical_sha256(dict(verdict)),
        verdict_path=verdict_path,
    )


def run_trial_entry(
    *,
    workflow_file: Path,
    entry_workflow: str,
    inputs: Mapping[str, Any],
    workspace: Path,
    state_dir: Path | None,
    run_ref_root: Path,
    options: TrialRunOptions | None = None,
) -> TrialRunResult:
    """Compile and execute one exact target-2.25 terminal trial entry."""

    source = _request_path(workflow_file, field="workflow_file")
    root = _request_path(workspace, field="workspace")
    runs = _request_path(state_dir, field="state_dir", optional=True)
    child_root = _request_path(run_ref_root, field="run_ref_root")
    assert source is not None and root is not None and child_root is not None
    if options is None:
        options = TrialRunOptions()
    elif type(options) is not TrialRunOptions:
        raise TypeError("options must be exact TrialRunOptions or None")
    if not isinstance(entry_workflow, str) or not entry_workflow:
        raise TrialEntryRequestError(
            "trial_entry_workflow_required",
            "entry_workflow must be non-empty",
        )
    if not isinstance(inputs, Mapping):
        raise TypeError("inputs must be a mapping")
    workspace_path = root.resolve()
    workflow_path = (
        source if source.is_absolute() else workspace_path / source
    ).resolve()
    state_path = None if runs is None else runs.resolve()
    run_ref_path = child_root.resolve(strict=False)
    if workflow_path.suffix != ".orc":
        raise TrialEntryRequestError(
            "trial_entry_source_unsupported",
            "trial entry requires a .orc source path",
        )
    if not workflow_path.is_file():
        raise TrialEntryRequestError(
            "trial_entry_source_missing",
            f"trial entry source does not exist: {workflow_path}",
        )
    if not child_root.is_absolute() or child_root != run_ref_path:
        raise TrialEntryRequestError(
            "trial_entry_run_ref_root_invalid",
            "run_ref_root must be a canonical absolute path",
        )

    built = _compile_trial_entry(
        workflow_file=workflow_path,
        entry_workflow=entry_workflow,
        workspace=workspace_path,
        options=options,
    )
    bound_inputs = bind_workflow_inputs(
        {
            name: dict(spec)
            for name, spec in workflow_public_input_contracts(
                built.validated_bundle
            ).items()
        },
        dict(inputs),
        workspace=workspace_path,
    )
    context = workflow_lisp_context_with_lowering_schema(
        dict(workflow_context(built.validated_bundle)),
        built.manifest.lowering_schema_version,
    )
    state_manager = StateManager(
        workspace=workspace_path,
        state_dir=state_path,
    )
    lock_stack = ExitStack()
    try:
        state_manager.run_root.mkdir(parents=True, exist_ok=True)
        lock_stack.enter_context(run_writer_lock(state_manager.run_root))
        run_state = state_manager.initialize(
            _workflow_path_for_state(workspace_path, workflow_path),
            context,
            bound_inputs=bound_inputs,
            result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
        )
        state_manager.bind_run_ref_root(run_ref_path)
        with state_manager.state_transaction() as transaction_state:
            record_compiled_frontend_provenance(
                transaction_state,
                built.validated_bundle.provenance,
            )

        session_id: str | None = None
        session_status = "failed"
        try:
            with state_manager.state_transaction() as transaction_state:
                session_id = open_executor_session(
                    transaction_state,
                    entrypoint="trial",
                    process_start_time=process_start_time_token(os.getpid()),
                )
            try:
                write_process_metadata(
                    state_manager.run_root,
                    executor_session_id=session_id,
                )
            except OSError:
                pass
            executor = WorkflowExecutor(
                built.validated_bundle,
                workspace_path,
                state_manager,
                logs_dir=state_manager.logs_dir,
                debug=False,
                stream_output=False,
                max_retries=options.max_retries,
                retry_delay_ms=options.retry_delay_ms,
                observability=None,
            )
            try:
                result = executor.execute(
                    run_id=run_state.run_id,
                    on_error="stop",
                    max_retries=options.max_retries,
                    retry_delay_ms=options.retry_delay_ms,
                )
            except Exception as exc:
                state_manager.fail_run(
                    {
                        "type": "trial_run_exception",
                        "message": _bounded_text(
                            str(exc),
                            _FAILURE_MESSAGE_LIMIT,
                            fallback=type(exc).__name__,
                        ),
                    }
                )
                result = state_manager.load().to_dict()
            if not isinstance(result, Mapping):
                raise ValueError("trial executor result must be a mapping")
            summary = _terminal_summary(result)
            session_status = summary.terminal_status
            return summary
        finally:
            if session_id is not None and state_manager.state is not None:
                with state_manager.state_transaction() as transaction_state:
                    close_executor_session(
                        transaction_state,
                        session_id=session_id,
                        status=session_status,
                    )
    finally:
        lock_stack.close()


__all__ = [
    "TRIAL_RUN_RESULT_SCHEMA_VERSION",
    "TrialEntryRequestError",
    "TrialFailureDiagnostic",
    "TrialRunOptions",
    "TrialRunResult",
    "run_trial_entry",
]
