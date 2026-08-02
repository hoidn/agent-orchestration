from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import random
import shutil
from threading import Barrier, Event, Lock, get_ident
import time

import pytest

import orchestrator.workflow.trial.runtime as trial_runtime_module
from orchestrator.workflow.executable_ir import (
    RunRefStepConfig,
    TrialArmStepConfig,
    TrialStepConfig,
)
from orchestrator.workflow.run_ref.bundle_transport import (
    write_bundle_capsule_directory,
)
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.config import (
    PathProgram,
    build_run_ref_static_config,
)
from orchestrator.workflow.run_ref.ledger import (
    RunRefVisitKey,
    advance_attempt,
    load_attempt_ledger,
)
from orchestrator.workflow.run_ref.runtime import (
    RunRefChildLaunch,
    RunRefChildProcessResult,
    RunRefRuntimeError,
)
from orchestrator.workflow.trial.config import (
    TrialArmStaticConfig,
    build_trial_runtime_request,
    build_trial_static_config,
)
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.ledger import TrialLedgerError, load_trial_event_ledger
from orchestrator.workflow.trial.runtime import (
    TrialRuntimeDependencies,
    execute_trial_cells,
)
from tests.test_workflow_lisp_trial_lowering import (
    _build_transportable_trial,
    _trial_node,
)
from tests.test_workflow_run_ref_runtime import _RuntimeHarness


class _InjectedCrash(RuntimeError):
    pass


def _rewrite_rechained_trial_ledger(path: Path, mutate) -> None:
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(rows)
    previous = None
    digest_projection = {}
    encoded = []
    for row in rows:
        original_digest = row["row_digest"]
        for field in (
            "prepared_trial_row_digest",
            "trial_settlement_row_digest",
        ):
            if field in row["payload"]:
                row["payload"][field] = digest_projection.get(
                    row["payload"][field],
                    row["payload"][field],
                )
        row["previous_row_digest"] = previous
        preimage = dict(row)
        preimage.pop("row_digest")
        row["row_digest"] = canonical_sha256(preimage)
        digest_projection[original_digest] = row["row_digest"]
        previous = row["row_digest"]
        encoded.append(canonical_json_bytes(row) + b"\n")
    path.write_bytes(b"".join(encoded))


def _rewrite_rechained_e1_ledger(path: Path, mutate):
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(rows)
    previous = None
    encoded = []
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
        row["previous_row_digest"] = previous
        preimage = dict(row)
        preimage.pop("row_digest")
        row["row_digest"] = canonical_sha256(preimage)
        previous = row["row_digest"]
        encoded.append(canonical_json_bytes(row) + b"\n")
    path.write_bytes(b"".join(encoded))
    return rows


def _runtime_fixture(
    tmp_path: Path,
    *,
    arm_timeout_ms: int = 900_000,
    trial_timeout_ms: int = 3_600_000,
    max_concurrency: int = 2,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    compile_root = tmp_path / "compile"
    compile_root.mkdir()
    result = _build_transportable_trial(
        compile_root,
        declarations="",
        type_name="String",
    )
    node = _trial_node(result)
    step_config = node.execution_config
    if (
        arm_timeout_ms != step_config.trial.budget["arm_timeout_ms"]
        or trial_timeout_ms != step_config.trial.budget["trial_timeout_ms"]
        or max_concurrency != step_config.trial.max_concurrency
    ):
        budget = dict(step_config.trial.budget)
        budget.update(
            arm_timeout_ms=arm_timeout_ms,
            trial_timeout_ms=trial_timeout_ms,
        )
        static = build_trial_static_config(
            compiler_runtime_identity_digest=(
                step_config.trial.compiler_runtime_identity_digest
            ),
            site_digest=step_config.trial.site_digest,
            arms=step_config.trial.arms,
            reps=step_config.trial.reps,
            max_concurrency=max_concurrency,
            evaluation=step_config.trial.evaluation,
            budget=budget,
            result_descriptor=step_config.trial.result_descriptor,
            result_digest=step_config.trial.result_digest,
        )
        step_config = TrialStepConfig(
            common=step_config.common,
            trial=static,
            arms=step_config.arms,
        )
    visit = RunRefVisitKey(
        parent_run_id="parent-run",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.compare",
        visit_count=1,
    )
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=visit,
        resolved_inputs_by_arm={
            "direct": {"payload": "fixed"},
            "orc": {"payload": "fixed"},
        },
    )
    parent_workspace = (tmp_path / "parent-workspace").resolve()
    parent_workspace.mkdir()
    parent_run_root = (tmp_path / "parent-run-root").resolve()
    parent_run_root.mkdir()
    run_ref_root = (tmp_path / "external-run-ref-root").resolve()
    capsule_dir = (tmp_path / "capsule").resolve()
    assert result.run_ref_bundle_capsule is not None
    write_bundle_capsule_directory(capsule_dir, result.run_ref_bundle_capsule)
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    sealed = build_sealed_opaque_label_map(
        request.cell_domain,
        salt=b"task-seven-runtime-salt" * 2,
    )
    return {
        "request": request,
        "parent_state": {"bound_inputs": {"payload": "fixed"}, "steps": {}},
        "parent_workspace": parent_workspace,
        "parent_run_root": parent_run_root,
        "run_ref_root": run_ref_root,
        "capsule_dir": capsule_dir,
        "scopes": scopes,
        "sealed": sealed,
    }


def _mixed_program_runtime_fixture(tmp_path: Path):
    fixture = _runtime_fixture(tmp_path)
    current = fixture["request"]
    bundle_executable = current.step_config.arms[0]
    replaced_executable = current.step_config.arms[1]
    replaced_static = replaced_executable.run_ref.run_ref
    path_site = "e" * 64
    path_result_descriptor = deepcopy(replaced_static.result_descriptor)
    path_result_descriptor["envelope"]["name"] = (
        f"RunRefResult${path_site[:16]}"
    )
    value_descriptor = path_result_descriptor["envelope"]["fields"][0]["type"]
    path_static = build_run_ref_static_config(
        compiler_runtime_identity_digest=(
            replaced_static.compiler_runtime_identity_digest
        ),
        site_digest=path_site,
        source=replaced_static.source,
        program=PathProgram(
            path="candidate.orc",
            entry_name="candidate",
            return_refinement=value_descriptor,
            allow_nested_structures=True,
        ),
        inputs=replaced_static.inputs,
        result_descriptor=path_result_descriptor,
        result_digest=canonical_sha256(path_result_descriptor),
        target_dsl_version="2.25",
    )
    static_arms = (
        current.static_config.arms[0],
        TrialArmStaticConfig(arm_id="orc", run_ref=path_static),
    )
    mixed_static = build_trial_static_config(
        compiler_runtime_identity_digest=(
            current.static_config.compiler_runtime_identity_digest
        ),
        site_digest=current.static_config.site_digest,
        arms=static_arms,
        reps=current.static_config.reps,
        max_concurrency=current.static_config.max_concurrency,
        evaluation=current.static_config.evaluation,
        budget=current.static_config.budget,
        result_descriptor=current.static_config.result_descriptor,
        result_digest=current.static_config.result_digest,
    )
    mixed_step = TrialStepConfig(
        common=current.step_config.common,
        trial=mixed_static,
        arms=(
            bundle_executable,
            TrialArmStepConfig(
                arm_id="orc",
                run_ref=RunRefStepConfig(
                    common=replaced_executable.run_ref.common,
                    run_ref=path_static,
                    capsule_binding=None,
                ),
            ),
        ),
    )
    mixed_request = build_trial_runtime_request(
        step_config=mixed_step,
        visit=current.visit,
        resolved_inputs_by_arm=current.resolved_inputs_by_arm,
    )
    fixture["request"] = mixed_request
    fixture["scopes"] = derive_trial_cell_effect_scopes(
        request=mixed_request,
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
    )
    fixture["sealed"] = build_sealed_opaque_label_map(
        mixed_request.cell_domain,
        salt=b"task-seven-runtime-salt" * 2,
    )
    return fixture


def _successful_process(
    launch: RunRefChildLaunch,
    *,
    value: str,
) -> RunRefChildProcessResult:
    workflow_outputs = {"__result__": value}
    child_run_root = (
        launch.workspace / ".orchestrate" / "runs" / launch.child_run_id
    )
    child_run_root.mkdir(parents=True)
    (child_run_root / "state.json").write_bytes(
        canonical_json_bytes(
            {
                "run_id": launch.child_run_id,
                "status": "completed",
                "workflow_outputs": workflow_outputs,
            }
        )
        + b"\n"
    )
    common = {
        "status": "completed",
        "child_run_id": launch.child_run_id,
        "workflow_outputs": workflow_outputs,
    }
    if launch.mode == "bundle":
        result = {
            **common,
            "schema_version": "run_ref_child_result.v1",
            "capsule_digest": launch.request_document[
                "expected_capsule_digest"
            ],
            "target_workflow_name": launch.request_document[
                "target_workflow_name"
            ],
        }
    else:
        result = {
            **common,
            "schema_version": "run_ref_path_child_result.v1",
            "step_config_digest": launch.request_document[
                "expected_step_config_digest"
            ],
            "target_workflow_name": "candidate",
            "path_compile": {
                "diagnostics": {},
                "program_identity": {},
                "signature": {},
                "effect_facts": {},
                "evidence": {},
            },
        }
    return RunRefChildProcessResult(
        returncode=0,
        stdout=canonical_json_bytes(result) + b"\n",
        stderr=b"",
        duration_ms=4,
    )


class _CellHarnesses:
    def __init__(
        self,
        *,
        delays: dict[TrialCellKey, float] | None = None,
        failing: set[TrialCellKey] | None = None,
        evidence_failing: set[TrialCellKey] | None = None,
        launch_barrier: Barrier | None = None,
        first_wave_barrier: Barrier | None = None,
        launch_waits: dict[TrialCellKey, Event] | None = None,
        completion_signals: dict[TrialCellKey, Event] | None = None,
    ) -> None:
        self.delays = delays or {}
        self.failing = failing or set()
        self.evidence_failing = evidence_failing or set()
        self.launch_barrier = launch_barrier
        self.first_wave_barrier = first_wave_barrier
        self.launch_waits = launch_waits or {}
        self.completion_signals = completion_signals or {}
        self.requests = []
        self.launches: list[TrialCellKey] = []
        self.completions: list[TrialCellKey] = []
        self.launch_threads: set[int] = set()
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def factory(self, cell, request):
        self.requests.append((cell, request))
        base = _RuntimeHarness()

        def materialize(*args, **kwargs):
            materialized = base.materialize(*args, **kwargs)
            setup = {
                "schema_version": "run_ref_setup_evidence.v1",
                "repository_revision_digest": (
                    materialized.repository_revision_id.digest
                ),
                "authored_setup_identity": (
                    materialized.repository_revision_id.authored_setup_identity
                ),
                "status": "passed",
                "commands": [],
            }
            setup_path = (
                materialized.setup_evidence_path.parent
                / f"{cell.arm_id}-{cell.rep}.json"
            )
            setup_path.write_bytes(canonical_json_bytes(setup) + b"\n")
            if cell in self.evidence_failing:
                setup_path.write_bytes(canonical_json_bytes({}) + b"\n")
            return replace(materialized, setup_evidence_path=setup_path)

        def launch(child: RunRefChildLaunch) -> RunRefChildProcessResult:
            with self._lock:
                self.launches.append(cell)
                launch_index = len(self.launches)
                self.launch_threads.add(get_ident())
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                if self.launch_barrier is not None:
                    self.launch_barrier.wait(timeout=3)
                if (
                    self.first_wave_barrier is not None
                    and launch_index <= self.first_wave_barrier.parties
                ):
                    self.first_wave_barrier.wait(timeout=3)
                wait = self.launch_waits.get(cell)
                if wait is not None and not wait.wait(timeout=3):
                    raise TimeoutError("fixture completion dependency timed out")
                time.sleep(self.delays.get(cell, 0.0))
                if cell in self.failing:
                    raise RunRefRuntimeError(
                        "run_ref_child_launch_failed",
                        "fixture_cell_failure",
                    )
                return _successful_process(
                    child,
                    value=f"{cell.arm_id}:{cell.rep}",
                )
            finally:
                with self._lock:
                    self.active -= 1
                    self.completions.append(cell)
                signal = self.completion_signals.get(cell)
                if signal is not None:
                    signal.set()

        return replace(
            base.dependencies(),
            materialize_source=materialize,
            launch_child=launch,
        )


def _execute(fixture, harnesses, *, clock=time.monotonic_ns, crash_hook=lambda _: None):
    return execute_trial_cells(
        fixture["request"],
        parent_state=fixture["parent_state"],
        parent_workspace=fixture["parent_workspace"],
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
        capsule_dir=fixture["capsule_dir"],
        sealed_opaque_labels=fixture["sealed"],
        dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=harnesses.factory,
            monotonic_ns=clock,
            crash_hook=crash_hook,
        ),
    )


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_random_completion_preserves_authored_order_and_exact_bounded_e1_requests(
    tmp_path: Path,
    seed: int,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    domain = fixture["request"].cell_domain
    randomizer = random.Random(seed)
    later_delays = {
        cell: randomizer.uniform(0.0, 0.008) for cell in domain[2:]
    }
    second_cell_completed = Event()
    harnesses = _CellHarnesses(
        delays=later_delays,
        first_wave_barrier=Barrier(
            fixture["request"].static_config.max_concurrency
        ),
        launch_waits={domain[0]: second_cell_completed},
        completion_signals={domain[1]: second_cell_completed},
    )

    result = _execute(fixture, harnesses)

    assert harnesses.completions.index(domain[1]) < harnesses.completions.index(
        domain[0]
    )
    assert tuple(outcome.cell for outcome in result.outcomes) == domain
    assert [outcome.envelope["value"] for outcome in result.outcomes] == [
        f"{cell.arm_id}:{cell.rep}" for cell in domain
    ]
    assert harnesses.max_active == fixture["request"].static_config.max_concurrency
    assert harnesses.max_active <= fixture["request"].static_config.max_concurrency
    assert Counter(cell for cell, _request in harnesses.requests) == Counter(domain)
    assert len({request.ledger_path for _cell, request in harnesses.requests}) == len(domain)
    assert all(outcome.status == "completed" for outcome in result.outcomes)


def test_parent_inputs_are_snapshotted_before_workers_can_observe_mutation(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    harnesses = _CellHarnesses()
    original_factory = harnesses.factory
    mutated = False

    def mutating_factory(cell, request):
        nonlocal mutated
        if not mutated:
            mutated = True
            fixture["parent_state"]["bound_inputs"]["payload"] = "mutated"
        return original_factory(cell, request)

    harnesses.factory = mutating_factory

    result = _execute(fixture, harnesses)

    assert all(outcome.status == "completed" for outcome in result.outcomes)
    assert fixture["parent_state"]["bound_inputs"]["payload"] == "mutated"
    assert all(
        request.parent_state["bound_inputs"]["payload"] == "fixed"
        for _cell, request in harnesses.requests
    )


def test_fresh_parent_input_mismatch_fails_before_creating_trial_state(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    fixture["parent_state"]["bound_inputs"]["payload"] = "mismatch"

    with pytest.raises(RunRefRuntimeError, match="trial_resolved_inputs_disagree"):
        _execute(fixture, _CellHarnesses())

    assert not fixture["scopes"][0].trial_root.exists()


def test_mixed_bundle_and_path_arms_select_their_own_capsule_mode(
    tmp_path: Path,
) -> None:
    fixture = _mixed_program_runtime_fixture(tmp_path)
    harnesses = _CellHarnesses()

    result = _execute(fixture, harnesses)

    assert all(outcome.status == "completed" for outcome in result.outcomes)
    assert Counter(harnesses.launches) == Counter(fixture["request"].cell_domain)


@pytest.mark.parametrize("capsule_kind", ["invalid", "missing", "absent"])
def test_invalid_bundle_capsule_fails_before_creating_trial_state(
    tmp_path: Path,
    capsule_kind: str,
) -> None:
    fixture = _mixed_program_runtime_fixture(tmp_path)
    bad_capsule = (tmp_path / "bad-capsule").resolve()
    if capsule_kind == "invalid":
        bad_capsule.write_text("not a directory\n", encoding="utf-8")
    fixture["capsule_dir"] = None if capsule_kind == "absent" else bad_capsule

    with pytest.raises(RunRefRuntimeError, match="capsule"):
        _execute(fixture, _CellHarnesses())

    assert not fixture["scopes"][0].trial_root.exists()
    assert all(not scope.effect_instance_root.exists() for scope in fixture["scopes"])


def test_durable_budget_window_does_not_reset_on_resume_and_rejects_backwards_time(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(
        tmp_path,
        arm_timeout_ms=1,
        trial_timeout_ms=10_000,
        max_concurrency=1,
    )
    harnesses = _CellHarnesses()

    def crash_orphan(boundary: str) -> None:
        if boundary == "after_e1_allocation_before_trial_allocation":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        execute_trial_cells(
            fixture["request"],
            parent_state=fixture["parent_state"],
            parent_workspace=fixture["parent_workspace"],
            parent_run_root=fixture["parent_run_root"],
            run_ref_root=fixture["run_ref_root"],
            capsule_dir=fixture["capsule_dir"],
            sealed_opaque_labels=fixture["sealed"],
            dependencies=TrialRuntimeDependencies(
                run_ref_dependencies=harnesses.factory,
                monotonic_ns=lambda: 0,
                wall_time_ns=lambda: 100,
                crash_hook=crash_orphan,
            ),
        )
    e1_before_backwards = fixture["scopes"][0].ledger_path.read_bytes()

    with pytest.raises(TrialLedgerError, match="clock.*backwards"):
        execute_trial_cells(
            fixture["request"],
            parent_state=fixture["parent_state"],
            parent_workspace=fixture["parent_workspace"],
            parent_run_root=fixture["parent_run_root"],
            run_ref_root=fixture["run_ref_root"],
            capsule_dir=fixture["capsule_dir"],
            sealed_opaque_labels=fixture["sealed"],
            dependencies=TrialRuntimeDependencies(
                run_ref_dependencies=harnesses.factory,
                monotonic_ns=lambda: 0,
                wall_time_ns=lambda: 99,
            ),
        )
    assert fixture["scopes"][0].ledger_path.read_bytes() == e1_before_backwards

    result = execute_trial_cells(
        fixture["request"],
        parent_state=fixture["parent_state"],
        parent_workspace=fixture["parent_workspace"],
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
        capsule_dir=fixture["capsule_dir"],
        sealed_opaque_labels=fixture["sealed"],
        dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=harnesses.factory,
            monotonic_ns=lambda: 0,
            wall_time_ns=lambda: 2_000_000,
        ),
    )

    assert harnesses.launches == []
    assert {outcome.status for outcome in result.outcomes} == {"failed"}
    assert {outcome.failure.code for outcome in result.outcomes} == {
        "trial_arm_timeout"
    }
    header = load_trial_event_ledger(result.ledger_path).rows[0].payload
    assert header["runtime_budget_window"]["opened_at_unix_ns"] == 100


def test_failure_is_a_terminal_value_and_does_not_cancel_siblings(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    failed_cell = fixture["request"].cell_domain[1]
    harnesses = _CellHarnesses(failing={failed_cell})

    result = _execute(fixture, harnesses)

    assert Counter(harnesses.launches) == Counter(fixture["request"].cell_domain)
    failed = result.outcomes[1]
    assert failed.status == "failed"
    assert failed.failure.record == {
        "code": "run_ref_child_launch_failed",
        "phase": "launched",
        "retryable": False,
        "secondary_causes": [],
    }
    assert all(
        outcome.status == "completed"
        for index, outcome in enumerate(result.outcomes)
        if index != 1
    )
    ledger = load_trial_event_ledger(result.ledger_path)
    [failure_row] = [
        row
        for row in ledger.rows
        if row.kind == "cell_failed" and row.payload["cell"] == failed_cell.record
    ]
    assert failure_row.payload["failure"] == failed.failure.record
    assert failure_row.payload["outcome_digest"].startswith("sha256:")
    assert failure_row.payload["evidence_digest"].startswith("sha256:")
    original_trial_ledger = result.ledger_path.read_bytes()
    for field in ("outcome_digest", "evidence_digest"):
        _rewrite_rechained_trial_ledger(
            result.ledger_path,
            lambda rows, field=field: next(
                row
                for row in rows
                if row["kind"] == "cell_failed"
                and row["payload"]["cell"] == failed_cell.record
            )["payload"].__setitem__(field, "sha256:" + "0" * 64),
        )
        with pytest.raises(TrialLedgerError, match=f"failed {field.split('_')[0]} digest"):
            load_trial_event_ledger(result.ledger_path)
        result.ledger_path.write_bytes(original_trial_ledger)
    failed_scope = fixture["scopes"][1]
    failed_e1 = load_attempt_ledger(failed_scope.ledger_path)
    assert failed_e1.rows[-1].row_digest == failed.e1_authority_row_digest
    assert failed_e1.rows[-1].bindings.workspace_path.is_dir()

    launches_before_resume = list(harnesses.launches)
    resumed = _execute(fixture, harnesses)
    assert harnesses.launches == launches_before_resume
    assert resumed.outcomes == result.outcomes
    assert failed_e1.rows[-1].bindings.workspace_path.is_dir()

    advance_attempt(
        failed_scope.ledger_path,
        visit=fixture["request"].visit,
        attempt_ordinal=failed_e1.rows[-1].attempt_ordinal,
        stage="child_completed",
        binding_updates={
            "child_terminal_state_digest": "sha256:" + "a" * 64,
            "result_payload_digest": "sha256:" + "b" * 64,
        },
    )
    with pytest.raises(TrialLedgerError, match="authority"):
        _execute(fixture, harnesses)


def test_fresh_operational_evidence_failure_is_a_value_but_reuse_tamper_is_not(
    tmp_path: Path,
) -> None:
    fresh = _runtime_fixture(tmp_path / "fresh")
    failed_cell = fresh["request"].cell_domain[0]
    fresh_harnesses = _CellHarnesses(evidence_failing={failed_cell})

    fresh_result = _execute(fresh, fresh_harnesses)

    assert fresh_result.outcomes[0].status == "failed"
    assert fresh_result.outcomes[0].failure.code == "run_ref_evidence_invalid"
    assert fresh_result.outcomes[0].failure.phase == "child_completed"
    assert all(
        outcome.status == "completed" for outcome in fresh_result.outcomes[1:]
    )

    reuse = _runtime_fixture(tmp_path / "reuse")
    reuse_harnesses = _CellHarnesses()
    _execute(reuse, reuse_harnesses)
    committed = load_attempt_ledger(reuse["scopes"][0].ledger_path).rows[-1]
    evidence_path = committed.bindings.workspace_path.parent / "evidence-manifest.json"
    evidence_path.write_bytes(canonical_json_bytes({}) + b"\n")

    with pytest.raises(RunRefRuntimeError, match="run_ref_evidence_invalid"):
        _execute(reuse, reuse_harnesses)


@pytest.mark.parametrize(
    ("arm_timeout_ms", "trial_timeout_ms", "expected_code"),
    [
        (1, 10_000, "trial_arm_timeout"),
        (10_000, 1, "trial_timeout"),
    ],
)
def test_deadline_settles_not_started_cells_and_allows_active_cells_to_finish(
    tmp_path: Path,
    arm_timeout_ms: int,
    trial_timeout_ms: int,
    expected_code: str,
) -> None:
    fixture = _runtime_fixture(
        tmp_path,
        arm_timeout_ms=arm_timeout_ms,
        trial_timeout_ms=trial_timeout_ms,
    )
    crossed = False
    lock = Lock()
    barrier = Barrier(2)

    def clock() -> int:
        with lock:
            return 20_000_000_000 if crossed else 0

    harnesses = _CellHarnesses(launch_barrier=barrier)
    original = harnesses.factory

    def factory(cell, request):
        dependencies = original(cell, request)
        launch = dependencies.launch_child

        def finish_then_expire(child):
            nonlocal crossed
            value = launch(child)
            with lock:
                crossed = True
            return value

        return replace(dependencies, launch_child=finish_then_expire, monotonic_ns=clock)

    harnesses.factory = factory
    result = _execute(fixture, harnesses, clock=clock)

    assert len(harnesses.launches) == 2
    assert [outcome.status for outcome in result.outcomes].count("completed") == 2
    assert all(
        outcome.envelope["accounting"]["elapsed_ms"] == 20_000
        for outcome in result.outcomes
        if outcome.status == "completed"
    )
    pending = [outcome for outcome in result.outcomes if outcome.status == "failed"]
    assert len(pending) == 2
    assert {outcome.failure.code for outcome in pending} == {expected_code}
    assert {outcome.failure.phase for outcome in pending} == {"scheduling"}
    assert {outcome.e1_authority_row_digest for outcome in pending} == {None}
    assert _execute(fixture, _CellHarnesses(), clock=clock).outcomes == result.outcomes


@pytest.mark.parametrize(
    ("boundary", "first_launches", "total_launches"),
    [
        ("after_e1_allocation_before_trial_allocation", 0, 4),
        ("after_e1_prepared_before_trial_prepared", 1, 5),
        ("after_trial_cell_settlement", 1, 4),
        ("after_e1_finalize_before_trial_commit", 1, 4),
    ],
)
def test_crash_gaps_reconcile_with_only_required_fresh_launches(
    tmp_path: Path,
    boundary: str,
    first_launches: int,
    total_launches: int,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _CellHarnesses()
    crashed = False

    def crash_hook(observed: str) -> None:
        nonlocal crashed
        if not crashed and observed == boundary:
            crashed = True
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash, match=boundary):
        _execute(fixture, harnesses, crash_hook=crash_hook)
    assert len(harnesses.launches) == first_launches

    result = _execute(fixture, harnesses)

    assert len(harnesses.launches) == total_launches
    assert all(outcome.status == "completed" for outcome in result.outcomes)
    first_scope = fixture["scopes"][0]
    rows = load_attempt_ledger(first_scope.ledger_path).rows
    assert len([row for row in rows if row.stage == "committed"]) == 1
    if boundary in {
        "after_e1_allocation_before_trial_allocation",
        "after_e1_prepared_before_trial_prepared",
    }:
        assert rows[-1].attempt_ordinal == 2


def test_orphan_allocation_after_discard_reconciles_the_exact_fresh_ordinal(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _CellHarnesses()
    crashed_prepared = False

    def crash_prepared(boundary: str) -> None:
        nonlocal crashed_prepared
        if not crashed_prepared and boundary == "after_e1_prepared_before_trial_prepared":
            crashed_prepared = True
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(fixture, harnesses, crash_hook=crash_prepared)

    crashed_orphan = False

    def crash_orphan(boundary: str) -> None:
        nonlocal crashed_orphan
        if not crashed_orphan and boundary == "after_e1_allocation_before_trial_allocation":
            crashed_orphan = True
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(fixture, harnesses, crash_hook=crash_orphan)
    assert len(harnesses.launches) == 1

    result = _execute(fixture, harnesses)

    assert all(outcome.status == "completed" for outcome in result.outcomes)
    rows = load_attempt_ledger(fixture["scopes"][0].ledger_path).rows
    assert rows[-1].attempt_ordinal == 3
    assert {
        row.attempt_ordinal for row in rows if row.stage == "allocated"
    } == {1, 2, 3}
    assert len(harnesses.launches) == 5


def test_nonallocation_suffix_after_discard_is_not_reconciled_as_an_orphan(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _CellHarnesses()

    def crash_prepared(boundary: str) -> None:
        if boundary == "after_e1_prepared_before_trial_prepared":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(fixture, harnesses, crash_hook=crash_prepared)

    def crash_orphan(boundary: str) -> None:
        if boundary == "after_e1_allocation_before_trial_allocation":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(fixture, harnesses, crash_hook=crash_orphan)
    scope = fixture["scopes"][0]
    advance_attempt(
        scope.ledger_path,
        visit=fixture["request"].visit,
        attempt_ordinal=2,
        stage="materialized",
        binding_updates={"verified_git_tree_id": "git-tree:" + "a" * 40},
    )

    with pytest.raises(TrialLedgerError, match="orphan.*ambiguous"):
        _execute(fixture, harnesses)
    assert len(harnesses.launches) == 1


def test_orphan_allocation_must_match_the_complete_current_e1_identity(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _CellHarnesses()

    def crash_orphan(boundary: str) -> None:
        if boundary == "after_e1_allocation_before_trial_allocation":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(fixture, harnesses, crash_hook=crash_orphan)
    path = fixture["scopes"][0].ledger_path
    row = json.loads(path.read_bytes())
    row["bindings"]["input_digest"] = "sha256:" + "0" * 64
    preimage = dict(row)
    preimage.pop("row_digest")
    row["row_digest"] = canonical_sha256(preimage)
    path.write_bytes(canonical_json_bytes(row) + b"\n")

    with pytest.raises(RunRefRuntimeError, match="allocation_authority_disagrees"):
        _execute(fixture, harnesses)
    assert harnesses.launches == []


def test_failed_reuse_revalidates_complete_current_e1_identity(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    failed_cell = fixture["request"].cell_domain[0]
    harnesses = _CellHarnesses(failing={failed_cell})
    result = _execute(fixture, harnesses)
    scope = fixture["scopes"][0]

    e1_rows = _rewrite_rechained_e1_ledger(
        scope.ledger_path,
        lambda rows: [
            row["bindings"].__setitem__(
                "input_digest",
                "sha256:" + "0" * 64,
            )
            for row in rows
        ],
    )

    def correlate_trial(rows) -> None:
        allocation = next(
            row
            for row in rows
            if row["kind"] == "cell_allocated"
            and row["payload"]["cell"] == failed_cell.record
        )
        failed = next(
            row
            for row in rows
            if row["kind"] == "cell_failed"
            and row["payload"]["cell"] == failed_cell.record
        )
        allocation["payload"]["e1_allocation_row_digest"] = e1_rows[0][
            "row_digest"
        ]
        failed["payload"]["e1_authority_row_digest"] = e1_rows[-1][
            "row_digest"
        ]
        failed["payload"]["evidence_digest"] = canonical_sha256(
            {
                "schema_version": "trial_cell_partial_evidence.v1",
                "cell": failed_cell.record,
                "failure_digest": failed["payload"]["failure_digest"],
                "e1_authority_row_digest": e1_rows[-1]["row_digest"],
            }
        )

    _rewrite_rechained_trial_ledger(result.ledger_path, correlate_trial)

    with pytest.raises(RunRefRuntimeError, match="attempt_authority_disagrees"):
        _execute(fixture, harnesses)


def test_existing_ledger_mismatch_fails_before_recreating_any_cell_root(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    result = _execute(fixture, _CellHarnesses())
    missing_root = fixture["scopes"][-1].effect_instance_root
    shutil.rmtree(missing_root)
    _rewrite_rechained_trial_ledger(
        result.ledger_path,
        lambda rows: rows[0]["payload"].__setitem__(
            "evaluation_digest",
            "sha256:" + "0" * 64,
        ),
    )

    with pytest.raises(TrialLedgerError, match="current runtime request"):
        _execute(fixture, _CellHarnesses())
    assert not missing_root.exists()


def test_valid_bound_e1_root_missing_fails_without_recreation(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    _execute(fixture, _CellHarnesses())
    missing_root = fixture["scopes"][0].effect_instance_root
    shutil.rmtree(missing_root)

    with pytest.raises(TrialLedgerError, match="bound E1 root"):
        _execute(fixture, _CellHarnesses())

    assert not missing_root.exists()


def _correlate_failed_trial_authority(
    path: Path,
    *,
    cell: TrialCellKey,
    authority_digest: str,
    phase: str,
) -> None:
    def correlate(rows) -> None:
        failed = next(
            row
            for row in rows
            if row["kind"] == "cell_failed"
            and row["payload"]["cell"] == cell.record
        )
        failure = failed["payload"]["failure"]
        failure["phase"] = phase
        failed["payload"]["failure_digest"] = canonical_sha256(failure)
        failed["payload"]["outcome_digest"] = canonical_sha256(
            {
                "schema_version": "trial_cell_failed_outcome.v1",
                "cell": cell.record,
                "failure": failure,
            }
        )
        failed["payload"]["e1_authority_row_digest"] = authority_digest
        failed["payload"]["evidence_digest"] = canonical_sha256(
            {
                "schema_version": "trial_cell_partial_evidence.v1",
                "cell": cell.record,
                "failure_digest": failed["payload"]["failure_digest"],
                "e1_authority_row_digest": authority_digest,
            }
        )

    _rewrite_rechained_trial_ledger(path, correlate)


def test_failed_reuse_rejects_failure_phase_that_disagrees_with_e1_head(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    failed_cell = fixture["request"].cell_domain[0]
    result = _execute(fixture, _CellHarnesses(failing={failed_cell}))
    authority = load_attempt_ledger(fixture["scopes"][0].ledger_path).rows[-1]
    _correlate_failed_trial_authority(
        result.ledger_path,
        cell=failed_cell,
        authority_digest=authority.row_digest,
        phase="materialized",
    )

    with pytest.raises(TrialLedgerError, match="failure phase"):
        _execute(fixture, _CellHarnesses())


def test_failed_reuse_rejects_non_in_progress_e1_head(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    failed_cell = fixture["request"].cell_domain[0]
    result = _execute(fixture, _CellHarnesses(failing={failed_cell}))
    scope = fixture["scopes"][0]
    launched = load_attempt_ledger(scope.ledger_path).rows[-1]
    child_completed = advance_attempt(
        scope.ledger_path,
        visit=launched.visit,
        attempt_ordinal=launched.attempt_ordinal,
        stage="child_completed",
        binding_updates={
            "child_terminal_state_digest": "sha256:" + "1" * 64,
            "result_payload_digest": "sha256:" + "2" * 64,
        },
    )
    delta_captured = advance_attempt(
        scope.ledger_path,
        visit=child_completed.visit,
        attempt_ordinal=child_completed.attempt_ordinal,
        stage="delta_captured",
        binding_updates={
            "workspace_delta_digest": "sha256:" + "3" * 64,
            "accounting_digest": "sha256:" + "4" * 64,
            "evidence_manifest_digest": "sha256:" + "5" * 64,
        },
    )
    pending = advance_attempt(
        scope.ledger_path,
        visit=delta_captured.visit,
        attempt_ordinal=delta_captured.attempt_ordinal,
        stage="completed_pending_parent_commit",
        binding_updates={},
    )
    _correlate_failed_trial_authority(
        result.ledger_path,
        cell=failed_cell,
        authority_digest=pending.row_digest,
        phase=pending.stage,
    )

    with pytest.raises(RunRefRuntimeError, match="attempt_authority_disagrees"):
        _execute(fixture, _CellHarnesses())


def test_workers_block_on_cell_bound_events_and_only_coordinator_mutates_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    harnesses = _CellHarnesses(delays={fixture["request"].cell_domain[0]: 0.02})
    coordinator = get_ident()
    mutation_threads: list[int] = []
    names = (
        "initialize_trial_event_ledger",
        "persist_run_ref_lifecycle_event",
        "append_trial_e1_boundary",
        "append_trial_cell_settlement",
        "append_trial_e1_committed",
    )
    for name in names:
        original = getattr(trial_runtime_module, name)

        def wrapper(*args, __original=original, **kwargs):
            mutation_threads.append(get_ident())
            return __original(*args, **kwargs)

        monkeypatch.setattr(trial_runtime_module, name, wrapper)

    result = _execute(fixture, harnesses)

    assert all(outcome.status == "completed" for outcome in result.outcomes)
    assert mutation_threads and set(mutation_threads) == {coordinator}
    assert harnesses.launch_threads and coordinator not in harnesses.launch_threads


def test_cross_routed_acknowledgement_fails_closed_and_joins_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    harnesses = _CellHarnesses()
    original = trial_runtime_module.persist_run_ref_lifecycle_event
    first_ack = None

    def cross_route(request, event):
        nonlocal first_ack
        acknowledgement = original(request, event)
        if event.stage != "allocated":
            return acknowledgement
        if first_ack is None:
            first_ack = acknowledgement
            return acknowledgement
        return first_ack

    monkeypatch.setattr(
        trial_runtime_module,
        "persist_run_ref_lifecycle_event",
        cross_route,
    )

    started = time.monotonic()
    with pytest.raises((ValueError, RunRefRuntimeError), match="acknowledgement|scope"):
        _execute(fixture, harnesses)
    assert time.monotonic() - started < 5


def test_authority_errors_are_not_converted_to_failed_cell_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    harnesses = _CellHarnesses()
    original = trial_runtime_module.persist_run_ref_lifecycle_event

    def corrupt_authority(request, event):
        if event.stage == "allocated":
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "fixture_authority_failure",
            )
        return original(request, event)

    monkeypatch.setattr(
        trial_runtime_module,
        "persist_run_ref_lifecycle_event",
        corrupt_authority,
    )

    with pytest.raises(RunRefRuntimeError, match="run_ref_ledger_invalid"):
        _execute(fixture, harnesses)
