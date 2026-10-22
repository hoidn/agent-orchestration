"""The file/2 presentation of one checked provider result; old renderers stay frozen."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from orchestrator.contracts.prompt_delivery import delivery_opening
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor


_GUIDANCE = ("description", "format_hint", "example")
_CONSTRAINTS = ("allowed", "under", "must_exist_target", "required")
_MARKERS = {"bool": "<boolean>", "integer": "<integer>", "float": "<finite number>",
            "string": "<string>", "value": "<strict JSON value>", "relpath": "<relpath>"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _pointer(pointer: str) -> tuple[str, ...]:
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")) if pointer else ()


def _nodes_at(schema, path):
    if not path:
        return [schema]
    kind = schema["type"]
    if kind in {"optional", "list", "map"}:
        key = {"optional": "item", "list": "items", "map": "values"}[kind]
        return _nodes_at(schema[key], path)
    if kind == "record":
        return [node for field in schema["fields"] if field["name"] == path[0]
                for node in _nodes_at(field, path[1:])]
    if kind == "union":
        return [node for variant in schema["variants"].values()
                for node in _nodes_at({"type": "record", "fields": variant["fields"]}, path)]
    return []


def _annotate(schema, payload):
    guidance = {key: payload[key] for key in _GUIDANCE if key in payload}
    if guidance and guidance not in schema.setdefault("_annotations", []):
        schema["_annotations"].append(guidance)


def _overlay(schema, source, root):
    for key in _CONSTRAINTS:
        if key in source:
            schema[key] = source[key]
    _annotate(schema, source)
    contexts = source.get("guidance_context", ())
    for context in sorted(contexts, key=lambda row: len(_pointer(row["json_pointer"]))):
        for ancestor in _nodes_at(root, _pointer(context["json_pointer"])):
            _annotate(ancestor, context)
    for key in ("item", "items", "keys", "values"):
        if isinstance(source.get(key), Mapping) and key in schema:
            _overlay(schema[key], source[key], schema[key])
    if schema["type"] == "record":
        by_name = {field["name"]: field for field in schema["fields"]}
        for field in source.get("fields", ()):
            if field["name"] in by_name:
                _overlay(by_name[field["name"]], field, schema)
    elif schema["type"] == "union":
        _overlay_union(schema, source)


def _overlay_fields(schema, fields, variant=None):
    for field in fields:
        path = _pointer(field["json_pointer"])
        for target in _nodes_at(schema, path):
            source = field
            if "guidance_by_variant" in field:
                source = {key: value for key, value in field.items()
                          if key not in (*_GUIDANCE, "guidance_context", "guidance_by_variant")}
                source.update(field["guidance_by_variant"].get(variant, {}))
            _overlay(target, source, schema)
            if path and target["type"] == "optional":
                target["_omittable"] = True


def _overlay_union(schema, payload):
    for tag in schema["discriminant"]["allowed"]:
        variant = schema["variants"][tag]
        variant_schema = {"type": "record", "fields": variant["fields"]}
        source = payload.get("variants", {}).get(tag, {})
        fields = [*payload.get("shared_fields", ()), *source.get("fields", ())]
        if fields and all("json_pointer" in field for field in fields):
            _overlay_fields(variant_schema, fields, tag)
        else:
            _overlay(variant_schema, source, variant_schema)
        if variant_schema.get("_annotations"):
            variant["_annotations"] = variant_schema["_annotations"]


def _project_json_shape(contract, descriptor):
    schema = transport_schema_for_descriptor(descriptor, allow_nested_structures=True)
    payload = contract["payload"]
    if contract["kind"] == "variant_output":
        _overlay_union(schema, payload)
    else:
        _overlay_fields(schema, payload.get("fields", ()))
    return schema


def _comments(schema, indent):
    prefix = " " * indent + "// "
    annotations = []
    if schema["type"] == "relpath":
        annotations.append({key: schema[key] for key in ("under", "must_exist_target") if key in schema})
    if schema.get("required") is False:
        annotations.append({"required": False})
    if schema.get("_omittable"):
        annotations.append({"omittable": True, "missing_value": None})
    annotations.extend(schema.get("_annotations", ()))
    lines = [prefix + _json(annotation) for annotation in annotations if annotation]
    if schema["type"] == "relpath":
        lines.append(prefix + "workspace-relative; include the declared under prefix")
    return lines


def _shape(schema, indent=0, prefix=""):
    pad = " " * indent
    lines = _comments(schema, indent)
    kind = schema["type"]
    if kind in _MARKERS:
        lines.append(pad + prefix + _MARKERS[kind])
    elif kind == "enum":
        lines.append(pad + prefix + " | ".join(_json(value) for value in schema["allowed"]))
    elif kind == "optional":
        lines.extend(_shape(schema["item"], indent, prefix + "null | "))
    elif kind == "record":
        if not schema["fields"]:
            lines.append(pad + prefix + "{}")
        else:
            lines.append(pad + prefix + "{")
            for index, field in enumerate(schema["fields"]):
                lines.extend(_shape(field, indent + 2, _json(field["name"]) + ": "))
                if index < len(schema["fields"]) - 1:
                    lines[-1] += ","
            lines.append(pad + "}")
    elif kind == "union":
        lines.append(pad + prefix + "(")
        for index, tag in enumerate(schema["discriminant"]["allowed"]):
            if index:
                lines.append(pad + "|")
            variant = schema["variants"][tag]
            record = {"type": "record", "fields": [
                {"name": schema["discriminant"]["name"], "type": "enum", "allowed": [tag]},
                *variant["fields"]], "_annotations": variant.get("_annotations", [])}
            lines.extend(_shape(record, indent + 2))
        lines.append(pad + ")")
    elif kind == "list":
        lines.append(pad + prefix + "[")
        lines.extend(_shape(schema["items"], indent + 2))
        lines[-1] += ","
        lines.extend([pad + "  ...", pad + "]"])
    elif kind == "map":
        lines.append(pad + prefix + "{")
        for annotation in schema["keys"].get("_annotations", ()):
            lines.append(pad + "  // " + _json({"keys": annotation}))
        lines.extend(_shape(schema["values"], indent + 2, "<string key>: "))
        lines[-1] += ","
        lines.extend([pad + "  ...", pad + "}"])
    else:
        raise ValueError(f"unsupported JSON shape type: {kind!r}")
    return lines


def render_json_shape_contract_block(contract, descriptor, result_path):
    """Render the actual nesting with annotations from this call's checked contract."""
    schema = _project_json_shape(contract, descriptor)
    lines = ["## Output Contract", *delivery_opening("value", "file/2", contract["payload"]), f"- path: {result_path}",
        "JSON shape, not an example: <...> denotes a type; | chooses one alternative; "
        "... denotes zero or more entries. Comments are contract annotations, not output."]
    guidance = contract["payload"].get("guidance")
    if guidance:
        lines.append("// " + _json({"guidance": guidance}))
    return "\n".join([*lines, *_shape(schema)]) + "\n"


def render_answer_contract_block(descriptor):
    """Show the same typed JSON shape for host answers without file delivery."""
    schema = transport_schema_for_descriptor(descriptor, allow_nested_structures=True)
    return "\n".join(["## Answer Contract", *_shape(schema)]) + "\n"
