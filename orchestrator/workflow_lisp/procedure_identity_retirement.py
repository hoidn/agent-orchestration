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
import stat
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote


SCHEMA = "workflow_lisp_procedure_identity_retirement.v1"
ROOT_CHECKSUM_CHARACTERIZATION_SCHEMA = (
    "workflow_lisp_root_checksum_characterization.v1"
)
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
        "build_manifest",
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
    store_terminal_run_count: int
    store_nonterminal_run_count: int
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
class RetiredIdentityQueryEvidence:
    evidence_path: str
    evidence_sha256: str
    query_version: str
    query_list_sha256: str
    identity_count: int
    identities_by_domain_sha256: str
    baseline_path: str
    baseline_sha256: str
    old_source_path: str
    retained_old_source_path: str
    old_source_sha256: str


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
    retired_identity_query_evidence: RetiredIdentityQueryEvidence
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


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is forbidden")


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
            "inventory_sha256",
            "source_path",
            "reviewed_call_site",
            "retained_wrapper",
            "contract_digest",
        },
        required={
            "inventory_path",
            "inventory_sha256",
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
                "store_terminal_run_count",
                "store_nonterminal_run_count",
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
                "store_terminal_run_count",
                "store_nonterminal_run_count",
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
                "store_terminal_run_count",
                "store_nonterminal_run_count",
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
                store_terminal_run_count=counts["store_terminal_run_count"],
                store_nonterminal_run_count=counts["store_nonterminal_run_count"],
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


def _parse_retired_identity_query_evidence(value: Any) -> RetiredIdentityQueryEvidence:
    path = "$.retired_identity_query_evidence"
    fields = {
        "evidence_path",
        "evidence_sha256",
        "query_version",
        "query_list_sha256",
        "identity_count",
        "identities_by_domain_sha256",
        "baseline_path",
        "baseline_sha256",
        "old_source_path",
        "retained_old_source_path",
        "old_source_sha256",
    }
    row = _object(value, path, allowed=fields, required=fields)
    for field in fields - {"identity_count"}:
        _string(row[field], f"{path}.{field}")
    identity_count = _integer(row["identity_count"], f"{path}.identity_count")
    return RetiredIdentityQueryEvidence(
        evidence_path=row["evidence_path"],
        evidence_sha256=row["evidence_sha256"],
        query_version=row["query_version"],
        query_list_sha256=row["query_list_sha256"],
        identity_count=identity_count,
        identities_by_domain_sha256=row["identities_by_domain_sha256"],
        baseline_path=row["baseline_path"],
        baseline_sha256=row["baseline_sha256"],
        old_source_path=row["old_source_path"],
        retained_old_source_path=row["retained_old_source_path"],
        old_source_sha256=row["old_source_sha256"],
    )


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
    fields = {
        "executable_node",
        "source_map_origin",
        "procedure_definition_note",
        "call_site_note",
    }
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
    root_common_fields = {
        "evidence_mode",
        "command",
        "default_resume",
        "observability_overrides",
        "cli_overrides",
        "exit_status",
        "executor_constructed",
        "provider_executed",
        "command_executed",
    }
    actual_tree_fields = root_common_fields | {
        "before_tree_digest",
        "after_tree_digest",
    }
    generic_characterization_fields = root_common_fields | {
        "characterization_path",
        "characterization_sha256",
        "projection_sha256",
        "tree_immutability",
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
        raw_root = _object(
            checksum["root"],
            "$.checksum_evidence.root",
            allowed=actual_tree_fields | generic_characterization_fields,
            required=root_common_fields,
        )
        evidence_mode = _string(
            raw_root["evidence_mode"],
            "$.checksum_evidence.root.evidence_mode",
        )
        if evidence_mode not in {"actual_tree", "generic_characterization"}:
            raise ValueError(
                "$.checksum_evidence.root.evidence_mode must be actual_tree or "
                "generic_characterization"
            )
        root_fields = (
            actual_tree_fields
            if evidence_mode == "actual_tree"
            else generic_characterization_fields
        )
        root = _object(
            raw_root,
            "$.checksum_evidence.root",
            allowed=root_fields,
            required=root_fields,
        )
        _string(root["command"], "$.checksum_evidence.root.command")
        _integer(root["exit_status"], "$.checksum_evidence.root.exit_status")
        if evidence_mode == "actual_tree":
            _string(root["before_tree_digest"], "$.checksum_evidence.root.before_tree_digest")
            _string(root["after_tree_digest"], "$.checksum_evidence.root.after_tree_digest")
        else:
            for key in (
                "characterization_path",
                "characterization_sha256",
                "projection_sha256",
                "tree_immutability",
            ):
                _string(root[key], f"$.checksum_evidence.root.{key}")
        for key in root_common_fields - {"evidence_mode", "command", "exit_status"}:
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
        "retired_identity_query_evidence",
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
        retired_identity_query_evidence=_parse_retired_identity_query_evidence(
            payload["retired_identity_query_evidence"]
        ),
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
        if row.new_disposition == "preserved" and not (
            row.new_identity is not None
            and row.old_identity == row.new_identity
            and row.old_disposition == "preserved"
        ):
            _issue(
                issues,
                "procedure_identity_retirement_identity_row_invalid",
                path,
                "new preserved identity requires the same old identity and preserved dispositions",
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

    old_table = {
        (row.identity_kind, row.old_identity): row.old_disposition
        for row in record.identity_delta
        if row.old_identity is not None
    }
    new_table = {
        (row.identity_kind, row.new_identity): row.new_disposition
        for row in record.identity_delta
        if row.new_identity is not None
    }
    recreated = sorted(
        f"{kind}:{identity}"
        for (kind, identity), disposition in old_table.items()
        if disposition == "retired" and new_table.get((kind, identity)) == "new"
    )
    if recreated:
        _issue(
            issues,
            "procedure_identity_retirement_identity_recreated",
            "$.identity_delta",
            "retired identities may not be recreated as new: " + ", ".join(recreated),
        )


def _load_content_addressed_file(
    root: Path,
    *,
    raw_path: str,
    declared_digest: str,
) -> tuple[bytes | None, str | None, str]:
    try:
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None, "procedure_identity_retirement_artifact_path_outside_repository", "path must be repository-relative"
        if _path_has_symlink_component(root, relative):
            return None, "procedure_identity_retirement_artifact_symlink_forbidden", "path must not contain symlink components"
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            return None, "procedure_identity_retirement_artifact_path_outside_repository", "path resolves outside repo_root"
        if not candidate.is_file():
            return None, "procedure_identity_retirement_artifact_missing", f"file does not exist: {raw_path}"
    except (OSError, RuntimeError, ValueError) as exc:
        return (
            None,
            "procedure_identity_retirement_artifact_path_invalid",
            f"path cannot be inspected safely: {exc}",
        )
    try:
        content = _read_stable_relative_bytes(root, relative)
    except ValueError as exc:
        return None, "procedure_identity_retirement_artifact_read_failed", str(exc)
    actual = f"sha256:{sha256(content).hexdigest()}"
    if actual != declared_digest:
        return None, "procedure_identity_retirement_artifact_digest_mismatch", f"declared {declared_digest}, observed {actual}"
    return content, None, ""


def _read_stable_relative_bytes(root: Path, relative: Path) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    if nofollow is None or directory is None or nonblock is None:
        raise ValueError(
            "descriptor-relative content-addressed reads require "
            "O_NOFOLLOW, O_DIRECTORY, and O_NONBLOCK"
        )

    directory_flags = os.O_RDONLY | directory | nofollow | close_on_exec
    file_flags = os.O_RDONLY | nofollow | nonblock | close_on_exec
    directory_descriptor: int | None = None
    file_descriptor: int | None = None
    try:
        directory_descriptor = os.open(root.resolve(strict=True), directory_flags)
        for component in relative.parts[:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        file_descriptor = os.open(
            relative.parts[-1],
            file_flags,
            dir_fd=directory_descriptor,
        )
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("content-addressed path must name a regular file")
            content = handle.read()
            after = os.fstat(handle.fileno())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"could not read content-addressed file safely: {relative}: {exc}"
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)

    signature_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    signature_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if signature_before != signature_after or len(content) != before.st_size:
        raise ValueError(
            f"content-addressed file changed while reading: {relative}"
        )
    return content


def _is_safe_repository_relative_metadata_path(raw_path: str) -> bool:
    try:
        relative = Path(raw_path)
        return (
            bool(raw_path)
            and bool(relative.parts)
            and "\x00" not in raw_path
            and not relative.is_absolute()
            and ".." not in relative.parts
        )
    except (OSError, RuntimeError, ValueError):
        return False


def _validate_artifacts(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    repo_root: Path,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    root = repo_root.resolve()
    payloads: dict[tuple[str, str], Mapping[str, Any]] = {}
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
        expected_name = "source.orc" if artifact.role == "source" else f"{artifact.role}.json"
        if relative.name != expected_name:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_role_path_mismatch",
                f"{path}.path",
                f"{artifact.role} evidence must use dedicated file {expected_name}",
            )
        content, error_code, error_message = _load_content_addressed_file(
            root,
            raw_path=artifact.path,
            declared_digest=artifact.sha256,
        )
        if error_code is not None or content is None:
            _issue(
                issues,
                error_code or "procedure_identity_retirement_artifact_read_failed",
                f"{path}.sha256" if error_code == "procedure_identity_retirement_artifact_digest_mismatch" else f"{path}.path",
                error_message,
            )
            continue
        if artifact.role == "source":
            payloads[(artifact.side, artifact.role)] = MappingProxyType({})
        else:
            try:
                payload = json.loads(
                    content,
                    object_pairs_hook=_json_object_without_duplicates,
                )
            except (json.JSONDecodeError, ValueError):
                payload = None
            if not isinstance(payload, dict):
                _issue(
                    issues,
                    "procedure_identity_retirement_artifact_content_invalid",
                    f"{path}.path",
                    "content-addressed production JSON must be an object",
                )
                continue
            payloads[(artifact.side, artifact.role)] = payload
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
    return payloads


def _public_contract_projection(executable: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for surface in ("outputs", "artifacts", "private_artifacts"):
        contracts = executable.get(surface)
        for name, raw in sorted(contracts.items()) if isinstance(contracts, Mapping) else ():
            if not isinstance(raw, Mapping):
                continue
            definition = raw.get("definition")
            stable_definition = {}
            if isinstance(definition, Mapping):
                stable_definition = {
                    key: definition[key]
                    for key in ("kind", "type", "allowed", "under", "must_exist_target")
                    if key in definition
                }
            rows.append(
                {
                    "surface": surface,
                    "name": name,
                    "kind": raw.get("kind"),
                    "value_type": raw.get("value_type"),
                    "definition": stable_definition,
                }
            )
    return rows


def _projection_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _canonical_json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _add_identity(
    identities: dict[str, set[str]],
    identity_kind: str,
    value: Any,
) -> None:
    if isinstance(value, str):
        identities[identity_kind].add(value)


def _collect_source_map_workflow_origins(
    identities: dict[str, set[str]],
    workflow_map: Mapping[str, Any],
) -> None:
    for field in (
        "command_boundaries",
        "core_nodes",
        "executable_nodes",
        "generated_path_allocations",
        "generated_semantic_effects",
        "validation_subjects",
    ):
        for row in _mapping_rows(workflow_map.get(field)):
            _add_identity(identities, "source_map_origin", row.get("origin_key"))
    for field in (
        "contract_fields",
        "generated_inputs",
        "generated_internal_inputs",
        "generated_outputs",
        "generated_paths",
        "step_ids",
    ):
        rows = workflow_map.get(field)
        for row in rows.values() if isinstance(rows, Mapping) else ():
            if isinstance(row, Mapping):
                _add_identity(
                    identities,
                    "source_map_origin",
                    row.get("origin_key"),
                )
    workflow_origin = workflow_map.get("workflow_origin")
    if isinstance(workflow_origin, Mapping):
        _add_identity(
            identities,
            "source_map_origin",
            workflow_origin.get("origin_key"),
        )


def _mapping_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(row for row in value if isinstance(row, Mapping))


def _collect_call_frame_identity(
    identities: dict[str, set[str]],
    row: Mapping[str, Any],
) -> None:
    step_id = row.get("step_id")
    if row.get("kind") == "call_boundary" and isinstance(step_id, str):
        identities["call_frame"].add(f"{step_id}::visit::1")


def _collect_production_identity_carriers(
    payloads: Mapping[tuple[str, str], Mapping[str, Any]],
    side: str,
) -> dict[str, set[str]]:
    identities = {kind: set() for kind in REQUIRED_IDENTITY_DOMAINS}
    typed = payloads[(side, "typed_frontend_ast")]
    semantic = payloads[(side, "semantic_ir")]
    executable = payloads[(side, "executable_ir")]
    runtime = payloads[(side, "runtime_plan")]
    points_payload = payloads[(side, "lexical_checkpoint_points")]
    source_map = payloads[(side, "source_map")]

    modules = typed.get("modules")
    for module in modules.values() if isinstance(modules, Mapping) else ():
        workflows = module.get("typed_workflows") if isinstance(module, Mapping) else None
        for workflow in _mapping_rows(workflows):
            definition = workflow.get("definition")
            if isinstance(definition, Mapping):
                _add_identity(identities, "workflow", definition.get("name"))
    _add_identity(identities, "workflow", executable.get("name"))

    semantic_workflows = semantic.get("workflows")
    if isinstance(semantic_workflows, Mapping):
        for workflow_key, workflow_payload in semantic_workflows.items():
            _add_identity(identities, "workflow", workflow_key)
            if not isinstance(workflow_payload, Mapping):
                continue
            _add_identity(
                identities,
                "workflow",
                workflow_payload.get("workflow_name"),
            )
            bridge = workflow_payload.get("executable_bridge")
            if not isinstance(bridge, Mapping):
                continue
            bridge_node_ids = bridge.get("node_ids")
            for node_id in bridge_node_ids if isinstance(bridge_node_ids, list) else ():
                _add_identity(identities, "executable_node", node_id)
            bridge_presentation_keys = bridge.get("presentation_keys")
            for presentation_key in (
                bridge_presentation_keys
                if isinstance(bridge_presentation_keys, list)
                else ()
            ):
                _add_identity(identities, "presentation_key", presentation_key)

    source_map_workflows = source_map.get("workflows")
    if isinstance(source_map_workflows, Mapping):
        for workflow_key, workflow_map in source_map_workflows.items():
            _add_identity(identities, "workflow", workflow_key)
            if isinstance(workflow_map, Mapping):
                _add_identity(
                    identities,
                    "workflow",
                    workflow_map.get("workflow_name"),
                )
                selected_entry = workflow_map.get("selected_entry_workflow")
                if isinstance(selected_entry, str):
                    _add_identity(identities, "workflow", selected_entry)
    _add_identity(identities, "workflow", runtime.get("workflow_name"))
    _add_identity(identities, "workflow", points_payload.get("workflow_name"))

    executable_nodes = executable.get("nodes")
    if isinstance(executable_nodes, Mapping):
        for node_key, node in executable_nodes.items():
            _add_identity(identities, "executable_node", node_key)
            if not isinstance(node, Mapping):
                continue
            _add_identity(identities, "executable_node", node.get("node_id"))
            _add_identity(identities, "step", node.get("step_id"))
            _add_identity(identities, "presentation_key", node.get("presentation_name"))
            _collect_call_frame_identity(identities, node)

    runtime_nodes = runtime.get("nodes")
    if isinstance(runtime_nodes, Mapping):
        for node_key, node in runtime_nodes.items():
            _add_identity(identities, "executable_node", node_key)
            if not isinstance(node, Mapping):
                continue
            _add_identity(identities, "executable_node", node.get("node_id"))
            _add_identity(identities, "step", node.get("step_id"))
            _add_identity(identities, "presentation_key", node.get("presentation_key"))
            _collect_call_frame_identity(identities, node)

    for checkpoint in _mapping_rows(runtime.get("resume_checkpoints")):
        _add_identity(identities, "executable_node", checkpoint.get("node_id"))
        _add_identity(identities, "step", checkpoint.get("step_id"))
        _add_identity(
            identities,
            "presentation_key",
            checkpoint.get("presentation_key"),
        )

    for point in _mapping_rows(runtime.get("lexical_checkpoint_points")):
        _add_identity(identities, "executable_node", point.get("node_id"))
        _add_identity(identities, "step", point.get("step_id"))
        _add_identity(identities, "presentation_key", point.get("presentation_key"))
        _add_identity(identities, "program_point", point.get("program_point_id"))
        _add_identity(identities, "checkpoint", point.get("checkpoint_id"))
        _add_identity(identities, "source_map_origin", point.get("origin_key"))
        details = point.get("details")
        if isinstance(details, Mapping):
            storage = details.get("storage")
            if isinstance(storage, Mapping):
                _add_identity(
                    identities,
                    "state_allocation",
                    storage.get("allocation_id"),
                )

    for point in _mapping_rows(points_payload.get("points")):
        _add_identity(identities, "program_point", point.get("program_point_id"))
        _add_identity(identities, "checkpoint", point.get("checkpoint_id"))
        executable_identity = point.get("executable_identity")
        if isinstance(executable_identity, Mapping):
            _add_identity(identities, "step", executable_identity.get("step_id"))
            _add_identity(
                identities,
                "presentation_key",
                executable_identity.get("presentation_key"),
            )
        storage = point.get("storage")
        if isinstance(storage, Mapping):
            _add_identity(
                identities,
                "state_allocation",
                storage.get("allocation_id"),
            )
        source_lineage = point.get("source_lineage")
        if isinstance(source_lineage, Mapping):
            _add_identity(
                identities,
                "source_map_origin",
                source_lineage.get("origin_key"),
            )

    for workflow_map in (
        source_map_workflows.values()
        if isinstance(source_map_workflows, Mapping)
        else ()
    ):
        if not isinstance(workflow_map, Mapping):
            continue
        _collect_source_map_workflow_origins(identities, workflow_map)
        for node in _mapping_rows(workflow_map.get("executable_nodes")):
            _add_identity(identities, "executable_node", node.get("node_id"))
            _add_identity(identities, "step", node.get("step_id"))
            _add_identity(
                identities,
                "presentation_key",
                node.get("presentation_name"),
            )
            _collect_call_frame_identity(identities, node)
        for allocation in _mapping_rows(workflow_map.get("generated_path_allocations")):
            _add_identity(
                identities,
                "state_allocation",
                allocation.get("allocation_id"),
            )
    return identities


def _collect_production_leak_carriers(
    payloads: Mapping[tuple[str, str], Mapping[str, Any]],
    side: str,
) -> dict[str, set[str]]:
    identities = {
        kind: set(values)
        for kind, values in _collect_production_identity_carriers(
            payloads,
            side,
        ).items()
    }
    semantic = payloads[(side, "semantic_ir")]
    executable = payloads[(side, "executable_ir")]
    runtime = payloads[(side, "runtime_plan")]
    points_payload = payloads[(side, "lexical_checkpoint_points")]

    for point in _mapping_rows(points_payload.get("points")):
        executable_identity = point.get("executable_identity")
        if isinstance(executable_identity, Mapping):
            _add_identity(
                identities,
                "executable_node",
                executable_identity.get("node_id"),
            )

    for field in ("body_region", "finalization_region"):
        values = executable.get(field)
        for node_id in values if isinstance(values, list) else ():
            _add_identity(identities, "executable_node", node_id)
    _add_identity(
        identities,
        "executable_node",
        executable.get("finalization_entry_node_id"),
    )

    ordered_node_ids = runtime.get("ordered_node_ids")
    for node_id in ordered_node_ids if isinstance(ordered_node_ids, list) else ():
        _add_identity(identities, "executable_node", node_id)

    semantic_workflows = semantic.get("workflows")
    for workflow in (
        semantic_workflows.values()
        if isinstance(semantic_workflows, Mapping)
        else ()
    ):
        if not isinstance(workflow, Mapping):
            continue
        statements = workflow.get("statements")
        for statement in (
            statements.values() if isinstance(statements, Mapping) else ()
        ):
            if not isinstance(statement, Mapping):
                continue
            node_ids = statement.get("executable_node_ids")
            for node_id in node_ids if isinstance(node_ids, list) else ():
                _add_identity(identities, "executable_node", node_id)
            presentation_keys = statement.get("presentation_keys")
            for presentation_key in (
                presentation_keys if isinstance(presentation_keys, list) else ()
            ):
                _add_identity(
                    identities,
                    "presentation_key",
                    presentation_key,
                )
            _add_identity(identities, "step", statement.get("step_id"))

    semantic_source_map = semantic.get("source_map")
    for entry in (
        semantic_source_map.values()
        if isinstance(semantic_source_map, Mapping)
        else ()
    ):
        if isinstance(entry, Mapping):
            _add_identity(
                identities,
                "source_map_origin",
                entry.get("origin_key"),
            )
    return identities


def _validate_retired_identity_query_evidence(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    repo_root: Path,
) -> dict[str, set[str]] | None:
    binding = record.retired_identity_query_evidence
    binding_path = "$.retired_identity_query_evidence"
    content, error_code, error_message = _load_content_addressed_file(
        repo_root.resolve(),
        raw_path=binding.evidence_path,
        declared_digest=binding.evidence_sha256,
    )
    if content is None:
        if error_code in {
            "procedure_identity_retirement_artifact_path_outside_repository",
            "procedure_identity_retirement_artifact_path_invalid",
            "procedure_identity_retirement_artifact_symlink_forbidden",
        }:
            code = "procedure_identity_retirement_query_evidence_path_invalid"
            path = f"{binding_path}.evidence_path"
        elif error_code in {
            "procedure_identity_retirement_artifact_missing",
            "procedure_identity_retirement_artifact_read_failed",
        }:
            code = "procedure_identity_retirement_query_evidence_unavailable"
            path = f"{binding_path}.evidence_path"
        elif error_code == "procedure_identity_retirement_artifact_digest_mismatch":
            code = "procedure_identity_retirement_query_evidence_digest_mismatch"
            path = f"{binding_path}.evidence_sha256"
        else:
            code = "procedure_identity_retirement_query_evidence_unavailable"
            path = f"{binding_path}.evidence_path"
        _issue(issues, code, path, error_message)
        return None
    try:
        evidence = json.loads(
            content,
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        _issue(
            issues,
            "procedure_identity_retirement_query_evidence_content_invalid",
            f"{binding_path}.evidence_path",
            f"pre-edit query evidence must be duplicate-free JSON: {exc}",
        )
        return None
    try:
        _reject_forbidden_runtime_keys(evidence)
    except ValueError as exc:
        _issue(
            issues,
            "procedure_identity_retirement_query_evidence_content_invalid",
            f"{binding_path}.evidence_path",
            f"pre-edit query evidence contains forbidden runtime authority: {exc}",
        )
        return None
    allowed_evidence_fields = {
        "schema",
        "capture_commit",
        "external_store_absence",
        "fact_class",
        "isolation_facts",
        "old_identity_query",
        "root_scope",
        "scans",
    }
    if (
        not isinstance(evidence, Mapping)
        or set(evidence) - allowed_evidence_fields
        or not isinstance(evidence.get("schema"), str)
        or not isinstance(evidence.get("old_identity_query"), Mapping)
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_evidence_content_invalid",
            f"{binding_path}.evidence_path",
            "pre-edit query evidence must use the closed generic scan envelope and contain schema plus old_identity_query",
        )
        return None

    query = evidence["old_identity_query"]
    allowed_query_fields = {
        "baseline_projection_matches_unchanged_source",
        "baseline_repo_relative_path",
        "baseline_sha256",
        "derivation_method",
        "derivation_method_version",
        "identities",
        "identities_by_domain",
        "identity_count",
        "query_list_digest_encoding",
        "query_list_sha256",
        "query_version",
        "source_boundary_validation",
        "source_repo_relative_path",
        "source_sha256",
        "temporary_candidate_repo_relative_path",
    }
    required_query_fields = {
        "query_version",
        "query_list_sha256",
        "identities",
        "identity_count",
        "identities_by_domain",
        "baseline_repo_relative_path",
        "baseline_sha256",
        "source_repo_relative_path",
        "source_sha256",
    }
    if set(query) - allowed_query_fields or not required_query_fields.issubset(query):
        _issue(
            issues,
            "procedure_identity_retirement_query_evidence_content_invalid",
            f"{binding_path}.evidence_path.old_identity_query",
            "old_identity_query must use the closed generic query field set and contain all replay fields",
        )
        return None

    query_version = query.get("query_version")
    if (
        not isinstance(query_version, str)
        or query_version != STORE_QUERY_VERSION
        or query_version != binding.query_version
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_version_mismatch",
            f"{binding_path}.query_version",
            "query version must match the supported version and retained evidence",
        )

    raw_identities = query.get("identities")
    raw_list_valid = (
        isinstance(raw_identities, list)
        and all(isinstance(identity, str) for identity in raw_identities)
        and raw_identities == sorted(raw_identities)
        and len(raw_identities) == len(set(raw_identities))
    )
    if not raw_list_valid:
        _issue(
            issues,
            "procedure_identity_retirement_query_list_invalid",
            f"{binding_path}.evidence_path.old_identity_query.identities",
            "retired identities must be a sorted duplicate-free string array",
        )
        raw_identities = []
    canonical_list_digest = _canonical_json_digest(raw_identities)
    if (
        query.get("query_list_sha256") != canonical_list_digest
        or binding.query_list_sha256 != canonical_list_digest
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_list_digest_mismatch",
            f"{binding_path}.query_list_sha256",
            "canonical retired-identity list digest does not match all bindings",
        )
    if (
        isinstance(query.get("identity_count"), bool)
        or not isinstance(query.get("identity_count"), int)
        or query.get("identity_count") != len(raw_identities)
        or binding.identity_count != len(raw_identities)
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_identity_count_mismatch",
            f"{binding_path}.identity_count",
            "retired-identity count does not match the canonical raw list",
        )

    raw_domains = query.get("identities_by_domain")
    domain_map: dict[str, set[str]] = {
        domain: set() for domain in REQUIRED_IDENTITY_DOMAINS
    }
    domain_map_valid = isinstance(raw_domains, Mapping) and set(raw_domains) == set(
        REQUIRED_IDENTITY_DOMAINS
    )
    if not domain_map_valid:
        _issue(
            issues,
            "procedure_identity_retirement_query_domain_map_invalid",
            f"{binding_path}.evidence_path.old_identity_query.identities_by_domain",
            "domain map must contain exactly the required identity domains",
        )
    else:
        for domain in sorted(REQUIRED_IDENTITY_DOMAINS):
            identities = raw_domains[domain]
            path = (
                f"{binding_path}.evidence_path.old_identity_query."
                f"identities_by_domain.{domain}"
            )
            if not isinstance(identities, list) or not all(
                isinstance(identity, str) for identity in identities
            ):
                _issue(
                    issues,
                    "procedure_identity_retirement_query_domain_map_invalid",
                    path,
                    "each identity domain must be a string array",
                )
                domain_map_valid = False
                continue
            if len(identities) != len(set(identities)):
                _issue(
                    issues,
                    "procedure_identity_retirement_query_domain_duplicate",
                    path,
                    "an identity may occur at most once within one domain",
                )
                domain_map_valid = False
                continue
            if identities != sorted(identities):
                _issue(
                    issues,
                    "procedure_identity_retirement_query_domain_map_invalid",
                    path,
                    "each identity domain must be sorted",
                )
                domain_map_valid = False
                continue
            domain_map[domain] = set(identities)
    if isinstance(raw_domains, Mapping):
        canonical_domain_digest = _canonical_json_digest(raw_domains)
        if binding.identities_by_domain_sha256 != canonical_domain_digest:
            _issue(
                issues,
                "procedure_identity_retirement_query_domain_map_digest_mismatch",
                f"{binding_path}.identities_by_domain_sha256",
                "exact domain-membership map digest does not match the record binding",
            )
    if domain_map_valid:
        flattened = sorted(set().union(*domain_map.values()))
        if flattened != raw_identities:
            _issue(
                issues,
                "procedure_identity_retirement_query_domain_membership_mismatch",
                f"{binding_path}.evidence_path.old_identity_query.identities_by_domain",
                "sorted unique domain flattening must equal the canonical raw list",
            )

    query_baseline_path = query.get("baseline_repo_relative_path")
    query_baseline_digest = query.get("baseline_sha256")
    if (
        not isinstance(query_baseline_path, str)
        or query_baseline_path != binding.baseline_path
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_baseline_path_mismatch",
            f"{binding_path}.baseline_path",
            "retained query path does not match the record binding",
        )
    elif not isinstance(query_baseline_digest, str):
        _issue(
            issues,
            "procedure_identity_retirement_query_baseline_digest_mismatch",
            f"{binding_path}.baseline_sha256",
            "retained query digest must be a string",
        )
    else:
        retained_content, retained_error, retained_message = _load_content_addressed_file(
            repo_root.resolve(),
            raw_path=query_baseline_path,
            declared_digest=query_baseline_digest,
        )
        if retained_content is None:
            if retained_error in {
                "procedure_identity_retirement_artifact_path_outside_repository",
                "procedure_identity_retirement_artifact_path_invalid",
                "procedure_identity_retirement_artifact_symlink_forbidden",
            }:
                issue_code = (
                    "procedure_identity_retirement_query_baseline_path_invalid"
                )
                issue_path = f"{binding_path}.baseline_path"
            elif retained_error in {
                "procedure_identity_retirement_artifact_missing",
                "procedure_identity_retirement_artifact_read_failed",
            }:
                issue_code = "procedure_identity_retirement_query_baseline_unavailable"
                issue_path = f"{binding_path}.baseline_path"
            elif retained_error == "procedure_identity_retirement_artifact_digest_mismatch":
                issue_code = (
                    "procedure_identity_retirement_query_baseline_digest_mismatch"
                )
                issue_path = f"{binding_path}.baseline_sha256"
            else:
                issue_code = "procedure_identity_retirement_query_baseline_unavailable"
                issue_path = f"{binding_path}.baseline_path"
            _issue(
                issues,
                issue_code,
                issue_path,
                f"retained bytes could not satisfy the query binding: {retained_error}: {retained_message}",
            )
        if query_baseline_digest != binding.baseline_sha256:
            _issue(
                issues,
                "procedure_identity_retirement_query_baseline_digest_mismatch",
                f"{binding_path}.baseline_sha256",
                "retained query digest does not match the record binding",
            )

    query_source_path = query.get("source_repo_relative_path")
    if (
        not isinstance(query_source_path, str)
        or query_source_path != binding.old_source_path
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_old_source_path_mismatch",
            f"{binding_path}.old_source_path",
            "historical source path does not match the record binding",
        )
    if not _is_safe_repository_relative_metadata_path(binding.old_source_path) or (
        isinstance(query_source_path, str)
        and not _is_safe_repository_relative_metadata_path(query_source_path)
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_old_source_path_invalid",
            f"{binding_path}.old_source_path",
            "historical source path must be safe repository-relative metadata",
        )

    query_source_digest = query.get("source_sha256")
    if (
        not isinstance(query_source_digest, str)
        or query_source_digest != binding.old_source_sha256
    ):
        _issue(
            issues,
            "procedure_identity_retirement_query_old_source_digest_mismatch",
            f"{binding_path}.old_source_sha256",
            "historical source digest does not match the record binding",
        )

    retained_content, retained_error, retained_message = _load_content_addressed_file(
        repo_root.resolve(),
        raw_path=binding.retained_old_source_path,
        declared_digest=binding.old_source_sha256,
    )
    if retained_content is None:
        if retained_error in {
            "procedure_identity_retirement_artifact_path_outside_repository",
            "procedure_identity_retirement_artifact_path_invalid",
            "procedure_identity_retirement_artifact_symlink_forbidden",
        }:
            issue_code = (
                "procedure_identity_retirement_query_retained_old_source_path_invalid"
            )
            issue_path = f"{binding_path}.retained_old_source_path"
        elif retained_error in {
            "procedure_identity_retirement_artifact_missing",
            "procedure_identity_retirement_artifact_read_failed",
        }:
            issue_code = (
                "procedure_identity_retirement_query_retained_old_source_unavailable"
            )
            issue_path = f"{binding_path}.retained_old_source_path"
        elif retained_error == "procedure_identity_retirement_artifact_digest_mismatch":
            issue_code = (
                "procedure_identity_retirement_query_retained_old_source_digest_mismatch"
            )
            issue_path = f"{binding_path}.old_source_sha256"
        else:
            issue_code = (
                "procedure_identity_retirement_query_retained_old_source_unavailable"
            )
            issue_path = f"{binding_path}.retained_old_source_path"
        _issue(
            issues,
            issue_code,
            issue_path,
            "retained old-source bytes could not satisfy the query binding: "
            f"{retained_error}: {retained_message}",
        )

    old_source_artifact = next(
        (
            artifact
            for artifact in record.artifacts
            if artifact.side == "old" and artifact.role == "source"
        ),
        None,
    )
    if old_source_artifact is not None:
        if binding.retained_old_source_path != old_source_artifact.path:
            _issue(
                issues,
                "procedure_identity_retirement_query_retained_old_source_path_mismatch",
                f"{binding_path}.retained_old_source_path",
                "retained old-source path must equal the old production source path",
            )
        if binding.old_source_sha256 != old_source_artifact.sha256:
            _issue(
                issues,
                "procedure_identity_retirement_query_old_source_digest_mismatch",
                f"{binding_path}.old_source_sha256",
                "retired-query old source digest must equal the old production source digest",
            )

    blocking_codes = {
        "procedure_identity_retirement_query_evidence_content_invalid",
        "procedure_identity_retirement_query_list_invalid",
        "procedure_identity_retirement_query_domain_map_invalid",
        "procedure_identity_retirement_query_domain_duplicate",
        "procedure_identity_retirement_query_domain_membership_mismatch",
    }
    if any(issue.code in blocking_codes for issue in issues):
        return None
    return domain_map


def _validate_production_artifact_relations(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    payloads: Mapping[tuple[str, str], Mapping[str, Any]],
    repo_root: Path,
    retired_query_domains: Mapping[str, set[str]] | None,
) -> None:
    eligible_sides = {
        side
        for side in ("old", "new")
        if all((side, role) in payloads for role in REQUIRED_ARTIFACT_ROLES)
    }
    schemas = {
        "semantic_ir": "workflow_semantic_ir.v1",
        "executable_ir": "workflow_executable_ir.v1",
        "runtime_plan": "workflow_runtime_plan.v1",
        "lexical_checkpoint_points": "workflow_lisp_lexical_checkpoint_points.v1",
        "source_map": "workflow_lisp_source_map.v1",
        "build_manifest": "workflow_lisp_procedure_retirement_build_manifest.v1",
    }
    for (side, role), payload in payloads.items():
        if side not in eligible_sides or role == "source":
            continue
        expected = schemas.get(role)
        if expected is not None and payload.get("schema_version") != expected:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_schema_mismatch",
                f"$.artifacts.{side}.{role}",
                f"expected production schema {expected}",
            )

    artifact_index = {
        (artifact.side, artifact.role): artifact
        for artifact in record.artifacts
        if artifact.side in {"old", "new"}
    }
    for side in ("old", "new"):
        if side not in eligible_sides:
            continue
        manifest = payloads.get((side, "build_manifest"))
        manifest_artifact = artifact_index.get((side, "build_manifest"))
        if manifest is None or manifest_artifact is None:
            continue
        inputs = manifest.get("inputs")
        outputs = manifest.get("outputs")
        header_valid = (
            manifest.get("side") == side
            and manifest.get("entry_workflow")
            == str(record.retained_public_entry.get("workflow", "")).split("::")[-1]
            and isinstance(manifest.get("lowering_route"), str)
            and bool(str(manifest.get("lowering_route")).strip())
            and manifest.get("compiler_version") == record.migration.get("compiler_version")
            and manifest.get("build_version") == record.migration.get("build_version")
            and isinstance(inputs, Mapping)
            and set(inputs) == {"source", "provider_externs", "prompt_externs", "command_boundaries"}
            and isinstance(outputs, Mapping)
            and set(outputs) == REQUIRED_ARTIFACT_ROLES - {"source", "build_manifest"}
        )
        if not header_valid:
            _issue(
                issues,
                "procedure_identity_retirement_build_manifest_invalid",
                f"$.artifacts.{side}.build_manifest",
                "build manifest header and input/output role sets must match the reviewed production build",
            )
            continue
        fixture_root = Path(manifest_artifact.path).parent.parent
        for group_name, rows in (("inputs", inputs), ("outputs", outputs)):
            for role, raw in rows.items():
                if not isinstance(raw, Mapping) or not isinstance(raw.get("path"), str) or not _valid_sha256(str(raw.get("sha256", ""))):
                    _issue(
                        issues,
                        "procedure_identity_retirement_build_manifest_invalid",
                        f"$.artifacts.{side}.build_manifest.{group_name}.{role}",
                        "manifest entry requires a safe path and sha256 digest",
                    )
                    continue
                referenced_path = (fixture_root / str(raw["path"])).as_posix()
                content, error_code, error_message = _load_content_addressed_file(
                    repo_root.resolve(),
                    raw_path=referenced_path,
                    declared_digest=str(raw["sha256"]),
                )
                if content is None:
                    _issue(
                        issues,
                        "procedure_identity_retirement_build_manifest_reference_invalid",
                        f"$.artifacts.{side}.build_manifest.{group_name}.{role}",
                        f"{error_code}: {error_message}",
                    )
                artifact = artifact_index.get((side, role))
                if group_name == "outputs" and (artifact is None or artifact.sha256 != raw.get("sha256")):
                    _issue(
                        issues,
                        "procedure_identity_retirement_build_manifest_output_mismatch",
                        f"$.artifacts.{side}.build_manifest.outputs.{role}",
                        "manifest output digest must equal the content-addressed artifact digest",
                    )
                if group_name == "inputs" and role == "source":
                    source = artifact_index.get((side, "source"))
                    if source is None or source.sha256 != raw.get("sha256"):
                        _issue(
                            issues,
                            "procedure_identity_retirement_build_manifest_source_mismatch",
                            f"$.artifacts.{side}.build_manifest.inputs.source",
                            "manifest source digest must equal the content-addressed source artifact digest",
                        )

    old_executable = payloads.get(("old", "executable_ir"))
    new_executable = payloads.get(("new", "executable_ir"))
    for side in eligible_sides:
        semantic = payloads[(side, "semantic_ir")]
        executable = payloads[(side, "executable_ir")]
        runtime = payloads[(side, "runtime_plan")]
        points = payloads[(side, "lexical_checkpoint_points")]
        entry = executable.get("name")
        semantic_workflows = semantic.get("workflows")
        semantic_entry = (
            semantic_workflows.get(entry)
            if isinstance(semantic_workflows, Mapping) and isinstance(entry, str)
            else None
        )
        executable_nodes = executable.get("nodes")
        executable_outputs = executable.get("outputs")
        semantic_bridge = semantic_entry.get("executable_bridge") if isinstance(semantic_entry, Mapping) else None
        semantic_outputs = semantic_entry.get("output_contract_ids") if isinstance(semantic_entry, Mapping) else None
        bridge_node_ids = semantic_bridge.get("node_ids") if isinstance(semantic_bridge, Mapping) else None
        semantic_maps = (
            "call_edges",
            "command_boundaries",
            "contracts",
            "effects",
            "refs",
            "source_map",
            "state_layout",
            "types",
            "workflows",
        )
        semantic_valid = (
            all(isinstance(semantic.get(key), Mapping) for key in semantic_maps)
            and isinstance(semantic_entry, Mapping)
            and semantic_entry.get("workflow_name") == entry
            and isinstance(semantic_bridge, Mapping)
            and isinstance(bridge_node_ids, list)
            and all(isinstance(node_id, str) for node_id in bridge_node_ids)
            and isinstance(executable_nodes, Mapping)
            and set(bridge_node_ids) == set(executable_nodes)
        )
        semantic_valid = bool(
            semantic_valid
            and isinstance(semantic_outputs, Mapping)
            and isinstance(executable_outputs, Mapping)
            and set(semantic_outputs) == set(executable_outputs)
        )
        if not semantic_valid:
            _issue(
                issues,
                "procedure_identity_retirement_semantic_ir_structure_invalid",
                f"$.artifacts.{side}.semantic_ir",
                "Semantic IR must contain the selected workflow, executable bridge, contracts, state, and source relations",
            )

        runtime_nodes = runtime.get("nodes")
        ordered_nodes = runtime.get("ordered_node_ids")
        runtime_points = runtime.get("lexical_checkpoint_points")
        point_rows = points.get("points")
        point_rows_valid = isinstance(point_rows, list) and all(
            isinstance(row, Mapping) and isinstance(row.get("checkpoint_id"), str)
            for row in point_rows
        )
        runtime_points_valid = isinstance(runtime_points, list) and all(
            isinstance(row, Mapping) and isinstance(row.get("checkpoint_id"), str)
            for row in runtime_points
        )
        expected_checkpoint_ids = (
            {str(row["checkpoint_id"]) for row in point_rows}
            if point_rows_valid
            else set()
        )
        runtime_checkpoint_ids = (
            {str(row["checkpoint_id"]) for row in runtime_points}
            if runtime_points_valid
            else set()
        )
        runtime_valid = (
            runtime.get("workflow_name") == entry
            and isinstance(runtime_nodes, Mapping)
            and isinstance(executable_nodes, Mapping)
            and set(runtime_nodes) == set(executable_nodes)
            and isinstance(ordered_nodes, list)
            and all(isinstance(node_id, str) for node_id in ordered_nodes)
            and len(ordered_nodes) == len(set(ordered_nodes))
            and set(ordered_nodes) == set(runtime_nodes)
            and expected_checkpoint_ids == runtime_checkpoint_ids
            and bool(expected_checkpoint_ids)
            and point_rows_valid
            and runtime_points_valid
            and isinstance(runtime.get("resume_checkpoints"), list)
            and isinstance(runtime.get("observability"), Mapping)
        )
        if not runtime_valid:
            _issue(
                issues,
                "procedure_identity_retirement_runtime_plan_structure_invalid",
                f"$.artifacts.{side}.runtime_plan",
                "runtime plan must bind the selected workflow, executable nodes, ordering, and lexical checkpoints",
            )

    if eligible_sides == {"old", "new"} and old_executable is not None and new_executable is not None:
        old_contract = _public_contract_projection(old_executable)
        new_contract = _public_contract_projection(new_executable)
        if old_contract != new_contract:
            _issue(
                issues,
                "procedure_identity_retirement_production_contract_mismatch",
                "$.artifacts",
                "old and new executable IR public contracts differ",
            )
        actual_digest = _projection_digest(old_contract)
        if record.retained_public_entry.get("contract_digest") != actual_digest:
            _issue(
                issues,
                "procedure_identity_retirement_public_contract_artifact_mismatch",
                "$.retained_public_entry.contract_digest",
                "retained public contract digest does not match executable IR",
            )
        expected_multiset: Counter[ArtifactContractKey] = Counter()
        for row in old_contract:
            surface = str(row["surface"])
            is_path = row["kind"] in {"path", "relpath"}
            expected_multiset[
                ArtifactContractKey(
                    owning_public_entry=str(record.retained_public_entry.get("workflow")),
                    semantic_step_role=(
                        "workflow_return_artifact" if surface == "outputs" and is_path
                        else "workflow_return_field" if surface == "outputs"
                        else "published_artifact" if surface == "artifacts"
                        else "private_artifact"
                    ),
                    contract_kind="artifact" if is_path or surface != "outputs" else "result_field",
                    name=str(row["name"]),
                    json_pointer=f"/{surface}/{row['name']}",
                    type_variant=str(row["value_type"]),
                    publication_role=(
                        "private_artifact" if surface == "private_artifacts"
                        else "published_artifact" if is_path or surface == "artifacts"
                        else "public_output"
                    ),
                )
            ] += 1
        for side in ("old", "new"):
            declared = Counter(
                {row.key: row.count for row in record.artifact_multiset if row.side == side}
            )
            if declared != expected_multiset:
                _issue(
                    issues,
                    "procedure_identity_retirement_artifact_multiset_artifact_mismatch",
                    f"$.artifact_multiset.{side}",
                    "declared contract multiset does not match production executable outputs",
                )

    source_map = payloads.get(("new", "source_map"))
    if "new" in eligible_sides and source_map is not None:
        workflows = source_map.get("workflows")
        selected = workflows.get(record.retained_public_entry.get("workflow")) if isinstance(workflows, Mapping) else None
        executable_nodes = selected.get("executable_nodes") if isinstance(selected, Mapping) else None
        node_origins = {
            row.get("node_id"): row.get("origin_key")
            for row in executable_nodes or ()
            if isinstance(row, Mapping)
        }
        serialized = json.dumps(selected, sort_keys=True) if selected is not None else ""
        for index, row in enumerate(record.lineage_notes):
            node = row.get("executable_node")
            if node_origins.get(node) != row.get("source_map_origin") or any(
                str(row.get(key, "")) not in serialized
                for key in ("procedure_definition_note", "call_site_note")
            ):
                _issue(
                    issues,
                    "procedure_identity_retirement_lineage_artifact_mismatch",
                    f"$.lineage_notes[{index}]",
                    "lineage node, origin, and notes must occur in the new production source map",
                )

    expected_identities: dict[str, dict[str, set[str]]] = {
        side: {kind: set() for kind in REQUIRED_IDENTITY_DOMAINS}
        for side in ("old", "new")
    }
    for side in ("old", "new"):
        if side not in eligible_sides:
            continue
        typed = payloads.get((side, "typed_frontend_ast"))
        executable = payloads.get((side, "executable_ir"))
        points_payload = payloads.get((side, "lexical_checkpoint_points"))
        map_payload = payloads.get((side, "source_map"))
        if typed is None or executable is None or points_payload is None or map_payload is None:
            continue
        expected_identities[side] = _collect_production_identity_carriers(payloads, side)
        program_identity = points_payload.get("program_identity")
        source_digest = program_identity.get("source_module_digest") if isinstance(program_identity, Mapping) else None
        declared_source_digest = next(
            (
                artifact.sha256
                for artifact in record.artifacts
                if artifact.side == side and artifact.role == "source"
            ),
            None,
        )
        if source_digest != declared_source_digest:
            _issue(
                issues,
                "procedure_identity_retirement_source_build_mismatch",
                f"$.artifacts.{side}.source",
                "source digest must match the compiler-produced program identity",
            )

    actual_identities = {
        "old": {
            kind: {
                row.old_identity: row.old_disposition
                for row in record.identity_delta
                if row.identity_kind == kind
                and row.old_identity is not None
                and row.old_disposition is not None
            }
            for kind in REQUIRED_IDENTITY_DOMAINS
        },
        "new": {
            kind: {
                row.new_identity: row.new_disposition
                for row in record.identity_delta
                if row.identity_kind == kind
                and row.new_identity is not None
                and row.new_disposition is not None
            }
            for kind in REQUIRED_IDENTITY_DOMAINS
        },
    }
    production_identities = {
        side: {
            kind: set(identities)
            for kind, identities in expected_identities[side].items()
        }
        for side in ("old", "new")
    }
    if retired_query_domains is not None:
        query_retired_rows = {
            (kind, identity)
            for kind, identities in retired_query_domains.items()
            for identity in identities
        }
        declared_retired_rows = {
            (row.identity_kind, row.old_identity)
            for row in record.identity_delta
            if row.old_disposition == "retired" and row.old_identity is not None
        }
        if query_retired_rows != declared_retired_rows:
            _issue(
                issues,
                "procedure_identity_retirement_query_retired_membership_mismatch",
                "$.retired_identity_query_evidence.evidence_path.old_identity_query.identities_by_domain",
                "frozen query domain memberships must exactly equal declared retired old identities",
            )
        query_raw_identities = set().union(*retired_query_domains.values())
        new_raw_identities: set[str] = set()
        if "new" in eligible_sides:
            new_leak_carriers = _collect_production_leak_carriers(payloads, "new")
            new_raw_identities = set().union(*new_leak_carriers.values())
        leaked = sorted(query_raw_identities & new_raw_identities)
        if leaked:
            _issue(
                issues,
                "procedure_identity_retirement_leaked_retired_identity",
                "$.retired_identity_query_evidence",
                "retired raw identities occur in new production domains: "
                + ", ".join(leaked),
            )
        for kind, identities in retired_query_domains.items():
            expected_identities["old"][kind].update(identities)

    for side, opposite in (("old", "new"), ("new", "old")):
        expected_table: dict[str, dict[str, str]] = {}
        for kind, identities in expected_identities[side].items():
            expected_table[kind] = {}
            for identity in identities:
                is_retired_query_identity = (
                    side == "old"
                    and retired_query_domains is not None
                    and identity in retired_query_domains[kind]
                )
                expected_table[kind][identity] = (
                    "retired"
                    if is_retired_query_identity
                    else "preserved"
                    if identity in production_identities[opposite][kind]
                    else "retired"
                    if side == "old"
                    else "new"
                )
        if actual_identities[side] != expected_table:
            _issue(
                issues,
                "procedure_identity_retirement_identity_artifact_mismatch",
                "$.identity_delta",
                f"{side} identity table must exactly match production identities and dispositions",
            )


def _validate_retained_inventory(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    repo_root: Path,
) -> None:
    raw_path = record.retained_wrapper_evidence.get("inventory_path")
    declared_digest = record.retained_wrapper_evidence.get("inventory_sha256")
    if not isinstance(raw_path, str) or not isinstance(declared_digest, str):
        return
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts or _path_has_symlink_component(repo_root, relative):
        _issue(
            issues,
            "procedure_identity_retirement_inventory_path_invalid",
            "$.retained_wrapper_evidence.inventory_path",
            "retained inventory must be a repository-relative non-symlink file",
        )
        return
    candidate = repo_root / relative
    try:
        content = _read_stable_bytes(candidate)
    except ValueError:
        _issue(
            issues,
            "procedure_identity_retirement_inventory_missing",
            "$.retained_wrapper_evidence.inventory_path",
            "retained inventory is unavailable",
        )
        return
    actual_digest = f"sha256:{sha256(content).hexdigest()}"
    if declared_digest != actual_digest:
        _issue(
            issues,
            "procedure_identity_retirement_inventory_digest_mismatch",
            "$.retained_wrapper_evidence.inventory_sha256",
            "declared retained inventory digest does not match repository content",
        )
    try:
        inventory = json.loads(content, object_pairs_hook=_json_object_without_duplicates)
    except (json.JSONDecodeError, ValueError):
        inventory = None
    expected = {
        "schema": "workflow_lisp_procedure_retirement_inventory.v1",
        "module": record.retained_public_entry.get("module"),
        "retained_public_entry": record.retained_public_entry.get("workflow"),
        "internal_callee": record.callee.get("identity"),
        "reviewed_call_site": record.retained_wrapper_evidence.get("reviewed_call_site"),
    }
    expected_export = str(record.retained_public_entry.get("workflow", "")).split("::")[-1]
    exported_entries = inventory.get("exported_entries") if isinstance(inventory, Mapping) else None
    public_entries = inventory.get("public_entries") if isinstance(inventory, Mapping) else None
    registered_entries = inventory.get("registered_public_entries") if isinstance(inventory, Mapping) else None
    callee_identity = record.callee.get("identity")
    inventory_mismatch = (
        not isinstance(inventory, Mapping)
        or any(inventory.get(key) != value for key, value in expected.items())
        or not all(
            isinstance(entries, list)
            for entries in (exported_entries, public_entries, registered_entries)
        )
        or any(
            expected_export not in entries
            for entries in (exported_entries, public_entries, registered_entries)
        )
        or any(
            callee_identity in entries
            for entries in (exported_entries, public_entries, registered_entries)
        )
    )
    if inventory_mismatch:
        _issue(
            issues,
            "procedure_identity_retirement_inventory_content_mismatch",
            "$.retained_wrapper_evidence.inventory_path",
            "retained inventory does not identify the reviewed module, entry, callee, and call site",
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


def _validate_root_checksum_characterization(
    root: Mapping[str, Any],
    issues: list[RetirementIssue],
    repository_root: Path,
) -> None:
    path = "$.checksum_evidence.root"
    if not root["command"].strip():
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_detail_invalid",
            f"{path}.command",
            "generic characterization command must be nonempty",
        )
    if root["tree_immutability"] != "before_equals_after":
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_tree_immutability_invalid",
            f"{path}.tree_immutability",
            "generic characterization must retain before_equals_after",
        )
    if root["default_resume"] is not True:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_nondefault_resume",
            f"{path}.default_resume",
            "generic characterization requires default resume behavior",
        )
    if root["observability_overrides"] is not False or root["cli_overrides"] is not False:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_overrides_present",
            path,
            "generic characterization forbids observability and CLI overrides",
        )
    if root["exit_status"] == 0:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_zero_exit",
            f"{path}.exit_status",
            "generic characterization requires a nonzero rejection exit",
        )
    if any(
        root[key] is not False
        for key in ("executor_constructed", "provider_executed", "command_executed")
    ):
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_execution_observed",
            path,
            "generic characterization must stop before executor, provider, or command execution",
        )

    content, error_code, message = _load_content_addressed_file(
        repository_root,
        raw_path=root["characterization_path"],
        declared_digest=root["characterization_sha256"],
    )
    error_codes = {
        "procedure_identity_retirement_artifact_path_outside_repository": (
            "procedure_identity_retirement_root_characterization_path_outside_repository"
        ),
        "procedure_identity_retirement_artifact_symlink_forbidden": (
            "procedure_identity_retirement_root_characterization_symlink_forbidden"
        ),
        "procedure_identity_retirement_artifact_missing": (
            "procedure_identity_retirement_root_characterization_missing"
        ),
        "procedure_identity_retirement_artifact_read_failed": (
            "procedure_identity_retirement_root_characterization_read_failed"
        ),
        "procedure_identity_retirement_artifact_digest_mismatch": (
            "procedure_identity_retirement_root_characterization_digest_mismatch"
        ),
        "procedure_identity_retirement_artifact_path_invalid": (
            "procedure_identity_retirement_root_characterization_path_invalid"
        ),
    }
    if content is None:
        _issue(
            issues,
            error_codes.get(
                error_code,
                "procedure_identity_retirement_root_characterization_read_failed",
            ),
            f"{path}.characterization_path",
            message,
        )
        return

    try:
        characterization = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_nonfinite_json_constant,
        )
        characterization = _object(
            characterization,
            "$.root_checksum_characterization",
            allowed={"schema", "projection", "projection_sha256"},
            required={"schema", "projection", "projection_sha256"},
        )
        projection = _object(
            characterization["projection"],
            "$.root_checksum_characterization.projection",
            allowed={"details", "claim_boundary"},
            required={"details", "claim_boundary"},
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_structure_invalid",
            f"{path}.characterization_path",
            f"characterization must be closed canonical JSON: {exc}",
        )
        return

    if characterization["schema"] != ROOT_CHECKSUM_CHARACTERIZATION_SCHEMA:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_schema_unsupported",
            f"{path}.characterization_path",
            f"expected {ROOT_CHECKSUM_CHARACTERIZATION_SCHEMA}",
        )

    observed_projection_digest = _canonical_json_digest(projection)
    if (
        characterization["projection_sha256"] != observed_projection_digest
        or root["projection_sha256"] != observed_projection_digest
    ):
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_projection_digest_mismatch",
            f"{path}.projection_sha256",
            "file and record projection digests must equal the canonical projection digest",
        )

    detail_fields = {
        "command",
        "default_resume",
        "observability_overrides",
        "cli_overrides",
        "exit_status",
        "tree_immutability",
        "executor_constructed",
        "provider_executed",
        "command_executed",
    }
    details = projection["details"]
    if not isinstance(details, dict):
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_structure_invalid",
            f"{path}.characterization_path",
            "projection details must be an object",
        )
        return
    unknown_details = set(details) - detail_fields
    missing_details = detail_fields - set(details)
    if unknown_details or (missing_details - {"tree_immutability"}):
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_structure_invalid",
            f"{path}.characterization_path",
            "projection details must have exactly the closed detail fields",
        )
    detail_types_valid = (
        isinstance(details.get("command"), str)
        and isinstance(details.get("default_resume"), bool)
        and isinstance(details.get("observability_overrides"), bool)
        and isinstance(details.get("cli_overrides"), bool)
        and isinstance(details.get("exit_status"), int)
        and not isinstance(details.get("exit_status"), bool)
        and isinstance(details.get("tree_immutability"), str)
        and isinstance(details.get("executor_constructed"), bool)
        and isinstance(details.get("provider_executed"), bool)
        and isinstance(details.get("command_executed"), bool)
    )
    if not detail_types_valid:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_structure_invalid",
            f"{path}.characterization_path",
            "projection detail values must have their exact scalar types",
        )
    if not isinstance(details.get("command"), str) or not details.get("command", "").strip():
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_detail_invalid",
            f"{path}.characterization_path",
            "projection command must be nonempty",
        )
    if "tree_immutability" not in details or details.get("tree_immutability") != "before_equals_after":
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_tree_immutability_invalid",
            f"{path}.characterization_path",
            "projection details must retain before_equals_after",
        )
    if details.get("default_resume") is not True:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_nondefault_resume",
            f"{path}.characterization_path",
            "projection details require default resume behavior",
        )
    if details.get("observability_overrides") is not False or details.get("cli_overrides") is not False:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_overrides_present",
            f"{path}.characterization_path",
            "projection details forbid observability and CLI overrides",
        )
    if details.get("exit_status") == 0:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_zero_exit",
            f"{path}.characterization_path",
            "projection details require a nonzero rejection exit",
        )
    if any(
        details.get(key) is not False
        for key in ("executor_constructed", "provider_executed", "command_executed")
    ):
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_execution_observed",
            f"{path}.characterization_path",
            "projection details must stop before executor, provider, or command execution",
        )

    claim_boundary = projection["claim_boundary"]
    expected_claim_boundary = {
        "actual_subject_rejection": "not_asserted",
        "cross_source_compatibility": "not_asserted",
        "runtime_authority": "none",
    }
    if claim_boundary != expected_claim_boundary:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_claim_boundary_invalid",
            f"{path}.characterization_path",
            "claim boundary must disclaim actual rejection and compatibility and have no runtime authority",
        )

    record_details = {
        key: root[key]
        for key in detail_fields
    }
    if details != record_details:
        _issue(
            issues,
            "procedure_identity_retirement_root_characterization_detail_mismatch",
            path,
            "record common and tree-immutability details must exactly match the retained projection",
        )


def _validate_evidence_blocks(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    repository_root: Path,
) -> None:
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
        new_points = {
            identity
            for row in record.identity_delta
            for identity, disposition in (
                (row.new_identity, row.new_disposition),
            )
            if row.identity_kind in {"checkpoint", "program_point"}
            and identity is not None
            and disposition == "new"
        }
        if resumed.get("interruption_point") not in new_points:
            _issue(
                issues,
                "procedure_identity_retirement_interruption_point_unknown",
                "$.new_id_evidence.interruption_resume.interruption_point",
                "interruption point must be a declared new checkpoint or program point",
            )
    if isinstance(clean, Mapping) and isinstance(resumed, Mapping) and clean.get("run_id") == resumed.get("run_id"):
        _issue(
            issues,
            "procedure_identity_retirement_new_id_run_ids_not_distinct",
            "$.new_id_evidence",
            "clean and interruption/resume evidence must use distinct run IDs",
        )
    root = record.checksum_evidence.get("root")
    if (
        isinstance(root, Mapping)
        and root.get("evidence_mode") == "actual_tree"
        and (
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
        )
    ):
        _issue(
            issues,
            "procedure_identity_retirement_root_checksum_proof_invalid",
            "$.checksum_evidence.root",
            "root proof must be default, byte-immutable, and pre-execution",
        )
    if isinstance(root, Mapping) and root.get("evidence_mode") == "generic_characterization":
        _validate_root_checksum_characterization(root, issues, repository_root)
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
    if isinstance(callee, Mapping):
        expected_callee = f"{record.callee.get('module')}::{record.callee.get('identity')}"
        if callee.get("mismatch_identity") != expected_callee:
            _issue(
                issues,
                "procedure_identity_retirement_callee_identity_mismatch",
                "$.checksum_evidence.callee.mismatch_identity",
                "checksum mismatch identity must be the reviewed qualified callee identity",
            )

    new_nodes = {
        row.new_identity
        for row in record.identity_delta
        if row.identity_kind == "executable_node"
        and row.new_disposition == "new"
        and row.new_identity is not None
    }
    new_origins = {
        row.new_identity
        for row in record.identity_delta
        if row.identity_kind == "source_map_origin"
        and row.new_disposition == "new"
        and row.new_identity is not None
    }
    for index, row in enumerate(record.lineage_notes):
        if row.get("executable_node") not in new_nodes or row.get("source_map_origin") not in new_origins:
            _issue(
                issues,
                "procedure_identity_retirement_lineage_identity_mismatch",
                f"$.lineage_notes[{index}]",
                "lineage node and source-map origin must be declared new identities",
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
        record.retained_wrapper_evidence.get("inventory_sha256"),
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
        "store_terminal_run_count",
        "store_nonterminal_run_count",
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
                "matching supported nonterminal state selects strict compatibility",
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
        named_root = Path(store.root)
        if not named_root.is_absolute() and ".." in named_root.parts:
            _issue(
                issues,
                "procedure_identity_retirement_known_store_unsafe_path",
                f"{path}.root",
                "relative known store root must not contain parent traversal",
            )
            continue
        candidate = named_root if named_root.is_absolute() else repository_root / named_root
        resolved_candidate = candidate.resolve(strict=False)
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
                "fresh scan found matching supported nonterminal state",
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
    artifact_payloads = _validate_artifacts(record, issues, repository_root)
    _validate_retained_inventory(record, issues, repository_root)
    retired_query_domains = _validate_retired_identity_query_evidence(
        record,
        issues,
        repository_root,
    )
    _validate_production_artifact_relations(
        record,
        issues,
        artifact_payloads,
        repository_root,
        retired_query_domains,
    )
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
    _validate_evidence_blocks(record, issues, repository_root)
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
        "producer",
        "source_step_id",
        "storage_allocation_id",
        "producer_step_id",
        "call_presentation_key",
        "caller_node_id",
        "allocation_id",
        "record_id",
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
        "artifact_consumes",
        "private_artifact_consumes",
        "_resolved_consumes",
        "_pending_artifact_consumes",
        "_pending_private_artifact_consumes",
        "compatibility_artifact_consumes",
        "public_artifact_consumes",
        "resolved_artifact_consumes",
        "for_each",
        "repeat_until",
    }
)


def _scan_error(code: str, message: str) -> ValueError:
    return ValueError(f"{code}: {message}")


def _store_tree_snapshot(store_root: Path) -> tuple[tuple[Any, ...], ...]:
    """Capture the complete named tree without following links."""

    rows: list[tuple[Any, ...]] = []

    def onerror(error: OSError) -> None:
        raise _scan_error(
            "procedure_identity_retirement_known_store_unreadable",
            f"could not enumerate store: {error}",
        )

    for current, directories, filenames in os.walk(
        store_root, followlinks=False, onerror=onerror
    ):
        directories.sort()
        filenames.sort()
        current_path = Path(current)
        for name in sorted(tuple(directories) + tuple(filenames)):
            candidate = current_path / name
            try:
                stat = candidate.lstat()
            except OSError as exc:
                raise _scan_error(
                    "procedure_identity_retirement_known_store_unreadable",
                    f"could not inspect store entry {candidate}: {exc}",
                ) from exc
            if candidate.is_symlink():
                raise _scan_error(
                    "procedure_identity_retirement_store_symlink_forbidden",
                    f"symlink encountered in store: {candidate}",
                )
            kind = "directory" if candidate.is_dir() else "file" if candidate.is_file() else "other"
            rows.append(
                (
                    candidate.relative_to(store_root).as_posix(),
                    stat.st_dev,
                    stat.st_ino,
                    kind,
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            )
    return tuple(sorted(rows))


def _is_supported_store_evidence(path: Path, store_root: Path) -> bool:
    relative = path.relative_to(store_root)
    lower_parts = tuple(part.lower() for part in relative.parts)
    filename = path.name.lower()
    if filename == "state.json":
        return True
    if path.suffix.lower() == ".jsonl":
        return True
    if path.suffix.lower() != ".json":
        return False
    return any(
        marker in lower_parts
        for marker in ("checkpoints", "manifests", "metadata", "call_frames")
    ) or "manifest" in filename or "identity" in filename


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
        directories.sort()
        filenames.sort()
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
            if _is_supported_store_evidence(candidate, store_root):
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
        if field_name in _IDENTITY_MAPPING_FIELDS or (
            isinstance(field_name, str)
            and (
                field_name.endswith("artifact_consumes")
                or field_name.endswith("_resolved_consumes")
            )
        ):
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
    before_tree = _store_tree_snapshot(store_root)
    files = _safe_store_files(store_root)

    counts = {
        "terminal_run_count": 0,
        "nonterminal_run_count": 0,
        "store_terminal_run_count": 0,
        "store_nonterminal_run_count": 0,
        "checkpoint_index_count": 0,
        "checkpoint_record_count": 0,
        "retained_manifest_count": 0,
        "identity_metadata_count": 0,
        "scanned_file_count": len(files),
    }
    raw_matches: list[dict[str, str]] = []
    scanned_files: list[dict[str, str]] = []
    run_is_terminal: dict[str, bool] = {}
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
            if filename == "state.json" and len(relative_parts) == 2:
                status = payload.get("status")
                terminal = isinstance(status, str) and status.lower() in _TERMINAL_STATUSES
                run_is_terminal[relative_parts[0]] = terminal
                if terminal:
                    counts["store_terminal_run_count"] += 1
                else:
                    counts["store_nonterminal_run_count"] += 1
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

    after_tree = _store_tree_snapshot(store_root)
    if before_tree != after_tree:
        raise _scan_error(
            "procedure_identity_retirement_known_store_tree_changed",
            "named store tree changed while scanning",
        )

    deduplicated = {
        (row["location"], row["identity"], row["field"]): row
        for row in raw_matches
    }
    matches = sorted(
        deduplicated.values(),
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
    )
    matching_runs = {
        row["path"].split("/", maxsplit=1)[0]
        for row in matches
        if "/" in row["path"]
    }
    missing_run_states = sorted(matching_runs.difference(run_is_terminal))
    if missing_run_states:
        raise _scan_error(
            "procedure_identity_retirement_matching_run_state_missing",
            "matching store evidence has no containing top-level run state: "
            + ", ".join(missing_run_states),
        )
    counts["terminal_run_count"] = sum(run_is_terminal[run] for run in matching_runs)
    counts["nonterminal_run_count"] = sum(
        not run_is_terminal[run] for run in matching_runs
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
