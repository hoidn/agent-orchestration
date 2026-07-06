from __future__ import annotations

import importlib
import json
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.diagnostics import serialize_diagnostic
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_lisp_command_boundaries import (
    run_neurips_backlog_checks_binding,
    validate_review_findings_v1_binding,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_RESOURCE_TRANSITION_EFFECTS_FIXTURE = FIXTURES / "valid" / "resource_transition_effects.orc"
VALID_PHASE_SNAPSHOT_EFFECTS_FIXTURE = FIXTURES / "valid" / "phase_snapshot_effects.orc"
VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE = FIXTURES / "valid" / "pointer_materialization_effects.orc"
VALID_LET_PROC_FIXTURE = FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc"
VALID_MACRO_ALIAS_FIXTURE = FIXTURES / "valid" / "macro_workflow_alias.orc"
IMPORTED_STDLIB_HELPER_ROOT = FIXTURES / "modules" / "valid" / "imported_stdlib_macro_payload_helper_composition"
IMPORTED_STDLIB_HELPER_ENTRY = (
    IMPORTED_STDLIB_HELPER_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)
IMPORTED_STDLIB_HELPER_MODULE = (
    IMPORTED_STDLIB_HELPER_ROOT / "imported_stdlib_macro_payload_helper_composition" / "std_payload_helpers.orc"
)
LEXICAL_CHECKPOINT_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_shadow_points.orc"
LEXICAL_POLICY_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_effect_policies.orc"
DESIGN_DELTA_PARENT_DRAIN_COMMANDS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)


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
        lowering_route="legacy",
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


def _build_entrypoint_source_map_document(
    path: Path,
    *,
    tmp_path: Path,
    selected_name: str,
    extra_source_roots: tuple[Path, ...] = (),
    validate_shared: bool = False,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    if module_match is None:
        module_name = f"test/{path.stem}"
        source = source.replace(
            '  (:target-dsl "2.14")\n',
            f'  (:target-dsl "2.14")\n  (defmodule {module_name})\n  (export {selected_name})\n',
            1,
        )
    else:
        module_name = module_match.group(1)
    module_path = (tmp_path / Path(*module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(*extra_source_roots, tmp_path),
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
            "prompts.implementation.review": "tests/fixtures/workflow_lisp/valid/prompts/implementation/review.md",
            "prompts.implementation.fix": "tests/fixtures/workflow_lisp/valid/prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "validate_review_findings_v1": validate_review_findings_v1_binding(),
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )
    workflow_name = next(
        name
        for name in result.validated_bundles_by_name
        if name == selected_name or name.endswith(f"::{selected_name}")
    )
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name=result.compiled_results_by_name,
            validated_bundles_by_name=result.validated_bundles_by_name,
        ),
        selected_name=workflow_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    return source_map_module, document, workflow_name


def _build_design_delta_implementation_phase_source_map_document(
    tmp_path: Path,
):
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "implementation_phase.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={
            "providers.implementation.execute": "fake-execute",
            "providers.implementation.review": "fake-review",
            "providers.implementation.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md"
            ),
            "prompts.implementation.review": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md"
            ),
            "prompts.implementation.fix": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
            ),
        },
        command_boundaries={
            "run_neurips_backlog_checks": run_neurips_backlog_checks_binding(),
            "validate_review_findings_v1": validate_review_findings_v1_binding(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    workflow_name = "lisp_frontend_design_delta/implementation_phase::implementation-phase"
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name=result.compiled_results_by_name,
            validated_bundles_by_name=result.validated_bundles_by_name,
        ),
        selected_name=workflow_name,
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )
    return document, workflow_name


def _design_delta_work_item_provider_externs() -> dict[str, str]:
    return {
        "providers.plan.draft": "fake-plan-draft",
        "providers.plan.review": "fake-plan-review",
        "providers.plan.fix": "fake-plan-fix",
        "providers.architect.draft": "fake-architect-draft",
        "providers.implementation.execute": "fake-implementation-execute",
        "providers.implementation.review": "fake-implementation-review",
        "providers.implementation.fix": "fake-implementation-fix",
        "providers.selector": "fake-selector",
        "providers.work-item.recovery-classifier": "fake-work-item-recovery",
    }


def _design_delta_work_item_prompt_externs() -> dict[str, object]:
    return {
        "prompts.plan.draft": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
        },
        "prompts.plan.review": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
        },
        "prompts.plan.fix": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
        },
        "prompts.implementation.execute": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md"
            )
        },
        "prompts.implementation.review": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md"
            )
        },
        "prompts.implementation.fix": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
            )
        },
        "prompts.work-item.classify-blocked-recovery": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
                "classify_blocked_implementation_recovery.md"
            )
        },
        "prompts.selector.select-next-work": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            )
        },
        "prompts.architect.draft": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_design_gap_architect/"
                "draft_implementation_architecture.md"
            )
        },
    }


def _build_design_delta_work_item_source_map_document(
    tmp_path: Path,
    *,
    validate_shared: bool,
):
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=_design_delta_work_item_provider_externs(),
        prompt_externs=_design_delta_work_item_prompt_externs(),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8")),
            manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
        ),
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )
    workflow_name = "lisp_frontend_design_delta/work_item::run-work-item"
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name=result.compiled_results_by_name,
            validated_bundles_by_name=result.validated_bundles_by_name,
        ),
        selected_name=workflow_name,
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )
    return document, workflow_name


def _build_imported_stdlib_helper_source_map_document(tmp_path: Path):
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    result = compile_stage3_entrypoint(
        IMPORTED_STDLIB_HELPER_ENTRY,
        source_roots=(IMPORTED_STDLIB_HELPER_ROOT,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    workflow_name = "imported_stdlib_macro_payload_helper_composition/entry::run-drain-like"
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name=result.compiled_results_by_name,
            validated_bundles_by_name=result.validated_bundles_by_name,
        ),
        selected_name=workflow_name,
        display_name_resolver=lambda name: name,
    )
    return document, workflow_name


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


def _source_map_payload(document) -> dict[str, object]:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    return build_module._json_data(document)


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


def test_generated_path_allocations_map_to_frontend_origins(tmp_path: Path) -> None:
    _, document, workflow_name = _build_source_map_document(
        VALID_POINTER_MATERIALIZATION_EFFECTS_FIXTURE,
        tmp_path=tmp_path,
        selected_name="orchestrate",
    )
    payload = _source_map_payload(document)
    workflow = payload["workflows"][workflow_name]
    allocations = workflow["generated_path_allocations"]
    allocation = next(
        item for item in allocations if item["semantic_role"] == "materialized_value_view"
    )

    assert allocation["origin_key"] == workflow["generated_paths"][allocation["concrete_path_template"]]["origin_key"]
    assert allocation["path_safety_policy"] == "workspace_relative"


def test_formatting_only_source_changes_preserve_allocation_identity(tmp_path: Path) -> None:
    original_path = tmp_path / "alloc" / "formatting_original.orc"
    formatted_path = tmp_path / "alloc" / "formatting_formatted.orc"
    original_source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule alloc/formatting)",
            "  (export command-checks)",
            "  (defpath WorkReport",
            '    :kind relpath',
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (status String)",
            "    (report WorkReport))",
            "  (defworkflow command-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" report_path)',
            "      :returns ChecksResult)))",
            "",
        ]
    )
    formatted_source = original_source.replace(
        "    (command-result run_checks\n",
        "    \n    (command-result run_checks\n",
        1,
    )
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_text(original_source, encoding="utf-8")
    formatted_path.write_text(formatted_source, encoding="utf-8")

    _, original_document, original_workflow_name = _build_source_map_document(
        original_path,
        tmp_path=tmp_path,
        selected_name="command-checks",
    )
    _, formatted_document, formatted_workflow_name = _build_source_map_document(
        formatted_path,
        tmp_path=tmp_path,
        selected_name="command-checks",
    )
    original_payload = _source_map_payload(original_document)
    formatted_payload = _source_map_payload(formatted_document)
    original_allocations = original_payload["workflows"][original_workflow_name]["generated_path_allocations"]
    formatted_allocations = formatted_payload["workflows"][formatted_workflow_name]["generated_path_allocations"]

    assert {
        (allocation["semantic_role"], allocation["stable_identity"])
        for allocation in original_allocations
    } == {
        (allocation["semantic_role"], allocation["stable_identity"])
        for allocation in formatted_allocations
    }


def test_source_map_records_nested_scope_projection_lineage(tmp_path: Path) -> None:
    _, document, workflow_name = _build_entrypoint_source_map_document(
        Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_implementation_phase.orc"),
        tmp_path=tmp_path,
        selected_name="implementation-phase",
        validate_shared=True,
    )
    workflow = document.workflows[workflow_name]

    assert workflow.step_ids
    assert workflow.executable_nodes


def test_source_map_records_generated_paths_inside_nested_branch_scopes(tmp_path: Path) -> None:
    _, document, workflow_name = _build_entrypoint_source_map_document(
        Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_implementation_phase.orc"),
        tmp_path=tmp_path,
        selected_name="implementation-phase",
        validate_shared=True,
    )
    workflow = document.workflows[workflow_name]

    assert workflow.generated_paths


def test_source_map_records_design_delta_implementation_phase_lineage(tmp_path: Path) -> None:
    document, workflow_name = _build_design_delta_implementation_phase_source_map_document(tmp_path)
    workflow = document.workflows[workflow_name]

    assert workflow.step_ids
    assert workflow.executable_nodes
    assert workflow.generated_paths


def test_source_map_no_bundle_finalize_selected_item_resource_transition_regression(
    tmp_path: Path,
) -> None:
    document, _ = _build_design_delta_work_item_source_map_document(
        tmp_path,
        validate_shared=False,
    )
    payload = _source_map_payload(document)
    work_item_path = REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc"
    std_resource_path = REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "resource.orc"
    matching_rows_by_workflow = {
        workflow_name: [
            node
            for node in workflow["core_nodes"]
            # Imported finalize proc lowering emits helper `match`/materialization
            # nodes plus the transition site itself on `__outcome`.
            if "std_resource_finalize_selected_item_proc_" in node["step_id"]
            and node["step_id"].endswith("__outcome")
        ]
        for workflow_name, workflow in payload["workflows"].items()
    }
    matching_rows_by_workflow = {
        workflow_name: rows
        for workflow_name, rows in matching_rows_by_workflow.items()
        if rows
    }

    assert set(matching_rows_by_workflow) == {
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation",
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation",
    }
    assert all(
        Path(payload["workflows"][workflow_name]["workflow_origin"]["path"]) == work_item_path
        for workflow_name in matching_rows_by_workflow
    )
    assert any(
        "std_resource_finalize_selected_item_proc_" in row["step_id"]
        for rows in matching_rows_by_workflow.values()
        for row in rows
    )
    assert all(
        Path(payload["workflows"][workflow_name]["step_ids"][row["step_id"]]["path"]) == std_resource_path
        for workflow_name, rows in matching_rows_by_workflow.items()
        for row in rows
    )
    assert all(
        row["step_kind"] == "resource_transition"
        for rows in matching_rows_by_workflow.values()
        for row in rows
    )
    assert all(
        row["step_kind"] != "step"
        for rows in matching_rows_by_workflow.values()
        for row in rows
    )


def test_source_map_records_imported_stdlib_macro_helper_provenance_and_lineage(
    tmp_path: Path,
) -> None:
    document, workflow_name = _build_imported_stdlib_helper_source_map_document(tmp_path)
    workflow = _source_map_payload(document)["workflows"][workflow_name]
    workflow_origin = workflow["workflow_origin"]
    expansion_frame = workflow_origin["expansion_stack"][0]
    gap_helper_step_name = next(
        step_name
        for step_name in workflow["step_ids"]
        if "selection-result-gap-payload_1__match_selection-result" in step_name
    )
    gap_helper_step = workflow["step_ids"][gap_helper_step_name]
    gap_helper_input_name = next(
        input_name
        for input_name in workflow["generated_internal_inputs"]
        if "__gap_payload__" in input_name
    )
    gap_helper_input = workflow["generated_internal_inputs"][gap_helper_input_name]

    assert Path(workflow_origin["path"]) == IMPORTED_STDLIB_HELPER_MODULE
    assert Path(expansion_frame["call_span"]["start"]["path"]) == IMPORTED_STDLIB_HELPER_ENTRY
    assert Path(expansion_frame["definition_span"]["start"]["path"]) == IMPORTED_STDLIB_HELPER_MODULE
    assert expansion_frame["macro_name"] == "emit-run-drain-like"

    assert gap_helper_step["form_path"] == [
        "workflow-lisp",
        "defproc",
        "selection-result-gap-payload",
    ]
    assert Path(gap_helper_step["path"]) == IMPORTED_STDLIB_HELPER_MODULE

    assert "__gap_payload__" in gap_helper_input["generated_name_origin"]
    assert Path(gap_helper_input["path"]) == IMPORTED_STDLIB_HELPER_MODULE
    assert gap_helper_input["form_path"] == [
        "workflow-lisp",
        "defproc",
        "selection-result-gap-payload",
    ]

    assert any(
        node["step_kind"] == "match" and "__gap_payload__" in node["step_id"]
        for node in workflow["core_nodes"]
    )
    assert any(
        node["kind"] == "match_join" and "selection-result-gap-payload" in node["origin_key"]
        for node in workflow["executable_nodes"]
    )
    assert any(
        allocation["semantic_role"] == "pure_projection_bundle"
        and "__gap_payload__" in allocation["generated_input_name"]
        for allocation in workflow["generated_path_allocations"]
    )


def test_source_map_records_generated_write_roots_across_reusable_call_boundaries(
    tmp_path: Path,
) -> None:
    _, document, workflow_name = _build_entrypoint_source_map_document(
        Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_imported_branch_effects.orc"),
        tmp_path=tmp_path,
        selected_name="entry",
        extra_source_roots=(Path("tests/fixtures/workflow_lisp/modules/valid/workflow_refs"),),
        validate_shared=True,
    )
    workflow = document.workflows[workflow_name]

    assert any("/calls/" in path for path in workflow.generated_paths)
    assert any(mapped_workflow.command_boundaries for mapped_workflow in document.workflows.values())


def test_source_map_records_branch_scoped_resume_identity_lineage(tmp_path: Path) -> None:
    _, document, workflow_name = _build_entrypoint_source_map_document(
        Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_branch_scope_collision.orc"),
        tmp_path=tmp_path,
        selected_name="entry",
        validate_shared=True,
    )
    workflow = document.workflows[workflow_name]

    assert workflow.executable_nodes


def test_source_map_keeps_lexical_checkpoint_lineage_route_neutral(tmp_path: Path) -> None:
    _, document, workflow_name = _build_entrypoint_source_map_document(
        LEXICAL_CHECKPOINT_FIXTURE,
        tmp_path=tmp_path,
        selected_name="orchestrate",
        validate_shared=True,
    )
    payload = _source_map_payload(document)
    workflow = payload["workflows"][workflow_name]
    source_map_text = json.dumps(payload, sort_keys=True).replace(str(tmp_path), "")

    assert workflow["generated_path_allocations"]
    assert "wcc_m4" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text


def test_source_map_keeps_r3_lexical_checkpoint_policy_lineage_route_neutral(tmp_path: Path) -> None:
    _, document, workflow_name = _build_entrypoint_source_map_document(
        LEXICAL_POLICY_FIXTURE,
        tmp_path=tmp_path,
        selected_name="orchestrate",
        validate_shared=True,
    )
    payload = _source_map_payload(document)
    workflow = payload["workflows"][workflow_name]
    source_map_text = json.dumps(payload, sort_keys=True).replace(str(tmp_path), "")

    assert workflow["generated_path_allocations"]
    assert "wcc_m4" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text
