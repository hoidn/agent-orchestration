from dataclasses import replace
from pathlib import Path

import pytest

import orchestrator.workflow_lisp.effects as effect_module
import orchestrator.workflow_lisp.expressions as expression_module
import orchestrator.workflow_lisp.functions as function_module
import orchestrator.workflow_lisp.macros as macro_module
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.form_registry import (
    FormKind,
    get_form_spec,
)
from orchestrator.workflow_lisp.procedures import (
    build_procedure_catalog,
    elaborate_procedure_definitions,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    RecordTypeRef,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import (
    build_extern_environment,
    elaborate_workflow_definitions,
)


def _module_source(target_dsl: str, *forms: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl}")',
            *(f"  {form}" for form in forms),
            ")",
        )
    )


def _type_environment(
    target_dsl: str,
    *forms: str,
) -> FrontendTypeEnvironment:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl, *forms),
            source_path=f"peer_target_{target_dsl.replace('.', '_')}.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    return FrontendTypeEnvironment.from_module(module)


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(
        source,
        source_path="provider_peer_expression.orc",
    )
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="provider_peer_expression.orc",
        form_path=("workflow-lisp", "provider-peer-group"),
    )


def _elaborate_peers(
    source: str,
    *,
    extra_bound_names: frozenset[str] = frozenset(),
    procedure_names: frozenset[str] = frozenset(),
):
    return elaborate_expression(
        _expression(source),
        bound_names=(
            frozenset(
                {
                    "providers.planner",
                    "providers.reviewer",
                    "providers.builder",
                    "providers.body",
                    "prompts.planner",
                    "prompts.reviewer",
                    "prompts.builder",
                    "prompts.body",
                }
            )
            | extra_bound_names
        ),
        procedure_names=procedure_names,
    )


def _peer_extern_environment():
    return build_extern_environment(
        provider_externs={
            "providers.planner": "planner-provider",
            "providers.reviewer": "reviewer-provider",
            "providers.builder": "builder-provider",
            "providers.body": "body-provider",
        },
        prompt_externs={
            "prompts.planner": "prompts/planner.md",
            "prompts.reviewer": "prompts/reviewer.md",
            "prompts.builder": "prompts/builder.md",
            "prompts.body": "prompts/body.md",
        },
    )


def _provider_result(
    provider: str,
    prompt: str,
    return_type: str = "String",
) -> str:
    return (
        f"(provider-result {provider} "
        f":prompt {prompt} :inputs () :returns {return_type})"
    )


def test_provider_peer_group_target_217_is_accepted_by_reader_and_shared_validator(
    tmp_path: Path,
) -> None:
    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.17", "(defenum Approval APPROVE)"),
            source_path="target_2_17.orc",
        )
    )
    assert module.target_dsl_version == "2.17"

    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.17",
                "name": "target-version",
                "steps": [
                    {
                        "name": "Done",
                        "command": ["echo", "done"],
                    }
                ],
            },
            workflow_path=tmp_path / "target-version.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert result.bundle.surface.version == "2.17"


@pytest.mark.parametrize("member_count", (2, 3, 8))
def test_with_live_provider_peers_accepts_static_member_bounds(
    member_count: int,
) -> None:
    bindings = " ".join(
        f'(member_{index} "value-{index}")'
        for index in range(member_count)
    )
    expr = _elaborate_peers(
        f"(with-live-provider-peers ({bindings}) member_0)"
    )

    peer_type = getattr(
        expression_module,
        "WithLiveProviderPeersExpr",
    )
    assert isinstance(expr, peer_type)
    assert tuple(binding.name for binding in expr.bindings) == tuple(
        f"member_{index}" for index in range(member_count)
    )
    assert isinstance(expr.body, expression_module.NameExpr)
    assert expr.body.name == "member_0"


@pytest.mark.parametrize("member_count", (1, 9))
def test_with_live_provider_peers_rejects_out_of_bound_member_count(
    member_count: int,
) -> None:
    bindings = " ".join(
        f'(member_{index} "value-{index}")'
        for index in range(member_count)
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_peers(
            f"(with-live-provider-peers ({bindings}) member_0)"
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "with_live_provider_peers_bindings_invalid"
    )


@pytest.mark.parametrize(
    ("source", "expected_code"),
    (
        (
            '(with-live-provider-peers ((planner "plan") (reviewer "review")))',
            "with_live_provider_peers_arity_invalid",
        ),
        (
            '(with-live-provider-peers planner planner)',
            "with_live_provider_peers_bindings_invalid",
        ),
        (
            (
                "(with-live-provider-peers "
                '(planner (reviewer "review")) reviewer)'
            ),
            "with_live_provider_peers_binding_invalid",
        ),
        (
            (
                "(with-live-provider-peers "
                '(("planner" "plan") (reviewer "review")) reviewer)'
            ),
            "with_live_provider_peers_binding_invalid",
        ),
        (
            (
                "(with-live-provider-peers "
                '((planner "plan" "extra") (reviewer "review")) reviewer)'
            ),
            "with_live_provider_peers_binding_invalid",
        ),
        (
            (
                "(with-live-provider-peers "
                '((planner "plan") (planner "review")) planner)'
            ),
            "with_live_provider_peers_binding_duplicate",
        ),
    ),
)
def test_with_live_provider_peers_rejects_malformed_static_bindings(
    source: str,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_peers(source)

    assert excinfo.value.diagnostics[0].code == expected_code


def test_with_live_provider_peers_traversal_preserves_authored_order() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review") (builder "build")) '
        "reviewer)"
    )

    children = iter_child_exprs(expr)

    assert [
        child.value
        if isinstance(child, expression_module.LiteralExpr)
        else child.name
        for child in children
    ] == ["plan", "review", "build", "reviewer"]


def test_with_live_provider_peers_has_reserved_static_registry_route() -> None:
    spec = get_form_spec("with-live-provider-peers")

    assert spec is not None
    assert spec.kind is FormKind.CORE_EFFECT
    assert spec.owner_module == "expressions"
    assert spec.elaboration_route == "with_live_provider_peers"
    assert spec.feature_tags == frozenset({"provider_peer_messaging"})
    assert spec.macro_bindable is False


def test_target_216_allows_macro_with_future_peer_form_spelling(
    tmp_path: Path,
) -> None:
    path = tmp_path / "target-216-peer-spelling.orc"
    path.write_text(
        _module_source(
            "2.16",
            "(defmacro with-live-provider-peers (value) value)",
            (
                "(defworkflow orchestrate () -> String "
                '(with-live-provider-peers "ok"))'
            ),
        ),
        encoding="utf-8",
    )

    syntax_module = build_syntax_module(
        read_sexpr_text(
            path.read_text(encoding="utf-8"),
            source_path=str(path),
        )
    )
    catalog = macro_module.collect_macro_catalog(syntax_module)
    assert "with-live-provider-peers" in catalog.definitions_by_name
    expanded = macro_module.expand_module_forms(
        syntax_module,
        catalog=catalog,
    )
    workflow = elaborate_workflow_definitions(expanded)[0]
    expr = elaborate_expression(
        workflow.body,
        bound_names=frozenset(),
    )

    assert isinstance(expr, expression_module.LiteralExpr)
    assert expr.value == "ok"


def test_target_217_reserves_peer_form_against_macro_shadowing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "target-217-peer-spelling.orc"
    path.write_text(
        _module_source(
            "2.17",
            "(defmacro with-live-provider-peers (value) value)",
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    assert excinfo.value.diagnostics[0].code == "macro_reserved_name"


def test_target_217_rejects_bare_imported_legacy_peer_macro() -> None:
    legacy_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                "(defmacro with-live-provider-peers (value) value)",
            ),
            source_path="legacy_peer_macro.orc",
        )
    )
    legacy_macro = macro_module.collect_macro_catalog(
        legacy_module
    ).definitions_by_name["with-live-provider-peers"]
    consumer_module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.17"),
            source_path="peer_macro_consumer.orc",
        )
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        macro_module.collect_macro_catalog_with_imports(
            consumer_module,
            imported_definitions={
                "with-live-provider-peers": legacy_macro,
            },
        )

    assert excinfo.value.diagnostics[0].code == "macro_reserved_name"


@pytest.mark.parametrize(
    "accessible_name",
    (
        "legacy.with-live-provider-peers",
        "legacy/module/with-live-provider-peers",
    ),
)
def test_target_217_allows_qualified_imported_legacy_peer_macro(
    accessible_name: str,
) -> None:
    legacy_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                "(defmacro with-live-provider-peers (value) value)",
            ),
            source_path="legacy_qualified_peer_macro.orc",
        )
    )
    legacy_macro = macro_module.collect_macro_catalog(
        legacy_module
    ).definitions_by_name["with-live-provider-peers"]
    consumer_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.17",
                (
                    "(defworkflow orchestrate () -> String "
                    f'({accessible_name} "ok"))'
                ),
            ),
            source_path="qualified_peer_macro_consumer.orc",
        )
    )

    catalog = macro_module.collect_macro_catalog_with_imports(
        consumer_module,
        imported_definitions={accessible_name: legacy_macro},
    )
    expanded = macro_module.expand_module_forms(
        consumer_module,
        catalog=catalog,
    )
    workflow = elaborate_workflow_definitions(expanded)[0]
    expr = elaborate_expression(
        workflow.body,
        bound_names=frozenset(),
        target_dsl_version="2.17",
    )

    assert catalog.definitions_by_name[accessible_name] is legacy_macro
    assert isinstance(expr, expression_module.LiteralExpr)
    assert expr.value == "ok"


def test_target_216_nested_legacy_peer_macro_keeps_generic_hygiene() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.16",
                (
                    "(defmacro with-live-provider-peers "
                    "(bindings body) body)"
                ),
                (
                    "(defmacro wrap () "
                    "(with-live-provider-peers "
                    '((input "p") (other "q")) input))'
                ),
                (
                    "(defworkflow run ((input String)) "
                    "-> String (wrap))"
                ),
            ),
            source_path="nested_legacy_peer_macro.orc",
        )
    )
    expanded = macro_module.expand_module_forms(
        syntax_module,
        catalog=macro_module.collect_macro_catalog(syntax_module),
    )
    workflow = elaborate_workflow_definitions(expanded)[0]
    expr = elaborate_expression(
        workflow.body,
        bound_names=frozenset({"input"}),
        target_dsl_version="2.16",
    )
    typed = typecheck_expression(
        expr,
        type_env=_type_environment("2.16"),
        value_env={"input": PrimitiveTypeRef(name="String")},
    )

    assert isinstance(expr, expression_module.NameExpr)
    assert expr.name == "input"
    assert typed.type_ref == PrimitiveTypeRef(name="String")


@pytest.mark.parametrize(
    ("callable_names_arg", "expected_type"),
    (
        ("function_names", expression_module.FunctionCallExpr),
        ("procedure_names", expression_module.ProcedureCallExpr),
    ),
)
def test_target_216_legacy_peer_spelling_dispatches_to_known_callable(
    callable_names_arg: str,
    expected_type,
) -> None:
    expr = elaborate_expression(
        _expression('(with-live-provider-peers "ok")'),
        bound_names=frozenset(),
        target_dsl_version="2.16",
        **{
            callable_names_arg: frozenset(
                {"with-live-provider-peers"}
            )
        },
    )

    assert isinstance(expr, expected_type)
    assert expr.callee_name == "with-live-provider-peers"


@pytest.mark.parametrize(
    "callable_names_arg",
    ("function_names", "procedure_names"),
)
def test_target_217_peer_core_form_stays_unshadowable_by_callable(
    callable_names_arg: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression('(with-live-provider-peers "ok")'),
            bound_names=frozenset(),
            target_dsl_version="2.17",
            **{
                callable_names_arg: frozenset(
                    {"with-live-provider-peers"}
                )
            },
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "with_live_provider_peers_arity_invalid"
    )


def test_target_216_legacy_peer_spelling_dispatches_to_bound_proc_ref() -> None:
    expr = elaborate_expression(
        _expression('(with-live-provider-peers "ok")'),
        bound_names=frozenset({"with-live-provider-peers"}),
        target_dsl_version="2.16",
    )

    assert isinstance(expr, expression_module.ProcedureCallExpr)
    assert expr.callee_name == "with-live-provider-peers"


def test_target_217_peer_core_form_stays_unshadowable_by_bound_proc_ref(
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression('(with-live-provider-peers "ok")'),
            bound_names=frozenset({"with-live-provider-peers"}),
            target_dsl_version="2.17",
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "with_live_provider_peers_arity_invalid"
    )


@pytest.mark.parametrize(
    "callable_definition",
    (
        (
            "(defun with-live-provider-peers "
            "((value String)) -> String value)"
        ),
        (
            "(defproc with-live-provider-peers "
            "((value String)) -> String "
            ":effects () :lowering inline value)"
        ),
    ),
)
def test_target_216_compiler_calls_legacy_peer_spelling_callable(
    tmp_path: Path,
    callable_definition: str,
) -> None:
    path = tmp_path / "target_216_legacy_peer_callable.orc"
    path.write_text(
        _module_source(
            "2.16",
            callable_definition,
            (
                "(defworkflow orchestrate () -> String "
                '(with-live-provider-peers "ok"))'
            ),
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].typed_body.type_ref == (
        PrimitiveTypeRef(name="String")
    )


def _let_proc_escape_analysis_peer_callable_source(
    target_dsl: str,
    callable_kind: str,
) -> str:
    if callable_kind == "defproc":
        callable_options = ":effects () :lowering inline "
    elif callable_kind == "defun":
        callable_options = ""
    else:
        raise AssertionError(f"unknown callable kind: {callable_kind}")
    return _module_source(
        target_dsl,
        (
            f"({callable_kind} with-live-provider-peers "
            "((value String)) -> String "
            f"{callable_options}value)"
        ),
        (
            f"({callable_kind} helper "
            "((value String)) -> String "
            f"{callable_options}"
            "(with-live-provider-peers value))"
        ),
        (
            "(defworkflow entry () -> String "
            "(let-proc (local () -> String "
            ':captures () "local") '
            '(helper "ok")))'
        ),
    )


def _let_proc_escape_analysis_cross_kind_source(target_dsl: str) -> str:
    return _module_source(
        target_dsl,
        (
            "(defun with-live-provider-peers "
            "((value String)) -> String value)"
        ),
        (
            "(defproc helper "
            "((value String)) -> String "
            ":effects () :lowering inline "
            "(with-live-provider-peers value))"
        ),
        (
            "(defworkflow entry () -> String "
            "(let-proc (local () -> String "
            ':captures () "local") '
            '(helper "ok")))'
        ),
    )


@pytest.mark.parametrize("callable_kind", ("defproc", "defun"))
def test_target_216_let_proc_escape_analysis_keeps_legacy_peer_callable(
    tmp_path: Path,
    callable_kind: str,
) -> None:
    path = tmp_path / "target_216_let_proc_peer_callable.orc"
    path.write_text(
        _let_proc_escape_analysis_peer_callable_source(
            "2.16",
            callable_kind,
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].typed_body.type_ref == (
        PrimitiveTypeRef(name="String")
    )


def test_target_216_let_proc_escape_analysis_resolves_function_from_defproc(
    tmp_path: Path,
) -> None:
    path = tmp_path / "target_216_let_proc_cross_kind_callable.orc"
    path.write_text(
        _let_proc_escape_analysis_cross_kind_source("2.16"),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].typed_body.type_ref == (
        PrimitiveTypeRef(name="String")
    )


def test_target_217_let_proc_escape_analysis_keeps_cross_kind_core_unshadowable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "target_217_let_proc_cross_kind_core.orc"
    path.write_text(
        _let_proc_escape_analysis_cross_kind_source("2.17"),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "with_live_provider_peers_arity_invalid"
    )


@pytest.mark.parametrize("callable_kind", ("defproc", "defun"))
def test_target_217_let_proc_escape_analysis_keeps_peer_core_unshadowable(
    tmp_path: Path,
    callable_kind: str,
) -> None:
    path = tmp_path / "target_217_let_proc_peer_core.orc"
    path.write_text(
        _let_proc_escape_analysis_peer_callable_source(
            "2.17",
            callable_kind,
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "with_live_provider_peers_arity_invalid"
    )


@pytest.mark.parametrize(
    ("target_dsl", "group_expression"),
    (
        (
            "2.16",
            (
                "(with-live-providers "
                "((worker "
                "(provider-result providers.worker "
                ":prompt prompts.worker :inputs () :returns String)) "
                "(supervisor "
                "(provider-result providers.supervisor "
                ":prompt prompts.supervisor :inputs () "
                ":returns ProviderSteeringDirective) "
                ":observes worker)) "
                "(proc-ref local))"
            ),
        ),
        (
            "2.17",
            (
                "(with-live-provider-peers "
                "((planner "
                "(provider-result providers.planner "
                ":prompt prompts.planner :inputs () :returns String)) "
                "(reviewer "
                "(provider-result providers.reviewer "
                ":prompt prompts.reviewer :inputs () :returns String))) "
                "(proc-ref local))"
            ),
        ),
    ),
)
def test_let_proc_escape_analysis_rejects_local_proc_from_provider_group_settlement(
    tmp_path: Path,
    target_dsl: str,
    group_expression: str,
) -> None:
    path = tmp_path / f"target_{target_dsl.replace('.', '_')}_group_escape.orc"
    path.write_text(
        _module_source(
            target_dsl,
            (
                "(defworkflow entry () -> String "
                "(let-proc (local () -> String "
                ':captures () "local") '
                f"{group_expression}))"
            ),
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={
                "providers.worker": "worker-provider",
                "providers.supervisor": "supervisor-provider",
                "providers.planner": "planner-provider",
                "providers.reviewer": "reviewer-provider",
            },
            prompt_externs={
                "prompts.worker": "prompts/worker.md",
                "prompts.supervisor": "prompts/supervisor.md",
                "prompts.planner": "prompts/planner.md",
                "prompts.reviewer": "prompts/reviewer.md",
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "let_proc_scope_escape"


def test_with_live_provider_peers_macro_hygiene_renames_all_binders_and_body(
) -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.17",
                (
                    "(defmacro define-team (name) "
                    "(defworkflow name () -> String "
                    "(with-live-provider-peers "
                    '((planner "plan") '
                    '(reviewer "review") '
                    '(builder "build")) '
                    "reviewer)))"
                ),
                "(define-team orchestrate)",
            ),
            source_path="provider_peer_macro_hygiene.orc",
        )
    )
    catalog = macro_module.collect_macro_catalog(syntax_module)
    expanded = macro_module.expand_module_forms(
        syntax_module,
        catalog=catalog,
    )

    workflow = elaborate_workflow_definitions(expanded)[0]
    group = elaborate_expression(
        workflow.body,
        bound_names=frozenset(),
    )
    peer_type = getattr(
        expression_module,
        "WithLiveProviderPeersExpr",
    )
    assert isinstance(group, peer_type)
    names = tuple(binding.name for binding in group.bindings)
    assert all(
        name.startswith("%macro__define-team__m0001__")
        for name in names
    )
    assert len(set(names)) == 3
    assert isinstance(group.body, expression_module.NameExpr)
    assert group.body.name == names[1]


def test_with_live_provider_peers_target_216_rejects_at_type_gate() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        "planner)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_environment("2.16"),
            value_env={},
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_peer_messaging_target_dsl_unsupported"
    )


def test_live_provider_peer_members_do_not_see_sibling_results() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer planner)) '
        "reviewer)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_environment("2.17"),
            value_env={},
        )

    assert excinfo.value.diagnostics[0].code == "name_unknown"


def test_live_provider_peers_preserve_member_effects_and_authored_order(
) -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        f"((planner {_provider_result('providers.planner', 'prompts.planner')}) "
        f"(reviewer {_provider_result('providers.reviewer', 'prompts.reviewer')}) "
        f"(builder {_provider_result('providers.builder', 'prompts.builder')})) "
        "planner)"
    )

    typed = typecheck_expression(
        expr,
        type_env=_type_environment("2.17"),
        value_env={},
        extern_environment=_peer_extern_environment(),
    )

    assert typed.type_ref == PrimitiveTypeRef(name="String")
    peer_effect_type = getattr(
        effect_module,
        "LivePeerMessagingEffect",
    )
    assert typed.effect_summary.direct_effects == frozenset(
        {
            effect_module.UsesProviderEffect(
                subject=("providers", "planner")
            ),
            effect_module.UsesProviderEffect(
                subject=("providers", "reviewer")
            ),
            effect_module.UsesProviderEffect(
                subject=("providers", "builder")
            ),
            peer_effect_type(
                members=("planner", "reviewer", "builder")
            ),
        }
    )
    assert not any(
        isinstance(effect, effect_module.LiveSupervisionEffect)
        for effect in typed.effect_summary.direct_effects
    )
    assert (
        typed.effect_summary.transitive_effects
        == typed.effect_summary.direct_effects
    )
    assert typed.effect_summary.procedure_edges == frozenset()


def test_live_provider_peers_type_pure_settlement_over_all_results() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        "((planner plan_value) (reviewer review_value)) "
        "(record TeamResult :plan planner :approved reviewer))",
        extra_bound_names=frozenset({"plan_value", "review_value"}),
    )

    typed = typecheck_expression(
        expr,
        type_env=_type_environment(
            "2.17",
            "(defrecord TeamResult (plan String) (approved Bool))",
        ),
        value_env={
            "plan_value": PrimitiveTypeRef(name="String"),
            "review_value": PrimitiveTypeRef(name="Bool"),
        },
    )

    assert isinstance(typed.type_ref, RecordTypeRef)
    assert typed.type_ref.definition.name == "TeamResult"


def test_live_provider_peers_reject_nontransportable_member_result() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        "((planner opaque) (reviewer review_value)) "
        "reviewer)",
        extra_bound_names=frozenset({"opaque", "review_value"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_environment("2.17"),
            value_env={
                "opaque": PrimitiveTypeRef(name="Json"),
                "review_value": PrimitiveTypeRef(name="String"),
            },
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_peer_messaging_member_type_invalid"
    )


def test_live_provider_peers_reject_nontransportable_settlement() -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.17",
                (
                    "(defproc settle () -> String "
                    ':effects () :lowering inline "done")'
                ),
            ),
            source_path="provider_peer_nontransportable_settlement.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    procedure_catalog = build_procedure_catalog(
        procedure_defs,
        type_env=type_env,
    )
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        "(proc-ref settle))",
        procedure_names=frozenset({"settle"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
            procedure_catalog=procedure_catalog,
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_peer_messaging_settlement_type_invalid"
    )


def test_live_provider_peers_reject_outer_settlement_capture() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        "outer)",
        extra_bound_names=frozenset({"outer"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_environment("2.17"),
            value_env={"outer": PrimitiveTypeRef(name="String")},
        )

    assert excinfo.value.diagnostics[0].code == "name_unknown"


def test_live_provider_peers_reject_effectful_settlement() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        f"{_provider_result('providers.body', 'prompts.body')})"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_environment("2.17"),
            value_env={},
            extern_environment=_peer_extern_environment(),
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_peer_messaging_settlement_effectful"
    )


def test_live_provider_peers_reject_effect_free_procedure_settlement_edge(
) -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.17",
                (
                    "(defproc settle () -> String "
                    ':effects () :lowering inline "done")'
                ),
            ),
            source_path="provider_peer_settlement_procedure.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    procedure_catalog = build_procedure_catalog(
        procedure_defs,
        type_env=type_env,
    )
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        "(settle))",
        procedure_names=frozenset({"settle"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
            procedure_catalog=procedure_catalog,
            procedure_effects_by_name={
                "settle": effect_module.EMPTY_EFFECT_SUMMARY,
            },
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "provider_peer_messaging_settlement_effectful"
    )


def test_live_provider_peer_type_boundary_rejects_transformed_duplicate(
) -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        "planner)"
    )
    planner, reviewer = expr.bindings

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            replace(
                expr,
                bindings=(
                    planner,
                    replace(reviewer, name=planner.name),
                ),
            ),
            type_env=_type_environment("2.17"),
            value_env={},
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "with_live_provider_peers_binding_duplicate"
    )


def _typed_identity_function():
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(
                "2.17",
                "(defun identity ((value String)) -> String value)",
            ),
            source_path="provider_peer_function_normalization.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    definitions = function_module.elaborate_function_definitions(
        syntax_module
    )
    catalog = function_module.build_function_catalog(
        definitions,
        type_env=type_env,
    )
    typed = function_module.typecheck_function_definitions(
        definitions,
        type_env=type_env,
        function_catalog=catalog,
    )
    return typed[0]


def test_live_provider_peers_normalize_helpers_in_members_and_settlement(
) -> None:
    identity = _typed_identity_function()
    expr = elaborate_expression(
        _expression(
            "(with-live-provider-peers "
            '((planner (identity "plan")) '
            '(reviewer (identity "review"))) '
            "(identity planner))"
        ),
        bound_names=frozenset(),
        function_names=frozenset({"identity"}),
    )

    normalized = function_module.normalize_function_calls(
        expr,
        typed_functions_by_name={"identity": identity},
    )

    assert all(
        isinstance(
            binding.value_expr,
            expression_module.LetStarExpr,
        )
        for binding in normalized.bindings
    )
    assert isinstance(normalized.body, expression_module.LetStarExpr)
    assert "FunctionCallExpr" not in repr(normalized)


def test_live_provider_peers_are_effectful_in_pure_helpers() -> None:
    expr = _elaborate_peers(
        "(with-live-provider-peers "
        '((planner "plan") (reviewer "review")) '
        "planner)"
    )

    assert (
        function_module._find_purity_violation(expr)
        == "with-live-provider-peers"
    )
