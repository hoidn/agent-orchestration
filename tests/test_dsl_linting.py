"""Tests for advisory DSL linting and normalization hints."""

from pathlib import Path

import pytest
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


def _load_workflow_bundle(tmp_path: Path, payload: dict):
    workflow_path = _write_yaml(tmp_path / "workflow.yaml", payload)
    return WorkflowLoader(tmp_path).load_bundle(workflow_path)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


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

    assert not hasattr(workflow.surface, "raw")

    warnings = lint_workflow(workflow)

    assert any(
        warning["code"] == "import-output-collision" and warning["output"] == "approved"
        for warning in warnings
    )


def test_lint_warns_when_top_level_relpath_boundaries_redundantly_declare_kind(tmp_path: Path):
    workflow = _load_workflow(
        tmp_path,
        {
            "version": "2.9",
            "name": "redundant-relpath-boundaries",
            "inputs": {
                "design_path": {
                    "kind": "relpath",
                    "type": "relpath",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            },
            "outputs": {
                "report_path": {
                    "kind": "relpath",
                    "type": "relpath",
                    "under": "artifacts/reports",
                    "must_exist_target": True,
                    "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
                }
            },
            "steps": [
                {
                    "name": "GenerateReport",
                    "command": ["bash", "-lc", "true"],
                    "expected_outputs": [
                        {
                            "name": "report_path",
                            "path": "state/report_path.txt",
                            "type": "relpath",
                            "under": "artifacts/reports",
                        }
                    ],
                }
            ],
        },
    )

    warnings = lint_workflow(workflow)

    warning_paths = {
        warning["path"]
        for warning in warnings
        if warning["code"] == "redundant-relpath-boundary-kind"
    }

    assert warning_paths == {"inputs.design_path", "outputs.report_path"}


def test_lint_does_not_warn_for_non_boundary_relpath_contracts(tmp_path: Path):
    workflow = _load_workflow(
        tmp_path,
        {
            "version": "2.9",
            "name": "relpath-lint-scope",
            "inputs": {
                "max_cycles": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "artifacts": {
                "report_path": {
                    "kind": "relpath",
                    "type": "relpath",
                    "pointer": "state/report_path.txt",
                },
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                },
            },
            "steps": [
                {
                    "name": "GenerateReport",
                    "command": ["bash", "-lc", "true"],
                    "expected_outputs": [
                        {
                            "name": "report_path",
                            "path": "state/report_path.txt",
                            "type": "relpath",
                            "under": "artifacts/reports",
                        }
                    ],
                    "publishes": [{"artifact": "report_path", "from": "report_path"}],
                },
                {
                    "name": "SetApproved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": True,
                    },
                },
            ],
        },
    )

    warnings = lint_workflow(workflow)

    assert all(warning["code"] != "redundant-relpath-boundary-kind" for warning in warnings)


def test_lint_does_not_warn_for_active_examples_using_preferred_relpath_boundary_style():
    repo_root = _repo_root()
    loader = WorkflowLoader(repo_root)
    workflow_paths = [
        "workflows/examples/design_plan_impl_review_stack_v2_call.yaml",
        "workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml",
        "workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml",
        "workflows/examples/workflow_signature_demo.yaml",
        "workflows/examples/library/repeat_until_review_loop.yaml",
        "workflows/library/depends_on_inject_imported_review.yaml",
        "workflows/library/review_fix_loop.yaml",
        "workflows/library/tracked_design_phase.yaml",
        "workflows/library/tracked_plan_phase.yaml",
        "workflows/library/design_plan_impl_implementation_phase.yaml",
        "workflows/library/follow_on_plan_phase.yaml",
        "workflows/library/follow_on_implementation_phase.yaml",
    ]

    for workflow_relpath in workflow_paths:
        workflow = loader.load(repo_root / workflow_relpath)
        warnings = lint_workflow(workflow)
        assert all(
            warning["code"] != "redundant-relpath-boundary-kind"
            for warning in warnings
        ), workflow_relpath


def test_lint_requires_loaded_workflow_bundle() -> None:
    with pytest.raises(TypeError, match="LoadedWorkflowBundle"):
        lint_workflow({"steps": []})


def test_lint_uses_surface_steps_from_typed_bundle(tmp_path: Path):
    bundle = _load_workflow_bundle(
        tmp_path,
        {
            "version": "1.4",
            "name": "shell-gate-bundle",
            "steps": [
                {
                    "name": "CheckReady",
                    "command": ["bash", "-lc", "test -f state/ready.txt"],
                }
            ],
        },
    )

    warnings = lint_workflow(bundle)

    assert any(
        warning["code"] == "shell-gate-to-assert" and warning["step"] == "CheckReady"
        for warning in warnings
    )


def test_lint_uses_typed_surface_leaf_fields_without_raw_payloads(tmp_path: Path):
    bundle = _load_workflow_bundle(
        tmp_path,
        {
            "version": "1.4",
            "name": "typed-lint-raw-drift",
            "steps": [
                {
                    "name": "CheckReady",
                    "command": ["bash", "-lc", "test -f state/ready.txt"],
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
    assert not hasattr(bundle.surface.steps[0], "raw")

    warnings = lint_workflow(bundle)
    warning_codes = {
        warning["code"]
        for warning in warnings
        if warning.get("step") == "CheckReady"
    }

    assert "shell-gate-to-assert" in warning_codes
    assert "goto-diamond-to-structured-control" in warning_codes


def test_lint_uses_typed_legacy_when_condition_without_raw_payloads(tmp_path: Path):
    bundle = _load_workflow_bundle(
        tmp_path,
        {
            "version": "1.4",
            "name": "typed-lint-legacy-when-raw-drift",
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
    assert not hasattr(bundle.surface.steps[1], "raw")

    warnings = lint_workflow(bundle)

    assert any(
        warning["code"] == "stringly-when-equals" and warning["step"] == "RouteDecision"
        for warning in warnings
    )


def test_lint_uses_typed_import_outputs_from_imported_bundles(tmp_path: Path):
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

    bundle = _load_workflow_bundle(
        tmp_path,
        {
            "version": "2.5",
            "name": "import-collision-bundle",
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

    warnings = lint_workflow(bundle)

    assert any(
        warning["code"] == "import-output-collision" and warning["output"] == "approved"
        for warning in warnings
    )
