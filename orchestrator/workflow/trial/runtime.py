"""Bounded target-2.25 trial-cell execution over acknowledged E1 workers."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
from queue import Empty, Queue
import stat
from threading import Event, Lock
import time
from typing import Any

from orchestrator.workflow.executable_ir import RunRefStepConfig
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.config import BundleProgram
from orchestrator.workflow.run_ref.ledger import (
    RunRefAttemptRecord,
    SettledRunRefResultBinding,
    load_attempt_ledger,
    settled_result_binding_from_record,
)
from orchestrator.workflow.run_ref.runtime import (
    PreparedRunRefSettlement,
    RunRefExecutionResult,
    RunRefLifecycleAcknowledgement,
    RunRefLifecycleAllocation,
    RunRefLifecycleDeadlineExceeded,
    RunRefLifecycleEvent,
    RunRefRuntimeDependencies,
    RunRefRuntimeError,
    RunRefRuntimeRequest,
    drive_run_ref_lifecycle,
    finalize_run_ref_parent_commit,
    persist_run_ref_lifecycle_event,
    preflight_run_ref_runtime_request,
    recover_run_ref_settlement,
    resolve_run_ref_parent_input_values_for_config,
    select_run_ref_lifecycle_allocation,
    validate_run_ref_lifecycle_attempt_authority,
    validate_run_ref_lifecycle_allocation,
)

from .config import TrialRuntimeRequest
from .contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellEffectScope,
    TrialCellKey,
    derive_trial_cell_effect_scopes,
)
from .ledger import (
    TrialLedgerError,
    append_trial_cell_failure,
    append_trial_cell_settlement,
    append_trial_e1_boundary,
    append_trial_e1_committed,
    build_trial_runtime_budget_window,
    classify_trial_cell_resume,
    discard_incomplete_trial_cell,
    initialize_trial_event_ledger,
    load_trial_event_ledger,
    reconcile_orphan_trial_cell_allocation,
    validate_trial_event_ledger_authority,
)


_CELL_FAILURE_CODES = frozenset(
    {
        "run_ref_child_launch_failed",
        "run_ref_child_result_invalid",
        "run_ref_delta_capture_failed",
        "run_ref_evidence_invalid",
    }
)


def _no_crash(_boundary: str) -> None:
    return None


def _default_run_ref_dependencies(
    _cell: TrialCellKey,
    _request: RunRefRuntimeRequest,
) -> RunRefRuntimeDependencies:
    return RunRefRuntimeDependencies()


@dataclass(frozen=True, slots=True)
class TrialRuntimeDependencies:
    """Narrow Task-7 seams; the caller thread remains the sole coordinator."""

    run_ref_dependencies: Callable[
        [TrialCellKey, RunRefRuntimeRequest], RunRefRuntimeDependencies
    ] = _default_run_ref_dependencies
    monotonic_ns: Callable[[], int] = time.monotonic_ns
    wall_time_ns: Callable[[], int] = time.time_ns
    crash_hook: Callable[[str], None] = _no_crash

    def __post_init__(self) -> None:
        if not all(
            callable(value)
            for value in (
                self.run_ref_dependencies,
                self.monotonic_ns,
                self.wall_time_ns,
                self.crash_hook,
            )
        ):
            raise TypeError("trial runtime dependencies must be callable")


@dataclass(frozen=True, slots=True)
class TrialCellFailure:
    code: str
    phase: str
    retryable: bool
    secondary_causes: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (self.code, self.phase)
        ):
            raise ValueError("trial failure code and phase must be non-empty")
        if type(self.retryable) is not bool:
            raise TypeError("trial failure retryable flag must be boolean")
        if not isinstance(self.secondary_causes, tuple):
            raise TypeError("trial failure secondary causes must be a tuple")
        try:
            canonical_json_bytes(list(self.secondary_causes))
        except (TypeError, ValueError) as exc:
            raise ValueError("trial failure secondary causes are not JSON") from exc

    @property
    def record(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "phase": self.phase,
            "retryable": self.retryable,
            "secondary_causes": list(self.secondary_causes),
        }


@dataclass(frozen=True, slots=True)
class TrialCellOutcome:
    """Task-7 terminal cell authority, before Task-8 evidence/adjudication."""

    cell: TrialCellKey
    status: str
    envelope: Mapping[str, Any] | None
    artifacts: Mapping[str, Any] | None
    settled_result: SettledRunRefResultBinding | None
    committed_row_digest: str | None
    failure: TrialCellFailure | None
    e1_authority_row_digest: str | None

    def __post_init__(self) -> None:
        if type(self.cell) is not TrialCellKey:
            raise TypeError("trial outcome cell must be exact TrialCellKey")
        if self.status == "completed":
            if (
                not isinstance(self.envelope, Mapping)
                or not isinstance(self.artifacts, Mapping)
                or type(self.settled_result) is not SettledRunRefResultBinding
                or not isinstance(self.committed_row_digest, str)
                or self.failure is not None
                or self.e1_authority_row_digest != self.committed_row_digest
            ):
                raise ValueError("completed trial cell outcome is incomplete")
        elif self.status == "failed":
            if (
                self.envelope is not None
                or self.artifacts is not None
                or self.settled_result is not None
                or self.committed_row_digest is not None
                or type(self.failure) is not TrialCellFailure
            ):
                raise ValueError("failed trial cell outcome is invalid")
        else:
            raise ValueError("trial cell outcome status is invalid")


@dataclass(frozen=True, slots=True)
class TrialRuntimeExecution:
    ledger_path: Path
    outcomes: tuple[TrialCellOutcome, ...]

    def __post_init__(self) -> None:
        path = Path(self.ledger_path)
        if not path.is_absolute() or path.resolve(strict=False) != path:
            raise ValueError("trial runtime ledger path must be canonical")
        if not isinstance(self.outcomes, tuple) or any(
            type(outcome) is not TrialCellOutcome for outcome in self.outcomes
        ):
            raise TypeError("trial runtime outcomes must be an exact tuple")
        object.__setattr__(self, "ledger_path", path)


@dataclass(frozen=True, slots=True)
class _AckReply:
    acknowledgement: RunRefLifecycleAcknowledgement | None = None
    error: BaseException | None = None


@dataclass(frozen=True, slots=True)
class _LifecycleProposal:
    cell: TrialCellKey
    request: RunRefRuntimeRequest
    event: RunRefLifecycleEvent
    reply: Queue[_AckReply]


@dataclass(frozen=True, slots=True)
class _WorkerResult:
    cell: TrialCellKey
    request: RunRefRuntimeRequest
    dependencies: RunRefRuntimeDependencies
    prepared: PreparedRunRefSettlement


def _head(path: Path) -> str:
    return load_trial_event_ledger(path).rows[-1].row_digest


def _cell_rows(path: Path, cell: TrialCellKey):
    return tuple(
        row
        for row in load_trial_event_ledger(path).rows[1:]
        if row.payload["cell"] == cell.record
    )


def _prepared_binding(path: Path, cell: TrialCellKey) -> SettledRunRefResultBinding:
    prepared = [row for row in _cell_rows(path, cell) if row.kind == "cell_prepared"]
    if len(prepared) != 1:
        raise TrialLedgerError("trial prepared cell authority is missing or ambiguous")
    return settled_result_binding_from_record(prepared[0].payload["settled_result"])


def _failure_from_record(value: Mapping[str, Any]) -> TrialCellFailure:
    if set(value) != {"code", "phase", "retryable", "secondary_causes"}:
        raise TrialLedgerError("trial failure value has missing or extra fields")
    causes = value["secondary_causes"]
    if not isinstance(causes, list):
        raise TrialLedgerError("trial failure secondary causes are invalid")
    return TrialCellFailure(
        code=value["code"],
        phase=value["phase"],
        retryable=value["retryable"],
        secondary_causes=tuple(causes),
    )


def _completed_outcome(
    cell: TrialCellKey,
    result: RunRefExecutionResult,
) -> TrialCellOutcome:
    return TrialCellOutcome(
        cell=cell,
        status="completed",
        envelope=dict(result.envelope),
        artifacts=dict(result.artifacts),
        settled_result=result.settled_result,
        committed_row_digest=result.committed_row_digest,
        failure=None,
        e1_authority_row_digest=result.committed_row_digest,
    )


def _failed_outcome(
    cell: TrialCellKey,
    failure: TrialCellFailure,
    authority: RunRefAttemptRecord | None,
) -> TrialCellOutcome:
    return TrialCellOutcome(
        cell=cell,
        status="failed",
        envelope=None,
        artifacts=None,
        settled_result=None,
        committed_row_digest=None,
        failure=failure,
        e1_authority_row_digest=(
            None if authority is None else authority.row_digest
        ),
    )


def _e1_request(
    *,
    trial_request: TrialRuntimeRequest,
    cell: TrialCellKey,
    scope: TrialCellEffectScope,
    parent_state: Mapping[str, Any],
    parent_workspace: Path,
    capsule_dir: Path | None,
) -> RunRefRuntimeRequest:
    step_config = _arm_step_config(trial_request, cell.arm_id)
    return RunRefRuntimeRequest(
        step_config=step_config,
        visit=trial_request.visit,
        parent_state=parent_state,
        parent_workspace=parent_workspace,
        parent_run_root=scope.effect_instance_root,
        run_ref_root=scope.run_ref_root,
        capsule_dir=_capsule_for_arm(step_config, capsule_dir),
    )


def _arm_step_config(
    request: TrialRuntimeRequest,
    arm_id: str,
) -> RunRefStepConfig:
    matching = [
        arm.run_ref for arm in request.step_config.arms if arm.arm_id == arm_id
    ]
    if len(matching) != 1:
        raise TrialLedgerError("trial arm executable authority is ambiguous")
    return matching[0]


def _capsule_for_arm(
    step_config: RunRefStepConfig,
    capsule_dir: Path | None,
) -> Path | None:
    if isinstance(step_config.run_ref.program, BundleProgram):
        return capsule_dir
    return None


def _preflight_trial_cells(
    request: TrialRuntimeRequest,
    parent_state: Mapping[str, Any],
    *,
    scopes: tuple[TrialCellEffectScope, ...],
    parent_workspace: Path,
    capsule_dir: Path | None,
) -> None:
    if tuple(scope.cell for scope in scopes) != request.cell_domain:
        raise TrialLedgerError("trial cell preflight domain disagrees")
    for scope in scopes:
        arm_id = scope.cell.arm_id
        step_config = _arm_step_config(request, arm_id)
        if (
            resolve_run_ref_parent_input_values_for_config(
                step_config,
                parent_state,
            )
            != request.resolved_inputs_by_arm[arm_id]
        ):
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "trial_resolved_inputs_disagree",
            )
        preflight_run_ref_runtime_request(
            step_config=step_config,
            visit=request.visit,
            parent_state=parent_state,
            parent_workspace=parent_workspace,
            prospective_parent_run_root=scope.effect_instance_root,
            run_ref_root=scope.run_ref_root,
            capsule_dir=_capsule_for_arm(step_config, capsule_dir),
        )


def _timeout_failure(
    *,
    now_ns: int,
    arm_deadline_ns: int,
    trial_deadline_ns: int,
) -> TrialCellFailure | None:
    deadline = min(arm_deadline_ns, trial_deadline_ns)
    if now_ns < deadline:
        return None
    code = (
        "trial_timeout"
        if trial_deadline_ns <= arm_deadline_ns
        else "trial_arm_timeout"
    )
    return TrialCellFailure(
        code=code,
        phase="scheduling",
        retryable=False,
        secondary_causes=(),
    )


def _runtime_failure(
    error: RunRefRuntimeError,
    *,
    phase: str,
    arm_deadline_ns: int,
    trial_deadline_ns: int,
) -> TrialCellFailure:
    if isinstance(error, RunRefLifecycleDeadlineExceeded):
        return TrialCellFailure(
            code=(
                "trial_timeout"
                if trial_deadline_ns <= arm_deadline_ns
                else "trial_arm_timeout"
            ),
            phase=phase,
            retryable=False,
            secondary_causes=(),
        )
    machine = error.machine_fields
    causes = machine.get("secondary_causes", [])
    return TrialCellFailure(
        code=error.code,
        phase=phase,
        retryable=False,
        secondary_causes=tuple(causes),
    )


def _is_cell_failure(error: BaseException) -> bool:
    return isinstance(error, RunRefRuntimeError) and (
        error.code in _CELL_FAILURE_CODES or error.code.startswith("trial_")
    )


def execute_trial_cells(
    request: TrialRuntimeRequest,
    *,
    parent_state: Mapping[str, Any],
    parent_workspace: Path,
    parent_run_root: Path,
    run_ref_root: Path,
    capsule_dir: Path | None,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
    dependencies: TrialRuntimeDependencies | None = None,
) -> TrialRuntimeExecution:
    """Execute or reconcile all cells; Task 8 and outer settlement are excluded."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be an exact TrialRuntimeRequest")
    if not isinstance(parent_state, Mapping):
        raise TypeError("parent_state must be a mapping")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("sealed labels must be exact SealedTrialOpaqueLabelMap")
    effects = dependencies or TrialRuntimeDependencies()
    if type(effects) is not TrialRuntimeDependencies:
        raise TypeError("dependencies must be exact TrialRuntimeDependencies")
    origin_ns = effects.monotonic_ns()
    if type(origin_ns) is not int or origin_ns < 0:
        raise ValueError("trial monotonic origin must be non-negative")
    wall_now_ns = effects.wall_time_ns()
    if type(wall_now_ns) is not int or wall_now_ns < 0:
        raise ValueError("trial wall-clock origin must be non-negative")
    try:
        frozen_parent_state = json.loads(canonical_json_bytes(dict(parent_state)))
    except (TypeError, ValueError) as exc:
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "trial_parent_state_not_canonical",
        ) from exc

    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=Path(parent_run_root),
        run_ref_root=Path(run_ref_root),
    )
    scope_by_cell = {scope.cell: scope for scope in scopes}
    _preflight_trial_cells(
        request,
        frozen_parent_state,
        scopes=scopes,
        parent_workspace=Path(parent_workspace),
        capsule_dir=(None if capsule_dir is None else Path(capsule_dir)),
    )
    ledger_path = scopes[0].trial_root / "trial-events.jsonl"
    if os.path.lexists(ledger_path):
        budget_window = validate_trial_event_ledger_authority(
            ledger_path,
            request=request,
            sealed_opaque_labels=sealed_opaque_labels,
        )
        if wall_now_ns < budget_window.opened_at_unix_ns:
            raise TrialLedgerError("trial runtime clock moved backwards")
        existing_ledger = load_trial_event_ledger(ledger_path)
    else:
        budget_window = build_trial_runtime_budget_window(
            request,
            opened_at_unix_ns=wall_now_ns,
        )
        initialize_trial_event_ledger(
            request=request,
            sealed_opaque_labels=sealed_opaque_labels,
            cell_scopes=scopes,
            runtime_budget_window=budget_window,
        )
        existing_ledger = None
    allocated_cells = (
        {
            (row.payload["cell"]["arm_id"], row.payload["cell"]["rep"])
            for row in existing_ledger.rows[1:]
            if row.kind == "cell_allocated"
        }
        if existing_ledger is not None
        else set()
    )
    for scope in scopes:
        cell_identity = (scope.cell.arm_id, scope.cell.rep)
        if cell_identity not in allocated_cells:
            scope.effect_instance_root.mkdir(parents=True, exist_ok=True)
            continue
        try:
            root_identity = scope.effect_instance_root.lstat()
            ledger_identity = scope.ledger_path.lstat()
        except OSError as exc:
            raise TrialLedgerError("trial bound E1 root is missing or invalid") from exc
        if (
            not stat.S_ISDIR(root_identity.st_mode)
            or stat.S_ISLNK(root_identity.st_mode)
            or not stat.S_ISREG(ledger_identity.st_mode)
        ):
            raise TrialLedgerError("trial bound E1 root is missing or invalid")
    e1_requests = {
        cell: _e1_request(
            trial_request=request,
            cell=cell,
            scope=scope_by_cell[cell],
            parent_state=frozen_parent_state,
            parent_workspace=Path(parent_workspace),
            capsule_dir=(None if capsule_dir is None else Path(capsule_dir)),
        )
        for cell in request.cell_domain
    }
    arm_deadlines = {
        arm_id: origin_ns + max(0, deadline_ns - wall_now_ns)
        for arm_id, deadline_ns in budget_window.arm_deadlines
    }
    trial_deadline = origin_ns + max(
        0,
        budget_window.trial_deadline_unix_ns - wall_now_ns,
    )
    outcomes: dict[TrialCellKey, TrialCellOutcome] = {}
    pending: deque[TrialCellKey] = deque()

    def append_commit(
        cell: TrialCellKey,
        e1_request: RunRefRuntimeRequest,
        result: RunRefExecutionResult,
    ) -> None:
        e1 = load_attempt_ledger(e1_request.ledger_path)
        matching = [
            row for row in e1.rows if row.row_digest == result.committed_row_digest
        ]
        if len(matching) != 1 or e1.rows[-1] != matching[0]:
            raise TrialLedgerError("trial E1 committed authority is not exact head")
        append_trial_e1_committed(
            ledger_path,
            expected_head_digest=_head(ledger_path),
            cell=cell,
            committed_authority=matching[0],
        )

    # Reconcile every durable state before scheduling untouched/fresh work.
    for cell in request.cell_domain:
        scope = scope_by_cell[cell]
        e1_request = e1_requests[cell]
        decision = classify_trial_cell_resume(
            ledger_path,
            request=request,
            cell=cell,
        )
        if decision.action == "reconcile_orphan_e1_allocation":
            orphan_e1 = load_attempt_ledger(scope.ledger_path)
            if not orphan_e1.rows:
                raise TrialLedgerError("trial orphan E1 allocation is missing")
            validate_run_ref_lifecycle_allocation(
                e1_request,
                authority=orphan_e1.rows[-1],
                effect_instance_root=scope.effect_instance_root,
                effect_instance_digest=scope.effect_instance_digest,
            )
            reconcile_orphan_trial_cell_allocation(
                ledger_path,
                expected_head_digest=_head(ledger_path),
                request=request,
                scope=scope,
            )
            decision = classify_trial_cell_resume(
                ledger_path,
                request=request,
                cell=cell,
            )
        if decision.action in {"discard_incomplete", "reconcile_discarded_e1"}:
            discard_incomplete_trial_cell(
                ledger_path,
                expected_head_digest=_head(ledger_path),
                request=request,
                cell=cell,
                current_step_config_digest=e1_request.step_config.step_config_digest,
            )
            pending.append(cell)
            continue
        if decision.action == "allocate_fresh":
            pending.append(cell)
            continue
        if decision.action == "reuse_failed":
            failures = [
                row for row in _cell_rows(ledger_path, cell) if row.kind == "cell_failed"
            ]
            if len(failures) != 1:
                raise TrialLedgerError("trial failed cell authority is ambiguous")
            failure_row = failures[0]
            failure = _failure_from_record(failure_row.payload["failure"])
            authority = None
            if failure_row.payload["e1_authority_row_digest"] is not None:
                e1 = load_attempt_ledger(e1_request.ledger_path)
                matches = [
                    row
                    for row in e1.rows
                    if row.row_digest
                    == failure_row.payload["e1_authority_row_digest"]
                ]
                if len(matches) != 1 or e1.rows[-1] != matches[0]:
                    raise TrialLedgerError("trial failed cell E1 authority disagrees")
                authority = matches[0]
                validate_run_ref_lifecycle_attempt_authority(
                    e1_request,
                    authority=authority,
                    effect_instance_root=scope.effect_instance_root,
                    effect_instance_digest=scope.effect_instance_digest,
                )
                if failure.phase != authority.stage:
                    raise TrialLedgerError(
                        "trial failure phase disagrees with active E1 authority"
                    )
            elif failure.phase != "scheduling":
                raise TrialLedgerError("trial unstarted failure phase is invalid")
            outcomes[cell] = _failed_outcome(
                cell,
                failure,
                authority,
            )
            continue
        settled = _prepared_binding(ledger_path, cell)
        if decision.action == "reconcile_pending_e1_commit":
            result = recover_run_ref_settlement(
                e1_request,
                settled_result=settled.record,
                reconcile_pending=True,
                effect_instance_digest=scope.effect_instance_digest,
            )
            effects.crash_hook("after_e1_finalize_before_trial_commit")
            append_commit(cell, e1_request, result)
        elif decision.action == "reconcile_e1_committed":
            result = recover_run_ref_settlement(
                e1_request,
                settled_result=settled.record,
                reconcile_pending=False,
                effect_instance_digest=scope.effect_instance_digest,
            )
            append_commit(cell, e1_request, result)
        elif decision.action == "reuse":
            result = recover_run_ref_settlement(
                e1_request,
                settled_result=settled.record,
                reconcile_pending=False,
                effect_instance_digest=scope.effect_instance_digest,
            )
        else:
            raise TrialLedgerError("trial cell resume action is unsupported")
        outcomes[cell] = _completed_outcome(cell, result)

    proposals: Queue[_LifecycleProposal] = Queue()
    abort = Event()
    abort_lock = Lock()
    abort_error: list[BaseException | None] = [None]

    def stop(error: BaseException) -> None:
        with abort_lock:
            if abort_error[0] is None:
                abort_error[0] = error
                abort.set()
        while True:
            try:
                proposal = proposals.get_nowait()
            except Empty:
                break
            proposal.reply.put(_AckReply(error=abort_error[0]))

    def current_abort() -> BaseException:
        with abort_lock:
            return abort_error[0] or RuntimeError("trial coordinator stopped")

    def run_cell(
        cell: TrialCellKey,
        e1_request: RunRefRuntimeRequest,
        allocation: RunRefLifecycleAllocation,
        cell_effects: RunRefRuntimeDependencies,
    ) -> _WorkerResult:
        def acknowledge(event: RunRefLifecycleEvent) -> RunRefLifecycleAcknowledgement:
            if abort.is_set():
                raise current_abort()
            reply: Queue[_AckReply] = Queue(maxsize=1)
            proposals.put(
                _LifecycleProposal(
                    cell=cell,
                    request=e1_request,
                    event=event,
                    reply=reply,
                )
            )
            while True:
                try:
                    response = reply.get(timeout=0.05)
                    break
                except Empty:
                    if abort.is_set():
                        raise current_abort()
            if response.error is not None:
                raise response.error
            if response.acknowledgement is None:
                raise RuntimeError("trial coordinator omitted acknowledgement")
            return response.acknowledgement

        prepared = drive_run_ref_lifecycle(
            e1_request,
            allocation=allocation,
            acknowledge=acknowledge,
            dependencies=cell_effects,
            deadline_monotonic_ns=min(
                arm_deadlines[cell.arm_id],
                trial_deadline,
            ),
            started_monotonic_ns=origin_ns,
        )
        return _WorkerResult(
            cell=cell,
            request=e1_request,
            dependencies=cell_effects,
            prepared=prepared,
        )

    def service(proposal: _LifecycleProposal) -> None:
        scope = scope_by_cell.get(proposal.cell)
        if (
            scope is None
            or proposal.request is not e1_requests[proposal.cell]
            or proposal.event.visit != request.visit
            or proposal.event.effect_instance_root != scope.effect_instance_root
        ):
            raise TrialLedgerError("trial lifecycle proposal carries cross-cell scope")
        acknowledgement = persist_run_ref_lifecycle_event(
            proposal.request,
            proposal.event,
        )
        if proposal.event.stage == "allocated":
            effects.crash_hook("after_e1_allocation_before_trial_allocation")
            append_trial_e1_boundary(
                ledger_path,
                expected_head_digest=_head(ledger_path),
                cell=proposal.cell,
                event=proposal.event,
                acknowledgement=acknowledgement,
            )
        elif proposal.event.stage == "completed_pending_parent_commit":
            effects.crash_hook("after_e1_prepared_before_trial_prepared")
            append_trial_e1_boundary(
                ledger_path,
                expected_head_digest=_head(ledger_path),
                cell=proposal.cell,
                event=proposal.event,
                acknowledgement=acknowledgement,
            )
        proposal.reply.put(_AckReply(acknowledgement=acknowledgement))

    def persist_failure(
        cell: TrialCellKey,
        error: RunRefRuntimeError,
    ) -> TrialCellOutcome:
        e1 = load_attempt_ledger(e1_requests[cell].ledger_path)
        authority = e1.rows[-1] if e1.rows else None
        phase = "scheduling" if authority is None else authority.stage
        failure = _runtime_failure(
            error,
            phase=phase,
            arm_deadline_ns=arm_deadlines[cell.arm_id],
            trial_deadline_ns=trial_deadline,
        )
        append_trial_cell_failure(
            ledger_path,
            expected_head_digest=_head(ledger_path),
            cell=cell,
            failure=failure.record,
            e1_authority=authority,
        )
        return _failed_outcome(cell, failure, authority)

    cap = request.static_config.max_concurrency
    futures: dict[Future[_WorkerResult], TrialCellKey] = {}
    executor = ThreadPoolExecutor(max_workers=cap, thread_name_prefix="trial-e1")
    try:
        while pending or futures:
            while pending and len(futures) < cap:
                cell = pending[0]
                timeout = _timeout_failure(
                    now_ns=effects.monotonic_ns(),
                    arm_deadline_ns=arm_deadlines[cell.arm_id],
                    trial_deadline_ns=trial_deadline,
                )
                if timeout is not None:
                    pending.popleft()
                    append_trial_cell_failure(
                        ledger_path,
                        expected_head_digest=_head(ledger_path),
                        cell=cell,
                        failure=timeout.record,
                    )
                    outcomes[cell] = _failed_outcome(cell, timeout, None)
                    continue
                pending.popleft()
                e1_request = e1_requests[cell]
                allocation = select_run_ref_lifecycle_allocation(
                    e1_request,
                    effect_instance_root=scope_by_cell[cell].effect_instance_root,
                    effect_instance_digest=scope_by_cell[cell].effect_instance_digest,
                )
                cell_effects = effects.run_ref_dependencies(cell, e1_request)
                if type(cell_effects) is not RunRefRuntimeDependencies:
                    raise TypeError(
                        "run_ref_dependencies must return RunRefRuntimeDependencies"
                    )
                cell_effects = replace(
                    cell_effects,
                    monotonic_ns=effects.monotonic_ns,
                )
                future = executor.submit(
                    run_cell,
                    cell,
                    e1_request,
                    allocation,
                    cell_effects,
                )
                futures[future] = cell

            if not futures:
                continue
            try:
                proposal = proposals.get(timeout=0.01)
            except Empty:
                proposal = None
            if proposal is not None:
                try:
                    service(proposal)
                except BaseException as error:
                    proposal.reply.put(_AckReply(error=error))
                    raise
                continue

            done = [future for future in futures if future.done()]
            done.sort(key=lambda future: request.cell_domain.index(futures[future]))
            for future in done:
                cell = futures.pop(future)
                try:
                    worker = future.result()
                except BaseException as error:
                    if not _is_cell_failure(error):
                        raise
                    assert isinstance(error, RunRefRuntimeError)
                    outcomes[cell] = persist_failure(cell, error)
                    continue
                prepared = worker.prepared
                outcome_digest = canonical_sha256(
                    {
                        "schema_version": "trial_cell_execution_outcome.v1",
                        "cell": cell.record,
                        "status": "completed",
                        "result_envelope_digest": canonical_sha256(
                            dict(prepared.envelope)
                        ),
                        "artifact_projection_digest": canonical_sha256(
                            dict(prepared.artifacts)
                        ),
                    }
                )
                append_trial_cell_settlement(
                    ledger_path,
                    expected_head_digest=_head(ledger_path),
                    cell=cell,
                    settled_result=prepared.settled_result,
                    outcome_digest=outcome_digest,
                    evidence_digest=(
                        prepared.settled_result.evidence_manifest_digest
                    ),
                )
                effects.crash_hook("after_trial_cell_settlement")
                result = finalize_run_ref_parent_commit(
                    worker.request,
                    prepared,
                    persisted_settled_result=prepared.settled_result.record,
                    dependencies=worker.dependencies,
                    effect_instance_digest=(
                        scope_by_cell[cell].effect_instance_digest
                    ),
                )
                effects.crash_hook("after_e1_finalize_before_trial_commit")
                append_commit(cell, worker.request, result)
                outcomes[cell] = _completed_outcome(cell, result)
    except BaseException as error:
        stop(error)
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    ordered = tuple(outcomes[cell] for cell in request.cell_domain)
    return TrialRuntimeExecution(ledger_path=ledger_path, outcomes=ordered)


__all__ = [
    "TrialCellFailure",
    "TrialCellOutcome",
    "TrialRuntimeDependencies",
    "TrialRuntimeExecution",
    "execute_trial_cells",
]
