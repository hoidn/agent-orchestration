from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.persisted_surface import serialize_persisted_workflow_surface_graph
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.build import _json_data
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import (
    EMPTY_EFFECT_SUMMARY,
    ProcedureCallEdge,
    UsesProviderEffect,
    effect_summary,
)
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs, walk_expr
from orchestrator.workflow_lisp.expressions import (
    FieldAccessExpr,
    FunctionCallExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    NameExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.functions import (
    FunctionDef,
    FunctionSignature,
    TypedFunctionDef,
    normalize_function_calls,
)
from orchestrator.workflow_lisp.procedure_specialization import specialize_typed_procedure
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
)
from orchestrator.workflow_lisp.typecheck import TypedExpr, typecheck_expression
from orchestrator.workflow_lisp.typecheck_effects import typecheck_provider_result_expr
from orchestrator.workflow_lisp.workflows import build_extern_environment
from orchestrator.workflow_lisp.wcc.route import (
    _validate_wcc_m2_expr_supported,
    _validate_wcc_m3_expr_supported,
    _validate_wcc_m4_expr_supported,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/provider_prompt_dependencies"
BASELINE = REPO_ROOT / "tests/baselines/workflow_lisp/provider_prompt_dependencies_keyword_free.json"
TYPE_FIXTURE = REPO_ROOT / "tests/fixtures/workflow_lisp/valid/type_definitions.orc"
CONSTANT_SPAN = SourceSpan(
    start=SourcePosition(path="<prompt-dependencies-test>", line=1, column=1, offset=0),
    end=SourcePosition(path="<prompt-dependencies-test>", line=1, column=2, offset=1),
)


def _manifest(name: str) -> dict[str, str]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _artifact(value: Any) -> dict[str, str]:
    data = _canonical(value)
    return {"canonical_bytes": data.decode("ascii"), "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}"}


def _route_artifacts(route: str) -> dict[str, dict[str, str]]:
    result = compile_stage3_module(
        (FIXTURE_ROOT / "keyword_free.orc").relative_to(REPO_ROOT),
        entry_workflow="keyword-free",
        provider_externs=_manifest("providers.json"),
        prompt_externs=_manifest("prompts.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route=route,
    )
    lowered = result.lowered_workflows[0]
    bundle = result.validated_bundles["keyword-free"]
    source_map = _json_data(
        build_source_map_document(
            SimpleNamespace(
                compiled_results_by_name={"__main__": result},
                validated_bundles_by_name=result.validated_bundles,
            ),
            selected_name="keyword-free",
            display_name_resolver=lambda name: name,
        )
    )
    return {
        "frontend_ast": _artifact(_json_data(result.module)),
        "lowered_mapping": _artifact(lowered.authored_mapping),
        "core_ast": _artifact(_json_data(bundle.core_workflow_ast)),
        "executable_ir": _artifact(workflow_executable_ir_to_json(bundle.ir)),
        "semantic_ir": _artifact(workflow_semantic_ir_to_json(bundle.semantic_ir)),
        "persisted_surface": _artifact(serialize_persisted_workflow_surface_graph(bundle)),
        "runtime_plan": _artifact(_json_data(bundle.runtime_plan)),
        "source_map": _artifact(source_map),
    }


def _expression_syntax(source: str) -> SyntaxNode:
    module = read_sexpr_text(source, source_path="prompt_dependencies_test.orc")
    assert len(module.items) == 1
    datum = module.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="prompt_dependencies_test.orc",
        form_path=("workflow-lisp", "prompt-dependencies-test"),
    )


def _elaborate_dependency_expr(
    clause: str,
    *,
    names: frozenset[str] = frozenset({"required_path", "optional_path"}),
) -> ProviderResultExpr:
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":prompt-dependencies {clause} :returns Bool)"
    )
    expr = elaborate_expression(
        _expression_syntax(source),
        bound_names=names | {"providers.execute", "prompts.execute"},
    )
    assert isinstance(expr, ProviderResultExpr)
    return expr


def _diagnostic_for_clause(clause: str) -> tuple[str, int, int]:
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":prompt-dependencies {clause} :returns Bool)"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(source),
            bound_names=frozenset(
                {"providers.execute", "prompts.execute", "required_path", "optional_path"}
            ),
        )
    diagnostic = excinfo.value.diagnostics[0]
    return diagnostic.code, diagnostic.span.start.offset, diagnostic.span.end.offset


def _type_env() -> FrontendTypeEnvironment:
    from orchestrator.workflow_lisp.compiler import compile_stage1_module

    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _extern_environment():
    return build_extern_environment(
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "tests/prompt.md"},
    )


def _typecheck_dependency_expr(clause: str, *, value_env: dict[str, object]) -> TypedExpr:
    names = frozenset(value_env) | {"providers.execute", "prompts.execute"}
    expr = _elaborate_dependency_expr(clause, names=names)
    return typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env=value_env,
        extern_environment=_extern_environment(),
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
    ("clause", "required", "optional", "position", "instruction"),
    [
        ("(:required (required_path))", ("required_path",), (), "prepend", None),
        ("(:optional (optional_path))", (), ("optional_path",), "prepend", None),
        (
            '(:optional (optional_path) :position append :instruction "Read these" '
            ":required (required_path))",
            ("required_path",),
            ("optional_path",),
            "append",
            "Read these",
        ),
    ],
)
def test_parser_prompt_dependencies_accepts_closed_typed_shape(
    clause: str,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    position: str,
    instruction: str | None,
) -> None:
    expr = _elaborate_dependency_expr(clause)

    assert type(expr.prompt_dependencies).__name__ == "PromptDependencySpec"
    assert tuple(item.name for item in expr.prompt_dependencies.required) == required
    assert tuple(item.name for item in expr.prompt_dependencies.optional) == optional
    assert expr.prompt_dependencies.position == position
    assert expr.prompt_dependencies.instruction == instruction
    assert expr.prompt_dependencies.span.start.offset < expr.prompt_dependencies.span.end.offset
    assert expr.prompt_dependencies.form_path == expr.form_path


def test_parser_prompt_dependencies_ast_omits_absence() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () :returns Bool)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute"}),
    )
    field_map = {item.name: item for item in fields(expr)}

    assert expr.prompt_dependencies is None
    assert field_map["prompt_dependencies"].metadata["json_omit_if_none"] is True


@pytest.mark.parametrize(
    ("clause", "expected_code", "token"),
    [
        ("()", "prompt_dependencies_clause_invalid", "()"),
        ("(:required ())", "prompt_dependencies_clause_invalid", "()"),
        ("(:optional ())", "prompt_dependencies_clause_invalid", "()"),
        (
            "(:required (required_path) :required (optional_path))",
            "prompt_dependencies_keyword_duplicate",
            ":required (optional_path)",
        ),
        (
            "(:required (required_path) :surprise (optional_path))",
            "prompt_dependencies_keyword_invalid",
            ":surprise",
        ),
        (
            "(:required (required_path) :position middle)",
            "prompt_dependency_position_invalid",
            "middle",
        ),
        (
            '(:required (required_path) :instruction (string/concat "a" "b"))',
            "prompt_dependency_instruction_literal_required",
            "(string/concat",
        ),
        (
            '(:required ((__generated-relpath-seed__ WorkReport "x" "test")))',
            "prompt_dependency_generated_relpath_invalid",
            "__generated-relpath-seed__",
        ),
    ],
)
def test_parser_prompt_dependencies_rejects_invalid_closed_shape_with_operand_span(
    clause: str,
    expected_code: str,
    token: str,
) -> None:
    code, start, end = _diagnostic_for_clause(clause)
    source = (
        "(provider-result providers.execute :prompt prompts.execute :inputs () "
        f":prompt-dependencies {clause} :returns Bool)"
    )
    assert code == expected_code
    token_offset = source.index(token, source.index(":prompt-dependencies"))
    assert start <= token_offset < end


@pytest.mark.parametrize("byte_count", [261629, 261630])
def test_parser_prompt_dependency_instruction_accepts_utf8_byte_boundary(byte_count: int) -> None:
    instruction = "a" * (byte_count - 2) + "é"
    expr = _elaborate_dependency_expr(
        f'(:required (required_path) :instruction "{instruction}")'
    )
    assert len(expr.prompt_dependencies.instruction.encode("utf-8")) == byte_count


def test_parser_prompt_dependency_instruction_rejects_utf8_byte_overflow() -> None:
    instruction = "a" * 261629 + "é"
    code, start, end = _diagnostic_for_clause(
        f'(:required (required_path) :instruction "{instruction}")'
    )
    assert code == "prompt_dependency_instruction_exceeds_byte_limit"
    assert 0 < start < end


def test_type_prompt_dependencies_accepts_relpath_name_and_field_projection() -> None:
    type_env = _type_env()
    report = type_env.resolve_type(
        "WorkReport", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    summary = type_env.resolve_type(
        "ImplementationSummary", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )

    typed = _typecheck_dependency_expr(
        "(:required (required_path result.report) :optional (optional_path))",
        value_env={"required_path": report, "optional_path": report, "result": summary},
    )

    assert typed.type_ref == PrimitiveTypeRef(name="Bool")


@pytest.mark.parametrize(
    ("operand", "value_env"),
    [
        ('"artifacts/work/report.md"', {}),
        ("text", {"text": PrimitiveTypeRef(name="String")}),
        ("true", {}),
        ("result.status", {}),
    ],
    ids=["path-looking-string", "string-name", "primitive", "record-string-field"],
)
def test_type_prompt_dependencies_rejects_non_relpath_before_inline_shape(
    operand: str,
    value_env: dict[str, object],
) -> None:
    if operand.startswith("result."):
        value_env = {
            "result": _type_env().resolve_type(
                "ImplementationSummary", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
            )
        }
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_dependency_expr(f"(:required ({operand}))", value_env=value_env)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_dependency_operand_type_invalid"


def test_type_prompt_dependencies_rejects_collection_record_and_extern_operands() -> None:
    type_env = _type_env()
    path_type = type_env.resolve_type(
        "WorkReport", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    record_type = type_env.resolve_type(
        "ImplementationSummary", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    invalid_types = {
        "optional_path": OptionalTypeRef(name="Optional[WorkReport]", item_type_ref=path_type),
        "path_list": ListTypeRef(name="List[WorkReport]", item_type_ref=path_type),
        "path_map": MapTypeRef(
            name="Map[String, WorkReport]",
            key_type_ref=PrimitiveTypeRef(name="String"),
            value_type_ref=path_type,
        ),
        "record_value": record_type,
    }
    for operand, type_ref in invalid_types.items():
        with pytest.raises(LispFrontendCompileError) as excinfo:
            _typecheck_dependency_expr(
                f"(:required ({operand}))", value_env={operand: type_ref}
            )
        assert excinfo.value.diagnostics[0].code == "prompt_dependency_operand_type_invalid"


def test_type_prompt_dependency_rejects_resolved_union_string_field_before_inline_shape() -> None:
    type_env = _type_env()
    union_type = type_env.resolve_type(
        "ImplementationState", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    blocked_variant = type_env.union_variant(
        union_type,
        "BLOCKED",
        span=CONSTANT_SPAN,
        form_path=("workflow-lisp", "test"),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_dependency_expr(
            "(:required (blocked.blocker_class))",
            value_env={"blocked": blocked_variant},
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "prompt_dependency_operand_type_invalid"
    assert diagnostic.span.start.offset > 0

    for operand in ("providers.execute", "prompts.execute"):
        with pytest.raises(LispFrontendCompileError) as excinfo:
            _typecheck_dependency_expr(f"(:required ({operand}))", value_env={})
        assert excinfo.value.diagnostics[0].code == "prompt_dependency_operand_type_invalid"


def test_inline_lowerable_prompt_dependencies_rejects_computation() -> None:
    path_type = _type_env().resolve_type(
        "WorkReport", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_dependency_expr(
            "(:required ((if ready first second)))",
            value_env={
                "ready": PrimitiveTypeRef(name="Bool"),
                "first": path_type,
                "second": path_type,
            },
        )

    assert excinfo.value.diagnostics[0].code == "prompt_dependency_operand_not_inline_lowerable"


def test_inline_lowerable_prompt_dependencies_allows_edges_but_rejects_effects() -> None:
    expr = _elaborate_dependency_expr("(:required (required_path))")
    dependency = expr.prompt_dependencies.required[0]
    path_type = _type_env().resolve_type(
        "WorkReport", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    edge = ProcedureCallEdge(callee_name="resolve-path")
    edge_summary = effect_summary(procedure_edges=(edge,))
    context = SimpleNamespace(
        type_env=_type_env(),
        value_env={},
        active_phase_scope=None,
        extern_environment=_extern_environment(),
    )

    def recurse_with(summary):
        def recurse(node):
            if node is expr.provider:
                return _typed(node, PrimitiveTypeRef(name="Provider"))
            if node is expr.prompt:
                return _typed(node, PrimitiveTypeRef(name="Prompt"))
            if node is dependency:
                return _typed(node, path_type, summary)
            raise AssertionError(f"unexpected node: {node!r}")

        return recurse

    accepted = typecheck_provider_result_expr(
        expr,
        context=context,
        recurse=recurse_with(edge_summary),
        typed_factory=lambda *, expr, type_ref, effect: _typed(expr, type_ref, effect),
    )
    assert edge in accepted.effect_summary.procedure_edges

    transitive = effect_summary(
        transitive_effects=(UsesProviderEffect(subject=("providers", "other")),),
        procedure_edges=(edge,),
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_provider_result_expr(
            expr,
            context=context,
            recurse=recurse_with(transitive),
            typed_factory=lambda *, expr, type_ref, effect: _typed(expr, type_ref, effect),
        )
    assert excinfo.value.diagnostics[0].code == "prompt_dependency_operand_not_inline_lowerable"


def test_inline_lowerable_prompt_dependencies_rejects_synthetic_nested_loop_operand() -> None:
    expr = _elaborate_dependency_expr("(:required (required_path))")
    path_type = _type_env().resolve_type(
        "WorkReport", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    nested_loop = LoopRecurExpr(
        max_iterations_expr=LiteralExpr(
            value=1, literal_kind="int", span=CONSTANT_SPAN, form_path=expr.form_path
        ),
        initial_state_expr=NameExpr(
            name="required_path", span=CONSTANT_SPAN, form_path=expr.form_path
        ),
        binding_name="state",
        body_expr=NameExpr(name="state", span=CONSTANT_SPAN, form_path=expr.form_path),
        span=CONSTANT_SPAN,
        form_path=expr.form_path,
    )
    expr = replace(
        expr,
        prompt_dependencies=replace(expr.prompt_dependencies, required=(nested_loop,)),
    )
    context = SimpleNamespace(
        type_env=_type_env(),
        value_env={},
        active_phase_scope=None,
        extern_environment=_extern_environment(),
    )

    def recurse(node):
        if node is expr.provider:
            return _typed(node, PrimitiveTypeRef(name="Provider"))
        if node is expr.prompt:
            return _typed(node, PrimitiveTypeRef(name="Prompt"))
        if node is nested_loop:
            return _typed(node, path_type)
        raise AssertionError(f"unexpected node: {node!r}")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_provider_result_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=lambda *, expr, type_ref, effect: _typed(expr, type_ref, effect),
        )
    assert excinfo.value.diagnostics[0].code == "prompt_dependency_operand_not_inline_lowerable"


def test_traversal_prompt_dependencies_visits_both_partitions_in_authored_order() -> None:
    expr = _elaborate_dependency_expr(
        "(:required (required_path) :optional (optional_path) :position append)"
    )
    children = iter_child_exprs(expr)
    assert [getattr(child, "name", None) for child in children] == [
        "providers.execute",
        "prompts.execute",
        "required_path",
        "optional_path",
    ]


def test_normalization_prompt_dependencies_rewrites_every_operand_and_preserves_policy() -> None:
    base = _elaborate_dependency_expr(
        '(:required (required_path) :optional (optional_path) :position append :instruction "Guide")'
    )
    helper_arg = NameExpr(name="value", span=CONSTANT_SPAN, form_path=base.form_path)
    helper_call = FunctionCallExpr(
        callee_name="identity-path",
        args=(NameExpr(name="required_path", span=CONSTANT_SPAN, form_path=base.form_path),),
        span=CONSTANT_SPAN,
        form_path=base.form_path,
    )
    function_def = FunctionDef(
        name="identity-path",
        params=(),
        return_type_name="WorkReport",
        body=_expression_syntax("value"),
        span=CONSTANT_SPAN,
        form_path=base.form_path,
    )
    path_type = _type_env().resolve_type(
        "WorkReport", span=CONSTANT_SPAN, form_path=("workflow-lisp", "test")
    )
    typed_function = TypedFunctionDef(
        definition=function_def,
        signature=FunctionSignature(
            name="identity-path",
            params=(("value", path_type),),
            return_type_ref=path_type,
            span=CONSTANT_SPAN,
            form_path=base.form_path,
        ),
        typed_body=_typed(helper_arg, path_type),
    )
    expr = replace(
        base,
        prompt_dependencies=replace(
            base.prompt_dependencies,
            required=(helper_call,),
            optional=(helper_call,),
        ),
    )

    normalized = normalize_function_calls(
        expr, typed_functions_by_name={"identity-path": typed_function}
    )

    assert all(
        isinstance(item, LetStarExpr)
        for item in (
            *normalized.prompt_dependencies.required,
            *normalized.prompt_dependencies.optional,
        )
    )
    assert normalized.prompt_dependencies.position == "append"
    assert normalized.prompt_dependencies.instruction == "Guide"


@pytest.mark.parametrize(
    "validator",
    [
        _validate_wcc_m2_expr_supported,
        _validate_wcc_m3_expr_supported,
        _validate_wcc_m4_expr_supported,
    ],
)
@pytest.mark.parametrize("partition", ["required", "optional"])
def test_wcc_routes_validate_each_prompt_dependency_partition(validator, partition: str) -> None:
    expr = _elaborate_dependency_expr("(:required (required_path) :optional (optional_path))")
    unsupported = FunctionCallExpr(
        callee_name="pure-helper",
        args=(),
        span=CONSTANT_SPAN,
        form_path=expr.form_path,
    )
    spec = expr.prompt_dependencies
    expr = replace(
        expr,
        prompt_dependencies=replace(
            spec,
            **{partition: (unsupported,)},
        ),
    )

    with pytest.raises(LispFrontendCompileError):
        validator(
            expr,
            workflow_name="generic-workflow",
            local_workflow_signatures={},
            workflow_ref_value_names=frozenset(),
        )


def test_mixed_prompt_dependency_fixture_preserves_aliases_fields_and_policy() -> None:
    result = compile_stage3_module(
        (FIXTURE_ROOT / "mixed.orc").relative_to(REPO_ROOT),
        entry_workflow="mixed",
        provider_externs=_manifest("providers.json"),
        prompt_externs=_manifest("prompts.json"),
        validate_shared=False,
        workspace_root=REPO_ROOT,
        lowering_route="legacy",
    )
    providers = [
        node
        for node in walk_expr(result.typed_workflows[0].typed_body.expr)
        if isinstance(node, ProviderResultExpr)
    ]
    assert len(providers) == 1
    spec = providers[0].prompt_dependencies
    assert [type(item).__name__ for item in spec.required] == ["NameExpr", "FieldAccessExpr"]
    assert [type(item).__name__ for item in spec.optional] == ["NameExpr", "FieldAccessExpr"]
    assert spec.position == "append"
    assert spec.instruction == "Use the supplied dependency set."


def test_loop_carried_relpath_fields_survive_frontend_and_wcc_m4_validation() -> None:
    result = compile_stage3_entrypoint(
        FIXTURE_ROOT / "procedure_loop.orc",
        source_roots=(FIXTURE_ROOT.parent,),
        entry_workflow="loop-carried",
        provider_externs=_manifest("providers.json"),
        prompt_externs=_manifest("prompts.json"),
        validate_shared=False,
        workspace_root=REPO_ROOT,
        lowering_route="legacy",
    )
    entry = next(
        workflow
        for workflow in result.entry_result.typed_workflows
        if workflow.definition.name.endswith("procedure_loop::loop-carried")
    )
    loop = next(
        node for node in walk_expr(entry.typed_body.expr) if isinstance(node, LoopRecurExpr)
    )
    provider = next(
        node for node in walk_expr(loop.body_expr) if isinstance(node, ProviderResultExpr)
    )
    spec = provider.prompt_dependencies

    assert isinstance(loop.initial_state_expr, NameExpr)
    assert loop.initial_state_expr.name == "inputs"
    assert [item.fields for item in spec.required] == [("required",)]
    assert [item.fields for item in spec.optional] == [("optional",)]
    assert all(item.base.name == loop.binding_name for item in (*spec.required, *spec.optional))
    assert spec.position == "append"
    assert spec.instruction == "Use the loop-carried dependency set."

    imported = result.compiled_results_by_name["provider_prompt_dependencies/mixed"]
    type_env = FrontendTypeEnvironment.from_module(imported.module)
    state_type = type_env.resolve_type(
        "DependencyInputs", span=loop.span, form_path=loop.form_path
    )
    typed_operands = [
        typecheck_expression(item, type_env=type_env, value_env={loop.binding_name: state_type})
        for item in (*spec.required, *spec.optional)
    ]
    assert all(
        isinstance(item.type_ref, PathTypeRef) and item.type_ref.definition.kind == "relpath"
        for item in typed_operands
    )
    assert UsesProviderEffect(subject=("providers", "execute")) in (
        entry.typed_body.effect_summary.direct_effects
    )

    _validate_wcc_m4_expr_supported(
        loop,
        workflow_name=entry.definition.name,
        local_workflow_signatures={},
        workflow_ref_value_names=frozenset(),
    )


def test_imported_bound_procedure_specialization_preserves_prompt_dependency_contract() -> None:
    result = compile_stage3_entrypoint(
        FIXTURE_ROOT / "procedure_loop.orc",
        source_roots=(FIXTURE_ROOT.parent,),
        entry_workflow="procedure-loop",
        provider_externs=_manifest("providers.json"),
        prompt_externs=_manifest("prompts.json"),
        validate_shared=False,
        workspace_root=REPO_ROOT,
        lowering_route="legacy",
    )
    entry_result = result.entry_result
    imported_result = result.compiled_results_by_name["provider_prompt_dependencies/mixed"]
    imported = next(
        item
        for item in imported_result.typed_procedures
        if item.definition.name.endswith("mixed::invoke-provider")
    )
    entry = next(
        workflow
        for workflow in entry_result.typed_workflows
        if workflow.definition.name.endswith("procedure_loop::procedure-loop")
    )
    calls = [
        node
        for node in walk_expr(entry.typed_body.expr)
        if isinstance(node, ProcedureCallExpr)
    ]
    imported_call = next(call for call in calls if call.callee_name == imported.definition.name)
    assert isinstance(imported_call.args[0], FieldAccessExpr)
    assert isinstance(imported_call.args[1], FieldAccessExpr)

    specialized = specialize_typed_procedure(
        imported,
        value_bindings={"required": imported_call.args[0]},
        remaining_params=(imported.signature.params[1],),
        workflow_path=FIXTURE_ROOT / "mixed.orc",
        type_env=FrontendTypeEnvironment.from_module(imported_result.module),
        typed_procedures_by_name={
            item.definition.name: item
            for compile_result in result.compiled_results_by_name.values()
            for item in compile_result.typed_procedures
        },
        specialized_name="%test.invoke-provider.required-bound",
    )
    provider = next(
        node
        for node in walk_expr(specialized.typed_body.expr)
        if isinstance(node, ProviderResultExpr)
    )
    spec = provider.prompt_dependencies
    assert [item.name for item in spec.required] == ["required"]
    assert [item.name for item in spec.optional] == ["optional"]
    assert spec.position == "append"
    assert spec.instruction == "Use the supplied dependency set."
    assert tuple(specialized.specialization.value_bindings) == ("required",)
    assert specialized.specialization.value_bindings["required"] == imported_call.args[0]
    assert specialized.specialization.bound_param_types["required"].definition.kind == "relpath"
    assert UsesProviderEffect(subject=("providers", "execute")) in (
        specialized.transitive_effect_summary.transitive_effects
    )

    discovered = [
        node
        for node in walk_expr(specialized.typed_body.expr)
        if isinstance(node, (NameExpr, FieldAccessExpr))
    ]
    assert spec.required[0] in discovered
    assert spec.optional[0] in discovered


TASK2_PRODUCTION_PATHS = (
    "orchestrator/workflow_lisp/expressions.py",
    "orchestrator/workflow_lisp/expression_traversal.py",
    "orchestrator/workflow_lisp/typecheck_effects.py",
    "orchestrator/workflow_lisp/functions.py",
    "orchestrator/workflow_lisp/procedure_specialization.py",
    "orchestrator/workflow_lisp/workflow_refs.py",
    "orchestrator/workflow_lisp/wcc/route.py",
)
FORBIDDEN_IDENTITIES = re.compile(
    r"verified[_-]iteration[_-]drain|generic[_-]run[_-]watchdog|"
    r"tracked[_-]plan[_-]phase|remaining[_-]neurips[_-]migration[_-]experiment|"
    r"codex|claude|anthropic|openai",
    re.IGNORECASE,
)


def _added_source_lines(patch: str) -> tuple[str, ...]:
    lines: list[str] = []
    in_header = False
    saw_old_header = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            in_header = True
            saw_old_header = False
            continue
        if in_header and line.startswith("--- "):
            saw_old_header = True
            continue
        if in_header and saw_old_header and line.startswith("+++ "):
            in_header = False
            saw_old_header = False
            continue
        if in_header:
            continue
        if line.startswith("+"):
            lines.append(line[1:])
    if in_header:
        raise ValueError("incomplete patch header")
    return tuple(lines)


def test_prompt_dependency_generic_mechanism_has_no_concrete_identity_branch() -> None:
    patch = subprocess.run(
        ["git", "diff", "--unified=0", "451765a2", "--", *TASK2_PRODUCTION_PATHS],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert not any(FORBIDDEN_IDENTITIES.search(line) for line in _added_source_lines(patch))


def test_prompt_dependency_genericity_added_line_extractor_rejects_leading_plus_identity() -> None:
    patch = "\n".join(
        [
            "diff --git a/path b/path",
            "--- a/path",
            "+++ b/path",
            "@@ -0,0 +1 @@",
            "+codex = 1",
        ]
    )
    added = _added_source_lines(patch)
    assert added == ("codex = 1",)
    assert any(FORBIDDEN_IDENTITIES.search(line) for line in added)


def test_keyword_free_provider_result_matches_preimplementation_dual_route_baseline() -> None:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert expected["schema"] == "provider_prompt_dependencies_keyword_free_baseline.v1"
    assert expected["implementation_base_commit"] == "451765a2ebd374111d2cbeab0969cec4830717fb"
    assert expected["routes"] == {
        "classic_direct": _route_artifacts("legacy"),
        "wcc_schema_2": _route_artifacts("wcc_m4"),
    }
