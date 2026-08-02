from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from orchestrator.state import StepResult
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.resume_planner import ResumeStateIntegrityError
from orchestrator.workflow.step_results import to_step_result
from orchestrator.workflow.trial.contracts import build_sealed_opaque_label_map
from orchestrator.workflow.trial.contracts import derive_trial_cell_effect_scopes
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from tests.test_workflow_trial_adjudication import _blinded_cell_harnesses
from tests.test_workflow_trial_outer_settlement import _prepare_terminal_trial
from tests.test_workflow_trial_runtime import _execute
from tests.test_workflow_trial_runtime import _runtime_fixture


def test_compiled_exact_pin_trial_executes_and_commits_parent_result(
    tmp_path: Path,
) -> None:
    from orchestrator.runtime_observability import (
        record_compiled_frontend_provenance,
    )
    from orchestrator.state import StateManager
    from orchestrator.workflow.pure_result_replay import (
        DERIVED_PURE_REPLAY_PROFILE,
    )
    from orchestrator.workflow.trial.runtime import TrialRuntimeDependencies
    from orchestrator.workflow_lisp.wcc.route import (
        workflow_lisp_context_with_lowering_schema,
    )
    from tests.test_workflow_lisp_trial_lowering import (
        COMMIT_A,
        COMMIT_B,
        _compile_trial_source,
        _write_trial_module,
    )
    from tests.test_workflow_trial_adjudication import (
        _Executor,
        _dependencies,
    )
    from tests.workflow_bundle_helpers import bundle_context_dict

    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    source_path = _write_trial_module(workspace)
    compiled = _compile_trial_source(source_path, workspace=workspace)
    bundle = compiled.validated_bundle
    trial_nodes = tuple(
        node for node in bundle.ir.nodes.values() if node.kind.value == "trial"
    )
    assert len(trial_nodes) == 1
    assert tuple(
        arm.run_ref.source.commit
        for arm in trial_nodes[0].execution_config.trial.arms
    ) == (COMMIT_A, COMMIT_B)

    run_ref_root = (tmp_path / "child-runs").resolve()
    run_ref_root.mkdir()
    manager = StateManager(
        workspace=workspace,
        run_id="deterministic-trial-smoke",
        state_dir=(workspace / "state").resolve(),
    )
    context = workflow_lisp_context_with_lowering_schema(
        bundle_context_dict(bundle),
        compiled.manifest.lowering_schema_version,
    )
    run_state = manager.initialize(
        source_path.relative_to(workspace).as_posix(),
        context=context,
        bound_inputs={},
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    manager.bind_run_ref_root(run_ref_root)
    with manager.state_transaction() as transaction_state:
        record_compiled_frontend_provenance(
            transaction_state,
            bundle.provenance,
        )

    harnesses = _blinded_cell_harnesses()
    evaluation_dependencies, check_calls = _dependencies(_Executor())
    executor = WorkflowExecutor(
        bundle,
        workspace,
        manager,
        logs_dir=manager.logs_dir,
        max_retries=0,
        retry_delay_ms=0,
        provider_observation_enabled=False,
    )
    executor._trial_runtime_dependencies = TrialRuntimeDependencies(
        run_ref_dependencies=harnesses.factory,
    )
    executor._trial_evaluation_dependencies = evaluation_dependencies

    result = executor.execute(
        run_id=run_state.run_id,
        on_error="stop",
        max_retries=0,
        retry_delay_ms=0,
    )

    assert result["status"] == "completed", result
    terminal = tuple(
        step
        for step in result["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("trial"), dict)
    )
    assert len(terminal) == 1
    assert terminal[0]["status"] == "completed"
    assert terminal[0]["trial"]["verdict"]["ranking"] == ["direct", "orc"]
    assert terminal[0]["trial"]["verdict"]["selected_arm"] is None
    assert result["workflow_outputs"][
        "return__verdict__budget_accounting__token_usage__variant"
    ] == "UNKNOWN"
    assert (
        "return__verdict__budget_accounting__token_usage__prompt_tokens"
        not in result["workflow_outputs"]
    )
    ledger_paths = tuple(manager.run_root.rglob("trial-events.jsonl"))
    assert len(ledger_paths) == 1
    ledger = load_trial_event_ledger(ledger_paths[0])
    assert ledger.rows[-1].kind == "trial_parent_committed"
    assert len(harnesses.launches) == 4
    assert check_calls == []


def test_trial_step_result_round_trips_exact_outer_authority() -> None:
    trial = {
        "schema_version": "trial_parent_result.v1",
        "request_digest": "sha256:" + "1" * 64,
        "prepared_row_digest": "sha256:" + "2" * 64,
        "result_envelope": {"outcomes": [], "verdict": {}, "verdict_artifact": "artifacts/trials/verdict.json"},
    }

    encoded = StepResult(status="completed", trial=trial).to_dict()
    decoded = to_step_result(encoded, "Compare")

    assert encoded["trial"] == trial
    assert decoded.trial == trial


def test_trial_executor_surface_owns_its_atomic_parent_settlement() -> None:
    executor = object.__new__(WorkflowExecutor)
    executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.TRIAL  # type: ignore[method-assign]
    calls: list[tuple[object, ...]] = []
    completed = {
        "status": "completed",
        "exit_code": 0,
        "artifacts": {"verdict": {"selected_arm": "direct"}},
        "trial": {"schema_version": "trial_parent_result.v1"},
    }
    executor._execute_trial = (  # type: ignore[attr-defined, method-assign]
        lambda step, state, *, step_name: (
            calls.append((step, state, step_name)) or completed
        )
    )
    executor._persist_step_result = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("trial owns its atomic parent settlement")
        )
    )
    state = {"steps": {}}
    step = {"name": "Compare", "id": "root.compare"}

    assert WorkflowExecutor._resolve_step_type(executor, step) == "trial"
    assert WorkflowExecutor._run_top_level_step(
        executor,
        step,
        state,
        step_name="Compare",
    ) is completed
    assert calls == [(step, state, "Compare")]


def test_trial_resume_reuses_the_interrupted_visit_identity() -> None:
    executor = object.__new__(WorkflowExecutor)
    executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.TRIAL  # type: ignore[method-assign]
    state = {
        "step_visits": {"Compare": 3},
        "current_step": {
            "name": "Compare",
            "step_id": "root.compare",
            "type": "trial",
            "status": "failed",
            "visit_count": 3,
        },
    }

    assert WorkflowExecutor._run_ref_resume_visit_count(
        executor,
        state,
        {"name": "Compare", "step_id": "root.compare"},
        step_name="Compare",
        step_id="root.compare",
        resume_current_step=True,
    ) == 3


@pytest.mark.parametrize(
    "mutation",
    (
        lambda state: state["current_step"].__setitem__("type", "run_ref"),
        lambda state: state["current_step"].__setitem__("status", "completed"),
        lambda state: state["current_step"].__setitem__("visit_count", 2),
        lambda state: state["step_visits"].__setitem__("Compare", 4),
    ),
)
def test_trial_resume_visit_identity_mismatch_fails_closed(mutation) -> None:
    executor = object.__new__(WorkflowExecutor)
    executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.TRIAL  # type: ignore[method-assign]
    state = {
        "step_visits": {"Compare": 3},
        "current_step": {
            "name": "Compare",
            "step_id": "root.compare",
            "type": "trial",
            "status": "failed",
            "visit_count": 3,
        },
    }
    mutation(state)

    with pytest.raises(
        ResumeStateIntegrityError,
        match="trial interrupted visit identity is invalid",
    ):
        WorkflowExecutor._run_ref_resume_visit_count(
            executor,
            state,
            {"name": "Compare", "step_id": "root.compare"},
            step_name="Compare",
            step_id="root.compare",
            resume_current_step=True,
        )


def test_trial_executor_atomically_commits_typed_result_before_ledger_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path / "fixture")
    request_authority = fixture["request"]
    step_config = request_authority.step_config
    workspace = fixture["parent_workspace"]
    parent_run_root = fixture["parent_run_root"]
    run_ref_root = fixture["run_ref_root"]
    build_root = (tmp_path / "build").resolve()
    (build_root / "run_ref_bundle_capsule.v1").mkdir(parents=True)
    events: list[str] = []
    persisted: dict[str, object] = {
        "run_id": "parent-run",
        "steps": {},
        "current_step": {
            "name": "Compare",
            "step_id": "root.compare",
            "type": "trial",
            "status": "running",
            "visit_count": 1,
        },
    }

    class FakeStateManager:
        run_root = parent_run_root
        state = SimpleNamespace(run_ref_root=run_ref_root.as_posix())

        def finalize_step_with_dataflow(self, step_name, result, **kwargs):
            assert kwargs["expected_step_name"] == "Compare"
            assert kwargs["expected_step_id"] == "root.compare"
            assert kwargs["expected_visit_count"] == 1
            assert kwargs["expected_step_type"] == "trial"
            assert kwargs["expected_step_status"] == "running"
            assert kwargs["commit_guard"]() is True
            assert result.trial == envelope
            assert result.artifacts == artifacts
            persisted["steps"] = {step_name: result.to_dict()}
            persisted["current_step"] = None
            events.append("parent_state")

        def load(self):
            pytest.fail("trial settlement bypassed the aggregate root reread")

    executor = object.__new__(WorkflowExecutor)
    executor.workspace = workspace
    executor.state_manager = FakeStateManager()
    executor.loaded_bundle = SimpleNamespace(
        provenance=SimpleNamespace(frontend_build_root=build_root),
    )
    executor.provider_registry = object()
    executor.prompt_composer = object()
    executor.provider_executor = object()
    executor._step_id = lambda _step: "root.compare"  # type: ignore[method-assign]
    executor._executable_node_for_step = (  # type: ignore[method-assign]
        lambda _step: SimpleNamespace(execution_config=step_config)
    )
    executor._resolve_output_contract_paths = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: (
            None,
            {"path": "artifacts/trial-result.json", "fields": []},
            None,
        )
    )
    executor._resolve_workspace_path = (  # type: ignore[method-assign]
        lambda relative: (workspace / relative).resolve()
    )
    artifacts = {
        "outcomes": [{"variant": "Completed", "arm_id": "direct"}],
        "verdict__selected_arm": "direct",
        "verdict_artifact": "artifacts/trials/verdict.json",
    }
    executor._apply_expected_outputs_contract = (  # type: ignore[method-assign]
        lambda _step, result, _state: {**result, "artifacts": artifacts}
    )
    executor._record_published_artifacts = (  # type: ignore[method-assign]
        lambda *_args, **kwargs: events.append("published") or None
    )
    executor._finalize_consumes = (  # type: ignore[method-assign]
        lambda *_args, **kwargs: events.append("consumes")
    )
    executor._attach_outcome = lambda _step, result: result  # type: ignore[method-assign]
    executor._emit_lexical_checkpoint_shadow_after_step_commit = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: events.append("checkpoint")
    )
    executor._emit_step_summary = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: events.append("summary")
    )
    owner = SimpleNamespace(
        root_manager=SimpleNamespace(
            run_id="parent-run",
            state=SimpleNamespace(run_ref_root=run_ref_root.as_posix()),
            bind_run_ref_root=lambda path: path,
            load=lambda: (
                events.append("parent_state_reread")
                or SimpleNamespace(
                    to_dict=lambda: json.loads(json.dumps(persisted)),
                )
            ),
        ),
        resume_scope_path=SimpleNamespace(call_frame_ids=()),
        aggregate_root=parent_run_root,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.resolve_aggregate_run_owner",
        lambda _manager: owner,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.os.urandom",
        lambda size: b"integration-label-salt" * 2 if size == 32 else pytest.fail(),
    )

    execution = SimpleNamespace(
        ledger_path=(parent_run_root / "trials" / "trial-events.jsonl").resolve(),
    )
    envelope = {
        "outcomes": [{"variant": "Completed", "arm_id": "direct"}],
        "verdict": {
            "selected_arm": "direct",
            "budget_accounting": {"elapsed_ms": 17},
        },
        "verdict_artifact": "artifacts/trials/verdict.json",
    }
    adjudicated = SimpleNamespace(
        authored_outcomes=tuple(envelope["outcomes"]),
        verdict=envelope["verdict"],
        verdict_artifact=SimpleNamespace(relpath=envelope["verdict_artifact"]),
    )
    prepared = SimpleNamespace(row=SimpleNamespace(row_digest="sha256:" + "7" * 64))

    def execute_cells(request, **kwargs):
        assert request.visit.record == request_authority.visit.record
        assert request.resolved_inputs_by_arm == request_authority.resolved_inputs_by_arm
        assert kwargs["parent_state"]["bound_inputs"] == {"payload": "fixed"}
        assert kwargs["parent_workspace"] == workspace
        assert kwargs["parent_run_root"] == parent_run_root
        assert kwargs["run_ref_root"] == run_ref_root
        assert kwargs["capsule_dir"] == build_root / "run_ref_bundle_capsule.v1"
        expected_labels = build_sealed_opaque_label_map(
            request.cell_domain,
            salt=b"integration-label-salt" * 2,
        )
        assert kwargs["sealed_opaque_labels"] == expected_labels
        events.append("cells")
        return execution

    monkeypatch.setattr(
        "orchestrator.workflow.trial.runtime.execute_trial_cells",
        execute_cells,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.adjudication.evaluate_trial_execution",
        lambda request, observed, **kwargs: (
            events.append("adjudicated") or adjudicated
        ),
    )

    def prepare(path, **kwargs):
        assert path == execution.ledger_path
        assert kwargs["request"].digest == request_authority.digest
        assert kwargs["parent_workspace"] == workspace
        assert kwargs["result_envelope"] == envelope
        events.append("prepared" if events.count("prepared") == 0 else "guard")
        return prepared

    monkeypatch.setattr(
        "orchestrator.workflow.trial.settlement.prepare_trial_parent_settlement",
        prepare,
    )

    def commit(path, **kwargs):
        assert path == execution.ledger_path
        assert kwargs["request"].digest == request_authority.digest
        assert kwargs["prepared"] is prepared
        assert kwargs["step_name"] == "Compare"
        assert kwargs["expected_artifacts"] == artifacts
        actual = kwargs["read_parent_state"]()
        assert actual["current_step"] is None
        assert actual["steps"]["Compare"]["trial"] == envelope
        events.append("ledger_committed")
        return SimpleNamespace(kind="trial_parent_committed")

    monkeypatch.setattr(
        "orchestrator.workflow.trial.settlement.commit_trial_parent_settlement",
        commit,
    )
    state = {
        "run_id": "parent-run",
        "bound_inputs": {"payload": "fixed"},
        "steps": {},
        "step_visits": {"Compare": 1},
        "current_step": dict(persisted["current_step"]),
        "artifact_versions": {},
        "artifact_consumes": {},
        "private_artifact_versions": {},
        "private_artifact_consumes": {},
    }
    step = {"name": "Compare", "step_id": "root.compare"}

    result = WorkflowExecutor._execute_trial(
        executor,
        step,
        state,
        step_name="Compare",
    )

    assert result["trial"] == envelope
    assert result["artifacts"] == artifacts
    assert json.loads(
        (workspace / "artifacts" / "trial-result.json").read_text(
            encoding="utf-8",
        )
    ) == envelope
    assert state["current_step"] is None
    assert events == [
        "cells",
        "adjudicated",
        "prepared",
        "published",
        "consumes",
        "guard",
        "parent_state",
        "parent_state_reread",
        "ledger_committed",
        "checkpoint",
        "summary",
    ]


@pytest.mark.parametrize("already_committed", (False, True))
def test_completed_trial_resume_only_reconciles_the_outer_commit_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    already_committed: bool,
) -> None:
    fixture = _runtime_fixture(tmp_path / "fixture")
    request_authority = fixture["request"]
    step_config = request_authority.step_config
    parent_run_root = fixture["parent_run_root"]
    run_ref_root = fixture["run_ref_root"]
    envelope = {
        "outcomes": [],
        "verdict": {"budget_accounting": {"elapsed_ms": 0}},
        "verdict_artifact": "artifacts/trials/verdict.json",
    }
    artifacts = {"verdict_artifact": envelope["verdict_artifact"]}
    state = {
        "run_id": "parent-run",
        "bound_inputs": {"payload": "fixed"},
        "current_step": None,
        "steps": {
            "Compare": {
                "status": "completed",
                "name": "Compare",
                "step_id": "root.compare",
                "visit_count": 1,
                "trial": envelope,
                "artifacts": artifacts,
            }
        },
    }
    events: list[str] = []

    class FakeStateManager:
        state = SimpleNamespace(run_ref_root=run_ref_root.as_posix())

        def load(self):
            pytest.fail("trial reconciliation bypassed the aggregate root reread")

    executor = object.__new__(WorkflowExecutor)
    executor.workspace = fixture["parent_workspace"]
    executor.state_manager = FakeStateManager()
    executor.loaded_bundle = SimpleNamespace(
        provenance=SimpleNamespace(frontend_build_root=None),
    )
    executor._step_node_ids = ["node"]
    step = {"name": "Compare", "step_id": "root.compare"}
    executor._runtime_step_for_node_id = lambda _node_id: step  # type: ignore[method-assign]
    executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.TRIAL  # type: ignore[method-assign]
    executor._executable_node_for_step = (  # type: ignore[method-assign]
        lambda _step: SimpleNamespace(execution_config=step_config)
    )
    executor._step_id = lambda _step: "root.compare"  # type: ignore[method-assign]
    executor._emit_lexical_checkpoint_shadow_after_step_commit = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: events.append("checkpoint")
    )
    owner = SimpleNamespace(
        root_manager=SimpleNamespace(
            run_id="parent-run",
            state=SimpleNamespace(run_ref_root=run_ref_root.as_posix()),
            bind_run_ref_root=lambda path: path,
            load=lambda: (
                events.append("parent_state_reread")
                or SimpleNamespace(
                    to_dict=lambda: json.loads(json.dumps(state)),
                )
            ),
        ),
        resume_scope_path=SimpleNamespace(call_frame_ids=()),
        aggregate_root=parent_run_root,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.resolve_aggregate_run_owner",
        lambda _manager: owner,
    )
    prepared = SimpleNamespace(row=SimpleNamespace(row_digest="sha256:" + "8" * 64))
    [scope, *_] = derive_trial_cell_effect_scopes(
        request=request_authority,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    ledger_path = scope.trial_root / "trial-events.jsonl"

    def prepare(path, **kwargs):
        assert path == ledger_path
        assert kwargs["request"].digest == request_authority.digest
        assert kwargs["result_envelope"] == envelope
        events.append("prepared_validated")
        return prepared

    def commit(path, **kwargs):
        assert path == ledger_path
        assert kwargs["request"].digest == request_authority.digest
        assert kwargs["prepared"] is prepared
        assert kwargs["step_name"] == "Compare"
        assert kwargs["expected_artifacts"] == artifacts
        assert kwargs["read_parent_state"]()["steps"]["Compare"]["trial"] == envelope
        events.append("commit_reused" if already_committed else "commit_appended")
        return SimpleNamespace(kind="trial_parent_committed")

    monkeypatch.setattr(
        "orchestrator.workflow.trial.settlement.prepare_trial_parent_settlement",
        prepare,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.settlement.commit_trial_parent_settlement",
        commit,
    )
    executor._trial_reconciliation_parent_state_reader = (  # type: ignore[method-assign]
        lambda **_kwargs: lambda: owner.root_manager.load().to_dict()
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.runtime.execute_trial_cells",
        lambda *_args, **_kwargs: pytest.fail("completed trial launched a child"),
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.adjudication.evaluate_trial_execution",
        lambda *_args, **_kwargs: pytest.fail("completed trial repeated evaluation"),
    )

    WorkflowExecutor._reconcile_completed_trials_before_resume(executor, state)

    assert events == [
        "prepared_validated",
        "parent_state_reread",
        "commit_reused" if already_committed else "commit_appended",
        "checkpoint",
    ]


def test_completed_trial_resume_fails_closed_before_any_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path / "fixture")
    step_config = fixture["request"].step_config
    state = {
        "run_id": "parent-run",
        "bound_inputs": {"payload": "fixed"},
        "current_step": None,
        "steps": {
            "Compare": {
                "status": "completed",
                "name": "Compare",
                "step_id": "root.compare",
                "visit_count": 1,
                "trial": {"tampered": True},
                "artifacts": {"verdict_artifact": "tampered"},
            }
        },
    }
    executor = object.__new__(WorkflowExecutor)
    executor.workspace = fixture["parent_workspace"]
    executor.state_manager = SimpleNamespace(
        state=SimpleNamespace(run_ref_root=fixture["run_ref_root"].as_posix()),
    )
    executor.loaded_bundle = SimpleNamespace(
        provenance=SimpleNamespace(frontend_build_root=None),
    )
    executor._step_node_ids = ["node"]
    step = {"name": "Compare", "step_id": "root.compare"}
    executor._runtime_step_for_node_id = lambda _node_id: step  # type: ignore[method-assign]
    executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.TRIAL  # type: ignore[method-assign]
    executor._executable_node_for_step = (  # type: ignore[method-assign]
        lambda _step: SimpleNamespace(execution_config=step_config)
    )
    executor._step_id = lambda _step: "root.compare"  # type: ignore[method-assign]
    owner = SimpleNamespace(
        root_manager=SimpleNamespace(
            run_id="parent-run",
            state=SimpleNamespace(run_ref_root=fixture["run_ref_root"].as_posix()),
            bind_run_ref_root=lambda path: path,
        ),
        resume_scope_path=SimpleNamespace(call_frame_ids=()),
        aggregate_root=fixture["parent_run_root"],
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.resolve_aggregate_run_owner",
        lambda _manager: owner,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.settlement.prepare_trial_parent_settlement",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("trial terminal authority is tampered")
        ),
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.runtime.execute_trial_cells",
        lambda *_args, **_kwargs: pytest.fail("invalid trial launched a child"),
    )
    monkeypatch.setattr(
        "orchestrator.workflow.trial.adjudication.evaluate_trial_execution",
        lambda *_args, **_kwargs: pytest.fail("invalid trial repeated evaluation"),
    )

    with pytest.raises(ValueError, match="terminal authority is tampered"):
        WorkflowExecutor._reconcile_completed_trials_before_resume(executor, state)


def test_ordinary_resume_does_not_import_or_allocate_trial_runtime(
    tmp_path: Path,
) -> None:
    probe_root = (tmp_path / "ordinary-run").resolve()
    probe_root.mkdir()
    code = """
import json
from pathlib import Path
import sys
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor

root = Path(sys.argv[1])
executor = object.__new__(WorkflowExecutor)
executor._step_node_ids = ["plain"]
executor._runtime_step_for_node_id = lambda _node_id: {"name": "Plain"}
executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.COMMAND
WorkflowExecutor._reconcile_completed_trials_before_resume(
    executor,
    {"steps": {}},
)
blocked = [
    name
    for name in (
        "orchestrator.workflow.trial.runtime",
        "orchestrator.workflow.trial.adjudication",
        "orchestrator.workflow.trial.settlement",
    )
    if name in sys.modules
]
print(json.dumps({"blocked": blocked, "entries": list(root.iterdir())}))
"""

    completed = subprocess.run(
        [sys.executable, "-c", code, probe_root.as_posix()],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"blocked": [], "entries": []}


def test_ordinary_resume_does_not_traverse_completed_trial_reconciliation() -> None:
    raw_state = {
        "run_id": "ordinary-run",
        "status": "running",
        "current_step": None,
        "steps": {"Plain": {"status": "completed"}},
    }
    executor = object.__new__(WorkflowExecutor)
    executor.executable_ir = SimpleNamespace(
        nodes={"plain": SimpleNamespace(kind=ExecutableNodeKind.COMMAND)},
    )
    executor._step_node_ids = ["plain"]
    executor.state_manager = SimpleNamespace(
        load=lambda: SimpleNamespace(
            to_dict=lambda: json.loads(json.dumps(raw_state)),
        )
    )
    executor.provider_observation_enabled = False
    executor.provider_observation_manager = None
    executor.summary_observer = None
    executor._wait_for_provider_observation_dependents = lambda: None  # type: ignore[method-assign]
    executor._close_owned_provider_observation_manager = lambda: None  # type: ignore[method-assign]
    executor._reconcile_completed_run_refs_before_resume = lambda _state: None  # type: ignore[method-assign]
    executor._configure_pure_replay_runtime = (  # type: ignore[method-assign]
        lambda _run_state, *, resume: setattr(
            executor,
            "_pure_replay_runtime",
            None,
        )
    )
    executor._reconcile_completed_trials_before_resume = (  # type: ignore[method-assign]
        lambda _state: pytest.fail(
            "ordinary resume traversed completed trial reconciliation"
        )
    )

    class StopAfterTrialGate(RuntimeError):
        pass

    executor._initialize_provider_observation_manager = (  # type: ignore[method-assign]
        lambda: (_ for _ in ()).throw(StopAfterTrialGate)
    )

    with pytest.raises(StopAfterTrialGate):
        WorkflowExecutor.execute(executor, resume=True)


@pytest.mark.parametrize("trial_authority", (None, "malformed"))
def test_compiled_trial_resume_reconciles_missing_or_malformed_authority(
    trial_authority: object,
) -> None:
    trial_step: dict[str, object] = {
        "status": "completed",
        "visit_count": 1,
        "artifacts": {},
    }
    if trial_authority is not None:
        trial_step["trial"] = trial_authority
    raw_state = {
        "run_id": "trial-run",
        "status": "running",
        "current_step": None,
        "steps": {"Compare": trial_step},
    }
    executor = object.__new__(WorkflowExecutor)
    executor.executable_ir = SimpleNamespace(
        nodes={"trial": SimpleNamespace(kind=ExecutableNodeKind.TRIAL)},
    )
    executor._step_node_ids = ["trial"]
    executor.state_manager = SimpleNamespace(
        load=lambda: SimpleNamespace(
            to_dict=lambda: json.loads(json.dumps(raw_state)),
        )
    )
    executor.provider_observation_enabled = False
    executor.provider_observation_manager = None
    executor.summary_observer = None
    executor._wait_for_provider_observation_dependents = lambda: None  # type: ignore[method-assign]
    executor._close_owned_provider_observation_manager = lambda: None  # type: ignore[method-assign]
    executor._reconcile_completed_run_refs_before_resume = lambda _state: None  # type: ignore[method-assign]
    executor._configure_pure_replay_runtime = (  # type: ignore[method-assign]
        lambda _run_state, *, resume: setattr(
            executor,
            "_pure_replay_runtime",
            None,
        )
    )
    reconciliation_calls: list[dict[str, object]] = []

    def reject_invalid_authority(state):
        reconciliation_calls.append(state)
        raise ValueError("compiled trial authority is invalid")

    executor._reconcile_completed_trials_before_resume = reject_invalid_authority  # type: ignore[method-assign]
    executor._fail_resume_state_integrity = (  # type: ignore[method-assign]
        lambda code, _message, _context: {"status": "failed", "code": code}
    )
    executor._initialize_provider_observation_manager = (  # type: ignore[method-assign]
        lambda: pytest.fail("invalid compiled trial authority escaped reconciliation")
    )

    result = WorkflowExecutor.execute(executor, resume=True)

    assert result == {
        "status": "failed",
        "code": "trial_resume_state_integrity_error",
    }
    assert reconciliation_calls == [raw_state]


def test_trial_resume_recovers_exact_sealed_labels_without_random_regeneration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path / "fixture")
    _execute(fixture, _blinded_cell_harnesses())
    executor = object.__new__(WorkflowExecutor)
    monkeypatch.setattr(
        "orchestrator.workflow.executor.os.urandom",
        lambda _size: pytest.fail("resume regenerated opaque labels"),
    )

    observed = WorkflowExecutor._trial_sealed_opaque_labels(
        executor,
        fixture["request"],
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
    )

    assert observed == fixture["sealed"]


def test_resume_reconciles_trial_against_derived_pure_overlay_after_e1(
) -> None:
    raw_state = {
        "run_id": "parent-run",
        "status": "running",
        "current_step": None,
        "steps": {
            "Derived": {
                "status": "completed",
                "result_storage": "derived_pure_replay.v1",
            },
            "Compare": {
                "status": "completed",
                "trial": {"result": "durable"},
            },
        },
    }
    run_state = SimpleNamespace(to_dict=lambda: json.loads(json.dumps(raw_state)))
    executor = object.__new__(WorkflowExecutor)
    executor.executable_ir = SimpleNamespace(
        nodes={"trial": SimpleNamespace(kind=ExecutableNodeKind.TRIAL)},
    )
    executor._step_node_ids = ["trial"]
    executor.state_manager = SimpleNamespace(load=lambda: run_state)
    executor.provider_observation_enabled = False
    executor.provider_observation_manager = None
    executor.summary_observer = None
    executor._wait_for_provider_observation_dependents = lambda: None  # type: ignore[method-assign]
    executor._close_owned_provider_observation_manager = lambda: None  # type: ignore[method-assign]
    events: list[str] = []
    executor._reconcile_completed_run_refs_before_resume = (  # type: ignore[method-assign]
        lambda _state: events.append("e1_reconciled")
    )

    class Replay:
        def overlay_active_state(self, state):
            events.append("pure_overlaid")
            active = json.loads(json.dumps(state))
            active["steps"]["Derived"] = {
                "status": "completed",
                "artifacts": {"value": "reconstructed"},
            }
            return active

    def configure(_run_state, *, resume):
        assert resume is True
        events.append("pure_configured")
        executor._pure_replay_runtime = Replay()

    executor._configure_pure_replay_runtime = configure  # type: ignore[method-assign]

    def reconcile_trial(state):
        assert state["steps"]["Derived"]["artifacts"] == {
            "value": "reconstructed"
        }
        events.append("trial_reconciled")
        raise ValueError("stop after reconciliation-order proof")

    executor._reconcile_completed_trials_before_resume = reconcile_trial  # type: ignore[method-assign]
    executor._fail_resume_state_integrity = (  # type: ignore[method-assign]
        lambda code, _message, _context: {"status": "failed", "code": code}
    )

    result = WorkflowExecutor.execute(executor, resume=True)

    assert result == {
        "status": "failed",
        "code": "trial_resume_state_integrity_error",
    }
    assert events == [
        "e1_reconciled",
        "pure_configured",
        "pure_overlaid",
        "trial_reconciled",
    ]


def test_nested_trial_parent_reader_uses_persisted_root_not_in_memory_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted_leaf = {
        "run_id": "parent-run",
        "current_step": None,
        "steps": {"Compare": {"trial": {"selected": "persisted"}}},
    }
    in_memory_leaf = {
        **persisted_leaf,
        "steps": {"Compare": {"trial": {"selected": "memory-only"}}},
    }
    persisted_root = {
        "run_id": "parent-run",
        "call_frames": {
            "outer": {
                "call_frame_id": "outer",
                "state": {
                    "run_id": "parent-run",
                    "call_frames": {
                            "inner": {
                                "call_frame_id": "inner",
                                "state": persisted_leaf,
                            },
                    },
                }
            }
        },
    }
    events: list[str] = []

    class RootManager:
        def load(self):
            events.append("root_disk_reread")
            return SimpleNamespace(
                to_dict=lambda: json.loads(json.dumps(persisted_root)),
            )

    class LeafManager:
        state = SimpleNamespace(to_dict=lambda: in_memory_leaf)

        def load(self):
            pytest.fail("nested in-memory load authorized trial settlement")

    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = LeafManager()
    owner = SimpleNamespace(
        root_manager=RootManager(),
        resume_scope_path=SimpleNamespace(call_frame_ids=("outer", "inner")),
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.resolve_aggregate_run_owner",
        lambda manager: owner
        if manager is executor.state_manager
        else pytest.fail("unexpected aggregate owner lookup"),
    )

    observed = WorkflowExecutor._read_trial_persisted_parent_state(executor)

    assert observed == persisted_leaf
    assert observed != in_memory_leaf
    assert events == ["root_disk_reread"]


def _completed_trial_reconciliation_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    fixture, execution, _adjudicated, envelope, _prepared = (
        _prepare_terminal_trial(tmp_path / "terminal")
    )
    request = fixture["request"]
    artifacts = {"verdict_artifact": envelope["verdict_artifact"]}
    state = {
        "run_id": request.visit.parent_run_id,
        "bound_inputs": {"payload": "fixed"},
        "current_step": None,
        "steps": {
            "Compare": {
                "status": "completed",
                "name": "Compare",
                "step_id": request.visit.step_id,
                "visit_count": request.visit.visit_count,
                "trial": envelope,
                "artifacts": artifacts,
            }
        },
    }
    root_manager = SimpleNamespace(
        run_id=request.visit.parent_run_id,
        state=SimpleNamespace(run_ref_root=fixture["run_ref_root"].as_posix()),
        bind_run_ref_root=lambda path: path,
        load=lambda: SimpleNamespace(
            to_dict=lambda: json.loads(json.dumps(state)),
        ),
    )
    owner = SimpleNamespace(
        root_manager=root_manager,
        resume_scope_path=SimpleNamespace(call_frame_ids=()),
        aggregate_root=fixture["parent_run_root"],
    )
    executor = object.__new__(WorkflowExecutor)
    executor.workspace = fixture["parent_workspace"]
    executor.state_manager = object()
    executor.loaded_bundle = SimpleNamespace(
        provenance=SimpleNamespace(frontend_build_root=None),
    )
    executor._step_node_ids = ["node"]
    step = {"name": "Compare", "step_id": request.visit.step_id}
    executor._runtime_step_for_node_id = lambda _node_id: step  # type: ignore[method-assign]
    executor._execution_kind_for_step = lambda _step: ExecutableNodeKind.TRIAL  # type: ignore[method-assign]
    executor._executable_node_for_step = (  # type: ignore[method-assign]
        lambda _step: SimpleNamespace(execution_config=request.step_config)
    )
    executor._step_id = lambda _step: request.visit.step_id  # type: ignore[method-assign]
    executor._emit_lexical_checkpoint_shadow_after_step_commit = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.resolve_aggregate_run_owner",
        lambda manager: owner
        if manager is executor.state_manager
        else pytest.fail("unexpected aggregate owner lookup"),
    )
    return SimpleNamespace(
        executor=executor,
        state=state,
        execution=execution,
        request=request,
    )


def test_completed_trial_reconciliation_appends_then_reuses_real_commit_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _completed_trial_reconciliation_fixture(tmp_path, monkeypatch)

    WorkflowExecutor._reconcile_completed_trials_before_resume(
        authority.executor,
        authority.state,
    )
    after_append = authority.execution.ledger_path.read_bytes()
    assert load_trial_event_ledger(authority.execution.ledger_path).rows[-1].kind == (
        "trial_parent_committed"
    )

    WorkflowExecutor._reconcile_completed_trials_before_resume(
        authority.executor,
        authority.state,
    )
    assert authority.execution.ledger_path.read_bytes() == after_append


def test_completed_trial_reconciliation_reuses_commit_with_later_current_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _completed_trial_reconciliation_fixture(tmp_path, monkeypatch)
    WorkflowExecutor._reconcile_completed_trials_before_resume(
        authority.executor,
        authority.state,
    )
    before = authority.execution.ledger_path.read_bytes()
    authority.state["current_step"] = {
        "name": "Later",
        "step_id": "root.later",
        "type": "provider",
        "status": "failed",
        "visit_count": 1,
    }

    WorkflowExecutor._reconcile_completed_trials_before_resume(
        authority.executor,
        authority.state,
    )

    assert authority.execution.ledger_path.read_bytes() == before


@pytest.mark.parametrize(
    "current_step",
    (
        {
            "name": "Compare",
            "step_id": "root.compare",
            "type": "trial",
            "status": "failed",
            "visit_count": 1,
        },
        {
            "name": "Later",
            "step_id": "",
            "type": "provider",
            "status": "failed",
            "visit_count": 1,
        },
    ),
)
def test_committed_trial_reconciliation_rejects_conflicting_current_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    current_step: dict[str, object],
) -> None:
    authority = _completed_trial_reconciliation_fixture(tmp_path, monkeypatch)
    WorkflowExecutor._reconcile_completed_trials_before_resume(
        authority.executor,
        authority.state,
    )
    before = authority.execution.ledger_path.read_bytes()
    authority.state["current_step"] = current_step

    with pytest.raises(ValueError, match="trial"):
        WorkflowExecutor._reconcile_completed_trials_before_resume(
            authority.executor,
            authority.state,
        )

    assert authority.execution.ledger_path.read_bytes() == before


def test_prepared_only_trial_reconciliation_rejects_later_current_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _completed_trial_reconciliation_fixture(tmp_path, monkeypatch)
    before = authority.execution.ledger_path.read_bytes()
    assert load_trial_event_ledger(authority.execution.ledger_path).rows[-1].kind == (
        "trial_prepared"
    )
    authority.state["current_step"] = {
        "name": "Later",
        "step_id": "root.later",
        "type": "provider",
        "status": "failed",
        "visit_count": 1,
    }

    with pytest.raises(ValueError, match="trial"):
        WorkflowExecutor._reconcile_completed_trials_before_resume(
            authority.executor,
            authority.state,
        )

    assert authority.execution.ledger_path.read_bytes() == before
