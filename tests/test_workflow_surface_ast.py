"""Tests for the typed surface workflow bundle and authored-shape AST."""

from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.loaded_bundle import (
    LoadedWorkflowBundle,
    workflow_context,
    workflow_import_metadata,
    workflow_provenance,
)
from orchestrator.workflow.predicates import ComparePredicateNode
from orchestrator.workflow.references import SelfOutputReference
from orchestrator.workflow.surface_ast import SurfaceStepKind
from tests.workflow_bundle_helpers import materialize_projection_body_steps


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
            "strict_flow": False,
            "context": {
                "project": "typed-pipeline",
            },
            "processed_dir": "typed-processed",
            "max_transitions": 9,
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


@dataclass
class _RecordingValidationBackend:
    calls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    managed_inputs: tuple[set[str], list[str]] = field(default_factory=lambda: (set(), []))

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def error_count(self) -> int:
        return len(self.errors)

    def version_at_least(self, version: str, minimum: str) -> bool:
        order = [
            "1.1", "1.1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8",
            "2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10",
        ]
        return order.index(version) >= order.index(minimum)

    def validate_top_level(self, workflow: dict, version: str) -> None:
        self.calls.append(f"validate_top_level:{version}")

    def build_finalization_catalog_steps(self, finalization: dict | None) -> list[dict]:
        self.calls.append("build_finalization_catalog_steps")
        if not isinstance(finalization, dict):
            return []
        steps = finalization.get("steps")
        if not isinstance(steps, list):
            return []
        prefixed = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            copied = dict(step)
            if isinstance(copied.get("name"), str):
                copied["name"] = f"finally.{copied['name']}"
            prefixed.append(copied)
        return prefixed

    def build_root_ref_catalog(self, steps: list[dict], artifacts: dict | None) -> dict:
        self.calls.append("build_root_ref_catalog")
        return {"artifacts": artifacts or {}, "multi_visit": set(), "non_step_results": set()}

    def validate_steps(
        self,
        steps: list[dict],
        version: str,
        artifacts_registry: dict | None,
        *,
        root_catalog: dict,
    ) -> None:
        self.calls.append(f"validate_steps:{len(steps)}")

    def validate_finally_block(
        self,
        finalization: dict | None,
        version: str,
        artifacts_registry: dict | None,
        root_catalog: dict,
    ) -> None:
        self.calls.append("validate_finally_block")

    def validate_dataflow_cross_references(self, steps: list[dict], artifacts: dict | None) -> None:
        self.calls.append(f"validate_dataflow_cross_references:{len(steps)}")

    def validate_workflow_outputs(self, outputs: dict, version: str, root_catalog: dict) -> None:
        self.calls.append(f"validate_workflow_outputs:{len(outputs)}")

    def validate_goto_targets(self, workflow: dict) -> None:
        self.calls.append("validate_goto_targets")

    def analyze_reusable_write_roots(self, workflow: dict) -> tuple[set[str], list[str]]:
        self.calls.append("analyze_reusable_write_roots")
        return self.managed_inputs

    def validate_call_write_root_collisions(self, steps: list[dict], finalization: dict | None) -> None:
        self.calls.append("validate_call_write_root_collisions")


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

    projection_step_names = [step["name"] for step in materialize_projection_body_steps(bundle)]
    assert "RouteReview.then" in projection_step_names
    assert "RouteReview" in projection_step_names


def test_load_exposes_typed_provenance_bundle_metadata(tmp_path: Path):
    """load() returns the typed bundle and surfaces provenance/import metadata directly."""
    workflow_path = _write_surface_workflow(tmp_path)

    loaded = WorkflowLoader(tmp_path).load(workflow_path)

    provenance = workflow_provenance(loaded)
    imported = workflow_import_metadata(loaded, "review_loop")

    assert isinstance(loaded, LoadedWorkflowBundle)
    assert not hasattr(loaded, "legacy_workflow")
    assert provenance.workflow_path == workflow_path.resolve()
    assert provenance.source_root == workflow_path.parent.resolve()
    assert imported is not None
    assert imported.workflow_path == (tmp_path / "workflows" / "library" / "review_loop.yaml").resolve()
    assert imported.source_root == (tmp_path / "workflows" / "library").resolve()


def test_surface_workflow_exposes_typed_root_metadata_without_raw_fallbacks(tmp_path: Path):
    """Typed workflow-root metadata stays available even when raw compatibility data is absent."""
    workflow_path = _write_surface_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    assert bundle.surface.strict_flow is False
    assert dict(bundle.surface.context) == {"project": "typed-pipeline"}
    assert bundle.surface.processed_dir == "typed-processed"
    assert bundle.surface.max_transitions == 9

    rawless_bundle = replace(
        bundle,
        surface=replace(bundle.surface, raw=MappingProxyType({})),
    )

    assert dict(workflow_context(rawless_bundle)) == {"project": "typed-pipeline"}


def test_elaboration_orchestrates_authored_shape_validation_before_ast_build(tmp_path: Path):
    """Elaboration owns authored-shape validation orchestration before AST materialization."""
    workflow_path = _write_surface_workflow(tmp_path)
    backend = _RecordingValidationBackend(managed_inputs=({"write_root"}, []))
    raw_workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    surface = elaborate_surface_workflow(
        raw_workflow,
        workflow_path=workflow_path,
        imported_bundles={},
        validation_backend=backend,
        workflow_is_imported=True,
    )

    assert surface is not None
    assert backend.calls == [
        "validate_top_level:2.7",
        "build_finalization_catalog_steps",
        "build_root_ref_catalog",
        "validate_steps:3",
        "validate_finally_block",
        "validate_goto_targets",
        "analyze_reusable_write_roots",
        "validate_call_write_root_collisions",
    ]
    assert surface.provenance.managed_write_root_inputs == ("write_root",)


def test_elaboration_returns_none_when_validation_backend_reports_errors(tmp_path: Path):
    """Elaboration must stop before AST parsing if authored-shape validation already failed."""
    workflow_path = _write_surface_workflow(tmp_path)
    backend = _RecordingValidationBackend()
    raw_workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    backend.errors.append("synthetic validation failure")

    surface = elaborate_surface_workflow(
        raw_workflow,
        workflow_path=workflow_path,
        imported_bundles={},
        validation_backend=backend,
    )

    assert surface is None
