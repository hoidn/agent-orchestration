"""Tests for advisory DSL linting and normalization hints."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.linting import lint_workflow


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _load_workflow(tmp_path: Path, payload: dict) -> dict:
    workflow_path = _write_yaml(tmp_path / "workflow.yaml", payload)
    return WorkflowLoader(tmp_path).load(workflow_path)


def test_lint_warns_when_shell_gate_should_be_assert(tmp_path: Path):
    workflow = _load_workflow(
        tmp_path,
        {
            "version": "1.4",
            "name": "shell-gate",
            "steps": [
                {
                    "name": "CheckReady",
                    "command": ["bash", "-lc", "test -f state/ready.txt"],
                }
            ],
        },
    )

    warnings = lint_workflow(workflow)

    assert any(
        warning["code"] == "shell-gate-to-assert" and warning["step"] == "CheckReady"
        for warning in warnings
    )


def test_lint_warns_when_stringly_equals_can_be_typed_predicate(tmp_path: Path):
    workflow = _load_workflow(
        tmp_path,
        {
            "version": "1.6",
            "name": "stringly-when",
            "steps": [
                {
                    "name": "ReviewPlan",
                    "command": ["echo", "APPROVE"],
                },
                {
                    "name": "RouteDecision",
                    "when": {
                        "equals": {
                            "left": "${steps.ReviewPlan.output}",
                            "right": "APPROVE",
                        }
                    },
                    "command": ["echo", "route"],
                },
            ],
        },
    )

    warnings = lint_workflow(workflow)

    assert any(
        warning["code"] == "stringly-when-equals" and warning["step"] == "RouteDecision"
        for warning in warnings
    )


def test_lint_warns_when_raw_goto_diamond_can_be_structured_control(tmp_path: Path):
    workflow = _load_workflow(
        tmp_path,
        {
            "version": "1.4",
            "name": "goto-diamond",
            "steps": [
                {
                    "name": "ReviewDecision",
                    "command": ["bash", "-lc", "exit 0"],
                    "on": {
                        "success": {"goto": "Approved"},
                        "failure": {"goto": "Revise"},
                    },
                },
                {
                    "name": "Approved",
                    "command": ["echo", "approved"],
                },
                {
                    "name": "Revise",
                    "command": ["echo", "revise"],
                },
            ],
        },
    )

    warnings = lint_workflow(workflow)

    assert any(
        warning["code"] == "goto-diamond-to-structured-control"
        and warning["step"] == "ReviewDecision"
        for warning in warnings
    )


def test_lint_warns_when_imported_workflows_export_colliding_outputs(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review.yaml",
        {
            "version": "2.5",
            "name": "review-loop",
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "steps": [
                {
                    "name": "SetApproved",
                    "id": "set_approved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": True,
                    },
                }
            ],
        },
    )
    _write_yaml(
        tmp_path / "workflows" / "library" / "fix.yaml",
        {
            "version": "2.5",
            "name": "fix-loop",
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "steps": [
                {
                    "name": "SetApproved",
                    "id": "set_approved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": False,
                    },
                }
            ],
        },
    )

    workflow = _load_workflow(
        tmp_path,
        {
            "version": "2.5",
            "name": "import-collision",
            "imports": {
                "review_loop": "workflows/library/review.yaml",
                "fix_loop": "workflows/library/fix.yaml",
            },
            "steps": [
                {
                    "name": "Done",
                    "command": ["echo", "done"],
                }
            ],
        },
    )

    warnings = lint_workflow(workflow)

    assert any(
        warning["code"] == "import-output-collision" and warning["output"] == "approved"
        for warning in warnings
    )
