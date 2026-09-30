from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from tests.test_workflow_lisp_improve_stdlib import _public_run, _public_run_files


def _public_compile_refusal(
    tmp_path: Path,
    source: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> tuple[int, str]:
    path = tmp_path / "grt" / "entry.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = _public_run(_public_run_files(tmp_path, {}))
    return result.exit_code, caplog.text


def _source(body: str, *, signature: str = "() -> Int", target: str = "2.33") -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target}")',
            "  (defmodule grt/entry)",
            "  (export run)",
            f"  (defworkflow run {signature} {body}))",
        )
    )


def _public_failure_state(root: Path) -> dict[str, object]:
    state_path = next((root / ".orchestrate" / "runs").glob("*/state.json"))
    return json.loads(state_path.read_text(encoding="utf-8"))


def test_oversized_payload_prints_count_cap_and_three_serialized_contributors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    values = lambda count: " ".join(str(index) for index in range(count))
    source = "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.33")',
            "  (defmodule grt/entry)",
            "  (export run)",
            "  (defworkflow run () -> List[List[Int]]",
            "    (let* ((first (list " + values(100) + "))",
            "           (second (list " + values(90) + "))",
            "           (third (list " + values(80) + ")))",
            "      (list first second third))))",
        )
    )

    exit_code, message = _public_compile_refusal(tmp_path, source, monkeypatch, caplog)

    assert exit_code == 2
    assert "pure_expr_payload_too_large" in message
    assert "node_count=274" in message
    assert "max_nodes=256" in message
    assert re.search(r"ListExpr at .*entry\.orc:7:\d+ nodes=101", message)
    assert re.search(r"ListExpr at .*entry\.orc:8:\d+ nodes=91", message)
    assert re.search(r"ListExpr at .*entry\.orc:9:\d+ nodes=81", message)


def test_public_pure_projection_overflow_prints_value_and_signed_64_bit_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(_source("(+ value 1)", signature="((value Int)) -> Int"), encoding="utf-8")
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"value": 2**63 - 1}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)
    state = _public_failure_state(tmp_path)

    assert result.exit_code == 1
    error = next(
        step["error"]
        for step in state["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("error"), dict)
    )
    assert "value=9223372036854775808" in error["message"]
    assert "minimum=-9223372036854775808" in error["message"]
    assert "maximum=9223372036854775807" in error["message"]
    assert error["type"] == "pure_expr_overflow"
    assert state["status"] == "failed"


def test_public_repeat_until_exhaustion_prints_observed_iteration_and_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(
        "(loop/recur :max 2 :state 0 (fn (state) "
        "(if (< state 10) (continue (+ state 1)) (done state))))"
    )
    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}))
    state = _public_failure_state(tmp_path)
    failure = next(
        step["error"]
        for step in state["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("error"), dict)
    )

    assert result.exit_code == 1
    assert failure["type"] == "repeat_until_iterations_exhausted"
    assert "max_iterations=2" in failure["message"]
    assert "last_iteration=1" in failure["message"]
    assert "completed_iterations=2" in failure["message"]


def test_list_map_effect_cap_reports_completed_iterations_and_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.18")',
            "  (defmodule grt/entry)",
            "  (export run)",
            "  (defworkflow child ((value Int)) -> Int value)",
            "  (defworkflow run ((values List[Int])) -> List[Int]",
            "    (list/map-effect ((item values)) :max 2",
            "      (call child :value item)))",
            ")",
        )
    )
    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"values": [1, 2, 3]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)
    state = _public_failure_state(tmp_path)
    failure = next(
        step["error"]
        for step in state["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("error"), dict)
    )

    assert result.exit_code == 1
    assert failure["type"] == "repeat_until_iterations_exhausted"
    assert failure["code"] == "list_map_effect_cap_exceeded"
    assert "last_iteration=1" in failure["message"]
    assert "max_iterations=2" in failure["message"]
    assert "completed_iterations=2" in failure["message"]


def test_list_map_effect_nonpositive_max_prints_value_and_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = _source(
        "(list/map-effect ((item (list 1))) :max 0 (call child :value item))",
        signature="() -> List[Int]",
        target="2.18",
    ).replace(
        "  (export run)",
        "  (export run)\n  (defworkflow child ((value Int)) -> Int value)",
    )

    exit_code, message = _public_compile_refusal(tmp_path, source, monkeypatch, caplog)

    assert exit_code == 2
    assert "list_map_effect_max_invalid" in message
    assert "value=0" in message and "minimum=1" in message


def test_public_loop_recur_zero_max_prints_value_and_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = _source(
        "(loop/recur :max 0 :state 0 (fn (state) (done state)))"
    )

    exit_code, message = _public_compile_refusal(
        tmp_path, source, monkeypatch, caplog
    )

    assert exit_code == 2
    assert "workflow_boundary_type_invalid" in message
    loop_line = next(
        (number, line.index("(loop/recur") + 1)
        for number, line in enumerate(source.splitlines(), 1)
        if "(loop/recur" in line
    )
    assert f"entry.orc:{loop_line[0]}:{loop_line[1]}:" in message
    assert "value=0" in message
    assert "minimum=1" in message


def test_repeated_loop_update_binding_still_hits_the_payload_node_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repeated = " ".join("next" for _ in range(100))
    source = "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.33")',
            "  (defmodule grt/entry)",
            "  (export run)",
            "  (defrecord LoopState (i Int) (acc Int))",
            "  (defworkflow run () -> Int",
            "    (loop/recur :max 2 :state (record LoopState :i 0 :acc 0)",
            "      (fn (state)",
            "        (if (< state.i 1)",
            "          (let* ((next (+ state.i 1)))",
            "            (continue (record-update state :i next :acc (+ state.acc "
            + repeated
            + ")))"
            ")",
            "          (done state.acc)))))",
            ")",
        )
    )

    exit_code, message = _public_compile_refusal(
        tmp_path, source, monkeypatch, caplog
    )

    assert exit_code == 2
    assert "pure_expr_payload_too_large" in message
    assert "max_nodes=256" in message
    node_count = re.search(r"node_count=(\d+)", message)
    assert node_count is not None and int(node_count.group(1)) > 256
    update_line = next(
        (number, line.index("(record-update") + 1)
        for number, line in enumerate(source.splitlines(), 1)
        if "(record-update" in line
    )
    assert f"entry.orc:{update_line[0]}:{update_line[1]}:" in message


@pytest.mark.xfail(strict=True, reason="F38: size diagnostics rank nested subtrees instead of copied totals")
def test_overflow_contributors_aggregate_repeated_source_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repeated_v = " ".join("n" for _ in range(19))
    innermost = "(+ " + " ".join("n" for _ in range(30)) + ")"
    middle = f"(+ {innermost} n n)"
    nested_b = f"(+ {middle} n n)"
    record_fields = " ".join(f":f{index} v" for index in range(1, 12))
    definitions = " ".join(f"(f{index} Int)" for index in range(1, 12))
    source = "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.29")',
            "  (defmodule grt/entry)",
            "  (export run)",
            f"  (defrecord T {definitions} (g Int))",
            "  (defworkflow run ((n Int)) -> T",
            f"    (let* ((v (+ {repeated_v})) (b {nested_b}))",
            f"      (record T {record_fields} :g b)))",
            ")",
        )
    )

    exit_code, message = _public_compile_refusal(
        tmp_path, source, monkeypatch, caplog
    )

    assert exit_code == 2
    assert "pure_expr_payload_too_large" in message
    assert "node_count=258" in message
    assert "max_nodes=256" in message
    v_column = source.splitlines()[7].index("(+") + 1
    assert f"entry.orc:8:{v_column} nodes=220" in message


@pytest.mark.xfail(strict=True, reason="F39: public transport byte refusals omit measured size and cap")
def test_public_transport_byte_refusal_prints_observed_size_and_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_workflow_lisp_generic_unions_runtime import _write_probe

    probe = _write_probe(
        tmp_path,
        "large_value",
        "import json, os\n"
        "from pathlib import Path\n"
        "output = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "value = {'items': [{'label': 'x' * 17_000_000}]}\n"
        "output.write_text(json.dumps(value), encoding='utf-8')\n",
    )
    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.33")',
                "  (defmodule grt/entry)",
                "  (export run)",
                "  (defrecord Item (label String))",
                "  (defrecord Big (items List[Item]))",
                "  (defproc produce () -> Big",
                "    :effects ((uses-command produce))",
                "    :lowering inline",
                f'    (command-result produce :argv ("python" "{probe}") :returns Big))',
                "  (defworkflow run () -> Big (produce)))",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {"produce": probe}))
    state = _public_failure_state(tmp_path)
    failure = next(
        step["error"]
        for step in state["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("error"), dict)
    )
    diagnostic = json.dumps(failure)
    expected_bytes = len(
        json.dumps(
            {"items": [{"label": "x" * 17_000_000}]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    assert result.exit_code == 1
    assert failure["type"] == "contract_violation"
    assert "invalid_transportable_value" in diagnostic
    violation = failure["context"]["violations"][0]
    origin = violation["source_origins"][0]
    assert origin["path"] == str(entry)
    assert (origin["line"], origin["column"]) == (11, 5)
    assert f"bytes={expected_bytes}" in diagnostic
    assert "maximum=16777216" in diagnostic


def test_trial_packet_builder_reports_actual_item_and_packet_byte_sizes() -> None:
    from orchestrator.workflow.trial.packets import (
        TrialPacketError,
        build_trial_evaluation_packet,
    )

    arguments: dict[str, object] = {
        "opaque_label": "opaque-" + "8" * 64,
        "observation_include": ("task_spec", "check_results"),
        "observations": {
            "task_spec": {"objective": "x" * 64},
            "check_results": [{"check_id": "unit", "status": "COMPLETED"}],
        },
        "sealed_identity_values": ("SECRET-ARM",),
    }
    packet = build_trial_evaluation_packet(
        **arguments, max_item_bytes=1_024, max_packet_bytes=4_096
    )
    canonical = lambda value: json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    item_size = len(canonical(packet["items"][0]))
    packet_size = len(canonical(packet))

    with pytest.raises(TrialPacketError) as item_error:
        build_trial_evaluation_packet(
            **arguments,
            max_item_bytes=item_size - 1,
            max_packet_bytes=4_096,
        )
    assert item_error.value.code == "trial_packet_limit_invalid"
    assert f"item_bytes={item_size}" in str(item_error.value)
    assert f"max_item_bytes={item_size - 1}" in str(item_error.value)

    with pytest.raises(TrialPacketError) as packet_error:
        build_trial_evaluation_packet(
            **arguments,
            max_item_bytes=256,
            max_packet_bytes=packet_size - 1,
        )
    assert packet_error.value.code == "trial_packet_limit_invalid"
    assert f"packet_bytes={packet_size}" in str(packet_error.value)
    assert f"max_packet_bytes={packet_size - 1}" in str(packet_error.value)


def test_trial_static_config_reports_rejected_values_and_related_limits(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from orchestrator.workflow.trial.config import build_trial_static_config
    from tests.test_workflow_trial_runtime import _runtime_fixture

    static = _runtime_fixture(tmp_path)["request"].static_config

    def build(**changes: object) -> None:
        values: dict[str, object] = {
            "compiler_runtime_identity_digest": static.compiler_runtime_identity_digest,
            "site_digest": static.site_digest,
            "arms": static.arms,
            "reps": static.reps,
            "max_concurrency": static.max_concurrency,
            "evaluation": static.evaluation,
            "budget": static.budget,
            "result_descriptor": static.result_descriptor,
            "result_digest": static.result_digest,
            "target_dsl_version": static.target_dsl_version,
        }
        values.update(changes)
        build_trial_static_config(**values)

    evaluation = static.evaluation
    budget = static.budget
    bad_budget = {**budget, "max_evaluator_attempts": 0}
    with pytest.raises(ValueError) as attempt_error:
        build(budget=bad_budget)
    assert "value=0" in str(attempt_error.value)
    assert "minimum=1" in str(attempt_error.value)

    with pytest.raises(ValueError) as concurrency_error:
        build(
            budget={**budget, "max_evaluator_attempts": 2, "max_evaluator_concurrency": 3}
        )
    assert "max_evaluator_concurrency=3" in str(concurrency_error.value)
    assert "max_evaluator_attempts=2" in str(concurrency_error.value)

    with pytest.raises(ValueError) as packet_error:
        build(
            evaluation={
                **evaluation,
                "max_item_bytes": 2_048,
                "max_packet_bytes": 1_024,
            }
        )
    assert "max_packet_bytes=1024" in str(packet_error.value)
    assert "minimum_max_packet_bytes=2048" in str(packet_error.value)

    with pytest.raises(ValueError) as repetitions_error:
        build(reps=65)
    assert "repetitions=65" in str(repetitions_error.value)
    assert "maximum_repetitions=64" in str(repetitions_error.value)

    with pytest.raises(ValueError) as arms_error:
        build(arms=())
    assert "arm_count=0" in str(arms_error.value)
    assert "minimum_arms=2" in str(arms_error.value)
    assert "maximum_arms=16" in str(arms_error.value)

    many_arms = tuple(
        replace(static.arms[0], arm_id=f"arm-{index}") for index in range(5)
    )
    with pytest.raises(ValueError) as concurrency_error:
        build(arms=many_arms, reps=20, max_concurrency=33)
    assert "concurrency=33" in str(concurrency_error.value)
    assert "maximum_concurrency=32" in str(concurrency_error.value)
    assert "cells=100" in str(concurrency_error.value)

    with pytest.raises(ValueError) as cells_error:
        build(arms=many_arms, reps=64)
    assert "repetitions=64" in str(cells_error.value)
    assert "cells=320" in str(cells_error.value)
    assert "maximum_cells=256" in str(cells_error.value)


def test_trial_check_timeout_refusal_shows_value_and_minimum(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.checks import TrialCheckError, run_trial_checks

    check = {
        "check_id": "correctness",
        "command": ["probe", "correctness"],
        "authority": "correctness",
        "required": True,
        "timeout_ms": 0,
    }
    with pytest.raises(TrialCheckError) as error:
        run_trial_checks(
            (check,),
            cwd=tmp_path,
            evidence_frozen_digest="sha256:" + "a" * 64,
            max_output_bytes=1_024,
            runner=lambda *_args, **_kwargs: pytest.fail("invalid timeout launched"),
        )
    assert "value=0" in str(error.value)
    assert "minimum=1" in str(error.value)


def test_persisted_trial_attempt_overflow_reports_used_and_limit(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.adjudication import persist_scorer_snapshot
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    from orchestrator.workflow.trial import evaluation, ledger
    from orchestrator.workflow.trial.ledger import load_trial_event_ledger
    from tests.test_workflow_trial_evaluator_preflight import _arguments

    fixture, arguments = _arguments(tmp_path)
    scorer, _prompt, _rubric = evaluation._resolve_scorer(
        scorer_config=arguments["scorer_config"],
        provider_registry=arguments["provider_registry"],
        prompt_composer=arguments["prompt_composer"],
    )
    persist_scorer_snapshot(scorer, arguments["scorer_root"])
    event = load_trial_event_ledger(fixture["ledger_path"])
    scorer_row = ledger.append_trial_scorer_freeze(
        fixture["ledger_path"],
        expected_head_digest=event.rows[-1].row_digest,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        snapshot_digest=canonical_sha256(scorer),
    )
    packet = arguments["packets"][0]
    for attempt in (1, 2):
        current = load_trial_event_ledger(fixture["ledger_path"])
        allocation = ledger.append_trial_evaluator_attempt_allocation(
            fixture["ledger_path"],
            expected_head_digest=current.rows[-1].row_digest,
            opaque_label=packet["evaluation_id"],
            local_attempt=attempt,
            global_attempt=attempt,
            packet_digest=canonical_sha256(packet),
            scorer_frozen_row_digest=scorer_row.row_digest,
            started_at_unix_ns=1_000_000_000,
        )
        ledger.append_trial_evaluator_attempt_settlement(
            fixture["ledger_path"],
            expected_head_digest=allocation.row_digest,
            allocation_row_digest=allocation.row_digest,
            opaque_label=packet["evaluation_id"],
            local_attempt=attempt,
            global_attempt=attempt,
            status="output_invalid",
            exit_code=1,
            duration_ms=1,
            token_usage={"variant": "UNKNOWN"},
            cost={"variant": "UNKNOWN"},
            stdout_digest="sha256:" + "1" * 64,
            stderr_digest="sha256:" + "2" * 64,
            output_digest=None,
            score_row_content_digest=None,
        )

    arguments["max_evaluator_attempts"] = 1
    arguments["max_evaluator_concurrency"] = 1
    with pytest.raises(evaluation.TrialEvaluationError) as error:
        evaluation.evaluate_trial_packets(**arguments)
    assert "attempts_used=2" in str(error.value)
    assert "max_evaluator_attempts=1" in str(error.value)


def test_trial_evaluator_exhaustion_logs_attempt_and_deadline_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from orchestrator.providers.executor import ProviderExecutionResult
    from orchestrator.workflow.trial import evaluation
    from tests.test_workflow_trial_evaluator_preflight import _arguments

    _fixture, arguments = _arguments(tmp_path)
    arguments["max_evaluator_attempts"] = 1
    arguments["max_evaluator_concurrency"] = 1

    class FailingExecutor:
        def prepare_invocation(self, *_args, **_kwargs):
            return "invocation", None

        def execute(self, _invocation, *, cwd):
            return ProviderExecutionResult(
                exit_code=1,
                stdout=b"",
                stderr=b"failed",
                duration_ms=3,
            )

    result = evaluation.evaluate_trial_packets(
        **{**arguments, "provider_executor": FailingExecutor()}
    )

    assert result.rows
    assert all(
        row["failure"]["code"] == "trial_evaluator_attempts_exhausted"
        for row in result.rows
    )
    assert "trial_evaluator_attempts_exhausted" in caplog.text
    assert "attempts_used=1" in caplog.text
    assert "max_evaluator_attempts=1" in caplog.text


def test_trial_evaluator_deadline_exhaustion_logs_observed_deadline(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from orchestrator.workflow.trial import evaluation
    from tests.test_workflow_trial_evaluator_preflight import _arguments

    _fixture, arguments = _arguments(tmp_path)
    arguments["deadline_unix_ns"] = 123
    arguments["wall_time_ns"] = lambda: 123

    result = evaluation.evaluate_trial_packets(**arguments)

    assert result.rows
    assert all(
        row["failure"]["code"] == "trial_evaluator_deadline_exhausted"
        for row in result.rows
    )
    assert "trial_evaluator_deadline_exhausted" in caplog.text
    assert "observed_unix_ns=123" in caplog.text
    assert "deadline_unix_ns=123" in caplog.text


def test_trial_evaluator_input_bounds_show_rejected_attempt_and_deadline(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial import evaluation
    from tests.test_workflow_trial_evaluator_preflight import _arguments

    _fixture, arguments = _arguments(tmp_path)
    with pytest.raises(evaluation.TrialEvaluationError) as attempts_error:
        evaluation.evaluate_trial_packets(
            **{**arguments, "max_evaluator_attempts": 0}
        )
    assert "max_evaluator_attempts=0" in str(attempts_error.value)
    assert "minimum=1" in str(attempts_error.value)

    with pytest.raises(evaluation.TrialEvaluationError) as deadline_error:
        evaluation.evaluate_trial_packets(
            **{**arguments, "deadline_unix_ns": -1}
        )
    assert "deadline value=-1" in str(deadline_error.value)
    assert "minimum=0" in str(deadline_error.value)
