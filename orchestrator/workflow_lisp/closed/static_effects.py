"""Declaration-only effect checks shared by typed and dynamic admission.

These checks consume canonical configuration and request data; expression typing,
site proofs and operand execution remain with their respective representation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import re
from typing import Any

from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.prompt_fragment_contract import _RENDERERS_BY_KIND, _scan_placeholders
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor


class StaticEffectError(ValueError):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def _fail(rule: str, message: str, node: Any = None) -> None:
    raise StaticEffectError(rule, message)


def _same(left: Any, right: Any) -> bool:
    return canonical_json_for_pure_value(left) == canonical_json_for_pure_value(right)


_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")

_RESULT_CONTRACT_METADATA_KEYS = frozenset(
    {
        "path",
        "guidance",
        "description",
        "format_hint",
        "example",
        "guidance_context",
        "guidance_by_variant",
        "result_guidance",
        "source_map_subject",
        "source_map_subjects_by_variant",
    }
)
_COMMAND_COMMON_FIELDS = frozenset(
    {
        "kind",
        "name",
        "stable_command",
        "must_not_repeat",
        "closure",
        "retirement_class",
        "retirement_label",
        "replacement_surface",
        "bridge_owner",
        "expiry_condition",
        "evidence_refs",
        "retirement_status",
    }
)
_COMMAND_CERTIFIED_FIELDS = frozenset(
    {
        "input_contract",
        "output_type_name",
        "effects",
        "path_safety",
        "source_map_behavior",
        "fixture_ids",
        "negative_fixture_ids",
        "behavior_class",
        "input_signature",
        "artifact_contracts",
        "state_writes",
        "error_codes",
        "owner_module",
        "replacement_path",
        "invocation_protocol",
        "transition_binding",
        "view_binding",
        "declared_promoted_fields",
    }
)
_PROMOTED_METADATA_FIELDS = frozenset(
    {
        "behavior_class",
        "input_signature",
        "artifact_contracts",
        "state_writes",
        "error_codes",
        "owner_module",
        "replacement_path",
        "invocation_protocol",
    }
)
_PROMPT_VALUE_PRIMITIVES = frozenset(
    {"String", "Int", "Float", "Bool", "Json", "Value"}
)


def _prompt_value_type_is_renderable(descriptor: Any) -> bool:
    """Mirror the source prompt owner's canonical-JSON type admission."""

    if not isinstance(descriptor, Mapping):
        return False
    kind = descriptor.get("kind")
    if kind == "primitive":
        return descriptor.get("name") in _PROMPT_VALUE_PRIMITIVES
    if kind in {"enum", "path", "record", "union"}:
        # The closed target is 2.35; whole-union prompt values were admitted at
        # 2.28 and the checked descriptor validator has already checked shape.
        return True
    if kind == "list":
        return _prompt_value_type_is_renderable(descriptor.get("item"))
    return False


def _validate_resolved_extern_rows(scope: Mapping[str, Any]) -> None:
    commands = scope.get("commands")
    providers = scope.get("providers")
    prompts = scope.get("prompts")
    if not isinstance(commands, Mapping) or not isinstance(providers, Mapping) or not isinstance(prompts, Mapping):
        _fail("configuration_scope", "resolved command, provider and prompt rows must be objects")
    _validate_command_configuration_rows(commands)
    for name, row in providers.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(row, Mapping)
            or set(row) != {"provider_id"}
            or not isinstance(row["provider_id"], str)
            or not row["provider_id"].strip()
        ):
            _fail("configuration_scope", "resolved provider row must contain exactly one provider_id")
    for name, row in prompts.items():
        if not isinstance(name, str) or not name or not isinstance(row, Mapping):
            _fail("configuration_scope", "resolved prompt row is malformed")
        source_kind = row.get("source_kind")
        expected = {"source_kind", "path"} | ({"asset_base"} if source_kind == "asset_file" else set())
        if (
            not isinstance(source_kind, str)
            or source_kind not in {"asset_file", "input_file"}
            or set(row) != expected
            or not isinstance(row.get("path"), str)
            or not row["path"].strip()
            or (source_kind == "asset_file" and (not isinstance(row.get("asset_base"), str) or not row["asset_base"]))
        ):
            _fail("configuration_scope", "resolved prompt row does not match its exact source shape")



def _validate_command_configuration_rows(commands: Mapping[str, Any]) -> None:
    for lookup_name, row in commands.items():
        if not isinstance(lookup_name, str) or not lookup_name.strip() or not isinstance(row, Mapping):
            _fail("configuration_scope", "command configuration key or row is malformed")
        kind = row.get("kind")
        if not isinstance(kind, str) or kind not in {"external_tool", "certified_adapter"}:
            _fail("configuration_scope", "command configuration kind is unsupported")
        expected = _COMMAND_COMMON_FIELDS | (
            _COMMAND_CERTIFIED_FIELDS if kind == "certified_adapter" else frozenset()
        )
        if set(row) != expected:
            _fail("configuration_scope", "command configuration row has missing or extra fields")
        if not isinstance(row.get("name"), str):
            _fail("configuration_scope", "command configuration name must be a string")
        stable = row.get("stable_command")
        if not isinstance(stable, list) or not stable or any(not isinstance(token, str) or not token for token in stable):
            _fail("configuration_scope", "command stable tokens must be a nonempty string array")
        if type(row.get("must_not_repeat")) is not bool:
            _fail("configuration_scope", "command repeat policy must be a boolean")
        closure = row.get("closure")
        if not isinstance(closure, list):
            _fail("configuration_scope", "command closure must be a canonical array")
        closure_pairs: list[tuple[str, str]] = []
        for closure_row in closure:
            if not isinstance(closure_row, Mapping) or set(closure_row) != {"base", "path"}:
                _fail("configuration_scope", "command closure row must contain base and path")
            base, path = closure_row["base"], closure_row["path"]
            if not isinstance(base, str) or base not in {"workspace", "absolute", "package:orchestrator"} or not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
                _fail("configuration_scope", "command closure path is malformed")
            absolute = path.startswith("/")
            if (base == "absolute") != absolute:
                _fail("configuration_scope", "command closure base does not match path absoluteness")
            body = path[1:] if absolute else path
            segments = body.split("/") if body and path != "." else []
            if any(segment in {"", "."} for segment in segments):
                _fail("configuration_scope", "command closure path is not normalized")
            normalized = ("/" if absolute else "") + "/".join(segments)
            if not segments and not absolute:
                normalized = "."
            if not segments and absolute:
                normalized = "/"
            if path != normalized:
                _fail("configuration_scope", "command closure path is not canonical")
            closure_pairs.append((base, path))
        if closure_pairs != sorted(set(closure_pairs)):
            _fail("configuration_scope", "command closure rows must be unique and canonically ordered")
        for field in (
            "retirement_class",
            "retirement_label",
            "replacement_surface",
            "bridge_owner",
            "expiry_condition",
            "retirement_status",
        ):
            if row[field] is not None and not isinstance(row[field], str):
                _fail("configuration_scope", f"command {field} must be a string or null")
        if not isinstance(row.get("evidence_refs"), list) or any(not isinstance(value, str) for value in row["evidence_refs"]):
            _fail("configuration_scope", "command evidence_refs must be an array of strings")
        if kind != "certified_adapter":
            continue
        for field in ("input_contract", "path_safety"):
            if not isinstance(row[field], Mapping):
                _fail("configuration_scope", f"certified command {field} must be an object")
        for field in (
            "output_type_name",
            "source_map_behavior",
        ):
            if not isinstance(row[field], str):
                _fail("configuration_scope", f"certified command {field} must be a string")
        for field in (
            "effects",
            "fixture_ids",
            "negative_fixture_ids",
            "artifact_contracts",
            "state_writes",
            "error_codes",
        ):
            if not isinstance(row[field], list) or any(not isinstance(value, str) for value in row[field]):
                _fail("configuration_scope", f"certified command {field} must be an array of strings")
        for field in ("behavior_class", "owner_module", "replacement_path", "invocation_protocol"):
            if row[field] is not None and not isinstance(row[field], str):
                _fail("configuration_scope", f"certified command {field} must be a string or null")
        signature = row["input_signature"]
        if not isinstance(signature, list):
            _fail("configuration_scope", "certified command input_signature must be an array")
        for signature_row in signature:
            if not isinstance(signature_row, Mapping) or set(signature_row) != {"name", "type_name", "required", "transport_key"}:
                _fail("configuration_scope", "certified command input signature row is malformed")
            if any(not isinstance(signature_row[field], str) for field in ("name", "type_name", "transport_key")) or type(signature_row["required"]) is not bool:
                _fail("configuration_scope", "certified command input signature row has invalid value types")
        for field, required in (
            ("transition_binding", {"transition_name", "resource_kind", "contract_role", "backend_selector"}),
            ("view_binding", {"view_name", "renderer_id", "renderer_version", "contract_role"}),
        ):
            nested = row[field]
            if nested is None:
                continue
            if not isinstance(nested, Mapping) or set(nested) != required:
                _fail("configuration_scope", f"certified command {field} has invalid fields")
            text_fields = required - ({"renderer_version"} if field == "view_binding" else set())
            if any(not isinstance(nested[name], str) for name in text_fields):
                _fail("configuration_scope", f"certified command {field} has invalid value types")
            if field == "view_binding" and type(nested["renderer_version"]) is not int:
                _fail("configuration_scope", "certified command view renderer_version must be an integer")
        promoted = row["declared_promoted_fields"]
        if (
            not isinstance(promoted, list)
            or any(not isinstance(field, str) for field in promoted)
            or promoted != sorted(set(promoted))
        ):
            _fail("configuration_scope", "certified command promoted fields are not canonical")



def _command_configuration_stable_tokens(row, node):
    stable = row.get("stable_command")
    if not isinstance(stable, list) or not stable or any(not isinstance(token, str) or not token for token in stable):
        _fail("configuration_scope", "command configuration omits its canonical stable tokens", node)
    return stable



def _check_command_configuration_identity(node, row, stable):
    if not _same(node.get("command"), stable):
        _fail("configuration_scope", "command stable tokens differ from its configuration binding", node)
    configured_closure = row.get("closure")
    if not isinstance(configured_closure, list):
        _fail("configuration_scope", "command configuration omits its normalized closure", node)
    if not _same(node.get("closure"), configured_closure):
        _fail("configuration_scope", "command closure differs from its configuration binding", node)
    expected_repeat = "never" if row["must_not_repeat"] else "rerun"
    if node.get("repeat") != expected_repeat:
        _fail("configuration_scope", "command repeat rule differs from its configuration binding", node)



def _check_certified_document_configuration(node, row):
    if node["argv"]:
        _fail("effect_shape", "certified document invocation must carry an empty argv array", node)
    promoted = row["declared_promoted_fields"]
    supports_promoted = (
        _PROMOTED_METADATA_FIELDS.issubset(promoted)
        and bool(row["behavior_class"])
        and bool(row["input_signature"])
        and bool(row["owner_module"])
        and row["invocation_protocol"] == "json_object_positional_arg"
    )
    if not supports_promoted:
        _fail("configuration_scope", "certified binding does not declare promoted document metadata", node)
    if not _document_keys_match_signature(row["input_signature"], node["document"]):
        _fail("configuration_scope", "command document keys differ from the selected signature rows", node)



def _document_keys_match_signature(signature: list[Any], document: list[Any]) -> bool:
    """Check the ordered projection of selected signature names, preserving duplicate rows."""

    if any(not isinstance(row, Mapping) for row in signature):
        return False
    if any(not isinstance(row, (list, tuple)) or len(row) != 2 or not isinstance(row[0], str) for row in document):
        return False
    actual_keys = [row[0] for row in document]
    required_names = {row["name"] for row in signature if row["required"]}
    last_index = {row["name"]: index for index, row in enumerate(signature)}
    states: set[tuple[int, tuple[tuple[str, bool], ...]]] = {(0, ())}
    for index, row in enumerate(signature):
        next_states: set[tuple[int, tuple[tuple[str, bool], ...]]] = set()
        for document_index, assignments_tuple in states:
            assignments = dict(assignments_tuple)
            name = row["name"]
            choices = (assignments[name],) if name in assignments else ((True,) if name in required_names else (False, True))
            for selected in choices:
                next_document_index = document_index
                if selected:
                    if document_index >= len(actual_keys) or actual_keys[document_index] != row["transport_key"]:
                        continue
                    next_document_index += 1
                next_assignments = dict(assignments)
                if name in next_assignments:
                    del next_assignments[name]
                if last_index[name] > index:
                    next_assignments[name] = selected
                next_states.add((next_document_index, tuple(sorted(next_assignments.items()))))
        states = next_states
        if not states:
            return False
    return any(document_index == len(actual_keys) for document_index, _ in states)



def _check_external_document_keys(node):
    names = set()
    for row in node["document"]:
        name = row[0]
        if not name or name in names:
            _fail("effect_shape", "external command document keys must be nonempty and unique", node)
        names.add(name)



def _checked_effect_result_contract(descriptor: Mapping[str, Any], *, whole_value: bool = False) -> dict[str, Any]:
    """Derive the structural output contract from its checked result type."""

    if whole_value:
        return {"kind": "output_bundle", "payload": {"fields": [{
            "name": "__result__", "json_pointer": "",
            **transport_schema_for_descriptor(descriptor, allow_nested_structures=True),
        }]}}

    def pointer(path: Sequence[str]) -> str:
        return "" if not path else "/" + "/".join(
            segment.replace("~", "~0").replace("/", "~1") for segment in path
        )

    def flatten(descriptor_: Mapping[str, Any], path: tuple[str, ...]) -> list[dict[str, Any]]:
        if descriptor_.get("kind") == "record":
            rows: list[dict[str, Any]] = []
            for field in descriptor_["fields"]:
                rows.extend(flatten(field["type"], (*path, field["name"])))
            return rows
        return [
            {
                "name": "__".join(path),
                "json_pointer": pointer(path),
                **transport_schema_for_descriptor(descriptor_, allow_nested_structures=True),
            }
        ]

    kind = descriptor.get("kind")
    if kind == "record":
        fields = flatten(descriptor, ())
        return {"kind": "output_bundle", "payload": {"fields": fields}}
    if kind == "union":
        variants = descriptor["variants"]
        per_variant = {
            variant["name"]: [
                row
                for field in variant["fields"]
                for row in flatten(field["type"], (field["name"],))
            ]
            for variant in variants
        }
        first_rows = per_variant[variants[0]["name"]]
        shared: list[dict[str, Any]] = []
        for candidate in first_rows:
            if all(
                any(_same(candidate, row) for row in per_variant[variant["name"]])
                for variant in variants[1:]
            ):
                shared.append(candidate)
        shared_names = {row["name"] for row in shared}
        return {
            "kind": "variant_output",
            "payload": {
                "discriminant": {
                    "name": "variant",
                    "json_pointer": "/variant",
                    "type": "enum",
                    "allowed": [variant["name"] for variant in variants],
                },
                "shared_fields": shared,
                "variants": {
                    variant["name"]: {
                        "fields": [
                            row for row in per_variant[variant["name"]]
                            if row["name"] not in shared_names
                        ]
                    }
                    for variant in variants
                },
            },
        }
    root = flatten(descriptor, ("__result__",))[0]
    root["json_pointer"] = ""
    return {"kind": "output_bundle", "payload": {"fields": [root]}}



def _result_contract_view(value: Any) -> Any:
    """Project only contract-owned provenance before structural comparison.

    Contract maps include user-authored variant names and guidance objects;
    recursively treating every matching dictionary key as metadata can
    erase real variants such as ``source_map_subject``.  Provenance keys
    are owned only by the payload root and its field rows.
    """

    if not isinstance(value, Mapping):
        return deepcopy(value)
    result = deepcopy(dict(value))
    for key in _RESULT_CONTRACT_METADATA_KEYS:
        result.pop(key, None)

    def project_field_rows(rows: Any) -> Any:
        if not isinstance(rows, list):
            return deepcopy(rows)
        projected = []
        for row in rows:
            if not isinstance(row, Mapping):
                projected.append(deepcopy(row))
                continue
            clean = deepcopy(dict(row))
            for key in _RESULT_CONTRACT_METADATA_KEYS:
                clean.pop(key, None)
            projected.append(clean)
        return projected

    for field_key in ("fields", "shared_fields"):
        if field_key in result:
            result[field_key] = project_field_rows(result[field_key])
    variants = result.get("variants")
    if isinstance(variants, Mapping):
        projected_variants = deepcopy(dict(variants))
        for variant in projected_variants.values():
            if isinstance(variant, Mapping) and "fields" in variant:
                variant["fields"] = project_field_rows(variant["fields"])
        result["variants"] = projected_variants
    return result



def _check_provider_prompt_fill_declarations(prompt: Mapping[str, Any], descriptor_check=None) -> None:
    fills = prompt["fills"]
    try:
        placeholders = _scan_placeholders(prompt["template"])
    except (TypeError, ValueError, RecursionError) as exc:
        _fail("effect_shape", f"provider prompt template is malformed: {exc}")

    names: set[str] = set()
    claimed: set[int] = set()
    for fill in fills:
        expected = {"name", "kind", "type", "value", "renderer_id", "output_role", "placeholder_ordinals"}
        if not isinstance(fill, Mapping) or set(fill) != expected:
            _fail("effect_shape", "provider template fill has invalid fields")
        name = fill["name"]
        if not isinstance(name, str) or not _NAME_RE.fullmatch(name) or name in names:
            _fail("effect_shape", "provider template slot names must be unique valid names")
        names.add(name)
        descriptor = fill["type"]
        if descriptor_check is not None:
            descriptor_check(descriptor)
        elif not isinstance(descriptor, Mapping):
            _fail("type_mismatch", "provider template slot descriptor must be an object")
        slot_kind = fill["kind"]
        if not isinstance(slot_kind, str):
            _fail("effect_shape", "provider template slot kind is invalid")
        if slot_kind == "doc":
            type_matches = descriptor.get("kind") == "path" and descriptor.get("must_exist_target") is True
            expected_renderer = None
        elif slot_kind == "text":
            type_matches = descriptor.get("kind") == "primitive" and descriptor.get("name") == "String"
            expected_renderer = _RENDERERS_BY_KIND["text"]
        elif slot_kind == "path":
            type_matches = descriptor.get("kind") == "path"
            expected_renderer = _RENDERERS_BY_KIND["path"]
        elif slot_kind == "value":
            type_matches = _prompt_value_type_is_renderable(descriptor)
            expected_renderer = _RENDERERS_BY_KIND["value"]
        else:
            _fail("effect_shape", f"unsupported provider template slot kind {slot_kind!r}")
        if not type_matches:
            _fail("effect_shape", f"provider template {slot_kind} slot has an incompatible type")
        if fill["renderer_id"] != expected_renderer:
            _fail("effect_shape", "provider template slot renderer does not match its kind and type")

        output_role = fill["output_role"]
        if output_role not in (None, "none", "required_string_file"):
            _fail("effect_shape", "provider template output role is unsupported")
        if output_role == "required_string_file" and not (
            slot_kind == "path"
            and descriptor.get("kind") == "path"
            and descriptor.get("must_exist_target") is False
        ):
            _fail("effect_shape", "required output slot must be a non-existing relpath")

        ordinals = fill["placeholder_ordinals"]
        if (
            not isinstance(ordinals, list)
            or any(type(index) is not int or index < 0 for index in ordinals)
            or ordinals != sorted(set(ordinals))
        ):
            _fail("effect_shape", "provider template slot placeholder ordinals are invalid")
        if slot_kind == "doc":
            if ordinals:
                _fail("effect_shape", "document slots do not consume template placeholders")
            continue
        if not ordinals:
            _fail("effect_shape", "rendered prompt slots require placeholder positions")
        for ordinal in ordinals:
            if ordinal >= len(placeholders) or placeholders[ordinal] != name or ordinal in claimed:
                _fail("effect_shape", "provider prompt placeholder rows are inconsistent")
            claimed.add(ordinal)

    if claimed != set(range(len(placeholders))):
        _fail("effect_shape", "provider prompt placeholder coverage is incomplete")
