"""Tests for pure workflow step-result helpers."""

from dataclasses import dataclass

from orchestrator.workflow import step_results
from orchestrator.workflow.outcomes import OutcomeRecorder


@dataclass
class _NestedRuntimeValue:
    details: object


def test_outcome_recorder_to_step_result_delegates_to_step_results(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(
        step_results,
        "to_step_result",
        lambda result, fallback_name: sentinel,
    )

    converted = OutcomeRecorder.to_step_result({}, "fallback")

    assert converted is sentinel


def test_json_safe_runtime_value_converts_nested_runtime_containers():
    value = {
        "payload": _NestedRuntimeValue(
            details=(
                {1: ["ready", _NestedRuntimeValue(details=(True, None))]},
                3,
            )
        )
    }

    assert step_results.json_safe_runtime_value(value) == {
        "payload": {
            "details": [
                {"1": ["ready", {"details": [True, None]}]},
                3,
            ]
        }
    }


def test_to_step_result_preserves_adjudication_truncation_and_defaults():
    adjudication = {"selected": "candidate-a"}

    converted = step_results.to_step_result(
        {"adjudication": adjudication},
        "fallback",
    )

    assert converted.status == "completed"
    assert converted.name == "fallback"
    assert converted.exit_code == 0
    assert converted.duration_ms == 0
    assert converted.adjudication == adjudication
    assert converted.truncated is None
    assert converted.skipped is False


def test_to_step_result_uses_failure_and_explicit_truncation_values():
    converted = step_results.to_step_result(
        {"exit_code": 7, "truncated": True},
        "fallback",
    )

    assert converted.status == "failed"
    assert converted.truncated is True
