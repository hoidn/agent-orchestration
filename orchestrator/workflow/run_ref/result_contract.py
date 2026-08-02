"""Neutral exact validation for generated run-reference result descriptors."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from orchestrator.workflow.type_descriptor import (
    is_transportable_type_descriptor as _shared_is_transportable_type_descriptor,
    validate_compiler_normalized_type_descriptor,
)

from .contracts import canonical_sha256


RUN_REF_RESULT_CONTRACT_SCHEMA = "run_ref_result_contract.v1"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GENERATED_RESULT_RE = re.compile(r"RunRefResult\$[0-9a-f]{16}\Z")


def _require_exact_keys(
    value: object,
    expected: set[str],
    *,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    if set(value) != expected:
        raise ValueError(f"{context} has missing or extra fields")
    return value


def _primitive(name: str) -> dict[str, str]:
    return {"kind": "primitive", "name": name}


def _field(name: str, type_descriptor: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "type": type_descriptor}


def _record(name: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "record", "name": name, "fields": fields}


def _optional(item: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "optional", "item": item}


def _list(item: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "list", "item": item}


def _workspace_delta_descriptor() -> dict[str, Any]:
    repository_revision = _record(
        "RepositoryRevisionId",
        [
            _field(name, _primitive("String"))
            for name in (
                "digest",
                "normalized_locator",
                "resolved_commit_sha",
                "materializer_version",
                "submodule_policy",
                "lfs_policy",
                "authored_setup_identity",
            )
        ],
    )
    workspace_entry = _record(
        "WorkspaceEntryDelta",
        [
            _field("path", _primitive("String")),
            _field("kind", _primitive("String")),
            _field("mode", _primitive("Int")),
            _field("size", _primitive("Int")),
            _field("old_sha256", _optional(_primitive("String"))),
            _field("new_sha256", _optional(_primitive("String"))),
            _field("link_target", _optional(_primitive("String"))),
        ],
    )
    normalized_text_entry = _record(
        "NormalizedTextDiffEntry",
        [
            _field("path", _primitive("String")),
            _field("text", _primitive("String")),
            _field("truncated", _primitive("Bool")),
            _field("omitted_bytes", _primitive("Int")),
        ],
    )
    normalized_diff = _record(
        "NormalizedWorkspaceDiff",
        [
            _field("entries", _list(normalized_text_entry)),
            _field("catalog_digest", _primitive("String")),
            _field("truncated", _primitive("Bool")),
            _field("omitted_bytes", _primitive("Int")),
            _field("omitted_entries", _primitive("Int")),
        ],
    )
    declared_artifact = _record(
        "DeclaredWorkspaceArtifact",
        [
            _field("name", _primitive("String")),
            _field("path", _primitive("String")),
            _field("kind", _primitive("String")),
            _field("mode", _primitive("Int")),
            _field("size", _primitive("Int")),
            _field("sha256", _optional(_primitive("String"))),
            _field("link_target", _optional(_primitive("String"))),
        ],
    )
    return _record(
        "WorkspaceDelta",
        [
            _field("base", repository_revision),
            _field("changed_files", _list(workspace_entry)),
            _field("deleted_files", _list(workspace_entry)),
            _field("untracked_files", _list(workspace_entry)),
            _field("normalized_diff", normalized_diff),
            _field("declared_artifacts", _list(declared_artifact)),
        ],
    )


def _accounting_descriptor() -> dict[str, Any]:
    return _record(
        "RunRefAccounting",
        [
            _field("child_run_id", _primitive("RunId")),
            _field("attempt_ordinal", _primitive("Int")),
            _field("terminal_status", _primitive("String")),
            _field("elapsed_ms", _primitive("Int")),
            _field("setup_ms", _primitive("Int")),
            _field("compile_ms", _primitive("Int")),
            _field("provider_attempts", _primitive("Value")),
            _field("token_usage", _primitive("Value")),
            _field("cost", _primitive("Value")),
        ],
    )


def is_transportable_type_descriptor(
    descriptor: Mapping[str, Any],
    *,
    collection_item: bool = False,
    allow_nested_structures: bool = False,
) -> bool:
    """Compatibility wrapper over the neutral transportability owner."""

    if collection_item and descriptor.get("kind") in {"record", "union"}:
        return allow_nested_structures and _shared_is_transportable_type_descriptor(
            descriptor,
            allow_nested_structures=True,
        )
    return _shared_is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=allow_nested_structures,
    )


def validate_run_ref_result_descriptor(
    descriptor: Mapping[str, Any],
    *,
    expected_generated_name: str | None = None,
    expected_digest: str | None = None,
    allow_nested_structures: bool = False,
) -> None:
    """Validate one full exact runtime-owned run-ref result descriptor."""

    row = _require_exact_keys(
        descriptor,
        {"schema", "envelope"},
        context="run-ref result descriptor",
    )
    if row["schema"] != RUN_REF_RESULT_CONTRACT_SCHEMA:
        raise ValueError("run-ref result descriptor schema is unsupported")
    envelope = row["envelope"]
    validate_compiler_normalized_type_descriptor(
        envelope,
        context="run_ref_result_contract.envelope",
    )
    if envelope["kind"] != "record":
        raise ValueError("run-ref result envelope must be a record")
    generated_name = envelope["name"]
    if not isinstance(generated_name, str) or _GENERATED_RESULT_RE.fullmatch(
        generated_name
    ) is None:
        raise ValueError("run-ref result envelope name is invalid")
    if expected_generated_name is not None and generated_name != expected_generated_name:
        raise ValueError("run-ref result envelope name does not match its site")
    fields = envelope["fields"]
    if [field["name"] for field in fields] != [
        "value",
        "workspace_delta",
        "accounting",
    ]:
        raise ValueError("run-ref result field order is invalid")
    if not is_transportable_type_descriptor(
        fields[0]["type"],
        allow_nested_structures=allow_nested_structures,
    ):
        raise ValueError("run-ref result value descriptor is not transportable")
    if fields[1]["type"] != _workspace_delta_descriptor():
        raise ValueError("run-ref workspace delta schema is invalid")
    if fields[2]["type"] != _accounting_descriptor():
        raise ValueError("run-ref accounting schema is invalid")
    digest = canonical_sha256(descriptor)
    if expected_digest is not None:
        if not isinstance(expected_digest, str) or _SHA256_RE.fullmatch(
            expected_digest
        ) is None:
            raise ValueError("run-ref result digest is invalid")
        if digest != expected_digest:
            raise ValueError("run-ref result digest does not match its descriptor")


__all__ = [
    "RUN_REF_RESULT_CONTRACT_SCHEMA",
    "is_transportable_type_descriptor",
    "validate_run_ref_result_descriptor",
]
