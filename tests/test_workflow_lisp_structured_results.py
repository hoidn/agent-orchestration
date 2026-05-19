from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_module,
    compile_stage1_module,
)
from orchestrator.workflow_lisp.contracts import (
    derive_structured_result_contract,
    derive_workflow_signature_contracts,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, WorkflowLispSyntaxModule, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef, RecordTypeRef, UnionTypeRef
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    WorkflowSignature,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
PHASE_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"


def _build_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    return build_syntax_module(read_sexpr_file(path))


def _build_type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_structured_result.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_structured_result.orc",
        form_path=("workflow-lisp", "structured-result-test"),
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _typecheck_fixture(path: Path, *, types_path: Path = TYPE_FIXTURE, **typecheck_kwargs):
    module = _compile_definition_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=build_workflow_catalog(
            module,
            workflow_defs,
            type_env,
        ),
        **typecheck_kwargs,
    )


def test_typecheck_workflow_definitions_validates_same_file_call_signatures() -> None:
    from orchestrator.workflow_lisp import (
        CertifiedAdapterBinding,
        CommandBoundaryEnvironment,
        ExternEnvironment,
        ExternalToolBinding,
        PromptExtern,
        ProviderExtern,
    )

    typed_workflows = _typecheck_fixture(
        FIXTURES / "valid" / "structured_results.orc",
        types_path=FIXTURES / "valid" / "structured_results.orc",
        extern_environment=ExternEnvironment(
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
        ),
        command_boundary_environment=CommandBoundaryEnvironment(
            bindings_by_name={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
                "normalize_result": CertifiedAdapterBinding(
                    name="normalize_result",
                    stable_command=("python", "scripts/normalize_result.py"),
                    input_contract={"type": "object"},
                    output_type_name="ImplementationSummary",
                    effects=("structured_result",),
                    path_safety={"kind": "workspace_relpath"},
                    source_map_behavior="step",
                    fixture_ids=("normalize_result_ok",),
                    negative_fixture_ids=("normalize_result_bad",),
                ),
            }
        ),
    )

    assert [typed_workflow.definition.name for typed_workflow in typed_workflows] == [
        "command_checks",
        "provider_attempt",
        "orchestrate",
    ]
    assert isinstance(typed_workflows[0].signature.return_type_ref, RecordTypeRef)
    assert isinstance(typed_workflows[1].signature.return_type_ref, RecordTypeRef)
    assert typed_workflows[2].typed_body.type_ref == typed_workflows[1].signature.return_type_ref


def test_macro_emitted_command_result_respects_existing_command_boundary_rules() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "valid" / "macro_workflow_alias.orc",
            validate_shared=False,
        )

    assert excinfo.value.diagnostics[0].code in {
        "command_adapter_missing_contract",
        "command_result_argv_invalid",
        "provider_result_provider_invalid",
    }


def test_typecheck_workflow_definitions_rejects_unknown_callees(tmp_path: Path) -> None:
    missing_callee = _write_module(
        tmp_path / "unknown_callee_stage3.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow missing-helper",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call helper",
                "      :input input",
                "      :report_path report_path)))",
            ]
        ),
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(missing_callee)

    _assert_diagnostic_code(excinfo, "workflow_call_unknown")


def test_derive_structured_result_contract_for_phase_translation_union_keeps_variant_fields() -> None:
    module = _compile_definition_module(PHASE_FIXTURE)
    type_env = FrontendTypeEnvironment.from_module(module)
    implementation_attempt = type_env.resolve_type(
        "ImplementationAttempt",
        span=_build_syntax_module(PHASE_FIXTURE).span,
        form_path=("workflow-lisp", "defunion", "ImplementationAttempt"),
    )

    assert isinstance(implementation_attempt, UnionTypeRef)
    contract = derive_structured_result_contract(
        implementation_attempt,
        workflow_name="run-implementation-attempt",
        step_id="run-implementation-attempt__attempt",
        span=_build_syntax_module(PHASE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "run-implementation-attempt"),
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload["discriminant"]["name"] == "variant"
    assert contract.payload["shared_fields"] == [
        {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        }
    ]
    assert contract.payload["variants"]["COMPLETED"]["fields"] == [
        {
            "name": "execution_report_path",
            "json_pointer": "/execution_report_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]
    assert contract.payload["variants"]["BLOCKED"]["fields"] == [
        {
            "name": "progress_report_path",
            "json_pointer": "/progress_report_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
        {
            "name": "blocker_class",
            "json_pointer": "/blocker_class",
            "type": "enum",
            "allowed": [
                "missing_resource",
                "unavailable_hardware",
                "roadmap_conflict",
                "external_dependency_outside_authority",
                "user_decision_required",
                "unrecoverable_after_fix_attempt",
            ],
        },
    ]


def test_typecheck_workflow_definitions_rejects_return_type_mismatches(tmp_path: Path) -> None:
    mismatch_path = _write_module(
        tmp_path / "return_type_mismatch.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow mismatch",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult)))",
            ],
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(mismatch_path)

    _assert_diagnostic_code(excinfo, "return_type_mismatch")


def test_typecheck_provider_result_requires_record_or_union_return_types(tmp_path: Path) -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute "
            ":prompt prompts.implementation.execute "
            ":inputs (input report_path) "
            ":returns WorkReport)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.implementation.execute", "input", "report_path"}),
    )
    with pytest.raises(LispFrontendCompileError) as bad_return:
        typecheck_expression(
            expr,
            type_env=_build_type_env(),
            value_env={
                "providers.execute": PrimitiveTypeRef(name="Provider"),
                "prompts.implementation.execute": PrimitiveTypeRef(name="Prompt"),
                "input": _build_type_env().resolve_type(
                    "ChecksResult",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
                "report_path": _build_type_env().resolve_type(
                    "WorkReport",
                    span=expr.span,
                    form_path=expr.form_path,
                ),
            },
        )
    _assert_diagnostic_code(bad_return, "provider_result_return_type_invalid")

    invalid_provider_path = _write_module(
        tmp_path / "provider_operand_type_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-result input",
                "      :prompt report_path",
                "      :inputs (input report_path)",
                "      :returns ImplementationState)))",
            ],
        ),
    )

    with pytest.raises(LispFrontendCompileError) as invalid_operands:
        _typecheck_fixture(invalid_provider_path)

    assert invalid_operands.value.diagnostics[0].code in {"type_mismatch", "provider_result_provider_invalid"}


def test_typecheck_provider_result_rejects_missing_or_mismatched_externs(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp import ExternEnvironment, PromptExtern, ProviderExtern

    with pytest.raises(LispFrontendCompileError) as missing_externs:
        _typecheck_fixture(
            FIXTURES / "valid" / "structured_results.orc",
            types_path=FIXTURES / "valid" / "structured_results.orc",
            extern_environment=ExternEnvironment(bindings_by_name={}),
        )
    assert missing_externs.value.diagnostics[0].code == "provider_result_provider_invalid"

    missing_prompt_path = _write_module(
        tmp_path / "missing_prompt_extern.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
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
                '         (record ImplementationSummary :status "completed" :report completed.execution_report))',
                "        ((BLOCKED blocked)",
                '         (record ImplementationSummary :status "blocked" :report blocked.progress_report))))))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as missing_prompt:
        _typecheck_fixture(
            missing_prompt_path,
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.execute": ProviderExtern(
                        name="providers.execute",
                        provider_id="test-provider",
                    ),
                }
            ),
        )
    assert missing_prompt.value.diagnostics[0].code == "provider_result_prompt_invalid"

    mismatch_path = _write_module(
        tmp_path / "mismatched_externs.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
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
                    '         (record ImplementationSummary :status "completed" :report completed.execution_report))',
                    "        ((BLOCKED blocked)",
                    '         (record ImplementationSummary :status "blocked" :report blocked.progress_report))))))',
                ]
            ),
        )

    with pytest.raises(LispFrontendCompileError) as mismatched_externs:
        _typecheck_fixture(
            mismatch_path,
            extern_environment=ExternEnvironment(
                bindings_by_name={
                    "providers.execute": PromptExtern(
                        name="providers.execute",
                        asset_file="prompts/implementation/execute.md",
                    ),
                    "prompts.implementation.execute": ProviderExtern(
                        name="prompts.implementation.execute",
                        provider_id="test-provider",
                    ),
                }
            ),
        )
    assert mismatched_externs.value.diagnostics[0].code == "provider_result_provider_invalid"


def test_typecheck_command_result_rejects_inline_shell_and_python_glue(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as bad_return:
        _typecheck_fixture(FIXTURES / "invalid" / "command_result_bad_return.orc")
    _assert_diagnostic_code(bad_return, "command_result_return_type_invalid")

    with pytest.raises(LispFrontendCompileError) as inline_python:
        _typecheck_fixture(FIXTURES / "invalid" / "inline_python_command_result.orc")
    _assert_diagnostic_code(inline_python, "inline_python_command_in_workflow")

    with pytest.raises(LispFrontendCompileError) as inline_shell:
        _typecheck_fixture(FIXTURES / "invalid" / "inline_shell_command_result.orc")
    _assert_diagnostic_code(inline_shell, "inline_shell_command_in_workflow")

    wrapped_shell = _write_module(
        tmp_path / "wrapped_shell_command_result.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow wrapped-shell",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result wrapped_shell",
                '      :argv ("bash -lc" report_path)',
                "      :returns ChecksResult)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as wrapped_shell_error:
        _typecheck_fixture(
            wrapped_shell,
            command_boundary_environment=build_command_boundary_environment(
                {
                    "wrapped_shell": ExternalToolBinding(
                        name="wrapped_shell",
                        stable_command=("bash -lc",),
                    )
                }
            ),
        )
    _assert_diagnostic_code(wrapped_shell_error, "command_result_argv_invalid")

    for shell in ("bash", "sh"):
        split_shell = _write_module(
            tmp_path / f"{shell}_split_shell_command_result.orc",
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow wrapped-shell",
                    "    ((report_path WorkReport))",
                    "    -> ChecksResult",
                    "    (command-result wrapped_shell",
                    f'      :argv ("{shell}" "-lc" report_path)',
                    "      :returns ChecksResult)))",
                ]
            ),
        )

        with pytest.raises(LispFrontendCompileError) as split_shell_error:
            _typecheck_fixture(
                split_shell,
                command_boundary_environment=build_command_boundary_environment(
                    {
                        "wrapped_shell": ExternalToolBinding(
                            name="wrapped_shell",
                            stable_command=(shell, "-lc"),
                        )
                    }
                ),
            )
        _assert_diagnostic_code(split_shell_error, "inline_shell_command_in_workflow")


def test_typecheck_command_result_accepts_external_tool_and_certified_adapter_bindings(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp import (
        CertifiedAdapterBinding,
        CommandBoundaryEnvironment,
        ExternEnvironment,
        ExternalToolBinding,
        PromptExtern,
        ProviderExtern,
    )

    command_path = _write_module(
        tmp_path / "command_boundaries.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow run-checks",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult))",
                "  (defworkflow normalize",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result normalize_result",
                '      :argv ("python" "scripts/normalize_result.py" report_path)',
                "      :returns ImplementationSummary)))",
            ]
        ),
    )

    typed = _typecheck_fixture(
        command_path,
        extern_environment=ExternEnvironment(
            bindings_by_name={
                "providers.execute": ProviderExtern(name="providers.execute", provider_id="test-provider"),
                "prompts.implementation.execute": PromptExtern(
                    name="prompts.implementation.execute",
                    asset_file="prompts/implementation/execute.md",
                ),
            }
        ),
        command_boundary_environment=CommandBoundaryEnvironment(
            bindings_by_name={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                ),
                "normalize_result": CertifiedAdapterBinding(
                    name="normalize_result",
                    stable_command=("python", "scripts/normalize_result.py"),
                    input_contract={"type": "object"},
                    output_type_name="ImplementationSummary",
                    effects=("structured_result",),
                    path_safety={"kind": "workspace_relpath"},
                    source_map_behavior="step",
                    fixture_ids=("normalize_result_ok",),
                    negative_fixture_ids=("normalize_result_bad",),
                ),
            }
        ),
    )

    assert [workflow.definition.name for workflow in typed] == ["run-checks", "normalize"]


def test_typecheck_command_result_rejects_missing_semantic_adapter_metadata(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp import CommandBoundaryEnvironment, ExternalToolBinding

    command_path = _write_module(
        tmp_path / "semantic_command_missing_adapter.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow normalize",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (command-result normalize_result",
                '      :argv ("python" "scripts/normalize_result.py" report_path)',
                "      :returns ImplementationSummary)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            command_path,
            command_boundary_environment=CommandBoundaryEnvironment(
                bindings_by_name={
                    "run_checks": ExternalToolBinding(
                        name="run_checks",
                        stable_command=("python", "scripts/run_checks.py"),
                    )
                }
            ),
        )

    assert excinfo.value.diagnostics[0].code in {
        "name_unknown",
        "command_adapter_missing_contract",
        "command_result_argv_invalid",
    }


@pytest.mark.parametrize(
    ("input_contract", "path_safety"),
    [
        ({}, {"kind": "workspace_relpath"}),
        ({"type": "object"}, {}),
    ],
)
def test_build_command_boundary_environment_rejects_incomplete_certified_adapter_metadata(
    input_contract: dict[str, object],
    path_safety: dict[str, object],
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_command_boundary_environment(
            {
                "normalize_result": CertifiedAdapterBinding(
                    name="normalize_result",
                    stable_command=("python", "scripts/normalize_result.py"),
                    input_contract=input_contract,
                    output_type_name="ImplementationSummary",
                    effects=("structured_result",),
                    path_safety=path_safety,
                    source_map_behavior="step",
                    fixture_ids=("normalize_result_ok",),
                    negative_fixture_ids=("normalize_result_bad",),
                )
            }
        )

    _assert_diagnostic_code(excinfo, "command_adapter_missing_contract")


def test_derive_structured_result_contract_builds_output_bundle_for_record_results() -> None:
    type_env = _build_type_env()
    checks_result = type_env.resolve_type(
        "ChecksResult",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(checks_result, RecordTypeRef)
    contract = derive_structured_result_contract(
        checks_result,
        workflow_name="command_checks",
        step_id="command_checks__run_checks",
    )

    assert contract.contract_kind == "output_bundle"
    assert contract.path == ".orchestrate/workflow_lisp/command_checks/command_checks__run_checks/result.json"
    assert contract.payload["fields"] == [
        {
            "name": "status",
            "json_pointer": "/status",
            "type": "string",
        },
        {
            "name": "report",
            "json_pointer": "/report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]


def test_derive_structured_result_contract_builds_variant_output_for_union_results() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    contract = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload["discriminant"] == {
        "name": "variant",
        "json_pointer": "/variant",
        "type": "enum",
        "allowed": ["COMPLETED", "BLOCKED"],
    }
    assert contract.payload["shared_fields"] == []
    assert contract.payload["variants"]["COMPLETED"]["fields"] == [
        {
            "name": "execution_report",
            "json_pointer": "/execution_report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }
    ]
    assert contract.payload["variants"]["BLOCKED"]["fields"][1] == {
        "name": "blocker_class",
        "json_pointer": "/blocker_class",
        "type": "enum",
        "allowed": [
            "missing_resource",
            "unavailable_hardware",
            "roadmap_conflict",
            "external_dependency_outside_authority",
            "user_decision_required",
            "unrecoverable_after_fix_attempt",
        ],
    }


def test_generated_bundle_paths_are_deterministic() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    first = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )
    second = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert first.path == second.path
    assert first.payload == second.payload


def test_workflow_signature_contract_flattening_records_origin_metadata() -> None:
    type_env = _build_type_env()
    implementation_summary = type_env.resolve_type(
        "ImplementationSummary",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_summary, RecordTypeRef)
    signature = WorkflowSignature(
        name="summarize_checks",
        params=(("input", implementation_summary),),
        return_type_ref=implementation_summary,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "summarize_checks"),
    )

    inputs, outputs, flattened = derive_workflow_signature_contracts(signature)

    assert tuple(inputs) == ("input__status", "input__report")
    assert tuple(outputs) == ("return__status", "return__report")
    assert [field.generated_name for field in flattened] == [
        "input__status",
        "input__report",
        "return__status",
        "return__report",
    ]
    assert flattened[0].source_path == ("input", "status")
    assert flattened[-1].source_path == ("return", "report")
    assert inputs["input__report"].definition == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }


def test_workflow_signature_contract_flattening_recurses_nested_records() -> None:
    module = compile_stage1_module(TYPE_FIXTURE)
    type_env = FrontendTypeEnvironment.from_module(module)
    nested_summary = type_env.resolve_type(
        "NestedImplementationSummary",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(nested_summary, RecordTypeRef)
    signature = WorkflowSignature(
        name="summarize_nested_checks",
        params=(("input", nested_summary),),
        return_type_ref=nested_summary,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "summarize_nested_checks"),
    )

    inputs, outputs, flattened = derive_workflow_signature_contracts(signature)

    assert tuple(inputs) == ("input__summary__status", "input__summary__report")
    assert tuple(outputs) == ("return__summary__status", "return__summary__report")
    assert [field.generated_name for field in flattened] == [
        "input__summary__status",
        "input__summary__report",
        "return__summary__status",
        "return__summary__report",
    ]
    assert flattened[0].source_path == ("input", "summary", "status")
    assert flattened[-1].source_path == ("return", "summary", "report")


@pytest.mark.parametrize(
    ("bad_type", "expected_code"),
    [
        ("Provider", "workflow_boundary_type_invalid"),
        ("Prompt", "workflow_boundary_type_invalid"),
        ("Json", "json_surface_unsupported"),
    ],
)
def test_build_workflow_catalog_rejects_unsupported_boundary_types_in_validated_contracts(
    tmp_path: Path,
    bad_type: str,
    expected_code: str,
) -> None:
    types_path = _write_module(
        tmp_path / f"boundary_types_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord InvalidInput",
                f"    (value {bad_type})",
                "    (report WorkReport))",
                "  (defrecord InvalidOutput",
                f"    (value {bad_type})",
                "    (report WorkReport)))",
            ]
        ),
    )
    module = compile_stage1_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_path = _write_module(
        tmp_path / f"boundary_workflow_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow summarize",
                "    ((input InvalidInput))",
                "    -> InvalidOutput",
                '    (record InvalidOutput :value "x" :report input.report)))',
            ]
        ),
    )
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(workflow_path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(module, workflow_defs, type_env)

    _assert_diagnostic_code(excinfo, expected_code)
