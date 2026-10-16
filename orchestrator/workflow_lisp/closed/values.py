"""Translate WCC and retained surface values into checked JSON values."""

from __future__ import annotations

from typing import Any, Mapping

from orchestrator.workflow.pure_expr import validate_pure_expr_payload
from orchestrator.workflow_lisp.type_env import TypeRef
from orchestrator.workflow_lisp.wcc import model as w


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
    elif isinstance(value, w.WccList):
        result = {
            "k": "list",
            "items": [translate_value(builder, item, d, env) for item in value.items],
            "type": builder.desc(value.metadata.type_ref, d),
        }
    elif isinstance(value, w.WccListMap):
        source = translate_value(builder, value.source, d, env)
        body_names = dict(d.names)
        binder = d.renamer.bind(value.binder_name, authored_label=value.binding_label, env=body_names)
        body_d = d.with_names(body_names)
        body_env = {**env, value.binder_name: value.binder_type_ref}
        body_d, aliases = builder._freeze_bound_capture(body_d, value.binding_identity, binder)
        result = {"k": "list_map", "binder": binder, "source": source,
            "body": {"k": "block", "body": _prepend_lets(builder.body(value.body, body_d, body_env), aliases),
                **builder.provenance(value.body_metadata)},
            "type": builder.desc(value.metadata.type_ref, d)}
    elif isinstance(value, w.WccBlock):
        closed = builder.body(value.body, d.with_names(dict(d.names)), env)
        result = closed["value"] if closed["k"] == "halt" else {"k": "block", "body": closed}
    elif isinstance(value, w.WccResultPath):
        if not isinstance(value.source, w.WccNameAtom):
            raise TypeError("WCC result path requires a named source binding")
        result = {"k": "result_path", "n": d.ref(value.source.name, value.source.metadata.binding_identity),
            "type": builder.desc(value.metadata.type_ref, d)}
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
    if op.operator == "compiler-list-nonempty-head":
        expression = {"kind": "list_nonempty_head", "source": refs[0], "element_type": result_type,
            "compiler_owned": True, "invariant_diagnostic": "list_nonempty_invariant_broken"}
    elif op.operator == "path/join-under":
        expression = {"kind": "path_join_under", "path_type": result_type, "child": refs[0]}
    elif op.operator in {"record-update", "loop-state-update"}:
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


def _prepend_lets(body: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        row["body"] = body
        body = row
    return body
