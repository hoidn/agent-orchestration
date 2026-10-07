"""Compiler-local command scopes, selected while typed arms still exist."""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace

from ..lowering.command_control_decisions import helper_capture_names
from ..lowering.command_control_summary import branch_control_summary, _binding_control_fact
from ..lowering.command_transport_decisions import (
    RUNTIME_REFERENCE, _wcc_continuation_binding_demands, wcc_binding_materialization,
)
from ..lowering.values import _resolve_inline_expr_value
from ..type_env import RecordTypeRef, UnionTypeRef, VariantCaseTypeRef
from ..wcc.anf import normalize_wcc_body_to_anf
from ..wcc import model as w
from ..wcc.model import WccCase, WccJoin, WccLet, WccNameAtom
from .names import canonical_type_descriptor
from .program import _canonical_json


_CALL_CHILD_FIELDS = {
    w.WccLet: ("bound_value", "body"),
    w.WccIf: ("condition", "then_body", "else_body"),
    w.WccJoin: ("body", "continuation"),
    w.WccJump: ("args",),
    w.WccRecJoin: ("budget", "initial_state", "body", "exhaustion"),
    w.WccLoopContinue: ("state_args",),
    w.WccLoopDone: ("result", "state"),
    w.WccHalt: ("result",),
    w.WccCall: ("args", "specialization_captures"),
    w.WccSpecializationCapture: ("value",),
    w.WccPerform: ("positional_args", "keyword_args"),
    w.WccSelect: ("condition", "then_arm", "else_arm"),
    w.WccFieldAccessAtom: ("base",),
    w.WccRecordAtom: ("fields",),
    w.WccInject: ("fields",),
    w.WccPureOp: ("args",),
    w.WccOpaqueFrontendValue: ("normalized_body",),
    w.WccProviderSupervision: ("settlement_body",),
    w.WccProviderPeerGroup: ("settlement_body",),
}


def _wcc_call_nodes(node, variants=()):
    """The owner's ordinary semantic edges, excluding source and child capsules."""
    if isinstance(node, w.WccCase):
        yield from _wcc_call_nodes(node.subject, variants)
        for arm in node.arms:
            yield from _wcc_call_nodes(arm.body, (*variants, arm.variant_name))
        return
    if isinstance(node, w.WccSelectArm):
        for binding in node.prefix:
            yield from _wcc_call_nodes(binding.bound_value, variants)
        yield from _wcc_call_nodes(node.value, variants)
        return
    if isinstance(node, (tuple, list)):
        for child in node:
            yield from _wcc_call_nodes(child, variants)
        return
    for field in _CALL_CHILD_FIELDS.get(type(node), ()):
        yield from _wcc_call_nodes(getattr(node, field), variants)
    if isinstance(node, w.WccCall) or isinstance(node, w.WccPerform) and node.perform_kind == "workflow_call":
        yield node, variants


def _call_coordinate(call, variants):
    return call.metadata.scope_id, call.metadata.node_id, tuple(variants)


def command_call_occurrences(body, call_declaration_identity):
    """Index coordinates only; no lexical facts or requests enter this table."""
    result, counts = {}, {}
    for call, variants in _wcc_call_nodes(body):
        coordinate = _call_coordinate(call, variants)
        if coordinate in result:
            raise ValueError("command call has a duplicated WCC coordinate")
        did = call_declaration_identity(call)
        encoded = _canonical_json(did)
        occurrence = counts.get(encoded, 0)
        counts[encoded] = occurrence + 1
        result[coordinate] = (did, occurrence)
    return result


def _call_preparation_callbacks(neutral, resolver, preparator):
    if preparator is None:
        return None, lambda final: None
    if resolver is None:
        raise ValueError("command call preparation requires its declaration resolver")
    inventory = command_call_occurrences(neutral, resolver)
    consumed = set()

    def consume(expr, call, context, actual_values, *, variants):
        coordinate = _call_coordinate(call, variants)
        if coordinate not in inventory or coordinate in consumed:
            raise ValueError("command call callback is unknown or repeated")
        consumed.add(coordinate)
        preparator(inventory[coordinate], expr, call, context, actual_values)

    def verify(final):
        if consumed != inventory.keys() or command_call_occurrences(final, resolver) != inventory:
            raise ValueError("command call preparation does not cover its final WCC inventory")

    return consume, verify


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

    def record_binding_demand(node, variants):
        if isinstance(node, WccLet):
            names = (node.bound_name,)
            continuation = node.body
        elif isinstance(node, WccJoin):
            names = tuple(param.name for param in node.params)
            continuation = node.continuation
        else:
            return
        for name in names:
            key = (*binding_demand_key(node.metadata, variants), name)
            result.setdefault(key[:-1], []).append((name, tuple(name in demand for demand in scanned[id(continuation)])))

    def visit(node, variants=()):
        record_binding_demand(node, variants)
        if isinstance(node, WccCase):
            visit(node.subject, variants)
            for arm in node.arms:
                visit(arm.body, (*variants, arm.variant_name))
            return
        if isinstance(node, w.WccSelectArm):
            for binding in node.prefix:
                record_binding_demand(binding, variants)
                visit(binding.bound_value, variants)
            visit(node.value, variants)
            return
        for child in _children(node):
            visit(child, variants)

    visit(body)
    return result


def runtime_binding_value(type_ref, *, facts, span, form_path):
    if isinstance(type_ref, UnionTypeRef):
        return _union_runtime_value(type_ref, facts=facts, span=span, form_path=form_path)
    if isinstance(type_ref, (RecordTypeRef, VariantCaseTypeRef)):
        return {field.name: runtime_binding_value(facts.type_env.record_field(
            type_ref, field.name, span=span, form_path=form_path),
            facts=facts, span=span, form_path=form_path) for field in type_ref.definition.fields}
    return RUNTIME_REFERENCE


def _runtime_shape(value):
    if isinstance(value, Mapping):
        return tuple((name, _runtime_shape(child)) for name, child in value.items())
    return None


def _union_runtime_value(type_ref, *, facts, span, form_path):
    values, conflicts = {}, set()
    for fields in type_ref.variant_field_types.values():
        for name, field_type in fields.items():
            value = runtime_binding_value(field_type, facts=facts, span=span, form_path=form_path)
            if name in values and _runtime_shape(values[name]) != _runtime_shape(value):
                conflicts.add(name)
            values.setdefault(name, value)
    return {"variant": RUNTIME_REFERENCE, **{name: value for name, value in values.items() if name not in conflicts}}


def _proven_runtime_value(value, old_type, new_type, *, control, operand):
    if not isinstance(old_type, UnionTypeRef) or not isinstance(new_type, VariantCaseTypeRef) or not isinstance(value, Mapping):
        return value
    payload = runtime_binding_value(new_type, facts=control,
        span=operand.metadata.source_span, form_path=operand.metadata.form_path)
    return {name: value.get(name, runtime) for name, runtime in payload.items()}


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
    values = {name: _resolve_inline_expr_value(value, local_values=values, retain_expression_facts=True)
        for name, value in values.items()}
    values.update(local_values or {})
    return operands, values


def command_loop_index_name(loop_name):
    """One unspellable compiler binder owned by the existing WCC loop."""
    return f"\0command-index:{loop_name}"


def _command_slot(expression, *, roots, source_program, index):
    from orchestrator.variables.substitution import parse_variable_expression
    from orchestrator.workflow.type_descriptor import command_boundary_row

    path, filters = parse_variable_expression(expression)
    if path == "loop.index" and index is not None:
        return {"kind": "slot", "name": ["loop-index"], "path": [],
            "filters": list(filters), "value": index}
    if not path.startswith("inputs."):
        return {"kind": "missing", "expression": expression}
    native_wire, *suffix = path[len("inputs."):].split(".")
    for source_formal, operand in roots:
        descriptor = canonical_type_descriptor(operand.metadata.type_ref, typed=source_program)
        if command_boundary_row(source_formal, descriptor, native_wire) is not None:
            return {"kind": "slot", "name": ["input", source_formal, native_wire],
                "path": suffix, "filters": list(filters), "value": operand}
    return {"kind": "missing", "expression": expression}


def _literal_command_plan(literal, *, roots, source_program, index):
    from orchestrator.variables.substitution import _ESCAPED_DOLLAR, tokenize_template

    parts = []
    for is_expression, token in tokenize_template(str(literal)):
        if is_expression:
            parts.append(_command_slot(token, roots=roots, source_program=source_program, index=index))
        else:
            text = token.replace(_ESCAPED_DOLLAR, "$")
            if text:
                if parts and parts[-1]["kind"] == "text":
                    parts[-1]["text"] += text
                else:
                    parts.append({"kind": "text", "text": text})
    return {"kind": "template", "parts": parts}


@dataclass(frozen=True)
class CommandScopeContext:
    control: object
    values: Mapping
    operands: Mapping
    demands: Mapping
    owner: str
    retained_bindings: tuple = ()
    include_command_plans: bool = False
    source_program: object = None
    command_bindings: object = None
    command_roots: tuple = ()
    command_index: object = None
    call_preparator: object = None
    io_routes: object = None
    io_bind: object = None

    def prepare_call(self, expr, call, *, variants, procedure_arguments=None):
        from ..wcc.anf import _normalize_call, _normalize_perform
        from ..wcc.model import WccCall

        if self.call_preparator is None:
            return
        if isinstance(call, WccCall):
            _, normalized = _normalize_call(call)
            expressions = tuple(argument for _, argument in procedure_arguments)
            original_args, normalized_args = call.args, normalized.args
        else:
            _, normalized = _normalize_perform(call)
            expressions = tuple(value for _, value in expr.bindings)
            original_args = tuple(value for _, value in call.keyword_args)
            normalized_args = tuple(value for _, value in normalized.keyword_args)
        actual_values = tuple(
            _resolve_inline_expr_value(argument, local_values=self.values, retain_expression_facts=True)
            if original == operand else runtime_binding_value(operand.metadata.type_ref,
                facts=self.control, span=argument.span, form_path=argument.form_path)
            for argument, original, operand in zip(expressions, original_args, normalized_args, strict=True))
        self.call_preparator(expr, normalized, self, actual_values, variants=variants)

    def plan_command(self, expr, perform):
        from ..expressions import LiteralExpr
        from ..wcc.anf import _normalize_perform

        if not self.include_command_plans:
            return perform
        payload = perform.operation_payload
        if payload["adapter_name"] is not None:
            plans = []
        else:
            binding = self.command_bindings[perform.target_name]
            offset = len(binding.stable_command)
            _, normalized = _normalize_perform(perform)
            plans = []
            for index in range(offset, len(perform.positional_args)):
                operand = perform.positional_args[index]
                resolved = _resolve_inline_expr_value(expr.argv[index], local_values=self.values, retain_expression_facts=True)
                if normalized.positional_args[index] != operand or not isinstance(resolved, LiteralExpr):
                    plans.append({"kind": "value"})
                else:
                    plans.append(_literal_command_plan(resolved.value,
                        roots=self.command_roots, source_program=self.source_program,
                        index=self.command_index))
        return replace(perform, operation_payload={**payload, "argv_transport": plans})

    def narrow(self, value_env):
        types = {name: value_env.get(name, type_ref) for name, type_ref in self.control.local_type_bindings.items()}
        operands = dict(self.operands)
        values = dict(self.values)
        control = replace(self.control, local_type_bindings=types)
        retained = list(self.retained_bindings)
        for name, type_ref in types.items():
            operand = operands.get(name)
            if operand is None or operand.metadata.type_ref == type_ref:
                continue
            original = next(row for row in reversed(retained) if row[4] == operand)
            values[name] = _proven_runtime_value(values[name], operand.metadata.type_ref, type_ref,
                control=control, operand=operand)
            operand = replace(operand, metadata=replace(operand.metadata, type_ref=type_ref))
            operands[name] = operand
            retained.append((original[0],
                operand.metadata.binding_identity, type_ref, values[name], operand))
        return replace(self, control=control, values=values,
            operands=operands, retained_bindings=tuple(retained))

    def compile_time_bind(self, expr, *, name, type_ref):
        _, value, _ = _binding_control_fact(expr, name=name, facts=self.control, local_values=self.values)
        routes = {} if self.io_routes is None else dict(self.io_routes)
        if self.io_bind is not None:
            routes[name] = self.io_bind(expr, routes)
        return replace(self, values={**self.values, name: value},
            io_routes=routes,
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
        resolved = None if expansion_owned and is_pure_projection_expr(expr) else _resolve_inline_expr_value(expr, local_values=self.values, retain_expression_facts=True)
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
            command_roots=roots, command_index=None,
            control=replace(control, local_type_bindings={name: value_env[name] for name in names},
                iteration_scope=None, workflow_name=f"%composition.{control.workflow_name}"))


def _validate_command_scope_inputs(producer_lowering_schema, closed_program,
    include_command_plans, source_program, command_bindings):
    if type(producer_lowering_schema) is not int or producer_lowering_schema not in (1, 2):
        raise ValueError("command scope analysis requires the producer's schema 1 or 2")
    if not closed_program:
        raise ValueError("command scope analysis requires closed elaboration")
    if include_command_plans and (source_program is None or command_bindings is None):
        raise ValueError("command plans require the exact source and command binding owner")


def elaborate_command_scopes(typed_body, *, incoming_command_facts,
    producer_lowering_schema, local_values=None, include_command_plans=False,
    source_program=None, command_bindings=None, command_roots=None,
    call_preparator=None, call_declaration_identity=None, command_root_names=None,
    command_index_name=None, io_routes=None, io_bind=None, **elaboration_inputs):
    """Elaborate the exact same owner twice; only the second selects arm scopes."""
    from ..wcc.elaborate import elaborate_typed_workflow_body, prepare_elaboration_call_types
    from ..wcc.model import WccIdentityFactory

    _validate_command_scope_inputs(
        producer_lowering_schema, elaboration_inputs.get("closed_program"),
        include_command_plans, source_program, command_bindings,
    )
    inputs = dict(elaboration_inputs)
    inputs.update(workflow_catalog=incoming_command_facts.workflow_catalog,
        typed_workflows_by_name=incoming_command_facts.workflows_by_name)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(typed_body, **inputs))
    prepare_call, verify_calls = _call_preparation_callbacks(neutral, call_declaration_identity, call_preparator)
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
    if command_root_names is not None:
        command_roots = tuple((formal, operands[name]) for formal, name in command_root_names.items())
    context = CommandScopeContext(facts, values, operands, continuation_binding_demands(neutral),
        "surface" if producer_lowering_schema == 1 else "wcc",
        tuple((binding_demand_key(operand.metadata, ()), typed_body.binding_environment.get(name),
            inputs["value_env"][name], values[name], operand) for name, operand in operands.items()),
        include_command_plans=include_command_plans, source_program=source_program,
        command_bindings=command_bindings,
        command_roots=tuple(operands.items()) if command_roots is None else command_roots,
        command_index=operands.get(command_index_name),
        call_preparator=prepare_call, io_routes=io_routes or {}, io_bind=io_bind)
    annotated = elaborate_typed_workflow_body(typed_body, **inputs, command_scope_context=context)
    result = normalize_wcc_body_to_anf(annotated)
    verify_calls(result)
    return result
