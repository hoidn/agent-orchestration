"""Canonical artifacts and command configuration for closed programs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .check import CheckedFormError, validate
from .sites import _ast_nodes, _definition_order


SCHEMA = "workflow-lisp/closed-program/1"
REPRESENTATION = "table/1"


class ClosedProgramInvalid(ValueError):
    """A stored closed program failed strict parsing or checked-form validation."""

    def __init__(self, rule: str, message: str, *, location: str = "<artifact>") -> None:
        super().__init__(f"closed_program_invalid ({rule}) at {location}: {message}")
        self.code = "closed_program_invalid"
        self.rule = rule
        self.location = location


@dataclass(frozen=True)
class ClosedProgram:
    tree: dict[str, Any]
    sites: tuple[tuple[str, str], ...]
    digest: str

    def artifact(self) -> str:
        """Return canonical JSON with source provenance and one final newline."""

        return _canonical_json(self.tree) + "\n"

    @classmethod
    def from_artifact(cls, text: str) -> ClosedProgram:
        try:
            tree = json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_non_json_constant,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            column = getattr(exc, "colno", None)
            location = f"<artifact>:{line}:{column}" if line is not None else "<artifact>"
            raise ClosedProgramInvalid("json", f"invalid strict JSON: {exc}", location=location) from exc

        if not isinstance(tree, dict) or tree.get("schema") != SCHEMA:
            raise ClosedProgramInvalid(
                "representation",
                f"expected closed-program schema {SCHEMA!r}",
            )
        if tree.get("representation") != REPRESENTATION:
            raise ClosedProgramInvalid(
                "representation",
                f"expected representation {REPRESENTATION!r}, got {tree.get('representation')!r}",
        )
        try:
            _canonical_json(tree)
            validate(tree)
        except CheckedFormError as exc:
            rule = "sites" if exc.rule.startswith(("site_", "site_table")) else exc.rule
            raise ClosedProgramInvalid(rule, str(exc), location=exc.location or "<artifact>") from exc
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ClosedProgramInvalid("checked_form", str(exc)) from exc

        rows = _sites_from_nodes(tree)
        declared = tuple(tuple(row) for row in tree["sites"])
        if rows != declared:
            raise ClosedProgramInvalid("sites", "site rows differ from perform node annotations")
        try:
            digest = program_digest(tree)
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ClosedProgramInvalid("json", str(exc)) from exc
        return cls(tree=tree, sites=rows, digest=digest)


def canonical_digest(value: Any) -> str:
    """Hash canonical, finite JSON without a trailing newline."""

    return "sha256:" + sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def program_digest(tree: dict[str, Any]) -> str:
    """Hash program semantics while excluding only source-node provenance."""

    return canonical_digest(strip_provenance(tree))


def strip_provenance(node: Any) -> Any:
    """Copy a closed program and omit `@` only at schema-authorized AST rows."""

    result = deepcopy(node)
    if not isinstance(result, dict):
        return result
    bodies = [result.get("body")]
    definitions = result.get("definitions")
    if isinstance(definitions, Mapping):
        bodies.extend(
            definition.get("body")
            for definition in definitions.values()
            if isinstance(definition, Mapping)
        )
    for body in bodies:
        if not isinstance(body, dict):
            continue
        for ast_node in _ast_nodes(body):
            ast_node.pop("@", None)
            if ast_node.get("k") == "case":
                for arm in ast_node.get("arms", ()):
                    if isinstance(arm, dict):
                        arm.pop("@", None)
            elif ast_node.get("k") == "select":
                for branch_name in ("then", "else"):
                    branch = ast_node.get(branch_name)
                    if not isinstance(branch, dict):
                        continue
                    branch.pop("@", None)
                    for row in branch.get("prefix", ()):
                        if isinstance(row, dict):
                            row.pop("@", None)
    return result


def canonical_command_configuration(
    bindings: Mapping[str, object],
    *,
    origins: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Project every supplied command binding into the closed semantic schema."""

    from ..command_boundaries import CertifiedAdapterBinding, ExternalToolBinding

    rows: dict[str, dict[str, Any]] = {}
    for lookup_name, binding in sorted(bindings.items()):
        if isinstance(binding, ExternalToolBinding):
            row = _common_command_row(lookup_name, binding, origins, kind="external_tool")
        elif isinstance(binding, CertifiedAdapterBinding):
            row = _common_command_row(lookup_name, binding, origins, kind="certified_adapter")
            row.update(
                input_contract=_json_value(binding.input_contract),
                output_type_name=binding.output_type_name,
                effects=list(binding.effects),
                path_safety=_json_value(binding.path_safety),
                source_map_behavior=binding.source_map_behavior,
                fixture_ids=list(binding.fixture_ids),
                negative_fixture_ids=list(binding.negative_fixture_ids),
                behavior_class=binding.behavior_class,
                input_signature=[
                    {
                        "name": item.name,
                        "type_name": item.type_name,
                        "required": item.required,
                        "transport_key": item.transport_key,
                    }
                    for item in binding.input_signature
                ],
                artifact_contracts=list(binding.artifact_contracts),
                state_writes=list(binding.state_writes),
                error_codes=list(binding.error_codes),
                owner_module=binding.owner_module,
                replacement_path=binding.replacement_path,
                invocation_protocol=binding.invocation_protocol,
                transition_binding=(
                    None
                    if binding.transition_binding is None
                    else {
                        "transition_name": binding.transition_binding.transition_name,
                        "resource_kind": binding.transition_binding.resource_kind,
                        "contract_role": binding.transition_binding.contract_role,
                        "backend_selector": binding.transition_binding.backend_selector,
                    }
                ),
                view_binding=(
                    None
                    if binding.view_binding is None
                    else {
                        "view_name": binding.view_binding.view_name,
                        "renderer_id": binding.view_binding.renderer_id,
                        "renderer_version": binding.view_binding.renderer_version,
                        "contract_role": binding.view_binding.contract_role,
                    }
                ),
                declared_promoted_fields=sorted(binding.declared_promoted_fields),
            )
        else:
            raise ValueError(f"unsupported command boundary binding at {lookup_name!r}")
        rows[lookup_name] = row
    _canonical_json(rows)
    return rows


def canonical_extern_configuration(
    externs: Mapping[str, object],
    *,
    asset_base: str,
) -> dict[str, dict[str, dict[str, str]]]:
    """Project resolved provider and prompt bindings into the closed schema.

    ``asset_base`` is the logical source-owner directory, supplied by the caller;
    a physical entry directory must not be used here.
    """

    from ..workflows import PromptExtern, ProviderExtern

    providers: dict[str, dict[str, str]] = {}
    prompts: dict[str, dict[str, str]] = {}
    for name, binding in sorted(externs.items()):
        if isinstance(binding, ProviderExtern):
            if not isinstance(binding.provider_id, str) or not binding.provider_id.strip():
                raise ValueError(f"resolved provider extern {name!r} has an invalid provider id")
            providers[name] = {"provider_id": binding.provider_id}
        elif isinstance(binding, PromptExtern):
            if (
                not isinstance(binding.path, str)
                or not binding.path.strip()
                or binding.source_kind not in {"asset_file", "input_file"}
            ):
                raise ValueError(f"resolved prompt extern {name!r} is malformed")
            row = {"source_kind": binding.source_kind, "path": binding.path}
            if binding.source_kind == "asset_file":
                if not isinstance(asset_base, str) or not asset_base.strip():
                    raise ValueError("asset prompt projection requires a logical asset base")
                row["asset_base"] = asset_base
            prompts[name] = row
        else:
            raise ValueError(f"unsupported resolved extern at {name!r}")
    result = {"providers": providers, "prompts": prompts}
    _canonical_json(result)
    return result


def canonical_configuration(
    bindings: Mapping[str, object],
    *,
    origins: Mapping[str, str],
    externs: Mapping[str, object],
    asset_base: str,
) -> dict[str, dict[str, Any]]:
    """Project one owner's exact command/provider/prompt configuration maps."""

    return {
        "commands": canonical_command_configuration(bindings, origins=origins),
        **canonical_extern_configuration(externs, asset_base=asset_base),
    }


def logical_asset_base_for_module(module_name: str) -> str:
    """Return the logical directory encoded by a canonical Workflow Lisp module."""

    if not isinstance(module_name, str) or not module_name or module_name.startswith("/"):
        raise ValueError("module name must be a nonempty relative logical path")
    parts = module_name.split("/")
    if any(part in {"", ".", ".."} or "\\" in part for part in parts):
        raise ValueError("module name must use canonical logical path components")
    return "/".join(parts[:-1]) or "."


def _common_command_row(
    lookup_name: str,
    binding: Any,
    origins: Mapping[str, str],
    *,
    kind: str,
) -> dict[str, Any]:
    origin = origins.get(lookup_name, "workspace")
    if origin not in {"workspace", "package:orchestrator"}:
        raise ValueError(f"unsupported trusted command origin for {lookup_name!r}: {origin!r}")
    return {
        "kind": kind,
        "name": binding.name,
        "stable_command": list(binding.stable_command),
        "must_not_repeat": binding.must_not_repeat,
        "closure": _canonical_closure(binding.closure, origin=origin),
        "retirement_class": binding.retirement_class,
        "retirement_label": binding.retirement_label,
        "replacement_surface": binding.replacement_surface,
        "bridge_owner": binding.bridge_owner,
        "expiry_condition": binding.expiry_condition,
        "evidence_refs": list(binding.evidence_refs),
        "retirement_status": binding.retirement_status,
    }


def _canonical_closure(value: Any, *, origin: str) -> list[dict[str, str]]:
    if value is None:
        raise ValueError("command boundary closure is missing")
    if not isinstance(value, (tuple, list)):
        raise ValueError("command boundary closure must be an array of literal paths")
    rows = set()
    for path in value:
        if not isinstance(path, str) or not path or "\x00" in path:
            raise ValueError("command boundary closure paths must be nonempty strings without NUL")
        path = path.replace("\\", "/")
        absolute = path.startswith("/")
        parts = [part for part in (path[1:] if absolute else path).split("/") if part not in {"", "."}]
        normalized = ("/" if absolute else "") + "/".join(parts)
        if not parts:
            normalized = "/" if absolute else "."
        rows.add(("absolute" if absolute else origin, normalized))
    return [{"base": base, "path": path} for base, path in sorted(rows)]


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("command metadata object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    raise ValueError(f"command metadata is not JSON data: {type(value).__name__}")


def _sites_from_nodes(tree: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    definitions = tree["definitions"]
    owners = [(tree["entry"], tree["body"])]
    owners.extend(
        (name, definitions[name]["body"])
        for name in _definition_order(tree, definitions)
    )
    return tuple(
        (owner, node["site"])
        for owner, body in owners
        for node in _ast_nodes(body)
        if node.get("k") == "perform"
    )


def _canonical_json(value: Any) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("canonical JSON contains an unpaired Unicode surrogate") from exc
    return text


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> Any:
    raise ValueError(f"non-JSON numeric constant {value!r}")
