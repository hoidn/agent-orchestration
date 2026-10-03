"""Derive command interfaces from checked JSON, independently of preparation."""

from hashlib import sha256
import json

_PURE_FIELDS = {"field": ("base",), "op": ("args",), "list": ("items",),
    "call": ("args",), "path_join": ("base", "child"),
    "list_map": ("source", "body")}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _pure_children(node):
    kind = node["k"]
    if kind in {"record", "inject"}:
        return [row[1] for row in node["fields"]]
    if kind == "perform":
        return _effect_children(node)
    fields = _PURE_FIELDS.get(kind, ())
    children = []
    for field in fields:
        value = node[field]
        children.extend(value if isinstance(value, list) else [value])
    return children


def _effect_children(node):
    if node["class"] == "command":
        slots = [part["value"] for plan in node.get("argv_transport", [])
            for part in plan.get("parts", []) if part["kind"] == "slot"]
        return [*node["argv"], *slots, *(row[1] for row in node.get("document", []))]
    if node["class"] == "run_ref":
        return [row[1] for row in node["inputs"]]
    if node["class"] == "provider":
        return _provider_children(node)
    return []


def _provider_children(node):
    dependencies = node.get("dependencies") or {}
    prompt = node.get("prompt") or {}
    return [*(row[2] for row in node["inputs"]),
        *(row["value"] for row in prompt.get("fills", [])),
        *dependencies.get("required", []), *dependencies.get("optional", []),
        *(node.get("policy") or {}).values()]


def _control_children(node):
    kind = node["k"]
    if kind == "case":
        return [node["subject"], *(arm["body"] for arm in node["arms"])]
    if kind == "select":
        children = [node["cond"]]
        for arm in (node["then"], node["else"]):
            children.extend(row["value"] for row in arm["prefix"])
            children.append(arm["value"])
        return children
    fields = {"let": ("value", "body"), "if": ("cond", "then", "else"),
        "join": ("body", "cont"), "loop": ("budget", "init", "body", "exhausted"),
        "block": ("body",), "halt": ("value",), "done": ("value",),
        "jump": ("args",), "continue": ("args",)}.get(kind)
    if fields is None:
        return _pure_children(node)
    children = []
    for field in fields:
        value = node.get(field)
        if value is not None:
            children.extend(value if isinstance(value, list) else [value])
    return children


def _term(node, fields, children, **retained):
    data = {key: value for key, value in node.items() if key not in (*fields, "@")}
    return _json({**data, **retained}), tuple(children)


def _resolve(value, aliases, binders=()):
    kind = value["k"]
    if kind in {"name", "result_path"}:
        root = aliases[value["n"]]
        return root if kind == "name" else _term(value, ("n",), (root,))
    if kind == "list_map":
        nested, frame = _term_binding(aliases, binders, value["binder"])
        return _term(value, ("source", "body"), (
            _resolve(value["source"], aliases, binders), _resolve(value["body"], nested, frame)))
    if kind == "select":
        return _term(value, ("cond", "then", "else"), (
            _resolve(value["cond"], aliases, binders),
            *(_select_term(value[arm], aliases, binders) for arm in ("then", "else"))))
    if kind == "block":
        return _term(value, ("body",), (_body_term(value["body"], aliases, binders),))
    fields = ("fields",) if kind in {"record", "inject"} else _PURE_FIELDS.get(kind, ())
    retained = {"fields": [row[0] for row in value["fields"]]} if "fields" in fields else {}
    return _term(value, fields,
        (_resolve(child, aliases, binders) for child in _pure_children(value)), **retained)


def _term_binding(aliases, binders, name, value=None):
    frame = (*binders, name)
    nested = {**aliases, name: ("local-binding", len(binders), name)}
    if value is not None and value["k"] in {"name", "lit"}:
        nested[name] = _resolve(value, aliases, binders)
    return nested, frame


def _select_term(arm, aliases, binders):
    terms = []
    for binding in arm["prefix"]:
        terms.append(_term(binding, ("value",), (_resolve(binding["value"], aliases, binders),)))
        aliases, binders = _term_binding(aliases, binders, binding["name"], binding["value"])
    terms.append(_resolve(arm["value"], aliases, binders))
    return _term(arm, ("prefix", "value"), terms)


def _body_term(node, aliases, binders):
    kind = node["k"]
    if kind == "let":
        nested, frame = _term_binding(aliases, binders, node["name"], node["value"])
        return _term(node, ("value", "body"), (_resolve(node["value"], aliases, binders),
            _body_term(node["body"], nested, frame)))
    if kind == "if":
        return _term(node, ("cond", "then", "else"), (_resolve(node["cond"], aliases, binders),
            *(_body_term(node[arm], aliases, binders) for arm in ("then", "else"))))
    if kind == "case":
        return _case_term(node, aliases, binders)
    if kind == "loop":
        return _loop_term(node, aliases, binders)
    if kind == "join":
        nested, frame = aliases, binders
        body = _body_term(node["body"], aliases, binders)
        for name, _ in node["params"]:
            nested, frame = _term_binding(nested, frame, name)
        return _term(node, ("body", "cont"), (body, _body_term(node["cont"], nested, frame)))
    return _term(node, ("value", "args"),
        (_resolve(child, aliases, binders) for child in _control_children(node)))


def _case_term(node, aliases, binders):
    terms = [_resolve(node["subject"], aliases, binders)]
    for arm in node["arms"]:
        nested, frame = _term_binding(aliases, binders, arm["bind"])
        roots = [_resolve(row[1], nested, frame) for row in arm.get("command_scope", [])]
        retained = {"command_scope": [row[0] for row in arm["command_scope"]]} if "command_scope" in arm else {}
        terms.append(_term(arm, ("command_scope", "body"),
            (*roots, _body_term(arm["body"], nested, frame)), **retained))
    return _term(node, ("subject", "arms"), terms)


def _loop_term(node, aliases, binders):
    nested, frame = _term_binding(aliases, binders, node["param"])
    exhausted = None if node["exhausted"] is None else _body_term(node["exhausted"], nested, frame)
    if "index" in node:
        nested, frame = _term_binding(nested, frame, node["index"])
    return _term(node, ("budget", "init", "body", "exhausted"), (
        _resolve(node["budget"], aliases, binders), _resolve(node["init"], aliases, binders),
        _body_term(node["body"], nested, frame), exhausted))


def _bind_alias(aliases, name, value):
    nested = dict(aliases)
    nested[name] = object()
    if value["k"] in {"name", "lit"}:
        nested[name] = _resolve(value, aliases)
    return nested


class _Projection:
    def __init__(self, tree, project_type, fail):
        self.tree, self.project_type, self.fail = tree, project_type, fail
        self.definitions = tree["definitions"]
        self.interfaces, self.bearings = {}, {}

    def contains(self, node):
        if node["k"] == "perform" and node["class"] == "command":
            return True
        if node["k"] == "call":
            self.derive(node["callee"])
            if self.bearings[node["callee"]]:
                return True
        return any(self.contains(child) for child in _control_children(node))

    def derive(self, owner):
        if owner in self.interfaces:
            return self.interfaces[owner]
        definition = self.tree if owner == self.tree["entry"] else self.definitions[owner]
        native, captures, roots, index, aliases = self.certificates(definition)
        bearing = self.contains(definition["body"])
        state = dict(roots=roots, index=index, aliases=aliases,
            counts={"command": 0, "case": 0, "loop": 0}, calls={},
            decisions=[], used_indexes=set(), bound_indexes=set())
        self.body(definition["body"], state)
        if state["used_indexes"] != state["bound_indexes"]:
            self.fail("command_index", "loop index certificate must be demanded in its body", definition)
        interface = {"native": native, "captures": captures, "decisions": state["decisions"]}
        self.interfaces[owner], self.bearings[owner] = interface, bearing
        return interface

    def certificates(self, definition):
        native = None
        roots, captures, index_root = {}, [], None
        aliases = {name: object() for name, _ in definition["params"]}
        if "command_params" in definition:
            native = []
            for formal, index in definition["command_params"]:
                wire, descriptor = definition["params"][index]
                native.append([formal, index, self.project_type(descriptor)])
                roots[formal] = (aliases[wire], ["native", formal])
        for index, capture in enumerate(definition.get("key", [None] * 8)[7] or ()):
            index_root = self.capture_certificate(definition, index, capture, captures, roots, index_root, aliases)
        return native, captures, roots, index_root, aliases

    def capture_certificate(self, definition, index, capture, captures, roots, index_root, aliases):
        wire, descriptor = definition["params"][index]
        for route in capture["routes"]:
            if route[0] not in {"command-input", "command-loop-index"}:
                continue
            captures.append([route, self.project_type(descriptor)])
            certified = (aliases[wire], ["capture", route])
            if route[0] == "command-input":
                roots[route[1]] = certified
            else:
                index_root = certified
        return index_root

    def body(self, node, state):
        kind = node["k"]
        if kind == "let":
            self.value(node["value"], state)
            nested = dict(state, aliases=_bind_alias(state["aliases"], node["name"], node["value"]))
            self.body(node["body"], nested)
        elif kind == "case":
            self.case(node, state)
        elif kind == "loop":
            self.loop(node, state)
        elif kind == "if":
            self.value(node["cond"], state)
            for branch in (node["then"], node["else"]):
                self.body(branch, dict(state))
        elif kind == "join":
            self.body(node["body"], dict(state))
            aliases = dict(state["aliases"])
            for name, _ in node["params"]:
                aliases[name] = object()
            self.body(node["cont"], dict(state, aliases=aliases))
        else:
            for value in _control_children(node):
                self.value(value, state)

    def case(self, node, state):
        bearing = any(self.contains(arm["body"]) for arm in node["arms"])
        ordinal = state["counts"]["case"]
        state["counts"]["case"] += bearing
        self.value(node["subject"], state)
        for arm in node["arms"]:
            aliases = dict(state["aliases"])
            aliases[arm["bind"]] = object()
            nested = dict(state, aliases=aliases)
            if "command_scope" in arm:
                nested["roots"] = self.arm_roots(arm, nested, ordinal)
                nested["index"] = None
                if bearing:
                    state["decisions"].append(["arm", ordinal, arm["variant"], "reset"])
            self.body(arm["body"], nested)

    def arm_roots(self, arm, state, ordinal):
        roots = {}
        for formal, value in arm["command_scope"]:
            self.value(value, state)
            roots[formal] = (_resolve(value, state["aliases"]),
                ["arm", ordinal, arm["variant"], formal])
        return roots

    def loop(self, node, state):
        ordinal = state["counts"]["loop"]
        state["counts"]["loop"] += "index" in node
        self.value(node["budget"], state)
        self.value(node["init"], state)
        aliases = dict(state["aliases"])
        aliases[node["param"]] = object()
        nested = dict(state, aliases=aliases, index=None)
        if "index" in node:
            body_aliases = dict(aliases)
            body_aliases[node["index"]] = object()
            nested["aliases"] = body_aliases
            nested["index"] = (body_aliases[node["index"]], ["loop", ordinal])
            state["bound_indexes"].add(ordinal)
        self.body(node["body"], nested)
        if node["exhausted"] is not None:
            self.body(node["exhausted"], dict(state, aliases=aliases))

    def value(self, node, state):
        kind = node["k"]
        if kind == "block":
            self.body(node["body"], dict(state))
        elif kind == "select":
            self.select(node, state)
        elif kind == "list_map":
            self.value(node["source"], state)
            aliases = dict(state["aliases"])
            aliases[node["binder"]] = object()
            self.value(node["body"], dict(state, aliases=aliases))
        else:
            for child in _pure_children(node):
                self.value(child, state)
            if kind == "call":
                self.call(node, state)
            if kind == "perform" and node["class"] == "command":
                self.command(node, state)

    def select(self, node, state):
        self.value(node["cond"], state)
        for arm in (node["then"], node["else"]):
            nested = dict(state)
            for binding in arm["prefix"]:
                self.value(binding["value"], nested)
                nested["aliases"] = _bind_alias(nested["aliases"], binding["name"], binding["value"])
            self.value(arm["value"], nested)

    def call(self, node, state):
        definition = self.definitions[node["callee"]]
        declaration = definition["key"][:3]
        selector = _json(declaration)
        occurrence = state["calls"].get(selector, 0)
        state["calls"][selector] = occurrence + 1
        child = self.derive(node["callee"])
        self.forwarded_roots(node, definition, state)
        if child["native"] or child["captures"] or child["decisions"]:
            digest = sha256(_json(child).encode()).hexdigest()
            state["decisions"].append(["call", declaration, occurrence, digest])

    def forwarded_roots(self, node, definition, state):
        for index, capture in enumerate(definition["key"][7]):
            for route in capture["routes"]:
                if route[0] == "command-input":
                    certified = state["roots"].get(route[1])
                elif route[0] == "command-loop-index":
                    certified = state["index"]
                else:
                    continue
                self.require_root(node["args"][index], certified, state, node)

    def require_root(self, value, certified, state, node):
        if certified is None:
            self.fail("command_transport", "command forwarding or slot lacks its root certificate", node)
        root, origin = certified
        if _resolve(value, state["aliases"]) != root:
            self.fail("command_transport", "command slot or forwarding must read its whole certified root", node)
        if origin[0] == "loop":
            state["used_indexes"].add(origin[1])
        return origin

    def command(self, node, state):
        ordinal = state["counts"]["command"]
        state["counts"]["command"] += 1
        for index, plan in enumerate(node.get("argv_transport", [])):
            choice = ["value"]
            if plan["kind"] == "template":
                choices = [self.lookup(part, state, node) for part in plan["parts"] if part["kind"] != "text"]
                choice = ["template", choices]
            state["decisions"].append(["arg", ordinal, index, choice])

    def lookup(self, part, state, node):
        if part["kind"] == "missing":
            return ["missing"]
        name = part["name"]
        if name[0] == "input":
            origin = self.require_root(part["value"], state["roots"].get(name[1]), state, node)
            return ["input", origin, name[2]]
        origin = self.require_root(part["value"], state["index"], state, node)
        return ["loop-index", origin]

def checked_command_interfaces(tree, *, project_type, fail):
    projection = _Projection(tree, project_type, fail)
    for owner in tree["definitions"]:
        projection.derive(owner)
    projection.derive(tree["entry"])
    return projection.interfaces
