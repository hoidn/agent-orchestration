from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_imported_workflow(workspace: Path) -> None:
    _write_yaml(
        workspace / "workflows" / "library" / "review_loop.yaml",
        {
            "version": "2.7",
            "name": "review-loop",
            "inputs": {
                "iteration": {"kind": "scalar", "type": "integer"},
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {"ref": "root.steps.WriteDecision.artifacts.review_decision"},
                }
            },
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "steps": [
                {
                    "name": "WriteDecision",
                    "id": "write_decision",
                    "set_scalar": {
                        "artifact": "review_decision",
                        "value": "APPROVE",
                    },
                }
            ],
        },
    )


def _write_core_ast_workflow(workspace: Path) -> Path:
    _write_imported_workflow(workspace)
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.7",
            "name": "core-ast",
            "inputs": {
                "decision_in": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "imports": {
                "review_loop": "workflows/library/review_loop.yaml",
            },
            "providers": {
                "audit_provider": {
                    "command": ["echo", "${PROMPT}"],
                    "input_mode": "argv",
                }
            },
            "artifacts": {
                "ready": {"kind": "scalar", "type": "bool"},
                "decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
                "route_action": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["SHIP", "FIX"],
                },
            },
            "steps": [
                {
                    "name": "RunChecks",
                    "id": "run_checks",
                    "command": ["python", "scripts/run_checks.py", "--strict"],
                },
                {
                    "name": "DraftSummary",
                    "id": "draft_summary",
                    "provider": "audit_provider",
                    "input_file": "prompts/review.md",
                },
                {
                    "name": "RouteReview",
                    "id": "route_review",
                    "if": {
                        "compare": {
                            "left": 1,
                            "op": "eq",
                            "right": 1,
                        }
                    },
                    "then": {
                        "id": "approve_path",
                        "steps": [
                            {
                                "name": "WriteApproved",
                                "id": "write_approved",
                                "set_scalar": {
                                    "artifact": "decision",
                                    "value": "APPROVE",
                                },
                            }
                        ],
                    },
                    "else": {
                        "id": "revise_path",
                        "steps": [
                            {
                                "name": "WriteRevision",
                                "id": "write_revision",
                                "set_scalar": {
                                    "artifact": "decision",
                                    "value": "REVISE",
                                },
                            }
                        ],
                    },
                },
                {
                    "name": "RouteDecision",
                    "id": "route_decision",
                    "match": {
                        "ref": "inputs.decision_in",
                        "cases": {
                            "APPROVE": {
                                "id": "approve_case",
                                "steps": [
                                    {
                                        "name": "WriteShip",
                                        "id": "write_ship",
                                        "set_scalar": {
                                            "artifact": "route_action",
                                            "value": "SHIP",
                                        },
                                    }
                                ],
                            },
                            "REVISE": {
                                "id": "revise_case",
                                "steps": [
                                    {
                                        "name": "WriteFix",
                                        "id": "write_fix",
                                        "set_scalar": {
                                            "artifact": "route_action",
                                            "value": "FIX",
                                        },
                                    }
                                ],
                            },
                        },
                    },
                },
                {
                    "name": "RunReview",
                    "id": "run_review",
                    "call": "review_loop",
                    "with": {
                        "iteration": 1,
                    },
                },
            ],
        },
    )


def test_build_core_workflow_ast_from_yaml_bundle_records_statement_order_and_metadata(
    tmp_path: Path,
) -> None:
    core_ast_module = importlib.import_module("orchestrator.workflow.core_ast")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_core_ast_workflow(tmp_path))
    core_ast = bundle.core_workflow_ast

    assert core_ast.schema_version == core_ast_module.CORE_WORKFLOW_AST_SCHEMA_VERSION
    assert core_ast.workflow_name == "core-ast"
    assert tuple(statement.meta.step_kind for statement in core_ast.body) == (
        "command",
        "provider",
        "if",
        "match",
        "call",
    )
    assert tuple(statement.meta.step_id for statement in core_ast.body) == (
        "run_checks",
        "draft_summary",
        "route_review",
        "route_decision",
        "run_review",
    )
    assert core_ast.imports["review_loop"].workflow_name == "review-loop"

    command_stmt = core_ast.body[0]
    assert command_stmt.meta.display_name == "RunChecks"
    assert command_stmt.meta.origin_key
    assert command_stmt.boundary_kind == "external_tool"
    assert command_stmt.boundary_name == "RunChecks"
    assert command_stmt.boundary_name != "scripts/run_checks.py"


def test_core_ast_helper_returns_shared_surface_from_loaded_bundle(tmp_path: Path) -> None:
    loaded_bundle_module = importlib.import_module("orchestrator.workflow.loaded_bundle")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_core_ast_workflow(tmp_path))

    assert loaded_bundle_module.workflow_core_ast(bundle) is bundle.core_workflow_ast
    assert loaded_bundle_module.workflow_core_ast(None) is None
    assert loaded_bundle_module.workflow_core_ast({"not": "a bundle"}) is None


def test_core_ast_validation_rejects_missing_source_map_origin(tmp_path: Path) -> None:
    core_ast_module = importlib.import_module("orchestrator.workflow.core_ast")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_core_ast_workflow(tmp_path))
    first_stmt = bundle.core_workflow_ast.body[0]
    broken_stmt = replace(first_stmt, meta=replace(first_stmt.meta, origin_key=""))
    broken_core_ast = replace(
        bundle.core_workflow_ast,
        body=(broken_stmt, *bundle.core_workflow_ast.body[1:]),
    )

    with pytest.raises(WorkflowValidationError) as excinfo:
        core_ast_module.validate_core_workflow_ast(broken_core_ast, imports=bundle.imports)

    error = excinfo.value.errors[0]
    assert "core_workflow_ast_invalid" in error.message
    assert error.subject_refs
    assert error.subject_refs[0].subject_kind == "step_id"
    assert error.subject_refs[0].subject_name.endswith("run_checks")
