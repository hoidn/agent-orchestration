"""Pure identities shared by closed-program construction and read-back."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import re
from typing import Any

from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.run_ref.config import ReferenceBinding, RunRefInput
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    validate_run_ref_result_descriptor,
)
from orchestrator.workflow.type_descriptor import validate_compiler_normalized_type_descriptor


_GENERATED_RESULT_NAME = re.compile(r"RunRefResult\$[0-9a-f]{16}\Z")
_IDENTITY_ATOM = re.compile(r"[^\s\[\],]+\Z")


def _qualified_template_head(value: str) -> bool:
    return "::" in value and value.split("::", 1)[0] and value.split("::", 1)[1]


def _split_identity_arguments(value: str, *, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                raise ValueError("identity has unbalanced brackets")
        elif char == separator and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    if depth != 0:
        raise ValueError("identity has unbalanced brackets")
    parts.append(value[start:])
    if any(not part for part in parts):
        raise ValueError("identity has an empty applied argument")
    return parts


def _parse_identity(value: str) -> Any:
    """Parse one runtime nominal identity without accepting alternate spelling."""

    if not isinstance(value, str) or not value:
        raise ValueError("identity must be a non-empty string")
    if any(char in value for char in "\t\r\n\f\v"):
        raise ValueError("identity contains noncanonical whitespace")

    if value.endswith(".variant"):
        owner_text = value[: -len(".variant")]
        if "[" in owner_text:
            owner = _parse_identity(owner_text)
            if (
                not isinstance(owner, Mapping)
                or set(owner) != {"head", "args"}
                or owner["head"] in {"List", "Optional", "Map"}
            ):
                raise ValueError("applied discriminant owner must be a nominal application")
            return {"owner": owner, "member": "variant"}

    opening = value.find("[")
    if opening < 0:
        if "]" in value:
            raise ValueError("identity has unbalanced brackets")
        return value
    if not value.endswith("]"):
        raise ValueError("applied identity must end at its matching bracket")
    head = value[:opening]
    body = value[opening + 1 : -1]
    depth = 0
    matching_close = None
    for index in range(opening, len(value)):
        if value[index] == "[":
            depth += 1
        elif value[index] == "]":
            depth -= 1
            if depth == 0:
                matching_close = index
                break
            if depth < 0:
                break
    if not head or not body or matching_close != len(value) - 1:
        raise ValueError("applied identity has invalid brackets")
    if _IDENTITY_ATOM.fullmatch(head) is None:
        raise ValueError("applied identity head is malformed")

    if head == "Map":
        args = _split_identity_arguments(body, separator=",")
        comma = next((index for index, char in enumerate(body) if char == "," and _top_level_at(body, index)), -1)
        if len(args) != 2 or comma <= 0 or comma == len(body) - 1 or body[comma - 1] == " " or body[comma + 1] == " ":
            raise ValueError("Map identity requires canonical comma-separated arguments")
    else:
        args = _split_identity_arguments(body, separator=" ")
        if head in {"List", "Optional"}:
            if len(args) != 1:
                raise ValueError(f"{head} identity requires one argument")
        elif not _qualified_template_head(head):
            raise ValueError("nominal application head must be module-qualified")
    return {"head": head, "args": [_parse_identity(arg) for arg in args]}


def _identity_from_runtime(
    value: str,
    *,
    run_ref_signatures: Mapping[str, dict[str, Any]],
) -> Any:
    parsed = _parse_identity(value)

    def project(identity: Any) -> Any:
        if isinstance(identity, str):
            if identity.startswith("RunRefResult$"):
                if _GENERATED_RESULT_NAME.fullmatch(identity) is None:
                    raise ValueError("reserved run-ref result identity is malformed")
                signature = run_ref_signatures.get(identity)
                if not isinstance(signature, Mapping):
                    raise ValueError(f"run-ref result producer is missing for {identity!r}")
                return {"kind": "run-ref-result", "signature": deepcopy(dict(signature))}
            return identity
        if "head" in identity:
            return {"head": identity["head"], "args": [project(arg) for arg in identity["args"]]}
        return {"owner": project(identity["owner"]), "member": identity["member"]}

    if _render_key_identity(parsed) != value:
        raise ValueError("identity does not use its canonical rendering")
    return project(parsed)


def _top_level_at(value: str, wanted: int) -> bool:
    depth = 0
    for index, char in enumerate(value):
        if index == wanted:
            return depth == 0
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
    return False


def _render_key_identity(value: Any) -> str:
    """Render the private structural key representation as its runtime spelling."""

    if isinstance(value, str):
        if not value or _IDENTITY_ATOM.fullmatch(value) is None:
            raise ValueError("key identity atom is malformed")
        return value
    if not isinstance(value, Mapping):
        raise ValueError("key identity must be an atom or structured object")
    if set(value) == {"kind", "signature"} and value.get("kind") == "run-ref-result":
        # The caller validates S membership against actual run-ref producers.
        return "RunRefResult$0000000000000000"
    if set(value) == {"head", "args"}:
        head, args = value["head"], value["args"]
        if not isinstance(head, str) or not isinstance(args, list) or not args:
            raise ValueError("applied key identity is malformed")
        if _IDENTITY_ATOM.fullmatch(head) is None:
            raise ValueError("applied key identity head is malformed")
        if head == "Map":
            if len(args) != 2:
                raise ValueError("Map key identity requires two arguments")
            text = f"Map[{_render_key_identity(args[0])},{_render_key_identity(args[1])}]"
        else:
            if head in {"List", "Optional"}:
                if len(args) != 1:
                    raise ValueError(f"{head} key identity requires one argument")
            elif not _qualified_template_head(head):
                raise ValueError("nominal key identity head must be module-qualified")
            text = f"{head}[{' '.join(_render_key_identity(arg) for arg in args)}]"
        if _parse_identity(text) != value:
            # Run-ref markers render to a reserved placeholder while parsing
            # back to its runtime atom, so check shape recursively instead.
            _validate_key_identity(value)
        return text
    if set(value) == {"owner", "member"} and value.get("member") == "variant":
        owner = value["owner"]
        if not isinstance(owner, Mapping) or set(owner) != {"head", "args"}:
            raise ValueError("applied discriminant owner must be a nominal application")
        if owner.get("head") in {"List", "Optional", "Map"}:
            raise ValueError("applied discriminant owner cannot be a container")
        return f"{_render_key_identity(owner)}.variant"
    raise ValueError("structured key identity has invalid fields")


def _validate_key_identity(value: Any) -> None:
    if isinstance(value, str):
        if not value or _IDENTITY_ATOM.fullmatch(value) is None:
            raise ValueError("key identity atom is malformed")
        return
    if not isinstance(value, Mapping):
        raise ValueError("key identity is malformed")
    if set(value) == {"kind", "signature"} and value.get("kind") == "run-ref-result":
        if not isinstance(value["signature"], Mapping):
            raise ValueError("run-ref key identity signature must be an object")
        return
    if set(value) == {"head", "args"}:
        head, args = value["head"], value["args"]
        if not isinstance(head, str) or not isinstance(args, list) or not args:
            raise ValueError("applied key identity is malformed")
        if head == "Map":
            if len(args) != 2:
                raise ValueError("Map key identity requires two arguments")
        elif head in {"List", "Optional"}:
            if len(args) != 1:
                raise ValueError(f"{head} key identity requires one argument")
        elif not _qualified_template_head(head):
            raise ValueError("nominal key identity head must be module-qualified")
        for argument in args:
            _validate_key_identity(argument)
        return
    if set(value) == {"owner", "member"} and value.get("member") == "variant":
        owner = value["owner"]
        if not isinstance(owner, Mapping) or set(owner) != {"head", "args"}:
            raise ValueError("applied discriminant owner must be a nominal application")
        if owner.get("head") in {"List", "Optional", "Map"}:
            raise ValueError("applied discriminant owner cannot be a container")
        _validate_key_identity(owner)
        return
    raise ValueError("structured key identity has invalid fields")


def _project_identity_argument_dependencies(value: Any, found: list[str]) -> None:
    if isinstance(value, str):
        if value.startswith("RunRefResult$"):
            if _GENERATED_RESULT_NAME.fullmatch(value) is None:
                raise ValueError("reserved run-ref result identity is malformed")
            found.append(value)
        return
    if "head" in value:
        for argument in value["args"]:
            _project_identity_argument_dependencies(argument, found)
    elif "owner" in value:
        _project_identity_argument_dependencies(value["owner"], found)


def canonical_callee_name_from_key(key: list[Any]) -> str:
    """Derive the stable readable name from one canonical nine-part key."""

    if not isinstance(key, list) or len(key) != 9:
        raise ValueError("definition key must be a nine-element list")
    module, kind, declaration = key[:3]
    if not isinstance(module, str) or not module:
        raise ValueError("definition key module must be a non-empty string")
    if kind not in {"procedure", "workflow"}:
        raise ValueError("definition key kind must be procedure or workflow")
    if isinstance(declaration, str) and declaration:
        declared_name = declaration
        is_local = False
    elif (
        isinstance(declaration, dict)
        and set(declaration) == {"owner", "name", "ordinal"}
        and isinstance(declaration["name"], str)
        and declaration["name"]
        and type(declaration["ordinal"]) is int
        and declaration["ordinal"] >= 0
    ):
        declared_name = declaration["name"]
        is_local = True
    else:
        raise ValueError("definition key declaration has invalid shape")

    base = f"{kind}:{module}::{declared_name}"
    if not is_local and not any(key[3:8]):
        return base
    encoded = canonical_json_for_pure_value(key).encode("utf-8")
    return f"{base}[{sha256(encoded).hexdigest()}]"


def key_type_descriptor(
    descriptor: dict[str, Any],
    *,
    run_ref_signatures: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Project a normalized runtime descriptor into a canonical definition key."""

    validate_compiler_normalized_type_descriptor(descriptor)
    kind = descriptor["kind"]
    if kind == "record":
        name = descriptor["name"]
        if name.startswith("RunRefResult$"):
            if _GENERATED_RESULT_NAME.fullmatch(name) is None:
                raise ValueError("reserved run-ref result name is malformed")
            signature = run_ref_signatures.get(name)
            if not isinstance(signature, Mapping):
                raise ValueError(f"run-ref result producer is missing for {name!r}")
            return {
                "kind": "run-ref-result",
                "signature": deepcopy(dict(signature)),
            }
        result = {
            **deepcopy(descriptor),
            "name": _identity_from_runtime(name, run_ref_signatures=run_ref_signatures),
            "fields": [
                {"name": field["name"], "type": key_type_descriptor(
                    field["type"], run_ref_signatures=run_ref_signatures
                )}
                for field in descriptor["fields"]
            ],
        }
        return result
    if kind == "union":
        return {
            **deepcopy(descriptor),
            "name": _identity_from_runtime(
                descriptor["name"], run_ref_signatures=run_ref_signatures
            ),
            "variants": [
                {
                    "name": variant["name"],
                    "fields": [
                        {"name": field["name"], "type": key_type_descriptor(
                            field["type"], run_ref_signatures=run_ref_signatures
                        )}
                        for field in variant["fields"]
                    ],
                }
                for variant in descriptor["variants"]
            ],
        }
    if kind == "variant_case":
        return {
            **deepcopy(descriptor),
            "union_name": _identity_from_runtime(
                descriptor["union_name"], run_ref_signatures=run_ref_signatures
            ),
            "fields": [
                {"name": field["name"], "type": key_type_descriptor(
                    field["type"], run_ref_signatures=run_ref_signatures
                )}
                for field in descriptor["fields"]
            ],
        }
    if kind == "enum":
        return {
            **deepcopy(descriptor),
            "name": _identity_from_runtime(
                descriptor["name"], run_ref_signatures=run_ref_signatures
            ),
        }
    if kind in {"optional", "list"}:
        return {
            "kind": kind,
            "item": key_type_descriptor(
                descriptor["item"], run_ref_signatures=run_ref_signatures
            ),
        }
    if kind == "map":
        return {
            "kind": "map",
            "key": key_type_descriptor(
                descriptor["key"], run_ref_signatures=run_ref_signatures
            ),
            "value": key_type_descriptor(
                descriptor["value"], run_ref_signatures=run_ref_signatures
            ),
        }
    return deepcopy(descriptor)


def run_ref_type_dependencies(descriptor: dict[str, Any]) -> tuple[str, ...]:
    """Return generated result identities in descriptor/argument traversal order."""

    validate_compiler_normalized_type_descriptor(descriptor)
    found: list[str] = []

    def visit_identity(identity: str) -> None:
        parsed = _parse_identity(identity)
        if _render_key_identity(parsed) != identity:
            raise ValueError("identity does not use its canonical rendering")
        _project_identity_argument_dependencies(parsed, found)

    def visit(current: Mapping[str, Any]) -> None:
        kind = current["kind"]
        if kind in {"record", "union", "enum"}:
            visit_identity(current["name"])
        elif kind == "variant_case":
            visit_identity(current["union_name"])
        if kind in {"optional", "list"}:
            visit(current["item"])
        elif kind == "map":
            visit(current["key"])
            visit(current["value"])
        elif kind in {"record", "variant_case"}:
            for field in current["fields"]:
                visit(field["type"])
        elif kind == "union":
            for variant in current["variants"]:
                for field in variant["fields"]:
                    visit(field["type"])

    visit(descriptor)
    return tuple(dict.fromkeys(found))


def canonical_run_ref_signature(
    inputs: Sequence[tuple[str, dict[str, Any]]],
    result_descriptor: dict[str, Any],
    *,
    run_ref_signatures: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Project one validated run-ref's ordered inputs and result contract."""

    validate_run_ref_result_descriptor(
        result_descriptor,
        allow_nested_structures=True,
    )
    projected_inputs: list[list[Any]] = []
    input_names: set[str] = set()
    for row in inputs:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise TypeError("run-ref signature inputs must be name/descriptor pairs")
        name, descriptor = row
        if not isinstance(name, str) or not name:
            raise ValueError("run-ref signature input names must be non-empty strings")
        if name in input_names:
            raise ValueError("run-ref signature input names must be unique")
        input_names.add(name)
        RunRefInput(
            name=name,
            type_descriptor=descriptor,
            binding=ReferenceBinding(f"inputs.{name}"),
            allow_nested_structures=True,
        )
        projected_inputs.append(
            [
                name,
                key_type_descriptor(
                    descriptor,
                    run_ref_signatures=run_ref_signatures,
                ),
            ]
        )

    envelope = result_descriptor["envelope"]
    projected_envelope = {
        "kind": "record",
        "fields": [
            {
                "name": field["name"],
                "type": key_type_descriptor(
                    field["type"],
                    run_ref_signatures=run_ref_signatures,
                ),
            }
            for field in envelope["fields"]
        ],
    }
    return {
        "inputs": projected_inputs,
        "result": {
            "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
            "envelope": projected_envelope,
        },
    }
