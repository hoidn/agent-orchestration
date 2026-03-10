"""Tests for the typed surface workflow bundle and authored-shape AST."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.loaded_bundle import workflow_import_metadata, workflow_provenance
from orchestrator.workflow.predicates import ComparePredicateNode
from orchestrator.workflow.references import SelfOutputReference
from orchestrator.workflow.surface_ast import SurfaceStepKind


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_review_loop_library(workspace: Path) -> None:
    _write_yaml(
        workspace / "workflows" / "library" / "review_loop.yaml",
        {
            "version": "2.7",
            "name": "review-loop",
            "inputs": {
                "iteration": {
                    "kind": "scalar",
                    "type": "integer",
                },
                "write_root": {
                    "kind": "relpath",
                    "type": "relpath",
                },
            },
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {"ref": "root.steps.WriteDecision.artifacts.review_decision"},
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


def _write_surface_workflow(workspace: Path) -> Path:
    _write_review_loop_library(workspace)
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.7",
            "name": "surface-ast",
            "imports": {
                "review_loop": "workflows/library/review_loop.yaml",
            },
            "artifacts": {
                "ready": {"kind": "scalar", "type": "bool"},
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
            },
            "steps": [
                {
                    "name": "SetReady",
                    "id": "set_ready",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                },
                {
                    "name": "RouteReview",
                    "id": "route_review",
                    "if": {
                        "artifact_bool": {
                            "ref": "root.steps.SetReady.artifacts.ready",
                        }
                    },
                    "then": {
                        "id": "approve_path",
                        "steps": [
                            {
                                "name": "WriteApproved",
                                "id": "write_approved",
                                "set_scalar": {
                                    "artifact": "review_decision",
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
                                    "artifact": "review_decision",
                                    "value": "REVISE",
                                },
                            }
                        ],
                    },
                },
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.RunReviewLoop.artifacts.review_decision",
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
                                "name": "RunReviewLoop",
                                "id": "run_review_loop",
                                "call": "review_loop",
                                "with": {
                                    "iteration": 1,
                                    "write_root": "state/review-loop",
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
                        "name": "WriteCleanupMarker",
                        "id": "write_cleanup_marker",
                        "command": ["bash", "-lc", "printf 'cleanup\\n'"],
                    }
                ],
            },
        },
    )


def test_loader_builds_surface_bundle_with_authored_structured_nodes(tmp_path: Path):
    """load_bundle exposes typed provenance/imports plus authored-shape structured nodes."""
    workflow_path = _write_surface_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    assert bundle.surface.name == "surface-ast"
    assert bundle.provenance.workflow_path == workflow_path.resolve()
    assert bundle.provenance.source_root == workflow_path.parent.resolve()
    assert bundle.surface.provenance.workflow_path == workflow_path.resolve()
    assert tuple(bundle.imports) == ("review_loop",)
    assert bundle.imports["review_loop"].surface.name == "review-loop"

    route_review = bundle.surface.steps[1]
    assert route_review.kind is SurfaceStepKind.IF
    assert route_review.step_id == "root.route_review"
    assert route_review.then_branch is not None
    assert route_review.then_branch.step_id == "root.route_review.approve_path"
    assert route_review.then_branch.steps[0].step_id == "root.route_review.approve_path.write_approved"
    assert route_review.else_branch is not None
    assert route_review.else_branch.steps[0].step_id == "root.route_review.revise_path.write_revision"

    review_loop = bundle.surface.steps[2]
    assert review_loop.kind is SurfaceStepKind.REPEAT_UNTIL
    assert review_loop.repeat_until is not None
    assert review_loop.repeat_until.token == "iteration_body"
    assert review_loop.repeat_until.steps[0].step_id == "root.review_loop.iteration_body.run_review_loop"
    assert isinstance(review_loop.repeat_until.condition, ComparePredicateNode)
    assert isinstance(review_loop.repeat_until.condition.left, SelfOutputReference)
    assert review_loop.repeat_until.condition.left.output_name == "review_decision"

    assert bundle.surface.finalization is not None
    assert bundle.surface.finalization.step_id == "root.finally.cleanup"
    assert bundle.surface.finalization.steps[0].step_id == "root.finally.cleanup.write_cleanup_marker"

    lowered_step_names = [step["name"] for step in bundle.legacy_workflow["steps"]]
    assert "RouteReview.then" in lowered_step_names
    assert "RouteReview" in lowered_step_names


def test_legacy_load_exposes_typed_provenance_adapter_metadata(tmp_path: Path):
    """load() stays dict-compatible while surfacing typed provenance/import adapters."""
    workflow_path = _write_surface_workflow(tmp_path)

    loaded = WorkflowLoader(tmp_path).load(workflow_path)

    provenance = workflow_provenance(loaded)
    imported = workflow_import_metadata(loaded, "review_loop")

    assert isinstance(loaded, dict)
    assert provenance.workflow_path == workflow_path.resolve()
    assert provenance.source_root == workflow_path.parent.resolve()
    assert imported is not None
    assert imported.workflow_path == (tmp_path / "workflows" / "library" / "review_loop.yaml").resolve()
    assert imported.source_root == (tmp_path / "workflows" / "library").resolve()
