import json
from contextlib import closing
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import OutputContractError
from orchestrator.workflow.evaluated.commands import validate_effect_result
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.normalized_type_descriptor import compiler_normalized_type_descriptor
from orchestrator.workflow_lisp.phase import derived_private_child_context_eligibility

from orchestrator.workflow_lisp.closed.frontend import _select_and_finalize_typed_program
from orchestrator.workflow_lisp.closed.build import Builder
from orchestrator.workflow_lisp.contracts import derive_prompt_guided_structured_result_contract, root_workflow_boundary_field
from orchestrator.workflow_lisp.result_guidance import normalized_result_guidance_payload
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.effects import UsesProviderEffect
from orchestrator.workflow_lisp.typed_prompt_inputs import select_prompt_fragment_renderer
from orchestrator.workflow_lisp.wcc.model import WccPerform

from orchestrator.workflow_lisp.family_profiles import (
    load_workflow_family_profile_catalog,
)
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import ProviderResultExpr
from orchestrator.workflow_lisp.loops import build_loop_lowering_plan
from orchestrator.workflow_lisp.type_env import (
    PRELUDE_PATH_TYPES,
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
)
from orchestrator.workflow_lisp.workflows import (
    ExternalToolBinding,
    build_workflow_catalog,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import build_syntax_module


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
STRUCTURED_RESULTS_FIXTURE = FIXTURES / "valid" / "structured_results.orc"
REMAP_FIXTURE = FIXTURES / "current235" / "invalid" / "shared_validation_remap.orc"
PHASE_STDLIB_FIXTURE = FIXTURES / "valid" / "phase_stdlib_run_provider_phase.orc"
TYPED_PROMPT_INPUT_FIXTURE = FIXTURES / "valid" / "typed_prompt_input_phase.orc"
GENERIC_FAMILY_PROFILE_FIXTURE = (
    FIXTURES / "family_profiles" / "generic_phase_family_profile.json"
)
LOCAL_REQUEST_TYPED_PROMPT_INPUT_FIXTURE = (
    FIXTURES / "valid" / "typed_prompt_input_local_request_record.orc"
)
LOOP_RECUR_UNION_RESULT_MISSING_ACTIVE_FIELD_FIXTURE = (
    FIXTURES / "current235" / "invalid" / "loop_recur_union_result_missing_active_field.orc"
)
ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE = (
    FIXTURES / "valid" / "design_delta_item_ctx_child_phase_reuse.orc"
)
DERIVED_PHASE_CONTEXT_BINDING_INVALID_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_binding_invalid.orc"
)
DERIVED_PHASE_CONTEXT_DIRECT_ENTRY_INVALID_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_direct_entry_invalid.orc"
)
DERIVED_PHASE_CONTEXT_AMBIGUOUS_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_ambiguous.orc"
)
DERIVED_PHASE_CONTEXT_NON_ITEM_CTX_ROOT_INVALID_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_non_item_ctx_root_invalid.orc"
)
DERIVED_PHASE_CONTEXT_PUBLIC_RUN_LEAVES_INVALID_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_public_run_leaves_invalid.orc"
)
DERIVED_PHASE_CONTEXT_FROM_COMPATIBILITY_BRIDGE_INVALID_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_from_compatibility_bridge_invalid.orc"
)
DERIVED_PHASE_CONTEXT_REREAD_INVALID_FIXTURE = (
    FIXTURES / "invalid" / "derived_phase_context_reread_invalid.orc"
)
REPO_ROOT = Path(__file__).resolve().parent.parent





def _walk_dataclass_values(node: object):
    yield node
    if is_dataclass(node):
        for field in fields(node):
            yield from _walk_dataclass_values(getattr(node, field.name))
    elif isinstance(node, (tuple, list)):
        for value in node:
            yield from _walk_dataclass_values(value)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk_dataclass_values(value)


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _write_provider_bundle_projection_module(
    tmp_path: Path,
    *,
    module_name: str,
    workflow_name: str,
    projection_expr: str,
    phase_scoped: bool,
    path_under: str,
) -> Path:
    if phase_scoped:
        body = "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                f"  (defmodule {module_name})",
                "  (import std/phase :only (with-phase))",
                f"  (export {workflow_name})",
                "  (defpath DesignDocPath",
                "    :kind relpath",
                '    :under "docs/design"',
                "    :must-exist true)",
                "  (defpath PlanDocPath",
                "    :kind relpath",
                '    :under "docs/plans"',
                "    :must-exist true)",
                "  (defpath SelectionBundlePath",
                "    :kind relpath",
                f'    :under "{path_under}"',
                "    :must-exist false)",
                "  (defpath ImplementationStateBundlePath",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root)",
                "    (implementation_state_bundle_path ImplementationStateBundlePath)",
                "    (execution_report_target WorkReportTarget)",
                "    (progress_report_target WorkReportTarget))",
                "  (defrecord SelectionInputs",
                "    (design DesignDocPath)",
                "    (plan PlanDocPath))",
                "  (defrecord SelectionDecision",
                "    (selection_status String))",
                "  (defrecord BundleProjection",
                "    (selection_bundle_path SelectionBundlePath))",
                f"  (defworkflow {workflow_name}",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs SelectionInputs))",
                "    -> BundleProjection",
                "    (with-phase phase-ctx implementation",
                "      (let* ((decision",
                "               (provider-result providers.execute",
                "                 :prompt prompts.implementation.execute",
                "                 :inputs (inputs.design inputs.plan)",
                "                 :returns SelectionDecision)))",
                "        (record BundleProjection",
                f"          :selection_bundle_path {projection_expr}))))",
                ")",
            ]
        )
    else:
        body = "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                f"  (defmodule {module_name})",
                f"  (export {workflow_name})",
                "  (defpath DesignDocPath",
                "    :kind relpath",
                '    :under "docs/design"',
                "    :must-exist true)",
                "  (defpath PlanDocPath",
                "    :kind relpath",
                '    :under "docs/plans"',
                "    :must-exist true)",
                "  (defpath SelectionBundlePath",
                "    :kind relpath",
                f'    :under "{path_under}"',
                "    :must-exist false)",
                "  (defrecord SelectionDecision",
                "    (selection_status String))",
                "  (defrecord BundleProjection",
                "    (selection_bundle_path SelectionBundlePath))",
                f"  (defworkflow {workflow_name}",
                "    ((design DesignDocPath)",
                "     (plan PlanDocPath))",
                "    -> BundleProjection",
                "    (let* ((decision",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (design plan)",
                "               :returns SelectionDecision)))",
                "      (record BundleProjection",
                f"        :selection_bundle_path {projection_expr})))",
                ")",
            ]
        )
    return _write_module(tmp_path / f"{module_name.replace('/', '_')}.orc", body + "\n")








def _walk_lowered_steps(steps: list[dict[str, object]]):
    for step in steps:
        yield step
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _walk_lowered_steps(repeat_until.get("steps", []))
        if_block = step.get("if")
        if isinstance(if_block, dict):
            then_block = if_block.get("then")
            else_block = if_block.get("else")
            if isinstance(then_block, dict):
                yield from _walk_lowered_steps(then_block.get("steps", []))
            if isinstance(else_block, dict):
                yield from _walk_lowered_steps(else_block.get("steps", []))
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case in match_block.get("cases", {}).values():
                if isinstance(case, dict):
                    yield from _walk_lowered_steps(case.get("steps", []))


def test_typed_effect_inference_descends_through_phase_inside_same_file_procedure(tmp_path: Path) -> None:
    path = _write_module(tmp_path / "phase_procedure.orc", '(workflow-lisp\n  (:language "0.1") (:target-dsl "2.35")\n  (defrecord RunCtx (run-id RunId) (state-root Path.state-root) (artifact-root Path.artifact-root))\n  (defrecord PhaseCtx (run RunCtx) (phase-name Symbol) (state-root Path.state-root) (artifact-root Path.artifact-root))\n  (defproc helper ((ctx PhaseCtx)) -> Bool\n    :effects ((uses-provider providers.execute)) :lowering inline\n    (with-phase ctx implementation\n      (provider-result providers.execute :prompt prompts.execute :inputs () :returns Bool)))\n  (defworkflow run ((ctx PhaseCtx)) -> Bool (helper ctx)))\n')
    result = compile_stage3_module(path, provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompt.md"}, workspace_root=tmp_path)
    effects = result.typed_workflows[0].typed_body.effect_summary.transitive_effects
    assert UsesProviderEffect(subject=("providers", "execute")) in effects
    helper = next(row for row in result.typed_procedures if row.definition.name.endswith("helper"))
    provider = next(node for node in walk_expr(helper.typed_body.expr) if isinstance(node, ProviderResultExpr))
    assert provider.prompt.name == "prompts.execute"


def _write_workflow_param_default_module(path: Path) -> Path:
    return _write_module(
        path,
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
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
        ),
    )


def _compile_definition_module(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def test_typed_root_guidance_preserves_provider_and_command_contracts(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "compiled_root_guidance_typed.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defworkflow guided-provider ()",
                '    -> (result Bool :description "Public provider decision." :example true)',
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs ()",
                '      :returns (result Bool :description "Provider must decide."',
                '        :format-hint "JSON boolean." :example true)))',
                "  (defworkflow guided-command ()",
                '    -> (result Bool :description "Public command decision." :example false)',
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                '      :returns (result Bool :description "Command must decide."',
                '        :format-hint "JSON boolean." :example false))))',
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md"
        },
        command_boundaries={
            "decide": ExternalToolBinding(
                name="decide",
                stable_command=("python", "scripts/decide.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    for workflow, example, public, effect in (
        (result.typed_workflows[0], True, "Public provider decision.", "Provider must decide."),
        (result.typed_workflows[1], False, "Public command decision.", "Command must decide."),
    ):
        assert normalized_result_guidance_payload(workflow.definition.return_spec.guidance,
            expected_type=workflow.signature.return_type_ref, type_env=result.typed_program.type_env) == {
                "description": public, "example": example}
        expr = workflow.typed_body.expr
        contract = derive_prompt_guided_structured_result_contract(workflow.signature.return_type_ref,
            workflow_name=workflow.definition.name, step_id="result", type_env=result.typed_program.type_env,
            span=expr.span, form_path=expr.form_path, guidance=expr.return_spec.guidance)
        field = contract.payload["fields"][0]
        assert {key: field[key] for key in ("description", "format_hint", "example")} == {
            "description": effect, "format_hint": "JSON boolean.", "example": example}


def test_typed_root_guidance_covers_record_union_and_private_procedures(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "compiled_root_guidance_shapes_typed.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord ReviewResult",
                '    (approved Bool :description "Payload approval." :example true))',
                "  (defunion Decision",
                "    (APPROVE",
                '      (approved Bool :description "Approval branch." :example true))',
                "    (REVISE",
                '      (reason String :description "Revision reason." :example "fix")))',
                "  (defproc build-review ()",
                '    -> (result ReviewResult :description "Private review result."',
                '      :format-hint "Complete review object."',
                '      :example (record ReviewResult :approved true))',
                "    :effects ((uses-command decide))",
                "    :lowering private-workflow",
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                "      :returns ReviewResult))",
                "  (defworkflow guided-record ()",
                '    -> (result ReviewResult :description "Public review result."',
                '      :example (record ReviewResult :approved true))',
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                "      :returns ReviewResult))",
                "  (defworkflow guided-union ()",
                '    -> (result Decision :description "Public decision result."',
                '      :example (variant Decision APPROVE :approved true))',
                "    (command-result decide",
                '      :argv ("python" "scripts/decide.py")',
                "      :returns Decision))",
                "  (defworkflow invoke-private () -> ReviewResult",
                "    (build-review)))",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        command_boundaries={
            "decide": ExternalToolBinding(
                name="decide",
                stable_command=("python", "scripts/decide.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    expected = {
        "guided-record": {"description": "Public review result.", "example": {"approved": True}},
        "guided-union": {"description": "Public decision result.", "example": {"variant": "APPROVE", "approved": True}},
        "build-review": {"description": "Private review result.", "format_hint": "Complete review object.", "example": {"approved": True}},
    }
    callables = (*result.typed_workflows, *result.typed_procedures)
    for row in callables:
        name = row.definition.name.rsplit("::", 1)[-1]
        if name in expected:
            assert normalized_result_guidance_payload(row.definition.return_spec.guidance,
                expected_type=row.signature.return_type_ref, type_env=result.typed_program.type_env) == expected[name]
    assert set(expected) <= {row.definition.name.rsplit("::", 1)[-1] for row in callables}


def test_shared_root_contracts_preserve_transportable_return_types() -> None:
    span = SourceSpan(start=SourcePosition(path="contracts.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="contracts.orc", line=1, column=2, offset=1))
    type_env = FrontendTypeEnvironment({}, target_dsl_version="2.35")
    for type_ref, kind, wire_type in ((PrimitiveTypeRef(name="Bool"), "scalar", "bool"),
        (PrimitiveTypeRef(name="Int"), "scalar", "integer"),
        (PrimitiveTypeRef(name="String"), "scalar", "string"),
        (PathTypeRef(name="Path.state-root", definition=PRELUDE_PATH_TYPES["Path.state-root"]), "relpath", "relpath")):
        field = root_workflow_boundary_field(type_ref, span=span, form_path=(), type_env=type_env)
        assert field.generated_name == "__result__"
        assert field.source_path == ("return",)
        assert field.contract_definition["kind"] == kind
        assert field.contract_definition["type"] == wire_type


def test_provider_bundle_path_projection_invalid_source(tmp_path: Path) -> None:
    workflow_path = _write_provider_bundle_projection_module(
        tmp_path,
        module_name="provider_bundle_projection_invalid_source",
        workflow_name="project-invalid-source",
        projection_expr="(provider-bundle-path design :as SelectionBundlePath)",
        phase_scoped=False,
        path_under=".orchestrate/workflow_lisp/entry",
    )

    with pytest.raises(LispFrontendCompileError):
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )


def test_provider_bundle_path_projection_missing_as_target(tmp_path: Path) -> None:
    workflow_path = _write_provider_bundle_projection_module(
        tmp_path,
        module_name="provider_bundle_projection_missing_as",
        workflow_name="project-missing-as",
        projection_expr="(provider-bundle-path decision)",
        phase_scoped=False,
        path_under=".orchestrate/workflow_lisp/entry",
    )

    with pytest.raises(LispFrontendCompileError):
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )


def test_provider_bundle_path_projection_non_path_target(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "provider_bundle_projection_non_path_target.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule provider_bundle_projection_non_path_target)",
                "  (export project-non-path)",
                "  (defpath DesignDocPath",
                "    :kind relpath",
                '    :under "docs/design"',
                "    :must-exist true)",
                "  (defpath PlanDocPath",
                "    :kind relpath",
                '    :under "docs/plans"',
                "    :must-exist true)",
                "  (defpath SelectionBundlePath",
                "    :kind relpath",
                '    :under ".orchestrate/workflow_lisp/entry"',
                "    :must-exist false)",
                "  (defrecord SelectionDecision",
                "    (selection_status String))",
                "  (defrecord BundleProjection",
                "    (selection_bundle_path SelectionBundlePath))",
                "  (defworkflow project-non-path",
                "    ((design DesignDocPath)",
                "     (plan PlanDocPath))",
                "    -> BundleProjection",
                "    (let* ((decision",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (design plan)",
                "               :returns SelectionDecision)))",
                "      (record BundleProjection",
                "        :selection_bundle_path (provider-bundle-path decision :as String))))",
                ")",
            ]
        )
        + "\n",
    )

    with pytest.raises(LispFrontendCompileError):
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )


def test_provider_bundle_path_projection_path_escape(tmp_path: Path) -> None:
    workflow_path = _write_provider_bundle_projection_module(
        tmp_path,
        module_name="provider_bundle_projection_path_escape",
        workflow_name="project-path-escape",
        projection_expr="(provider-bundle-path decision :as SelectionBundlePath)",
        phase_scoped=False,
        path_under="../state",
    )

    with pytest.raises(LispFrontendCompileError):
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=True,
            workspace_root=tmp_path,
        )


def test_typed_provider_phase_preserves_prompt_input_types(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        TYPED_PROMPT_INPUT_FIXTURE,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (GENERIC_FAMILY_PROFILE_FIXTURE,)
        ),
    )

    program = _select_and_finalize_typed_program(result, entry_path=TYPED_PROMPT_INPUT_FIXTURE,
        entry_workflow='run-typed-prompt-phase-demo')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    assert providers[0].positional_args
    assert [row.metadata.type_ref.name for row in providers[0].positional_args] == ["PhaseCtx", "PromptContext"]


def test_typed_provider_inputs_preserve_binding_order_types_and_default_renderers(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "typed_carriage.orc"
    module_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule typed_carriage)
  (export PhaseOneResult TrialResult run)
  (defpath TaskFile
    :kind relpath
    :under "task"
    :must-exist true)
  (defrecord PhaseOneResult
    (allowed_value String)
    (allowed_path TaskFile))
  (defrecord TrialResult
    (status String)
    (marker String))
  (defworkflow run
    ((task TaskFile))
    -> TrialResult
    (let* ((prior
             (provider-result providers.phase-one
               :prompt prompts.phase-one
               :inputs (task)
               :returns PhaseOneResult))
           (final
             (provider-result providers.phase-two
               :prompt prompts.phase-two
               :inputs (prior.allowed_value prior.allowed_path)
               :returns TrialResult)))
      final)))
""".lstrip(),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        entry_workflow="run",
        provider_externs={
            "providers.phase-one": "phase-one-provider",
            "providers.phase-two": "phase-two-provider",
        },
        prompt_externs={
            "prompts.phase-one": "phase-one.md",
            "prompts.phase-two": "phase-two.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    program = _select_and_finalize_typed_program(result.entry_result, entry_path=module_path,
        entry_workflow='run')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    phase_two = next(row for row in providers if row.target_name == "providers.phase-two")
    values = phase_two.positional_args
    assert [row.fields[-1] for row in values] == ["allowed_value", "allowed_path"]
    assert [row.metadata.type_ref.name for row in values] == ["String", "TaskFile"]
    assert [select_prompt_fragment_renderer(row.metadata.type_ref, kind=kind)
        for row, kind in zip(values, ("value", "path"), strict=True)] == ["canonical-json", "posix-path-line"]


def test_typed_provider_record_input_uses_canonical_default_renderer(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "typed_record_carriage.orc"
    module_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule typed_record_carriage)
  (export PromptRequest TrialResult run)
  (defrecord PromptRequest
    (focus String)
    (approved Bool))
  (defrecord TrialResult
    (status String))
  (defworkflow run
    ((request PromptRequest))
    -> TrialResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs (request)
      :returns TrialResult)))
""".lstrip(),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        entry_workflow="run",
        provider_externs={"providers.execute": "record-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    program = _select_and_finalize_typed_program(result.entry_result, entry_path=module_path,
        entry_workflow='run')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    values = providers[0].positional_args
    assert len(values) == 1
    assert values[0].name == "request"
    assert values[0].metadata.type_ref.name == "PromptRequest"
    assert select_prompt_fragment_renderer(values[0].metadata.type_ref,
        kind="value") == "canonical-json"


def test_typed_provider_inputs_preserve_types_with_distinct_renderer_eligibility(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "mixed_typed_carriage.orc"
    module_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule mixed_typed_carriage)
  (export TrialResult run)
  (defrecord TrialResult
    (status String))
  (defworkflow run
    ((count Int)
     (items List[RunId]))
    -> TrialResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs (count items)
      :returns TrialResult)))
""".lstrip(),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        entry_workflow="run",
        provider_externs={"providers.execute": "mixed-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    program = _select_and_finalize_typed_program(result.entry_result, entry_path=module_path,
        entry_workflow='run')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    values = providers[0].positional_args
    assert [row.name for row in values] == ["count", "items"]
    assert [row.metadata.type_ref.name for row in values] == ["Int", "List[RunId]"]
    assert select_prompt_fragment_renderer(values[0].metadata.type_ref,
        kind="value") == "canonical-json"
    assert select_prompt_fragment_renderer(values[1].metadata.type_ref,
        kind="value") is None


def test_typed_provider_literal_inputs_preserve_types_values_and_order(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "literal_typed_carriage.orc"
    module_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule literal_typed_carriage)
  (export TrialResult run)
  (defrecord TrialResult
    (status String))
  (defworkflow run
    ()
    -> TrialResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs (true 42 "focus")
      :returns TrialResult)))
""".lstrip(),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        entry_workflow="run",
        provider_externs={"providers.execute": "literal-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    program = _select_and_finalize_typed_program(result.entry_result, entry_path=module_path,
        entry_workflow='run')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    values = providers[0].positional_args
    assert [row.metadata.type_ref.name for row in values] == ["Bool", "Int", "String"]
    assert [row.value for row in values] == [True, 42, "focus"]
    assert all(select_prompt_fragment_renderer(row.metadata.type_ref,
        kind="value") == "canonical-json" for row in values)


def test_typed_provider_profile_configuration_retains_list_input(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "profile_list_carriage.orc"
    module_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule profile_list_carriage)
  (export TrialResult run)
  (defrecord TrialResult
    (status String))
  (defworkflow run
    ((items List[Int]))
    -> TrialResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs (items)
      :returns TrialResult)))
""".lstrip(),
        encoding="utf-8",
    )
    profile_payload = json.loads(
        GENERIC_FAMILY_PROFILE_FIXTURE.read_text(encoding="utf-8")
    )
    profile_payload["family_id"] = "profile_list_carriage_fixture"
    profile_payload["target_workflows"] = ["profile_list_carriage::run"]
    profile_payload["checked_public_inputs"] = {}
    profile_payload["entry_phase_identities"] = {}
    profile_payload["hidden_context_rules"] = []
    profile_payload["typed_prompt_input_rows"] = [
        {
            "workflow_name": "profile_list_carriage::run",
            "provider_binding": "providers.execute",
            "binding_name": "items",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "inputs.items",
            },
            "value_type_name": "List[Int]",
            "source_map_origin_key": "profile_list_carriage::run",
            "u0_row_id": "u0.fixture.items",
            "c0_row_id": "c0.fixture.items",
            "injection_order": 0,
        }
    ]
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(profile_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        entry_workflow="run",
        provider_externs={"providers.execute": "list-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (profile_path,)
        ),
    )
    program = _select_and_finalize_typed_program(result.entry_result, entry_path=module_path,
        entry_workflow='run')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    values = providers[0].positional_args
    assert len(values) == 1
    assert values[0].name == "items"
    assert values[0].metadata.type_ref.name == "List[Int]"
    assert select_prompt_fragment_renderer(values[0].metadata.type_ref,
        kind="value") == "canonical-json"


def test_typed_phase_stdlib_preserves_provider_input_operands(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        PHASE_STDLIB_FIXTURE,
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
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    program = _select_and_finalize_typed_program(result, entry_path=PHASE_STDLIB_FIXTURE,
        entry_workflow='run-provider-phase-demo')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    assert providers[0].positional_args


def test_typed_phase_request_preserves_one_typed_prompt_input_binding(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        LOCAL_REQUEST_TYPED_PROMPT_INPUT_FIXTURE,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (GENERIC_FAMILY_PROFILE_FIXTURE,)
        ),
    )

    program = _select_and_finalize_typed_program(result, entry_path=LOCAL_REQUEST_TYPED_PROMPT_INPUT_FIXTURE,
        entry_workflow='run-local-request-record-demo')
    body = Builder(program)._workflow_wcc_body(program.entry, program)
    providers = [row for row in _walk_dataclass_values(body)
        if isinstance(row, WccPerform) and row.perform_kind in {"provider_result", "run_provider_phase"}]
    assert providers
    values = providers[0].positional_args[1:]
    assert len(values) == 1
    assert values[0].name == "request"
    assert values[0].metadata.type_ref.name == "ImplementationRequest"
    assert select_prompt_fragment_renderer(values[0].metadata.type_ref,
        kind="value") == "canonical-json"


def test_stage3_analysis_preserves_typed_workflow_names_across_profiles(tmp_path: Path) -> None:
    no_validation = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={"run_checks": ExternalToolBinding(name="run_checks", stable_command=("python", "scripts/run_checks.py"))},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    validated = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={"run_checks": ExternalToolBinding(name="run_checks", stable_command=("python", "scripts/run_checks.py"))},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert [workflow.definition.name for workflow in no_validation.typed_workflows] == [
        "entry::command_checks",
        "entry::provider_attempt",
        "entry::orchestrate",
    ]
    assert [row.definition.name for row in validated.typed_workflows] == [
        row.definition.name for row in no_validation.typed_workflows]


def test_typed_workflow_signature_preserves_authored_param_defaults(tmp_path: Path) -> None:
    result = compile_stage3_module(
        _write_workflow_param_default_module(tmp_path / "workflow_param_defaults.orc"),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    defaults = result.typed_workflows[0].signature.param_defaults
    assert {name: value.normalized_value for name, value in defaults.items()} == {
        "message": "hello", "count": 3, "score": 0.5, "enabled": True,
        "status": "ready", "report_path": "default.md"}
    assert defaults["enabled"].normalized_value is True


def test_build_workflow_catalog_reconstructs_imported_param_defaults_from_typed_program(tmp_path: Path) -> None:
    compiled = compile_stage3_module(
        _write_module(
            tmp_path / "workflow_param_defaults_imported.orc",
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.35")',
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
                    "    ((count Int :default 3)",
                    "     (score Float :default 0.5)",
                    "     (enabled Bool :default true)",
                    "     (status Status :default ready)",
                    '     (report_path WorkReport :default "default.md"))',
                    "    -> Summary",
                    "    (record Summary :report report_path)))",
                ]
            ),
        ),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    assert compiled.typed_program.target == "2.35"
    assert compiled.typed_program.entry_module == "entry"
    caller_types = _write_module(
        tmp_path / "caller_types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defenum Status",
                "    ready",
                "    blocked)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord Summary",
                "    (report WorkReport)))",
            ]
        ),
    )

    workflow_catalog = build_workflow_catalog(
        _compile_definition_module(caller_types),
        (),
        FrontendTypeEnvironment.from_module(_compile_definition_module(caller_types)),
        imported_programs={"defaults": _select_and_finalize_typed_program(compiled,
            entry_path=tmp_path / "workflow_param_defaults_imported.orc", entry_workflow="defaults")},
    )

    defaults = workflow_catalog.signatures_by_name["defaults"].param_defaults
    assert defaults["count"].normalized_value == 3
    assert defaults["score"].normalized_value == 0.5
    assert defaults["enabled"].normalized_value is True
    assert defaults["status"].normalized_value == "ready"
    assert defaults["report_path"].normalized_value == "default.md"


def test_typed_loop_plans_preserve_root_and_nested_collection_descriptors(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "rich_list_loop_lowering.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Task",
                "    (task_id String))",
                "  (defunion TaskOutcome",
                "    (PENDING (task Task))",
                "    (BLOCKED (reason String)))",
                "  (defrecord Progress",
                "    (tasks List[Task]))",
                "  (defworkflow root-loop ((tasks List[Task]) (finish Bool)) -> List[Task]",
                "    (loop/recur :max 1 :state tasks :on-exhausted state",
                "      (fn (state) (if finish (done state) (continue state)))))",
                "  (defworkflow nested-loop",
                "    ((tasks List[Task]) (finish Bool))",
                "    -> Progress",
                "    (loop/recur :max 1",
                "      :state (record Progress :tasks tasks)",
                "      :on-exhausted state",
                "      (fn (state) (if finish (done state) (continue state)))))",
                "  (defworkflow union-provider-loop ((finish Bool)) -> List[TaskOutcome]",
                "    (let* ((outcomes",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs ()",
                "               :returns List[TaskOutcome])))",
                "      (loop/recur :max 1 :state outcomes :on-exhausted state",
                "        (fn (state) (if finish (done state) (continue state))))))",
                ")",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        validate_shared=True,
        workspace_root=tmp_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
    )

    type_env = result.typed_program.type_env
    span = SourceSpan(
        start=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
        end=SourcePosition(path=str(workflow_path), line=1, column=2, offset=1),
    )
    for type_name, field_name, item_type in (
        ("List[Task]", "", "record"),
        ("Progress", "tasks", "record"),
        ("List[TaskOutcome]", "", "union"),
    ):
        type_ref = type_env.resolve_type(type_name, span=span,
            form_path=("workflow-lisp", "defworkflow", "root-loop"))
        plan = build_loop_lowering_plan(step_name_prefix="rich-list",
            state_type_ref=type_ref, result_type_ref=type_ref, span=span,
            form_path=("workflow-lisp", "defworkflow", "root-loop"), type_env=type_env)
        for root, projection in (("state", plan.state_projection), ("result", plan.result_projection)):
            field = projection.flattened_fields[0]
            assert field.source_path == ((root, field_name) if field_name else (root,))
            assert field.contract_definition["kind"] == "collection"
            assert field.contract_definition["items"]["type"] == item_type


def test_lowering_rich_list_union_exhaustion_return_keeps_typed_outcome(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "rich_list_union_exhaustion_old_target.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Task (task_id String))",
                "  (defunion TaskOutcome (PENDING (task Task)) (BLOCKED (reason String)))",
                "  (defrecord Progress (remaining List[TaskOutcome]) (label String))",
                "  (defrecord Summary (work List[TaskOutcome]) (note String))",
                "  (defunion Outcome",
                "    (INCOMPLETE (summary Summary))",
                "    (COMPLETE (note String)))",
                "  (defworkflow nested-rich-list-loop ((finish Bool)) -> Outcome",
                "    (let* ((outcomes",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs ()",
                "               :returns List[TaskOutcome])))",
                "      (loop/recur :max 1",
                "        :state (record Progress :remaining outcomes :label \"state\")",
                "        :on-exhausted",
                "          (variant Outcome INCOMPLETE",
                "            :summary (record Summary :work state.remaining :note \"exhausted\"))",
                "        (fn (state)",
                "          (if finish",
                "              (done (variant Outcome COMPLETE :note \"done\"))",
                "              (continue state))))))",
                ")",
            ]
        ),
    )

    result = compile_stage3_module(workflow_path, validate_shared=True, workspace_root=tmp_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"})
    [workflow] = result.typed_workflows
    assert workflow.signature.return_type_ref.name == "Outcome"
    assert set(workflow.signature.return_type_ref.variant_field_types) == {"INCOMPLETE", "COMPLETE"}



def test_lowering_outer_record_exhaustion_variant_keeps_typed_result(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "outer_record_exhaustion_variant.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Task (task_id String))",
                "  (defrecord Progress (remaining List[Task]))",
                "  (defunion Outcome",
                "    (INCOMPLETE (remaining List[Task]) (note String))",
                "    (COMPLETE (note String)))",
                "  (defrecord Result (outcome Outcome))",
                "  (defworkflow outer-record-exhaustion",
                "    ((tasks List[Task]) (finish Bool)) -> Result",
                "    (loop/recur :max 1",
                "      :state (record Progress :remaining tasks)",
                "      :on-exhausted",
                "        (record Result",
                "          :outcome (variant Outcome INCOMPLETE",
                "            :remaining state.remaining",
                "            :note \"exhausted\"))",
                "      (fn (state)",
                "        (if finish",
                "            (done (record Result",
                "              :outcome (variant Outcome COMPLETE :note \"done\")))",
                "            (continue state)))))",
                ")",
            ]
        ),
    )

    result = compile_stage3_module(workflow_path, validate_shared=True, workspace_root=tmp_path)
    [workflow] = result.typed_workflows
    assert workflow.definition.name == "entry::outer-record-exhaustion"
    assert workflow.signature.return_type_ref.field_types["outcome"].name == "Outcome"



@pytest.mark.parametrize("list_type", ("List[Task]", "List[Optional[Task]]"))
def test_lowering_nested_rich_loop_state_keeps_typed_tasks(
    tmp_path: Path,
    list_type: str,
) -> None:
    workflow_path = _write_module(
        tmp_path / "nested_rich_loop.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Task (task_id String))",
                f"  (defrecord Progress (tasks {list_type}))",
                "  (defworkflow legacy-nested ((tasks " + list_type + ") (finish Bool)) -> Progress",
                "    (loop/recur :max 1",
                "      :state (record Progress :tasks tasks)",
                "      :on-exhausted state",
                "      (fn (state) (if finish (done state) (continue state)))))",
                ")",
            ]
        ),
    )

    result = compile_stage3_module(workflow_path, validate_shared=True, workspace_root=tmp_path)
    [workflow] = result.typed_workflows
    assert workflow.signature.return_type_ref.field_types["tasks"].name == list_type



@pytest.mark.parametrize(
    ("bad_type", "expected_code"),
    [
        ("Provider", "workflow_boundary_type_invalid"),
        ("Prompt", "workflow_boundary_type_invalid"),
        ("Json", "json_surface_unsupported"),
    ],
)
def test_lowering_rich_return_admission_retains_unsupported_leaf_refusals(
    tmp_path: Path,
    bad_type: str,
    expected_code: str,
) -> None:
    workflow_path = _write_module(
        tmp_path / f"rich_return_{bad_type.lower()}_rejected.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defunion InnerChoice (YES (value String)) (NO))",
                "  (defunion OuterChoice (NESTED (choice InnerChoice)) (PLAIN))",
                f"  (defrecord Summary (prior_choice OuterChoice) (notes List[String]) (work List[{bad_type}]))",
                "  (defunion Outcome",
                "    (INCOMPLETE (summary Summary))",
                "    (COMPLETE (note String)))",
                "  (defworkflow invalid-rich-return ((finish Bool)) -> Outcome",
                "    (if finish",
                "        (variant Outcome COMPLETE :note \"done\")",
                "        (variant Outcome COMPLETE :note \"not-done\")))",
                ")",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            workflow_path,

            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == expected_code


def test_build_workflow_catalog_reconstructs_imported_typed_rich_union_return_at_229(
    tmp_path: Path,
) -> None:
    imported_source = _write_module(
        tmp_path / "imported_rich_union_return.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Task (task_id String))",
                "  (defunion TaskOutcome",
                "    (PENDING (task Task))",
                "    (BLOCKED (reason String)))",
                "  (defrecord Summary (work List[TaskOutcome]))",
                "  (defunion Outcome",
                "    (INCOMPLETE (summary Summary))",
                "    (COMPLETE (note String)))",
                "  (defworkflow imported-rich-return ((finish Bool)) -> Outcome",
                "    (if finish",
                "        (variant Outcome COMPLETE :note \"done\")",
                "        (variant Outcome COMPLETE :note \"not-done\")))",
                ")",
            ]
        ),
    )
    imported = compile_stage3_module(
        imported_source,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    assert imported.typed_program.target == "2.35"
    assert imported.typed_program.entry_module == "entry"
    caller_types = _write_module(
        tmp_path / "caller_rich_union_return_types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Task (task_id String))",
                "  (defunion TaskOutcome",
                "    (PENDING (task Task))",
                "    (BLOCKED (reason String)))",
                "  (defrecord Summary (work List[TaskOutcome]))",
                "  (defunion Outcome",
                "    (INCOMPLETE (summary Summary))",
                "    (COMPLETE (note String)))",
                ")",
            ]
        ),
    )
    caller_module = _compile_definition_module(caller_types)
    workflow_catalog = build_workflow_catalog(
        caller_module,
        (),
        FrontendTypeEnvironment.from_module(caller_module),
        imported_programs={"imported-rich-return": _select_and_finalize_typed_program(imported,
            entry_path=imported_source, entry_workflow="imported-rich-return")},
    )

    assert workflow_catalog.signatures_by_name[
        "imported-rich-return"
    ].return_type_ref.name == "Outcome"


def test_lowering_loop_recur_rejects_missing_active_union_field(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            LOOP_RECUR_UNION_RESULT_MISSING_ACTIVE_FIELD_FIXTURE,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,

        )

    diagnostic = excinfo.value.diagnostics[0]

    assert diagnostic.code == "record_field_missing"
    assert diagnostic.span.start.path.endswith("loop_recur_union_result_missing_active_field.orc")
    assert diagnostic.form_path == (
        "workflow-lisp",
        "defworkflow",
        "loop-recur-union-result-missing-active-field",
    )


def test_typed_effect_inference_descends_through_if_expr(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "if_provider_requirements.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (ready Bool)",
                "    (report WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport))",
                "  (defworkflow provider-helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (if input.ready",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs (input.report)",
                "        :returns WorkflowOutput)",
                "      (record WorkflowOutput",
                "        :report input.report))))",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    typed_workflow = result.typed_workflows[0]
    effects = typed_workflow.typed_body.effect_summary.transitive_effects
    assert UsesProviderEffect(subject=("providers", "execute")) in effects
    provider = next(node for node in walk_expr(typed_workflow.typed_body.expr) if isinstance(node, ProviderResultExpr))
    assert provider.prompt.name == "prompts.implementation.execute"








def test_derived_phase_context_eligibility_refuses_generic_caller_without_item_ctx(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "generic_child_phase_context_without_item_ctx.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule generic_child_phase_context_without_item_ctx)",
                "  (import std/phase :only (with-phase))",
                "  (export entry)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Payload",
                "    (status String))",
                "  (defrecord Result",
                "    (status String))",
                "  (defworkflow child",
                "    ((phase-ctx PhaseCtx)",
                "     (payload Payload))",
                "    -> Result",
                "    (with-phase phase-ctx generic",
                "      (record Result",
                "        :status payload.status)))",
                "  (defworkflow entry",
                "    ((payload Payload))",
                "    -> Result",
                "    (call child",
                "      :payload payload)))",
            ]
        ),
        encoding="utf-8",
    )
    profile_path = tmp_path / "generic_child_phase_context_without_item_ctx.profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_family_profile.v1",
                "family_id": "generic_child_phase_context_without_item_ctx",
                "workflow_name_prefixes": [],
                "target_workflows": [
                    "generic_child_phase_context_without_item_ctx::child"
                ],
                "boundary_authority_registry": None,
                "checked_public_inputs": {},
                "entry_phase_identities": {},
                "hidden_context_rules": [
                    {
                        "workflow_name": "generic_child_phase_context_without_item_ctx::child",
                        "parameter_name": "phase-ctx",
                        "phase_identity": "generic",
                    }
                ],
                "typed_prompt_input_rows": [],
            }
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(tmp_path,),
        command_boundaries={},
        validate_shared=False,

        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog((profile_path,)),
    )
    caller = _select_and_finalize_typed_program(result.entry_result,
        entry_path=Path(result.entry_result.module.span.start.path), entry_workflow="entry")
    diagnostic = derived_private_child_context_eligibility(caller.entry.signature, param_name="phase-ctx")
    assert not diagnostic.allowed
    assert diagnostic.diagnostic_code == "derived_phase_context_binding_invalid"
    assert "item-context-first route" in diagnostic.diagnostic_message

















def test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_non_exported_workflow(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    workflow_path = source_root / "promoted_pkg" / "entry.orc"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    _write_module(
        workflow_path,
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule promoted_pkg/entry)",
                "  (import library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper",
                "    :as bootstrap",
                "    :only (ResumeInputs PlanGateWrapperSurfaceResult resume-plan-gate-wrapper))",
                "  (export promoted-entry-resume-plan-gate-wrapper)",
                "  (defworkflow promoted-entry-resume-plan-gate-wrapper",
                "    ((inputs bootstrap.ResumeInputs))",
                "    -> bootstrap.PlanGateWrapperSurfaceResult",
                "    (call bootstrap.resume-plan-gate-wrapper",
                "      :inputs inputs))",
                "  (defworkflow helper-wrapper",
                "    ((inputs bootstrap.ResumeInputs))",
                "    -> bootstrap.PlanGateWrapperSurfaceResult",
                "    (call bootstrap.resume-plan-gate-wrapper",
                "      :inputs inputs)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            workflow_path,
            source_roots=(source_root, FIXTURES / "valid"),
            command_boundaries={
                "resolve_plan_gate": ExternalToolBinding(
                    name="resolve_plan_gate",
                    stable_command=("python", "scripts/resolve_plan_gate.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    assert "phase-ctx" in diagnostic.message


def test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unselected_exported_entry_workflow(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "selected_later_exported_entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule selected_later_exported_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export first-entry second-entry helper ResumeInputs WorkflowOutput PhaseCtx RunCtx WorkReport)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ResumeInputs",
                "    (report_path WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report_path WorkReport))",
                "  (defworkflow first-entry",
                "    ((inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (call helper",
                "      :inputs inputs))",
                "  (defworkflow second-entry",
                "    ((inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (call helper",
                "      :inputs inputs))",
                "  (defworkflow helper",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record WorkflowOutput",
                "        :report_path inputs.report_path))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            workflow_path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
            entry_workflow="selected_later_exported_entry::second-entry",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    assert "phase-ctx" in diagnostic.message


def test_compile_stage3_entrypoint_rejects_hidden_context_omission_for_unselected_magic_name_entry_workflow(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "leak_hidden_context.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule leak_hidden_context)",
                "  (import std/phase :only (with-phase))",
                "  (export run-entry selected-entry helper ResumeInputs WorkflowOutput PhaseCtx RunCtx WorkReport)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ResumeInputs",
                "    (report_path WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report_path WorkReport))",
                "  (defworkflow run-entry",
                "    ((inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (call helper",
                "      :inputs inputs))",
                "  (defworkflow selected-entry",
                "    ((inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (call helper",
                "      :inputs inputs))",
                "  (defworkflow helper",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record WorkflowOutput",
                "        :report_path inputs.report_path))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            workflow_path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
            entry_workflow="leak_hidden_context::selected-entry",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    assert "phase-ctx" in diagnostic.message


def test_compile_stage3_entrypoint_names_the_denied_gate_for_unexported_non_magic_name_entry_workflow(
    tmp_path: Path,
) -> None:
    workflow_path = _write_module(
        tmp_path / "entry_bootstrap_gate_diagnostic_probe.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule entry_bootstrap_gate_diagnostic_probe)",
                "  (import std/phase :only (with-phase))",
                "  (export helper ResumeInputs WorkflowOutput PhaseCtx RunCtx WorkReport)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ResumeInputs",
                "    (report_path WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report_path WorkReport))",
                "  (defworkflow unexported-custom-entry",
                "    ((inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (call helper",
                "      :inputs inputs))",
                "  (defworkflow helper",
                "    ((phase-ctx PhaseCtx)",
                "     (inputs ResumeInputs))",
                "    -> WorkflowOutput",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record WorkflowOutput",
                "        :report_path inputs.report_path))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            workflow_path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
            entry_workflow="entry_bootstrap_gate_diagnostic_probe::unexported-custom-entry",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    denial_note = next(
        note
        for note in diagnostic.notes
        if "entry_bootstrap_name_gate_denied" in note
        and "unexported-custom-entry" in note
    )
    assert "explicit_entry_bootstrap_eligibility" in denial_note
    assert "docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md" in denial_note














def test_evaluated_result_boundary_rejects_authored_path_under_escape(tmp_path: Path) -> None:
    result = compile_stage3_module(REMAP_FIXTURE,
        command_boundaries={"run_checks": ExternalToolBinding(name="run_checks", stable_command=("python", "scripts/run_checks.py"))},
        workspace_root=tmp_path)
    workflow = result.typed_workflows[0]
    type_env = result.typed_program.workflow_type_env(workflow.definition.name)
    contract = derive_prompt_guided_structured_result_contract(workflow.signature.return_type_ref,
        workflow_name=workflow.definition.name, step_id="result", type_env=type_env,
        span=workflow.definition.span, form_path=("workflow-lisp", "defworkflow"))
    report = next(field for field in contract.payload["fields"] if field["name"] == "report")
    assert report["under"] == "../escape"
    node = {"class": "command", "contract": {"kind": contract.contract_kind, "payload": dict(contract.payload)},
        "result": compiler_normalized_type_descriptor(workflow.signature.return_type_ref, type_env=type_env)}
    with closing(WorkspaceFiles(tmp_path)) as files:
        with pytest.raises(OutputContractError) as excinfo:
            validate_effect_result(node, b'{"status":"ok","report":"report.md"}', "result.json", files)
    assert excinfo.value.violations[0]["type"] == "invalid_under_root"
    assert excinfo.value.violations[0]["context"]["under"] == "../escape"


@pytest.mark.parametrize(
    ("field_defs", "field_type"),
    [
        ((), "Json"),
        ((), "Provider"),
        ((), "Prompt"),
    ],
)
def test_shared_result_contract_rejects_unsupported_collection_element_types(
    tmp_path: Path,
    field_defs: tuple[str, ...],
    field_type: str,
) -> None:
    workflow_path = _write_module(
        tmp_path / "unsupported_collection_element.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                *field_defs,
                "  (defrecord InvalidResult",
                f"    (payloads List[{field_type}]))",
                "  (defrecord WorkflowOutput",
                "    (report String))",
                "  (defworkflow orchestrate",
                "    ()",
                "    -> WorkflowOutput",
                "    (let* ((result",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs ()",
                "               :returns InvalidResult)))",
                '      (record WorkflowOutput :report "ok"))))',
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    workflow = result.typed_workflows[0]
    provider = next(node for node in walk_expr(workflow.typed_body.expr) if isinstance(node, ProviderResultExpr))
    type_env = result.typed_program.workflow_type_env(workflow.definition.name)
    result_type = type_env.resolve_type(provider.returns_type_name, span=provider.span, form_path=provider.form_path)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        derive_prompt_guided_structured_result_contract(result_type, workflow_name=workflow.definition.name,
            step_id="result", type_env=type_env, span=provider.span, form_path=provider.form_path)
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "collection_element_type_unsupported"
    assert diagnostic.span == provider.span
    assert diagnostic.form_path == provider.form_path


def test_stage3_entrypoint_coexists_with_explicit_imported_typed_program(tmp_path: Path) -> None:
    imported_bundle_source = tmp_path / "selector_run.orc"
    imported_bundle_source.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
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
        ),
        encoding="utf-8",
    )
    imported_bundle = compile_stage3_module(
        imported_bundle_source,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    imported_program = _select_and_finalize_typed_program(imported_bundle,
        entry_path=imported_bundle_source, entry_workflow="selector-run")

    source_root = MODULE_FIXTURES / "valid" / "imported_bundle_mix"
    result = compile_stage3_entrypoint(
        source_root / "neurips" / "entry.orc",
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        imported_programs={"selector-run": imported_program},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "selector-run" in result.entry_result.workflow_catalog.signatures_by_name
    assert "neurips/helper::provider-attempt" in result.entry_result.workflow_catalog.signatures_by_name


def test_compile_stage3_module_normalizes_function_calls_before_lowering(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "valid" / "defun_forward_ref.orc",
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert all(type(node).__name__ != "FunctionCallExpr"
        for node in _walk_dataclass_values(result.typed_workflows[0].typed_body))


def test_compile_stage3_module_supports_helper_match_after_provider_binding(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "helper_match_after_provider_binding.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defun summarize",
                "    ((attempt ImplementationState))",
                "    -> ImplementationSummary",
                "    (match attempt",
                "      ((COMPLETED completed)",
                "       (record ImplementationSummary",
                "         :report completed.execution_report))",
                "      ((BLOCKED blocked)",
                "       (record ImplementationSummary",
                "         :report blocked.progress_report))))",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report_path)",
                "               :returns ImplementationState)))",
                "      (summarize attempt))))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].definition.name == "entry::orchestrate"


def test_compile_stage3_module_supports_helper_alias_then_match_lowering(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "helper_alias_then_match.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report_path)",
                "               :returns ImplementationState))",
                "            (alias attempt))",
                "      (match alias",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary",
                "           :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary",
                "           :report blocked.progress_report))))))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].definition.name == "entry::orchestrate"


def test_lower_workflow_definitions_distinguish_forwarded_proc_ref_bindings_with_shared_lexical_names(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "proc_ref_forwarded_binding_identity.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (report WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport))",
                "  (defproc helper-a",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ((uses-command run_checks))",
                "    :lowering private-workflow",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.report "a")',
                "      :returns WorkflowOutput))",
                "  (defproc helper-b",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ((uses-command run_checks))",
                "    :lowering private-workflow",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.report "b")',
                "      :returns WorkflowOutput))",
                "  (defproc forward",
                "    ((runner ProcRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ()",
                "    :lowering inline",
                "    (runner input))",
                "  (defworkflow first",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (let* ((runner (proc-ref helper-a))",
                "           (forwarder (bind-proc (proc-ref forward)",
                "                        :runner runner)))",
                "      (forwarder input)))",
                "  (defworkflow second",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (let* ((runner (proc-ref helper-b))",
                "           (forwarder (bind-proc (proc-ref forward)",
                "                        :runner runner)))",
                "      (forwarder input))))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    forwarded_specializations = [
        procedure
        for procedure in result.typed_procedures
        if procedure.definition.name.startswith("%proc-ref.entry.forward.")
    ]
    bound_runner_targets = {
        procedure.specialization.proc_ref_bindings["runner"].procedure_name
        for procedure in forwarded_specializations
    }

    assert len(forwarded_specializations) == 2
    assert bound_runner_targets == {"entry::helper-a", "entry::helper-b"}

@pytest.mark.parametrize("source", (
    DERIVED_PHASE_CONTEXT_BINDING_INVALID_FIXTURE,
    DERIVED_PHASE_CONTEXT_DIRECT_ENTRY_INVALID_FIXTURE,
    DERIVED_PHASE_CONTEXT_NON_ITEM_CTX_ROOT_INVALID_FIXTURE,
    DERIVED_PHASE_CONTEXT_AMBIGUOUS_FIXTURE,
    DERIVED_PHASE_CONTEXT_PUBLIC_RUN_LEAVES_INVALID_FIXTURE,
    DERIVED_PHASE_CONTEXT_FROM_COMPATIBILITY_BRIDGE_INVALID_FIXTURE,
    DERIVED_PHASE_CONTEXT_REREAD_INVALID_FIXTURE,
), ids=lambda source: source.stem)
def test_historical_private_context_fixture_is_refused(tmp_path: Path, source: Path) -> None:
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    original = source.read_bytes()
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_typed_program(source, entry_workflow="run-entry",
            source_roots=(source.parent,), command_boundaries={}, workspace_root=tmp_path)
    assert caught.value.diagnostics[0].code == "target_dsl_unsupported"
    assert source.read_bytes() == original

@pytest.mark.parametrize("definition", (
    "(defrecord NestedPayload (value String))",
    "(defunion NestedPayload (VALUE (value String)))",
), ids=("record", "union"))
def test_shared_result_contract_accepts_nested_collection_payloads(tmp_path: Path, definition: str) -> None:
    source = _write_module(tmp_path / "nested_result.orc",
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        + definition + ' (defrecord Result (payloads List[NestedPayload])) '
        '(defworkflow run () -> Result (provider-result p :prompt q :inputs () :returns Result)))')
    result = compile_stage3_module(source, provider_externs={"p": "test"},
        prompt_externs={"q": "prompt.md"}, workspace_root=tmp_path, validate_shared=False)
    [workflow] = result.typed_workflows
    type_env = result.typed_program.workflow_type_env(workflow.definition.name)
    contract = derive_prompt_guided_structured_result_contract(workflow.signature.return_type_ref,
        workflow_name=workflow.definition.name, step_id="result", type_env=type_env,
        span=workflow.definition.span, form_path=workflow.definition.form_path)
    [field] = contract.payload["fields"]
    assert field["name"] == "payloads"
    assert field["type"] == "list"
