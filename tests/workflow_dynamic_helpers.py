"""Shared builders for production dynamic-program admission and evaluation tests."""

from __future__ import annotations

import hashlib
import json

import pytest


INT = {"kind": "primitive", "name": "Int"}
BOOL = {"kind": "primitive", "name": "Bool"}


def _pointer(parent: str, item: str) -> str:
    escaped = item.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


def _children(node):
    kind = node.get("k")
    if kind in {"lit", "name", "fail"}:
        return ()
    if kind == "let":
        return (*[("bindings", (index, 1), row[1]) for index, row in enumerate(node["bindings"])], ("body", (), node["body"]))
    if kind == "fn":
        return tuple(("captures", (index,), child) for index, child in enumerate(node["captures"]))
    if kind == "call":
        return (("callee", (), node["callee"]), *[("args", (index,), child) for index, child in enumerate(node["args"])])
    if kind == "if":
        return (("cond", (), node["cond"]), ("then", (), node["then"]), ("else", (), node["else"]))
    if kind == "record":
        return tuple(("fields", (index, 1), child) for index, (_, child) in enumerate(node["fields"]))
    if kind == "field":
        return (("base", (), node["base"]),)
    if kind == "list":
        return tuple(("items", (index,), child) for index, child in enumerate(node["items"]))
    if kind == "at":
        return (("base", (), node["base"]), ("index", (), node["index"]))
    if kind == "op":
        return tuple(("args", (index,), child) for index, child in enumerate(node["args"]))
    if kind == "record-update":
        return (("base", (), node["base"]), *[("fields", (index, 1), child) for index, (_, child) in enumerate(node["fields"])])
    if kind == "effect":
        return (("inputs", (), node["inputs"]),)
    if kind == "perform":
        if node["class"] == "command":
            return (*[("argv", (i,), child) for i, child in enumerate(node["argv"])],
                    *[("document", (i, 1), child) for i, (_, child) in enumerate(node.get("document", []))])
        prompt = node["prompt"]
        dependencies = node["dependencies"] or {}
        return (*[("prompt", ("fills", i, "value"), fill["value"]) for i, fill in enumerate(prompt.get("fills", []))],
                *[("dependencies", (role, i), child) for role in ("required", "optional") for i, child in enumerate(dependencies.get(role, []))],
                *[("policy", (key,), child) for key, child in sorted((node["policy"] or {}).items())])
    return ()


def _node_paths(node, path):
    yield path
    for field, indices, child in _children(node):
        child_path = _pointer(path, field)
        for index in indices:
            child_path = _pointer(child_path, str(index))
        yield from _node_paths(child, child_path)


def _source_paths(code, definition):
    definition_path = _pointer("/definitions", code)
    paths = [definition_path]
    paths.extend(_node_paths(definition["body"], _pointer(definition_path, "body")))
    boundary = definition["boundary"]
    if boundary is not None:
        boundary_path = _pointer(definition_path, "boundary")
        for index, _ in enumerate(boundary["params"]):
            paths.append(_pointer(_pointer(boundary_path, "params"), str(index)))
        for name in boundary["defaults"]:
            paths.append(_pointer(_pointer(boundary_path, "defaults"), name))
        paths.append(_pointer(boundary_path, "result"))
    return paths


def _prompt_subjects(node, path):
    if node.get("k") == "perform":
        yield _pointer(path, "result"), None
        if node["class"] == "provider":
            prompt = node["prompt"]
            owner = node["prompt_owner"]["module"]
            yield _pointer(path, "prompt"), owner
            if "template" in prompt:
                yield _pointer(path, "result"), owner
                yield _pointer(_pointer(path, "prompt"), "template"), owner
                for i, _ in enumerate(prompt["fills"]):
                    yield _pointer(_pointer(_pointer(path, "prompt"), "fills"), str(i)), owner
    for field, indices, child in _children(node):
        child_path = _pointer(path, field)
        for index in indices:
            child_path = _pointer(child_path, str(index))
        yield from _prompt_subjects(child, child_path)


def _definition(body, *, params=(), captures=(), owner_module="demo", asset_base=None, boundary=None):
    return {
        "params": list(params),
        "captures": list(captures),
        "body": body,
        "owner": {"module": owner_module, "asset_base": asset_base if asset_base is not None else owner_module.rpartition("/")[0] or "."},
        "boundary": boundary,
    }


def _span(path="demo/main.orc"):
    return {
        "start": {"path": path, "line": 1, "column": 1, "offset": 0},
        "end": {"path": path, "line": 1, "column": 2, "offset": 1},
    }


def _artifact(
    body=None,
    *,
    definitions=None,
    schemas=None,
    defaults=None,
    bindings=None,
    result="Int",
    entry="demo::main",
    params=None,
    budget=100,
    sources=None,
):
    body = {"k": "name", "n": "n"} if body is None else body
    definitions = {} if definitions is None else definitions
    schemas = {"Int": INT, "Bool": BOOL} if schemas is None else schemas
    params = [["n", "Int"]] if params is None else [list(row) for row in params]
    parameter_names = [row[0] for row in params]
    if defaults is None:
        defaults = {"n": 3} if params == [["n", "Int"]] else {}
    module = entry.rpartition("::")[0]
    entry_definition = _definition(
        body,
        params=parameter_names,
        owner_module=module,
        boundary={"params": params, "defaults": defaults, "result": result},
    )
    all_definitions = {entry: entry_definition, **definitions}
    if sources is None:
        modules = {definition["owner"]["module"] for definition in all_definitions.values()} | set(bindings or {})
        sources = {}
        for source_module in modules:
            relative_path = source_module.replace(".", "/") + "/main.orc"
            source_bytes = f"(workflow-lisp (:module {source_module}))\n".encode()
            sources[source_module] = {
                "root_role": "source",
                "relative_path": relative_path,
                "source_sha256": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
            }
    source_map_entries = {}
    for code, definition in all_definitions.items():
        source = definition["owner"]["module"]
        for node_pointer in _source_paths(code, definition):
            source_map_entries[node_pointer] = {
                "source": source,
                "span": _span(sources[source]["relative_path"]),
                "form_path": ["workflow-lisp", "definition", code],
            }
        for node_pointer, prompt_source in _prompt_subjects(definition["body"], _pointer(_pointer("/definitions", code), "body")):
            subject_source = prompt_source or source
            source_map_entries[node_pointer] = {
                "source": subject_source,
                "span": _span(sources[subject_source]["relative_path"]),
                "form_path": ["workflow-lisp", "definition", code],
            }
    return {
        "schema": "workflow-lisp/dynamic-program/1",
        "target": "3.0",
        "entry": entry,
        "budget": budget,
        "definitions": all_definitions,
        "schemas": schemas,
        "bindings": {} if bindings is None else bindings,
        "sources": sources,
        "source_map": {
            "schema": "workflow-lisp/dynamic-source-map/1",
            "entries": source_map_entries,
        },
    }


def _text(value):
    return json.dumps(value, allow_nan=True, separators=(",", ":"))


def _read(value):
    from orchestrator.workflow_lisp.dynamic.program import DynamicProgram

    return DynamicProgram.from_artifact(value if isinstance(value, (str, bytes)) else _text(value))


def _invalid(action):
    with pytest.raises(ValueError) as caught:
        action()
    assert getattr(caught.value, "code", None) == "dynamic_program_invalid"
    return caught.value
