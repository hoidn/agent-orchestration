from __future__ import annotations



from pathlib import Path












from orchestrator.workflow.core_ast import build_core_workflow_ast, workflow_core_ast_to_json








from orchestrator.workflow.references import MaterializeViewBindingReference






from orchestrator.workflow.state_layout import (
    GeneratedPathAllocationRequest,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
    StateLayout,
)


from orchestrator.workflow.surface_ast import (
    SurfaceContract,
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)


from orchestrator.workflow.view_renderer import VIEW_RENDERER_SCHEMA_VERSION






REPO_ROOT = Path(__file__).resolve().parent.parent


VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"


MATERIALIZE_VIEW_RUNTIME = VALID_FIXTURES / "materialize_view_runtime.orc"


MATERIALIZE_VIEW_ALLOCATED_TARGET = VALID_FIXTURES / "materialize_view_allocated_target.orc"


ENTRY_PUBLICATION_RUNTIME = VALID_FIXTURES / "entry_publication_runtime.orc"


def _materialized_value_type() -> dict[str, object]:
    return {
        "kind": "record",
        "name": "DrainSummaryValue",
        "fields": [
            {"name": "status", "type": {"kind": "primitive", "name": "String"}},
            {"name": "run_state_path", "type": {"kind": "path", "name": "RunStatePath"}},
        ],
    }


def _path_contract(*, under: str) -> dict[str, object]:
    return {
        "kind": "relpath",
        "type": "relpath",
        "under": under,
        "must_exist_target": True,
    }


def _string_contract() -> dict[str, object]:
    return {
        "kind": "scalar",
        "type": "string",
    }


def _generated_surface_workflow(
    tmp_path: Path,
    *,
    generated_target: bool,
    include_state_layout_allocations: bool = False,
    renderer_schema_version: int = VIEW_RENDERER_SCHEMA_VERSION,
) -> SurfaceWorkflow:
    target_path = (
        "state/materialized-views/generated-summary.json"
        if generated_target
        else "artifacts/work/materialized-summary.json"
    )
    generated_path_allocations = ()
    allocation_id = None
    if include_state_layout_allocations or generated_target:
        allocation = StateLayout.allocate(
            GeneratedPathAllocationRequest(
                owner="workflow_lisp",
                workflow_name="materialize-view-runtime",
                semantic_role=GeneratedPathSemanticRole.MATERIALIZED_VALUE_VIEW,
                privacy=(
                    GeneratedPathPrivacy.COMPATIBILITY_VIEW
                    if generated_target
                    else GeneratedPathPrivacy.PUBLIC_ARTIFACT
                ),
                resume_scope=GeneratedPathResumeScope.NONE,
                stable_identity="materialize-view-runtime/summary",
                projection_hints={"path_template": target_path},
            )
        )
        generated_path_allocations = (allocation,)
        allocation_id = allocation.allocation_id

    step = SurfaceStep(
        name="MaterializeView",
        step_id="materialize_view",
        kind=SurfaceStepKind.MATERIALIZE_VIEW,
        common=SurfaceStepCommonConfig(),
        materialize_view={
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "view_renderer_schema_version": renderer_schema_version,
            "value_type": _materialized_value_type(),
            "value_document": {
                "status": MaterializeViewBindingReference(ref="inputs.status"),
                "run_state_path": MaterializeViewBindingReference(ref="inputs.run_state_path"),
            },
            "target_path": target_path,
            "target_allocation_id": allocation_id,
            "authority_class": "materialized_view",
            "output_contracts": {
                "return": _path_contract(under="state" if generated_target else "artifacts/work"),
            },
        },
    )
    return SurfaceWorkflow(
        version="2.14",
        name="materialize-view-runtime",
        steps=(step,),
        provenance=WorkflowProvenance(
            workflow_path=tmp_path / "generated.yaml",
            source_root=tmp_path,
            generated_path_allocations=generated_path_allocations,
        ),
        inputs={
            "status": SurfaceContract(
                name="status",
                kind="scalar",
                value_type="string",
                definition=_string_contract(),
            ),
            "run_state_path": SurfaceContract(
                name="run_state_path",
                kind="relpath",
                value_type="relpath",
                definition=_path_contract(under="state"),
            ),
        },
    )


def test_generated_materialize_view_step_serializes_into_core_ast(tmp_path: Path) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    core_ast = build_core_workflow_ast(workflow, imports={}, provenance=workflow.provenance)
    core_ast_json = workflow_core_ast_to_json(core_ast)

    assert core_ast.body[0].materialize_view["renderer_id"] == "canonical-json"
    assert core_ast_json["body"][0]["kind"] == "materialize_view"
