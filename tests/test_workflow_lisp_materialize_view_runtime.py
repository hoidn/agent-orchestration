from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.core_ast import build_core_workflow_ast, workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.lowering import build_loaded_workflow_bundle, lower_surface_workflow
from orchestrator.workflow.references import MaterializeViewBindingReference
from orchestrator.workflow.runtime_step import RuntimeStep
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
from orchestrator.workflow.view_renderer import VIEW_RENDERER_SCHEMA_VERSION, view_bytes_digest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint

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


def _resume_failed_single_step(state_manager: StateManager, *, step_name: str) -> None:
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {step_name: {"status": "failed", "exit_code": 1}}
    state_manager._write_state()


def _write_authored_materialize_view_workflow(workspace: Path) -> Path:
    payload = {
        "version": "2.14",
        "name": "materialize-view-runtime",
        "steps": [
            {
                "name": "MaterializeView",
                "id": "materialize_view",
                "materialize_view": {
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
                    "value_type": _materialized_value_type(),
                    "value_document": {
                        "status": {"ref": "inputs.status"},
                        "run_state_path": {"ref": "inputs.run_state_path"},
                    },
                    "target_path": "artifacts/work/materialized-summary.json",
                    "target_allocation_id": None,
                    "authority_class": "materialized_view",
                    "output_contracts": {
                        "return": _path_contract(under="artifacts/work"),
                    },
                },
            }
        ],
    }
    workflow_path = workspace / "workflow.yaml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return workflow_path


def _compile_materialize_view_bundle(fixture_path: Path, tmp_path: Path):
    result = compile_stage3_entrypoint(
        fixture_path,
        source_roots=(fixture_path.parent,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    module_name = f"{fixture_path.stem}::orchestrate"
    return result.validated_bundles_by_name[module_name]


def _compile_entry_publication_bundle(tmp_path: Path, workflow_name: str):
    result = compile_stage3_entrypoint(
        ENTRY_PUBLICATION_RUNTIME,
        source_roots=(ENTRY_PUBLICATION_RUNTIME.parent,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name[f"entry_publication_runtime::{workflow_name}"]


def _compile_single_ref_field_materialize_view_bundle(tmp_path: Path):
    module_path = tmp_path / "materialize_view_single_ref_field.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule materialize_view_single_ref_field)",
                "  (export orchestrate)",
                "  (defpath SummaryPath",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord OnlyRef",
                "    (ref String))",
                "  (defrecord Output",
                "    (summary_path SummaryPath))",
                "  (defworkflow orchestrate",
                "    ((target_path SummaryPath))",
                "    -> Output",
                "    (let* ((summary_path",
                "             (materialize-view runtime-summary",
                "               :value (record OnlyRef",
                '                        :ref "literal-string")',
                "               :renderer canonical-json",
                "               :renderer-version 1",
                "               :target target_path",
                "               :returns SummaryPath)))",
                "      (record Output",
                "        :summary_path summary_path))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["materialize_view_single_ref_field::orchestrate"]


def test_generated_materialize_view_step_serializes_into_core_ast(tmp_path: Path) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    core_ast = build_core_workflow_ast(workflow, imports={}, provenance=workflow.provenance)
    executable, _projection = lower_surface_workflow(workflow)
    node = next(iter(executable.nodes.values()))
    runtime_step = RuntimeStep(node=node, name="MaterializeView", step_id="materialize_view")
    core_ast_json = workflow_core_ast_to_json(core_ast)

    assert node.kind is ExecutableNodeKind.MATERIALIZE_VIEW
    assert runtime_step["materialize_view"]["renderer_id"] == "canonical-json"
    assert core_ast_json["body"][0]["kind"] == "materialize_view"


def test_generated_materialize_view_bundle_emits_semantic_effect_and_state_layout_roles(
    tmp_path: Path,
) -> None:
    workflow = _generated_surface_workflow(
        tmp_path,
        generated_target=True,
        include_state_layout_allocations=True,
    )
    bundle = build_loaded_workflow_bundle(workflow, imports={})

    effect = next(
        entry
        for entry in bundle.semantic_ir.effects.values()
        if entry.effect_kind == "materialize_view"
    )
    layout_kinds = {
        entry.layout_kind
        for entry in bundle.semantic_ir.state_layout.values()
    }

    assert effect.details["renderer_id"] == "canonical-json"
    assert effect.details["renderer_version"] == 1
    assert effect.details["authority_class"] == "materialized_view"
    assert "materialized_value_view" in layout_kinds


def test_loader_rejects_authored_materialize_view_step(tmp_path: Path) -> None:
    workflow_file = _write_authored_materialize_view_workflow(tmp_path)

    with pytest.raises(WorkflowValidationError) as excinfo:
        WorkflowLoader(tmp_path).load_bundle(workflow_file)

    assert "materialize_view is compiler-generated only" in str(excinfo.value)


def test_compile_stage3_entrypoint_emits_visible_materialize_view_step(tmp_path: Path) -> None:
    bundle = _compile_materialize_view_bundle(MATERIALIZE_VIEW_RUNTIME, tmp_path)

    assert [step.kind.value for step in bundle.surface.steps] == ["materialize_view"]
    assert bundle.surface.steps[0].materialize_view["renderer_id"] == "canonical-json"
    assert bundle.surface.steps[0].materialize_view["target_path"] == {"ref": "inputs.target_path"}


def test_compile_stage3_entrypoint_allocates_generated_materialize_view_target(tmp_path: Path) -> None:
    bundle = _compile_materialize_view_bundle(MATERIALIZE_VIEW_ALLOCATED_TARGET, tmp_path)
    step = bundle.surface.steps[0]
    generated_allocations = bundle.surface.provenance.generated_path_allocations

    assert step.kind.value == "materialize_view"
    assert isinstance(step.materialize_view["target_path"], str)
    assert isinstance(step.materialize_view["target_allocation_id"], str)
    assert any(
        allocation.semantic_role.value == "materialized_value_view"
        for allocation in generated_allocations
    )


@pytest.mark.parametrize(
    ("generated_target", "expected_target"),
    [
        (False, "artifacts/work/materialized-summary.json"),
        (True, "state/materialized-views/generated-summary.json"),
    ],
)
def test_executor_runs_generated_materialize_view_step(
    tmp_path: Path,
    *,
    generated_target: bool,
    expected_target: str,
) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=generated_target)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id=f"materialize-view-{generated_target}")
    state_manager.initialize(
        "generated.yaml",
        bound_inputs={
            "status": "BLOCKED",
            "run_state_path": "state/run-state.json",
        },
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    step_result = state["steps"]["MaterializeView"]
    target_path = tmp_path / expected_target
    rendered = target_path.read_bytes()

    assert state["status"] == "completed"
    assert step_result["status"] == "completed"
    assert step_result["artifacts"]["return"] == expected_target
    assert rendered == b'{"run_state_path":"state/run-state.json","status":"BLOCKED"}\n'
    assert step_result["debug"]["materialize_view"]["reused_view"] is False
    assert step_result["debug"]["materialize_view"]["target_path"] == expected_target
    assert step_result["debug"]["materialize_view"]["view_digest"] == view_bytes_digest(rendered)


def test_authored_materialize_view_runtime_renders_authored_target(tmp_path: Path) -> None:
    bundle = _compile_materialize_view_bundle(MATERIALIZE_VIEW_RUNTIME, tmp_path)
    step_name = bundle.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-authored-target")
    state_manager.initialize(
        str(MATERIALIZE_VIEW_RUNTIME),
        bound_inputs={
            "status": "BLOCKED",
            "run_state_path": "state/run-state.json",
            "target_path": "artifacts/work/materialized-summary.json",
        },
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    rendered_path = tmp_path / "artifacts/work/materialized-summary.json"

    assert result["status"] == "completed"
    assert result["steps"][step_name]["artifacts"] == {
        "return": "artifacts/work/materialized-summary.json"
    }
    assert rendered_path.read_bytes() == b'{"run_state_path":"state/run-state.json","status":"BLOCKED"}\n'


def test_authored_materialize_view_runtime_renders_allocated_target(tmp_path: Path) -> None:
    bundle = _compile_materialize_view_bundle(MATERIALIZE_VIEW_ALLOCATED_TARGET, tmp_path)
    step = bundle.surface.steps[0]
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-generated-target")
    state_manager.initialize(
        str(MATERIALIZE_VIEW_ALLOCATED_TARGET),
        bound_inputs={
            "status": "DONE",
            "run_state_path": "state/final-run-state.json",
        },
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    target_path = result["steps"][step.name]["artifacts"]["return"]

    assert result["status"] == "completed"
    assert target_path.startswith("state/workflow_lisp_views/materialize-view-allocated-target")
    assert target_path.endswith("/generated-summary.json")
    assert (tmp_path / target_path).read_bytes() == (
        b'{"run_state_path":"state/final-run-state.json","status":"DONE"}\n'
    )


def test_authored_materialize_view_runtime_preserves_literal_ref_field_data(tmp_path: Path) -> None:
    bundle = _compile_single_ref_field_materialize_view_bundle(tmp_path)
    step_name = bundle.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-ref-field")
    state_manager.initialize(
        "materialize_view_single_ref_field.orc",
        bound_inputs={"target_path": "artifacts/work/only-ref.json"},
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    rendered_path = tmp_path / "artifacts/work/only-ref.json"

    assert result["status"] == "completed"
    assert result["steps"][step_name]["artifacts"] == {
        "return": "artifacts/work/only-ref.json"
    }
    assert rendered_path.read_bytes() == b'{"ref":"literal-string"}\n'


def test_entry_publication_runtime_writes_published_variant_without_observability_summary(
    tmp_path: Path,
) -> None:
    bundle = _compile_entry_publication_bundle(tmp_path, "entry-publication-runtime")
    state_manager = StateManager(workspace=tmp_path, run_id="entry-publication-done")
    state_manager.initialize(
        str(ENTRY_PUBLICATION_RUNTIME.resolve()),
        bound_inputs={"selected_variant": "DONE"},
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    publication_step = next(
        step
        for step in result["steps"].values()
        if isinstance(step.get("debug", {}).get("materialize_view"), dict)
    )
    target_path = publication_step["artifacts"]["return"]

    assert result["status"] == "completed"
    assert target_path.endswith("done-drain-summary.json")
    assert (tmp_path / target_path).read_bytes() == (
        b'{"message":"published-done","variant":"DONE"}\n'
    )
    assert not list(tmp_path.rglob("observability_summary_report.json"))


def test_entry_publication_runtime_omitted_variant_writes_nothing(
    tmp_path: Path,
) -> None:
    bundle = _compile_entry_publication_bundle(tmp_path, "entry-publication-runtime")
    state_manager = StateManager(workspace=tmp_path, run_id="entry-publication-skipped")
    state_manager.initialize(
        str(ENTRY_PUBLICATION_RUNTIME.resolve()),
        bound_inputs={"selected_variant": "SKIPPED"},
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert result["status"] == "completed"
    assert not any(
        isinstance(step.get("debug", {}).get("materialize_view"), dict)
        for step in result["steps"].values()
    )
    publication_root = (
        tmp_path
        / "artifacts"
        / "work"
        / "workflow_lisp_entry_publication"
        / "entry-publication-runtime--entry-publication-runtime"
    )
    assert not publication_root.exists()


def test_nested_entry_publication_call_does_not_write_publication_artifact(
    tmp_path: Path,
) -> None:
    bundle = _compile_entry_publication_bundle(tmp_path, "call-entry-publication-runtime")
    state_manager = StateManager(workspace=tmp_path, run_id="entry-publication-nested-call")
    state_manager.initialize(
        str(ENTRY_PUBLICATION_RUNTIME.resolve()),
        bound_inputs={"selected_variant": "DONE"},
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    publication_root = (
        tmp_path
        / "artifacts"
        / "work"
        / "workflow_lisp_entry_publication"
        / "entry-publication-runtime--entry-publication-runtime"
    )

    assert result["status"] == "completed"
    assert not publication_root.exists()


def test_entry_publication_runtime_fails_closed_when_publication_view_drifts_on_resume(
    tmp_path: Path,
) -> None:
    bundle = _compile_entry_publication_bundle(tmp_path, "entry-publication-runtime")
    state_manager = StateManager(workspace=tmp_path, run_id="entry-publication-drift")
    state_manager.initialize(
        str(ENTRY_PUBLICATION_RUNTIME.resolve()),
        bound_inputs={"selected_variant": "DONE"},
    )

    first = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    publication_step_name = next(
        step_name
        for step_name, step in first["steps"].items()
        if isinstance(step.get("debug", {}).get("materialize_view"), dict)
    )
    target_path = tmp_path / first["steps"][publication_step_name]["artifacts"]["return"]
    target_path.write_text('{"variant":"DONE","message":"tampered"}\n', encoding="utf-8")

    _resume_failed_single_step(state_manager, step_name=publication_step_name)
    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["steps"][publication_step_name]["status"] == "failed"
    assert (
        resumed["steps"][publication_step_name]["error"]["type"]
        == "materialize_view_nondeterministic_render"
    )


def test_materialize_view_runtime_reuses_committed_view_on_resume(tmp_path: Path) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-runtime")
    state_manager.initialize(
        "generated.yaml",
        bound_inputs={"status": "DONE", "run_state_path": "state/final-run-state.json"},
    )

    first = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    _resume_failed_single_step(state_manager, step_name="MaterializeView")
    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert first["steps"]["MaterializeView"]["debug"]["materialize_view"]["reused_view"] is False
    assert resumed["steps"]["MaterializeView"]["artifacts"] == {
        "return": "artifacts/work/materialized-summary.json"
    }
    assert resumed["steps"]["MaterializeView"]["debug"]["materialize_view"]["reused_view"] is True


def test_materialize_view_runtime_fails_closed_when_rendered_bytes_drift_for_same_evidence_key(
    tmp_path: Path,
) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-drift")
    state_manager.initialize(
        "generated.yaml",
        bound_inputs={"status": "DONE", "run_state_path": "state/final-run-state.json"},
    )

    WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    target_path = tmp_path / "artifacts/work/materialized-summary.json"
    target_path.write_text('{"status":"tampered"}\n', encoding="utf-8")

    _resume_failed_single_step(state_manager, step_name="MaterializeView")
    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["steps"]["MaterializeView"]["status"] == "failed"
    assert resumed["steps"]["MaterializeView"]["error"]["type"] == "materialize_view_nondeterministic_render"


def test_materialize_view_runtime_fails_closed_when_resume_schema_changes(tmp_path: Path) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-schema")
    state_manager.initialize(
        "generated.yaml",
        bound_inputs={"status": "DONE", "run_state_path": "state/final-run-state.json"},
    )

    first = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    evidence_path = tmp_path / first["steps"]["MaterializeView"]["debug"]["materialize_view"]["evidence_path"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["view_renderer_schema_version"] = 999
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _resume_failed_single_step(state_manager, step_name="MaterializeView")
    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["steps"]["MaterializeView"]["status"] == "failed"
    assert resumed["steps"]["MaterializeView"]["error"]["type"] == "materialize_view_resume_schema_mismatch"


def test_materialize_view_runtime_preserves_atomic_commit_when_rename_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-atomic")
    state_manager.initialize(
        "generated.yaml",
        bound_inputs={"status": "DONE", "run_state_path": "state/final-run-state.json"},
    )
    target_path = tmp_path / "artifacts/work/materialized-summary.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("old\n", encoding="utf-8")

    def _boom(_src: str, _dst: str) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr("orchestrator.workflow.executor.os.replace", _boom)
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    runtime_step = executor._runtime_step_by_name("MaterializeView")
    assert runtime_step is not None
    result = executor._execute_materialize_view(
        runtime_step.to_compat_dict(),
        state_manager.state.to_dict() if state_manager.state is not None else {},
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "materialize_view_render_failed"
    assert target_path.read_text(encoding="utf-8") == "old\n"
    assert not list(target_path.parent.glob(".materialized-summary.json.tmp-*"))


def test_materialize_view_runtime_preserves_atomic_commit_when_evidence_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _generated_surface_workflow(tmp_path, generated_target=False)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-evidence-atomic")
    state_manager.initialize(
        "generated.yaml",
        bound_inputs={"status": "DONE", "run_state_path": "state/final-run-state.json"},
    )
    target_path = tmp_path / "artifacts/work/materialized-summary.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("old\n", encoding="utf-8")
    evidence_path = tmp_path / "artifacts/work/.materialized-summary.json.materialize-view-evidence.json"
    original_atomic_write_bytes = WorkflowExecutor._atomic_write_bytes

    def _fail_evidence_write(self: WorkflowExecutor, path: Path, content: bytes) -> None:
        if path == evidence_path:
            raise OSError("evidence write failed")
        original_atomic_write_bytes(self, path, content)

    monkeypatch.setattr(WorkflowExecutor, "_atomic_write_bytes", _fail_evidence_write)
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    runtime_step = executor._runtime_step_by_name("MaterializeView")
    assert runtime_step is not None
    result = executor._execute_materialize_view(
        runtime_step.to_compat_dict(),
        state_manager.state.to_dict() if state_manager.state is not None else {},
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "materialize_view_render_failed"
    assert target_path.read_text(encoding="utf-8") == "old\n"
    assert not evidence_path.exists()
