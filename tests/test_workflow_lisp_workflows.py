import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    LetStarExpr,
    MatchExpr,
    NameExpr,
    ProviderResultExpr,
    RecordExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import SyntaxNode, WorkflowLispSyntaxModule, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, RecordTypeRef, UnionTypeRef
from orchestrator.workflow_lisp.workflows import (
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    WorkflowCatalog,
    WorkflowDef,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
INVALID_FIXTURES = FIXTURES / "invalid"
MODULE_FIXTURES = FIXTURES / "modules"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
PHASE_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"
WORKFLOW_REF_FIXTURE = FIXTURES / "valid" / "workflow_refs_same_file.orc"
PROC_REF_RUNTIME_TRANSPORT_FIXTURE = FIXTURES / "invalid" / "proc_ref_runtime_transport_invalid.orc"
FORM_PATH = ("workflow-lisp", "workflow-expression-test")


def _build_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    return build_syntax_module(read_sexpr_file(path))


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _build_type_env(path: Path = TYPE_FIXTURE) -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(_compile_definition_module(path))


def _write_module(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _expression_syntax(source: str, *, form_path: tuple[str, ...] = FORM_PATH) -> SyntaxNode:
    parse_tree = read_sexpr_file(FIXTURES / "valid" / "minimal_module.orc")
    del parse_tree
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    expr_tree = read_sexpr_text(source, source_path="inline_workflow_expression.orc")
    assert len(expr_tree.items) == 1
    datum = expr_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_workflow_expression.orc",
        form_path=form_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def test_elaborate_workflow_definitions_builds_record_only_same_file_catalog() -> None:
    structured_results = FIXTURES / "valid" / "structured_results.orc"
    syntax_module = _build_syntax_module(structured_results)
    definition_module = _compile_definition_module(structured_results)

    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(
        definition_module,
        workflow_defs,
        _build_type_env(structured_results),
    )

    assert [workflow_def.name for workflow_def in workflow_defs] == [
        "command_checks",
        "provider_attempt",
        "orchestrate",
    ]
    assert all(isinstance(workflow_def, WorkflowDef) for workflow_def in workflow_defs)
    assert isinstance(workflow_catalog, WorkflowCatalog)
    assert tuple(workflow_catalog.signatures_by_name) == (
        "command_checks",
        "provider_attempt",
        "orchestrate",
    )

    provider_attempt = workflow_catalog.signatures_by_name["provider_attempt"]
    orchestrate = workflow_catalog.signatures_by_name["orchestrate"]

    assert [param_name for param_name, _ in provider_attempt.params] == ["input", "report_path"]
    assert isinstance(provider_attempt.return_type_ref, RecordTypeRef)
    assert provider_attempt.return_type_ref.name == "ImplementationSummary"
    assert [param_name for param_name, _ in orchestrate.params] == ["input", "report_path"]
    assert isinstance(orchestrate.return_type_ref, RecordTypeRef)
    assert orchestrate.return_type_ref.name == "ImplementationSummary"


def test_build_workflow_catalog_rejects_duplicate_workflow_names() -> None:
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    syntax_module = build_syntax_module(
        read_sexpr_text(
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow duplicate",
                    "    ((report_path WorkReport))",
                    "    -> ImplementationSummary",
                    '    (record ImplementationSummary :status "ok" :report report_path))',
                    "  (defworkflow duplicate",
                    "    ((report_path WorkReport))",
                    "    -> ImplementationSummary",
                    '    (record ImplementationSummary :status "blocked" :report report_path)))',
                ]
            ),
            source_path="duplicate_workflow_definition.orc",
        )
    )
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            compile_stage1_module(TYPE_FIXTURE),
            workflow_defs,
            _build_type_env(),
        )

    _assert_diagnostic_code(excinfo, "workflow_definition_duplicate")


def test_typecheck_workflow_definitions_rejects_duplicate_parameter_names() -> None:
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    syntax_module = build_syntax_module(
        read_sexpr_text(
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow duplicate-param",
                    "    ((report_path WorkReport)",
                    "     (report_path WorkReport))",
                    "    -> ImplementationSummary",
                    '    (record ImplementationSummary :status "ok" :report report_path)))',
                ]
            ),
            source_path="duplicate_workflow_param.orc",
        )
    )
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_workflow_definitions(
            workflow_defs,
            type_env=_build_type_env(),
            workflow_catalog=build_workflow_catalog(
                compile_stage1_module(TYPE_FIXTURE),
                workflow_defs,
                _build_type_env(),
            ),
        )

    _assert_diagnostic_code(excinfo, "workflow_param_duplicate")


def test_typecheck_workflow_definitions_requires_record_or_union_return_type() -> None:
    syntax_module = _build_syntax_module(FIXTURES / "invalid" / "workflow_return_type_invalid.orc")
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            compile_stage1_module(TYPE_FIXTURE),
            workflow_defs,
            _build_type_env(),
        )

    _assert_diagnostic_code(excinfo, "workflow_return_type_invalid")


def test_elaborate_expression_supports_call_and_provider_result_with_extern_symbols() -> None:
    call_expr = elaborate_expression(
        _expression_syntax("(call helper :input input :report_path report_path)"),
        bound_names=frozenset({"input", "report_path"}),
    )
    provider_expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute "
            ":prompt prompts.implementation.execute "
            ":inputs (input report_path) "
            ":returns ImplementationState)"
        ),
        bound_names=frozenset({"input", "report_path"}),
    )

    assert isinstance(call_expr, CallExpr)
    assert call_expr.callee_name == "helper"
    assert [binding_name for binding_name, _ in call_expr.bindings] == ["input", "report_path"]

    assert isinstance(provider_expr, ProviderResultExpr)
    assert isinstance(provider_expr.provider, NameExpr)
    assert provider_expr.provider.name == "providers.execute"
    assert isinstance(provider_expr.prompt, NameExpr)
    assert provider_expr.prompt.name == "prompts.implementation.execute"
    assert provider_expr.returns_type_name == "ImplementationState"
    assert len(provider_expr.inputs) == 2


def test_build_workflow_catalog_accepts_macro_expanded_top_level_workflows() -> None:
    import importlib

    macros = importlib.import_module("orchestrator.workflow_lisp.macros")
    fixture = FIXTURES / "valid" / "macro_workflow_alias.orc"
    syntax_module = _build_syntax_module(fixture)
    expanded = macros.expand_module_forms(
        syntax_module,
        catalog=macros.collect_macro_catalog(syntax_module),
    )
    module = elaborate_definition_module(_definition_only_syntax_module(expanded))
    workflow_defs = elaborate_workflow_definitions(expanded)

    workflow_catalog = build_workflow_catalog(
        module,
        workflow_defs,
        FrontendTypeEnvironment.from_module(module),
    )

    assert tuple(workflow_catalog.signatures_by_name) == ("command_checks", "provider_attempt")


def test_compile_stage3_module_keeps_schema_built_records_transparent_to_workflow_typing(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    result = compile_stage3_module(
        FIXTURES / "valid" / "defschema_workflow_inputs.orc",
        validate_shared=False,
        workspace_root=tmp_path,
    )

    signature = result.workflow_catalog.signatures_by_name["summarize"]
    input_name, input_type = signature.params[0]

    assert input_name == "input"
    assert isinstance(input_type, RecordTypeRef)
    assert [field.name for field in input_type.definition.fields] == [
        "status",
        "execution_report",
        "review_report",
    ]
    assert isinstance(signature.return_type_ref, RecordTypeRef)
    assert [field.name for field in signature.return_type_ref.definition.fields] == [
        "status",
        "execution_report",
    ]

def test_compile_stage3_module_exposes_procedure_catalog_without_changing_workflow_signatures(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    result = compile_stage3_module(
        FIXTURES / "valid" / "defproc_inline.orc",
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert tuple(result.workflow_catalog.signatures_by_name) == ("orchestrate",)
    assert tuple(result.procedure_catalog.signatures_by_name) == ("build-checks", "copy-checks")
    assert [procedure.definition.name for procedure in result.typed_procedures] == [
        "build-checks",
        "copy-checks",
    ]


def test_phase_translation_fixture_uses_extern_symbols_without_workflow_transport() -> None:
    syntax_module = _build_syntax_module(PHASE_FIXTURE)
    workflow_def = elaborate_workflow_definitions(syntax_module)[0]
    body = elaborate_expression(
        workflow_def.body,
        bound_names=frozenset(param.name for param in workflow_def.params),
    )

    assert [param.name for param in workflow_def.params] == ["phase-ctx", "inputs"]
    assert type(body).__name__ == "WithPhaseExpr"
    assert type(body.body).__name__ == "LetStarExpr"
    attempt_expr = body.body.bindings[0][1]
    assert isinstance(attempt_expr, ProviderResultExpr)
    assert attempt_expr.provider.name == "providers.execute"
    assert attempt_expr.prompt.name == "prompts.implementation.execute"
    assert attempt_expr.returns_type_name == "ImplementationAttempt"

def test_elaborate_expression_rejects_malformed_effectful_forms() -> None:
    with pytest.raises(LispFrontendCompileError) as malformed_call:
        elaborate_expression(
            _expression_syntax("(call helper provider)"),
            bound_names=frozenset({"provider"}),
        )
    _assert_diagnostic_code(malformed_call, "frontend_parse_error")

    with pytest.raises(LispFrontendCompileError) as malformed_provider:
        elaborate_expression(
            _expression_syntax("(provider-result provider :inputs input :returns ImplementationState)"),
            bound_names=frozenset({"provider", "input"}),
        )
    _assert_diagnostic_code(malformed_provider, "frontend_parse_error")

    with pytest.raises(LispFrontendCompileError) as malformed_command:
        elaborate_expression(
            _expression_syntax("(command-result run_checks :argv report_path :returns ChecksResult)"),
            bound_names=frozenset({"report_path"}),
        )
    _assert_diagnostic_code(malformed_command, "frontend_parse_error")


def test_structured_results_fixture_uses_union_provider_result_match_and_avoids_provider_prompt_workflow_params() -> None:
    syntax_module = _build_syntax_module(FIXTURES / "valid" / "structured_results.orc")
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    provider_attempt = next(workflow for workflow in workflow_defs if workflow.name == "provider_attempt")
    orchestrate = next(workflow for workflow in workflow_defs if workflow.name == "orchestrate")
    provider_body = elaborate_expression(
        provider_attempt.body,
        bound_names=frozenset(param.name for param in provider_attempt.params),
    )
    call_body = elaborate_expression(
        orchestrate.body,
        bound_names=frozenset(param.name for param in orchestrate.params),
    )

    assert [param.name for param in provider_attempt.params] == ["input", "report_path"]
    assert [param.name for param in orchestrate.params] == ["input", "report_path"]
    assert isinstance(provider_body, LetStarExpr)
    assert provider_body.bindings[0][0] == "attempt"
    attempt_expr = provider_body.bindings[0][1]
    assert isinstance(attempt_expr, ProviderResultExpr)
    assert attempt_expr.provider.name == "providers.execute"
    assert attempt_expr.prompt.name == "prompts.implementation.execute"
    assert attempt_expr.returns_type_name == "ImplementationState"
    assert isinstance(provider_body.body, MatchExpr)
    assert [arm.variant_name for arm in provider_body.body.arms] == ["COMPLETED", "BLOCKED"]
    assert all(isinstance(arm.body, RecordExpr) for arm in provider_body.body.arms)
    assert all([field_name for field_name, _ in arm.body.fields] == ["report"] for arm in provider_body.body.arms)
    assert isinstance(call_body, CallExpr)
    assert [binding_name for binding_name, _ in call_body.bindings] == ["input", "report_path"]


def test_build_workflow_catalog_accepts_union_workflow_returns_when_projection_is_supported(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_return.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationState",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input report_path)",
                "      :returns ImplementationState)))",
            ]
        ),
    )
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(path))

    workflow_catalog = build_workflow_catalog(
        compile_stage1_module(TYPE_FIXTURE),
        workflow_defs,
        _build_type_env(),
    )

    assert isinstance(workflow_catalog.signatures_by_name["provider-attempt"].return_type_ref, UnionTypeRef)


def test_workflow_boundary_rejects_collection_typed_params(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            INVALID_FIXTURES / "workflow_boundary_collection_invalid.orc",
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "workflow_boundary_collection_unsupported")


def test_workflow_boundary_rejects_collection_typed_returns(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_boundary_collection_return.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowOutput",
                "    (attempt_ids List[Int]))",
                "  (defworkflow entry",
                "    ()",
                "    -> WorkflowOutput",
                '    (record WorkflowOutput :attempt_ids "unused")))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "workflow_boundary_collection_unsupported")


def test_workflow_boundary_rejects_collections_inside_workflow_ref_signatures(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_boundary_collection_workflow_ref.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defworkflow entry",
                "    ((runner WorkflowRef[List[Int] -> WorkflowOutput]))",
                "    -> WorkflowOutput",
                '    (record WorkflowOutput :value "ok")))',
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "workflow_boundary_collection_unsupported")


@pytest.mark.parametrize(
    ("bad_type", "expected_code"),
    [
        ("Provider", "workflow_boundary_type_invalid"),
        ("Prompt", "workflow_boundary_type_invalid"),
        ("Json", "json_surface_unsupported"),
    ],
)
def test_build_workflow_catalog_rejects_unsupported_workflow_param_types(
    tmp_path: Path,
    bad_type: str,
    expected_code: str,
) -> None:
    path = _write_module(
        tmp_path / f"param_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow summarize",
                f"    ((value {bad_type})",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                '    (record ImplementationSummary :status "ok" :report report_path)))',
            ]
        ),
    )
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(compile_stage1_module(TYPE_FIXTURE), workflow_defs, _build_type_env())

    _assert_diagnostic_code(excinfo, expected_code)


@pytest.mark.parametrize(
    ("bad_type", "expected_code"),
    [
        ("Provider", "workflow_boundary_type_invalid"),
        ("Prompt", "workflow_boundary_type_invalid"),
        ("Json", "json_surface_unsupported"),
    ],
)
def test_build_workflow_catalog_rejects_unsupported_workflow_return_fields(
    tmp_path: Path,
    bad_type: str,
    expected_code: str,
) -> None:
    types_path = _write_module(
        tmp_path / f"types_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord InvalidSummary",
                f"    (value {bad_type})",
                "    (report WorkReport)))",
            ]
        ),
    )
    module = compile_stage1_module(types_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_path = _write_module(
        tmp_path / f"return_{bad_type.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow summarize",
                "    ((report_path WorkReport))",
                "    -> InvalidSummary",
                '    (record InvalidSummary :value "ignored" :report report_path)))',
            ]
        ),
    )
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(workflow_path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(module, workflow_defs, type_env)

    _assert_diagnostic_code(excinfo, expected_code)


def test_typecheck_workflow_definitions_accepts_union_workflow_calls_with_match_projection(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "same_file_union_call.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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
                "           :status \"completed\"",
                "           :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary",
                "           :status \"blocked\"",
                "           :report blocked.progress_report))))))",
            ]
        ),
    )
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)

    workflow_catalog = build_workflow_catalog(
        compile_stage1_module(TYPE_FIXTURE),
        workflow_defs,
        _build_type_env(),
    )
    typed = typecheck_workflow_definitions(
        workflow_defs,
        type_env=_build_type_env(),
        workflow_catalog=workflow_catalog,
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
    )

    assert [workflow.definition.name for workflow in typed] == ["helper", "entry"]


def test_compile_stage3_entrypoint_registers_imported_workflow_signatures(tmp_path: Path) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = MODULE_FIXTURES / "valid" / "callables"
    result = compile_fn(
        source_root / "neurips" / "entry.orc",
        source_roots=(source_root,),
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

    assert "neurips/helper::provider-attempt" in result.entry_result.workflow_catalog.signatures_by_name


def test_compile_stage3_module_supports_local_and_imported_helpers(tmp_path: Path) -> None:
    compiler = _compiler_module()
    compile_module = getattr(compiler, "compile_stage3_module", None)
    assert callable(compile_module), "compile_stage3_module is missing"
    local_result = compile_module(
        FIXTURES / "valid" / "defun_forward_ref.orc",
        validate_shared=False,
        workspace_root=tmp_path,
    )
    compile_entrypoint = getattr(compiler, "compile_stage3_entrypoint", None)
    assert callable(compile_entrypoint), "compile_stage3_entrypoint is missing"

    imported_result = compile_entrypoint(
        MODULE_FIXTURES / "valid" / "imported_defun" / "entry.orc",
        source_roots=(MODULE_FIXTURES / "valid" / "imported_defun",),
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

    assert local_result.typed_workflows[0].definition.name == "orchestrate"
    assert imported_result.entry_result.typed_workflows[0].definition.name == "entry::orchestrate"


def test_compile_stage3_strips_workflow_ref_params_from_lowered_runtime_boundaries(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    result = compile_stage3_module(
        WORKFLOW_REF_FIXTURE,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    for lowered in result.lowered_workflows:
        assert "runner" not in lowered.authored_mapping["inputs"]


def test_workflow_boundary_rejects_top_level_proc_ref_params(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            PROC_REF_RUNTIME_TRANSPORT_FIXTURE,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")


def test_workflow_boundary_rejects_proc_ref_record_fields(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_boundary_proc_ref_record.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defrecord InvalidEnvelope",
                "    (runner ProcRef[WorkflowInput -> WorkflowOutput]))",
                "  (defworkflow helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :value input.value)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")


def test_workflow_boundary_rejects_proc_ref_union_payloads(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_boundary_proc_ref_union.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defunion InvalidState",
                "    (READY",
                "      (runner ProcRef[WorkflowInput -> WorkflowOutput])))",
                "  (defworkflow helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :value input.value)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")
