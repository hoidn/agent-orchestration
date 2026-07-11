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
    EnumMemberExpr,
    LetStarExpr,
    MatchExpr,
    NameExpr,
    ProviderResultExpr,
    RecordExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import SyntaxNode, WorkflowLispSyntaxModule, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
)
from orchestrator.workflow_lisp.workflow_refs import (
    ResolvedWorkflowRef,
    WorkflowExternRebindingPlan,
    WorkflowRefAuthoritySource,
)
from orchestrator.workflow_lisp.workflows import (
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    WorkflowCatalog,
    WorkflowDef,
    WorkflowSignature,
    _merged_private_compatibility_bridge_types_by_workflow,
    _workflow_omits_private_compatibility_bridge_via_workflow_ref,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    specialized_private_compatibility_bridge_callees,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
INVALID_FIXTURES = FIXTURES / "invalid"
MODULE_FIXTURES = FIXTURES / "modules"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
PHASE_FIXTURE = FIXTURES / "valid" / "neurips_implementation_attempt.orc"
WORKFLOW_REF_FIXTURE = FIXTURES / "valid" / "workflow_refs_same_file.orc"
PROC_REF_BIND_PROC_FIXTURE = FIXTURES / "valid" / "proc_ref_bind_proc_forwarding.orc"
PROC_REF_RUNTIME_TRANSPORT_FIXTURE = FIXTURES / "invalid" / "proc_ref_runtime_transport_invalid.orc"
ENTRY_PUBLICATION_RUNTIME_FIXTURE = FIXTURES / "valid" / "entry_publication_runtime.orc"
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


def _inline_span(path: str = "inline_workflow_expression.orc") -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(path=path, line=1, column=0, offset=0),
        end=SourcePosition(path=path, line=1, column=1, offset=1),
    )


def _inline_name(name: str) -> NameExpr:
    return NameExpr(name=name, span=_inline_span(), form_path=FORM_PATH)


def _inline_call(callee_name: str, *binding_names: str) -> CallExpr:
    return CallExpr(
        callee_name=callee_name,
        bindings=tuple((binding_name, _inline_name(binding_name)) for binding_name in binding_names),
        span=_inline_span(),
        form_path=FORM_PATH,
    )


def _workflow_output_type() -> RecordTypeRef:
    output_type = _build_type_env(WORKFLOW_REF_FIXTURE).resolve_type(
        "WorkflowOutput",
        span=_inline_span(),
        form_path=FORM_PATH,
    )
    assert isinstance(output_type, RecordTypeRef)
    return output_type


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


def test_elaborate_workflow_definitions_parses_workflow_param_default_metadata() -> None:
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    syntax_module = build_syntax_module(
        read_sexpr_text(
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow defaults",
                    "    ((report_path WorkReport :default \"reports/default.md\")",
                    "     (status String))",
                    "    -> ImplementationSummary",
                    '    (record ImplementationSummary :status status :report report_path)))',
                ]
            ),
            source_path="workflow_param_default_metadata.orc",
        )
    )

    workflow_def = elaborate_workflow_definitions(syntax_module)[0]
    report_path_param, status_param = workflow_def.params

    assert report_path_param.name == "report_path"
    assert report_path_param.type_name == "WorkReport"
    assert getattr(report_path_param, "default_value").datum == "reports/default.md"
    assert status_param.name == "status"
    assert getattr(status_param, "default_value") is None


def test_elaborate_workflow_definitions_rejects_unknown_workflow_param_keyword() -> None:
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    syntax_module = build_syntax_module(
        read_sexpr_text(
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow defaults",
                    "    ((report_path WorkReport :optional true))",
                    "    -> ImplementationSummary",
                    '    (record ImplementationSummary :status "ok" :report report_path)))',
                ]
            ),
            source_path="workflow_param_unknown_keyword.orc",
        )
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_workflow_definitions(syntax_module)

    _assert_diagnostic_code(excinfo, "frontend_parse_error")
    assert "unknown workflow param keyword `:optional`" in excinfo.value.diagnostics[0].message


def test_elaborate_workflow_definitions_rejects_workflow_param_default_without_value() -> None:
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    syntax_module = build_syntax_module(
        read_sexpr_text(
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defworkflow defaults",
                    "    ((report_path WorkReport :default))",
                    "    -> ImplementationSummary",
                    '    (record ImplementationSummary :status "ok" :report report_path)))',
                ]
            ),
            source_path="workflow_param_default_without_value.orc",
        )
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_workflow_definitions(syntax_module)

    _assert_diagnostic_code(excinfo, "frontend_parse_error")
    assert "workflow param `:default` requires a value" in excinfo.value.diagnostics[0].message


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
    assert isinstance(provider_expr.provider, (NameExpr, EnumMemberExpr))
    assert provider_expr.provider.name == "providers.execute"
    assert isinstance(provider_expr.prompt, (NameExpr, EnumMemberExpr))
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


def test_build_workflow_catalog_normalizes_supported_workflow_param_defaults(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_param_defaults.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum Status",
                "    ready",
                "    blocked)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Summary",
                "    (report WorkReport))",
                "  (defworkflow defaults",
                '    ((message String :default "hello")',
                "     (count Int :default 3)",
                "     (score Float :default 0.5)",
                "     (enabled Bool :default true)",
                "     (status Status :default ready)",
                '     (report_path WorkReport :default "reports/default.md"))',
                "    -> Summary",
                "    (record Summary :report report_path)))",
            ]
        ),
    )
    module = _compile_definition_module(path)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(path))

    workflow_catalog = build_workflow_catalog(
        module,
        workflow_defs,
        FrontendTypeEnvironment.from_module(module),
    )

    defaults = workflow_catalog.signatures_by_name["defaults"].param_defaults
    assert defaults["message"].normalized_value == "hello"
    assert defaults["count"].normalized_value == 3
    assert defaults["score"].normalized_value == 0.5
    assert defaults["enabled"].normalized_value is True
    assert defaults["status"].normalized_value == "ready"
    assert defaults["report_path"].normalized_value == "reports/default.md"


def test_compile_stage3_module_rejects_float_literals_outside_workflow_param_defaults(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "float_literal_body_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Summary",
                "    (score Float))",
                "  (defworkflow defaults",
                "    ((score Float))",
                "    -> Summary",
                "    (record Summary :score 0.5)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "frontend_parse_error")
    assert "only supported in `defworkflow` parameter defaults" in excinfo.value.diagnostics[0].message


def test_build_workflow_catalog_rejects_structured_workflow_param_defaults(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_param_structured_default_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord MultiInput",
                "    (status String)",
                "    (report String))",
                "  (defrecord Summary",
                "    (status String))",
                "  (defworkflow defaults",
                '    ((input MultiInput :default "nope"))',
                "    -> Summary",
                '    (record Summary :status input.status)))',
            ]
        ),
    )
    module = _compile_definition_module(path)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            module,
            workflow_defs,
            FrontendTypeEnvironment.from_module(module),
        )

    _assert_diagnostic_code(excinfo, "workflow_param_default_unsupported")
    assert "flatten to exactly one workflow input contract" in excinfo.value.diagnostics[0].message


def test_build_workflow_catalog_rejects_type_invalid_workflow_param_defaults(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_param_type_invalid_default.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Summary",
                "    (status String))",
                "  (defworkflow defaults",
                '    ((count Int :default "three"))',
                "    -> Summary",
                '    (record Summary :status "ok")))',
            ]
        ),
    )
    module = _compile_definition_module(path)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            module,
            workflow_defs,
            FrontendTypeEnvironment.from_module(module),
        )

    _assert_diagnostic_code(excinfo, "workflow_param_default_type_invalid")
    assert "default for workflow param `count` must match boundary type `Int`" in excinfo.value.diagnostics[0].message


def test_workflow_boundary_accepts_lowerable_collection_typed_params_under_wcc(tmp_path: Path) -> None:
    del tmp_path
    path = INVALID_FIXTURES / "workflow_boundary_collection_invalid.orc"
    module = _compile_definition_module(path)
    workflow_catalog = build_workflow_catalog(
        module,
        elaborate_workflow_definitions(_build_syntax_module(path)),
        FrontendTypeEnvironment.from_module(module),
        allow_collection_input_boundaries=True,
    )

    assert workflow_catalog.signatures_by_name["entry"].params[0][0] == "attempt_ids"


def test_workflow_boundary_rejects_unsupported_collection_typed_returns(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "workflow_boundary_collection_return.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowOutput",
                "    (attempt_ids Map[String, Int]))",
                "  (defworkflow entry",
                "    ()",
                "    -> WorkflowOutput",
                '    (record WorkflowOutput :attempt_ids "unused")))',
            ]
        ),
    )
    module = _compile_definition_module(path)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            module,
            workflow_defs,
            FrontendTypeEnvironment.from_module(module),
            allow_collection_return_boundaries=True,
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

    _assert_diagnostic_code(excinfo, "workflow_ref_runtime_transport_forbidden")


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
        lowering_route="legacy",
    )

    for lowered in result.lowered_workflows:
        assert "runner" not in lowered.authored_mapping["inputs"]


def test_workflow_ref_bridge_omission_helpers_track_specialized_hidden_bridge_targets() -> None:
    span = _inline_span()
    output_type = _workflow_output_type()
    string_type = PrimitiveTypeRef("String")
    bridge_type = PrimitiveTypeRef("ProgressLedger")
    callee_signature = WorkflowSignature(
        name="project-selected-compat",
        params=(("item-id", string_type), ("progress_ledger_path", bridge_type)),
        return_type_ref=output_type,
        span=span,
        form_path=FORM_PATH,
        private_compatibility_bridge_types={"progress_ledger_path": bridge_type},
    )
    wrapper_signature = WorkflowSignature(
        name="invoke-runner",
        params=(
            (
                "runner",
                WorkflowRefTypeRef(
                    name="WorkflowRef[(String ProgressLedger) -> WorkflowOutput]",
                    param_type_refs=(string_type, bridge_type),
                    return_type_ref=output_type,
                ),
            ),
            ("item-id", string_type),
        ),
        return_type_ref=output_type,
        span=span,
        form_path=FORM_PATH,
    )
    wrapper_def = WorkflowDef(
        name="invoke-runner",
        params=(),
        return_type_name="WorkflowOutput",
        body=_inline_call("runner", "item-id"),
        span=span,
        form_path=FORM_PATH,
    )

    assert _workflow_omits_private_compatibility_bridge_via_workflow_ref(
        wrapper_def,
        signatures_by_name={"invoke-runner": wrapper_signature},
    )
    assert specialized_private_compatibility_bridge_callees(
        wrapper_def,
        base_signature=wrapper_signature,
        workflow_ref_bindings={
            "runner": ResolvedWorkflowRef(
                workflow_name="project-selected-compat",
                signature_params=callee_signature.params,
                return_type_ref=output_type,
                authority_source=WorkflowRefAuthoritySource(
                    kind="local",
                    workflow_name="project-selected-compat",
                ),
                extern_rebinding_plan=WorkflowExternRebindingPlan(
                    provider_bindings={},
                    prompt_bindings={},
                ),
            )
        },
        signatures_by_name={"project-selected-compat": callee_signature},
    ) == frozenset({"project-selected-compat"})


def test_private_bridge_type_helper_merges_omitted_local_callee_bridge_inputs() -> None:
    span = _inline_span()
    output_type = _workflow_output_type()
    string_type = PrimitiveTypeRef("String")
    bridge_type = PrimitiveTypeRef("ProgressLedger")
    callee_signature = WorkflowSignature(
        name="project-selected-compat",
        params=(("item-id", string_type), ("progress_ledger_path", bridge_type)),
        return_type_ref=output_type,
        span=span,
        form_path=FORM_PATH,
        private_compatibility_bridge_types={"progress_ledger_path": bridge_type},
    )
    wrapper_signature = WorkflowSignature(
        name="invoke-selected-compat",
        params=(("item-id", string_type),),
        return_type_ref=output_type,
        span=span,
        form_path=FORM_PATH,
    )
    callee_def = WorkflowDef(
        name="project-selected-compat",
        params=(),
        return_type_name="WorkflowOutput",
        body=_inline_name("item-id"),
        span=span,
        form_path=FORM_PATH,
    )
    wrapper_def = WorkflowDef(
        name="invoke-selected-compat",
        params=(),
        return_type_name="WorkflowOutput",
        body=_inline_call("project-selected-compat", "item-id"),
        span=span,
        form_path=FORM_PATH,
    )

    assert _merged_private_compatibility_bridge_types_by_workflow(
        workflow_defs=(callee_def, wrapper_def),
        signatures_by_name={
            "project-selected-compat": callee_signature,
            "invoke-selected-compat": wrapper_signature,
        },
    ) == {
        "invoke-selected-compat": {"progress_ledger_path": bridge_type}
    }


def test_workflow_boundary_rejects_top_level_proc_ref_params(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            PROC_REF_RUNTIME_TRANSPORT_FIXTURE,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")


def test_workflow_boundary_rejects_macro_emitted_proc_ref_runtime_transport(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_proc_ref_runtime_transport.orc",
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-proc-ref-workflow"


def test_workflow_boundary_accepts_proc_ref_specialized_workflows_with_runtime_inputs(tmp_path: Path) -> None:
    result = compile_stage3_module(
        PROC_REF_BIND_PROC_FIXTURE,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "entry" in result.validated_bundles


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


def test_elaborate_workflow_definitions_accepts_optional_publish_metadata_clause() -> None:
    syntax_module = _build_syntax_module(ENTRY_PUBLICATION_RUNTIME_FIXTURE)

    workflow_defs = elaborate_workflow_definitions(syntax_module)
    entry_workflow = next(
        workflow_def
        for workflow_def in workflow_defs
        if workflow_def.name == "entry-publication-runtime"
    )

    assert hasattr(entry_workflow, "publication_policy")
    assert getattr(entry_workflow, "publication_policy") is not None


def test_elaborate_workflow_definitions_keeps_legacy_single_body_workflows_source_compatible() -> None:
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(TYPE_FIXTURE))

    assert all(getattr(workflow_def, "body", None) is not None for workflow_def in workflow_defs)


def test_workflow_signature_identity_excludes_publish_metadata() -> None:
    type_env = _build_type_env(ENTRY_PUBLICATION_RUNTIME_FIXTURE)
    definition_module = _compile_definition_module(ENTRY_PUBLICATION_RUNTIME_FIXTURE)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(ENTRY_PUBLICATION_RUNTIME_FIXTURE))

    workflow_catalog = build_workflow_catalog(
        definition_module,
        workflow_defs,
        type_env,
    )

    publishable_signature = workflow_catalog.signatures_by_name[
        "entry-publication-runtime"
    ]
    helper_signature = workflow_catalog.signatures_by_name[
        "call-entry-publication-runtime"
    ]

    assert publishable_signature.params == helper_signature.params
    assert publishable_signature.return_type_ref == helper_signature.return_type_ref
    assert not hasattr(publishable_signature, "publication_policy")


def test_build_syntax_module_accepts_target_dsl_215_without_rejecting_214() -> None:
    from orchestrator.workflow_lisp.reader import read_sexpr_text

    def _module_source(target_dsl: str) -> str:
        return "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                f'  (:target-dsl "{target_dsl}")',
                "  (defenum Approval",
                "    APPROVE))",
            ]
        )

    v215_module = build_syntax_module(
        read_sexpr_text(_module_source("2.15"), source_path="target_dsl_215.orc")
    )
    v214_module = build_syntax_module(
        read_sexpr_text(_module_source("2.14"), source_path="target_dsl_214.orc")
    )

    assert v215_module.target_dsl_version == "2.15"
    assert v214_module.target_dsl_version == "2.14"


def test_build_workflow_catalog_accepts_native_transportable_scalar_returns() -> None:
    fixture = FIXTURES / "valid" / "native_transportable_returns.orc"
    module = _compile_definition_module(fixture)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(fixture))

    catalog = build_workflow_catalog(module, workflow_defs, type_env)

    signatures = catalog.signatures_by_name
    assert signatures["native-approval-flag"].return_type_ref == PrimitiveTypeRef(name="Bool")
    assert signatures["native-review-decision"].return_type_ref.allowed_values == ("APPROVE", "REVISE")
    assert signatures["native-confidence-score"].return_type_ref == PrimitiveTypeRef(name="Float")
    assert signatures["native-finding-count"].return_type_ref == PrimitiveTypeRef(name="Int")
    assert signatures["native-summary-line"].return_type_ref == PrimitiveTypeRef(name="String")
    assert isinstance(signatures["native-report-location"].return_type_ref, PathTypeRef)


def _native_collection_return_module(tmp_path: Path, return_type_name: str) -> Path:
    stem = return_type_name.replace("[", "_").replace("]", "").replace(",", "_").replace(" ", "")
    return _write_module(
        tmp_path / f"native_return_{stem.lower()}.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defworkflow native-collection-return",
                "    ((report_path WorkReport))",
                f"    -> {return_type_name}",
                "    (command-result collect_values",
                '      :argv ("python" "scripts/collect_values.py" report_path)',
                f"      :returns {return_type_name})))",
            ]
        ),
    )


def test_build_workflow_catalog_accepts_native_list_return_with_collection_boundaries(
    tmp_path: Path,
) -> None:
    module_path = _native_collection_return_module(tmp_path, "List[Int]")
    module = _compile_definition_module(module_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(module_path))

    catalog = build_workflow_catalog(
        module,
        workflow_defs,
        type_env,
        allow_collection_return_boundaries=True,
    )

    return_type_ref = catalog.signatures_by_name["native-collection-return"].return_type_ref
    assert isinstance(return_type_ref, ListTypeRef)
    assert return_type_ref.item_type_ref == PrimitiveTypeRef(name="Int")


@pytest.mark.parametrize("return_type_name", ["Optional[Bool]", "Map[String, Float]"])
def test_build_workflow_catalog_keeps_stage3_boundary_rules_for_native_collection_returns(
    tmp_path: Path,
    return_type_name: str,
) -> None:
    module_path = _native_collection_return_module(tmp_path, return_type_name)
    module = _compile_definition_module(module_path)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(_build_syntax_module(module_path))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_workflow_catalog(
            module,
            workflow_defs,
            type_env,
            allow_collection_return_boundaries=True,
        )

    _assert_diagnostic_code(excinfo, "workflow_boundary_collection_unsupported")
