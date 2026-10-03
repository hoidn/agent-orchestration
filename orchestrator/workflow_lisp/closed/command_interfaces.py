"""Finite command decisions projected from one prepared WCC owner."""

from hashlib import sha256

from ..wcc import model as w
from .command_templates import (
    _CALL_CHILD_FIELDS, _call_coordinate, command_call_occurrences, command_loop_index_name,
)
from .program import _canonical_json


def command_interface_digest(interface):
    return sha256(_canonical_json(interface).encode()).hexdigest()


def _children(node):
    if isinstance(node, w.WccSelectArm):
        yield from (binding.bound_value for binding in node.prefix)
        yield node.value
    elif isinstance(node, (tuple, list)):
        yield from node
    else:
        yield from (getattr(node, name) for name in _CALL_CHILD_FIELDS.get(type(node), ()))


def _child_interface(call, variants, *, occurrences, child_interfaces):
    declaration, occurrence = occurrences[_call_coordinate(call, variants)]
    interface = child_interfaces[(_canonical_json(declaration), occurrence)]
    return declaration, occurrence, interface


def _is_call(node):
    return isinstance(node, w.WccCall) or (
        isinstance(node, w.WccPerform) and node.perform_kind == "workflow_call")


def _is_relevant(interface):
    return bool(interface["decisions"] or interface["captures"] or interface["native"])


def _captures_index(interface):
    return any(row[0] == ["command-loop-index"] for row in interface["captures"])


def _plans(command):
    plans = command.operation_payload.get("argv_transport")
    if plans is None:
        raise ValueError("prepared command is missing argv transport")
    return plans


def command_native_parameters(body, candidates, *, child_interfaces=None,
    child_demands=None, call_declaration_identity=None):
    """Select demanded whole roots while respecting arm namespace resets."""
    demanded, lookups = set(), False
    occurrences = command_call_occurrences(body, call_declaration_identity) if call_declaration_identity else {}

    def child_call(node, variants):
        nonlocal lookups
        declaration, occurrence = occurrences[_call_coordinate(node, variants)]
        selector = (_canonical_json(declaration), occurrence)
        lookups = bool(child_demands[selector]) or lookups
        demanded.update(row[0][1] for row in child_interfaces[selector]["captures"]
            if row[0][0] == "command-input")

    def command(node):
        nonlocal lookups
        for plan in _plans(node):
            for part in plan.get("parts", ()):
                if part["kind"] != "text":
                    lookups = True
                if part["kind"] == "slot" and part["name"][0] == "input":
                    demanded.add(part["name"][1])

    def visit(node, native=True, variants=()):
        if isinstance(node, w.WccCase):
            visit(node.subject, native, variants)
            for arm in node.arms:
                visit(arm.body, native and arm.command_scope is None, (*variants, arm.variant_name))
            return
        for child in _children(node):
            visit(child, native, variants)
        if native and isinstance(node, w.WccPerform) and node.perform_kind == "command_result":
            command(node)
        if native and child_interfaces is not None and _is_call(node):
            child_call(node, variants)

    visit(body)
    return [row for row in candidates if row[0] in demanded] if lookups else None


def command_capture_routes(body, *, child_interfaces, call_declaration_identity):
    """Demand incoming roots only until their actual arm or loop reset."""
    occurrences = command_call_occurrences(body, call_declaration_identity)
    routes = set()

    def command(node, incoming_index):
        for plan in _plans(node):
            for part in plan.get("parts", ()):
                if part["kind"] != "slot":
                    continue
                if part["name"][0] == "input":
                    routes.add(("command-input", part["name"][1]))
                elif incoming_index:
                    routes.add(("command-loop-index",))

    def visit_case(node, variants, inherited, incoming_index):
        visit(node.subject, variants, inherited, incoming_index)
        for arm in node.arms:
            retained = inherited and arm.command_scope is None
            visit(arm.body, (*variants, arm.variant_name), retained,
                incoming_index and arm.command_scope is None)

    def visit_loop(node, variants, inherited, incoming_index):
        for child in (node.budget, node.initial_state, node.exhaustion):
            visit(child, variants, inherited, incoming_index)
        visit(node.body, variants, inherited, False)

    def inherit(node, variants, incoming_index):
        if isinstance(node, w.WccPerform) and node.perform_kind == "command_result":
            command(node, incoming_index)
        if _is_call(node):
            _, _, interface = _child_interface(node, variants,
                occurrences=occurrences, child_interfaces=child_interfaces)
            routes.update(tuple(row[0]) for row in interface["captures"]
                if incoming_index or row[0] != ["command-loop-index"])

    def visit(node, variants=(), inherited=True, incoming_index=True):
        if isinstance(node, w.WccCase):
            visit_case(node, variants, inherited, incoming_index)
            return
        if isinstance(node, w.WccRecJoin):
            visit_loop(node, variants, inherited, incoming_index)
            return
        for child in _children(node):
            visit(child, variants, inherited, incoming_index)
        if inherited:
            inherit(node, variants, incoming_index)

    visit(body)
    return routes


def command_fact_demand(body, *, child_demands, call_declaration_identity):
    """The selected request needs inline facts locally or through inline children."""
    occurrences = command_call_occurrences(body, call_declaration_identity)

    def visit(node, variants=()):
        if isinstance(node, w.WccCase):
            return visit(node.subject, variants) or any(
                visit(arm.body, (*variants, arm.variant_name)) for arm in node.arms)
        if isinstance(node, w.WccPerform) and node.perform_kind == "command_result":
            return bool(_plans(node))
        if _is_call(node):
            declaration, occurrence = occurrences[_call_coordinate(node, variants)]
            if child_demands[(_canonical_json(declaration), occurrence)]:
                return True
        return any(visit(child, variants) for child in _children(node))

    return visit(body)


def command_bearing(body, *, child_bearings, call_declaration_identity):
    """Actual command descendants, including commands with no transported argv."""
    occurrences = command_call_occurrences(body, call_declaration_identity)

    def visit(node, variants=()):
        if isinstance(node, w.WccCase):
            return visit(node.subject, variants) or any(
                visit(arm.body, (*variants, arm.variant_name)) for arm in node.arms)
        if isinstance(node, w.WccPerform) and node.perform_kind == "command_result":
            return True
        if _is_call(node):
            declaration, occurrence = occurrences[_call_coordinate(node, variants)]
            if child_bearings[(_canonical_json(declaration), occurrence)]:
                return True
        return any(visit(child, variants) for child in _children(node))

    return visit(body)


def _local_inventory(body, *, occurrences, child_interfaces, child_bearings):
    """Count relevant cases and used loop binders in semantic preorder."""
    cases, loops = [], []

    def visit_case(node, variants, index):
        ordinal = len(cases)
        cases.append(False)
        subject_bearing = visit(node.subject, variants, index)
        bearing = False
        for arm in node.arms:
            arm_index = index if arm.command_scope is None else None
            bearing = visit(arm.body, (*variants, arm.variant_name), arm_index) or bearing
        cases[ordinal] = bearing
        return subject_bearing or bearing

    def visit_loop(node, variants, index):
        ordinal = len(loops)
        loops.append(False)
        owned_index = (ordinal, command_loop_index_name(node.loop_name))
        bearing = visit(node.budget, variants, index)
        bearing = visit(node.initial_state, variants, index) or bearing
        bearing = visit(node.body, variants, owned_index) or bearing
        return visit(node.exhaustion, variants, index) or bearing

    def mark_command_index(node, index):
        if index is None:
            return
        for plan in _plans(node):
            for part in plan.get("parts", ()):
                if part["kind"] == "slot" and part["name"] == ["loop-index"]:
                    if isinstance(part["value"], w.WccNameAtom) and part["value"].name == index[1]:
                        loops[index[0]] = True

    def visit(node, variants=(), index=None):
        if isinstance(node, w.WccCase):
            return visit_case(node, variants, index)
        if isinstance(node, w.WccRecJoin):
            return visit_loop(node, variants, index)
        bearing = False
        for child in _children(node):
            bearing = visit(child, variants, index) or bearing
        if isinstance(node, w.WccPerform) and node.perform_kind == "command_result":
            mark_command_index(node, index)
            return True
        if _is_call(node):
            declaration, occurrence, interface = _child_interface(node, variants,
                occurrences=occurrences, child_interfaces=child_interfaces)
            if index is not None and _captures_index(interface):
                loops[index[0]] = True
            return child_bearings[(_canonical_json(declaration), occurrence)] or bearing
        return bearing

    visit(body)
    return cases, loops


def _input_origin(formal, *, native_rows, command_capture_rows, reset):
    if reset is not None:
        ordinal, variant, roots = reset
        if any(name == formal for name, _ in roots):
            return ["arm", ordinal, variant, formal]
        raise ValueError("prepared input slot is outside its arm command scope")
    if any(row[0] == formal for row in native_rows or ()):
        return ["native", formal]
    route = ["command-input", formal]
    if any(row[0] == route for row in command_capture_rows):
        return ["capture", route]
    raise ValueError("prepared input slot has no native or capture certificate")


def command_loop_index_binders(body, *, child_interfaces, child_bearings, call_declaration_identity):
    """The existing loop owners whose body really uses its own index."""
    occurrences = command_call_occurrences(body, call_declaration_identity)
    _, bits = _local_inventory(body, occurrences=occurrences,
        child_interfaces=child_interfaces, child_bearings=child_bearings)

    def loops(node):
        if isinstance(node, w.WccRecJoin):
            yield node.loop_name
        if isinstance(node, w.WccCase):
            yield from loops(node.subject)
            for arm in node.arms:
                yield from loops(arm.body)
            return
        for child in _children(node):
            yield from loops(child)

    return frozenset(name for name, used in zip(loops(body), bits, strict=True) if used)


def _lookup_choice(part, *, native_rows, command_capture_rows, reset, index):
    if part["kind"] == "missing":
        return ["missing"]
    name = part["name"]
    if name[0] == "input":
        origin = _input_origin(name[1], native_rows=native_rows,
            command_capture_rows=command_capture_rows, reset=reset)
        return ["input", origin, name[2]]
    if index is not None and isinstance(part["value"], w.WccNameAtom) and part["value"].name == index[1]:
        return ["loop-index", ["loop", index[0]]]
    route = ["command-loop-index"]
    if reset is None and any(row[0] == route for row in command_capture_rows):
        return ["loop-index", ["capture", route]]
    raise ValueError("prepared loop index has no body binder or capture certificate")


def command_interface(body, *, native_rows, command_capture_rows, child_interfaces,
                      call_declaration_identity, child_bearings=None):
    """Return exactly the checked interface/digest preimage defined by R12."""
    occurrences = command_call_occurrences(body, call_declaration_identity)
    case_bits, loop_bits = _local_inventory(body,
        occurrences=occurrences, child_interfaces=child_interfaces,
        child_bearings={} if child_bearings is None else child_bearings)
    cases, loops = iter(case_bits), iter(loop_bits)
    decisions, counts = [], {"command": 0, "case": 0, "loop": 0}

    def visit_case(node, variants, reset, index):
        bearing = next(cases)
        ordinal = counts["case"]
        counts["case"] += bearing
        visit(node.subject, variants, reset, index)
        for arm in node.arms:
            arm_reset, arm_index = reset, index
            if bearing and arm.command_scope is not None:
                decisions.append(["arm", ordinal, arm.variant_name, "reset"])
                arm_reset, arm_index = (ordinal, arm.variant_name, arm.command_scope), None
            visit(arm.body, (*variants, arm.variant_name), arm_reset, arm_index)

    def visit_loop(node, variants, reset, index):
        demanded = next(loops)
        ordinal = counts["loop"]
        counts["loop"] += demanded
        visit(node.budget, variants, reset, index)
        visit(node.initial_state, variants, reset, index)
        owned = (ordinal, command_loop_index_name(node.loop_name)) if demanded else None
        visit(node.body, variants, reset, owned)
        visit(node.exhaustion, variants, reset, index)

    def command_rows(node, reset, index):
        ordinal = counts["command"]
        counts["command"] += 1
        for argument, plan in enumerate(_plans(node)):
            choice = ["value"]
            if plan["kind"] == "template":
                choices = [_lookup_choice(part, native_rows=native_rows,
                    command_capture_rows=command_capture_rows, reset=reset, index=index)
                    for part in plan["parts"] if part["kind"] != "text"]
                choice = ["template", choices]
            decisions.append(["arg", ordinal, argument, choice])

    def visit(node, variants=(), reset=None, index=None):
        if isinstance(node, w.WccCase):
            return visit_case(node, variants, reset, index)
        if isinstance(node, w.WccRecJoin):
            return visit_loop(node, variants, reset, index)
        for child in _children(node):
            visit(child, variants, reset, index)
        if isinstance(node, w.WccPerform) and node.perform_kind == "command_result":
            command_rows(node, reset, index)
        elif _is_call(node):
            declaration, occurrence, child = _child_interface(node, variants,
                occurrences=occurrences, child_interfaces=child_interfaces)
            if _is_relevant(child):
                decisions.append(["call", declaration, occurrence, command_interface_digest(child)])

    visit(body)
    return {"native": native_rows, "captures": command_capture_rows, "decisions": decisions}
