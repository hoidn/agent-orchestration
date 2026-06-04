from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.diagnostics import serialize_diagnostic
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_RESOURCE_TRANSITION_EFFECTS_FIXTURE = FIXTURES / "valid" / "resource_transition_effects.orc"
VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE = FIXTURES / "valid" / "phase_snapshot_effects.orc"
VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE = FIXTURES / "valid" / "pointer_materialization_effects.orc"
VALID_LET_PROC_FIXTURE = FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc"
VALID_MACRO_ALIAS_FIXTURE = FIXTURES / "valid" / "macro_workflow_alias.orc"


def _compile(path: Path, *, tmp_path: Path, validate_shared: bool = False):
    return compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _build_source_map_document(
    path: Path,
    *,
    tmp_path: Path,
    selected_name: str,
    validate_shared: bool = False,
):
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    compile_result = _compile(path, tmp_path=tmp_path, validate_shared=validate_shared)
    canonical_name = next(
        workflow.definition.name
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == selected_name or workflow.definition.name.endswith(f"::{selected_name}")
    )
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name={"__main__": compile_result},
            validated_bundles_by_name=compile_result.validated_bundles,
        ),
        selected_name=canonical_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    return source_map_module, document, canonical_name


def _write_parametric_source_map_module(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/module)",
                "  (export entry)",
                "  (defrecord WorkflowInput",
                "    (report String))",
                "  (defproc apply-runner",
                "    :forall (T)",
                "    ((runner ProcRef[T -> T])",
                "     (value T))",
                "    -> T",
                "    :effects ()",
                "    :lowering inline",
                "    (runner value))",
                "  (defproc echo-input",
                "    ((value WorkflowInput))",
                "    -> WorkflowInput",
                "    :effects ()",
                "    :lowering inline",
                "    (record WorkflowInput",
                "      :report value.report))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowInput",
                "    (apply-runner (proc-ref echo-input) input)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _walk_steps(raw_steps: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_steps, list):
        return ()
    steps: list[dict[str, object]] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        steps.append(step)
        match = step.get("match")
        if isinstance(match, dict):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, dict):
                    steps.extend(_walk_steps(case.get("steps")))
    return tuple(steps)


def test_command_boundary_lineage_persists_declared_effects(tmp_path: Path) -> None:
    _, document, workflow_name = _build_source_map_document(
        VALID_RESOURCE_TRANSITION_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        selected_name="move-selected-item",
    )
    workflow = document.workflows[workflow_name]
    boundary = workflow.command_boundaries[0]

    assert boundary.boundary_kind == "certified_adapter"
    assert boundary.command_name == "apply_resource_transition"
    assert boundary.declared_effects == ("resource_transition", "ledger_update")


def test_generated_semantic_effects_emit_snapshot_and_pointer_lineage(tmp_path: Path) -> None:
    _, document, workflow_name = _build_source_map_document(
        VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        selected_name="orchestrate",
    )
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    workflow = document.workflows[workflow_name]
    payload = build_module._json_data(document)

    assert "generated_semantic_effects" in payload["workflows"][workflow_name]
    assert any(effect.effect_kind == "snapshot_capture" for effect in workflow.generated_semantic_effects)
    assert any(effect.effect_kind == "pointer_materialization" for effect in workflow.generated_semantic_effects)
    assert any(effect.effect_key.startswith("snapshot:") for effect in workflow.generated_semantic_effects)
    assert any(effect.effect_key.startswith("pointer:") for effect in workflow.generated_semantic_effects)
    assert any(
        effect.details["snapshot_kind"].endswith("_before")
        for effect in workflow.generated_semantic_effects
        if effect.effect_kind == "snapshot_capture"
    )
    assert any(
        "pointer_path" in effect.details
        for effect in workflow.generated_semantic_effects
        if effect.effect_kind == "pointer_materialization"
    )


def test_materialize_without_pointer_path_does_not_emit_pointer_lineage(tmp_path: Path) -> None:
    _, document, workflow_name = _build_source_map_document(
        VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        selected_name="orchestrate",
    )
    compile_result = _compile(VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE, tmp_path=tmp_path)
    workflow = document.workflows[workflow_name]
    lowered = next(
        lowered_workflow
        for lowered_workflow in compile_result.lowered_workflows
        if lowered_workflow.typed_workflow.definition.name == workflow_name
    )
    pointer_keys = {
        effect.effect_key
        for effect in workflow.generated_semantic_effects
        if effect.effect_kind == "pointer_materialization"
    }

    plain_value_names = {
        value["name"]
        for step in _walk_steps(lowered.authored_mapping["steps"])
        if "materialize_artifacts" in step
        for value in step["materialize_artifacts"]["values"]
        if "pointer" not in value
    }

    assert plain_value_names
    assert all(
        f"pointer:materialize_shared_fields:{value_name}" not in pointer_keys
        for value_name in plain_value_names
    )


def test_source_map_validator_rejects_invalid_generated_semantic_effect_lineage(tmp_path: Path) -> None:
    source_map_module, document, workflow_name = _build_source_map_document(
        VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        selected_name="orchestrate",
    )
    workflow = document.workflows[workflow_name]
    broken_effect = getattr(source_map_module, "GeneratedSemanticEffectLineage")(
        effect_key="pointer:missing-step:selected_item_summary",
        step_id="missing_step",
        effect_kind="pointer_materialization",
        origin_key=f"{workflow_name}::generated_path::state/missing.json",
        details={"pointer_path": "state/missing.json", "representation_role": "artifact_pointer"},
    )
    broken_document = replace(
        document,
        workflows={
            **dict(document.workflows),
            workflow_name: replace(
                workflow,
                generated_semantic_effects=workflow.generated_semantic_effects + (broken_effect,),
            ),
        },
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        source_map_module.validate_source_map_document(broken_document)

    assert excinfo.value.diagnostics[0].code == "source_map_generated_effect_invalid"


def test_source_map_records_let_proc_authored_lineage(tmp_path: Path) -> None:
    _, document, workflow_name = _build_source_map_document(
        VALID_LET_PROC_FIXTURE,
        tmp_path=tmp_path,
        selected_name="entry",
    )
    workflow = document.workflows[workflow_name]

    assert any(
        "let-proc" in note
        for entry in workflow.step_ids.values()
        for note in entry.notes
    )


def test_source_map_records_parametric_specialization_authored_lineage(tmp_path: Path) -> None:
    path = _write_parametric_source_map_module(tmp_path / "demo" / "module.orc")
    _, document, workflow_name = _build_source_map_document(
        path,
        tmp_path=tmp_path,
        selected_name="entry",
    )
    workflow = document.workflows[workflow_name]
    notes = [
        note
        for entry in workflow.step_ids.values()
        for note in entry.notes
    ]

    assert any("parametric specialization selected for `apply-runner`" in note for note in notes)
    assert any("T = WorkflowInput" in note for note in notes)


def test_source_map_validator_preserves_macro_origin_ownership_for_unmapped_executable_nodes(
    tmp_path: Path,
) -> None:
    source_map_module, document, workflow_name = _build_source_map_document(
        VALID_MACRO_ALIAS_FIXTURE,
        tmp_path=tmp_path,
        selected_name="command_checks",
        validate_shared=True,
    )
    workflow = document.workflows[workflow_name]
    assert workflow.executable_nodes
    broken_node = replace(workflow.executable_nodes[0], origin_key="missing-origin")
    broken_document = replace(
        document,
        workflows={
            **dict(document.workflows),
            workflow_name: replace(
                workflow,
                executable_nodes=(broken_node,) + workflow.executable_nodes[1:],
            ),
        },
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        source_map_module.validate_source_map_document(broken_document)

    diagnostic = excinfo.value.diagnostics[0]
    payload = serialize_diagnostic(diagnostic)
    assert diagnostic.code == "source_map_executable_node_unmapped"
    assert diagnostic.span.start.path.endswith("tests/fixtures/workflow_lisp/valid/macro_workflow_alias.orc")
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "defworkflow-alias"
    assert payload["code"] == "source_map_executable_node_unmapped"
    assert payload["validation_pass"] == "source_map"
    assert payload["authority_layer"] == "frontend"
