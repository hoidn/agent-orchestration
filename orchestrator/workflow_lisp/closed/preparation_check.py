"""Pure equality guard over two completed, already retained preparations."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass

from .. import expressions as e
from ..type_env import TypeRef
from ..wcc import model as w
from .command_templates import _call_coordinate, command_call_occurrences
from .names import _key_type_ref, _run_ref_signatures


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
        self.contexts = tuple(self.query_context(side) for side in range(2))
        self.inventories = tuple(command_call_occurrences(row.prepared_body,
            lambda call, side=side: self.declaration_identity(call, side))
            for side, row in enumerate(requests))

    def query_context(self, side):
        request, callable_def = self.requests[side], self.callables[side]
        source = self.owners[side]
        types = source.procedure_type_env(callable_def) if hasattr(request, "procedure") else source.workflow_type_env(callable_def.definition.name)
        context = self.builder.definition_context(canonical=callable_def.definition.name,
            owner=callable_def.definition.name, source_program=source, type_env=types,
            node=callable_def.typed_body, params=callable_def.definition.params, callable_def=callable_def)
        context.captures = request.captures
        context.procedure_refs = getattr(request, "procedure_refs", {})
        context.workflow_refs = getattr(request, "workflow_refs", {})
        return context

    def declaration_identity(self, call, side):
        from .names import _callable_header, _find_typed_definition
        from .frontend import resolve_workflow_target

        kind = "procedure" if isinstance(call, w.WccCall) else "workflow"
        name = (call.specialized_callee_name or call.callee_name) if kind == "procedure" else call.target_name
        owner = self.owners[side]
        if kind == "workflow":
            target = resolve_workflow_target(owner, self.callables[side].definition.name, name)
            if target is None:
                _fail("call original declaration owner")
            _, selected, owner = target
        else:
            selected = _find_typed_definition(owner, kind, name)
        if selected is None:
            _fail("call original declaration owner")
        return list(_callable_header(selected, typed=owner)[:3])

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
        self.walk(left.body, right.body, local, path + ".body")

    def WccSelectArm(self, left, right, frame, path):
        _same(len(left.prefix), len(right.prefix), path + ".prefix.length")
        local = frame
        for index, (a, b) in enumerate(zip(left.prefix, right.prefix, strict=True)):
            field = f"{path}.prefix[{index}]"
            self.record(a, b, local, field, ("bound_name", "body"))
            local = _bind(local, (a.bound_name, b.bound_name),
                (a.metadata.binding_identity, b.metadata.binding_identity), field)
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
        self.creation_recipes(left, right, frame, path + ".creations")

    def creation_facts(self, call, side):
        source = self.owners[side]
        return self.builder._prepare_computed_capture_requests(None, self.contexts[side], source,
            classify_call=call)["creations"]

    def creation_recipes(self, left, right, frame, path):
        rows = tuple(self.creation_facts(call, side) for side, call in enumerate((left, right)))
        _same(len(rows[0]), len(rows[1]), path + ".length")
        for index, (a, b) in enumerate(zip(*rows, strict=True)):
            field = f"{path}[{index}]"
            _same(a[1], b[1], field + ".formal")
            self.types(a[3], b[3], field + ".type")
            local = self.creation_aliases((a[4], b[4]), frame, field)
            self.walk(a[2], b[2], local, field + ".expression")

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

        _same(canonical_source_request(left.source), canonical_source_request(right.source), path + ".source")
        _same(left.program.record, right.program.record, path + ".program")
        _same(left.allow_nested_structures, right.allow_nested_structures, path + ".nested")

    def run_ref_inputs(self, left, right, path):
        rows = tuple(row.metadata.type_ref.run_ref_origin[1] for row in (left, right))
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
        _same(left.normalized_body is None, right.normalized_body is None, path + ".mode")
        if left.normalized_body is not None:
            self.walk(left.normalized_body, right.normalized_body, frame, path + ".body")
        else:
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
