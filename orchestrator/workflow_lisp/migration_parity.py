"""Workflow Lisp migration parity reports and derived views."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


TARGETS_SCHEMA_VERSION = "workflow_lisp_migration_parity_targets.v1"
REPORT_SCHEMA_VERSION = "workflow_lisp_migration_parity_report.v2"
INDEX_SCHEMA_VERSION = "workflow_lisp_migration_parity_index.v2"
GATE_EVALUATION_SCHEMA_VERSION = "workflow_lisp_migration_parity_gate_evaluation.v1"
TOOL_VERSION = "workflow_lisp_migration_parity.v2"
DESIGN_DELTA_G8_DELETION_EVIDENCE_SCHEMA_VERSION = (
    "workflow_lisp_design_delta_g8_deletion_evidence.v1"
)
DESIGN_DELTA_G8_DELETED_MANIFEST_ROWS = (
    "classify_lisp_frontend_work_item_terminal",
    "select_lisp_frontend_blocked_recovery_route",
    "record_terminal_work_item",
    "record_blocked_recovery_outcome",
    "write_lisp_frontend_drain_status",
    "finalize_lisp_frontend_drain_summary",
)
DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS = (
    "record_terminal_work_item",
    "record_blocked_recovery_outcome",
    "write_lisp_frontend_drain_status",
    "finalize_lisp_frontend_drain_summary",
)
DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS = (
    "with-phase",
    "finalize-selected-item",
    "backlog-drain",
)
DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS = ("with-phase",)
COMMAND_ROLES = (
    "compile",
    "dry_run",
    "smoke_or_integration",
    "output_contract_parity",
    "terminal_state_parity",
    "artifact_parity",
    "resume_parity",
)
REQUIRED_EVIDENCE_ROLES = (
    "compile",
    "shared_validation",
    "dry_run",
    "smoke_or_integration",
    "baseline_characterization",
    "output_contract_parity",
    "terminal_state_parity",
    "artifact_parity",
    "resume_parity",
)
BASELINE_FIELDS = ("inputs", "outputs", "terminal_states", "artifacts", "resume_behavior")
PASSING_ARTIFACT_STATUSES = {"emitted", "validated", "pass"}
GATE_OWNED_REPORT_FIELDS = frozenset({"primary_surface", "report_valid", "evidence_complete"})
REQUIRED_REPORT_STRING_FIELDS = (
    "workflow_family",
    "candidate",
    "yaml_primary",
    "tool_version",
    "dsl_version",
    "generated_at",
    "report_path",
)
REQUIRED_REPORT_MAPPING_FIELDS = (
    "target_identity",
    "evidence_freshness",
    "command_logs",
    "promotion_eligibility",
    "compile_artifacts",
    "evidence",
)
REQUIRED_REPORT_OBJECT_LIST_FIELDS = ("accepted_differences", "deprecated_yaml_mechanics")


@dataclass(frozen=True)
class EvidenceCommand:
    argv: tuple[str, ...] | None
    waiver: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ParityTarget:
    target_manifest_path: Path
    target_manifest_sha256: str
    target_index: int
    workflow_family: str
    candidate: str
    yaml_primary: str
    entry_workflow: str
    provider_externs_file: str | None
    prompt_externs_file: str | None
    command_boundaries_file: str | None
    imported_workflow_bundles_file: str | None
    readiness_label: str | None
    lowering_route: str | None
    lowering_schema_version: int | None
    required_family_evidence_roles: tuple[str, ...]
    baseline_characterization: Mapping[str, list[str]]
    accepted_differences: tuple[Mapping[str, Any], ...]
    deprecated_yaml_mechanics: tuple[Mapping[str, Any], ...]
    promotion_eligibility: Mapping[str, Any]
    compile_artifacts: Mapping[str, tuple[str, ...]]
    runtime_audit_artifacts: tuple[Mapping[str, str], ...]
    family_evidence_artifacts: tuple[Mapping[str, object], ...]
    evidence_commands: Mapping[str, EvidenceCommand]


@dataclass(frozen=True)
class CommandOutcome:
    status: str
    argv: tuple[str, ...] | None
    exit_code: int | None
    elapsed_seconds: float
    stdout: str
    stderr: str
    waiver: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ValidatedGateRow:
    workflow_family: str
    report: Mapping[str, Any]
    report_valid: bool
    evidence_complete: bool
    non_regressive: bool
    eligible_for_primary_surface: bool
    primary_surface: str
    reasons: tuple[str, ...]
    target_identity: Mapping[str, Any]


def load_parity_targets(path: Path) -> list[ParityTarget]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != TARGETS_SCHEMA_VERSION:
        raise ValueError(f"expected schema_version {TARGETS_SCHEMA_VERSION}")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("targets must be a non-empty array")

    manifest_sha256 = _sha256_file(path.resolve())
    targets: list[ParityTarget] = []
    seen_families: set[str] = set()
    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, Mapping):
            raise ValueError(f"target at index {index} must be an object")
        if "non_regressive" in raw_target:
            raise ValueError("manifest may not author non_regressive")

        workflow_family = _require_string(raw_target, "workflow_family")
        if workflow_family in seen_families:
            raise ValueError(f"duplicate workflow_family `{workflow_family}`")
        seen_families.add(workflow_family)

        baseline = _require_mapping(raw_target, "baseline_characterization")
        normalized_baseline = {
            field_name: _require_non_empty_string_list(baseline, field_name)
            for field_name in BASELINE_FIELDS
        }
        promotion_eligibility = _require_mapping(raw_target, "promotion_eligibility")
        eligible = promotion_eligibility.get("eligible_for_primary_surface")
        if not isinstance(eligible, bool):
            raise ValueError(
                f"promotion_eligibility.eligible_for_primary_surface must be a boolean for `{workflow_family}`"
            )
        if not eligible and not _string_or_none(promotion_eligibility.get("blocked_reason")):
            raise ValueError(
                f"promotion_eligibility.blocked_reason is required for ineligible `{workflow_family}`"
            )

        compile_artifacts = _require_mapping(raw_target, "compile_artifacts")
        normalized_compile_artifacts = {
            "required": tuple(_require_non_empty_string_list(compile_artifacts, "required")),
            "optional": tuple(_require_string_list(compile_artifacts, "optional")),
        }
        evidence_commands = _require_mapping(raw_target, "evidence_commands")
        normalized_commands = {
            role: _parse_command_spec(
                workflow_family=workflow_family,
                role=role,
                raw_value=evidence_commands.get(role),
            )
            for role in COMMAND_ROLES
        }

        targets.append(
            ParityTarget(
                target_manifest_path=path.resolve(),
                target_manifest_sha256=manifest_sha256,
                target_index=index,
                workflow_family=workflow_family,
                candidate=_require_string(raw_target, "candidate"),
                yaml_primary=_require_string(raw_target, "yaml_primary"),
                entry_workflow=_require_string(raw_target, "entry_workflow"),
                provider_externs_file=_optional_string(raw_target, "provider_externs_file"),
                prompt_externs_file=_optional_string(raw_target, "prompt_externs_file"),
                command_boundaries_file=_optional_string(raw_target, "command_boundaries_file"),
                imported_workflow_bundles_file=_optional_string(raw_target, "imported_workflow_bundles_file"),
                readiness_label=_optional_string(raw_target, "readiness_label"),
                lowering_route=_optional_string(raw_target, "lowering_route"),
                lowering_schema_version=_optional_int(raw_target, "lowering_schema_version"),
                required_family_evidence_roles=tuple(
                    _require_string_list(raw_target, "required_family_evidence_roles")
                    if "required_family_evidence_roles" in raw_target
                    else ()
                ),
                baseline_characterization=normalized_baseline,
                accepted_differences=tuple(_require_object_list(raw_target, "accepted_differences")),
                deprecated_yaml_mechanics=tuple(_require_object_list(raw_target, "deprecated_yaml_mechanics")),
                promotion_eligibility=promotion_eligibility,
                compile_artifacts=normalized_compile_artifacts,
                runtime_audit_artifacts=_parse_runtime_audit_artifacts(
                    raw_target,
                    workflow_family=workflow_family,
                ),
                family_evidence_artifacts=_parse_family_evidence_artifacts(
                    raw_target,
                    workflow_family=workflow_family,
                ),
                evidence_commands=normalized_commands,
            )
        )

    return targets


def validate_parity_targets_against_route_readiness(
    targets: Sequence[ParityTarget],
    registry: object,
    repo_root: Path,
) -> list[Mapping[str, object]]:
    """Validate parity target route/readiness identity against the registry."""

    from orchestrator.workflow_lisp.route_readiness import (
        validate_migration_targets_against_route_readiness,
    )

    return validate_migration_targets_against_route_readiness(targets, registry, repo_root)


def run_parity_target(
    target: ParityTarget,
    *,
    output_root: Path,
    repo_root: Path,
    today: date | None = None,
    generated_by: Sequence[str] | None = None,
) -> dict[str, object]:
    resolved_output_root = output_root.resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    logs_root = resolved_output_root / "logs" / target.workflow_family
    logs_root.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, object] = {}
    command_logs: dict[str, object] = {}
    compile_payload: Mapping[str, Any] | None = None
    build_manifest: Mapping[str, Any] | None = None
    compile_artifacts_snapshot: Mapping[str, Any] | None = None
    required_artifact_freshness_snapshot: Mapping[str, Any] | None = None
    compile_manifest_path_snapshot: str | None = None
    compile_manifest_sha256_snapshot: str | None = None
    compiled_workflow_checksum_snapshot: str | None = None
    compile_manifest_snapshot: Mapping[Path, tuple[int, int, int]] | None = None

    for role in COMMAND_ROLES:
        stdout_log = logs_root / f"{role}.stdout.log"
        stderr_log = logs_root / f"{role}.stderr.log"
        if role == "compile":
            compile_manifest_snapshot = _snapshot_build_manifests(repo_root)
        previous_regenerating_family = os.environ.get(
            "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_FAMILY"
        )
        previous_regenerating_report = os.environ.get(
            "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_REPORT"
        )
        previous_regenerating_markdown = os.environ.get(
            "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_MARKDOWN"
        )
        previous_regenerating_index = os.environ.get(
            "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_INDEX"
        )
        if role == "artifact_parity":
            report_path = resolved_output_root / f"{target.workflow_family}.json"
            os.environ[
                "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_FAMILY"
            ] = target.workflow_family
            os.environ[
                "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_REPORT"
            ] = str(report_path.resolve())
            os.environ[
                "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_MARKDOWN"
            ] = str(report_path.with_suffix(".md").resolve())
            os.environ[
                "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_INDEX"
            ] = str((resolved_output_root / "index.json").resolve())
        try:
            outcome = _run_command(
                target.evidence_commands[role],
                role=role,
                repo_root=repo_root,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
        finally:
            if role == "artifact_parity":
                if previous_regenerating_family is None:
                    os.environ.pop(
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_FAMILY",
                        None,
                    )
                else:
                    os.environ[
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_FAMILY"
                    ] = previous_regenerating_family
                if previous_regenerating_report is None:
                    os.environ.pop(
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_REPORT",
                        None,
                    )
                else:
                    os.environ[
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_REPORT"
                    ] = previous_regenerating_report
                if previous_regenerating_markdown is None:
                    os.environ.pop(
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_MARKDOWN",
                        None,
                    )
                else:
                    os.environ[
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_MARKDOWN"
                    ] = previous_regenerating_markdown
                if previous_regenerating_index is None:
                    os.environ.pop(
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_INDEX",
                        None,
                    )
                else:
                    os.environ[
                        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_INDEX"
                    ] = previous_regenerating_index
        command_logs[role] = {
            "stdout": _relative_path(stdout_log, repo_root),
            "stderr": _relative_path(stderr_log, repo_root),
        }
        evidence_record: dict[str, object] = {
            "status": outcome.status,
        }
        if outcome.argv is not None:
            evidence_record["argv"] = list(outcome.argv)
        if outcome.exit_code is not None:
            evidence_record["exit_code"] = outcome.exit_code
        evidence_record["elapsed_seconds"] = round(outcome.elapsed_seconds, 3)
        if outcome.waiver is not None:
            evidence_record["waiver"] = dict(outcome.waiver)
        evidence[role] = evidence_record
        if role == "compile":
            compile_payload, build_manifest = _load_compile_outputs(outcome.stdout, repo_root)
            if compile_payload is None or build_manifest is None:
                recovered_payload, recovered_manifest = (
                    _recover_compile_outputs_from_failed_conformance(
                        target=target,
                        stderr=outcome.stderr,
                        repo_root=repo_root,
                        preexisting_manifests=compile_manifest_snapshot,
                    )
                )
                if compile_payload is None:
                    compile_payload = recovered_payload
                if build_manifest is None:
                    build_manifest = recovered_manifest
            if compile_payload is not None and isinstance(compile_payload.get("build_root"), str):
                build_root = Path(str(compile_payload["build_root"]))
                evidence_record["build_root"] = _relative_or_absolute_path(
                    build_root,
                    repo_root,
                )
                if build_manifest is not None:
                    evidence_record["manifest_path"] = _relative_or_absolute_path(
                        build_root / "manifest.json",
                        repo_root,
                    )
                    compile_artifacts_snapshot = _compile_artifact_report(
                        target=target,
                        build_manifest=build_manifest,
                        build_root=build_root,
                        repo_root=repo_root,
                    )
                    required_artifact_freshness_snapshot = (
                        _build_required_artifact_freshness(
                            compile_artifacts_snapshot,
                            repo_root=repo_root,
                        )
                    )
                    compile_manifest_path_snapshot = _relative_or_absolute_path(
                        build_root / "manifest.json",
                        repo_root,
                    )
                    compile_manifest_sha256_snapshot = _sha256_file(
                        build_root / "manifest.json"
                    )
                    compiled_workflow_checksum_snapshot = _string_or_none(
                        build_manifest.get("compiled_workflow_checksum")
                    )

    evidence["shared_validation"] = _shared_validation_evidence(build_manifest)
    evidence["baseline_characterization"] = {
        "status": "pass",
        **{field_name: list(values) for field_name, values in target.baseline_characterization.items()},
    }

    compile_artifacts = (
        dict(compile_artifacts_snapshot)
        if compile_artifacts_snapshot is not None
        else _compile_artifact_report(
            target=target,
            build_manifest=build_manifest,
            build_root=Path(str(compile_payload["build_root"]))
            if compile_payload and isinstance(compile_payload.get("build_root"), str)
            else None,
            repo_root=repo_root,
        )
    )
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    target_identity = _build_target_identity(target, repo_root=repo_root)
    evidence_freshness = _build_evidence_freshness(
        target=target,
        generated_at=generated_at,
        compile_artifacts=compile_artifacts,
        command_logs=command_logs,
        compile_payload=compile_payload,
        build_manifest=build_manifest,
        required_artifact_freshness=required_artifact_freshness_snapshot,
        compile_manifest_path=compile_manifest_path_snapshot,
        compile_manifest_sha256=compile_manifest_sha256_snapshot,
        compiled_workflow_checksum=compiled_workflow_checksum_snapshot,
        repo_root=repo_root,
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "workflow_family": target.workflow_family,
        "candidate": target.candidate,
        "yaml_primary": target.yaml_primary,
        "tool_version": TOOL_VERSION,
        "dsl_version": "2.14",
        "generated_at": generated_at,
        "generated_by": list(generated_by or ("python", "-m", "orchestrator", "migration-parity")),
        "report_path": _relative_path(resolved_output_root / f"{target.workflow_family}.json", repo_root),
        "target_identity": target_identity,
        "evidence_freshness": evidence_freshness,
        "command_logs": command_logs,
        "accepted_differences": [dict(entry) for entry in target.accepted_differences],
        "deprecated_yaml_mechanics": [dict(entry) for entry in target.deprecated_yaml_mechanics],
        "promotion_eligibility": dict(target.promotion_eligibility),
        "compile_artifacts": compile_artifacts,
        "evidence": evidence,
    }
    workflow_boundary = _load_selected_workflow_boundary_projection(
        target=target,
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    adapter_census = _load_compile_artifact_json(
        artifact_name="adapter_census",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    boundary_authority_report = _load_compile_artifact_json(
        artifact_name="boundary_authority_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    value_flow_census_report = _load_compile_artifact_json(
        artifact_name="value_flow_census_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    consumer_rendering_census_report = _load_compile_artifact_json(
        artifact_name="consumer_rendering_census_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    entry_publication_report = _load_compile_artifact_json(
        artifact_name="entry_publication_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    compatibility_bridge_report = _load_compile_artifact_json(
        artifact_name="compatibility_bridge_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    rendering_cleanup_report = _load_compile_artifact_json(
        artifact_name="rendering_cleanup_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    transition_authoring_report = _load_compile_artifact_json(
        artifact_name="transition_authoring_report",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    g8_deletion_evidence = _load_compile_artifact_json(
        artifact_name="g8_deletion_evidence",
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    if workflow_boundary is not None:
        report["workflow_boundary_projection"] = workflow_boundary
    if isinstance(adapter_census, Mapping):
        report["adapter_census"] = dict(adapter_census)
    if isinstance(boundary_authority_report, Mapping):
        report["boundary_authority_report"] = dict(boundary_authority_report)
    if isinstance(value_flow_census_report, Mapping):
        report["value_flow_census_report"] = dict(value_flow_census_report)
    if isinstance(consumer_rendering_census_report, Mapping):
        report["consumer_rendering_census_report"] = dict(
            consumer_rendering_census_report
        )
    if isinstance(entry_publication_report, Mapping):
        report["entry_publication_report"] = dict(entry_publication_report)
    if isinstance(compatibility_bridge_report, Mapping):
        report["compatibility_bridge_report"] = dict(compatibility_bridge_report)
    if isinstance(rendering_cleanup_report, Mapping):
        report["rendering_cleanup_report"] = dict(rendering_cleanup_report)
    if isinstance(transition_authoring_report, Mapping):
        report["transition_authoring_report"] = dict(transition_authoring_report)
    if isinstance(g8_deletion_evidence, Mapping):
        report["g8_deletion_evidence"] = dict(g8_deletion_evidence)
    if target.required_family_evidence_roles:
        parent_route_identity, parent_family_evidence = _parent_family_evidence(
            target=target,
            evidence=evidence,
            compile_artifacts=compile_artifacts,
            compile_payload=compile_payload,
            build_manifest=build_manifest,
            workflow_boundary=workflow_boundary,
            adapter_census=adapter_census,
            boundary_authority_report=boundary_authority_report,
            g8_deletion_evidence=g8_deletion_evidence,
            repo_root=repo_root,
        )
        report["route_identity"] = parent_route_identity
        evidence.update(parent_family_evidence)
    report["non_regressive"] = compute_non_regressive(report, today=today or date.today())
    return report


def compute_non_regressive(report: Mapping[str, Any], *, today: date) -> bool:
    evidence = _require_report_mapping(report, "evidence")
    for role in REQUIRED_EVIDENCE_ROLES:
        if role not in evidence:
            return False

    if _status(evidence["compile"]) != "pass":
        return False
    if _status(evidence["shared_validation"]) != "pass":
        return False
    if not _dry_run_evidence_passes(evidence, today=today):
        return False

    smoke = _require_report_mapping(evidence, "smoke_or_integration")
    smoke_status = _status(smoke)
    if smoke_status == "waived":
        if not _waiver_is_valid(smoke.get("waiver"), today=today, require_targeted_evidence=True):
            return False
    elif smoke_status != "pass":
        return False

    baseline = _require_report_mapping(evidence, "baseline_characterization")
    for field_name in BASELINE_FIELDS:
        values = baseline.get(field_name)
        if not isinstance(values, list) or not values:
            return False

    for role in ("output_contract_parity", "terminal_state_parity", "artifact_parity", "resume_parity"):
        if _status(evidence[role]) != "pass":
            return False

    target_identity = _require_report_mapping(report, "target_identity")
    required_family_roles = target_identity.get("required_family_evidence_roles", ())
    if required_family_roles:
        if not isinstance(required_family_roles, list) or not all(
            isinstance(role, str) and role for role in required_family_roles
        ):
            return False
        route_identity = report.get("route_identity")
        if not isinstance(route_identity, Mapping):
            return False
        if route_identity.get("readiness_label") != target_identity.get("readiness_label"):
            return False
        if route_identity.get("lowering_route") != target_identity.get("lowering_route"):
            return False
        if route_identity.get("lowering_schema_version") != target_identity.get(
            "lowering_schema_version"
        ):
            return False
        for role in required_family_roles:
            role_evidence = evidence.get(role)
            if not isinstance(role_evidence, Mapping) or _status(role_evidence) != "pass":
                return False

    compile_artifacts = _require_report_mapping(report, "compile_artifacts")
    required_artifacts = _require_report_mapping(compile_artifacts, "required")
    for artifact in required_artifacts.values():
        if _status(artifact) != "pass":
            return False

    for mechanic in _require_report_object_list(report, "deprecated_yaml_mechanics"):
        if _string_or_none(mechanic.get("replacement")):
            continue
        if _waiver_is_valid(mechanic.get("waiver"), today=today, require_targeted_evidence=False):
            continue
        return False

    return True


def _dry_run_evidence_passes(evidence: Mapping[str, object], *, today: date) -> bool:
    dry_run = _require_report_mapping(evidence, "dry_run")
    dry_run_status = _status(dry_run)
    if dry_run_status == "pass":
        return True
    if dry_run_status != "waived":
        return False

    waiver = dry_run.get("waiver")
    if not _waiver_is_valid(waiver, today=today, require_targeted_evidence=True):
        return False
    targeted_roles = waiver.get("targeted_evidence") if isinstance(waiver, Mapping) else None
    if not isinstance(targeted_roles, list):
        return False
    runtime_substitute_roles = {"smoke_or_integration", "parent_callable_smoke"}
    if not set(targeted_roles).issubset(runtime_substitute_roles):
        return False
    return all(
        isinstance(evidence.get(role), Mapping) and _status(evidence[role]) == "pass"
        for role in targeted_roles
    )


def render_parity_markdown(report: Mapping[str, Any]) -> str:
    primary_surface = _primary_surface_for_report(report)
    promotion = _require_report_mapping(report, "promotion_eligibility")
    evidence = _require_report_mapping(report, "evidence")
    compile_artifacts = _require_report_mapping(report, "compile_artifacts")
    baseline = _require_report_mapping(evidence, "baseline_characterization")

    lines = [
        f"# Parity Report: {report['workflow_family']}",
        "",
        f"- Candidate: `{report['candidate']}`",
        f"- YAML primary: `{report['yaml_primary']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Non-regressive: `{str(bool(report['non_regressive'])).lower()}`",
        f"- Promotion eligible: `{str(bool(promotion['eligible_for_primary_surface'])).lower()}`",
        f"- Primary surface: `{primary_surface}`",
        "",
        "## Baseline Characterization",
        f"- Inputs: {', '.join(f'`{value}`' for value in baseline['inputs'])}",
        f"- Outputs: {', '.join(f'`{value}`' for value in baseline['outputs'])}",
        f"- Terminal states: {', '.join(f'`{value}`' for value in baseline['terminal_states'])}",
        f"- Artifacts: {', '.join(f'`{value}`' for value in baseline['artifacts'])}",
        f"- Resume behavior: {', '.join(f'`{value}`' for value in baseline['resume_behavior'])}",
        "",
        "## Evidence",
    ]
    for role in REQUIRED_EVIDENCE_ROLES:
        role_evidence = _require_report_mapping(evidence, role)
        lines.append(f"- `{role}`: `{_status(role_evidence)}`")

    lines.extend(
        [
            "",
            "## Compile Artifacts",
        ]
    )
    for bucket in ("required", "optional"):
        bucket_items = _require_report_mapping(compile_artifacts, bucket)
        for artifact_name, artifact_data in sorted(bucket_items.items()):
            artifact_mapping = _require_report_mapping(bucket_items, artifact_name)
            artifact_path = artifact_mapping.get("path")
            artifact_suffix = f" (`{artifact_path}`)" if artifact_path else ""
            lines.append(f"- `{bucket}.{artifact_name}`: `{_status(artifact_mapping)}`{artifact_suffix}")

    lines.extend(
        [
            "",
            "## Deprecated YAML Mechanics",
        ]
    )
    mechanics = _require_report_object_list(report, "deprecated_yaml_mechanics")
    if not mechanics:
        lines.append("- None")
    else:
        for mechanic in mechanics:
            mechanic_name = mechanic.get("mechanic", "unknown")
            replacement = _string_or_none(mechanic.get("replacement"))
            waiver = mechanic.get("waiver")
            if replacement:
                lines.append(f"- `{mechanic_name}` -> `{replacement}`")
            elif isinstance(waiver, Mapping):
                lines.append(
                    f"- `{mechanic_name}` waived by `{waiver.get('owner', 'unknown')}` until `{waiver.get('expiry', 'unknown')}`"
                )
            else:
                lines.append(f"- `{mechanic_name}` unresolved")

    return "\n".join(lines) + "\n"


def render_parity_index(
    reports: Sequence[ValidatedGateRow],
) -> dict[str, object]:
    rows = []
    for gate_row in reports:
        if not isinstance(gate_row, ValidatedGateRow):
            raise TypeError("render_parity_index expects ValidatedGateRow inputs")
        report = gate_row.report
        report_path = Path(str(report["report_path"]))
        rows.append(
            {
                "workflow_family": report["workflow_family"],
                "candidate": report["candidate"],
                "yaml_primary": report["yaml_primary"],
                "json_report": str(report_path),
                "markdown_report": str(report_path.with_suffix(".md")),
                "report_valid": gate_row.report_valid,
                "evidence_complete": gate_row.evidence_complete,
                "non_regressive": gate_row.non_regressive,
                "promotion_eligibility": dict(_require_report_mapping(report, "promotion_eligibility")),
                "primary_surface": gate_row.primary_surface,
            }
        )
    rows.sort(key=lambda row: str(row["workflow_family"]))
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "targets": rows,
    }


def _validate_report_for_gate(
    report: Mapping[str, Any],
    *,
    target: ParityTarget,
    targets_file: Path,
    repo_root: Path,
    today: date,
    fail_closed_for_stale_evidence: bool = False,
) -> ValidatedGateRow:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(f"report schema_version must be {REPORT_SCHEMA_VERSION}")

    gate_owned_fields = sorted(GATE_OWNED_REPORT_FIELDS.intersection(report.keys()))
    if gate_owned_fields:
        raise ValueError(
            "report may not publish gate-owned fields: " + ", ".join(gate_owned_fields)
        )

    _require_report_contract(report)

    target_identity = _require_report_mapping(report, "target_identity")
    expected_identity = _build_target_identity(
        target,
        repo_root=repo_root,
        targets_file=targets_file,
    )
    _require_exact_mapping_match(
        target_identity,
        expected_identity,
        label="target_identity",
    )

    expected_non_regressive = compute_non_regressive(report, today=today)
    if bool(report.get("non_regressive")) != expected_non_regressive:
        raise ValueError("report non_regressive does not match recomputed non_regressive")

    evidence_complete, reasons = _validate_required_evidence_completeness(report)
    evidence_freshness = _require_report_mapping(report, "evidence_freshness")
    freshness_complete, freshness_reasons = _validate_evidence_freshness(
        report,
        evidence_freshness=evidence_freshness,
        repo_root=repo_root,
        fail_closed=fail_closed_for_stale_evidence,
    )
    evidence_complete = evidence_complete and freshness_complete
    reasons.extend(freshness_reasons)
    promotion = _require_report_mapping(report, "promotion_eligibility")
    eligible_for_primary_surface = bool(promotion.get("eligible_for_primary_surface"))
    if not expected_non_regressive:
        reasons.append("non_regressive=false")
    if not eligible_for_primary_surface:
        reasons.append(
            _string_or_none(promotion.get("blocked_reason")) or "eligible_for_primary_surface=false"
        )
    primary_surface = _primary_surface_for_non_regressive_and_eligibility(
        non_regressive=expected_non_regressive,
        eligible_for_primary_surface=eligible_for_primary_surface,
    )
    return ValidatedGateRow(
        workflow_family=str(report["workflow_family"]),
        report=report,
        report_valid=True,
        evidence_complete=evidence_complete,
        non_regressive=expected_non_regressive,
        eligible_for_primary_surface=eligible_for_primary_surface,
        primary_surface=primary_surface,
        reasons=tuple(reasons),
        target_identity=target_identity,
    )


def render_gate_evaluation(
    *,
    gate_rows: Sequence[ValidatedGateRow],
    gate_mode: str,
    targets_file: Path,
    selected_targets: Sequence[str],
    repo_root: Path,
) -> dict[str, object]:
    ordered_rows = sorted(gate_rows, key=lambda row: row.workflow_family)
    selected_set = set(selected_targets)
    gated_rows = [
        row for row in ordered_rows if not selected_set or row.workflow_family in selected_set
    ]
    results = [
        {
            "workflow_family": row.workflow_family,
            "report_path": str(row.report["report_path"]),
            "target_identity": dict(row.target_identity),
            "report_valid": row.report_valid,
            "evidence_complete": row.evidence_complete,
            "non_regressive": row.non_regressive,
            "eligible_for_primary_surface": row.eligible_for_primary_surface,
            "primary_surface": _gate_primary_surface_for_row(row),
            "reasons": list(row.reasons),
        }
        for row in ordered_rows
    ]
    selected_identity_rows = [
        dict(row.target_identity)
        for row in ordered_rows
        if row.workflow_family in set(selected_targets)
    ]
    return {
        "schema_version": GATE_EVALUATION_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "gate_mode": gate_mode,
        "targets_file": _relative_or_absolute_path(targets_file, repo_root),
        "selected_targets": list(selected_targets),
        "selected_target_identities": selected_identity_rows,
        "results": results,
        "overall_pass": all(_gate_row_passes(row, gate_mode=gate_mode) for row in gated_rows),
    }


def validate_report_for_target(
    report: Mapping[str, Any],
    *,
    target: ParityTarget,
    targets_file: Path,
    repo_root: Path,
    today: date | None = None,
    fail_closed_for_stale_evidence: bool = False,
) -> ValidatedGateRow:
    return _validate_report_for_gate(
        report,
        target=target,
        targets_file=targets_file,
        repo_root=repo_root,
        today=today or date.today(),
        fail_closed_for_stale_evidence=fail_closed_for_stale_evidence,
    )


def derive_primary_surface(
    *,
    non_regressive: bool,
    eligible_for_primary_surface: bool,
) -> str:
    return _primary_surface_for_non_regressive_and_eligibility(
        non_regressive=non_regressive,
        eligible_for_primary_surface=eligible_for_primary_surface,
    )


def write_reports(
    reports: Sequence[Mapping[str, Any]],
    *,
    output_root: Path,
    repo_root: Path,
    gate_rows: Sequence[ValidatedGateRow],
    gate_evaluation: Mapping[str, Any],
) -> tuple[Path, Path]:
    resolved_output_root = output_root.resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    for report in reports:
        report_path = repo_root / str(report["report_path"])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        markdown_path = report_path.with_suffix(".md")
        markdown_path.write_text(render_parity_markdown(report), encoding="utf-8")

    index_path = resolved_output_root / "index.json"
    index_path.write_text(
        json.dumps(render_parity_index(gate_rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    gate_evaluation_path = resolved_output_root / "gate_evaluation.json"
    gate_evaluation_path.write_text(
        json.dumps(gate_evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index_path, gate_evaluation_path


def run_migration_parity(
    *,
    targets_file: Path,
    output_root: Path,
    selected_targets: Sequence[str] | None = None,
    repo_root: Path,
    today: date | None = None,
    generated_by: Sequence[str] | None = None,
    gate_mode: str = "advisory",
) -> dict[str, object]:
    evaluation_date = today or date.today()
    all_targets = load_parity_targets(targets_file)
    selected_target_names = (
        list(selected_targets)
        if selected_targets
        else [target.workflow_family for target in all_targets]
    )
    targets = list(all_targets)
    if selected_targets:
        selected = set(selected_targets)
        missing = sorted(selected.difference(target.workflow_family for target in all_targets))
        if missing:
            raise ValueError(f"unknown workflow_family selection(s): {', '.join(missing)}")
        targets = [target for target in targets if target.workflow_family in selected]

    reports = [
        run_parity_target(
            target,
            output_root=output_root,
            repo_root=repo_root,
            today=evaluation_date,
            generated_by=generated_by,
        )
        for target in targets
    ]
    gate_rows = _validated_gate_rows_for_targets(
        all_targets,
        refreshed_reports=reports,
        output_root=output_root,
        targets_file=targets_file,
        repo_root=repo_root,
        today=evaluation_date,
    )
    gate_evaluation = render_gate_evaluation(
        gate_rows=gate_rows,
        gate_mode=gate_mode,
        targets_file=targets_file,
        selected_targets=selected_target_names,
        repo_root=repo_root,
    )
    index_path, gate_evaluation_path = write_reports(
        reports,
        output_root=output_root,
        repo_root=repo_root,
        gate_rows=gate_rows,
        gate_evaluation=gate_evaluation,
    )
    non_regressive_targets = sorted(
        report["workflow_family"] for report in reports if bool(report["non_regressive"])
    )
    regressive_targets = sorted(
        report["workflow_family"] for report in reports if not bool(report["non_regressive"])
    )
    return {
        "targets_processed": len(reports),
        "reports_written": len(reports),
        "non_regressive_targets": non_regressive_targets,
        "regressive_targets": regressive_targets,
        "gate_mode": gate_mode,
        "overall_pass": bool(gate_evaluation["overall_pass"]),
        "index_path": _relative_path(index_path, repo_root),
        "gate_evaluation_path": _relative_path(gate_evaluation_path, repo_root),
    }


def _validated_gate_rows_for_targets(
    targets: Sequence[ParityTarget],
    *,
    refreshed_reports: Sequence[Mapping[str, Any]],
    output_root: Path,
    targets_file: Path,
    repo_root: Path,
    today: date,
) -> list[ValidatedGateRow]:
    refreshed_by_family = {
        str(report["workflow_family"]): report for report in refreshed_reports
    }
    gate_rows: list[ValidatedGateRow] = []
    for target in targets:
        report = refreshed_by_family.get(target.workflow_family)
        if report is None:
            report = _load_existing_report(
                output_root / f"{target.workflow_family}.json",
                workflow_family=target.workflow_family,
            )
        gate_rows.append(
            _validate_report_for_gate(
                report,
                target=target,
                targets_file=targets_file,
                repo_root=repo_root,
                today=today,
                fail_closed_for_stale_evidence=target.workflow_family not in refreshed_by_family,
            )
        )
    return gate_rows


def _load_existing_report(path: Path, *, workflow_family: str) -> Mapping[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            "cannot refresh aggregate parity index without an existing report for "
            f"unselected workflow_family `{workflow_family}` at `{path}`"
        ) from exc

    if not isinstance(report, Mapping):
        raise ValueError(f"existing report for `{workflow_family}` at `{path}` must be a JSON object")
    if report.get("workflow_family") != workflow_family:
        raise ValueError(
            f"existing report at `{path}` does not match workflow_family `{workflow_family}`"
        )
    return report


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_json_bytes(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()}"


def _build_target_identity(
    target: ParityTarget,
    *,
    repo_root: Path,
    targets_file: Path | None = None,
) -> dict[str, object]:
    candidate_path = repo_root / target.candidate
    identity: dict[str, object] = {
        "targets_schema_version": TARGETS_SCHEMA_VERSION,
        "target_manifest_path": _relative_or_absolute_path((targets_file or target.target_manifest_path), repo_root),
        "target_manifest_sha256": target.target_manifest_sha256,
        "target_index": target.target_index,
        "workflow_family": target.workflow_family,
        "candidate_path": target.candidate,
        "candidate_sha256": _sha256_file(candidate_path),
        "yaml_primary_path": target.yaml_primary,
        "entry_workflow": target.entry_workflow,
    }
    if target.readiness_label is not None:
        identity["readiness_label"] = target.readiness_label
    if target.lowering_route is not None:
        identity["lowering_route"] = target.lowering_route
    if target.lowering_schema_version is not None:
        identity["lowering_schema_version"] = target.lowering_schema_version
    if target.required_family_evidence_roles:
        identity["required_family_evidence_roles"] = list(
            target.required_family_evidence_roles
        )
    if target.runtime_audit_artifacts:
        identity["runtime_audit_artifacts"] = [dict(entry) for entry in target.runtime_audit_artifacts]
    if target.family_evidence_artifacts:
        identity["family_evidence_artifacts"] = [
            dict(entry) for entry in target.family_evidence_artifacts
        ]
    return identity


def _build_required_artifact_freshness(
    compile_artifacts: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, object]:
    required = _require_report_mapping(compile_artifacts, "required")
    freshness: dict[str, object] = {}
    for artifact_name, artifact_value in required.items():
        artifact = _require_report_mapping(required, artifact_name)
        artifact_path = _string_or_none(artifact.get("path"))
        artifact_entry: dict[str, object] = {
            "status": _status(artifact),
            "path": artifact_path,
        }
        if artifact_path:
            resolved_path = repo_root / artifact_path
            if resolved_path.exists():
                artifact_entry["sha256"] = _sha256_file(resolved_path)
        freshness[artifact_name] = artifact_entry
    return freshness


def _build_evidence_refs(
    command_logs: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, object]:
    refs: dict[str, object] = {}
    for role, raw_paths in command_logs.items():
        paths = _require_report_mapping(command_logs, str(role))
        role_refs: dict[str, object] = {}
        for stream in ("stdout", "stderr"):
            stream_path = _string_or_none(paths.get(stream))
            if not stream_path:
                continue
            resolved_path = repo_root / stream_path
            role_refs[stream] = {
                "path": stream_path,
                "sha256": _sha256_file(resolved_path) if resolved_path.exists() else None,
            }
        refs[str(role)] = role_refs
    return refs


def _build_runtime_audit_artifact_freshness(
    runtime_audit_artifacts: Sequence[Mapping[str, str]],
    *,
    repo_root: Path,
) -> dict[str, object]:
    freshness: dict[str, object] = {}
    for artifact in runtime_audit_artifacts:
        artifact_id = str(artifact["artifact_id"])
        artifact_path = str(artifact["path"])
        resolved_path = repo_root / artifact_path
        entry: dict[str, object] = {
            "path": artifact_path,
            "transition_name": artifact["transition_name"],
            "resource_kind": artifact["resource_kind"],
            "exists": resolved_path.exists(),
        }
        if resolved_path.exists():
            entry["sha256"] = _sha256_file(resolved_path)
        freshness[artifact_id] = entry
    return freshness


def _build_family_evidence_artifact_freshness(
    family_evidence_artifacts: Sequence[Mapping[str, object]],
    *,
    repo_root: Path,
) -> dict[str, object]:
    freshness: dict[str, object] = {}
    for artifact in family_evidence_artifacts:
        artifact_id = str(artifact["artifact_id"])
        artifact_path = str(artifact["path"])
        resolved_path = repo_root / artifact_path
        entry: dict[str, object] = {
            "path": artifact_path,
            "evidence_role": str(artifact["evidence_role"]),
            "declared_schema_version": str(artifact["schema_version"]),
            "exists": resolved_path.exists(),
        }
        if resolved_path.exists():
            entry["sha256"] = _sha256_file(resolved_path)
        freshness[artifact_id] = entry
    return freshness


def _build_evidence_freshness(
    *,
    target: ParityTarget,
    generated_at: str,
    compile_artifacts: Mapping[str, Any],
    command_logs: Mapping[str, Any],
    compile_payload: Mapping[str, Any] | None,
    build_manifest: Mapping[str, Any] | None,
    required_artifact_freshness: Mapping[str, Any] | None = None,
    compile_manifest_path: str | None = None,
    compile_manifest_sha256: str | None = None,
    compiled_workflow_checksum: str | None = None,
    repo_root: Path,
) -> dict[str, object]:
    freshness: dict[str, object] = {
        "generated_at": generated_at,
        "required_artifacts": dict(required_artifact_freshness)
        if required_artifact_freshness is not None
        else _build_required_artifact_freshness(
            compile_artifacts,
            repo_root=repo_root,
        ),
        "evidence_refs": _build_evidence_refs(command_logs, repo_root=repo_root),
    }
    if target.runtime_audit_artifacts:
        freshness["runtime_audit_artifacts"] = _build_runtime_audit_artifact_freshness(
            target.runtime_audit_artifacts,
            repo_root=repo_root,
        )
    if target.family_evidence_artifacts:
        freshness["family_evidence_artifacts"] = _build_family_evidence_artifact_freshness(
            target.family_evidence_artifacts,
            repo_root=repo_root,
        )
    manifest_path = compile_manifest_path
    manifest_sha256 = compile_manifest_sha256
    checksum = compiled_workflow_checksum
    if manifest_path is None and isinstance(compile_payload, Mapping) and isinstance(
        compile_payload.get("build_root"), str
    ):
        resolved_manifest_path = Path(str(compile_payload["build_root"])) / "manifest.json"
        if resolved_manifest_path.exists():
            manifest_path = _relative_or_absolute_path(
                resolved_manifest_path,
                repo_root,
            )
            manifest_sha256 = _sha256_file(resolved_manifest_path)
    if checksum is None and isinstance(build_manifest, Mapping):
        checksum = _string_or_none(build_manifest.get("compiled_workflow_checksum"))
    if manifest_path:
        freshness["compile_manifest_path"] = manifest_path
    if manifest_sha256:
        freshness["compile_manifest_sha256"] = manifest_sha256
    if checksum:
        freshness["compiled_workflow_checksum"] = checksum
    return freshness


def _load_selected_workflow_boundary_projection(
    *,
    target: ParityTarget,
    build_manifest: Mapping[str, Any] | None,
    build_root: Path | None,
    repo_root: Path,
) -> dict[str, object] | None:
    if build_manifest is None:
        return None
    artifact_paths = dict(build_manifest.get("artifact_paths", {}))
    boundary_path = _resolve_build_artifact_path(
        artifact_paths.get("workflow_boundary_projection"),
        build_root=build_root,
        repo_root=repo_root,
    )
    if boundary_path is None or not boundary_path.exists():
        return None
    try:
        payload = json.loads(boundary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    workflows = payload.get("workflows")
    if not isinstance(workflows, list):
        return None
    selected = next(
        (
            item
            for item in workflows
            if isinstance(item, Mapping)
            and (
                item.get("display_name") == target.entry_workflow
                or item.get("workflow_name") == target.entry_workflow
                or str(item.get("workflow_name", "")).endswith(f"::{target.entry_workflow}")
            )
        ),
        None,
    )
    if not isinstance(selected, Mapping):
        return None
    boundary = selected.get("boundary")
    if not isinstance(boundary, Mapping):
        return None
    return {
        "workflow_name": str(selected.get("workflow_name")),
        "display_name": str(selected.get("display_name")),
        "public_input_names": sorted(
            name
            for name in boundary.get("public_input_names", ())
            if isinstance(name, str)
        ),
        "private_runtime_context_bindings": [
            {
                key: value
                for key, value in binding.items()
                if key
                in {
                    "binding_id",
                    "source_param_name",
                    "context_family",
                    "bridge_class",
                    "derived_phase_identity",
                    "generated_input_names",
                }
            }
            for binding in boundary.get("private_runtime_context_bindings", ())
            if isinstance(binding, Mapping)
        ],
        "private_managed_write_root_inputs": sorted(
            name
            for name in boundary.get("private_managed_write_root_inputs", ())
            if isinstance(name, str)
        ),
        "private_compatibility_bridge_inputs": sorted(
            name
            for name in boundary.get("private_compatibility_bridge_inputs", ())
            if isinstance(name, str)
        ),
    }


def _load_compile_artifact_json(
    *,
    artifact_name: str,
    build_manifest: Mapping[str, Any] | None,
    build_root: Path | None,
    repo_root: Path,
) -> Mapping[str, Any] | None:
    if build_manifest is None:
        return None
    artifact_paths = dict(build_manifest.get("artifact_paths", {}))
    artifact_path = _resolve_build_artifact_path(
        artifact_paths.get(artifact_name),
        build_root=build_root,
        repo_root=repo_root,
    )
    if artifact_path is None or not artifact_path.exists():
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _parent_family_evidence(
    *,
    target: ParityTarget,
    evidence: Mapping[str, object],
    compile_artifacts: Mapping[str, Any],
    compile_payload: Mapping[str, Any] | None,
    build_manifest: Mapping[str, Any] | None,
    workflow_boundary: Mapping[str, Any] | None,
    adapter_census: Mapping[str, Any] | None,
    boundary_authority_report: Mapping[str, Any] | None,
    g8_deletion_evidence: Mapping[str, Any] | None,
    repo_root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    route_identity = {
        "readiness_label": target.readiness_label,
        "lowering_route": _reported_lowering_route(
            compile_payload=compile_payload,
            build_manifest=build_manifest,
        ),
        "lowering_schema_version": _reported_lowering_schema_version(
            build_manifest=build_manifest,
        ),
    }
    role_evidence: dict[str, object] = {}
    for role in target.required_family_evidence_roles:
        if role == "route_identity":
            role_evidence[role] = _route_identity_evidence(
                target=target,
                route_identity=route_identity,
            )
        elif role == "parent_callable_compile":
            role_evidence[role] = _parent_callable_compile_evidence(
                target=target,
                evidence=evidence,
                compile_artifacts=compile_artifacts,
                compile_payload=compile_payload,
                build_manifest=build_manifest,
                route_identity=route_identity,
                repo_root=repo_root,
            )
        elif role == "parent_callable_smoke":
            role_evidence[role] = _parent_callable_smoke_evidence(evidence)
        elif role == "resource_transition_parity":
            role_evidence[role] = _resource_transition_parity_evidence(
                target=target,
                g8_deletion_evidence=g8_deletion_evidence,
                repo_root=repo_root,
            )
        elif role == "projection_retirement_parity":
            role_evidence[role] = _projection_retirement_parity_evidence(
                target=target,
                compile_payload=compile_payload,
                build_manifest=build_manifest,
                adapter_census=adapter_census,
                g8_deletion_evidence=g8_deletion_evidence,
                repo_root=repo_root,
            )
        elif role == "view_retirement_parity":
            role_evidence[role] = _view_retirement_parity_evidence(
                target=target,
                adapter_census=adapter_census,
                g8_deletion_evidence=g8_deletion_evidence,
                repo_root=repo_root,
            )
        elif role == "public_private_boundary_parity":
            role_evidence[role] = _public_private_boundary_parity_evidence(
                workflow_boundary,
                boundary_authority_report=boundary_authority_report,
            )
        elif role == "boundary_artifact_justifications":
            role_evidence[role] = _boundary_artifact_justification_evidence(
                target=target,
                compile_artifacts=compile_artifacts,
                workflow_boundary=workflow_boundary,
                route_identity=route_identity,
            )
        else:
            role_evidence[role] = {
                "status": "fail",
                "reason": f"unknown required parent-family evidence role `{role}`",
            }
    return route_identity, role_evidence


def _reported_lowering_schema_version(
    *,
    build_manifest: Mapping[str, Any] | None,
) -> int | None:
    if isinstance(build_manifest, Mapping):
        schema_version = build_manifest.get("lowering_schema_version")
        if isinstance(schema_version, int):
            return schema_version
    return None


def _reported_lowering_route(
    *,
    compile_payload: Mapping[str, Any] | None,
    build_manifest: Mapping[str, Any] | None,
) -> str | None:
    if isinstance(compile_payload, Mapping):
        route = compile_payload.get("lowering_route")
        if isinstance(route, str) and route:
            return route
    if isinstance(build_manifest, Mapping):
        route = build_manifest.get("lowering_route")
        if isinstance(route, str) and route:
            return route
    return None


def _route_identity_evidence(
    *,
    target: ParityTarget,
    route_identity: Mapping[str, Any],
) -> dict[str, object]:
    reasons: list[str] = []
    if route_identity.get("readiness_label") != target.readiness_label:
        reasons.append("readiness_label mismatch")
    if route_identity.get("lowering_route") != target.lowering_route:
        reasons.append("lowering_route mismatch")
    if route_identity.get("lowering_schema_version") != target.lowering_schema_version:
        reasons.append("lowering_schema_version mismatch")
    return {
        "status": "fail" if reasons else "pass",
        "readiness_label": route_identity.get("readiness_label"),
        "lowering_route": route_identity.get("lowering_route"),
        "lowering_schema_version": route_identity.get("lowering_schema_version"),
        **({"reasons": reasons} if reasons else {}),
    }


def _parent_callable_compile_evidence(
    *,
    target: ParityTarget,
    evidence: Mapping[str, object],
    compile_artifacts: Mapping[str, Any],
    compile_payload: Mapping[str, Any] | None,
    build_manifest: Mapping[str, Any] | None,
    route_identity: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, object]:
    reasons: list[str] = []
    if _status(evidence.get("compile")) != "pass":
        reasons.append("compile evidence is not passing")
    if _status(evidence.get("shared_validation")) != "pass":
        reasons.append("shared validation evidence is not passing")
    if _route_identity_evidence(target=target, route_identity=route_identity)["status"] != "pass":
        reasons.append("route identity is not passing")
    required_artifacts = _require_report_mapping(compile_artifacts, "required")
    missing_or_failed = [
        str(artifact_name)
        for artifact_name, artifact in required_artifacts.items()
        if not isinstance(artifact, Mapping) or _status(artifact) != "pass"
    ]
    if missing_or_failed:
        reasons.append("required compile artifact(s) not passing: " + ", ".join(missing_or_failed))
    reasons.extend(
        _parent_loop_control_reasons(
            target=target,
            compile_payload=compile_payload,
            build_manifest=build_manifest,
            repo_root=repo_root,
        )
    )
    return {
        "status": "fail" if reasons else "pass",
        "readiness_label": target.readiness_label,
        "lowering_route": target.lowering_route,
        "lowering_schema_version": route_identity.get("lowering_schema_version"),
        **({"reasons": reasons} if reasons else {}),
    }


def _parent_loop_control_reasons(
    *,
    target: ParityTarget,
    compile_payload: Mapping[str, Any] | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> list[str]:
    if target.entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return []
    build_root = (
        Path(str(compile_payload["build_root"]))
        if isinstance(compile_payload, Mapping)
        and isinstance(compile_payload.get("build_root"), str)
        else None
    )
    artifact_paths = dict(build_manifest.get("artifact_paths", {})) if build_manifest else {}
    core_ast_path = _resolve_build_artifact_path(
        artifact_paths.get("core_workflow_ast"),
        build_root=build_root,
        repo_root=repo_root,
    )
    reason = "parent drain entrypoint does not own loop control"
    if core_ast_path is None or not core_ast_path.exists():
        return [reason]
    try:
        core_ast = json.loads(core_ast_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [reason]

    top_level = core_ast.get("body") if isinstance(core_ast, Mapping) else None
    if not isinstance(top_level, list):
        return [reason]
    top_level_calls = {
        alias
        for node in top_level
        for alias in _core_ast_call_aliases(node)
    }
    if "std/drain::backlog-drain" in top_level_calls:
        return []
    repeat_nodes = [
        node
        for node in top_level
        if isinstance(node, Mapping) and str(node.get("kind")) == "repeat_until"
    ]
    legacy_loop_proof_alias = "lisp_frontend_design_delta/drain::drain-loop-proof"
    if legacy_loop_proof_alias in top_level_calls or not repeat_nodes:
        return [reason]

    loop_aliases = {
        alias
        for repeat_node in repeat_nodes
        for alias in _core_ast_call_aliases(repeat_node)
    }
    required_exact_aliases = {
        "lisp_frontend_design_delta/selector::select-next-work",
        "lisp_frontend_design_delta/work_item::run-work-item",
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture",
    }
    has_projection = any(str(alias).endswith("::project-selector-action.v1") for alias in loop_aliases)
    has_legacy_selector_action = (
        "lisp_frontend_design_delta/selector::select-next-action" in loop_aliases
    )
    if (
        not required_exact_aliases.issubset(loop_aliases)
        or not has_projection
        or has_legacy_selector_action
    ):
        return [reason]
    return []


def _core_ast_call_aliases(node: object) -> list[str]:
    aliases: list[str] = []
    if isinstance(node, Mapping):
        alias = node.get("call_alias")
        if isinstance(alias, str):
            aliases.append(alias)
        workflow_call = node.get("workflow_call")
        if isinstance(workflow_call, Mapping):
            workflow = workflow_call.get("workflow")
            if isinstance(workflow, str):
                aliases.append(workflow)
        for value in node.values():
            aliases.extend(_core_ast_call_aliases(value))
    elif isinstance(node, list):
        for item in node:
            aliases.extend(_core_ast_call_aliases(item))
    return aliases


def _parent_callable_smoke_evidence(evidence: Mapping[str, object]) -> dict[str, object]:
    smoke = evidence.get("smoke_or_integration")
    if isinstance(smoke, Mapping) and _status(smoke) == "pass":
        return {
            "status": "pass",
            "source_role": "smoke_or_integration",
        }
    return {
        "status": "fail",
        "reason": "smoke_or_integration evidence is not passing",
    }


def _resource_transition_parity_evidence(
    *,
    target: ParityTarget,
    g8_deletion_evidence: Mapping[str, Any] | None = None,
    repo_root: Path,
) -> dict[str, object]:
    if target.command_boundaries_file is None:
        return {
            "status": "fail",
            "reason": "target does not declare command_boundaries_file",
        }
    manifest_path = repo_root / target.command_boundaries_file
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "fail",
            "reason": f"command boundary manifest is unreadable: {exc}",
        }
    if not isinstance(manifest, Mapping):
        return {
            "status": "fail",
            "reason": "command boundary manifest is not an object",
        }
    deleted_rows, deletion_reasons = _validated_design_delta_g8_deleted_rows(
        target=target,
        g8_deletion_evidence=g8_deletion_evidence,
        required_rows=DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS,
    )
    helper_rows: dict[str, object] = {}
    reasons: list[str] = []
    reasons.extend(deletion_reasons)
    for helper in DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS:
        row = manifest.get(helper)
        if isinstance(row, Mapping):
            helper_rows[helper] = {
                "status": "fail",
                "reason": "deleted helper still present in active manifest",
            }
            reasons.append(f"deleted helper `{helper}` is still present in the active manifest")
            continue
        helper_status = "pass" if helper in deleted_rows else "fail"
        helper_rows[helper] = {
            "status": helper_status,
            "reason": "deleted via g8_deletion_evidence"
            if helper_status == "pass"
            else "g8_deletion_evidence does not record helper deletion",
        }
        if helper_status != "pass":
            reasons.append(f"g8_deletion_evidence does not record deleted helper `{helper}`")
    runtime_audit = _runtime_audit_transition_parity_evidence(
        target=target,
        repo_root=repo_root,
    )
    if runtime_audit["status"] != "pass":
        reasons.append(
            runtime_audit.get("reason")
            if isinstance(runtime_audit.get("reason"), str)
            else "runtime audit evidence failed"
        )
    return {
        "status": "fail" if reasons else "pass",
        "helpers": helper_rows,
        "g8_deleted_rows": sorted(deleted_rows),
        "runtime_audit": runtime_audit,
        **({"reasons": reasons} if reasons else {}),
    }


def _runtime_audit_transition_parity_evidence(
    *,
    target: ParityTarget,
    repo_root: Path,
) -> dict[str, object]:
    if not target.runtime_audit_artifacts:
        return {
            "status": "fail",
            "reason": "target does not declare runtime_audit_artifacts",
        }
    artifacts: dict[str, object] = {}
    reasons: list[str] = []
    for artifact in target.runtime_audit_artifacts:
        artifact_id = artifact["artifact_id"]
        artifact_path = repo_root / artifact["path"]
        artifact_status = "pass"
        artifact_reasons: list[str] = []
        if not artifact_path.exists():
            artifact_status = "fail"
            artifact_reasons.append(f"missing runtime audit artifact `{artifact_id}`")
            artifacts[artifact_id] = {
                "status": artifact_status,
                "path": artifact["path"],
                "transition_name": artifact["transition_name"],
                "resource_kind": artifact["resource_kind"],
                "reason": artifact_reasons[0],
            }
            reasons.extend(artifact_reasons)
            continue
        try:
            rows = [
                json.loads(line)
                for line in artifact_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            artifact_status = "fail"
            artifact_reasons.append(
                f"runtime audit artifact `{artifact_id}` is unreadable: {exc}"
            )
            artifacts[artifact_id] = {
                "status": artifact_status,
                "path": artifact["path"],
                "transition_name": artifact["transition_name"],
                "resource_kind": artifact["resource_kind"],
                "reason": artifact_reasons[0],
            }
            reasons.extend(artifact_reasons)
            continue
        matching_row = next(
            (
                row
                for row in rows
                if isinstance(row, Mapping)
                and row.get("transition_name") == artifact["transition_name"]
                and row.get("resource_kind") == artifact["resource_kind"]
            ),
            None,
        )
        if matching_row is None:
            artifact_status = "fail"
            artifact_reasons.append(
                f"runtime audit artifact `{artifact_id}` does not contain the declared transition identity"
            )
        artifacts[artifact_id] = {
            "status": artifact_status,
            "path": artifact["path"],
            "transition_name": artifact["transition_name"],
            "resource_kind": artifact["resource_kind"],
            **({"reasons": artifact_reasons} if artifact_reasons else {}),
        }
        reasons.extend(artifact_reasons)
    return {
        "status": "fail" if reasons else "pass",
        "artifacts": artifacts,
        **({"reason": reasons[0], "reasons": reasons} if reasons else {}),
    }


def _validated_design_delta_g8_deleted_rows(
    *,
    target: ParityTarget,
    g8_deletion_evidence: Mapping[str, Any] | None,
    required_rows: Sequence[str],
) -> tuple[set[str], list[str]]:
    reasons: list[str] = []
    if g8_deletion_evidence is None:
        return set(), ["missing g8_deletion_evidence compile artifact"]
    if g8_deletion_evidence.get("schema_version") != DESIGN_DELTA_G8_DELETION_EVIDENCE_SCHEMA_VERSION:
        reasons.append("g8_deletion_evidence compile artifact has wrong schema_version")
    if g8_deletion_evidence.get("workflow_family") != target.workflow_family:
        reasons.append("g8_deletion_evidence compile artifact does not match target workflow_family")
    if g8_deletion_evidence.get("status") != "pass":
        reasons.append("g8_deletion_evidence compile artifact is not passing")
    removed_manifest_rows = g8_deletion_evidence.get("removed_manifest_rows")
    if not isinstance(removed_manifest_rows, list) or not all(
        isinstance(row_name, str) and row_name for row_name in removed_manifest_rows
    ):
        reasons.append("g8_deletion_evidence compile artifact does not declare removed_manifest_rows")
        return set(), reasons
    removed_registry_heads = g8_deletion_evidence.get("removed_registry_heads")
    if not isinstance(removed_registry_heads, list) or not all(
        isinstance(head_name, str) and head_name for head_name in removed_registry_heads
    ):
        reasons.append("g8_deletion_evidence compile artifact does not declare removed_registry_heads")
    else:
        missing_removed_heads = sorted(
            head_name
            for head_name in DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS
            if head_name not in removed_registry_heads
        )
        if missing_removed_heads:
            reasons.append(
                "g8_deletion_evidence compile artifact is missing deleted registry heads: "
                + ", ".join(missing_removed_heads)
            )
    hook_surface_delta = g8_deletion_evidence.get("hook_surface_delta")
    if not isinstance(hook_surface_delta, Mapping):
        reasons.append("g8_deletion_evidence compile artifact does not declare hook_surface_delta")
    else:
        imported_only_registry_heads = hook_surface_delta.get("imported_only_registry_heads")
        if not isinstance(imported_only_registry_heads, list) or not all(
            isinstance(head_name, str) and head_name for head_name in imported_only_registry_heads
        ):
            reasons.append(
                "g8_deletion_evidence compile artifact does not declare imported_only_registry_heads"
            )
        else:
            missing_imported_only_heads = sorted(
                head_name
                for head_name in DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS
                if head_name not in imported_only_registry_heads
            )
            if missing_imported_only_heads:
                reasons.append(
                    "g8_deletion_evidence compile artifact is missing imported-only registry heads: "
                    + ", ".join(missing_imported_only_heads)
                )
    removed_rows = {row_name for row_name in removed_manifest_rows}
    missing_required_rows = sorted(row_name for row_name in required_rows if row_name not in removed_rows)
    if missing_required_rows:
        reasons.append(
            "g8_deletion_evidence compile artifact is missing deleted rows: "
            + ", ".join(missing_required_rows)
    )
    return removed_rows, reasons


def _build_root_from_compile_payload(
    compile_payload: Mapping[str, Any] | None,
) -> Path | None:
    if isinstance(compile_payload, Mapping) and isinstance(compile_payload.get("build_root"), str):
        return Path(str(compile_payload["build_root"]))
    return None


def _projection_deleted_helper_live_lineage(
    *,
    build_manifest: Mapping[str, Any] | None,
    build_root: Path | None,
    repo_root: Path,
) -> tuple[set[str], list[str]]:
    reasons: list[str] = []
    source_map = _load_compile_artifact_json(
        artifact_name="source_map",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    core_workflow_ast = _load_compile_artifact_json(
        artifact_name="core_workflow_ast",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if source_map is None:
        reasons.append(
            "missing source_map compile artifact needed for deleted projection helper lineage"
        )
    if core_workflow_ast is None:
        reasons.append(
            "missing core_workflow_ast compile artifact needed for deleted projection helper lineage"
        )
    live_names: set[str] = set()
    if isinstance(source_map, Mapping):
        workflows = source_map.get("workflows")
        if not isinstance(workflows, Mapping):
            reasons.append(
                "source_map compile artifact does not contain workflow lineage for deleted projection helpers"
            )
        else:
            for workflow_payload in workflows.values():
                if not isinstance(workflow_payload, Mapping):
                    continue
                command_boundaries = workflow_payload.get("command_boundaries")
                if not isinstance(command_boundaries, list):
                    continue
                for boundary in command_boundaries:
                    if not isinstance(boundary, Mapping):
                        continue
                    boundary_name = boundary.get("adapter_name") or boundary.get("command_name")
                    if isinstance(boundary_name, str) and boundary_name:
                        live_names.add(boundary_name)
    if isinstance(core_workflow_ast, Mapping):
        live_names.update(_core_ast_boundary_names(core_workflow_ast))
    return live_names, reasons


def _core_ast_boundary_names(node: object) -> set[str]:
    names: set[str] = set()
    if isinstance(node, Mapping):
        for key in ("adapter_name", "command_name"):
            value = node.get(key)
            if isinstance(value, str) and value:
                names.add(value)
        for value in node.values():
            names.update(_core_ast_boundary_names(value))
    elif isinstance(node, list):
        for item in node:
            names.update(_core_ast_boundary_names(item))
    return names


def _projection_retirement_parity_evidence(
    *,
    target: ParityTarget,
    compile_payload: Mapping[str, Any] | None = None,
    build_manifest: Mapping[str, Any] | None = None,
    adapter_census: Mapping[str, Any] | None = None,
    g8_deletion_evidence: Mapping[str, Any] | None = None,
    repo_root: Path,
) -> dict[str, object]:
    artifacts = [
        artifact
        for artifact in target.family_evidence_artifacts
        if artifact.get("evidence_role") == "projection_retirement_parity"
    ]
    if not artifacts:
        return {
            "status": "fail",
            "reason": "target does not declare projection_retirement_parity family_evidence_artifacts",
        }
    results: dict[str, object] = {}
    reasons: list[str] = []
    build_root = _build_root_from_compile_payload(compile_payload)
    for artifact in artifacts:
        artifact_id = str(artifact["artifact_id"])
        artifact_path = repo_root / str(artifact["path"])
        declared_schema_version = str(artifact["schema_version"])
        artifact_status = "pass"
        artifact_reasons: list[str] = []
        adapter_states: dict[str, object] = {}
        payload: Mapping[str, Any] | None = None
        if not artifact_path.exists():
            artifact_status = "fail"
            artifact_reasons.append(f"missing family evidence artifact `{artifact_id}`")
        else:
            try:
                loaded = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` is unreadable: {exc}"
                )
            else:
                if not isinstance(loaded, Mapping):
                    artifact_status = "fail"
                    artifact_reasons.append(
                        f"family evidence artifact `{artifact_id}` must be a JSON object"
                    )
                else:
                    payload = loaded
        if payload is not None:
            if payload.get("schema_version") != declared_schema_version:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` has wrong schema_version"
                )
            if payload.get("artifact_id") != artifact_id:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not report its declared artifact_id"
                )
            if payload.get("workflow_family") != target.workflow_family:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not match workflow_family `{target.workflow_family}`"
                )
            if payload.get("overall_status") != "pass" or payload.get("all_passed") is not True:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not record a passing dual-run result"
                )
            adapters = payload.get("adapters")
            if not isinstance(adapters, Mapping) or not adapters:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not declare adapter results"
                )
            elif adapter_census is None:
                artifact_status = "fail"
                artifact_reasons.append("missing adapter_census compile artifact")
            else:
                if adapter_census.get("workflow_family") != target.workflow_family:
                    artifact_status = "fail"
                    artifact_reasons.append(
                        "adapter_census compile artifact does not match target workflow_family"
                    )
                rows = adapter_census.get("rows")
                if not isinstance(rows, list):
                    artifact_status = "fail"
                    artifact_reasons.append("adapter_census compile artifact does not contain row data")
                else:
                    rows_by_name = {
                        str(row.get("binding_name")): row
                        for row in rows
                        if isinstance(row, Mapping) and isinstance(row.get("binding_name"), str)
                    }
                    missing_adapter_names = [
                        adapter_name
                        for adapter_name in adapters
                        if isinstance(adapter_name, str) and adapter_name not in rows_by_name
                    ]
                    deleted_rows: set[str] = set()
                    deletion_reasons: list[str] = []
                    if missing_adapter_names:
                        deleted_rows, deletion_reasons = _validated_design_delta_g8_deleted_rows(
                            target=target,
                            g8_deletion_evidence=g8_deletion_evidence,
                            required_rows=missing_adapter_names,
                        )
                    deleted_live_lineage, deleted_lineage_reasons = (
                        _projection_deleted_helper_live_lineage(
                            build_manifest=build_manifest,
                            build_root=build_root,
                            repo_root=repo_root,
                        )
                        if missing_adapter_names
                        else (set(), [])
                    )
                    if deletion_reasons:
                        artifact_status = "fail"
                        artifact_reasons.extend(deletion_reasons)
                    if deleted_lineage_reasons:
                        artifact_status = "fail"
                        artifact_reasons.extend(deleted_lineage_reasons)
                    for adapter_name in adapters:
                        if not isinstance(adapter_name, str):
                            artifact_status = "fail"
                            artifact_reasons.append(
                                f"family evidence artifact `{artifact_id}` uses a non-string adapter name"
                            )
                            continue
                        row = rows_by_name.get(adapter_name)
                        if row is None:
                            deleted_reason: str | None = None
                            if g8_deletion_evidence is None:
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` missing from "
                                    "adapter_census and g8_deletion_evidence"
                                )
                            elif (
                                g8_deletion_evidence.get("schema_version")
                                != DESIGN_DELTA_G8_DELETION_EVIDENCE_SCHEMA_VERSION
                            ):
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` has wrong "
                                    "g8_deletion_evidence schema_version"
                                )
                            elif g8_deletion_evidence.get("workflow_family") != target.workflow_family:
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` has wrong "
                                    "g8_deletion_evidence workflow_family"
                                )
                            elif g8_deletion_evidence.get("status") != "pass":
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` has non-passing "
                                    "g8_deletion_evidence"
                                )
                            elif adapter_name not in deleted_rows:
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` missing from "
                                    "adapter_census and g8_deletion_evidence"
                                )
                            elif deleted_lineage_reasons:
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` cannot be proven deleted "
                                    "because compile/source_map lineage evidence is unreadable or missing"
                                )
                            elif adapter_name in deleted_live_lineage:
                                deleted_reason = (
                                    f"projection adapter `{adapter_name}` still has live "
                                    "compile/source_map invocation lineage"
                                )
                            if deleted_reason is None:
                                adapter_states[adapter_name] = {
                                    "status": "pass",
                                    "retirement_state": "deleted_after_retirement",
                                    "evidence_source": "g8_deletion_evidence",
                                }
                                continue
                            artifact_status = "fail"
                            artifact_reasons.append(deleted_reason)
                            adapter_states[adapter_name] = {
                                "status": "fail",
                                "retirement_state": "invalid",
                                "evidence_source": "g8_deletion_evidence",
                                "reason": deleted_reason,
                            }
                            continue
                        invocation_sites = row.get("invocation_sites")
                        has_invocation_sites = isinstance(invocation_sites, list) and bool(
                            invocation_sites
                        )
                        adapter_reason: str | None = None
                        if row.get("retirement_status") != "retired":
                            adapter_reason = (
                                f"adapter `{adapter_name}` is not marked retired in adapter_census"
                            )
                        elif row.get("liveness") != "unreferenced" or has_invocation_sites:
                            adapter_reason = f"retired adapter `{adapter_name}` is still live"
                        if adapter_reason is None:
                            adapter_states[adapter_name] = {
                                "status": "pass",
                                "retirement_state": "retained_retired_unreferenced",
                                "evidence_source": "adapter_census",
                            }
                            continue
                        artifact_status = "fail"
                        artifact_reasons.append(adapter_reason)
                        adapter_states[adapter_name] = {
                            "status": "fail",
                            "retirement_state": "invalid",
                            "evidence_source": "adapter_census",
                            "reason": adapter_reason,
                        }
        results[artifact_id] = {
            "status": artifact_status,
            "path": str(artifact["path"]),
            "schema_version": declared_schema_version,
            **({"adapter_states": adapter_states} if adapter_states else {}),
            **({"reasons": artifact_reasons} if artifact_reasons else {}),
        }
        reasons.extend(artifact_reasons)
    return {
        "status": "fail" if reasons else "pass",
        "artifacts": results,
        **({"reason": reasons[0], "reasons": reasons} if reasons else {}),
    }


def _view_retirement_parity_evidence(
    *,
    target: ParityTarget,
    adapter_census: Mapping[str, Any] | None = None,
    g8_deletion_evidence: Mapping[str, Any] | None = None,
    repo_root: Path,
) -> dict[str, object]:
    artifacts = [
        artifact
        for artifact in target.family_evidence_artifacts
        if artifact.get("evidence_role") == "view_retirement_parity"
    ]
    if not artifacts:
        return {
            "status": "fail",
            "reason": "target does not declare view_retirement_parity family_evidence_artifacts",
        }
    results: dict[str, object] = {}
    reasons: list[str] = []
    deleted_rows, deletion_reasons = _validated_design_delta_g8_deleted_rows(
        target=target,
        g8_deletion_evidence=g8_deletion_evidence,
        required_rows=("finalize_lisp_frontend_drain_summary",),
    )
    reasons.extend(deletion_reasons)
    for artifact in artifacts:
        artifact_id = str(artifact["artifact_id"])
        artifact_path = repo_root / str(artifact["path"])
        declared_schema_version = str(artifact["schema_version"])
        artifact_status = "pass"
        artifact_reasons: list[str] = []
        payload: Mapping[str, Any] | None = None
        if not artifact_path.exists():
            artifact_status = "fail"
            artifact_reasons.append(f"missing family evidence artifact `{artifact_id}`")
        else:
            try:
                loaded = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` is unreadable: {exc}"
                )
            else:
                if not isinstance(loaded, Mapping):
                    artifact_status = "fail"
                    artifact_reasons.append(
                        f"family evidence artifact `{artifact_id}` must be a JSON object"
                    )
                else:
                    payload = loaded
        if payload is not None:
            if payload.get("schema_version") != declared_schema_version:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` has wrong schema_version"
                )
            if payload.get("artifact_id") != artifact_id:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not report its declared artifact_id"
                )
            if payload.get("workflow_family") != target.workflow_family:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not match workflow_family `{target.workflow_family}`"
                )
            if payload.get("overall_status") != "pass" or payload.get("all_passed") is not True:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not record a passing dual-run result"
                )
            adapters = payload.get("adapters")
            finalizer_payload = (
                adapters.get("finalize_lisp_frontend_drain_summary")
                if isinstance(adapters, Mapping)
                else None
            )
            if not isinstance(adapters, Mapping) or not adapters:
                artifact_status = "fail"
                artifact_reasons.append(
                    f"family evidence artifact `{artifact_id}` does not declare adapter results"
                )
            elif not isinstance(finalizer_payload, Mapping):
                artifact_status = "fail"
                artifact_reasons.append(
                    "family evidence artifact "
                    f"`{artifact_id}` does not declare `finalize_lisp_frontend_drain_summary`"
                )
            elif finalizer_payload.get("status") != "pass":
                artifact_status = "fail"
                artifact_reasons.append(
                    "family evidence artifact "
                    f"`{artifact_id}` does not record a passing finalizer adapter result"
                )
            if "finalize_lisp_frontend_drain_summary" not in deleted_rows:
                artifact_status = "fail"
                artifact_reasons.append(
                    "g8_deletion_evidence compile artifact does not record deleted finalizer row"
                )
            if adapter_census is not None:
                if adapter_census.get("workflow_family") != target.workflow_family:
                    artifact_status = "fail"
                    artifact_reasons.append(
                        "adapter_census compile artifact does not match target workflow_family"
                    )
                rows = adapter_census.get("rows")
                if not isinstance(rows, list):
                    artifact_status = "fail"
                    artifact_reasons.append("adapter_census compile artifact does not contain row data")
                else:
                    row = next(
                        (
                            candidate
                            for candidate in rows
                            if isinstance(candidate, Mapping)
                            and candidate.get("binding_name") == "finalize_lisp_frontend_drain_summary"
                        ),
                        None,
                    )
                    if row is not None:
                        artifact_status = "fail"
                        artifact_reasons.append(
                            "adapter_census compile artifact still contains `finalize_lisp_frontend_drain_summary`"
                        )
        results[artifact_id] = {
            "status": artifact_status,
            "path": str(artifact["path"]),
            "schema_version": declared_schema_version,
            **({"reasons": artifact_reasons} if artifact_reasons else {}),
        }
        reasons.extend(artifact_reasons)
    return {
        "status": "fail" if reasons else "pass",
        "artifacts": results,
        **({"reason": reasons[0], "reasons": reasons} if reasons else {}),
    }


def _public_private_boundary_parity_evidence(
    workflow_boundary: Mapping[str, Any] | None,
    *,
    boundary_authority_report: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    if boundary_authority_report is None:
        return {
            "status": "fail",
            "reason": "missing boundary_authority_report compile artifact",
        }
    workflows = boundary_authority_report.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        return {
            "status": "fail",
            "reason": "boundary_authority_report does not contain workflow rows",
        }
    if workflow_boundary is None:
        return {
            "status": "fail",
            "reason": "missing workflow boundary projection for entry workflow",
        }
    selected_workflow_name = workflow_boundary.get("workflow_name")
    if not isinstance(selected_workflow_name, str) or not selected_workflow_name:
        return {
            "status": "fail",
            "reason": "workflow boundary projection does not identify the entry workflow",
        }
    boundary_row = next(
        (
            row
            for row in workflows
            if isinstance(row, Mapping) and row.get("workflow_name") == selected_workflow_name
        ),
        None,
    )
    if not isinstance(boundary_row, Mapping):
        return {
            "status": "fail",
            "reason": "boundary_authority_report does not contain a selected workflow row",
        }
    reasons: list[str] = []
    unclassified = boundary_row.get("unclassified")
    if isinstance(unclassified, list) and unclassified:
        reasons.append("unclassified path-like boundary values remain")
    public_leaks = boundary_row.get("public_leaks")
    if isinstance(public_leaks, list) and public_leaks:
        reasons.append("public boundary still exposes private authority classes")
    if reasons:
        return {
            "status": "fail",
            "reasons": reasons,
            "unclassified": list(unclassified) if isinstance(unclassified, list) else [],
            "public_leaks": list(public_leaks) if isinstance(public_leaks, list) else [],
        }
    public_inputs = set(workflow_boundary.get("public_input_names", ()))
    explicitly_public = {
        name
        for name in boundary_row.get("public_authored", ())
        if isinstance(name, str)
    }
    always_forbidden_inputs = {
        "phase-ctx",
        "drain-ctx",
        "selection_bundle_path",
        "run_state_path",
        "state_root",
    }
    legacy_compatibility_inputs = {
        "manifest_path",
        "architecture_bundle_path",
        "progress_ledger_path",
    }
    exposed_forbidden = sorted(
        name
        for name in public_inputs
        if (
            name in always_forbidden_inputs
            or str(name).startswith("__write_root__")
            or (name in legacy_compatibility_inputs and name not in explicitly_public)
        )
    )
    if exposed_forbidden:
        return {
            "status": "fail",
            "exposed_forbidden_public_inputs": exposed_forbidden,
        }
    return {
        "status": "pass",
        "public_input_count": len(public_inputs),
        "private_runtime_context_binding_count": len(
            workflow_boundary.get("private_runtime_context_bindings", ())
        ),
        "private_managed_write_root_count": len(
            workflow_boundary.get("private_managed_write_root_inputs", ())
        ),
        "private_compatibility_bridge_count": len(
            workflow_boundary.get("private_compatibility_bridge_inputs", ())
        ),
    }


def _boundary_artifact_justification_evidence(
    *,
    target: ParityTarget,
    compile_artifacts: Mapping[str, Any],
    workflow_boundary: Mapping[str, Any] | None,
    route_identity: Mapping[str, Any],
) -> dict[str, object]:
    reasons: list[str] = []
    boundary_records: list[dict[str, object]] = []
    artifact_records: list[dict[str, object]] = []
    common = {
        "readiness_label": route_identity.get("readiness_label"),
        "route": route_identity.get("lowering_route"),
        "schema_version": route_identity.get("lowering_schema_version"),
    }

    if workflow_boundary is None:
        reasons.append("missing workflow boundary projection for entry workflow")
    else:
        boundary_records.append(
            {
                "boundary_id": workflow_boundary.get("workflow_name") or target.entry_workflow,
                "reason": "public_boundary_identity",
                "parity_constrained": bool(
                    workflow_boundary.get("private_compatibility_bridge_inputs")
                    or workflow_boundary.get("private_managed_write_root_inputs")
                ),
                **common,
            }
        )

    allowed_reasons = {
        "public_boundary_identity",
        "parity_comparison",
        "prerequisite_compile_evidence",
        "legacy_consumption",
        "cross_run_durability",
    }
    required_artifacts = _require_report_mapping(compile_artifacts, "required")
    optional_artifacts = _require_report_mapping(compile_artifacts, "optional")
    for artifact_name, artifact in {
        **dict(required_artifacts),
        **dict(optional_artifacts),
    }.items():
        if not isinstance(artifact, Mapping):
            continue
        if _status(artifact) != "pass":
            if artifact_name in required_artifacts:
                reasons.append(f"required artifact `{artifact_name}` lacks passing justification target")
            continue
        if artifact_name in {
            "consumer_rendering_census_report",
            "typed_prompt_input_report",
            "entry_publication_report",
            "compatibility_bridge_report",
            "rendering_cleanup_report",
        }:
            reason = "prerequisite_compile_evidence"
        else:
            reason = (
                "parity_comparison"
                if artifact_name
                in {
                    "adapter_census",
                    "boundary_authority_report",
                    "value_flow_census_report",
                    "g8_deletion_evidence",
                    "core_workflow_ast",
                    "semantic_ir",
                    "source_map",
                    "workflow_boundary_projection",
                }
                else "cross_run_durability"
            )
        artifact_records.append(
            {
                "artifact_id": str(artifact_name),
                "path": artifact.get("path"),
                "reason": reason,
                "parity_constrained": reason
                in {"parity_comparison", "prerequisite_compile_evidence"},
                **common,
            }
        )
    if workflow_boundary is not None and not any(
        record.get("artifact_id") == "workflow_boundary_projection"
        for record in artifact_records
    ):
        artifact_records.append(
            {
                "artifact_id": "workflow_boundary_projection",
                "path": None,
                "reason": "parity_comparison",
                "parity_constrained": True,
                **common,
            }
        )
    if not artifact_records:
        reasons.append("no artifact justifications recorded")
    for record in (*boundary_records, *artifact_records):
        if record.get("reason") not in allowed_reasons:
            reasons.append(f"unsupported justification reason for `{record}`")
        if record.get("parity_constrained") is not True and record.get("reason") in {
            "parity_comparison",
            "prerequisite_compile_evidence",
        }:
            reasons.append(f"parity comparison record lacks parity_constrained label: `{record}`")
    return {
        "status": "fail" if reasons else "pass",
        "boundary_justifications": boundary_records,
        "artifact_justifications": artifact_records,
        **({"reasons": reasons} if reasons else {}),
    }


def _validate_evidence_freshness(
    report: Mapping[str, Any],
    *,
    evidence_freshness: Mapping[str, Any],
    repo_root: Path,
    fail_closed: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence_complete = True

    def mark_incomplete(message: str) -> None:
        nonlocal evidence_complete
        if fail_closed:
            raise ValueError(message)
        evidence_complete = False
        reasons.append(message)

    compile_evidence = _require_report_mapping(_require_report_mapping(report, "evidence"), "compile")
    compile_manifest_path = _string_or_none(compile_evidence.get("manifest_path")) or _string_or_none(
        evidence_freshness.get("compile_manifest_path")
    )
    if compile_manifest_path:
        if evidence_freshness.get("compile_manifest_path") != compile_manifest_path:
            raise ValueError("evidence_freshness.compile_manifest_path does not match current compile manifest path")
        compile_manifest_file = repo_root / compile_manifest_path
        if not compile_manifest_file.exists():
            mark_incomplete("missing compile manifest")
        else:
            expected_sha = _string_or_none(evidence_freshness.get("compile_manifest_sha256"))
            if not expected_sha:
                mark_incomplete("missing compile_manifest_sha256")
            elif expected_sha != _sha256_file(compile_manifest_file):
                raise ValueError("evidence_freshness.compile_manifest_sha256 does not match current compile manifest")
            compile_manifest = json.loads(compile_manifest_file.read_text(encoding="utf-8"))
            current_checksum = _string_or_none(compile_manifest.get("compiled_workflow_checksum"))
            if current_checksum:
                reported_checksum = _string_or_none(evidence_freshness.get("compiled_workflow_checksum"))
                if not reported_checksum:
                    mark_incomplete("missing compiled_workflow_checksum")
                elif reported_checksum != current_checksum:
                    raise ValueError("evidence_freshness.compiled_workflow_checksum does not match current compile evidence")

    required_artifacts = _require_report_mapping(evidence_freshness, "required_artifacts")
    current_required_artifacts = _require_report_mapping(_require_report_mapping(report, "compile_artifacts"), "required")
    for artifact_name, artifact_value in current_required_artifacts.items():
        artifact = _require_report_mapping(current_required_artifacts, artifact_name)
        current_path = _string_or_none(artifact.get("path"))
        current_status = _status(artifact)
        freshness_artifact = required_artifacts.get(artifact_name)
        if not isinstance(freshness_artifact, Mapping):
            mark_incomplete(f"missing freshness row for required artifact `{artifact_name}`")
            continue
        if freshness_artifact.get("path") != current_path:
            raise ValueError(f"required_artifacts.{artifact_name}.path does not match current required artifact path")
        if freshness_artifact.get("status") != current_status:
            raise ValueError(f"required_artifacts.{artifact_name}.status does not match current required artifact status")
        if current_path:
            current_file = repo_root / current_path
            if not current_file.exists():
                mark_incomplete(f"missing required artifact file `{artifact_name}`")
                continue
            expected_sha = _string_or_none(freshness_artifact.get("sha256"))
            if not expected_sha:
                mark_incomplete(f"missing required artifact digest `{artifact_name}`")
            elif expected_sha != _sha256_file(current_file):
                if artifact_name == "source_map":
                    mark_incomplete(
                        "required artifact `source_map` digest changed while compile "
                        "manifest identity remained stable"
                    )
                else:
                    raise ValueError(
                        f"required_artifacts.{artifact_name}.sha256 does not match current artifact"
                    )

    evidence_refs = _require_report_mapping(evidence_freshness, "evidence_refs")
    current_command_logs = _require_report_mapping(report, "command_logs")
    for role, raw_paths in current_command_logs.items():
        paths = _require_report_mapping(current_command_logs, str(role))
        freshness_role = evidence_refs.get(role)
        if not isinstance(freshness_role, Mapping):
            mark_incomplete(f"missing evidence freshness refs for `{role}`")
            continue
        for stream in ("stdout", "stderr"):
            current_path = _string_or_none(paths.get(stream))
            if not current_path:
                mark_incomplete(f"missing {stream} log path for `{role}`")
                continue
            current_file = repo_root / current_path
            stream_ref = freshness_role.get(stream)
            if not isinstance(stream_ref, Mapping):
                mark_incomplete(f"missing freshness ref for `{role}` {stream}")
                continue
            if stream_ref.get("path") != current_path:
                raise ValueError(f"evidence_refs.{role}.{stream}.path does not match current log path")
            if not current_file.exists():
                mark_incomplete(f"missing {stream} log for `{role}`")
                continue
            expected_sha = _string_or_none(stream_ref.get("sha256"))
            if not expected_sha:
                mark_incomplete(f"missing {stream} log digest for `{role}`")
            elif expected_sha != _sha256_file(current_file):
                raise ValueError(f"evidence_refs.{role}.{stream}.sha256 does not match current log")

    expected_runtime_audits = report.get("target_identity", {}).get("runtime_audit_artifacts", ())
    if isinstance(expected_runtime_audits, list) and expected_runtime_audits:
        freshness_runtime_audits = evidence_freshness.get("runtime_audit_artifacts")
        if not isinstance(freshness_runtime_audits, Mapping):
            mark_incomplete("missing runtime_audit_artifacts freshness")
        else:
            for artifact in expected_runtime_audits:
                if not isinstance(artifact, Mapping):
                    mark_incomplete("runtime_audit_artifacts target identity row is invalid")
                    continue
                artifact_id = _string_or_none(artifact.get("artifact_id"))
                artifact_path = _string_or_none(artifact.get("path"))
                if not artifact_id or not artifact_path:
                    mark_incomplete("runtime_audit_artifacts target identity row is incomplete")
                    continue
                freshness_artifact = freshness_runtime_audits.get(artifact_id)
                if not isinstance(freshness_artifact, Mapping):
                    mark_incomplete(f"missing runtime audit freshness row `{artifact_id}`")
                    continue
                if freshness_artifact.get("path") != artifact_path:
                    raise ValueError(
                        f"runtime_audit_artifacts.{artifact_id}.path does not match current target path"
                    )
                current_file = repo_root / artifact_path
                if not current_file.exists():
                    mark_incomplete(f"missing runtime audit artifact `{artifact_id}`")
                    continue
                expected_sha = _string_or_none(freshness_artifact.get("sha256"))
                if not expected_sha:
                    mark_incomplete(f"missing runtime audit artifact digest `{artifact_id}`")
                elif expected_sha != _sha256_file(current_file):
                    raise ValueError(
                        f"runtime_audit_artifacts.{artifact_id}.sha256 does not match current artifact"
                    )

    expected_family_artifacts = report.get("target_identity", {}).get("family_evidence_artifacts", ())
    if isinstance(expected_family_artifacts, list) and expected_family_artifacts:
        freshness_family_artifacts = evidence_freshness.get("family_evidence_artifacts")
        if not isinstance(freshness_family_artifacts, Mapping):
            mark_incomplete("missing family_evidence_artifacts freshness")
        else:
            for artifact in expected_family_artifacts:
                if not isinstance(artifact, Mapping):
                    mark_incomplete("family_evidence_artifacts target identity row is invalid")
                    continue
                artifact_id = _string_or_none(artifact.get("artifact_id"))
                artifact_path = _string_or_none(artifact.get("path"))
                if not artifact_id or not artifact_path:
                    mark_incomplete("family_evidence_artifacts target identity row is incomplete")
                    continue
                freshness_artifact = freshness_family_artifacts.get(artifact_id)
                if not isinstance(freshness_artifact, Mapping):
                    mark_incomplete(f"missing family evidence freshness row `{artifact_id}`")
                    continue
                if freshness_artifact.get("path") != artifact_path:
                    raise ValueError(
                        f"family_evidence_artifacts.{artifact_id}.path does not match current target path"
                    )
                current_file = repo_root / artifact_path
                if not current_file.exists():
                    mark_incomplete(f"missing family evidence artifact `{artifact_id}`")
                    continue
                expected_sha = _string_or_none(freshness_artifact.get("sha256"))
                if not expected_sha:
                    mark_incomplete(f"missing family evidence artifact digest `{artifact_id}`")
                elif expected_sha != _sha256_file(current_file):
                    raise ValueError(
                        f"family_evidence_artifacts.{artifact_id}.sha256 does not match current artifact"
                    )

    return evidence_complete, reasons


def _validate_required_evidence_completeness(
    report: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence_complete = True

    def mark_incomplete(message: str) -> None:
        nonlocal evidence_complete
        evidence_complete = False
        reasons.append(message)

    evidence = _require_report_mapping(report, "evidence")
    for role in REQUIRED_EVIDENCE_ROLES:
        if role not in evidence:
            mark_incomplete(f"missing required evidence role `{role}`")

    compile_artifacts = _require_report_mapping(report, "compile_artifacts")
    required_artifacts = _require_report_mapping(compile_artifacts, "required")
    for artifact_name, artifact_value in required_artifacts.items():
        artifact = _require_report_mapping(required_artifacts, artifact_name)
        if _status(artifact) != "pass":
            mark_incomplete(f"required compile artifact `{artifact_name}` is not passing")

    target_identity = _require_report_mapping(report, "target_identity")
    required_family_roles = target_identity.get("required_family_evidence_roles", ())
    if isinstance(required_family_roles, list) and required_family_roles:
        route_identity = report.get("route_identity")
        if not isinstance(route_identity, Mapping):
            mark_incomplete("missing route_identity for parent-family evidence")
        else:
            for field_name in ("readiness_label", "lowering_route", "lowering_schema_version"):
                if route_identity.get(field_name) != target_identity.get(field_name):
                    mark_incomplete(f"route_identity.{field_name} does not match target")
        for role in required_family_roles:
            role_evidence = evidence.get(role)
            if not isinstance(role_evidence, Mapping):
                mark_incomplete(f"missing parent-family evidence role `{role}`")
            elif _status(role_evidence) != "pass":
                mark_incomplete(f"parent-family evidence role `{role}` is not passing")

    return evidence_complete, reasons


def _require_exact_mapping_match(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
) -> None:
    actual_keys = set(actual.keys())
    expected_keys = set(expected.keys())
    extra_keys = sorted(actual_keys - expected_keys)
    if extra_keys:
        raise ValueError(f"{label} contains unexpected keys: {', '.join(extra_keys)}")
    missing_keys = sorted(expected_keys - actual_keys)
    if missing_keys:
        raise ValueError(f"{label} is missing keys: {', '.join(missing_keys)}")
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            raise ValueError(f"{label}.{key} does not match current selected target")


def _require_report_contract(report: Mapping[str, Any]) -> None:
    for field_name in REQUIRED_REPORT_STRING_FIELDS:
        _require_string(report, field_name)
    _require_non_empty_string_list(report, "generated_by")
    for field_name in REQUIRED_REPORT_OBJECT_LIST_FIELDS:
        _require_report_object_list(report, field_name)
    for field_name in REQUIRED_REPORT_MAPPING_FIELDS:
        _require_report_mapping(report, field_name)
    if not isinstance(report.get("non_regressive"), bool):
        raise ValueError("report field `non_regressive` must be a boolean")


def _gate_row_passes(row: ValidatedGateRow, *, gate_mode: str) -> bool:
    base_pass = row.report_valid and row.evidence_complete and row.non_regressive
    if gate_mode == "advisory":
        return True
    if gate_mode == "require_non_regressive":
        return base_pass
    if gate_mode == "require_promotable":
        return base_pass and row.eligible_for_primary_surface
    raise ValueError(f"unknown gate mode `{gate_mode}`")


def _parse_command_spec(*, workflow_family: str, role: str, raw_value: Any) -> EvidenceCommand:
    if role in {"dry_run", "smoke_or_integration"} and isinstance(raw_value, Mapping):
        argv = raw_value.get("argv")
        waiver = raw_value.get("waiver")
        if argv is None and waiver is None:
            raise ValueError(f"`{workflow_family}` {role} must declare argv or waiver")
        normalized_argv = None if argv is None else tuple(_validate_argv(argv, role=role, workflow_family=workflow_family))
        if waiver is not None and not _waiver_is_valid(waiver, today=date.min, require_targeted_evidence=True):
            raise ValueError(f"`{workflow_family}` {role} waiver is malformed")
        return EvidenceCommand(argv=normalized_argv, waiver=waiver)

    return EvidenceCommand(
        argv=tuple(_validate_argv(raw_value, role=role, workflow_family=workflow_family)),
        waiver=None,
    )


def _validate_argv(raw_argv: Any, *, role: str, workflow_family: str) -> list[str]:
    if isinstance(raw_argv, str):
        raise ValueError(f"`{workflow_family}` {role} command must be argv, not a shell string")
    if not isinstance(raw_argv, list) or not raw_argv:
        raise ValueError(f"`{workflow_family}` {role} command must be a non-empty argv array")
    argv: list[str] = []
    for arg in raw_argv:
        if not isinstance(arg, str) or not arg:
            raise ValueError(f"`{workflow_family}` {role} command argv must contain non-empty strings")
        if "__write_root__" in arg:
            raise ValueError(
                f"`{workflow_family}` {role} command may not expose compiler-owned hidden managed write roots such as `__write_root__...`"
            )
        argv.append(arg)
    return argv


def _run_command(
    command: EvidenceCommand,
    *,
    role: str,
    repo_root: Path,
    stdout_log: Path,
    stderr_log: Path,
) -> CommandOutcome:
    started = time.perf_counter()
    if command.argv is None:
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return CommandOutcome(
            status="waived",
            argv=None,
            exit_code=None,
            elapsed_seconds=time.perf_counter() - started,
            stdout="",
            stderr="",
            waiver=command.waiver,
        )

    try:
        completed = subprocess.run(
            command.argv,
            cwd=repo_root,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
    except OSError as exc:
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        exit_code = 1

    stdout_log.write_text(stdout, encoding="utf-8")
    stderr_log.write_text(stderr, encoding="utf-8")
    return CommandOutcome(
        status="pass" if exit_code == 0 else "fail",
        argv=command.argv,
        exit_code=exit_code,
        elapsed_seconds=time.perf_counter() - started,
        stdout=stdout,
        stderr=stderr,
        waiver=command.waiver,
    )


def _load_compile_outputs(stdout: str, repo_root: Path) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None, None
    build_root_raw = payload.get("build_root")
    if not isinstance(build_root_raw, str):
        return payload, None
    manifest_path = Path(build_root_raw) / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload, None
    return payload, manifest


def _recover_compile_outputs_from_failed_conformance(
    *,
    target: ParityTarget,
    stderr: str,
    repo_root: Path,
    preexisting_manifests: Mapping[Path, tuple[int, int, int]] | None = None,
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    if "reference_family_conformance_invalid" not in stderr:
        return None, None

    build_root_parent = repo_root / ".orchestrate" / "build"
    if not build_root_parent.exists():
        return None, None

    candidate_path = (repo_root / target.candidate).resolve()
    required_artifacts = tuple(
        artifact_name
        for artifact_name in target.compile_artifacts["required"]
        if artifact_name in {"core_workflow_ast", "semantic_ir", "source_map"}
    )

    manifests = sorted(
        build_root_parent.glob("*/manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests:
        if not _manifest_was_updated_after_compile_attempt(
            manifest_path,
            preexisting_manifests=preexisting_manifests,
        ):
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        source_path = manifest.get("source_path")
        entry_workflow = manifest.get("entry_workflow")
        if not isinstance(source_path, str) or Path(source_path).resolve() != candidate_path:
            continue
        if entry_workflow != target.entry_workflow:
            continue
        source_sha256 = _string_or_none(manifest.get("source_sha256"))
        if not source_sha256 or source_sha256 != _sha256_file(candidate_path):
            continue
        artifact_paths = manifest.get("artifact_paths")
        if not isinstance(artifact_paths, Mapping):
            continue
        if any(
            not isinstance(artifact_paths.get(artifact_name), str)
            or not (repo_root / str(artifact_paths[artifact_name])).exists()
            for artifact_name in required_artifacts
        ):
            continue
        build_root = manifest_path.parent
        return {"build_root": str(build_root)}, manifest
    return None, None


def _snapshot_build_manifests(repo_root: Path) -> dict[Path, tuple[int, int, int]]:
    build_root_parent = repo_root / ".orchestrate" / "build"
    if not build_root_parent.exists():
        return {}
    snapshot: dict[Path, tuple[int, int, int]] = {}
    for manifest_path in build_root_parent.glob("*/manifest.json"):
        try:
            stat_result = manifest_path.stat()
        except OSError:
            continue
        snapshot[manifest_path.resolve()] = (
            stat_result.st_mtime_ns,
            stat_result.st_ctime_ns,
            stat_result.st_size,
        )
    return snapshot


def _manifest_was_updated_after_compile_attempt(
    manifest_path: Path,
    *,
    preexisting_manifests: Mapping[Path, tuple[int, int, int]] | None,
) -> bool:
    try:
        stat_result = manifest_path.stat()
    except OSError:
        return False
    current_signature = (
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
        stat_result.st_size,
    )
    if preexisting_manifests is None:
        return True
    previous_signature = preexisting_manifests.get(manifest_path.resolve())
    if previous_signature is None:
        return True
    return current_signature != previous_signature


def _shared_validation_evidence(build_manifest: Mapping[str, Any] | None) -> dict[str, object]:
    if build_manifest is None:
        return {"status": "fail"}
    return {
        "status": "pass" if build_manifest.get("shared_validation_status") == "validated" else "fail",
    }


def _compile_artifact_report(
    *,
    target: ParityTarget,
    build_manifest: Mapping[str, Any] | None,
    build_root: Path | None,
    repo_root: Path,
) -> dict[str, object]:
    required: dict[str, object] = {}
    optional: dict[str, object] = {}
    artifact_paths = dict(build_manifest.get("artifact_paths", {})) if build_manifest else {}
    artifact_status = dict(build_manifest.get("artifact_status", {})) if build_manifest else {}
    debug_yaml_status = build_manifest.get("debug_yaml_status") if build_manifest else None

    for artifact_name in target.compile_artifacts["required"]:
        path = _report_artifact_path(artifact_paths.get(artifact_name), build_root=build_root, repo_root=repo_root)
        if artifact_name == "value_flow_census_report":
            required[artifact_name] = _value_flow_census_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        if artifact_name == "consumer_rendering_census_report":
            required[artifact_name] = _consumer_rendering_census_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        if artifact_name == "typed_prompt_input_report":
            required[artifact_name] = _typed_prompt_input_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        if artifact_name == "entry_publication_report":
            required[artifact_name] = _entry_publication_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        if artifact_name == "compatibility_bridge_report":
            required[artifact_name] = _compatibility_bridge_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        if artifact_name == "rendering_cleanup_report":
            required[artifact_name] = _rendering_cleanup_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        if artifact_name == "transition_authoring_report":
            required[artifact_name] = _transition_authoring_artifact_status(
                target=target,
                path=path,
                build_root=build_root,
                build_manifest=build_manifest,
                repo_root=repo_root,
            )
            continue
        raw_status = _artifact_raw_status(
            artifact_name,
            path=path,
            artifact_status=artifact_status,
            debug_yaml_status=debug_yaml_status,
        )
        required[artifact_name] = {
            "status": "pass" if path and raw_status in PASSING_ARTIFACT_STATUSES else "missing",
            "path": path,
        }

    for artifact_name in target.compile_artifacts["optional"]:
        path = _report_artifact_path(artifact_paths.get(artifact_name), build_root=build_root, repo_root=repo_root)
        raw_status = _artifact_raw_status(
            artifact_name,
            path=path,
            artifact_status=artifact_status,
            debug_yaml_status=debug_yaml_status,
        )
        optional[artifact_name] = {
            "status": "pass" if path and raw_status in PASSING_ARTIFACT_STATUSES else "not_implemented",
            "path": path,
        }

    return {"required": required, "optional": optional}


def _value_flow_census_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="value_flow_census_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "value_flow_census_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("workflow_family") != target.workflow_family:
        reasons.append("workflow_family mismatch")
    if payload.get("status") != "pass":
        reasons.append("status is not pass")
    workflow_rows = payload.get("workflow_rows")
    if not isinstance(workflow_rows, list):
        reasons.append("workflow_rows missing")
    else:
        workflow_surfaces = {
            row.get("workflow_surface")
            for row in workflow_rows
            if isinstance(row, Mapping)
        }
        if target.entry_workflow not in workflow_surfaces:
            reasons.append("selected workflow surface is missing")
        declared_workflow_surfaces = payload.get("declared_workflow_surfaces")
        if not isinstance(declared_workflow_surfaces, list) or not all(
            isinstance(item, str) and item for item in declared_workflow_surfaces
        ):
            reasons.append("declared_workflow_surfaces missing")
        else:
            for workflow_surface in declared_workflow_surfaces:
                if workflow_surface not in workflow_surfaces:
                    reasons.append(
                        f"declared workflow surface is missing: {workflow_surface}"
                    )
    for bucket_name in (
        "missing_rows",
        "stale_rows",
        "invalid_rows",
        "extra_compiled_rows",
    ):
        bucket = payload.get(bucket_name)
        if isinstance(bucket, list) and bucket:
            reasons.append(f"{bucket_name} present")
    for forbidden_key in ("track_r_status", "track_c_status", "track_completion"):
        if forbidden_key in payload:
            reasons.append(f"forbidden track completion field `{forbidden_key}` present")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _consumer_rendering_census_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="consumer_rendering_census_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "consumer_rendering_census_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("workflow_family") != target.workflow_family:
        reasons.append("workflow_family mismatch")
    if payload.get("status") != "pass":
        reasons.append("prerequisite compile evidence status is not pass")
    checked_manifest = payload.get("checked_manifest")
    if not isinstance(checked_manifest, Mapping):
        reasons.append("checked_manifest missing")
    source_census = payload.get("source_census")
    if not isinstance(source_census, Mapping):
        reasons.append("source_census missing")
    for bucket_name in ("missing_rows", "stale_rows", "invalid_rows"):
        bucket = payload.get(bucket_name)
        if isinstance(bucket, list) and bucket:
            reasons.append(f"{bucket_name} present")
    for forbidden_key in ("track_r_status", "track_c_status", "track_completion"):
        if forbidden_key in payload:
            reasons.append(f"forbidden track completion field `{forbidden_key}` present")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _typed_prompt_input_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="typed_prompt_input_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "typed_prompt_input_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("workflow_family") != target.workflow_family:
        reasons.append("workflow_family mismatch")
    if payload.get("status") != "pass":
        reasons.append("prerequisite compile evidence status is not pass")
    selected_rows = payload.get("selected_rows")
    if not isinstance(selected_rows, list) or not selected_rows:
        reasons.append("selected_rows missing")
    for bucket_name in ("missing_rows", "stale_rows", "invalid_rows"):
        bucket = payload.get(bucket_name)
        if isinstance(bucket, list) and bucket:
            reasons.append(f"{bucket_name} present")
    for forbidden_key in ("track_r_status", "track_c_status", "track_completion"):
        if forbidden_key in payload:
            reasons.append(f"forbidden track completion field `{forbidden_key}` present")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _entry_publication_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="entry_publication_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "entry_publication_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("status") != "pass":
        reasons.append("prerequisite compile evidence status is not pass")
    selected_rows = payload.get("selected_c0_rows")
    if not isinstance(selected_rows, list) or not selected_rows:
        reasons.append("selected_c0_rows missing")
    for forbidden_key in ("track_r_status", "track_c_status", "track_completion"):
        if forbidden_key in payload:
            reasons.append(f"forbidden track completion field `{forbidden_key}` present")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _compatibility_bridge_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="compatibility_bridge_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "compatibility_bridge_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("workflow_family") != target.workflow_family:
        reasons.append("workflow_family mismatch")
    if payload.get("status") != "pass":
        reasons.append("prerequisite compile evidence status is not pass")
    selected_rows = payload.get("selected_c0_rows")
    if not isinstance(selected_rows, list) or not selected_rows:
        reasons.append("selected_c0_rows missing")
    blocked_bridges = payload.get("blocked_bridges")
    if not isinstance(blocked_bridges, list):
        reasons.append("blocked_bridges missing")
    contract_isolation = payload.get("contract_isolation")
    expected_contract_checks = (
        "workflow_signature_unchanged",
        "call_contract_unchanged",
        "boundary_projection_public_inputs_unchanged",
        "typed_steps_do_not_consume_bridge_views",
    )
    if not isinstance(contract_isolation, Mapping):
        reasons.append("contract_isolation missing")
    else:
        for check_name in expected_contract_checks:
            if contract_isolation.get(check_name) is not True:
                reasons.append(f"contract_isolation.{check_name} is not true")
    for forbidden_key in ("track_r_status", "track_c_status", "track_completion"):
        if forbidden_key in payload:
            reasons.append(f"forbidden track completion field `{forbidden_key}` present")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _rendering_cleanup_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="rendering_cleanup_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "rendering_cleanup_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("workflow_family") != target.workflow_family:
        reasons.append("workflow_family mismatch")
    if payload.get("status") != "pass":
        reasons.append("prerequisite compile evidence status is not pass")
    decision_counts = payload.get("decision_counts")
    if not isinstance(decision_counts, Mapping) or not decision_counts:
        reasons.append("decision_counts missing")
    selected_rows = payload.get("selected_rows")
    if not isinstance(selected_rows, list) or not selected_rows:
        reasons.append("selected_rows missing")
    cleanup_decisions = payload.get("cleanup_decisions")
    if not isinstance(cleanup_decisions, list) or not cleanup_decisions:
        reasons.append("cleanup_decisions missing")
    else:
        required_cleanup_fields = (
            "cleanup_id",
            "c0_row_id",
            "u0_row_id",
            "previous_track_c_decision",
            "cleanup_decision",
            "durability_before",
            "durability_after",
            "replacement_evidence",
            "compiled_liveness",
            "source_cleanup",
        )
        for row in cleanup_decisions:
            if not isinstance(row, Mapping):
                reasons.append("cleanup_decisions contains non-object rows")
                break
            missing = [
                field_name
                for field_name in required_cleanup_fields
                if field_name not in row
            ]
            if missing:
                reasons.append(
                    "cleanup_decisions row missing fields: " + ", ".join(missing)
                )
                break
            if not isinstance(row.get("replacement_evidence"), Mapping):
                reasons.append("cleanup_decisions replacement_evidence missing")
                break
            if not isinstance(row.get("compiled_liveness"), Mapping):
                reasons.append("cleanup_decisions compiled_liveness missing")
                break
            if not isinstance(row.get("source_cleanup"), Mapping):
                reasons.append("cleanup_decisions source_cleanup missing")
                break
            cleanup_decision = row.get("cleanup_decision")
            if cleanup_decision == "KEEP_TIMED_PUBLICATION" and not isinstance(
                row.get("timed_publication"), Mapping
            ):
                reasons.append("cleanup_decisions timed_publication missing")
                break
            if cleanup_decision == "KEPT_BLOCKED_COMPATIBILITY" and not isinstance(
                row.get("blocked_by"), Mapping
            ):
                reasons.append("cleanup_decisions blocked_by missing")
                break
    blocked_row_ids = payload.get("blocked_row_ids")
    if not isinstance(blocked_row_ids, list):
        reasons.append("blocked_row_ids missing")
    source_census = payload.get("source_census")
    if not isinstance(source_census, Mapping) or not source_census:
        reasons.append("source_census missing")
    prerequisite_reports = payload.get("prerequisite_reports")
    if not isinstance(prerequisite_reports, Mapping) or not prerequisite_reports:
        reasons.append("prerequisite_reports missing")
    durability_reconciliation = payload.get("durability_reconciliation")
    expected_durability_checks = (
        "prompt_rows_ephemeral",
        "durable_publications_state_layout_allocated",
        "durable_bridges_state_layout_allocated",
        "body_materialize_views_timed_only",
    )
    if not isinstance(durability_reconciliation, Mapping):
        reasons.append("durability_reconciliation missing")
    else:
        for check_name in expected_durability_checks:
            if durability_reconciliation.get(check_name) is not True:
                reasons.append(f"durability_reconciliation.{check_name} is not true")
    contract_isolation = payload.get("contract_isolation")
    expected_contract_checks = (
        "workflow_signature_unchanged",
        "typed_steps_do_not_consume_views",
        "prompt_views_not_published",
        "observability_views_not_semantic_outputs",
    )
    if not isinstance(contract_isolation, Mapping):
        reasons.append("contract_isolation missing")
    else:
        for check_name in expected_contract_checks:
            if contract_isolation.get(check_name) is not True:
                reasons.append(f"contract_isolation.{check_name} is not true")
    for forbidden_key in ("track_r_status", "track_c_status", "track_completion"):
        if forbidden_key in payload:
            reasons.append(f"forbidden track completion field `{forbidden_key}` present")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _transition_authoring_artifact_status(
    *,
    target: ParityTarget,
    path: str | None,
    build_root: Path | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    if path is None:
        return {"status": "missing", "path": None}
    payload = _load_compile_artifact_json(
        artifact_name="transition_authoring_report",
        build_manifest=build_manifest,
        build_root=build_root,
        repo_root=repo_root,
    )
    if payload is None:
        return {
            "status": "missing",
            "path": path,
            "reason": "transition_authoring_report is unreadable or absent",
        }
    reasons: list[str] = []
    if payload.get("workflow_family") != target.workflow_family:
        reasons.append("workflow_family mismatch")
    if payload.get("status") != "pass":
        reasons.append("transition authoring report status is not pass")
    compiled_origins = payload.get("compiled_origins")
    if not isinstance(compiled_origins, list) or not compiled_origins:
        reasons.append("compiled_origins missing")
    for field_name in (
        "ordinary_body_violations",
        "extra_origins",
        "stale_allowed_origins",
        "invalid_allowed_origins",
        "source_shape_violations",
    ):
        field_value = payload.get(field_name)
        if not isinstance(field_value, list):
            reasons.append(f"{field_name} missing")
        elif field_value:
            reasons.append(f"{field_name} is not empty")
    return {
        "status": "fail" if reasons else "pass",
        "path": path,
        **({"reason": "; ".join(reasons)} if reasons else {}),
    }


def _report_artifact_path(
    raw_path: str | None,
    *,
    build_root: Path | None,
    repo_root: Path,
) -> str | None:
    if raw_path is None:
        return None
    artifact_path = Path(raw_path)
    if artifact_path.is_absolute():
        return _relative_or_absolute_path(artifact_path, repo_root)
    if build_root is not None:
        artifact_path = build_root.parent.parent / artifact_path
        return _relative_or_absolute_path(artifact_path, repo_root)
    return raw_path


def _resolve_build_artifact_path(
    raw_path: str | None,
    *,
    build_root: Path | None,
    repo_root: Path,
) -> Path | None:
    if raw_path is None:
        return None
    artifact_path = Path(raw_path)
    if artifact_path.is_absolute():
        return artifact_path
    if build_root is not None:
        candidate = build_root / artifact_path
        if candidate.exists():
            return candidate
        candidate = build_root.parent.parent / artifact_path
        if candidate.exists():
            return candidate
    return repo_root / artifact_path


def _artifact_raw_status(
    artifact_name: str,
    *,
    path: str | None,
    artifact_status: Mapping[str, Any],
    debug_yaml_status: Any,
) -> str:
    if artifact_name == "expanded_debug_yaml":
        return str(debug_yaml_status or "not_requested")
    if artifact_name in artifact_status:
        return str(artifact_status[artifact_name])
    if path:
        return "emitted"
    return "missing"


def _primary_surface_for_report(report: Mapping[str, Any]) -> str:
    promotion = _require_report_mapping(report, "promotion_eligibility")
    return _primary_surface_for_non_regressive_and_eligibility(
        non_regressive=bool(report.get("non_regressive")),
        eligible_for_primary_surface=bool(promotion.get("eligible_for_primary_surface")),
    )


def _primary_surface_for_non_regressive_and_eligibility(
    *,
    non_regressive: bool,
    eligible_for_primary_surface: bool,
) -> str:
    if non_regressive and eligible_for_primary_surface:
        return "orc"
    return "yaml"


def _gate_primary_surface_for_row(row: ValidatedGateRow) -> str | None:
    if not row.report_valid or not row.evidence_complete or not row.non_regressive:
        return None
    return row.primary_surface


def _waiver_is_valid(
    waiver: Any,
    *,
    today: date,
    require_targeted_evidence: bool,
) -> bool:
    if not isinstance(waiver, Mapping):
        return False
    owner = _string_or_none(waiver.get("owner"))
    justification = _string_or_none(waiver.get("justification"))
    expiry = _string_or_none(waiver.get("expiry"))
    if not owner or not justification or not expiry:
        return False
    try:
        expiry_date = date.fromisoformat(expiry)
    except ValueError:
        return False
    if expiry_date < today:
        return False
    if require_targeted_evidence:
        targeted_evidence = waiver.get("targeted_evidence")
        if not isinstance(targeted_evidence, list) or not targeted_evidence:
            return False
        if not all(isinstance(item, str) and item for item in targeted_evidence):
            return False
    return True


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"`{key}` must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"`{key}` must be a non-empty string when provided")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"`{key}` must be an integer when provided")
    return value


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"`{key}` must be an object")
    return value


def _require_non_empty_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    values = _require_string_list(payload, key)
    if not values:
        raise ValueError(f"`{key}` must contain at least one string")
    return values


def _require_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"`{key}` must be an array of strings")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"`{key}` must be an array of non-empty strings")
    return list(value)


def _require_object_list(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"`{key}` must be an array of objects")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"`{key}` must be an array of objects")
    return list(value)


def _parse_runtime_audit_artifacts(
    payload: Mapping[str, Any],
    *,
    workflow_family: str,
) -> tuple[Mapping[str, str], ...]:
    raw_artifacts = payload.get("runtime_audit_artifacts")
    if raw_artifacts is None:
        return ()
    artifacts = _require_object_list(payload, "runtime_audit_artifacts")
    normalized: list[Mapping[str, str]] = []
    for artifact in artifacts:
        normalized.append(
            {
                "artifact_id": _require_string(artifact, "artifact_id"),
                "path": _require_string(artifact, "path"),
                "transition_name": _require_string(artifact, "transition_name"),
                "resource_kind": _require_string(artifact, "resource_kind"),
            }
        )
    return tuple(normalized)


def _parse_family_evidence_artifacts(
    payload: Mapping[str, Any],
    *,
    workflow_family: str,
) -> tuple[Mapping[str, object], ...]:
    raw_artifacts = payload.get("family_evidence_artifacts")
    if raw_artifacts is None:
        return ()
    artifacts = _require_object_list(payload, "family_evidence_artifacts")
    normalized: list[Mapping[str, object]] = []
    seen_ids: set[str] = set()
    for artifact in artifacts:
        artifact_id = _require_string(artifact, "artifact_id")
        if artifact_id in seen_ids:
            raise ValueError(
                f"family_evidence_artifacts duplicates artifact_id `{artifact_id}` for `{workflow_family}`"
            )
        seen_ids.add(artifact_id)
        normalized.append(
            {
                "artifact_id": artifact_id,
                "path": _require_string(artifact, "path"),
                "evidence_role": _require_string(artifact, "evidence_role"),
                "schema_version": _require_string(artifact, "schema_version"),
            }
        )
    return tuple(normalized)


def _require_report_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"report field `{key}` must be an object")
    return value


def _require_report_object_list(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"report field `{key}` must be an array of objects")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"report field `{key}` must be an array of objects")
    return list(value)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _status(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("status", "missing"))
    return "missing"


def _relative_path(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def _relative_or_absolute_path(path: Path, repo_root: Path) -> str:
    resolved_repo_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(resolved_repo_root))
    except ValueError:
        return str(resolved_path)
