"""Frontend reconstruction retained only by historical provider-region preparation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ..expression_traversal import map_expr
from ..expressions import (
    CompilerListNonemptyHeadExpr, EnumMemberExpr, FieldAccessExpr, GeneratedRelpathSeedExpr,
    IfExpr, LetStarExpr, ListExpr, ListMapExpr, LiteralExpr, NameExpr, PathJoinUnderExpr,
    ProviderBundlePathExpr, PureOpExpr, RecordExpr, RecordUpdateExpr, UnionVariantExpr,
    UnionVariantTagExpr,
)
from ..type_env import DiscriminantTypeRef, PathTypeRef, PrimitiveTypeRef
from .model import (
    WccBlock, WccFieldAccessAtom, WccInject, WccList, WccListMap, WccLiteralAtom,
    WccNameAtom, WccOpaqueFrontendValue, WccPhaseTargetAtom, WccPureOp,
    WccRecordAtom, WccResultPath, WccSelect, WccSelectArm, WccValue,
)


def _frontend_expr_from_wcc_value(value: WccValue):
    from .elaborate import _body_to_prefix_and_value

    if isinstance(value, WccLiteralAtom):
        if isinstance(value.metadata.type_ref, DiscriminantTypeRef):
            owner = value.metadata.type_ref
            return UnionVariantTagExpr(union_name=owner.union_name, variant_name=str(value.value),
                variant_names=owner.variant_names, discriminant_owner=owner.owner_union or owner.applied_union,
                span=value.metadata.source_span, form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack)
        if isinstance(value.metadata.type_ref, PathTypeRef):
            return GeneratedRelpathSeedExpr(target_type_ref=value.metadata.type_ref,
                literal_path=str(value.value), seed_role="wcc-literal",
                span=value.metadata.source_span, form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack)
        if value.literal_kind == "enum":
            type_ref = value.metadata.type_ref
            if not isinstance(type_ref, PrimitiveTypeRef) or not type_ref.allowed_values:
                raise TypeError("enum WCC literal requires an enum primitive type")
            return EnumMemberExpr(
                enum_name=type_ref.name,
                member_name=str(value.value),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        return LiteralExpr(
            value=value.value,
            literal_kind=value.literal_kind,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccNameAtom):
        return NameExpr(
            name=value.name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccPhaseTargetAtom):
        from ..expressions import PhaseTargetExpr

        return PhaseTargetExpr(
            target_name=value.target_name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccOpaqueFrontendValue):
        return value.expr
    if isinstance(value, WccFieldAccessAtom):
        return FieldAccessExpr(
            base=_frontend_expr_from_wcc_value(value.base),
            fields=value.fields,
            shared_field_types=value.shared_field_types,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccRecordAtom):
        return RecordExpr(
            type_name=value.type_name,
            fields=tuple(
                (field_name, _frontend_expr_from_wcc_value(field_value))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
            resolved_type=value.resolved_type,
        )
    if isinstance(value, WccPureOp):
        if value.operator == "compiler-list-nonempty-head":
            return CompilerListNonemptyHeadExpr(source_expr=_frontend_expr_from_wcc_value(value.args[0]),
                element_type_ref=value.metadata.type_ref, span=value.metadata.source_span,
                form_path=value.metadata.form_path, expansion_stack=value.metadata.expansion_stack)
        if value.operator == "path/join-under":
            return PathJoinUnderExpr(path_type_name=value.metadata.type_ref.name,
                path_type_ref=value.metadata.type_ref, child_expr=_frontend_expr_from_wcc_value(value.args[0]),
                span=value.metadata.source_span, form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack)
        if value.operator in {"record-update", "loop-state-update"}:
            if not value.args:
                raise TypeError("record-update WCC pure op requires a base argument")
            return RecordUpdateExpr(
                base_expr=_frontend_expr_from_wcc_value(value.args[0]),
                overrides=tuple(
                    (
                        field_name,
                        _frontend_expr_from_wcc_value(field_value),
                    )
                    for field_name, field_value in zip(value.field_names, value.args[1:], strict=True)
                ),
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        return PureOpExpr(
            operator=value.operator,
            args=tuple(_frontend_expr_from_wcc_value(arg) for arg in value.args),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccInject):
        return UnionVariantExpr(
            type_name=value.union_name,
            variant_name=value.variant_name,
            fields=tuple(
                (field_name, _frontend_expr_from_wcc_value(field_value))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
            resolved_type=value.resolved_type,
        )
    if isinstance(value, WccResultPath):
        return ProviderBundlePathExpr(source_expr=_frontend_expr_from_wcc_value(value.source),
            target_type_name=value.metadata.type_ref.name, span=value.metadata.source_span,
            form_path=value.metadata.form_path, expansion_stack=value.metadata.expansion_stack)
    if isinstance(value, WccListMap):
        prefix, result = _body_to_prefix_and_value(value.body)
        return ListMapExpr(binder_name=value.binder_name,
            source_expr=_frontend_expr_from_wcc_value(value.source),
            body_expr=_frontend_wcc_select_arm(WccSelectArm(prefix=prefix, value=result)),
            source_item_type_ref=value.binder_type_ref,
            result_item_type_ref=value.body_metadata.type_ref,
            binding_label=value.binding_label, binding_identity=value.binding_identity,
            span=value.metadata.source_span, form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack)
    if isinstance(value, WccList):
        return ListExpr(
            items=tuple(_frontend_expr_from_wcc_value(item) for item in value.items),
            element_type_ref=value.metadata.type_ref.item_type_ref,
            item_type_refs=tuple(item.metadata.type_ref for item in value.items),
            span=value.metadata.source_span, form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccBlock):
        prefix, result = _body_to_prefix_and_value(value.body)
        return _frontend_wcc_select_arm(WccSelectArm(prefix=prefix, value=result))
    if isinstance(value, WccSelect):
        return IfExpr(
            condition_expr=_frontend_expr_from_wcc_value(value.condition),
            then_expr=_frontend_wcc_select_arm(value.then_arm),
            else_expr=_frontend_wcc_select_arm(value.else_arm),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    raise TypeError(f"unsupported WCC value during defunctionalization: {type(value).__name__}")


def _frontend_wcc_select_arm(arm: WccSelectArm):
    """Reconstruct one select arm without an environment substitution."""

    bindings = tuple(
        (
            let_node.bound_name,
            _frontend_expr_from_wcc_value(let_node.bound_value),
        )
        for let_node in arm.prefix
    )
    value_expr = _frontend_expr_from_wcc_value(arm.value)
    if not bindings:
        return value_expr
    return LetStarExpr(
        bindings=bindings,
        binding_identities=tuple(node.metadata.binding_identity for node in arm.prefix),
        binding_capture_sources=tuple(
            (node.bound_value.metadata.binding_identity, node.bound_type_ref)
            if isinstance(node.bound_value, WccNameAtom) and node.bound_value.is_capture_read
            else None for node in arm.prefix),
        body=value_expr,
        span=arm.value.metadata.source_span,
        form_path=arm.value.metadata.form_path,
        expansion_stack=arm.value.metadata.expansion_stack,
    )


def substitute_opaque_expression(
    expr: object,
    substitutions: Mapping[str, WccValue],
) -> object:
    """Substitute free names inside one opaque frontend expression.

    A bind-site rename keeps the authored reference span; any non-name
    substitution value is materialized through the shared WCC-to-frontend
    reconstruction so the opaque child stays a closed frontend term.
    """

    def on_name(node: NameExpr):
        replacement = substitutions.get(node.name)
        if replacement is None:
            return node
        if isinstance(replacement, WccNameAtom):
            if replacement.name == node.name:
                return node
            return replace(node, name=replacement.name)
        return _frontend_expr_from_wcc_value(replacement)

    return map_expr(expr, on_name)
