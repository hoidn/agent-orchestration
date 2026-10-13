"""Canonical normalized-program identity shared by preparation and wire validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Iterable

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256


def _canonical_json_value(value: object) -> object:
    """Copy one closed JSON value through the canonical encoder."""

    return json.loads(canonical_json_bytes(value))


def _is_sha256_identity(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _canonical_selected_entry(
    selected_entry: Mapping[str, object],
) -> dict[str, object]:
    value = _canonical_json_value(dict(selected_entry))
    if not isinstance(value, Mapping) or set(value) != {
        "selected_name",
        "canonical_name",
        "signature",
    }:
        raise ValueError("selected entry has an invalid shape")
    if any(
        not isinstance(value.get(field), str) or not value.get(field)
        for field in ("selected_name", "canonical_name")
    ):
        raise ValueError("selected entry names must be non-empty strings")
    signature = value.get("signature")
    if not isinstance(signature, Mapping) or set(signature) != {
        "parameters",
        "return_type",
        "input_contracts",
        "output_contracts",
    }:
        raise ValueError("selected entry signature has an invalid shape")
    parameters = signature.get("parameters")
    if not isinstance(parameters, list) or any(
        not isinstance(parameter, Mapping)
        or set(parameter) != {"name", "type", "required"}
        or not isinstance(parameter.get("name"), str)
        or not parameter.get("name")
        or not isinstance(parameter.get("type"), str)
        or not parameter.get("type")
        or not isinstance(parameter.get("required"), bool)
        for parameter in parameters
    ):
        raise ValueError("selected entry signature parameters have an invalid shape")
    parameter_names = [str(parameter["name"]) for parameter in parameters]
    if len(parameter_names) != len(set(parameter_names)):
        raise ValueError("selected entry signature parameters contain a duplicate")
    if (
        not isinstance(signature.get("return_type"), str)
        or not signature.get("return_type")
    ):
        raise ValueError("selected entry return type must be a non-empty string")
    for field in ("input_contracts", "output_contracts"):
        contracts = signature.get(field)
        if not isinstance(contracts, Mapping) or any(
            not isinstance(name, str) or not name for name in contracts
        ):
            raise ValueError(f"selected entry {field} have an invalid shape")
    return dict(value)


def _canonical_module_source_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    value = _canonical_json_value(list(rows))
    if not isinstance(value, list) or not value:
        raise ValueError("program identity requires module source revisions")
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"module_name", "source_sha256"}
        or not isinstance(row.get("module_name"), str)
        or not row.get("module_name")
        or not _is_sha256_identity(row.get("source_sha256"))
        for row in value
    ):
        raise ValueError("module source revisions have an invalid shape")
    names = [str(row["module_name"]) for row in value]
    if len(names) != len(set(names)):
        raise ValueError("module source revisions contain a duplicate module")
    return sorted(
        (dict(row) for row in value),
        key=lambda row: str(row["module_name"]).encode("utf-8"),
    )


def _canonical_compiler_source_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    value = _canonical_json_value(list(rows))
    if not isinstance(value, list) or not value:
        raise ValueError("program identity requires compiler source revisions")
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"root_role", "relative_path", "source_sha256"}
        or not isinstance(row.get("root_role"), str)
        or not row.get("root_role")
        or not isinstance(row.get("relative_path"), str)
        or not row.get("relative_path")
        or not _is_sha256_identity(row.get("source_sha256"))
        for row in value
    ):
        raise ValueError("compiler source revisions have an invalid shape")
    identities = [
        (str(row["root_role"]), str(row["relative_path"]))
        for row in value
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("compiler source revisions contain a duplicate path")
    return sorted(
        (dict(row) for row in value),
        key=lambda row: (
            str(row["root_role"]).encode("utf-8"),
            str(row["relative_path"]).encode("utf-8"),
        ),
    )


def _canonical_imported_bundle_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    value = _canonical_json_value(list(rows))
    if not isinstance(value, list):
        raise ValueError("imported bundle bindings have an invalid shape")
    expected_fields = {
        "canonical_key",
        "bundle_kind",
        "workflow_name",
        "resolved_workflow_name",
    }
    if any(
        not isinstance(row, Mapping)
        or set(row) != expected_fields
        or not isinstance(row.get("canonical_key"), str)
        or not row.get("canonical_key")
        or not isinstance(row.get("bundle_kind"), str)
        or not row.get("bundle_kind")
        or not (
            row.get("workflow_name") is None
            or (
                isinstance(row.get("workflow_name"), str)
                and bool(row.get("workflow_name"))
            )
        )
        or not isinstance(row.get("resolved_workflow_name"), str)
        or not row.get("resolved_workflow_name")
        for row in value
    ):
        raise ValueError("imported bundle bindings have an invalid shape")
    keys = [str(row["canonical_key"]) for row in value]
    if len(keys) != len(set(keys)):
        raise ValueError("imported bundle bindings contain a duplicate key")
    return sorted(
        (dict(row) for row in value),
        key=lambda row: str(row["canonical_key"]).encode("utf-8"),
    )


def build_normalized_program_identity(
    *,
    compiler_runtime_identity: str,
    module_source_revisions: Iterable[Mapping[str, object]],
    compiler_source_revisions: Iterable[Mapping[str, object]],
    imported_bundle_bindings: Iterable[Mapping[str, object]],
    selected_entry: Mapping[str, object],
    lowering_route: str,
    lowering_schema_version: int,
    configuration_payload_digests: Mapping[str, str],
    configuration_revisions: Iterable[Mapping[str, object]],
    boundary_admission_profile: str | None = None,
) -> dict[str, object]:
    """Build the path-independent identity exposed by machine compilation."""

    if not _is_sha256_identity(compiler_runtime_identity):
        raise ValueError("compiler/runtime identity must be a SHA-256 identity")
    if not isinstance(lowering_route, str) or not lowering_route:
        raise ValueError("lowering route must be non-empty")
    if (
        not isinstance(lowering_schema_version, int)
        or isinstance(lowering_schema_version, bool)
        or lowering_schema_version < 1
    ):
        raise ValueError("lowering schema version must be positive")
    module_rows = _canonical_module_source_rows(module_source_revisions)
    compiler_source_rows = _canonical_compiler_source_rows(
        compiler_source_revisions
    )
    imported_bundle_rows = _canonical_imported_bundle_rows(
        imported_bundle_bindings
    )
    payload_digests = _canonical_json_value(dict(configuration_payload_digests))
    expected_configuration_roles = {
        "provider_externs",
        "prompt_externs",
        "command_boundaries",
    }
    if (
        not isinstance(payload_digests, Mapping)
        or set(payload_digests) != expected_configuration_roles
        or any(not _is_sha256_identity(value) for value in payload_digests.values())
    ):
        raise ValueError("configuration payload digests have an invalid shape")
    revision_rows_value = _canonical_json_value(list(configuration_revisions))
    if not isinstance(revision_rows_value, list) or {
        row.get("role")
        for row in revision_rows_value
        if isinstance(row, Mapping)
    } != expected_configuration_roles:
        raise ValueError("configuration revisions have an invalid role set")
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"role", "source_sha256"}
        or not (
            row.get("source_sha256") is None
            or _is_sha256_identity(row.get("source_sha256"))
        )
        for row in revision_rows_value
    ):
        raise ValueError("configuration revisions have an invalid shape")
    if len(revision_rows_value) != len(expected_configuration_roles):
        raise ValueError("configuration revisions contain a duplicate role")
    revision_rows = sorted(
        (dict(row) for row in revision_rows_value),
        key=lambda row: str(row["role"]).encode("utf-8"),
    )
    selected_entry_value = _canonical_selected_entry(selected_entry)
    if boundary_admission_profile is not None and boundary_admission_profile != (
        "transportable_child"
    ):
        raise ValueError("boundary admission profile is invalid")
    components = {
        "schema_version": (
            "workflow_lisp_program_identity.v1"
            if boundary_admission_profile is None
            else "workflow_lisp_program_identity.v2"
        ),
        "compiler_runtime_identity": compiler_runtime_identity,
        "module_source_revisions": module_rows,
        "compiler_source_revisions": compiler_source_rows,
        "imported_bundle_bindings": imported_bundle_rows,
        "selected_entry_sha256": canonical_sha256(selected_entry_value),
        "lowering_route": lowering_route,
        "lowering_schema_version": lowering_schema_version,
        "configuration_payload_digests": payload_digests,
        "configuration_revisions": revision_rows,
    }
    if boundary_admission_profile is not None:
        components["boundary_admission_profile"] = boundary_admission_profile
    return {
        **components,
        "digest": canonical_sha256(components),
    }
