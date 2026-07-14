from __future__ import annotations

import importlib
import json
import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
import yaml

from orchestrator.exceptions import ValidationSubjectRef, WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import thaw_surface_workflow


REPO_ROOT = Path(__file__).resolve().parent.parent
PURE_EXPR_SELECTOR_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/pure_expr_selector_action_projection.orc")
LEXICAL_CHECKPOINT_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_shadow_points.orc")
LEXICAL_POLICY_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_effect_policies.orc")
LEXICAL_RESTORE_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_restore_regions.orc")
TYPED_PROMPT_INPUT_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/typed_prompt_input_phase.orc")
ENTRY_PUBLICATION_RUNTIME_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/entry_publication_runtime.orc")


@pytest.mark.parametrize("lowering_route", ["legacy", "wcc_m4"])
def test_compiled_result_guidance_survives_every_shared_ir_layer(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    source_path = tmp_path / f"result_guidance_{lowering_route}.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defworkflow guided ()",
                '    -> (result Bool :description "Public decision." :example true)',
                "    (provider-result providers.execute",
                "      :prompt prompts.execute",
                "      :inputs ()",
                '      :returns (result Bool :description "Provider decision." :example true))))',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_module(
        source_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )
    bundle = result.validated_bundles["guided"]
    expected = {"description": "Public decision.", "example": True}

    assert dict(bundle.surface.result_guidance) == expected
    assert dict(bundle.core_workflow_ast.result_guidance) == expected
    assert dict(bundle.semantic_ir.workflows["guided"].result_guidance) == expected
    assert dict(bundle.ir.result_guidance) == expected
    assert thaw_surface_workflow(bundle)["result_guidance"] == expected
    execution_config = next(iter(bundle.ir.nodes.values())).execution_config
    assert execution_config.common.output_bundle["fields"][0]["description"] == "Provider decision."
    assert execution_config.common.output_bundle["fields"][0]["example"] is True
    semantic_output = bundle.semantic_ir.contracts["contract:guided:output:__result__"]
    assert "description" not in semantic_output.definition
    assert "example" not in semantic_output.definition
    assert workflow_core_ast_to_json(bundle.core_workflow_ast)["result_guidance"] == expected
    assert workflow_semantic_ir_to_json(bundle.semantic_ir)["workflows"]["guided"]["result_guidance"] == expected
    assert workflow_executable_ir_to_json(bundle.ir)["result_guidance"] == expected
    assert not hasattr(bundle.runtime_plan, "result_guidance")
    assert not hasattr(bundle.projection, "result_guidance")


def test_result_guidance_is_omitted_when_absent_and_runtime_plan_neutral(tmp_path: Path) -> None:
    workflow_path = tmp_path / "result_guidance_neutrality.yaml"
    workflow = {
        "version": "2.15",
        "name": "result-guidance-neutrality",
        "artifacts": {"ready": {"kind": "scalar", "type": "bool"}},
        "outputs": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
                "from": {"ref": "root.steps.SetReady.artifacts.ready"},
            }
        },
        "steps": [
            {
                "name": "SetReady",
                "id": "set_ready",
                "set_scalar": {"artifact": "ready", "value": True},
            }
        ],
    }
    _write_yaml(workflow_path, workflow)
    plain_loader = WorkflowLoader(tmp_path)
    plain_loader._enabled_preview_versions = frozenset({"2.15"})
    plain = plain_loader.load_bundle(workflow_path)
    guided_workflow = {
        **workflow,
        "result_guidance": {
            "description": "True when the workflow is ready.",
            "example": True,
        },
    }
    _write_yaml(workflow_path, guided_workflow)
    guided_loader = WorkflowLoader(tmp_path)
    guided_loader._enabled_preview_versions = frozenset({"2.15"})
    guided = guided_loader.load_bundle(workflow_path)

    plain_core = workflow_core_ast_to_json(plain.core_workflow_ast)
    plain_semantic = workflow_semantic_ir_to_json(plain.semantic_ir)
    plain_executable = workflow_executable_ir_to_json(plain.ir)
    assert "result_guidance" not in plain_core
    assert "result_guidance" not in plain_semantic["workflows"][plain.surface.name]
    assert "result_guidance" not in plain_executable
    assert plain_core["schema_version"] == "core_workflow_ast.v1"
    assert plain_semantic["schema_version"] == "workflow_semantic_ir.v1"
    assert plain_executable["schema_version"] == "workflow_executable_ir.v1"

    assert guided.surface.outputs == plain.surface.outputs
    assert guided.core_workflow_ast.outputs == plain.core_workflow_ast.outputs
    assert guided.ir.outputs == plain.ir.outputs
    assert guided.ir.nodes == plain.ir.nodes
    assert guided.projection == plain.projection
    assert guided.runtime_plan == plain.runtime_plan
    assert guided.runtime_plan.resume_checkpoints == plain.runtime_plan.resume_checkpoints

    guided_core = workflow_core_ast_to_json(guided.core_workflow_ast)
    guided_core.pop("result_guidance")
    assert guided_core == plain_core
    guided_executable = workflow_executable_ir_to_json(guided.ir)
    guided_executable.pop("result_guidance")
    assert guided_executable == plain_executable
    guided_semantic = workflow_semantic_ir_to_json(guided.semantic_ir)
    guided_semantic["workflows"][guided.surface.name].pop("result_guidance")
    assert guided_semantic == plain_semantic


@pytest.mark.parametrize("lowering_route", ["legacy", "wcc_m4"])
def test_record_union_and_private_procedure_result_guidance_reaches_shared_ir(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    source_path = tmp_path / f"result_guidance_shapes_{lowering_route}.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defrecord ReviewResult (approved Bool))",
                "  (defunion Decision",
                "    (APPROVE (approved Bool))",
                "    (REVISE (reason String)))",
                "  (defproc build-review ()",
                '    -> (result ReviewResult :description "Private review result.")',
                "    :effects ((uses-command decide))",
                "    :lowering private-workflow",
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                "      :returns ReviewResult))",
                "  (defworkflow guided-record ()",
                '    -> (result ReviewResult :description "Public review result.")',
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                '      :returns (result ReviewResult :description "Command review result.")))',
                "  (defworkflow guided-union ()",
                '    -> (result Decision :description "Public decision result.")',
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                '      :returns (result Decision :description "Command decision result.")))',
                "  (defworkflow invoke-private () -> ReviewResult",
                "    (build-review)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_module(
        source_path,
        command_boundaries={
            "decide": ExternalToolBinding(
                name="decide",
                stable_command=("python", "scripts/decide.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )
    expected_by_name = {
        "guided-record": {"description": "Public review result."},
        "guided-union": {"description": "Public decision result."},
    }
    private_name = next(
        name for name in result.validated_bundles if name.startswith("%") and "build-review" in name
    )
    expected_by_name[private_name] = {"description": "Private review result."}

    for workflow_name, expected in expected_by_name.items():
        bundle = result.validated_bundles[workflow_name]
        assert dict(bundle.surface.result_guidance) == expected
        assert dict(bundle.core_workflow_ast.result_guidance) == expected
        assert dict(bundle.semantic_ir.workflows[workflow_name].result_guidance) == expected
        assert dict(bundle.ir.result_guidance) == expected

    record_bundle = result.validated_bundles["guided-record"]
    record_config = next(iter(record_bundle.ir.nodes.values())).execution_config
    assert record_config.common.output_bundle["guidance"] == {
        "description": "Command review result."
    }
    union_bundle = result.validated_bundles["guided-union"]
    union_config = next(iter(union_bundle.ir.nodes.values())).execution_config
    assert union_config.common.variant_output["guidance"] == {
        "description": "Command decision result."
    }
    for bundle in (record_bundle, union_bundle):
        for contract in bundle.semantic_ir.contracts.values():
            if contract.source_kind == "output":
                assert "guidance" not in contract.definition


def _real_union_contract_source_map_payload(tmp_path: Path):
    source_path = tmp_path / "semantic-ir-union-lineage.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule semantic-ir/union-lineage)",
                "  (export entry)",
                "  (defunion Decision",
                "    (ACCEPTED",
                "      (report String))",
                "    (REJECTED",
                "      (report String)))",
                "  (defworkflow entry",
                "    ((input String))",
                "    -> Decision",
                "    (provider-result providers.execute",
                "      :prompt prompts.execute",
                "      :inputs (input)",
                "      :returns Decision)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compile_result = compile_stage3_module(
        source_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    workflow_name = next(
        workflow.definition.name
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == "entry"
        or workflow.definition.name.endswith("::entry")
    )
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name={"__main__": compile_result},
            validated_bundles_by_name=compile_result.validated_bundles,
        ),
        selected_name=workflow_name,
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )
    payload = build_module._json_data(document)
    bundle = next(
        bundle
        for name, bundle in compile_result.validated_bundles.items()
        if name == workflow_name or name.endswith(f"::{workflow_name}")
    )
    return workflow_name, payload, bundle


def _g0_retirement_metadata(
    *,
    retirement_class: str,
    retirement_label: str,
    replacement_surface: str,
    bridge_owner: str,
    expiry_condition: str,
    evidence_ref: str,
) -> dict[str, object]:
    return {
        "retirement_class": retirement_class,
        "retirement_label": retirement_label,
        "replacement_surface": replacement_surface,
        "bridge_owner": bridge_owner,
        "expiry_condition": expiry_condition,
        "evidence_refs": (evidence_ref,),
    }


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _detach_core_ast_surface_links(value):
    if isinstance(value, tuple):
        return tuple(_detach_core_ast_surface_links(item) for item in value)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _detach_core_ast_surface_links(item) for key, item in value.items()})
    if not is_dataclass(value):
        return value

    updates = {}
    for field_def in fields(value):
        field_value = getattr(value, field_def.name)
        if field_def.name in {"_surface_step", "_surface_workflow"}:
            updates[field_def.name] = None
            continue
        detached = _detach_core_ast_surface_links(field_value)
        if detached is not field_value:
            updates[field_def.name] = detached
    return replace(value, **updates) if updates else value


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


def _write_consume_prompt_semantic_ir_workflow(workspace: Path) -> Path:
    (workspace / "prompts").mkdir(parents=True, exist_ok=True)
    (workspace / "prompts" / "review.md").write_text(
        "Review consumed artifacts.\n",
        encoding="utf-8",
    )
    return _write_yaml(
        workspace / "consume_prompt_workflow.yaml",
        {
            "version": "2.7",
            "name": "consume-prompt-semantic-ir",
            "providers": {
                "audit_provider": {
                    "command": ["echo", "${PROMPT}"],
                    "input_mode": "argv",
                }
            },
            "artifacts": {
                "baseline_design": {
                    "pointer": "state/baseline_design.txt",
                    "type": "relpath",
                    "under": "docs",
                },
                "execution_log": {
                    "pointer": "state/execution_log.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                },
                "private_notes": {
                    "pointer": "state/private_notes.txt",
                    "type": "relpath",
                    "under": "state",
                },
            },
            "steps": [
                {
                    "name": "Review",
                    "id": "review",
                    "provider": "audit_provider",
                    "input_file": "prompts/review.md",
                    "prompt_consumes": [],
                    "consumes": [
                        {
                            "artifact": "baseline_design",
                            "prompt": {
                                "mode": "reference",
                                "label": "Baseline design",
                                "role": "compatibility_baseline",
                            },
                        },
                        {
                            "artifact": "execution_log",
                            "prompt": {"mode": "content"},
                        },
                        {
                            "artifact": "private_notes",
                            "prompt": {
                                "mode": "none",
                                "role": "internal_only",
                            },
                        },
                    ],
                }
            ],
        },
    )


def _build_frontend_bundle_from_fixture(
    tmp_path: Path,
    *,
    fixture_path: Path,
    module_name: str,
    entry_workflow: str,
    extra_source_roots: tuple[Path, ...] = (),
) -> object:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    request_cls = getattr(build_module, "FrontendBuildRequest")
    source = fixture_path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    if module_match is None:
        source = source.replace(
            '  (:target-dsl "2.14")\n',
            f'  (:target-dsl "2.14")\n  (defmodule {module_name}/module)\n  (export {entry_workflow})\n',
            1,
        )
        resolved_module_name = f"{module_name}/module"
    else:
        resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return build_module.build_frontend_bundle(
        request_cls(
            source_path=module_path,
            source_roots=(*extra_source_roots, tmp_path),
            entry_workflow=entry_workflow,
            provider_externs_path=Path("tests/fixtures/workflow_lisp/cli/providers.json"),
            prompt_externs_path=Path("tests/fixtures/workflow_lisp/cli/prompts.json"),
            imported_workflow_bundles_path=None,
            command_boundaries_path=Path("tests/fixtures/workflow_lisp/cli/commands.json"),
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _compile_entrypoint_fixture(
    tmp_path: Path,
    *,
    fixture_path: Path,
    entry_workflow: str,
    extra_source_roots: tuple[Path, ...] = (),
):
    source = fixture_path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    if module_match is None:
        module_name = f"test/{fixture_path.stem}"
        source = source.replace(
            '  (:target-dsl "2.14")\n',
            f'  (:target-dsl "2.14")\n  (defmodule {module_name})\n  (export {entry_workflow})\n',
            1,
        )
    else:
        module_name = module_match.group(1)
    module_path = (tmp_path / Path(*module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return compile_stage3_entrypoint(
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
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                ),
                **_g0_retirement_metadata(
                    retirement_class="validation",
                    retirement_label="keep_bridge",
                    replacement_surface="typed review findings validation bridge",
                    bridge_owner="std/phase",
                    expiry_condition="retain until typed validation replaces the command bridge",
                    evidence_ref="validate_review_findings_v1",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _entrypoint_validated_bundle(result, *, entry_workflow: str):
    for workflow_name, bundle in result.validated_bundles_by_name.items():
        if workflow_name == entry_workflow or workflow_name.endswith(f"::{entry_workflow}"):
            return bundle
    raise AssertionError(f"validated bundle not found for entry workflow: {entry_workflow}")


def _compile_design_delta_implementation_phase_entrypoint(tmp_path: Path):
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
            "run_neurips_backlog_checks": ExternalToolBinding(
                name="run_neurips_backlog_checks",
                stable_command=(
                    "python",
                    "workflows/library/scripts/run_neurips_backlog_checks.py",
                ),
                **_g0_retirement_metadata(
                    retirement_class="genuine_system",
                    retirement_label="keep_certified_system",
                    replacement_surface="bounded repo-local checks",
                    bridge_owner="lisp_frontend_design_delta/implementation_phase",
                    expiry_condition="retain while backlog checks remain an external repo-local tool",
                    evidence_ref="run_neurips_backlog_checks",
                ),
            ),
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                ),
                **_g0_retirement_metadata(
                    retirement_class="validation",
                    retirement_label="keep_bridge",
                    replacement_surface="typed review findings validation bridge",
                    bridge_owner="std/phase",
                    expiry_condition="retain until typed validation replaces the command bridge",
                    evidence_ref="validate_review_findings_v1",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name[
        "lisp_frontend_design_delta/implementation_phase::implementation-phase"
    ]
    return result, bundle


def _build_materialize_view_bundle():
    lowering_module = importlib.import_module("orchestrator.workflow.lowering")
    surface_ast = importlib.import_module("orchestrator.workflow.surface_ast")

    workflow = surface_ast.SurfaceWorkflow(
        version="2.14",
        name="materialize-view-semantic-ir",
        steps=(
            surface_ast.SurfaceStep(
                name="MaterializeView",
                step_id="materialize_view",
                kind=surface_ast.SurfaceStepKind.MATERIALIZE_VIEW,
                common=surface_ast.SurfaceStepCommonConfig(),
                materialize_view={
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "view_renderer_schema_version": 1,
                    "value_type": {
                        "kind": "record",
                        "name": "SummaryValue",
                        "fields": [
                            {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                        ],
                    },
                    "value_document": {"status": "DONE"},
                    "target_path": "state/materialized-views/summary.json",
                    "target_allocation_id": "alloc:test:materialized_value_view",
                    "authority_class": "materialized_view",
                    "output_contracts": {
                        "return": {
                            "kind": "relpath",
                            "type": "relpath",
                            "under": "state",
                            "must_exist_target": True,
                        }
                    },
                },
            ),
        ),
        provenance=surface_ast.WorkflowProvenance(
            workflow_path=Path("generated.yaml"),
            source_root=Path("."),
        ),
    )
    return lowering_module.build_loaded_workflow_bundle(workflow, imports={})


def _build_parametric_frontend_bundle(tmp_path: Path) -> object:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    request_cls = getattr(build_module, "FrontendBuildRequest")
    module_path = tmp_path / "demo" / "module.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
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
    return build_module.build_frontend_bundle(
        request_cls(
            source_path=module_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            provider_externs_path=Path("tests/fixtures/workflow_lisp/cli/providers.json"),
            prompt_externs_path=Path("tests/fixtures/workflow_lisp/cli/prompts.json"),
            imported_workflow_bundles_path=None,
            command_boundaries_path=Path("tests/fixtures/workflow_lisp/cli/commands.json"),
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _statement_step_ids(workflow) -> list[str]:
    return [
        workflow.statements[statement_id].step_id.split(".")[-1]
        for statement_id in workflow.authored_statement_ids
    ]


def _core_command_steps(statements: tuple[object, ...]) -> list[object]:
    command_steps: list[object] = []
    for statement in statements:
        if getattr(getattr(statement, "meta", None), "step_kind", None) == "command":
            command_steps.append(statement)
        if hasattr(statement, "then_branch"):
            command_steps.extend(_core_command_steps(statement.then_branch.statements))
            else_branch = getattr(statement, "else_branch", None)
            if else_branch is not None:
                command_steps.extend(_core_command_steps(else_branch.statements))
        elif hasattr(statement, "cases"):
            for case in statement.cases.values():
                command_steps.extend(_core_command_steps(case.statements))
        elif hasattr(statement, "statements"):
            command_steps.extend(_core_command_steps(statement.statements))
    return command_steps


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
    assert not any(
        effect.effect_kind in {"resource_transition", "ledger_update", "snapshot_capture", "pointer_materialization"}
        for effect in semantic_ir.effects.values()
    )


def test_semantic_ir_projects_statement_taxonomy_facets(tmp_path: Path) -> None:
    yaml_bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))
    yaml_workflow = yaml_bundle.semantic_ir.workflows[yaml_bundle.surface.name]

    yaml_command_effect = next(
        effect
        for effect in yaml_bundle.semantic_ir.effects.values()
        if effect.effect_kind == "command_call"
    )
    yaml_call_edge = yaml_bundle.semantic_ir.call_edges[yaml_workflow.call_edge_ids[0]]
    yaml_prompt_surface = yaml_bundle.semantic_ir.prompt_surfaces[yaml_workflow.prompt_surface_ids[0]]

    assert yaml_command_effect.boundary_kind == "external_tool"
    assert yaml_command_effect.boundary_name == "RunChecks"
    assert yaml_call_edge.call_alias == "review_loop"
    assert yaml_prompt_surface.provider_name == "audit_provider"
    assert any(
        layout.layout_kind == "presentation_key"
        for layout in yaml_bundle.semantic_ir.state_layout.values()
    )
    assert any(
        layout.layout_kind == "resume_checkpoint"
        for layout in yaml_bundle.semantic_ir.state_layout.values()
    )


def test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence(
    tmp_path: Path,
) -> None:
    bundle = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=TYPED_PROMPT_INPUT_FIXTURE,
        entry_workflow="run-typed-prompt-phase-demo",
        extra_source_roots=(TYPED_PROMPT_INPUT_FIXTURE.parent,),
    ).validated_bundles_by_name["typed_prompt_input_phase::run-typed-prompt-phase-demo"]

    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    prompt_surface = bundle.semantic_ir.prompt_surfaces[workflow.prompt_surface_ids[0]]

    assert getattr(prompt_surface, "typed_prompt_inputs")
    typed_prompt_input = prompt_surface.typed_prompt_inputs[0]
    assert typed_prompt_input["renderer"]["renderer_id"] == "canonical-json"
    assert typed_prompt_input["value_type_name"]
    assert typed_prompt_input["c0_row_id"]
    assert "rendered_bytes" not in str(typed_prompt_input)

    pointer_result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc"),
        module_name="pointer_effects",
        entry_workflow="orchestrate",
    )
    pointer_bundle = pointer_result.validated_bundle
    pointer_source_map = json.loads(pointer_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    pointer_workflow_name = next(iter(pointer_source_map["workflows"]))

    assert any(
        effect.effect_kind == "pointer_materialization"
        for effect in pointer_bundle.semantic_ir.effects.values()
    )
    assert any(
        proof.proof_kind == "variant_surface"
        for proof in pointer_bundle.semantic_ir.proofs.values()
    )
    assert any(
        effect["effect_kind"] == "pointer_materialization"
        for effect in pointer_source_map["workflows"][pointer_workflow_name]["generated_semantic_effects"]
    )

    snapshot_result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/phase_snapshot_effects.orc"),
        module_name="phase_snapshot",
        entry_workflow="orchestrate",
    )
    snapshot_bundle = snapshot_result.validated_bundle
    snapshot_source_map = json.loads(snapshot_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    snapshot_workflow_name = next(iter(snapshot_source_map["workflows"]))

    assert any(
        effect.effect_kind == "snapshot_capture"
        for effect in snapshot_bundle.semantic_ir.effects.values()
    )
    assert {(plan.operation_kind, plan.selection_relevant) for plan in snapshot_bundle.runtime_plan.snapshots} >= {
        ("pre_snapshot", True),
        ("select_variant_output", True),
    }


def test_semantic_ir_consume_prompt_surface_records_prompt_view_metadata_without_authority_leak(
    tmp_path: Path,
) -> None:
    bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_consume_prompt_semantic_ir_workflow(tmp_path)
    )

    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    prompt_surface = bundle.semantic_ir.prompt_surfaces[workflow.prompt_surface_ids[0]]

    policies = getattr(prompt_surface, "consumed_prompt_policies")
    by_artifact = {entry["artifact_name"]: entry for entry in policies}

    assert prompt_surface.prompt_consumes == ()
    assert by_artifact["baseline_design"]["mode"] == "reference"
    assert by_artifact["baseline_design"]["label"] == "Baseline design"
    assert by_artifact["baseline_design"]["role"] == "compatibility_baseline"
    assert by_artifact["execution_log"]["mode"] == "content"
    assert by_artifact["private_notes"]["mode"] == "none"
    assert by_artifact["private_notes"]["role"] == "internal_only"
    assert not any(
        contract.contract_name == "compatibility_baseline"
        for contract in bundle.semantic_ir.contracts.values()
    )


def test_semantic_ir_records_entry_publication_materialize_view_metadata(
    tmp_path: Path,
) -> None:
    bundle = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=ENTRY_PUBLICATION_RUNTIME_FIXTURE,
        entry_workflow="entry-publication-runtime",
        extra_source_roots=(ENTRY_PUBLICATION_RUNTIME_FIXTURE.parent,),
    ).validated_bundles_by_name["entry_publication_runtime::entry-publication-runtime"]

    publication_effect = next(
        effect
        for effect in bundle.semantic_ir.effects.values()
        if effect.effect_kind == "materialize_view"
        and isinstance(effect.details.get("publication"), Mapping)
    )

    assert publication_effect.details["publication"]["role"] == "drain-summary"
    assert publication_effect.details["publication"]["row_id"].startswith(
        "publish.entry-publication-runtime"
    )


def test_semantic_ir_promotes_pure_projection_generated_effects(tmp_path: Path) -> None:
    pure_projection_result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=PURE_EXPR_SELECTOR_FIXTURE,
        module_name="pure_expr_selector",
        entry_workflow="orchestrate",
    )
    pure_projection_bundle = pure_projection_result.validated_bundle
    pure_projection_source_map = json.loads(
        pure_projection_result.artifact_paths["source_map"].read_text(encoding="utf-8")
    )
    pure_projection_workflow_name = next(iter(pure_projection_source_map["workflows"]))
    pure_projection_effect = next(
        effect
        for effect in pure_projection_bundle.semantic_ir.effects.values()
        if effect.effect_kind == "pure_projection"
    )

    assert pure_projection_effect.details["pure_expr_schema_version"] == 1
    assert pure_projection_effect.details["payload_digest"].startswith("sha256:")
    assert "__write_root__" in pure_projection_effect.details["output_bundle_path"]
    assert "result_bundle" in pure_projection_effect.details["output_bundle_path"]
    assert any(
        effect["effect_kind"] == "pure_projection"
        for effect in pure_projection_source_map["workflows"][pure_projection_workflow_name]["generated_semantic_effects"]
    )
    assert any(
        entry.layout_kind == "pure_projection_bundle"
        and str(entry.details.get("generated_input_name", "")).startswith(
            "__write_root__pure_expr_selector_action_projection_orchestrate__"
        )
        and str(entry.details.get("generated_input_name", "")).endswith("__result_bundle")
        for entry in pure_projection_bundle.semantic_ir.state_layout.values()
    )


def test_semantic_ir_records_materialize_view_effect_details() -> None:
    bundle = _build_materialize_view_bundle()

    effect = next(
        candidate
        for candidate in bundle.semantic_ir.effects.values()
        if candidate.effect_kind == "materialize_view"
    )

    assert effect.details["renderer_id"] == "canonical-json"
    assert effect.details["renderer_version"] == 1
    assert effect.details["view_renderer_schema_version"] == 1
    assert effect.details["target_path"] == "state/materialized-views/summary.json"
    assert effect.details["authority_class"] == "materialized_view"


def test_semantic_ir_validation_keeps_legacy_callable_surface_for_materialize_view_bundle() -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    bundle = _build_materialize_view_bundle()

    semantic_ir_module.validate_workflow_semantic_ir(
        bundle.semantic_ir,
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
    )


def test_semantic_ir_builds_resource_transition_bundle(tmp_path: Path) -> None:
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

    assert any(
        effect.effect_kind == "resource_transition"
        for effect in resource_bundle.semantic_ir.effects.values()
    )
    assert any(
        effect.effect_kind == "ledger_update"
        for effect in resource_bundle.semantic_ir.effects.values()
    )
    assert any(
        boundary.boundary_kind == "certified_adapter"
        and boundary.boundary_name == "apply_resource_transition"
        for boundary in resource_bundle.semantic_ir.command_boundaries.values()
    )


def test_compiled_bundle_bridge_node_sets_match_executable_runtime_semantic_and_source_map_surfaces(
    tmp_path: Path,
) -> None:
    result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc"),
        module_name="pointer_effects",
        entry_workflow="orchestrate",
    )
    bundle = result.validated_bundle
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    source_map_path = bundle.surface.provenance.frontend_source_trace_path
    assert isinstance(source_map_path, Path)
    source_map_payload = json.loads(source_map_path.read_text(encoding="utf-8"))

    executable_node_ids = set(bundle.ir.nodes)
    runtime_plan_node_ids = set(bundle.runtime_plan.nodes)
    semantic_bridge_node_ids = set(workflow.executable_bridge.node_ids)
    source_map_node_ids = {
        node["node_id"]
        for node in source_map_payload["workflows"][bundle.surface.name]["executable_nodes"]
    }

    assert executable_node_ids == runtime_plan_node_ids
    assert executable_node_ids == semantic_bridge_node_ids
    assert executable_node_ids == source_map_node_ids


def test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys(
    tmp_path: Path,
) -> None:
    result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc"),
        module_name="pointer_effects",
        entry_workflow="orchestrate",
    )
    executable_ir_payload = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    serialized = json.dumps(executable_ir_payload, sort_keys=True)

    assert executable_ir_payload["schema_version"] == "workflow_executable_ir.v1"
    assert "_surface_step" not in serialized
    assert "_surface_workflow" not in serialized
    assert "typed_workflow" not in serialized
    assert "form_path" not in serialized
    assert "expansion_stack" not in serialized
    assert "validation_subjects" not in serialized
    assert "ProcRef" not in serialized
    assert "WorkflowRef" not in serialized
    for marker in (
        "workflow_lisp_runtime_closure",
        "closure_families",
        "InvokeClosure",
        "Closure[",
        "runtime_closure",
    ):
        assert marker not in serialized


def test_compiled_bundle_erases_type_params_before_semantic_and_executable_surfaces(
    tmp_path: Path,
) -> None:
    result = _build_parametric_frontend_bundle(tmp_path)
    semantic_ir_payload = result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")
    executable_ir_payload = result.artifact_paths["executable_ir"].read_text(encoding="utf-8")

    for serialized in (semantic_ir_payload, executable_ir_payload):
        assert "TypeParamRef" not in serialized
        assert '"type_params"' not in serialized
        assert '"where_clauses"' not in serialized
        assert ":forall" not in serialized
        assert "ProcRef[T -> T]" not in serialized


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
    assert "executable_ir_invalid" not in error.message
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


def test_semantic_ir_source_map_bridges_every_contract_field_subject(
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    workflow_name, source_map_payload, _ = _real_union_contract_source_map_payload(tmp_path)
    workflow_payload = source_map_payload["workflows"][workflow_name]

    bridges = semantic_ir_module._frontend_source_map_bridges_from_payload(
        workflow_name,
        workflow_payload,
    )
    field_subjects = {
        (
            binding["subject_ref"]["subject_name"],
            binding["origin_key"],
        )
        for binding in workflow_payload["validation_subjects"]
        if binding["subject_ref"]["subject_kind"] == "variant_output_field"
    }
    bridged_fields = {
        (bridge.subject_ref.subject_name, bridge.origin_key)
        for bridge in bridges.values()
        if bridge.subject_ref.subject_kind == "variant_output_field"
    }

    assert field_subjects
    assert bridged_fields == field_subjects


def test_semantic_ir_source_map_bridges_root_result_output_bundle_field_subject(
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    source_path = tmp_path / "semantic-ir-root-result-lineage.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule semantic-ir/root-result-lineage)",
                "  (export entry)",
                "  (defworkflow entry",
                "    ((input String))",
                "    -> Bool",
                "    (provider-result providers.execute",
                "      :prompt prompts.execute",
                "      :inputs (input)",
                "      :returns Bool)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compile_result = compile_stage3_module(
        source_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    workflow_name = next(
        workflow.definition.name
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == "entry"
        or workflow.definition.name.endswith("::entry")
    )
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    document = source_map_module.build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name={"__main__": compile_result},
            validated_bundles_by_name=compile_result.validated_bundles,
        ),
        selected_name=workflow_name,
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )
    workflow_payload = build_module._json_data(document)["workflows"][workflow_name]

    bridges = semantic_ir_module._frontend_source_map_bridges_from_payload(
        workflow_name,
        workflow_payload,
    )

    root_field_subjects = {
        (
            binding["subject_ref"]["subject_name"],
            binding["origin_key"],
        )
        for binding in workflow_payload["validation_subjects"]
        if binding["subject_ref"]["subject_kind"] == "output_bundle_field"
    }
    bridged_root_fields = {
        (bridge.subject_ref.subject_name, bridge.origin_key)
        for bridge in bridges.values()
        if bridge.subject_ref.subject_kind == "output_bundle_field"
    }
    assert root_field_subjects
    assert any(
        subject_name.endswith("::root-result::__result__")
        for subject_name, _ in root_field_subjects
    )
    assert bridged_root_fields == root_field_subjects


def test_semantic_ir_source_map_rejects_contract_field_subject_with_missing_origin(
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    workflow_name, source_map_payload, _ = _real_union_contract_source_map_payload(tmp_path)
    workflow_payload = source_map_payload["workflows"][workflow_name]
    field_binding = next(
        binding
        for binding in workflow_payload["validation_subjects"]
        if binding["subject_ref"]["subject_kind"] == "variant_output_field"
    )
    broken_payload = {
        **workflow_payload,
        "contract_fields": {
            subject_name: entry
            for subject_name, entry in workflow_payload["contract_fields"].items()
            if entry["origin_key"] != field_binding["origin_key"]
        },
    }

    with pytest.raises(WorkflowValidationError) as excinfo:
        semantic_ir_module._frontend_source_map_bridges_from_payload(
            workflow_name,
            broken_payload,
        )

    error = excinfo.value.errors[0]
    assert "semantic_ir_invalid" in error.message
    assert error.subject_refs == (
        ValidationSubjectRef(
            subject_kind="variant_output_field",
            subject_name=field_binding["subject_ref"]["subject_name"],
            workflow_name=workflow_name,
        ),
    )


def test_semantic_ir_source_map_old_v1_without_contract_fields_still_derives(
    tmp_path: Path,
) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    workflow_name, source_map_payload, bundle = _real_union_contract_source_map_payload(tmp_path)
    workflow_payload = source_map_payload["workflows"][workflow_name]
    old_v1_workflow_payload = {
        key: value
        for key, value in workflow_payload.items()
        if key != "contract_fields"
    }
    old_v1_workflow_payload["validation_subjects"] = [
        binding
        for binding in workflow_payload["validation_subjects"]
        if binding["subject_ref"]["subject_kind"] != "variant_output_field"
    ]
    old_v1_source_map_path = tmp_path / "old-v1-source-map.json"
    old_v1_source_map_path.write_text(
        json.dumps(
            {
                **source_map_payload,
                "workflows": {
                    **source_map_payload["workflows"],
                    workflow_name: old_v1_workflow_payload,
                },
            }
        ),
        encoding="utf-8",
    )
    old_v1_provenance = replace(
        bundle.surface.provenance,
        frontend_source_trace_path=old_v1_source_map_path,
    )

    semantic_ir = semantic_ir_module.derive_workflow_semantic_ir(
        surface=replace(bundle.surface, provenance=old_v1_provenance),
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
        imports=bundle.imports,
        provenance=old_v1_provenance,
    )

    assert semantic_ir.source_map
    assert all(
        bridge.subject_ref.subject_kind != "variant_output_field"
        for bridge in semantic_ir.source_map.values()
    )


def test_source_map_executable_coverage_failures_stay_in_source_map_diagnostic_family(
    tmp_path: Path,
) -> None:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
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
    source_map_document = source_map_module.build_source_map_document(
        result.compile_result,
        selected_name=result.selected_workflow_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    selected_workflow = source_map_document.workflows[result.validated_bundle.surface.name]
    broken_node = replace(selected_workflow.executable_nodes[0], origin_key="missing-origin")
    broken_workflow = replace(
        selected_workflow,
        executable_nodes=(broken_node, *selected_workflow.executable_nodes[1:]),
    )
    broken_document = replace(
        source_map_document,
        workflows={
            **dict(source_map_document.workflows),
            selected_workflow.workflow_name: broken_workflow,
        },
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        source_map_module.validate_source_map_document(broken_document)

    diagnostics_module = importlib.import_module("orchestrator.workflow_lisp.diagnostics")
    classified = diagnostics_module.with_diagnostic_metadata(excinfo.value.diagnostics[0])

    assert classified.code == "source_map_executable_node_unmapped"
    assert classified.validation_pass == "source_map"


def test_load_returns_typed_bundle_with_semantic_ir(tmp_path: Path) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    loaded = WorkflowLoader(tmp_path).load(_write_semantic_ir_workflow(tmp_path))
    semantic_workflow = loaded.semantic_ir.workflows[loaded.surface.name]

    assert loaded.semantic_ir.schema_version == semantic_ir_module.WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION
    assert semantic_workflow.workflow_name == loaded.surface.name
    assert [statement.meta.step_id for statement in loaded.core_workflow_ast.body] == [
        semantic_workflow.statements[statement_id].step_id.split(".")[-1]
        for statement_id in semantic_workflow.authored_statement_ids
    ]


def test_semantic_ir_derivation_uses_detached_core_ast_payload(tmp_path: Path) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))
    detached_core_ast = _detach_core_ast_surface_links(bundle.core_workflow_ast)

    detached_semantic_ir = semantic_ir_module.derive_workflow_semantic_ir(
        core_workflow_ast=detached_core_ast,
        surface=bundle.surface,
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
        imports=bundle.imports,
        provenance=bundle.provenance,
    )
    workflow = detached_semantic_ir.workflows[bundle.surface.name]
    original_workflow = bundle.semantic_ir.workflows[bundle.surface.name]

    assert workflow.authored_statement_ids == original_workflow.authored_statement_ids
    assert workflow.authored_statement_ids
    assert tuple(workflow.statements) == tuple(original_workflow.statements)


def test_semantic_ir_derivation_prefers_core_ast_contracts_and_import_catalog(tmp_path: Path) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))
    detached_core_ast = _detach_core_ast_surface_links(bundle.core_workflow_ast)

    mutated_surface = replace(
        bundle.surface,
        inputs=MappingProxyType(
            {
                **dict(bundle.surface.inputs),
                "write_root": replace(bundle.surface.inputs["write_root"], value_type="integer"),
            }
        ),
        imports=MappingProxyType(
            {
                **dict(bundle.surface.imports),
                "review_loop": replace(
                    bundle.surface.imports["review_loop"],
                    workflow_name="wrong/workflow::name",
                ),
            }
        ),
    )

    detached_semantic_ir = semantic_ir_module.derive_workflow_semantic_ir(
        core_workflow_ast=detached_core_ast,
        surface=mutated_surface,
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
        imports=bundle.imports,
        provenance=bundle.provenance,
    )

    input_contract = next(
        contract
        for contract in detached_semantic_ir.contracts.values()
        if contract.source_kind == "input" and contract.contract_name == "write_root"
    )
    import_ref = next(
        ref
        for ref in detached_semantic_ir.refs.values()
        if ref.ref_kind == "import_alias" and ref.subject_name == "review_loop"
    )

    assert input_contract.value_type == bundle.core_workflow_ast.inputs["write_root"].value_type
    assert input_contract.value_type == "relpath"
    assert import_ref.target == bundle.core_workflow_ast.imports["review_loop"].workflow_name
    assert import_ref.target != "wrong/workflow::name"


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
    resource_command_steps = _core_command_steps(resource_bundle.core_workflow_ast.body)

    assert any(effect.boundary_kind == "certified_adapter" for effect in resource_effects)
    assert any(
        step.boundary_kind == "certified_adapter" and step.boundary_name == "apply_resource_transition"
        for step in resource_command_steps
    )


def test_frontend_build_semantic_ir_projects_promoted_resource_and_ledger_effects(tmp_path: Path) -> None:
    result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/resource_transition_effects.orc"),
        module_name="resource_effects",
        entry_workflow="move-selected-item",
    )
    effects = list(result.validated_bundle.semantic_ir.effects.values())

    resource_effect = next(effect for effect in effects if effect.effect_kind == "resource_transition")
    ledger_effect = next(effect for effect in effects if effect.effect_kind == "ledger_update")

    assert any(effect.effect_kind == "command_call" and effect.boundary_kind == "certified_adapter" for effect in effects)
    assert resource_effect.details == {"from_queue": "active", "to_queue": "in_progress"}
    assert ledger_effect.details == {"event_name": "SELECTED"}


def test_frontend_build_semantic_ir_projects_generated_snapshot_and_pointer_effects(tmp_path: Path) -> None:
    result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/phase_snapshot_effects.orc"),
        module_name="snapshot_effects",
        entry_workflow="orchestrate",
    )
    effects = list(result.validated_bundle.semantic_ir.effects.values())

    snapshot_effect = next(effect for effect in effects if effect.effect_kind == "snapshot_capture")
    pointer_effects = [
        effect
        for effect in effects
        if effect.effect_kind == "pointer_materialization"
    ]

    assert any(effect.effect_kind == "provider_call" for effect in effects)
    assert snapshot_effect.details["snapshot_kind"].endswith("_before")
    assert tuple(snapshot_effect.details["candidate_names"]) == ("COMPLETED", "BLOCKED")
    assert pointer_effects
    assert all(effect.details["representation_role"] == "artifact_pointer" for effect in pointer_effects)


def test_derive_semantic_ir_rejects_invalid_promoted_frontend_lineage(tmp_path: Path) -> None:
    semantic_ir_module = importlib.import_module("orchestrator.workflow.semantic_ir")
    result = _build_frontend_bundle_from_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc"),
        module_name="pointer_effects",
        entry_workflow="orchestrate",
    )
    bundle = result.validated_bundle
    source_map_path = bundle.surface.provenance.frontend_source_trace_path
    assert isinstance(source_map_path, Path)
    source_map_payload = json.loads(source_map_path.read_text(encoding="utf-8"))
    workflow_payload = source_map_payload["workflows"][bundle.surface.name]
    workflow_payload["generated_semantic_effects"][0]["step_id"] = "missing_step"
    broken_source_map_path = tmp_path / "broken_promoted_source_map.json"
    broken_source_map_path.write_text(json.dumps(source_map_payload, indent=2) + "\n", encoding="utf-8")

    broken_provenance = replace(
        bundle.provenance,
        frontend_source_trace_path=broken_source_map_path,
    )

    with pytest.raises(WorkflowValidationError) as excinfo:
        semantic_ir_module.derive_workflow_semantic_ir(
            core_workflow_ast=bundle.core_workflow_ast,
            surface=replace(bundle.surface, provenance=broken_provenance),
            ir=bundle.ir,
            projection=bundle.projection,
            runtime_plan=bundle.runtime_plan,
            imports=bundle.imports,
            provenance=broken_provenance,
        )

    assert excinfo.value.errors
    assert "semantic_ir_invalid" in excinfo.value.errors[0].message


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

    assert len(bundle.runtime_plan.resume_checkpoints) >= 2
    assert len(workflow.executable_bridge.resume_checkpoint_ids) == len(bundle.runtime_plan.resume_checkpoints)
    assert len(set(workflow.executable_bridge.resume_checkpoint_ids)) == len(bundle.runtime_plan.resume_checkpoints)
    assert len(resume_layouts) == len(bundle.runtime_plan.resume_checkpoints)
    assert actual_resume_pairs == expected_resume_pairs


def test_semantic_ir_records_nested_scope_projection_lineage(tmp_path: Path) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_implementation_phase.orc"),
        entry_workflow="implementation-phase",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="implementation-phase")
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]

    assert workflow.authored_statement_ids
    assert workflow.executable_bridge.node_ids


def test_semantic_ir_records_generated_paths_inside_nested_branch_scopes(tmp_path: Path) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_implementation_phase.orc"),
        entry_workflow="implementation-phase",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="implementation-phase")

    assert any(
        effect.effect_kind in {"provider_call", "workflow_call"}
        for effect in bundle.semantic_ir.effects.values()
    )


def test_semantic_ir_records_design_delta_implementation_phase_lineage(tmp_path: Path) -> None:
    _result, bundle = _compile_design_delta_implementation_phase_entrypoint(tmp_path)
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]

    assert workflow.authored_statement_ids
    assert workflow.executable_bridge.node_ids
    assert any(
        effect.effect_kind in {"provider_call", "workflow_call", "command_boundary"}
        for effect in bundle.semantic_ir.effects.values()
    )


def test_semantic_ir_records_generated_write_roots_across_reusable_call_boundaries(
    tmp_path: Path,
) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_imported_branch_effects.orc"),
        entry_workflow="entry",
        extra_source_roots=(Path("tests/fixtures/workflow_lisp/modules/valid/workflow_refs"),),
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="entry")

    assert bundle.semantic_ir.workflows[bundle.surface.name].statements


def test_semantic_ir_records_branch_scoped_resume_identity_lineage(tmp_path: Path) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=Path("tests/fixtures/workflow_lisp/valid/design_delta_nested_branch_scope_collision.orc"),
        entry_workflow="entry",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="entry")
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    assert workflow.executable_bridge.resume_checkpoint_ids


def test_lexical_checkpoint_runtime_plan_and_semantic_ir_bridges_are_additive(tmp_path: Path) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=LEXICAL_CHECKPOINT_FIXTURE,
        entry_workflow="orchestrate",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="orchestrate")
    workflow = bundle.semantic_ir.workflows[bundle.surface.name]

    checkpoint_points = bundle.runtime_plan.lexical_checkpoint_points

    assert checkpoint_points
    assert any(point.point_kind == "effect_boundary" for point in checkpoint_points)
    assert any(point.point_kind == "loop_back_edge" for point in checkpoint_points)
    assert all(
        point.details.get("wcc_identity", {}).get("node_id_digest", "").startswith("sha256:")
        and point.details.get("storage", {}).get("semantic_role") == "lexical_checkpoint_record"
        for point in checkpoint_points
    )
    assert workflow.executable_bridge.resume_checkpoint_ids
    assert bundle.runtime_plan.resume_checkpoints


def test_yaml_bundle_runtime_plan_remains_without_lexical_checkpoint_metadata(tmp_path: Path) -> None:
    yaml_bundle = WorkflowLoader(tmp_path).load_bundle(_write_semantic_ir_workflow(tmp_path))

    assert getattr(yaml_bundle.runtime_plan, "lexical_checkpoint_points", ()) == ()
    assert not any(
        layout.layout_kind.startswith("lexical_checkpoint")
        for layout in yaml_bundle.semantic_ir.state_layout.values()
    )


def test_lexical_checkpoint_semantic_ir_state_layout_entries_are_additive(tmp_path: Path) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=LEXICAL_CHECKPOINT_FIXTURE,
        entry_workflow="orchestrate",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="orchestrate")
    checkpoint_layouts = [
        layout
        for layout in bundle.semantic_ir.state_layout.values()
        if layout.layout_kind.startswith("lexical_checkpoint")
    ]

    assert any(layout.layout_kind == "lexical_checkpoint_point" for layout in checkpoint_layouts)
    assert any(layout.layout_kind == "lexical_checkpoint_record" for layout in checkpoint_layouts)
    assert any(layout.layout_kind == "lexical_checkpoint_index" for layout in checkpoint_layouts)


def test_lexical_checkpoint_record_layout_scope_matches_point_storage_scope(tmp_path: Path) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=LEXICAL_CHECKPOINT_FIXTURE,
        entry_workflow="orchestrate",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="orchestrate")
    record_layouts_by_checkpoint_id = {
        layout.details.get("stable_identity"): layout
        for layout in bundle.semantic_ir.state_layout.values()
        if layout.layout_kind == "lexical_checkpoint_record"
    }
    loop_back_edge_points = [
        point for point in bundle.runtime_plan.lexical_checkpoint_points if point.point_kind == "loop_back_edge"
    ]

    assert loop_back_edge_points
    assert all(
        record_layouts_by_checkpoint_id[point.checkpoint_id].details.get("resume_scope")
        == point.details.get("storage", {}).get("resume_scope")
        for point in bundle.runtime_plan.lexical_checkpoint_points
    )


def test_lexical_checkpoint_semantic_ir_surfaces_restore_metadata_additively_and_route_neutrally(
    tmp_path: Path,
) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=LEXICAL_RESTORE_FIXTURE,
        entry_workflow="orchestrate",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="orchestrate")
    point_layouts = [
        layout
        for layout in bundle.semantic_ir.state_layout.values()
        if layout.layout_kind == "lexical_checkpoint_point"
    ]

    restore_labels = {
        label
        for layout in point_layouts
        for label in layout.details.get("restore", {}).get("eligibility", ())
    }

    assert {"pure_binding", "let_continuation", "match_branch", "loop_frame"} <= restore_labels
    assert any(layout.details.get("restore", {}).get("binding_descriptor_digests") for layout in point_layouts)
    assert any(layout.details.get("restore", {}).get("proof_descriptor_digests") for layout in point_layouts)
    assert any(layout.details.get("restore", {}).get("loop_frame_descriptor_digest") for layout in point_layouts)


def test_lexical_checkpoint_semantic_ir_surfaces_r3_policy_summaries_additively(
    tmp_path: Path,
) -> None:
    result = _compile_entrypoint_fixture(
        tmp_path,
        fixture_path=LEXICAL_POLICY_FIXTURE,
        entry_workflow="orchestrate",
    )
    bundle = _entrypoint_validated_bundle(result, entry_workflow="orchestrate")
    point_layouts = {
        layout.details.get("checkpoint_id"): layout
        for layout in bundle.semantic_ir.state_layout.values()
        if layout.layout_kind == "lexical_checkpoint_point"
    }
    effect_points = [
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
    ]

    assert effect_points
    assert any(point.details.get("effect_boundary", {}).get("policy", {}) for point in effect_points)
    assert {
        point.details["effect_boundary"]["effect_kind"]
        for point in effect_points
    } >= {"pure_projection", "provider", "command", "call", "materialize_view", "resource_transition"}
    assert all(
        point_layouts[point.checkpoint_id].details.get("effect_boundary", {}).get("policy", {}).get("policy_kind")
        == point.details.get("effect_boundary", {}).get("policy", {}).get("policy_kind")
        for point in effect_points
    )
    assert all("binding_descriptors" not in layout.details.get("restore", {}) for layout in point_layouts.values())
    assert all("proof_descriptors" not in layout.details.get("restore", {}) for layout in point_layouts.values())
    assert all("loop_frame_descriptor" not in layout.details.get("restore", {}) for layout in point_layouts.values())
    serialized = json.dumps([dict(layout.details) for layout in point_layouts.values()], sort_keys=True)
    assert "restore_payload" not in serialized
    assert "wcc-node:" not in serialized
    assert "runtime_sidecar" not in serialized
