"""Historical adjudication results exercise the retained report reader only."""

import json
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.report import build_status_snapshot, render_status_markdown
from orchestrator.workflow.executable_ir import (
    ExecutableWorkflow, LeafExecutableNode, ExecutableNodeKind, WorkflowRegion,
)
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.state_projection import (
    WorkflowStateProjection, CompatibilityNodeProjection, CompatibilityStepDefinition,
)
from orchestrator.workflow.surface_ast import SurfaceWorkflow, WorkflowProvenance


def _captured_report(workspace: Path, variant: str):
    fixture = Path(__file__).parent / "fixtures" / "historical_adjudication_report.json"
    captured = json.loads(fixture.read_text())["variants"][variant]
    captured = json.loads(json.dumps(captured).replace("@WORKSPACE@", str(workspace)))
    info = captured["bundle"]
    provenance = WorkflowProvenance(
        workflow_path=Path(captured["workflow_path"]),
        source_root=Path(captured["source_root"]),
    )
    node = LeafExecutableNode(
        node_id=info["node_id"], step_id=info["step_id"],
        presentation_name=info["display_name"], kind=ExecutableNodeKind(info["kind"]),
        region=WorkflowRegion(info["region"]), lexical_scope=tuple(info["lexical_scope"]),
    )
    entry = CompatibilityNodeProjection(
        node_id=node.node_id, step_id=node.step_id,
        presentation_key=info["step_name"], display_name=info["display_name"],
        region=node.region, compatibility_index=info["compatibility_index"],
        step_definition=CompatibilityStepDefinition(report_kind=info["report_kind"]),
    )
    bundle = LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version=info["version"], name=info["name"], steps=(), provenance=provenance,
        ),
        core_workflow_ast=None, semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version="workflow_executable_ir.v1", version=info["version"],
            name=info["name"], provenance=provenance, body_region=(node.node_id,),
            finalization_region=(), finalization_entry_node_id=None,
            nodes=MappingProxyType({node.node_id: node}),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType({node.node_id: entry}),
            node_id_by_compatibility_index=MappingProxyType({entry.compatibility_index: node.node_id}),
            compatibility_index_by_node_id=MappingProxyType({node.node_id: entry.compatibility_index}),
            presentation_key_by_node_id=MappingProxyType({node.node_id: entry.presentation_key}),
            node_id_by_step_id=MappingProxyType({node.step_id: node.node_id}),
        ),
        runtime_plan=None, imports=MappingProxyType({}), provenance=provenance,
    )
    return captured["state"], bundle


def test_report_projects_adjudication_fields_for_success_and_failure(tmp_path: Path) -> None:
    success_state, loaded = _captured_report(tmp_path, "success")
    success_snapshot = build_status_snapshot(
        loaded,
        success_state,
        tmp_path / ".orchestrate/runs/run-1",
    )
    success_adjudication = success_snapshot["steps"][0]["output"]["adjudication"]

    assert success_adjudication == {
        "selected_candidate_id": "b",
        "selected_score": 0.9,
        "selection_reason": "highest_score",
        "score_ledger_path": "artifacts/evaluations/draft_scores.jsonl",
        "run_score_ledger_path": success_state["steps"]["Draft"]["adjudication"]["run_score_ledger_path"],
        "promotion_status": "committed",
        "failure_type": None,
    }
    success_markdown = render_status_markdown(success_snapshot)
    assert "selected_candidate_id: `b`" in success_markdown
    assert "promotion_status: `committed`" in success_markdown

    failure_workspace = tmp_path / "failure"
    failure_workspace.mkdir()
    failure_state, failure_loaded = _captured_report(failure_workspace, "failure")
    failure_snapshot = build_status_snapshot(
        failure_loaded,
        failure_state,
        failure_workspace / ".orchestrate/runs/run-1",
    )
    failure_adjudication = failure_snapshot["steps"][0]["output"]["adjudication"]

    assert failure_adjudication["selected_candidate_id"] is None
    assert failure_adjudication["promotion_status"] == "not_selected"
    assert failure_adjudication["failure_type"] == "adjudication_partial_scoring_failed"
