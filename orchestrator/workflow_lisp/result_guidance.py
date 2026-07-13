"""Immutable authored metadata for typed Workflow Lisp result occurrences."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

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
) -> Any | None:
    """Elaborate, typecheck, evaluate, and schema-check one authored example."""

    if guidance is None or guidance.example_expr is None:
        return None
    example_node = guidance.example_expr
    try:
        from .expressions import elaborate_expression

        expr = elaborate_expression(
            example_node,
            bound_names=frozenset(),
            guidance_example=True,
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
    from .lowering.pure_projection import is_pure_projection_expr
    from .type_env import OptionalTypeRef, type_refs_compatible
    from .typecheck import typecheck_expression

    if not is_pure_projection_expr(expr, allow_generated_relpath_seed=True):
        _raise_example_diagnostic(
            "result_guidance_example_not_constant",
            "result guidance example must be an effect-free compile-time constant",
            example_node=example_node,
        )
    try:
        typed = typecheck_expression(expr, type_env=type_env, value_env={})
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
        from .lowering.pure_projection import evaluate_closed_pure_expr

        value = evaluate_closed_pure_expr(
            typed.expr,
            result_type=typed.type_ref,
            type_env=type_env,
        )
    except (LispFrontendCompileError, TypeError, ValueError) as exc:
        _raise_example_type_mismatch(expected_type, example_node=example_node, cause=exc)
    return validate_typed_guidance_constant(
        value,
        expected_type=expected_type,
        type_env=type_env,
        example_node=example_node,
        workspace=workspace,
    )


def validate_typed_guidance_constant(
    value: Any,
    *,
    expected_type,
    type_env,
    example_node: SyntaxNode,
    workspace: Path | None = None,
) -> Any:
    """Validate JSON-native constant data through pure and output schemas."""

    from orchestrator.contracts.output_contract import OutputContractError

    try:
        from .lowering.pure_projection import evaluate_typed_constant

        normalized = evaluate_typed_constant(
            value,
            result_type=expected_type,
            type_env=type_env,
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
) -> None:
    """Validate all definition and callable guidance visible in one module."""

    from .definitions import RecordDef, SchemaDef, UnionDef

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
