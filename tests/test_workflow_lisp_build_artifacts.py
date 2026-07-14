from __future__ import annotations

import importlib
import json
from dataclasses import asdict, is_dataclass, replace
from enum import Enum
from pathlib import Path

import pytest

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow_lisp.compiler import compile_stage1_entrypoint, compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.definitions import RecordField
from orchestrator.workflow_lisp.functions import FunctionDef
from orchestrator.workflow_lisp.modules import resolve_module_graph
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.wcc.route import LoweringRoute


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations"
)
# This checked-in candidate remains the authoritative proof source for the
# imported-child prerequisite until the shipping library module lands its
# separate parent-callable `run-work-item` export.
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
IMPORTED_STDLIB_HELPER_ROOT = FIXTURES / "modules" / "valid" / "imported_stdlib_macro_payload_helper_composition"
IMPORTED_STDLIB_HELPER_ENTRY = (
    IMPORTED_STDLIB_HELPER_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)
PURE_EXPR_SELECTOR_FIXTURE = FIXTURES / "valid" / "pure_expr_selector_action_projection.orc"
MATERIALIZE_VIEW_ALLOCATED_TARGET_FIXTURE = FIXTURES / "valid" / "materialize_view_allocated_target.orc"
LEXICAL_CHECKPOINT_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_shadow_points.orc"
LEXICAL_POLICY_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_effect_policies.orc"
LEXICAL_RESTORE_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_restore_regions.orc"
PROCEDURE_IDENTITY_FIXTURE = FIXTURES / "valid" / "procedure_lowering_identity_modes.orc"
RUNTIME_CLOSURE_MARKERS = (
    "workflow_lisp_runtime_closure",
    "closure_families",
    "InvokeClosure",
    "Closure[",
    "runtime_closure",
)


def test_json_data_keeps_plain_return_and_field_dataclasses_legacy_compatible() -> None:
    span = SourceSpan(
        start=SourcePosition(path="plain.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="plain.orc", line=1, column=2, offset=1),
    )
    function_def = FunctionDef(
        name="approved",
        params=(),
        return_type_name="Bool",
        body=True,
        span=span,
        form_path=("workflow-lisp", "defun", "approved"),
    )
    field = RecordField(name="approved", type_name="Bool", span=span)

    function_payload = _build_module()._json_data(function_def)
    field_payload = _build_module()._json_data(field)

    assert function_payload["return_type_name"] == "Bool"
    assert "return_spec" not in function_payload
    assert field_payload == {
        "name": "approved",
        "type_name": "Bool",
        "span": _build_module()._json_data(span),
    }


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")












def _build_request(tmp_path: Path, *, manifest_path: Path | None = None):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return request_cls(
        source_path=ENTRYPOINT,
        source_roots=(SOURCE_ROOT, tmp_path),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=manifest_path or (CLI_FIXTURES / "imported_workflow_bundles.json"),
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _procedure_identity_build_request(tmp_path: Path):
    request_cls = getattr(_build_module(), "FrontendBuildRequest")
    return request_cls(
        source_path=PROCEDURE_IDENTITY_FIXTURE,
        source_roots=(PROCEDURE_IDENTITY_FIXTURE.parent,),
        entry_workflow="orchestrate",
        provider_externs_path=PROCEDURE_IDENTITY_FIXTURE.with_suffix(".providers.json"),
        prompt_externs_path=PROCEDURE_IDENTITY_FIXTURE.with_suffix(".prompts.json"),
        command_boundaries_path=PROCEDURE_IDENTITY_FIXTURE.with_suffix(".commands.json"),
        emit_debug_yaml=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )


def _selected_hook_semantic_ir_request(tmp_path: Path, *, selected_hook: str):
    module_path = tmp_path / "selected" / "hooks.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule selected/hooks)",
                "  (export entry)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (report WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport))",
                "  (defproc run-command",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ((uses-command run_checks))",
                "    :lowering inline",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.report)',
                "      :returns WorkflowOutput))",
                "  (defproc run-provider",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ((uses-provider providers.execute))",
                "    :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input.report)",
                "      :returns WorkflowOutput))",
                "  (defproc invoke-selected",
                "    ((hook ProcRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ()",
                "    :lowering inline",
                "    (hook input))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                f"    (invoke-selected (proc-ref {selected_hook}) input)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    request_cls = getattr(_build_module(), "FrontendBuildRequest")
    return request_cls(
        source_path=module_path,
        source_roots=(tmp_path,),
        entry_workflow="entry",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )


def _imported_stdlib_helper_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return request_cls(
        source_path=IMPORTED_STDLIB_HELPER_ENTRY,
        source_roots=(IMPORTED_STDLIB_HELPER_ROOT,),
        entry_workflow="run-drain-like",
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _design_delta_parent_drain_request(
    tmp_path: Path,
    *,
    command_boundaries_path: Path | None = None,
):
    run_state_path = tmp_path / "state" / "run_state.json"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    if not run_state_path.exists():
        run_state_path.write_text("{}\n", encoding="utf-8")
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return request_cls(
        source_path=REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        entry_workflow="lisp_frontend_design_delta/drain::drain",
        provider_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.providers.json",
        prompt_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=command_boundaries_path
        or (DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"),
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )




def _build_pure_expr_selector_projection(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=PURE_EXPR_SELECTOR_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_materialize_view_allocated_target(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=MATERIALIZE_VIEW_ALLOCATED_TARGET_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_lexical_checkpoint_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=LEXICAL_CHECKPOINT_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_lexical_policy_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=LEXICAL_POLICY_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_lexical_restore_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=LEXICAL_RESTORE_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


































































def _validate_review_findings_retirement_metadata() -> dict[str, object]:
    return {
        "retirement_class": "validation",
        "retirement_label": "keep_bridge",
        "replacement_surface": "typed review findings validation bridge",
        "bridge_owner": "std/phase",
        "expiry_condition": (
            "retain until typed review-findings validation parity replaces the command bridge"
        ),
        "evidence_refs": ("validate_review_findings_v1",),
    }




def _write_structured_results_module(tmp_path: Path) -> Path:
    package_dir = tmp_path / "lineage_pkg"
    package_dir.mkdir(parents=True, exist_ok=True)
    module_path = package_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lineage_pkg/entry)",
                "  (export command_checks provider_attempt orchestrate)",
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow command_checks",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult))",
                "  (defworkflow provider_attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary :report blocked.progress_report)))))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call provider_attempt",
                "      :input input",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return module_path

def _structured_results_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = _write_structured_results_module(tmp_path)
    return request_cls(
        source_path=module_path,
        source_roots=(tmp_path,),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _selector_projection_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    providers_path = tmp_path / "selector_providers.json"
    prompts_path = tmp_path / "selector_prompts.json"
    commands_path = tmp_path / "selector_commands.json"
    providers_path.write_text(
        json.dumps({"providers.selector": "codex"}, indent=2) + "\n",
        encoding="utf-8",
    )
    prompts_path.write_text(
        json.dumps(
            {
                "prompts.selector.select-next-work": (
                    "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
                )
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    commands_path.write_text(
        json.dumps(
            {
                "validate_review_findings_v1": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "-m",
                        "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                    ],
                    **_validate_review_findings_retirement_metadata(),
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return request_cls(
        source_path=REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "selector.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        entry_workflow="select-next-work",
        provider_externs_path=providers_path,
        prompt_externs_path=prompts_path,
        imported_workflow_bundles_path=None,
        command_boundaries_path=commands_path,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )














def _resume_entry_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    fixture_root = FIXTURES / "modules" / "valid" / "callables"
    fixture = fixture_root / "neurips" / "helper.orc"
    return request_cls(
        source_path=fixture,
        source_roots=(fixture_root,),
        entry_workflow="provider-attempt",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _write_workflow_param_default_module(tmp_path: Path) -> Path:
    package_dir = tmp_path / "defaults_pkg"
    package_dir.mkdir(parents=True, exist_ok=True)
    module_path = package_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule defaults_pkg/entry)",
                "  (export defaults)",
                "  (defenum Status",
                "    ready",
                "    blocked)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord Summary",
                "    (report WorkReport))",
                "  (defworkflow defaults",
                '    ((message String :default "hello")',
                "     (count Int :default 3)",
                "     (score Float :default 0.5)",
                "     (enabled Bool :default true)",
                "     (status Status :default ready)",
                '     (report_path WorkReport :default "default.md"))',
                "    -> Summary",
                "    (record Summary :report report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return module_path


def _workflow_param_default_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = _write_workflow_param_default_module(tmp_path)
    return request_cls(
        source_path=module_path,
        source_roots=(tmp_path,),
        entry_workflow="defaults",
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )


def _lint_warning_variant_output_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = FIXTURES / "valid" / "lint_warning_variant_output.orc"
    return request_cls(
        source_path=module_path,
        source_roots=(FIXTURES / "valid",),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _pointer_effects_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = FIXTURES / "valid" / "pointer_materialization_effects.orc"
    return request_cls(
        source_path=module_path,
        source_roots=(FIXTURES / "valid",),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _thaw_source_map_value(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _thaw_source_map_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _thaw_source_map_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_source_map_value(item) for item in value]
    return value


def _same_file_wcc_m3_source_map_payload(
    tmp_path: Path,
    *,
    fixture_path: Path,
    module_filename: str,
    selected_name: str,
) -> dict[str, object]:
    module_path = tmp_path / module_filename
    module_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")
    graph = resolve_module_graph(module_path, source_roots=(tmp_path,))
    compile_result = workflow_lisp_compiler._compile_stage3_graph(
        graph,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        imported_workflow_bundles=None,
        command_boundaries=None,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=workflow_lisp_compiler.normalize_lowering_route("wcc_m3"),
        entry_workflow=selected_name,
    )
    source_map = build_source_map_document(
        compile_result,
        selected_name=selected_name,
        display_name_resolver=lambda workflow_name: workflow_name.split("::")[-1],
    )
    return _thaw_source_map_value(source_map)


def _route_neutral_wcc_m4_source_map_payload(tmp_path: Path) -> dict[str, object]:
    fixture_path = FIXTURES / "valid" / "loop_recur_on_exhausted_union.orc"
    module_text = fixture_path.read_text(encoding="utf-8").replace(
        '  (:target-dsl "2.14")\n',
        '  (:target-dsl "2.14")\n'
        "  (defmodule route_neutral_loop)\n"
        "  (export loop-recur-on-exhausted-union)\n",
        1,
    )
    module_path = tmp_path / "route_neutral_loop.orc"
    module_path.write_text(module_text, encoding="utf-8")
    graph = resolve_module_graph(module_path, source_roots=(tmp_path,))
    compile_result = workflow_lisp_compiler._compile_stage3_graph(
        graph,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        imported_workflow_bundles=None,
        command_boundaries=None,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=workflow_lisp_compiler.normalize_lowering_route("wcc_m4"),
        entry_workflow="route_neutral_loop::loop-recur-on-exhausted-union",
    )
    source_map = build_source_map_document(
        compile_result,
        selected_name="route_neutral_loop::loop-recur-on-exhausted-union",
        display_name_resolver=lambda workflow_name: workflow_name.split("::")[-1],
    )
    return _thaw_source_map_value(source_map)


def _wcc_m4_full_fixture_source_map_payload(tmp_path: Path) -> dict[str, object]:
    fixture_path = FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc"
    compile_result = compile_stage3_entrypoint(
        fixture_path,
        source_roots=(fixture_path.parent,),
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
                **_validate_review_findings_retirement_metadata(),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    source_map = build_source_map_document(
        compile_result,
        selected_name="wcc_m4_implementation_phase_full_fixture::run",
        display_name_resolver=lambda workflow_name: workflow_name.split("::")[-1],
    )
    return _thaw_source_map_value(source_map)


def _workflow_public_input_contracts(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_public_input_contracts",
        loaded_bundle_helpers.workflow_input_contracts,
    )
    return helper(bundle)


def _workflow_runtime_input_contracts(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_input_contracts",
        loaded_bundle_helpers.workflow_input_contracts,
    )
    return helper(bundle)


def _workflow_runtime_context_inputs(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_context_inputs",
        lambda _: (),
    )
    return helper(bundle)


def _workflow_boundary_projection(bundle):
    helper = getattr(loaded_bundle_helpers, "workflow_boundary_projection")
    return helper(bundle)


def _workflow_payload_by_suffix(payload: dict[str, object], workflow_suffix: str) -> dict[str, object]:
    workflows = payload["workflows"]
    assert isinstance(workflows, list)
    return next(
        workflow
        for workflow in workflows
        if isinstance(workflow, dict) and str(workflow.get("workflow_name", "")).endswith(f"::{workflow_suffix}")
    )


def _allocation_payload_by_role(payload: list[dict[str, object]], semantic_role: str) -> dict[str, object]:
    return next(
        allocation
        for allocation in payload
        if isinstance(allocation, dict) and allocation.get("semantic_role") == semantic_role
    )


def _certified_resolve_plan_gate_binding() -> CertifiedAdapterBinding:
    return CertifiedAdapterBinding(
        name="resolve_plan_gate",
        stable_command=("python", "scripts/resolve_plan_gate.py"),
        input_contract={"type": "object"},
        output_type_name="PlanGateResult",
        effects=("structured_result",),
        path_safety={"kind": "workspace_relpath"},
        source_map_behavior="step",
        fixture_ids=("resolve_plan_gate_ok",),
        negative_fixture_ids=("resolve_plan_gate_bad",),
    )


def _resume_or_start_command_boundaries() -> dict[str, CertifiedAdapterBinding]:
    return {
        "resolve_plan_gate": _certified_resolve_plan_gate_binding(),
        "validate_reusable_phase_state": CertifiedAdapterBinding(
            name="validate_reusable_phase_state",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
            ),
            input_contract={"type": "object"},
            output_type_name="ResumeReuseDecision",
            effects=("resume_state_reuse", "structured_result"),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resume_state_reuse_valid",),
            negative_fixture_ids=(
                "resume_state_pointer_authority_forbidden",
                "resume_state_contract_fingerprint_mismatch",
                "resume_state_bundle_schema_invalid",
            ),
            behavior_class="resume_state_reuse",
            owner_module="std/phase",
            replacement_path="resume-or-start",
        ),
        "write_reusable_phase_state_v1": CertifiedAdapterBinding(
            name="write_reusable_phase_state_v1",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
            ),
            input_contract={"type": "object"},
            output_type_name="ReusablePhaseStateWriteAck",
            effects=("resume_state_reuse", "structured_result"),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resume_state_write_v1",),
            negative_fixture_ids=(
                "resume_state_path_unsafe",
                "resume_state_required_artifact_missing",
            ),
            behavior_class="resume_state_reuse",
            owner_module="std/phase",
            replacement_path="resume-or-start",
        ),
        "load_canonical_phase_result__PlanGateResult": CertifiedAdapterBinding(
            name="load_canonical_phase_result__PlanGateResult",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
            ),
            input_contract={"type": "object"},
            output_type_name="PlanGateResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resume_state_load_PlanGateResult",),
            negative_fixture_ids=("resume_state_loader_schema_invalid",),
            behavior_class="resume_state_reuse",
            owner_module="std/phase",
            replacement_path="resume-or-start",
        ),
        "load_canonical_phase_result__PlanGateWrapperResult": CertifiedAdapterBinding(
            name="load_canonical_phase_result__PlanGateWrapperResult",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
            ),
            input_contract={"type": "object"},
            output_type_name="PlanGateWrapperResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resume_state_load_PlanGateWrapperResult",),
            negative_fixture_ids=("resume_state_loader_schema_invalid",),
            behavior_class="resume_state_reuse",
            owner_module="std/phase",
            replacement_path="resume-or-start",
        ),
    }


def _compile_resume_fixture(tmp_path: Path):
    fixture = FIXTURES / "valid" / "phase_stdlib_resume_or_start.orc"
    return compile_stage3_module(
        fixture,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
            **_resume_or_start_command_boundaries(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _assert_no_runtime_closure_markers(serialized: str) -> None:
    for marker in RUNTIME_CLOSURE_MARKERS:
        assert marker not in serialized


def test_build_fingerprint_is_stable_for_identical_inputs(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    first = build_frontend_bundle(_build_request(tmp_path))
    second = build_frontend_bundle(_build_request(tmp_path))

    assert first.manifest.fingerprint == second.manifest.fingerprint
    assert first.build_root == second.build_root


def test_build_fingerprint_changes_when_imported_bundle_manifest_changes(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    alternate_bundle = tmp_path / "selector_alt.yaml"
    alternate_bundle.write_text(
        (CLI_FIXTURES / "imported_selector.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    alternate_manifest = tmp_path / "imported_workflow_bundles.alt.json"
    alternate_manifest.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "yaml",
                    "path": str(alternate_bundle),
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original = build_frontend_bundle(_build_request(tmp_path))
    alternate = build_frontend_bundle(_build_request(tmp_path, manifest_path=alternate_manifest))

    assert original.manifest.fingerprint != alternate.manifest.fingerprint


def test_build_fingerprint_normalizes_alias_and_canonical_entry_workflow(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    alias_result = build_frontend_bundle(_build_request(tmp_path))
    canonical_request = _build_request(tmp_path)
    canonical_request = type(canonical_request)(
        **{
            **canonical_request.__dict__,
            "entry_workflow": "neurips/entry::orchestrate",
        }
    )
    canonical_result = build_frontend_bundle(canonical_request)

    assert alias_result.entry_selection.canonical_name == "neurips/entry::orchestrate"
    assert canonical_result.entry_selection.canonical_name == "neurips/entry::orchestrate"
    assert alias_result.manifest.fingerprint == canonical_result.manifest.fingerprint


def test_build_fingerprint_changes_when_command_boundary_manifest_changes(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    alternate_manifest = tmp_path / "commands.alt.json"
    alternate_manifest.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original = build_frontend_bundle(_build_request(tmp_path))
    alternate_request = _build_request(tmp_path)
    alternate_request = type(alternate_request)(
        **{
            **alternate_request.__dict__,
            "command_boundaries_path": alternate_manifest,
        }
    )
    alternate = build_frontend_bundle(alternate_request)

    assert original.manifest.fingerprint != alternate.manifest.fingerprint


def test_parse_command_boundary_manifest_accepts_promoted_certified_adapter_metadata() -> None:
    build = _build_module()
    parse_manifest = getattr(build, "_parse_command_boundaries_manifest")

    bindings = parse_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "execution_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "execution_report",
                    },
                    {
                        "name": "review_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "review_report",
                    },
                ],
                "artifact_contracts": ["implementation_summary_report"],
                "state_writes": [],
                "error_codes": ["normalize_result_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    binding = bindings["normalize_result"]

    assert binding.behavior_class == "structured_result"
    assert binding.invocation_protocol == "json_object_positional_arg"
    assert tuple(field.transport_key for field in binding.input_signature) == (
        "execution_report",
        "review_report",
    )


def test_parse_command_boundary_manifest_keeps_legacy_certified_adapter_argv_compatibility() -> None:
    build = _build_module()
    parse_manifest = getattr(build, "_parse_command_boundaries_manifest")

    bindings = parse_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
            }
        },
        manifest_path=None,
    )

    binding = bindings["normalize_result"]

    assert binding.output_type_name == "ImplementationSummary"
    assert binding.stable_command == ("python", "scripts/normalize_result.py")


def test_build_fingerprint_changes_when_promoted_adapter_metadata_changes(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    first_manifest = tmp_path / "commands.promoted.first.json"
    second_manifest = tmp_path / "commands.promoted.second.json"
    first_manifest.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                },
                "normalize_result": {
                    "kind": "certified_adapter",
                    "stable_command": ["python", "scripts/normalize_result.py"],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ImplementationSummary",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["normalize_result_ok"],
                    "negative_fixture_ids": ["normalize_result_bad"],
                    "behavior_class": "structured_result",
                    "input_signature": [
                        {
                            "name": "execution_report",
                            "type_name": "WorkReport",
                            "required": True,
                            "transport_key": "execution_report",
                        }
                    ],
                    "artifact_contracts": ["implementation_summary_report"],
                    "state_writes": [],
                    "error_codes": ["normalize_result_invalid_payload"],
                    "owner_module": "std/phase",
                    "replacement_path": None,
                    "invocation_protocol": "json_object_positional_arg",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    second_manifest.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                },
                "normalize_result": {
                    "kind": "certified_adapter",
                    "stable_command": ["python", "scripts/normalize_result.py"],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ImplementationSummary",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["normalize_result_ok"],
                    "negative_fixture_ids": ["normalize_result_bad"],
                    "behavior_class": "structured_result",
                    "input_signature": [
                        {
                            "name": "execution_report",
                            "type_name": "WorkReport",
                            "required": True,
                            "transport_key": "execution_report_path",
                        }
                    ],
                    "artifact_contracts": ["implementation_summary_report"],
                    "state_writes": [],
                    "error_codes": ["normalize_result_invalid_payload"],
                    "owner_module": "std/phase",
                    "replacement_path": None,
                    "invocation_protocol": "json_object_positional_arg",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    first_request = _build_request(tmp_path)
    first_request = type(first_request)(
        **{
            **first_request.__dict__,
            "command_boundaries_path": first_manifest,
        }
    )
    second_request = _build_request(tmp_path)
    second_request = type(second_request)(
        **{
            **second_request.__dict__,
            "command_boundaries_path": second_manifest,
        }
    )

    first = build_frontend_bundle(first_request)
    second = build_frontend_bundle(second_request)

    assert first.manifest.fingerprint != second.manifest.fingerprint


def test_build_accepts_compiled_imported_workflow_bundles_manifest_and_public_runtime_input_projections(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    compiled_selector = tmp_path / "compiled" / "selector.orc"
    compiled_selector.parent.mkdir(parents=True, exist_ok=True)
    compiled_selector.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule compiled/selector)",
                "  (export selector-run)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow selector-run",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input report_path)",
                "      :returns ImplementationSummary)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compiled_manifest = tmp_path / "imported_workflow_bundles.compiled.json"
    compiled_manifest.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": str(compiled_selector),
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_frontend_bundle(_build_request(tmp_path, manifest_path=compiled_manifest))

    assert result.imported_workflow_bundles[0].bundle_kind == "compiled"
    assert result.imported_workflow_bundles[0].workflow_name == "compiled/selector::selector-run"
    assert result.imported_workflow_bundles[0].bundle.ir.schema_version == "workflow_executable_ir.v1"
    assert result.imported_workflow_bundles[0].bundle.runtime_plan.schema_version == "workflow_runtime_plan.v1"
    bundle = result.imported_workflow_bundles[0].bundle
    assert workflow_managed_write_root_inputs(bundle) == (
        "__write_root__compiled_selector_selector_run__result__result_bundle",
    )
    assert "__write_root__compiled_selector_selector_run__result__result_bundle" not in _workflow_public_input_contracts(
        bundle
    )
    assert "__write_root__compiled_selector_selector_run__result__result_bundle" in _workflow_runtime_input_contracts(
        bundle
    )


@pytest.mark.parametrize(
    ("request_field", "file_name", "payload", "expected_message"),
    [
        (
            "provider_externs_path",
            "providers.invalid-entry.json",
            {"providers.execute": {"bad": True}},
            "provider externs manifest entries must map non-empty string names to string values",
        ),
        (
            "prompt_externs_path",
            "prompts.invalid-entry.json",
            {"prompts.implementation.execute": {"bad": True}},
            (
                "prompt externs manifest entries must map non-empty string names to string values "
                "or objects with exactly one of `asset_file` or `input_file`"
            ),
        ),
    ],
)
def test_build_rejects_non_string_extern_manifest_entries(
    tmp_path: Path,
    request_field: str,
    file_name: str,
    payload: dict[str, object],
    expected_message: str,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    manifest_path = tmp_path / file_name
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    request = _build_request(tmp_path)
    request = type(request)(**{**request.__dict__, request_field: manifest_path})

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(request)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_lisp_manifest_invalid"
    assert diagnostic.message == expected_message


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (
            {"run_checks": 5},
            "manifest entry for `run_checks` must be a JSON object",
        ),
        (
            {"run_checks": {"kind": "external_tool", "stable_command": 5}},
            "`stable_command` for `run_checks` must be an array of strings",
        ),
    ],
)
def test_build_rejects_invalid_command_boundary_manifest_entries(
    tmp_path: Path,
    payload: dict[str, object],
    expected_message: str,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    manifest_path = tmp_path / "commands.invalid-entry.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    request = _build_request(tmp_path)
    request = type(request)(**{**request.__dict__, "command_boundaries_path": manifest_path})

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(request)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "command_boundary_manifest_invalid"
    assert diagnostic.message == expected_message


def test_build_emits_required_artifacts_and_emitted_status_entries(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_build_request(tmp_path))
    core_workflow_ast = json.loads(result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    runtime_plan = json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8"))

    expected_artifacts = {
        "manifest.json",
        "frontend_ast.json",
        "expanded_frontend_ast.json",
        "typed_frontend_ast.json",
        "lowered_workflows.json",
        "executable_ir.json",
        "core_workflow_ast.json",
        "semantic_ir.json",
        "runtime_plan.json",
        "source_map.json",
        "workflow_boundary_projection.json",
        "diagnostics.json",
    }

    assert expected_artifacts.issubset({path.name for path in result.artifact_paths.values()})
    assert executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert runtime_plan["schema_version"] == "workflow_runtime_plan.v1"
    assert result.artifact_paths["core_workflow_ast"].name == "core_workflow_ast.json"
    assert result.artifact_paths["semantic_ir"].name == "semantic_ir.json"
    assert result.artifact_paths["runtime_plan"].name == "runtime_plan.json"
    assert result.manifest.artifact_paths["runtime_plan"].endswith("/runtime_plan.json")
    assert result.manifest.artifact_status["executable_ir"] == "emitted"
    assert result.manifest.artifact_status["runtime_plan"] == "emitted"
    assert result.manifest.artifact_status["core_workflow_ast"] == "emitted"
    assert result.manifest.artifact_status["semantic_ir"] == "emitted"
    _assert_no_runtime_closure_markers(json.dumps(core_workflow_ast, sort_keys=True))
    _assert_no_runtime_closure_markers(json.dumps(semantic_ir, sort_keys=True))
    _assert_no_runtime_closure_markers(json.dumps(executable_ir, sort_keys=True))
    _assert_no_runtime_closure_markers(json.dumps(runtime_plan, sort_keys=True))


def test_typed_frontend_ast_records_resolved_procedure_lowering(tmp_path: Path) -> None:
    result = _build_module().build_frontend_bundle(
        _procedure_identity_build_request(tmp_path)
    )
    payload = json.loads(
        result.artifact_paths["typed_frontend_ast"].read_text(encoding="utf-8")
    )
    rows = payload["modules"]["procedure_lowering_identity_modes"]["typed_procedures"]
    artifact_by_name = {row["definition"]["name"]: row for row in rows}

    assert set(artifact_by_name) == {
        procedure.definition.name
        for procedure in result.compile_result.entry_result.typed_procedures
    }
    expected_modes = {
        "inline-plan": ("inline", None),
        "private-helper": (
            "private-workflow",
            "%procedure_lowering_identity_modes.procedure_lowering_identity_modes::private-helper.v1",
        ),
        "auto-helper": (
            "private-workflow",
            "%procedure_lowering_identity_modes.procedure_lowering_identity_modes::auto-helper.v1",
        ),
    }
    for procedure in result.compile_result.entry_result.typed_procedures:
        artifact = artifact_by_name[procedure.definition.name]
        assert artifact["signature"]["requested_lowering_mode"] == (
            procedure.signature.requested_lowering_mode.value
        )
        assert artifact["resolved_lowering_mode"] == procedure.resolved_lowering_mode.value
        assert artifact["generated_workflow_name"] == procedure.generated_workflow_name
        short_name = procedure.definition.name.rsplit("::", 1)[-1]
        assert (
            artifact["resolved_lowering_mode"],
            artifact["generated_workflow_name"],
        ) == expected_modes[short_name]


def test_build_artifacts_persist_diagnostic_validation_metadata(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    write_build_artifacts = getattr(build, "_write_build_artifacts")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    artifact_root = tmp_path / "diagnostic_artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    diagnostic = LispFrontendDiagnostic(
        code="source_map_executable_node_unmapped",
        message="executable node `run__step` does not resolve to a declared origin",
        span=SourceSpan(
            start=SourcePosition(path="lineage_pkg/entry.orc", line=24, column=3, offset=0),
            end=SourcePosition(path="lineage_pkg/entry.orc", line=24, column=18, offset=15),
        ),
        validation_pass="executable",
        authority_layer="frontend",
    )

    artifact_paths = write_build_artifacts(
        build_root=artifact_root,
        compile_result=result.compile_result,
        validated_bundle=result.validated_bundle,
        entry_selection=result.entry_selection,
        diagnostics=(diagnostic,),
        emit_debug_yaml=False,
        source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        workflow_boundary_projection_payload=json.loads(
            result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
        ),
    )
    payload = json.loads(artifact_paths["diagnostics"].read_text(encoding="utf-8"))

    assert payload == [
        {
            "authority_layer": "frontend",
            "code": "source_map_executable_node_unmapped",
            "column": 3,
            "diagnostic_kind": "validation",
            "expansion_stack": [],
            "form_path": [],
            "line": 24,
            "message": "executable node `run__step` does not resolve to a declared origin",
            "notes": [],
            "path": "lineage_pkg/entry.orc",
            "phase": "executable",
            "severity": "error",
            "validation_pass": "executable",
        }
    ]


def test_build_persists_warning_lints_in_diagnostics_artifact_on_success(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_lint_warning_variant_output_request(tmp_path))
    payload = json.loads(result.artifact_paths["diagnostics"].read_text(encoding="utf-8"))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "variant_output_without_variant_specific_fields",
    ]
    assert payload == [
        {
            "authority_layer": "frontend",
            "code": "variant_output_without_variant_specific_fields",
            "column": 3,
            "diagnostic_kind": "required_lint",
            "expansion_stack": [],
            "form_path": ["workflow-lisp", "defworkflow", "orchestrate"],
            "line": 18,
            "message": "union `ImplementationAttempt` lowers without variant-specific fields; prefer a record plus enum",
            "notes": [],
            "path": str((FIXTURES / "valid" / "lint_warning_variant_output.orc").resolve()),
            "phase": "typecheck",
            "severity": "warn",
            "validation_pass": "contract",
        }
    ]






def test_build_runtime_plan_artifact_matches_selected_workflow_lineage_and_manifest(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    runtime_plan = json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    selected_workflow = result.validated_bundle.surface.name
    runtime_plan_node_ids = set(runtime_plan["nodes"])
    executable_ir_node_ids = set(executable_ir["nodes"])
    source_map_node_ids = {
        node["node_id"]
        for node in source_map["workflows"][selected_workflow]["executable_nodes"]
    }

    assert executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert runtime_plan["schema_version"] == "workflow_runtime_plan.v1"
    assert runtime_plan["workflow_name"] == selected_workflow
    assert semantic_ir["schema_version"] == "workflow_semantic_ir.v1"
    assert semantic_ir["workflows"][selected_workflow]["workflow_name"] == selected_workflow
    assert json.loads(result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))["schema_version"] == (
        "core_workflow_ast.v1"
    )
    assert executable_ir_node_ids == runtime_plan_node_ids
    assert runtime_plan_node_ids == source_map_node_ids
    assert result.manifest.artifact_paths["runtime_plan"].endswith("/runtime_plan.json")
    assert result.manifest.artifact_status["executable_ir"] == "emitted"
    assert result.manifest.artifact_status["runtime_plan"] == "emitted"
    assert result.manifest.artifact_status["core_workflow_ast"] == "emitted"
    assert result.manifest.artifact_status["semantic_ir"] == "emitted"


def test_prompt_extern_object_entries_are_accepted_by_build_service(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    asset_result = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.asset-file-object.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "asset",
        )
    )
    input_result = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.input-file.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "input",
        )
    )

    asset_binding = asset_result.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]
    input_binding = input_result.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]

    assert asset_binding.source_kind == "asset_file"
    assert asset_binding.path == "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
    assert asset_binding.asset_file == "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
    assert input_binding.source_kind == "input_file"
    assert input_binding.path == "prompts/workspace/implementation/execute.md"
    assert input_binding.asset_file is None


def test_prompt_extern_asset_file_shorthand_normalization_in_build_service(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    shorthand = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "shorthand",
        )
    )
    explicit = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.asset-file-object.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "explicit",
        )
    )

    shorthand_binding = shorthand.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]
    explicit_binding = explicit.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]

    assert shorthand_binding.source_kind == explicit_binding.source_kind == "asset_file"
    assert shorthand_binding.path == explicit_binding.path
    assert shorthand_binding.asset_file == explicit_binding.asset_file


def test_prompt_extern_asset_file_shorthand_normalization_stabilizes_fingerprint_and_producer_context(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    derive_context = getattr(compiler, "_derive_reusable_state_producer_context")

    shorthand = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "shorthand-fingerprint",
        )
    )
    explicit = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.asset-file-object.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "explicit-fingerprint",
        )
    )

    stage1 = compile_stage1_entrypoint(ENTRYPOINT, source_roots=(SOURCE_ROOT,))
    command_env = build_command_boundary_environment(
        {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        }
    )
    shorthand_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )
    explicit_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": {"asset_file": "prompts/implementation/execute.md"}},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )

    assert shorthand.manifest.fingerprint == explicit.manifest.fingerprint
    assert shorthand_context["compile_inputs_fingerprint"] == explicit_context["compile_inputs_fingerprint"]


def test_prompt_extern_object_entries_emit_source_kind_aware_reusable_state_metadata() -> None:
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    derive_context = getattr(compiler, "_derive_reusable_state_producer_context")
    stage1 = compile_stage1_entrypoint(ENTRYPOINT, source_roots=(SOURCE_ROOT,))
    command_env = build_command_boundary_environment(
        {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        }
    )

    asset_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": {"asset_file": "prompts/implementation/execute.md"}},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )
    input_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": {"input_file": "prompts/workspace/implementation/execute.md"}},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )

    assert asset_context["prompt_extern_bindings"] == {
        "prompts.implementation.execute": "prompts/implementation/execute.md"
    }
    assert asset_context["prompt_extern_source_bindings"] == {
        "prompts.implementation.execute": {"asset_file": "prompts/implementation/execute.md"}
    }
    assert input_context["prompt_extern_bindings"] == {}
    assert input_context["prompt_extern_source_bindings"] == {
        "prompts.implementation.execute": {"input_file": "prompts/workspace/implementation/execute.md"}
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "prompts.implementation.execute": {
                "asset_file": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
                "input_file": "prompts/workspace/implementation/execute.md",
            }
        },
        {
            "prompts.implementation.execute": {
                "source_kind": "input_file",
                "path": "prompts/workspace/implementation/execute.md",
            }
        },
        {"prompts.implementation.execute": {"unknown": "value"}},
        {"prompts.implementation.execute": {"asset_file": 5}},
    ],
)
def test_prompt_extern_object_shape_invalid_diagnostic(tmp_path: Path, payload: dict[str, object]) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    manifest_path = tmp_path / "prompts.invalid-object.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(
            request_cls(
                source_path=ENTRYPOINT,
                source_roots=(SOURCE_ROOT,),
                entry_workflow="orchestrate",
                provider_externs_path=CLI_FIXTURES / "providers.json",
                prompt_externs_path=manifest_path,
                imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
                command_boundaries_path=CLI_FIXTURES / "commands.json",
                emit_debug_yaml=False,
                workspace_root=tmp_path,
            )
        )

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_invalid"
    assert "prompt externs manifest entries" in excinfo.value.diagnostics[0].message


def test_build_artifacts_emit_private_artifact_catalog(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc",
            source_roots=(REPO_ROOT / "workflows" / "examples",),
            entry_workflow="review-revise-design-docs",
            provider_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "providers.json"
            ),
            prompt_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "prompts.json"
            ),
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))

    assert executable_ir["private_artifacts"] == {}


def test_semantic_ir_private_artifact_catalog_bridge(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc",
            source_roots=(REPO_ROOT / "workflows" / "examples",),
            entry_workflow="review-revise-design-docs",
            provider_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "providers.json"
            ),
            prompt_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "prompts.json"
            ),
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))

    assert result.validated_bundle.ir.private_artifacts == {}
    assert executable_ir["private_artifacts"] == {}
    assert semantic_ir["workflows"][result.selected_workflow_name]["workflow_name"] == result.selected_workflow_name


def test_build_manifest_records_source_map_schema_and_coverage_for_emitted_artifacts(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))

    assert result.manifest.source_map_schema_version == "workflow_lisp_source_map.v1"
    assert result.manifest.source_map_coverage == {
        "frontend_ast": "covered",
        "lowered_surface": "covered",
        "shared_validation_subjects": "covered",
        "executable_ir": "covered",
        "runtime_logs": "covered",
        "core_workflow_ast": "covered",
        "semantic_ir": "covered",
    }


def test_build_artifacts_preserve_statement_taxonomy_facet_lineage(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    structured_result = build_frontend_bundle(_structured_results_request(tmp_path))
    structured_core = json.loads(structured_result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    structured_semantic = json.loads(structured_result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    structured_source_map = json.loads(structured_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    structured_workflow = structured_result.entry_selection.canonical_name
    command_checks_workflow = "lineage_pkg/entry::command_checks"

    assert [statement["kind"] for statement in structured_core["body"]] == ["call"]
    assert structured_semantic["workflows"][structured_workflow]["call_edge_ids"]
    assert structured_source_map["workflows"][command_checks_workflow]["generated_internal_inputs"]

    snapshot_source = (FIXTURES / "valid" / "phase_snapshot_effects.orc").read_text(encoding="utf-8")
    snapshot_module_path = tmp_path / "phase" / "snapshot.orc"
    snapshot_module_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_module_path.write_text(
        snapshot_source.replace(
            '  (defmodule phase_snapshot_effects)\n',
            '  (defmodule phase/snapshot)\n',
            1,
        ),
        encoding="utf-8",
    )
    snapshot_result = build_frontend_bundle(
        request_cls(
            source_path=snapshot_module_path,
            source_roots=(tmp_path,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    snapshot_core = json.loads(snapshot_result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    snapshot_semantic = json.loads(snapshot_result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    snapshot_source_map = json.loads(snapshot_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    snapshot_workflow = snapshot_result.entry_selection.canonical_name
    snapshot_effect_kinds = {
        effect["effect_kind"]
        for effect in snapshot_semantic["effects"].values()
    }

    assert "select_variant_output" in [statement["kind"] for statement in snapshot_core["body"]]
    assert {"pointer_materialization", "snapshot_capture"}.issubset(snapshot_effect_kinds)
    assert any(
        effect["effect_kind"] == "snapshot_capture"
        for effect in snapshot_source_map["workflows"][snapshot_workflow]["generated_semantic_effects"]
    )
    assert any(
        node["step_kind"] == "select_variant_output"
        for node in snapshot_source_map["workflows"][snapshot_workflow]["core_nodes"]
    )

    resource_source = (FIXTURES / "valid" / "resource_stdlib_transition.orc").read_text(encoding="utf-8")
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
    resource_result = build_frontend_bundle(
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
            lowering_route=LoweringRoute.LEGACY,
        )
    )
    resource_core = json.loads(resource_result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    resource_semantic = json.loads(resource_result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    resource_source_map = json.loads(resource_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    resource_workflow = resource_result.entry_selection.canonical_name

    assert [statement["kind"] for statement in resource_core["body"]] == ["command"]
    assert any(
        boundary["boundary_kind"] == "certified_adapter"
        and boundary["boundary_name"] == "apply_resource_transition"
        for boundary in resource_semantic["command_boundaries"].values()
    )
    assert {
        effect["effect_kind"]
        for effect in resource_semantic["effects"].values()
    } >= {"command_call", "resource_transition", "ledger_update"}
    assert resource_source_map["workflows"][resource_workflow]["command_boundaries"]


def test_build_semantic_ir_uses_current_source_map_validation_subject_bridges(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    first = build_frontend_bundle(_build_request(tmp_path))
    selected_workflow = first.entry_selection.canonical_name

    def validation_subject_names(result) -> set[tuple[str, str]]:
        source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
        return {
            (
                binding["subject_ref"]["subject_kind"],
                binding["subject_ref"]["subject_name"],
            )
            for binding in source_map["workflows"][selected_workflow]["validation_subjects"]
        }

    def semantic_ir_subject_names(result) -> set[tuple[str, str]]:
        semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
        return {
            (
                entry["subject_ref"]["subject_kind"],
                entry["subject_ref"]["subject_name"],
            )
            for entry in semantic_ir["source_map"].values()
            if entry["bridge_kind"] == "validation_subject" and entry["workflow_name"] == selected_workflow
        }

    assert semantic_ir_subject_names(first) == validation_subject_names(first)

    stale_source_map = json.loads(first.artifact_paths["source_map"].read_text(encoding="utf-8"))
    stale_source_map["workflows"][selected_workflow]["validation_subjects"] = stale_source_map["workflows"][
        selected_workflow
    ]["validation_subjects"][:1]
    first.artifact_paths["source_map"].write_text(
        json.dumps(stale_source_map, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    second = build_frontend_bundle(_build_request(tmp_path))

    assert semantic_ir_subject_names(second) == validation_subject_names(second)


def test_export_request_normalization_resolves_default_and_explicit_destinations(tmp_path: Path) -> None:
    build = _build_module()
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")

    requests = normalize_exports(
        {
            "executable_ir": [None],
            "core_workflow_ast": [None],
            "runtime_plan": ["exports/runtime/runtime_plan.snapshot.json"],
            "semantic_ir": ["exports/semantic_ir.snapshot.json"],
            "source_map": [None],
        },
        cwd=tmp_path,
        source_path=ENTRYPOINT,
    )

    assert requests["executable_ir"].destination == (tmp_path / "executable_ir.json").resolve()
    assert requests["core_workflow_ast"].destination == (tmp_path / "core_workflow_ast.json").resolve()
    assert requests["runtime_plan"].destination == (
        tmp_path / "exports" / "runtime" / "runtime_plan.snapshot.json"
    ).resolve()
    assert requests["semantic_ir"].destination == (tmp_path / "exports" / "semantic_ir.snapshot.json").resolve()
    assert requests["source_map"].destination == (tmp_path / "source_map.json").resolve()
    assert (tmp_path / "exports").is_dir()


def test_export_request_normalization_rejects_duplicate_requests(tmp_path: Path) -> None:
    build = _build_module()
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        normalize_exports(
            {
                "core_workflow_ast": [None, "exports/core_workflow_ast.json"],
            },
            cwd=tmp_path,
            source_path=ENTRYPOINT,
        )

    assert excinfo.value.diagnostics[0].phase == "cli_request"
    assert "requested more than once" in excinfo.value.diagnostics[0].message


def test_export_request_normalization_rejects_existing_directory_destination(tmp_path: Path) -> None:
    build = _build_module()
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")
    destination = tmp_path / "exports"
    destination.mkdir()

    with pytest.raises(LispFrontendCompileError) as excinfo:
        normalize_exports(
            {
                "semantic_ir": ["exports"],
            },
            cwd=tmp_path,
            source_path=ENTRYPOINT,
        )

    assert excinfo.value.diagnostics[0].phase == "cli_request"
    assert "existing directory" in excinfo.value.diagnostics[0].message


def test_exported_artifacts_copy_canonical_bytes_without_mutating_manifest_or_canonical_paths(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    emit_exports = getattr(build, "emit_requested_frontend_artifact_exports")
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")

    request = replace(_build_request(tmp_path), emit_debug_yaml=True)
    result = build_frontend_bundle(request)
    original_manifest_paths = dict(result.manifest.artifact_paths)
    original_artifact_paths = dict(result.artifact_paths)
    export_requests = normalize_exports(
        {
            "executable_ir": ["exports/runtime/executable_ir.json"],
            "core_workflow_ast": ["exports/core/core_workflow_ast.json"],
            "runtime_plan": ["exports/runtime/runtime_plan.json"],
            "semantic_ir": ["exports/semantic/semantic_ir.json"],
            "source_map": ["exports/maps/source_map.json"],
            "expanded_debug_yaml": ["exports/debug/expanded.debug.yaml"],
        },
        cwd=tmp_path,
        source_path=ENTRYPOINT,
    )

    exported = emit_exports(result=result, export_requests=export_requests)

    assert exported["executable_ir"].read_bytes() == result.artifact_paths["executable_ir"].read_bytes()
    assert exported["core_workflow_ast"].read_bytes() == result.artifact_paths["core_workflow_ast"].read_bytes()
    assert exported["runtime_plan"].read_bytes() == result.artifact_paths["runtime_plan"].read_bytes()
    assert exported["semantic_ir"].read_bytes() == result.artifact_paths["semantic_ir"].read_bytes()
    assert exported["source_map"].read_bytes() == result.artifact_paths["source_map"].read_bytes()
    assert exported["expanded_debug_yaml"].read_bytes() == result.artifact_paths["expanded_debug_yaml"].read_bytes()
    assert result.manifest.artifact_paths == original_manifest_paths
    assert dict(result.artifact_paths) == original_artifact_paths


def test_build_result_same_file_validated_bundles_keep_executable_and_runtime_surfaces(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    command_checks_bundle = result.compile_result.validated_bundles_by_name["lineage_pkg/entry::command_checks"]

    assert isinstance(command_checks_bundle, type(result.validated_bundle))
    assert command_checks_bundle.ir.schema_version == "workflow_executable_ir.v1"
    assert command_checks_bundle.runtime_plan.schema_version == "workflow_runtime_plan.v1"


def test_build_frontend_bundle_emits_authored_defaults_via_public_inputs_and_boundary_projection(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_workflow_param_default_request(tmp_path))
    public_inputs = _workflow_public_input_contracts(result.validated_bundle)
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = next(
        workflow
        for workflow in projection["workflows"]
        if workflow["workflow_name"] == "defaults_pkg/entry::defaults"
    )
    flattened_inputs = {field["generated_name"]: field["contract_definition"] for field in workflow_projection["flattened_inputs"]}

    assert public_inputs["message"]["default"] == "hello"
    assert public_inputs["count"]["default"] == 3
    assert public_inputs["score"]["default"] == 0.5
    assert public_inputs["enabled"]["default"] is True
    assert public_inputs["status"]["default"] == "ready"
    assert public_inputs["report_path"]["default"] == "default.md"
    assert flattened_inputs["message"]["default"] == "hello"
    assert flattened_inputs["count"]["default"] == 3
    assert flattened_inputs["score"]["default"] == 0.5
    assert flattened_inputs["enabled"]["default"] is True
    assert flattened_inputs["status"]["default"] == "ready"
    assert flattened_inputs["report_path"]["default"] == "default.md"


def test_resume_or_start_generated_internal_inputs_keep_reusable_state_paths_runtime_only(
    tmp_path: Path,
) -> None:
    result = _compile_resume_fixture(tmp_path)

    bundle = result.validated_bundles["phase_stdlib_resume_or_start::resume-record-phase"]
    runtime_inputs = _workflow_runtime_input_contracts(bundle)
    public_inputs = _workflow_public_input_contracts(bundle)
    managed_inputs = workflow_managed_write_root_inputs(bundle)
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_resume_or_start::resume-record-phase"
    )
    branch_step = lowered.authored_mapping["steps"][1]
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    writer_step = next(
        step
        for step in start_steps
        if step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
        ]
    )
    writer_hidden_input = writer_step["output_bundle"]["path"].removeprefix("${inputs.").removesuffix("}")

    assert writer_hidden_input in managed_inputs
    assert writer_hidden_input in runtime_inputs
    assert writer_hidden_input not in public_inputs
    assert writer_step["output_bundle"]["path"] in lowered.origin_map.generated_path_spans


def test_workflow_boundary_projection_emits_generated_path_allocations(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = _workflow_payload_by_suffix(projection, "provider_attempt")
    allocations = workflow_projection["generated_path_allocations"]
    provider_bundle = _allocation_payload_by_role(allocations, "provider_result_bundle")
    generated_inputs = {
        entry["generated_name"]: entry
        for entry in workflow_projection["generated_internal_inputs"]
    }

    assert provider_bundle["privacy"] == "private_generated"
    assert provider_bundle["resume_scope"] == "step_visit"
    assert provider_bundle["generated_input_name"].startswith("__write_root__")
    assert provider_bundle["generated_input_name"].endswith("__result_bundle")
    assert generated_inputs[provider_bundle["generated_input_name"]]["allocation_id"] == provider_bundle["allocation_id"]


def test_source_map_emits_generated_path_allocations(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::provider_attempt"))
    workflow = source_map["workflows"][workflow_name]
    provider_bundle = _allocation_payload_by_role(
        workflow["generated_path_allocations"],
        "provider_result_bundle",
    )
    generated_path = workflow["generated_paths"][provider_bundle["concrete_path_template"]]

    assert provider_bundle["privacy"] == "private_generated"
    assert provider_bundle["generated_input_name"].startswith("__write_root__")
    assert provider_bundle["generated_input_name"].endswith("__result_bundle")
    assert provider_bundle["origin_key"] == generated_path["origin_key"]


def test_semantic_ir_emits_generated_path_allocations(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    provider_layout = next(
        entry
        for entry in semantic_ir["state_layout"].values()
        if entry["workflow_name"].endswith("::orchestrate")
        and entry["layout_kind"] == "reusable_call_write_root"
    )

    assert provider_layout["details"]["privacy"] == "compatibility_view"
    assert provider_layout["details"]["resume_scope"] == "call_frame"
    assert provider_layout["details"]["generated_input_name"].startswith("__write_root__")
    assert provider_layout["details"]["generated_input_name"].endswith("__result_bundle")
    assert provider_layout["details"]["allocation_id"]


def test_provider_bundle_path_projection_boundary_provenance(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = _workflow_payload_by_suffix(projection, "select-next-work")
    flattened_outputs = {
        field["generated_name"]: field
        for field in workflow_projection["flattened_outputs"]
    }
    selection_bundle = flattened_outputs["return__selection_bundle_path"]
    provenance = selection_bundle["projection"]

    assert selection_bundle["contract_definition"]["under"] == "state"
    assert provenance["projection_class"] == "provider_bundle_path_projection"
    assert provenance["authority_class"] == "materialized_view"
    assert provenance["output_kind"] == "output_bundle"
    assert provenance["source_step_id"]


def test_provider_bundle_path_projection_semantic_ir_lineage(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    projection_effect = next(
        effect
        for effect in semantic_ir["effects"].values()
        if effect["effect_kind"] == "provider_bundle_path_projection"
    )

    assert projection_effect["details"]["projection_class"] == "provider_bundle_path_projection"
    assert projection_effect["details"]["authority_class"] == "materialized_view"
    assert projection_effect["details"]["projected_output_name"] == "return__selection_bundle_path"
    assert projection_effect["details"]["semantic_authority"] == "provider_structured_output_bundle"


def test_provider_bundle_path_projection_source_map_lineage(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::select-next-work"))
    workflow = source_map["workflows"][workflow_name]
    projection_effect = next(
        effect
        for effect in workflow["generated_semantic_effects"]
        if effect["effect_kind"] == "provider_bundle_path_projection"
    )

    assert projection_effect["details"]["projection_class"] == "provider_bundle_path_projection"
    assert projection_effect["details"]["authority_class"] == "materialized_view"
    assert projection_effect["details"]["projected_output_name"] == "return__selection_bundle_path"
    assert projection_effect["details"]["semantic_authority"] == "provider_structured_output_bundle"
    assert projection_effect["details"].get("allocation_id") or projection_effect["details"].get("path_template")


def test_provider_bundle_path_projection_contract_metadata(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = _workflow_payload_by_suffix(projection, "select-next-work")
    flattened_outputs = {
        field["generated_name"]: field
        for field in workflow_projection["flattened_outputs"]
    }
    provenance = flattened_outputs["return__selection_bundle_path"]["projection"]

    assert provenance["projection_id"]
    assert provenance["projection_class"] == "provider_bundle_path_projection"
    assert provenance["authority_class"] == "materialized_view"
    assert provenance["bundle_under"] == "state"
    assert provenance["bundle_must_exist_target"] is False
    assert provenance["negative_validation_cases"] == [
        "missing_bundle",
        "stale_input",
        "schema_mismatch",
        "path_escape",
        "pointer_authority_rejected",
    ]
    assert provenance.get("path_template") or provenance.get("allocation_id")


def test_build_artifacts_emit_entrypoint_managed_write_root_allocations(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_resume_entry_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))

    workflow_name = "neurips/helper::provider-attempt"
    workflow_projection = next(
        workflow
        for workflow in projection["workflows"]
        if workflow["workflow_name"] == workflow_name
    )
    entrypoint_projection = _allocation_payload_by_role(
        workflow_projection["generated_path_allocations"],
        "entrypoint_managed_write_root",
    )
    source_map_workflow = source_map["workflows"][workflow_name]
    entrypoint_source_map = _allocation_payload_by_role(
        source_map_workflow["generated_path_allocations"],
        "entrypoint_managed_write_root",
    )
    entrypoint_layout = next(
        entry
        for entry in semantic_ir["state_layout"].values()
        if entry["workflow_name"] == workflow_name
        and entry["layout_kind"] == "entrypoint_managed_write_root"
    )

    assert entrypoint_projection["privacy"] == "private_generated"
    assert entrypoint_projection["resume_scope"] == "run"
    assert entrypoint_projection["generated_input_name"].startswith("__write_root__")
    assert "${runtime.run_id}" in entrypoint_projection["concrete_path_template"]
    assert entrypoint_source_map["allocation_id"] == entrypoint_projection["allocation_id"]
    assert entrypoint_layout["details"]["allocation_id"] == entrypoint_projection["allocation_id"]












def test_promoted_entry_runtime_context_inputs_stay_internal_and_appear_in_projection(
    tmp_path: Path,
) -> None:
    fixture = FIXTURES / "valid" / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(FIXTURES / "valid",),
        command_boundaries=_resume_or_start_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result

    workflow_name = (
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::"
        "promoted-entry-resume-plan-gate-wrapper"
    )
    bundle = result.validated_bundles[workflow_name]
    runtime_inputs = _workflow_runtime_input_contracts(bundle)
    public_inputs = _workflow_public_input_contracts(bundle)
    runtime_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == workflow_name
    )

    assert runtime_context_inputs == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert runtime_context_inputs.issubset(runtime_inputs)
    assert runtime_context_inputs.isdisjoint(public_inputs)
    assert {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
        if item.reason == "runtime_owned_context"
    } == {
        "phase-ctx__run__run-id": "runtime_owned_context",
        "phase-ctx__run__state-root": "runtime_owned_context",
        "phase-ctx__run__artifact-root": "runtime_owned_context",
        "phase-ctx__phase-name": "runtime_owned_context",
        "phase-ctx__state-root": "runtime_owned_context",
        "phase-ctx__artifact-root": "runtime_owned_context",
    }


def test_promoted_entry_private_exec_context_binding_metadata_drives_boundary_projection(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")
    fixture = tmp_path / "private_exec_context_phase_entry.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        request_cls(
            source_path=fixture,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )
    result = built.compile_result.entry_result

    workflow_name = "private_exec_context_phase_entry::entry"
    bundle = result.validated_bundles[workflow_name]
    boundary = _workflow_boundary_projection(bundle)
    projection_payload = json.loads(
        built.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == workflow_name
    )

    assert set(boundary.public_input_contracts) == set(_workflow_public_input_contracts(bundle))
    assert boundary.private_managed_write_root_inputs == ()
    assert boundary.private_compatibility_bridge_inputs == ()
    assert len(boundary.private_runtime_context_bindings) == 1

    binding = boundary.private_runtime_context_bindings[0]
    assert binding.binding_id == "phase-ctx"
    assert binding.source_param_name == "phase-ctx"
    assert binding.context_family == "PhaseCtx"
    assert binding.bridge_class == "runtime_owned_context"
    assert binding.required_capabilities == ("run",)
    assert binding.derived_phase_identity == "plan-gate-wrapper"
    assert set(binding.generated_input_names) == set(_workflow_runtime_context_inputs(bundle))
    assert binding.projection_hints["context_binding_schema_version"] == 1
    assert binding.projection_hints["context_input_roles"] == {
        "phase-ctx__run__run-id": "run_anchor:run-id",
        "phase-ctx__run__state-root": "run_anchor:state-root",
        "phase-ctx__run__artifact-root": "run_anchor:artifact-root",
        "phase-ctx__phase-name": "compile_time_default",
        "phase-ctx__state-root": "compile_time_default",
        "phase-ctx__artifact-root": "compile_time_default",
    }

    assert not any(
        name.startswith("phase-ctx__work-item")
        for name in workflow_projection["boundary"]["public_input_names"]
    )
    serialized_binding = workflow_projection["boundary"]["private_runtime_context_bindings"][0]
    assert serialized_binding["binding_id"] == "phase-ctx"
    assert serialized_binding["source_param_name"] == "phase-ctx"
    assert serialized_binding["context_family"] == "PhaseCtx"
    assert serialized_binding["bridge_class"] == "runtime_owned_context"
    assert serialized_binding["derived_phase_identity"] == "plan-gate-wrapper"
    assert serialized_binding["generated_input_names"] == sorted(
        _workflow_runtime_context_inputs(bundle)
    )
    assert serialized_binding["projection_hints"] == binding.projection_hints
    assert all(
        name.startswith("__write_root__")
        for name in workflow_projection["boundary"]["private_managed_write_root_inputs"]
    )
    assert not (
        set(workflow_projection["boundary"]["private_managed_write_root_inputs"])
        & set(workflow_projection["boundary"]["public_input_names"])
    )
    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == []
    assert workflow_projection["boundary"]["pure_projection_classification"] == {
        "structural": True
    }












def test_boundary_projection_serializer_uses_typed_bundle_compatibility_split(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    serialize = getattr(build, "_serialize_workflow_boundary_projection")
    request_cls = getattr(build, "FrontendBuildRequest")
    fixture = tmp_path / "private_exec_context_phase_entry.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        request_cls(
            source_path=fixture,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )

    workflow_name = "private_exec_context_phase_entry::entry"
    lowered = next(
        workflow
        for workflow in built.compile_result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == workflow_name
    )
    compatibility_lowered = replace(
        lowered,
        compatibility_bridge_inputs=("compatibility__legacy_state_root",),
    )
    entry_result = replace(
        built.compile_result.entry_result,
        lowered_workflows=tuple(
            compatibility_lowered
            if workflow.typed_workflow.definition.name == workflow_name
            else workflow
            for workflow in built.compile_result.entry_result.lowered_workflows
        ),
    )
    compile_result = replace(
        built.compile_result,
        entry_result=entry_result,
        compiled_results_by_name={
            **dict(built.compile_result.compiled_results_by_name),
            next(iter(built.compile_result.compiled_results_by_name)): entry_result,
        },
    )

    projection_payload = serialize(
        compile_result,
        selected_name=workflow_name,
    )
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == workflow_name
    )

    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "compatibility__legacy_state_root"
    ]


def test_boundary_projection_serializer_preserves_lowered_compatibility_inputs_without_bundle(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")
    serialize = getattr(build, "_serialize_workflow_boundary_projection")

    fixture = tmp_path / "private_exec_context_phase_entry.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        request_cls(
            source_path=fixture,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )
    entry_result = built.compile_result.entry_result
    lowered = replace(
        entry_result.lowered_workflows[0],
        compatibility_bridge_inputs=("compatibility__legacy_state_root",),
    )
    linked_entry_result = replace(
        entry_result,
        lowered_workflows=(lowered, *entry_result.lowered_workflows[1:]),
        validated_bundles={},
    )
    module_name = next(iter(built.compile_result.compiled_results_by_name))
    compile_result = replace(
        built.compile_result,
        entry_result=linked_entry_result,
        compiled_results_by_name={
            **dict(built.compile_result.compiled_results_by_name),
            module_name: linked_entry_result,
        },
        validated_bundles_by_name={},
    )

    projection_payload = serialize(
        compile_result,
        selected_name=lowered.typed_workflow.definition.name,
    )
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == lowered.typed_workflow.definition.name
    )

    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "compatibility__legacy_state_root"
    ]


def test_build_frontend_bundle_keeps_wcc_default_schema_and_lowering_route_out_of_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    result = build_frontend_bundle(_build_request(tmp_path))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest_payload = json.dumps(manifest, sort_keys=True)
    source_map_payload = result.artifact_paths["source_map"].read_text(encoding="utf-8")

    assert result.manifest.shared_validation_status == "validated"
    assert manifest["lowering_schema_version"] == 2
    assert "wcc_m1" not in manifest_payload
    assert "wcc_m2" not in manifest_payload
    assert "wcc_m4" not in manifest_payload
    assert "lowering_route" not in manifest_payload
    assert "wcc_m1" not in source_map_payload
    assert "wcc_m2" not in source_map_payload
    assert "wcc_m4" not in source_map_payload
    assert "lowering_route" not in source_map_payload


def test_build_frontend_bundle_keeps_wcc_candidate_schema_and_lowering_route_out_of_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request = _build_request(tmp_path)
    result = build_frontend_bundle(
        type(request)(
            **{
                **request.__dict__,
                "lowering_route": LoweringRoute.WCC_M4,
            }
        )
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest_text = json.dumps(manifest, sort_keys=True)
    source_map_text = result.artifact_paths["source_map"].read_text(encoding="utf-8")

    assert result.manifest.shared_validation_status == "validated"
    assert manifest["lowering_schema_version"] == 2
    assert "wcc_m4" not in manifest_text
    assert "lowering_route" not in manifest_text
    assert "wcc_m4" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text


def test_same_file_wcc_m3_source_map_keeps_route_names_out_and_preserves_match_join_lineage(
    tmp_path: Path,
) -> None:
    source_map = _same_file_wcc_m3_source_map_payload(
        tmp_path,
        fixture_path=FIXTURES / "characterization" / "sources" / "design_delta_union_match_projection.orc",
        module_filename="union_match_probe.orc",
        selected_name="union_match_probe::summarize",
    )
    source_map_text = json.dumps(source_map, sort_keys=True).replace(str(tmp_path), "")
    workflow = source_map["workflows"]["union_match_probe::summarize"]

    assert "wcc_m1" not in source_map_text
    assert "wcc_m2" not in source_map_text
    assert "wcc_m3" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert any(node["kind"] == "match_join" for node in workflow["executable_nodes"])
    assert workflow["validation_subjects"]
    assert workflow["core_nodes"]


def test_wcc_m4_source_map_keeps_route_names_out_and_preserves_repeat_until_lineage(
    tmp_path: Path,
) -> None:
    source_map = _route_neutral_wcc_m4_source_map_payload(tmp_path)
    source_map_text = json.dumps(source_map, sort_keys=True).replace(str(tmp_path), "")
    workflow = source_map["workflows"]["route_neutral_loop::loop-recur-on-exhausted-union"]

    assert "wcc_m4" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text
    assert "Wcc" not in source_map_text
    assert any(node["step_kind"] == "repeat_until" for node in workflow["core_nodes"])
    assert any(node["kind"] == "repeat_until_frame" for node in workflow["executable_nodes"])
    assert {"return__variant", "return__reason", "return__report"}.issubset(workflow["generated_outputs"])
    assert workflow["generated_outputs"]["return__reason"]["generated_name_origin"] == "return__reason"
    assert workflow["validation_subjects"]


def test_wcc_m4_full_fixture_source_map_records_review_loop_and_command_lineage(
    tmp_path: Path,
) -> None:
    source_map = _wcc_m4_full_fixture_source_map_payload(tmp_path)
    source_map_text = json.dumps(source_map, sort_keys=True)
    workflow = source_map["workflows"]["wcc_m4_implementation_phase_full_fixture::run"]

    command_names = {boundary["command_name"] for boundary in workflow["command_boundaries"]}
    assert {"run_checks", "validate_review_findings_v1"}.issubset(command_names)
    assert any(node["step_kind"] == "repeat_until" for node in workflow["core_nodes"])
    assert any(node["kind"] == "repeat_until_frame" for node in workflow["executable_nodes"])
    assert {"return__variant", "return__review_report", "return__findings__items_path"}.issubset(
        workflow["generated_outputs"]
    )
    assert any(
        allocation["semantic_role"] == "command_result_bundle" and "run_checks" in allocation["stable_identity"]
        for allocation in workflow["generated_path_allocations"]
    )
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text


def test_build_persists_wcc_inline_procedure_notes(tmp_path: Path) -> None:
    result = _build_module().build_frontend_bundle(_procedure_identity_build_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    checkpoint_points = json.loads(
        result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8")
    )
    workflow = source_map["workflows"]["procedure_lowering_identity_modes::orchestrate"]
    inline_nodes = [
        node
        for node in workflow["core_nodes"]
        if node["step_kind"] in {"provider", "match"} and "inline_plan" in node["step_id"]
    ]

    assert {node["step_kind"] for node in inline_nodes} == {"provider", "match"}
    assert len(inline_nodes) == 2
    for node in inline_nodes:
        notes = workflow["step_ids"][node["step_id"]]["notes"]
        assert any(note.startswith("procedure definition at") for note in notes)
        assert any(note.startswith("procedure call site at") for note in notes)

    entries_by_origin = {
        entry["origin_key"]: entry for entry in workflow["step_ids"].values()
    }
    inline_checkpoints = [
        point
        for point in checkpoint_points["points"]
        if "inline_plan" in point["executable_identity"]["step_id"]
    ]
    assert {point["effect_boundary"]["effect_kind"] for point in inline_checkpoints} == {
        "provider",
        "command",
    }
    for point in inline_checkpoints:
        notes = entries_by_origin[point["source_lineage"]["origin_key"]]["notes"]
        assert any(note.startswith("procedure definition at") for note in notes)
        assert any(note.startswith("procedure call site at") for note in notes)


def test_build_frontend_bundle_emits_imported_stdlib_macro_helper_provenance_across_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    result = build_frontend_bundle(_imported_stdlib_helper_request(tmp_path))

    workflow_name = "imported_stdlib_macro_payload_helper_composition/entry::run-drain-like"
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    workflow = source_map["workflows"][workflow_name]

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

    coverage_bridges = {
        bridge["origin_key"]
        for key, bridge in semantic_ir["source_map"].items()
        if key.startswith(f"source_map:{workflow_name}:coverage:")
    }
    assert {"core_workflow_ast", "executable_ir", "semantic_ir"}.issubset(coverage_bridges)


def test_build_emits_debug_yaml_when_requested_and_marks_manifest_status(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    request = _build_request(tmp_path)
    request = type(request)(**{**request.__dict__, "emit_debug_yaml": True})
    result = build_frontend_bundle(request)

    debug_yaml_path = result.artifact_paths["expanded_debug_yaml"]
    debug_yaml_text = debug_yaml_path.read_text(encoding="utf-8")

    assert debug_yaml_path.name == "expanded.debug.yaml"
    assert result.manifest.debug_yaml_status == "emitted"
    assert debug_yaml_path.exists()
    assert "non-authoritative" in debug_yaml_text
    assert "must not be used as execution input" in debug_yaml_text


def test_build_removes_stale_debug_yaml_when_not_requested(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    debug_request = _build_request(tmp_path)
    debug_request = type(debug_request)(**{**debug_request.__dict__, "emit_debug_yaml": True})
    debug_result = build_frontend_bundle(debug_request)

    plain_result = build_frontend_bundle(_build_request(tmp_path))

    assert plain_result.build_root == debug_result.build_root
    assert plain_result.manifest.debug_yaml_status == "not_requested"
    assert "expanded_debug_yaml" not in plain_result.artifact_paths
    assert not (plain_result.build_root / "expanded.debug.yaml").exists()


def test_source_map_emits_versioned_schema_and_runtime_lineage_sections(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )

    assert source_map["schema_version"] == "workflow_lisp_source_map.v1"
    assert source_map["coverage"] == {
        "frontend_ast": "covered",
        "lowered_surface": "covered",
        "shared_validation_subjects": "covered",
        "executable_ir": "covered",
        "runtime_logs": "covered",
        "core_workflow_ast": "covered",
        "semantic_ir": "covered",
    }

    command_checks_name = "lineage_pkg/entry::command_checks"
    provider_attempt_name = "lineage_pkg/entry::provider_attempt"
    entry_name = "lineage_pkg/entry::orchestrate"
    command_checks = source_map["workflows"][command_checks_name]
    provider_attempt = source_map["workflows"][provider_attempt_name]
    entry_workflow = source_map["workflows"][entry_name]
    assert entry_workflow["selected_entry_workflow"] is True
    assert entry_workflow["workflow_name"] == entry_name
    assert set(source_map["workflows"]) == {command_checks_name, provider_attempt_name, entry_name}

    expected_sections = {
        "workflow_origin",
        "step_ids",
        "generated_inputs",
        "generated_outputs",
        "generated_paths",
        "generated_internal_inputs",
        "generated_semantic_effects",
        "core_nodes",
        "command_boundaries",
        "validation_subjects",
        "executable_nodes",
    }
    for workflow in source_map["workflows"].values():
        assert expected_sections.issubset(workflow)
        assert workflow["workflow_origin"]["origin_key"]
        assert workflow["core_nodes"]
        assert all(node["origin_key"] for node in workflow["core_nodes"])

    command_step_ids = {
        name for name in command_checks["step_ids"] if name.endswith("command_checks__run_checks")
    }
    internal_input_name = next(iter(command_checks["generated_internal_inputs"]))
    command_boundary = command_checks["command_boundaries"][0]
    core_node = command_checks["core_nodes"][0]
    assert command_step_ids
    assert internal_input_name.endswith("__result_bundle")
    assert len(command_checks["command_boundaries"]) == 1
    assert command_boundary["step_id"] in command_step_ids
    assert command_checks["step_ids"][command_boundary["step_id"]]["origin_key"]
    assert command_boundary["command_name"] == "run_checks"
    assert command_boundary["boundary_kind"] == "external_tool"
    assert command_boundary["origin_key"] == command_checks["step_ids"][command_boundary["step_id"]]["origin_key"]
    assert core_node["statement_id"]
    assert core_node["step_id"] in command_step_ids
    assert core_node["origin_key"] == command_checks["step_ids"][core_node["step_id"]]["origin_key"]
    assert {
        subject["subject_ref"]["subject_kind"]
        for subject in provider_attempt["validation_subjects"]
    } >= {"step_id", "generated_input", "generated_output", "workflow"}
    assert any(
        node["kind"] == "match_join" and node["region"] == "body"
        for node in provider_attempt["executable_nodes"]
    )
    assert "contract_definition" not in json.dumps(source_map, sort_keys=True)
    assert boundary_projection["schema_version"] == "workflow_lisp_boundary_projection.v1"
    assert boundary_projection["entry_workflow"] == entry_name
    projection_entry = next(
        workflow
        for workflow in boundary_projection["workflows"]
        if workflow["workflow_name"] == command_checks_name
    )
    assert projection_entry["params"] == [{"name": "report_path", "type_kind": "relpath"}]
    assert projection_entry["return_kind"] == "record"
    assert [field["generated_name"] for field in projection_entry["flattened_inputs"]] == ["report_path"]
    assert {field["generated_name"] for field in projection_entry["flattened_outputs"]} == {
        "return__report",
        "return__status",
    }
    assert len(projection_entry["generated_internal_inputs"]) == 1
    assert projection_entry["generated_internal_inputs"][0]["generated_name"].endswith("__result_bundle")
    assert projection_entry["generated_internal_inputs"][0]["reason"] == "managed_write_root"


def _write_native_root_return_module(tmp_path: Path) -> Path:
    package_dir = tmp_path / "root_return_pkg"
    package_dir.mkdir(parents=True, exist_ok=True)
    module_path = package_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule root_return_pkg/entry)",
                "  (export orchestrate)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport))",
                "    -> Bool",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns Bool)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return module_path


def _native_root_return_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = _write_native_root_return_module(tmp_path)
    return request_cls(
        source_path=module_path,
        source_roots=(tmp_path,),
        entry_workflow="orchestrate",
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def test_boundary_projection_serializes_root_return_kind_for_native_transportable_return(
    tmp_path: Path,
) -> None:
    """A native-return (public v2.15) root-valued public workflow serializes
    `return_kind: "root"` in the boundary-projection build artifact, on the
    same schema version as existing record/union boundaries, with a single
    generated `__result__` output."""
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_native_root_return_request(tmp_path))
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )

    assert boundary_projection["schema_version"] == "workflow_lisp_boundary_projection.v1"
    entry_name = "root_return_pkg/entry::orchestrate"
    projection_entry = next(
        workflow
        for workflow in boundary_projection["workflows"]
        if workflow["workflow_name"] == entry_name
    )
    assert projection_entry["return_kind"] == "root"
    assert [field["generated_name"] for field in projection_entry["flattened_outputs"]] == [
        "__result__"
    ]


def test_source_map_serializes_generated_semantic_effects_for_frontend_build(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_pointer_effects_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::orchestrate"))
    workflow = source_map["workflows"][workflow_name]

    assert "generated_semantic_effects" in workflow
    assert any(
        effect["effect_kind"] == "pointer_materialization"
        for effect in workflow["generated_semantic_effects"]
    )


def test_build_artifacts_expose_pure_projection_effects_and_generated_paths(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    result = _build_pure_expr_selector_projection(tmp_path)
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::orchestrate"))
    workflow = source_map["workflows"][workflow_name]
    lowered = next(
        workflow_result
        for workflow_result in result.compile_result.entry_result.lowered_workflows
        if workflow_result.typed_workflow.definition.name == workflow_name
    )

    assert any(
        effect["effect_kind"] == "pure_projection"
        for effect in workflow["generated_semantic_effects"]
    )
    assert any(
        allocation["semantic_role"] == "pure_projection_bundle"
        for allocation in workflow["generated_path_allocations"]
    )
    assert any(
        effect["effect_kind"] == "pure_projection"
        for effect in semantic_ir["effects"].values()
    )
    assert "pure_projection" in _observed_statement_families(lowered.authored_mapping["steps"])
    managed_write_root_input = next(
        name
        for name in lowered.authored_mapping["inputs"]
        if name.startswith("__write_root__")
    )
    assert lowered.authored_mapping["inputs"][managed_write_root_input] == {
        "kind": "relpath",
        "type": "relpath",
    }


def test_build_artifacts_expose_materialize_view_effects_and_generated_paths(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    result = _build_materialize_view_allocated_target(tmp_path)
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::orchestrate"))
    workflow = source_map["workflows"][workflow_name]
    lowered = next(
        workflow_result
        for workflow_result in result.compile_result.entry_result.lowered_workflows
        if workflow_result.typed_workflow.definition.name == workflow_name
    )

    effect = next(
        effect
        for effect in workflow["generated_semantic_effects"]
        if effect["effect_kind"] == "materialize_view"
    )

    assert effect["details"]["renderer_id"] == "canonical-json"
    assert effect["details"]["authority_class"] == "materialized_view"
    assert any(
        allocation["semantic_role"] == "materialized_value_view"
        for allocation in workflow["generated_path_allocations"]
    )
    assert any(
        entry["effect_kind"] == "materialize_view"
        for entry in semantic_ir["effects"].values()
    )
    assert "materialize_view" in _observed_statement_families(lowered.authored_mapping["steps"])


def test_review_loop_command_boundary_surfaces_validate_review_findings_adapter(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    module_dir = tmp_path / "review_findings_build"
    module_dir.mkdir(parents=True, exist_ok=True)
    module_path = module_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule review_findings_build/entry)",
                "  (import std/phase :only (ReviewFindings ReviewFindingsJsonPath))",
                "  (export validate-findings)",
                "  (defworkflow validate-findings",
                "    ((items_path ReviewFindingsJsonPath))",
                "    -> ReviewFindings",
                "    (command-result validate_review_findings_v1",
                '      :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" items_path)',
                "      :returns ReviewFindings)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = module_dir / "commands.json"
    manifest_path.write_text(
        json.dumps(
            {
                "validate_review_findings_v1": {
                    "kind": "certified_adapter",
                    "stable_command": [
                        "python",
                        "-m",
                        "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                    ],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ReviewFindings",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["review_findings_valid"],
                    "negative_fixture_ids": ["review_findings_pointer_authority_forbidden"],
                    **_validate_review_findings_retirement_metadata(),
                }
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = build_frontend_bundle(
        request_cls(
            source_path=module_path,
            source_roots=(tmp_path,),
            entry_workflow="validate-findings",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=manifest_path,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = result.entry_selection.canonical_name

    assert any(
        boundary["boundary_kind"] == "certified_adapter"
        and boundary["boundary_name"] == "validate_review_findings_v1"
        for boundary in semantic_ir["command_boundaries"].values()
    )
    assert source_map["workflows"][workflow_name]["command_boundaries"]


def test_review_loop_bundle_preserves_distinct_review_report_and_findings_seed_paths(
    tmp_path: Path,
) -> None:
    fixture = FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
    module_path = tmp_path / "phase_stdlib_review_loop.orc"
    module_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    for relpath in (
        "prompts/implementation/review.md",
        "prompts/implementation/fix.md",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
                **_validate_review_findings_retirement_metadata(),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_review_loop::review-revise-loop-demo"
    )
    seed_step = next(step for step in lowered.authored_mapping["steps"] if step["name"].endswith("__seed"))
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }
    outputs = lowered.authored_mapping["outputs"]

    assert seed_values["state__last_review_report"]["source"] == {
        "literal": "artifacts/review/last-review-report.md"
    }
    assert seed_values["state__latest_findings__items_path"]["source"] == {
        "literal": "artifacts/work/review-findings-seed.json"
    }
    assert outputs["return__review_report"]["under"] == "artifacts/review"
    assert outputs["return__last_review_report"]["under"] == "artifacts/review"
    assert outputs["return__findings__items_path"]["under"] == "artifacts/work"


def test_stdlib_contract_inventory_is_compile_time_only_and_not_serialized_into_frontend_build_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    source_map_text = result.artifact_paths["source_map"].read_text(encoding="utf-8")
    boundary_projection_text = result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    serialized_artifacts = {
        name: path.read_text(encoding="utf-8") for name, path in result.artifact_paths.items()
    }
    combined = json.dumps(serialized_artifacts, sort_keys=True)

    forbidden_markers = (
        "StdlibLoweringContract",
        "structured_result_producer",
        "review_reuse_control",
        "resource_finalize_drain",
        "source_map_expectations",
    )

    for marker in forbidden_markers:
        assert marker not in source_map_text
        assert marker not in boundary_projection_text
        assert marker not in combined


def test_semantic_ir_artifact_serializes_promoted_effects_for_frontend_build(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_pointer_effects_request(tmp_path))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    effects = [
        effect
        for effect in semantic_ir["effects"].values()
        if effect["effect_kind"] in {"pointer_materialization", "snapshot_capture", "resource_transition", "ledger_update"}
    ]

    assert any(effect["effect_kind"] == "pointer_materialization" for effect in effects)


@pytest.mark.parametrize(
    ("selected_hook", "selected_effect_kind", "unselected_effect_kind"),
    [
        ("run-command", "command_call", "provider_call"),
        ("run-provider", "provider_call", "command_call"),
    ],
)
def test_selected_hook_semantic_ir_preserves_effect_and_procedure_source_lineage(
    tmp_path: Path,
    selected_hook: str,
    selected_effect_kind: str,
    unselected_effect_kind: str,
) -> None:
    build_frontend_bundle = getattr(_build_module(), "build_frontend_bundle")
    result = build_frontend_bundle(
        _selected_hook_semantic_ir_request(tmp_path, selected_hook=selected_hook)
    )
    semantic_ir = json.loads(
        result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")
    )
    source_map = json.loads(
        result.artifact_paths["source_map"].read_text(encoding="utf-8")
    )
    selected_effects = [
        effect
        for effect in semantic_ir["effects"].values()
        if effect["effect_kind"] == selected_effect_kind
    ]

    assert len(selected_effects) == 1
    assert not any(
        effect["effect_kind"] == unselected_effect_kind
        for effect in semantic_ir["effects"].values()
    )
    effect = selected_effects[0]
    workflow_name = effect["workflow_name"]
    statement = semantic_ir["workflows"][workflow_name]["statements"][
        effect["statement_id"]
    ]
    source_workflow = source_map["workflows"][workflow_name]
    core_node = next(
        node
        for node in source_workflow["core_nodes"]
        if node["statement_id"] == statement["step_id"]
    )
    step_source = source_workflow["step_ids"][core_node["step_id"]]

    assert any("procedure call site at" in note for note in step_source["notes"])
    assert any("procedure definition at" in note for note in step_source["notes"])
    assert any("proc-ref specialization selected" in note for note in step_source["notes"])
    assert effect["statement_id"] in semantic_ir["workflows"][workflow_name]["statements"]
    assert statement["step_id"].endswith(core_node["step_id"])
    assert core_node["origin_key"] == step_source["origin_key"]


def test_design_delta_parent_drain_adapters_emit_resource_transition_effects(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=REPO_ROOT
            / "workflows"
            / "library"
            / "lisp_frontend_design_delta"
            / "drain.orc",
            source_roots=(REPO_ROOT / "workflows" / "library",),
            entry_workflow="lisp_frontend_design_delta/drain::drain",
            provider_externs_path=REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.providers.json",
            prompt_externs_path=REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow
        for compiled in result.compile_result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }

    expected_adapters = {
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
    }
    adapter_rows = {
        row["command_name"]: row
        for workflow in source_map["workflows"].values()
        for row in workflow.get("command_boundaries", [])
        if row.get("boundary_name") in expected_adapters
        or row.get("command_name") in expected_adapters
    }

    assert adapter_rows == {}

    effect_kinds_by_subject: dict[str, set[str]] = {}
    for effect in semantic_ir["effects"].values():
        boundary_name = effect.get("boundary_name")
        if not isinstance(boundary_name, str):
            continue
        for adapter_name in expected_adapters:
            if adapter_name in boundary_name:
                effect_kinds_by_subject.setdefault(adapter_name, set()).add(effect["effect_kind"])

    assert any(effect["effect_kind"] == "resource_transition" for effect in semantic_ir["effects"].values())
    assert any(effect["effect_kind"] == "materialize_view" for effect in semantic_ir["effects"].values())

    drain_families = _observed_statement_families(
        lowered_by_name["lisp_frontend_design_delta/drain::drain"].authored_mapping["steps"]
    )
    work_item_families = _observed_statement_families(
        lowered_by_name[
            "lisp_frontend_design_delta/work_item::run-work-item"
        ].authored_mapping["steps"]
    )
    assert "materialize_view" in drain_families
    assert "materialize_view" not in work_item_families
    assert "materialize_artifacts" in work_item_families


def test_source_trace_preserves_distinct_workflows_with_shared_display_names(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    source_root = tmp_path / "duplicate_names"
    package_dir = source_root / "pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/types)",
                "  (export WorkReport Out)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Out",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "helper.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/helper)",
                "  (import pkg/types :only (WorkReport Out))",
                "  (export run)",
                "  (defworkflow run",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (report_path)",
                "      :returns Out)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "entry.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/entry)",
                "  (import pkg/types :only (WorkReport Out))",
                "  (import pkg/helper :as helper :only (run))",
                "  (export run)",
                "  (defworkflow run",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (call helper.run",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_frontend_bundle(
        request_cls(
            source_path=package_dir / "entry.orc",
            source_roots=(source_root,),
            entry_workflow="run",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))

    assert source_map["schema_version"] == "workflow_lisp_source_map.v1"
    assert set(source_map["workflows"]) >= {"pkg/entry::run", "pkg/helper::run"}
    assert source_map["workflows"]["pkg/entry::run"]["selected_entry_workflow"] is True
    assert source_map["workflows"]["pkg/helper::run"]["selected_entry_workflow"] is False
    assert source_map["workflows"]["pkg/entry::run"]["display_name"] == "run"
    assert source_map["workflows"]["pkg/helper::run"]["display_name"] == "run"


def test_source_map_validator_rejects_missing_required_validation_subject_bindings(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    build_source_map_document = getattr(source_map_module, "build_source_map_document")
    validate_source_map_document = getattr(source_map_module, "validate_source_map_document")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    document = build_source_map_document(
        result.compile_result,
        selected_name=result.entry_selection.canonical_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    workflow_name = "lineage_pkg/entry::command_checks"
    workflow = document.workflows[workflow_name]
    broken_workflow = replace(
        workflow,
        validation_subjects=tuple(
            binding
            for binding in workflow.validation_subjects
            if not (
                binding.subject_ref.subject_kind == "generated_output"
                and binding.subject_ref.subject_name == "return__report"
            )
        ),
    )
    broken_document = replace(
        document,
        workflows={**dict(document.workflows), workflow_name: broken_workflow},
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_source_map_document(broken_document)

    assert excinfo.value.diagnostics[0].code == "source_map_validation_subject_missing"
    assert "generated_output:return__report" in excinfo.value.diagnostics[0].message


def test_source_map_validator_rejects_missing_core_node_lineage_when_coverage_claimed(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    build_source_map_document = getattr(source_map_module, "build_source_map_document")
    validate_source_map_document = getattr(source_map_module, "validate_source_map_document")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    document = build_source_map_document(
        result.compile_result,
        selected_name=result.entry_selection.canonical_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    workflow_name = "lineage_pkg/entry::command_checks"
    workflow = document.workflows[workflow_name]
    broken_workflow = replace(workflow, core_nodes=())
    broken_document = replace(
        document,
        workflows={**dict(document.workflows), workflow_name: broken_workflow},
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_source_map_document(broken_document)

    assert excinfo.value.diagnostics[0].code == "source_map_core_node_missing"
    assert workflow_name in excinfo.value.diagnostics[0].message




def test_design_delta_parent_drain_build_omits_retired_certification_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    result = build.build_frontend_bundle(_design_delta_parent_drain_request(tmp_path))

    retired_artifact_names = {
        "g8_deletion_evidence",
        "adapter_census",
        "boundary_authority_report",
        "value_flow_census_report",
        "consumer_rendering_census_report",
        "reference_family_conformance_profile",
    }
    assert retired_artifact_names.isdisjoint(result.artifact_paths)
    assert retired_artifact_names.isdisjoint(result.manifest.artifact_paths)
    assert retired_artifact_names.isdisjoint(result.manifest.artifact_status)
    assert not (result.build_root / "g8_deletion_evidence.json").exists()



















































































































































































def test_build_emits_lexical_checkpoint_points_artifact(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    points_path = result.artifact_paths["lexical_checkpoint_points"]
    payload = json.loads(points_path.read_text(encoding="utf-8"))

    assert points_path.name == "lexical_checkpoint_points.json"
    assert payload["schema_version"] == "workflow_lisp_lexical_checkpoint_points.v1"
    assert payload["checkpoint_schema_version"] == "workflow_lisp_lexical_checkpoint.v1"
    assert payload["program_identity"]["source_module_digest"].startswith("sha256:")
    assert payload["program_identity"]["executable_ir_digest"].startswith("sha256:")
    assert payload["program_identity"]["semantic_ir_digest"].startswith("sha256:")
    assert payload["points"]
    assert all(
        point["wcc_identity"]["node_id_digest"].startswith("sha256:")
        and point["wcc_identity"]["scope_id_digest"].startswith("sha256:")
        and point["binding_schema"]["schema_digest"].startswith("sha256:")
        and point["storage"]["semantic_role"] == "lexical_checkpoint_record"
        for point in payload["points"]
    )


def test_build_emits_compile_time_lexical_checkpoint_shadow_report(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    report_path = result.artifact_paths["lexical_checkpoint_shadow_report"]
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    points_payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))

    assert report_path.name == "lexical_checkpoint_shadow_report.json"
    assert payload["schema_version"] == "workflow_lisp_lexical_checkpoint_shadow_report.v1"
    assert payload["status"] == "pass"
    assert payload["checked_points"] == len(points_payload["points"])
    assert payload["checked_records"] == 0
    assert payload["diagnostics"] == []


def test_build_manifest_records_checkpoint_artifact_paths(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    assert result.manifest.artifact_paths["lexical_checkpoint_points"].endswith("/lexical_checkpoint_points.json")
    assert result.manifest.artifact_paths["lexical_checkpoint_shadow_report"].endswith(
        "/lexical_checkpoint_shadow_report.json"
    )


def test_checkpoint_points_artifact_is_route_neutral_in_public_fields(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    payload = result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8")
    assert "wcc_m4" not in payload
    assert "lowering_route" not in payload
    assert "wcc-node:" not in payload


def test_runtime_plan_artifact_keeps_lexical_checkpoint_details_route_neutral(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    payload = result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")
    assert "runtime_program_identity" not in payload
    assert "wcc_m4" not in payload
    assert "wcc-node:" not in payload


def test_build_emits_restore_eligibility_details_in_lexical_checkpoint_points_artifact(tmp_path: Path) -> None:
    result = _build_lexical_restore_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    restore_labels = {
        label
        for point in payload["points"]
        for label in point.get("restore", {}).get("eligibility", ())
    }

    assert {"pure_binding", "let_continuation", "match_branch", "loop_frame"} <= restore_labels
    assert any(point.get("restore", {}).get("binding_descriptor_digests") for point in payload["points"])
    assert any(point.get("restore", {}).get("proof_descriptor_digests") for point in payload["points"])
    assert any(point.get("restore", {}).get("loop_frame_descriptor_digest") for point in payload["points"])
    assert all("binding_descriptors" not in point.get("restore", {}) for point in payload["points"])
    assert all("proof_descriptors" not in point.get("restore", {}) for point in payload["points"])
    assert all("loop_frame_descriptor" not in point.get("restore", {}) for point in payload["points"])
    assert "wcc-node:" not in json.dumps(payload, sort_keys=True)
    assert "wcc_m4" not in json.dumps(payload, sort_keys=True)


def test_checkpoint_points_artifact_rejects_missing_executable_node_linkage(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    payload["points"][0]["executable_identity"]["node_id"] = "missing.node"
    result.artifact_paths["lexical_checkpoint_points"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )


def test_checkpoint_points_artifact_rejects_missing_source_map_origin(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    payload["points"][0]["source_lineage"]["origin_key"] = "source:missing"

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )


def test_checkpoint_points_artifact_rejects_program_identity_drift(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    payload["program_identity"]["executable_ir_digest"] = "sha256:drifted"

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )


def test_build_emits_r3_policy_summaries_for_lexical_checkpoint_effect_boundaries(tmp_path: Path) -> None:
    result = _build_lexical_policy_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))

    effect_policies = {
        point["effect_boundary"]["effect_kind"]: point["effect_boundary"]["policy"]
        for point in payload["points"]
        if point["point_kind"] == "effect_boundary"
    }

    assert set(effect_policies) >= {
        "pure_projection",
        "provider",
        "command",
        "call",
        "materialize_view",
        "resource_transition",
    }
    assert all(policy["schema_version"] == "workflow_lisp_effect_resume_policy.v1" for policy in effect_policies.values())
    assert all("runtime_program_identity" not in json.dumps(policy, sort_keys=True) for policy in effect_policies.values())
    assert all("wcc-node:" not in json.dumps(policy, sort_keys=True) for policy in effect_policies.values())


def test_lexical_checkpoint_points_artifact_rejects_missing_r3_policy_envelope(tmp_path: Path) -> None:
    result = _build_lexical_policy_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    effect_boundary_point = next(point for point in payload["points"] if point["point_kind"] == "effect_boundary")
    effect_boundary_point["effect_boundary"].pop("policy", None)

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )
