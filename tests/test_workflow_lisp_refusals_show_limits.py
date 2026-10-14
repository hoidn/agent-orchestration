from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_improve_stdlib import _public_run, _public_run_files




def _source(body: str, *, signature: str = "() -> Int", target: str = "2.35") -> str:
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
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data

    assert result.exit_code == 1
    error = state
    assert "value=9223372036854775808" in error["message"]
    assert "minimum=-9223372036854775808" in error["message"]
    assert "maximum=9223372036854775807" in error["message"]
    assert error["code"] == "pure_expr_overflow"
    assert state["outcome"] == "failed"


def test_public_bounded_loop_without_fallback_records_failed_terminal(
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
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data
    failure = state

    assert result.exit_code == 1
    assert failure["outcome"] == "failed"
    assert failure["code"] == "loop_exhausted"
    assert not snapshot.active_commits


def test_public_list_map_effect_cap_records_failed_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.35")',
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
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data
    failure = state

    assert result.exit_code == 1
    assert failure["outcome"] == "failed"
    assert failure["code"] == "list_map_effect_cap_exceeded"
    assert not snapshot.active_commits










@pytest.mark.xfail(strict=True, reason="F39: public transport byte refusals omit measured size and cap")
def test_public_transport_byte_refusal_prints_observed_size_and_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.workflow_evaluated_totality_helpers import _write_probe

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
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data
    failure = state
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
    from tests.test_workflow_lisp_trial_lowering import _historical_trial_config

    static = _historical_trial_config()

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
