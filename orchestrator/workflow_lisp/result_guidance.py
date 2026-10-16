"""Immutable authored metadata for typed Workflow Lisp result occurrences."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .compiler_session import CompilerSession
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .syntax import (
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    syntax_head,
    syntax_identifier,
)


from orchestrator.workflow.pure_expr import (
    PURE_EXPR_SCHEMA_VERSION, PURE_EXPR_OPERATOR_CATALOG,
    PureExprEvaluationError, evaluate_pure_expr, validate_pure_expr_payload,
)
from .diagnostics import records_defect_provenance
from .reader import SourceReadTrace

if TYPE_CHECKING:
    from .type_env import FrontendTypeEnvironment, TypeRef


_LEXICAL_LOCAL_BINDING = object()

@dataclass(frozen=True)
class ResultGuidance:
    """Optional provider-facing guidance attached to one result occurrence."""

    description: str | None = None
    format_hint: str | None = None
    example_expr: SyntaxNode | None = None


@dataclass(frozen=True)
class ReturnSpec:
    """One return type occurrence plus its optional authored guidance."""

    type_name: str
    guidance: ResultGuidance | None = field(compare=False)
    span: SourceSpan = field(compare=False)


def normalized_result_guidance_payload(
    guidance: ResultGuidance | None,
    *,
    expected_type=None,
    type_env=None,
    workspace: Path | None = None,
    source_read_trace=None,
) -> dict[str, Any] | None:
    """Project authored guidance once into the canonical JSON-native wire payload."""

    if guidance is None:
        return None
    payload: dict[str, Any] = {}
    if guidance.description is not None:
        payload["description"] = guidance.description
    if guidance.format_hint is not None:
        payload["format_hint"] = guidance.format_hint
    if guidance.example_expr is not None:
        if expected_type is None or type_env is None:
            raise TypeError("typed result guidance examples require an expected type and type environment")
        payload["example"] = validate_result_guidance_example(
            guidance,
            expected_type=expected_type,
            type_env=type_env,
            workspace=workspace,
            source_read_trace=source_read_trace,
        )
    return payload or None


def parse_return_spec(
    raw_return: object,
    *,
    form_path: tuple[str, ...],
    label: str,
) -> ReturnSpec:
    """Parse a plain type symbol or return-position ``(result T ...)`` form."""

    return_identifier = syntax_identifier(raw_return)
    if return_identifier is not None:
        return ReturnSpec(return_identifier.resolved_name, None, return_identifier.span)
    if not isinstance(raw_return, SyntaxList):
        _raise_guidance_error(
            f"{label} must be a symbol or `(result Type ...)`",
            node=raw_return,
            form_path=form_path,
        )
    head = syntax_head(raw_return)
    if head is None or head.resolved_name != "result" or len(raw_return.items) < 2:
        _raise_guidance_error(
            f"{label} must be a symbol or `(result Type ...)`",
            node=raw_return,
            form_path=form_path,
        )
    type_identifier = syntax_identifier(raw_return.items[1])
    if type_identifier is None:
        _raise_guidance_error(
            "`result` type must be a symbol",
            node=raw_return.items[1],
            form_path=form_path,
        )
    guidance = parse_result_guidance(
        raw_return.items[2:],
        form_path=form_path,
        label="`result`",
    )
    return ReturnSpec(type_identifier.resolved_name, guidance, raw_return.span)


def parse_result_guidance(
    items: tuple[object, ...],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> ResultGuidance | None:
    """Parse the closed guidance-key set without validating example semantics."""

    if not items:
        return None
    if len(items) % 2 != 0:
        _raise_guidance_error(
            f"{label} guidance requires keyword/value pairs",
            node=items[-1],
            form_path=form_path,
        )
    values: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_guidance_error(
                f"{label} guidance entries must start with keywords",
                node=keyword_node,
                form_path=form_path,
            )
        if keyword_node.value not in {":description", ":format-hint", ":example"}:
            _raise_guidance_error(
                f"{label} guidance has unknown key `{keyword_node.value}`",
                node=keyword_node,
                form_path=form_path,
            )
        if keyword_node.value in values:
            _raise_guidance_error(
                f"{label} guidance duplicates key `{keyword_node.value}`",
                node=keyword_node,
                form_path=form_path,
            )
        values[keyword_node.value] = value_node

    description = _parse_nonempty_string(
        values.get(":description"), key=":description", form_path=form_path, label=label
    )
    format_hint = _parse_nonempty_string(
        values.get(":format-hint"), key=":format-hint", form_path=form_path, label=label
    )
    example_node = values.get(":example")
    example_expr = None
    if example_node is not None:
        example_expr = SyntaxNode(
            datum=example_node,
            span=example_node.span,
            module_path=example_node.module_path,
            form_path=form_path,
        )
    return ResultGuidance(description, format_hint, example_expr)


def _parse_nonempty_string(
    node: object | None,
    *,
    key: str,
    form_path: tuple[str, ...],
    label: str,
) -> str | None:
    if node is None:
        return None
    if not isinstance(node, SyntaxString) or not node.value.strip():
        _raise_guidance_error(
            f"{label} guidance `{key}` must be a non-empty string",
            node=node,
            form_path=form_path,
        )
    return node.value


def _raise_guidance_error(
    message: str,
    *,
    node: object,
    form_path: tuple[str, ...],
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="result_guidance_invalid",
                message=message,
                span=node.span,
                form_path=form_path,
                expansion_stack=getattr(node, "expansion_stack", ()),
            ),
        )
    )


def validate_result_guidance_example(
    guidance: ResultGuidance | None,
    *,
    expected_type,
    type_env,
    workspace: Path | None = None,
    source_read_trace=None,
    compiler_session: CompilerSession | None = None,
) -> Any | None:
    """Elaborate, typecheck, evaluate, and schema-check one authored example."""

    compiler_session = compiler_session or CompilerSession()
    if guidance is None or guidance.example_expr is None:
        return None
    example_node = guidance.example_expr
    from .type_env import PrimitiveTypeRef

    if expected_type == PrimitiveTypeRef(name="Value"):
        _raise_example_diagnostic(
            "value_guidance_example_unsupported",
            (
                "result guidance examples are unsupported for `Value` "
                "without a checked Value constant surface"
            ),
            example_node=example_node,
        )
    try:
        from .expressions import elaborate_expression

        expr = elaborate_expression(
            example_node,
            bound_names=frozenset(),
            guidance_example=True,
            session_state=compiler_session.elaboration,
        )
        expr = _contextualize_path_literals(expr, expected_type=expected_type)
    except (LispFrontendCompileError, TypeError, ValueError) as exc:
        _raise_example_diagnostic(
            "result_guidance_example_not_constant",
            "result guidance example must be an effect-free compile-time constant",
            example_node=example_node,
            cause=exc,
        )

    from .effects import EMPTY_EFFECT_SUMMARY
    from .expression_traversal import walk_expr
    from .expressions import RunRefExpr
    from .expression_traversal import is_pure_projection_expr
    from .type_env import OptionalTypeRef, type_refs_compatible
    from .typecheck import typecheck_expression
    from .typecheck_context import raise_run_ref_placement_invalid

    direct_run_ref = next(
        (candidate for candidate in walk_expr(expr) if isinstance(candidate, RunRefExpr)),
        None,
    )
    if direct_run_ref is not None:
        raise_run_ref_placement_invalid(
            direct_run_ref,
            reason="is not permitted in a result-guidance example",
        )

    if not is_pure_projection_expr(expr, allow_generated_relpath_seed=True):
        _raise_example_diagnostic(
            "result_guidance_example_not_constant",
            "result guidance example must be an effect-free compile-time constant",
            example_node=example_node,
        )
    try:
        typed = typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
            compiler_session=compiler_session,
        )
    except LispFrontendCompileError as exc:
        code = exc.diagnostics[0].code if exc.diagnostics else ""
        if code in {"name_unknown", "effect_not_permitted"}:
            _raise_example_diagnostic(
                "result_guidance_example_not_constant",
                "result guidance example must be an effect-free compile-time constant",
                example_node=example_node,
                cause=exc,
            )
        _raise_example_type_mismatch(expected_type, example_node=example_node, cause=exc)
    if typed.effect_summary != EMPTY_EFFECT_SUMMARY:
        from .effects import effect_summary_contains_runs_ref

        if effect_summary_contains_runs_ref(typed.effect_summary):
            raise_run_ref_placement_invalid(
                typed.expr,
                reason="is not permitted in a result-guidance example",
                effect_summary=typed.effect_summary,
            )
        _raise_example_diagnostic(
            "result_guidance_example_not_constant",
            "result guidance example must be an effect-free compile-time constant",
            example_node=example_node,
        )

    compatible = type_refs_compatible(expected_type, typed.type_ref)
    if isinstance(expected_type, OptionalTypeRef):
        compatible = compatible or type_refs_compatible(expected_type.item_type_ref, typed.type_ref)
    if not compatible:
        _raise_example_type_mismatch(expected_type, example_node=example_node)

    try:
        value = evaluate_closed_pure_expr(
            typed.expr,
            result_type=typed.type_ref,
            type_env=type_env,
            source_read_trace=source_read_trace,
        )
    except (LispFrontendCompileError, TypeError, ValueError) as exc:
        _raise_example_type_mismatch(expected_type, example_node=example_node, cause=exc)
    return validate_typed_guidance_constant(
        value,
        expected_type=expected_type,
        type_env=type_env,
        example_node=example_node,
        workspace=workspace,
        source_read_trace=source_read_trace,
    )


def validate_typed_guidance_constant(
    value: Any,
    *,
    expected_type,
    type_env,
    example_node: SyntaxNode,
    workspace: Path | None = None,
    source_read_trace=None,
) -> Any:
    """Validate JSON-native constant data through pure and output schemas."""

    from orchestrator.contracts.output_contract import OutputContractError

    try:
        normalized = evaluate_typed_constant(
            value,
            result_type=expected_type,
            type_env=type_env,
            source_read_trace=source_read_trace,
        )
        _validate_against_structured_result_contract(
            normalized,
            expected_type=expected_type,
            workspace=workspace or Path.cwd(),
            example_node=example_node,
        )
    except (LispFrontendCompileError, OutputContractError, TypeError, ValueError) as exc:
        _raise_example_type_mismatch(expected_type, example_node=example_node, cause=exc)
    return normalized


def validate_module_result_guidance(
    module,
    *,
    type_env,
    function_defs: tuple[object, ...] = (),
    procedure_defs: tuple[object, ...] = (),
    workflow_defs: tuple[object, ...] = (),
    workspace: Path | None = None,
    source_read_trace=None,
    compiler_session: CompilerSession | None = None,
) -> None:
    """Validate all definition and callable guidance visible in one module."""

    from .definitions import RecordDef, SchemaDef, UnionDef

    compiler_session = compiler_session or CompilerSession()

    for definition in (*module.schemas, *module.definitions):
        if isinstance(definition, RecordDef):
            field_groups = (definition.fields,)
        elif isinstance(definition, UnionDef):
            field_groups = tuple(variant.fields for variant in definition.variants)
        elif isinstance(definition, SchemaDef):
            field_groups = (definition.members,)
        else:
            continue
        for fields in field_groups:
            for field_def in fields:
                guidance = getattr(field_def, "guidance", None)
                if guidance is None or guidance.example_expr is None:
                    continue
                field_type = type_env.resolve_type(
                    field_def.type_name,
                    span=field_def.span,
                    form_path=guidance.example_expr.form_path,
                )
                validate_result_guidance_example(
                    guidance,
                    expected_type=field_type,
                    type_env=type_env,
                    workspace=workspace,
                    source_read_trace=source_read_trace,
                    compiler_session=compiler_session,
                )

    for definition in (*function_defs, *procedure_defs, *workflow_defs):
        return_spec = getattr(definition, "return_spec", None)
        if (
            return_spec is None
            or return_spec.guidance is None
            or return_spec.guidance.example_expr is None
        ):
            continue
        return_type = type_env.resolve_type(
            return_spec.type_name,
            span=return_spec.span,
            form_path=return_spec.guidance.example_expr.form_path,
            local_type_params=frozenset(
                param.name for param in getattr(definition, "type_params", ())
            ),
        )
        if type(return_type).__name__ == "TypeParamRef":
            continue
        validate_result_guidance_example(
            return_spec.guidance,
            expected_type=return_type,
            type_env=type_env,
            workspace=workspace,
            source_read_trace=source_read_trace,
            compiler_session=compiler_session,
        )


def _contextualize_path_literals(expr, *, expected_type):
    """Reify authored strings as typed path constants under declared context."""

    from .expressions import (
        GeneratedRelpathSeedExpr,
        IfExpr,
        LiteralExpr,
        RecordExpr,
        UnionVariantExpr,
    )
    from .type_env import OptionalTypeRef, PathTypeRef, RecordTypeRef, UnionTypeRef

    if isinstance(expected_type, OptionalTypeRef):
        return _contextualize_path_literals(expr, expected_type=expected_type.item_type_ref)
    if isinstance(expected_type, PathTypeRef) and isinstance(expr, LiteralExpr) and expr.literal_kind == "string":
        return GeneratedRelpathSeedExpr(
            target_type_ref=expected_type,
            literal_path=expr.value,
            seed_role="result-guidance-example",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expected_type, RecordTypeRef) and isinstance(expr, RecordExpr):
        return replace(
            expr,
            fields=tuple(
                (
                    name,
                    _contextualize_path_literals(
                        value,
                        expected_type=expected_type.field_types.get(name),
                    ),
                )
                if name in expected_type.field_types
                else (name, value)
                for name, value in expr.fields
            ),
        )
    if isinstance(expected_type, UnionTypeRef) and isinstance(expr, UnionVariantExpr):
        variant_fields = expected_type.variant_field_types.get(expr.variant_name, {})
        return replace(
            expr,
            fields=tuple(
                (
                    name,
                    _contextualize_path_literals(
                        value,
                        expected_type=variant_fields.get(name),
                    ),
                )
                if name in variant_fields
                else (name, value)
                for name, value in expr.fields
            ),
        )
    if isinstance(expr, IfExpr):
        return replace(
            expr,
            then_expr=_contextualize_path_literals(expr.then_expr, expected_type=expected_type),
            else_expr=_contextualize_path_literals(expr.else_expr, expected_type=expected_type),
        )
    return expr


def _validate_against_structured_result_contract(
    value: Any,
    *,
    expected_type,
    workspace: Path,
    example_node: SyntaxNode,
) -> None:
    from orchestrator.contracts.output_contract import validate_contract_value

    from .contracts import derive_structured_result_contract

    contract = derive_structured_result_contract(
        expected_type,
        workflow_name="result-guidance-example",
        step_id="result-guidance-example__value",
        span=example_node.span,
        form_path=example_node.form_path,
    )
    payload = _without_existence_requirements(contract.payload)
    if contract.contract_kind == "output_bundle":
        for field_spec in payload["fields"]:
            found, field_value = _resolve_json_pointer(value, field_spec["json_pointer"])
            if not found:
                raise ValueError(f"missing example field at {field_spec['json_pointer']!r}")
            validate_contract_value(field_value, dict(field_spec), workspace=workspace)
        return

    discriminant = payload["discriminant"]
    found, variant_name = _resolve_json_pointer(value, discriminant["json_pointer"])
    if not found:
        raise ValueError("union example is missing its discriminant")
    validate_contract_value(variant_name, dict(discriminant), workspace=workspace)
    for field_spec in payload.get("shared_fields", ()):
        found, field_value = _resolve_json_pointer(value, field_spec["json_pointer"])
        if not found:
            raise ValueError(f"missing shared example field at {field_spec['json_pointer']!r}")
        validate_contract_value(field_value, dict(field_spec), workspace=workspace)
    variant = payload["variants"].get(variant_name)
    if variant is None:
        raise ValueError(f"unknown example variant {variant_name!r}")
    for field_spec in variant.get("fields", ()):
        found, field_value = _resolve_json_pointer(value, field_spec["json_pointer"])
        if not found:
            raise ValueError(f"missing variant example field at {field_spec['json_pointer']!r}")
        validate_contract_value(field_value, dict(field_spec), workspace=workspace)


def _without_existence_requirements(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: False if key == "must_exist_target" else _without_existence_requirements(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_without_existence_requirements(item) for item in value]
    return value


def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or token not in current:
            return False, None
        current = current[token]
    return True, current


def _raise_example_type_mismatch(expected_type, *, example_node: SyntaxNode, cause=None) -> None:
    _raise_example_diagnostic(
        "result_guidance_example_type_mismatch",
        f"result guidance example does not match declared type `{expected_type.name}`",
        example_node=example_node,
        cause=cause,
    )


def _raise_example_diagnostic(
    code: str,
    message: str,
    *,
    example_node: SyntaxNode,
    cause: object | None = None,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=example_node.span,
                form_path=example_node.form_path,
                expansion_stack=getattr(example_node.datum, "expansion_stack", ()),
            ),
        )
    ) from cause


def evaluate_closed_pure_expr(
    expr: Any,
    *,
    result_type: TypeRef,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> Any:
    """Evaluate one typechecked guidance constant with only lexical bindings."""
    from .type_env import PrimitiveTypeRef


    diagnostic_sources: dict[int, tuple[str, str, int, int]] = {}
    payload_expr, inferred_type = _payload_expr(
        expr,
        type_env=type_env,
        source_read_trace=source_read_trace,
        lexical_bindings={},
        lexical_types={},
        diagnostic_sources=diagnostic_sources,
        diagnostic_root_id=id(expr),
    )
    if not _pure_projection_type_equivalent(
        inferred_type,
        result_type,
        type_env=type_env,
        source_read_trace=source_read_trace,
    ) and not (
        isinstance(result_type, PrimitiveTypeRef)
        and result_type.allowed_values
        and payload_expr.get("kind") == "literal"
        and isinstance(payload_expr.get("type"), dict)
        and payload_expr["type"].get("kind") == "enum"
    ):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="pure_expr_operand_type_mismatch",
                    message="pure projection result type did not match the lowered contract",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=getattr(expr, "expansion_stack", ()),
                ),
            )
        )
    payload = {
        "pure_expr_schema_version": _required_pure_expr_schema_version(
            expr,
            payload_expr=payload_expr,
        ),
        "result_type": _type_descriptor(
            result_type,
            type_env=type_env,
            source_read_trace=source_read_trace,
        ),
        "bindings": {},
        "expr": payload_expr,
    }
    try:
        validate_pure_expr_payload(payload, diagnostic_sources=diagnostic_sources)
    except PureExprEvaluationError as exc:
        _raise_pure_expr_error(
            exc,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
        )
    return evaluate_pure_expr(payload, resolved_bindings={})


def evaluate_typed_constant(
    value: Any,
    *,
    result_type: TypeRef,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> Any:
    """Normalize JSON-native compile-time data through the shared evaluator."""

    descriptor = _type_descriptor(
        result_type,
        type_env=type_env,
        source_read_trace=source_read_trace,
    )
    return evaluate_pure_expr(
        {
            "pure_expr_schema_version": PURE_EXPR_SCHEMA_VERSION,
            "result_type": descriptor,
            "bindings": {},
            "expr": {"kind": "literal", "type": descriptor, "value": value},
        },
        resolved_bindings={},
    )


def _required_pure_expr_schema_version(
    expr: Any,
    *,
    payload_expr: Mapping[str, Any] | None = None,
) -> int:
    from .expressions import CompilerListNonemptyHeadExpr, ListExpr, ListMapExpr, PathJoinUnderExpr, PureOpExpr
    from .expression_traversal import walk_expr

    if payload_expr is not None and _payload_requires_schema_3(payload_expr):
        return 3
    if payload_expr is not None and _payload_requires_schema_2(payload_expr):
        return 2
    for node in walk_expr(expr):
        if isinstance(
            node,
            (
                CompilerListNonemptyHeadExpr,
                ListExpr,
                ListMapExpr,
                PathJoinUnderExpr,
            ),
        ):
            return 2
        if isinstance(node, PureOpExpr):
            spec = PURE_EXPR_OPERATOR_CATALOG.get(node.operator)
            if spec is not None and spec.min_schema_version >= 2:
                return 2
    return PURE_EXPR_SCHEMA_VERSION


def _payload_requires_schema_2(node: Any) -> bool:
    if isinstance(node, Mapping):
        kind = node.get("kind")
        if kind in {"list", "list_map", "path_join_under", "list_nonempty_head"}:
            return True
        if kind == "op":
            spec = PURE_EXPR_OPERATOR_CATALOG.get(node.get("operator"))
            if spec is not None and spec.min_schema_version >= 2:
                return True
        return any(_payload_requires_schema_2(value) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_payload_requires_schema_2(value) for value in node)
    return False


def _payload_requires_schema_3(node: Any) -> bool:
    if isinstance(node, Mapping):
        if node.get("kind") == "let":
            return True
        return any(_payload_requires_schema_3(value) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_payload_requires_schema_3(value) for value in node)
    return False


def _pure_projection_type_equivalent(
    inferred_type: TypeRef,
    result_type: TypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> bool:
    from .type_env import PrimitiveTypeRef

    if _type_descriptor(
        inferred_type,
        type_env=type_env,
        source_read_trace=source_read_trace,
    ) == _type_descriptor(
        result_type,
        type_env=type_env,
        source_read_trace=source_read_trace,
    ):
        return True
    if (
        isinstance(inferred_type, PrimitiveTypeRef)
        and isinstance(result_type, PrimitiveTypeRef)
        and _short_type_name(inferred_type.name) == _short_type_name(result_type.name)
    ):
        if not result_type.allowed_values:
            return not inferred_type.allowed_values
        if not inferred_type.allowed_values:
            return True
        return set(inferred_type.allowed_values) == set(result_type.allowed_values)
    inferred_definition = getattr(inferred_type, "definition", None)
    result_definition = getattr(result_type, "definition", None)
    if (
        inferred_definition is not None
        and result_definition is not None
        and type(inferred_type) is type(result_type)
        and getattr(inferred_definition, "name", None) == getattr(result_definition, "name", None)
        and getattr(getattr(inferred_definition, "span", None), "start", None) is not None
        and getattr(getattr(result_definition, "span", None), "start", None) is not None
        and inferred_definition.span.start.path == result_definition.span.start.path
    ):
        return True
    return False


def _short_type_name(name: str) -> str:
    return name.rsplit("::", 1)[-1].rsplit("/", 1)[-1]


def _payload_expr(
    expr: Any,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None,
    lexical_bindings: Mapping[str, Any],
    lexical_types: Mapping[str, TypeRef],
    diagnostic_sources: dict[int, tuple[str, str, int, int]] | None = None,
    diagnostic_root_id: int | None = None,
) -> tuple[dict[str, Any], TypeRef]:
    payload_expr, inferred_type = _payload_expr_impl(
        expr,
        type_env=type_env, source_read_trace=source_read_trace,
        lexical_bindings=lexical_bindings,
        lexical_types=lexical_types,
        diagnostic_sources=diagnostic_sources,
        diagnostic_root_id=diagnostic_root_id,
    )
    if diagnostic_sources is not None and id(expr) != diagnostic_root_id:
        start = getattr(getattr(getattr(expr, "span", None), "start", None), "line", None)
        position = getattr(getattr(expr, "span", None), "start", None)
        path = getattr(position, "path", None)
        column = getattr(position, "column", None)
        if isinstance(path, str) and isinstance(start, int) and isinstance(column, int):
            diagnostic_sources.setdefault(
                id(payload_expr),
                (type(expr).__name__, path, start, column),
            )
    return payload_expr, inferred_type


@records_defect_provenance("lowering")
def _payload_expr_impl(
    expr: Any,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None,
    lexical_bindings: Mapping[str, Any],
    lexical_types: Mapping[str, TypeRef],
    diagnostic_sources: dict[int, tuple[str, str, int, int]] | None,
    diagnostic_root_id: int | None,
) -> tuple[dict[str, Any], TypeRef]:
    from .expressions import CompilerListNonemptyHeadExpr, EnumMemberExpr, FieldAccessExpr, GeneratedRelpathSeedExpr, IfExpr, LetStarExpr, ListExpr, ListMapExpr, LiteralExpr, NameExpr, PathJoinUnderExpr, PureOpExpr, RecordExpr, RecordUpdateExpr, UnionVariantExpr, UnionVariantTagExpr
    from .type_env import ListTypeRef

    if isinstance(expr, LetStarExpr):
        child_bindings = dict(lexical_bindings)
        child_types = dict(lexical_types)
        payload_bindings: list[dict[str, Any]] = []
        for binding_name, binding_expr in expr.bindings:
            value_node, binding_type = _payload_expr(
                binding_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=child_bindings,
                lexical_types=child_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )
            payload_bindings.append(
                {
                    "name": binding_name,
                    "type": _type_descriptor(
                        binding_type,
                        type_env=type_env,
                        source_read_trace=source_read_trace,
                    ),
                    "value": value_node,
                }
            )
            child_bindings[binding_name] = _LEXICAL_LOCAL_BINDING
            child_types[binding_name] = binding_type
        body_node, body_type = _payload_expr(
            expr.body,
            type_env=type_env, source_read_trace=source_read_trace,
            lexical_bindings=child_bindings,
            lexical_types=child_types,
            diagnostic_sources=diagnostic_sources,
            diagnostic_root_id=diagnostic_root_id,
        )
        return {
            "kind": "let",
            "bindings": payload_bindings,
            "body": body_node,
        }, body_type
    if isinstance(expr, NameExpr):
        if expr.name in lexical_bindings:
            if lexical_bindings[expr.name] is _LEXICAL_LOCAL_BINDING:
                type_ref = lexical_types[expr.name]
                return {"kind": "binding", "name": expr.name}, type_ref
            return _payload_expr(
                lexical_bindings[expr.name],
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )
        raise ValueError(f"closed pure expression has unbound name `{expr.name}`")
    if isinstance(expr, LiteralExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "literal",
            "type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "value": expr.value,
        }, type_ref
    if isinstance(expr, GeneratedRelpathSeedExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "literal",
            "type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "value": expr.literal_path,
        }, type_ref
    if isinstance(expr, EnumMemberExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "literal",
            "type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "value": expr.member_name,
        }, type_ref
    if isinstance(expr, UnionVariantTagExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "literal",
            "type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "value": expr.variant_name,
        }, type_ref
    if isinstance(expr, FieldAccessExpr):
        if expr.base.name in lexical_bindings:
            bound = lexical_bindings[expr.base.name]
            if bound is _LEXICAL_LOCAL_BINDING:
                base_node: Any = {"kind": "binding", "name": expr.base.name}
                base_type = lexical_types[expr.base.name]
            else:
                base_node, base_type = _payload_expr(
                    bound,
                    type_env=type_env, source_read_trace=source_read_trace,
                    lexical_bindings=lexical_bindings,
                    lexical_types=lexical_types,
                    diagnostic_sources=diagnostic_sources,
                    diagnostic_root_id=diagnostic_root_id,
                )
        else:
            base_node, base_type = _payload_expr(
                expr.base,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )
        node = base_node
        type_ref = _infer_expr_type(
            expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types
        )
        current_type = base_type
        for field_name in expr.fields:
            node = {"kind": "field_access", "base": node, "field": field_name}
            current_type = _field_type(
                current_type, field_name, type_env=type_env
            )
        return node, type_ref
    if isinstance(expr, RecordExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "record",
            "type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "fields": [
                {
                    "name": field_name,
                    "value": _payload_expr(
                        field_expr,
                        type_env=type_env, source_read_trace=source_read_trace,
                        lexical_bindings=lexical_bindings,
                        lexical_types=lexical_types,
                        diagnostic_sources=diagnostic_sources,
                        diagnostic_root_id=diagnostic_root_id,
                    )[0],
                }
                for field_name, field_expr in expr.fields
            ],
        }, type_ref
    if isinstance(expr, UnionVariantExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "union",
            "type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "variant": expr.variant_name,
            "fields": [
                {
                    "name": field_name,
                    "value": _payload_expr(
                        field_expr,
                        type_env=type_env, source_read_trace=source_read_trace,
                        lexical_bindings=lexical_bindings,
                        lexical_types=lexical_types,
                        diagnostic_sources=diagnostic_sources,
                        diagnostic_root_id=diagnostic_root_id,
                    )[0],
                }
                for field_name, field_expr in expr.fields
            ],
        }, type_ref
    if isinstance(expr, RecordUpdateExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "record_update",
            "record_type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "base": _payload_expr(
                expr.base_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )[0],
            "fields": [
                {
                    "name": field_name,
                    "value": _payload_expr(
                        field_expr,
                        type_env=type_env, source_read_trace=source_read_trace,
                        lexical_bindings=lexical_bindings,
                        lexical_types=lexical_types,
                        diagnostic_sources=diagnostic_sources,
                        diagnostic_root_id=diagnostic_root_id,
                    )[0],
                }
                for field_name, field_expr in expr.overrides
            ],
        }, type_ref
    if isinstance(expr, PureOpExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "op",
            "operator": expr.operator,
            "args": [
                _payload_expr(
                    arg,
                    type_env=type_env, source_read_trace=source_read_trace,
                    lexical_bindings=lexical_bindings,
                    lexical_types=lexical_types,
                    diagnostic_sources=diagnostic_sources,
                    diagnostic_root_id=diagnostic_root_id,
                )[0]
                for arg in expr.args
            ],
        }, type_ref
    if isinstance(expr, ListExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        assert isinstance(type_ref, ListTypeRef)
        return {
            "kind": "list",
            "element_type": _type_descriptor(
                type_ref.item_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "items": [
                _payload_expr(
                    item,
                    type_env=type_env, source_read_trace=source_read_trace,
                    lexical_bindings=lexical_bindings,
                    lexical_types=lexical_types,
                    diagnostic_sources=diagnostic_sources,
                    diagnostic_root_id=diagnostic_root_id,
                )[0]
                for item in expr.items
            ],
        }, type_ref
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        source_node, source_type = _payload_expr(
            expr.source_expr,
            type_env=type_env, source_read_trace=source_read_trace,
            lexical_bindings=lexical_bindings,
            lexical_types=lexical_types,
            diagnostic_sources=diagnostic_sources,
            diagnostic_root_id=diagnostic_root_id,
        )
        if (
            not isinstance(source_type, ListTypeRef)
            or not _pure_projection_type_equivalent(
                source_type.item_type_ref,
                expr.element_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            )
        ):
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="list_nonempty_invariant_broken",
                        message=(
                            "compiler-owned nonempty head source does not "
                            "match its exact element type"
                        ),
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                )
            )
        return {
            "kind": "list_nonempty_head",
            "source": source_node,
            "element_type": _type_descriptor(
                expr.element_type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "compiler_owned": True,
            "invariant_diagnostic": "list_nonempty_invariant_broken",
        }, expr.element_type_ref
    if isinstance(expr, ListMapExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        assert isinstance(type_ref, ListTypeRef)
        source_node, source_type = _payload_expr(
            expr.source_expr,
            type_env=type_env, source_read_trace=source_read_trace,
            lexical_bindings=lexical_bindings,
            lexical_types=lexical_types,
            diagnostic_sources=diagnostic_sources,
            diagnostic_root_id=diagnostic_root_id,
        )
        assert isinstance(source_type, ListTypeRef)
        child_bindings = dict(lexical_bindings)
        child_bindings[expr.binder_name] = _LEXICAL_LOCAL_BINDING
        child_types = dict(lexical_types)
        child_types[expr.binder_name] = source_type.item_type_ref
        body_node, body_type = _payload_expr(
            expr.body_expr,
            type_env=type_env, source_read_trace=source_read_trace,
            lexical_bindings=child_bindings,
            lexical_types=child_types,
            diagnostic_sources=diagnostic_sources,
            diagnostic_root_id=diagnostic_root_id,
        )
        return {
            "kind": "list_map",
            "source": source_node,
            "binder": {
                "name": expr.binder_name,
                "type": _type_descriptor(
                    source_type.item_type_ref,
                    type_env=type_env,
                    source_read_trace=source_read_trace,
                ),
            },
            "body": body_node,
            "result_element_type": _type_descriptor(
                body_type,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
        }, type_ref
    if isinstance(expr, PathJoinUnderExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "path_join_under",
            "path_type": _type_descriptor(
                type_ref,
                type_env=type_env,
                source_read_trace=source_read_trace,
            ),
            "child": _payload_expr(
                expr.child_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )[0],
        }, type_ref
    if isinstance(expr, IfExpr):
        type_ref = _infer_expr_type(expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        return {
            "kind": "if",
            "condition": _payload_expr(
                expr.condition_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )[0],
            "then": _payload_expr(
                expr.then_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )[0],
            "else": _payload_expr(
                expr.else_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                diagnostic_sources=diagnostic_sources,
                diagnostic_root_id=diagnostic_root_id,
            )[0],
        }, type_ref
    raise TypeError(f"unsupported pure projection expression: {type(expr).__name__}")


def _infer_expr_type(
    expr: Any,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None,
    lexical_types: Mapping[str, TypeRef],
) -> TypeRef:
    from .expressions import CompilerListNonemptyHeadExpr, EnumMemberExpr, FieldAccessExpr, GeneratedRelpathSeedExpr, IfExpr, LetStarExpr, ListExpr, ListMapExpr, LiteralExpr, NameExpr, PathJoinUnderExpr, PureOpExpr, RecordExpr, RecordUpdateExpr, UnionVariantExpr, UnionVariantTagExpr
    from .type_env import ListTypeRef, OptionalTypeRef, PrimitiveTypeRef
    from .typecheck_pure_ops import catalog_operator_result_type

    if isinstance(expr, LiteralExpr):
        if expr.literal_kind == "bool":
            return PrimitiveTypeRef(name="Bool")
        if expr.literal_kind == "int":
            return PrimitiveTypeRef(name="Int")
        if expr.literal_kind == "float":
            return PrimitiveTypeRef(name="Float")
        return PrimitiveTypeRef(name="String")
    if isinstance(expr, GeneratedRelpathSeedExpr):
        return expr.target_type_ref
    if isinstance(expr, EnumMemberExpr):
        return type_env.resolve_type(
            expr.enum_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, UnionVariantTagExpr):
        return PrimitiveTypeRef(name=expr.union_name, allowed_values=expr.variant_names)
    if isinstance(expr, NameExpr):
        return lexical_types[expr.name]
    if isinstance(expr, FieldAccessExpr):
        current = _infer_expr_type(expr.base, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
        for field_name in expr.fields:
            current = _field_type(current, field_name, type_env=type_env)
        return current
    if isinstance(expr, RecordExpr | UnionVariantExpr):
        return type_env.resolve_constructor_type(
            expr, expansion_stack=getattr(expr, "expansion_stack", ())
        )
    if isinstance(expr, RecordUpdateExpr):
        return _infer_expr_type(expr.base_expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
    if isinstance(expr, ListExpr):
        if expr.element_type_ref is None:
            raise TypeError("typed list expression is missing its element type")
        return ListTypeRef(
            name=f"List[{expr.element_type_ref.name}]",
            item_type_ref=expr.element_type_ref,
        )
    if isinstance(expr, ListMapExpr):
        if expr.result_item_type_ref is None:
            raise TypeError("typed list/map expression is missing its result element type")
        return ListTypeRef(
            name=f"List[{expr.result_item_type_ref.name}]",
            item_type_ref=expr.result_item_type_ref,
        )
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        return expr.element_type_ref
    if isinstance(expr, PathJoinUnderExpr):
        if expr.path_type_ref is None:
            raise TypeError("typed path/join-under expression is missing its path type")
        return expr.path_type_ref
    if isinstance(expr, PureOpExpr):
        arg_types = tuple(
            _infer_expr_type(arg, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
            for arg in expr.args
        )
        operator = expr.operator
        catalog_type = catalog_operator_result_type(operator, arg_types)
        if catalog_type is not None:
            return catalog_type
        if operator in {"=", "!=", "some?"}:
            return PrimitiveTypeRef(name="Bool")
        if operator == "or-else":
            if isinstance(arg_types[0], OptionalTypeRef):
                return arg_types[0].item_type_ref
            return PrimitiveTypeRef(name="Int")
        if operator == "string/concat":
            return PrimitiveTypeRef(name="String")
        if operator == "list/empty?":
            return PrimitiveTypeRef(name="Bool")
        if operator == "list/head":
            assert isinstance(arg_types[0], ListTypeRef)
            return OptionalTypeRef(
                name=f"Optional[{arg_types[0].item_type_ref.name}]",
                item_type_ref=arg_types[0].item_type_ref,
            )
        if operator in {"list/rest", "list/append"}:
            return arg_types[0]
        if operator == "list/length":
            return PrimitiveTypeRef(name="Int")
        if operator == "print":
            return arg_types[0]
        raise TypeError(f"unsupported pure operator `{operator}`")
    if isinstance(expr, IfExpr):
        return _infer_expr_type(expr.then_expr, type_env=type_env, source_read_trace=source_read_trace, lexical_types=lexical_types)
    if isinstance(expr, LetStarExpr):
        child_types = dict(lexical_types)
        for binding_name, binding_expr in expr.bindings:
            child_types[binding_name] = _infer_expr_type(
                binding_expr,
                type_env=type_env, source_read_trace=source_read_trace,
                lexical_types=child_types,
            )
        return _infer_expr_type(expr.body, type_env=type_env, source_read_trace=source_read_trace, lexical_types=child_types)
    raise TypeError(f"unsupported type inference expression `{type(expr).__name__}`")


def _field_type(type_ref: TypeRef, field_name: str, *, type_env: FrontendTypeEnvironment) -> TypeRef:
    from .type_env import PrimitiveTypeRef, RecordTypeRef, UnionTypeRef, VariantCaseTypeRef

    if isinstance(type_ref, RecordTypeRef):
        resolved = type_ref.field_types.get(field_name)
        if resolved is not None:
            return resolved
        for field in type_ref.definition.fields:
            if field.name == field_name:
                return type_env.resolve_type(field.type_name, span=field.span, form_path=())
    if isinstance(type_ref, UnionTypeRef):
        if field_name == "variant":
            return PrimitiveTypeRef(name="String")
        for variant in type_ref.definition.variants:
            resolved = type_ref.variant_field_types.get(variant.name, {}).get(field_name)
            if resolved is not None:
                return resolved
    if isinstance(type_ref, VariantCaseTypeRef):
        # Same carried-field-types preference as `_type_descriptor` (gap C):
        # the bare-name union re-lookup below fails for caller-module unions
        # inside specialized generic bodies; `field_types` carries the same
        # resolved mapping the lookup would produce.
        if type_ref.field_types is not None:
            resolved = type_ref.field_types.get(field_name)
            if resolved is not None:
                return resolved
        union_type = type_env.resolve_type(type_ref.union_name, span=type_ref.definition.span, form_path=())
        if isinstance(union_type, UnionTypeRef):
            resolved = union_type.variant_field_types.get(type_ref.variant_name, {}).get(field_name)
            if resolved is not None:
                return resolved
    raise KeyError(f"unknown field `{field_name}` on `{type(type_ref).__name__}`")


def _type_descriptor(
    type_ref: TypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    source_read_trace: SourceReadTrace | None = None,
) -> dict[str, Any]:
    from .normalized_type_descriptor import compiler_normalized_type_descriptor

    return compiler_normalized_type_descriptor(
        type_ref,
        type_env=type_env,
        source_read_trace=source_read_trace,
    )


def _raise_pure_expr_error(
    error: PureExprEvaluationError,
    *,
    span,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=error.code,
                message=str(error),
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
