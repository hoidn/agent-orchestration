from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
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
                "iteration": {"kind": "scalar", "type": "integer"},
                "write_root": {"kind": "relpath", "type": "relpath"},
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


def _write_semantic_ir_workflow(workspace: Path) -> Path:
    _write_review_loop_library(workspace)
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.7",
            "name": "semantic-ir",
            "imports": {
                "review_loop": "workflows/library/review_loop.yaml",
            },
            "providers": {
                "audit_provider": {
                    "command": ["echo", "${PROMPT}"],
                    "input_mode": "argv",
                }
            },
            "inputs": {
                "write_root": {"kind": "relpath", "type": "relpath"},
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {"ref": "root.steps.RunReview.artifacts.review_decision"},
                }
            },
            "steps": [
                {
                    "name": "RunChecks",
                    "id": "run_checks",
                    "command": ["python", "scripts/run_checks.py"],
                },
                {
                    "name": "DraftSummary",
                    "id": "draft_summary",
                    "provider": "audit_provider",
                    "input_file": "prompts/review.md",
                    "inject_output_contract": False,
                    "expected_outputs": [
                        {
                            "name": "summary_path",
                            "path": "state/summary.md",
                            "type": "relpath",
                            "under": "artifacts/work",
                        }
                    ],
                },
                {
                    "name": "RunReview",
                    "id": "run_review",
                    "call": "review_loop",
                    "with": {
                        "iteration": 1,
                        "write_root": "state/review-loop",
                    },
                },
            ],
        },
    )


def _statement_step_ids(workflow) -> list[str]:
    return [
        workflow.statements[statement_id].step_id.split(".")[-1]
        for statement_id in workflow.authored_statement_ids
    ]


def test_derive_semantic_ir_from_yaml_bundle_records_contracts_refs_effects_and_bridges(
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))

    semantic_ir = bundle.semantic_ir
    workflow = semantic_ir.workflows[bundle.surface.name]

    assert semantic_ir.schema_version == semantic_ir_module.WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION
    assert _statement_step_ids(workflow) == ["run_checks", "draft_summary", "run_review"]
    assert workflow.command_boundary_ids
    assert workflow.call_edge_ids
    assert workflow.prompt_surface_ids
    assert workflow.publication_ref_ids
    assert workflow.executable_bridge.workflow_name == bundle.surface.name
    assert set(workflow.executable_bridge.node_ids) == set(bundle.ir.nodes)
    assert set(workflow.executable_bridge.presentation_keys) == {
        node.presentation_key for node in bundle.runtime_plan.nodes.values()
    }
    assert set(workflow.call_edge_ids).issubset(set(semantic_ir.call_edges))
    assert set(workflow.prompt_surface_ids).issubset(set(semantic_ir.prompt_surfaces))
    assert set(workflow.command_boundary_ids).issubset(set(semantic_ir.command_boundaries))
    assert any(ref.ref_kind == "workflow_input" for ref in semantic_ir.refs.values())
    assert any(contract.contract_name == "write_root" for contract in semantic_ir.contracts.values())
    assert any(ref.ref_kind == "publication_plan" for ref in semantic_ir.refs.values())

    call_edge = semantic_ir.call_edges[workflow.call_edge_ids[0]]
    prompt_surface = semantic_ir.prompt_surfaces[workflow.prompt_surface_ids[0]]
    command_boundary = semantic_ir.command_boundaries[workflow.command_boundary_ids[0]]

    command_effect = next(
        effect
        for effect in semantic_ir.effects.values()
        if effect.effect_kind == "command_call"
    )
    call_effect = next(
        effect
        for effect in semantic_ir.effects.values()
        if effect.effect_kind == "workflow_call"
    )
    assert command_effect.boundary_kind == "external_tool"
    assert command_effect.boundary_name == "RunChecks"
    assert call_effect.call_target == "review_loop"
    assert call_edge.call_alias == "review_loop"
    assert prompt_surface.provider_name == "audit_provider"
    assert prompt_surface.input_file == "prompts/review.md"
    assert prompt_surface.inject_output_contract is False
    assert command_boundary.boundary_kind == "external_tool"


def test_semantic_ir_helper_returns_shared_surface_from_loaded_bundle(tmp_path: Path) -> None:
    loaded_bundle_module = importlib.import_module("orchestrator.workflow.loaded_bundle")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))

    assert loaded_bundle_module.workflow_semantic_ir(bundle) is bundle.semantic_ir
    assert loaded_bundle_module.workflow_semantic_ir(None) is None
    assert loaded_bundle_module.workflow_semantic_ir({"not": "a bundle"}) is None


def test_semantic_ir_validation_rejects_missing_executable_bridge_node(tmp_path: Path) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    exceptions_module = importlib.import_module("orchestrator.exceptions")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    statement_id = workflow.authored_statement_ids[0]
    missing_node_id = workflow.statements[statement_id].executable_node_ids[0]
    broken_bridge = replace(
        workflow.executable_bridge,
        node_ids=tuple(
            node_id
            for node_id in workflow.executable_bridge.node_ids
            if node_id != missing_node_id
        ),
    )
    broken_workflow = replace(workflow, executable_bridge=broken_bridge)
    broken_semantic_ir = replace(
        bundle.semantic_ir,
        workflows={
            **dict(bundle.semantic_ir.workflows),
            bundle.surface.name: broken_workflow,
        },
    )

    with pytest.raises(exceptions_module.WorkflowValidationError) as excinfo:
        semantic_ir_module.validate_workflow_semantic_ir(
            broken_semantic_ir,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
        )

    error = excinfo.value.errors[0]
    assert "semantic_ir_invalid" in error.message
    assert error.subject_refs
    assert error.subject_refs[0].subject_kind == "step_id"
    assert error.subject_refs[0].subject_name.endswith("run_checks")


@pytest.mark.parametrize(
    ("mutation", "expected_fragment", "expected_subject_kind", "expected_subject_name"),
    [
        (
            "input_contract",
            "input contract `write_root` references missing contract",
            "workflow",
            "semantic-ir",
        ),
        (
            "statement_ref",
            "statement `root.run_checks` references missing ref",
            "step_id",
            "run_checks",
        ),
        (
            "statement_effect",
            "statement `root.run_checks` references missing effect",
            "step_id",
            "run_checks",
        ),
        (
            "proof_ref",
            "proof `proof:semantic-ir:draft_summary` references missing ref",
            "step_id",
            "draft_summary",
        ),
        (
            "state_layout_checkpoint",
            "resume-checkpoint layout",
            "step_id",
            "run_checks",
        ),
        (
            "resume_checkpoint_bridge",
            "resume checkpoint `missing.checkpoint`",
            "step_id",
            None,
        ),
    ],
)
def test_semantic_ir_validation_rejects_missing_catalog_and_checkpoint_bridges(
    tmp_path: Path,
    mutation: str,
    expected_fragment: str,
    expected_subject_kind: str,
    expected_subject_name: str | None,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    exceptions_module = importlib.import_module("orchestrator.exceptions")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    workflows = dict(bundle.semantic_ir.workflows)
    proofs = dict(bundle.semantic_ir.proofs)
    state_layout = dict(bundle.semantic_ir.state_layout)

    if mutation == "input_contract":
        workflows[bundle.surface.name] = replace(
            workflow,
            input_contract_ids={"write_root": "contract:missing"},
        )
    elif mutation == "statement_ref":
        statement_id = workflow.authored_statement_ids[0]
        workflows[bundle.surface.name] = replace(
            workflow,
            statements={
                **dict(workflow.statements),
                statement_id: replace(
                    workflow.statements[statement_id],
                    ref_ids=("ref:missing",),
                ),
            },
        )
    elif mutation == "statement_effect":
        statement_id = workflow.authored_statement_ids[0]
        workflows[bundle.surface.name] = replace(
            workflow,
            statements={
                **dict(workflow.statements),
                statement_id: replace(
                    workflow.statements[statement_id],
                    effect_ids=("effect:missing",),
                ),
            },
        )
    elif mutation == "proof_ref":
        proof_id = "proof:semantic-ir:draft_summary"
        proofs[proof_id] = semantic_ir_module.SemanticProofEntry(
            proof_id=proof_id,
            workflow_name=bundle.surface.name,
            proof_kind="variant_surface",
            statement_id=workflow.authored_statement_ids[1],
            ref_ids=("ref:missing",),
        )
    elif mutation == "state_layout_checkpoint":
        checkpoint_layout_id = next(
            layout_id
            for layout_id, layout in state_layout.items()
            if layout.layout_kind == "resume_checkpoint"
        )
        state_layout[checkpoint_layout_id] = replace(
            state_layout[checkpoint_layout_id],
            node_id="missing.checkpoint",
        )
    elif mutation == "resume_checkpoint_bridge":
        workflows[bundle.surface.name] = replace(
            workflow,
            executable_bridge=replace(
                workflow.executable_bridge,
                resume_checkpoint_ids=("missing.checkpoint",),
            ),
        )
    else:
        raise AssertionError(f"unexpected mutation {mutation}")

    broken_semantic_ir = replace(
        bundle.semantic_ir,
        workflows=workflows,
        proofs=proofs,
        state_layout=state_layout,
    )

    with pytest.raises(exceptions_module.WorkflowValidationError) as excinfo:
        semantic_ir_module.validate_workflow_semantic_ir(
            broken_semantic_ir,
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
        )

    error = excinfo.value.errors[0]
    assert "semantic_ir_invalid" in error.message
    assert expected_fragment in error.message
    assert error.subject_refs
    assert error.subject_refs[0].subject_kind == expected_subject_kind
    if expected_subject_name is not None:
        assert error.subject_refs[0].subject_name.endswith(expected_subject_name)


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        ("missing_origin", "does not resolve to a declared source-map origin"),
        ("missing_subject", "references unsupported source-map subject"),
    ],
)
def test_derive_semantic_ir_rejects_invalid_frontend_source_map_bridges(
    tmp_path: Path,
    mutation: str,
    expected_fragment: str,
) -> None:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    exceptions_module = importlib.import_module("orchestrator.exceptions")
    request_cls = getattr(build_module, "FrontendBuildRequest")
    result = build_module.build_frontend_bundle(
        request_cls(
            source_path=Path("tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc"),
            source_roots=(Path("tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix"),),
            entry_workflow="orchestrate",
            provider_externs_path=Path("tests/fixtures/workflow_lisp/cli/providers.json"),
            prompt_externs_path=Path("tests/fixtures/workflow_lisp/cli/prompts.json"),
            imported_workflow_bundles_path=Path("tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json"),
            command_boundaries_path=Path("tests/fixtures/workflow_lisp/cli/commands.json"),
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    bundle = result.validated_bundle
    source_map_path = bundle.surface.provenance.frontend_source_trace_path
    assert isinstance(source_map_path, Path)
    source_map_payload = json.loads(source_map_path.read_text(encoding="utf-8"))
    workflow_payload = source_map_payload["workflows"][bundle.surface.name]
    bindings = workflow_payload["validation_subjects"]
    assert bindings

    if mutation == "missing_origin":
        bindings[0]["origin_key"] = "missing-origin"
    elif mutation == "missing_subject":
        bindings[0]["subject_ref"] = {
            "subject_kind": "generated_input",
            "subject_name": "missing_input",
            "workflow_name": bundle.surface.name,
        }
    else:
        raise AssertionError(f"unexpected mutation {mutation}")

    broken_source_map_path = tmp_path / "broken_source_map.json"
    broken_source_map_path.write_text(
        json.dumps(source_map_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    broken_provenance = replace(
        bundle.surface.provenance,
        frontend_source_trace_path=broken_source_map_path,
    )

    with pytest.raises(exceptions_module.WorkflowValidationError) as excinfo:
        semantic_ir_module.derive_workflow_semantic_ir(
            surface=replace(bundle.surface, provenance=broken_provenance),
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            imports=bundle.imports,
            provenance=broken_provenance,
        )

    error = excinfo.value.errors[0]
    assert "semantic_ir_invalid" in error.message
    assert expected_fragment in error.message
    assert error.subject_refs
    assert error.subject_refs[0].workflow_name == bundle.surface.name


def test_load_returns_typed_bundle_with_semantic_ir(tmp_path: Path) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    loaded = WorkflowLoader(tmp_path).load(_write_semantic_ir_workflow(tmp_path))

    assert loaded.semantic_ir.schema_version == semantic_ir_module.WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION
    assert loaded.semantic_ir.workflows[loaded.surface.name].workflow_name == loaded.surface.name


def test_compiled_bundle_semantic_ir_preserves_command_boundary_classification(tmp_path: Path) -> None:
    structured_result = compile_stage3_module(
        Path("tests/fixtures/workflow_lisp/valid/structured_results.orc"),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    command_bundle = structured_result.validated_bundles["command_checks"]
    command_effects = [
        effect
        for effect in command_bundle.semantic_ir.effects.values()
        if effect.effect_kind == "command_call"
    ]
    assert any(effect.boundary_kind == "external_tool" for effect in command_effects)

    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    request_cls = getattr(build_module, "FrontendBuildRequest")
    resource_source = Path("tests/fixtures/workflow_lisp/valid/resource_stdlib_transition.orc").read_text(
        encoding="utf-8"
    )
    resource_module_path = tmp_path / "resource" / "module.orc"
    resource_module_path.parent.mkdir(parents=True, exist_ok=True)
    resource_module_path.write_text(
        resource_source.replace(
            '  (:target-dsl "2.14")\n',
            '  (:target-dsl "2.14")\n  (defmodule resource/module)\n  (export move-selected-item)\n',
            1,
        ),
        encoding="utf-8",
    )
    resource_result = build_module.build_frontend_bundle(
        request_cls(
            source_path=resource_module_path,
            source_roots=(tmp_path,),
            entry_workflow="move-selected-item",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    resource_bundle = resource_result.validated_bundle
    resource_effects = [
        effect
        for effect in resource_bundle.semantic_ir.effects.values()
        if effect.effect_kind == "command_call"
    ]

    assert any(effect.boundary_kind == "certified_adapter" for effect in resource_effects)


def test_compiled_bundle_semantic_ir_preserves_distinct_resume_checkpoints(tmp_path: Path) -> None:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    request_cls = getattr(build_module, "FrontendBuildRequest")
    result = build_module.build_frontend_bundle(
        request_cls(
            source_path=Path("tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc"),
            source_roots=(Path("tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix"),),
            entry_workflow="orchestrate",
            provider_externs_path=Path("tests/fixtures/workflow_lisp/cli/providers.json"),
            prompt_externs_path=Path("tests/fixtures/workflow_lisp/cli/prompts.json"),
            imported_workflow_bundles_path=Path("tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json"),
            command_boundaries_path=Path("tests/fixtures/workflow_lisp/cli/commands.json"),
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )

    bundle = result.validated_bundle
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    resume_layouts = [
        layout
        for layout in bundle.semantic_ir.state_layout.values()
        if layout.layout_kind == "resume_checkpoint"
    ]
    expected_resume_pairs = {
        (checkpoint.node_id, checkpoint.checkpoint_kind)
        for checkpoint in bundle.runtime_plan.resume_checkpoints
    }
    actual_resume_pairs = {
        (
            layout.node_id,
            layout.details["checkpoint_kind"],
        )
        for layout in resume_layouts
    }

    assert len(bundle.runtime_plan.resume_checkpoints) == 4
    assert len(workflow.executable_bridge.resume_checkpoint_ids) == len(bundle.runtime_plan.resume_checkpoints)
    assert len(set(workflow.executable_bridge.resume_checkpoint_ids)) == len(bundle.runtime_plan.resume_checkpoints)
    assert len(resume_layouts) == len(bundle.runtime_plan.resume_checkpoints)
    assert actual_resume_pairs == expected_resume_pairs
