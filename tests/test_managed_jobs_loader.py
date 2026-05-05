from pathlib import Path
from copy import deepcopy

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader


def _write_workflow(tmp_path: Path, workflow: dict) -> Path:
    path = tmp_path / "workflow.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    return path


def _base_workflow(version: str) -> dict:
    return {
        "version": version,
        "name": "managed-provider",
        "providers": {
            "impl": {
                "command": ["python", "-c", "print('ok')"],
                "input_mode": "stdin",
            },
        },
        "steps": [
            {
                "name": "Execute",
                "provider": "impl",
                "managed_jobs": {
                    "policy": "workflows/managed_jobs/policy.yaml",
                    "watch_roots": ["scripts/training"],
                    "backend": "auto",
                    "poll_budget_sec": 60,
                    "on": {
                        "complete": "Review",
                        "failed": "Fix",
                        "invalid": "Fix",
                        "outstanding": "fail_resumable",
                    },
                },
            },
            {"name": "Review", "command": ["true"]},
            {"name": "Fix", "command": ["true"]},
        ],
    }


def _load(tmp_path: Path, workflow: dict):
    return WorkflowLoader(tmp_path).load(_write_workflow(tmp_path, workflow))


def _messages(exc_info: pytest.ExceptionInfo[WorkflowValidationError]) -> list[str]:
    return [str(error.message) for error in exc_info.value.errors]


def test_managed_jobs_requires_v213(tmp_path: Path) -> None:
    with pytest.raises(WorkflowValidationError) as exc_info:
        _load(tmp_path, _base_workflow("2.12"))

    assert any("managed_jobs requires version '2.13'" in message for message in _messages(exc_info))


def test_managed_jobs_loads_at_v213(tmp_path: Path) -> None:
    loaded = _load(tmp_path, _base_workflow("2.13"))

    assert loaded.surface.version == "2.13"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda workflow: (
                workflow["steps"][0].pop("provider"),
                workflow["steps"][0].update({"command": ["true"]}),
            ),
            "managed_jobs is valid only on provider steps",
        ),
        (
            lambda workflow: (
                workflow["steps"][0].pop("provider"),
                workflow["steps"][0].update(
                    {
                        "adjudicated_provider": {
                            "candidates": [{"id": "candidate_a", "provider": "impl"}],
                            "evaluator": {
                                "provider": "impl",
                                "input_file": "prompts/evaluate.md",
                                "evidence_confidentiality": "same_trust_boundary",
                            },
                            "score_ledger_path": "artifacts/scores.jsonl",
                        },
                        "input_file": "prompts/task.md",
                        "expected_outputs": [
                            {
                                "name": "decision",
                                "path": "artifacts/decision.txt",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                            }
                        ],
                    }
                ),
            ),
            "managed_jobs is invalid with adjudicated_provider",
        ),
        (lambda workflow: workflow["steps"][0].update({"retries": {"max": 1}}), "managed_jobs cannot be combined with provider retries"),
        (lambda workflow: workflow["steps"][0].update({"on": {"success": {"goto": "Review"}}}), "managed_jobs cannot be combined with ordinary on handlers"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"].pop("policy"), "managed_jobs.policy is required"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"].update({"watch_roots": []}), "managed_jobs.watch_roots must be a non-empty list"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"].update({"policy": "/tmp/policy.yaml"}), "managed_jobs.policy: absolute paths not allowed"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"].update({"watch_roots": ["../training"]}), "managed_jobs.watch_roots[0]: parent directory traversal"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"].update({"backend": "pbs"}), "managed_jobs.backend must be one of"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"].update({"poll_budget_sec": 0}), "managed_jobs.poll_budget_sec must be a positive integer"),
        (
            lambda workflow: (
                workflow["steps"][0].update({"timeout_sec": 10}),
                workflow["steps"][0]["managed_jobs"].update({"poll_budget_sec": 11}),
            ),
            "managed_jobs.poll_budget_sec cannot exceed timeout_sec",
        ),
        (lambda workflow: workflow["steps"][0]["managed_jobs"]["on"].pop("complete"), "managed_jobs.on.complete is required"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"]["on"].update({"outstanding": "Review"}), "managed_jobs.on.outstanding must be 'fail_resumable'"),
        (lambda workflow: workflow["steps"][0]["managed_jobs"]["on"].update({"complete": "Missing"}), "managed_jobs.on.complete references unknown target 'Missing'"),
    ],
)
def test_managed_jobs_rejects_invalid_schema(tmp_path: Path, mutate, expected: str) -> None:
    workflow = deepcopy(_base_workflow("2.13"))
    mutate(workflow)

    with pytest.raises(WorkflowValidationError) as exc_info:
        _load(tmp_path, workflow)

    assert any(expected in message for message in _messages(exc_info))
