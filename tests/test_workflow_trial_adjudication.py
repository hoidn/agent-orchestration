from __future__ import annotations

from dataclasses import replace
import json
import re
from pathlib import Path
import subprocess
from threading import Lock

import pytest

from orchestrator.providers.executor import ProviderExecutionResult
import orchestrator.workflow.trial.runtime as trial_runtime_module
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from orchestrator.workflow.trial.runtime import (
    TrialRuntimeDependencies,
    execute_trial_cells,
)
from orchestrator.workflow.type_descriptor import validate_transport_value
from tests.test_workflow_trial_runtime import (
    _CellHarnesses,
    _InjectedCrash,
    _execute,
    _runtime_fixture,
)
from tests.test_workflow_trial_check_authority import _fixture_with_checks


class _Registry:
    def exists(self, name: str) -> bool:
        return name == "scorer"

    def merge_params(self, name: str, params: dict[str, object]):
        assert name == "scorer"
        assert params == {}
        return {"model": "fixed", "temperature": 0}


class _Composer:
    def read_prompt_source(self, source, **_kwargs):
        assert source == {"asset_file": "rubrics/trial.md"}
        return "Judge the selected evidence against this fixed rubric.", None


class _Executor:
    def __init__(self, *, forbidden: bool = False) -> None:
        self.forbidden = forbidden
        self.prepared: list[str] = []
        self.executed: list[str] = []

    def prepare_invocation(self, provider, params, context, **kwargs):
        if self.forbidden:
            raise AssertionError("validated resume must not prepare a provider")
        assert provider == "scorer"
        assert params.params == {"model": "fixed", "temperature": 0}
        assert context == {}
        prompt = kwargs["prompt_content"]
        labels = tuple(dict.fromkeys(re.findall(r"opaque-[0-9a-f]{64}", prompt)))
        assert len(labels) == 1
        self.prepared.append(prompt)
        return labels[0], None

    def execute(self, label, *, cwd):
        if self.forbidden:
            raise AssertionError("validated resume must not launch a provider")
        self.executed.append(label)
        return ProviderExecutionResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "candidate_id": label,
                    "score": 0.5,
                    "summary": "the selected result satisfies the rubric",
                    "citations": ["validated_result"],
                }
            ).encode("utf-8"),
            stderr=b"",
            duration_ms=3,
        )


class _InvalidExecutor(_Executor):
    def execute(self, label, *, cwd):
        if self.forbidden:
            raise AssertionError("validated resume must not launch a provider")
        self.executed.append(label)
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b'{"not":"a trial score"}',
            stderr=b"",
            duration_ms=2,
        )


def _dependencies(executor: _Executor, *, check_runner=None):
    from orchestrator.workflow.trial.adjudication import (
        TrialEvaluationDependencies,
    )

    check_calls: list[object] = []

    def forbidden_check(*_args, **_kwargs):
        check_calls.append(object())
        raise AssertionError("the fixture authors no deterministic checks")

    return (
        TrialEvaluationDependencies(
            provider_registry=_Registry(),
            prompt_composer=_Composer(),
            provider_executor=executor,
            check_runner=check_runner or forbidden_check,
        ),
        check_calls,
    )


def _blinded_cell_harnesses(**kwargs) -> _CellHarnesses:
    return _CellHarnesses(
        result_value=lambda cell: f"candidate-output:{cell.rep}",
        **kwargs,
    )


def _durable_bytes(execution, result) -> tuple[bytes, ...]:
    trial_root = execution.ledger_path.parent
    return (
        execution.ledger_path.read_bytes(),
        (trial_root / "scorer" / "metadata.json").read_bytes(),
        (trial_root / "scores.jsonl").read_bytes(),
        result.verdict_artifact.path.read_bytes(),
    )


class _ManualClock:
    def __init__(self, now_ns: int) -> None:
        self._now_ns = now_ns
        self._lock = Lock()

    def __call__(self) -> int:
        with self._lock:
            return self._now_ns

    def advance(self, elapsed_ns: int) -> None:
        with self._lock:
            self._now_ns += elapsed_ns


def test_task8_coordinator_drives_exact_chain_and_reuses_terminal_result(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution

    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _blinded_cell_harnesses())
    executor = _Executor()
    dependencies, check_calls = _dependencies(executor)

    first = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )

    ledger = load_trial_event_ledger(execution.ledger_path)
    post_cell_kinds = [
        row.kind
        for row in ledger.rows
        if row.kind
        in {
            "evidence_frozen",
            "check_settled",
            "checks_frozen",
            "packets_frozen",
            "scorer_frozen",
            "evaluator_attempt_allocated",
            "evaluator_attempt_settled",
            "score_settled",
            "scores_frozen",
            "aggregation_frozen",
            "verdict_settled",
            "verdict_published",
        }
    ]
    assert post_cell_kinds[:4] == [
        "evidence_frozen",
        "checks_frozen",
        "packets_frozen",
        "scorer_frozen",
    ]
    evaluation_kinds = post_cell_kinds[4:-4]
    assert evaluation_kinds.count("evaluator_attempt_allocated") == len(
        fixture["request"].cell_domain
    )
    assert evaluation_kinds.count("evaluator_attempt_settled") == len(
        fixture["request"].cell_domain
    )
    assert evaluation_kinds.count("score_settled") == len(
        fixture["request"].cell_domain
    )
    assert post_cell_kinds[-4:] == [
        "scores_frozen",
        "aggregation_frozen",
        "verdict_settled",
        "verdict_published",
    ]
    assert check_calls == []
    assert len(executor.prepared) == len(fixture["request"].cell_domain)
    assert len(executor.executed) == len(fixture["request"].cell_domain)
    assert [row["variant"] for row in first.authored_outcomes] == [
        "Completed"
    ] * len(fixture["request"].cell_domain)
    assert first.verdict_artifact.path.is_file()
    assert first.verdict_artifact.relpath.startswith("artifacts/trials/")
    envelope = {
        "outcomes": list(first.authored_outcomes),
        "verdict": first.verdict,
        "verdict_artifact": first.verdict_artifact.relpath,
    }
    assert validate_transport_value(
        envelope,
        fixture["request"].static_config.result_descriptor["envelope"],
        allow_nested_structures=True,
    ) == envelope

    before = _durable_bytes(execution, first)
    forbidden = _Executor(forbidden=True)
    resumed_dependencies, resumed_check_calls = _dependencies(forbidden)
    resumed = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=resumed_dependencies,
    )

    assert resumed.authored_outcomes == first.authored_outcomes
    assert resumed.verdict == first.verdict
    assert resumed.verdict_artifact.record == first.verdict_artifact.record
    assert resumed_check_calls == []
    assert _durable_bytes(execution, resumed) == before


def test_serial_cells_charge_only_each_durable_attempt_window_in_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.trial.adjudication as adjudication_module

    evaluate_trial_execution = adjudication_module.evaluate_trial_execution

    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    cell_elapsed_ms = 5
    evaluator_elapsed_ms = 3
    clock = _ManualClock(1_000_000_000)
    harnesses = _blinded_cell_harnesses()
    original_factory = harnesses.factory
    original_driver = trial_runtime_module.drive_run_ref_lifecycle
    original_evaluator = adjudication_module.evaluate_trial_packets
    driver_starts: dict[Path, int] = {}

    def timed_factory(cell, request):
        dependencies = original_factory(cell, request)
        launch = dependencies.launch_child

        def timed_launch(child):
            result = launch(child)
            clock.advance(cell_elapsed_ms * 1_000_000)
            return result

        return replace(dependencies, launch_child=timed_launch)

    def observing_driver(request, **kwargs):
        allocation = kwargs["allocation"]
        driver_starts[allocation.effect_instance_root] = kwargs[
            "started_monotonic_ns"
        ]
        return original_driver(request, **kwargs)

    def deterministic_evaluator(**kwargs):
        kwargs["wall_time_ns"] = lambda: 2_000_000_000
        return original_evaluator(**kwargs)

    harnesses.factory = timed_factory
    monkeypatch.setattr(
        trial_runtime_module,
        "drive_run_ref_lifecycle",
        observing_driver,
    )
    monkeypatch.setattr(
        adjudication_module,
        "evaluate_trial_packets",
        deterministic_evaluator,
    )
    execution = execute_trial_cells(
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
            wall_time_ns=lambda: 2_000_000_000,
        ),
    )

    allocations = [
        row
        for row in load_trial_event_ledger(execution.ledger_path).rows
        if row.kind == "cell_allocated"
    ]
    assert [row.payload["started_monotonic_ns"] for row in allocations] == [
        1_000_000_000 + index * cell_elapsed_ms * 1_000_000
        for index in range(len(fixture["request"].cell_domain))
    ]
    assert {
        Path(row.payload["effect_instance_root"]): row.payload[
            "started_monotonic_ns"
        ]
        for row in allocations
    } == driver_starts
    assert [
        outcome.envelope["accounting"]["elapsed_ms"]
        for outcome in execution.outcomes
    ] == [cell_elapsed_ms] * len(fixture["request"].cell_domain)

    dependencies, _check_calls = _dependencies(_Executor())
    result = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )
    assert result.verdict["budget_accounting"]["elapsed_ms"] == (
        cell_elapsed_ms + evaluator_elapsed_ms
    ) * len(fixture["request"].cell_domain)


def test_required_check_failure_remains_primary_and_excludes_raw_score_from_aggregate(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution

    fixture = _fixture_with_checks(
        tmp_path,
        (
            {
                "check_id": "required",
                "command": ["probe", "required"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1000,
            },
        ),
    )
    execution = _execute(fixture, _blinded_cell_harnesses())
    check_calls: list[tuple[tuple[str, ...], Path, bool]] = []

    def failing_check(argv, *, cwd, shell, **_kwargs):
        check_calls.append((tuple(argv), Path(cwd), shell))
        return subprocess.CompletedProcess(argv, 1, stdout=b"no", stderr=b"")

    dependencies, _unused = _dependencies(
        _Executor(),
        check_runner=failing_check,
    )
    result = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )

    assert len(check_calls) == len(fixture["request"].cell_domain)
    assert all(call[2] is False for call in check_calls)
    assert [row["variant"] for row in result.authored_outcomes] == [
        "Failed"
    ] * len(fixture["request"].cell_domain)
    assert all(
        row["failure"]["code"] == "trial_required_check_failed"
        and row["failure"]["phase"] == "checks"
        and any(
            fact["variant"] == "Score" for fact in row["evidence"]["facts"]
        )
        for row in result.authored_outcomes
    )
    assert all(
        row["score"] is None and row["failed_count"] == 2
        for row in result.verdict["aggregate_scores"]
    )
    assert result.verdict["success_rule_disposition"] == "insufficient_scored_arms"


def test_optional_check_failure_alone_preserves_completed_outcomes(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution

    fixture = _fixture_with_checks(
        tmp_path,
        (
            {
                "check_id": "advisory",
                "command": ["probe", "advisory"],
                "authority": "invariant",
                "required": False,
                "timeout_ms": 1000,
            },
        ),
    )
    execution = _execute(fixture, _blinded_cell_harnesses())

    def failing_check(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout=b"advisory", stderr=b"")

    dependencies, _unused = _dependencies(
        _Executor(),
        check_runner=failing_check,
    )
    result = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )

    assert all(row["variant"] == "Completed" for row in result.authored_outcomes)
    assert all(
        evidence["status"] == "COMPLETED" and evidence["exit_code"] == 1
        for row in result.authored_outcomes
        for evidence in row["evidence"]["check_results"]
    )


def test_evaluator_exhaustion_fails_cells_without_inventing_score_facts(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution

    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _blinded_cell_harnesses())
    executor = _InvalidExecutor()
    dependencies, _check_calls = _dependencies(executor)

    result = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )

    assert len(executor.executed) == fixture["request"].static_config.budget[
        "max_evaluator_attempts"
    ]
    assert all(
        row["variant"] == "Failed"
        and row["failure"] == {
            "code": "trial_evaluator_attempts_exhausted",
            "phase": "evaluation",
            "retryable": False,
            "secondary_causes": [],
        }
        and not any(
            fact["variant"] == "Score" for fact in row["evidence"]["facts"]
        )
        for row in result.authored_outcomes
    )
    assert result.verdict["budget_accounting"]["evaluator_attempts"] == len(
        fixture["request"].cell_domain
    )
    assert result.verdict["success_rule_disposition"] == "insufficient_scored_arms"


def test_task8_coordinator_accepts_a_valid_discarded_attempt_prefix(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution

    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _blinded_cell_harnesses()
    crashed = False

    def crash_once(boundary: str) -> None:
        nonlocal crashed
        if not crashed and boundary == "after_e1_prepared_before_trial_prepared":
            crashed = True
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(fixture, harnesses, crash_hook=crash_once)
    execution = _execute(fixture, harnesses)
    dependencies, _check_calls = _dependencies(_Executor())

    result = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )

    assert all(row["variant"] == "Completed" for row in result.authored_outcomes)
    ledger = load_trial_event_ledger(execution.ledger_path)
    assert any(row.kind == "cell_discarded" for row in ledger.rows)
    assert result.verdict["budget_accounting"]["child_attempts"] == len(
        harnesses.launches
    )
