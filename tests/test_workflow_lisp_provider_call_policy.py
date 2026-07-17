from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.core_ast import _statement_to_json
from orchestrator.workflow.executable_ir import (
    ProviderStepConfig,
    _json_value,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.persisted_surface import (
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
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
from orchestrator.workflow_lisp.wcc.defunctionalize import (
    _frontend_expr_from_wcc_loop_binding_value,
)
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow
from orchestrator.workflow_lisp.wcc.model import (
    WccBody,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccPerform,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/provider_call_policy"
TYPE_FIXTURE = REPO_ROOT / "tests/fixtures/workflow_lisp/valid/type_definitions.orc"
KEYWORD_FREE_FIXTURE = FIXTURE_ROOT / "keyword_free.orc"
POLICY_FIXTURE = FIXTURE_ROOT / "policy.orc"
PROCEDURE_POLICY_FIXTURE = FIXTURE_ROOT / "procedure_policy.orc"
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


def _compile_policy_fixture(path: Path, *, route: str = "wcc_m4"):
    workflow_name = {
        POLICY_FIXTURE: "policy",
        PROCEDURE_POLICY_FIXTURE: "procedure-policy",
    }[path]
    return compile_stage3_module(
        path.relative_to(REPO_ROOT),
        entry_workflow=workflow_name,
        provider_externs=_load_manifest("providers.json"),
        prompt_externs=_load_manifest("prompts.json"),
        validate_shared=False,
        workspace_root=REPO_ROOT,
        lowering_route=route,
    )


def _compile_validated_policy_fixture():
    return compile_stage3_module(
        POLICY_FIXTURE.relative_to(REPO_ROOT),
        entry_workflow="policy",
        provider_externs=_load_manifest("providers.json"),
        prompt_externs=_load_manifest("prompts.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route="wcc_m4",
    )


def _build_policy_source(tmp_path: Path, source: str, *, name: str):
    source_path = tmp_path / name / "policy.orc"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source = source.replace(
        '  (:target-dsl "2.15")\n',
        '  (:target-dsl "2.15")\n  (defmodule policy)\n  (export policy)\n',
        1,
    )
    source_path.write_text(source, encoding="utf-8")
    prompt_path = source_path.parent / "tests/fixtures/workflow_lisp/provider_call_policy/prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("Return a WorkResult bundle.\n", encoding="utf-8")
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(source_path.parent,),
            entry_workflow="policy",
            provider_externs_path=FIXTURE_ROOT / "providers.json",
            prompt_externs_path=FIXTURE_ROOT / "prompts.json",
            workspace_root=source_path.parent,
            lowering_route="wcc_m4",
        )
    )


def _provider_steps(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "provider" in value:
            found.append(value)
        for item in value.values():
            found.extend(_provider_steps(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_provider_steps(item))
    return found


def _mappings_with_key(value: Any, key: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if key in value:
            found.append(value)
        for item in value.values():
            found.extend(_mappings_with_key(item, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_mappings_with_key(item, key))
    return found


def _first_wcc_perform(body: WccBody, *, perform_kind: str) -> WccPerform:
    current = body
    while isinstance(current, WccLet):
        if (
            isinstance(current.bound_value, WccPerform)
            and current.bound_value.perform_kind == perform_kind
        ):
            return current.bound_value
        current = current.body
    raise AssertionError(f"no WCC perform of kind {perform_kind!r}")


def _elaborated_policy_perform(path: Path = POLICY_FIXTURE) -> WccPerform:
    result = _compile_policy_fixture(path)
    workflow_name = {
        POLICY_FIXTURE: "policy",
        PROCEDURE_POLICY_FIXTURE: "procedure-policy",
    }[path]
    typed_workflow = next(
        workflow
        for workflow in result.typed_workflows
        if workflow.definition.name == workflow_name
    )
    type_env = FrontendTypeEnvironment.from_module(result.module)
    workflow_return_types = {
        workflow.definition.name: workflow.signature.return_type_ref
        for workflow in result.typed_workflows
    }
    procedure_return_types = {
        procedure.definition.name: procedure.signature.return_type_ref
        for procedure in result.typed_procedures
    }
    body = elaborate_typed_workflow(
        typed_workflow,
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version="wcc_m4",
    )
    return _first_wcc_perform(body, perform_kind="provider_result")


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
    result = _compile_validated_policy_fixture()
    bundle = result.validated_bundles["policy"]
    node_id = "root.policy__result"
    runtime_plan = _json_data(bundle.runtime_plan)
    semantic_ir = workflow_semantic_ir_to_json(bundle.semantic_ir)
    persisted_graph = serialize_persisted_workflow_surface_graph(bundle)
    source_map = _json_data(
        build_source_map_document(
            SimpleNamespace(
                compiled_results_by_name={"__main__": result},
                validated_bundles_by_name=result.validated_bundles,
            ),
            selected_name="policy",
            display_name_resolver=lambda workflow_name: workflow_name,
        )
    )

    assert runtime_plan["nodes"][node_id]["kind"] == "provider"
    assert any(effect["effect_kind"] == "provider_call" for effect in semantic_ir["effects"].values())
    persisted_steps = persisted_graph["nodes"]["policy"]["steps"]
    assert [step["kind"] for step in persisted_steps] == ["provider"]
    source_workflow = source_map["workflows"]["policy"]
    assert [node["step_kind"] for node in source_workflow["core_nodes"]] == ["provider"]
    assert [node["kind"] for node in source_workflow["executable_nodes"]] == ["provider"]

    for projection in (runtime_plan, semantic_ir, persisted_graph, source_map):
        assert not _contains_key(projection, "provider_call_policy")


def test_content_addressed_core_and_executable_artifacts_carry_provider_call_policy(
    tmp_path: Path,
) -> None:
    result = _build_policy_source(
        tmp_path,
        POLICY_FIXTURE.read_text(encoding="utf-8"),
        name="artifact-build",
    )
    core_payload = json.loads(
        result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8")
    )
    executable_payload = json.loads(
        result.artifact_paths["executable_ir"].read_text(encoding="utf-8")
    )

    assert result.build_root.name == result.manifest.fingerprint
    assert core_payload["body"][0]["provider_call_policy"] == {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
    }
    assert len(executable_payload["nodes"]) == 1
    node = next(iter(executable_payload["nodes"].values()))
    assert node["execution_config"]["provider_call_policy"] == {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
    }


def test_provider_call_policy_edits_change_existing_source_and_build_identities(
    tmp_path: Path,
) -> None:
    base = POLICY_FIXTURE.read_text(encoding="utf-8")
    literal = base.replace(":model model", ':model "gpt-5"')
    without_effort = base.replace("      :effort effort\n", "")
    cases = {
        "literal": (literal, literal.replace('"gpt-5"', '"gpt-5.1"')),
        "binding_expression": (
            base,
            base.replace(":model model", ":model effort"),
        ),
        "keyword_added": (without_effort, base),
        "keyword_removed": (base, without_effort),
    }
    stable_root = tmp_path / "stable"
    stable_source_path = stable_root / "policy.orc"
    state_manager = StateManager(stable_root, run_id="provider-policy-identity")

    def capture(source: str) -> dict[str, Any]:
        result = _build_policy_source(tmp_path, source, name="stable")
        program_identity = json.loads(
            result.artifact_paths["lexical_checkpoint_points"].read_text(
                encoding="utf-8"
            )
        )["program_identity"]
        return {
            "source_path": Path(result.manifest.source_path),
            "source_roots": tuple(result.manifest.source_roots),
            "source_digest": result.manifest.source_sha256,
            "build_fingerprint": result.manifest.fingerprint,
            "program_identity": program_identity,
            "executable_ir_digest": hashlib.sha256(
                result.artifact_paths["executable_ir"].read_bytes()
            ).hexdigest(),
            "workflow_checksum": state_manager.calculate_checksum(stable_source_path),
        }

    identical_first = capture(base)
    identical_second = capture(base)
    assert identical_first == identical_second
    assert identical_first["source_path"] == stable_source_path
    assert identical_first["source_roots"] == (str(stable_root),)

    for before_source, after_source in cases.values():
        before = capture(before_source)
        after = capture(after_source)

        assert before["source_path"] == after["source_path"] == stable_source_path
        assert before["source_roots"] == after["source_roots"] == (str(stable_root),)
        assert before["source_digest"] != after["source_digest"]
        assert before["build_fingerprint"] != after["build_fingerprint"]
        assert before["program_identity"] != after["program_identity"]
        assert before["executable_ir_digest"] != after["executable_ir_digest"]
        assert before["workflow_checksum"] != after["workflow_checksum"]


def test_wcc_provider_call_policy_payload_preserves_present_operands() -> None:
    perform = _elaborated_policy_perform()

    assert perform.perform_kind == "provider_result"
    assert isinstance(perform.operation_payload, dict)
    assert isinstance(perform.operation_payload["model"], WccNameAtom)
    assert perform.operation_payload["model"].name == "model"
    assert isinstance(perform.operation_payload["effort"], WccNameAtom)
    assert perform.operation_payload["effort"].name == "effort"
    assert isinstance(perform.operation_payload["timeout_sec"], WccLiteralAtom)
    assert perform.operation_payload["timeout_sec"].value == 7200


def test_wcc_provider_call_policy_reconstruct_preserves_present_operands() -> None:
    reconstructed = _frontend_expr_from_wcc_loop_binding_value(
        _elaborated_policy_perform()
    )

    assert isinstance(reconstructed, ProviderResultExpr)
    assert isinstance(reconstructed.model, NameExpr)
    assert reconstructed.model.name == "model"
    assert isinstance(reconstructed.effort, NameExpr)
    assert reconstructed.effort.name == "effort"
    assert isinstance(reconstructed.timeout_sec, LiteralExpr)
    assert reconstructed.timeout_sec.value == 7200


def test_wcc_provider_call_policy_payload_preserves_absence() -> None:
    result = _compile_keyword_free()
    typed_workflow = result.typed_workflows[0]
    body = elaborate_typed_workflow(
        typed_workflow,
        type_env=FrontendTypeEnvironment.from_module(result.module),
        workflow_return_types={
            typed_workflow.definition.name: typed_workflow.signature.return_type_ref
        },
        route_schema_version="wcc_m4",
    )
    perform = _first_wcc_perform(body, perform_kind="provider_result")

    assert isinstance(perform.operation_payload, dict)
    assert not {"model", "effort", "timeout_sec"} & perform.operation_payload.keys()
    reconstructed = _frontend_expr_from_wcc_loop_binding_value(perform)
    assert isinstance(reconstructed, ProviderResultExpr)
    assert reconstructed.model is None
    assert reconstructed.effort is None
    assert reconstructed.timeout_sec is None


@pytest.mark.parametrize("route", ["wcc_m2", "wcc_m3", "wcc_m4"])
def test_wcc_routes_preserve_provider_call_policy_lowering(route: str) -> None:
    result = _compile_policy_fixture(POLICY_FIXTURE, route=route)
    mapping = result.lowered_workflows[0].authored_mapping
    provider_step = _provider_steps(mapping)[0]

    assert provider_step["provider_call_policy"] == {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
    }
    assert provider_step["timeout_sec"] == 7200


def test_direct_wcc_provider_call_policy_lowering_matches() -> None:
    provider_steps = {
        route: _provider_steps(
            _compile_policy_fixture(POLICY_FIXTURE, route=route)
            .lowered_workflows[0]
            .authored_mapping
        )[0]
        for route in ("legacy", "wcc_m4")
    }

    for field_name in ("provider_call_policy", "timeout_sec"):
        assert provider_steps["legacy"][field_name] == provider_steps["wcc_m4"][field_name]


def test_lowering_renders_literal_and_projected_provider_call_policy_values(
    tmp_path: Path,
) -> None:
    source = POLICY_FIXTURE.read_text(encoding="utf-8")
    source = source.replace(
        "((model String)\n     (effort String))",
        "((model String)\n     (effort String)\n     (config WorkResult))",
    )
    source = source.replace(":model model", ':model "gpt-5"')
    source = source.replace(":effort effort", ":effort config.summary")
    path = tmp_path / "literal_projected_policy.orc"
    path.write_text(source, encoding="utf-8")

    result = compile_stage3_module(
        path,
        entry_workflow="policy",
        provider_externs=_load_manifest("providers.json"),
        prompt_externs=_load_manifest("prompts.json"),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    provider_step = _provider_steps(result.lowered_workflows[0].authored_mapping)[0]

    assert provider_step["provider_call_policy"] == {
        "model": "gpt-5",
        "effort": "${inputs.config__summary}",
    }


@pytest.mark.parametrize(
    ("retained_line", "expected_policy"),
    [
        (":model model", {"model": "${inputs.model}"}),
        (":effort effort", {"effort": "${inputs.effort}"}),
    ],
)
def test_lowering_emits_only_authored_provider_call_policy_key(
    tmp_path: Path,
    retained_line: str,
    expected_policy: dict[str, str],
) -> None:
    source = POLICY_FIXTURE.read_text(encoding="utf-8")
    policy_lines = {
        ":model model",
        ":effort effort",
    }
    source = "\n".join(
        line
        for line in source.splitlines()
        if line.strip() not in policy_lines or line.strip() == retained_line
    ) + "\n"
    path = tmp_path / "one_key_policy.orc"
    path.write_text(source, encoding="utf-8")

    result = compile_stage3_module(
        path,
        entry_workflow="policy",
        provider_externs=_load_manifest("providers.json"),
        prompt_externs=_load_manifest("prompts.json"),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    provider_step = _provider_steps(result.lowered_workflows[0].authored_mapping)[0]

    assert provider_step["provider_call_policy"] == expected_policy


def test_lowering_does_not_emit_empty_provider_call_policy() -> None:
    mapping = _compile_keyword_free().lowered_workflows[0].authored_mapping
    provider_step = _provider_steps(mapping)[0]

    assert "provider_call_policy" not in provider_step
    assert "timeout_sec" not in provider_step


def test_procedure_policy_specialization_uses_caller_bound_inputs_through_loop() -> None:
    result = _compile_policy_fixture(PROCEDURE_POLICY_FIXTURE)
    mappings = [lowered.authored_mapping for lowered in result.lowered_workflows]
    provider_steps = [
        step
        for mapping in mappings
        for step in _provider_steps(mapping)
        if "provider_call_policy" in step
    ]

    assert len(provider_steps) == 1
    assert provider_steps[0]["provider_call_policy"] == {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
    }
    assert provider_steps[0]["timeout_sec"] == 7200
    root_mapping = result.lowered_workflows[0].authored_mapping
    procedure_call = next(
        step
        for step in _mappings_with_key(root_mapping, "call")
        if step["call"].endswith("invoke-provider.v1")
    )
    assert procedure_call["with"]["model"] == {"ref": "inputs.model"}
    assert procedure_call["with"]["effort"] == {"ref": "inputs.effort"}
    assert all(
        not _contains_key(mapping, "provider_call_policy_specialization")
        for mapping in mappings
    )


def test_provider_call_policy_survives_surface_core_executable_and_runtime_step() -> None:
    result = _compile_validated_policy_fixture()
    bundle = result.validated_bundles["policy"]
    expected_policy = {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
    }

    surface_step = bundle.surface.steps[0]
    core_step = bundle.core_workflow_ast.body[0]
    node = bundle.ir.nodes["root.policy__result"]
    config = node.execution_config
    assert isinstance(config, ProviderStepConfig)

    assert dict(surface_step.provider_call_policy or {}) == expected_policy
    assert dict(core_step.provider_call_policy or {}) == expected_policy
    assert dict(config.provider_call_policy or {}) == expected_policy
    with pytest.raises(TypeError):
        surface_step.provider_call_policy["model"] = "mutated"  # type: ignore[index]
    assert workflow_executable_ir_to_json(bundle.ir)["nodes"][node.node_id][
        "execution_config"
    ]["provider_call_policy"] == expected_policy
    assert dict(RuntimeStep(node=node, name="Policy", step_id="policy"))[
        "provider_call_policy"
    ] == expected_policy
    assert surface_step.common.timeout_sec == 7200
    assert core_step.common.timeout_sec == 7200
    assert config.common.timeout_sec == 7200


def test_provider_call_policy_absence_is_none_and_omitted_from_typed_json() -> None:
    result = _compile_keyword_free()
    bundle = result.validated_bundles[WORKFLOW_NAME]
    surface_step = bundle.surface.steps[0]
    core_step = bundle.core_workflow_ast.body[0]
    node = bundle.ir.nodes[NODE_ID]
    config = node.execution_config
    assert isinstance(config, ProviderStepConfig)

    assert surface_step.provider_call_policy is None
    assert core_step.provider_call_policy is None
    assert config.provider_call_policy is None
    assert "provider_call_policy" not in _statement_to_json(core_step)
    assert "provider_call_policy" not in _json_value(config)
    assert "provider_call_policy" not in dict(
        RuntimeStep(node=node, name=RUNTIME_NAME, step_id=RUNTIME_STEP_ID)
    )


def test_provider_call_policy_serializers_use_field_local_model_effort_order() -> None:
    result = _compile_validated_policy_fixture()
    bundle = result.validated_bundles["policy"]
    core_step = bundle.core_workflow_ast.body[0]
    node = bundle.ir.nodes["root.policy__result"]
    config = node.execution_config
    assert isinstance(config, ProviderStepConfig)

    expected_core = (
        b'{"meta":{"id":"root.policy__result","step_id":"policy__result",'
        b'"step_kind":"provider","display_name":"policy__result","lexical_scope":[],'
        b'"origin_key":"policy::root.policy__result","generated_by":null},"common":'
        b'{"on":null,"consumes":[],"consume_bundle":null,"publishes":[],'
        b'"expected_outputs":[],"output_bundle":{"path":"${inputs.__write_root__policy__result__result_bundle}",'
        b'"fields":[{"name":"approved","json_pointer":"/approved","type":"bool"},'
        b'{"name":"summary","json_pointer":"/summary","type":"string"}]},'
        b'"variant_output":null,"pre_snapshot":null,"requires_variant":null,'
        b'"persist_artifacts_in_state":null,"provider_session":null,"max_visits":null,'
        b'"retries":null,"env":null,"secrets":[],"timeout_sec":7200,'
        b'"output_capture":null,"output_file":null,"allow_parse_error":null},'
        b'"kind":"provider","provider":"test-provider","provider_params":null,'
        b'"managed_jobs":null,"input_file":null,"asset_file":'
        b'"tests/fixtures/workflow_lisp/provider_call_policy/prompt.md","depends_on":{},'
        b'"asset_depends_on":[],"inject_output_contract":true,"inject_consumes":null,'
        b'"prompt_consumes":null,"typed_prompt_inputs":[],"consumes_injection_position":null,'
        b'"provider_call_policy":{"model":"m","effort":"e"}}'
    )
    expected_executable = (
        b'{"common":{"on":{},"consumes":[],"consume_bundle":null,"publishes":[],'
        b'"expected_outputs":[],"output_bundle":{"fields":[{"json_pointer":"/approved",'
        b'"name":"approved","type":"bool"},{"json_pointer":"/summary","name":"summary",'
        b'"type":"string"}],"path":"${inputs.__write_root__policy__result__result_bundle}"},'
        b'"variant_output":null,"pre_snapshot":null,"requires_variant":null,'
        b'"persist_artifacts_in_state":null,"provider_session":null,"max_visits":null,'
        b'"retries":null,"env":null,"secrets":[],"timeout_sec":7200,'
        b'"output_capture":null,"output_file":null,"allow_parse_error":null},'
        b'"provider":"test-provider","provider_params":null,'
        b'"provider_call_policy":{"model":"m","effort":"e"},"input_file":null,'
        b'"asset_file":"tests/fixtures/workflow_lisp/provider_call_policy/prompt.md",'
        b'"depends_on":{},"asset_depends_on":[],"inject_output_contract":true,'
        b'"inject_consumes":null,"prompt_consumes":null,"typed_prompt_inputs":[],'
        b'"consumes_injection_position":null,"managed_jobs":null}'
    )

    for policy in (
        {"model": "m", "effort": "e"},
        {"effort": "e", "model": "m"},
    ):
        core_bytes = json.dumps(
            _statement_to_json(replace(core_step, provider_call_policy=policy)),
            separators=(",", ":"),
        ).encode("utf-8")
        executable_bytes = json.dumps(
            _json_value(replace(config, provider_call_policy=policy)),
            separators=(",", ":"),
        ).encode("utf-8")

        assert core_bytes == expected_core
        assert executable_bytes == expected_executable


def test_provider_call_policy_serializer_rejects_unexpected_key() -> None:
    result = _compile_validated_policy_fixture()
    bundle = result.validated_bundles["policy"]
    core_step = bundle.core_workflow_ast.body[0]
    node = bundle.ir.nodes["root.policy__result"]
    config = node.execution_config
    assert isinstance(config, ProviderStepConfig)

    with pytest.raises(ValueError, match="unexpected provider call policy key"):
        _statement_to_json(
            replace(core_step, provider_call_policy={"model": "m", "unknown": "x"})
        )
    with pytest.raises(ValueError, match="unexpected provider call policy key"):
        _json_value(
            replace(config, provider_call_policy={"model": "m", "unknown": "x"})
        )
