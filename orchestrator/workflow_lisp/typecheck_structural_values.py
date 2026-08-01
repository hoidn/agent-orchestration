"""Structural list and rooted-path value typecheck ownership."""

from __future__ import annotations

from dataclasses import replace

from .diagnostics import LispFrontendCompileError
from .effects import EMPTY_EFFECT_SUMMARY, effect_summary_contains_runs_ref
from .expressions import (
    CallExpr,
    CommandResultExpr,
    CompilerListNonemptyHeadExpr,
    ContinueExpr,
    DoneExpr,
    ExprNode,
    FieldAccessExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    ListExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LiteralExpr,
    LoopRecurExpr,
    LoopStateField,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    NameExpr,
    PathJoinUnderExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    PureOpExpr,
)
from .type_env import ListTypeRef, PathTypeRef, PrimitiveTypeRef, TypeRef
from .typecheck_context import (
    TypecheckContext,
    TypedExpr,
    _type_label,
    _type_refs_compatible,
    raise_error,
    raise_run_ref_placement_invalid,
)


def _is_transportable_result_type(type_ref: TypeRef) -> bool:
    # `contracts` owns this predicate but imports workflow signatures, which
    # return through this typechecker during module initialization.
    from .contracts import is_transportable_result_type

    return is_transportable_result_type(type_ref)


def typecheck_structural_value_expr(
    expr: ExprNode,
    *,
    context: TypecheckContext,
    recurse,
    typed_factory,
    expected_type: TypeRef | None,
) -> TypedExpr | None:
    """Typecheck list traversal and rooted-path structural value forms."""

    type_env = context.type_env
    value_env = context.value_env

    if isinstance(expr, GeneratedRelpathSeedExpr):
        seed_type = expr.target_type_ref
        if isinstance(seed_type, str):
            seed_type = type_env.resolve_type(
                seed_type,
                span=expr.span,
                form_path=expr.form_path,
            )
            expr = GeneratedRelpathSeedExpr(
                target_type_ref=seed_type,
                literal_path=expr.literal_path,
                seed_role=expr.seed_role,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if not isinstance(seed_type, PathTypeRef) or seed_type.definition.kind != "relpath":
            raise_error(
                f"generated relpath seed `{expr.seed_role}` requires a relpath type, got `{_type_label(seed_type)}`",
                code="type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return typed_factory(expr=expr, type_ref=seed_type, effect=EMPTY_EFFECT_SUMMARY)
    if isinstance(expr, ListExpr):
        expected_list = expected_type if isinstance(expected_type, ListTypeRef) else None
        if not expr.items:
            if expected_list is None and expr.element_type_ref is not None:
                expected_list = ListTypeRef(
                    name=f"List[{expr.element_type_ref.name}]",
                    item_type_ref=expr.element_type_ref,
                )
            if expected_list is None:
                raise_error(
                    "empty `(list)` requires one exact expected `List[T]` context",
                    code="list_empty_type_context_required",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            list_type = expected_list
            item_type = expected_list.item_type_ref
            typed_items = ()
        else:
            typed_item_values = tuple(
                recurse(
                    item,
                    expected_type=(
                        expected_list.item_type_ref
                        if expected_list is not None
                        else None
                    ),
                )
                for item in expr.items
            )
            item_type = typed_item_values[0].type_ref
            if any(
                not _type_refs_compatible(item_type, typed_item.type_ref)
                for typed_item in typed_item_values[1:]
            ):
                raise_error(
                    "list constructor elements must have one exact compatible type",
                    code="pure_expr_operand_type_mismatch",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            list_type = ListTypeRef(
                name=f"List[{item_type.name}]",
                item_type_ref=item_type,
            )
            if expected_list is not None and not _type_refs_compatible(
                expected_list,
                list_type,
            ):
                raise_error(
                    (
                        "list constructor type did not match its exact expected "
                        f"context `{_type_label(expected_list)}`"
                    ),
                    code="pure_expr_operand_type_mismatch",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            typed_items = tuple(item.expr for item in typed_item_values)
            if any(
                item.effect_summary != EMPTY_EFFECT_SUMMARY
                for item in typed_item_values
            ):
                raise_error(
                    "list constructor elements must be pure",
                    code="effect_not_permitted",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
        if not _is_transportable_result_type(list_type):
            raise_error(
                (
                    "list collection contract is unsupported for complete type "
                    f"`{_type_label(list_type)}`"
                ),
                code="list_collection_contract_unsupported",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return typed_factory(
            expr=replace(
                expr,
                items=typed_items,
                element_type_ref=item_type,
            ),
            type_ref=list_type,
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, ListMapExpr):
        typed_source = recurse(expr.source_expr)
        if not isinstance(typed_source.type_ref, ListTypeRef):
            raise_error(
                "`list/map` source must have a List type",
                code="pure_expr_operand_type_mismatch",
                span=expr.source_expr.span,
                form_path=expr.source_expr.form_path,
                expansion_stack=expr.source_expr.expansion_stack,
            )
        if typed_source.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise_error(
                "`list/map` source must be pure",
                code="list_map_body_effect_forbidden",
                span=expr.source_expr.span,
                form_path=expr.source_expr.form_path,
                expansion_stack=expr.source_expr.expansion_stack,
            )
        if not _is_transportable_result_type(typed_source.type_ref):
            raise_error(
                (
                    "list collection contract is unsupported for complete type "
                    f"`{_type_label(typed_source.type_ref)}`"
                ),
                code="list_collection_contract_unsupported",
                span=expr.source_expr.span,
                form_path=expr.source_expr.form_path,
                expansion_stack=expr.source_expr.expansion_stack,
            )
        body_env = {
            **value_env,
            expr.binder_name: typed_source.type_ref.item_type_ref,
        }
        typed_body = recurse(expr.body_expr, value_env=body_env)
        if typed_body.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise_error(
                "`list/map` body must be pure",
                code="list_map_body_effect_forbidden",
                span=expr.body_expr.span,
                form_path=expr.body_expr.form_path,
                expansion_stack=expr.body_expr.expansion_stack,
            )
        result_type = ListTypeRef(
            name=f"List[{typed_body.type_ref.name}]",
            item_type_ref=typed_body.type_ref,
        )
        if not _is_transportable_result_type(result_type):
            raise_error(
                (
                    "list collection contract is unsupported for complete type "
                    f"`{_type_label(result_type)}`"
                ),
                code="list_collection_contract_unsupported",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if expected_type is not None and not _type_refs_compatible(
            expected_type,
            result_type,
        ):
            raise_error(
                (
                    f"`list/map` produced `{_type_label(result_type)}` but "
                    f"the checked context expected `{_type_label(expected_type)}`"
                ),
                code="pure_expr_operand_type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return typed_factory(
            expr=replace(
                expr,
                source_expr=typed_source.expr,
                body_expr=typed_body.expr,
                source_item_type_ref=typed_source.type_ref.item_type_ref,
                result_item_type_ref=typed_body.type_ref,
            ),
            type_ref=result_type,
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        typed_source = recurse(expr.source_expr)
        if not isinstance(typed_source.type_ref, ListTypeRef):
            raise_error(
                "compiler-owned nonempty head requires a List source",
                code="list_nonempty_invariant_broken",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if (
            typed_source.effect_summary != EMPTY_EFFECT_SUMMARY
            or not _type_refs_compatible(
                typed_source.type_ref.item_type_ref,
                expr.element_type_ref,
            )
        ):
            raise_error(
                "compiler-owned nonempty head has inconsistent source metadata",
                code="list_nonempty_invariant_broken",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return typed_factory(
            expr=replace(expr, source_expr=typed_source.expr),
            type_ref=expr.element_type_ref,
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, ListMapEffectExpr):
        typed_source = recurse(expr.source_expr)
        if effect_summary_contains_runs_ref(typed_source.effect_summary):
            raise_run_ref_placement_invalid(
                typed_source.expr,
                reason="is not permitted in a `list/map-effect` source",
            )
        if not isinstance(typed_source.type_ref, ListTypeRef):
            raise_error(
                "`list/map-effect` source must have a List type",
                code="pure_expr_operand_type_mismatch",
                span=expr.source_expr.span,
                form_path=expr.source_expr.form_path,
                expansion_stack=expr.source_expr.expansion_stack,
            )
        if typed_source.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise_error(
                "`list/map-effect` source must be pure",
                code="list_map_effect_body_unsupported",
                span=expr.source_expr.span,
                form_path=expr.source_expr.form_path,
                expansion_stack=expr.source_expr.expansion_stack,
            )
        if not _is_transportable_result_type(typed_source.type_ref):
            raise_error(
                (
                    "list collection contract is unsupported for complete type "
                    f"`{_type_label(typed_source.type_ref)}`"
                ),
                code="list_collection_contract_unsupported",
                span=expr.source_expr.span,
                form_path=expr.source_expr.form_path,
                expansion_stack=expr.source_expr.expansion_stack,
            )
        from .expression_traversal import walk_expr
        from .expressions import RunRefExpr

        try:
            direct_run_ref = next(
                (
                    candidate
                    for candidate in walk_expr(expr.body_expr)
                    if isinstance(candidate, RunRefExpr)
                ),
                None,
            )
        except TypeError:
            direct_run_ref = None
        if direct_run_ref is not None:
            raise_run_ref_placement_invalid(
                direct_run_ref,
                reason="is not permitted in a `list/map-effect` body",
            )
        if not isinstance(
            expr.body_expr,
            (
                ProviderResultExpr,
                CommandResultExpr,
                CallExpr,
                ProcedureCallExpr,
            ),
        ):
            raise_error(
                (
                    "`list/map-effect` body must be one provider, command, "
                    "workflow, or procedure call"
                ),
                code="list_map_effect_body_unsupported",
                span=expr.body_expr.span,
                form_path=expr.body_expr.form_path,
                expansion_stack=expr.body_expr.expansion_stack,
            )
        body_env = {
            **value_env,
            expr.binder_name: typed_source.type_ref.item_type_ref,
        }
        typed_body = recurse(expr.body_expr, value_env=body_env)
        if effect_summary_contains_runs_ref(typed_body.effect_summary):
            raise_run_ref_placement_invalid(
                typed_body.expr,
                reason="is not permitted in a `list/map-effect` body",
            )
        from .expression_traversal import iter_child_exprs
        from .functions import _find_purity_violation

        nested_effect = next(
            (
                violation
                for child in iter_child_exprs(typed_body.expr)
                if (violation := _find_purity_violation(child)) is not None
            ),
            None,
        )
        if nested_effect is not None:
            raise_error(
                (
                    "`list/map-effect` call arguments must be pure; found "
                    f"effectful form `{nested_effect}`"
                ),
                code="list_map_effect_body_unsupported",
                span=expr.body_expr.span,
                form_path=expr.body_expr.form_path,
                expansion_stack=expr.body_expr.expansion_stack,
            )
        result_type = ListTypeRef(
            name=f"List[{typed_body.type_ref.name}]",
            item_type_ref=typed_body.type_ref,
        )
        if not _is_transportable_result_type(result_type):
            raise_error(
                (
                    "list collection contract is unsupported for complete type "
                    f"`{_type_label(result_type)}`"
                ),
                code="list_collection_contract_unsupported",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if expected_type is not None and not _type_refs_compatible(
            expected_type,
            result_type,
        ):
            raise_error(
                (
                    f"`list/map-effect` produced `{_type_label(result_type)}` but "
                    f"the checked context expected `{_type_label(expected_type)}`"
                ),
                code="pure_expr_operand_type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        state_name = "__list_map_effect_state"
        next_state_name = "__list_map_effect_next_state"
        effect_result_name = "__list_map_effect_result"
        tail_name = "__list_map_effect_tail"
        appended_name = "__list_map_effect_results"

        def _state_field(field_name: str) -> FieldAccessExpr:
            return FieldAccessExpr(
                base=NameExpr(
                    name=state_name,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                fields=(field_name,),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )

        remaining = _state_field("remaining")
        results = _state_field("results")
        tail = PureOpExpr(
            operator="list/rest",
            args=(remaining,),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        appended = PureOpExpr(
            operator="list/append",
            args=(
                results,
                NameExpr(
                    name=effect_result_name,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        updated_state = LoopStateUpdateExpr(
            base_expr=NameExpr(
                name=state_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            overrides=(
                (
                    "remaining",
                    NameExpr(
                        name=tail_name,
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
                (
                    "results",
                    NameExpr(
                        name=appended_name,
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
            ),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        inner_control = IfExpr(
            condition_expr=PureOpExpr(
                operator="list/empty?",
                args=(
                    NameExpr(
                        name=tail_name,
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            then_expr=DoneExpr(
                result_expr=NameExpr(
                    name=appended_name,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                terminal_state_expr=NameExpr(
                    name=next_state_name,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
            else_expr=ContinueExpr(
                state_expr=NameExpr(
                    name=next_state_name,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        nonempty_body = LetStarExpr(
            bindings=(
                (
                    expr.binder_name,
                    CompilerListNonemptyHeadExpr(
                        source_expr=remaining,
                        element_type_ref=typed_source.type_ref.item_type_ref,
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
                (effect_result_name, typed_body.expr),
                (tail_name, tail),
                (appended_name, appended),
                (next_state_name, updated_state),
            ),
            body=inner_control,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        loop_body = IfExpr(
            condition_expr=PureOpExpr(
                operator="list/empty?",
                args=(remaining,),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            then_expr=DoneExpr(
                result_expr=results,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            else_expr=nonempty_body,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        synthetic_loop = LoopRecurExpr(
            max_iterations_expr=LiteralExpr(
                value=expr.max_iterations,
                literal_kind="int",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            initial_state_expr=LoopStateSeedExpr(
                fields=(
                    LoopStateField(
                        name="remaining",
                        type_name=typed_source.type_ref.name,
                        value_expr=typed_source.expr,
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                    LoopStateField(
                        name="results",
                        type_name=result_type.name,
                        value_expr=ListExpr(
                            items=(),
                            element_type_ref=typed_body.type_ref,
                            span=expr.span,
                            form_path=expr.form_path,
                            expansion_stack=expr.expansion_stack,
                        ),
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            binding_name=state_name,
            body_expr=loop_body,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            exhaustion_diagnostic_code="list_map_effect_cap_exceeded",
            single_iteration_effect_kinds=(
                "provider",
                "command",
                "call",
            ),
            effect_cardinality_diagnostic_code=(
                "list_map_effect_body_unsupported"
            ),
        )
        return recurse(synthetic_loop, expected_type=result_type)
    if isinstance(expr, PathJoinUnderExpr):
        try:
            path_type = type_env.resolve_type(
                expr.path_type_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        except LispFrontendCompileError as exc:
            if exc.diagnostics and exc.diagnostics[0].code == "type_unknown":
                raise_error(
                    (
                        "`path/join-under` selected an unresolved or non-path "
                        f"type `{expr.path_type_name}`"
                    ),
                    code="path_join_under_type_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            raise
        if not isinstance(path_type, PathTypeRef):
            raise_error(
                (
                    "`path/join-under` selected an unresolved or non-path "
                    f"type `{expr.path_type_name}`"
                ),
                code="path_join_under_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        typed_child = recurse(expr.child_expr)
        if typed_child.type_ref != PrimitiveTypeRef(name="String"):
            raise_error(
                "`path/join-under` child must have exact `String` type",
                code="pure_expr_operand_type_mismatch",
                span=expr.child_expr.span,
                form_path=expr.child_expr.form_path,
                expansion_stack=expr.child_expr.expansion_stack,
            )
        if typed_child.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise_error(
                "`path/join-under` child must be pure",
                code="effect_not_permitted",
                span=expr.child_expr.span,
                form_path=expr.child_expr.form_path,
                expansion_stack=expr.child_expr.expansion_stack,
            )
        return typed_factory(
            expr=replace(
                expr,
                child_expr=typed_child.expr,
                path_type_ref=path_type,
            ),
            type_ref=path_type,
            effect=EMPTY_EFFECT_SUMMARY,
        )
    return None
