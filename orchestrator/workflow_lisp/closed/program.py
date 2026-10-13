"""Compiler-owned typed configuration projection for closed programs."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from orchestrator.contracts.closed_program.program import _canonical_json

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
