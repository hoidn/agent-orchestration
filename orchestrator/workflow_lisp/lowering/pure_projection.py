"""Shared lowering helpers for compiler-generated pure projection steps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.pure_expr import (
    PureExprEvaluationError,
    evaluate_pure_expr,
    pure_expr_payload_digest,
    validate_pure_expr_payload,
)
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..contracts import derive_union_workflow_boundary_projection, derive_workflow_boundary_fields
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    EnumMemberExpr,
    FieldAccessExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    NameExpr,
    PureOpExpr,
    RecordExpr,
    RecordUpdateExpr,
    UnionVariantExpr,
)
from ..type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)
from .context import _LoweringContext
from .generated_paths import allocate_generated_result_bundle
from .origins import GeneratedSemanticEffectBinding, _record_step_origin
from .values import ProjectedPathRef, _resolve_inline_expr_value


PURE_PROJECTION_EFFECT_KIND = "pure_projection"


@dataclass(frozen=True)
class LoweredPureProjection:
    """One generated pure projection step plus its flattened output refs."""

    step: dict[str, Any]
    output_refs: dict[str, str]


def is_pure_projection_expr(expr: Any) -> bool:
    """Return whether one frontend expression can lower through pure projection."""

    if isinstance(expr, (LiteralExpr, EnumMemberExpr, NameExpr, FieldAccessExpr, PureOpExpr, RecordUpdateExpr)):
        return True
    if isinstance(expr, RecordExpr):
        return all(is_pure_projection_expr(field_expr) for _, field_expr in expr.fields)
    if isinstance(expr, UnionVariantExpr):
        return all(is_pure_projection_expr(field_expr) for _, field_expr in expr.fields)
    if isinstance(expr, IfExpr):
        return (
            is_pure_projection_expr(expr.condition_expr)
            and is_pure_projection_expr(expr.then_expr)
            and is_pure_projection_expr(expr.else_expr)
        )
    if isinstance(expr, LetStarExpr):
        return all(is_pure_projection_expr(binding_expr) for _, binding_expr in expr.bindings) and is_pure_projection_expr(expr.body)
    return False


def try_evaluate_static_pure_expr(
    expr: Any,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> Any | None:
    """Return the evaluated value when one pure expression is fully static."""

    payload, binding_refs = build_pure_projection_payload(
        expr,
        result_type=result_type,
        context=context,
        local_values=local_values,
    )
    if _contains_runtime_ref(binding_refs):
        return None
    try:
        return evaluate_pure_expr(payload, resolved_bindings=binding_refs)
    except PureExprEvaluationError as exc:
        _raise_pure_expr_error(
            exc,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
        )


def lower_pure_projection_step(
    expr: Any,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name: str,
    step_id: str,
    source_expr: Any | None = None,
    stable_target: str = "pure_projection",
    output_contracts: Mapping[str, Mapping[str, Any]] | None = None,
) -> LoweredPureProjection:
    """Lower one pure expression into a generated runtime-visible projection step."""

    payload, binding_refs = build_pure_projection_payload(
        expr,
        result_type=result_type,
        context=context,
        local_values=local_values,
    )
    payload_digest = pure_expr_payload_digest(payload)
    lowered_output_contracts = dict(
        output_contracts
        or _output_contracts_for_type(
            result_type,
            context=context,
            span=expr.span,
            form_path=expr.form_path,
        )
    )
    bundle_allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=source_expr or expr,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.PURE_PROJECTION_BUNDLE,
        stable_target=stable_target,
    )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=source_expr or expr)
    context.generated_semantic_effects.append(
        GeneratedSemanticEffectBinding(
            effect_key=f"{PURE_PROJECTION_EFFECT_KIND}:{step_id}",
            step_id=step_id,
            effect_kind=PURE_PROJECTION_EFFECT_KIND,
            origin=context.step_spans[step_id],
            details={
                "payload_digest": payload_digest,
                "pure_expr_schema_version": payload.get("pure_expr_schema_version"),
                "result_type": dict(payload["result_type"]),
                "output_bundle_path": bundle_allocation.concrete_path_template,
            },
        )
    )
    step = {
        "name": step_name,
        "id": step_id,
        "output_bundle": {
            "path": bundle_allocation.concrete_path_template,
            "fields": _output_bundle_fields(lowered_output_contracts),
        },
        "pure_projection": {
            "payload": payload,
            "binding_refs": binding_refs,
            "payload_digest": payload_digest,
            "output_contracts": lowered_output_contracts,
        },
    }
    return LoweredPureProjection(
        step=step,
        output_refs={
            output_name: f"root.steps.{step_name}.artifacts.{output_name}"
            for output_name in lowered_output_contracts
        },
    )


def build_pure_projection_payload(
    expr: Any,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one validated runtime payload plus runtime binding refs."""

    bindings: dict[str, dict[str, Any]] = {}
    binding_refs: dict[str, Any] = {}
    payload_expr, inferred_type = _payload_expr(
        expr,
        context=context,
        local_values=local_values,
        lexical_bindings={},
        lexical_types={},
        bindings=bindings,
        binding_refs=binding_refs,
    )
    if not _pure_projection_type_equivalent(
        inferred_type,
        result_type,
        type_env=context.type_env,
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
        "pure_expr_schema_version": 1,
        "result_type": _type_descriptor(result_type, type_env=context.type_env),
        "bindings": bindings,
        "expr": payload_expr,
    }
    try:
        validate_pure_expr_payload(payload)
    except PureExprEvaluationError as exc:
        _raise_pure_expr_error(
            exc,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
        )
    return payload, binding_refs


def _pure_projection_type_equivalent(
    inferred_type: TypeRef,
    result_type: TypeRef,
    *,
    type_env: FrontendTypeEnvironment,
) -> bool:
    if _type_descriptor(inferred_type, type_env=type_env) == _type_descriptor(
        result_type,
        type_env=type_env,
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
    return False


def _short_type_name(name: str) -> str:
    return name.rsplit("::", 1)[-1].rsplit("/", 1)[-1]


def _payload_expr(
    expr: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    lexical_bindings: Mapping[str, Any],
    lexical_types: Mapping[str, TypeRef],
    bindings: dict[str, dict[str, Any]],
    binding_refs: dict[str, Any],
) -> tuple[dict[str, Any], TypeRef]:
    if isinstance(expr, LetStarExpr):
        child_bindings = dict(lexical_bindings)
        child_types = dict(lexical_types)
        for binding_name, binding_expr in expr.bindings:
            child_bindings[binding_name] = binding_expr
            child_types[binding_name] = _infer_expr_type(
                binding_expr,
                context=context,
                lexical_types=child_types,
            )
        return _payload_expr(
            expr.body,
            context=context,
            local_values=local_values,
            lexical_bindings=child_bindings,
            lexical_types=child_types,
            bindings=bindings,
            binding_refs=binding_refs,
        )
    if isinstance(expr, NameExpr):
        if expr.name in lexical_bindings:
            return _payload_expr(
                lexical_bindings[expr.name],
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )
        local_binding = local_values.get(expr.name)
        if (
            isinstance(
                local_binding,
                (
                    FieldAccessExpr,
                    EnumMemberExpr,
                    IfExpr,
                    LetStarExpr,
                    LiteralExpr,
                    NameExpr,
                    PureOpExpr,
                    RecordExpr,
                    RecordUpdateExpr,
                    UnionVariantExpr,
                ),
            )
            and local_binding is not expr
        ):
            return _payload_expr(
                local_binding,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )
        type_ref = lexical_types.get(expr.name) or context.local_type_bindings.get(expr.name)
        if type_ref is None:
            raise KeyError(f"missing local type binding for `{expr.name}`")
        bindings.setdefault(expr.name, {"type": _type_descriptor(type_ref, type_env=context.type_env)})
        binding_refs.setdefault(
            expr.name,
            _binding_ref_value(expr.name, local_values=local_values),
        )
        return {"kind": "binding", "name": expr.name}, type_ref
    if isinstance(expr, LiteralExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "literal",
            "type": _type_descriptor(type_ref, type_env=context.type_env),
            "value": expr.value,
        }, type_ref
    if isinstance(expr, EnumMemberExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "literal",
            "type": _type_descriptor(type_ref, type_env=context.type_env),
            "value": expr.member_name,
        }, type_ref
    if isinstance(expr, FieldAccessExpr):
        base_expr: Any = expr.base
        if expr.base.name in lexical_bindings:
            base_expr = lexical_bindings[expr.base.name]
            for field_name in expr.fields:
                base_expr = FieldAccessExpr(
                    base=base_expr if isinstance(base_expr, NameExpr) else _name_expr(expr.base.name, expr),
                    fields=(field_name,) if isinstance(base_expr, NameExpr) else (field_name,),
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=getattr(expr, "expansion_stack", ()),
                )
        if not isinstance(base_expr, FieldAccessExpr):
            base_node, _ = _payload_expr(
                expr.base,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )
        else:
            base_node, _ = _payload_expr(
                base_expr,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )
        node = base_node
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        base_type = _infer_expr_type(expr.base, context=context, lexical_types=lexical_types)
        current_type = base_type
        for field_name in expr.fields:
            node = {"kind": "field_access", "base": node, "field": field_name}
            current_type = _field_type(current_type, field_name, type_env=context.type_env)
        return node, type_ref
    if isinstance(expr, RecordExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "record",
            "type": _type_descriptor(type_ref, type_env=context.type_env),
            "fields": [
                {
                    "name": field_name,
                    "value": _payload_expr(
                        field_expr,
                        context=context,
                        local_values=local_values,
                        lexical_bindings=lexical_bindings,
                        lexical_types=lexical_types,
                        bindings=bindings,
                        binding_refs=binding_refs,
                    )[0],
                }
                for field_name, field_expr in expr.fields
            ],
        }, type_ref
    if isinstance(expr, UnionVariantExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "union",
            "type": _type_descriptor(type_ref, type_env=context.type_env),
            "variant": expr.variant_name,
            "fields": [
                {
                    "name": field_name,
                    "value": _payload_expr(
                        field_expr,
                        context=context,
                        local_values=local_values,
                        lexical_bindings=lexical_bindings,
                        lexical_types=lexical_types,
                        bindings=bindings,
                        binding_refs=binding_refs,
                    )[0],
                }
                for field_name, field_expr in expr.fields
            ],
        }, type_ref
    if isinstance(expr, RecordUpdateExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "record_update",
            "record_type": _type_descriptor(type_ref, type_env=context.type_env),
            "base": _payload_expr(
                expr.base_expr,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )[0],
            "fields": [
                {
                    "name": field_name,
                    "value": _payload_expr(
                        field_expr,
                        context=context,
                        local_values=local_values,
                        lexical_bindings=lexical_bindings,
                        lexical_types=lexical_types,
                        bindings=bindings,
                        binding_refs=binding_refs,
                    )[0],
                }
                for field_name, field_expr in expr.overrides
            ],
        }, type_ref
    if isinstance(expr, PureOpExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "op",
            "operator": expr.operator,
            "args": [
                _payload_expr(
                    arg,
                    context=context,
                    local_values=local_values,
                    lexical_bindings=lexical_bindings,
                    lexical_types=lexical_types,
                    bindings=bindings,
                    binding_refs=binding_refs,
                )[0]
                for arg in expr.args
            ],
        }, type_ref
    if isinstance(expr, IfExpr):
        type_ref = _infer_expr_type(expr, context=context, lexical_types=lexical_types)
        return {
            "kind": "if",
            "condition": _payload_expr(
                expr.condition_expr,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )[0],
            "then": _payload_expr(
                expr.then_expr,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )[0],
            "else": _payload_expr(
                expr.else_expr,
                context=context,
                local_values=local_values,
                lexical_bindings=lexical_bindings,
                lexical_types=lexical_types,
                bindings=bindings,
                binding_refs=binding_refs,
            )[0],
        }, type_ref
    raise TypeError(f"unsupported pure projection expression: {type(expr).__name__}")


def _binding_ref_value(name: str, *, local_values: Mapping[str, Any]) -> Any:
    if name not in local_values:
        raise KeyError(f"missing local value for `{name}`")
    return _runtime_binding_value(local_values[name])


def _runtime_binding_value(value: Any) -> Any:
    if isinstance(value, ProjectedPathRef):
        return {"ref": value.ref}
    if isinstance(value, LiteralExpr):
        return value.value
    if isinstance(value, EnumMemberExpr):
        return value.member_name
    if isinstance(value, GeneratedRelpathSeedExpr):
        return value.literal_path
    if isinstance(value, str):
        return {"ref": value}
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.startswith("__"):
                continue
            result[str(key)] = _runtime_binding_value(item)
        return result
    if isinstance(value, list):
        return [_runtime_binding_value(item) for item in value]
    if isinstance(value, tuple):
        return [_runtime_binding_value(item) for item in value]
    if isinstance(value, (bool, int, float)):
        return value
    if value is None:
        return None
    if isinstance(value, (NameExpr, FieldAccessExpr, RecordExpr, PureOpExpr, RecordUpdateExpr, UnionVariantExpr, IfExpr)):
        resolved = _resolve_inline_expr_value(value, local_values={})
        if resolved is value:
            raise TypeError(f"runtime binding cannot resolve expression `{type(value).__name__}`")
        return _runtime_binding_value(resolved)
    raise TypeError(f"unsupported runtime binding value: {type(value).__name__}")


def _infer_expr_type(
    expr: Any,
    *,
    context: _LoweringContext,
    lexical_types: Mapping[str, TypeRef],
) -> TypeRef:
    if isinstance(expr, LiteralExpr):
        if expr.literal_kind == "bool":
            return PrimitiveTypeRef(name="Bool")
        if expr.literal_kind == "int":
            return PrimitiveTypeRef(name="Int")
        return PrimitiveTypeRef(name="String")
    if isinstance(expr, EnumMemberExpr):
        return context.type_env.resolve_type(
            expr.enum_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, NameExpr):
        return lexical_types.get(expr.name) or context.local_type_bindings[expr.name]
    if isinstance(expr, FieldAccessExpr):
        current = _infer_expr_type(expr.base, context=context, lexical_types=lexical_types)
        for field_name in expr.fields:
            current = _field_type(current, field_name, type_env=context.type_env)
        return current
    if isinstance(expr, RecordExpr):
        return context.type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
        )
    if isinstance(expr, UnionVariantExpr):
        return context.type_env.resolve_type(
            expr.type_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
        )
    if isinstance(expr, RecordUpdateExpr):
        return _infer_expr_type(expr.base_expr, context=context, lexical_types=lexical_types)
    if isinstance(expr, PureOpExpr):
        arg_types = tuple(
            _infer_expr_type(arg, context=context, lexical_types=lexical_types)
            for arg in expr.args
        )
        operator = expr.operator
        if operator in {"=", "!=", "<", "<=", ">", ">=", "and", "or", "not", "some?"}:
            return PrimitiveTypeRef(name="Bool")
        if operator in {"+", "-", "*", "min", "max", "or-else"}:
            if operator == "or-else" and isinstance(arg_types[0], OptionalTypeRef):
                return arg_types[0].item_type_ref
            return PrimitiveTypeRef(name="Int")
        if operator in {"string/concat", "symbol/name"}:
            return PrimitiveTypeRef(name="String")
        if operator == "string/empty?":
            return PrimitiveTypeRef(name="Bool")
        raise TypeError(f"unsupported pure operator `{operator}`")
    if isinstance(expr, IfExpr):
        return _infer_expr_type(expr.then_expr, context=context, lexical_types=lexical_types)
    if isinstance(expr, LetStarExpr):
        child_types = dict(lexical_types)
        for binding_name, binding_expr in expr.bindings:
            child_types[binding_name] = _infer_expr_type(
                binding_expr,
                context=context,
                lexical_types=child_types,
            )
        return _infer_expr_type(expr.body, context=context, lexical_types=child_types)
    raise TypeError(f"unsupported type inference expression `{type(expr).__name__}`")


def _field_type(type_ref: TypeRef, field_name: str, *, type_env: FrontendTypeEnvironment) -> TypeRef:
    if isinstance(type_ref, RecordTypeRef):
        resolved = type_ref.field_types.get(field_name)
        if resolved is not None:
            return resolved
        for field in type_ref.definition.fields:
            if field.name == field_name:
                return type_env.resolve_type(field.type_name, span=field.span, form_path=())
    if isinstance(type_ref, UnionTypeRef):
        for variant in type_ref.definition.variants:
            for field in variant.fields:
                if field.name == field_name:
                    return type_env.resolve_type(field.type_name, span=field.span, form_path=())
    if isinstance(type_ref, VariantCaseTypeRef):
        for field in type_ref.definition.fields:
            if field.name == field_name:
                return type_env.resolve_type(field.type_name, span=field.span, form_path=())
    raise KeyError(f"unknown field `{field_name}` on `{type(type_ref).__name__}`")


def _type_descriptor(type_ref: TypeRef, *, type_env: FrontendTypeEnvironment) -> dict[str, Any]:
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            return {
                "kind": "enum",
                "name": type_ref.name,
                "allowed": list(type_ref.allowed_values),
            }
        return {"kind": "primitive", "name": type_ref.name}
    if isinstance(type_ref, PathTypeRef):
        return {"kind": "path", "name": type_ref.name}
    if isinstance(type_ref, OptionalTypeRef):
        return {"kind": "optional", "item": _type_descriptor(type_ref.item_type_ref, type_env=type_env)}
    if isinstance(type_ref, ListTypeRef):
        return {"kind": "list", "item": _type_descriptor(type_ref.item_type_ref, type_env=type_env)}
    if isinstance(type_ref, MapTypeRef):
        return {
            "kind": "map",
            "key": _type_descriptor(type_ref.key_type_ref, type_env=type_env),
            "value": _type_descriptor(type_ref.value_type_ref, type_env=type_env),
        }
    if isinstance(type_ref, RecordTypeRef):
        return {
            "kind": "record",
            "name": type_ref.name,
            "fields": [
                {
                    "name": field.name,
                    "type": _type_descriptor(type_ref.field_types[field.name], type_env=type_env),
                }
                for field in type_ref.definition.fields
            ],
        }
    if isinstance(type_ref, UnionTypeRef):
        return {
            "kind": "union",
            "name": type_ref.name,
            "variants": [
                {
                    "name": variant.name,
                    "fields": [
                        {
                            "name": field.name,
                            "type": _type_descriptor(
                                type_ref.variant_field_types[variant.name][field.name],
                                type_env=type_env,
                            ),
                        }
                        for field in variant.fields
                    ],
                }
                for variant in type_ref.definition.variants
            ],
        }
    if isinstance(type_ref, VariantCaseTypeRef):
        return {
            "kind": "variant_case",
            "union_name": type_ref.union_name,
            "variant": type_ref.variant_name,
            "fields": [
                {
                    "name": field.name,
                    "type": _type_descriptor(
                        type_env.resolve_type(field.type_name, span=field.span, form_path=()),
                        type_env=type_env,
                    ),
                }
                for field in type_ref.definition.fields
            ],
        }
    raise TypeError(f"unsupported pure type descriptor for `{type(type_ref).__name__}`")


def _output_contracts_for_type(
    type_ref: TypeRef,
    *,
    context: _LoweringContext,
    span,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return _structured_output_contracts(
            type_ref,
            generated_name="return",
            source_path=("return",),
            span=span,
            form_path=form_path,
        )
    return {
        "return": {
            "kind": "scalar",
            "type": _scalar_contract_type(type_ref),
            **(
                {"allowed": list(type_ref.allowed_values)}
                if isinstance(type_ref, PrimitiveTypeRef) and type_ref.allowed_values
                else {}
            ),
        }
    }


def _scalar_contract_type(type_ref: TypeRef) -> str:
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            return "enum"
        name_map = {"Bool": "bool", "Int": "integer", "Float": "float", "String": "string", "Symbol": "string"}
        return name_map.get(type_ref.name, "string")
    if isinstance(type_ref, PathTypeRef):
        return "relpath"
    raise TypeError(f"unsupported scalar pure projection contract `{type(type_ref).__name__}`")


def output_contracts_for_boundary_type(
    type_ref: TypeRef,
    *,
    generated_name: str,
    span,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build output contracts for one arbitrary boundary name prefix."""

    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return _structured_output_contracts(
            type_ref,
            generated_name=generated_name,
            source_path=(generated_name,),
            span=span,
            form_path=form_path,
        )
    return {
        generated_name: {
            "kind": "scalar",
            "type": _scalar_contract_type(type_ref),
            **(
                {"allowed": list(type_ref.allowed_values)}
                if isinstance(type_ref, PrimitiveTypeRef) and type_ref.allowed_values
                else {}
            ),
        }
    }


def _output_bundle_fields(output_contracts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for output_name, contract in output_contracts.items():
        if not isinstance(output_name, str) or not output_name:
            continue
        if not isinstance(contract, Mapping):
            continue
        field = {
            "name": output_name,
            "json_pointer": _output_json_pointer(output_name),
            **dict(contract),
        }
        fields.append(field)
    return fields


def _structured_output_contracts(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    generated_name: str,
    source_path: tuple[str, ...],
    span,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    fields = derive_workflow_boundary_fields(
        type_ref,
        generated_name=generated_name,
        source_path=source_path,
        span=span,
        form_path=form_path,
    )
    if not isinstance(type_ref, UnionTypeRef):
        return {
            field.generated_name: dict(field.contract_definition)
            for field in fields
        }

    projection = derive_union_workflow_boundary_projection(
        type_ref,
        span=span,
        form_path=form_path,
    )
    variant_names = tuple(projection.variant_fields)
    shared_names = {field.generated_name for field in projection.shared_fields}
    variant_name_map = {
        field.generated_name: variant_name
        for variant_name, variant_fields in projection.variant_fields.items()
        for field in variant_fields
    }
    contracts: dict[str, dict[str, Any]] = {}
    for field in fields:
        definition = dict(field.contract_definition)
        metadata: dict[str, Any] = {
            "projection_class": "union_workflow_boundary",
            "return_kind": "union",
            "union_output_group": "return",
            "discriminant_output": projection.discriminant_field.generated_name,
        }
        if field.generated_name == projection.discriminant_field.generated_name:
            metadata["field_role"] = "discriminant"
            metadata["active_variants"] = list(variant_names)
        elif field.generated_name in shared_names:
            metadata["field_role"] = "shared"
            metadata["active_variants"] = list(variant_names)
        else:
            active_variant = variant_name_map.get(field.generated_name)
            metadata["field_role"] = "variant" if active_variant is not None else "unknown"
            metadata["active_variants"] = [active_variant] if active_variant is not None else []
        definition["projection"] = metadata
        contracts[field.generated_name] = definition
    return contracts


def _output_json_pointer(output_name: str) -> str:
    if output_name == "return":
        return "/result"
    if output_name == "return__variant":
        return "/result/variant"
    suffix = output_name.removeprefix("return__")
    if not suffix or suffix == output_name:
        return "/result"
    return "/result/" + suffix.replace("__", "/")


def _contains_runtime_ref(value: Any) -> bool:
    if isinstance(value, Mapping):
        if set(value) == {"ref"} and isinstance(value.get("ref"), str):
            return True
        return any(_contains_runtime_ref(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_runtime_ref(item) for item in value)
    return False


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


def _name_expr(name: str, source_expr: Any) -> NameExpr:
    return NameExpr(
        name=name,
        span=source_expr.span,
        form_path=source_expr.form_path,
        expansion_stack=getattr(source_expr, "expansion_stack", ()),
    )
