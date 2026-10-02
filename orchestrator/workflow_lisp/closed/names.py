"""Pure identities shared by closed-program construction and read-back."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import fields as dataclass_fields, is_dataclass, replace as dataclass_replace
from hashlib import sha256
import re
from types import SimpleNamespace
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


class CanonicalNameError(ValueError):
    """A checked type has no retained owner facts for a stable identity."""

    def __init__(self, typename: str):
        self.typename = typename
        super().__init__(f"canonical identity is missing owner facts for {typename!r}")


class Renamer:
    """Allocate deterministic wire names while preserving lexical references."""

    def __init__(self, *, reserved_names: Sequence[str] = ()) -> None:
        self._reserved = set(reserved_names)
        self._next = 1

    def bind(
        self,
        name: str,
        *,
        authored_label: str | None,
        env: dict[str, str],
    ) -> str:
        """Bind an authored or generated source name in one lexical frame."""

        if authored_label is not None and name == authored_label:
            wire_name = name
        else:
            while f"%{self._next}" in self._reserved:
                self._next += 1
            wire_name = f"%{self._next}"
            self._next += 1
        self._reserved.add(wire_name)
        env[name] = wire_name
        return wire_name

    @staticmethod
    def ref(name: str, *, env: Mapping[str, str]) -> str:
        """Resolve a source binder through its current lexical frame."""

        try:
            return env[name]
        except KeyError as exc:
            raise ValueError(f"unbound source name {name!r}") from exc


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


def _typed_type_envs(typed: Any) -> tuple[Any, ...]:
    found: list[Any] = []
    for candidate in (
        getattr(typed, "type_env", None),
        *getattr(typed, "module_type_envs", {}).values(),
        *getattr(typed, "procedure_type_envs", {}).values(),
        *getattr(typed, "workflow_type_envs", {}).values(),
    ):
        if candidate is not None and all(candidate is not old for old in found):
            found.append(candidate)
    return tuple(found)


def _definition_owner_identity(type_ref: Any, *, typed: Any) -> str:
    from ..type_env import PrimitiveTypeRef, RecordTypeRef

    if isinstance(type_ref, PrimitiveTypeRef) and not type_ref.allowed_values:
        return type_ref.name

    environments = list(_typed_type_envs(typed))
    seen_programs = {id(typed)}
    pending = list(getattr(typed, "imported_programs", {}).values())
    while pending:
        program = pending.pop(0)
        if id(program) in seen_programs:
            continue
        seen_programs.add(id(program))
        for environment in _typed_type_envs(program):
            if all(environment is not old for old in environments):
                environments.append(environment)
        pending.extend(getattr(program, "imported_programs", {}).values())
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.allowed_values:
        for environment in environments:
            module = environment.declaring_module(type_ref)
            name = environment.declaring_name(type_ref)
            if module is not None and name is not None:
                return f"{module}::{name}"
        raise CanonicalNameError(type_ref.name)

    for environment in environments:
        module = environment.declaring_module(type_ref)
        name = environment.declaring_name(type_ref)
        if module is not None and name is not None:
            return f"{module}::{name}"

    for environment in environments:
        compiler_identity = environment.compiler_type_identity(type_ref)
        if compiler_identity is not None:
            return compiler_identity

    # These exact compiler-owned run-ref records have a stable logical
    # namespace and are reserved against source declarations in each owning
    # module. Their specialized TypeRefs may carry equivalent cloned
    # RecordDefs, so consult the checked session inventory only after giving an
    # actual retained source declaration its owner-qualified identity.
    if isinstance(type_ref, RecordTypeRef):
        from ..typecheck_run_ref import RUN_REF_FIXED_TYPE_NAMES

        if type_ref.name in RUN_REF_FIXED_TYPE_NAMES:
            for environment in environments:
                state = getattr(environment, "session_state", None)
                for metadata in getattr(state, "run_ref_metadata_by_name", {}).values():
                    if any(
                        name == type_ref.name
                        for name, _ in metadata.compiler_owned_types
                    ):
                        return type_ref.name
    raise CanonicalNameError(getattr(type_ref, "name", type(type_ref).__name__))


def _union_for_variant(type_ref: Any, *, typed: Any) -> Any:
    from ..type_env import UnionTypeRef

    for environment in _typed_type_envs(typed):
        for candidate in getattr(environment, "_type_refs", {}).values():
            if (
                isinstance(candidate, UnionTypeRef)
                and any(variant is type_ref.definition for variant in candidate.definition.variants)
            ):
                return candidate
    raise CanonicalNameError(getattr(type_ref, "union_name", type(type_ref).__name__))


def _union_for_discriminant(type_ref: Any, *, typed: Any) -> Any:
    from ..type_env import UnionTypeRef

    candidates = [
        candidate
        for environment in _typed_type_envs(typed)
        for candidate in getattr(environment, "_type_refs", {}).values()
        if isinstance(candidate, UnionTypeRef)
        and candidate.name == type_ref.union_name
    ]
    unique = []
    for candidate in candidates:
        if all(candidate is not old for old in unique):
            unique.append(candidate)
    if len(unique) == 1:
        return unique[0]
    raise CanonicalNameError(type_ref.union_name)


def _loop_carrier_metadata(type_ref: Any, *, typed: Any):
    from ..loop_state import carrier_metadata_for_type

    field_types = tuple(
        (field.name, type_ref.field_types[field.name])
        for field in type_ref.definition.fields
    )
    matches = []
    for environment in _typed_type_envs(typed):
        state = getattr(environment, "session_state", None)
        if state is None:
            continue
        metadata = carrier_metadata_for_type(
            type_ref,
            session_state=state,
            field_types=field_types,
            type_env=environment,
        )
        if metadata is not None and all(metadata is not old for old in matches):
            matches.append(metadata)
    if not matches:
        return None
    first = matches[0]
    if any(
        (match.family, match.field_names) != (first.family, first.field_names)
        for match in matches[1:]
    ):
        raise RuntimeError("loop-state carrier has conflicting retained family facts")
    return first


def _loop_carrier_identity(
    type_ref: Any,
    *,
    typed: Any,
    active: set[int],
    run_ref_projection=None,
) -> str | None:
    metadata = _loop_carrier_metadata(type_ref, typed=typed)
    if metadata is None:
        return None
    if metadata.family is None:
        raise RuntimeError("loop-state carrier has no retained declaration family")

    from ..type_env import RecordTypeRef

    if not isinstance(type_ref, RecordTypeRef):
        raise TypeError("loop-state carrier metadata was attached to a non-record type")
    fields = tuple(
        (field.name, type_ref.field_types[field.name])
        for field in type_ref.definition.fields
    )
    run_refs = run_ref_projection or _run_ref_signatures(typed)
    descriptor_rows = [
        [
            name,
            run_refs.key_type(field_type)
            if hasattr(run_refs, "key_type")
            else key_type_descriptor(
                canonical_type_descriptor(field_type, typed=typed),
                run_ref_signatures=run_refs,
            ),
        ]
        for name, field_type in fields
    ]
    key = [metadata.family, descriptor_rows]
    encoded = canonical_json_for_pure_value(key).encode("utf-8")
    head = (
        "workflow_lisp/private::loop-state-carrier$"
        + sha256(encoded).hexdigest()
    )
    arguments = " ".join(
        _canonical_identity(
            field_type,
            typed=typed,
            active=active,
            # Q uses a local projection when the public caller supplied none;
            # I must retain the caller's concrete producer context. The key
            # projection later erases that runtime spelling through S.
            run_ref_projection=run_ref_projection,
        )
        for _, field_type in fields
    )
    return f"{head}[{arguments}]"


def _canonical_identity(
    type_ref: Any,
    *,
    typed: Any,
    active: set[int],
    run_ref_projection=None,
) -> str:
    from ..type_env import (
        DiscriminantTypeRef,
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        RecordTypeRef,
        UnionTypeRef,
        VariantCaseTypeRef,
    )

    marker = id(type_ref)
    if marker in active:
        raise CanonicalNameError(getattr(type_ref, "name", type(type_ref).__name__))
    active.add(marker)
    try:
        if isinstance(type_ref, (PrimitiveTypeRef, PathTypeRef)):
            return _definition_owner_identity(type_ref, typed=typed)
        if isinstance(type_ref, RecordTypeRef):
            if _GENERATED_RESULT_NAME.fullmatch(type_ref.name):
                if run_ref_projection is not None:
                    return run_ref_projection.alias_for(type_ref)
                return type_ref.name
            carrier_identity = _loop_carrier_identity(
                type_ref,
                typed=typed,
                active=active,
                run_ref_projection=run_ref_projection,
            )
            if carrier_identity is not None:
                return carrier_identity
            return _definition_owner_identity(type_ref, typed=typed)
        if isinstance(type_ref, UnionTypeRef):
            template = _definition_owner_identity(type_ref, typed=typed)
            if not type_ref.type_args:
                return template
            args = " ".join(
                _canonical_identity(
                    arg,
                    typed=typed,
                    active=active,
                    run_ref_projection=run_ref_projection,
                )
                for arg in type_ref.type_args
            )
            return f"{template}[{args}]"
        if isinstance(type_ref, VariantCaseTypeRef):
            union_type = _union_for_variant(type_ref, typed=typed)
            template = _definition_owner_identity(union_type, typed=typed)
            if not type_ref.union_type_args:
                return f"{template}.variant"
            args = " ".join(
                _canonical_identity(
                    arg,
                    typed=typed,
                    active=active,
                    run_ref_projection=run_ref_projection,
                )
                for arg in type_ref.union_type_args
            )
            return f"{template}[{args}].variant"
        if isinstance(type_ref, DiscriminantTypeRef):
            union_ref = (
                type_ref.owner_union
                or type_ref.applied_union
                or _union_for_discriminant(type_ref, typed=typed)
            )
            union_identity = _canonical_identity(
                union_ref,
                typed=typed,
                active=active,
                run_ref_projection=run_ref_projection,
            )
            return f"{union_identity}.variant"
        if isinstance(type_ref, ListTypeRef):
            return f"List[{_canonical_identity(type_ref.item_type_ref, typed=typed, active=active, run_ref_projection=run_ref_projection)}]"
        if isinstance(type_ref, OptionalTypeRef):
            return f"Optional[{_canonical_identity(type_ref.item_type_ref, typed=typed, active=active, run_ref_projection=run_ref_projection)}]"
        if isinstance(type_ref, MapTypeRef):
            key = _canonical_identity(type_ref.key_type_ref, typed=typed, active=active, run_ref_projection=run_ref_projection)
            value = _canonical_identity(type_ref.value_type_ref, typed=typed, active=active, run_ref_projection=run_ref_projection)
            return f"Map[{key},{value}]"
        raise CanonicalNameError(getattr(type_ref, "name", type(type_ref).__name__))
    finally:
        active.remove(marker)


def canonical_type_identity(type_ref: Any, *, typed: Any) -> str:
    """Return a source-independent, owner-qualified identity for one checked type."""

    return _canonical_identity(type_ref, typed=typed, active=set())


def canonical_type_descriptor(
    type_ref: Any,
    *,
    typed: Any,
    _run_ref_projection=None,
) -> dict[str, Any]:
    """Build a normalized runtime descriptor with retained canonical names."""

    from ..type_env import (
        DiscriminantTypeRef,
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        RecordTypeRef,
        UnionTypeRef,
        VariantCaseTypeRef,
    )

    def field_rows(fields, field_types):
        return [
            {"name": field.name, "type": build(field_types[field.name])}
            for field in fields
        ]

    def identity(ref):
        return _canonical_identity(
            ref,
            typed=typed,
            active=set(),
            run_ref_projection=_run_ref_projection,
        )

    def build(ref):
        if isinstance(ref, PrimitiveTypeRef):
            if ref.allowed_values:
                return {
                    "kind": "enum",
                    "name": identity(ref),
                    "allowed": list(ref.allowed_values),
                }
            return {"kind": "primitive", "name": ref.name}
        if isinstance(ref, PathTypeRef):
            return {
                "kind": "path",
                "name": identity(ref),
                "under": ref.definition.under,
                "must_exist_target": ref.definition.must_exist,
            }
        if isinstance(ref, OptionalTypeRef):
            return {"kind": "optional", "item": build(ref.item_type_ref)}
        if isinstance(ref, ListTypeRef):
            return {"kind": "list", "item": build(ref.item_type_ref)}
        if isinstance(ref, MapTypeRef):
            return {
                "kind": "map",
                "key": build(ref.key_type_ref),
                "value": build(ref.value_type_ref),
            }
        if isinstance(ref, RecordTypeRef):
            generated_name = getattr(ref, "name", "")
            record_name = (
                _run_ref_projection.alias_for(ref)
                if _run_ref_projection is not None
                and _GENERATED_RESULT_NAME.fullmatch(generated_name)
                else generated_name
                if _GENERATED_RESULT_NAME.fullmatch(generated_name)
                else identity(ref)
            )
            return {
                "kind": "record",
                "name": record_name,
                "fields": field_rows(ref.definition.fields, ref.field_types),
            }
        if isinstance(ref, UnionTypeRef):
            return {
                "kind": "union",
                "name": identity(ref),
                "variants": [
                    {
                        "name": variant.name,
                        "fields": field_rows(
                            variant.fields,
                            ref.variant_field_types[variant.name],
                        ),
                    }
                    for variant in ref.definition.variants
                ],
            }
        if isinstance(ref, VariantCaseTypeRef):
            union_template = _definition_owner_identity(
                _union_for_variant(ref, typed=typed),
                typed=typed,
            )
            union_name = (
                f"{union_template}["
                + " ".join(identity(arg) for arg in ref.union_type_args)
                + "]"
                if ref.union_type_args
                else union_template
            )
            return {
                "kind": "variant_case",
                "union_name": union_name,
                "variant": ref.variant_name,
                "fields": field_rows(ref.definition.fields, ref.field_types or {}),
            }
        if isinstance(ref, DiscriminantTypeRef):
            return {
                "kind": "enum",
                "name": identity(ref),
                "allowed": list(ref.variant_names),
            }
        raise CanonicalNameError(getattr(ref, "name", type(ref).__name__))

    descriptor = build(type_ref)
    validate_compiler_normalized_type_descriptor(descriptor)
    return descriptor


class _RunRefProjection:
    """Project generated carriers from their retained exact TypeRef origins."""

    def __init__(self, typed: Any) -> None:
        self.typed = typed
        self.aliases: dict[int, str] = {}
        self.refs_by_alias: dict[str, Any] = {}
        self.signatures: dict[str, dict[str, Any]] = {}
        self.active: set[int] = set()
        self.next_alias = 1
        self.reserved_names = {
            type_ref.name
            for environment in _typed_type_envs(typed)
            for type_ref in getattr(environment, "_type_refs", {}).values()
            if isinstance(getattr(type_ref, "name", None), str)
        }

    def alias_for(self, type_ref: Any) -> str:
        marker = id(type_ref)
        alias = self.aliases.get(marker)
        if alias is not None:
            return alias
        if not isinstance(getattr(type_ref, "run_ref_origin", None), tuple):
            raise CanonicalNameError(getattr(type_ref, "name", type(type_ref).__name__))
        while True:
            alias = f"RunRefResult${self.next_alias:016x}"
            self.next_alias += 1
            if alias not in self.reserved_names:
                break
        self.reserved_names.add(alias)
        self.aliases[marker] = alias
        self.refs_by_alias[alias] = type_ref
        return alias

    def descriptor(self, type_ref: Any) -> dict[str, Any]:
        return canonical_type_descriptor(
            type_ref,
            typed=self.typed,
            _run_ref_projection=self,
        )

    def signature(self, type_ref: Any) -> dict[str, Any]:
        alias = self.alias_for(type_ref)
        existing = self.signatures.get(alias)
        if existing is not None:
            return existing
        marker = id(type_ref)
        if marker in self.active:
            raise ValueError(
                f"cyclic run-ref signature dependency for {type_ref.name!r}"
            )
        origin = type_ref.run_ref_origin
        if (
            not isinstance(origin, tuple)
            or len(origin) != 2
            or not isinstance(origin[1], tuple)
        ):
            raise CanonicalNameError(type_ref.name)
        self.active.add(marker)
        try:
            input_descriptors = [
                (formal, self.descriptor(input_ref))
                for formal, input_ref in origin[1]
            ]
            result_descriptor = self.descriptor(type_ref)
            dependencies = list(run_ref_type_dependencies(result_descriptor))
            for _, descriptor in input_descriptors:
                dependencies.extend(run_ref_type_dependencies(descriptor))
            for dependency in dict.fromkeys(dependencies):
                if dependency == alias:
                    continue
                dependency_ref = self.refs_by_alias.get(dependency)
                if dependency_ref is None:
                    raise CanonicalNameError(dependency)
                self.signature(dependency_ref)
            result = canonical_run_ref_signature(
                input_descriptors,
                {
                    "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
                    "envelope": result_descriptor,
                },
                run_ref_signatures=self.signatures,
            )
            self.signatures[alias] = result
            return result
        finally:
            self.active.remove(marker)

    def key_type(self, type_ref: Any) -> dict[str, Any]:
        descriptor = self.descriptor(type_ref)
        for dependency in run_ref_type_dependencies(descriptor):
            dependency_ref = self.refs_by_alias.get(dependency)
            if dependency_ref is None:
                raise CanonicalNameError(dependency)
            self.signature(dependency_ref)
        return key_type_descriptor(
            descriptor,
            run_ref_signatures=self.signatures,
        )


def _run_ref_signatures(typed: Any) -> _RunRefProjection:
    """Create lazy generated-name resolution from exact retained TypeRefs."""

    return _RunRefProjection(typed)


def _key_type_ref(type_ref: Any, *, typed: Any, run_ref_signatures) -> dict[str, Any]:
    from ..type_env import ProcRefTypeRef, WorkflowRefTypeRef

    def identity(ref):
        if isinstance(run_ref_signatures, _RunRefProjection):
            return run_ref_signatures.key_type(ref)
        return key_type_descriptor(
            canonical_type_descriptor(ref, typed=typed),
            run_ref_signatures=run_ref_signatures,
        )

    if isinstance(type_ref, ProcRefTypeRef):
        return {
            "kind": "procedure-reference",
            "signature": {
                "params": [identity(arg) for arg in type_ref.param_type_refs],
                "result": identity(type_ref.return_type_ref),
            },
        }
    if isinstance(type_ref, WorkflowRefTypeRef):
        return {
            "kind": "workflow-reference",
            "signature": {
                "params": [identity(arg) for arg in type_ref.param_type_refs],
                "result": identity(type_ref.return_type_ref),
            },
        }
    return identity(type_ref)


def _formal_sort_key(formal: Any) -> tuple[int, Any]:
    if (
        isinstance(formal, (list, tuple))
        and len(formal) == 2
        and formal[0] == "local"
        and type(formal[1]) is int
        and formal[1] >= 0
    ):
        return (0, formal[1])
    if isinstance(formal, str) and formal:
        return (1, formal)
    raise ValueError("definition binding formal selector is malformed")


def _formal_selector(definition: Any, formal: Any, *, typed: Any) -> Any:
    """Use local capture indexes while keeping ordinary formals as strings."""

    if not isinstance(formal, str):
        return deepcopy(formal)
    local_facts = getattr(typed, "local_definition_keys", {}).get(
        getattr(getattr(definition, "definition", None), "name", "")
    )
    specialization = getattr(definition, "specialization", None)
    if local_facts is None and specialization is not None:
        local_facts = getattr(typed, "local_definition_keys", {}).get(
            specialization.base_name
        )
    if isinstance(local_facts, (tuple, list)) and len(local_facts) == 6:
        capture_schema = local_facts[3]
        for index, row in enumerate(capture_schema):
            if isinstance(row, (tuple, list)) and len(row) == 2 and row[0] == formal:
                return ["local", index]
    return formal


def _binding_fact(mapping: Any, formal: Any, *, selector: Any | None = None) -> Any:
    """Read a plain binding-fact map using the source formal or wire selector."""

    if isinstance(mapping, Mapping):
        for key in (formal, tuple(selector) if isinstance(selector, list) else selector):
            if key is not None:
                try:
                    if key in mapping:
                        return mapping[key]
                except TypeError:
                    continue
        if isinstance(selector, list):
            encoded = canonical_json_for_pure_value(selector)
            if encoded in mapping:
                return mapping[encoded]
        return None
    if isinstance(mapping, Sequence) and not isinstance(mapping, (str, bytes)):
        for row in mapping:
            if isinstance(row, (tuple, list)) and len(row) == 2:
                if row[0] == selector or row[0] == formal:
                    return row[1]
    return None


def _source_expression_identity(value: Any, *, typed: Any) -> Any:
    """Compare retained checked expressions while excluding source coordinates."""

    from ..type_env import (
        DiscriminantTypeRef,
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        ProcRefTypeRef,
        RecordTypeRef,
        TypeParamRef,
        UnionTypeRef,
        VariantCaseTypeRef,
        WorkflowRefTypeRef,
    )

    type_ref_classes = (
        DiscriminantTypeRef,
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        ProcRefTypeRef,
        RecordTypeRef,
        TypeParamRef,
        UnionTypeRef,
        VariantCaseTypeRef,
        WorkflowRefTypeRef,
    )
    ignored_fields = {
        "span",
        "form_path",
        "expansion_stack",
        "keyword_span",
        "keyword_form_path",
        "keyword_expansion_stack",
        "definition_span",
        "source_identity",
    }

    def project(item: Any) -> Any:
        if isinstance(item, type_ref_classes):
            return ["type", _key_type_ref(item, typed=typed, run_ref_signatures=_run_ref_signatures(typed))]
        if item is None or type(item) in {str, int, float, bool}:
            return [type(item).__name__, item]
        if isinstance(item, Mapping):
            return [
                "mapping",
                [
                    [key, project(child)]
                    for key, child in sorted(item.items(), key=lambda pair: canonical_json_for_pure_value(pair[0]))
                ],
            ]
        if isinstance(item, (tuple, list)):
            return ["sequence", [project(child) for child in item]]
        if is_dataclass(item) and not isinstance(item, type):
            return [
                type(item).__name__,
                [
                    [field.name, project(getattr(item, field.name))]
                    for field in dataclass_fields(item)
                    if field.name not in ignored_fields
                    and not field.metadata.get("semantic_identity_omit")
                ],
            ]
        return [type(item).__name__]

    return project(value)


def _capture_fact_type(capture: Any, *, typed: Any, run_refs: Mapping[str, Any]) -> Any:
    if isinstance(capture, Mapping):
        type_ref = capture.get("type", capture.get("type_ref"))
    else:
        type_ref = getattr(capture, "type_ref", None)
    if type_ref is None:
        raise ValueError("capture facts require a typed capture type")
    return _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs)


def _capture_fact_routes(capture: Any) -> list[Any]:
    routes = capture.get("routes") if isinstance(capture, Mapping) else getattr(capture, "routes", None)
    if not isinstance(routes, Sequence) or isinstance(routes, (str, bytes)):
        raise ValueError("capture facts require an ordered route sequence")
    return list(routes)


def _remap_pref_capture_indices(
    reference: Mapping[str, Any], capture_map: Mapping[int, int]
) -> dict[str, Any]:
    """Move nested procedure-reference capture indexes into its caller key."""

    result = deepcopy(dict(reference))
    for row in result["bound"]:
        binding = row[2]
        if set(binding) == {"capture"}:
            index = binding["capture"]
            if index not in capture_map:
                raise ValueError("nested procedure capture has no enclosing route")
            binding["capture"] = capture_map[index]
        elif set(binding) == {"procedure"}:
            binding["procedure"] = _remap_pref_capture_indices(
                binding["procedure"], capture_map
            )
    return result


def _unify_type_params(pattern: Any, actual: Any, *, typed: Any, bindings: dict[str, Any]) -> None:
    """Recover concrete generic arguments from one retained typed signature."""

    from ..type_env import (
        DiscriminantTypeRef,
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        ProcRefTypeRef,
        RecordTypeRef,
        TypeParamRef,
        UnionTypeRef,
        VariantCaseTypeRef,
        WorkflowRefTypeRef,
    )

    if isinstance(pattern, TypeParamRef):
        existing = bindings.get(pattern.name)
        if existing is not None and _key_type_ref(
            existing, typed=typed, run_ref_signatures=_run_ref_signatures(typed)
        ) != _key_type_ref(actual, typed=typed, run_ref_signatures=_run_ref_signatures(typed)):
            raise ValueError(f"resolved signature gives conflicting type arguments for {pattern.name!r}")
        bindings[pattern.name] = actual
        return
    if isinstance(pattern, ListTypeRef) and isinstance(actual, ListTypeRef):
        _unify_type_params(pattern.item_type_ref, actual.item_type_ref, typed=typed, bindings=bindings)
        return
    if isinstance(pattern, OptionalTypeRef) and isinstance(actual, OptionalTypeRef):
        _unify_type_params(pattern.item_type_ref, actual.item_type_ref, typed=typed, bindings=bindings)
        return
    if isinstance(pattern, MapTypeRef) and isinstance(actual, MapTypeRef):
        _unify_type_params(pattern.key_type_ref, actual.key_type_ref, typed=typed, bindings=bindings)
        _unify_type_params(pattern.value_type_ref, actual.value_type_ref, typed=typed, bindings=bindings)
        return
    if isinstance(pattern, (ProcRefTypeRef, WorkflowRefTypeRef)) and isinstance(
        actual, type(pattern)
    ):
        if len(pattern.param_type_refs) != len(actual.param_type_refs):
            raise ValueError("resolved reference signature changes generic arity")
        for left, right in zip(pattern.param_type_refs, actual.param_type_refs):
            _unify_type_params(left, right, typed=typed, bindings=bindings)
        _unify_type_params(pattern.return_type_ref, actual.return_type_ref, typed=typed, bindings=bindings)
        return
    if isinstance(pattern, RecordTypeRef) and isinstance(actual, RecordTypeRef):
        pattern_origin = getattr(pattern, "run_ref_origin", None)
        actual_origin = getattr(actual, "run_ref_origin", None)
        if pattern_origin is not None or actual_origin is not None:
            if pattern_origin is None or actual_origin is None:
                raise ValueError("resolved signature changes a generated run-ref result")
            projection = _run_ref_signatures(typed)
            if _key_type_ref(pattern, typed=typed, run_ref_signatures=projection) != _key_type_ref(
                actual,
                typed=typed,
                run_ref_signatures=projection,
            ):
                raise ValueError("resolved signature changes a generated run-ref result")
            return
        if (
            _definition_owner_identity(pattern, typed=typed)
            != _definition_owner_identity(actual, typed=typed)
            or tuple(pattern.field_types) != tuple(actual.field_types)
        ):
            raise ValueError("resolved signature changes a nominal record declaration")
        for name in pattern.field_types:
            _unify_type_params(pattern.field_types[name], actual.field_types[name], typed=typed, bindings=bindings)
        return
    if isinstance(pattern, UnionTypeRef) and isinstance(actual, UnionTypeRef):
        if (
            _definition_owner_identity(pattern, typed=typed)
            != _definition_owner_identity(actual, typed=typed)
            or len(pattern.type_args) != len(actual.type_args)
        ):
            raise ValueError("resolved signature changes a nominal union declaration")
        for left, right in zip(pattern.type_args, actual.type_args):
            _unify_type_params(left, right, typed=typed, bindings=bindings)
        if not pattern.type_args:
            if set(pattern.variant_field_types) != set(actual.variant_field_types):
                raise ValueError("resolved signature changes union variants")
            for variant, fields in pattern.variant_field_types.items():
                if set(fields) != set(actual.variant_field_types[variant]):
                    raise ValueError("resolved signature changes union fields")
                for name, left in fields.items():
                    _unify_type_params(left, actual.variant_field_types[variant][name], typed=typed, bindings=bindings)
        return
    if isinstance(pattern, VariantCaseTypeRef) and isinstance(actual, VariantCaseTypeRef):
        if (
            _definition_owner_identity(pattern, typed=typed)
            != _definition_owner_identity(actual, typed=typed)
            or set(pattern.field_types or {}) != set(actual.field_types or {})
        ):
            raise ValueError("resolved signature changes a nominal variant case")
        for name, left in (pattern.field_types or {}).items():
            _unify_type_params(left, (actual.field_types or {})[name], typed=typed, bindings=bindings)
        for left, right in zip(pattern.union_type_args, actual.union_type_args):
            _unify_type_params(left, right, typed=typed, bindings=bindings)
        return
    if isinstance(pattern, DiscriminantTypeRef) and isinstance(actual, DiscriminantTypeRef):
        if pattern.applied_union is not None and actual.applied_union is not None:
            _unify_type_params(pattern.applied_union, actual.applied_union, typed=typed, bindings=bindings)
            return
    if _key_type_ref(
        pattern, typed=typed, run_ref_signatures=_run_ref_signatures(typed)
    ) != _key_type_ref(actual, typed=typed, run_ref_signatures=_run_ref_signatures(typed)):
        raise ValueError("resolved signature disagrees with its original typed declaration")


def _reference_source_and_selected(resolved: Any, *, typed: Any) -> tuple[Any, Any]:
    source = _find_typed_definition(typed, "procedure", resolved.procedure_name)
    target_name = getattr(resolved, "call_target_name", resolved.procedure_name)
    selected = _find_typed_definition(typed, "procedure", target_name)
    if source is None:
        source = selected
    if source is None:
        raise ValueError(f"resolved procedure declaration is unavailable: {resolved.procedure_name!r}")
    source_specialization = getattr(source, "specialization", None)
    source_name = (
        source_specialization.base_name
        if source_specialization is not None
        else source.definition.name
    )
    selected_specialization = getattr(selected, "specialization", None) if selected is not None else None
    if selected is not None and selected_specialization is not None:
        if selected_specialization.base_name != source_name:
            selected = None
    elif selected is source and getattr(resolved, "bound_args", ()):
        selected = None
    return source, selected


def _lift_capture_route(route: Any, selector: Any) -> Any:
    if not isinstance(route, Sequence) or isinstance(route, (str, bytes)) or not route:
        raise ValueError("capture route facts must be tagged sequences")
    if route[0] in {"parameter", "local"}:
        return ["reference", [deepcopy(selector)], deepcopy(list(route))]
    if route[0] == "reference" and len(route) == 3:
        return ["reference", [deepcopy(selector), *deepcopy(list(route[1]))], deepcopy(route[2])]
    raise ValueError("nested context capture requires checked conversion route facts")


def _reference_capture_prefix(
    resolved: Any,
    *,
    binding_facts: Mapping[str, Any],
    typed: Any,
    active: set[Any] | None = None,
) -> list[Any]:
    """Project capture requirements already carried by one resolved PRef."""

    active = active if active is not None else set()
    marker = (
        id(resolved),
        canonical_json_for_pure_value(
            _source_expression_identity(binding_facts, typed=typed)
        ),
    )
    if marker in active:
        raise ValueError("recursive capture-prefix requirements are not finite")
    active.add(marker)
    try:
        source, selected = _reference_source_and_selected(resolved, typed=typed)
        selector_owner = selected or source
        target_facts = dict(binding_facts.get("target", {}) or {})
        explicit = binding_facts.get(
            "target_captures", target_facts.get("captures")
        )
        if explicit is not None:
            return list(explicit)
        selected_spec = getattr(selector_owner, "specialization", None)
        proc_bindings = dict(getattr(selected_spec, "proc_ref_bindings", {}) or {})
        workflow_bindings = dict(getattr(selected_spec, "workflow_ref_bindings", {}) or {})
        bound_facts = binding_facts.get("bound", {}) or {}
        captures: list[dict[str, Any]] = []
        for arg in resolved.bound_args:
            selector = _formal_selector(selector_owner, arg.name, typed=typed)
            fact = _binding_fact(bound_facts, arg.name, selector=selector)
            if not isinstance(fact, Mapping) or len(fact) != 1:
                raise ValueError(f"bound procedure argument fact is missing or malformed for {arg.name!r}")
            category, payload = next(iter(fact.items()))
            if category == "capture":
                route = ["local", selector[1]] if isinstance(selector, list) else ["parameter", selector]
                captures.append({"type": arg.type_ref, "routes": [route]})
                continue
            if category == "procedure":
                nested = proc_bindings.get(arg.name)
                if nested is None and isinstance(payload, Mapping):
                    nested = payload.get("resolved")
                if nested is None:
                    nested = getattr(arg, "value_expr", None)
                if nested is None or not hasattr(nested, "bound_args"):
                    raise ValueError(f"nested resolved procedure value is missing for {arg.name!r}")
                nested_facts = payload.get("facts", payload) if isinstance(payload, Mapping) else {}
                for child_capture in _reference_capture_prefix(
                    nested,
                    binding_facts=nested_facts,
                    typed=typed,
                    active=active,
                ):
                    child_type = child_capture.get("type", child_capture.get("type_ref"))
                    child_routes = child_capture.get("routes")
                    if child_type is None or not isinstance(child_routes, Sequence):
                        raise ValueError("nested capture facts are malformed")
                    captures.append(
                        {
                            "type": child_type,
                            "routes": [
                                _lift_capture_route(route, selector)
                                for route in child_routes
                            ],
                        }
                    )
                continue
            if category == "workflow":
                nested = workflow_bindings.get(arg.name)
                if nested is None and isinstance(payload, Mapping):
                    nested = payload.get("resolved")
                if nested is None:
                    raise ValueError(f"nested resolved workflow value is missing for {arg.name!r}")
                continue
        return captures
    finally:
        active.remove(marker)


def _capture_index_mapping(
    target_captures: Sequence[Any],
    enclosing_captures: Sequence[Any],
    *,
    reference_path: Sequence[Any],
    typed: Any,
    run_refs: Mapping[str, Any],
) -> dict[int, int]:
    result: dict[int, int] = {}
    path = list(reference_path)
    for target_index, capture in enumerate(target_captures):
        capture_type = _capture_fact_type(capture, typed=typed, run_refs=run_refs)
        for route in _capture_fact_routes(capture):
            if not isinstance(route, Sequence) or isinstance(route, (str, bytes)) or not route:
                raise ValueError("capture route facts are malformed")
            if route[0] in {"parameter", "local"}:
                terminal = [route[0], route[1]]
                routed_path = path
            elif route[0] == "reference" and len(route) == 3:
                terminal = route[2]
                routed_path = [*path, *route[1]]
            else:
                continue
            external_route = ["reference", routed_path, terminal]
            matches = [
                index
                for index, enclosing in enumerate(enclosing_captures)
                if _capture_fact_type(enclosing, typed=typed, run_refs=run_refs)
                == capture_type
                and any(
                    canonical_json_for_pure_value(candidate)
                    == canonical_json_for_pure_value(external_route)
                    for candidate in _capture_fact_routes(enclosing)
                )
            ]
            if len(matches) != 1:
                raise ValueError("target capture route does not identify one enclosing capture")
            previous = result.get(target_index)
            if previous is not None and previous != matches[0]:
                raise ValueError("one target capture maps to competing enclosing captures")
            result[target_index] = matches[0]
    return result


def _remap_capture_fact_scope(facts: Any, index_map: Mapping[int, int]) -> Any:
    """Translate checked nested binding facts into an immediate target scope."""

    if not isinstance(facts, Mapping):
        return deepcopy(facts)
    result = deepcopy(dict(facts))
    bound = result.get("bound")
    if isinstance(bound, Mapping):
        remapped = {}
        for formal, fact in bound.items():
            if isinstance(fact, Mapping) and len(fact) == 1:
                category, payload = next(iter(fact.items()))
                if category == "capture" and type(payload) is int:
                    if payload not in index_map:
                        raise ValueError("nested capture fact has no target-scope route")
                    fact = {"capture": index_map[payload]}
                elif category in {"procedure", "workflow"} and isinstance(payload, Mapping):
                    fact = {category: _remap_capture_fact_scope(payload, index_map)}
            remapped[formal] = fact
        result["bound"] = remapped
    for section in ("procedure_references", "workflow_references"):
        rows = result.get(section)
        if isinstance(rows, Mapping):
            result[section] = {
                formal: _remap_capture_fact_scope(row, index_map)
                for formal, row in rows.items()
            }
    return result


def _normalize_closed_value(value: Any) -> Any:
    """Project one checked closed expression without source names or labels."""
    # Checked closed values retain binder/reference links but no binder
    # provenance. Reserving source spellings would break alpha equivalence
    # when a binder happens to be named ``%1``.
    renamer = Renamer()

    def bind_name(name: Any, env: dict[str, str]) -> str:
        if not isinstance(name, str) or not name:
            raise ValueError("closed-expression binder must have a nonempty name")
        return renamer.bind(name, authored_label=None, env=env)

    def closed_value(node: Any, env: dict[str, str]) -> Any:
        if not isinstance(node, Mapping) or not isinstance(node.get("k"), str):
            raise ValueError("checked closed expression must be a typed value node")
        kind = node["k"]
        if "@" in node:
            raise ValueError("closed expressions cannot retain source provenance")
        if kind == "lit":
            return {"k": "lit", "v": deepcopy(node["v"]), "type": deepcopy(node["type"])}
        if kind == "name":
            return {"k": "name", "n": renamer.ref(node["n"], env=env)}
        if kind == "field":
            return {
                "k": "field",
                "base": closed_value(node["base"], env),
                "path": deepcopy(node["path"]),
            }
        if kind in {"record", "inject"}:
            fields = [
                [field_name, closed_value(field_value, env)]
                for field_name, field_value in node["fields"]
            ]
            result = {"k": kind, "type": deepcopy(node["type"]), "fields": fields}
            if kind == "inject":
                result["variant"] = deepcopy(node["variant"])
                result = {
                    "k": "inject",
                    "type": deepcopy(node["type"]),
                    "variant": deepcopy(node["variant"]),
                    "fields": fields,
                }
            return result
        if kind == "op":
            return {
                "k": "op",
                "payload": deepcopy(node["payload"]),
                "args": [closed_value(child, env) for child in node["args"]],
            }
        if kind == "select":
            result = {"k": "select", "cond": closed_value(node["cond"], env)}
            for arm_name in ("then", "else"):
                arm = node[arm_name]
                arm_env = dict(env)
                prefix = []
                for row in arm["prefix"]:
                    row_value = closed_value(row["value"], arm_env)
                    wire_name = bind_name(row["name"], arm_env)
                    prefix.append({"name": wire_name, "value": row_value})
                result[arm_name] = {
                    "prefix": prefix,
                    "value": closed_value(arm["value"], arm_env),
                }
            return result
        if kind == "list":
            return {
                "k": "list",
                "items": [closed_value(child, env) for child in node["items"]],
                "type": deepcopy(node["type"]),
            }
        if kind == "list_map":
            source = closed_value(node["source"], env)
            body_env = dict(env)
            binder = bind_name(node["binder"], body_env)
            return {
                "k": "list_map",
                "binder": binder,
                "source": source,
                "body": closed_value(node["body"], body_env),
                "type": deepcopy(node["type"]),
            }
        if kind == "path_join":
            return {
                "k": "path_join",
                "base": closed_value(node["base"], env),
                "child": closed_value(node["child"], env),
                "type": deepcopy(node["type"]),
            }
        if kind == "block":
            return {"k": "block", "body": closed_body(node["body"], dict(env))}
        raise ValueError(f"unsupported checked closed-expression node {kind!r}")

    def closed_body(node: Any, env: dict[str, str]) -> Any:
        if not isinstance(node, Mapping) or not isinstance(node.get("k"), str):
            raise ValueError("checked closed expression body must be a body node")
        kind = node["k"]
        if "@" in node:
            raise ValueError("closed expressions cannot retain source provenance")
        if kind == "let":
            value = closed_value(node["value"], env)
            nested = dict(env)
            name = bind_name(node["name"], nested)
            return {
                "k": "let",
                "name": name,
                "value": value,
                "body": closed_body(node["body"], nested),
            }
        if kind in {"halt", "done"}:
            return {"k": kind, "value": closed_value(node["value"], env)}
        if kind == "if":
            return {
                "k": "if",
                "cond": closed_value(node["cond"], env),
                "then": closed_body(node["then"], dict(env)),
                "else": closed_body(node["else"], dict(env)),
            }
        if kind == "case":
            subject = closed_value(node["subject"], env)
            arms = []
            for arm in node["arms"]:
                arm_env = dict(env)
                wire_name = bind_name(arm["bind"], arm_env)
                arms.append(
                    {
                        "variant": deepcopy(arm["variant"]),
                        "bind": wire_name,
                        "body": closed_body(arm["body"], arm_env),
                    }
                )
            return {"k": "case", "subject": subject, "arms": arms}
        raise ValueError(f"unsupported checked closed-expression body {kind!r}")

    normalized = closed_value(value, {})
    canonical_json_for_pure_value(normalized)
    return normalized


def _find_typed_definition(typed: Any, kind: str, name: str) -> Any:
    seen_programs: set[int] = set()
    pending = [typed]
    while pending:
        program = pending.pop(0)
        if id(program) in seen_programs:
            continue
        seen_programs.add(id(program))
        table = getattr(program, "procedures" if kind == "procedure" else "workflows", {})
        value = table.get(name)
        if value is not None:
            return value
        for value in table.values():
            if getattr(getattr(value, "definition", None), "name", None) == name:
                return value
            specialization = getattr(value, "specialization", None)
            if getattr(specialization, "specialized_name", None) == name:
                return value
        pending.extend(getattr(program, "imported_programs", {}).values())
    return None


def _callable_header(definition: Any, *, typed: Any) -> tuple[str, str, Any, bool]:
    from ..procedures import TypedProcedureDef
    from ..workflows import TypedWorkflowDef

    if isinstance(definition, TypedProcedureDef):
        kind = "procedure"
    elif isinstance(definition, TypedWorkflowDef):
        kind = "workflow"
    else:
        raise TypeError("canonical definition key requires a typed procedure or workflow")
    specialization = getattr(definition, "specialization", None)
    callable_name = (
        specialization.base_name
        if specialization is not None
        else definition.definition.name
    )
    module, separator, declared_name = callable_name.partition("::")
    if not separator:
        module = getattr(typed, "entry_module", None) or "entry"
        declared_name = callable_name
    local_facts = getattr(typed, "local_definition_keys", {}).get(
        definition.definition.name
    )
    if local_facts is None and specialization is not None:
        local_facts = getattr(typed, "local_definition_keys", {}).get(
            specialization.base_name
        )
    is_local = isinstance(local_facts, (tuple, list)) and len(local_facts) == 6
    if is_local:
        owner_name, local_name, _legacy_ordinal = local_facts[:3]
        local_did = getattr(typed, "local_definition_dids", {}).get(
            definition.definition.name
        )
        if local_did is None and specialization is not None:
            local_did = getattr(typed, "local_definition_dids", {}).get(
                specialization.base_name
            )
        if (
            not isinstance(local_did, (list, tuple))
            or len(local_did) != 3
            or local_did[1] != "procedure"
            or not isinstance(local_did[2], Mapping)
            or set(local_did[2]) != {"owner", "name", "ordinal"}
        ):
            raise ValueError("local definition has no retained full declaration DId")
        module, local_kind, local_decl = local_did
        local_owner = local_decl["owner"]
        if (
            not isinstance(local_owner, (list, tuple))
            or len(local_owner) != 3
            or local_owner[1] not in {"procedure", "workflow"}
            or local_decl["name"] != local_name
            or type(local_decl["ordinal"]) is not int
            or local_decl["ordinal"] < 0
        ):
            raise ValueError("retained local declaration DId is malformed")
        qualified_owner = f"{local_owner[0]}::{local_owner[2]}"
        if qualified_owner != owner_name:
            raise ValueError("local definition owner DId disagrees with legacy local facts")
        owner_candidate = _find_typed_definition(typed, local_owner[1], qualified_owner)
        if owner_candidate is None:
            raise ValueError("local definition's retained owner callable is missing")
        owner = _callable_header(owner_candidate, typed=typed)
        if [owner[0], owner[1], owner[2]] != list(local_owner):
            raise ValueError("local definition owner DId disagrees with typed callable")
        return module, local_kind, local_decl, True
    return module, kind, declared_name, False


def _definition_key(
    definition: Any,
    *,
    typed: Any,
    binding_facts: Mapping[str, Any],
    capture_parameters: Sequence[Any],
    residual_signature: Mapping[str, Any] | None,
    active: set[Any],
) -> list[Any]:
    from ..type_env import (
        ProcRefTypeRef,
        WorkflowRefTypeRef,
    )

    marker = (
        id(definition),
        canonical_json_for_pure_value(
            _source_expression_identity(
                (binding_facts, capture_parameters, residual_signature), typed=typed
            )
        ),
    )
    if marker in active:
        raise ValueError("recursive callable binding keys are not finite")
    active.add(marker)
    try:
        module, kind, declaration, is_local = _callable_header(definition, typed=typed)
        specialization = getattr(definition, "specialization", None)
        run_refs = _run_ref_signatures(typed)

        type_bindings = getattr(specialization, "type_bindings", {}) or {}
        types = [
            [formal, _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs)]
            for formal, type_ref in sorted(type_bindings.items())
        ]

        nested_facts = binding_facts.get("procedure_references", {}) or {}
        procedure_bindings = getattr(specialization, "proc_ref_bindings", {}) or {}
        procedures = []
        for formal, resolved in procedure_bindings.items():
            selector = _formal_selector(definition, formal, typed=typed)
            procedures.append(
                [
                    selector,
                    _procedure_reference_key(
                        resolved,
                        typed=typed,
                        binding_facts=_binding_fact(
                            nested_facts, formal, selector=selector
                        ) or {},
                        capture_parameters=capture_parameters,
                        reference_path=[selector],
                        active=active,
                    ),
                ]
            )
        procedures.sort(key=lambda row: _formal_sort_key(row[0]))

        workflow_facts = binding_facts.get("workflow_references", {}) or {}
        workflow_bindings = getattr(specialization, "workflow_ref_bindings", {}) or {}
        workflows = []
        for formal, resolved in workflow_bindings.items():
            selector = _formal_selector(definition, formal, typed=typed)
            workflows.append(
                [
                    selector,
                    _workflow_reference_key(
                        resolved,
                        typed=typed,
                        binding_facts=_binding_fact(
                            workflow_facts, formal, selector=selector
                        ) or {},
                        active=active,
                    ),
                ]
            )
        workflows.sort(key=lambda row: _formal_sort_key(row[0]))

        closed_values = binding_facts.get("closed_values", {}) or {}
        value_bindings = getattr(specialization, "value_bindings", {}) or {}
        value_types = getattr(specialization, "bound_param_types", {}) or {}
        values = []
        for formal, source_value in value_bindings.items():
            selector = _formal_selector(definition, formal, typed=typed)
            fact = _binding_fact(closed_values, formal, selector=selector)
            if fact is None:
                raise ValueError(
                    f"checked closed value fact is missing for binding {formal!r}"
                )
            if isinstance(fact, Mapping) and set(fact) == {"type", "value"}:
                type_ref = fact["type"]
                value = fact["value"]
            else:
                type_ref = value_types.get(formal)
                value = fact
            if type_ref is None:
                raise ValueError(f"closed value type fact is missing for {formal!r}")
            values.append(
                [
                    selector,
                    _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs),
                    _normalize_closed_value(value),
                ]
            )
        values.sort(key=lambda row: _formal_sort_key(row[0]))

        captures = []
        for capture in capture_parameters:
            if isinstance(capture, Mapping):
                capture_type = capture.get("type", capture.get("type_ref"))
                routes = capture.get("routes")
            else:
                capture_type = getattr(capture, "type_ref", None)
                routes = getattr(capture, "routes", None)
            if capture_type is None or not isinstance(routes, Sequence) or isinstance(routes, (str, bytes)):
                raise ValueError("capture parameter facts require type and routes")
            canonical_routes = sorted(
                {canonical_json_for_pure_value(route): deepcopy(route) for route in routes}.values(),
                key=canonical_json_for_pure_value,
            )
            if not canonical_routes:
                raise ValueError("runtime capture requires at least one owner route")
            captures.append(
                {
                    "type": _key_type_ref(capture_type, typed=typed, run_ref_signatures=run_refs),
                    "routes": canonical_routes,
                }
            )

        declared_params = tuple(getattr(definition.signature, "params", ()))
        compile_time_names = (
            set(type_bindings)
            | set(procedure_bindings)
            | set(workflow_bindings)
            | set(value_bindings)
        )
        derived_params = [
            type_ref
            for name, type_ref in declared_params
            if name not in compile_time_names
        ]
        derived_result = definition.signature.return_type_ref
        if residual_signature is not None:
            supplied_params = residual_signature.get("params")
            supplied_result = residual_signature.get("result")
            if (
                not isinstance(supplied_params, Sequence)
                or isinstance(supplied_params, (str, bytes))
                or supplied_result is None
            ):
                raise ValueError("residual signature facts are malformed")
            derived_key = {
                "params": [
                    _key_type_ref(ref, typed=typed, run_ref_signatures=run_refs)
                    for ref in derived_params
                ],
                "result": _key_type_ref(
                    derived_result, typed=typed, run_ref_signatures=run_refs
                ),
            }
            supplied_key = {
                "params": [
                    _key_type_ref(ref, typed=typed, run_ref_signatures=run_refs)
                    for ref in supplied_params
                ],
                "result": _key_type_ref(
                    supplied_result, typed=typed, run_ref_signatures=run_refs
                ),
            }
            if supplied_key != derived_key:
                raise ValueError("residual signature facts disagree with the typed callable")
        param_rows = derived_params
        result_ref = derived_result
        residual = {
            "params": [
                _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs)
                for type_ref in param_rows
            ],
            "result": _key_type_ref(result_ref, typed=typed, run_ref_signatures=run_refs),
        }
        if is_local:
            owner_did = declaration["owner"]
            module = owner_did[0]
        return [module, kind, declaration, types, procedures, workflows, values, captures, residual]
    finally:
        active.remove(marker)


def _procedure_reference_key(
    resolved: Any,
    *,
    typed: Any,
    binding_facts: Mapping[str, Any],
    capture_parameters: Sequence[Any],
    reference_path: Sequence[Any],
    active: set[Any],
) -> dict[str, Any]:
    from ..type_env import TypeParamRef, substitute_type_params

    base = _find_typed_definition(typed, "procedure", resolved.procedure_name)
    target_name = getattr(resolved, "call_target_name", resolved.procedure_name)
    selected = _find_typed_definition(typed, "procedure", target_name)
    source = base or selected
    if source is None:
        raise ValueError(f"resolved procedure declaration is unavailable: {resolved.procedure_name!r}")
    source_specialization = getattr(source, "specialization", None)
    source_name = (
        source_specialization.base_name
        if source_specialization is not None
        else source.definition.name
    )
    selected_specialization = getattr(selected, "specialization", None) if selected is not None else None
    if selected is not None and selected_specialization is not None:
        selected_base = selected_specialization.base_name
        if selected_base != source_name:
            selected = None
            selected_specialization = None
    if selected is source and source_specialization is None and target_name != resolved.procedure_name:
        selected = None
        selected_specialization = None
    if selected is not None and selected_specialization is None and resolved.bound_args:
        selected = None

    bound_args = {arg.name: arg for arg in resolved.bound_args}
    if len(bound_args) != len(resolved.bound_args):
        raise ValueError("resolved procedure reference repeats a bound formal")
    binding_facts = binding_facts or {}
    target_facts = dict(binding_facts.get("target", {}) or {})
    for forbidden in ("residual_signature", "target_residual", "key", "target_key"):
        if forbidden in target_facts:
            raise ValueError(f"procedure target facts may not supply {forbidden}")
    bound_facts = binding_facts.get("bound", {}) or {}
    run_refs = _run_ref_signatures(typed)

    # Merge retained specialization maps with the resolved additions.  Map
    # conflicts are checked by their semantic projections, never by repr.
    source_maps = {
        name: dict(getattr(source_specialization, name, {}) or {})
        for name in (
            "type_bindings",
            "proc_ref_bindings",
            "workflow_ref_bindings",
            "value_bindings",
            "bound_param_types",
        )
    }
    selected_maps = {
        name: dict(getattr(selected_specialization, name, {}) or {})
        for name in source_maps
    } if selected_specialization is not None else {name: {} for name in source_maps}

    def same_fact(left: Any, right: Any) -> bool:
        if left is right:
            return True
        try:
            return _source_expression_identity(left, typed=typed) == _source_expression_identity(right, typed=typed)
        except (TypeError, ValueError, RecursionError):
            return False

    def merge_map(name: str, *sources: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for source_map in sources:
            for formal, value in source_map.items():
                previous = result.get(formal)
                if previous is not None and not same_fact(previous, value):
                    raise ValueError(f"specialization facts conflict for {name}.{formal}")
                result[formal] = value
        return result

    from ..type_env import (
        DiscriminantTypeRef,
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        ProcRefTypeRef,
        RecordTypeRef,
        TypeParamRef as TypeParamRefClass,
        UnionTypeRef,
        VariantCaseTypeRef,
        WorkflowRefTypeRef,
    )
    type_ref_classes = (
        DiscriminantTypeRef, ListTypeRef, MapTypeRef, OptionalTypeRef,
        PathTypeRef, PrimitiveTypeRef, ProcRefTypeRef, RecordTypeRef,
        TypeParamRefClass, UnionTypeRef, VariantCaseTypeRef, WorkflowRefTypeRef,
    )
    type_facts = target_facts.get("type_bindings", {}) or {}
    if not isinstance(type_facts, Mapping):
        raise ValueError("target type binding facts must be a mapping")
    if any(
        not isinstance(formal, str) or not isinstance(ref, type_ref_classes)
        for formal, ref in type_facts.items()
    ):
        raise ValueError("target type binding facts must contain TypeRefs")
    type_bindings = merge_map("type bindings", source_maps["type_bindings"], selected_maps["type_bindings"], type_facts)
    proc_bindings = merge_map("procedure references", source_maps["proc_ref_bindings"], selected_maps["proc_ref_bindings"])
    workflow_bindings = merge_map("workflow references", source_maps["workflow_ref_bindings"], selected_maps["workflow_ref_bindings"])
    value_bindings = merge_map("value bindings", source_maps["value_bindings"], selected_maps["value_bindings"])
    bound_param_types = merge_map("bound parameter types", source_maps["bound_param_types"], selected_maps["bound_param_types"])

    if any(not isinstance(formal, str) or not isinstance(ref, type_ref_classes) for formal, ref in type_bindings.items()):
        raise ValueError("merged target type bindings must contain TypeRefs")

    source_signature = source.signature
    inferred = dict(type_bindings)
    source_params = tuple(source_signature.params)
    resolved_param_rows = tuple(resolved.signature_params)
    if len(source_params) == len(resolved_param_rows) and [n for n, _ in source_params] == [n for n, _ in resolved_param_rows]:
        for (_, expected), (_, actual) in zip(source_params, resolved_param_rows):
            _unify_type_params(expected, actual, typed=typed, bindings=inferred)
        _unify_type_params(source_signature.return_type_ref, resolved.return_type_ref, typed=typed, bindings=inferred)
    elif not source_specialization:
        raise ValueError("resolved procedure signature does not correspond to its retained declaration")
    type_bindings = inferred
    for name, type_ref in type_bindings.items():
        previous = (selected_maps["type_bindings"].get(name) or source_maps["type_bindings"].get(name))
        if previous is not None and _key_type_ref(previous, typed=typed, run_ref_signatures=run_refs) != _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs):
            raise ValueError(f"resolved procedure changes inherited type binding {name!r}")

    bound_categories: dict[str, tuple[str, Any, Any]] = {}
    captured_formals: set[str] = set()
    closed_values = dict(target_facts.get("closed_values", {}) or {})
    target_procedure_facts = dict(target_facts.get("procedure_references", {}) or {})
    target_workflow_facts = dict(target_facts.get("workflow_references", {}) or {})
    for formal, arg in bound_args.items():
        selector = _formal_selector(source, formal, typed=typed)
        fact = _binding_fact(bound_facts, formal, selector=selector)
        if not isinstance(fact, Mapping) or len(fact) != 1:
            raise ValueError(f"bound procedure argument fact is missing or malformed for {formal!r}")
        category, payload = next(iter(fact.items()))
        if category not in {"value", "capture", "procedure", "workflow"}:
            raise ValueError(f"bound procedure argument category is invalid for {formal!r}")
        if formal in bound_param_types and _key_type_ref(
            bound_param_types[formal], typed=typed, run_ref_signatures=run_refs
        ) != _key_type_ref(arg.type_ref, typed=typed, run_ref_signatures=run_refs):
            raise ValueError(f"bound procedure argument type disagrees for {formal!r}")
        bound_param_types[formal] = arg.type_ref
        bound_categories[formal] = (category, payload, selector)
        if category == "value":
            retained_value = value_bindings.get(formal)
            if retained_value is not None and not same_fact(retained_value, arg.value_expr):
                raise ValueError(f"bound procedure value conflicts with retained target fact {formal!r}")
            value_bindings[formal] = arg.value_expr
            if not isinstance(payload, Mapping) or not isinstance(payload.get("k"), str):
                raise ValueError(f"checked closed value fact is malformed for {formal!r}")
            closed_values[formal] = {"type": arg.type_ref, "value": payload}
        elif category == "capture":
            captured_formals.add(formal)
            value_bindings.pop(formal, None)
        elif category == "procedure":
            nested = proc_bindings.get(formal)
            if nested is None and getattr(arg, "value_expr", None) is not None:
                if hasattr(arg.value_expr, "procedure_name") and hasattr(arg.value_expr, "bound_args"):
                    nested = arg.value_expr
            if nested is None and isinstance(payload, Mapping):
                nested = payload.get("resolved")
            if nested is None:
                raise ValueError(f"nested resolved procedure value is missing for {formal!r}")
            previous = proc_bindings.get(formal)
            if previous is not None and not same_fact(previous, nested):
                raise ValueError(f"nested procedure fact conflicts for {formal!r}")
            proc_bindings[formal] = nested
            if isinstance(payload, Mapping):
                target_procedure_facts[formal] = payload.get("facts", payload)
        elif category == "workflow":
            nested = workflow_bindings.get(formal)
            if nested is None and isinstance(payload, Mapping):
                nested = payload.get("resolved")
            if nested is None:
                raise ValueError(f"nested resolved workflow value is missing for {formal!r}")
            previous = workflow_bindings.get(formal)
            if previous is not None and not same_fact(previous, nested):
                raise ValueError(f"nested workflow fact conflicts for {formal!r}")
            workflow_bindings[formal] = nested
            if isinstance(payload, Mapping):
                target_workflow_facts[formal] = payload.get("facts", payload)

    # The target's substituted signature is a retained fact.  Apply exactly
    # the existing specialization map, then remove this reference's bound
    # formals in the source's ordered parameter sequence.
    substituted_params = tuple(
        (name, substitute_type_params(type_ref, type_bindings))
        for name, type_ref in source_params
    )
    substituted_result = substitute_type_params(source_signature.return_type_ref, type_bindings)
    if len(substituted_params) == len(resolved_param_rows) and [n for n, _ in substituted_params] == [n for n, _ in resolved_param_rows]:
        for (_, expected), (_, actual) in zip(substituted_params, resolved_param_rows):
            if _key_type_ref(expected, typed=typed, run_ref_signatures=run_refs) != _key_type_ref(actual, typed=typed, run_ref_signatures=run_refs):
                raise ValueError("resolved procedure parameter types disagree after substitution")
    elif not source_specialization:
        raise ValueError("resolved procedure parameter partition disagrees with source signature")
    if _key_type_ref(substituted_result, typed=typed, run_ref_signatures=run_refs) != _key_type_ref(
        resolved.return_type_ref, typed=typed, run_ref_signatures=run_refs
    ):
        raise ValueError("resolved procedure result type disagrees after substitution")
    bound_names = set(bound_categories)
    residual_names = [name for name, _ in resolved.residual_params]
    expected_residual = [
        name for name, _ in resolved.signature_params if name not in bound_names
    ]
    if residual_names != expected_residual:
        raise ValueError("resolved procedure residual does not preserve the ordered bound partition")
    for name, type_ref in resolved.residual_params:
        expected = dict(resolved.signature_params).get(name)
        if expected is None or _key_type_ref(expected, typed=typed, run_ref_signatures=run_refs) != _key_type_ref(
            type_ref, typed=typed, run_ref_signatures=run_refs
        ):
            raise ValueError("resolved procedure residual type differs from its source partition")

    # A retained selected row is preferred, but never trusted as a matcher.
    # When absent, this plain overlay describes the same typed declaration
    # without running specialization or typechecking again.
    if selected is not None:
        selected_params = tuple(selected.signature.params)
        if [name for name, _ in selected_params] != residual_names or any(
            _key_type_ref(actual, typed=typed, run_ref_signatures=run_refs)
            != _key_type_ref(expected, typed=typed, run_ref_signatures=run_refs)
            for (_, actual), (_, expected) in zip(selected_params, resolved.residual_params)
        ) or _key_type_ref(selected.signature.return_type_ref, typed=typed, run_ref_signatures=run_refs) != _key_type_ref(
            resolved.return_type_ref, typed=typed, run_ref_signatures=run_refs
        ):
            raise ValueError("materialized procedure specialization disagrees with resolved signature")

    # Runtime bindings that happen to be stored in value_bindings (for
    # example NameExpr) belong to the capture prefix, never K[6].
    target_captures = list(
        binding_facts.get("target_captures", target_facts.get("captures"))
        or _reference_capture_prefix(
            resolved,
            binding_facts=binding_facts,
            typed=typed,
        )
    )
    for formal, (category, payload, selector) in bound_categories.items():
        if category != "capture":
            continue
        if type(payload) is not int or payload < 0 or payload >= len(capture_parameters):
            raise ValueError("procedure-reference capture index is outside its enclosing key")
        route = ["local", selector[1]] if isinstance(selector, list) else ["parameter", selector]
        arg_type = bound_args[formal].type_ref
        arg_key_type = _key_type_ref(arg_type, typed=typed, run_ref_signatures=run_refs)
        matching = [
            row_index
            for row_index, capture in enumerate(target_captures)
            if _capture_fact_type(capture, typed=typed, run_refs=run_refs)
            == arg_key_type
            and route in _capture_fact_routes(capture)
        ]
        if len(matching) > 1:
            raise ValueError("runtime binding has ambiguous target capture facts")
        if not matching:
            target_captures.append({"type": arg_type, "routes": [route]})

    # Nested checked facts are written in the enclosing callable's capture
    # indexes.  The target key has its own compact prefix, so translate only
    # those fact indexes before constructing K.  The canonical nested target
    # itself is constructed once in its own scope and lifted below.
    target_to_outer = _capture_index_mapping(
        target_captures,
        capture_parameters,
        reference_path=reference_path,
        typed=typed,
        run_refs=run_refs,
    )
    outer_to_target = {outer: target for target, outer in target_to_outer.items()}
    for formal, (category, payload, _selector) in bound_categories.items():
        if category == "procedure" and isinstance(payload, Mapping):
            nested_facts = payload.get("facts", payload)
            if isinstance(nested_facts, Mapping):
                target_procedure_facts[formal] = _remap_capture_fact_scope(
                    nested_facts, outer_to_target
                )
        elif category == "workflow" and isinstance(payload, Mapping):
            nested_facts = payload.get("facts", payload)
            if isinstance(nested_facts, Mapping):
                target_workflow_facts[formal] = _remap_capture_fact_scope(
                    nested_facts, outer_to_target
                )
    for capture in target_captures:
        for route in _capture_fact_routes(capture):
            if isinstance(route, Sequence) and route and route[0] in {"parameter", "local"}:
                terminal_selector = (
                    route[1]
                    if route[0] == "parameter"
                    else ["local", route[1]]
                )
                for formal, (category, _payload, selector) in bound_categories.items():
                    if category == "value" and selector == terminal_selector:
                        raise ValueError("one target formal is both a closed value and a runtime capture")

    effective_captures = {
        name: capture
        for name, capture in value_bindings.items()
        if not any(
            isinstance(route, Sequence)
            and route
            and ((route[0] == "parameter" and route[1] == name)
                 or (route[0] == "local" and ["local", route[1]] == _formal_selector(source, name, typed=typed)))
            for capture in target_captures
            for route in _capture_fact_routes(capture)
        )
    }
    target_facts["closed_values"] = closed_values
    if target_procedure_facts:
        target_facts["procedure_references"] = target_procedure_facts
    if target_workflow_facts:
        target_facts["workflow_references"] = target_workflow_facts
    effective_specialization = SimpleNamespace(
        base_name=source_name,
        specialized_name=target_name,
        type_bindings=type_bindings,
        proc_ref_bindings=proc_bindings,
        workflow_ref_bindings=workflow_bindings,
        value_bindings=effective_captures,
        bound_param_types=bound_param_types,
    )
    target_body = selected if selected is not None else source
    target_view = dataclass_replace(
        target_body,
        signature=dataclass_replace(
            target_body.signature,
            params=tuple(resolved.residual_params),
            return_type_ref=resolved.return_type_ref,
        ),
        specialization=effective_specialization,
    )
    target_key = _definition_key(
        target_view,
        typed=typed,
        binding_facts=target_facts,
        capture_parameters=target_captures,
        residual_signature=None,
        active=active,
    )
    residual = deepcopy(target_key[8])
    expected_residual = {
        "params": [
            _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs)
            for _, type_ref in resolved.residual_params
        ],
        "result": _key_type_ref(resolved.return_type_ref, typed=typed, run_ref_signatures=run_refs),
    }
    if residual != expected_residual:
        raise ValueError("resolved procedure residual does not match its merged target")

    # Derive the entire bound table from the one converted target K.  Only
    # the reference view's capture indexes are lifted to the enclosing scope.
    expected: dict[str, tuple[Any, Any, Any]] = {}

    def add_expected(selector: Any, descriptor: Any, binding: Any) -> None:
        encoded = canonical_json_for_pure_value(selector)
        if encoded in expected:
            raise ValueError("target specialization binds one formal through multiple categories")
        expected[encoded] = (deepcopy(selector), descriptor, binding)

    for selector, nested in target_key[4]:
        add_expected(selector, {"kind": "procedure-reference", "signature": deepcopy(nested["residual"])}, {"procedure": nested})
    for selector, nested in target_key[5]:
        add_expected(selector, {"kind": "workflow-reference", "signature": deepcopy(nested["target"][8])}, {"workflow": nested})
    for selector, descriptor, value in target_key[6]:
        add_expected(selector, descriptor, {"value": value})

    capture_map: dict[int, int] = {}
    path = list(reference_path)
    for target_index, capture in enumerate(target_key[7]):
        for route in capture["routes"]:
            if route[0] in {"parameter", "local"}:
                terminal = [route[0], route[1]]
                routed_path = path
            elif route[0] == "reference":
                terminal = route[2]
                routed_path = [*path, *route[1]]
            else:
                continue
            external_route = ["reference", routed_path, terminal]
            matches = [
                index
                for index, outer_capture in enumerate(capture_parameters)
                if _capture_fact_type(outer_capture, typed=typed, run_refs=run_refs) == capture["type"]
                and any(
                    canonical_json_for_pure_value(candidate)
                    == canonical_json_for_pure_value(external_route)
                    for candidate in _capture_fact_routes(outer_capture)
                )
            ]
            if len(matches) != 1:
                raise ValueError("target capture route does not identify one enclosing capture")
            previous = capture_map.get(target_index)
            if previous is not None and previous != matches[0]:
                raise ValueError("one target capture maps to competing enclosing captures")
            capture_map[target_index] = matches[0]
            if route[0] in {"parameter", "local"}:
                selector = route[1] if route[0] == "parameter" else ["local", route[1]]
                add_expected(selector, capture["type"], {"capture": matches[0]})

    rows = [
        [selector, deepcopy(descriptor), deepcopy(binding)]
        for selector, descriptor, binding in expected.values()
    ]
    rows.sort(key=lambda row: _formal_sort_key(row[0]))
    actual = {canonical_json_for_pure_value(selector): (descriptor, binding) for selector, descriptor, binding in rows}
    for formal, (category, payload, selector) in bound_categories.items():
        encoded = canonical_json_for_pure_value(selector)
        if encoded not in actual:
            raise ValueError(f"resolved bound formal is absent from target K: {formal!r}")
        descriptor, binding = actual[encoded]
        if descriptor != _key_type_ref(bound_args[formal].type_ref, typed=typed, run_ref_signatures=run_refs):
            raise ValueError(f"resolved bound formal type disagrees with target K: {formal!r}")
        if category == "value":
            supplied = {"value": _normalize_closed_value(payload)}
            if canonical_json_for_pure_value(supplied) != canonical_json_for_pure_value(binding):
                raise ValueError(f"closed bound expression disagrees with target K: {formal!r}")
        elif category == "capture":
            if binding != {"capture": payload}:
                raise ValueError(f"runtime bound capture disagrees with target routes: {formal!r}")
        elif category == "procedure" and set(binding) != {"procedure"}:
            raise ValueError(f"nested procedure binding disagrees with target K: {formal!r}")
        elif category == "workflow" and set(binding) != {"workflow"}:
            raise ValueError(f"nested workflow binding disagrees with target K: {formal!r}")

    for row in rows:
        binding = row[2]
        if set(binding) == {"procedure"}:
            binding["procedure"] = _remap_pref_capture_indices(binding["procedure"], capture_map)
    return {"target": target_key, "residual": residual, "bound": rows}


def _workflow_reference_key(
    resolved: Any,
    *,
    typed: Any,
    binding_facts: Mapping[str, Any],
    active: set[int],
) -> dict[str, Any]:
    target = _find_typed_definition(typed, "workflow", resolved.workflow_name)
    if target is None:
        raise ValueError(f"resolved workflow target is unavailable: {resolved.workflow_name!r}")
    target_facts = dict(binding_facts.get("target", {}) or {})
    target_facts.pop("residual_signature", None)
    target_facts.pop("target_residual", None)
    target_facts.pop("key", None)
    target_facts.pop("target_key", None)
    target_captures = binding_facts.get(
        "target_captures", target_facts.get("captures", ())
    ) or ()
    target_key = _definition_key(
        target,
        typed=typed,
        binding_facts=target_facts,
        capture_parameters=target_captures,
        residual_signature=None,
        active=active,
    )
    run_refs = _run_ref_signatures(typed)
    resolved_residual = {
        "params": [
            _key_type_ref(type_ref, typed=typed, run_ref_signatures=run_refs)
            for _, type_ref in resolved.signature_params
        ],
        "result": _key_type_ref(
            resolved.return_type_ref, typed=typed, run_ref_signatures=run_refs
        ),
    }
    if target_key[8] != resolved_residual:
        raise ValueError("resolved workflow signature does not match its typed target")
    externs = binding_facts.get("externs")
    if externs is None:
        plan = resolved.extern_rebinding_plan
        if plan.provider_bindings or plan.prompt_bindings:
            raise ValueError("workflow reference requires exact resolved extern rows")
        externs = {"providers": [], "prompts": []}
    if not isinstance(externs, Mapping) or set(externs) != {"providers", "prompts"}:
        raise ValueError("workflow reference extern rows are malformed")
    projected = {}
    for category in ("providers", "prompts"):
        planned = getattr(resolved.extern_rebinding_plan, f"{category[:-1]}_bindings")
        rows = externs[category]
        if isinstance(rows, Mapping):
            row_pairs = list(rows.items())
        elif isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            row_pairs = []
            for row in rows:
                if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != 2:
                    raise ValueError("workflow reference extern row is malformed")
                row_pairs.append((row[0], row[1]))
        else:
            raise ValueError("workflow reference extern rows must be a mapping or array")
        if (
            any(not isinstance(formal, str) or not formal for formal, _ in row_pairs)
            or len({formal for formal, _ in row_pairs}) != len(row_pairs)
            or {formal for formal, _ in row_pairs} != set(planned)
        ):
            raise ValueError("workflow reference extern rows disagree with the resolved plan")
        projected_rows = []
        for formal, row in sorted(row_pairs, key=lambda pair: pair[0]):
            if category == "providers":
                if (
                    not isinstance(row, Mapping)
                    or set(row) != {"provider_id"}
                    or not isinstance(row["provider_id"], str)
                    or not row["provider_id"].strip()
                ):
                    raise ValueError("resolved provider extern row is malformed")
            else:
                source_kind = row.get("source_kind") if isinstance(row, Mapping) else None
                expected_fields = (
                    {"source_kind", "path", "asset_base"}
                    if source_kind == "asset_file"
                    else {"source_kind", "path"}
                )
                if (
                    not isinstance(row, Mapping)
                    or source_kind not in {"asset_file", "input_file"}
                    or set(row) != expected_fields
                    or not isinstance(row.get("path"), str)
                    or not row["path"].strip()
                    or (
                        source_kind == "asset_file"
                        and (
                            not isinstance(row.get("asset_base"), str)
                            or not row["asset_base"].strip()
                        )
                    )
                ):
                    raise ValueError("resolved prompt extern row is malformed")
            projected_rows.append([formal, deepcopy(dict(row))])
        projected[category] = projected_rows
    return {"target": target_key, "externs": projected}


def canonical_definition_key(
    definition: Any,
    *,
    typed: Any,
    binding_facts: Mapping[str, Any],
    capture_parameters: Sequence[Any],
    residual_signature: Mapping[str, Any] | None,
) -> list[Any]:
    """Construct the complete canonical key from one retained typed callable."""

    if not isinstance(binding_facts, Mapping):
        raise TypeError("binding_facts must be a mapping")
    return _definition_key(
        definition,
        typed=typed,
        binding_facts=binding_facts,
        capture_parameters=capture_parameters,
        residual_signature=residual_signature,
        active=set(),
    )


def canonical_callee_name(definition: Any, *, key: list[Any]) -> str:
    """Return the sole canonical display name for a constructed definition key."""

    _ = definition
    return canonical_callee_name_from_key(key)
