"""Closure and equality guards over completed, already retained preparations."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass

from .. import expressions as e
from ..type_env import TypeRef
from ..wcc import model as w
from .command_templates import _call_coordinate, command_call_occurrences
from .names import _key_type_ref, _run_ref_signatures


def _payload_fields(payload, required, optional, label):
    if not isinstance(payload, Mapping) or set(payload) - required - optional or required - set(payload):
        raise ValueError(f"prepared executable {label} has missing or unexpected payload fields")


def _closed_capture_value(value):
    """Check the wire/context subset produced for instantiated captures."""
    from orchestrator.contracts.closed_program.check import _VALUE_KEYS
    from .build import _canonical_json

    try:
        _canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("prepared capture contains an unclosed operand") from exc

    def operand(node):
        if not isinstance(node, Mapping) or node.get("k") not in {"name", "field", "record", "lit", "context"}:
            raise ValueError("prepared capture wire has an unknown executable kind")
        kind = node["k"]
        if set(node) - _VALUE_KEYS[kind]:
            raise ValueError("prepared capture wire has an unexpected executable field")
        if kind == "name":
            if not isinstance(node.get("n"), str) or not node["n"]:
                raise ValueError("prepared capture wire has no name operand")
        elif kind == "field":
            if not isinstance(node.get("path"), list) or any(not isinstance(name, str) for name in node["path"]):
                raise ValueError("prepared capture wire has no field selector")
            operand(node.get("base"))
        elif kind == "record":
            if not isinstance(node.get("type"), Mapping) or not isinstance(node.get("fields"), list):
                raise ValueError("prepared capture context has no typed fields")
            for row in node["fields"]:
                if not isinstance(row, (tuple, list)) or len(row) != 2 or not isinstance(row[0], str):
                    raise ValueError("prepared capture context has an invalid field")
                operand(row[1])
        elif kind == "lit":
            # A typed Value literal may contain JSON data; its data is not code.
            if "v" not in node or not isinstance(node.get("type"), Mapping):
                raise ValueError("prepared capture literal has no typed data")
        elif node.get("field") != "run-id":
            raise ValueError("prepared capture context has an unknown field")

    operand(value)


def _prepared_declaration_identity(call, source_program, owner_name):
    from .names import _callable_header, _find_typed_definition
    from .frontend import resolve_workflow_target

    if isinstance(call, w.WccCall):
        selected = _find_typed_definition(source_program, "procedure",
            call.specialized_callee_name or call.callee_name)
    else:
        target = resolve_workflow_target(source_program, owner_name, call.target_name)
        if target is None:
            _fail("call original declaration owner")
        _, selected, source_program = target
    if selected is None:
        _fail("call original declaration owner")
    return list(_callable_header(selected, typed=source_program)[:3])


def _closed_perform_payload(perform, builder):
    from .effects import require_closed_perform

    require_closed_perform(builder, perform)
    kind, payload = perform.perform_kind, perform.operation_payload
    if kind in {"workflow_call", "agent"}:
        if payload is not None:
            raise ValueError("prepared executable effect has an unexpected payload")
        if kind == "agent" and any(name not in {"model", "effort"} for name, _ in perform.keyword_args):
            raise ValueError("prepared executable agent policy has an unknown field")
        return
    if kind == "run_ref":
        if type(payload) not in {w.WccRunRefPayload, w.WccRunRefWorkflowPayload}:
            raise ValueError("prepared executable run-ref has an unknown payload kind")
        return
    if kind == "command_result":
        _payload_fields(payload, {"adapter_name", "adapter_inputs", "return_spec"},
            {"inputs_present", "operand_order", "argv_transport"}, "command")
        if payload["adapter_name"] is not None and not isinstance(payload["adapter_name"], str):
            raise ValueError("prepared executable command adapter name is invalid")
        if "inputs_present" in payload and type(payload["inputs_present"]) is not bool:
            raise ValueError("prepared executable command input presence is invalid")
        if "operand_order" in payload and (not isinstance(payload["operand_order"], tuple)
                or any(not isinstance(name, str) for name in payload["operand_order"])):
            raise ValueError("prepared executable command operand order is invalid")
        for name, _value in payload["adapter_inputs"]:
            if not isinstance(name, str):
                raise ValueError("prepared executable command input name is invalid")
        for plan in payload.get("argv_transport", ()):
            if not isinstance(plan, Mapping):
                raise ValueError("prepared executable command transport payload is missing")
            if plan.get("kind") == "value":
                _payload_fields(plan, {"kind"}, set(), "command value plan")
                continue
            _payload_fields(plan, {"kind", "parts"}, set(), "command template")
            if plan["kind"] != "template" or not isinstance(plan["parts"], list):
                raise ValueError("prepared executable command transport has an unknown kind")
            for part in plan["parts"]:
                if not isinstance(part, Mapping):
                    raise ValueError("prepared executable command transport part is missing")
                part_kind = part.get("kind")
                if part_kind == "slot":
                    _payload_fields(part, {"kind", "name", "path", "filters", "value"}, set(), "command slot")
                    if any(not isinstance(part[field], list) or any(not isinstance(item, str) for item in part[field])
                            for field in ("name", "path", "filters")):
                        raise ValueError("prepared executable command slot selector is invalid")
                    name = part["name"]
                    if name != ["loop-index"] and (len(name) != 3 or name[0] != "input"):
                        raise ValueError("prepared executable command slot has an unknown selector")
                elif part_kind in {"text", "missing"}:
                    field = "text" if part_kind == "text" else "expression"
                    _payload_fields(part, {"kind", field}, set(), "command text")
                    if not isinstance(part[field], str):
                        raise ValueError("prepared executable command text is invalid")
                else:
                    raise ValueError("prepared executable command transport part has an unknown kind")
        return
    allowed = {"prompt_application", "prompt_dependencies", "model", "effort", "timeout_sec", "delivery",
        "session_artifact", "context_expr", "capture_context", "materialization_attempts"}
    if kind == "agent_turn":
        allowed.add("agent_origins")
    _payload_fields(payload, {"return_spec"}, allowed, "provider")
    application = payload.get("prompt_application")
    if application is not None:
        _payload_fields(application, {"template", "fills"}, set(), "prompt application")
        if not isinstance(application["template"], str) or not isinstance(application["fills"], (tuple, list)):
            raise ValueError("prepared executable prompt application is invalid")
        for row in application["fills"]:
            _payload_fields(row, {"name", "kind", "type_ref", "value", "renderer_id", "output_role", "placeholder_ordinals"},
                set(), "prompt fill")
            if (not isinstance(row["name"], str) or row["kind"] not in {"doc", "text", "value", "path"}
                    or row["type_ref"] is None or row["output_role"] not in {"none", "required_string_file"}
                    or row["renderer_id"] is not None and not isinstance(row["renderer_id"], str)
                    or not isinstance(row["placeholder_ordinals"], (tuple, list))
                    or any(type(index) is not int or index < 0 for index in row["placeholder_ordinals"])):
                raise ValueError("prepared executable prompt fill has invalid static facts")
    elif not isinstance(perform.prompt_name, str):
        raise ValueError("prepared executable provider prompt is missing")
    dependencies = payload.get("prompt_dependencies")
    if dependencies is not None:
        if type(dependencies) is not w.WccPromptDependencyPayload or dependencies.position not in {"append", "prepend"}:
            raise ValueError("prepared executable prompt dependency payload is invalid")
        if dependencies.instruction is not None and not isinstance(dependencies.instruction, str):
            raise ValueError("prepared executable dependency instruction is invalid")
        for row in dependencies.rows:
            if type(row) is not w.WccPromptDependencyRow or row.role not in {"required", "optional"} or type(row.authored_index) is not int or row.authored_index < 0:
                raise ValueError("prepared executable prompt dependency row is invalid")
    if kind == "agent_turn" and (not isinstance(payload.get("agent_origins"), tuple)
            or not payload["agent_origins"] or any(not isinstance(name, str) for name in payload["agent_origins"])):
        raise ValueError("prepared executable agent origins are missing")


def assert_closed_preparation(body, children, *, context, builder):
    """Check the completed entry/request graph, without consulting executable source."""
    from ..diagnostics import records_defect_provenance
    from ..expressions import ResourceTransitionExpr
    from orchestrator.workflow.pure_expr import PURE_EXPR_OPERATOR_CATALOG
    from .command_templates import _wcc_semantic_children

    value_types = {w.WccLiteralAtom, w.WccNameAtom, w.WccFieldAccessAtom, w.WccRecordAtom,
        w.WccInject, w.WccPureOp, w.WccSelect, w.WccList, w.WccListMap, w.WccBlock, w.WccResultPath}
    body_types = {w.WccLet, w.WccCase, w.WccIf, w.WccJoin, w.WccJump, w.WccLoopContinue,
        w.WccLoopDone, w.WccRecJoin, w.WccParallelMap, w.WccHalt}
    binding_types = value_types | {w.WccPerform, w.WccCall, w.WccProviderSupervision, w.WccProviderPeerGroup}
    domains = {"value": value_types, "body": body_types, "binding": binding_types,
        "arm": {w.WccCaseArm, w.WccSelectArm}, "capture": {w.WccSpecializationCapture}}
    @records_defect_provenance("closed-program")
    def operand(node, domain="value", *, children, inventory, seen, variants=()):
        if type(node) is w.WccOpaqueFrontendValue and isinstance(node.expr, ResourceTransitionExpr):
            raise builder.gap("resource-transition", "resource transitions are translated by the runtime adapter", node.expr)
        if type(node) not in domains[domain]:
            raise ValueError(f"prepared executable {domain} operand has unknown or unclosed shape {type(node).__name__}")
        coordinate = (id(node), variants)
        if coordinate in seen:
            return
        seen.add(coordinate)
        if type(node) is w.WccProviderSupervision:
            raise builder.gap("with-live-providers", "provider supervision has no closed form in this release", node)
        if type(node) is w.WccProviderPeerGroup:
            raise builder.gap("with-live-provider-peers", "provider peer groups have no closed form in this release", node)
        if type(node) not in {w.WccSelectArm, w.WccCaseArm, w.WccSpecializationCapture}:
            if type(node.metadata) is not w.WccNodeMetadata or node.metadata.type_ref is None:
                raise ValueError("prepared executable operand has no typed metadata")
        if type(node) is w.WccLiteralAtom and (type(node.value) not in {str, int, float, bool}
                or node.literal_kind not in {"string", "int", "float", "bool", "enum", "variant-tag"}):
            raise ValueError("prepared executable literal has an unknown kind or value")
        if type(node) is w.WccNameAtom and (not isinstance(node.name, str) or not node.name):
            raise ValueError("prepared executable name operand is missing")
        if type(node) is w.WccIf and node.condition_shape is not None:
            raise ValueError("prepared executable conditional retains a frontend classification")
        if type(node) is w.WccPureOp:
            if node.operator in {"record-update", "loop-state-update"}:
                valid = len(node.args) == len(node.field_names) + 1
            elif node.operator in {"path/join", "path/join-under", "compiler-list-nonempty-head"}:
                valid = len(node.args) == (2 if node.operator == "path/join" else 1)
            else:
                spec = PURE_EXPR_OPERATOR_CATALOG.get(node.operator)
                valid = spec is not None and len(node.args) >= spec.min_arity and (spec.max_arity is None or len(node.args) <= spec.max_arity)
            if not valid:
                raise ValueError("prepared executable pure operation has an unknown kind or missing operand")
        if type(node) is w.WccPerform:
            _closed_perform_payload(node, builder)
            for child in w.perform_payload_values(node.perform_kind, node.operation_payload):
                operand(child, children=children, inventory=inventory, seen=seen, variants=variants)
        for field, child in _wcc_semantic_children(node):
            domain = ("body" if field in {"body", "then_body", "else_body", "continuation", "exhaustion", "workspace_body", "settlement_body"}
                else "binding" if field == "bound_value" else "arm" if field in {"arm", "then_arm", "else_arm"}
                else "capture" if field == "specialization_captures" else "value")
            child_variants = (*variants, child.variant_name) if type(child) is w.WccCaseArm else variants
            operand(child, domain, children=children, inventory=inventory, seen=seen, variants=child_variants)
        if type(node) is w.WccCall or type(node) is w.WccPerform and node.perform_kind == "workflow_call":
            coordinate = _call_coordinate(node, variants)
            if coordinate not in inventory:
                raise ValueError("prepared operand has an unknown executable call")
            declaration, occurrence = inventory[coordinate]
            request = children[(_canonical_json(declaration), occurrence)]
            check_request(request.prepared_body, request.prepared_children, request)

    from .build import _canonical_json

    seen_requests = set()

    def check_request(prepared_body, prepared_children, owner):
        if id(owner) in seen_requests:
            return
        seen_requests.add(id(owner))
        if prepared_body is None or not isinstance(prepared_children, Mapping):
            raise ValueError("closed preparation requires a prepared body and child table")
        if hasattr(owner, "prepared_body") and any(getattr(owner, name) is None for name in (
                "computed_capture_sources", "computed_capture_requests_by_alias", "reference_capture_aliases")):
            raise ValueError("call emission requires completed capture preparation")
        callable_def = getattr(owner, "procedure", None) or getattr(owner, "workflow", None)
        owner_name = callable_def.definition.name if callable_def is not None else owner.owner
        inventory = command_call_occurrences(prepared_body,
            lambda call: _prepared_declaration_identity(call, owner.source_program, owner_name))
        if set(prepared_children) != {(_canonical_json(declaration), occurrence)
                for declaration, occurrence in inventory.values()}:
            raise ValueError("prepared child table does not cover its executable call inventory")
        operands = {"children": prepared_children, "inventory": inventory, "seen": set()}
        operand(prepared_body, "body", **operands)
        for rows in (owner.computed_capture_requests_by_alias or {}).values():
            for recipe in rows:
                if recipe.prepared_value is None:
                    raise ValueError("computed capture has no prepared value recipe")
                operand(recipe.prepared_value, **operands)
        for value in getattr(owner, "prepared_closed_values", ()):
            operand(value, **operands)
        for value in getattr(owner, "arguments", None) or ():
            operand(value, **operands)
        for capture in getattr(owner, "captures", None) or ():
            value = capture.value
            if value is None:
                identity = capture.identity
                if hasattr(owner, "workflow"):
                    # Context forwarding retains positions and declared context names,
                    # rather than an executable expression.
                    if type(identity) is not int and (not isinstance(identity, tuple)
                            or not identity or identity[0] not in {"caller-context", "forwarded-context"}):
                        raise ValueError("prepared workflow capture has no retained context recipe")
                elif builder._is_command_capture(capture):
                    operand(identity, **operands)
                else:
                    if not isinstance(identity, tuple) or not identity:
                        raise ValueError("prepared capture has no retained lexical recipe")
                    kind = identity[0]
                    if kind == "lexical-capture" and len(identity) == 2:
                        operand(identity[1], **operands)
                    elif kind in {"creation-alias", "forwarded-capture"} and len(identity) == 2:
                        if type(identity[1]) is not (str if kind == "creation-alias" else int):
                            raise ValueError("prepared capture has an invalid retained lexical recipe")
                    elif kind in {"creation", "bind-proc"} and len(identity) == 3:
                        if type(identity[1]) is not int or not isinstance(identity[2], (str, tuple)):
                            raise ValueError("prepared capture has an invalid retained creation recipe")
                    else:
                        raise ValueError("prepared capture has no retained lexical recipe")
            elif isinstance(value, Mapping):
                _closed_capture_value(value)
            else:
                operand(value, **operands)
        return inventory

    return check_request(body, children, context)


def _fail(path):
    raise ValueError(f"contradictory prepared bodies at {path}")


def _same(left, right, path):
    if not _strict_equal(left, right):
        _fail(path)


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        return left.keys() == right.keys() and all(
            _strict_equal(child, right[key]) for key, child in left.items())
    if isinstance(left, (tuple, list)):
        return len(left) == len(right) and all(_strict_equal(a, b)
            for a, b in zip(left, right, strict=True))
    return left == right


def _frame():
    return {"names": ({}, {}), "identities": ({}, {}), "targets": ({}, {}),
        "roots": ({}, {}), "index": (None, None), "variants": (),
        "retention_demands": (frozenset(), frozenset()), "retention_tokens": (set(), set())}


def _copy_frame(frame):
    return {**frame, **{key: tuple(dict(row) for row in frame[key])
        for key in ("names", "identities", "targets", "roots")}}


def _bind(frame, names, identities, token, *, namespace="names"):
    local = _copy_frame(frame)
    for side, name in enumerate(names):
        local[namespace][side][name] = token
        if identities[side] is not None:
            local["identities"][side][identities[side]] = token
            _retain_token(local, side, identities[side], token)
    return local


def _retain_token(frame, side, identity, token):
    if identity in frame["retention_demands"][side]:
        frame["retention_tokens"][side].add(token)


def _reference(name, identity, frame, side, *, namespace="names"):
    if identity is not None:
        if identity not in frame["identities"][side]:
            _fail("retained binding owner")
        return frame["identities"][side][identity]
    return frame[namespace][side].get(name, ("free", name))


class _Comparison:
    def __init__(self, requests, builder):
        self.requests, self.builder = requests, builder
        self.owners = tuple(row.source_program for row in requests)
        self.callables = tuple(row.procedure if hasattr(row, "procedure") else row.workflow
            for row in requests)
        self.inventories = tuple(command_call_occurrences(row.prepared_body,
            lambda call, side=side: self.declaration_identity(call, side))
            for side, row in enumerate(requests))

    def declaration_identity(self, call, side):
        return _prepared_declaration_identity(call, self.owners[side],
            self.callables[side].definition.name)

    def types(self, left, right, path, owners=None):
        from ..loops import LoopControlTypeRef

        if type(left) is not type(right):
            _fail(path)
        if left is None:
            return
        if isinstance(left, LoopControlTypeRef):
            self.types(left.state_type_ref, right.state_type_ref, path + ".state", owners)
            self.types(left.result_type_ref, right.result_type_ref, path + ".result", owners)
            return
        owners = self.owners if owners is None else owners
        projected = tuple(_key_type_ref(ref, typed=owner,
            run_ref_signatures=_run_ref_signatures(owner))
            for ref, owner in zip((left, right), owners, strict=True))
        _same(*projected, path)

    def seed(self):
        frame = _frame()
        frame["retention_demands"] = tuple(row.retained_capture_bindings for row in self.requests)
        for side, request in enumerate(self.requests):
            callable_def = self.callables[side]
            retained = callable_def.typed_body.binding_environment or {}
            aliases = self.builder._runtime_capture_names(callable_def, request.captures,
                self.owners[side]) if hasattr(request, "procedure") else {}
            for name, index in aliases.items():
                frame["names"][side][name] = ("capture", index)
            for index, capture in enumerate(request.captures):
                frame["names"][side][self.builder._capture_source(index)] = ("capture", index)
                if capture.source_name is not None:
                    frame["names"][side][capture.source_name] = ("capture", index)
                for route in capture.routes:
                    self.seed_route(frame, side, route, index)
            for index, (name, _) in enumerate(callable_def.signature.params):
                frame["names"][side][name] = ("param", index)
            for name, identity in retained.items():
                if name in frame["names"][side]:
                    frame["identities"][side][identity] = frame["names"][side][name]
            for source_name, identity, type_ref in getattr(request, "capture_source_bindings", ()):
                names = {self.builder._capture_source(index): index for index in range(len(request.captures))}
                if identity is None or source_name not in names:
                    _fail("capture source slot owner")
                index = names[source_name]
                self.types(type_ref, request.captures[index].type_ref,
                    f"capture source[{index}].type", (self.owners[side], self.owners[side]))
                token = ("capture", index)
                existing = frame["identities"][side].get(identity)
                if existing is not None and existing != token:
                    _fail("capture source origin has incompatible slots")
                frame["identities"][side][identity] = token
            self.seed_native(frame, side, request)
        self.seed_retention(frame)
        return frame

    @staticmethod
    def seed_retention(frame):
        for side, identities in enumerate(frame["identities"]):
            for identity, token in identities.items():
                _retain_token(frame, side, identity, token)

    @staticmethod
    def retention(frame):
        for demands, tokens in zip(frame["retention_demands"], frame["retention_tokens"], strict=True):
            if not isinstance(demands, frozenset) or len(demands) != len(tokens):
                _fail("retention binding owner")
        _same(*frame["retention_tokens"], "retention bindings")

    def seed_route(self, frame, side, route, index):
        if route[0] == "parameter":
            frame["names"][side][route[1]] = ("capture", index)
        elif route[0] in {"command-input", "command-loop-index"}:
            name = self.builder._command_capture_source(route)
            frame["names"][side][name] = ("capture", index)
            if route[0] == "command-input":
                frame["roots"][side][route[1]] = name
            else:
                frame["index"] = tuple(name if row == side else value
                    for row, value in enumerate(frame["index"]))

    def seed_native(self, frame, side, request):
        names = [self.builder._capture_source(index) for index in range(len(request.captures))]
        names.extend(name for name, _ in self.callables[side].signature.params)
        for formal, index in request.command_params or ():
            frame["roots"][side][formal] = names[index]

    def header(self):
        left, right = self.requests
        for field in ("key", "command_interface", "command_params", "argument_indices"):
            _same(getattr(left, field, None), getattr(right, field, None), field)
        self.projection_obligations()
        _same(len(left.captures), len(right.captures), "captures.length")
        for index, (a, b) in enumerate(zip(left.captures, right.captures, strict=True)):
            self.types(a.type_ref, b.type_ref, f"capture[{index}].type",
                (a.type_program or self.owners[0], b.type_program or self.owners[1]))
            _same(a.routes, b.routes, f"capture[{index}].routes")
        configs = tuple(self.configuration(owner, callable_def.definition.name)
            for owner, callable_def in zip(self.owners, self.callables, strict=True))
        _same(*configs, "configuration")

    def projection_obligations(self):
        rows = tuple(getattr(request, "projection_type_obligations", ()) for request in self.requests)
        _same(len(rows[0]), len(rows[1]), "projection_obligations.length")
        for index, (left, right) in enumerate(zip(*rows, strict=True)):
            _same(left[0], right[0], f"projection_obligations[{index}].formal")
            self.types(left[1], right[1], f"projection_obligations[{index}].type", (left[2], right[2]))

    def configuration(self, owner, name):
        from .program import canonical_configuration, logical_asset_base_for_module

        module = self.builder._module_for_owner(owner, name)
        bindings, origins = self.builder._command_bindings(owner, module)
        externs = owner.module_externs.get(module, {})
        if not externs and module == owner.entry_module:
            externs = owner.externs
        return canonical_configuration(bindings, origins=origins, externs=externs,
            asset_base=logical_asset_base_for_module(module))

    def walk(self, left, right, frame, path):
        if type(left) is not type(right):
            _fail(path)
        handler = getattr(self, type(left).__name__, None)
        if handler is not None:
            handler(left, right, frame, path)
        elif isinstance(left, TypeRef.__args__):
            self.types(left, right, path)
        elif isinstance(left, Mapping):
            self.mapping(left, right, frame, path)
        elif isinstance(left, (tuple, list)):
            self.sequence(left, right, frame, path)
        elif is_dataclass(left):
            self.record(left, right, frame, path)
        else:
            _same(left, right, path)

    def sequence(self, left, right, frame, path):
        _same(len(left), len(right), path + ".length")
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            self.walk(a, b, frame, f"{path}[{index}]")

    def mapping(self, left, right, frame, path):
        _same(tuple(left), tuple(right), path + ".keys")
        for key in left:
            self.walk(left[key], right[key], frame, f"{path}.{key}")

    def record(self, left, right, frame, path, skip=()):
        if type(left).__module__.startswith("orchestrator.workflow_lisp."):
            skip = (*skip, "span", "form_path", "expansion_stack", "authored_callee_span")
        if type(left).__module__ == e.__name__:
            skip = (*skip, "binding_identity")
        for field in fields(left):
            if field.name not in skip:
                self.walk(getattr(left, field.name), getattr(right, field.name), frame,
                    f"{path}.{field.name}")

    def WccNodeMetadata(self, left, right, frame, path):
        self.types(left.type_ref, right.type_ref, path + ".type")
        _same(left.binding_label, right.binding_label, path + ".binding_label")

    def WccNameAtom(self, left, right, frame, path):
        self.WccNodeMetadata(left.metadata, right.metadata, frame, path + ".metadata")
        _same(_reference(left.name, left.metadata.binding_identity, frame, 0),
            _reference(right.name, right.metadata.binding_identity, frame, 1), path)

    def name(self, left, right, frame, path, namespace="names"):
        _same(_reference(left, None, frame, 0, namespace=namespace),
            _reference(right, None, frame, 1, namespace=namespace), path)

    def WccLet(self, left, right, frame, path):
        self.record(left, right, frame, path, ("bound_name", "body"))
        local = _bind(frame, (left.bound_name, right.bound_name),
            (left.metadata.binding_identity, right.metadata.binding_identity), path)
        local = self.creation_recipes((left.bound_name, right.bound_name), local, path + ".creations")
        self.walk(left.body, right.body, local, path + ".body")

    def WccSelectArm(self, left, right, frame, path):
        _same(len(left.prefix), len(right.prefix), path + ".prefix.length")
        local = frame
        for index, (a, b) in enumerate(zip(left.prefix, right.prefix, strict=True)):
            field = f"{path}.prefix[{index}]"
            self.record(a, b, local, field, ("bound_name", "body"))
            local = _bind(local, (a.bound_name, b.bound_name),
                (a.metadata.binding_identity, b.metadata.binding_identity), field)
            local = self.creation_recipes((a.bound_name, b.bound_name), local, field + ".creations")
        self.walk(left.value, right.value, local, path + ".value")

    def WccIf(self, left, right, frame, path):
        self.record(left, right, frame, path,
            ("condition_shape", "then_proof_context", "else_proof_context"))

    def WccCaseArm(self, left, right, frame, path):
        self.record(left, right, frame, path,
            ("binding_name", "binding_identity", "body", "command_scope"))
        local = _bind(frame, (left.binding_name, right.binding_name),
            (left.binding_identity, right.binding_identity), path)
        local["variants"] = (*frame["variants"], left.variant_name)
        self.walk(left.command_scope, right.command_scope, local, path + ".command_scope")
        if left.command_scope is not None:
            local["roots"] = (dict(left.command_scope), dict(right.command_scope))
            local["index"] = (None, None)
        self.walk(left.body, right.body, local, path + ".body")

    def parameters(self, left, right, frame, path, identities):
        _same(len(left), len(right), path + ".length")
        local = frame
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            self.types(a.type_ref, b.type_ref, f"{path}[{index}].type")
            local = _bind(local, (a.name, b.name),
                identities if len(left) == 1 else (None, None), (path, index))
        return local

    def WccJoin(self, left, right, frame, path):
        self.walk(left.metadata, right.metadata, frame, path + ".metadata")
        local = _bind(frame, (left.join_name, right.join_name), (None, None),
            path, namespace="targets")
        self.walk(left.body, right.body, local, path + ".body")
        local = self.parameters(left.params, right.params, local, path + ".params",
            (left.metadata.binding_identity, right.metadata.binding_identity))
        self.walk(left.continuation, right.continuation, local, path + ".continuation")

    def WccRecordAtom(self, left, right, frame, path):
        if left.type_name == right.type_name:
            return self.record(left, right, frame, path)
        from ..type_env import RecordTypeRef
        from .names import canonical_type_descriptor

        for side, value in enumerate((left, right)):
            resolved, retained = value.resolved_type, value.metadata.type_ref
            if not isinstance(resolved, RecordTypeRef) or not isinstance(retained, RecordTypeRef):
                _fail(path + ".constructor type")
            _same(value.type_name, resolved.name, path + ".constructor name")
            _same(resolved.name, retained.name, path + ".constructor owner")
            owner = self.owners[side]
            _same(canonical_type_descriptor(resolved, typed=owner),
                canonical_type_descriptor(retained, typed=owner), path + ".constructor descriptor")
            self.types(resolved, retained, path + ".constructor type", (owner, owner))
        self.record(left, right, frame, path, ("type_name",))

    def WccListMap(self, left, right, frame, path):
        self.record(left, right, frame, path, ("binder_name", "binding_identity", "body"))
        local = _bind(frame, (left.binder_name, right.binder_name),
            (left.binding_identity, right.binding_identity), path)
        self.walk(left.body, right.body, local, path + ".body")

    def WccParallelMap(self, left, right, frame, path):
        from .command_templates import command_parallel_index_name

        self.record(left, right, frame, path,
            ("binder_name", "binding_identity", "workspace_body", "body"))
        local = _bind(frame, (left.binder_name, right.binder_name),
            (left.binding_identity, right.binding_identity), path)
        workspace = {**local, "index": (None, None)}
        self.walk(left.workspace_body, right.workspace_body, workspace, path + ".workspace_body")
        indexes = tuple(command_parallel_index_name(row.metadata.node_id) for row in (left, right))
        local = _bind(local, indexes, (None, None), (path, "index"))
        local["index"] = indexes
        self.walk(left.body, right.body, local, path + ".body")

    def WccRecJoin(self, left, right, frame, path):
        from .command_templates import command_loop_index_name

        self.record(left, right, frame, path, ("loop_name", "params", "body", "exhaustion"))
        local = _bind(frame, (left.loop_name, right.loop_name), (None, None),
            path, namespace="targets")
        local = self.parameters(left.params, right.params, local, path + ".params",
            (left.metadata.binding_identity, right.metadata.binding_identity))
        self.walk(left.exhaustion, right.exhaustion, local, path + ".exhaustion")
        index_names = tuple(command_loop_index_name(row.loop_name) for row in (left, right))
        local = _bind(local, index_names, (None, None), (path, "index"))
        local["index"] = index_names
        self.walk(left.body, right.body, local, path + ".body")

    def WccJump(self, left, right, frame, path):
        self.name(left.join_name, right.join_name, frame, path + ".target", "targets")
        self.record(left, right, frame, path, ("join_name",))

    def WccLoopContinue(self, left, right, frame, path):
        self.name(left.target_name, right.target_name, frame, path + ".target", "targets")
        self.record(left, right, frame, path, ("target_name",))

    def child(self, call, frame, side):
        did, occurrence = self.inventories[side][_call_coordinate(call, frame["variants"])]
        from .build import _canonical_json

        return self.requests[side].prepared_children[(_canonical_json(did), occurrence)]

    def calls(self, left, right, frame, path):
        children = tuple(self.child(call, frame, side) for side, call in enumerate((left, right)))
        _same(children[0].key, children[1].key, path + ".child.key")
        self.command_sources(children, frame, path)
        return children

    def command_sources(self, children, frame, path):
        for capture in children[0].captures:
            for route in capture.routes:
                self.command_source(route, frame, path)

    def command_source(self, route, frame, path):
        if route[0] == "command-input":
            values = tuple(roots[route[1]] for roots in frame["roots"])
        elif route[0] == "command-loop-index":
            values = frame["index"]
        else:
            return
        if isinstance(values[0], str):
            self.name(*values, frame, path + ".command source")
        else:
            self.walk(*values, frame, path + ".command source")

    def WccCall(self, left, right, frame, path):
        children = self.calls(left, right, frame, path)
        self.walk(left.metadata, right.metadata, frame, path + ".metadata")
        operands = tuple(tuple(call.args[index] for index in child.argument_indices)
            for call, child in zip((left, right), children, strict=True))
        self.walk(*operands, frame, path + ".args")
        self.walk(left.specialization_captures, right.specialization_captures,
            frame, path + ".captures")
        self.walk(children[0].prepared_closed_values, children[1].prepared_closed_values,
            frame, path + ".closed operands")
        self.capture_inputs(children, frame, path + ".capture inputs")

    def capture_inputs(self, children, frame, path):
        for index, (left, right) in enumerate(zip(children[0].captures, children[1].captures, strict=True)):
            if self.builder._is_command_capture(left):
                continue
            values = []
            for side, capture in enumerate((left, right)):
                value = capture.value
                if value is None:
                    identity = capture.identity
                    if identity[0] == "lexical-capture":
                        value = identity[1]
                    elif identity[0] == "creation-alias":
                        value = ("name", _reference(identity[1], None, frame, side))
                    elif identity[0] in {"creation", "bind-proc"}:
                        formal = identity[2] if identity[0] == "creation" else (identity[2],)
                        name = self.requests[side].computed_capture_sources[(identity[1], formal)]
                        value = ("name", _reference(name, None, frame, side))
                    elif identity[0] == "forwarded-capture":
                        value = ("capture", identity[1])
                    else:
                        _fail(path + ".recipe")
                values.append(value)
            self.walk(*values, frame, f"{path}[{index}]")

    def creation_recipes(self, names, frame, path):
        rows = tuple((request.computed_capture_requests_by_alias or {}).get(name, ())
            for request, name in zip(self.requests, names, strict=True))
        _same(len(rows[0]), len(rows[1]), path + ".length")
        result = frame
        for index, (a, b) in enumerate(zip(*rows, strict=True)):
            field = f"{path}[{index}]"
            _same(a.formal, b.formal, field + ".formal")
            self.types(a.type_ref, b.type_ref, field + ".type")
            local = self.creation_aliases((a.source_aliases, b.source_aliases), result, field)
            self.walk(a.prepared_value, b.prepared_value, local, field + ".value")
            result = _bind(result, (a.source_name, b.source_name), (None, None), field)
        return result

    def creation_aliases(self, aliases, frame, path):
        local = _copy_frame(frame)
        _same(len(aliases[0]), len(aliases[1]), path + ".aliases.length")
        for index, ((a, left), (b, right)) in enumerate(zip(
                aliases[0].items(), aliases[1].items(), strict=True)):
            tokens = (_reference(left, None, frame, 0), _reference(right, None, frame, 1))
            _same(*tokens, f"{path}.aliases[{index}]")
            local["names"][0][a], local["names"][1][b] = tokens
        # The existing insertion rule selects the final ordered source alias.
        return local

    def WccSpecializationCapture(self, left, right, frame, path):
        self.record(left, right, frame, path, ("source_name", "source_binding"))
        identities = tuple(getattr(row.source_binding, "source_binding_identity", None)
            for row in (left, right))
        if any(identity is not None for identity in identities):
            tokens = tuple(_reference(row.source_name, identity, frame, side)
                for side, (row, identity) in enumerate(zip((left, right), identities, strict=True)))
            _same(*tokens, path + ".source binding")

    def WccPerform(self, left, right, frame, path):
        if left.perform_kind == "workflow_call":
            self.calls(left, right, frame, path)
            self.record(left, right, frame, path, ("target_name",))
        elif left.perform_kind == "run_ref":
            self.record(left, right, frame, path, ("returns_type_name", "operation_payload"))
            self.run_ref_header(left.operation_payload, right.operation_payload, path + ".payload")
            self.run_ref_inputs(left, right, path + ".inputs")
        else:
            self.record(left, right, frame, path)

    def run_ref_header(self, left, right, path):
        from orchestrator.workflow.run_ref.source import canonical_source_request
        from orchestrator.workflow_lisp.wcc.model import WccRunRefWorkflowPayload

        _same(type(left), type(right), path + ".mode")
        if isinstance(left, WccRunRefWorkflowPayload):
            # The `:commit` operand is a positional argument compared with the perform.
            for name in ("repo", "workflow_name", "policy", "allow_nested_structures"):
                _same(getattr(left, name), getattr(right, name), f"{path}.{name}")
            return
        _same(canonical_source_request(left.source), canonical_source_request(right.source), path + ".source")
        _same(left.program.record, right.program.record, path + ".program")
        _same(left.allow_nested_structures, right.allow_nested_structures, path + ".nested")

    def run_ref_inputs(self, left, right, path):
        from .names import run_ref_outcome_result

        rows = tuple((run_ref_outcome_result(row.metadata.type_ref) or row.metadata.type_ref).run_ref_origin[1]
            for row in (left, right))
        for perform, inputs in zip((left, right), rows, strict=True):
            names = tuple(name for name, _ in inputs)
            _same(names, tuple(name for name, _ in perform.keyword_args), path + ".operands")
            _same(names, tuple(name for name, _ in perform.operation_payload.input_type_descriptors), path + ".descriptor names")
        _same(len(rows[0]), len(rows[1]), path + ".length")
        for index, (a, b) in enumerate(zip(*rows, strict=True)):
            _same(a[0], b[0], path + ".formal")
            self.types(a[1], b[1], f"{path}[{index}].type")

    def WccRunRefPayload(self, left, right, frame, path):
        self.run_ref_header(left, right, path)
        self.walk(left.input_type_descriptors, right.input_type_descriptors, frame, path + ".inputs")

    def NameExpr(self, left, right, frame, path):
        self.name(left.name, right.name, frame, path)

    def LetStarExpr(self, left, right, frame, path):
        _same(len(left.bindings), len(right.bindings), path + ".bindings.length")
        self.walk(left.condition_normalization_input, right.condition_normalization_input,
            frame, path + ".condition input")
        local = frame
        for index, (a, b) in enumerate(zip(left.bindings, right.bindings, strict=True)):
            field = f"{path}.bindings[{index}]"
            self.frontend_binding_value(left, right, index, local, field + ".value")
            labels = tuple(row.binding_labels[index] if index < len(row.binding_labels) else None
                for row in (left, right))
            _same(*labels, field + ".label")
            identities = tuple(row.binding_identities[index] if index < len(row.binding_identities) else None
                for row in (left, right))
            local = _bind(local, (a[0], b[0]), identities, field)
        self.walk(left.body, right.body, local, path + ".body")

    def frontend_binding_value(self, left, right, index, frame, path):
        sources = tuple(row.binding_capture_sources[index] if index < len(row.binding_capture_sources) else None
            for row in (left, right))
        _same(sources[0] is None, sources[1] is None, path + ".retained source")
        if sources[0] is None:
            self.walk(left.bindings[index][1], right.bindings[index][1], frame, path)
            return
        self.types(sources[0][1], sources[1][1], path + ".type")
        tokens = tuple(_reference(source[0].name, source[0], frame, side)
            for side, source in enumerate(sources))
        _same(*tokens, path + ".retained binding")

    def MatchArm(self, left, right, frame, path):
        self.record(left, right, frame, path, ("binding_name", "binding_identity", "body"))
        local = _bind(frame, (left.binding_name, right.binding_name),
            (left.binding_identity, right.binding_identity), path)
        self.walk(left.body, right.body, local, path + ".body")

    def ListMapExpr(self, left, right, frame, path):
        self.record(left, right, frame, path, ("binder_name", "body_expr"))
        local = _bind(frame, (left.binder_name, right.binder_name),
            (left.binding_identity, right.binding_identity), path)
        self.walk(left.body_expr, right.body_expr, local, path + ".body")

    def LiteralExpr(self, left, right, frame, path):
        _same(left.literal_kind, right.literal_kind, path + ".kind")
        _same(left.value, right.value, path + ".value")

    def WccOpaqueFrontendValue(self, left, right, frame, path):
        self.walk(left.metadata, right.metadata, frame, path + ".metadata")
        self.frontend(left.expr, right.expr, frame, path + ".expr")

    def frontend(self, left, right, frame, path):
        self.walk(left, right, frame, path)


def assert_same_prepared_body(left, right, *, builder):
    """Validate equality without emission, registration or another body copy."""
    comparison = _Comparison((left, right), builder)
    comparison.header()
    frame = comparison.seed()
    comparison.walk(left.prepared_body, right.prepared_body, frame, "body")
    comparison.retention(frame)
