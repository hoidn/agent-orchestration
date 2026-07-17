from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.workflow.core_ast import _statement_to_json
from orchestrator.workflow.executable_ir import (
    ProviderStepConfig,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.persisted_surface import (
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.build import _json_data
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import (
    EMPTY_EFFECT_SUMMARY,
    ProcedureCallEdge,
    UsesProviderEffect,
    effect_summary,
)
from orchestrator.workflow_lisp.expressions import (
    FieldAccessExpr,
    FunctionCallExpr,
    LetStarExpr,
    LiteralExpr,
    NameExpr,
    ProviderResultExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs, walk_expr
from orchestrator.workflow_lisp.functions import (
    FunctionDef,
    FunctionSignature,
    TypedFunctionDef,
    normalize_function_calls,
)
from orchestrator.workflow_lisp.macros import collect_macro_catalog, expand_module_forms
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import (
    SyntaxIdentifier,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    build_syntax_module,
    syntax_head_name,
)
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef
from orchestrator.workflow_lisp.typecheck import TypedExpr, typecheck_expression
from orchestrator.workflow_lisp.typecheck_effects import typecheck_provider_result_expr
from orchestrator.workflow_lisp.workflows import build_extern_environment


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/provider_call_policy"
TYPE_FIXTURE = REPO_ROOT / "tests/fixtures/workflow_lisp/valid/type_definitions.orc"
KEYWORD_FREE_FIXTURE = FIXTURE_ROOT / "keyword_free.orc"
KEYWORD_FREE_BASELINE = (
    REPO_ROOT / "tests/baselines/workflow_lisp/provider_call_policy_keyword_free.json"
)
WORKFLOW_NAME = "keyword-free"
NODE_ID = "root.keyword_free__result"
RUNTIME_NAME = "KeywordFreeProvider"
RUNTIME_STEP_ID = "keyword_free_provider"
CONSTANT_SPAN = SourceSpan(
    start=SourcePosition(path="<provider-call-policy-fixture>", line=1, column=1, offset=0),
    end=SourcePosition(path="<provider-call-policy-fixture>", line=1, column=2, offset=1),
)


def _load_manifest(name: str) -> dict[str, str]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _compile_keyword_free():
    return compile_stage3_module(
        KEYWORD_FREE_FIXTURE.relative_to(REPO_ROOT),
        entry_workflow=WORKFLOW_NAME,
        provider_externs=_load_manifest("providers.json"),
        prompt_externs=_load_manifest("prompts.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route="wcc_m4",
    )


def _keyword_free_representation_payload() -> dict[str, Any]:
    result = _compile_keyword_free()
    typed_expr = result.typed_workflows[0].typed_body.expr
    assert isinstance(typed_expr, ProviderResultExpr)
    typed_expr = replace(
        typed_expr,
        provider=replace(typed_expr.provider, span=CONSTANT_SPAN),
        prompt=replace(typed_expr.prompt, span=CONSTANT_SPAN),
        span=CONSTANT_SPAN,
    )

    bundle = result.validated_bundles[WORKFLOW_NAME]
    assert len(bundle.core_workflow_ast.body) == 1
    assert tuple(bundle.ir.nodes) == (NODE_ID,)
    node = bundle.ir.nodes[NODE_ID]
    assert isinstance(node.execution_config, ProviderStepConfig)

    executable_node = workflow_executable_ir_to_json(bundle.ir)["nodes"][NODE_ID]
    return {
        "typed_provider_result": _json_data(typed_expr),
        "core_provider_statement": _statement_to_json(bundle.core_workflow_ast.body[0]),
        "executable_provider_config": executable_node["execution_config"],
        "runtime_step": dict(
            RuntimeStep(node=node, name=RUNTIME_NAME, step_id=RUNTIME_STEP_ID)
        ),
    }


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_key(item, key) for item in value)
    return False


def _expression_syntax(source: str) -> SyntaxNode:
    module = read_sexpr_text(source, source_path="provider_call_policy_test.orc")
    assert len(module.items) == 1
    datum = module.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="provider_call_policy_test.orc",
        form_path=("workflow-lisp", "provider-call-policy-test"),
    )


def _elaborate_policy_expr(source: str) -> ProviderResultExpr:
    expr = elaborate_expression(
        _expression_syntax(source),
        bound_names=frozenset(
            {
                "providers.execute",
                "prompts.execute",
                "model_input",
                "effort_input",
            }
        ),
    )
    assert isinstance(expr, ProviderResultExpr)
    return expr


def _diagnostic_code(source: str) -> str:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_policy_expr(source)
    return excinfo.value.diagnostics[0].code


def _policy_type_env() -> FrontendTypeEnvironment:
    from orchestrator.workflow_lisp.compiler import compile_stage1_module

    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _policy_extern_environment():
    return build_extern_environment(
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
    )


def _typecheck_policy_source(
    source: str,
    *,
    value_env: dict[str, object] | None = None,
) -> TypedExpr:
    names = set(value_env or {})
    names.update({"providers.execute", "prompts.execute"})
    expr = elaborate_expression(
        _expression_syntax(source),
        bound_names=frozenset(names),
    )
    return typecheck_expression(
        expr,
        type_env=_policy_type_env(),
        value_env=value_env or {},
        extern_environment=_policy_extern_environment(),
    )


def _typed(expr, type_ref, summary=EMPTY_EFFECT_SUMMARY) -> TypedExpr:
    return TypedExpr(
        expr=expr,
        type_ref=type_ref,
        effect_summary=summary,
        span=expr.span,
        form_path=expr.form_path,
    )


@pytest.mark.parametrize(
    ("keyword_section", "field_name", "expected_type"),
    [
        (':model "gpt-5"', "model", LiteralExpr),
        (':effort "high"', "effort", LiteralExpr),
        (":timeout-sec 7200", "timeout_sec", LiteralExpr),
    ],
)
def test_parse_provider_call_policy_accepts_each_optional_keyword_alone(
    keyword_section: str,
    field_name: str,
    expected_type: type,
) -> None:
    expr = _elaborate_policy_expr(
        "(provider-result providers.execute "
        ":prompt prompts.execute :inputs () "
        f"{keyword_section} :returns Bool)"
    )

    assert isinstance(getattr(expr, field_name), expected_type)
    for absent_name in {"model", "effort", "timeout_sec"} - {field_name}:
        assert getattr(expr, absent_name) is None


@pytest.mark.parametrize(
    "sections",
    [
        ':prompt prompts.execute :inputs () :returns Bool '
        ':model model_input :effort effort_input :timeout-sec 7200',
        ':timeout-sec 7200 :returns Bool :effort effort_input '
        ':prompt prompts.execute :model model_input :inputs ()',
        ':effort effort_input :prompt prompts.execute :model model_input '
        ':inputs () :timeout-sec 7200 :returns Bool',
    ],
)
def test_parse_provider_call_policy_is_keyword_order_independent(sections: str) -> None:
    source = f"(provider-result providers.execute {sections})"

    expr = _elaborate_policy_expr(source)

    assert isinstance(expr.model, NameExpr)
    assert expr.model.name == "model_input"
    assert isinstance(expr.effort, NameExpr)
    assert expr.effort.name == "effort_input"
    assert isinstance(expr.timeout_sec, LiteralExpr)
    assert expr.timeout_sec.value == 7200
    assert expr.model.span.start.offset == source.index("model_input")
    assert expr.effort.span.start.offset == source.index("effort_input")
    assert expr.timeout_sec.span.start.offset == source.index("7200")


def test_provider_call_policy_ast_marks_optional_fields_for_none_omission() -> None:
    expr = _elaborate_policy_expr(
        "(provider-result providers.execute "
        ":prompt prompts.execute :inputs () :returns Bool)"
    )

    field_map = {item.name: item for item in fields(expr)}
    assert expr.model is None
    assert expr.effort is None
    assert expr.timeout_sec is None
    assert field_map["model"].metadata["json_omit_if_none"] is True
    assert field_map["effort"].metadata["json_omit_if_none"] is True
    assert field_map["timeout_sec"].metadata["json_omit_if_none"] is True


@pytest.mark.parametrize(
    "source",
    [
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        ":returns Bool :model)",
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        ':model "a" :model "b" :returns Bool)',
    ],
)
def test_parse_provider_call_policy_rejects_malformed_or_duplicate_keywords(source: str) -> None:
    assert _diagnostic_code(source) == "frontend_parse_error"


def test_parse_provider_call_policy_rejects_unknown_keyword() -> None:
    assert (
        _diagnostic_code(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":temperature 1 :returns Bool)"
        )
        == "provider_result_keyword_invalid"
    )


@pytest.mark.parametrize(
    ("operand", "value_env"),
    [
        ('"gpt-5"', {}),
        ("workflow_model", {"workflow_model": PrimitiveTypeRef(name="String")}),
        ("procedure_model", {"procedure_model": PrimitiveTypeRef(name="String")}),
        ("lexical_model", {"lexical_model": PrimitiveTypeRef(name="String")}),
    ],
    ids=["literal", "workflow-input", "procedure-parameter", "lexical-name"],
)
def test_type_provider_call_policy_accepts_inline_string_sources(
    operand: str,
    value_env: dict[str, object],
) -> None:
    typed = _typecheck_policy_source(
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":model {operand} :returns Bool)",
        value_env=value_env,
    )

    assert typed.type_ref == PrimitiveTypeRef(name="Bool")


def test_type_provider_call_policy_accepts_string_field_projection() -> None:
    type_env = _policy_type_env()
    result_type = type_env.resolve_type(
        "ImplementationSummary",
        span=CONSTANT_SPAN,
        form_path=("workflow-lisp", "provider-call-policy-test"),
    )
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        ":effort result.status :returns Bool)"
    )
    names = frozenset({"providers.execute", "prompts.execute", "result"})
    expr = elaborate_expression(_expression_syntax(source), bound_names=names)

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={"result": result_type},
        extern_environment=_policy_extern_environment(),
    )

    assert typed.type_ref == PrimitiveTypeRef(name="Bool")
    assert isinstance(expr.effort, FieldAccessExpr)


@pytest.mark.parametrize(
    ("keyword", "operand", "value_env", "expected_code"),
    [
        (":model", "true", {}, "provider_result_model_type_invalid"),
        (":model", "(if ready 1 2)", {"ready": PrimitiveTypeRef(name="Bool")}, "provider_result_model_type_invalid"),
        (":effort", "1", {}, "provider_result_effort_type_invalid"),
        (
            ":effort",
            "(record ImplementationSummary :status \"ok\" :report report)",
            {
                "report": _policy_type_env().resolve_type(
                    "WorkReport",
                    span=CONSTANT_SPAN,
                    form_path=("workflow-lisp", "provider-call-policy-test"),
                )
            },
            "provider_result_effort_type_invalid",
        ),
    ],
)
def test_type_provider_call_policy_rejects_non_string_before_inline_shape(
    keyword: str,
    operand: str,
    value_env: dict[str, object],
    expected_code: str,
) -> None:
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f"{keyword} {operand} :returns Bool)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_policy_source(source, value_env=value_env)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == expected_code
    assert diagnostic.span.start.offset == source.index(operand)


@pytest.mark.parametrize(
    ("operand", "value_env"),
    [
        (
            '(if ready "gpt-5" "gpt-5-mini")',
            {"ready": PrimitiveTypeRef(name="Bool")},
        ),
        ('(string/concat "gpt" "-5")', {}),
        (
            "(provider-result providers.execute :prompt prompts.execute :inputs () :returns String)",
            {},
        ),
    ],
    ids=["computed-if", "pure-operator", "direct-effect"],
)
def test_inline_lowerable_provider_call_policy_rejects_computed_string_operands(
    operand: str,
    value_env: dict[str, object],
) -> None:
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":model {operand} :returns Bool)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_policy_source(source, value_env=value_env)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_result_policy_operand_not_inline_lowerable"
    assert diagnostic.span.start.offset == source.index(operand)


def test_inline_lowerable_policy_rejects_transitive_effects_but_allows_procedure_edges() -> None:
    expr = _elaborate_policy_expr(
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        ":model model_input :returns Bool)"
    )
    assert expr.model is not None
    context = SimpleNamespace(
        type_env=_policy_type_env(),
        value_env={},
        active_phase_scope=None,
        extern_environment=_policy_extern_environment(),
    )
    edge = ProcedureCallEdge(callee_name="render-model")
    edge_only_summary = effect_summary(procedure_edges=(edge,))

    def edge_only_recurse(node):
        if node is expr.provider:
            return _typed(node, PrimitiveTypeRef(name="Provider"))
        if node is expr.prompt:
            return _typed(node, PrimitiveTypeRef(name="Prompt"))
        if node is expr.model:
            return _typed(node, PrimitiveTypeRef(name="String"), edge_only_summary)
        raise AssertionError(f"unexpected recurse node: {node!r}")

    accepted = typecheck_provider_result_expr(
        expr,
        context=context,
        recurse=edge_only_recurse,
        typed_factory=lambda *, expr, type_ref, effect: _typed(expr, type_ref, effect),
    )
    assert edge in accepted.effect_summary.procedure_edges

    transitive_summary = effect_summary(
        direct_effects=(),
        transitive_effects=(UsesProviderEffect(subject=("providers", "other")),),
        procedure_edges=(edge,),
    )

    def transitive_recurse(node):
        if node is expr.provider:
            return _typed(node, PrimitiveTypeRef(name="Provider"))
        if node is expr.prompt:
            return _typed(node, PrimitiveTypeRef(name="Prompt"))
        if node is expr.model:
            return _typed(node, PrimitiveTypeRef(name="String"), transitive_summary)
        raise AssertionError(f"unexpected recurse node: {node!r}")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_provider_result_expr(
            expr,
            context=context,
            recurse=transitive_recurse,
            typed_factory=lambda *, expr, type_ref, effect: _typed(expr, type_ref, effect),
        )
    assert excinfo.value.diagnostics[0].code == "provider_result_policy_operand_not_inline_lowerable"


@pytest.mark.parametrize("value", [1, 7200])
def test_timeout_provider_call_policy_accepts_positive_int_literals(value: int) -> None:
    typed = _typecheck_policy_source(
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":timeout-sec {value} :returns Bool)"
    )

    assert typed.type_ref == PrimitiveTypeRef(name="Bool")


@pytest.mark.parametrize(
    ("operand", "value_env", "expected_code"),
    [
        ("timeout_value", {"timeout_value": PrimitiveTypeRef(name="Int")}, "provider_result_timeout_literal_required"),
        ("(+ 1 2)", {}, "provider_result_timeout_literal_required"),
        ("true", {}, "provider_result_timeout_type_invalid"),
        ("1.5", {}, "provider_result_timeout_type_invalid"),
        ('"7200"', {}, "provider_result_timeout_type_invalid"),
        ("0", {}, "provider_result_timeout_nonpositive"),
        ("-1", {}, "provider_result_timeout_nonpositive"),
    ],
)
def test_timeout_provider_call_policy_enforces_literal_type_and_positive_domain(
    operand: str,
    value_env: dict[str, object],
    expected_code: str,
) -> None:
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":timeout-sec {operand} :returns Bool)"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_policy_source(source, value_env=value_env)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == expected_code
    assert diagnostic.span.start.offset == source.index(operand)


def test_traversal_provider_call_policy_visits_model_and_effort_but_not_literal_timeout() -> None:
    expr = _elaborate_policy_expr(
        "(provider-result providers.execute :effort effort_input :timeout-sec 30 "
        ":inputs (model_input) :returns Bool :model model_input :prompt prompts.execute)"
    )

    children = iter_child_exprs(expr)
    assert [getattr(child, "name", None) for child in children] == [
        "providers.execute",
        "prompts.execute",
        "model_input",
        "model_input",
        "effort_input",
    ]
    assert expr.timeout_sec not in children
    assert tuple(walk_expr(expr)) == (expr, *children)


def test_normalization_provider_call_policy_rewrites_model_and_effort_and_preserves_timeout() -> None:
    base = _elaborate_policy_expr(
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        ':model "unused" :effort "unused" :timeout-sec 30 :returns Bool)'
    )
    helper_arg = NameExpr(name="value", span=CONSTANT_SPAN, form_path=base.form_path)
    helper_call = FunctionCallExpr(
        callee_name="identity-model",
        args=(LiteralExpr(value="gpt-5", literal_kind="string", span=CONSTANT_SPAN, form_path=base.form_path),),
        span=CONSTANT_SPAN,
        form_path=base.form_path,
    )
    function_def = FunctionDef(
        name="identity-model",
        params=(),
        return_type_name="String",
        body=_expression_syntax("value"),
        span=CONSTANT_SPAN,
        form_path=base.form_path,
    )
    signature = FunctionSignature(
        name="identity-model",
        params=(("value", PrimitiveTypeRef(name="String")),),
        return_type_ref=PrimitiveTypeRef(name="String"),
        span=CONSTANT_SPAN,
        form_path=base.form_path,
    )
    typed_function = TypedFunctionDef(
        definition=function_def,
        signature=signature,
        typed_body=_typed(helper_arg, PrimitiveTypeRef(name="String")),
    )
    expr = replace(base, model=helper_call, effort=helper_call)
    authored_timeout = expr.timeout_sec

    normalized = normalize_function_calls(
        expr,
        typed_functions_by_name={"identity-model": typed_function},
    )

    assert isinstance(normalized, ProviderResultExpr)
    assert isinstance(normalized.model, LetStarExpr)
    assert isinstance(normalized.effort, LetStarExpr)
    assert normalized.timeout_sec is authored_timeout


def test_macro_hygiene_provider_call_policy_uses_keyword_roles_in_reordered_form() -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.15")',
            "  (make-policy policy)",
            "  (defmacro make-policy (workflow-name)",
            "    (defworkflow workflow-name",
            "      ((source String))",
            "      -> Bool",
            "      (let* ((tmp source))",
            "        (provider-result providers.execute",
            "          :returns Bool",
            "          :effort tmp",
            "          :timeout-sec 30",
            "          :inputs ()",
            "          :model tmp",
            "          :prompt prompts.execute)))))",
        ]
    )
    syntax_module = build_syntax_module(
        read_sexpr_text(source, source_path="provider_policy_macro.orc")
    )
    expanded = expand_module_forms(
        syntax_module,
        catalog=collect_macro_catalog(syntax_module),
    )

    def lists(node):
        if isinstance(node, SyntaxNode):
            yield from lists(node.datum)
            return
        if isinstance(node, SyntaxList):
            yield node
            for item in node.items:
                yield from lists(item)

    provider_form = next(
        item
        for form in expanded.forms
        for item in lists(form)
        if syntax_head_name(item) == "provider-result"
    )
    sections = {
        keyword.value: provider_form.items[index + 1]
        for index, keyword in enumerate(provider_form.items[:-1])
        if isinstance(keyword, SyntaxKeyword)
    }

    assert isinstance(sections[":model"], SyntaxIdentifier)
    assert isinstance(sections[":effort"], SyntaxIdentifier)
    assert sections[":model"].resolved_name == "%macro__make-policy__m0001__tmp"
    assert sections[":effort"].resolved_name == "%macro__make-policy__m0001__tmp"
    assert sections[":timeout-sec"].value == 30


def test_keyword_free_provider_result_matches_pre_feature_golden_bytes() -> None:
    actual = _canonical_bytes(_keyword_free_representation_payload())

    assert actual == KEYWORD_FREE_BASELINE.read_bytes()


def test_provider_call_policy_projection_exclusions_remain_policy_neutral() -> None:
    result = _compile_keyword_free()
    bundle = result.validated_bundles[WORKFLOW_NAME]
    runtime_plan = _json_data(bundle.runtime_plan)
    semantic_ir = workflow_semantic_ir_to_json(bundle.semantic_ir)
    persisted_graph = serialize_persisted_workflow_surface_graph(bundle)
    source_map = _json_data(
        build_source_map_document(
            SimpleNamespace(
                compiled_results_by_name={"__main__": result},
                validated_bundles_by_name=result.validated_bundles,
            ),
            selected_name=WORKFLOW_NAME,
            display_name_resolver=lambda workflow_name: workflow_name,
        )
    )

    assert runtime_plan["nodes"][NODE_ID]["kind"] == "provider"
    assert any(effect["effect_kind"] == "provider_call" for effect in semantic_ir["effects"].values())
    persisted_steps = persisted_graph["nodes"][WORKFLOW_NAME]["steps"]
    assert [step["kind"] for step in persisted_steps] == ["provider"]
    source_workflow = source_map["workflows"][WORKFLOW_NAME]
    assert [node["step_kind"] for node in source_workflow["core_nodes"]] == ["provider"]
    assert [node["kind"] for node in source_workflow["executable_nodes"]] == ["provider"]

    for projection in (runtime_plan, semantic_ir, persisted_graph, source_map):
        assert not _contains_key(projection, "provider_call_policy")
