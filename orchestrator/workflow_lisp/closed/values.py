"""Translate WCC and retained surface values into checked JSON values."""

from __future__ import annotations

from typing import Any, Mapping

from orchestrator.workflow.pure_expr import validate_pure_expr_payload
from orchestrator.workflow_lisp.effects import EMPTY_EFFECT_SUMMARY
from orchestrator.workflow_lisp.expressions import (
    CompilerListNonemptyHeadExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    ListExpr,
    ListMapExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    NameExpr,
    PathJoinUnderExpr,
    ProviderBundlePathExpr,
    ResourceTransitionExpr,
    UnionVariantTagExpr,
)
from orchestrator.workflow_lisp.type_env import TypeRef
from orchestrator.workflow_lisp.wcc import model as w
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import _elaborate_expr_to_body


def translate_value(builder: Any, value: Any, d: Any, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    metadata = getattr(value, "metadata", None)
    if isinstance(value, w.WccLiteralAtom):
        result = {"k": "lit", "v": value.value, "type": builder.desc(value.metadata.type_ref, d)}
    elif isinstance(value, w.WccNameAtom):
        result = {
            "k": "name",
            "n": d.ref(value.name, value.metadata.binding_identity),
        }
    elif isinstance(value, w.WccFieldAccessAtom):
        result = {
            "k": "field",
            "base": translate_value(builder, value.base, d, env),
            "path": list(value.fields),
        }
        if value.shared_field_types:
            result["shared"] = [builder.desc(target, d) if target is not None else None
                                for target in value.shared_field_types]
    elif isinstance(value, w.WccRecordAtom):
        result = {
            "k": "record",
            "type": builder.desc(value.metadata.type_ref, d),
            "fields": [[name, translate_value(builder, item, d, env)] for name, item in value.fields],
        }
    elif isinstance(value, w.WccInject):
        result = {
            "k": "inject",
            "type": builder.desc(value.metadata.type_ref, d),
            "variant": value.variant_name,
            "fields": [[name, translate_value(builder, item, d, env)] for name, item in value.fields],
        }
    elif isinstance(value, w.WccPureOp):
        result = _operator(builder, value, d, env)
    elif isinstance(value, w.WccSelect):
        result = {
            "k": "select",
            "cond": translate_value(builder, value.condition, d, env),
            "then": _select_arm(builder, value.then_arm, d, env),
            "else": _select_arm(builder, value.else_arm, d, env),
        }
    elif isinstance(value, w.WccOpaqueFrontendValue):
        result = _opaque(builder, value, d, env)
    elif isinstance(value, w.WccPhaseTargetAtom):
        raise ValueError(f"phase target {value.target_name!r} escaped WCC elaboration")
    else:
        raise ValueError(f"WCC value {type(value).__name__} has no closed translation")
    return {**result, **builder.provenance(metadata)}


def _select_arm(builder: Any, arm: w.WccSelectArm, d: Any, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    local_names = dict(d.names)
    binding_aliases = dict(d.binding_aliases or {})
    run_ref_names = dict(d.run_ref_names or {})
    local_types = dict(env)
    prefix = []
    for let in arm.prefix:
        current = d.with_names(
            local_names,
            binding_aliases=binding_aliases,
            run_ref_names=run_ref_names,
        )
        value = builder.binding(let.bound_value, current, local_types)
        nested = dict(local_names)
        name = d.renamer.bind(
            let.bound_name,
            authored_label=let.metadata.binding_label,
            env=nested,
        )
        prefix.append({"name": name, "value": value})
        producer = builder.run_ref_producers_by_effect.get(id(value))
        if producer is None and isinstance(let.bound_value, w.WccNameAtom):
            resolved_name = current.resolved_binding_name(
                let.bound_value.name,
                let.bound_value.metadata.binding_identity,
            )
            producers = run_ref_names.get(resolved_name, ())
        elif producer is not None:
            producers = (producer,)
        else:
            producers = builder._run_ref_context_for_value(let.bound_value, current)
        if producers:
            run_ref_names[let.bound_name] = producers
        bound = d.with_names(
            nested,
            binding_aliases=binding_aliases,
            run_ref_names=run_ref_names,
        )
        bound, aliases = builder._freeze_bound_capture(
            bound,
            let.metadata.binding_identity,
            name,
            producers,
        )
        binding_aliases = dict(bound.binding_aliases or {})
        local_names = dict(bound.names)
        run_ref_names = dict(bound.run_ref_names or {})
        prefix.extend({"name": row["name"], "value": row["value"]} for row in aliases)
        local_types[let.bound_name] = let.bound_type_ref
    return {
        "prefix": prefix,
        "value": translate_value(
            builder,
            arm.value,
            d.with_names(
                local_names,
                binding_aliases=binding_aliases,
                run_ref_names=run_ref_names,
            ),
            local_types,
        ),
    }


def _operator(builder: Any, op: w.WccPureOp, d: Any, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    args = [translate_value(builder, arg, d, env) for arg in op.args]
    result_type = builder.desc(op.metadata.type_ref, d)
    arg_types = [builder.desc(arg.metadata.type_ref, d) for arg in op.args]
    if op.operator == "path/join":
        return {
            "k": "path_join",
            "base": args[0],
            "child": args[1],
            "type": result_type,
        }
    refs = [{"kind": "binding", "name": f"a{index}"} for index in range(len(args))]
    if op.operator == "record-update":
        expression = {
            "kind": "record_update",
            "record_type": result_type,
            "base": refs[0],
            "fields": [
                {"name": name, "value": reference}
                for name, reference in zip(op.field_names, refs[1:], strict=True)
            ],
        }
    else:
        expression = {"kind": "op", "operator": op.operator, "args": refs}
    payload = _payload(expression, result_type, arg_types)
    validate_pure_expr_payload(payload, max_nodes=None)
    return {"k": "op", "payload": payload, "args": args}


def _payload(expression: dict[str, Any], result_type: dict[str, Any], arg_types: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pure_expr_schema_version": 2,
        "result_type": result_type,
        "bindings": {f"a{index}": {"type": desc} for index, desc in enumerate(arg_types)},
        "expr": expression,
    }


def _opaque(builder: Any, value: w.WccOpaqueFrontendValue, d: Any, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    if value.normalized_body is not None:
        closed = builder.body(value.normalized_body, d.with_names(dict(d.names)), env)
        if closed["k"] == "halt":
            return closed["value"]
        return {"k": "block", "body": closed, **builder.provenance(value.metadata)}
    expr = value.expr
    if isinstance(expr, UnionVariantTagExpr):
        result = {"k": "lit", "v": expr.variant_name, "type": builder.desc(value.metadata.type_ref, d)}
    elif isinstance(expr, LoopStateSeedExpr):
        result = {
            "k": "record",
            "type": builder.desc(value.metadata.type_ref, d),
            "fields": [
                [field.name, frontend_value(builder, field.value_expr, d, env)]
                for field in expr.fields
            ],
        }
    elif isinstance(expr, LoopStateUpdateExpr):
        names = [name for name, _ in expr.overrides]
        refs = [{"kind": "binding", "name": f"a{index}"} for index in range(len(names) + 1)]
        result_type = builder.desc(value.metadata.type_ref, d)
        result = {
            "k": "op",
            "payload": _payload(
                {
                    "kind": "record_update",
                    "record_type": result_type,
                    "base": refs[0],
                    "fields": [
                        {"name": name, "value": reference}
                        for name, reference in zip(names, refs[1:], strict=True)
                    ],
                },
                result_type,
                [result_type, *[builder.desc(value.metadata.type_ref.field_types[name], d) for name in names]],
            ),
            "args": [
                frontend_value(builder, expr.base_expr, d, env),
                *[frontend_value(builder, item, d, env) for _, item in expr.overrides],
            ],
        }
        validate_pure_expr_payload(result["payload"], max_nodes=None)
    elif isinstance(expr, ListExpr):
        result = {
            "k": "list",
            "items": [frontend_value(builder, item, d, env) for item in expr.items],
            "type": builder.desc(value.metadata.type_ref, d),
        }
    elif isinstance(expr, CompilerListNonemptyHeadExpr):
        element = builder.desc(expr.element_type_ref, d)
        result = {
            "k": "op",
            "payload": _payload(
                {
                    "kind": "list_nonempty_head",
                    "source": {"kind": "binding", "name": "a0"},
                    "element_type": element,
                    "compiler_owned": True,
                    "invariant_diagnostic": "list_nonempty_invariant_broken",
                },
                element,
                [{"kind": "list", "item": element}],
            ),
            "args": [frontend_value(builder, expr.source_expr, d, env)],
        }
        validate_pure_expr_payload(result["payload"], max_nodes=None)
    elif isinstance(expr, ListMapExpr):
        source = frontend_value(builder, expr.source_expr, d, env)
        body_env = dict(env)
        body_env[expr.binder_name] = expr.source_item_type_ref
        body_names = dict(d.names)
        binder = d.renamer.bind(expr.binder_name, authored_label=expr.binding_label, env=body_names)
        body_d = d.with_names(body_names)
        body = frontend_body(
            builder,
            expr.body_expr,
            body_d,
            body_env,
            binding_identity=expr.binding_identity,
            binder_wire=binder,
        )
        result = {
            "k": "list_map",
            "binder": binder,
            "source": source,
            "body": body,
            "type": builder.desc(value.metadata.type_ref, d),
        }
    elif isinstance(expr, PathJoinUnderExpr):
        path_desc = builder.desc(expr.path_type_ref or value.metadata.type_ref, d)
        payload = _payload(
            {
                "kind": "path_join_under",
                "path_type": path_desc,
                "child": {"kind": "binding", "name": "a0"},
            },
            path_desc,
            [{"kind": "primitive", "name": "String"}],
        )
        validate_pure_expr_payload(payload, max_nodes=None)
        result = {
            "k": "op",
            "payload": payload,
            "args": [frontend_value(builder, expr.child_expr, d, env)],
        }
    elif isinstance(expr, IfExpr):
        result = {
            "k": "select",
            "cond": frontend_value(builder, expr.condition_expr, d, env),
            "then": {"prefix": [], "value": frontend_value(builder, expr.then_expr, d, env)},
            "else": {"prefix": [], "value": frontend_value(builder, expr.else_expr, d, env)},
        }
    elif isinstance(expr, LetStarExpr):
        result = frontend_value(builder, expr, d, env)
    elif isinstance(expr, GeneratedRelpathSeedExpr):
        result = {"k": "lit", "v": expr.literal_path, "type": builder.desc(value.metadata.type_ref, d)}
    elif isinstance(expr, ProviderBundlePathExpr) and isinstance(expr.source_expr, NameExpr):
        from ..typecheck_effects import require_evaluated_provider_bundle_path_target

        require_evaluated_provider_bundle_path_target(expr, value.metadata.type_ref)
        result = {
            "k": "result_path",
            "n": d.ref(expr.source_expr.name),
            "type": builder.desc(value.metadata.type_ref, d),
        }
    elif isinstance(expr, ResourceTransitionExpr):
        raise builder.gap(
            "resource-transition",
            "resource transitions are translated by the runtime adapter",
            expr,
        )
    else:
        raise ValueError(
            f"retained surface value {type(expr).__name__} has no closed translator"
        )
    return {**result, **builder.provenance(value.metadata)}


def frontend_value(builder: Any, expr: Any, d: Any, env: Mapping[str, TypeRef]) -> dict[str, Any]:
    if isinstance(expr, NameExpr):
        return {"k": "name", "n": d.ref(expr.name), **builder.provenance(expr)}
    builder.opaque_ordinal += 1
    scope = w.WccIdentityFactory(
        owner_name=d.owner,
        lexical_owner_chain=("closed-opaque", str(builder.opaque_ordinal)),
        route_schema_version=builder.route_schema_version,
        closed_program=True,
    )
    body = _elaborate_expr_to_body(
        expr,
        scope=scope,
        type_env=d.type_env,
        value_env=env,
        workflow_return_types=builder._workflow_return_types_for(d.source_program, d.owner),
        procedure_return_types=builder.procedure_return_types,
        effect_summary=EMPTY_EFFECT_SUMMARY,
        procedure_edges_by_site={},
        compile_time_bindings={},
    )
    normalized = normalize_wcc_body_to_anf(body)
    builder._prepare_computed_capture_requests(normalized, d, d.source_program)
    closed = builder.body(normalized, d.with_names(dict(d.names)), env)
    if closed["k"] == "halt":
        return closed["value"]
    return {"k": "block", "body": closed, **builder.provenance(expr)}


def frontend_body(
    builder: Any,
    expr: Any,
    d: Any,
    env: Mapping[str, TypeRef],
    *,
    binding_identity: object | None = None,
    binder_wire: str | None = None,
) -> dict[str, Any]:
    builder.opaque_ordinal += 1
    scope = w.WccIdentityFactory(
        owner_name=d.owner,
        lexical_owner_chain=("closed-opaque", str(builder.opaque_ordinal)),
        route_schema_version=builder.route_schema_version,
        closed_program=True,
    )
    body = _elaborate_expr_to_body(
        expr,
        scope=scope,
        type_env=d.type_env,
        value_env=env,
        workflow_return_types=builder._workflow_return_types_for(d.source_program, d.owner),
        procedure_return_types=builder.procedure_return_types,
        effect_summary=EMPTY_EFFECT_SUMMARY,
        procedure_edges_by_site={},
        compile_time_bindings={},
    )
    normalized = normalize_wcc_body_to_anf(body)
    builder._prepare_computed_capture_requests(normalized, d, d.source_program)
    d, alias_prefix = builder._freeze_bound_capture(
        d,
        binding_identity,
        binder_wire,
    )
    return {
        "k": "block",
        "body": _prepend_lets(builder.body(normalized, d, env), alias_prefix),
        **builder.provenance(expr),
    }


def _prepend_lets(body: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        row["body"] = body
        body = row
    return body
