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
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "workflow_lisp_procedure_identity_retirement.v1"
COMPATIBILITY_CLASS = "reviewed_internal_identity_retirement"
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
            },
        )
        for key in ("root", "query_version", "query_time", "normalized_scan_digest"):
            _string(row[key], f"{path}.{key}")
        owner = _string(row.get("owner"), f"{path}.owner", nullable=True)
        attestation = _string(row.get("attestation"), f"{path}.attestation", nullable=True)
        attested_at = _string(row.get("attested_at"), f"{path}.attested_at", nullable=True)
        counts = {
            key: _integer(row[key], f"{path}.{key}")
            for key in ("terminal_run_count", "nonterminal_run_count", "call_frame_count", "consumer_count")
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
        _string(callee["parent_metadata_delta"], "$.checksum_evidence.callee.parent_metadata_delta")
        for key in callee_fields - {"parent_metadata_delta"}:
            _boolean(callee[key], f"$.checksum_evidence.callee.{key}")
    return _frozen(new_evidence), _frozen(checksum)


def load_retirement_record(path: str | Path) -> ProcedureIdentityRetirementRecord:
    """Load a strict v1 evidence record without consulting runtime state."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
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
    if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True


def _validate_identity_delta(record: ProcedureIdentityRetirementRecord, issues: list[RetirementIssue]) -> None:
    domains = {row.identity_kind for row in record.identity_delta}
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
        if row.old_disposition == "preserved" and (
            row.new_identity is None or row.new_disposition != "preserved"
        ):
            _issue(
                issues,
                "procedure_identity_retirement_identity_row_invalid",
                f"$.identity_delta[{index}]",
                "a preserved old identity requires a preserved new identity",
            )


def _validate_artifacts(
    record: ProcedureIdentityRetirementRecord,
    issues: list[RetirementIssue],
    repo_root: Path,
) -> None:
    root = repo_root.resolve()
    roles_by_side: dict[str, set[str]] = {"old": set(), "new": set()}
    for index, artifact in enumerate(record.artifacts):
        path = f"$.artifacts[{index}]"
        if artifact.side not in roles_by_side:
            _issue(issues, "procedure_identity_retirement_artifact_side_invalid", path, "side must be old or new")
            continue
        roles_by_side[artifact.side].add(artifact.role)
        if not _valid_sha256(artifact.sha256):
            _issue(
                issues,
                "procedure_identity_retirement_artifact_digest_invalid",
                f"{path}.sha256",
                "artifact digest must be sha256:<64 lowercase hexadecimal characters>",
            )
            continue
        candidate = (root / artifact.path).resolve()
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
        actual = f"sha256:{sha256(candidate.read_bytes()).hexdigest()}"
        if actual != artifact.sha256:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_digest_mismatch",
                f"{path}.sha256",
                f"declared {artifact.sha256}, observed {actual}",
            )
    for side, roles in roles_by_side.items():
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
    for index, row in enumerate(record.artifact_multiset):
        if row.count <= 0:
            _issue(
                issues,
                "procedure_identity_retirement_artifact_count_invalid",
                f"$.artifact_multiset[{index}].count",
                "artifact multiset count must be positive",
            )
        elif row.side in multisets:
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
    root = record.checksum_evidence.get("root")
    if isinstance(root, Mapping) and (
        root["default_resume"] is not True
        or root["observability_overrides"] is not False
        or root["cli_overrides"] is not False
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
        callee["checksum_mismatch_observed"] is not True
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
    if not record.known_state_stores:
        _issue(
            issues,
            "procedure_identity_retirement_known_store_missing",
            "$.known_state_stores",
            "every known store must be enumerated",
        )
    for index, store in enumerate(record.known_state_stores):
        path = f"$.known_state_stores[{index}]"
        if not store.owner or not store.owner.strip():
            _issue(
                issues,
                "procedure_identity_retirement_known_store_unowned",
                f"{path}.owner",
                "known store requires a genuine named owner",
            )
        if not store.attestation or not store.attestation.strip() or not store.attested_at:
            _issue(
                issues,
                "procedure_identity_retirement_attestation_missing",
                f"{path}.attestation",
                "known store requires a timestamped owner attestation",
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
            for count in (
                store.terminal_run_count,
                store.nonterminal_run_count,
                store.call_frame_count,
                store.consumer_count,
            )
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
    _validate_artifacts(record, issues, Path(repo_root))
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
    return RetirementValidationResult(issues=tuple(sorted(issues, key=lambda issue: (issue.path, issue.code))))


_TERMINAL_STATUSES = frozenset({"completed", "succeeded", "failed", "cancelled", "canceled", "aborted", "terminated"})
_IDENTITY_KEYS = frozenset(
    {
        "workflow_id",
        "workflow_name",
        "retained_workflow_id",
        "call_frame_id",
        "caller_call_frame_id",
        "parent_call_frame_id",
        "caller_step_id",
        "step_id",
        "current_step",
        "completed_step",
        "completed_steps",
        "executable_node_id",
        "program_point_id",
        "checkpoint_id",
        "checkpoint_ids",
        "state_allocation_id",
        "source_map_origin",
        "presentation_key",
    }
)


def _identity_matches(
    value: Any,
    *,
    retired: frozenset[str],
    relative_path: str,
    pointer: str = "",
    key_name: str | None = None,
) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            matches.extend(
                _identity_matches(
                    value[key],
                    retired=retired,
                    relative_path=relative_path,
                    pointer=f"{pointer}/{escaped}",
                    key_name=key,
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
                    key_name=key_name,
                )
            )
    elif key_name in _IDENTITY_KEYS and isinstance(value, str) and value in retired:
        matches.append(
            {
                "identity": value,
                "key": key_name,
                "path": relative_path,
                "pointer": pointer or "/",
            }
        )
    return matches


def scan_known_state_store(
    root: str | Path,
    *,
    retired_identities: Iterable[str],
    query_version: str,
) -> dict[str, Any]:
    """Return normalized facts about one explicitly named local state store.

    The scan never supplies an owner, attestation, or claim about external
    stores.  Its digest excludes the absolute root so identical copied content
    produces the same normalized query result.
    """

    store_root = Path(root)
    retired = frozenset(str(identity) for identity in retired_identities)
    if not isinstance(query_version, str) or not query_version:
        raise ValueError("query_version must be a non-empty string")
    if any(not identity for identity in retired):
        raise ValueError("retired_identities must contain only non-empty strings")

    terminal_runs = 0
    nonterminal_runs = 0
    checkpoint_indexes = 0
    checkpoint_records = 0
    retained_manifests = 0
    identity_metadata = 0
    parse_errors = 0
    matches: list[dict[str, str]] = []
    scanned_files: list[dict[str, str]] = []
    json_paths = sorted(
        (path for path in store_root.rglob("*.json") if path.is_file()),
        key=lambda path: path.relative_to(store_root).as_posix(),
    ) if store_root.is_dir() else []
    for path in json_paths:
        relative = path.relative_to(store_root).as_posix()
        content = path.read_bytes()
        scanned_files.append({"path": relative, "sha256": f"sha256:{sha256(content).hexdigest()}"})
        lower_parts = tuple(part.lower() for part in path.relative_to(store_root).parts)
        filename = path.name.lower()
        if "checkpoints" in lower_parts:
            if filename == "index.json" or "index" in filename:
                checkpoint_indexes += 1
            else:
                checkpoint_records += 1
        if "manifest" in filename or "manifests" in lower_parts:
            retained_manifests += 1
        if "metadata" in lower_parts or "identity" in filename:
            identity_metadata += 1
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            parse_errors += 1
            continue
        relative_parts = path.relative_to(store_root).parts
        is_top_level_state = filename == "state.json" and len(relative_parts) <= 2
        if is_top_level_state and isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(status, str) and status.lower() in _TERMINAL_STATUSES:
                terminal_runs += 1
            else:
                nonterminal_runs += 1
        matches.extend(
            _identity_matches(
                payload,
                retired=retired,
                relative_path=relative,
            )
        )

    matches.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    call_frame_count = sum(1 for row in matches if "call_frame" in row["key"])
    normalized = {
        "query_version": query_version,
        "retired_identities": sorted(retired),
        "terminal_run_count": terminal_runs,
        "nonterminal_run_count": nonterminal_runs,
        "call_frame_count": call_frame_count,
        "consumer_count": len(matches),
        "checkpoint_index_count": checkpoint_indexes,
        "checkpoint_record_count": checkpoint_records,
        "retained_manifest_count": retained_manifests,
        "identity_metadata_count": identity_metadata,
        "parse_error_count": parse_errors,
        "matches": matches,
        "scanned_files": scanned_files,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {
        "root": str(store_root),
        **normalized,
        "matches": tuple(dict(row) for row in matches),
        "scanned_files": tuple(dict(row) for row in scanned_files),
        "normalized_scan_digest": f"sha256:{sha256(encoded).hexdigest()}",
    }
