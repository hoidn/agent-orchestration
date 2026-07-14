"""Evidence-only procedure identity retirement records.

This module is deliberately detached from run, resume, executor, and call
paths.  A retirement record supports human review; it is never a runtime
directive, identity alias, or state-remapping input.

The checked-in valid fixture contains conspicuously fictional owner and
attestation text.  That test data must never be copied into pilot evidence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote


SCHEMA = "workflow_lisp_procedure_identity_retirement.v1"
COMPATIBILITY_CLASS = "reviewed_internal_identity_retirement"
STORE_QUERY_VERSION = "procedure-identity-store-query.v1"
FORBIDDEN_RUNTIME_KEYS = frozenset(
    {"runtime_remap", "remap_directive", "identity_aliases", "old_to_new_map"}
)
REQUIRED_ARTIFACT_ROLES = frozenset(
    {
        "source",
        "typed_frontend_ast",
        "semantic_ir",
        "executable_ir",
        "runtime_plan",
        "lexical_checkpoint_points",
        "source_map",
    }
)
REQUIRED_IDENTITY_DOMAINS = frozenset(
    {
        "workflow",
        "call_frame",
        "executable_node",
        "step",
        "presentation_key",
        "program_point",
        "checkpoint",
        "state_allocation",
        "source_map_origin",
    }
)


@dataclass(frozen=True)
class ContentAddressedArtifact:
    side: str
    role: str
    path: str
    sha256: str


@dataclass(frozen=True)
class KnownStateStoreEvidence:
    root: str
    owner: str | None
    query_version: str
    query_time: str
    normalized_scan_digest: str
    terminal_run_count: int
    nonterminal_run_count: int
    call_frame_count: int
    consumer_count: int
    checkpoint_index_count: int
    checkpoint_record_count: int
    retained_manifest_count: int
    identity_metadata_count: int
    scanned_file_count: int
    attestation: str | None
    attested_at: str | None


@dataclass(frozen=True)
class IdentityDeltaRow:
    identity_kind: str
    old_identity: str | None
    old_disposition: str | None
    new_identity: str | None
    new_disposition: str | None


@dataclass(frozen=True)
class ArtifactContractKey:
    owning_public_entry: str
    semantic_step_role: str
    contract_kind: str
    name: str
    json_pointer: str
    type_variant: str
    publication_role: str


@dataclass(frozen=True)
class ArtifactMultisetRow:
    side: str
    key: ArtifactContractKey
    count: int


@dataclass(frozen=True)
class ExecutionOrderEntry:
    side: str
    position: int
    semantic_step_role: str
    contract_kind: str
    name: str


@dataclass(frozen=True)
class ProcedureIdentityRetirementRecord:
    schema: str
    migration: Mapping[str, Any]
    retained_public_entry: Mapping[str, Any]
    callee: Mapping[str, Any]
    retained_wrapper_evidence: Mapping[str, Any]
    supporting_labels: tuple[str, ...]
    known_state_stores: tuple[KnownStateStoreEvidence, ...]
    external_store_absence: str
    artifacts: tuple[ContentAddressedArtifact, ...]
    identity_delta: tuple[IdentityDeltaRow, ...]
    artifact_multiset: tuple[ArtifactMultisetRow, ...]
    execution_order: tuple[ExecutionOrderEntry, ...]
    lineage_notes: tuple[Mapping[str, Any], ...]
    new_id_evidence: Mapping[str, Any]
    checksum_evidence: Mapping[str, Any]
    runtime_directives: tuple[Any, ...]


@dataclass(frozen=True)
class RetirementIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class RetirementValidationResult:
    issues: tuple[RetirementIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def _frozen(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_frozen(item) for item in value)
    return value


def _object(
    value: Any,
    path: str,
    *,
    allowed: Iterable[str],
    required: Iterable[str] = (),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    allowed_set = set(allowed)
    unknown = sorted(set(value) - allowed_set)
    if unknown:
        raise ValueError(f"{path} has unknown fields: {', '.join(unknown)}")
    missing = sorted(set(required) - set(value))
    if missing:
        raise ValueError(f"{path} is missing required fields: {', '.join(missing)}")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _string(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        suffix = " or null" if nullable else ""
        raise ValueError(f"{path} must be a string{suffix}")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    return value


def _reject_forbidden_runtime_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_RUNTIME_KEYS:
                raise ValueError(
                    "procedure_identity_retirement_forbidden_runtime_key: "
                    f"{path}.{key} is forbidden"
                )
            _reject_forbidden_runtime_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_runtime_keys(item, f"{path}[{index}]")


def _json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                "procedure_identity_retirement_duplicate_json_key: "
                f"duplicate JSON object key {key!r}"
            )
        result[key] = value
    return result


def _parse_metadata(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    migration = _object(
        payload["migration"],
        "$.migration",
        allowed={
            "migration_id",
            "compatibility_class",
            "repository_commit",
            "compiler_version",
            "build_version",
            "captured_at",
            "test_fixture_notice",
        },
        required={
            "migration_id",
            "compatibility_class",
            "repository_commit",
            "compiler_version",
            "build_version",
            "captured_at",
        },
    )
    for key, value in migration.items():
        _string(value, f"$.migration.{key}")

    retained = _object(
        payload["retained_public_entry"],
        "$.retained_public_entry",
        allowed={"module", "workflow", "contract_digest"},
        required={"module", "workflow", "contract_digest"},
    )
    for key, value in retained.items():
        _string(value, f"$.retained_public_entry.{key}")

    callee = _object(
        payload["callee"],
        "$.callee",
        allowed={
            "module",
            "identity",
            "exported",
            "registered_public_entry",
            "public",
            "route_promoted",
            "route_live",
        },
        required={
            "module",
            "identity",
            "exported",
            "registered_public_entry",
            "public",
            "route_promoted",
            "route_live",
        },
    )
    _string(callee["module"], "$.callee.module")
    _string(callee["identity"], "$.callee.identity")
    for key in ("exported", "registered_public_entry", "public", "route_promoted", "route_live"):
        _boolean(callee[key], f"$.callee.{key}")

    wrapper = _object(
        payload["retained_wrapper_evidence"],
        "$.retained_wrapper_evidence",
        allowed={
            "inventory_path",
            "source_path",
            "reviewed_call_site",
            "retained_wrapper",
            "contract_digest",
        },
        required={
            "inventory_path",
            "source_path",
            "reviewed_call_site",
            "retained_wrapper",
            "contract_digest",
        },
    )
    for key, value in wrapper.items():
        _string(value, f"$.retained_wrapper_evidence.{key}")
    return _frozen(migration), _frozen(retained), _frozen(callee), _frozen(wrapper)


def _parse_stores(value: Any) -> tuple[KnownStateStoreEvidence, ...]:
    stores: list[KnownStateStoreEvidence] = []
    for index, raw in enumerate(_list(value, "$.known_state_stores")):
        path = f"$.known_state_stores[{index}]"
        row = _object(
            raw,
            path,
            allowed={
                "root",
                "owner",
                "query_version",
                "query_time",
                "normalized_scan_digest",
                "terminal_run_count",
                "nonterminal_run_count",
                "call_frame_count",
                "consumer_count",
                "checkpoint_index_count",
                "checkpoint_record_count",
                "retained_manifest_count",
                "identity_metadata_count",
                "scanned_file_count",
                "attestation",
                "attested_at",
            },
            required={
                "root",
                "query_version",
                "query_time",
                "normalized_scan_digest",
                "terminal_run_count",
                "nonterminal_run_count",
                "call_frame_count",
                "consumer_count",
                "checkpoint_index_count",
                "checkpoint_record_count",
                "retained_manifest_count",
                "identity_metadata_count",
                "scanned_file_count",
            },
        )
        for key in ("root", "query_version", "query_time", "normalized_scan_digest"):
            _string(row[key], f"{path}.{key}")
        owner = _string(row.get("owner"), f"{path}.owner", nullable=True)
        attestation = _string(row.get("attestation"), f"{path}.attestation", nullable=True)
        attested_at = _string(row.get("attested_at"), f"{path}.attested_at", nullable=True)
        counts = {
            key: _integer(row[key], f"{path}.{key}")
            for key in (
                "terminal_run_count",
                "nonterminal_run_count",
                "call_frame_count",
                "consumer_count",
                "checkpoint_index_count",
                "checkpoint_record_count",
                "retained_manifest_count",
                "identity_metadata_count",
                "scanned_file_count",
            )
        }
        stores.append(
            KnownStateStoreEvidence(
                root=row["root"],
                owner=owner,
                query_version=row["query_version"],
                query_time=row["query_time"],
                normalized_scan_digest=row["normalized_scan_digest"],
                terminal_run_count=counts["terminal_run_count"],
                nonterminal_run_count=counts["nonterminal_run_count"],
                call_frame_count=counts["call_frame_count"],
                consumer_count=counts["consumer_count"],
                checkpoint_index_count=counts["checkpoint_index_count"],
                checkpoint_record_count=counts["checkpoint_record_count"],
                retained_manifest_count=counts["retained_manifest_count"],
                identity_metadata_count=counts["identity_metadata_count"],
                scanned_file_count=counts["scanned_file_count"],
                attestation=attestation,
                attested_at=attested_at,
            )
        )
    return tuple(stores)


def _parse_artifacts(value: Any) -> tuple[ContentAddressedArtifact, ...]:
    artifacts: list[ContentAddressedArtifact] = []
    for index, raw in enumerate(_list(value, "$.artifacts")):
        path = f"$.artifacts[{index}]"
        row = _object(
            raw,
            path,
            allowed={"side", "role", "path", "sha256"},
            required={"side", "role", "path", "sha256"},
        )
        for key in ("side", "role", "path", "sha256"):
            _string(row[key], f"{path}.{key}")
        artifacts.append(ContentAddressedArtifact(**row))
    return tuple(artifacts)


def _parse_identity_delta(value: Any) -> tuple[IdentityDeltaRow, ...]:
    rows: list[IdentityDeltaRow] = []
    for index, raw in enumerate(_list(value, "$.identity_delta")):
        path = f"$.identity_delta[{index}]"
        row = _object(
            raw,
            path,
            allowed={
                "identity_kind",
                "old_identity",
                "old_disposition",
                "new_identity",
                "new_disposition",
            },
            required={
                "identity_kind",
                "old_identity",
                "old_disposition",
                "new_identity",
                "new_disposition",
            },
        )
        identity_kind = _string(row["identity_kind"], f"{path}.identity_kind")
        old_identity = _string(row["old_identity"], f"{path}.old_identity", nullable=True)
        old_disposition = _string(row["old_disposition"], f"{path}.old_disposition", nullable=True)
        new_identity = _string(row["new_identity"], f"{path}.new_identity", nullable=True)
        new_disposition = _string(row["new_disposition"], f"{path}.new_disposition", nullable=True)
        rows.append(
            IdentityDeltaRow(
                identity_kind=identity_kind,
                old_identity=old_identity,
                old_disposition=old_disposition,
                new_identity=new_identity,
                new_disposition=new_disposition,
            )
        )
    return tuple(rows)


def _parse_artifact_key(value: Any, path: str) -> ArtifactContractKey:
    fields = {
        "owning_public_entry",
        "semantic_step_role",
        "contract_kind",
        "name",
        "json_pointer",
        "type_variant",
        "publication_role",
    }
    row = _object(value, path, allowed=fields, required=fields)
    for key in fields:
        _string(row[key], f"{path}.{key}")
    return ArtifactContractKey(**row)


def _parse_artifact_multiset(value: Any) -> tuple[ArtifactMultisetRow, ...]:
    payload = _object(value, "$.artifact_multiset", allowed={"old", "new"}, required={"old", "new"})
    rows: list[ArtifactMultisetRow] = []
    for side in ("old", "new"):
        for index, raw in enumerate(_list(payload[side], f"$.artifact_multiset.{side}")):
            path = f"$.artifact_multiset.{side}[{index}]"
            item = _object(raw, path, allowed={"key", "count"}, required={"key"})
            if "count" not in item:
                raise ValueError(
                    "procedure_identity_retirement_artifact_count_missing: "
                    f"{path}.count is required for keyed-multiset evidence"
                )
            count = _integer(item["count"], f"{path}.count")
            rows.append(
                ArtifactMultisetRow(
                    side=side,
                    key=_parse_artifact_key(item["key"], f"{path}.key"),
                    count=count,
                )
            )
    return tuple(rows)


def _parse_execution_order(value: Any) -> tuple[ExecutionOrderEntry, ...]:
    payload = _object(value, "$.execution_order", allowed={"old", "new"}, required={"old", "new"})
    rows: list[ExecutionOrderEntry] = []
    fields = {"position", "semantic_step_role", "contract_kind", "name"}
    for side in ("old", "new"):
        for index, raw in enumerate(_list(payload[side], f"$.execution_order.{side}")):
            path = f"$.execution_order.{side}[{index}]"
            item = _object(raw, path, allowed=fields, required=fields)
            position = _integer(item["position"], f"{path}.position")
            for key in ("semantic_step_role", "contract_kind", "name"):
                _string(item[key], f"{path}.{key}")
            rows.append(ExecutionOrderEntry(side=side, position=position, **{key: item[key] for key in fields - {"position"}}))
    return tuple(rows)


def _parse_lineage_notes(value: Any) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    fields = {"executable_node", "procedure_definition_note", "call_site_note"}
    for index, raw in enumerate(_list(value, "$.lineage_notes")):
        path = f"$.lineage_notes[{index}]"
        row = _object(raw, path, allowed=fields, required=fields)
        for key in fields:
            _string(row[key], f"{path}.{key}")
        rows.append(_frozen(row))
    return tuple(rows)


def _parse_evidence_blocks(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    new_evidence = _object(
        payload["new_id_evidence"],
        "$.new_id_evidence",
        allowed={"clean_run", "interruption_resume"},
    )
    clean_fields = {"run_id", "status", "public_contract_digest", "artifact_multiset_digest"}
    resume_fields = {
        "run_id",
        "interruption_point",
        "status",
        "reused_only_new_id_work",
        "public_contract_digest",
    }
    if "clean_run" in new_evidence:
        clean = _object(
            new_evidence["clean_run"],
            "$.new_id_evidence.clean_run",
            allowed=clean_fields,
            required=clean_fields,
        )
        for key, value in clean.items():
            _string(value, f"$.new_id_evidence.clean_run.{key}")
    if "interruption_resume" in new_evidence:
        resume = _object(
            new_evidence["interruption_resume"],
            "$.new_id_evidence.interruption_resume",
            allowed=resume_fields,
            required=resume_fields,
        )
        for key, value in resume.items():
            if key == "reused_only_new_id_work":
                _boolean(value, f"$.new_id_evidence.interruption_resume.{key}")
            else:
                _string(value, f"$.new_id_evidence.interruption_resume.{key}")

    checksum = _object(
        payload["checksum_evidence"],
        "$.checksum_evidence",
        allowed={"root", "callee"},
    )
    root_fields = {
        "command",
        "default_resume",
        "observability_overrides",
        "cli_overrides",
        "exit_status",
        "before_tree_digest",
        "after_tree_digest",
        "executor_constructed",
        "provider_executed",
        "command_executed",
    }
    callee_fields = {
        "command",
        "mismatch_identity",
        "checksum_mismatch_observed",
        "child_workflow_executed",
        "provider_executed",
        "command_executed",
        "child_state_identity_remapped",
        "parent_metadata_delta",
    }
    if "root" in checksum:
        root = _object(checksum["root"], "$.checksum_evidence.root", allowed=root_fields, required=root_fields)
        _string(root["command"], "$.checksum_evidence.root.command")
        _integer(root["exit_status"], "$.checksum_evidence.root.exit_status")
        _string(root["before_tree_digest"], "$.checksum_evidence.root.before_tree_digest")
        _string(root["after_tree_digest"], "$.checksum_evidence.root.after_tree_digest")
        for key in root_fields - {"command", "exit_status", "before_tree_digest", "after_tree_digest"}:
            _boolean(root[key], f"$.checksum_evidence.root.{key}")
    if "callee" in checksum:
        callee = _object(
            checksum["callee"],
            "$.checksum_evidence.callee",
            allowed=callee_fields,
            required=callee_fields,
        )
        for key in ("command", "mismatch_identity", "parent_metadata_delta"):
            _string(callee[key], f"$.checksum_evidence.callee.{key}")
        for key in callee_fields - {"command", "mismatch_identity", "parent_metadata_delta"}:
            _boolean(callee[key], f"$.checksum_evidence.callee.{key}")
    return _frozen(new_evidence), _frozen(checksum)


def load_retirement_record(path: str | Path) -> ProcedureIdentityRetirementRecord:
    """Load a strict v1 evidence record without consulting runtime state."""

    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicates,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load procedure identity retirement record {source}: {exc}") from exc
    _reject_forbidden_runtime_keys(payload)
    root_fields = {
        "schema",
        "migration",
        "retained_public_entry",
        "callee",
        "retained_wrapper_evidence",
        "supporting_labels",
        "known_state_stores",
        "external_store_absence",
        "artifacts",
        "identity_delta",
        "artifact_multiset",
        "execution_order",
        "lineage_notes",
        "new_id_evidence",
        "checksum_evidence",
        "runtime_directives",
    }
    payload = _object(payload, "$", allowed=root_fields, required=root_fields)
    schema = _string(payload["schema"], "$.schema")
    external_store_absence = _string(payload["external_store_absence"], "$.external_store_absence")
    migration, retained, callee, wrapper = _parse_metadata(payload)
    labels = tuple(
        _string(value, f"$.supporting_labels[{index}]")
        for index, value in enumerate(_list(payload["supporting_labels"], "$.supporting_labels"))
    )
    runtime_directives = tuple(_frozen(value) for value in _list(payload["runtime_directives"], "$.runtime_directives"))
    new_evidence, checksum = _parse_evidence_blocks(payload)
    return ProcedureIdentityRetirementRecord(
        schema=schema,
        migration=migration,
        retained_public_entry=retained,
        callee=callee,
        retained_wrapper_evidence=wrapper,
        supporting_labels=labels,
        known_state_stores=_parse_stores(payload["known_state_stores"]),
        external_store_absence=external_store_absence,
        artifacts=_parse_artifacts(payload["artifacts"]),
        identity_delta=_parse_identity_delta(payload["identity_delta"]),
        artifact_multiset=_parse_artifact_multiset(payload["artifact_multiset"]),
        execution_order=_parse_execution_order(payload["execution_order"]),
        lineage_notes=_parse_lineage_notes(payload["lineage_notes"]),
        new_id_evidence=new_evidence,
        checksum_evidence=checksum,
        runtime_directives=runtime_directives,
    )


def _issue(issues: list[RetirementIssue], code: str, path: str, message: str) -> None:
    issues.append(RetirementIssue(code=code, path=path, message=message))


def _valid_sha256(value: str) -> bool:
    return re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _path_has_symlink_component(root: Path, relative: Path) -> bool:
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _validate_identity_delta(record: ProcedureIdentityRetirementRecord, issues: list[RetirementIssue]) -> None:
    domains = {row.identity_kind for row in record.identity_delta}
    unknown = sorted(domains - REQUIRED_IDENTITY_DOMAINS)
    if unknown:
        _issue(
            issues,
            "procedure_identity_retirement_identity_domain_unknown",
            "$.identity_delta",
            f"unknown identity domains: {', '.join(unknown)}",
        )
    missing = sorted(REQUIRED_IDENTITY_DOMAINS - domains)
    if missing:
        _issue(
            issues,
            "procedure_identity_retirement_identity_domain_incomplete",
            "$.identity_delta",
            f"missing identity domains: {', '.join(missing)}",
        )
    for side, allowed in (("old", {"preserved", "retired"}), ("new", {"preserved", "new"})):
        seen: dict[tuple[str, str], str] = {}
        for index, row in enumerate(record.identity_delta):
            identity = getattr(row, f"{side}_identity")
            disposition = getattr(row, f"{side}_disposition")
            path = f"$.identity_delta[{index}]"
            if (identity is None) != (disposition is None) or (disposition is not None and disposition not in allowed):
                _issue(
                    issues,
                    "procedure_identity_retirement_identity_row_invalid",
                    path,
                    f"{side} identity/disposition must be paired and use {sorted(allowed)}",
                )
                continue
            if identity is None:
                continue
            key = (row.identity_kind, identity)
            if key in seen:
                _issue(
                    issues,
                    f"procedure_identity_retirement_identity_duplicate_{side}",
                    path,
                    f"duplicate {side} identity {row.identity_kind}:{identity}",
                )
                if seen[key] != disposition:
                    _issue(
                        issues,
                        f"procedure_identity_retirement_identity_conflict_{side}",
                        path,
                        f"{side} identity is marked both {seen[key]} and {disposition}",
                    )
            else:
                seen[key] = disposition
    for index, row in enumerate(record.identity_delta):
        path = f"$.identity_delta[{index}]"
        if row.old_identity is None and row.new_identity is None:
            _issue(
                issues,
                "procedure_identity_retirement_identity_row_invalid",
                path,
                "identity row cannot be empty on both sides",
            )
        if row.old_disposition == "preserved" and not (
            row.old_identity is not None
            and row.new_identity == row.old_identity
            and row.new_disposition == "preserved"
        ):
            _issue(
                issues,
                "procedure_identity_retirement_identity_row_invalid",
                path,
                "preserved identity requires the same old/new identity and preserved dispositions",
            )
        if row.old_disposition == "retired" and not (
            row.old_identity is not None
            and row.new_identity is None
            and row.new_disposition is None
        ):
            _issue(
                issues,
                "procedure_identity_retirement_identity_row_invalid",
                path,
                "retired identity must have no new side",
            )
        if row.new_disposition == "new" and not (
            row.new_identity is not None
            and row.old_identity is None
            and row.old_disposition is None
        ):
            _issue(
                issues,
                "procedure_identity_retirement_identity_row_invalid",
                path,
                "new identity must have no old side",
            )


def _validate_artifacts(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    repo_root: Path,
) -> None:
    root = repo_root.resolve()
    roles_by_side: dict[str, set[str]] = {"old": set(), "new": set()}
    role_counts: Counter[tuple[str, str]] = Counter()
    for index, artifact in enumerate(record.artifacts):
        path = f"$.artifacts[{index}]"
        if artifact.side not in roles_by_side:
            _issue(issues, "procedure_identity_retirement_artifact_side_invalid", path, "side must be old or new")
            continue
        roles_by_side[artifact.side].add(artifact.role)
        role_counts[(artifact.side, artifact.role)] += 1
        if role_counts[(artifact.side, artifact.role)] > 1:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_role_duplicate",
                path,
                f"duplicate {artifact.side} artifact role {artifact.role}",
            )
        if not _valid_sha256(artifact.sha256):
            _issue(
                issues,
                "procedure_identity_retirement_artifact_digest_invalid",
                f"{path}.sha256",
                "artifact digest must be sha256:<64 lowercase hexadecimal characters>",
            )
            continue
        relative = Path(artifact.path)
        if relative.is_absolute() or ".." in relative.parts:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_path_outside_repository",
                f"{path}.path",
                "artifact path must be a safe repository-relative path",
            )
            continue
        if _path_has_symlink_component(root, relative):
            _issue(
                issues,
                "procedure_identity_retirement_artifact_symlink_forbidden",
                f"{path}.path",
                "artifact path must not contain symlink components",
            )
            continue
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_path_outside_repository",
                f"{path}.path",
                "artifact path must resolve inside repo_root",
            )
            continue
        if not candidate.is_file():
            _issue(
                issues,
                "procedure_identity_retirement_artifact_missing",
                f"{path}.path",
                f"artifact does not exist: {artifact.path}",
            )
            continue
        expected_name = "source.orc" if artifact.role == "source" else f"{artifact.role}.json"
        if candidate.name != expected_name:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_role_path_mismatch",
                f"{path}.path",
                f"{artifact.role} evidence must use dedicated file {expected_name}",
            )
        try:
            content = _read_stable_bytes(candidate)
        except ValueError as exc:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_read_failed",
                f"{path}.path",
                str(exc),
            )
            continue
        actual = f"sha256:{sha256(content).hexdigest()}"
        if actual != artifact.sha256:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_digest_mismatch",
                f"{path}.sha256",
                f"declared {artifact.sha256}, observed {actual}",
            )
    for side, roles in roles_by_side.items():
        extra = sorted(roles - REQUIRED_ARTIFACT_ROLES)
        if extra:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_role_unknown",
                "$.artifacts",
                f"{side} evidence has unknown roles: {', '.join(extra)}",
            )
        missing = sorted(REQUIRED_ARTIFACT_ROLES - roles)
        if missing:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_role_missing",
                "$.artifacts",
                f"{side} evidence is missing roles: {', '.join(missing)}",
            )


def _validate_contracts_and_order(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
) -> None:
    multisets: dict[str, Counter[ArtifactContractKey]] = {"old": Counter(), "new": Counter()}
    side_indexes = {"old": 0, "new": 0}
    for row in record.artifact_multiset:
        side_index = side_indexes.get(row.side, 0)
        path = f"$.artifact_multiset.{row.side}[{side_index}]"
        if row.side in side_indexes:
            side_indexes[row.side] += 1
        if row.count <= 0:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_count_invalid",
                f"{path}.count",
                "artifact multiset count must be positive",
            )
        elif row.side in multisets:
            if row.key in multisets[row.side]:
                _issue(
                    issues,
                    "procedure_identity_retirement_artifact_key_duplicate",
                    path,
                    "each side must aggregate a contract key into one counted row",
                )
            multisets[row.side][row.key] += row.count
    if multisets["old"] != multisets["new"]:
        _issue(
            issues,
            "procedure_identity_retirement_artifact_multiset_mismatch",
            "$.artifact_multiset",
            "old and new artifact contract keyed multisets differ",
        )

    sequences: dict[str, list[tuple[str, str, str]]] = {"old": [], "new": []}
    for side in ("old", "new"):
        entries = sorted((row for row in record.execution_order if row.side == side), key=lambda row: row.position)
        positions = [row.position for row in entries]
        if positions != list(range(len(entries))):
            _issue(
                issues,
                "procedure_identity_retirement_execution_order_invalid",
                f"$.execution_order.{side}",
                "execution-order positions must be contiguous from zero",
            )
        sequences[side] = [(row.semantic_step_role, row.contract_kind, row.name) for row in entries]
    if sequences["old"] != sequences["new"]:
        _issue(
            issues,
            "procedure_identity_retirement_execution_order_mismatch",
            "$.execution_order",
            "old and new execution-order evidence differs",
        )
    for side in ("old", "new"):
        ordered_counter = Counter(sequences[side])
        multiset_counter: Counter[tuple[str, str, str]] = Counter()
        for key, count in multisets[side].items():
            multiset_counter[(key.semantic_step_role, key.contract_kind, key.name)] += count
        if ordered_counter != multiset_counter:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_order_incoherent",
                f"$.execution_order.{side}",
                "execution order must contain exactly the counted artifact contract occurrences",
            )


def _canonical_artifact_multiset_digest(record: ProcedureIdentityRetirementRecord) -> str:
    rows = [row for row in record.artifact_multiset if row.side == "old"]
    payload = [
        {
            "key": {
                "owning_public_entry": row.key.owning_public_entry,
                "semantic_step_role": row.key.semantic_step_role,
                "contract_kind": row.key.contract_kind,
                "name": row.key.name,
                "json_pointer": row.key.json_pointer,
                "type_variant": row.key.type_variant,
                "publication_role": row.key.publication_role,
            },
            "count": row.count,
        }
        for row in sorted(
            rows,
            key=lambda row: (
                row.key.owning_public_entry,
                row.key.semantic_step_role,
                row.key.contract_kind,
                row.key.name,
                row.key.json_pointer,
                row.key.type_variant,
                row.key.publication_role,
            ),
        )
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _validate_evidence_blocks(record: ProcedureIdentityRetirementRecord, issues: list[RetirementIssue]) -> None:
    for block in ("clean_run", "interruption_resume"):
        if block not in record.new_id_evidence:
            _issue(
                issues,
                "procedure_identity_retirement_new_id_evidence_missing",
                f"$.new_id_evidence.{block}",
                f"new-ID {block} evidence is required",
            )
    for block in ("root", "callee"):
        if block not in record.checksum_evidence:
            _issue(
                issues,
                "procedure_identity_retirement_checksum_evidence_missing",
                f"$.checksum_evidence.{block}",
                f"{block} checksum evidence is required",
            )
    public_contract_digest = record.retained_public_entry.get("contract_digest")
    clean = record.new_id_evidence.get("clean_run")
    resumed = record.new_id_evidence.get("interruption_resume")
    if isinstance(clean, Mapping):
        invalid = (
            not str(clean.get("run_id", "")).strip()
            or clean.get("status") not in {"completed", "succeeded"}
            or not _valid_sha256(str(clean.get("public_contract_digest", "")))
            or not _valid_sha256(str(clean.get("artifact_multiset_digest", "")))
        )
        if invalid:
            _issue(
                issues,
                "procedure_identity_retirement_new_id_evidence_invalid",
                "$.new_id_evidence.clean_run",
                "clean run requires a nonempty run ID, successful terminal status, and valid digests",
            )
        if clean.get("public_contract_digest") != public_contract_digest:
            _issue(
                issues,
                "procedure_identity_retirement_public_contract_mismatch",
                "$.new_id_evidence.clean_run.public_contract_digest",
                "clean run public contract must equal the retained public contract",
            )
        if clean.get("artifact_multiset_digest") != _canonical_artifact_multiset_digest(record):
            _issue(
                issues,
                "procedure_identity_retirement_artifact_multiset_digest_mismatch",
                "$.new_id_evidence.clean_run.artifact_multiset_digest",
                "artifact multiset digest does not match canonical keyed-multiset evidence",
            )
    if isinstance(resumed, Mapping):
        invalid = (
            not str(resumed.get("run_id", "")).strip()
            or not str(resumed.get("interruption_point", "")).strip()
            or resumed.get("status") not in {"completed", "succeeded"}
            or resumed.get("reused_only_new_id_work") is not True
            or not _valid_sha256(str(resumed.get("public_contract_digest", "")))
        )
        if invalid:
            _issue(
                issues,
                "procedure_identity_retirement_new_id_evidence_invalid",
                "$.new_id_evidence.interruption_resume",
                "resume requires a run ID, interruption point, successful status, valid digest, and new-ID-only reuse",
            )
        if resumed.get("public_contract_digest") != public_contract_digest or (
            isinstance(clean, Mapping)
            and resumed.get("public_contract_digest") != clean.get("public_contract_digest")
        ):
            _issue(
                issues,
                "procedure_identity_retirement_public_contract_mismatch",
                "$.new_id_evidence.interruption_resume.public_contract_digest",
                "resumed and clean public contracts must equal the retained public contract",
            )
    root = record.checksum_evidence.get("root")
    if isinstance(root, Mapping) and (
        not str(root.get("command", "")).strip()
        or root["default_resume"] is not True
        or root["observability_overrides"] is not False
        or root["cli_overrides"] is not False
        or root["exit_status"] == 0
        or not _valid_sha256(str(root["before_tree_digest"]))
        or not _valid_sha256(str(root["after_tree_digest"]))
        or root["before_tree_digest"] != root["after_tree_digest"]
        or root["executor_constructed"] is not False
        or root["provider_executed"] is not False
        or root["command_executed"] is not False
    ):
        _issue(
            issues,
            "procedure_identity_retirement_root_checksum_proof_invalid",
            "$.checksum_evidence.root",
            "root proof must be default, byte-immutable, and pre-execution",
        )
    callee = record.checksum_evidence.get("callee")
    if isinstance(callee, Mapping) and (
        not str(callee.get("command", "")).strip()
        or not str(callee.get("mismatch_identity", "")).strip()
        or not str(callee.get("parent_metadata_delta", "")).strip()
        or callee["checksum_mismatch_observed"] is not True
        or callee["child_workflow_executed"] is not False
        or callee["provider_executed"] is not False
        or callee["command_executed"] is not False
        or callee["child_state_identity_remapped"] is not False
    ):
        _issue(
            issues,
            "procedure_identity_retirement_callee_checksum_proof_invalid",
            "$.checksum_evidence.callee",
            "callee proof must reject before child execution without remapping",
        )


def validate_retirement_record(
    record: ProcedureIdentityRetirementRecord,
    *,
    repo_root: str | Path,
) -> RetirementValidationResult:
    """Validate review evidence without mutating state or supplying runtime policy."""

    issues: list[RetirementIssue] = []
    if record.schema != SCHEMA:
        _issue(issues, "procedure_identity_retirement_schema_unsupported", "$.schema", f"expected {SCHEMA}")
    if record.migration.get("compatibility_class") != COMPATIBILITY_CLASS:
        _issue(
            issues,
            "procedure_identity_retirement_compatibility_class_invalid",
            "$.migration.compatibility_class",
            f"expected {COMPATIBILITY_CLASS}",
        )
    for key in ("migration_id", "compiler_version", "build_version"):
        value = record.migration.get(key)
        if not isinstance(value, str) or not value.strip():
            _issue(
                issues,
                "procedure_identity_retirement_metadata_missing",
                f"$.migration.{key}",
                f"{key} must be nonempty",
            )
    repository_commit = record.migration.get("repository_commit")
    if not isinstance(repository_commit, str) or re.fullmatch(r"[0-9a-f]{40}", repository_commit) is None:
        _issue(
            issues,
            "procedure_identity_retirement_metadata_invalid",
            "$.migration.repository_commit",
            "repository_commit must be a full lowercase hexadecimal commit ID",
        )
    if not _valid_timestamp(record.migration.get("captured_at")):
        _issue(
            issues,
            "procedure_identity_retirement_timestamp_invalid",
            "$.migration.captured_at",
            "captured_at must be a timezone-aware ISO-8601 timestamp",
        )
    retained_digest = record.retained_public_entry.get("contract_digest")
    wrapper_digest = record.retained_wrapper_evidence.get("contract_digest")
    for path, digest in (
        ("$.retained_public_entry.contract_digest", retained_digest),
        ("$.retained_wrapper_evidence.contract_digest", wrapper_digest),
    ):
        if not isinstance(digest, str) or not _valid_sha256(digest):
            _issue(
                issues,
                "procedure_identity_retirement_digest_invalid",
                path,
                "contract digest must be lowercase sha256:<64 hexadecimal characters>",
            )
    public_flags = ("exported", "registered_public_entry", "public", "route_promoted", "route_live")
    if any(record.callee.get(field) is not False for field in public_flags):
        _issue(
            issues,
            "procedure_identity_retirement_public_boundary",
            "$.callee",
            "callee must be internal and its route must be neither promoted nor live",
        )
    substantive = (
        record.callee.get("module"),
        record.callee.get("identity"),
        record.retained_public_entry.get("module"),
        record.retained_public_entry.get("workflow"),
        record.retained_wrapper_evidence.get("inventory_path"),
        record.retained_wrapper_evidence.get("source_path"),
        record.retained_wrapper_evidence.get("reviewed_call_site"),
        record.retained_wrapper_evidence.get("retained_wrapper"),
        record.retained_wrapper_evidence.get("contract_digest"),
    )
    if any(not isinstance(value, str) or not value.strip() for value in substantive):
        _issue(
            issues,
            "procedure_identity_retirement_substantive_evidence_missing",
            "$.retained_wrapper_evidence",
            "supporting labels cannot replace callee, wrapper, call-site, and contract evidence",
        )
    if record.retained_wrapper_evidence.get("contract_digest") != record.retained_public_entry.get("contract_digest"):
        _issue(
            issues,
            "procedure_identity_retirement_retained_contract_mismatch",
            "$.retained_wrapper_evidence.contract_digest",
            "retained wrapper and public entry contract digests differ",
        )
    old_artifact_paths = {
        artifact.role: artifact.path
        for artifact in record.artifacts
        if artifact.side == "old"
    }
    cross_relation_mismatch = (
        record.callee.get("module") != record.retained_public_entry.get("module")
        or record.retained_wrapper_evidence.get("retained_wrapper")
        != record.retained_public_entry.get("workflow")
        or record.retained_wrapper_evidence.get("source_path") != old_artifact_paths.get("source")
        or record.retained_wrapper_evidence.get("inventory_path")
        != old_artifact_paths.get("typed_frontend_ast")
        or str(record.callee.get("identity", ""))
        not in str(record.retained_wrapper_evidence.get("reviewed_call_site", ""))
    )
    if cross_relation_mismatch:
        _issue(
            issues,
            "procedure_identity_retirement_substantive_evidence_mismatch",
            "$.retained_wrapper_evidence",
            "callee, retained wrapper, call site, and old source/inventory artifacts must agree",
        )
    public_entry = record.retained_public_entry.get("workflow")
    if any(row.key.owning_public_entry != public_entry for row in record.artifact_multiset):
        _issue(
            issues,
            "procedure_identity_retirement_artifact_public_entry_mismatch",
            "$.artifact_multiset",
            "every artifact contract must be owned by the retained public entry",
        )
    if not record.known_state_stores:
        _issue(
            issues,
            "procedure_identity_retirement_known_store_missing",
            "$.known_state_stores",
            "every known store must be enumerated",
        )
    retired_identities = {
        row.old_identity
        for row in record.identity_delta
        if row.old_disposition == "retired" and row.old_identity is not None
    }
    repository_root = Path(repo_root).resolve()
    seen_store_roots: set[Path] = set()
    count_fields = (
        "terminal_run_count",
        "nonterminal_run_count",
        "call_frame_count",
        "consumer_count",
        "checkpoint_index_count",
        "checkpoint_record_count",
        "retained_manifest_count",
        "identity_metadata_count",
        "scanned_file_count",
    )
    for index, store in enumerate(record.known_state_stores):
        path = f"$.known_state_stores[{index}]"
        if not store.root.strip() or not store.query_version.strip():
            _issue(
                issues,
                "procedure_identity_retirement_metadata_missing",
                path,
                "store root and query version must be nonempty",
            )
        if not _valid_timestamp(store.query_time):
            _issue(
                issues,
                "procedure_identity_retirement_timestamp_invalid",
                f"{path}.query_time",
                "query_time must be a timezone-aware ISO-8601 timestamp",
            )
        if not store.owner or not store.owner.strip():
            _issue(
                issues,
                "procedure_identity_retirement_known_store_unowned",
                f"{path}.owner",
                "known store requires a genuine named owner",
            )
        if (
            not store.attestation
            or not store.attestation.strip()
            or not store.attested_at
        ):
            _issue(
                issues,
                "procedure_identity_retirement_attestation_missing",
                f"{path}.attestation",
                "known store requires a timestamped owner attestation",
            )
        elif not _valid_timestamp(store.attested_at):
            _issue(
                issues,
                "procedure_identity_retirement_timestamp_invalid",
                f"{path}.attested_at",
                "attested_at must be a timezone-aware ISO-8601 timestamp",
            )
        if store.nonterminal_run_count > 0:
            _issue(
                issues,
                "procedure_identity_retirement_supported_state_present",
                f"{path}.nonterminal_run_count",
                "supported nonterminal state selects strict compatibility",
            )
        if store.call_frame_count > 0 or store.consumer_count > 0:
            _issue(
                issues,
                "procedure_identity_retirement_old_identity_consumer_present",
                path,
                "old call frames or identity-addressing consumers select strict compatibility",
            )
        if any(
            count < 0
            for count in (getattr(store, field) for field in count_fields)
        ):
            _issue(
                issues,
                "procedure_identity_retirement_store_count_invalid",
                path,
                "store counts must be non-negative",
            )
        if not _valid_sha256(store.normalized_scan_digest):
            _issue(
                issues,
                "procedure_identity_retirement_store_digest_invalid",
                f"{path}.normalized_scan_digest",
                "known-store digest must be sha256:<64 hexadecimal characters>",
            )
        relative_root = Path(store.root)
        if relative_root.is_absolute() or ".." in relative_root.parts:
            _issue(
                issues,
                "procedure_identity_retirement_known_store_unsafe_path",
                f"{path}.root",
                "known store root must be a safe repository-relative path",
            )
            continue
        candidate = repository_root / relative_root
        resolved_candidate = candidate.resolve(strict=False)
        if resolved_candidate != repository_root and repository_root not in resolved_candidate.parents:
            _issue(
                issues,
                "procedure_identity_retirement_known_store_unsafe_path",
                f"{path}.root",
                "known store root resolves outside repo_root",
            )
            continue
        if resolved_candidate in seen_store_roots:
            _issue(
                issues,
                "procedure_identity_retirement_known_store_duplicate",
                f"{path}.root",
                "known store roots must be unique after canonical resolution",
            )
            continue
        seen_store_roots.add(resolved_candidate)
        try:
            observed = scan_known_state_store(
                candidate,
                retired_identities=retired_identities,
                query_version=store.query_version,
            )
        except ValueError as exc:
            message = str(exc)
            code = message.split(":", 1)[0]
            if not code.startswith("procedure_identity_retirement_"):
                code = "procedure_identity_retirement_known_store_scan_failed"
            _issue(issues, code, f"{path}.root", message)
            continue
        if observed["normalized_scan_digest"] != store.normalized_scan_digest:
            _issue(
                issues,
                "procedure_identity_retirement_known_store_digest_mismatch",
                f"{path}.normalized_scan_digest",
                "declared store digest does not match a fresh normalized scan",
            )
        for field in count_fields:
            if observed[field] != getattr(store, field):
                _issue(
                    issues,
                    "procedure_identity_retirement_known_store_count_mismatch",
                    f"{path}.{field}",
                    f"declared {getattr(store, field)}, observed {observed[field]}",
                )
        if observed["nonterminal_run_count"] > 0:
            _issue(
                issues,
                "procedure_identity_retirement_supported_state_present",
                f"{path}.nonterminal_run_count",
                "fresh scan found supported nonterminal state",
            )
        if observed["call_frame_count"] > 0 or observed["consumer_count"] > 0:
            _issue(
                issues,
                "procedure_identity_retirement_old_identity_consumer_present",
                path,
                "fresh scan found an old call frame or identity-addressing consumer",
            )
    if record.external_store_absence != "not_asserted":
        _issue(
            issues,
            "procedure_identity_retirement_external_absence_asserted",
            "$.external_store_absence",
            "repository evidence cannot assert external-store absence",
        )
    if record.runtime_directives:
        _issue(
            issues,
            "procedure_identity_retirement_runtime_directive_present",
            "$.runtime_directives",
            "retirement evidence may not contain runtime directives",
        )
    _validate_artifacts(record, issues, repository_root)
    _validate_identity_delta(record, issues)
    _validate_contracts_and_order(record, issues)
    if not record.lineage_notes or any(
        not row["procedure_definition_note"].startswith("procedure definition at")
        or not row["call_site_note"].startswith("procedure call site at")
        for row in record.lineage_notes
    ):
        _issue(
            issues,
            "procedure_identity_retirement_lineage_evidence_missing",
            "$.lineage_notes",
            "lineage evidence requires definition and consuming call-site notes",
        )
    _validate_evidence_blocks(record, issues)
    unique = {
        (issue.code, issue.path, issue.message): issue
        for issue in issues
    }
    return RetirementValidationResult(
        issues=tuple(
            sorted(unique.values(), key=lambda issue: (issue.path, issue.code, issue.message))
        )
    )


_TERMINAL_STATUSES = frozenset(
    {"completed", "succeeded", "failed", "cancelled", "canceled", "aborted", "terminated"}
)
_IDENTITY_VALUE_FIELDS = frozenset(
    {
        "workflow_id",
        "workflow_name",
        "retained_workflow_id",
        "call_frame_id",
        "caller_call_frame_id",
        "parent_call_frame_id",
        "execution_frame_id",
        "call_step_id",
        "caller_step_id",
        "step_id",
        "current_step",
        "completed_step",
        "completed_steps",
        "node_id",
        "executable_node_id",
        "program_point_id",
        "checkpoint_id",
        "checkpoint_ids",
        "state_allocation_id",
        "origin_key",
        "source_map_origin",
        "source_map_origin_key",
        "presentation_key",
    }
)
_IDENTITY_MAPPING_FIELDS = frozenset(
    {
        "steps",
        "completed_steps",
        "call_frames",
        "step_visits",
        "checkpoints",
        "program_points",
        "workflows",
        "presentation_keys",
        "state_allocations",
        "source_map_origins",
        "execution_frames",
    }
)


def _scan_error(code: str, message: str) -> ValueError:
    return ValueError(f"{code}: {message}")


def _safe_store_files(store_root: Path) -> tuple[Path, ...]:
    if store_root.is_symlink():
        raise _scan_error(
            "procedure_identity_retirement_store_symlink_forbidden",
            f"store root is a symlink: {store_root}",
        )
    if not store_root.exists() or not store_root.is_dir():
        raise _scan_error(
            "procedure_identity_retirement_known_store_unavailable",
            f"store root is missing or not a directory: {store_root}",
        )
    resolved_root = store_root.resolve(strict=True)
    supported: list[Path] = []

    def onerror(error: OSError) -> None:
        raise _scan_error(
            "procedure_identity_retirement_known_store_unreadable",
            f"could not enumerate store: {error}",
        )

    for current, directories, filenames in os.walk(store_root, followlinks=False, onerror=onerror):
        current_path = Path(current)
        for name in tuple(directories) + tuple(filenames):
            candidate = current_path / name
            try:
                if candidate.is_symlink():
                    raise _scan_error(
                        "procedure_identity_retirement_store_symlink_forbidden",
                        f"symlink encountered in store: {candidate}",
                    )
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise _scan_error(
                    "procedure_identity_retirement_known_store_unreadable",
                    f"could not resolve store entry {candidate}: {exc}",
                ) from exc
            if resolved != resolved_root and resolved_root not in resolved.parents:
                raise _scan_error(
                    "procedure_identity_retirement_known_store_unsafe_path",
                    f"store entry escapes root: {candidate}",
                )
        for filename in filenames:
            candidate = current_path / filename
            if candidate.suffix.lower() in {".json", ".jsonl"}:
                supported.append(candidate)
    return tuple(sorted(supported, key=lambda path: path.relative_to(store_root).as_posix()))


def _read_stable_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            content = handle.read()
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise _scan_error(
            "procedure_identity_retirement_known_store_unreadable",
            f"could not read {path}: {exc}",
        ) from exc
    signature_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    signature_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if signature_before != signature_after or len(content) != before.st_size:
        raise _scan_error(
            "procedure_identity_retirement_known_store_scan_race",
            f"store file changed while scanning: {path}",
        )
    return content


def _match_row(
    *,
    identity: str,
    field: str,
    relative_path: str,
    pointer: str,
) -> dict[str, str]:
    location = relative_path + (pointer if pointer.startswith("#") else f"{pointer or '/'}")
    return {
        "identity": identity,
        "field": field,
        "key": field,
        "path": relative_path,
        "pointer": pointer or "/",
        "location": location,
    }


def _identity_matches(
    value: Any,
    *,
    retired: frozenset[str],
    relative_path: str,
    pointer: str = "",
    field_name: str | None = None,
) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    if isinstance(value, dict):
        if field_name in _IDENTITY_MAPPING_FIELDS:
            for identity in sorted(value):
                if identity in retired:
                    escaped = identity.replace("~", "~0").replace("/", "~1")
                    matches.append(
                        _match_row(
                            identity=identity,
                            field=f"{field_name}_key",
                            relative_path=relative_path,
                            pointer=f"{pointer}/{escaped}",
                        )
                    )
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            matches.extend(
                _identity_matches(
                    value[key],
                    retired=retired,
                    relative_path=relative_path,
                    pointer=f"{pointer}/{escaped}",
                    field_name=key,
                )
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(
                _identity_matches(
                    item,
                    retired=retired,
                    relative_path=relative_path,
                    pointer=f"{pointer}/{index}",
                    field_name=field_name,
                )
            )
    elif field_name in _IDENTITY_VALUE_FIELDS and isinstance(value, str) and value in retired:
        matches.append(
            _match_row(
                identity=value,
                field=field_name,
                relative_path=relative_path,
                pointer=pointer,
            )
        )
    return matches


def _load_store_objects(path: Path, content: bytes, relative: str) -> tuple[tuple[str, dict[str, Any]], ...]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _scan_error(
            "procedure_identity_retirement_store_content_invalid",
            f"supported store file is not UTF-8: {relative}",
        ) from exc
    if path.suffix.lower() == ".jsonl":
        rows: list[tuple[str, dict[str, Any]]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, object_pairs_hook=_json_object_without_duplicates)
            except (json.JSONDecodeError, ValueError) as exc:
                raise _scan_error(
                    "procedure_identity_retirement_store_content_invalid",
                    f"malformed JSONL row {relative}#{line_number}: {exc}",
                ) from exc
            if not isinstance(row, dict):
                raise _scan_error(
                    "procedure_identity_retirement_store_content_invalid",
                    f"JSONL row must be an object: {relative}#{line_number}",
                )
            rows.append((f"{relative}#{line_number}", row))
        return tuple(rows)
    try:
        payload = json.loads(text, object_pairs_hook=_json_object_without_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise _scan_error(
            "procedure_identity_retirement_store_content_invalid",
            f"malformed JSON object {relative}: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise _scan_error(
            "procedure_identity_retirement_store_content_invalid",
            f"supported JSON file must contain an object: {relative}",
        )
    return ((relative, payload),)


def scan_known_state_store(
    root: str | Path,
    *,
    retired_identities: Iterable[str],
    query_version: str,
) -> dict[str, Any]:
    """Return deterministic, fail-closed facts about one named state store."""

    if query_version != STORE_QUERY_VERSION:
        raise _scan_error(
            "procedure_identity_retirement_query_version_unsupported",
            f"unsupported query version: {query_version!r}",
        )
    store_root = Path(root)
    retired_values = tuple(retired_identities)
    if any(not isinstance(identity, str) or not identity for identity in retired_values):
        raise ValueError("retired_identities must contain only non-empty strings")
    retired = frozenset(retired_values)
    files = _safe_store_files(store_root)

    counts = {
        "terminal_run_count": 0,
        "nonterminal_run_count": 0,
        "checkpoint_index_count": 0,
        "checkpoint_record_count": 0,
        "retained_manifest_count": 0,
        "identity_metadata_count": 0,
        "scanned_file_count": len(files),
    }
    raw_matches: list[dict[str, str]] = []
    scanned_files: list[dict[str, str]] = []
    for path in files:
        relative_path = path.relative_to(store_root).as_posix()
        content = _read_stable_bytes(path)
        scanned_files.append(
            {"path": relative_path, "sha256": f"sha256:{sha256(content).hexdigest()}"}
        )
        lower_parts = tuple(part.lower() for part in path.relative_to(store_root).parts)
        filename = path.name.lower()
        if "checkpoints" in lower_parts:
            if filename == "index.json" or "index" in filename:
                counts["checkpoint_index_count"] += 1
            else:
                counts["checkpoint_record_count"] += 1
        if "manifest" in filename or "manifests" in lower_parts:
            counts["retained_manifest_count"] += 1
        if "metadata" in lower_parts or "identity" in filename:
            counts["identity_metadata_count"] += 1

        for object_location, payload in _load_store_objects(path, content, relative_path):
            relative_parts = path.relative_to(store_root).parts
            if filename == "state.json" and len(relative_parts) <= 2:
                status = payload.get("status")
                if isinstance(status, str) and status.lower() in _TERMINAL_STATUSES:
                    counts["terminal_run_count"] += 1
                else:
                    counts["nonterminal_run_count"] += 1
            raw_matches.extend(
                _identity_matches(
                    payload,
                    retired=retired,
                    relative_path=object_location,
                )
            )

        for part_index, part in enumerate(path.relative_to(store_root).parts):
            candidates = {unquote(part), unquote(Path(part).stem)}
            for identity in sorted(retired.intersection(candidates)):
                raw_matches.append(
                    _match_row(
                        identity=identity,
                        field="path_component",
                        relative_path=relative_path,
                        pointer=f"#path/{part_index}",
                    )
                )

    deduplicated = {
        (row["location"], row["identity"], row["field"]): row
        for row in raw_matches
    }
    matches = sorted(
        deduplicated.values(),
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
    )
    call_frame_count = sum(
        1
        for row in matches
        if "call_frame" in row["field"]
        or "execution_frame" in row["field"]
        or (row["field"] == "path_component" and "/call_frames/" in f"/{row['path']}")
    )
    normalized = {
        "query_version": query_version,
        "retired_identities": sorted(retired),
        **counts,
        "call_frame_count": call_frame_count,
        "consumer_count": len(matches),
        "matches": matches,
        "scanned_files": scanned_files,
    }
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return {
        "root": str(store_root),
        **normalized,
        "matches": tuple(dict(row) for row in matches),
        "scanned_files": tuple(dict(row) for row in scanned_files),
        "normalized_scan_digest": f"sha256:{sha256(encoded).hexdigest()}",
    }
