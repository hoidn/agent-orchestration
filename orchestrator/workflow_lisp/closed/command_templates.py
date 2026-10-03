"""Compiler-local command scopes, selected while typed arms still exist."""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace

from ..lowering.command_control_decisions import helper_capture_names, helper_capture_payload
from ..lowering.command_control_summary import branch_control_summary, _binding_control_fact, _materialized_binding_value
from ..lowering.command_transport_decisions import (
    RUNTIME_REFERENCE, _wcc_continuation_binding_demands, wcc_binding_materialization,
)
from ..lowering.values import _flatten_boundary_leaf_paths, _resolve_inline_expr_value
from ..type_env import RecordTypeRef, UnionTypeRef
from ..wcc.anf import normalize_wcc_body_to_anf
from ..wcc.model import WccCase, WccJoin, WccLet, WccNameAtom


def binding_demand_key(metadata, variants):
    """The actual WCC binder, inside its existing variant frame."""
    return (variants, metadata.scope_id, metadata.node_id, metadata.binding_identity)


def _children(node):
    if isinstance(node, Mapping):
        return node.values()
    if isinstance(node, (tuple, list)):
        return node
    if is_dataclass(node):
        return (getattr(node, field.name) for field in fields(node)
            if field.name not in {"metadata", "bound_type_ref", "binding_type_ref", "command_scope"})
    return ()


def continuation_binding_demands(body):
    """Project only the three demand bits from the ordinary neutral ANF."""
    scanned = _wcc_continuation_binding_demands(body)
    result = {}

    def visit(node, variants=()):
        if isinstance(node, WccLet):
            names = (node.bound_name,)
            continuation = node.body
        elif isinstance(node, WccJoin):
            names = tuple(param.name for param in node.params)
            continuation = node.continuation
        else:
            names = ()
        for name in names:
            key = (*binding_demand_key(node.metadata, variants), name)
            result.setdefault(key[:-1], []).append((name, tuple(name in demand for demand in scanned[id(continuation)])))
        if isinstance(node, WccCase):
            visit(node.subject, variants)
            for arm in node.arms:
                visit(arm.body, (*variants, arm.variant_name))
            return
        for child in _children(node):
            visit(child, variants)

    visit(body)
    return result


def runtime_binding_value(type_ref, *, facts, span, form_path):
    payload = helper_capture_payload(type_ref, type_env=facts.type_env, span=span, form_path=form_path)
    if payload is not None:
        return {name: runtime_binding_value(field_type, facts=facts, span=span, form_path=form_path)
            for name, field_type in payload[1].items()}
    if not isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return RUNTIME_REFERENCE
    names = tuple(name for name, _ in _flatten_boundary_leaf_paths(type_ref, generated_name="return"))
    return _materialized_binding_value(type_ref, output_names=names, facts=facts)


def _runtime_capture_names(expr, *, types, values):
    from ..wcc.elaborate import _is_compile_time_reference_value

    return tuple(name for name in helper_capture_names(expr, local_type_bindings=types)
        if not _is_compile_time_reference_value(values.get(name)))


def _initial_bindings(typed_body, *, inputs, scope, facts, procedure_edges, local_values):
    from ..wcc.elaborate import _elaborate_atomic_value, _is_compile_time_reference_value

    compile_time = inputs.get("compile_time_bindings", {})
    operands, values = {}, dict(compile_time)
    for name, type_ref in inputs["value_env"].items():
        if name in compile_time:
            if _is_compile_time_reference_value(compile_time[name]):
                continue
            operands[name] = _elaborate_atomic_value(compile_time[name], scope=scope,
                type_env=facts.type_env, value_env=inputs["value_env"],
                workflow_return_types=facts.workflow_return_types,
                procedure_return_types=facts.procedure_return_types,
                effect_summary=typed_body.effect_summary, procedure_edges_by_site=procedure_edges,
                compile_time_bindings=compile_time)
            continue
        operands[name] = WccNameAtom(metadata=scope.atom_metadata(role=f"name:{name}", type_ref=type_ref,
            source_span=typed_body.expr.span, form_path=typed_body.expr.form_path,
            binding_identity=typed_body.binding_environment.get(name)), name=name)
        values[name] = runtime_binding_value(type_ref, facts=facts,
            span=typed_body.expr.span, form_path=typed_body.expr.form_path)
    values.update(local_values or {})
    return operands, values


@dataclass(frozen=True)
class CommandScopeContext:
    control: object
    values: Mapping
    operands: Mapping
    demands: Mapping
    owner: str
    retained_bindings: tuple = ()

    def narrow(self, value_env):
        types = {name: value_env.get(name, type_ref) for name, type_ref in self.control.local_type_bindings.items()}
        operands = dict(self.operands)
        retained = list(self.retained_bindings)
        for name, type_ref in types.items():
            operand = operands.get(name)
            if operand is None or operand.metadata.type_ref == type_ref:
                continue
            original = next(row for row in reversed(retained) if row[4] == operand)
            operand = replace(operand, metadata=replace(operand.metadata, type_ref=type_ref))
            operands[name] = operand
            retained.append((original[0],
                operand.metadata.binding_identity, type_ref, self.values[name], operand))
        return replace(self, control=replace(self.control, local_type_bindings=types),
            operands=operands, retained_bindings=tuple(retained))

    def compile_time_bind(self, expr, *, name, type_ref):
        _, value, _ = _binding_control_fact(expr, name=name, facts=self.control, local_values=self.values)
        return replace(self, values={**self.values, name: value},
            control=replace(self.control, local_type_bindings={**self.control.local_type_bindings, name: type_ref}))

    def binding_demands(self, metadata, variants):
        key = binding_demand_key(metadata, variants)
        matches = self.demands.get(key, ())
        if len(matches) != 1:
            raise ValueError("command continuation has no unique retained WCC binder")
        return matches[0][1]

    def bind(self, expr, *, name, type_ref, operand, metadata, variants, expansion_owned=False, capture_source=None):
        demands = self.binding_demands(metadata, variants)
        if capture_source is not None:
            source_identity, source_type = capture_source
            matches = (row for row in reversed(self.retained_bindings)
                if row[1] == source_identity and row[2] == source_type)
            retained = next(matches, None)
            if retained is None:
                raise ValueError("command capture has no retained binder in its lexical frame")
            value = retained[3]
        elif self.owner in {"surface", "loop"}:
            _, value, _ = _binding_control_fact(expr, name=name, facts=self.control,
                local_values=self.values, capture_source=capture_source)
        else:
            value = self._wcc_binding_value(expr, demands=demands, expansion_owned=expansion_owned)
        if value is None:
            value = runtime_binding_value(type_ref, facts=self.control, span=expr.span, form_path=expr.form_path)
        return replace(self,
            control=replace(self.control, local_type_bindings={**self.control.local_type_bindings, name: type_ref}),
            values={**self.values, name: value}, operands={**self.operands, name: operand},
            retained_bindings=(*self.retained_bindings,
                (binding_demand_key(metadata, variants), metadata.binding_identity, type_ref, value, operand)))

    def _wcc_binding_value(self, expr, *, demands, expansion_owned):
        from ..conditionals import _contains_effect
        from ..expressions import NameExpr
        from ..lowering.pure_projection import is_pure_projection_expr

        if _contains_effect(expr):
            return None
        resolved = None if expansion_owned and is_pure_projection_expr(expr) else _resolve_inline_expr_value(expr, local_values=self.values)
        kind, value = wcc_binding_materialization(expr, expansion_owned=expansion_owned,
            existing_ref=self.values.get(expr.name) if isinstance(expr, NameExpr) else None,
            resolved_binding=resolved, run_ref_demand=demands[0],
            provider_context_demand=demands[1], request_input_demand=demands[2])
        return value if kind == "alias" else None

    def arm(self, expr, *, result_type, name, type_ref, operand, value_env):
        from ..wcc.elaborate import _is_compile_time_reference_value

        types = {**self.control.local_type_bindings, name: type_ref}
        control = replace(self.control, local_type_bindings=types)
        value = runtime_binding_value(type_ref, facts=control, span=expr.span, form_path=expr.form_path)
        child = replace(self, control=control, values={**self.values, name: value},
            operands={**self.operands, name: operand}, retained_bindings=(*self.retained_bindings,
                (binding_demand_key(operand.metadata, (type_ref.variant_name,)),
                    operand.metadata.binding_identity, type_ref, value, operand)))
        if self.owner != "surface" or not branch_control_summary(
            expr, result_type=result_type, facts=control, local_values=child.values,
        ):
            return None, child
        names = _runtime_capture_names(expr, types=types, values=child.values)
        roots = tuple((name, child.operands[name]) for name in names)
        values = {name: value for name, value in child.values.items() if _is_compile_time_reference_value(value)}
        values.update({name: runtime_binding_value(value_env[name], facts=control,
            span=expr.span, form_path=expr.form_path) for name in names})
        operands = dict(roots)
        retained = tuple((binding_demand_key(operand.metadata, (type_ref.variant_name,)),
            operand.metadata.binding_identity, value_env[name], values[name], operand)
            for name, operand in roots)
        return roots, replace(child, values=values, operands=operands, retained_bindings=retained,
            control=replace(control, local_type_bindings={name: value_env[name] for name in names},
                iteration_scope=None, workflow_name=f"%composition.{control.workflow_name}"))


def elaborate_command_scopes(typed_body, *, incoming_command_facts,
    producer_lowering_schema, local_values=None, **elaboration_inputs):
    """Elaborate the exact same owner twice; only the second selects arm scopes."""
    from ..wcc.elaborate import elaborate_typed_workflow_body, prepare_elaboration_call_types
    from ..wcc.model import WccIdentityFactory

    if type(producer_lowering_schema) is not int or producer_lowering_schema not in (1, 2):
        raise ValueError("command scope analysis requires the producer's schema 1 or 2")
    if not elaboration_inputs.get("closed_program"):
        raise ValueError("command scope analysis requires closed elaboration")
    inputs = dict(elaboration_inputs)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(typed_body, **inputs))
    edges, returns = prepare_elaboration_call_types(typed_body,
        resolved_procedures_by_name=inputs.get("resolved_procedures_by_name"),
        procedure_return_types=inputs.get("procedure_return_types"), closed_program=True)
    facts = replace(incoming_command_facts, closed_program=True,
        local_type_bindings=dict(inputs["value_env"]),
        workflow_return_types=inputs.get("workflow_return_types", {}), procedure_return_types=returns)
    scope = WccIdentityFactory(owner_name=inputs["owner_name"], lexical_owner_chain=("workflow",),
        route_schema_version=inputs["route_schema_version"], closed_program=True)
    operands, values = _initial_bindings(typed_body, inputs=inputs, scope=scope,
        facts=facts, procedure_edges=edges, local_values=local_values)
    context = CommandScopeContext(facts, values, operands, continuation_binding_demands(neutral),
        "surface" if producer_lowering_schema == 1 else "wcc",
        tuple((binding_demand_key(operand.metadata, ()), typed_body.binding_environment.get(name),
            inputs["value_env"][name], values[name], operand) for name, operand in operands.items()))
    annotated = elaborate_typed_workflow_body(typed_body, **inputs, command_scope_context=context)
    return normalize_wcc_body_to_anf(annotated)
