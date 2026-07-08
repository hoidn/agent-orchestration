"""Stateless request/manifest loaders, field validators, and io leaf helpers for the Workflow Lisp build.

Extracted from build.py. Pure functions — no design-delta coupling, no build-state.
Imported by build.py, build_design_delta.py, and build_artifacts.py; imports nothing from them.

Contract: see docs/plans/2026-07-07-build-module-split.md (build.py split). Behavior is
byte-identical to the pre-split build.py definitions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .command_boundaries import (
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
    ExternalToolBinding,
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
    TransitionBindingMetadata,
    ViewBindingMetadata,
)
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourcePosition, SourceSpan
from .workflows import normalize_public_prompt_extern_binding, prompt_extern_source_payload

if TYPE_CHECKING:
    from .build import FrontendBuildRequest


def _resolve_request(request: FrontendBuildRequest) -> FrontendBuildRequest:
    from .build import FrontendBuildRequest

    workspace_root = (request.workspace_root or Path.cwd()).resolve()
    source_path = request.source_path.resolve()
    if not source_path.exists():
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_cli_input_missing",
                    message="workflow Lisp entrypoint does not exist",
                    path=source_path,
                ),
            )
        )
    source_roots = tuple(root.resolve() for root in request.source_roots)
    return FrontendBuildRequest(
        source_path=source_path,
        source_roots=source_roots,
        entry_workflow=request.entry_workflow,
        provider_externs_path=request.provider_externs_path.resolve() if request.provider_externs_path else None,
        prompt_externs_path=request.prompt_externs_path.resolve() if request.prompt_externs_path else None,
        imported_workflow_bundles_path=request.imported_workflow_bundles_path.resolve()
        if request.imported_workflow_bundles_path
        else None,
        command_boundaries_path=request.command_boundaries_path.resolve() if request.command_boundaries_path else None,
        emit_debug_yaml=request.emit_debug_yaml,
        workspace_root=workspace_root,
        lint_profile=request.lint_profile,
        lowering_route=request.lowering_route,
    )


def _load_string_mapping(
    manifest_path: Path | None,
    *,
    label: str,
) -> Mapping[str, str]:
    if manifest_path is None:
        return {}
    payload = _load_json_file(manifest_path, label=label)
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_invalid",
                    message=f"{label} must be a JSON object",
                    path=manifest_path,
                ),
            )
        )
    entries: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_manifest_invalid",
                        message=f"{label} entries must map non-empty string names to string values",
                        path=manifest_path,
                    ),
                )
            )
        entries[key] = value
    return entries


def _load_prompt_extern_mapping(
    manifest_path: Path | None,
) -> Mapping[str, str | dict[str, str]]:
    if manifest_path is None:
        return {}
    payload = _load_json_file(manifest_path, label="prompt externs manifest")
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_invalid",
                    message="prompt externs manifest must be a JSON object",
                    path=manifest_path,
                ),
            )
        )
    entries: dict[str, str | dict[str, str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_manifest_invalid",
                        message="prompt externs manifest entries must use non-empty string names",
                        path=manifest_path,
                    ),
                )
            )
        try:
            binding = normalize_public_prompt_extern_binding(key, value)
        except (TypeError, ValueError):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_manifest_invalid",
                        message=(
                            "prompt externs manifest entries must map non-empty string names to string values "
                            "or objects with exactly one of `asset_file` or `input_file`"
                        ),
                        path=manifest_path,
                    ),
                )
            ) from None
        entries[key] = binding.path if binding.source_kind == "asset_file" and isinstance(value, str) else prompt_extern_source_payload(binding)
    return entries


def _load_command_boundaries_manifest_payload(
    manifest_path: Path | None,
) -> Mapping[str, object]:
    if manifest_path is None:
        return {}
    payload = _load_json_file(manifest_path, label="command boundaries manifest")
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message="command boundaries manifest must be a JSON object",
                    path=manifest_path,
                ),
            )
        )
    entries: dict[str, object] = {}
    for name, raw_entry in payload.items():
        if not isinstance(name, str) or not name:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message="command boundaries manifest entries must use non-empty string names",
                        path=manifest_path,
                    ),
                )
            )
        entries[name] = raw_entry
    return entries


def _parse_command_boundaries_manifest(
    payload: Mapping[str, object],
    *,
    manifest_path: Path | None,
) -> Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]:
    bindings: dict[str, ExternalToolBinding | CertifiedAdapterBinding] = {}
    for name, raw_entry in payload.items():
        if not isinstance(raw_entry, Mapping):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"manifest entry for `{name}` must be a JSON object",
                        path=manifest_path or Path(name),
                    ),
                )
            )
        stable_command = _require_string_array(
            raw_entry.get("stable_command", ()),
            field_name="stable_command",
            binding_name=name,
            manifest_path=manifest_path,
        )
        kind = raw_entry.get("kind", "external_tool")
        if not isinstance(kind, str) or not kind:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"`kind` for `{name}` must be a non-empty string",
                        path=manifest_path or Path(name),
                    ),
                )
            )
        if kind == "external_tool":
            bindings[name] = ExternalToolBinding(
                name=name,
                stable_command=stable_command,
                retirement_class=_require_optional_string_field(
                    raw_entry.get("retirement_class"),
                    field_name="retirement_class",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_label=_require_optional_string_field(
                    raw_entry.get("retirement_label"),
                    field_name="retirement_label",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                replacement_surface=_require_optional_string_field(
                    raw_entry.get("replacement_surface"),
                    field_name="replacement_surface",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                bridge_owner=_require_optional_string_field(
                    raw_entry.get("bridge_owner"),
                    field_name="bridge_owner",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                expiry_condition=_require_optional_string_field(
                    raw_entry.get("expiry_condition"),
                    field_name="expiry_condition",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                evidence_refs=_require_optional_string_array(
                    raw_entry.get("evidence_refs"),
                    field_name="evidence_refs",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_status=_require_optional_string_field(
                    raw_entry.get("retirement_status"),
                    field_name="retirement_status",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
            )
            continue
        if kind == "certified_adapter":
            declared_promoted_fields = frozenset(
                key
                for key in PROMOTED_CALL_REQUIRED_METADATA_FIELDS
                if key in raw_entry
            )
            bindings[name] = CertifiedAdapterBinding(
                name=name,
                stable_command=stable_command,
                input_contract=_require_mapping_field(
                    raw_entry.get("input_contract", {}),
                    field_name="input_contract",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                output_type_name=_require_string_field(
                    raw_entry.get("output_type_name", ""),
                    field_name="output_type_name",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                effects=_require_string_array(
                    raw_entry.get("effects", ()),
                    field_name="effects",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                path_safety=_require_mapping_field(
                    raw_entry.get("path_safety", {}),
                    field_name="path_safety",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                source_map_behavior=_require_string_field(
                    raw_entry.get("source_map_behavior", ""),
                    field_name="source_map_behavior",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                fixture_ids=_require_string_array(
                    raw_entry.get("fixture_ids", ()),
                    field_name="fixture_ids",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                negative_fixture_ids=_require_string_array(
                    raw_entry.get("negative_fixture_ids", ()),
                    field_name="negative_fixture_ids",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                behavior_class=_require_optional_string_field(
                    raw_entry.get("behavior_class"),
                    field_name="behavior_class",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                input_signature=_require_input_signature(
                    raw_entry.get("input_signature", ()),
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                artifact_contracts=_require_string_array(
                    raw_entry.get("artifact_contracts", ()),
                    field_name="artifact_contracts",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                state_writes=_require_string_array(
                    raw_entry.get("state_writes", ()),
                    field_name="state_writes",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                error_codes=_require_string_array(
                    raw_entry.get("error_codes", ()),
                    field_name="error_codes",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                owner_module=_require_optional_string_field(
                    raw_entry.get("owner_module"),
                    field_name="owner_module",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                replacement_path=_require_optional_string_field(
                    raw_entry.get("replacement_path"),
                    field_name="replacement_path",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                invocation_protocol=_require_optional_string_field(
                    raw_entry.get("invocation_protocol"),
                    field_name="invocation_protocol",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                transition_binding=_require_transition_binding(
                    raw_entry.get("transition_binding"),
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                view_binding=_require_view_binding(
                    raw_entry.get("view_binding"),
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                declared_promoted_fields=declared_promoted_fields,
                retirement_class=_require_optional_string_field(
                    raw_entry.get("retirement_class"),
                    field_name="retirement_class",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_label=_require_optional_string_field(
                    raw_entry.get("retirement_label"),
                    field_name="retirement_label",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                replacement_surface=_require_optional_string_field(
                    raw_entry.get("replacement_surface"),
                    field_name="replacement_surface",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                bridge_owner=_require_optional_string_field(
                    raw_entry.get("bridge_owner"),
                    field_name="bridge_owner",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                expiry_condition=_require_optional_string_field(
                    raw_entry.get("expiry_condition"),
                    field_name="expiry_condition",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                evidence_refs=_require_optional_string_array(
                    raw_entry.get("evidence_refs"),
                    field_name="evidence_refs",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_status=_require_optional_string_field(
                    raw_entry.get("retirement_status"),
                    field_name="retirement_status",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
            )
            continue
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"unsupported command boundary kind `{kind}` for `{name}`",
                    path=manifest_path,
                ),
            )
        )
    return bindings


def _require_string_array(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be an array of strings",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return tuple(value)


def _require_optional_string_array(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    return _require_string_array(
        value,
        field_name=field_name,
        binding_name=binding_name,
        manifest_path=manifest_path,
    )


def _require_mapping_field(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be a JSON object",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return dict(value)


def _require_string_field(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> str:
    if not isinstance(value, str):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be a string",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return value


def _require_optional_string_field(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be a string or null",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return value


def _require_input_signature(
    value: object,
    *,
    binding_name: str,
    manifest_path: Path | None,
) -> tuple[CertifiedAdapterInputField, ...]:
    if not isinstance(value, (list, tuple)):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`input_signature` for `{binding_name}` must be an array of objects",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    fields: list[CertifiedAdapterInputField] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"`input_signature[{index}]` for `{binding_name}` must be a JSON object",
                        path=manifest_path or Path(binding_name),
                    ),
                )
            )
        name = _require_string_field(
            item.get("name", ""),
            field_name=f"input_signature[{index}].name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        )
        type_name = _require_string_field(
            item.get("type_name", ""),
            field_name=f"input_signature[{index}].type_name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        )
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"`input_signature[{index}].required` for `{binding_name}` must be a boolean",
                        path=manifest_path or Path(binding_name),
                    ),
                )
            )
        transport_key = _require_string_field(
            item.get("transport_key", ""),
            field_name=f"input_signature[{index}].transport_key",
            binding_name=binding_name,
            manifest_path=manifest_path,
        )
        fields.append(
            CertifiedAdapterInputField(
                name=name,
                type_name=type_name,
                required=required,
                transport_key=transport_key,
            )
        )
    return tuple(fields)


def _require_transition_binding(
    value: object,
    *,
    binding_name: str,
    manifest_path: Path | None,
) -> TransitionBindingMetadata | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`transition_binding` for `{binding_name}` must be an object",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return TransitionBindingMetadata(
        transition_name=_require_string_field(
            value.get("transition_name", ""),
            field_name="transition_binding.transition_name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        resource_kind=_require_string_field(
            value.get("resource_kind", ""),
            field_name="transition_binding.resource_kind",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        contract_role=_require_string_field(
            value.get("contract_role", ""),
            field_name="transition_binding.contract_role",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        backend_selector=_require_string_field(
            value.get("backend_selector", ""),
            field_name="transition_binding.backend_selector",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
    )


def _require_view_binding(
    value: object,
    *,
    binding_name: str,
    manifest_path: Path | None,
) -> ViewBindingMetadata | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`view_binding` for `{binding_name}` must be an object",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    renderer_version = value.get("renderer_version")
    if not isinstance(renderer_version, int):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`view_binding.renderer_version` for `{binding_name}` must be an integer",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return ViewBindingMetadata(
        view_name=_require_string_field(
            value.get("view_name", ""),
            field_name="view_binding.view_name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        renderer_id=_require_string_field(
            value.get("renderer_id", ""),
            field_name="view_binding.renderer_id",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        renderer_version=renderer_version,
        contract_role=_require_string_field(
            value.get("contract_role", ""),
            field_name="view_binding.contract_role",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
    )


def _load_json_file(path: Path, *, label: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_missing",
                    message=f"{label} does not exist",
                    path=path,
                ),
            )
        ) from exc
    except json.JSONDecodeError as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_invalid_json",
                    message=f"{label} must contain valid JSON",
                    path=path,
                    line=exc.lineno,
                    column=exc.colno,
                    offset=exc.pos,
                    notes=(exc.msg,),
                ),
            )
        ) from exc


def _resolve_manifest_relative_path(manifest_path: Path, entry_path: str) -> Path:
    candidate = Path(entry_path)
    if not candidate.is_absolute():
        candidate = (manifest_path.parent / candidate).resolve()
    return candidate


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cli_request_diagnostic(
    *,
    code: str,
    message: str,
    path: Path,
    line: int = 1,
    column: int = 1,
    offset: int = 0,
    notes: tuple[str, ...] = (),
) -> LispFrontendDiagnostic:
    return LispFrontendDiagnostic(
        code=code,
        message=message,
        span=SourceSpan(
            start=SourcePosition(path=str(path), line=line, column=column, offset=offset),
            end=SourcePosition(path=str(path), line=line, column=column, offset=offset),
        ),
        notes=notes,
        phase="cli_request",
    )


def _json_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    if isinstance(value, list):
        return [_json_data(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _json_data(getattr(value, field.name))
            for field in fields(value)
        }
    if hasattr(value, "__dict__"):
        return {
            key: _json_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)
