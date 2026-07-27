"""Frozen compiler carrier for one Workflow Lisp prompt fragment application."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA = "compiler_prompt_fragment_contract.v1"
COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2 = "compiler_prompt_fragment_contract.v2"
_IDENTITY_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PLACEHOLDER_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_RENDERERS_BY_KIND = {
    "text": "raw-utf8-string",
    "value": "canonical-json",
    "path": "posix-path-line",
}


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_json(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("prompt fragment contract values must be JSON-compatible")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_json(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _thaw_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    context: str,
) -> None:
    if set(value) != expected:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            f"{context} must contain exactly {sorted(expected)}"
        )


def _require_non_empty_string(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            f"{context} must be a non-empty string"
        )
    return value


def _validate_value_source(value_source: Mapping[str, Any]) -> None:
    _require_exact_keys(
        value_source,
        {"kind", "binding"},
        context="value_source",
    )
    if value_source["kind"] != "typed_binding_ref":
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "value_source.kind must be typed_binding_ref"
        )
    binding = value_source["binding"]
    if isinstance(binding, Mapping):
        _require_exact_keys(binding, {"ref"}, context="value_source.binding")
        ref = _require_non_empty_string(
            binding["ref"],
            context="value_source.binding.ref",
        )
        if not ref.startswith(
            ("inputs.", "root.steps.", "self.steps.", "parent.steps.")
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "value_source binding ref is outside the admitted runtime namespaces"
            )
        return
    if binding is None or isinstance(binding, (str, bool, int)):
        return
    if isinstance(binding, float) and math.isfinite(binding):
        return
    raise ValueError(
        "compiler_prompt_fragment_contract_invalid: "
        "value_source binding must be one admitted ref or JSON scalar literal"
    )


def _scan_placeholders(template: str) -> tuple[str, ...]:
    names: list[str] = []
    index = 0
    while index < len(template):
        char = template[index]
        if char == "{":
            if index + 1 < len(template) and template[index + 1] == "{":
                index += 2
                continue
            closing = template.find("}", index + 1)
            if closing < 0:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: malformed template placeholder"
                )
            name = template[index + 1 : closing]
            if not _PLACEHOLDER_NAME_RE.fullmatch(name):
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: malformed template placeholder"
                )
            names.append(name)
            index = closing + 1
            continue
        if char == "}":
            if index + 1 < len(template) and template[index + 1] == "}":
                index += 2
                continue
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: malformed template placeholder"
            )
        index += 1
    return tuple(names)


@dataclass(frozen=True)
class CompilerPromptFragmentRenderedSlot:
    """One rendered slot in declaration order."""

    name: str
    kind: str
    static_type: Mapping[str, Any]
    renderer_id: str
    value_source: Mapping[str, Any]
    placeholder_ordinals: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "static_type", _freeze_json(self.static_type))
        object.__setattr__(self, "value_source", _freeze_json(self.value_source))
        object.__setattr__(
            self,
            "placeholder_ordinals",
            tuple(self.placeholder_ordinals),
        )
        if not isinstance(self.name, str) or not _PLACEHOLDER_NAME_RE.fullmatch(
            self.name
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: rendered slot name is invalid"
            )
        expected_renderer = _RENDERERS_BY_KIND.get(self.kind)
        if expected_renderer is None or self.renderer_id != expected_renderer:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: rendered slot kind/renderer mismatch"
            )
        if not isinstance(self.static_type, Mapping) or not self.static_type:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: static_type is required"
            )
        if not isinstance(self.value_source, Mapping) or not self.value_source:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: value_source is required"
            )
        from orchestrator.workflow_lisp.lowering.pure_projection import (
            validate_compiler_normalized_type_descriptor,
        )

        try:
            validate_compiler_normalized_type_descriptor(
                self.static_type,
                context="static_type",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "static_type is not a compiler normalized type descriptor"
            ) from exc
        _validate_value_source(self.value_source)
        if (
            not isinstance(self.placeholder_ordinals, tuple)
            or not self.placeholder_ordinals
            or any(
                not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0
                for ordinal in self.placeholder_ordinals
            )
            or tuple(sorted(set(self.placeholder_ordinals)))
            != self.placeholder_ordinals
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: placeholder ordinals are invalid"
            )

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentRenderedSlot":
        return self


@dataclass(frozen=True)
class CompilerPromptFragmentContract:
    """Exact template plus the closed program needed to render it at runtime."""

    schema_version: str
    template_utf8: str
    rendered_slots: tuple[CompilerPromptFragmentRenderedSlot, ...]
    compiled_prompt_fragment_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rendered_slots", tuple(self.rendered_slots))
        validate_compiler_prompt_fragment_contract(self)

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentContract":
        return self


@dataclass(frozen=True)
class CompilerPromptFragmentOutputPosition:
    """One compiler-owned output-position row in slot declaration order."""

    slot_name: str
    output_role: str
    expected_output: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_output",
            _freeze_json(self.expected_output),
        )
        if not isinstance(
            self.slot_name, str
        ) or not _PLACEHOLDER_NAME_RE.fullmatch(self.slot_name):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position slot name is invalid"
            )
        if self.output_role != "required_string_file":
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position role must be required_string_file"
            )
        if not isinstance(self.expected_output, Mapping):
            raise TypeError("expected_output must be a mapping")
        _require_exact_keys(
            self.expected_output,
            {"name", "path", "type", "required"},
            context="output_position.expected_output",
        )
        if self.expected_output["name"] != self.slot_name:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position name must match its slot"
            )
        _require_non_empty_string(
            self.expected_output["path"],
            context="output_position.expected_output.path",
        )
        if (
            self.expected_output["type"] != "string"
            or self.expected_output["required"] is not True
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position must require one string file"
            )

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentOutputPosition":
        return self


@dataclass(frozen=True)
class CompilerPromptFragmentContractV2:
    """V2 renderer carrier with compiler-owned output-position obligations."""

    schema_version: str
    template_utf8: str
    rendered_slots: tuple[CompilerPromptFragmentRenderedSlot, ...]
    output_positions: tuple[CompilerPromptFragmentOutputPosition, ...]
    compiled_prompt_fragment_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rendered_slots", tuple(self.rendered_slots))
        object.__setattr__(self, "output_positions", tuple(self.output_positions))
        validate_compiler_prompt_fragment_contract(self)

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentContractV2":
        return self


def _path_template_from_rendered_slot(
    slot: CompilerPromptFragmentRenderedSlot,
) -> str:
    """Derive one output template solely from the frozen Q1 value source."""

    _validate_value_source(slot.value_source)
    binding = slot.value_source["binding"]
    if isinstance(binding, Mapping):
        return "${" + str(binding["ref"]) + "}"
    if isinstance(binding, str):
        return binding
    raise ValueError(
        "compiler_prompt_fragment_contract_invalid: "
        "output-position value source must be a binding ref or string literal"
    )


def _validate_compiler_prompt_fragment_contract_v2(
    contract: CompilerPromptFragmentContractV2,
) -> CompilerPromptFragmentContractV2:
    if contract.schema_version != COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: unsupported schema"
        )
    if not isinstance(contract.template_utf8, str):
        raise TypeError("template_utf8 must be a string")
    if not isinstance(contract.rendered_slots, tuple):
        raise TypeError("rendered_slots must be a tuple")
    if not isinstance(contract.output_positions, tuple):
        raise TypeError("output_positions must be a tuple")
    if not contract.output_positions:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "v2 contract requires at least one output-position row"
        )
    if not _IDENTITY_RE.fullmatch(contract.compiled_prompt_fragment_identity):
        raise ValueError(
            "compiled_prompt_fragment_identity_invalid: identity is malformed"
        )

    placeholders = _scan_placeholders(contract.template_utf8)
    rendered_names: set[str] = set()
    claimed_ordinals: set[int] = set()
    path_slots: dict[str, tuple[int, CompilerPromptFragmentRenderedSlot]] = {}
    for index, slot in enumerate(contract.rendered_slots):
        if type(slot) is not CompilerPromptFragmentRenderedSlot:
            raise TypeError(
                "rendered_slots must contain CompilerPromptFragmentRenderedSlot"
            )
        slot.__post_init__()
        if slot.name in rendered_names:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "rendered slot names must be unique"
            )
        rendered_names.add(slot.name)
        if slot.kind == "path":
            path_slots[slot.name] = (index, slot)
        for ordinal in slot.placeholder_ordinals:
            if ordinal >= len(placeholders) or placeholders[ordinal] != slot.name:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: "
                    "placeholder row mismatch"
                )
            if ordinal in claimed_ordinals:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: "
                    "placeholder ordinal is duplicated"
                )
            claimed_ordinals.add(ordinal)
    if claimed_ordinals != set(range(len(placeholders))):
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "placeholder rows are incomplete"
        )

    output_names: set[str] = set()
    declaration_indexes: list[int] = []
    for row in contract.output_positions:
        if type(row) is not CompilerPromptFragmentOutputPosition:
            raise TypeError(
                "output_positions must contain "
                "CompilerPromptFragmentOutputPosition"
            )
        row.__post_init__()
        if row.slot_name in output_names:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position names must be unique"
            )
        output_names.add(row.slot_name)
        path_slot = path_slots.get(row.slot_name)
        if path_slot is None:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position must name one rendered path slot"
            )
        declaration_index, slot = path_slot
        declaration_indexes.append(declaration_index)
        if row.expected_output["path"] != _path_template_from_rendered_slot(slot):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position path differs from its normalized value source"
            )
    if declaration_indexes != sorted(declaration_indexes):
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "output positions must follow slot declaration order"
        )
    return contract


def validate_compiler_prompt_fragment_contract(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2,
) -> CompilerPromptFragmentContract | CompilerPromptFragmentContractV2:
    """Validate a typed fragment contract without coercing mappings."""

    if type(contract) is CompilerPromptFragmentContractV2:
        return _validate_compiler_prompt_fragment_contract_v2(contract)
    if type(contract) is not CompilerPromptFragmentContract:
        raise TypeError("expected CompilerPromptFragmentContract")
    if contract.schema_version != COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: unsupported schema"
        )
    if not isinstance(contract.template_utf8, str):
        raise TypeError("template_utf8 must be a string")
    if not isinstance(contract.rendered_slots, tuple):
        raise TypeError("rendered_slots must be a tuple")
    if not _IDENTITY_RE.fullmatch(contract.compiled_prompt_fragment_identity):
        raise ValueError(
            "compiled_prompt_fragment_identity_invalid: identity is malformed"
        )
    placeholders = _scan_placeholders(contract.template_utf8)
    names: set[str] = set()
    claimed_ordinals: set[int] = set()
    for slot in contract.rendered_slots:
        if type(slot) is not CompilerPromptFragmentRenderedSlot:
            raise TypeError(
                "rendered_slots must contain CompilerPromptFragmentRenderedSlot"
            )
        slot.__post_init__()
        if slot.name in names:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: rendered slot names must be unique"
            )
        names.add(slot.name)
        for ordinal in slot.placeholder_ordinals:
            if ordinal >= len(placeholders) or placeholders[ordinal] != slot.name:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: placeholder row mismatch"
                )
            if ordinal in claimed_ordinals:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: placeholder ordinal is duplicated"
                )
            claimed_ordinals.add(ordinal)
    if claimed_ordinals != set(range(len(placeholders))):
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: placeholder rows are incomplete"
        )
    return contract


def validate_compiler_prompt_fragment_pair(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2 | None,
    identity: str | None,
) -> None:
    """Reject absent, malformed, or contradictory fragment carriage."""

    if contract is None and identity is None:
        return
    if contract is None or identity is None:
        raise ValueError(
            "compiled_prompt_fragment_identity_missing: contract and identity must be paired"
        )
    validate_compiler_prompt_fragment_contract(contract)
    if not isinstance(identity, str) or not _IDENTITY_RE.fullmatch(identity):
        raise ValueError(
            "compiled_prompt_fragment_identity_invalid: identity is malformed"
        )
    if contract.compiled_prompt_fragment_identity != identity:
        raise ValueError(
            "compiled_prompt_fragment_identity_mismatch: contract identity differs"
        )


def serialize_compiler_prompt_fragment_rendered_slot(
    slot: CompilerPromptFragmentRenderedSlot,
) -> dict[str, Any]:
    """Serialize one validated rendered-slot row."""

    slot.__post_init__()
    return {
        "name": slot.name,
        "kind": slot.kind,
        "static_type": _thaw_json(slot.static_type),
        "renderer_id": slot.renderer_id,
        "value_source": _thaw_json(slot.value_source),
        "placeholder_ordinals": list(slot.placeholder_ordinals),
    }


def serialize_compiler_prompt_fragment_contract(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2,
) -> dict[str, Any]:
    """Serialize one validated contract to its closed wire representation."""

    validate_compiler_prompt_fragment_contract(contract)
    serialized = {
        "schema_version": contract.schema_version,
        "template_utf8": contract.template_utf8,
        "rendered_slots": [
            serialize_compiler_prompt_fragment_rendered_slot(slot)
            for slot in contract.rendered_slots
        ],
        "compiled_prompt_fragment_identity": (
            contract.compiled_prompt_fragment_identity
        ),
    }
    if type(contract) is CompilerPromptFragmentContractV2:
        serialized["output_positions"] = [
            {
                "slot_name": row.slot_name,
                "output_role": row.output_role,
                "expected_output": _thaw_json(row.expected_output),
            }
            for row in contract.output_positions
        ]
    return serialized


def canonical_compiler_prompt_fragment_contract_json(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2,
) -> str:
    """Return compact canonical UTF-8 JSON with no trailing newline."""

    return _canonical_json_bytes(
        serialize_compiler_prompt_fragment_contract(contract)
    ).decode("utf-8")


def freeze_prompt_fragment_json(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Freeze compiler-owned JSON projections before putting them in the IR."""

    frozen = _freeze_json(value)
    assert isinstance(frozen, Mapping)
    return frozen
