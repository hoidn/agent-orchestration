from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
PURE_EXPR_SELECTOR_PROJECTION = VALID_FIXTURES / "pure_expr_selector_action_projection.orc"


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


def _compile_pure_projection_bundle(tmp_path: Path):
    result = compile_stage3_entrypoint(
        PURE_EXPR_SELECTOR_PROJECTION,
        source_roots=(VALID_FIXTURES,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_selector_action_projection::orchestrate"]


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
                        "outputs": {
                            "decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.WriteApproved.artifacts.decision",
                                },
                            }
                        },
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
                        "outputs": {
                            "decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.WriteRevision.artifacts.decision",
                                },
                            }
                        },
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
                                "outputs": {
                                    "route_action": {
                                        "kind": "scalar",
                                        "type": "enum",
                                        "allowed": ["SHIP", "FIX"],
                                        "from": {
                                            "ref": "self.steps.WriteShip.artifacts.route_action",
                                        },
                                    }
                                },
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
                                "outputs": {
                                    "route_action": {
                                        "kind": "scalar",
                                        "type": "enum",
                                        "allowed": ["SHIP", "FIX"],
                                        "from": {
                                            "ref": "self.steps.WriteFix.artifacts.route_action",
                                        },
                                    }
                                },
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


def _write_control_taxonomy_workflow(workspace: Path) -> Path:
    (workspace / "prompt.md").write_text("review\n", encoding="utf-8")
    return _write_yaml(
        workspace / "control-taxonomy.yaml",
        {
            "version": "2.14",
            "name": "control-taxonomy",
            "providers": {
                "fake_provider": {
                    "command": [
                        "bash",
                        "-lc",
                        "cat >/dev/null; printf '{\"review_decision\":\"APPROVE\"}\\n'",
                    ],
                    "input_mode": "stdin",
                }
            },
            "artifacts": {
                "failed_count": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [
                {
                    "name": "WaitForSignal",
                    "id": "wait_for_signal",
                    "wait_for": {
                        "patterns": ["*.txt"],
                        "timeout_sec": 1,
                    },
                },
                {
                    "name": "AssertReady",
                    "id": "assert_ready",
                    "assert": {
                        "equals": {
                            "left": 1,
                            "right": 1,
                        }
                    },
                },
                {
                    "name": "InitializeCounter",
                    "id": "initialize_counter",
                    "set_scalar": {
                        "artifact": "failed_count",
                        "value": 1,
                    },
                },
                {
                    "name": "IncrementCounter",
                    "id": "increment_counter",
                    "increment_scalar": {
                        "artifact": "failed_count",
                        "by": 2,
                    },
                },
                {
                    "name": "MaterializeTargets",
                    "id": "materialize_targets",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "execution_report_target_path",
                                "source": {
                                    "literal": "artifacts/work/execution_report.md",
                                },
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": False,
                                },
                            },
                            {
                                "name": "progress_report_target_path",
                                "source": {
                                    "literal": "artifacts/work/progress_report.md",
                                },
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": False,
                                },
                            },
                        ]
                    },
                },
                {
                    "name": "CaptureBefore",
                    "id": "capture_before",
                    "pre_snapshot": {
                        "name": "before",
                        "digest": "sha256",
                        "candidates": {
                            "COMPLETED": {
                                "ref": "root.steps.MaterializeTargets.artifacts.execution_report_target_path",
                            },
                            "BLOCKED": {
                                "ref": "root.steps.MaterializeTargets.artifacts.progress_report_target_path",
                            },
                        },
                    },
                    "command": ["echo", "ok"],
                },
                {
                    "name": "SelectImplementationOutcome",
                    "id": "select_implementation_outcome",
                    "select_variant_output": {
                        "path": "state/implementation_state.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED", "BLOCKED"],
                        },
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "execution_report_path",
                                        "json_pointer": "/execution_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                            "BLOCKED": {
                                "fields": [
                                    {
                                        "name": "progress_report_path",
                                        "json_pointer": "/progress_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                        },
                        "evidence": {
                            "mode": "snapshot_diff",
                            "snapshot": {
                                "ref": "root.steps.CaptureBefore.snapshots.before",
                            },
                        },
                    },
                },
                {
                    "name": "LoopItems",
                    "id": "loop_items",
                    "for_each": {
                        "items": ["one"],
                        "steps": [
                            {
                                "name": "LoopCommand",
                                "id": "loop_command",
                                "command": ["echo", "loop"],
                            }
                        ],
                    },
                },
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "review_iteration",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.ReviewProvider.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {
                                    "ref": "self.outputs.review_decision",
                                },
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "max_iterations": 3,
                        "steps": [
                            {
                                "name": "ReviewProvider",
                                "id": "review_provider",
                                "provider": "fake_provider",
                                "input_file": "prompt.md",
                                "output_bundle": {
                                    "path": "state/review-decision.json",
                                    "fields": [
                                        {
                                            "name": "review_decision",
                                            "json_pointer": "/review_decision",
                                            "type": "enum",
                                            "allowed": ["APPROVE", "REVISE"],
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                },
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "Cleanup",
                        "id": "cleanup_cmd",
                        "command": ["echo", "clean"],
                    }
                ],
            },
        },
    )


def _write_adjudicated_provider_workflow(workspace: Path) -> Path:
    (workspace / "prompt.md").write_text("draft\n", encoding="utf-8")
    (workspace / "evaluator.md").write_text("score\n", encoding="utf-8")
    return _write_yaml(
        workspace / "adjudicated-taxonomy.yaml",
        {
            "version": "2.14",
            "name": "adjudicated-taxonomy",
            "artifacts": {
                "result_path": {
                    "kind": "relpath",
                    "type": "relpath",
                    "pointer": "state/result_path.txt",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            },
            "providers": {
                "candidate_a": {
                    "command": [
                        "bash",
                        "-lc",
                        "cat >/dev/null; mkdir -p state docs/plans; "
                        "printf 'docs/plans/a.md\\n' > state/result_path.txt; "
                        "printf 'a' > docs/plans/a.md",
                    ],
                    "input_mode": "stdin",
                },
                "candidate_b": {
                    "command": [
                        "bash",
                        "-lc",
                        "cat >/dev/null; mkdir -p state docs/plans; "
                        "printf 'docs/plans/b.md\\n' > state/result_path.txt; "
                        "printf 'b' > docs/plans/b.md",
                    ],
                    "input_mode": "stdin",
                },
                "evaluator": {
                    "command": [
                        "bash",
                        "-lc",
                        "cat >/dev/null; printf '{\"candidate_id\":\"a\",\"score\":1,\"summary\":\"ok\"}\\n'",
                    ],
                    "input_mode": "stdin",
                },
            },
            "steps": [
                {
                    "name": "Draft",
                    "id": "draft",
                    "input_file": "prompt.md",
                    "adjudicated_provider": {
                        "candidates": [
                            {
                                "id": "a",
                                "provider": "candidate_a",
                            },
                            {
                                "id": "b",
                                "provider": "candidate_b",
                            },
                        ],
                        "evaluator": {
                            "provider": "evaluator",
                            "input_file": "evaluator.md",
                            "evidence_confidentiality": "same_trust_boundary",
                        },
                        "selection": {
                            "tie_break": "candidate_order",
                        },
                        "score_ledger_path": "artifacts/evaluations/draft_scores.jsonl",
                    },
                    "expected_outputs": [
                        {
                            "name": "result_path",
                            "path": "state/result_path.txt",
                            "type": "relpath",
                            "under": "docs/plans",
                            "must_exist_target": True,
                        }
                    ],
                    "publishes": [
                        {
                            "artifact": "result_path",
                            "from": "result_path",
                        }
                    ],
                }
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


def test_core_ast_records_current_base_statement_family_inventory(tmp_path: Path) -> None:
    core_ast_module = importlib.import_module("orchestrator.workflow.core_ast")

    primary = WorkflowLoader(tmp_path).load_bundle(_write_core_ast_workflow(tmp_path))
    control = WorkflowLoader(tmp_path).load_bundle(_write_control_taxonomy_workflow(tmp_path))
    adjudicated = WorkflowLoader(tmp_path).load_bundle(_write_adjudicated_provider_workflow(tmp_path))
    pure_projection = _compile_pure_projection_bundle(tmp_path)

    emitted_kinds = {
        statement["kind"]
        for bundle in (primary, control, adjudicated, pure_projection)
        for statement in core_ast_module.workflow_core_ast_to_json(bundle.core_workflow_ast)["body"]
    }
    finalization = core_ast_module.workflow_core_ast_to_json(control.core_workflow_ast)["finalization"]

    assert emitted_kinds == {
        "adjudicated_provider",
        "assert",
        "call",
        "command",
        "for_each",
        "if",
        "increment_scalar",
        "match",
        "materialize_artifacts",
        "pure_projection",
        "provider",
        "repeat_until",
        "select_variant_output",
        "set_scalar",
        "wait_for",
    }
    assert finalization is not None
    assert finalization["step_id"] == "root.finally.cleanup"
    assert [statement["kind"] for statement in finalization["statements"]] == ["command"]


def test_core_ast_serializes_pure_projection_statement_payload(tmp_path: Path) -> None:
    core_ast_module = importlib.import_module("orchestrator.workflow.core_ast")
    bundle = _compile_pure_projection_bundle(tmp_path)

    body = core_ast_module.workflow_core_ast_to_json(bundle.core_workflow_ast)["body"]

    assert [statement["kind"] for statement in body] == ["pure_projection"]
    assert body[0]["pure_projection"]["payload"]["pure_expr_schema_version"] == 1
    assert body[0]["pure_projection"]["output_contracts"]["return__status"]["type"] == "string"
    assert body[0]["common"]["output_bundle"]["path"] == "${inputs.__write_root__pure_expr_selector_action_projection_orchestrate__result_bundle}"


def test_core_ast_structural_blocks_preserve_nested_lineage(tmp_path: Path) -> None:
    core_ast_module = importlib.import_module("orchestrator.workflow.core_ast")
    primary = WorkflowLoader(tmp_path).load_bundle(_write_core_ast_workflow(tmp_path))
    control = WorkflowLoader(tmp_path).load_bundle(_write_control_taxonomy_workflow(tmp_path))

    branch_statement = primary.core_workflow_ast.body[2]
    match_statement = primary.core_workflow_ast.body[3]

    assert branch_statement.then_branch.step_id == "root.route_review.approve_path"
    assert list(branch_statement.then_branch.outputs) == ["decision"]
    assert [statement.meta.step_id for statement in branch_statement.then_branch.statements] == ["write_approved"]
    assert branch_statement.else_branch is not None
    assert branch_statement.else_branch.step_id == "root.route_review.revise_path"
    assert list(branch_statement.else_branch.outputs) == ["decision"]
    assert [statement.meta.step_id for statement in branch_statement.else_branch.statements] == ["write_revision"]

    approve_case = match_statement.cases["APPROVE"]
    revise_case = match_statement.cases["REVISE"]
    assert approve_case.step_id == "root.route_decision.approve_case"
    assert list(approve_case.outputs) == ["route_action"]
    assert [statement.meta.step_id for statement in approve_case.statements] == ["write_ship"]
    assert revise_case.step_id == "root.route_decision.revise_case"
    assert list(revise_case.outputs) == ["route_action"]
    assert [statement.meta.step_id for statement in revise_case.statements] == ["write_fix"]

    assert control.core_workflow_ast.finalization is not None
    assert control.core_workflow_ast.finalization.step_id == "root.finally.cleanup"
    assert [statement.meta.step_id for statement in control.core_workflow_ast.finalization.statements] == [
        "cleanup_cmd"
    ]

    traversed = tuple(core_ast_module._iter_statements(control.core_workflow_ast))
    traversed_step_ids = {statement.meta.step_id for statement in traversed}
    assert "loop_items" in traversed_step_ids
    assert "loop_command" in traversed_step_ids
    assert "review_loop" in traversed_step_ids
    assert "review_provider" in traversed_step_ids
    assert "cleanup_cmd" in traversed_step_ids
    assert all(statement.meta.id for statement in traversed)
    assert all(statement.meta.step_id for statement in traversed)
    assert all(statement.meta.origin_key for statement in traversed)


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
