"""Tests for v2.8 score-aware predicate helpers."""

from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.predicates import TypedPredicateEvaluator


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return workflow_file


def _load_executor(workspace: Path, workflow: dict, run_id: str = "score-gate-run") -> WorkflowExecutor:
    workflow_file = _write_workflow(workspace, workflow)
    loaded = WorkflowLoader(workspace).load(workflow_file)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    return WorkflowExecutor(loaded, workspace, state_manager)


def test_score_predicate_evaluator_supports_thresholds_and_bands():
    evaluator = TypedPredicateEvaluator()
    state = {
        "steps": {
            "ScoreCandidate": {
                "artifacts": {
                    "quality_score": 0.91,
                }
            }
        }
    }

    assert evaluator.evaluate(
        {
            "score": {
                "ref": "root.steps.ScoreCandidate.artifacts.quality_score",
                "gte": 0.9,
            }
        },
        state,
    )
    assert evaluator.evaluate(
        {
            "score": {
                "ref": "root.steps.ScoreCandidate.artifacts.quality_score",
                "gt": 0.9,
                "lt": 0.95,
            }
        },
        state,
    )
    assert not evaluator.evaluate(
        {
            "score": {
                "ref": "root.steps.ScoreCandidate.artifacts.quality_score",
                "gte": 0.95,
            }
        },
        state,
    )


def test_loader_requires_v28_for_score_predicates(tmp_path: Path):
    workflow = {
        "version": "2.7",
        "name": "score-gate-version-boundary",
        "artifacts": {
            "quality_score": {
                "kind": "scalar",
                "type": "float",
            }
        },
        "steps": [
            {
                "name": "WriteScore",
                "id": "write_score",
                "set_scalar": {
                    "artifact": "quality_score",
                    "value": 0.91,
                },
            },
            {
                "name": "GateScore",
                "id": "gate_score",
                "assert": {
                    "score": {
                        "ref": "root.steps.WriteScore.artifacts.quality_score",
                        "gte": 0.9,
                    }
                },
            },
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(_write_workflow(tmp_path, workflow))

    assert any(
        "score predicates require version '2.8'" in str(error.message)
        for error in exc_info.value.errors
    )


@pytest.mark.parametrize(
    ("score_node", "message_fragment"),
    [
        (
            {
                "ref": "root.steps.WriteScore.artifacts.quality_score",
            },
            "score requires at least one bound",
        ),
        (
            {
                "ref": "root.steps.WriteScore.artifacts.quality_score",
                "gt": 0.8,
                "gte": 0.9,
            },
            "score cannot declare both gt and gte",
        ),
    ],
)
def test_loader_rejects_invalid_score_bound_shapes(
    tmp_path: Path,
    score_node: dict,
    message_fragment: str,
):
    workflow = {
        "version": "2.8",
        "name": "invalid-score-bounds",
        "artifacts": {
            "quality_score": {
                "kind": "scalar",
                "type": "float",
            }
        },
        "steps": [
            {
                "name": "WriteScore",
                "id": "write_score",
                "set_scalar": {
                    "artifact": "quality_score",
                    "value": 0.91,
                },
            },
            {
                "name": "GateScore",
                "id": "gate_score",
                "assert": {
                    "score": score_node,
                },
            },
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(_write_workflow(tmp_path, workflow))

    assert any(message_fragment in str(error.message) for error in exc_info.value.errors)


def test_loader_rejects_non_numeric_score_refs(tmp_path: Path):
    workflow = {
        "version": "2.8",
        "name": "invalid-score-ref",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "steps": [
            {
                "name": "WriteReady",
                "id": "write_ready",
                "set_scalar": {
                    "artifact": "ready",
                    "value": True,
                },
            },
            {
                "name": "GateScore",
                "id": "gate_score",
                "assert": {
                    "score": {
                        "ref": "root.steps.WriteReady.artifacts.ready",
                        "gte": 0.9,
                    }
                },
            },
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(_write_workflow(tmp_path, workflow))

    assert any(
        "score requires a numeric ref" in str(error.message)
        for error in exc_info.value.errors
    )


def test_score_assert_failure_can_recover_via_on_failure_goto(tmp_path: Path):
    workflow = {
        "version": "2.8",
        "name": "score-assert-recovery",
        "artifacts": {
            "quality_score": {
                "kind": "scalar",
                "type": "float",
            },
            "recovered": {
                "kind": "scalar",
                "type": "bool",
            },
        },
        "steps": [
            {
                "name": "WriteScore",
                "id": "write_score",
                "set_scalar": {
                    "artifact": "quality_score",
                    "value": 0.82,
                },
            },
            {
                "name": "GateScore",
                "id": "gate_score",
                "assert": {
                    "score": {
                        "ref": "root.steps.WriteScore.artifacts.quality_score",
                        "gte": 0.9,
                    }
                },
                "on": {
                    "failure": {
                        "goto": "RecordRecovery",
                    }
                },
            },
            {
                "name": "RecordRecovery",
                "id": "record_recovery",
                "set_scalar": {
                    "artifact": "recovered",
                    "value": True,
                },
            },
        ],
    }

    state = _load_executor(tmp_path, workflow).execute()

    assert state["status"] == "completed"
    assert state["steps"]["GateScore"]["status"] == "failed"
    assert state["steps"]["GateScore"]["exit_code"] == 3
    assert state["steps"]["GateScore"]["error"]["type"] == "assert_failed"
    assert state["steps"]["RecordRecovery"]["artifacts"] == {"recovered": True}
