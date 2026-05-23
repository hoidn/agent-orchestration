import importlib
from dataclasses import fields, is_dataclass
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.exceptions import ValidationError, ValidationSubjectRef
from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.lowering import (
    _workflow_extern_requirements,
    lower_workflow_definitions,
    validate_lowered_workflows,
)
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    CommandBoundaryEnvironment,
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
STRUCTURED_RESULTS_FIXTURE = FIXTURES / "valid" / "structured_results.orc"
PHASE_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"
COLLECTION_STRUCTURED_RESULT_FIXTURE = FIXTURES / "valid" / "collection_structured_result.orc"
REMAP_FIXTURE = FIXTURES / "invalid" / "shared_validation_remap.orc"
PHASE_STDLIB_FIXTURE = FIXTURES / "valid" / "phase_stdlib_run_provider_phase.orc"
WORKFLOW_REF_FIXTURE = FIXTURES / "valid" / "workflow_refs_same_file.orc"
LOOP_RECUR_MINIMAL_FIXTURE = FIXTURES / "valid" / "loop_recur_minimal.orc"
IF_MINIMAL_FIXTURE = FIXTURES / "valid" / "if_conditionals_minimal.orc"


def _extern_environment() -> ExternEnvironment:
    return ExternEnvironment(
        bindings_by_name={
            "providers.execute": ProviderExtern(
                name="providers.execute",
                provider_id="test-provider",
            ),
            "prompts.implementation.execute": PromptExtern(
                name="prompts.implementation.execute",
                asset_file="prompts/implementation/execute.md",
            ),
        }
    )


def _command_boundary_environment() -> CommandBoundaryEnvironment:
    return CommandBoundaryEnvironment(
        bindings_by_name={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
        }
    )


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path

def _compile_definition_module(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _typed_fixture_workflows():
    module = _compile_definition_module(STRUCTURED_RESULTS_FIXTURE)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = build_syntax_module(read_sexpr_file(STRUCTURED_RESULTS_FIXTURE))
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
        command_boundary_environment=_command_boundary_environment(),
    )
    return typed_workflows, workflow_catalog


def test_lower_workflow_definitions_emits_authored_mappings_with_hidden_write_roots() -> None:
    typed_workflows, workflow_catalog = _typed_fixture_workflows()
    lowered = lower_workflow_definitions(
        typed_workflows,
        workflow_path=STRUCTURED_RESULTS_FIXTURE,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
        command_boundary_environment=_command_boundary_environment(),
    )

    assert [workflow.typed_workflow.definition.name for workflow in lowered] == [
        "command_checks",
        "provider_attempt",
        "orchestrate",
    ]

    command_checks = next(workflow for workflow in lowered if workflow.typed_workflow.definition.name == "command_checks")
    provider_attempt = next(
        workflow for workflow in lowered if workflow.typed_workflow.definition.name == "provider_attempt"
    )
    orchestrate = next(workflow for workflow in lowered if workflow.typed_workflow.definition.name == "orchestrate")

    assert isinstance(command_checks.authored_mapping, dict)
    assert command_checks.authored_mapping["version"] == "2.14"
    assert "imports" not in orchestrate.authored_mapping
    assert "__write_root__command_checks__run_checks__result_bundle" in command_checks.authored_mapping["inputs"]
    assert "__write_root__provider_attempt__attempt__result_bundle" in provider_attempt.authored_mapping["inputs"]
    assert "providers" not in provider_attempt.authored_mapping

    assert [step["id"] for step in provider_attempt.authored_mapping["steps"]] == [
        "provider_attempt__attempt",
        "provider_attempt__match_attempt",
    ]

    provider_step = provider_attempt.authored_mapping["steps"][0]
    assert provider_step["provider"] == "test-provider"
    assert provider_step["asset_file"] == "prompts/implementation/execute.md"
    assert provider_step["inject_output_contract"] is True
    assert "variant_output" in provider_step

    match_step = provider_attempt.authored_mapping["steps"][1]
    assert tuple(provider_attempt.authored_mapping["outputs"]) == ("return__report",)
    completed_case = match_step["match"]["cases"]["COMPLETED"]
    assert completed_case["outputs"]["return__report"]["from"]["ref"].endswith(".artifacts.execution_report")
    assert completed_case["steps"][0]["assert"]["compare"]["left"]["ref"].endswith(".artifacts.execution_report")
    assert (
        completed_case["steps"][0]["assert"]["compare"]["left"]
        == completed_case["steps"][0]["assert"]["compare"]["right"]
    )
    blocked_case = match_step["match"]["cases"]["BLOCKED"]
    assert blocked_case["outputs"]["return__report"]["from"]["ref"].endswith(".artifacts.progress_report")
    assert blocked_case["steps"][0]["assert"]["compare"]["left"]["ref"].endswith(".artifacts.progress_report")
    assert blocked_case["steps"][0]["assert"]["compare"]["left"] == blocked_case["steps"][0]["assert"]["compare"]["right"]

    command_step = command_checks.authored_mapping["steps"][0]
    assert command_step["command"] == ["python", "scripts/run_checks.py", "${inputs.report_path}"]
    assert "output_bundle" in command_step

    call_step = orchestrate.authored_mapping["steps"][0]
    assert call_step["call"] == "provider_attempt"
    assert (
        call_step["with"]["__write_root__provider_attempt__attempt__result_bundle"]
        == ".orchestrate/workflow_lisp/calls/orchestrate/orchestrate__call_provider_attempt/provider_attempt/__write_root__provider_attempt__attempt__result_bundle.json"
    )


def test_validate_lowered_workflows_reuses_in_memory_imported_bundles(tmp_path: Path) -> None:
    typed_workflows, workflow_catalog = _typed_fixture_workflows()
    lowered = lower_workflow_definitions(
        typed_workflows,
        workflow_path=STRUCTURED_RESULTS_FIXTURE,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
        command_boundary_environment=_command_boundary_environment(),
    )

    validated = validate_lowered_workflows(lowered, workspace_root=tmp_path)

    assert tuple(validated) == ("command_checks", "provider_attempt", "orchestrate")
    orchestrate_bundle = validated["orchestrate"]
    assert "provider_attempt" in orchestrate_bundle.surface.imports
    assert "imports" not in next(
        workflow for workflow in lowered if workflow.typed_workflow.definition.name == "orchestrate"
    ).authored_mapping
    assert workflow_managed_write_root_inputs(validated["provider_attempt"]) == (
        "__write_root__provider_attempt__attempt__result_bundle",
    )


def test_compile_stage3_module_returns_lowered_workflows_and_optional_bundles(tmp_path: Path) -> None:
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
        "command_checks",
        "provider_attempt",
        "orchestrate",
    ]
    assert len(no_validation.lowered_workflows) == 3
    assert no_validation.validated_bundles == {}
    assert tuple(validated.validated_bundles) == ("command_checks", "provider_attempt", "orchestrate")


def test_lower_workflow_definitions_supports_union_returning_same_file_calls(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_call_projection.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware",
                "    roadmap_conflict",
                "    external_dependency_outside_authority",
                "    user_decision_required",
                "    unrecoverable_after_fix_attempt)",
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
                "  (defworkflow helper",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationState",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input report_path)",
                "      :returns ImplementationState))",
                "  (defworkflow entry",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (call helper",
                "               :input input",
                "               :report_path report_path)))",
                "      (match attempt",
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
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "entry"
    )
    helper = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "helper"
    )

    assert any(step.get("call") == "helper" for step in authored["steps"])
    assert any("match" in step for step in authored["steps"])
    assert helper.boundary_projection.return_kind == "union"
    assert [field.generated_name for field in helper.boundary_projection.flattened_outputs] == [
        "return__variant",
        "return__execution_report",
        "return__progress_report",
        "return__blocker_class",
    ]
    assert set(helper.origin_map.authored_input_spans) == {"input__status", "input__report", "report_path"}
    assert set(helper.origin_map.internal_input_spans) == {
        "__write_root__helper__result__result_bundle",
    }
    assert set(helper.origin_map.generated_input_spans) == {
        "input__status",
        "input__report",
        "report_path",
        "__write_root__helper__result__result_bundle",
    }


def test_compile_stage3_module_preserves_macro_provenance_in_origin_maps(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "valid" / "macro_workflow_alias.orc",
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    command_checks = next(
        workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "command_checks"
    )
    origin = command_checks.origin_map.step_spans["command_checks__run_checks"]

    assert origin.expansion_stack[0].macro_name == "defworkflow-alias"
    assert origin.expansion_stack[0].expansion_id == "m0001"


def test_lowering_loop_recur_uses_repeat_until_with_typed_outputs(tmp_path: Path) -> None:
    result = compile_stage3_module(
        LOOP_RECUR_MINIMAL_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "loop-recur-minimal"
    )

    repeat_step = next(step for step in lowered["steps"] if "repeat_until" in step)
    assert repeat_step["name"] == "loop-recur-minimal__loop"
    assert repeat_step["repeat_until"]["condition"]["compare"]["right"] == "DONE"
    assert "state__variant" in repeat_step["repeat_until"]["outputs"]
    assert "result__status" in repeat_step["repeat_until"]["outputs"]
    assert "result__report" in repeat_step["repeat_until"]["outputs"]


def test_lowering_loop_recur_preserves_origin_map_for_generated_steps(tmp_path: Path) -> None:
    result = compile_stage3_module(
        LOOP_RECUR_MINIMAL_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "loop-recur-minimal"
    )

    assert set(lowered.origin_map.step_spans) >= {
        "loop-recur-minimal__seed",
        "loop-recur-minimal__loop",
        "loop-recur-minimal__result",
    }
    assert set(lowered.origin_map.generated_output_spans) >= {
        "return__status",
        "return__report",
    }
    assert any(
        "__write_root__loop_recur_minimal__attempt__result_bundle" in path
        for path in lowered.origin_map.generated_path_spans
    )


def test_lowering_if_bool_literal_emits_shared_if_step(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "if_bool_literal.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow choose-report",
                "    ((report_path WorkReport)",
                "     (fallback_path WorkReport))",
                "    -> ImplementationSummary",
                "    (if true",
                "      (record ImplementationSummary :report report_path)",
                "      (record ImplementationSummary :report fallback_path))))",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    if_step = lowered["steps"][0]

    assert "if" in if_step
    assert if_step["if"]["compare"]["left"] is True
    assert if_step["if"]["compare"]["right"] is True
    assert "then" in if_step
    assert "else" in if_step


def test_lowering_if_bool_ref_emits_artifact_bool_predicate(tmp_path: Path) -> None:
    result = compile_stage3_module(
        IF_MINIMAL_FIXTURE,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    if_step = lowered["steps"][0]

    assert if_step["if"] == {
        "artifact_bool": {
            "ref": "inputs.ready",
        }
    }


def test_lowering_if_projects_branch_outputs_for_record_result(tmp_path: Path) -> None:
    result = compile_stage3_module(
        IF_MINIMAL_FIXTURE,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    if_step = lowered["steps"][0]

    assert lowered["outputs"]["return__report"]["from"]["ref"] == (
        "root.steps.choose-report.artifacts.return__report"
    )
    assert if_step["then"]["outputs"]["return__report"]["from"]["ref"] == "inputs.report_path"
    assert if_step["else"]["outputs"]["return__report"]["from"]["ref"] == "inputs.fallback_path"


def test_workflow_extern_requirements_descend_through_if_expr(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "if_provider_requirements.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
    provider_names, prompt_names = _workflow_extern_requirements(
        typed_workflow,
        typed_procedures={procedure.definition.name: procedure for procedure in result.typed_procedures},
    )

    assert provider_names == {"providers.execute"}
    assert prompt_names == {"prompts.implementation.execute"}


def test_compile_stage3_module_includes_generated_private_procedure_workflow(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "valid" / "defproc_private_workflow.orc",
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]

    assert "%defproc_private_workflow.build-checks.v1" in lowered_names


def test_compile_stage3_module_supports_terminal_record_projection_returns(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "terminal_record_projection.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (status String)",
                "    (report WorkReport))",
                "  (defworkflow provider_attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationSummary)))",
                "      (record ImplementationSummary",
                "        :status attempt.status",
                "        :report attempt.report))))",
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

    lowered = result.lowered_workflows[0].authored_mapping
    assert [step["id"] for step in lowered["steps"]] == ["provider_attempt__attempt"]
    assert lowered["outputs"]["return__status"]["from"]["ref"].endswith(".artifacts.status")
    assert lowered["outputs"]["return__report"]["from"]["ref"].endswith(".artifacts.report")

def test_lower_workflow_definitions_supports_generic_match_outputs(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "generic_match_outputs.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord AttemptReport",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow provider_attempt",
                "    ((report_path WorkReport))",
                "    -> AttemptReport",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record AttemptReport :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record AttemptReport :report blocked.progress_report))))))",
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

    lowered_workflow = result.lowered_workflows[0]
    lowered = lowered_workflow.authored_mapping
    assert "providers" not in lowered
    assert tuple(lowered["outputs"]) == ("return__report",)
    assert [field.generated_name for field in lowered_workflow.boundary_projection.flattened_outputs] == [
        "return__report"
    ]
    match_step = lowered["steps"][1]
    completed_outputs = match_step["match"]["cases"]["COMPLETED"]["outputs"]
    assert completed_outputs["return__report"]["from"]["ref"].endswith(".artifacts.execution_report")
    assert (
        match_step["match"]["cases"]["COMPLETED"]["steps"][0]["assert"]["compare"]["left"]["ref"].endswith(
            ".artifacts.execution_report"
        )
    )
    assert (
        match_step["match"]["cases"]["BLOCKED"]["steps"][0]["assert"]["compare"]["left"]["ref"].endswith(
            ".artifacts.progress_report"
        )
    )


def test_compile_stage3_module_rejects_literal_only_match_exports(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "literal_match_exports.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
                "  (defworkflow provider_attempt",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary",
                '           :status "completed"',
                "           :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary",
                '           :status "blocked"',
                "           :report blocked.progress_report))))))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_return_not_exportable"
    assert "status" in diagnostic.message


def test_lower_workflow_definitions_accepts_same_file_call_field_bindings(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "field_bound_call.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defworkflow command_checks",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult))",
                "    -> ChecksResult",
                "    (call command_checks",
                "      :report_path input.report)))",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow.authored_mapping for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "orchestrate"
    )
    assert lowered["steps"][0]["with"]["report_path"] == {"ref": "inputs.input__report"}


def test_compile_stage3_module_remaps_shared_validation_failures() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            REMAP_FIXTURE,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries={"run_checks": ExternalToolBinding(name="run_checks", stable_command=("python", "scripts/run_checks.py"))},
            validate_shared=True,
            workspace_root=Path.cwd(),
        )

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "path_definition_invalid",
        "path_definition_invalid",
        "path_definition_invalid",
    ]
    assert all(diagnostic.span.start.path.endswith("shared_validation_remap.orc") for diagnostic in diagnostics)
    assert all("parent directory traversal" in diagnostic.message for diagnostic in diagnostics)
    assert all(diagnostic.validation_pass == "shared_validation" for diagnostic in diagnostics)
    assert all(diagnostic.authority_layer == "shared_validation" for diagnostic in diagnostics)
    assert "id must match" not in diagnostics[0].message


def test_compile_stage3_module_validates_hyphenated_workflow_names(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "hyphenated_workflow.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defworkflow run-checks",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult)))",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    assert lowered["name"] == "run-checks"
    assert lowered["steps"][0]["id"] == "run_checks__run_checks"
    assert tuple(result.validated_bundles) == ("run-checks",)


def test_compile_stage3_module_validates_hyphenated_provider_and_call_workflow_names(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "hyphenated_provider_and_call.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
                "    (status String)",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input report_path)",
                "      :returns ImplementationSummary))",
                "  (defworkflow orchestrate-run",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call provider-attempt",
                "      :input input",
                "      :report_path report_path))",
                ")",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    provider_attempt = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "provider-attempt"
    )
    orchestrate = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate-run"
    )

    assert [step["id"] for step in provider_attempt["steps"]] == ["provider_attempt__result"]
    assert orchestrate["steps"][0]["id"] == "orchestrate_run__call_provider_attempt"
    assert tuple(result.validated_bundles) == ("provider-attempt", "orchestrate-run")


def test_compile_stage3_module_supports_nested_record_workflow_boundaries(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "nested_boundary.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord InnerSummary",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord OuterSummary",
                "    (summary InnerSummary))",
                "  (defworkflow summarize",
                "    ((input OuterSummary))",
                "    -> OuterSummary",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.summary.report)',
                "      :returns OuterSummary))",
                "  (defworkflow orchestrate",
                "    ((input OuterSummary))",
                "    -> OuterSummary",
                "    (call summarize :input input)))",
            ]
        ),
    )

    result = compile_stage3_module(
        workflow_path,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    summarize = next(
        workflow.authored_mapping for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "summarize"
    )
    orchestrate = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )

    assert tuple(summarize["inputs"]) == (
        "input__summary__status",
        "input__summary__report",
        "__write_root__summarize__run_checks__result_bundle",
    )
    assert tuple(summarize["outputs"]) == ("return__summary__status", "return__summary__report")
    assert summarize["steps"][0]["output_bundle"]["fields"] == [
        {"name": "summary__status", "json_pointer": "/summary/status", "type": "string"},
        {
            "name": "summary__report",
            "json_pointer": "/summary/report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]
    assert orchestrate["steps"][0]["with"]["input__summary__status"] == {"ref": "inputs.input__summary__status"}
    assert orchestrate["steps"][0]["with"]["input__summary__report"] == {"ref": "inputs.input__summary__report"}


def test_compile_stage3_module_lowers_recursive_collection_structured_results(tmp_path: Path) -> None:
    result = compile_stage3_module(
        COLLECTION_STRUCTURED_RESULT_FIXTURE,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    orchestrate = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    provider_step = orchestrate["steps"][0]
    fields_by_name = {
        field["name"]: field for field in provider_step["output_bundle"]["fields"]
    }

    assert fields_by_name["owner"] == {
        "name": "owner",
        "json_pointer": "/owner",
        "type": "optional",
        "item": {"type": "string"},
    }
    assert fields_by_name["attempt_ids"] == {
        "name": "attempt_ids",
        "json_pointer": "/attempt_ids",
        "type": "list",
        "items": {"type": "integer"},
    }
    assert fields_by_name["reports"] == {
        "name": "reports",
        "json_pointer": "/reports",
        "type": "map",
        "keys": {"type": "string"},
        "values": {
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    }
    assert fields_by_name["review_states"] == {
        "name": "review_states",
        "json_pointer": "/review_states",
        "type": "list",
        "items": {
            "type": "optional",
            "item": {
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            },
        },
    }


@pytest.mark.parametrize(
    ("field_defs", "field_type"),
    [
        ((), "Json"),
        ((), "Provider"),
        ((), "Prompt"),
        (("  (defrecord NestedPayload", "    (value String))"), "NestedPayload"),
        (
            (
                "  (defunion NestedPayload",
                "    (VALUE",
                "      (value String)))",
            ),
            "NestedPayload",
        ),
    ],
)
def test_compile_stage3_module_rejects_unsupported_collection_element_types(
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
                '  (:target-dsl "2.14")',
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

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "collection_element_type_unsupported"


def test_compile_stage3_module_lowers_phase_translation_fixture_with_phase_scoped_bundle_path(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        PHASE_FIXTURE,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    assert tuple(lowered["outputs"]) == (
        "return__implementation_state",
        "return__implementation_state_bundle_path",
    )
    assert tuple(lowered["artifacts"]) == (
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    )
    assert "providers" not in lowered
    assert "__write_root__run_implementation_attempt__attempt__result_bundle" not in lowered["inputs"]

    prelude_step = lowered["steps"][0]
    assert prelude_step["name"] == "MaterializeImplementationAttemptPromptInputs"
    assert prelude_step["materialize_artifacts"] == {
        "values": [
            {
                "name": "design",
                "source": {"input": "inputs__design"},
                "contract": {"inherit": "source"},
                "pointer": {
                    "path": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/design.txt",
                },
            },
            {
                "name": "plan",
                "source": {"input": "inputs__plan"},
                "contract": {"inherit": "source"},
                "pointer": {
                    "path": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/plan.txt",
                },
            },
            {
                "name": "execution_report_target",
                "source": {"ref": "inputs.phase-ctx__execution_report_target"},
                "contract": lowered["inputs"]["phase-ctx__execution_report_target"],
                "pointer": {
                    "path": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/execution_report_target.txt",
                },
            },
            {
                "name": "progress_report_target",
                "source": {"ref": "inputs.phase-ctx__progress_report_target"},
                "contract": lowered["inputs"]["phase-ctx__progress_report_target"],
                "pointer": {
                    "path": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/progress_report_target.txt",
                },
            },
        ]
    }
    assert prelude_step["publishes"] == [
        {"artifact": "design", "from": "design"},
        {"artifact": "plan", "from": "plan"},
        {"artifact": "execution_report_target", "from": "execution_report_target"},
        {"artifact": "progress_report_target", "from": "progress_report_target"},
    ]
    assert lowered["artifacts"]["design"] == {
        "kind": "relpath",
        "type": "relpath",
        "under": "docs/design",
        "must_exist_target": True,
        "pointer": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/design.txt",
    }
    assert lowered["artifacts"]["plan"] == {
        "kind": "relpath",
        "type": "relpath",
        "under": "docs/plans",
        "must_exist_target": True,
        "pointer": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/plan.txt",
    }
    assert lowered["artifacts"]["execution_report_target"] == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
        "pointer": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/execution_report_target.txt",
    }
    assert lowered["artifacts"]["progress_report_target"] == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
        "pointer": ".orchestrate/workflow_lisp/run-implementation-attempt/materialized/progress_report_target.txt",
    }

    provider_step = lowered["steps"][1]
    assert provider_step["provider"] == "fake"
    assert provider_step["asset_file"] == "prompts/implementation/execute.md"
    assert provider_step["consumes"] == [
        {
            "artifact": "design",
            "policy": "latest_successful",
            "freshness": "any",
        },
        {
            "artifact": "plan",
            "policy": "latest_successful",
            "freshness": "any",
        },
        {
            "artifact": "execution_report_target",
            "policy": "latest_successful",
            "freshness": "any",
        },
        {
            "artifact": "progress_report_target",
            "policy": "latest_successful",
            "freshness": "any",
        },
    ]
    assert provider_step["prompt_consumes"] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    assert "variant_output" in provider_step
    assert provider_step["variant_output"]["path"] == "${inputs.phase-ctx__implementation_state_bundle_path}"

    match_step = lowered["steps"][2]
    assert match_step["match"]["ref"] == "root.steps.run-implementation-attempt__attempt.artifacts.variant"
    completed_outputs = match_step["match"]["cases"]["COMPLETED"]["outputs"]
    blocked_outputs = match_step["match"]["cases"]["BLOCKED"]["outputs"]
    assert completed_outputs["return__implementation_state"]["from"]["ref"].endswith(".artifacts.implementation_state")
    assert blocked_outputs["return__implementation_state"]["from"]["ref"].endswith(".artifacts.implementation_state")
    assert completed_outputs["return__implementation_state_bundle_path"] == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
        "from": {"ref": "inputs.phase-ctx__implementation_state_bundle_path"},
    }
    assert blocked_outputs["return__implementation_state_bundle_path"] == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
        "from": {"ref": "inputs.phase-ctx__implementation_state_bundle_path"},
    }


def test_compile_stage3_module_maps_phase_targets_by_name_not_position(tmp_path: Path) -> None:
    workflow_path = _write_module(
        tmp_path / "phase_targets_swapped.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum BlockerClass",
                "    missing_resource)",
                "  (defenum ImplementationStateTag",
                "    COMPLETED",
                "    BLOCKED)",
                "  (defpath DesignDocPath",
                "    :kind relpath",
                '    :under "docs/design"',
                "    :must-exist true)",
                "  (defpath PlanDocPath",
                "    :kind relpath",
                '    :under "docs/plans"',
                "    :must-exist true)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defpath ImplementationStateBundlePath",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord ImplementationAttemptInputs",
                "    (design DesignDocPath)",
                "    (plan PlanDocPath))",
                "  (defrecord ImplementationAttemptPhaseCtx",
                "    (implementation_state_bundle_path ImplementationStateBundlePath)",
                "    (execution_report_target WorkReportTarget)",
                "    (progress_report_target WorkReportTarget))",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (implementation_state ImplementationStateTag)",
                "      (execution_report_path WorkReport))",
                "    (BLOCKED",
                "      (implementation_state ImplementationStateTag)",
                "      (progress_report_path WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defrecord ImplementationAttemptSurfaceResult",
                "    (implementation_state ImplementationStateTag)",
                "    (implementation_state_bundle_path ImplementationStateBundlePath))",
                "  (defworkflow run-implementation-attempt",
                "    ((phase-ctx ImplementationAttemptPhaseCtx)",
                "     (inputs ImplementationAttemptInputs))",
                "    -> ImplementationAttemptSurfaceResult",
                "    (with-phase phase-ctx implementation",
                "      (let* ((attempt",
                "               (provider-result providers.execute",
                "                 :prompt prompts.implementation.execute",
                "                 :inputs (inputs.design",
                "                          inputs.plan",
                "                          (phase-target progress-report)",
                "                          (phase-target execution-report))",
                "                 :returns ImplementationAttempt)))",
                "        (match attempt",
                "          ((COMPLETED completed)",
                "           (record ImplementationAttemptSurfaceResult",
                "             :implementation_state completed.implementation_state",
                "             :implementation_state_bundle_path",
                "               phase-ctx.implementation_state_bundle_path))",
                "          ((BLOCKED blocked)",
                "           (record ImplementationAttemptSurfaceResult",
                "             :implementation_state blocked.implementation_state",
                "             :implementation_state_bundle_path",
                "               phase-ctx.implementation_state_bundle_path)))))))",
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

    prelude_values = result.lowered_workflows[0].authored_mapping["steps"][0]["materialize_artifacts"]["values"]
    prelude_by_name = {value["name"]: value for value in prelude_values}

    assert prelude_by_name["execution_report_target"]["source"] == {
        "ref": "inputs.phase-ctx__execution_report_target"
    }
    assert prelude_by_name["progress_report_target"]["source"] == {
        "ref": "inputs.phase-ctx__progress_report_target"
    }


def test_compile_stage3_module_labels_phase_prompt_hidden_inputs_distinct_from_write_roots(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        PHASE_STDLIB_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow
        for workflow in result.lowered_workflows
    }

    for workflow_name in ("run-provider-phase-demo", "produce-one-of-demo"):
        projection = lowered_by_name[workflow_name].boundary_projection
        assert projection.generated_internal_inputs
        assert {
            item.generated_name: item.reason for item in projection.generated_internal_inputs
        } == {
            f"__phase_prompt__{workflow_name}__attempt__execution_report_target": "phase_prompt_transport",
            f"__phase_prompt__{workflow_name}__attempt__progress_report_target": "phase_prompt_transport",
        }


def test_compile_stage3_entrypoint_coexists_with_explicit_imported_bundles(tmp_path: Path) -> None:
    compile_entrypoint = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_entrypoint), "compile_stage3_entrypoint is missing"

    imported_bundle_source = tmp_path / "selector_run.orc"
    imported_bundle_source.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
    ).validated_bundles["selector-run"]

    source_root = MODULE_FIXTURES / "valid" / "imported_bundle_mix"
    result = compile_entrypoint(
        source_root / "neurips" / "entry.orc",
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        imported_workflow_bundles={"selector-run": imported_bundle},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "selector-run" in result.entry_result.workflow_catalog.signatures_by_name
    assert "neurips/helper::provider-attempt" in result.entry_result.workflow_catalog.signatures_by_name


def test_origin_map_assigns_stable_origin_keys_and_validation_subject_bindings(tmp_path: Path) -> None:
    result = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    command_checks = next(
        workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "command_checks"
    )
    origin_map = command_checks.origin_map

    assert origin_map.workflow_origin.origin_key
    assert all(origin.origin_key for origin in origin_map.step_spans.values())
    assert all(origin.origin_key for origin in origin_map.authored_input_spans.values())
    assert all(origin.origin_key for origin in origin_map.internal_input_spans.values())
    assert all(origin.origin_key for origin in origin_map.generated_output_spans.values())
    assert all(origin.origin_key for origin in origin_map.generated_path_spans.values())
    assert {
        binding.subject_ref.subject_kind for binding in origin_map.validation_subject_bindings
    } >= {"workflow", "step_id", "generated_input", "generated_output", "generated_path"}


def test_source_map_remap_prefers_structured_validation_subject_refs(tmp_path: Path) -> None:
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering")
    raise_remapped = getattr(lowering_module, "_raise_remapped_validation_error")

    result = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    command_checks = next(
        workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "command_checks"
    )
    report_path_origin = next(
        origin
        for name, origin in command_checks.origin_map.authored_input_spans.items()
        if name.endswith("report_path")
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        raise_remapped(
            command_checks,
            [
                ValidationError(
                    "structured subject ref should win even when the message has no generated names",
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="generated_input",
                            subject_name=next(
                                name
                                for name in command_checks.origin_map.authored_input_spans
                                if name.endswith("report_path")
                            ),
                            workflow_name=command_checks.typed_workflow.definition.name,
                        ),
                    ),
                )
            ],
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.span == report_path_origin.span
    assert diagnostic.form_path == report_path_origin.form_path
    assert diagnostic.validation_pass == "shared_validation"
    assert diagnostic.authority_layer == "shared_validation"


def test_source_map_remap_adds_compatibility_note_for_message_fallback(tmp_path: Path) -> None:
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering")
    raise_remapped = getattr(lowering_module, "_raise_remapped_validation_error")

    result = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    command_checks = next(
        workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "command_checks"
    )
    generated_step_id = next(iter(command_checks.origin_map.step_spans))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        raise_remapped(
            command_checks,
            [
                ValidationError(
                    f"Step '{generated_step_id}': workflow_call_version_mismatch for imported workflow boundary",
                )
            ],
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_call_version_mismatch"
    assert diagnostic.validation_pass == "shared_validation"
    assert diagnostic.authority_layer == "shared_validation"
    assert any("message text fallback" in note for note in diagnostic.notes)


def test_source_map_remap_reports_missing_structured_subject_bindings(tmp_path: Path) -> None:
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering")
    raise_remapped = getattr(lowering_module, "_raise_remapped_validation_error")

    result = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        raise_remapped(
            next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "command_checks"),
            [
                ValidationError(
                    "subject ref is present but should not silently fall back to the workflow origin",
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="generated_input",
                            subject_name="missing_input",
                            workflow_name="command_checks",
                        ),
                    ),
                )
            ],
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "source_map_validation_ref_missing"
    assert diagnostic.validation_pass == "source_map"
    assert diagnostic.authority_layer == "frontend"


def test_source_map_validate_one_lowered_workflow_attaches_structured_subject_refs_from_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering")
    validate_one = getattr(lowering_module, "_validate_one_lowered_workflow")

    result = compile_stage3_module(
        REMAP_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    lowered = result.lowered_workflows[0]
    captured_errors: list[ValidationError] = []

    def capture_errors(lowered_workflow, errors):
        del lowered_workflow
        captured_errors.extend(errors)
        raise RuntimeError("captured shared validation errors")

    monkeypatch.setattr(lowering_module, "_raise_remapped_validation_error", capture_errors)

    with pytest.raises(RuntimeError, match="captured shared validation errors"):
        validate_one(
            lowered,
            workspace_root=tmp_path,
            imported_bundles={},
            workflow_is_imported=False,
        )

    assert [error.message for error in captured_errors] == [
        "inputs.report_path.under: parent directory traversal ('..') not allowed",
        "Step 'escaped-summary__run_checks': output_bundle.fields[1] under: parent directory traversal ('..') not allowed",
        "outputs.return__report.under: parent directory traversal ('..') not allowed",
    ]
    assert [
        tuple(
            (ref.subject_kind, ref.subject_name, ref.workflow_name)
            for ref in error.subject_refs
        )
        for error in captured_errors
    ] == [
        (("generated_input", "report_path", "escaped-summary"),),
        (("step_id", "escaped-summary__run_checks", "escaped-summary"),),
        (("generated_output", "return__report", "escaped-summary"),),
    ]


def test_source_map_validate_one_lowered_workflow_attaches_structured_subject_refs_for_output_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering")
    validate_one = getattr(lowering_module, "_validate_one_lowered_workflow")

    result = compile_stage3_module(
        STRUCTURED_RESULTS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    command_checks = next(
        workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "command_checks"
    )
    broken_outputs = dict(command_checks.authored_mapping["outputs"])
    broken_report = dict(broken_outputs["return__report"])
    broken_report["from"] = {"ref": "bad.ref"}
    broken_outputs["return__report"] = broken_report
    broken_workflow = replace(
        command_checks,
        authored_mapping={**dict(command_checks.authored_mapping), "outputs": broken_outputs},
    )
    captured_errors: list[ValidationError] = []

    def capture_errors(lowered_workflow, errors):
        del lowered_workflow
        captured_errors.extend(errors)
        raise RuntimeError("captured shared validation errors")

    monkeypatch.setattr(lowering_module, "_raise_remapped_validation_error", capture_errors)

    with pytest.raises(RuntimeError, match="captured shared validation errors"):
        validate_one(
            broken_workflow,
            workspace_root=tmp_path,
            imported_bundles={},
            workflow_is_imported=False,
        )

    assert [error.message for error in captured_errors] == [
        "outputs.return__report.from must reference root.steps.*",
    ]
    assert [
        tuple(
            (ref.subject_kind, ref.subject_name, ref.workflow_name)
            for ref in error.subject_refs
        )
        for error in captured_errors
    ] == [
        (("generated_output", "return__report", "command_checks"),),
    ]


def test_compile_stage3_module_normalizes_function_calls_before_lowering(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "valid" / "defun_forward_ref.orc",
        validate_shared=False,
        workspace_root=tmp_path,
    )

    def walk(node: object):
        yield node
        if is_dataclass(node):
            for field in fields(node):
                yield from walk(getattr(node, field.name))
            return
        if isinstance(node, tuple):
            for item in node:
                yield from walk(item)

    assert all(type(node).__name__ != "FunctionCallExpr" for node in walk(result.typed_workflows[0].typed_body))


def test_compile_stage3_module_supports_helper_match_after_provider_binding(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "helper_match_after_provider_binding.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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

    assert result.typed_workflows[0].definition.name == "orchestrate"


def test_compile_stage3_module_supports_helper_alias_then_match_lowering(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "helper_alias_then_match.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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

    assert result.typed_workflows[0].definition.name == "orchestrate"


def test_lower_workflow_definitions_specialize_same_file_workflow_ref_calls(tmp_path: Path) -> None:
    result = compile_stage3_module(
        WORKFLOW_REF_FIXTURE,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    entry = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "entry")
    call_step = entry.authored_mapping["steps"][0]

    assert call_step["call"] != "call-runner"
    assert call_step["call"].startswith("call-runner")


def test_lower_workflow_definitions_reuse_workflow_ref_specialized_procedure_private_workflow_calls(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "workflow_ref_private_procedure.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (report WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport))",
                "  (defworkflow echo-helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.report)',
                "      :returns WorkflowOutput))",
                "  (defproc invoke-runner",
                "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ((calls-workflow runner))",
                "    :lowering auto",
                "    (call runner",
                "      :input input))",
                "  (defworkflow first",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (invoke-runner echo-helper input))",
                "  (defworkflow second",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (invoke-runner echo-helper input)))",
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

    private_workflows = [
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.startswith("%workflow_ref_private_procedure.")
    ]
    assert len(private_workflows) == 1

    private_name = private_workflows[0].typed_workflow.definition.name
    assert "invoke-runner__spec__runner__echo_helper" in private_name

    first = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "first")
    second = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "second")

    assert first.authored_mapping["steps"][0]["call"] == private_name
    assert second.authored_mapping["steps"][0]["call"] == private_name


def test_compile_stage3_module_renders_helper_provenance_notes_for_shared_validation_errors(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "helper_shared_validation_remap.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath EscapedReport",
                "    :kind relpath",
                '    :under "../escape"',
                "    :must-exist true)",
                "  (defrecord EscapedSummary",
                "    (report EscapedReport))",
                "  (defun summarize",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    (record EscapedSummary",
                "      :report report_path))",
                "  (defworkflow orchestrate",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    (summarize report_path)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=True,
            workspace_root=tmp_path,
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "helper call site at" in rendered
    assert "helper definition at" in rendered
