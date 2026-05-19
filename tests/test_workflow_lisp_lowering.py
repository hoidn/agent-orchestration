from pathlib import Path

import pytest

from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lowering import lower_workflow_definitions, validate_lowered_workflows
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
STRUCTURED_RESULTS_FIXTURE = FIXTURES / "valid" / "structured_results.orc"
PHASE_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"
REMAP_FIXTURE = FIXTURES / "invalid" / "shared_validation_remap.orc"


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
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
        command_boundary_environment=_command_boundary_environment(),
    )


def test_lower_workflow_definitions_emits_authored_mappings_with_hidden_write_roots() -> None:
    lowered = lower_workflow_definitions(
        _typed_fixture_workflows(),
        workflow_path=STRUCTURED_RESULTS_FIXTURE,
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
    lowered = lower_workflow_definitions(
        _typed_fixture_workflows(),
        workflow_path=STRUCTURED_RESULTS_FIXTURE,
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


def test_lower_workflow_definitions_supports_projection_only_match_record_outputs(tmp_path: Path) -> None:
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

    lowered = result.lowered_workflows[0].authored_mapping
    assert "providers" not in lowered
    assert tuple(lowered["outputs"]) == ("return__report",)
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
                "    (status String)",
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
